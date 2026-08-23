"""The scout desk's contract: metered spend, no numbers, honest absences.

ADR 0060 switched the Scout on as a desk -- two staff scouts and a master --
and every safety property of that decision lives here:

- **No number can leave the desk.** `DeskBriefing` is prose fields only,
  asserted by walking the schema rather than by trusting the prompt. A prompt
  is guidance; a schema is enforcement.
- **Every call is metered, and a refusal costs zero.** The staff pair is
  reserved in `agent_calls` before the first request goes out; the master is
  reserved only once a staff note exists to synthesise.
- **"Filed nothing" is not "found nothing".** A dead scout and a scout who
  looked and found nothing produce different inputs to the master, in words.

No network: the Anthropic client is stubbed, as in `test_agents.py`.

What these tests do NOT establish: that a real briefing is any good, that the
prompts produce useful notes, or that the API routes serve this correctly --
`tests/test_api.py` owns the route contract.
"""

from __future__ import annotations

import typing

from backend.agents.base import AgentConfig
from backend.agents.budget import AgentBudget
from backend.agents.pro_bettor import SharpTake
from backend.agents.scout import ScoutReport
from backend.agents.scout_desk import (
    BoardTile,
    DeskBriefing,
    StaffNote,
    complete_board,
    convene_desk,
)
from backend.store import db

CONFIG = AgentConfig(api_key="test", model="claude-opus-5")

EMPTY_REPORT = ScoutReport(
    game="A at B", findings=[], summary="Nothing noteworthy.",
    searched_for=["injuries"],
)
BRIEFING = DeskBriefing(
    headline="Quiet game.", assessment="Both scouts filed thin notes.",
)
SHARP = SharpTake(
    headline="Nothing here a pro would act on.",
    read="The filings are thin and everything in them is old news.",
)


class StubResponse:
    def __init__(self, parsed=None):
        self.parsed_output = parsed
        self.stop_reason = "end_turn"
        self.stop_details = None


class DeskStubMessages:
    """Dispatches on the requested schema, so one client serves staff and
    master differently; records every call's kwargs in order."""

    def __init__(self, *, staff=EMPTY_REPORT, briefing=BRIEFING,
                 staff_raises=None):
        self._staff = staff
        self._briefing = briefing
        self._staff_raises = staff_raises  # None, or a set of 0-based staff call indexes
        self._staff_seen = 0
        self.calls = []
        self.rows_at_first_call = None

    def attach_budget_probe(self, conn):
        self._probe_conn = conn

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.rows_at_first_call is None and hasattr(self, "_probe_conn"):
            self.rows_at_first_call = self._probe_conn.execute(
                "SELECT COUNT(*) AS c FROM agent_calls"
            ).fetchone()["c"]
        if kwargs["output_format"] is ScoutReport:
            index = self._staff_seen
            self._staff_seen += 1
            if self._staff_raises and index in self._staff_raises:
                raise RuntimeError("this scout is down")
            return StubResponse(self._staff)
        if kwargs["output_format"] is SharpTake:
            return StubResponse(SHARP)
        return StubResponse(self._briefing)


class DeskStubClient:
    def __init__(self, **kwargs):
        self.messages = DeskStubMessages(**kwargs)


def _budget(tmp_path, *, daily=24, searches_daily=0, tokens_daily=0):
    conn = db.init_db(tmp_path / "desk.db")
    return conn, AgentBudget(
        conn, per_pass_budget=8, daily_budget=daily,
        searches_daily_budget=searches_daily, tokens_daily_budget=tokens_daily,
    )


async def _convene(client, budget):
    return await convene_desk(
        client, CONFIG, budget,
        ticker="KXTEST", event_title="A at B", league="baseball_mlb",
        commence_iso="2026-08-21T22:00:00+00:00",
        home_team="B", away_team="A", now_ms=1_000_000,
    )


class TestNoNumberCanLeaveTheDesk:
    def test_the_briefing_schema_is_prose_only_all_the_way_down(self):
        """Walked, not trusted. A numeric field added anywhere in
        `DeskBriefing` -- however nested, including the board tiles and any
        `Literal` member -- fails here, because the schema is the enforcement
        layer the prompts merely describe."""
        from pydantic import BaseModel as PydanticBase

        def leaves(annotation):
            args = typing.get_args(annotation)
            if not args:
                yield annotation
            for arg in args:
                yield from leaves(arg)

        def check_model(model, path):
            for name, field in model.model_fields.items():
                where = f"{path}.{name}"
                for leaf in leaves(field.annotation):
                    if isinstance(leaf, type) and issubclass(leaf, PydanticBase):
                        check_model(leaf, where)
                        continue
                    if isinstance(leaf, str):
                        continue  # a Literal member: words, never numbers
                    assert not isinstance(leaf, (int, float, complex)), (
                        f"{where} has a numeric Literal member {leaf!r}; the "
                        f"desk must not have a field a forecast could hide in"
                    )
                    assert leaf not in (int, float, complex), (
                        f"{where} can carry a number; the desk must not have "
                        f"a field a forecast could hide in"
                    )
                    assert leaf in (str, list, type(None)), (
                        f"{where} has unexpected leaf {leaf!r}; keep the "
                        f"briefing words-only"
                    )

        check_model(DeskBriefing, "DeskBriefing")


