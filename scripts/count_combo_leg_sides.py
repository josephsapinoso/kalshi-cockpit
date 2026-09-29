"""Count NO-side game-winner (moneyline) legs in Joe's recent KXMVE combos.

Why this script exists
-----------------------
Session 62 killed pricing a NO-side moneyline leg in `/parlay-check` on "only
2 of 150 of Joe's combos carry one." That count has no committed instrument:
no script, no measurement doc, and it is not in `inspect_live_db.py` (session
63 fact-scout). It is also contradicted by Joe's one held combo at the time,
where 5 of 8 legs were NFL "NO -- team wins" moneylines the check cannot
price (`backend/parlays.py:991`: the pool emits team-YES rows only;
`backend/parlay_check.py:190` returns "no consensus reading" for them). The
150 were dominated by one old event (93 of them). This script re-counts on
the population Joe bets *now*, gated by `--since`, before any build decision.

What it does
------------
1. `GET /portfolio/fills` (and `/portfolio/settlements` as a supplement) for
   fills on KXMVE tickers, paginated, read-only.
2. Groups fills by combo ticker and keeps the ones **first filled on or
   after `--since`** -- a ticker with an earlier fill and a later one is
   still "first filled" before the cutoff and is excluded, on purpose: the
   goal is the population Joe is building *now*, not every combo that ever
   touched the window.
3. For each surviving ticker, `GET /markets/{ticker}` and reads
   `mve_selected_legs` (or `market.mve_selected_legs`) off the response.
4. Classifies every leg with `classify_leg` (pure, no network) and counts,
   by sport, how many combos carry at least one leg that is BOTH a
   game-winner (moneyline) market AND held on the `no` side.

Which series are moneyline markets
-----------------------------------
Read off the same map the discovery/linker path already owns
(`backend.kalshi.discovery._SERIES_RE`, `_SUFFIX_TO_MARKET_TYPE`): a series
ticker ending `GAME` classifies as `"moneyline"` there
(`backend/parlays.py:1095` gates the same string). This module does not
invent a second list -- it derives a leg's series ticker the same way
`backend.kalshi.combos.ComboLeg.series` already does
(`event_ticker.split("-")[0]`) and looks the suffix up in the shared map.
Prop series are excluded first via `backend.kalshi.props.is_prop_series`,
matching `classify_series`'s own ordering, though no prop ticker has ever
been observed to also match the `GAME` suffix.

Read-only, no state written
----------------------------
Every network call here is a GET. No order, no RFQ, no `lookup_combo` mint
(a mint would create a real market and this ticket forbids that). No
credential is ever printed -- `KalshiRestClient` is imported and reused
exactly as `scripts/analyse_combo_fill_fees.py` and
`scripts/capture_fills_fixture.py` already do. **Operator data never enters
the repo** (`tasks/lessons.md`): every result goes to stdout only; nothing is
written to a file under this repository.

What this does not establish
-----------------------------
- **A rate that predicts the next combo.** This is a census of one account's
  combos since one date, not a forecast. Read `n` (the printed combo count)
  before the percentage.
- **Whether pricing a NO-side moneyline leg is worth building.** That
  decision is named in the issue this script closes (#170): re-run after
  merge with `--since 2026-09-10`, and the >=10% threshold there is Joe's
  call, not a conclusion this script draws.
- **Anything about spread, total or team-total legs held on the NO side.**
  Those are already priced (`backend/parlays.py:1080` handles spread NO
  legs as the favorite's cover); only the moneyline gap is being sized here.
- **What `--by-kind` establishes and does not (#198).** It classifies every
  leg by sport x kind x side and flags whether the desk has a pricing path
  for that kind. `desk_prices_kind` is derived from the maps the pool
  already reads, never a second list: moneyline is priced on the YES side
  only (`backend/parlays.py:991`); spread and total by their series'
  market type (the subtitle parsers in `spreads.py`/`totals.py` need a
  subtitle, which `mve_selected_legs` does not carry, so the gate is the
  series-level type they are registered under); a prop when
  `is_prop_series` holds AND its stat is in `PROP_MARKET_KEYS_BY_SPORT`.
  "Priced" means a path exists, not that a price was available for any
  particular game. `same_game` compares the fixture suffix (the text after
  the first hyphen of `event_ticker`, the same convention
  `ComboCollection.fixture` uses); a raw event-ticker compare is wrong
  because prop events carry their own series (ADR 0153). Legs of one game
  through different series therefore count as same-game.
- **Completeness of `/portfolio/fills`.** `backend/kalshi/rest.py:fills`
  documents a measured retention window shorter than three months on this
  account; a combo whose only fill aged out of that window will not appear
  here, and this script does not attempt to detect that absence.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.kalshi.discovery import _SERIES_RE, _SUFFIX_TO_MARKET_TYPE  # noqa: E402
from backend.kalshi.props import (  # noqa: E402
    MARKET_TYPE_PROP,
    MLB_PROP_SERIES,
    NFL_PROP_SERIES,
    PROP_SERIES,
    is_prop_series,
)
from backend.kalshi.spreads import MARKET_TYPE_SPREAD  # noqa: E402
from backend.kalshi.totals import MARKET_TYPE_TOTAL  # noqa: E402
from backend.odds import client as odds_client  # noqa: E402

#: The market_type string that means "game-winner" everywhere else in this
#: repo (`backend/parlays.py:1095`, `backend/runner.py:2483`,
#: `_SUFFIX_TO_MARKET_TYPE["GAME"]`). Named once here rather than repeating
#: the literal.
MARKET_TYPE_MONEYLINE = "moneyline"

#: Every KXMVE combination lives under this prefix on the market/event/fill
#: tickers (`scripts/analyse_combo_fill_fees.py:PREFIX`, same string).
KXMVE_PREFIX = "KXMVE"


@dataclass(frozen=True)
class LegClass:
    """One `mve_selected_legs` entry, classified without any network call."""

    event_ticker: str
    market_ticker: str
    side: str  # "yes" or "no" -- refused, never defaulted (see classify_leg)
    market_type: Optional[str]  # moneyline | spread | total | team_total | prop | None
    sport: Optional[str]  # the series prefix, e.g. "NFL", "MLB" -- None if unclassified

    @property
    def is_moneyline(self) -> bool:
        return self.market_type == MARKET_TYPE_MONEYLINE

    @property
    def is_no_side_moneyline(self) -> bool:
        return self.is_moneyline and self.side == "no"


def series_ticker_of(event_ticker: str) -> str:
    """The series prefix an `event_ticker` sits under.

    Same split `backend.kalshi.combos.ComboLeg.series` already uses
    (`event_ticker.split("-")[0]`) -- one reader for the identity, not a
    second copy of it.
    """
    return event_ticker.split("-")[0]


def classify_leg(leg: Mapping[str, Any]) -> LegClass:
    """Classify one `mve_selected_legs` entry: moneyline or not, side, sport.

    **`side` is read, never defaulted.** A leg missing or misspelling `side`
    raises rather than being read as `"yes"` -- the same refusal
    `backend.kalshi.combos._leg_sides` applies on the write path, for the
    same reason: on a path where `yes` is the common value, a silently
    defaulted side is wrong exactly on the rows that are not `yes`, which are
    the only rows this script exists to find.
    """
    event_ticker = str(leg["event_ticker"])
    market_ticker = str(leg["market_ticker"])
    side = str(leg["side"])
    if side not in ("yes", "no"):
        raise ValueError(
            f"leg {market_ticker} has side {side!r}; a leg is 'yes' or 'no'"
        )

    series_ticker = series_ticker_of(event_ticker)
    if is_prop_series(series_ticker):
        # Ordering mirrors `backend.kalshi.discovery.classify_series`: props
        # are decided first, by ticker, ahead of the suffix regex below.
        return LegClass(event_ticker, market_ticker, side, MARKET_TYPE_PROP, None)

    match = _SERIES_RE.match(series_ticker)
    if match is None:
        return LegClass(event_ticker, market_ticker, side, None, None)
    market_type = _SUFFIX_TO_MARKET_TYPE.get(match.group(2))
    return LegClass(event_ticker, market_ticker, side, market_type, match.group(1))


def combo_no_side_moneyline_sports(legs: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Every distinct sport this combo carries a NO-side moneyline leg for.

    A combo with two NFL NO-side moneyline legs contributes `("NFL",)` once
    (a set, not a leg count); a combo with an NFL one and an MLB one
    contributes both, because "by sport" breaks down where the finding is,
    not the combo total (printed separately by the caller).
    """
    classified = [classify_leg(leg) for leg in legs]
    sports = {c.sport or "UNKNOWN" for c in classified if c.is_no_side_moneyline}
    return tuple(sorted(sports))


