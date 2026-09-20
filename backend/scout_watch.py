"""`backend/scout_watch.py` -- convene the scout desk on tonight's ladder,
unattended. ADR 0180 section 3.1.

**Copies `backend/hedge_watch.py:161-224`'s loop shape exactly**, for the same
reasons that module gives: its own connection (a concurrent task on the
runner's handle would interleave two transactions on one connection, and a
second connection in the same process is what WAL is for), factories rather
than instances (this task owns the only connection and client it may use),
swallow-and-log (a wedged venue or an exhausted budget must degrade this to
"no auto convenings", never take down the process recording the evidence the
whole project depends on), and only `CancelledError` exits.

**This is the first thing in this repo that can spend Anthropic money with
nobody tapping anything**, so every ceiling REFUSES rather than degrades
(ADR 0180's money contract, restated here as code):

- `enabled` is `SCOUT_AUTO_CONVENE_ENABLED`. Off means the cycle does not even
  call `config_factory()` -- zero calls, full stop, not "zero spent calls
  after reading the ladder".
- `config_factory()` returning `None` (no `ANTHROPIC_API_KEY`) is the keyless
  state and ends the cycle the same way -- never a raise, matching
  `AgentConfig.from_env`'s own contract.
- `max_per_day` counts today's `scout_briefings.trigger = 'auto'` rows against
  the AGENT BUDGET day (`AgentBudget.day_start_ms`), not a calendar day --
  the same rollover the shared ceilings use, so "today" means one thing.
- `reserve_taps` is enforced by asking whether the budget can still afford
  `reserve_taps` convenings of Joe's own AFTER this one:
  `can_afford(2 * (1 + reserve_taps), ..., searches_worst_case=
  STAFF_PAIR_SEARCHES_WORST_CASE * (1 + reserve_taps))`. A single convening
  that would leave the reserve unaffordable is refused, not shrunk.
- `refresh_hours` skips a fixture whose newest briefing is younger than that
  UNLESS that briefing is `failed` -- a dead convening does not block a retry.

One convening per cycle: the loop reads tonight's ladder the way
`GET /api/parlays` does (`build_ladder_payload_widening`), walks its distinct
fixtures kickoff-soonest first, and convenes on the first one that clears
every guard (an affordable, unscouted fixture `_resolve_scout_fixture` can
actually resolve a ticker for). Finding none ends the cycle exactly like a
refusal does: nothing spent, sleep, try again.

`_resolve_scout_fixture` and `_run_scout_desk` are the SAME functions
`backend/api/routers/scout.py`'s tap path calls -- module-level there, lifted
out of the `register()` closure so the tap and this watcher share one write
path. `_run_scout_desk` takes the trigger ('tap' there, 'auto' here) and
writes it onto the completed row, so a briefing's own row states who sent the
desk after it, not only at insert time.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

from .agents.base import AgentConfig
from .agents.budget import AgentBudget
from .agents.scout_desk import STAFF_PAIR_SEARCHES_WORST_CASE
from .api.routers.scout import _resolve_scout_fixture, _run_scout_desk
from .config import StalenessConfig
from .parlays import _leg_scouting, build_ladder_payload_widening
from .store import db as store_db

logger = logging.getLogger(__name__)

#: Matches the hedge watcher's idle cadence order of magnitude. Ten minutes:
#: the ladder does not change fast enough for anything tighter to matter, and
#: this is a background convening, not a phone waiting on a response.
DEFAULT_INTERVAL_S = 600.0


def _distinct_fixtures_kickoff_soonest(payload: dict) -> list[dict]:
    """Distinct fixtures from a ladder payload, soonest kickoff first.

    A fixture is one Kalshi event (`event_ticker`) -- legs on different
    markets of the same game are the same fixture, and convening the desk
    once covers all of them (ADR 0088: the join is by game). Each fixture
    keeps every leg ticker seen for it, in payload order, so the caller can
    try more than one if `_resolve_scout_fixture` cannot resolve the first.
    """
    fixtures: dict[str, dict] = {}
    for card in payload.get("cards", []):
        for leg in card.get("legs", []):
            event_ticker = leg.get("event_ticker")
            ticker = leg.get("ticker")
            if event_ticker is None or ticker is None:
                continue
            commence_ms = leg.get("commence_ms")
            entry = fixtures.setdefault(
                event_ticker, {"commence_ms": commence_ms, "tickers": []}
            )
            if commence_ms is not None and (
                entry["commence_ms"] is None or commence_ms < entry["commence_ms"]
            ):
                entry["commence_ms"] = commence_ms
            if ticker not in entry["tickers"]:
                entry["tickers"].append(ticker)
    return sorted(
        fixtures.values(),
        key=lambda f: (f["commence_ms"] is None, f["commence_ms"]),
    )


def _is_fresh(row, *, now_ms: int, refresh_hours: int) -> bool:
    """Whether `row` (a `sqlite3.Row` from `_leg_scouting`, or `None`) is a
    briefing recent enough to skip.

    `None` (never scouted) is never fresh. A `failed` convening is never
    fresh either, however recent -- ADR 0180's "unless failed" clause -- so a
    dead attempt does not block every later cycle from retrying. `sqlite3.Row`
    has no `.get`, so absence is read with `in row.keys()` rather than assumed
    dict-like.
    """
    if row is None:
        return False
    if "status" not in row.keys() or row["status"] is None:
        return False
    if row["status"] == "failed":
        return False
    if "requested_ms" not in row.keys() or row["requested_ms"] is None:
        return False
    age_ms = now_ms - row["requested_ms"]
    return age_ms < refresh_hours * 3600 * 1000


async def _convene_one(
    conn,
    db_path,
    config_factory: Callable[[], Optional[AgentConfig]],
    client_factory: Callable[[AgentConfig], object],
    *,
    refresh_hours: int,
    max_per_day: int,
    reserve_taps: int,
    now_ms: int,
) -> None:
    """One cycle's worth of work. Refuses, or convenes at most one fixture."""
    config = config_factory()
    if config is None:
        # No ANTHROPIC_API_KEY: the keyless state, never a raise. Nothing to
        # convene with, and the ladder scan below is not free of DB work, so
        # there is nothing worth spending it on either.
        return

    budget = AgentBudget.from_config(conn, config)
    day_start_ms = budget.day_start_ms(now_ms)
    auto_today = conn.execute(
        "SELECT COUNT(*) AS c FROM scout_briefings "
        "WHERE trigger = 'auto' AND requested_ms >= ?",
        (day_start_ms,),
    ).fetchone()["c"]
    if auto_today >= max_per_day:
        logger.info(
            "scout watch refused: %d of %d unattended convenings already "
            "made today (SCOUT_AUTO_MAX_CONVENINGS_PER_DAY)",
            auto_today, max_per_day,
        )
        return

    # After this one convening, `reserve_taps` more of Joe's own must still
    # fit. Asked as one fan-out rather than two separate checks, because
    # `refusal_reason` is the one place the three daily ceilings are read
    # together and a second implementation would drift (`budget.py`'s own
    # argument against a second `can_afford`).
    reserved_calls = 2 * (1 + reserve_taps)
    reserved_searches = STAFF_PAIR_SEARCHES_WORST_CASE * (1 + reserve_taps)
    reason = budget.refusal_reason(
        reserved_calls, now_ms, searches_worst_case=reserved_searches
    )
    if reason is not None:
        logger.info(
            "scout watch refused: %s (leaving %d taps in reserve)",
            reason, reserve_taps,
        )
        return

    staleness = StalenessConfig.load()
    payload = build_ladder_payload_widening(
        conn, now_ms=now_ms, max_odds_age_ms=staleness.max_odds_age_s * 1000
    )
    fixtures = _distinct_fixtures_kickoff_soonest(payload)

    for fixture_entry in fixtures:
        resolved = None
        resolved_ticker = None
        for ticker in fixture_entry["tickers"]:
            candidate = _resolve_scout_fixture(conn, ticker)
            if candidate is not None:
                resolved = candidate
                resolved_ticker = ticker
                break
        if resolved is None:
            continue

        scouting = _leg_scouting(conn, [resolved_ticker])
        if _is_fresh(
            scouting.get(resolved_ticker), now_ms=now_ms, refresh_hours=refresh_hours
        ):
            continue

        cursor = conn.execute(
            "INSERT INTO scout_briefings (ticker, event_title, league, "
            "home_team, away_team, commence_ms, requested_ms, status, "
            "model, trigger) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, "
            "'auto')",
            (
                resolved_ticker,
                resolved["event_title"],
                resolved["league"],
                resolved["home_team"],
                resolved["away_team"],
                resolved["commence_ms"],
                now_ms,
                config.model,
            ),
        )
        conn.commit()
        row_id = int(cursor.lastrowid)
        logger.info(
            "scout watch convening %d: %s (%s), unattended",
            row_id, resolved_ticker, resolved["event_title"],
        )
        await _run_scout_desk(
            db_path, row_id, config, resolved, resolved_ticker,
            trigger="auto", client_factory=client_factory,
        )
        return

    logger.info("scout watch: no eligible fixture this cycle")


