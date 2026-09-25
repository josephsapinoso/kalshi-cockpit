"""Server-side resolution, caching and the background run for the leg scout
(#151/#152, ADR 0186). `backend/api/routers/leg_verdicts.py` is the only
caller.

**This module spends nothing itself.** `resolve_leg` and `cached_verdict`
are reads; the one metered call lives in `backend/agents/leg_verdict.py` and
is reached from here only through `_run_leg_verdict`, which
`tests/test_has_callers.py` tracks the same way it tracks
`backend/api/routers/scout.py::_run_scout_desk`.

**Advisory, not transactional.** Nothing here is imported by the order, RFQ
or hedge paths, and `tests/test_leg_verdicts_never_touch_money.py` fails
closed if a future change makes that true. A leg's TAKE/PASS is shown beside
the buy button; it never blocks it.

Three things this module resolves server-side, so nothing about the price or
the clock can arrive from the browser:

- the ask of the side being bought, from `backend.parlays.leg_facts` /
  `_ask_facts_for_side` -- the one definition of a leg's price this repo has;
- the game's kickoff, from the same `event_links` -> `odds_snapshots` chain
  `backend.parlays._commence_ms_for_tickers` reads (never
  `kalshi_events.commence_ms`, which runs ~3 hours late on game series,
  ADR 0006);
- the desk's newest briefing on the leg's GAME, via
  `backend.parlays._leg_scouting` -- the #150 join that matches by fixture
  segment and league, not by market ticker, so a spread or total leg still
  sees a briefing filed against the game's moneyline.

What this module does not establish: that a verdict is any good (the
pre-registered measurement's job), or that caching a verdict for
`fresh_hours` is the right window (Joe's own choice, `LegVerdictConfig`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence, Union

from .agents.base import AgentConfig, build_client
from .agents.budget import AgentBudget
from .agents.leg_verdict import build_prompt, give_leg_verdict
from .config import LegVerdictConfig
from .core.prices import format_price
from .parlays import _ask_facts_for_side, _leg_scouting, _scout_facts, leg_facts
from .store import db

logger = logging.getLogger(__name__)

#: A `running` row still owned by a live process is reported `pending`; past
#: this it is treated the same as no row at all, so a fresh call may be
#: tried rather than a phone waiting forever on a process that died.
RUNNING_PATIENCE_MS = 5 * 60 * 1000

#: A `failed` row blocks an automatic retry for this long -- the counterpart
#: to `RUNNING_PATIENCE_MS`, so a call that died does not get re-tried on
#: every tap of a page left open.
FAILED_RETRY_BLOCK_MS = 15 * 60 * 1000


@dataclass(frozen=True)
class LegContext:
    """What `resolve_leg` read, server-side, for one (ticker, side)."""

    ticker: str
    side: str
    label: str
    ask_tenths: int
    ask_display: str
    event_title: str
    league: Optional[str]
    commence_ms: int
    briefing_id: Optional[int]
    briefing_text: Optional[str]


@dataclass(frozen=True)
class LegRefusal:
    """`resolve_leg` found a reason this leg cannot be scouted right now.

    Never carries a partial context -- a refused leg spends nothing and
    writes no row, so there is nothing else to carry.
    """

    reason: str


def _fixture_for_ticker(conn, ticker: str) -> Optional[dict]:
    """`(event_title, league, commence_ms)` for the leg's GAME, or `None`.

    The same join shape as `_resolve_scout_fixture`
    (`backend/api/routers/scout.py`), but keyed straight off
    `kalshi_markets` -> `kalshi_events` -> `event_links` rather than through
    a `recommendations` row: a leg the ladder never priced (a spread, or a
    prop the engine has not reached) can still be a leg Joe is about to buy,
    and it must not need a `recommendations` row to be scoutable.

    `league` is the sportsbook's own `sport_key` (`odds_snapshots.sport_key`,
    e.g. `basketball_wnba`), never `event_links.league` (Kalshi's competition
    string, e.g. `"Pro Basketball (W)"`) -- the same choice `_leg_scouting`'s
    docstring warns about for a different column of the same name.
    """
    market = conn.execute(
        "SELECT m.event_ticker AS event_ticker, e.title AS kalshi_title "
        "FROM kalshi_markets m "
        "JOIN kalshi_events e ON e.event_ticker = m.event_ticker "
        "WHERE m.ticker = ?",
        (ticker,),
    ).fetchone()
    if not market:
        return None
    link = conn.execute(
        "SELECT odds_event_id FROM event_links "
        "WHERE kalshi_event_ticker = ? LIMIT 1",
        (market["event_ticker"],),
    ).fetchone()
    if not link:
        return None
    # SQLite's bare-column rule: with a lone MIN() aggregate and no GROUP BY,
    # the bare columns come from the row that achieved the minimum -- the
    # earliest snapshot, whose team names and sport never change within one
    # fixture. Same trick `_resolve_scout_fixture` uses.
    fixture = conn.execute(
        "SELECT home_team, away_team, sport_key, MIN(commence_ms) AS commence_ms "
        "FROM odds_snapshots WHERE odds_event_id = ?",
        (link["odds_event_id"],),
    ).fetchone()
    if not fixture or fixture["home_team"] is None:
        return None
    title = market["kalshi_title"] or f"{fixture['away_team']} at {fixture['home_team']}"
    return {
        "event_title": title,
        "league": fixture["sport_key"],
        "commence_ms": fixture["commence_ms"],
    }


def _briefing_for_ticker(
    conn, ticker: str, *, now_ms: int
) -> tuple[Optional[int], Optional[str]]:
    """`(briefing_id, briefing_text)` for the leg's GAME, or `(None, None)`.

    Goes through `_leg_scouting` -- the #150 same-game join, matched by
    fixture segment and league rather than by market ticker, so a spread or
    total leg still sees a briefing filed against the game's moneyline.

    `_leg_scouting` does not select `scout_briefings.id` (it answers a
    display question, not a foreign-key one), so the id is recovered by a
    second, narrow lookup on the same ticker and `requested_ms` it already
    returned -- both of which came out of the same row, so the lookup finds
    it back rather than guessing at one.

    `briefing_text` is the headline plus any non-clear tiles, in the same
    shape `_scout_facts` renders for the API -- prose, never a number, the
    same rule `LegVerdict` itself is held to.
    """
    scouting = _leg_scouting(conn, [ticker])
    row = scouting.get(ticker)
    if row is None:
        return None, None
    facts = _scout_facts(row, now_ms=now_ms)
    if facts["scout"] not in ("briefed", "filed_nothing"):
        # still running, refused, or failed -- nothing usable to hand the seat
        return None, None
    id_row = conn.execute(
        "SELECT id FROM scout_briefings WHERE ticker = ? AND requested_ms = ? "
        "ORDER BY id DESC LIMIT 1",
        (row["scout_ticker"], row["requested_ms"]),
    ).fetchone()
    briefing_id = int(id_row["id"]) if id_row else None
    parts: list[str] = []
    if facts["scout_headline"]:
        parts.append(facts["scout_headline"])
    for flag in facts["scout_flags"]:
        category = flag.get("category")
        state = flag.get("state")
        note = flag.get("note")
        parts.append(f"{category} ({state}): {note}" if note else f"{category}: {state}")
    return briefing_id, ("\n".join(parts) if parts else None)


def resolve_leg(conn, ticker: str, side: str, now_ms: int) -> Union[LegContext, LegRefusal]:
    """One leg, resolved server-side, or the named reason it cannot be.

    Refusal reasons, in the order checked: a bad `side`, no linked
    sportsbook fixture, no known kickoff, kickoff already passed, no quote
    for the side being bought. Every one of these spends nothing -- they are
    read-only checks that run before any budget is even consulted.
    """
    if side not in ("yes", "no"):
        return LegRefusal(f"a leg's side is 'yes' or 'no', not {side!r}")

    market = conn.execute(
        "SELECT title FROM kalshi_markets WHERE ticker = ?", (ticker,)
    ).fetchone()
    label = market["title"] if market and market["title"] else ticker

    fixture = _fixture_for_ticker(conn, ticker)
    if fixture is None:
        return LegRefusal(
            f"{ticker} has no linked sportsbook fixture, so the desk cannot "
            f"tell which game this is."
        )
    commence_ms = fixture["commence_ms"]
    if commence_ms is None:
        return LegRefusal(f"{ticker}'s kickoff is unknown.")
    if now_ms >= commence_ms:
        return LegRefusal("This game has already started.")

    facts = leg_facts(conn, [ticker], now_ms=now_ms).get(ticker, {})
    ask_tenths, ask_display, _depth = _ask_facts_for_side(facts, side)
    if ask_tenths is None:
        return LegRefusal(f"{ticker} has no quote for the {side.upper()} side right now.")

    briefing_id, briefing_text = _briefing_for_ticker(conn, ticker, now_ms=now_ms)

    return LegContext(
        ticker=ticker,
        side=side,
        label=label,
        ask_tenths=int(ask_tenths),
        ask_display=ask_display,
        event_title=fixture["event_title"],
        league=fixture["league"],
        commence_ms=int(commence_ms),
        briefing_id=briefing_id,
        briefing_text=briefing_text,
    )


def cached_verdict(
    conn,
    ticker: str,
    side: str,
    *,
    ask_tenths: int,
    commence_ms: Optional[int],
    config: LegVerdictConfig,
    now_ms: int,
):
    """The newest `leg_verdicts` row to SERVE without a fresh call, or `None`.

    `None` means "run a fresh call" -- either nothing was ever requested for
    this leg, or what exists is too old, moved too far from the current ask,
    or is a `refused` row (never reused: a refusal named a reason that may
    no longer hold, and the whole point of asking again is to let the
    budget answer that question fresh, not to remember yesterday's no).

    - a `complete` row younger than `config.fresh_hours`, whose recorded ask
      is within `config.price_move_tenths` of the ask right now, and whose
      game has not started, is served as-is;
    - a `running` row younger than `RUNNING_PATIENCE_MS` is served as
      pending -- there is already a call in flight, and sending a second one
      would double the spend for the same leg;
    - a `failed` row younger than `FAILED_RETRY_BLOCK_MS` is served as-is
      (no automatic retry yet);
    - anything else falls through to `None`.
    """
    row = conn.execute(
        "SELECT * FROM leg_verdicts WHERE ticker = ? AND side = ? "
        "ORDER BY requested_ms DESC, id DESC LIMIT 1",
        (ticker, side),
    ).fetchone()
    if row is None:
        return None
    age_ms = now_ms - int(row["requested_ms"])
    status = row["status"]
    if status == "running":
        return row if age_ms < RUNNING_PATIENCE_MS else None
    if status == "failed":
        return row if age_ms < FAILED_RETRY_BLOCK_MS else None
    if status == "refused":
        return None
    if status == "complete":
        fresh_window_ms = config.fresh_hours * 3600 * 1000
        if age_ms >= fresh_window_ms:
            return None
        recorded_ask = row["ask_tenths"]
        if recorded_ask is None or abs(int(recorded_ask) - int(ask_tenths)) > config.price_move_tenths:
            return None
        if commence_ms is not None and now_ms >= commence_ms:
            return None
        return row
    return None


def _row_to_response(row, *, now_ms: int) -> dict:
    """One `leg_verdicts` row, rendered into the frozen response shape.

    **The response has four states; the table has four statuses, but they
    are not the same four.** `complete` -> `cached` (served without a fresh
    call) and `running` -> `pending` map one to one. `refused` AND `failed`
    both render as `refused`: to the reader waiting on a verdict, "a ceiling
    said no" and "the call died and will not be retried yet" are the same
    fact -- nothing is coming right now, and `refusal_reason` says why.
    Splitting them into a fifth state would let a caller branch on a
    distinction Joe was never going to act on differently.
    """
    status = row["status"]
    ask_tenths = row["ask_tenths"]
    ask_display = format_price(ask_tenths) if ask_tenths is not None else None
    base = {
        "ticker": row["ticker"],
        "side": row["side"],
        "id": int(row["id"]),
        "ask_display_at_verdict": ask_display,
    }
    if status == "complete":
        stamp = row["completed_ms"] or row["requested_ms"]
        base.update(
            state="cached",
            verdict=row["verdict"],
            reason=row["reason"],
            age_ms=max(0, now_ms - int(stamp)),
            refusal_reason=None,
        )
        return base
    if status == "running":
        base.update(
            state="pending",
            verdict=None,
            reason=None,
            age_ms=max(0, now_ms - int(row["requested_ms"])),
            refusal_reason=None,
        )
        return base
    # failed or refused
    stamp = row["completed_ms"] or row["requested_ms"]
    base.update(
        state="refused",
        verdict=None,
        reason=None,
        age_ms=max(0, now_ms - int(stamp)),
        refusal_reason=row["refusal_reason"],
    )
    return base


def _absent_response(ticker: str, side: str) -> dict:
    return {
        "ticker": ticker,
        "side": side,
        "state": "none",
        "id": None,
        "verdict": None,
        "reason": None,
        "ask_display_at_verdict": None,
        "age_ms": None,
        "refusal_reason": None,
    }


def read_verdicts(conn, legs: Sequence[tuple[str, str]], *, now_ms: int) -> list[dict]:
    """The newest row for each `(ticker, side)`, or the honest `"none"`.

    Read-only: spends nothing, and never convenes anything. Every leg asked
    about is present in the result, in the order asked -- a caller must not
    have to tell "no verdict was ever requested" apart from "I forgot to
    ask for this one".
    """
    out: list[dict] = []
    for ticker, side in legs:
        row = conn.execute(
            "SELECT * FROM leg_verdicts WHERE ticker = ? AND side = ? "
            "ORDER BY requested_ms DESC, id DESC LIMIT 1",
            (ticker, side),
        ).fetchone()
        out.append(
            _absent_response(ticker, side)
            if row is None
            else _row_to_response(row, now_ms=now_ms)
        )
    return out


def _ask_phrase(ctx: LegContext) -> str:
    """The sentence `build_prompt` wants, from the bare price string
    `resolve_leg` recorded (`"43c"`). Kept separate from the API's own
    `ask_display_at_verdict`, which stays the bare price -- the prompt wants
    a sentence, the phone wants a chip."""
    return f"Kalshi asks {ctx.ask_display} for {ctx.side.upper()}"


async def _run_leg_verdict(
    db_path,
    row_id: int,
    config: AgentConfig,
    ctx: LegContext,
    *,
    client_factory=None,
) -> None:
    """The background half of one leg verdict. Owns its own connection.

    Shaped like `backend/api/routers/scout.py::_run_scout_desk`:
    `client_factory` defaults to `None` rather than to `build_client`, so
    `tests/test_has_callers.py` can pin the literal `build_client(config)`
    call below as the one site here that constructs a billed client, and a
    caller (tests) may still override it.

    Runs after the row has already been inserted `running` (the route
    returns its id in the 202 before this executes), so nothing here may
    raise out: every failure ends in the row being marked `failed`, because a
    verdict that dies silently is indistinguishable from one still running.
    """
    conn = db.open_db(db_path)
    try:
        budget = AgentBudget.from_config(conn, config)
        client = (
            build_client(config) if client_factory is None else client_factory(config)
        )
        commence_iso = (
            datetime.fromtimestamp(ctx.commence_ms / 1000, tz=timezone.utc).isoformat()
            if ctx.commence_ms is not None
            else None
        )
        prompt = build_prompt(
            label=ctx.label,
            side=ctx.side,
            ask_display=_ask_phrase(ctx),
            event_title=ctx.event_title,
            league=ctx.league or "unknown",
            commence_iso=commence_iso,
            briefing_text=ctx.briefing_text,
        )
        result = await give_leg_verdict(
            client,
            config,
            budget,
            ticker=ctx.ticker,
            side=ctx.side,
            prompt=prompt,
            now_ms=db.now_ms(),
        )
        verdict = result.verdict.verdict if result.verdict is not None else None
        reason = result.verdict.reason if result.verdict is not None else None
        usage = result.usage
        conn.execute(
            "UPDATE leg_verdicts SET status = ?, completed_ms = ?, verdict = ?, "
            "reason = ?, refusal_reason = ?, agent_call_id = ?, input_tokens = ?, "
            "output_tokens = ?, web_searches = ? WHERE id = ?",
            (
                result.status,
                db.now_ms(),
                verdict,
                reason,
                result.refusal_reason,
                result.agent_call_id,
                usage.input_tokens if usage is not None else None,
                usage.output_tokens if usage is not None else None,
                usage.web_searches if usage is not None else None,
                row_id,
            ),
        )
        conn.commit()
    except Exception:
        logger.exception("leg verdict %d (%s %s) died", row_id, ctx.ticker, ctx.side)
        conn.execute(
            "UPDATE leg_verdicts SET status = 'failed', completed_ms = ? WHERE id = ?",
            (db.now_ms(), row_id),
        )
        conn.commit()
    finally:
        conn.close()


def insert_running_row(conn, ctx: LegContext, *, card_key, model: str, trigger: str, now_ms: int) -> int:
    """Write the `running` row a background call will settle. Returns its id.

    Called only after the route's own `AgentBudget.refusal_reason` check
    passed, so every row this writes represents a call the day could afford
    at the moment it was reserved.
    """
    cursor = conn.execute(
        "INSERT INTO leg_verdicts (ticker, side, card_key, ask_tenths, "
        "commence_ms, requested_ms, status, model, trigger, briefing_id) "
        "VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)",
        (
            ctx.ticker,
            ctx.side,
            card_key,
            ctx.ask_tenths,
            ctx.commence_ms,
            now_ms,
            model,
            trigger,
            ctx.briefing_id,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)
