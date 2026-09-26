"""`POST /api/parlays/check` -- price a parlay someone else built (#166).

Joe tails a friend's parlays: 82 of his 142 settled parlays were never priced
on this desk because he copied them from someone who built them elsewhere
(#164, #165). This module takes pasted text -- a kalshi.com link or a bare
`KXMVE...` ticker -- reads the combination's legs straight off the venue (the
minted market already exists; nothing here mints one), prices each leg and
the conservative joint from the desk's own consensus, reads the book, and
writes one `parlay_lookups` row keyed to that ticker under `card_key =
"checked"` -- so `/bets` (#161, #163), Ask the Market and Take It all see it
without being changed themselves. (Was `card_key = "outside"` until the
round-2 review: `/hedge` labels a bought position with its `card_key`, and
"outside" collides with `hand_recorded_position`'s own meaning of "outside
this desk". "checked" does not.)

**Reuse, not a parallel implementation.** The leg read is `mve_legs`
(`backend/kalshi/rfq.py`), the same function `hedge.adopt_venue_combo` (#148)
uses for a combination bought outside the desk; the per-leg chance is the
same `candidate_pool` / `ladder_candidates` scan the ladder itself runs, with
`eligible_events` cleared to `None` -- a minted ticker already proves Kalshi
will combine its legs, so the venue-combinability filter would only ever
throw away a leg this function has independent proof is fine; the joint is
`core.ladder.joint_for`, the same function `price_card_on_kalshi` calls; the
book read and the derived-ask identity are `OrderBook`, the same class every
other price on this desk goes through; and the row is `parlays._record_lookup`,
the one writer of `parlay_lookups`.

**Never mints, never spends.** The ticket already exists on the venue by the
time a friend has shared it, so there is no `lookup_combo` call and no
`allow_market_creation` -- the one difference from `price_card_on_kalshi`,
which mints (or finds) the combination its own card names. No agent, no
scout, no odds fetch: everything this function reads is already in the
database or on one or two venue calls (`GET /markets/{ticker}`, or, for a
link that only names the EVENT, `GET /markets?event_ticker=...` to find its
one market first) plus the order book.

**A leg the pool cannot answer for is `chance: null` with a named reason,
never `0.0`.** CLAUDE.md's rule ("unreadable resolves to `None`, never `0`")
applies here exactly as it does to `unusable_reason`: a friend's parlay can
easily carry a leg this desk has no consensus for (a prop, a league the odds
feed does not carry, a market that has gone stale) and the screen must say
so in words, not a number that reads as "impossible".

**A real kalshi.com combo link does not carry a market ticker at all --
round-2 finding.** A measured URL shape is
`https://kalshi.com/markets/kxmvecrosscategory/mve-cross-category/
kxmvecrosscategory-s2026338240a5999`: the first path segment is the SERIES
(`KXMVECROSSCATEGORY`, never looked up on its own -- there is no one market
to resolve it to), and the last is the EVENT ticker (`KXMVE...-S<year><hex>`,
15 characters after the `S`), never the MARKET ticker (which is the event
ticker plus a further `-<11 hex>`, e.g. `KXMVECROSSCATEGORY0-SHARD1-
S2026B3D8BDECEA6-930882E712B`). The first version of this module took the
first `KXMVE...` regex match, which on that URL is the series segment, and
`GET /markets/{series}` 404s. `_match_ticker` now collects every candidate
token, strips trailing punctuation, and classifies each as market-shaped,
event-shaped or series-only; a market-shaped token is preferred outright, an
event-shaped one is resolved to its one market via `_resolve_event_ticker`,
and a series-only one is refused before any venue call -- there is no single
market a bare series name could mean.

**Response contract** (kept exact -- the frontend lane's own copy of this
must match verbatim; #167):

```
{
  "status": "priced" | "book_empty",
  "minted_market_ticker": "KXMVE...",
  "rfq_available": bool,
  "rfq_unavailable_reason": str | null,
  "legs": [{"market_ticker": str, "side": "yes"|"no", "label": str,
            "commence_ms": int|null, "chance": float|null,
            "chance_display": str|null,
            "unknown_reason": str|null, "unknown_reason_code": str|null}],
  "fair": {"conservative": float|null, "conservative_percent_display": str|null,
           "fair_cost_display": str|null, "no_joint_reason": "unknown_leg"|"same_game"|null},
  "quoted": {"ask_display": str, "depth_display": str|null, "quoted_ms": int,
             "quote_max_age_ms": int|null} | null,
  "hold_display": str|null,
  "words": str,
  "notes": {"unquoted": str, "fee": str}
}
```

`rfq_available` is true only when the market's own `exchange_index == 1`
(Kalshi's combinations shard -- the RFQ path hard-codes shard 1,
`combo_rfq.py`/`kalshi/rfq.py`, and an unsharded `KXMVE` market carries
`exchange_index: 0`, `tests/fixtures/combo_priced_markets.json`) AND its
`status == "active"`. `rfq_unavailable_reason` names which of the two failed,
never both at once (the shard check runs first). Neither `combo_rfq.py` nor
`kalshi/rfq.py` is edited here -- they still assume shard 1 unconditionally;
this module only reads the fact and states it before Joe taps Ask the Market
on a combination that would refuse there.

`unknown_reason` is now WORDS, for Joe, not a bare code -- `unknown_reason_code`
keeps the code beside it for anything that reads this row programmatically.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Sequence

from backend.core.correlation import CorrelationRefused
from backend.core.ladder import (
    UNUSABLE_REASONS,
    CandidateLeg,
    Leg,
    joint_for,
    unusable_reason,
)
from backend.core.parlay import ParlayQuote, value_parlay
from backend.kalshi.orderbook import OrderBook
from backend.kalshi.rest import EXCHANGE_INDEX_COMBOS
from backend.kalshi.rfq import RfqRefused, mve_legs
from backend.parlays import (
    HORIZON_LADDER,
    NOTES,
    LookupRefused,
    _commence_ms_for_tickers,
    _cost_per_contract,
    _record_lookup,
    candidate_pool,
    horizon_end_ms,
    ladder_candidates,
)

logger = logging.getLogger(__name__)

#: The row's own identity in `parlay_lookups.card_key`. Never reused by a
#: registered card (`core.ladder.CARD_SHAPES`) -- this parlay was not built
#: by this desk, so it does not share a recipe's key. Named "checked" rather
#: than the original "outside": `/hedge` labels a position it watches with
#: its `card_key` (`routes.py::_record_combo_position`), and
#: `hand_recorded_position` already uses "outside" to mean "not bought
#: through this desk at all" -- a different fact from "this desk priced a
#: combination it did not build", which is what this key actually records.
CARD_KEY = "checked"

#: `HORIZONS`/`HORIZON_LADDER` run narrowest-first (`parlays.py`), so the last
#: entry is the widest window this desk carries. A friend's parlay was built
#: on ITS OWN clock, not this desk's "tonight" -- the widest window is the
#: only one that does not refuse a leg for a reason that has nothing to do
#: with whether the desk can price it.
WIDEST_HORIZON = HORIZON_LADDER[-1]

#: Every `KXMVE...` token in pasted text, case-insensitive. Deliberately does
#: not assume a URL shape -- Joe's own answer (2026-09-25) named a kalshi.com
#: link as the near-term case and a screenshot as later, and no sample link
#: was in hand to anchor a stricter pattern against when this was first
#: built. `finditer`, not a single `search`: a URL carries more than one
#: `KXMVE...`-shaped segment (series, event, sometimes market) and which one
#: is USABLE is a question `_match_ticker` answers, not this pattern.
_TICKER_PATTERN = re.compile(r"KXMVE[A-Za-z0-9._-]+", re.IGNORECASE)

#: A market-shaped tail: `-S<hex>-<hex>`, e.g.
#: `-S2026B3D8BDECEA6-930882E712B`. `S` is never itself a hex digit, so this
#: can only match the LAST two hyphen-delimited groups of a token, and a
#: token ending in a plain hex group (no `S` prefix on it) cannot also match
#: this -- the two shapes are structurally exclusive at the end of a string.
_MARKET_TAIL_RE = re.compile(r"-S[0-9A-F]+-[0-9A-F]+$")

#: An event-shaped tail: `-S<hex>` with nothing after it. Anchored the same
#: way, so a market-shaped token (which ends in a further `-<hex>` group)
#: never matches this one too -- check market first anyway, since order
#: matters if either regex is ever loosened.
_EVENT_TAIL_RE = re.compile(r"-S[0-9A-F]+$")

#: Reasons a leg absent from the candidate pool cannot be priced, spelled the
#: same way `resolve_requested_legs` (`parlays.py:2810`) tells Joe about a
#: drifted leg on his own card -- reused, not re-derived, so the two screens
#: cannot describe the same fact in two words. Kept as a public vocabulary
#: (`unknown_reason_code` on the wire carries these verbatim) even though the
#: leg's own `unknown_reason` is now rendered in words -- see
#: `_missing_leg_words`.
REASON_GAME_STARTED = "game_started"
REASON_OUTSIDE_WINDOW = "outside_window"
REASON_NOT_SERVED = "not_served"

#: Words for the three reasons above, in the same voice
#: `resolve_requested_legs` already uses for a drifted leg on the desk's own
#: card (`parlays.py:2900-2932`) -- not re-derived, because two spellings of
#: "this leg cannot be priced" is exactly the drift CLAUDE.md's copy-recurrence
#: lesson warns about.
_MISSING_LEG_REASON_WORDS: dict[str, str] = {
    REASON_GAME_STARTED: "this leg's game has already started",
    REASON_OUTSIDE_WINDOW: (
        "this leg kicks off further out than this desk's widest window reads"
    ),
    REASON_NOT_SERVED: "this desk has no consensus reading for this leg",
}


def _reason_words(code: Optional[str]) -> Optional[str]:
    """A leg's `unknown_reason` code, in plain words for Joe.

    Two vocabularies feed this: the three-way missing-leg split above (a leg
    the candidate pool never mentions) and `core.ladder.UNUSABLE_REASONS` (a
    leg the pool contains but refuses as stale, unmeasurable or not a
    probability) -- `unusable_reason`'s own codes. Both are reused, not
    restated, so a fix to either's wording reaches this screen automatically.
    """
    if code is None:
        return None
    if code in _MISSING_LEG_REASON_WORDS:
        return _MISSING_LEG_REASON_WORDS[code]
    return UNUSABLE_REASONS.get(code, code)


def _strip_trailing_punctuation(token: str) -> str:
    """A token the regex captured, with a trailing `.`, `_` or `-` removed.

    The character class that finds a `KXMVE...` token also happily matches a
    sentence's closing period or a URL's trailing separator, and those are
    never part of the ticker. Strips repeatedly (`"..."`, `"--"`), not once.
    """
    return token.rstrip("._-")


def _classify_token(token: str) -> str:
    """`"market"`, `"event"` or `"series"` -- see the module docstring's
    round-2 finding for the shapes these three cover."""
    if _MARKET_TAIL_RE.search(token):
        return "market"
    if _EVENT_TAIL_RE.search(token):
        return "event"
    return "series"


def _match_ticker(text: str) -> Optional[tuple[str, str]]:
    """`(kind, token)` for the best `KXMVE...` token in `text`, or `None`.

    Every token is collected and classified; a market-shaped one wins over an
    event-shaped one, which wins over a series-only one, regardless of where
    in the text each appears -- the real kalshi.com URL this was built
    against (module docstring) carries a series segment BEFORE its event
    segment, so "first found" would have picked the one that can never be
    looked up.
    """
    tokens = [
        _strip_trailing_punctuation(m.group(0)).upper()
        for m in _TICKER_PATTERN.finditer(text or "")
    ]
    tokens = [t for t in tokens if t]
    if not tokens:
        return None
    by_kind: dict[str, str] = {}
    for token in tokens:
        kind = _classify_token(token)
        by_kind.setdefault(kind, token)
    for kind in ("market", "event", "series"):
        if kind in by_kind:
            return kind, by_kind[kind]
    return None  # pragma: no cover -- every token has a kind


def extract_ticker(text: str) -> Optional[str]:
    """The best `KXMVE...` MARKET ticker in `text`, if one is directly
    present -- upper-cased, or `None`.

    **Kept for callers that only want a market ticker and do not want to
    resolve an event.** Returns `None` on an event-shaped or series-only
    match too, since neither is a market ticker; `check_parlay_text` uses
    `_match_ticker` directly so it can still resolve the event case rather
    than refusing it.
    """
    match = _match_ticker(text)
    if match is None or match[0] != "market":
        return None
    return match[1]


def _percent_display(p: Optional[float]) -> Optional[str]:
    """A probability as a percentage that never rounds a small reading to
    "0%".

    `parlays._percent` (`core.prices.format_probability`) rounds to the
    nearest tenth of a cent, so a reading of 0.0004 (0.04%) prints "0%" --
    exactly the failure `bets/page.tsx`'s `chancePercent` was written to
    fix for `chance_when_priced` (lessons 2026-09-25). That fix lives in the
    frontend only; this is the same four-band rule for the two percentages
    this module renders (`chance_display`, `conservative_percent_display`),
    so a longshot leg in a friend's parlay does not read as "no chance" on
    the one screen whose whole job is to say what a chance actually is.
    """
    if p is None:
        return None
    pct = p * 100.0
    if pct >= 10:
        return f"{round(pct)}%"
    if pct >= 1:
        return f"{pct:.1f}%"
    if pct >= 0.01:
        return f"{pct:.2f}%"
    return "under 0.01%"


def _leg_label(ticker: str, side: str, titles: dict) -> str:
    """`kalshi_markets.title` when this instance has seen the market, else
    the bare ticker, prefixed `"NO -- "` on a NO leg.

    The same convention `hedge.adopt_venue_combo` (#148) uses for a leg with
    no upstream sportsbook-phrased label to fall back on -- a friend's parlay
    has none either, by construction: no card of this desk's own ever chose
    a phrasing for it.
    """
    base = titles.get(ticker) or ticker
    return f"NO -- {base}" if side == "no" else base


def _titles_for(conn, tickers: Sequence[str]) -> dict:
    """`{ticker: title}` for every leg this instance has ingested, silently
    omitting one it has not -- the caller falls back to the ticker."""
    if not tickers:
        return {}
    placeholders = ",".join("?" for _ in tickers)
    out: dict = {}
    for row in conn.execute(
        f"SELECT ticker, title FROM kalshi_markets WHERE ticker IN ({placeholders})",
        tuple(tickers),
    ):
        if row["title"]:
            out[str(row["ticker"])] = str(row["title"])
    return out


def _missing_leg_reason(
    commence_ms: Optional[int], *, now_ms: int, horizon: str
) -> str:
    """Why a leg absent from the candidate pool cannot be priced -- the same
    three-way split `resolve_requested_legs` makes for a drifted leg on the
    desk's own card, reused rather than re-derived (`parlays.py:2900-2932`).
    """
    if commence_ms is not None and commence_ms <= now_ms:
        return REASON_GAME_STARTED
    if commence_ms is not None and commence_ms > horizon_end_ms(now_ms, horizon):
        return REASON_OUTSIDE_WINDOW
    return REASON_NOT_SERVED


def _unwrap_market(payload) -> dict:
    """The bare market dict from either envelope `mve_legs` accepts --
    `{"market": {...}}` (the singular `GET /markets/{ticker}` shape) or a
    bare dict (one item of a `GET /markets?event_ticker=...` list, the shape
    `combo_priced_markets.json` itself captures). Never raises: an
    unreadable shape returns `{}`, and every reader here already treats a
    missing key as "unknown", not as a crash.
    """
    if isinstance(payload, dict) and isinstance(payload.get("market"), dict):
        return payload["market"]
    return payload if isinstance(payload, dict) else {}


async def _resolve_event_ticker(api, event_ticker: str) -> tuple[str, dict]:
    """`(market_ticker, market_payload)` for the ONE market on this event.

    A kalshi.com combo link names the EVENT, never the market (module
    docstring's round-2 finding) -- there is no committed fixture of this
    exact read (`GET /markets?event_ticker=...` for a KXMVE event) at the
    time this was written; the shape asserted here is the one
    `KalshiRestClient.markets_for_event` already documents for the same
    endpoint (`{"markets": [...], "cursor": ...}`), read directly rather
    than through that method because it drops every `KXMVE`-prefixed market
    as discovery-hygiene junk (`backend/kalshi/rest.py` `JUNK_PREFIX`) --
    exactly the markets this function exists to find.

    **Refuses unless the event has exactly one market.** "One market per
    combo event" has never been measured across the whole venue, so this
    checks it every time rather than assuming it: zero markets is an
    unreadable link, and more than one is a link the desk cannot resolve
    without the market's own ticker, because Kalshi does not say which
    market goes with which side of a share.
    """
    try:
        payload = await api.get("/markets", event_ticker=event_ticker)
    except Exception as exc:  # noqa: BLE001 -- transport; no row, nothing read
        raise LookupRefused(
            502,
            f"Kalshi's markets for the event {event_ticker} could not be "
            f"read ({exc}). Nothing was created.",
        ) from exc

    markets = payload.get("markets") if isinstance(payload, dict) else None
    if not isinstance(markets, list) or not markets:
        raise LookupRefused(
            422,
            "the link or ticker could not be matched to a combination: "
            f"Kalshi's read of the event {event_ticker} named no market. "
            "Nothing was created.",
        )
    if len(markets) != 1:
        raise LookupRefused(
            422,
            "the link or ticker could not be matched to a combination: "
            f"the event {event_ticker} lists {len(markets)} markets, and "
            "this desk cannot tell which one is the combination without "
            "the market's own link or ticker. Nothing was created.",
        )
    market = markets[0]
    market_ticker = market.get("ticker") if isinstance(market, dict) else None
    if not market_ticker:
        raise LookupRefused(
            422,
            "the link or ticker could not be matched to a combination: "
            f"the event {event_ticker}'s one market carries no ticker of "
            "its own. Nothing was created.",
        )
    return str(market_ticker), market


async def check_parlay_text(
    conn,
    *,
    text: str,
    now_ms: int,
    api,
    max_odds_age_ms: int,
    horizon: str = WIDEST_HORIZON,
    max_kalshi_quote_age_ms: Optional[int] = None,
) -> dict:
    """Read a pasted combination's legs off Kalshi and price it. See module
    docstring for the pipeline, the response contract and what is
    deliberately not spent.

    Raises `LookupRefused` for every refusal that writes no row (no ticker in
    the text, a series-only token, an event with zero or several markets, an
    unreadable market, a leg with no readable side or ticker) and for the one
    refusal that writes a row first (the order book could not be read -- the
    market exists on the venue by this point, so the failure is recorded
    with the ticker before the caller is told).
    """
    match = _match_ticker(text)
    if match is None:
        raise LookupRefused(
            422,
            "paste the Kalshi link or the KXMVE... ticker for the parlay "
            "you want checked. Nothing was read.",
        )
    kind, token = match

    if kind == "series":
        # **Never looked up.** A series name (`KXMVECROSSCATEGORY`) is a
        # whole product line, not one combination -- there is no `GET`
        # this desk could make that resolves to a single market, so this
        # refuses before any venue call, the same way "no token at all" does.
        raise LookupRefused(
            422,
            "the link or ticker could not be matched to a combination: "
            f"{token!r} names a whole series of combinations, not one of "
            "them. Paste the market's own link (the one with a specific "
            "combination open) or its ticker instead. Nothing was created.",
        )

    if kind == "market":
        ticker = token
        try:
            market_payload = await api.get(f"/markets/{ticker}")
        except Exception as exc:  # noqa: BLE001 -- transport; no row, nothing read
            raise LookupRefused(
                502,
                f"Kalshi's market for {ticker} could not be read ({exc}). "
                "Nothing was created.",
            ) from exc
    else:
        # kind == "event": resolve to the one market this event carries.
        ticker, market_payload = await _resolve_event_ticker(api, token)

    market = _unwrap_market(market_payload)
    exchange_index = market.get("exchange_index")
    status_on_venue = market.get("status")

    rfq_available = True
    rfq_unavailable_reason: Optional[str] = None
    if exchange_index != EXCHANGE_INDEX_COMBOS:
        rfq_available = False
        rfq_unavailable_reason = (
            "Asking the makers only works on combinations in Kalshi's "
            "combinations account (shard 1); this one is in another."
        )
    elif status_on_venue != "active":
        rfq_available = False
        rfq_unavailable_reason = "this combination is no longer trading"

    try:
        collection_ticker, venue_legs = mve_legs(market_payload)
    except RfqRefused as exc:
        raise LookupRefused(
            422,
            f"Kalshi's market for {ticker} carries no legs to check: {exc}. "
            "Nothing was created.",
        ) from exc

    # **Refused by name, before anything is priced and before any row.**
    # A leg with no readable side -- the same rule `hedge.adopt_venue_combo`
    # states for the identical shape: guessing `"yes"` would misdescribe a
    # real NO leg, and KXMVE combos carry them routinely. A leg missing its
    # own `market_ticker` or `event_ticker` is the same class of refusal:
    # every reader below indexes those fields directly, and a `KeyError`
    # bubbling out of this module is a 500, not a refusal in words, and a
    # stored literal `"None"` string is the same "unreadable resolves to a
    # substitute" defect CLAUDE.md's rule already forbids for a probability.
    for leg in venue_legs:
        if not leg.get("market_ticker") or not leg.get("event_ticker"):
            raise LookupRefused(
                422,
                f"Kalshi's market for {ticker} names a leg with no readable "
                "market ticker or event ticker. Nothing was created.",
            )
        side = leg.get("side")
        if side not in ("yes", "no"):
            raise LookupRefused(
                422,
                f"Kalshi's market for {ticker} names a leg "
                f"({leg.get('market_ticker')!r}) with no readable side "
                f"({side!r}). Nothing was created.",
            )

    leg_tickers = [str(leg["market_ticker"]) for leg in venue_legs]
    titles = _titles_for(conn, leg_tickers)

    # **`eligible_events` cleared to `None`.** A minted ticker already proves
    # the venue will combine these legs -- that is what "it exists" means --
    # so `combo_eligible_events`'s cache would only ever throw away a leg this
    # function has independent, stronger proof is fine to price.
    pool = candidate_pool(conn, now_ms=now_ms, max_odds_age_ms=max_odds_age_ms)
    pool = pool._replace(eligible_events=None)
    candidates, _excluded = ladder_candidates(
        conn,
        now_ms=now_ms,
        max_odds_age_ms=max_odds_age_ms,
        horizon=horizon,
        pool=pool,
    )
    by_key = {
        (c.kalshi_event_ticker, c.kalshi_market_ticker, c.side): c for c in candidates
    }

    missing_tickers = [
        str(leg["market_ticker"])
        for leg in venue_legs
        if (
            str(leg["event_ticker"]),
            str(leg["market_ticker"]),
            str(leg["side"]),
        )
        not in by_key
    ]
    kickoffs = _commence_ms_for_tickers(conn, missing_tickers)

    response_legs: list[dict] = []
    usable: list[CandidateLeg] = []
    any_unusable = False
    leg_details: dict[tuple, dict] = {}
    legs_pairs: list[tuple] = []

    for leg in venue_legs:
        event_ticker = str(leg["event_ticker"])
        market_ticker = str(leg["market_ticker"])
        side = str(leg["side"])
        legs_pairs.append((event_ticker, market_ticker))

        candidate = by_key.get((event_ticker, market_ticker, side))
        chance: Optional[float] = None
        unknown_reason_code: Optional[str] = None
        commence_ms: Optional[int] = None

        if candidate is None:
            # **Absent from the pool is never a chance, and never a zero.**
            # `chance` already starts `None` above; restated here, on its own
            # line, because this is the one branch CLAUDE.md's rule
            # ("unreadable resolves to `None`, never `0`") is actually about
            # -- a leg this desk has no consensus for is not "0% likely", it
            # is "unknown", and the two must never render the same.
            chance = None
            any_unusable = True
            commence_ms = kickoffs.get(market_ticker)
            unknown_reason_code = _missing_leg_reason(
                commence_ms, now_ms=now_ms, horizon=horizon
            )
        else:
            commence_ms = candidate.commence_ms
            reason_code = unusable_reason(candidate, max_odds_age_ms=max_odds_age_ms)
            if reason_code is not None:
                any_unusable = True
                unknown_reason_code = reason_code
            else:
                chance = candidate.p_conservative
                usable.append(candidate)

        label = _leg_label(market_ticker, side, titles)
        response_legs.append(
            {
                "market_ticker": market_ticker,
                "side": side,
                "label": label,
                "commence_ms": commence_ms,
                "chance": chance,
                "chance_display": _percent_display(chance),
                "unknown_reason": _reason_words(unknown_reason_code),
                "unknown_reason_code": unknown_reason_code,
            }
        )
        leg_details[(event_ticker, market_ticker)] = {
            "side": side,
            "label": label,
            "commence_ms": commence_ms,
        }

    fair_joint: Optional[float] = None
    no_joint_reason: Optional[str] = None
    if any_unusable:
        no_joint_reason = "unknown_leg"
    else:
        odds_event_ids = {c.odds_event_id for c in usable}
        if len(odds_event_ids) != len(usable):
            no_joint_reason = "same_game"
        else:
            try:
                joint = joint_for(usable)
            except CorrelationRefused:
                # The except-clause IS live here (not merely defensive): a
                # test that disables the pre-check above still gets
                # `no_joint_reason = "same_game"` off THIS branch, because
                # `joint_for` -> `joint_probability_all` raises
                # `CorrelationRefused` for the identical same-game pair
                # independently. Two guards for one fact, on purpose.
                no_joint_reason = "same_game"
            else:
                fair_joint = joint.conservative

    try:
        book_payload = await api.orderbook(ticker, depth=10)
        book = OrderBook(ticker=ticker)
        book.apply_snapshot(book_payload, None, now_ms)
    except Exception as exc:  # noqa: BLE001 -- recorded WITH the ticker, then worded
        _record_lookup(
            conn,
            now_ms=now_ms,
            card_key=CARD_KEY,
            stake_cents=0,
            legs=legs_pairs,
            status="error",
            collection_ticker=collection_ticker,
            minted=ticker,
            error=f"orderbook: {exc}",
            leg_details=leg_details,
        )
        raise LookupRefused(
            502,
            f"Kalshi's order book for {ticker} could not be read ({exc}). "
            "Nothing is priced; the combination exists and can be looked at "
            "in the Kalshi app.",
        ) from exc

    ask_tenths = book.best_yes_ask
    depth = book.depth_at_ask("yes") if ask_tenths is not None else None
    status = "priced" if ask_tenths is not None else "book_empty"

    # **The same book-detail string `price_card_on_kalshi` records on its own
    # `book_empty` branch** -- `yes_bid`/level counts, so a later read of this
    # row can tell "truly empty" from "had a YES bid, just no NO bid" without
    # a second venue call. Recorded on every status, not only `book_empty`:
    # unlike the mint path, this row never gets a second write, so the one
    # write is the only chance to carry it.
    yes_bid_for_detail = book.best_yes_bid
    book_detail = (
        f"yes_bid={yes_bid_for_detail if yes_bid_for_detail is not None else 'none'} "
        f"yes_levels={len(book.yes_bids)} no_levels={len(book.no_bids)}"
    )

    hold: Optional[float] = None
    if status == "priced" and fair_joint is not None:
        valuation = value_parlay(
            ParlayQuote(
                legs=tuple(
                    Leg(
                        label=c.kalshi_market_ticker,
                        probability=c.p_conservative,
                        event_key=c.odds_event_id,
                        league=c.league,
                        commence_ms=c.commence_ms,
                    )
                    for c in usable
                ),
                offered_decimal=1000.0 / ask_tenths,
            )
        )
        hold = valuation.hold

    _record_lookup(
        conn,
        now_ms=now_ms,
        card_key=CARD_KEY,
        stake_cents=0,
        legs=legs_pairs,
        status=status,
        collection_ticker=collection_ticker,
        minted=ticker,
        no_bid_tenths=book.best_no_bid if status == "priced" else None,
        ask_tenths=ask_tenths if status == "priced" else None,
        depth=depth,
        fair_joint=fair_joint,
        hold=hold,
        error=None if status == "priced" else book_detail,
        leg_details=leg_details,
    )

    quoted: Optional[dict] = None
    if status == "priced":
        quoted = {
            "ask_display": _cost_per_contract(ask_tenths),
            "depth_display": (
                None
                if depth is None
                else f"about {depth:g} contracts resting at that price"
            ),
            "quoted_ms": now_ms,
            "quote_max_age_ms": max_kalshi_quote_age_ms,
        }
        words = (
            "Read off Kalshi's own order book for this combination. This "
            "parlay was not built on this desk, so a leg outside its own "
            "coverage reads as unknown rather than a chance."
        )
    elif book.has_unpriced_interest("no"):
        # **Not truly empty -- finer than this desk reads.** The derived ask
        # comes from the best WHOLE-TENTH resting NO bid; a level priced
        # finer than a tenth of a cent is real interest this desk simply
        # cannot state as a tradeable ask, which is a different fact from
        # "nobody is bidding at all" and must not share that sentence.
        words = (
            "Kalshi's book for this combination is not truly empty -- there "
            "is interest resting at prices finer than a tenth of a cent, "
            "which this desk cannot read as a tradeable price. A "
            "combination is priced by asking: market makers quote you "
            "privately, and their prices never appear in the book. Ask "
            "instead."
        )
    else:
        # **Never claims Kalshi just created this market -- round-2
        # correction.** This module never mints anything (module docstring);
        # the market already existed, so "Kalshi created the market" -- the
        # wording `price_card_on_kalshi` uses right after its own mint call
        # -- would assert something that did not happen here. The substance
        # survives: a combination's book is empty by design between RFQs
        # (ADR 0164), not a sign nobody will trade it.
        words = (
            "Nothing is resting in this combination's public order book -- "
            "which is the normal state for a Kalshi combination, not a sign "
            "that nobody will trade it. A combination is priced by asking: "
            "market makers quote you privately, and their prices never "
            "appear in the book. Re-reading the book will keep saying this, "
            "so ask instead."
        )
    if status != "priced" and not rfq_available:
        # **"Ask instead" is only true where asking can work.** Seen on the
        # first live check (2026-09-26): a finalized combination got the
        # empty-book sentence ending "so ask instead" beside a screen that
        # had, correctly, withheld the Ask button. Copy that points at a
        # withheld control is the same lie as a control that is not there.
        reason = (rfq_unavailable_reason or "").rstrip(".")
        words = (
            "Nothing this desk can read is resting in this combination's "
            "public order book, and asking the makers is not available "
            f"here: {reason[:1].lower()}{reason[1:]}."
        )

    return {
        "status": status,
        "minted_market_ticker": ticker,
        "rfq_available": rfq_available,
        "rfq_unavailable_reason": rfq_unavailable_reason,
        "legs": response_legs,
        "fair": {
            "conservative": fair_joint,
            "conservative_percent_display": _percent_display(fair_joint),
            "fair_cost_display": (
                _cost_per_contract(fair_joint * 1000)
                if fair_joint is not None
                else None
            ),
            "no_joint_reason": no_joint_reason,
        },
        "quoted": quoted,
        "hold_display": f"{hold * 100:.1f}%" if hold is not None else None,
        "words": words,
        "notes": {"unquoted": NOTES["unquoted"], "fee": NOTES["fee"]},
    }
