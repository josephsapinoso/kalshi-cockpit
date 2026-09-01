"""Joe's calibration bet log: the write path for `bet_estimates`.

Implements §9 of the calibration registration
(`docs/measurements/2026-08-17-preregistration-joe-calibration-bet-log.md`,
as amended). §9 governs: if this module and §9 disagree, this module is wrong.

Joe types two things -- a ticker and P(YES) in basis points -- plus one 0/1
answer tapped before the probability input enables. Everything else here is
derived from the ticker and the clock, or captured from the venue at estimate
time. Nothing in this module writes to `recommendations`, ever: that table is
the registered population of a *different* measurement (ADR 0021/0034) and a
hand estimate landing in it would contaminate that record silently.

What this module does not establish: anything. It is a recorder. The analysis
(one look, at the registered stop) lives elsewhere and is embargoed until the
stopping rule fires; the one hard rule enforced here is that the estimate-time
quote is captured and **never returned to a caller that could render it**.

Two regimes now share this table -- v32, ticket #11, 2026-09-01
---------------------------------------------------------------
`is_study_row = 1` is the calibration study's own record: collected under ADR
0044's promise that its captured quote and its score would never be shown to
the person being measured. There is exactly one such row and the promise holds,
because at n = 1 keeping it costs nothing.

`is_study_row = 0` is a **decoupled call**: Joe logging what he thinks from a
price-free screen that says at log time it will be scored against Kalshi's
close and read back to him. It is not tied to a bet -- the premise that it was
turned out to be false (1 typed estimate ever, 0 hand bets through the tool's
order path, because the Kalshi app is faster and he is already in it), and
tying the number to a position discards nearly all of it for no gain.

The score is written by `analysis.clv.score_bet_estimate_calls` into the four
`call_*` columns and read back one row at a time by `last_scored_call` below.
**It grades him against the market, never against the outcome**, so it measures
disagreement with Kalshi and not correctness; it is a display and not a verdict,
and the full statement of what it cannot establish is in those two docstrings.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from backend.portfolio_poll import STUDY_START_MS_KEY
from backend.store import db

# Series prefix -> the registration's fixed sport enum. Matched against the
# series component of the ticker (everything before the first hyphen), longest
# prefix first so `KXNCAAB` is never swallowed by a shorter `KXN...` entry.
#
# An unknown prefix maps to (is_sports=0, sport=None) rather than guessing:
# non-sports rows are excluded from the primary population and reported
# separately (§2), so the cost of a false negative is a row landing in the
# separately-reported bucket -- visible -- while a false positive would pool
# a Fed market into the sports population in silence.
_SPORT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("KXNCAAF", "ncaaf"),
    ("KXNCAAB", "ncaab"),
    ("KXWNBA", "wnba"),
    ("KXMLB", "mlb"),
    ("KXNBA", "nba"),
    ("KXNFL", "nfl"),
    ("KXNHL", "nhl"),
    ("KXATP", "tennis"),
    ("KXWTA", "tennis"),
    ("KXUFC", "mma"),
    ("KXPGA", "golf"),
    ("KXCFB", "ncaaf"),
    ("KXEPL", "soccer"),
    ("KXUCL", "soccer"),
    ("KXMLS", "soccer"),
)

# Kalshi's Multi-Variate Event prefix. `kalshi/combos.py` and
# `kalshi/discovery.py` (JUNK_PREFIX) both key on the same string; a compound
# stated probability has no single settlement to score against, so §2 excludes
# these structurally.
_MULTI_LEG_PREFIX = "KXMVE"


def series_of(ticker: str) -> str:
    """The series component: `KXMLBGAME-26AUG09...` -> `KXMLBGAME`."""
    return ticker.split("-", 1)[0].upper()


def classify_ticker(ticker: str) -> tuple[int, Optional[str], int]:
    """(is_sports, sport, is_multi_leg), from the ticker string alone.

    String-only on purpose: a hand bet can be on a market discovery has never
    seen (UFC, ATP doubles, non-sports), so a classification that needed a
    `kalshi_markets` row would fail exactly where the registration says the
    coverage gap is (Amendment A6).
    """
    series = series_of(ticker)
    if series.startswith(_MULTI_LEG_PREFIX):
        return 0, None, 1
    for prefix, sport in _SPORT_PREFIXES:
        if series.startswith(prefix):
            return 1, sport, 0
    return 0, None, 0


def market_context(
    conn: sqlite3.Connection, ticker: str
) -> tuple[Optional[str], Optional[int]]:
    """(event_ticker, commence_ms) from the discovery record, when it exists.

    Both are None for an undiscovered market. `cluster_key` then falls back to
    the ticker itself (§9.3: COALESCE(event_ticker, ticker)) and `is_in_play`
    to 0 -- a claim of "in play" needs a commence time to stand on.
    """
    row = conn.execute(
        """
        SELECT m.event_ticker, e.commence_ms
        FROM kalshi_markets m
        LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker
        WHERE m.ticker = ?
        """,
        (ticker,),
    ).fetchone()
    if row is None:
        return None, None
    return row["event_ticker"], row["commence_ms"]


def record_estimate(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    stated_probability_bp: int,
    estimate_server_ms: int,
    had_already_opened_kalshi: Optional[int] = None,
    estimate_client_ms: Optional[int] = None,
    server_yes_bid_tenths: Optional[int] = None,
    server_yes_ask_tenths: Optional[int] = None,
    server_quote_observed_ms: Optional[int] = None,
    server_quote_unreadable_reason: Optional[str] = None,
) -> int:
    """Write one estimate row. Returns the row id.

    The caller supplies the quote fields it captured (or the reason it could
    not); this function derives everything else. It never raises on a missing
    discovery row -- an undiscovered ticker is a registered, expected case.
    """
    if not (1 <= stated_probability_bp <= 9999):
        raise ValueError(
            f"stated_probability_bp must be 1..9999, got {stated_probability_bp}"
        )
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("ticker is empty")
    is_sports, sport, is_multi_leg = classify_ticker(ticker)
    event_ticker, commence_ms = market_context(conn, ticker)
    cluster_key = event_ticker or ticker
    is_in_play = int(commence_ms is not None and estimate_server_ms >= commence_ms)
    cur = conn.execute(
        """
        INSERT INTO bet_estimates (
            ticker, stated_probability_bp, estimate_server_ms,
            estimate_client_ms, had_already_opened_kalshi, cluster_key,
            server_yes_bid_tenths, server_yes_ask_tenths,
            server_quote_observed_ms, server_quote_unreadable_reason,
            is_in_play, is_sports, is_multi_leg, sport, is_study_row
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker,
            stated_probability_bp,
            estimate_server_ms,
            estimate_client_ms,
            had_already_opened_kalshi,
            cluster_key,
            server_yes_bid_tenths,
            server_yes_ask_tenths,
            server_quote_observed_ms,
            server_quote_unreadable_reason,
            is_in_play,
            is_sports,
            is_multi_leg,
            sport,
            # 0 -- a decoupled call, not a study row (v32, ticket #11).
            #
            # **A literal and not a parameter, deliberately.** The study is
            # stopped and terminal (Amendment 2, 2026-08-20): there is no
            # production reason to write a study row ever again, and a
            # parameter would be a door into a closed regime. The column's
            # DEFAULT is 1, so a *forgotten* value is embargoed rather than
            # rendered -- the safe direction -- and this line is what makes
            # the deliberate value the other one.
            0,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def revise_estimate(
    conn: sqlite3.Connection,
    estimate_id: int,
    *,
    reason: str,
    revised_ms: int,
) -> bool:
    """Flag an estimate revised, with the reason on an append-only row.

    §7.4: the probability itself is never edited -- the DB trigger rejects
    that regardless of what any caller intends. This sets
    `stated_probability_is_revised = 1` (excluding the row per §2) and appends
    the reason to `bet_estimate_revisions`. Returns False when no such row
    exists.
    """
    reason = reason.strip()
    if not reason:
        raise ValueError("a revision must carry a reason")
    row = conn.execute(
        "SELECT id FROM bet_estimates WHERE id = ?", (estimate_id,)
    ).fetchone()
    if row is None:
        return False
    conn.execute(
        "UPDATE bet_estimates SET stated_probability_is_revised = 1 "
        "WHERE id = ?",
        (estimate_id,),
    )
    conn.execute(
        "INSERT INTO bet_estimate_revisions (estimate_id, reason, revised_ms) "
        "VALUES (?, ?, ?)",
        (estimate_id, reason, revised_ms),
    )
    conn.commit()
    return True


# Embargo-safe columns, and ONLY these. The estimate-time quote
# (`server_yes_*_tenths`), the outcome fields, match status and anything
# aggregable stay out of every payload until the registered stop (§5, A7).
_SAFE_COLUMNS = (
    "id",
    "ticker",
    "stated_probability_bp",
    "estimate_server_ms",
    "had_already_opened_kalshi",
    "stated_probability_is_revised",
)


def recent_estimates(
    conn: sqlite3.Connection, *, limit: int = 10
) -> list[dict[str, Any]]:
    """The last few entries, embargo-safe fields only.

    Exists so the phone can confirm "it saved" and pick a row to revise. What
    Joe typed is not embargoed from Joe; what the server captured is.
    """
    rows = conn.execute(
        f"SELECT {', '.join(_SAFE_COLUMNS)} FROM bet_estimates "
        "ORDER BY estimate_server_ms DESC, id DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [dict(row) for row in rows]


def last_scored_call(conn: sqlite3.Connection) -> Optional[dict[str, Any]]:
    """The most recently scored decoupled call. **One, or None. Never a list.**

    Ticket #11 decisions 8 and 9: logging the next call shows the last one's
    result, where it can still change behaviour, and `/bets` is the archive.
    The singular return is the design, not an optimisation -- decision 8 reads
    *"one call at a time until 30 scored"*, and the reason is that **a list is
    a scoreboard with extra steps**: five rows on one screen is an average the
    reader computes by eye, and eye-aggregation is still aggregation. So there
    is no `limit`, no offset and no second row to ask for.

    What it cannot establish
    ------------------------
    The number here is Joe's stated probability minus the closing YES mid: it
    grades him **against the market, never against the outcome**. One result
    cannot grade a probability -- a good 58% call loses 42% of the time -- and
    without settlements there is no way to separate "Joe has an edge" from
    "Joe is noisy" (ADR 0037: the in-house model's own error, 4.04 points,
    exceeded its whole disagreement with Kalshi, 3.72). It is a **display**.
    A verdict is a separate pre-registration.

    Fields, and the one that is arithmetic rather than storage:

    - `stated_probability_bp` -- what he typed, in basis points.
    - `call_clv_tenths` -- the score, in tenths of a percent. Positive means
      he said higher than Kalshi closed.
    - `closing_mid_tenths` -- **recovered, not read.** `stated / 10 - clv` is
      exact, because `stated_probability_bp` is write-once (the DB trigger)
      and `call_clv_tenths` was written once with the score. Reading it back
      from `closing_lines` would be *wrong*: `store_closing_line` upserts, so
      that row can move after the score was taken, and the screen would then
      show a mid the verdict was not computed from.
    - `is_in_play` -- decision 14. In-play calls are a different skill and
      must never share a denominator with pre-game ones. Carried so a consumer
      can separate them; nothing here pools, so nothing here can breach it.
    - `is_study_row` -- always 0 by construction (the WHERE clause). Carried
      because the embargo walker keys on it: a payload may only show a score
      if it says out loud which regime the row belongs to.

    Returns `None` when nothing has been scored yet -- not a zero, and not an
    empty score. "No call has been graded" and "your call scored 0.0" are
    different states and this repo has collapsed that pair before.
    """
    row = conn.execute(
        "SELECT id, ticker, stated_probability_bp, estimate_server_ms, "
        "is_in_play, is_study_row, stated_probability_is_revised, "
        "call_clv_tenths, call_clv_horizon_hours, call_clv_scored_ms "
        "FROM bet_estimates "
        "WHERE call_clv_scored_ms IS NOT NULL AND is_study_row = 0 "
        "ORDER BY call_clv_scored_ms DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    call = dict(row)
    call["closing_mid_tenths"] = (
        call["stated_probability_bp"] / 10 - call["call_clv_tenths"]
    )
    return call


def search_markets(
    conn: sqlite3.Connection,
    query: str,
    *,
    now_ms: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Markets matching `query`, for the one-tap picker. No prices, ever.

    Searches ticker, title and player name over markets that are still open
    (close in the future, or status active). Ordered soonest-closing first,
    because the market Joe is about to bet is almost always the next game.
    """
    like = f"%{query.strip()}%"
    rows = conn.execute(
        """
        SELECT m.ticker, m.title, m.player_name, m.event_ticker,
               e.title AS event_title, m.close_ms
        FROM kalshi_markets m
        LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker
        WHERE (m.ticker LIKE ? OR m.title LIKE ? OR m.player_name LIKE ?
               OR e.title LIKE ?)
          AND (m.close_ms IS NULL OR m.close_ms > ?)
          AND (m.status IS NULL OR m.status = 'active')
        ORDER BY m.close_ms IS NULL, m.close_ms ASC
        LIMIT ?
        """,
        (like, like, like, like, now_ms, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]


# The money arm's ceiling, in dollars. Joe's ruling (2026-08-18, recorded in
# tasks/NEXT.md and registration A2): $100 is a hard cumulative TOTAL, not
# weekly, and when it is reached everything stops, permanently. A constant
# rather than config, deliberately -- the arm is REGISTERED (§5 arm 3, as
# amended by A2), and changing this number is amending the registration.
STUDY_LOSS_CEILING_DOLLARS = 100.0

# The study's terminal state. Joe stopped it on 2026-08-20 ~22:05Z ("just
# scrap it. I am a newbie bettor.") -- registration Amendment 2: STOPPED
# WITHOUT RESULT, nothing scored, the recording machinery kept on its own
# justifications. A constant rather than a DB row, deliberately: the stop is
# REGISTERED and terminal, and reopening is a NEW registration (new code),
# so representing it as mutable state would misdescribe it. This is
# 2026-08-20T22:05:00Z in epoch milliseconds.
STUDY_STOPPED_BY_OWNER_MS = 1787263500000
STUDY_TERMINAL_STATE = "stopped_without_result"


def study_loss_dollars(conn: sqlite3.Connection) -> Optional[float]:
    """Cumulative net realised loss since study start, in dollars. §5 arm 3.

    The registered formula, verbatim from Amendment A2: "sum(payout - cost -
    fee) over settled positions, where payout is contracts x $1 on a win and
    $0 on a loss", over study-period `venue_settlements`. This function
    returns the NEGATION of that sum -- a positive number is money lost -- so
    the arm fires when the return value reaches `STUDY_LOSS_CEILING_DOLLARS`.

    Why reading this before the stop does not violate the embargo (A7, and
    the partner's explicit ruling 2026-08-18): §5 forbids aggregates over
    *the estimate log*. This reads `venue_settlements` -- Joe's own money,
    which he sees in the Kalshi app regardless -- and touches no estimate
    row. The one guard A7 states is real: nothing derived from this may be
    attributed to logged bets, split into a win rate, or scoped to the study
    population. It is one number about the wallet, not about the log.

    Returns `None` -- refusal, never 0.0 -- when the study has not been
    stamped open, or when ANY study-period settlement row cannot carry the
    registered formula: an unreadable entry price or fee, or a
    `market_result` that is neither "yes" nor "no" (a void has no registered
    payout and inventing one here would silently amend the stopping rule).
    An empty settlement set with the study open is a true $0.00, not a
    refusal. Callers must treat `None` as "cannot know", not "not stopped".
    """
    start_text = db.get_meta(conn, STUDY_START_MS_KEY)
    if start_text is None:
        return None
    rows = conn.execute(
        "SELECT side, contracts, entry_price_tenths, fee_cost_tenths, "
        "market_result FROM venue_settlements WHERE settled_ms >= ?",
        (int(start_text),),
    ).fetchall()
    net_tenths = Decimal(0)
    for row in rows:
        result = row["market_result"]
        if result not in ("yes", "no"):
            return None
        if row["entry_price_tenths"] is None or row["fee_cost_tenths"] is None:
            return None
        try:
            contracts = Decimal(str(row["contracts"]))
        except InvalidOperation:
            return None
        if not contracts.is_finite() or contracts < 0:
            return None
        cost = contracts * row["entry_price_tenths"]
        payout = contracts * 1000 if result == row["side"] else Decimal(0)
        net_tenths += payout - cost - Decimal(row["fee_cost_tenths"])
    return float(-net_tenths / 1000)


def study_stop_fired(conn: sqlite3.Connection) -> Optional[bool]:
    """Whether the money arm has fired. Tri-state, and the `None` matters.

    `True` / `False` only when the loss is computable; `None` when it is not.
    The write path refuses new estimates only on a computable `True` -- an
    unreadable record must not lock Joe out of logging, and equally must not
    be reported as "not stopped".
    """
    loss = study_loss_dollars(conn)
    if loss is None:
        return None
    return loss >= STUDY_LOSS_CEILING_DOLLARS


# ---------------------------------------------------------------------------
# The self-lockout (fleet convening item 10)
# ---------------------------------------------------------------------------

def engage_lockout(
    conn: sqlite3.Connection, *, now_ms: int, day_start_hour: int
) -> int:
    """One tap of "not tonight": lock the estimate log until the next day roll.

    The first control in this product that lets Joe act on the recognition
    that he should not be betting *right now* -- the tilt review's finding was
    that every existing guard fires on money already lost, never on the
    decision to sit down.

    The release instant is the next `day_start_hour`:00Z strictly after now --
    the same roll hour the odds budget and the risk day already use, because a
    third definition of "tomorrow" is how the looser one wins in silence.
    Tapping twice is idempotent by construction: the target instant is a
    property of the clock, not of the tap count, so a second row carries the
    same `until_ms` and MAX() over the table changes nothing.

    **There is deliberately no disengage.** A lockout that can be talked back
    open ten minutes later is a speed bump, not a control; the release is the
    day roll and nothing else. If that ever needs to change, it is a decision
    for an ADR, not a parameter.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
    release = now.replace(hour=day_start_hour, minute=0, second=0, microsecond=0)
    if release <= now:
        release += timedelta(days=1)
    until_ms = int(release.timestamp() * 1000)
    conn.execute(
        "INSERT INTO self_lockouts (requested_ms, until_ms) VALUES (?, ?)",
        (now_ms, until_ms),
    )
    conn.commit()
    return until_ms


def lockout_until(conn: sqlite3.Connection, *, now_ms: int) -> Optional[int]:
    """When the active lockout releases, or None if none is active.

    `None` and "a lockout exists but has expired" are the same answer on
    purpose: an expired lockout is over, and surfacing its corpse would turn
    "you said not tonight, and tonight ended" into a nag.
    """
    row = conn.execute(
        "SELECT MAX(until_ms) AS until_ms FROM self_lockouts WHERE until_ms > ?",
        (now_ms,),
    ).fetchone()
    return row["until_ms"] if row and row["until_ms"] is not None else None
