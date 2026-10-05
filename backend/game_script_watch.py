"""The unattended game-script watcher's decision (#217, ADR 0190, story #213).

`decide` is pure: given the clock, the fixtures, the cards that exist and the
budget's numbers, it says which games get a card built and which are refused
for a named ceiling. `load_inputs` and `record_refusals` are the small impure
edge, and `watch_game_scripts_forever` is the loop `scripts/run_loop.py`
starts behind `GAME_SCRIPT_AUTO_ENABLED` (S3b).

Choices, each stated because it was a choice:

- **Soonest kickoff first.** A game about to start is the one the card is
  for; the order is a function of the clock only, never of a price (ADR 0071).
- **The unattended share.** Building stops once the day's recorded tokens plus
  this pass's reservations would cross `1 - SCOUT_AUTO_TAP_TOKEN_SHARE` of
  `AGENT_MAX_TOKENS_PER_DAY`, so Joe's own taps keep the rest. Each card is
  reserved at `CARD_TOKEN_ESTIMATE` = 290,000, the first real card's cost
  (289,372 tokens, 2026-09-30, `agent_calls.id` 179, n = 1, #218). It was
  60,000, the leg-verdict analogue
  (`agents/leg_verdict.LEG_VERDICT_TOKEN_RESERVATION`, mean ~51K, range
  29K-90K), and was ~4.8x low. One reading is not a rate: re-read
  `agent-spend` (agent='game_script') after the first automatic Sunday.
- **Searches** are reserved at `GAME_SCRIPT_MAX_SEARCHES` (3) per card.
- **A game with a `built` or `skipped` card is done.** A refused row is not a
  card and does not count (ADR 0190 section 2 dedupe).
- **A fixture with no `game_event_ticker` is skipped, never guessed.**
- **It never convenes the scout desk** and imports nothing from it.

What this does not establish: what a card costs or whether one is any good;
that `event_links` has a link for every game (an unlinked game is silently not
built, and `load_inputs` logs how many it saw so that is countable).
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable, Mapping, Optional, Sequence

from .agents.game_script import (
    CALL_FAILED_PREFIX, GAME_SCRIPT_MAX_SEARCHES, RECHECK_MAX_SEARCHES,
)
from .agents.base import AgentConfig
from .agents.budget import AgentBudget
from .kalshi.discovery import IN_SCOPE_LEAGUES
from .store import db as store_db
from .store import game_script_cards

logger = logging.getLogger(__name__)

#: Reserved per card against the token ceiling: the first real card's cost.
CARD_TOKEN_ESTIMATE = 290_000
CARD_SEARCHES = GAME_SCRIPT_MAX_SEARCHES

#: The T-2h drop-if re-check (#289, Joe's (A) to #270). Reserved at the
#: top of the town hall's 20-40K estimate until a real one is read; one
#: search. Only for a game Joe opened, inside `RECHECK_LEAD_MS` of kickoff.
RECHECK_TOKEN_ESTIMATE = 40_000
RECHECK_SEARCHES = RECHECK_MAX_SEARCHES
RECHECK_LEAD_MS = 2 * 3_600_000
RECHECK = "recheck"

BUILD = "build"
REFUSED_BUDGET = "refused_budget"

#: A card in either of these means the game is done. A refusal is not a card.
DONE_STATUSES = ("built", "skipped")

_HOUR_MS = 3_600_000

#: A failed call (#309) is retried, but not in a tight loop: a failure whose
#: tokens were lost settles NULL usage, so the token and search brakes do not
#: see it and only the daily call ceiling would. One retry an hour per game,
#: and at most this many failed rows before the game is left to a tap.
RETRY_BACKOFF_MS = _HOUR_MS
MAX_FAILED_ATTEMPTS = 3


def _is_call_failure(card: dict) -> bool:
    return (
        card.get("status") == "refused_invalid"
        and str(card.get("reason") or "").startswith(CALL_FAILED_PREFIX)
    )


def _in_retry_pause(now_ms: int, rows: list[dict]) -> bool:
    failed = [c for c in rows if _is_call_failure(c)]
    if len(failed) >= MAX_FAILED_ATTEMPTS:
        return True
    last = max((int(c.get("built_ms") or 0) for c in failed), default=0)
    return bool(last) and now_ms - last < RETRY_BACKOFF_MS

#: A season start more than this far behind a game is last season's date, and
#: a date cut that old can no longer tell preseason from regular season: the
#: NBA and NHL regular seasons and playoffs end inside ~260 days of their
#: starts, and next season's preseason opens ~350 days after. So a game past
#: this line is refused rather than built, until the date is updated
#: (`GAME_SCRIPT_REGULAR_SEASON_STARTS`). Without it the cut fails open every
#: autumn and every preseason game costs a card (~290K tokens).
STALE_SEASON_START_DAYS = 300


def season_start_is_stale(kickoff_ms: int, start_ms: int) -> bool:
    return kickoff_ms - start_ms > STALE_SEASON_START_DAYS * 24 * _HOUR_MS


@dataclass(frozen=True)
class Fixture:
    game_event_ticker: Optional[str]  # None: no event_links row -> skipped
    sport_key: str
    kickoff_ms: int


@dataclass(frozen=True)
class WatchBudget:
    """The budget's numbers, read once. A ceiling of 0 means none is set."""

    tokens_today: int
    tokens_ceiling: int
    searches_today: int
    searches_ceiling: int
    tap_token_share: float = 0.5


