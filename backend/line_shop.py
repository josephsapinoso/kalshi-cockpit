"""Line-shopping hint: the same opinion, bought the cheaper way round (#245).

On a two-outcome game the two teams' markets are mirror images, so "Washington
wins" can be bought two ways: YES on Washington, or NO on Atlanta. They are
different orders against different books and they can cost different amounts.
This module says so, on the row, when the other way is cheaper **after fees**.

What it is: a fact about what you pay. Copy says so in one fixed sentence,
`DISCLAIMER`, and the copy makes no claim that the bet is good.

What it is not:

- **Not a signal, not a ranking.** Nothing in the slate sorts or filters on the
  hint (ADR 0071 §2.5: a per-row fact is transparency, an ordering is a claim;
  `tests/test_line_shopping_hint.py` reads the route's sort keys).
- **Not for every league.** Only MLB, NBA, WNBA, NCAAF and NFL. Soccer has a
  Tie market, so NO on one team is not YES on the other. NHL stays off until a
  rules read confirms how overtime and a shootout resolve. A league that is
  missing or unrecognised refuses, it is not guessed.
- **Not across two instants.** Both books must carry the same read time. A
  hint built from two different reads compares prices that never coexisted.

The fee is `core/fees.calculate_fee` as-is, at `FEE_REFERENCE_CONTRACTS`. The
fee is rounded per order, so one contract would be dominated by rounding; 100 is
a stated reference, not a recommended size.

Does not establish: that either route fills at the shown price (the depth shown
is the best ask only), or how a NFL tie settles across the two routes (the
ticket says $0.50 each; nothing here tests it).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

from .core.fees import calculate_fee
from .core.prices import format_price
from .kalshi.discovery import IN_SCOPE_LEAGUES

#: The sport keys the hint may fire on. NHL and every soccer league are absent
#: on purpose; see the module docstring.
ALLOWED_SPORT_KEYS: frozenset[str] = frozenset(
    {
        "baseball_mlb",
        "basketball_nba",
        "basketball_wnba",
        "americanfootball_ncaaf",
        "americanfootball_nfl",
    }
)

#: The same gate on Kalshi's own ticker, so a row whose league string is
#: wrong still cannot carry the hint on a soccer or NHL ticker.
ALLOWED_SERIES: frozenset[str] = frozenset(
    {"KXMLBGAME", "KXNBAGAME", "KXWNBAGAME", "KXNCAAFGAME", "KXNFLGAME"}
)

FEE_REFERENCE_CONTRACTS = 100

#: Smaller than this (tenths of a cent, per contract, after fees) is rounding,
#: not a cheaper route.
MIN_SAVING_TENTHS_PER_CONTRACT = 1

DISCLAIMER = "This cuts what you pay. It does not create an edge."


@dataclass(frozen=True)
class BookRead:
    """One market's best bids as they were read, and when."""

    ticker: str
    yes_bid_tenths: Optional[int]
    yes_bid_qty: Optional[float]
    no_bid_tenths: Optional[int]
    no_bid_qty: Optional[float]
    read_ms: Optional[int]
    team: Optional[str] = None


def _series(ticker: str) -> str:
    return ticker.split("-", 1)[0]


def league_allowed(ticker: str, league: Optional[str]) -> bool:
    """True only when both the ticker's series and the league are allowed.

    `league` arrives in either vocabulary (the odds feed's sport key or
    Kalshi's competition string, see `lib/leagueLabel.ts`); an unknown or
    missing value refuses.
    """
    if not league or _series(ticker) not in ALLOWED_SERIES:
        return False
    sport_key = IN_SCOPE_LEAGUES.get(league, league)
    return sport_key in ALLOWED_SPORT_KEYS


def _ask_and_depth(book: BookRead, side: str) -> Optional[tuple[int, float]]:
    """(ask in tenths, contracts at that ask) for buying `side`.

    Kalshi publishes bids only: the YES ask is the complement of the best NO
    bid and its depth is that bid's quantity, and the reverse for NO. A missing
    bid or an empty level is no price, never zero.
    """
    if side == "yes":
        bid, qty = book.no_bid_tenths, book.no_bid_qty
    else:
        bid, qty = book.yes_bid_tenths, book.yes_bid_qty
    if bid is None or qty is None or qty <= 0 or not 0 < bid < 1000:
        return None
    return 1000 - bid, float(qty)


def _all_in_tenths(ask_tenths: int) -> Optional[int]:
    """Total cost of FEE_REFERENCE_CONTRACTS at `ask`, fee included, in tenths."""
    fee = calculate_fee(ask_tenths, FEE_REFERENCE_CONTRACTS)
    if fee is None:
        return None
    return ask_tenths * FEE_REFERENCE_CONTRACTS + round(fee * 1000)


