"""`/api/estimates/*` and `/api/desk/*`: the calibration bet log and the desk's
own record of looking, passing and locking itself out.

Moved verbatim from `backend/api/routes.py` on 2026-09-04; see
`backend/api/routers/__init__.py` for the `register()` shape and why. The two
writers at the top (`_write_estimate`, `_revise_estimate`) were module-level
helpers with no other caller and came along unchanged -- which is why
`_write_estimate`'s docstring still says `_write_intent` is "below": that
writer belongs to the order path and stayed in `routes.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from ... import estimates as bet_estimates
from ... import passes as desk_passes
from ...config import AppConfig, ConfigError, OddsConfig
from ...kalshi.quotes import QuoteUnavailable
from ...odds import attention
from ...store import db
from ..schemas import DeskPassRequest, EstimateRequest, EstimateRevisionRequest


def _write_estimate(db_path, **kwargs) -> int:
    """One estimate row, on its own writable connection in a worker thread.

    Same shape as `_write_intent` below, for the same reason: the connection
    is made inside the threadpool worker that uses it, and it is short-lived
    so the write lock is held for the smallest possible window.
    """
    conn = db.open_db(db_path)
    try:
        return bet_estimates.record_estimate(conn, **kwargs)
    finally:
        conn.close()


def _revise_estimate(db_path, estimate_id: int, *, reason: str, revised_ms: int) -> bool:
    conn = db.open_db(db_path)
    try:
        return bet_estimates.revise_estimate(
            conn, estimate_id, reason=reason, revised_ms=revised_ms
        )
    finally:
        conn.close()


def register(
    app: FastAPI,
    *,
    app_config: AppConfig,
    odds: OddsConfig,
    live_quotes,
    get_conn,
    require_auth,
) -> None:
    """Attach the ten estimate and desk handlers to `app`, in their original
    order."""

    # -- the calibration bet log (registration 2026-08-17, as amended) -------

    @app.get("/api/estimates/markets")
    def estimate_market_search(
        q: str = Query(default="", max_length=80), conn=Depends(get_conn)
    ) -> dict:
        """The one-tap picker's search. Serves no prices, by construction.

        `search_markets` selects no quote column, so this route cannot leak
        the number the anchoring tripwires exist to measure.
        """
        query = q.strip()
        if len(query) < 2:
            return {"markets": []}
        return {
            "markets": bet_estimates.search_markets(
                conn, query, now_ms=db.now_ms()
            )
        }

    @app.get("/api/estimates/recent")
    def estimate_recent(conn=Depends(get_conn)) -> dict:
        """The last few entries, embargo-safe columns only.

        What Joe typed is not embargoed from Joe; what the server captured at
        estimate time is, until the registered stop. The column list lives in
        `estimates._SAFE_COLUMNS` and the test suite asserts the quote never
        appears here.
        """
        return {"estimates": bet_estimates.recent_estimates(conn)}

    @app.get("/api/estimates/last-scored")
    def estimate_last_scored_call(conn=Depends(get_conn)) -> dict:
        """The last scored call, singular: "you said 58%, Kalshi closed 61%".

        Ticket #11 decisions 8 and 9. **One call, or null** -- there is no
        `limit` parameter and no list form, because a list is a scoreboard
        with extra steps and eye-aggregation is still aggregation. The verdict
        belongs on the log screen, where seeing the last result immediately
        before typing the next one is the only place it can change anything.

        This route serves a score, which `/api/estimates/recent` deliberately
        does not: `recent` is a list, and a list of scores is the aggregate
        decision 8 forbids.

        **Why this does not breach ADR 0044's embargo.** Amendment 3 scopes the
        embargo to the study's own rows -- `is_study_row = 1`, collected under
        a promise they would never be shown. `last_scored_call` selects
        `is_study_row = 0` only, and the payload carries that flag so the
        embargo walker in the tests can see which regime it is looking at
        rather than being told.

        What it cannot establish: the score grades Joe against Kalshi's close
        and never against an outcome, so it is disagreement with the market,
        not correctness. A display, not a verdict; a verdict needs its own
        pre-registration and the shared 300 floor (ADR 0065, amended
        2026-08-29). Nothing here averages, rates, ranks or trends.
        """
        return {"call": bet_estimates.last_scored_call(conn)}

    @app.get("/api/estimates/stop")
    def estimate_money_arm(conn=Depends(get_conn)) -> dict:
        """The money arm's position: "$X of $100", for the /estimate strip.

        Embargo-safe by A7's explicit ruling (and the partner's, 2026-08-18):
        §5 forbids aggregates over *the estimate log*; this is a sum over
        `venue_settlements` -- Joe's own money, visible in the Kalshi app
        regardless -- and reads no estimate row. The guard that IS real:
        nothing here may be attributed to logged bets, split into a win rate,
        or scoped to the study population. One wallet number, nothing else.

        `loss_dollars` and `stopped` are null when the record cannot carry
        the registered formula (no study start stamped, or an unreadable
        settlement row) -- unknown is a state, not a zero, and the strip
        renders it as such.
        """
        loss = bet_estimates.study_loss_dollars(conn)
        return {
            # The registration's terminal state (Amendment 2, 2026-08-20):
            # Joe stopped the study, without result. Distinct from `stopped`
            # below, which is the $100 money arm and never fired -- the strip
            # must not render "the $100 stop has fired" for an owner stop.
            "study_state": bet_estimates.STUDY_TERMINAL_STATE,
            "stopped_by_owner_ms": bet_estimates.STUDY_STOPPED_BY_OWNER_MS,
            "loss_dollars": loss,
            "ceiling_dollars": bet_estimates.STUDY_LOSS_CEILING_DOLLARS,
            "stopped": None
            if loss is None
            else loss >= bet_estimates.STUDY_LOSS_CEILING_DOLLARS,
            # The self-lockout's release instant, or null. On this payload
            # rather than a route of its own because the strip that renders
            # the money arm is the strip that renders this -- one fetch, one
            # state, no second poller.
            "lockout_until_ms": bet_estimates.lockout_until(
                conn, now_ms=db.now_ms()
            ),
        }

    @app.post("/api/desk/lockout", dependencies=[Depends(require_auth)])
    def engage_desk_lockout(conn=Depends(get_conn)) -> dict:
        """One tap of "not tonight", on the desk's own name (2026-08-21).

        The lockout outlived the study that named its old route: it writes
        the same append-only `self_lockouts` table, keyed to the same day
        roll, and since the study stopped its value is the render -- the
        landing screen shows the note from the version of Joe that decided,
        with the release time -- plus the record of every reach for it. It
        is honest about what it cannot do: nothing here stops a hand bet in
        the Kalshi app. No parameters, no disengage, no duration picker,
        for the reasons the original gives.

        **Engaging from unlocked also appends one `desk_passes` row** (scope
        'tonight', slice B6): the tap IS the decision to pass the night, and
        one gesture should not need a second one to be counted. Guarded on
        not-already-locked because the lockout is idempotent by design -- a
        second tap is the same decision, not a second one, and must not
        inflate the pass count. Verified by disabling: pass write removed ->
        the lockout-writes-a-pass test fails; restored -> green.
        """
        del conn  # the write path opens its own handle, below
        now = db.now_ms()
        write_conn = db.open_db(app_config.db_path)
        try:
            already_locked = (
                bet_estimates.lockout_until(write_conn, now_ms=now) is not None
            )
            until_ms = bet_estimates.engage_lockout(
                write_conn,
                now_ms=now,
                day_start_hour=odds.budget_day_start_utc_hour,
            )
            if not already_locked:
                desk_passes.record_pass(
                    write_conn, now_ms=now, scope="tonight"
                )
        finally:
            write_conn.close()
        return {"locked": True, "until_ms": until_ms}

    @app.post("/api/desk/pass", dependencies=[Depends(require_auth)])
    def record_desk_pass(
        request: DeskPassRequest, conn=Depends(get_conn)
    ) -> dict:
        """Append one per-market pass (slice B6). Auth like every mutation.

        Writes `desk_passes` with the ticker as scope, uppercased to match
        every other ticker write. **Deliberately no validation against
        discovery**: a pass on a market this tool never discovered is still
        a decision Joe made, and refusing to record a real "no" because our
        own discovery missed the market is the wrong way round (the
        `venue_settlements` argument exactly). Append-only -- there is no
        edit or delete route, and the record is never scored or rated.
        """
        del conn  # the write path opens its own handle, below
        write_conn = db.open_db(app_config.db_path)
        try:
            pass_id = desk_passes.record_pass(
                write_conn,
                now_ms=db.now_ms(),
                scope=request.ticker.strip().upper(),
                reason=request.reason,
            )
        finally:
            write_conn.close()
        return {"recorded": True, "id": pass_id}

    @app.post("/api/desk/attention", dependencies=[Depends(require_auth)])
    def record_desk_attention(conn=Depends(get_conn)) -> dict:
        """Someone has the desk open. Auth like every mutation.

        **This is the input the odds feed follows** (ADR 0071 §2.6). The fixed
        `ODDS_DESK_WINDOW_UTC` bought a sweep every ten minutes for twelve hours
        a day whether or not anyone was looking; a stamp here is what now tells
        `decide_sweeps` that the ten-minute cadence is worth paying for.

        **The time is the server's, never the caller's**, and the route takes no
        body at all rather than an optional one. A client-supplied timestamp is
        a number the caller chooses, and the only value worth choosing is a
        future one -- which would hold the desk open past its own TTL. There is
        nothing a body could carry that this route should trust.

        No rate limit, deliberately. The ceiling that matters is the attention
        daily credit slice in `odds/timing.py`, which sits where the money is
        actually spent; a limit here would be a second and weaker copy of it.
        See the route handler in `frontend/src/app/desk-attention/route.ts`,
        which carries the same argument at more length.
        """
        del conn  # the write path opens its own handle, below
        write_conn = db.open_db(app_config.db_path)
        try:
            attention.stamp(write_conn, now_ms=db.now_ms())
        finally:
            write_conn.close()
        return {"recorded": True}

    @app.post("/api/estimates/lockout", dependencies=[Depends(require_auth)])
    def engage_self_lockout(conn=Depends(get_conn)) -> dict:
        """One tap of "not tonight" (fleet convening item 10).

        **Deprecated name, working route** (2026-08-21): the lockout now
        belongs to the desk, not the stopped study -- new callers use
        `POST /api/desk/lockout`. This stays because a deployed frontend may
        still call it and both write the same table, so they cannot come to
        disagree. Delete only with a frontend audit in hand.

        Locks `POST /api/estimates` -- logging a call -- until the next day
        roll at the odds budget's own hour, with a 423. **It is now the only
        423 on that endpoint**: the $100 money arm's was deleted 2026-09-01
        (ticket #11), and this one was deliberately kept, because a study stop
        condition and an instruction Joe gave himself are not the same kind of
        thing. **No parameters and no disengage
        endpoint**, deliberately: a lockout with a duration picker is a
        negotiation, and one that can be cancelled is a speed bump. Tapping
        again is idempotent; the release instant is a property of the clock.

        The write needs a writable connection; `get_conn` serves the API's
        usual read-only handle, so this opens its own, exactly as
        `log_estimate` does for its write.

        The pass write mirrors `/api/desk/lockout` exactly (slice B6): a tap
        through the deprecated name is the same decision and must count the
        same, or the pass total would depend on which frontend build tapped.
        """
        now = db.now_ms()
        write_conn = db.open_db(app_config.db_path)
        try:
            already_locked = (
                bet_estimates.lockout_until(write_conn, now_ms=now) is not None
            )
            until_ms = bet_estimates.engage_lockout(
                write_conn,
                now_ms=now,
                day_start_hour=odds.budget_day_start_utc_hour,
            )
            if not already_locked:
                desk_passes.record_pass(
                    write_conn, now_ms=now, scope="tonight"
                )
        finally:
            write_conn.close()
        return {"locked": True, "until_ms": until_ms}

    @app.post("/api/estimates", dependencies=[Depends(require_auth)])
    async def log_estimate(request: EstimateRequest) -> dict:
        """Record one call: stamp it, capture the quote, say nothing back.

        Since 2026-09-01 (ticket #11) every row written here is a **decoupled
        call**, `is_study_row = 0`: Joe logging what he thinks, not tied to a
        bet, scored at close against Kalshi's own price and read back to him
        one row at a time on `/api/estimates/last-scored`. The stopped study's
        own row is `is_study_row = 1` and is neither scored nor served (ADR
        0044 Amendment 3).

        The server fetches the market's book *at estimate time* and stores it
        for the anchoring tripwires (§7.7). **The response never carries it**,
        and that is unchanged by the decoupling: the score is the closing mid,
        not the book at the moment he typed, and handing him the latter would
        still be handing the anchor to the person being measured.

        A quote that cannot be read is recorded as a reason string rather than
        blocking the write -- the estimate is the measurement and a transient
        network failure must not cost the row. The one refusal: a ticker
        Kalshi has permanently never heard of AND discovery has never seen,
        which can only be a typo, and an unjoinable row is worse than a retype.
        """
        # **The $100 money arm used to refuse here, and it no longer does**
        # (decision-map ticket #11, resolved 2026-09-01; ADR 0044 Amendment 3).
        # It was a *study* stop condition sitting on the one endpoint that
        # records what Joe thinks. It never gated betting -- the order path
        # carries its own daily-loss switch and its own caps, and 76 of 76
        # settled positions were placed in the Kalshi app, which this server
        # cannot reach at all. So the only thing it could actually stop was
        # him writing a number down, which costs nothing and risks nothing.
        #
        # `study_loss_dollars` is untouched and `GET /api/estimates/stop`
        # still serves it: the wallet strip is a fact about his money and
        # keeps its reader. What is deleted is its power over the write path.
        #
        # **The self-lockout below is a different door and is deliberately
        # kept.** That is an instruction Joe gave himself, and its whole value
        # is that it does not negotiate.
        stop_conn = db.open_db(app_config.db_path, read_only=True)
        try:
            lockout_release = bet_estimates.lockout_until(
                stop_conn, now_ms=db.now_ms()
            )
        finally:
            stop_conn.close()
        # The self-lockout, server-side (fleet convening item 10) and now the
        # ONLY refusal on this route: a disabled button is a hint to a human;
        # this is the control. 423 Locked -- nothing about the request is
        # wrong, the resource is locked, and it unlocks itself at the day
        # roll.
        # Guard verified by disabling: predicate forced False -> the 423
        # lockout test fails; restored -> green.
        if lockout_release is not None:
            release_iso = datetime.fromtimestamp(
                lockout_release / 1000, timezone.utc
            ).strftime("%H:%M UTC on %Y-%m-%d")
            raise HTTPException(
                status_code=423,
                detail=(
                    f"You locked yourself out until {release_iso}. Nothing "
                    f"is wrong with the request; you asked not to be able to "
                    f"do this tonight, and there is no early unlock."
                ),
            )

        stamped = db.now_ms()
        ticker = request.ticker.strip().upper()
        yes_bid = yes_ask = observed = None
        unreadable: Optional[str] = None
        permanently_unknown = False
        try:
            quote = await live_quotes().fetch(ticker, observed_ms=stamped)
        except ConfigError as exc:
            unreadable = f"no Kalshi credentials at estimate time: {exc}"
        except QuoteUnavailable as exc:
            unreadable = str(exc)
            permanently_unknown = exc.permanent
        else:
            yes_bid = quote.market.yes_bid_tenths
            yes_ask = quote.ask_tenths("yes")
            observed = quote.observed_ms

        if permanently_unknown:
            conn = db.open_db(app_config.db_path, read_only=True)
            try:
                known = bet_estimates.market_context(conn, ticker) != (None, None)
                discovered = conn.execute(
                    "SELECT 1 FROM kalshi_markets WHERE ticker = ?", (ticker,)
                ).fetchone()
            finally:
                conn.close()
            if not discovered and not known:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Kalshi has never heard of {ticker!r} and neither "
                        f"has discovery. Check the ticker and retype it -- "
                        f"an estimate nothing can join to is not a record."
                    ),
                )

        row_id = await run_in_threadpool(
            _write_estimate,
            app_config.db_path,
            ticker=ticker,
            stated_probability_bp=request.stated_probability_bp,
            estimate_server_ms=stamped,
            had_already_opened_kalshi=request.had_already_opened_kalshi,
            estimate_client_ms=request.estimate_client_ms,
            server_yes_bid_tenths=yes_bid,
            server_yes_ask_tenths=yes_ask,
            server_quote_observed_ms=observed,
            server_quote_unreadable_reason=unreadable,
        )
        # Deliberately quote-free. Rendering the captured book here would hand
        # the anchoring reference to the person being measured (§7.7).
        return {
            "id": row_id,
            "ticker": ticker,
            "stated_probability_bp": request.stated_probability_bp,
            "estimate_server_ms": stamped,
        }

    @app.post(
        "/api/estimates/{estimate_id}/revise",
        dependencies=[Depends(require_auth)],
    )
    async def revise_estimate_route(
        estimate_id: int, request: EstimateRevisionRequest
    ) -> dict:
        """Flag an estimate as mistyped. Append-only; nothing is edited.

        The probability itself cannot be changed by anyone -- the schema
        trigger rejects the UPDATE below the route layer. This records the
        reason and sets the revised flag, which excludes the row (§2). The
        corrected estimate is a new row through `log_estimate`, with fresh
        clocks and a fresh quote.
        """
        done = await run_in_threadpool(
            _revise_estimate,
            app_config.db_path,
            estimate_id,
            reason=request.reason,
            revised_ms=db.now_ms(),
        )
        if not done:
            raise HTTPException(
                status_code=404, detail=f"no estimate with id {estimate_id}"
            )
        return {"revised": estimate_id}