@dataclass(frozen=True)
class Action:
    kind: str  # BUILD | REFUSED_BUDGET
    game_event_ticker: str
    sport_key: str
    kickoff_ms: int
    reason: Optional[str] = None  # names the ceiling on a refusal


def _token_reason(budget: WatchBudget, line: int) -> str:
    # Stable text (no running totals) so a repeated refusal is one row a day.
    return (
        f"unattended token share reached: AGENT_MAX_TOKENS_PER_DAY "
        f"{budget.tokens_ceiling} x (1 - SCOUT_AUTO_TAP_TOKEN_SHARE "
        f"{budget.tap_token_share}) = {line}; the rest is kept for taps"
    )


def _search_reason(budget: WatchBudget) -> str:
    return (
        f"AGENT_MAX_SEARCHES_PER_DAY {budget.searches_ceiling} would be "
        f"reached by another card's {CARD_SEARCHES} searches"
    )


def decide(
    now_ms: int,
    fixtures: Iterable[Fixture],
    cards: Iterable[dict],
    budget: WatchBudget,
    *,
    lead_hours: int = 24,
    sports: Optional[Iterable[str]] = None,
    season_starts: Optional[Mapping[str, int]] = None,
) -> list[Action]:
    """Actions for this pass, soonest kickoff first. Pure.

    `cards` are rows with `game_event_ticker` and `status`. `sports` limits to
    those sport keys (default: every sport is accepted; the adapter passes
    Joe's). `season_starts` maps a card sport key to its regular season's
    first ms; a game kicking off before it is preseason and is not built and
    not recorded (Joe, 2026-09-30). A game more than
    `STALE_SEASON_START_DAYS` after it is treated the same way, because the
    date is last season's (`run_pass` logs a warning naming the sport). Once a ceiling binds every later game is
    refused for the same one.
    """
    done = {
        c["game_event_ticker"] for c in cards if c.get("status") in DONE_STATUSES
    }
    cards = list(cards)
    by_game: dict[str, list[dict]] = {}
    for c in cards:
        by_game.setdefault(c["game_event_ticker"], []).append(c)
    allowed = None if sports is None else set(sports)
    horizon = now_ms + lead_hours * _HOUR_MS
    seen: set[str] = set()
    todo: list[Fixture] = []
    for f in fixtures:
        ticker = f.game_event_ticker
        if not ticker or ticker in done or ticker in seen:
            continue
        if _in_retry_pause(now_ms, by_game.get(ticker, [])):
            continue
        if allowed is not None and f.sport_key not in allowed:
            continue
        if not (now_ms < f.kickoff_ms <= horizon):
            continue
        start = (season_starts or {}).get(f.sport_key)
        if start is not None and (
            f.kickoff_ms < start or season_start_is_stale(f.kickoff_ms, start)
        ):
            continue
        seen.add(ticker)
        todo.append(f)
    todo.sort(key=lambda f: (f.kickoff_ms, f.game_event_ticker))

    token_line = (
        int(budget.tokens_ceiling * (1.0 - budget.tap_token_share))
        if budget.tokens_ceiling > 0
        else None
    )
    actions: list[Action] = []
    chosen = 0
    binding: Optional[str] = None
    for f in todo:
        if binding is None:
            n = chosen + 1
            if (
                token_line is not None
                and budget.tokens_today + n * CARD_TOKEN_ESTIMATE > token_line
            ):
                binding = _token_reason(budget, token_line)
            elif (
                budget.searches_ceiling > 0
                and budget.searches_today + n * CARD_SEARCHES
                > budget.searches_ceiling
            ):
                binding = _search_reason(budget)
        if binding is not None:
            actions.append(
                Action(REFUSED_BUDGET, f.game_event_ticker, f.sport_key, f.kickoff_ms, binding)
            )
        else:
            chosen += 1
            actions.append(Action(BUILD, f.game_event_ticker, f.sport_key, f.kickoff_ms))
    return actions