def _leg(book: BookRead, side: str, ask: int, depth: float, total: int) -> dict:
    return {
        "ticker": book.ticker,
        "side": side,
        "team": book.team,
        "ask_tenths": ask,
        "ask_display": format_price(ask),
        "depth": depth,
        "all_in_tenths_per_contract": total / FEE_REFERENCE_CONTRACTS,
    }


def compute_hint(
    *,
    league: Optional[str],
    own: BookRead,
    own_side: str,
    other: BookRead,
) -> Optional[dict]:
    """The hint for a row buying `own_side` of `own`, or None.

    `other` is the mirror market of the same two-outcome game. The same
    opinion is `own_side` on `own`, or the opposite side on `other`.
    """
    if own_side not in ("yes", "no"):
        return None
    if not (league_allowed(own.ticker, league) and league_allowed(other.ticker, league)):
        return None
    # One read or no hint. Unknown read times are "different", not "equal".
    if own.read_ms is None or other.read_ms is None or own.read_ms != other.read_ms:
        return None
    other_side = "no" if own_side == "yes" else "yes"
    mine = _ask_and_depth(own, own_side)
    theirs = _ask_and_depth(other, other_side)
    if mine is None or theirs is None:
        return None
    my_total = _all_in_tenths(mine[0])
    their_total = _all_in_tenths(theirs[0])
    if my_total is None or their_total is None:
        return None
    saving = my_total - their_total  # tenths, over the reference contracts
    if saving < MIN_SAVING_TENTHS_PER_CONTRACT * FEE_REFERENCE_CONTRACTS:
        return None
    per_contract = saving / FEE_REFERENCE_CONTRACTS
    cheaper = _leg(other, other_side, theirs[0], theirs[1], their_total)
    current = _leg(own, own_side, mine[0], mine[1], my_total)
    copy = (
        f"Same opinion, cheaper way: {other_side.upper()} at "
        f"{cheaper['ask_display']} ({cheaper['depth']:g} contracts at that ask) "
        f"instead of {own_side.upper()} at {current['ask_display']} "
        f"({current['depth']:g} at that ask). About {per_contract:.1f} tenths of "
        f"a cent less per contract after fees, at {FEE_REFERENCE_CONTRACTS} "
        f"contracts. {DISCLAIMER}"
    )
    return {
        "cheaper": cheaper,
        "current": current,
        "saving_tenths_per_contract": per_contract,
        "fee_reference_contracts": FEE_REFERENCE_CONTRACTS,
        "read_ms": own.read_ms,
        "copy": copy,
    }


def _latest_book(conn: sqlite3.Connection, ticker: str, team: Optional[str]) -> BookRead:
    row = conn.execute(
        "SELECT yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty, "
        "COALESCE(confirmed_ms, observed_ms) AS read_ms "
        "FROM kalshi_quotes WHERE ticker = ? "
        "ORDER BY observed_ms DESC, id DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    if row is None:
        return BookRead(ticker, None, None, None, None, None, team)
    return BookRead(
        ticker,
        row["yes_bid_tenths"],
        row["yes_bid_qty"],
        row["no_bid_tenths"],
        row["no_bid_qty"],
        row["read_ms"],
        team,
    )


def hint_for_row(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    side: str,
    league: Optional[str],
) -> Optional[dict]:
    """Look up the mirror market and compute the hint for one slate row.

    Refuses (None) unless the event has exactly two moneyline markets: a third
    (a Tie market) is the soccer shape and means the two sides are not mirrors.
    """
    if not league_allowed(ticker, league):
        return None
    me = conn.execute(
        "SELECT event_ticker, market_type, yes_side_team "
        "FROM kalshi_markets WHERE ticker = ?",
        (ticker,),
    ).fetchone()
    if me is None or not me["event_ticker"] or me["market_type"] != "moneyline":
        return None
    siblings = conn.execute(
        "SELECT ticker, yes_side_team FROM kalshi_markets "
        "WHERE event_ticker = ? AND market_type = 'moneyline'",
        (me["event_ticker"],),
    ).fetchall()
    # Exactly one mirror, or none: a second (a Tie market) means the two teams
    # are not each other's complement. With our own row among `siblings` that
    # is `len(others) == 1`.
    others = [s for s in siblings if s["ticker"] != ticker]
    if len(others) != 1:
        return None
    return compute_hint(
        league=league,
        own=_latest_book(conn, ticker, me["yes_side_team"]),
        own_side=side,
        other=_latest_book(conn, others[0]["ticker"], others[0]["yes_side_team"]),
    )
