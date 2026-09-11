"""`GET /api/exposure`: the cheapest honest answer to "how deep am I already?"

ADR 0112 removed all five brakes from the hand-bet path, and the caps were the
only consumer of Joe's exposure figure -- so after they went, nothing on any
screen read it before a bet. ADR 0071 section 2.2 makes price transparency the
desk's job at the moment of a bet, and what Kalshi charges is half of that;
what he already has on is the other half. `/parlays`, the screen all four real
combination fills were placed on, fetched no position data at all.

What this establishes
---------------------
- The route serves `open_positions` and NOTHING else: two keys, pinned by
  name. `/api/bets` serves the same block and also 200 settled rows, the pass
  summary and the lockout clock, and `<ManualTicket>` opens this read on seven
  surfaces beside a live Kalshi book read.
- A stale, unmirrored or never-polled record arrives as the server's own
  refusal SENTENCE with the money field `None` -- never `0`, never `"$0.00"`.
  That is the repo's standing rule (*unreadable resolves to `None`, never
  `0`*) on the one figure whose false zero reads as "nothing at risk".
- A figure that IS readable arrives in integer tenths of a cent beside a
  pre-rendered display string, and carries the clock of the read that
  produced it.
- An empty-but-fresh venue is count 0 and `$0.00`, which is a reading and not
  a refusal -- the state the live account has been in since schema v33.

What it does NOT establish
--------------------------
That `open_positions` picks the right refusal for a given database state
(`tests/test_venue_positions.py` and `tests/test_bets_sections.py` own that),
that the stamps are the right clocks (`tests/test_open_positions_stamp.py`),
or anything the screen does with the payload
(`tests/test_manual_ticket_exposure.py`).

Mutations run 2026-09-10, each applied alone and reversed exactly afterwards.
Counts are over BOTH exposure files run together (28 tests), because a screen
guard and a server guard on the same figure are worth nothing separately:

| mutation | red |
|---|---|
| `bets.open_positions`: the stale branch also sets `staked_tenths = 0`, `staked_display = "$0.00"` beside its refusal | 4 |
| `bets.open_positions`: `count_age_ms` left as `None` | 4 |
| `ledger`: `/api/exposure` returns `bets_record(conn, limit=200)` with the block bolted on, as `/api/bets` does | 2 |
| `ledger`: `as_of_ms` dropped from the payload | 2 |
| `exposureLine`: the `staked_refusal` branch prints `$${staked_tenths / 1000}` instead of the server's words | 4 |
| `exposureLine`: `valueStamp` aliased over `countStamp`, so the figure wears the balance's clock | 2 |
| `exposureLine`: the count-0 branch removed, so a fresh empty venue prints "$0.00 staked" | 1 |
| `ManualTicket`: `exposure !== null && !exposure.refused` prepended to `canConfirm` | 1 |
| `ManualTicket`: `disabled={!canConfirm || exposure?.refused === true}` on the confirm button | 1 |
"""

from __future__ import annotations

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db

# The route takes its own `db.now_ms()`, so every fixture clock is relative to
# the real one. A frozen constant here would drift past the staleness bound on
# its own and make "fresh" mean "whenever this file was written".
def fresh_ms() -> int:
    """Inside `TONIGHT_STALE_AFTER_MS` (30 minutes) by a wide margin."""
    return db.now_ms() - 60_000


def stale_ms() -> int:
    """Six hours ago: well past the bound, and not near its edge."""
    return db.now_ms() - 6 * 3600 * 1000