def decide_rechecks(
    now_ms: int,
    cards: Iterable[dict],
    opened: Iterable[str],
) -> list[dict]:
    """The built cards to re-check this pass, soonest kickoff first. Pure.

    A card qualifies when it is `built`, has never been re-checked, kicks off
    within `RECHECK_LEAD_MS` and has not started, and its game is in `opened`
    (Joe looked at it on the desk: Joe's (A) to #270, not every card).

    **No budget gate here, deliberately (Joe, 2026-10-03).** Until then the
    unattended token share bound re-checks as it binds builds, and on
    2026-10-02 the T-24h builds had spent that share (4.47M of a 4.5M line)
    by 22:35Z: five cards Joe had minted were never re-checked, and nothing
    said so, because a card past the line was "simply not chosen". A
    re-check runs only for a game Joe opened or minted -- spend on his
    behalf, like a tap -- so it now answers to the day's real ceilings
    alone, which `recheck_card` reads per call and STAMPS as
    `refused_budget` when they bind.
    """
    opened_set = {t.strip().upper() for t in opened}
    todo = sorted(
        (
            c for c in cards
            if c.get("status") == "built"
            and c.get("recheck_ms") is None
            and now_ms < c["kickoff_ms"] <= now_ms + RECHECK_LEAD_MS
            and c["game_event_ticker"].strip().upper() in opened_set
        ),
        key=lambda c: (c["kickoff_ms"], c["game_event_ticker"]),
    )
    return todo


# --- the impure edge ---------------------------------------------------------

_FIXTURE_SQL = (
    "SELECT f.sport_key AS sport_key, f.commence_ms AS commence_ms, "
    "       l.kalshi_event_ticker AS ticker "
    "FROM odds_fixtures f "
    "LEFT JOIN event_links l ON l.odds_event_id = f.odds_event_id "
    "WHERE f.commence_ms > ? AND f.commence_ms <= ?"
)


def _is_game_event(ticker: str) -> bool:
    return ticker.split("-")[0].endswith("GAME")


def load_inputs(
    conn: sqlite3.Connection, now_ms: int, lead_hours: int
) -> tuple[list[Fixture], list[dict]]:
    """Fixtures inside the lead window, each carrying its Kalshi game event.

    The link is `event_links` (`odds_event_id` -> `kalshi_event_ticker`), the
    one the slate and the ladder use (`backend/parlays.py` `CANDIDATE_SQL`,
    `_commence_ms_for_tickers`); a fixture links to the game, spread and prop
    events of one matchup, and the game event is the one whose series ends in
    `GAME`. A fixture with no such row comes back with `None` and is skipped by
    `decide`. Only Joe's leagues (`IN_SCOPE_LEAGUES`) are read.
    """
    horizon = now_ms + lead_hours * _HOUR_MS
    sports = set(IN_SCOPE_LEAGUES.values())
    linked: dict[str, Fixture] = {}
    unlinked = 0
    for row in conn.execute(_FIXTURE_SQL, (now_ms, horizon)).fetchall():
        if row["sport_key"] not in sports:
            continue
        ticker = row["ticker"]
        if ticker is None:
            unlinked += 1
            continue
        if not _is_game_event(ticker):
            continue
        # The card's own form ("nfl"), not the odds feed's
        # ("americanfootball_nfl"), so a refused row and a built row for one
        # sport carry the same key.
        linked[ticker] = Fixture(
            ticker, game_script_cards.sport_key_for(ticker), int(row["commence_ms"])
        )
    if unlinked:
        logger.info("game-script watch: %d fixture(s) with no Kalshi link", unlinked)
    fixtures = list(linked.values())
    cards: list[dict] = []
    if linked:
        marks = ",".join("?" * len(linked))
        cards = [
            dict(r)
            for r in conn.execute(
                "SELECT game_event_ticker, status, reason, built_ms "
                "FROM game_script_cards "
                f"WHERE game_event_ticker IN ({marks})",
                list(linked),
            ).fetchall()
        ]
    return fixtures, cards


