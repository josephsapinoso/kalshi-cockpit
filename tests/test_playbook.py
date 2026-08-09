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
        "kelly_fraction, suggested_contracts, kalshi_quote_age_ms, "
        "odds_age_ms, suppressed_reason, reason_text, clv_scored_ms"
        ") VALUES (?, ?, ?, 'yes', 500, 0.5, 0, 0.01, 0.0, 0.0, ?, 0, 0, ?, '', ?)",
        (NOW, version, ticker, contracts, suppressed, NOW if scored else None),
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


class TestAnEmptyListIsNotAHealthySilence:
    """The rendering decision this screen exists to protect.

    `lessons` has exactly one writer -- the Historian -- and nothing that runs
    calls it. So an empty list is a fact about wiring, and showing it as
    "nothing to report" is a screen reporting a healthy silence over a
    disconnected wire. Same shape as `analysis/marts.py` refusing to let a
    missing warehouse read as an empty one.
    """

    def test_no_lessons_says_the_historian_has_not_run(self, conn):
        add_version(conn, 1, {"a": 1})
        payload = read_playbook(conn)
        assert payload["lessons"] == []
        assert payload["historian_has_run"] is False

    def test_one_lesson_flips_it(self, conn):
        add_version(conn, 1, {"a": 1})
        conn.execute(
            "INSERT INTO lessons (created_ms, title, body, sample_size) "
            "VALUES (?, 't', 'b', 120)",
            (NOW,),
        )
        conn.commit()
        assert read_playbook(conn)["historian_has_run"] is True