# ---------------------------------------------------------------------------
# --by-kind (#198): sport x kind x side, the desk's pricing path, same-game.
# All pure; no network.
# ---------------------------------------------------------------------------

UNKNOWN_SPORT = "UNKNOWN"


@dataclass(frozen=True)
class KindLeg:
    """One leg by sport x kind x side, and whether the desk can price it."""

    sport: str
    kind: str  # moneyline | spread | total | prop:<stat> | other:<series>
    side: str
    desk_prices_kind: bool


def _prop_sport(series_ticker: str) -> str:
    # Which of the two prop maps owns the series names its league; the map is
    # the module's own, not a second list.
    if series_ticker in MLB_PROP_SERIES:
        return "MLB"
    if series_ticker in NFL_PROP_SERIES:
        return "NFL"
    return UNKNOWN_SPORT


def _feed_buys_prop_stat(stat: str) -> bool:
    """Whether any sport's feed prop-market keys carry this stat.

    Read off `odds.client.PROP_MARKET_KEYS_BY_SPORT` at call time (the map
    `sport_has_prop_markets` and `prop_market_keys` are built on).
    """
    return any(stat in keys for keys in odds_client.PROP_MARKET_KEYS_BY_SPORT.values())


def classify_leg_kind(leg: Mapping[str, Any]) -> KindLeg:
    """Sport, kind, side and `desk_prices_kind` for one `mve_selected_legs` entry.

    Unrecognised series are `other:<series>`, never dropped. Side handling is
    `classify_leg`'s (refused, never defaulted).
    """
    base = classify_leg(leg)
    series = series_ticker_of(base.event_ticker)

    if series in PROP_SERIES:
        stat = PROP_SERIES[series]
        return KindLeg(
            _prop_sport(series), f"prop:{stat}", base.side, _feed_buys_prop_stat(stat)
        )
    sport = base.sport or UNKNOWN_SPORT
    if base.market_type == MARKET_TYPE_MONEYLINE:
        # The pool emits team-YES rows only (`backend/parlays.py:991`).
        return KindLeg(sport, "moneyline", base.side, base.side == "yes")
    if base.market_type == MARKET_TYPE_SPREAD:
        return KindLeg(sport, "spread", base.side, True)
    if base.market_type == MARKET_TYPE_TOTAL:
        return KindLeg(sport, "total", base.side, True)
    return KindLeg(sport, f"other:{series}", base.side, False)


