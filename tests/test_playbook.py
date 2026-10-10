"""The Playbook: which rules were in force, and what was recorded under each.

The column this reads — `recommendations.strategy_config_version` — has been
written since the engine was built and read by nothing. That matters because a
threshold edit splits the evidence into halves that cannot be pooled, and the
halves look exactly like one continuous record once they are totalled. This is
the partition made visible.

What these tests establish
--------------------------
That the per-version counts partition the rows correctly, that a version with
no rows still appears, that the diff between versions points the right way, and
that the three states of `accepted_by_user` stay three.

What they do not establish
--------------------------
That any version's numbers *support* anything. Whether a version's CLV clears
the always-valid bound is `gate.py`'s question, asked of the actionable
population only, and nothing here second-guesses it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.playbook import (
    MIN_ROWS_TO_MEAN_ANYTHING,
    config_diff,
    config_versions,
    lessons,
    read_playbook,
)
from backend.store import db

NOW = 1_786_000_000_000


@pytest.fixture
def conn(tmp_path):
    connection = db.init_db(tmp_path / "playbook.db")
    connection.execute(
        "INSERT INTO kalshi_series (series_ticker, first_seen_ms, last_seen_ms) "
        "VALUES ('S', 0, 0)"
    )
    connection.execute(
        "INSERT INTO kalshi_events (event_ticker, series_ticker, first_seen_ms, "
        "last_seen_ms) VALUES ('E', 'S', 0, 0)"
    )
    for ticker in ("T1", "T2"):
        connection.execute(
            "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, "
            "first_seen_ms, last_seen_ms) VALUES (?, 'E', 'S', 0, 0)",
            (ticker,),
        )
    connection.commit()
    yield connection
    connection.close()


def add_version(conn, version, config, *, rationale="because", to_ms=None):
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "effective_to_ms, config_json, rationale, approved_by_user) "
        "VALUES (?, ?, ?, ?, ?, ?, 0)",
        (version, NOW, NOW, to_ms, json.dumps(config, sort_keys=True), rationale),
    )
    conn.commit()


def add_rec(
    conn, version, *, ticker="T1", suppressed=None, contracts=0, scored=False
):
    conn.execute(
        "INSERT INTO recommendations ("
        "created_ms, strategy_config_version, ticker, side, entry_ask_tenths, "
        "fair_probability, edge_tenths, fee_predicted, ev_net_dollars, "
        # `reference_contracts` mirrors `suggested_contracts`: these fixtures
        # stand for a record written at the reference profile, and the Playbook
        # screen counts `actionable` off the reference column so that comparing
        # two strategy versions cannot pick up a deposit change. ADR 0015.
        "kelly_fraction, suggested_contracts, reference_contracts, "
        "kalshi_quote_age_ms, "
        "odds_age_ms, suppressed_reason, reason_text, clv_scored_ms"
        ") VALUES (?, ?, ?, 'yes', 500, 0.5, 0, 0.01, 0.0, 0.0, ?, ?, 0, 0, ?, '', ?)",
        (NOW, version, ticker, contracts, contracts, suppressed,
         NOW if scored else None),
    )
    conn.commit()


class TestTheCountsPartitionTheRecord:
    def test_each_version_counts_only_its_own_rows(self, conn):
        add_version(conn, 1, {"max_odds_age_s": 900}, to_ms=NOW + 1)
        add_version(conn, 2, {"max_odds_age_s": 600})
        add_rec(conn, 1)
        add_rec(conn, 1)
        add_rec(conn, 2)

        by_version = {v["version"]: v for v in config_versions(conn)}
        assert by_version[1]["recommendations"] == 2
        assert by_version[2]["recommendations"] == 1

    def test_a_version_with_no_rows_still_appears(self, conn):
        """The most interesting row on the screen.

        A version that produced nothing is the one that shortened every
        neighbouring version's sample, and an INNER JOIN would delete exactly
        that evidence.
        """
        add_version(conn, 1, {"a": 1}, to_ms=NOW + 1)
        add_version(conn, 2, {"a": 2})
        add_rec(conn, 2)

        by_version = {v["version"]: v for v in config_versions(conn)}
        assert set(by_version) == {1, 2}
        assert by_version[1]["recommendations"] == 0
        assert by_version[1]["markets"] == 0

    def test_the_populations_are_not_the_same_number(self, conn):
        """Recommendations, unsuppressed and actionable must be able to differ.

        If a wrong query made all three equal, every version would look
        internally consistent and the screen would say nothing.
        """
        add_version(conn, 1, {"a": 1})
        add_rec(conn, 1, suppressed="stale_odds")
        add_rec(conn, 1, suppressed=None, contracts=0)
        add_rec(conn, 1, suppressed=None, contracts=5, scored=True)

        version = config_versions(conn)[0]
        assert version["recommendations"] == 3
        assert version["unsuppressed"] == 2
        assert version["actionable"] == 1
        assert version["clv_scored"] == 1

    def test_markets_counts_games_not_rows(self, conn):
        """One market polled repeatedly is one market.

        The row count measures uptime; this repo has a lesson about exactly
        that, and reporting them side by side is what keeps the distinction.
        """
        add_version(conn, 1, {"a": 1})
        for _ in range(5):
            add_rec(conn, 1, ticker="T1")
        add_rec(conn, 1, ticker="T2")

        version = config_versions(conn)[0]
        assert version["recommendations"] == 6
        assert version["markets"] == 2

    def test_a_thin_version_is_flagged_rather_than_filtered(self, conn):
        add_version(conn, 1, {"a": 1})
        add_rec(conn, 1)
        version = config_versions(conn)[0]
        assert version["recommendations"] == 1
        assert version["has_enough_to_say_anything"] is False
        assert MIN_ROWS_TO_MEAN_ANYTHING > 1


class TestCurrentIsReadFromTheColumn:
    def test_the_open_ended_version_is_the_current_one(self, conn):
        add_version(conn, 1, {"a": 1}, to_ms=NOW + 5)
        add_version(conn, 2, {"a": 2})
        by_version = {v["version"]: v for v in config_versions(conn)}
        assert by_version[2]["is_current"] is True
        assert by_version[1]["is_current"] is False

    def test_the_highest_version_is_not_assumed_current(self, conn):
        """A superseded row keeps its number, so ordering cannot answer this.

        After a rollback the highest version is closed and a lower one is open.
        Reading `effective_to_ms` gets it right; `max(version)` names the wrong
        one, and names it confidently.
        """
        add_version(conn, 1, {"a": 1})
        add_version(conn, 2, {"a": 2}, to_ms=NOW + 5)

        payload = read_playbook(conn)
        assert payload["current_version"] == 1


class TestTheDiffPointsForwards:
    def test_it_reports_the_change_in_the_right_direction(self, conn):
        add_version(conn, 1, {"max_odds_age_s": 900}, to_ms=NOW + 1)
        add_version(conn, 2, {"max_odds_age_s": 600})

        payload = read_playbook(conn)
        newest = payload["config_versions"][0]
        assert newest["version"] == 2
        assert newest["changed_from_previous"] == {
            "max_odds_age_s": {"from": 900, "to": 600}
        }

    def test_a_backwards_diff_would_be_a_different_answer(self):
        """The anchor, chosen where the wrong implementation differs.

        Versions arrive newest-first, so diffing against the *previous element*
        rather than the next one describes every change backwards — and renders
        perfectly either way. `from == to` would pass under both.
        """
        assert config_diff({"x": 1}, {"x": 2}) == {"x": {"from": 1, "to": 2}}
        assert config_diff({"x": 2}, {"x": 1}) == {"x": {"from": 2, "to": 1}}

    def test_a_deleted_setting_is_a_change(self):
        """A threshold that disappeared is exactly the edit worth seeing."""
        assert config_diff({"x": 1}, {}) == {"x": {"from": 1, "to": None}}
        assert config_diff({}, {"x": 1}) == {"x": {"from": None, "to": 1}}

    def test_the_oldest_version_has_nothing_to_diff_against(self, conn):
        add_version(conn, 1, {"a": 1})
        payload = read_playbook(conn)
        assert payload["config_versions"][-1]["changed_from_previous"] == {}


class TestUnreadableIsNotEmpty:
    def test_an_unparseable_config_is_none_not_an_empty_dict(self, conn):
        """`{}` would render as "a version with no settings", which is a claim.

        An unreadable one needs somebody to look; an empty one does not.
        """
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, "
            "effective_from_ms, config_json, rationale, approved_by_user) "
            "VALUES (1, ?, ?, 'not json', 'r', 0)",
            (NOW, NOW),
        )
        conn.commit()
        assert config_versions(conn)[0]["config"] is None


class TestLessonsKeepTheirThreeStates:
    def _add_lesson(self, conn, *, accepted, diff='{"x": 1}'):
        conn.execute(
            "INSERT INTO lessons (created_ms, title, body, evidence_json, "
            "sample_size, proposed_config_diff, accepted_by_user) "
            "VALUES (?, 't', 'b', NULL, 120, ?, ?)",
            (NOW, diff, accepted),
        )
        conn.commit()

    def test_undecided_rejected_and_accepted_stay_distinct(self, conn):
        self._add_lesson(conn, accepted=None)
        self._add_lesson(conn, accepted=0)
        self._add_lesson(conn, accepted=1)

        states = [entry["accepted_by_user"] for entry in lessons(conn)]
        # Identity, not equality. `0 == False` and `1 == True` in Python, so an
        # implementation that returned the raw integers would satisfy a
        # value comparison and lose the very distinction under test.
        assert sum(1 for s in states if s is None) == 1
        assert sum(1 for s in states if s is False) == 1
        assert sum(1 for s in states if s is True) == 1

    def test_only_the_undecided_ones_await_approval(self, conn):
        """Collapsing NULL into False would empty this list.

        Collapsing it the other way would put every rejected proposal back in
        front of the user, forever.
        """
        add_version(conn, 1, {"a": 1})
        self._add_lesson(conn, accepted=None)
        self._add_lesson(conn, accepted=0)

        payload = read_playbook(conn)
        assert len(payload["proposals_awaiting_approval"]) == 1
        assert payload["proposals_awaiting_approval"][0]["accepted_by_user"] is None

    def test_a_lesson_with_no_proposal_is_not_awaiting_anything(self, conn):
        add_version(conn, 1, {"a": 1})
        self._add_lesson(conn, accepted=None, diff=None)
        payload = read_playbook(conn)
        assert payload["proposals_awaiting_approval"] == []


class TestThePlaybookDrawsNothingThatCannotFill:
    """#344: the Lessons section is gone, and the drill works today.

    `lessons` had one writer, the Historian, deleted on 2026-09-05 (ADR 0106),
    so the screen's Lessons block could only ever say "never run". The payload
    keeps the field (the backend is untouched), the page stops drawing it. The
    five-step drill told Joe to "log the estimate anyway", and the estimate log
    was retired (ADR 0094, 0131).

    Source-text assertions, like `TestParlayChapter`: they establish that the
    files omit the retired text, not that the page renders.
    """

    ROOT = Path(__file__).resolve().parents[1] / "frontend" / "src"

    def _code(self, rel: str) -> str:
        text = (self.ROOT / rel).read_text(encoding="utf-8")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)

    def test_the_payload_still_carries_lessons(self, conn):
        """The field stays; only the screen's block went."""
        add_version(conn, 1, {"a": 1})
        assert read_playbook(conn)["lessons"] == []

    def test_the_lessons_block_is_not_drawn(self):
        """Mutation observed red: restore the `Lessons` heading."""
        code = self._code("app/playbook/page.tsx")
        assert "Lessons" not in code
        assert "LessonCard" not in code
        assert "Historian has never run" not in code
        assert "historian_has_run" not in code

    def test_the_estimate_drill_is_refused(self):
        """Mutation observed red: restore "log the estimate anyway"."""
        text = re.sub(
            r"\s+", " ", self._code("components/FiveStepTest.tsx")
        )
        assert "the estimate anyway" not in text
        assert "skip the bet" not in text

    def test_the_drill_says_to_write_it_on_paper_and_compare_to_the_close(self):
        text = re.sub(
            r"\s+", " ", self._code("components/FiveStepTest.tsx")
        )
        assert "on paper" in text
        assert "Kalshi’s close, not to the result" in text

    def test_one_lesson_flips_it(self, conn):
        """Inserted by hand, because nothing in the tree inserts one. The
        backend flag keeps its historical name; nothing on the screen reads
        it now."""
        add_version(conn, 1, {"a": 1})
        conn.execute(
            "INSERT INTO lessons (created_ms, title, body, sample_size) "
            "VALUES (?, 't', 'b', 120)",
            (NOW,),
        )
        conn.commit()
        assert read_playbook(conn)["historian_has_run"] is True