class TestTheDeskIsMetered:
    async def test_a_refused_desk_makes_no_call_and_spends_nothing(self, tmp_path):
        conn, budget = _budget(tmp_path, daily=1)  # cannot afford the pair
        client = DeskStubClient()
        result = await _convene(client, budget)
        assert result.status == "refused"
        assert result.refusal_reason is not None
        assert client.messages.calls == []
        count = conn.execute("SELECT COUNT(*) AS c FROM agent_calls").fetchone()["c"]
        assert count == 0

    async def test_the_search_brake_refuses_the_desk_with_call_budget_left(
        self, tmp_path
    ):
        """The v17 brake: the day has 22 of 24 calls left, but the searches
        already recorded leave no room for the staff pair's worst case
        (2 x max_uses = 12), so the desk is refused BEFORE any reserve --
        nothing spent, nothing half-filed. Mutation run: the
        `searches_worst_case` argument dropped from `convene_desk`'s
        `can_afford` call -- this test goes red (the desk would convene).
        File restored byte-identical."""
        from backend.agents.base import CallUsage

        conn, budget = _budget(tmp_path, searches_daily=12)
        spent = budget.reserve(called_ms=1, agent="scout_staff_home", model="m")
        budget.settle(spent, verdict="filed",
                      usage=CallUsage(input_tokens=1, output_tokens=1,
                                      web_searches=6))
        client = DeskStubClient()
        result = await _convene(client, budget)
        assert result.status == "refused"
        assert "web searches" in result.refusal_reason
        assert client.messages.calls == []
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM agent_calls"
        ).fetchone()["c"]
        assert count == 1  # only the seeded row; the desk reserved nothing

    async def test_the_staff_pair_is_reserved_before_the_first_request(self, tmp_path):
        """Crash direction: over-count. If the process dies mid-desk, the day
        must already carry the rows -- `budget.py` has the argument."""
        conn, budget = _budget(tmp_path)
        client = DeskStubClient()
        client.messages.attach_budget_probe(conn)
        await _convene(client, budget)
        assert client.messages.rows_at_first_call == 2

    async def test_a_full_briefing_is_exactly_four_metered_calls(self, tmp_path):
        """Was three until 2026-08-23: ADR 0069 seats the pro-bettor as a
        fourth metered call after the master settles."""
        conn, budget = _budget(tmp_path)
        client = DeskStubClient()
        result = await _convene(client, budget)
        assert result.status == "complete"
        # The board is completed server-side on the way out, so compare the
        # prose; the six-tile projection has its own test class.
        assert result.briefing.headline == BRIEFING.headline
        assert len(result.briefing.board) == 6
        assert result.sharp is not None
        assert result.sharp.headline == SHARP.headline
        agents = [
            r["agent"]
            for r in conn.execute(
                "SELECT agent FROM agent_calls ORDER BY id"
            ).fetchall()
        ]
        assert agents == [
            "scout_staff_home", "scout_staff_away", "scout_master",
            "pro_bettor",
        ]

    async def test_the_master_is_not_paid_when_no_staff_filed(self, tmp_path):
        conn, budget = _budget(tmp_path)
        client = DeskStubClient(staff_raises={0, 1})
        result = await _convene(client, budget)
        assert result.status == "failed"
        assert result.briefing is None
        count = conn.execute("SELECT COUNT(*) AS c FROM agent_calls").fetchone()["c"]
        assert count == 2  # the staff pair was reserved; nothing more

    async def test_an_unaffordable_pro_seat_downgrades_nothing(self, tmp_path):
        """ADR 0069: `status` ignores the seat. Three calls affordable means
        staff + master run, the convening is still `complete`, and the
        seat's absence carries its reason instead of a downgraded word."""
        conn, budget = _budget(tmp_path, daily=3)  # staff + master, no Willy
        client = DeskStubClient()
        result = await _convene(client, budget)
        assert result.status == "complete"
        assert result.briefing is not None
        assert result.sharp is None
        assert result.sharp_absent_reason is not None
        count = conn.execute("SELECT COUNT(*) AS c FROM agent_calls").fetchone()["c"]
        assert count == 3  # the refused seat reserved nothing

    async def test_an_unaffordable_master_returns_partial_with_the_notes(self, tmp_path):
        conn, budget = _budget(tmp_path, daily=2)  # staff fit, master does not
        client = DeskStubClient()
        result = await _convene(client, budget)
        assert result.status == "partial"
        assert result.briefing is None
        assert all(n.report is not None for n in result.staff)
        count = conn.execute("SELECT COUNT(*) AS c FROM agent_calls").fetchone()["c"]
        assert count == 2