def game_key(event_ticker: str) -> str:
    """The game a leg belongs to: the fixture suffix after the first hyphen.

    `KXWNBAGAME-26AUG09LVNY` and `KXWNBAPTS-26AUG09LVNY` are one game though
    their event tickers differ (ADR 0153; same convention as
    `ComboCollection.fixture`). `combos.same_game_collections` works on whole
    collections, not on a bought combo's legs, so it is not called here.
    """
    _, _, suffix = event_ticker.partition("-")
    return suffix or event_ticker


def combo_is_same_game(legs: Sequence[Mapping[str, Any]]) -> bool:
    """True when two or more legs belong to one game."""
    keys = [game_key(str(leg["event_ticker"])) for leg in legs]
    return len(keys) != len(set(keys))


@dataclass
class KindCensus:
    n_combos: int
    n_same_game: int
    #: (sport, kind, side) -> (combos carrying >= 1 such leg, desk_prices_kind)
    cells: dict[tuple[str, str, str], tuple[int, bool]]
    #: (sport, kind) -> combos carrying >= 1 UNPRICED leg of that sport x kind
    unpriced_kinds: dict[tuple[str, str], int]


def census_by_kind(combos: Sequence[Sequence[Mapping[str, Any]]]) -> KindCensus:
    """Aggregate legs of many combos; each combo counts once per cell."""
    cells: dict[tuple[str, str, str], list] = {}
    unpriced: dict[tuple[str, str], int] = {}
    n_same = 0
    for legs in combos:
        classified = [classify_leg_kind(leg) for leg in legs]
        if combo_is_same_game(legs):
            n_same += 1
        seen_cells = {(c.sport, c.kind, c.side): c.desk_prices_kind for c in classified}
        for key, priced in seen_cells.items():
            entry = cells.setdefault(key, [0, priced])
            entry[0] += 1
        for sk in {(c.sport, c.kind) for c in classified if not c.desk_prices_kind}:
            unpriced[sk] = unpriced.get(sk, 0) + 1
    return KindCensus(
        len(combos), n_same, {k: (v[0], v[1]) for k, v in cells.items()}, unpriced
    )