#: How far back a visit to `/game/<event>` counts as Joe having opened it.
OPENED_LOOKBACK_MS = 48 * _HOUR_MS


def load_recheck_inputs(conn: sqlite3.Connection, now_ms: int) -> tuple[list[dict], set[str]]:
    """Built, never-re-checked cards kicking off inside `RECHECK_LEAD_MS`,
    and the games Joe opened.

    "Opened" is read from the desk's own heartbeat (`desk_attention.path`,
    one row a minute while a page is visible): a `/game/<event>` path in the
    last `OPENED_LOOKBACK_MS`. A card he minted (`combo_ticker` set) counts
    too. Both reads are bounded: the cards by kickoff, the heartbeat by its
    `seen_ms` index.
    """
    cards = [
        dict(r)
        for r in conn.execute(
            "SELECT id, game_event_ticker, kickoff_ms, status, recheck_ms, "
            "drop_if, combo_ticker FROM game_script_cards "
            "WHERE status = 'built' AND recheck_ms IS NULL "
            "AND kickoff_ms > ? AND kickoff_ms <= ?",
            (now_ms, now_ms + RECHECK_LEAD_MS),
        ).fetchall()
    ]
    opened = {c["game_event_ticker"].upper() for c in cards if c.get("combo_ticker")}
    for (path,) in conn.execute(
        "SELECT DISTINCT path FROM desk_attention "
        "WHERE seen_ms >= ? AND path LIKE '/game/%'",
        (now_ms - OPENED_LOOKBACK_MS,),
    ).fetchall():
        ticker = (path or "").split("?")[0].rstrip("/").split("/")[-1]
        if ticker:
            opened.add(ticker.upper())
    return cards, opened


def record_refusals(
    conn: sqlite3.Connection, actions: Sequence[Action], now_ms: int, day_start_ms: int
) -> int:
    """Write a `refused_budget` card row per refused game, once per budget day.

    `record_watch_outcome`'s table (`scout_watch_log`) has a closed outcome
    vocabulary for the scout desk and a CHECK on it, so it is not reused; the
    card table already has the `refused_budget` status, and the reason text is
    stable so the same refusal on the same game is not re-written every cycle
    (~144 a day). Returns rows written. Never raises: a failed write must not
    stop the pass.
    """
    written = 0
    for a in actions:
        if a.kind != REFUSED_BUDGET:
            continue
        try:
            prior = conn.execute(
                "SELECT 1 FROM game_script_cards WHERE game_event_ticker = ? "
                "AND status = 'refused_budget' AND reason = ? AND built_ms >= ?",
                (a.game_event_ticker, a.reason, day_start_ms),
            ).fetchone()
            if prior is not None:
                continue
            game_script_cards.insert_card(
                conn,
                game_event_ticker=a.game_event_ticker,
                sport_key=a.sport_key,
                kickoff_ms=a.kickoff_ms,
                built_ms=now_ms,
                status="refused_budget",
                reason=a.reason,
            )
            written += 1
        except Exception:  # noqa: BLE001 - the recorder must not fail the pass
            logger.exception("game-script watch: could not record a refusal")
    return written


# --- the loop (S3b) ------------------------------------------------------------

#: Seconds between passes. A game is built once, at T-lead, so the cadence only
#: decides how late after crossing the line it is picked up.
DEFAULT_INTERVAL_S = 900.0


