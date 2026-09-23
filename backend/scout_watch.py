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

One convening per cycle: the loop reads TONIGHT's ladder only
(`build_ladder_payload`, its own `DEFAULT_HORIZON`) -- **never the widened
one** (Joe's #119 answer, 2026-09-23): a quiet night stays quiet rather than
reaching into tomorrow's slate, and a tomorrow fixture is never convened on
a night with nothing tonight. Ahead of the ladder, the loop first collects
fixtures behind Joe's currently HELD parlay legs (`_held_fixtures_kickoff_soonest`
-- open positions, pending legs, kickoff still ahead and inside the same
tonight bound), because a game he already has money on riding is worth
scouting before one he might merely bet, Joe's own instruction the same day.
Held fixtures are tried first, soonest kickoff first; the ladder's fixtures
follow, deduplicated by `event_ticker` against the held set. The loop walks
this combined list and convenes on the first fixture that clears every guard
(an affordable, unscouted fixture `_resolve_scout_fixture` can actually
resolve a ticker for). Finding none ends the cycle exactly like a refusal
does: nothing spent, sleep, try again.

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
from .config import StalenessConfig, configured_day_start_utc_hour
# Aliased: `_convene_one` binds a LOCAL named `day_start_ms`, which would
# shadow this for the whole function body and make the keyless call above it
# an UnboundLocalError. The alias is the guard, not a style choice.
from .odds.timing import day_start_ms as budget_day_start_ms
from .parlays import _leg_scouting, build_ladder_payload, horizon_end_ms
from .store import db as store_db
from .store.scout_watch_log import (
    CONVENED,
    KEYLESS,
    NO_CANDIDATE,
    REFUSED_ALLOWANCE,
    REFUSED_BUDGET,
    record_watch_outcome,
)

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
    `event_ticker` rides along on each entry (beside `commence_ms` and
    `tickers`) so a caller merging this list against another one -- the held
    fixtures below -- can dedupe without re-deriving the dict's own key.
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
                event_ticker,
                {"event_ticker": event_ticker, "commence_ms": commence_ms, "tickers": []},
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


def _fallback_ticker_for_event(conn, event_ticker: str) -> Optional[str]:
    """The most recent `recommendations.ticker` on `event_ticker`, or `None`.

    A held leg's own `ticker` can be unlinked (no `event_links` row) or
    absent entirely (a hand-typed sportsbook slip, `ticker IS NULL`), so
    `_resolve_scout_fixture` on the leg's own ticker has nothing to resolve.
    The game itself is still findable through whatever the runner already
    priced on that event: one bounded, indexed query -- `kalshi_markets`
    filters on `event_ticker`, which `idx_markets_event` covers, and
    `recommendations` is then read by its own `ticker` primary lookup.
    """
    row = conn.execute(
        "SELECT r.ticker AS ticker FROM recommendations r "
        "JOIN kalshi_markets m ON m.ticker = r.ticker "
        "WHERE m.event_ticker = ? "
        "ORDER BY r.created_ms DESC, r.id DESC LIMIT 1",
        (event_ticker,),
    ).fetchone()
    return None if row is None else row["ticker"]