def format_by_kind(census: KindCensus, *, skipped: int, since_text: str) -> str:
    n = census.n_combos
    pct = (lambda c: f"{100.0 * c / n:.1f}%") if n else (lambda c: "n/a")
    lines = [
        f"since                         : {since_text} (UTC midnight)",
        f"combos read                   : {n}",
        f"combos unreadable/skipped     : {skipped}",
        "per (sport, kind, side): combos carrying >= 1 such leg  "
        "(a combo counts in every cell it touches)",
    ]
    for (sport, kind, side), (count, priced) in sorted(
        census.cells.items(), key=lambda kv: (-kv[1][0], kv[0])
    ):
        lines.append(
            f"  {sport:8s} {kind:28s} {side:3s} {count:4d}  {pct(count):>6s}  "
            f"desk_prices_kind={'yes' if priced else 'NO'}"
        )
    if census.unpriced_kinds:
        (sport, kind), count = max(
            census.unpriced_kinds.items(), key=lambda kv: (kv[1], kv[0])
        )
        lines.append(
            f"top unpriced kind (sport x kind, any side): {sport} {kind}  "
            f"{count} combos  {pct(count)}"
        )
    else:
        lines.append("top unpriced kind             : none")
    lines.append(
        f"same-game combos              : {census.n_same_game}  {pct(census.n_same_game)}"
    )
    if n:
        lines.append(f"(n = {n}, one account, not a forecast)")
    else:
        lines.append("shares: NOT COMPUTABLE -- zero combos read")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Network glue below. Nothing above this line makes a request; nothing below
# it is exercised by tests/test_count_combo_leg_sides.py, which is pinned to
# the pure classifier per the ticket's Done-when.
# ---------------------------------------------------------------------------


def parse_since(text: str) -> int:
    """`--since` as an inclusive UTC-midnight epoch-seconds cutoff."""
    dt = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


async def _kxmve_fills(api: Any, *, max_pages: Optional[int] = None) -> list[dict]:
    """Every fill on a KXMVE ticker, oldest first, read-only.

    Kalshi's `/portfolio/fills` has no `ticker` prefix filter, so this walks
    the whole page set and filters client-side -- the same shape
    `scripts/analyse_combo_fill_fees.py:combo_rows` uses against a capture.
    """
    out = []
    async for fill in api.paginate("/portfolio/fills", "fills", max_pages=max_pages):
        if str(fill.get("ticker", "")).startswith(KXMVE_PREFIX):
            out.append(fill)
    return out


def _first_fill_ts(fills_for_ticker: Sequence[dict]) -> Optional[int]:
    values = [f.get("ts") for f in fills_for_ticker if isinstance(f.get("ts"), int)]
    return min(values) if values else None