async def run_pass(
    conn: sqlite3.Connection,
    agent_config: AgentConfig,
    build: Callable[[str], Awaitable[dict]],
    *,
    now_ms: int,
    lead_hours: int,
    tap_token_share: float,
    season_starts: Optional[Mapping[str, int]] = None,
    recheck: Optional[Callable[[dict], Awaitable[str]]] = None,
) -> dict:
    """One pass: read, decide, record refusals, build each chosen game in turn,
    then re-check any opened game's card inside two hours of kickoff (#289).

    `build(game_event_ticker)` is the one build path
    (`backend/api/routers/game.build_card_for_game`, bound by the caller), so
    the tap and the watcher share its reuse check and its metered call. Games
    are built one at a time, soonest first; one game's failure is logged and
    does not stop the next. Returns counts, for the log line.
    """
    fixtures, cards = load_inputs(conn, now_ms, lead_hours)
    stale = sorted({
        f.sport_key
        for f in fixtures
        if (season_starts or {}).get(f.sport_key) is not None
        and season_start_is_stale(f.kickoff_ms, season_starts[f.sport_key])
    })
    if stale:
        logger.warning(
            "game-script watch: no cards for %s -- the season start in "
            "GAME_SCRIPT_REGULAR_SEASON_STARTS is more than %d days old; "
            "set this season's date",
            ",".join(stale), STALE_SEASON_START_DAYS,
        )
    meter = AgentBudget.from_config(conn, agent_config)
    state = meter.state(now_ms)
    budget = WatchBudget(
        tokens_today=state.tokens_today,
        tokens_ceiling=state.tokens_daily_budget,
        searches_today=state.searches_today,
        searches_ceiling=state.searches_daily_budget,
        tap_token_share=tap_token_share,
    )
    actions = decide(
        now_ms, fixtures, cards, budget,
        lead_hours=lead_hours, season_starts=season_starts,
    )
    refused = record_refusals(conn, actions, now_ms, meter.day_start_ms(now_ms))
    built = failed = 0
    for action in actions:
        if action.kind != BUILD:
            continue
        try:
            await build(action.game_event_ticker)
            built += 1
        except asyncio.CancelledError:
            raise
        except Exception:                                        # noqa: BLE001
            failed += 1
            logger.exception(
                "game-script watch: build failed for %s", action.game_event_ticker
            )
    rechecked = 0
    if recheck is not None:
        recheck_cards, opened = load_recheck_inputs(conn, now_ms)
        for card in decide_rechecks(now_ms, recheck_cards, opened):
            try:
                await recheck(card)
                rechecked += 1
            except asyncio.CancelledError:
                raise
            except Exception:                                    # noqa: BLE001
                failed += 1
                logger.exception(
                    "game-script watch: re-check failed for %s", card["game_event_ticker"]
                )
    return {
        "built": built, "failed": failed, "refused_written": refused,
        "rechecked": rechecked,
    }


async def watch_game_scripts_forever(
    db_path,
    config_factory: Callable[[], Optional[AgentConfig]],
    build: Callable[[str, AgentConfig], Awaitable[dict]],
    *,
    enabled: bool,
    lead_hours: int,
    tap_token_share: float = 0.5,
    season_starts: Optional[Mapping[str, int]] = None,
    recheck: Optional[Callable[[dict, AgentConfig], Awaitable[str]]] = None,
    interval_s: float = DEFAULT_INTERVAL_S,
    sleep=asyncio.sleep,
    clock=time.time,
    max_cycles: Optional[int] = None,
) -> None:
    """The watcher as a long-running task beside `watch_scouts_forever`.

    `enabled = False` makes zero calls: `config_factory` is never invoked and
    nothing is read. A cycle that raises is logged and not re-raised, so the
    task survives to the next one. `sleep`, `clock` and `max_cycles` exist for
    tests; production passes none.
    """
    conn = store_db.connect(db_path)
    try:
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            cycles += 1
            try:
                if enabled:
                    agent_config = config_factory()
                    if agent_config is not None:
                        counts = await run_pass(
                            conn,
                            agent_config,
                            lambda ticker: build(ticker, agent_config),
                            now_ms=int(clock() * 1000),
                            lead_hours=lead_hours,
                            tap_token_share=tap_token_share,
                            season_starts=season_starts,
                            recheck=(
                                None if recheck is None
                                else (lambda card: recheck(card, agent_config))
                            ),
                        )
                        if any(counts.values()):
                            logger.info("game-script watch: %s", counts)
            except asyncio.CancelledError:
                raise
            except Exception:                                    # noqa: BLE001
                logger.exception("game-script watch cycle failed")
            await sleep(interval_s)
    finally:
        conn.close()