def _held_fixtures_kickoff_soonest(
    conn, *, now_ms: int, end_ms: int
) -> list[dict]:
    """Fixtures behind Joe's currently HELD parlay legs, soonest kickoff first.

    Joe's instruction, 2026-09-23: auto-scouting should cover a game he
    already has money riding on before it reaches for the open ladder. A leg
    counts only while it is still live and still ahead of us: the position
    must be `open` (a closed, settled or void ticket has nothing left to
    watch for), the leg's own `outcome` must be `pending` (a started or
    already-resolved leg is done, not upcoming), no sibling leg on the same
    position may have `outcome = 'lost'` (one lost leg kills the whole
    parlay, `hedge.py:1398`, so nothing on it is worth scouting -- a `void`
    sibling does not kill it and is still scouted), and its kickoff must be
    both strictly after `now_ms` and inside the SAME tonight bound
    `build_ladder_payload` uses for the ladder -- `horizon_end_ms`, passed in
    as `end_ms` rather than re-derived here, so there is exactly one
    definition of "tonight" in this module.

    Same dict shape as `_distinct_fixtures_kickoff_soonest` (plus
    `event_ticker`, for the same merge-dedup reason): `commence_ms` and
    `tickers`. A leg's `ticker` can be NULL (a hand-typed slip) -- such a leg
    is still grouped by `event_ticker`, it just contributes nothing to
    `tickers` directly. For every grouped fixture, `_fallback_ticker_for_event`
    is tried and, if it finds something not already in `tickers`, APPENDED
    LAST -- so the caller's existing try-in-order resolution loop tries every
    real leg ticker first and only reaches the fallback once all of them have
    failed (or there were none), exactly ADR 0180's resolution order.
    """
    rows = conn.execute(
        "SELECT l.ticker AS ticker, l.event_ticker AS event_ticker, "
        "l.commence_ms AS commence_ms "
        "FROM parlay_position_legs l "
        "JOIN parlay_positions p ON p.id = l.position_id "
        "WHERE p.status = 'open' AND l.outcome = 'pending' "
        "AND l.event_ticker IS NOT NULL AND l.commence_ms IS NOT NULL "
        "AND l.commence_ms > ? AND l.commence_ms <= ? "
        "AND NOT EXISTS ("
        "SELECT 1 FROM parlay_position_legs x "
        "WHERE x.position_id = p.id AND x.outcome = 'lost'"
        ") "
        "ORDER BY l.position_id, l.leg_index",
        (now_ms, end_ms),
    ).fetchall()
    fixtures: dict[str, dict] = {}
    for row in rows:
        event_ticker = row["event_ticker"]
        entry = fixtures.setdefault(
            event_ticker,
            {
                "event_ticker": event_ticker,
                "commence_ms": row["commence_ms"],
                "tickers": [],
            },
        )
        if row["commence_ms"] < entry["commence_ms"]:
            entry["commence_ms"] = row["commence_ms"]
        ticker = row["ticker"]
        if ticker is not None and ticker not in entry["tickers"]:
            entry["tickers"].append(ticker)
    for entry in fixtures.values():
        fallback = _fallback_ticker_for_event(conn, entry["event_ticker"])
        if fallback is not None and fallback not in entry["tickers"]:
            entry["tickers"].append(fallback)
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
    client_factory: Optional[Callable[[AgentConfig], object]] = None,
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
        #
        # The budget day is computed from the configured hour directly rather
        # than from `AgentBudget`, which needs the config we do not have. Same
        # function, same hour, so a keyless row lands on the same day boundary
        # as every other row.
        record_watch_outcome(
            conn,
            budget_day_ms=budget_day_start_ms(
                now_ms, hour=configured_day_start_utc_hour()
            ),
            now_ms=now_ms,
            outcome=KEYLESS,
            detail="no ANTHROPIC_API_KEY: the desk does not exist here",
        )
        return

    budget = AgentBudget.from_config(conn, config)
    day_start_ms = budget.day_start_ms(now_ms)
    auto_today = conn.execute(
        "SELECT COUNT(*) AS c FROM scout_briefings "
        "WHERE trigger = 'auto' AND requested_ms >= ?",
        (day_start_ms,),
    ).fetchone()["c"]
    if auto_today >= max_per_day:
        reason = (
            f"{auto_today} of {max_per_day} unattended convenings already "
            f"made today (SCOUT_AUTO_MAX_CONVENINGS_PER_DAY)"
        )
        logger.info("scout watch refused: %s", reason)
        record_watch_outcome(
            conn,
            budget_day_ms=day_start_ms,
            now_ms=now_ms,
            outcome=REFUSED_ALLOWANCE,
            detail=reason,
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
        # `reason` is passed through VERBATIM -- it already names the ceiling
        # and both numbers. Re-deriving which of calls/tokens/searches bound
        # would be a second implementation of `refusal_reason`'s ladder, which
        # is exactly what `budget.py` argues against.
        record_watch_outcome(
            conn,
            budget_day_ms=day_start_ms,
            now_ms=now_ms,
            outcome=REFUSED_BUDGET,
            detail=reason,
        )
        return

    staleness = StalenessConfig.load()
    # Tonight only -- never widened (#119). `end_ms` is the same bound
    # `build_ladder_payload`'s default horizon uses, computed once and handed
    # to the held-fixtures read too, so both halves of the merged list agree
    # on what "tonight" means.
    end_ms = horizon_end_ms(now_ms)
    held = _held_fixtures_kickoff_soonest(conn, now_ms=now_ms, end_ms=end_ms)
    payload = build_ladder_payload(
        conn, now_ms=now_ms, max_odds_age_ms=staleness.max_odds_age_s * 1000
    )
    ladder = _distinct_fixtures_kickoff_soonest(payload)
    # Held fixtures first, soonest kickoff first within each group -- Joe's
    # own instruction: a game he already has money on is worth scouting
    # before one he might merely bet. Deduped by `event_ticker` rather than
    # concatenated blind, so a game that is both held AND on tonight's ladder
    # is tried once, at its held (earlier) position.
    seen_event_tickers = {f["event_ticker"] for f in held}
    fixtures = held + [
        f for f in ladder if f["event_ticker"] not in seen_event_tickers
    ]

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
        # Recorded BEFORE the desk runs, not after. `_run_scout_desk` awaits
        # the whole fan-out and can raise; the decision to spend was already
        # taken at the `INSERT` above, and a recorder that only fires on a
        # clean return would under-report exactly the convenings that went
        # wrong. The `scout_briefings` row carries what came back.
        record_watch_outcome(
            conn,
            budget_day_ms=day_start_ms,
            now_ms=now_ms,
            outcome=CONVENED,
            detail=f"sent the desk on {resolved_ticker}",
        )
        await _run_scout_desk(
            db_path, row_id, config, resolved, resolved_ticker,
            trigger="auto", client_factory=client_factory,
        )
        return

    logger.info("scout watch: no eligible fixture this cycle")
    record_watch_outcome(
        conn,
        budget_day_ms=day_start_ms,
        now_ms=now_ms,
        outcome=NO_CANDIDATE,
        detail="no eligible fixture on the ladder this cycle",
    )


async def watch_scouts_forever(
    db_path,
    config_factory: Callable[[], Optional[AgentConfig]],
    client_factory: Optional[Callable[[AgentConfig], object]] = None,
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

    `client_factory` is passed straight through to `_run_scout_desk`. `None`
    -- what production passes -- means that function's own literal
    `build_client(config)` call, which is the one `tests/test_has_callers.py`
    allowlists; tests hand it a stub instead. **This module never names
    `build_client` or `structured_call` on purpose**: the billed-path
    scanner allowlists modules by the symbols they name, and every call this
    watcher causes goes out through `backend/api/routers/scout.py` and
    `backend/agents/scout_desk.py`, the two modules already on that list,
    under the same `AgentBudget` meter -- plus this module's own brakes.

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