def tickers_first_filled_since(fills: Sequence[dict], since_ts: int) -> list[str]:
    """Combo tickers whose EARLIEST fill is on or after `since_ts`.

    A ticker with a fill before the cutoff and another after it is still
    "first filled" before the cutoff and is excluded -- the population this
    script sizes is the combos Joe is building *now*, not every combo that
    merely touched the window.
    """
    by_ticker: dict[str, list[dict]] = {}
    for f in fills:
        by_ticker.setdefault(str(f.get("ticker", "")), []).append(f)
    kept = []
    for ticker, rows in by_ticker.items():
        first = _first_fill_ts(rows)
        if first is not None and first >= since_ts:
            kept.append(ticker)
    return sorted(kept)


def legs_from_market_response(payload: Mapping[str, Any]) -> Optional[list[dict]]:
    """`mve_selected_legs` off a `GET /markets/{ticker}` response.

    Checked at both the nesting levels this repo has actually observed
    (`backend.kalshi.combos.echoed_legs` reads the same two spots) --
    `None` when neither carries it, never `[]` (`tasks/lessons.md`:
    unreadable resolves to `None`, not a substitute).
    """
    market = payload.get("market") or {}
    raw = market.get("mve_selected_legs")
    if raw is None:
        raw = payload.get("mve_selected_legs")
    if not isinstance(raw, list):
        return None
    return raw


async def count_since(
    since_text: str, *, by_kind: bool = False, max_tickers: Optional[int] = None
) -> int:
    from backend.config import KalshiConfig
    from backend.kalshi.rest import KalshiRestClient

    since_ts = parse_since(since_text)

    async with KalshiRestClient(KalshiConfig.load()) as api:
        fills = await _kxmve_fills(api)
        tickers = tickers_first_filled_since(fills, since_ts)
        if max_tickers is not None:
            tickers = tickers[:max_tickers]
        all_legs: list[list[dict]] = []

        by_sport: dict[str, int] = {}
        unreadable = 0
        n_combos = len(tickers)
        n_with_no_side_moneyline = 0
        for ticker in tickers:
            try:
                payload = await api.get(f"/markets/{ticker}")
            except Exception as exc:  # noqa: BLE001 -- refuse, never guess
                print(f"{ticker}: fetch failed ({type(exc).__name__}); skipped")
                unreadable += 1
                continue
            legs = legs_from_market_response(payload)
            if legs is None:
                print(f"{ticker}: no mve_selected_legs in response; skipped")
                unreadable += 1
                continue
            all_legs.append(legs)
            sports = combo_no_side_moneyline_sports(legs)
            if sports:
                n_with_no_side_moneyline += 1
            for sport in sports:
                by_sport[sport] = by_sport.get(sport, 0) + 1

    if by_kind:
        print(
            format_by_kind(
                census_by_kind(all_legs), skipped=unreadable, since_text=since_text
            )
        )
        return 0
    print(f"since                         : {since_text} (UTC midnight)")
    print(f"combos first filled since     : {n_combos}")
    print(f"combos unreadable/skipped     : {unreadable}")
    print(f"combos with a NO-side moneyline leg : {n_with_no_side_moneyline}")
    print("by sport (a combo may count in more than one sport)  :")
    for sport, count in sorted(by_sport.items()):
        print(f"  {sport:10s} {count}")
    if n_combos:
        rate = 100.0 * n_with_no_side_moneyline / n_combos
        print(f"rate (n = {n_combos}, one account, not a forecast) : {rate:.1f}%")
    else:
        print("rate: NOT COMPUTABLE -- zero combos first filled since this date")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--since",
        required=True,
        help="YYYY-MM-DD, UTC. Combos first filled before this date are excluded.",
    )
    ap.add_argument(
        "--by-kind",
        action="store_true",
        help="Report sport x kind x side, desk pricing path and same-game share.",
    )
    ap.add_argument(
        "--max-tickers",
        type=int,
        default=None,
        help="Read at most this many combo tickers (one GET each).",
    )
    args = ap.parse_args()
    return asyncio.run(
        count_since(args.since, by_kind=args.by_kind, max_tickers=args.max_tickers)
    )


if __name__ == "__main__":
    raise SystemExit(main())
