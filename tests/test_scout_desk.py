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
from backend.agents.scout import ScoutReport
from backend.agents.scout_desk import DeskBriefing, convene_desk
from backend.store import db

CONFIG = AgentConfig(api_key="test", model="claude-opus-5")

EMPTY_REPORT = ScoutReport(
    game="A at B", findings=[], summary="Nothing noteworthy.",
    searched_for=["injuries"],
)
BRIEFING = DeskBriefing(
    headline="Quiet game.", assessment="Both scouts filed thin notes.",
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
        return StubResponse(self._briefing)


class DeskStubClient:
    def __init__(self, **kwargs):
        self.messages = DeskStubMessages(**kwargs)


def _budget(tmp_path, *, daily=24):
    conn = db.init_db(tmp_path / "desk.db")
    return conn, AgentBudget(conn, per_pass_budget=8, daily_budget=daily)


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

    async def test_the_staff_pair_is_reserved_before_the_first_request(self, tmp_path):
        """Crash direction: over-count. If the process dies mid-desk, the day
        must already carry the rows -- `budget.py` has the argument."""
        conn, budget = _budget(tmp_path)
        client = DeskStubClient()
        client.messages.attach_budget_probe(conn)
        await _convene(client, budget)
        assert client.messages.rows_at_first_call == 2

    async def test_a_full_briefing_is_exactly_three_metered_calls(self, tmp_path):
        conn, budget = _budget(tmp_path)
        client = DeskStubClient()
        result = await _convene(client, budget)
        assert result.status == "complete"
        assert result.briefing == BRIEFING
        agents = [
            r["agent"]
            for r in conn.execute(
                "SELECT agent FROM agent_calls ORDER BY id"
            ).fetchall()
        ]
        assert agents == ["scout_staff_home", "scout_staff_away", "scout_master"]

    async def test_the_master_is_not_paid_when_no_staff_filed(self, tmp_path):
        conn, budget = _budget(tmp_path)
        client = DeskStubClient(staff_raises={0, 1})
        result = await _convene(client, budget)
        assert result.status == "failed"
        assert result.briefing is None
        count = conn.execute("SELECT COUNT(*) AS c FROM agent_calls").fetchone()["c"]
        assert count == 2  # the staff pair was reserved; nothing more

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
        assert result.briefing == BRIEFING  # the master still ran
        master_call = client.messages.calls[-1]
        assert master_call["output_format"] is DeskBriefing
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