class TestParlayChapter:
    """The Playbook's parlay chapter (#328): six facts, every term glossed.

    Static text read at the source, like the five steps. What this does not
    establish: that any sentence is persuasive, or that the page renders.
    """

    ROOT = Path(__file__).resolve().parents[1] / "frontend" / "src"

    def chapter(self) -> str:
        return (self.ROOT / "components" / "ParlayChapter.tsx").read_text(
            encoding="utf-8"
        )

    def plain(self) -> str:
        text = re.sub(r"/\*.*?\*/", "", self.chapter(), flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", "", text)
        for entity, char in (
            ("&ldquo;", '"'),
            ("&rdquo;", '"'),
            ("&rsquo;", "'"),
        ):
            text = text.replace(entity, char)
        return re.sub(r"\s+", " ", text)

    def test_the_six_facts_are_present(self):
        text = self.plain()
        for fact in (
            "12 cents wins about 1 time in 8",
            "5 cents, about 1 in 20",
            "Three 80% legs land together 51%",
            "six land 26%",
            "loses the whole card 1 time in 10",
            "about 11% more payout",
            "about 6.65% at 5 cents, 5.25% at 25 cents, 3.5% at 50 cents",
            "pay about half that share",
            "3.8 cents and 36.6 cents apart",
            "every bid on the three combinations this desk held sat below",
            "Expected vs won",
            "below 5 expected on each side",
        ):
            assert fact in text, fact

    def test_each_new_term_is_wrapped_and_defined(self):
        source = self.chapter()
        glossary = (self.ROOT / "lib" / "glossary.ts").read_text(encoding="utf-8")
        for key in ("fee_share", "sunk_cost", "single", "parlay", "leg", "fee"):
            assert f'k="{key}"' in source, key
        for key in ("fee_share", "sunk_cost", "single"):
            assert f"  {key}: {{" in glossary, key

    def test_it_is_mounted_on_the_playbook_below_the_five_steps(self):
        page = (self.ROOT / "app" / "playbook" / "page.tsx").read_text(
            encoding="utf-8"
        )
        assert page.index("<FiveStepTest />") < page.index("<ParlayChapter />")
        assert "<details" in self.chapter()

    def test_it_never_tells_him_what_to_stake_or_praises_a_price(self):
        text = self.plain()
        assert "Bet two dollars" not in text
        for word in ("cheap", "predict", "an edge", "bargain"):
            assert not re.search(rf"\b{word}", text, re.IGNORECASE), word

    def test_no_literal_fee_coefficient_in_the_chapter(self):
        assert not re.search(r"(?<![\d.])0\.07\d?(?!\d)", self.plain())