class TestFiledNothingIsNotFoundNothing:
    async def test_a_dead_scout_reaches_the_master_as_filed_nothing(self, tmp_path):
        conn, budget = _budget(tmp_path)
        client = DeskStubClient(staff_raises={0})  # the home scout dies
        result = await _convene(client, budget)
        assert result.status == "partial"
        assert result.briefing is not None  # the master still ran
        assert result.briefing.headline == BRIEFING.headline
        # By schema, not position: since ADR 0069 the pro's seat calls after
        # the master, so `calls[-1]` is Willy's.
        master_call = next(
            c for c in client.messages.calls
            if c["output_format"] is DeskBriefing
        )
        prompt = master_call["messages"][0]["content"]
        assert "FILED NOTHING" in prompt
        # And the surviving scout's actual filing is present, not paraphrased.
        assert "Nothing noteworthy." in prompt

    async def test_an_empty_filing_reaches_the_master_as_a_report(self, tmp_path):
        conn, budget = _budget(tmp_path)
        client = DeskStubClient()
        await _convene(client, budget)
        prompt = client.messages.calls[-1]["messages"][0]["content"]
        assert "FILED NOTHING" not in prompt
        assert '"findings": []' in prompt

    async def test_each_scout_is_briefed_on_their_own_club_only(self, tmp_path):
        """Joe's design: one scout per club, and the venue belongs to the
        host's scout. The away scout must be told the venue is not theirs."""
        conn, budget = _budget(tmp_path)
        client = DeskStubClient()
        await _convene(client, budget)
        staff_systems = [
            c["system"][-1]["text"]
            for c in client.messages.calls
            if c["output_format"] is ScoutReport
        ]
        home, away = staff_systems
        assert "You are the B scout" in home
        assert "your team is the host" in home
        assert "You are the A scout" in away
        assert "Your team is the visitor" in away


class TestTheBoardIsCompletedServerSide:
    """The schema cannot promise six tiles; `complete_board` must.

    A missing tile renders as nothing, and nothing reads calmer than
    "unconfirmed" -- the exact defect the board exists to close. Every rule
    here moves in the safe direction only: omission and unearned calm become
    warnings, never the reverse.
    """

    def _report(self, *, findings=(), searched=("injuries",)):
        return ScoutReport(
            game="A at B", findings=list(findings),
            summary="s", searched_for=list(searched),
        )

    def _staff(self, report):
        return [
            StaffNote(role="home", team="B", report=report),
            StaffNote(role="away", team="A", report=report),
        ]

    def test_a_missing_tile_becomes_unconfirmed_not_nothing(self):
        briefing = DeskBriefing(
            headline="h", assessment="a",
            board=[BoardTile(category="lineup", state="stale_only", note="n")],
        )
        completed = complete_board(briefing, self._staff(self._report()))
        assert [t.category for t in completed.board] == [
            "lineup", "injury", "weather", "rest_travel", "venue", "other",
        ]
        weather = next(t for t in completed.board if t.category == "weather")
        assert weather.state == "unconfirmed"

    def test_duplicate_tiles_collapse_to_the_most_alarming(self):
        briefing = DeskBriefing(
            headline="h", assessment="a",
            board=[
                BoardTile(category="injury", state="clear", note="calm"),
                BoardTile(category="injury", state="fresh", note="new IL move"),
            ],
        )
        completed = complete_board(briefing, self._staff(self._report()))
        injury = next(t for t in completed.board if t.category == "injury")
        assert injury.state == "fresh"

    def test_an_unearned_clear_is_rewritten_unconfirmed(self):
        """"Nothing notable" from a desk that never looked is not a finding."""
        briefing = DeskBriefing(
            headline="h", assessment="a",
            board=[BoardTile(category="weather", state="clear", note="fine")],
        )
        # Nobody searched weather and nobody filed a weather finding.
        completed = complete_board(
            briefing, self._staff(self._report(searched=("injuries",)))
        )
        weather = next(t for t in completed.board if t.category == "weather")
        assert weather.state == "unconfirmed"

    def test_an_earned_clear_survives(self):
        briefing = DeskBriefing(
            headline="h", assessment="a",
            board=[BoardTile(category="weather", state="clear", note="roof shut")],
        )
        completed = complete_board(
            briefing,
            self._staff(self._report(searched=("game-day weather and roof",))),
        )
        weather = next(t for t in completed.board if t.category == "weather")
        assert weather.state == "clear"

    async def test_the_desk_serves_a_completed_board(self, tmp_path):
        """Wired, not just available: `convene_desk` must run the projection,
        so a briefing leaving the desk always carries all six tiles."""
        conn, budget = _budget(tmp_path)
        client = DeskStubClient(
            briefing=DeskBriefing(headline="h", assessment="a", board=[])
        )
        result = await _convene(client, budget)
        assert result.briefing is not None
        assert len(result.briefing.board) == 6
        assert all(t.state == "unconfirmed" for t in result.briefing.board)
