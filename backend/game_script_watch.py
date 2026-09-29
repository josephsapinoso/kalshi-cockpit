"""The unattended game-script watcher's decision (#217, ADR 0190, story #213).

`decide` is pure: given the clock, the fixtures, the cards that exist and the
budget's numbers, it says which games get a card built and which are refused
for a named ceiling. `load_inputs` and `record_refusals` are the small impure
edge. Runner wiring and the flag are S3b and are not here.

Choices, each stated because it was a choice:

- **Soonest kickoff first.** A game about to start is the one the card is
  for; the order is a function of the clock only, never of a price (ADR 0071).
- **The unattended share.** Building stops once the day's recorded tokens plus
  this pass's reservations would cross `1 - SCOUT_AUTO_TAP_TOKEN_SHARE` of
  `AGENT_MAX_TOKENS_PER_DAY`, so Joe's own taps keep the rest. Each card is
  reserved at `CARD_TOKEN_ESTIMATE` = 60,000, the leg-verdict analogue
  (`agents/leg_verdict.LEG_VERDICT_TOKEN_RESERVATION`, mean ~51K, range
  29K-90K). **That is a borrowed number**: no game-script card has been read
  from `agent-spend` yet (#213 gates the live flag on that reading).
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

import logging
import sqlite3
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from .agents.game_script import GAME_SCRIPT_MAX_SEARCHES
from .agents.leg_verdict import LEG_VERDICT_TOKEN_RESERVATION
from .kalshi.discovery import IN_SCOPE_LEAGUES
from .store import game_script_cards

logger = logging.getLogger(__name__)

#: Reserved per card against the token ceiling. Borrowed from the leg verdict.
CARD_TOKEN_ESTIMATE = LEG_VERDICT_TOKEN_RESERVATION
CARD_SEARCHES = GAME_SCRIPT_MAX_SEARCHES

BUILD = "build"
REFUSED_BUDGET = "refused_budget"

#: A card in either of these means the game is done. A refusal is not a card.
DONE_STATUSES = ("built", "skipped")

_HOUR_MS = 3_600_000


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
) -> list[Action]:
    """Actions for this pass, soonest kickoff first. Pure.

    `cards` are rows with `game_event_ticker` and `status`. `sports` limits to
    those sport keys (default: every sport is accepted; the adapter passes
    Joe's). Once a ceiling binds every later game is refused for the same one.
    """
    done = {
        c["game_event_ticker"] for c in cards if c.get("status") in DONE_STATUSES
    }
    allowed = None if sports is None else set(sports)
    horizon = now_ms + lead_hours * _HOUR_MS
    seen: set[str] = set()
    todo: list[Fixture] = []
    for f in fixtures:
        ticker = f.game_event_ticker
        if not ticker or ticker in done or ticker in seen:
            continue
        if allowed is not None and f.sport_key not in allowed:
            continue
        if not (now_ms < f.kickoff_ms <= horizon):
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
        linked[ticker] = Fixture(ticker, row["sport_key"], int(row["commence_ms"]))
    if unlinked:
        logger.info("game-script watch: %d fixture(s) with no Kalshi link", unlinked)
    fixtures = list(linked.values())
    cards: list[dict] = []
    if linked:
        marks = ",".join("?" * len(linked))
        cards = [
            dict(r)
            for r in conn.execute(
                "SELECT game_event_ticker, status FROM game_script_cards "
                f"WHERE game_event_ticker IN ({marks})",
                list(linked),
            ).fetchall()
        ]
    return fixtures, cards


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
