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
from backend.kalshi.props import MARKET_TYPE_PROP, is_prop_series  # noqa: E402

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


async def count_since(since_text: str) -> int:
    from backend.config import KalshiConfig
    from backend.kalshi.rest import KalshiRestClient

    since_ts = parse_since(since_text)

    async with KalshiRestClient(KalshiConfig.load()) as api:
        fills = await _kxmve_fills(api)
        tickers = tickers_first_filled_since(fills, since_ts)

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
            sports = combo_no_side_moneyline_sports(legs)
            if sports:
                n_with_no_side_moneyline += 1
            for sport in sports:
                by_sport[sport] = by_sport.get(sport, 0) + 1

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
    args = ap.parse_args()
    return asyncio.run(count_since(args.since))


if __name__ == "__main__":
    raise SystemExit(main())