async def watch_scouts_forever(
    db_path,
    config_factory: Callable[[], Optional[AgentConfig]],
    client_factory: Callable[[AgentConfig], object],
    *,
    refresh_hours: int,
    max_per_day: int,
    reserve_taps: int,
    enabled: bool,
    interval_s: float = DEFAULT_INTERVAL_S,
    sleep=asyncio.sleep,
    clock=time.time,
    max_cycles: Optional[int] = None,
) -> None:
    """The watcher as a long-running task beside `watch_hedges_forever`.

    `client_factory` is passed straight through to `_run_scout_desk`, which
    defaults to `build_client` for the tap route but accepts an override so
    this watcher (and its tests) can hand it a stub instead of reaching for a
    real Anthropic client.

    `enabled = False` makes zero calls: `config_factory` is never invoked,
    nothing is read, nothing is spent -- the flag gates the cycle before
    anything else runs. `sleep`, `clock` and `max_cycles` exist for tests;
    production passes none.
    """
    conn = store_db.connect(db_path)
    try:
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            cycles += 1
            now_ms = int(clock() * 1000)
            try:
                if enabled:
                    await _convene_one(
                        conn,
                        db_path,
                        config_factory,
                        client_factory,
                        refresh_hours=refresh_hours,
                        max_per_day=max_per_day,
                        reserve_taps=reserve_taps,
                        now_ms=now_ms,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:                                    # noqa: BLE001
                # Deliberately broad, and deliberately not re-raised. See the
                # module docstring: this task existing tomorrow matters more
                # than any one cycle succeeding today.
                logger.exception("scout watch cycle failed")
            await sleep(interval_s)
    finally:
        conn.close()
