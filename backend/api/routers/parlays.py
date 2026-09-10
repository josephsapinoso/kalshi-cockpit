"""`/api/builder/*` and `/api/parlays/*`: the builder and the parlay desk.

Moved verbatim from `backend/api/routes.py` on 2026-09-04; see
`backend/api/routers/__init__.py` for the `register()` shape and why.

`combo_api` arrives as the closure `create_app` built: one shared Kalshi REST
client for the lookup and bid paths, constructed lazily from
`backend.api.routes.KalshiRestClient` on the first tap, so the tests that
patch that name (`test_parlay_lookup`, `test_combo_bid_routes`) still reach
the client these handlers use. This module must not import the class itself.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query

from ...combo_bids import place_resting_bid
from ...config import AppConfig, ConfigError, StalenessConfig
from ...core.correlation import CorrelationRefused
from ...core.parlay import (
    ParlayQuote,
    american_to_decimal,
    decimal_to_american,
    kalshi_equivalent,
    value_parlay,
)
from ...core.prices import format_dollars, format_price
from ...core.suppression import SuppressionConfig
from ...core.teaser import find_wong_candidates
from ...core.trust import TrustThresholds
from ...list_filters import MAX_WITHIN_HOURS, FilterRefused, parse_list_filter
from ...parlays import (
    COMBO_EXIT_CENSUS_BOOKS_NO_YES_BID,
    COMBO_EXIT_CENSUS_BOOKS_READ,
    COMBO_EXIT_CENSUS_SERIES,
    COMBO_EXIT_CENSUS_SHARD_BOOKS_READ,
    COMBO_EXIT_CENSUS_SHARD_SERIES,
    COMBO_EXIT_SHARD_YES_BID_BOOKS,
    COMBO_EXIT_SHARD_YES_BID_DATE,
    COMBO_EXIT_SHARD_YES_BID_SIZE_CONTRACTS,
    LookupRefused,
    DEFAULT_HORIZON,
    HORIZONS,
    build_ladder_payload,
    price_card_on_kalshi,
)
from ...store import db
from ...kalshi.rest import KalshiAPIError
from ...store.combo_orders import (
    STATUS_GONE_AT_VENUE,
    TERMINAL_STATUSES as TERMINAL_COMBO_STATUSES,
    ComboOrderRefused,
    record_cancel as record_combo_cancel,
    record_gone_at_venue as record_combo_gone_at_venue,
    working_orders as working_combo_bids,
)
from ..schemas import (
    ComboBidCancelRequest,
    ComboBidRequest,
    ParlayLookupRequest,
    ParlayRequest,
)


def register(
    app: FastAPI,
    *,
    app_config: AppConfig,
    staleness: StalenessConfig,
    thresholds: SuppressionConfig,
    combo_api,
    get_conn,
    require_auth,
) -> None:
    """Attach the seven builder and parlay handlers, in their original order."""

    # -- builder -----------------------------------------------------------

    @app.post("/api/builder/parlay")
    def price_parlay(request: ParlayRequest) -> dict:
        """Price a sportsbook parlay against devigged consensus.

        A read-only calculation on numbers the caller supplies, so it needs no
        auth -- and it is available on the demo instance, where it is one of the
        more interesting things to show.

        Same-game legs return 422 with the refusal text rather than a number.
        """
        legs = tuple(l.to_leg() for l in request.legs)
        try:
            valuation = value_parlay(
                ParlayQuote(
                    legs=legs,
                    offered_decimal=american_to_decimal(request.offered_american),
                ),
                correlation_overrides=request.overrides(),
            )
        except CorrelationRefused as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        alternative = kalshi_equivalent(
            legs,
            contracts_per_leg=request.kalshi_contracts_per_leg,
            correlation_overrides=request.overrides(),
        )
        return {
            "fair_probability": valuation.fair_probability,
            "naive_probability": valuation.naive_probability,
            "independence_error_points": valuation.independence_error_points,
            "fair_american": decimal_to_american(valuation.fair_decimal),
            "offered_american": request.offered_american,
            "hold": valuation.hold,
            "ev_per_dollar": valuation.ev_per_dollar,
            "is_positive_ev": valuation.is_positive_ev,
            "correlation_was_supplied": valuation.correlation_was_supplied,
            "verdict": valuation.verdict,
            "kalshi_alternative": {
                "total_cost_dollars": alternative.total_cost_dollars,
                "total_fee_dollars": alternative.total_fee_dollars,
                "fee_share_of_stake": alternative.fee_share_of_stake,
                "expected_value_dollars": alternative.expected_value_dollars,
                "note": alternative.note,
            },
        }

    @app.get("/api/builder/wong-screen")
    def wong_screen(
        lines: str = Query(
            ...,
            description="Comma-separated team:line pairs, e.g. 'Chiefs:-8,Jets:2'",
        ),
        points: float = Query(6.0),
    ) -> dict:
        """Filter a slate to the legs inside the documented Wong windows.

        Deliberately strict. The entire effect lives in favourites of −7.5 to
        −8.5 and underdogs of +1.5 to +2.5 on a six-point teaser, and a screen
        that returned near-misses would defeat its own purpose.
        """
        board: list[tuple[str, float]] = []
        for pair in lines.split(","):
            team, _, raw = pair.partition(":")
            try:
                board.append((team.strip(), float(raw)))
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"{pair!r} is not 'team:line'",
                ) from exc

        candidates = find_wong_candidates(board, points=points)
        return {
            "points": points,
            "screened": [{"team": t, "line": l} for t, l in board],
            "candidates": [{"team": t, "line": l} for t, l in candidates],
            "note": (
                "Being in the window is necessary, not sufficient. Pricing the "
                "teaser needs an empirical margin distribution fitted per "
                "spread bucket; without one the Builder refuses rather than "
                "guessing."
            ),
        }

    # -- parlay desk (ADR 0070) --------------------------------------------

    @app.get("/api/parlays")
    def parlays(
        conn=Depends(get_conn),
        league: Optional[str] = Query(
            None,
            description=(
                "Cut the candidate pool to one league, by the odds feed's "
                "sport key (`baseball_mlb`). An unknown key is a 422."
            ),
        ),
        within_hours: Optional[int] = Query(
            None,
            ge=1,
            le=MAX_WITHIN_HOURS,
            description=(
                "Cut the candidate pool to games kicking off within this "
                "many hours, on the sportsbook's clock."
            ),
        ),
        horizon: str = Query(
            DEFAULT_HORIZON,
            description=(
                "Which kickoff window the cards are built from: `tonight` "
                "(default), `tomorrow`, or `48h`. Unlike `within_hours`, "
                "which only NARROWS the pool, this moves its upper bound. "
                "An unknown key is a 422."
            ),
        ),
    ) -> dict:
        """The ladder: three parlay cards at FAIR value, worded server-side.

        `league` and `within_hours` are the #15 cuts, parsed by the same
        function `/api/slate` uses. They shrink the candidate pool the six
        cards are built from and reorder nothing; every card keeps its own
        cut's ordering, none of which is the consensus-vs-Kalshi gap. The
        payload carries a `filter` echo, with how many legs the cut removed,
        only when a cut was applied -- unfiltered stays byte-identical.

        A read of the same devigged consensus the slate serves, reshaped into
        the venue's own combination product -- a betting-desk feature (ADR
        0062), not an edge claim. Nothing here computes a breakeven, an EV, or
        a size (`tests/test_parlays_api.py` walks the keys); Kalshi's actual
        quote for a card is read only by the lookup path, off the minted
        market's order book, and is never blended into these numbers.

        Refuses in words, never by omission: a card the slate cannot fill
        carries `not_built_reason`, and every excluded leg is counted by
        reason in `excluded`.
        """
        now = db.now_ms()
        # **Refused, not silently defaulted.** A typo in the query string
        # would otherwise serve tonight's cards under tomorrow's URL, and the
        # screen would look like it had simply found nothing -- the failure
        # mode this desk already has too much of.
        if horizon not in HORIZONS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"'{horizon}' is not a window this desk carries. "
                    f"Choose one of: {', '.join(HORIZONS)}."
                ),
            )
        try:
            list_filter = parse_list_filter(league, within_hours, now_ms=now)
        except FilterRefused as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return build_ladder_payload(
            conn,
            now_ms=now,
            max_odds_age_ms=staleness.max_odds_age_s * 1000,
            list_filter=list_filter,
            horizon=horizon,
            # Built from the configs that already enforce these limits, so the
            # score refuses on the same numbers every other surface does.
            # `thresholds` here is the SuppressionConfig -- deliberately not
            # named `suppression`, because a route function by that name would
            # rebind it, which it silently did once (see the comment at its
            # definition). Passing the engine's own config, not a second set.
            trust_thresholds=TrustThresholds.from_configs(
                staleness, thresholds
            ),
        )

    @app.post("/api/parlays/lookup", dependencies=[Depends(require_auth)])
    async def parlay_lookup(request: ParlayLookupRequest) -> dict:
        """Mint the card's combo on Kalshi and price it off its own book.

        Auth-gated: the POST creates a real market on the exchange (no money
        moves -- exactly what the app does when a user taps legs -- but it is
        an outward-facing write, and combo lookups are the one such write on
        the authorized-actions list). Synchronous: two REST calls, seconds.

        Refusals are words, never guesses: a drifted card is 409, a missing
        collection or an empty book comes back as a status the screen renders
        honestly, and every attempt -- priced, empty, refused, error -- is a
        `parlay_lookups` row.
        """
        try:
            api = combo_api()
        except ConfigError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"no Kalshi credentials on this instance: {exc}",
            ) from exc

        now = db.now_ms()
        # Its own writable connection, like every mutating route: `get_conn`
        # is deliberately read-only, and this route records a `parlay_lookups`
        # row for every outcome. Async route, one coroutine, one thread.
        write_conn = db.open_db(app_config.db_path)
        try:
            return await price_card_on_kalshi(
                write_conn,
                card_key=request.card_key,
                stake_cents=request.stake_cents,
                requested_legs=[
                    (l.event_ticker, l.market_ticker) for l in request.legs
                ],
                now_ms=now,
                max_odds_age_ms=staleness.max_odds_age_s * 1000,
                horizon=request.horizon,
                api=api,
            )
        except LookupRefused as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=exc.detail
            ) from exc
        finally:
            write_conn.close()

    @app.post("/api/parlays/bid", dependencies=[Depends(require_auth)])
    async def parlay_bid(request: ComboBidRequest) -> dict:
        """Rest a bid on this card's combination at Joe's chosen price.

        The desk's one control that commits money to a combination, and it
        rests rather than buys because there is nothing to buy: no combination
        book this repo has read carried a resting YES bid (ADR 0012 section 5).

        Refusals are words, and the one that matters most is the shard: Kalshi
        keeps collateral per exchange shard and will not move it for an order,
        so a $2 bid against a $21 account is refused when the combinations
        shard holds a penny. The venue says `insufficient_balance`; the desk
        says which shard, how much is on it, and where to fix it.
        """
        if not request.combo_acknowledged:
            # The census numbers are SOURCED from `parlays.COMBO_EXIT_CENSUS_*`
            # rather than typed. They were the literal digits "40 of 40" until
            # 2026-09-06 -- the same shape that kept a refuted census sentence
            # green for eleven days -- and the exit claim they carry is
            # unchanged, because the 2026-09-06 parlay census measured ENTRY.
            # Pinned by `test_no_census_number_in_the_bid_refusal_is_typed`,
            # which reads this source rather than the rendered string.
            # The scope clause is the same fix as the buy ticket's
            # `combo_note`, landed on BOTH surfaces in one commit and for the
            # reason the registration gives (§12.4): correcting one and not
            # the other reproduces the original defect on the surface nobody
            # looks at. Sourced, never typed -- `SHARD1` carries a digit and
            # the guard below refuses bare integers.
            raise HTTPException(
                status_code=422,
                detail=(
                    f"a combination is close to enter-only: "
                    f"{COMBO_EXIT_CENSUS_BOOKS_NO_YES_BID} of "
                    f"{COMBO_EXIT_CENSUS_BOOKS_READ} combination books this "
                    f"repo read had no YES bid on the other side. All of "
                    f"those were "
                    f"{' and '.join(COMBO_EXIT_CENSUS_SERIES)}, and "
                    f"{COMBO_EXIT_CENSUS_SHARD_BOOKS_READ} were on "
                    f"{COMBO_EXIT_CENSUS_SHARD_SERIES}. On "
                    f"{COMBO_EXIT_SHARD_YES_BID_DATE}, "
                    f"{COMBO_EXIT_SHARD_YES_BID_BOOKS} books on that shard "
                    f"did carry a resting YES bid of "
                    f"{COMBO_EXIT_SHARD_YES_BID_SIZE_CONTRACTS} contracts at "
                    f"a single price, so an exit exists, is small, and its "
                    f"frequency is unmeasured. The fee model is "
                    f"unverified (ADR 0046). Send `combo_acknowledged` only if "
                    f"that is understood."
                ),
            )
        try:
            api = combo_api()
        except ConfigError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"no Kalshi credentials on this instance: {exc}",
            ) from exc

        now = db.now_ms()
        write_conn = db.open_db(app_config.db_path)
        try:
            return await place_resting_bid(
                write_conn,
                card_key=request.card_key,
                requested_legs=[
                    (l.event_ticker, l.market_ticker) for l in request.legs
                ],
                price_tenths=request.price_tenths,
                stake_tenths=request.stake_cents * 10,
                now_ms=now,
                max_odds_age_ms=staleness.max_odds_age_s * 1000,
                api=api,
            )
        except ComboOrderRefused as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=exc.detail
            ) from exc
        except LookupRefused as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=exc.detail
            ) from exc
        finally:
            write_conn.close()

    @app.get("/api/parlays/bids")
    def parlay_bids(conn=Depends(get_conn)) -> dict:
        """Every resting bid that is or might still be working.

        Unauthenticated for the reason `/api/parlays` is: it reads the desk's
        own record and mutates nothing. A bid that can fill while nobody is
        watching has to be visible without a login prompt in the way.
        """
        rows = working_combo_bids(conn)
        return {
            "generated_ms": db.now_ms(),
            "bids": [
                {
                    "id": row["id"],
                    "ticker": row["ticker"],
                    "card_key": row["card_key"],
                    "status": row["status"],
                    "contracts": row["count"],
                    "price_display": format_price(row["limit_price_tenths"]),
                    "committed_display": format_dollars(
                        row["count"] * row["limit_price_tenths"]
                    ),
                    "placed_ms": row["placed_ms"],
                    "cancel_after_ms": row["cancel_after_ms"],
                    "dry_run": bool(row["dry_run"]),
                    # Said on every row rather than once at the top: a person
                    # scanning a list of "resting" bids will otherwise read the
                    # word as "working towards a fill".
                    "note": (
                        "Waiting for a seller. You hold nothing yet."
                        if row["status"] == "resting" else None
                    ),
                }
                for row in rows
            ],
        }

    @app.post(
        "/api/parlays/bids/{bid_id}/cancel",
        dependencies=[Depends(require_auth)],
    )
    async def parlay_bid_cancel(
        bid_id: int, request: ComboBidCancelRequest
    ) -> dict:
        """Take one resting bid back.

        **The shard comes from the stored row, never re-read from the market.**
        A cancel is most needed exactly when the market has become unreadable,
        and a cancel without its shard returns 404 for an order that is
        demonstrably resting (measured 2026-08-30).
        """
        try:
            api = combo_api()
        except ConfigError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"no Kalshi credentials on this instance: {exc}",
            ) from exc

        write_conn = db.open_db(app_config.db_path)
        try:
            row = write_conn.execute(
                "SELECT * FROM combo_orders WHERE id = ?", (bid_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, f"no bid with id {bid_id}")
            if row["status"] in TERMINAL_COMBO_STATUSES:
                raise HTTPException(
                    409,
                    "that bid is already " + str(row["status"])
                    + " and cannot be cancelled.",
                )
            if not row["kalshi_order_id"]:
                # A bid whose create never came back. Nothing to cancel at the
                # venue by id -- and refusing here would be wrong, because this
                # is the row most in need of attention. It is marked cancelled
                # locally with the reason on it, and the words say to check.
                record_combo_cancel(
                    write_conn, bid_id, now_ms=db.now_ms(), reduced_by=None,
                    reason="no exchange order id; cancelled locally only",
                )
                return {
                    "status": "cancelled_locally",
                    "words": (
                        "This bid has no exchange order id -- its request left "
                        "the desk and never came back. It is marked cancelled "
                        "here, but it may be resting on Kalshi: check the "
                        "Kalshi app before placing another."
                    ),
                }
            try:
                response = await api.cancel_order(
                    row["kalshi_order_id"],
                    exchange_index=row["exchange_index"],
                )
            except KalshiAPIError as exc:
                if exc.status_code != 404:
                    raise HTTPException(
                        502,
                        f"the cancel did not go through ({exc}). The bid may "
                        f"still be resting; try again or cancel it in the "
                        f"Kalshi app.",
                    ) from exc
                # The venue's 404 is correct and final: no order by this id is
                # resting. Until 2026-09-06 this branch told Joe the bid "may
                # still be resting" over an order that had filled five days
                # earlier, and left the row `resting` for the watcher to
                # retry once a minute. The row is marked terminal in the
                # venue's words -- not `cancelled`, because nothing was.
                record_combo_gone_at_venue(
                    write_conn, bid_id, now_ms=db.now_ms(), venue_body=exc.body,
                )
                return {
                    "status": STATUS_GONE_AT_VENUE,
                    "reduced_by": None,
                    "words": (
                        "Kalshi has no such order resting: it filled, was "
                        "cancelled, or has settled. Check Your bets."
                    ),
                }
            except Exception as exc:                             # noqa: BLE001
                raise HTTPException(
                    502,
                    f"the cancel did not go through ({exc}). The bid may still "
                    f"be resting; try again or cancel it in the Kalshi app.",
                ) from exc
            reduced = (
                response.get("reduced_by") if isinstance(response, dict) else None
            )
            try:
                reduced_by = None if reduced is None else float(reduced)
            except (TypeError, ValueError):
                reduced_by = None
            record_combo_cancel(
                write_conn, bid_id, now_ms=db.now_ms(),
                reduced_by=reduced_by, reason=request.reason,
            )
            withdrawn = 0.0 if reduced_by is None else reduced_by
            return {
                "status": "cancelled",
                "reduced_by": reduced_by,
                "words": (
                    f"Cancelled. {withdrawn:g} contracts were still working "
                    f"and are now withdrawn."
                ),
            }
        finally:
            write_conn.close()