def _build(tmp_path, *, positions_ms=None, row_count=0, exposures=()):
    """A real database carrying one positions poll and its mirrored rows."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "exposure.db"
    conn = db.init_db(path)
    if positions_ms is not None:
        cur = conn.execute(
            "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count, mirrored) "
            "VALUES (?, 'positions', 1, ?, 1)",
            (positions_ms, row_count),
        )
        poll_id = cur.lastrowid
        for i, tenths in enumerate(exposures):
            conn.execute(
                "INSERT INTO venue_positions "
                "(poll_log_id, polled_ms, ticker, exposure_tenths) "
                "VALUES (?, ?, ?, ?)",
                (poll_id, positions_ms, f"KXTEST-{i}", tenths),
            )
    conn.commit()
    conn.close()
    return path


async def _get(path):
    app = create_app(AppConfig(instance_mode="demo", db_path=path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        return await client.get("/api/exposure")


class TestTheRouteCarriesOnlyExposure:
    async def test_the_payload_is_two_keys_and_no_more(self, tmp_path):
        """The whole point of a second route. Anything else served here is
        weight a buy button pays for on every open, on seven surfaces."""
        response = await _get(_build(tmp_path))
        assert response.status_code == 200
        payload = response.json()
        assert set(payload) == {"as_of_ms", "open_positions"}

    async def test_it_drags_none_of_what_api_bets_drags(self, tmp_path):
        """`/api/bets` serves this same block beside `bets_record(limit=200)`,
        `pass_summary` and `lockout_until`. None of the three may appear."""
        response = await _get(_build(tmp_path))
        text = response.text
        for heavy in ("bets", "passes", "lockout_until_ms", "sections"):
            assert f'"{heavy}"' not in text, heavy

    async def test_the_block_is_the_same_shape_the_slate_and_bets_carry(
        self, tmp_path
    ):
        """Passed through unshaped, so `OpenPositionsBlock` stays one type and
        the two renderings cannot drift apart."""
        payload = (await _get(_build(tmp_path))).json()
        assert set(payload["open_positions"]) == {
            "count",
            "count_as_of_ms",
            "count_age_ms",
            "value_tenths",
            "value_display",
            "value_as_of_ms",
            "value_age_ms",
            "value_refusal",
            "staked_tenths",
            "staked_display",
            "staked_refusal",
        }

    async def test_as_of_ms_names_the_clock_the_ages_were_taken_against(
        self, tmp_path
    ):
        """Sent so nothing downstream subtracts a browser millisecond from a
        server one. With a read on the record, `as_of - count_as_of` is the
        served `count_age_ms` exactly."""
        payload = (await _get(_build(
            tmp_path, positions_ms=fresh_ms(), row_count=1,
            exposures=(2_500,),
        ))).json()
        block = payload["open_positions"]
        assert isinstance(payload["as_of_ms"], int)
        assert block["count_age_ms"] is not None
        assert (
            payload["as_of_ms"] - block["count_as_of_ms"]
            == block["count_age_ms"]
        )


class TestUnreadableIsWordsAndNeverAZero:
    async def test_a_never_polled_record_refuses_in_words(self, tmp_path):
        """The empty demo database. `staked_tenths` is `None`, not `0`, and
        the sentence says the venue was never asked."""
        block = (await _get(_build(tmp_path))).json()["open_positions"]
        assert block["count"] is None
        assert block["staked_tenths"] is None
        assert block["staked_display"] is None
        assert isinstance(block["staked_refusal"], str)
        assert block["staked_refusal"] != ""

    async def test_a_stale_read_refuses_and_keeps_its_clock(self, tmp_path):
        """Past the staleness bound the figure refuses, the stamp survives, so
        the screen can say "not read since" rather than showing an old number
        as current -- or a zero, which would read as nothing at risk."""
        polled = stale_ms()
        path = _build(
            tmp_path, positions_ms=polled, row_count=2,
            exposures=(4_000, 6_000),
        )
        block = (await _get(path)).json()["open_positions"]
        assert block["count"] is None
        assert block["staked_tenths"] is None
        assert block["staked_display"] is None
        assert isinstance(block["staked_refusal"], str)
        assert block["count_as_of_ms"] == polled
        assert block["count_age_ms"] is not None and block["count_age_ms"] > 0

    async def test_no_refusal_state_ever_serves_a_dollar_string(self, tmp_path):
        """The one substitution this route exists to make impossible. Over
        every refusing state reachable without a mirrored poll, `$` never
        appears in the staked fields."""
        for path in (
            _build(tmp_path / "a", positions_ms=None),
            _build(tmp_path / "b", positions_ms=stale_ms(), row_count=1,
                   exposures=(1_000,)),
            # Mirror mismatch: the poll counted two rows, one was kept.
            _build(tmp_path / "c", positions_ms=fresh_ms(),
                   row_count=2, exposures=(1_000,)),
        ):
            block = (await _get(path)).json()["open_positions"]
            assert block["staked_display"] is None
            assert block["staked_tenths"] is None
            assert isinstance(block["staked_refusal"], str)
            assert "$" not in block["staked_refusal"]


class TestAReadableFigureIsTenthsAndADisplayString:
    async def test_the_money_is_integer_tenths_beside_its_rendering(
        self, tmp_path
    ):
        """Money is integer tenths of a cent everywhere in the risk path; the
        screen renders the string and never re-derives the number."""
        path = _build(
            tmp_path, positions_ms=fresh_ms(), row_count=2,
            exposures=(12_340, 9_660),
        )
        block = (await _get(path)).json()["open_positions"]
        assert block["count"] == 2
        assert block["staked_tenths"] == 22_000
        assert isinstance(block["staked_tenths"], int)
        assert block["staked_display"] == "$22.00"
        assert block["staked_refusal"] is None

    async def test_an_empty_but_fresh_venue_is_a_reading_not_a_refusal(
        self, tmp_path
    ):
        """Count 0 and $0.00 from the same successful read seconds ago: the
        venue said it holds nothing, and that is knowledge. This is the one
        `$0.00` the rule above permits, and it is permitted because a count
        of 0 says the same thing in the same breath."""
        path = _build(tmp_path, positions_ms=fresh_ms(), row_count=0)
        block = (await _get(path)).json()["open_positions"]
        assert block["count"] == 0
        assert block["staked_tenths"] == 0
        assert block["staked_display"] == "$0.00"
        assert block["staked_refusal"] is None


class TestTheRouteIsNotAGate:
    def test_the_handler_reads_open_positions_and_writes_nothing(self):
        """A read beside a buy button must not be able to change anything,
        and must not be reachable as a brake. The handler's body is one call
        and one dict; anything with a side effect would have to appear here."""
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "backend" / "api" / "routers" / "ledger.py"
        ).read_text(encoding="utf-8")
        body = source.split('@app.get("/api/exposure")')[1].split(
            '@app.get("/api/bets")'
        )[0]
        code = "\n".join(
            line for line in body.splitlines()
            if not line.strip().startswith(("#", '"""', "*", "-"))
        )
        for forbidden in ("INSERT", "UPDATE", "DELETE", "commit(", "HTTPException"):
            assert forbidden not in code, forbidden


@pytest.mark.parametrize("route", ["/api/exposure"])
async def test_the_route_is_registered(tmp_path, route):
    """A route that exists only in a module nothing calls is the failure this
    repo has a memory entry about. This asserts the app actually serves it."""
    app = create_app(AppConfig(instance_mode="demo", db_path=_build(tmp_path)))
    paths = {r.path for r in app.routes}          # type: ignore[attr-defined]
    assert route in paths
