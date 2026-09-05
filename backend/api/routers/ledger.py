"""`/api/bets` and `/api/ledger`: the settled record and the evidence record.

Moved verbatim from `backend/api/routes.py` on 2026-09-04; see
`backend/api/routers/__init__.py` for the `register()` shape and why.
`_gate_open` had exactly one caller and it is here, so it came along.

`/api/ledger` is the one route that joins `fair_prices` through
`recommendations.fair_price_id`, which is why this module is enumerated in
`scripts/dry_run_fair_price_downsample.py`'s F2 reader list: the P1 check
greps `backend/` for the table name and refuses any file that list does not
name.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, FastAPI, Query

from ... import bets as bets_module
from ... import estimates as bet_estimates
from ... import passes as desk_passes
from ...analysis.clv import DEFAULT_HORIZON_HOURS
from ...config import GateConfig
from ...gate import clustered_clv, evaluate_gate
from ...store import db
from ..serialise import _serialise


def _gate_open(conn, gate: GateConfig) -> bool:
    """One definition of open, shared by every caller.

    This used to be a second, independent implementation of the gate logic, and
    a looser one -- it never checked whether CLV survived the noise guard, so it
    would have reported open on a positive-but-indistinguishable record.
    """
    return evaluate_gate(conn, gate).open


def register(app: FastAPI, *, gate: GateConfig, get_conn) -> None:
    """Attach the two ledger handlers to `app`, in their original order."""

    @app.get("/api/bets")
    def bets(conn=Depends(get_conn), limit: int = Query(200, le=1000)) -> dict:
        """Joe's own settled bets, from the venue's settlement mirror.

        The first screen of the betting desk (ADR 0062, partner item 1):
        `venue_settlements` has been mirrored since 2026-08-18 and nothing
        ever read it back to him. Public read for the same reason the ledger
        is -- on live the middleware gates every route, and the demo's table
        is empty by construction (the poller needs credentials).

        Honesty contract, enforced in `backend/bets.py`: per-row net uses the
        one registered settlement formula (A2), a row that cannot carry it is
        None -- never 0 -- and the totals say how many rows they exclude.
        This endpoint never touches `bet_estimates`; the estimate log stays
        embargoed (Amendment 2 stopped the study without result).

        `open_positions` rides here as well as on the slate because /bets is
        the money-record screen and settled rows alone hide what is at risk
        right now -- the largest hole of the 2026-08-22 review.
        """
        payload = bets_module.bets_record(conn, limit=limit)
        now = db.now_ms()
        payload["open_positions"] = bets_module.open_positions(conn, now_ms=now)
        # The "not tonight" release, so /bets can render the same one-tap
        # control the slate carries (slice B5): the record screen with the
        # biggest red number in the product is where the impulse to chase
        # lives, and the control belongs beside it. Same table, same clock
        # as the slate's tonight block -- one source, two screens.
        payload["lockout_until_ms"] = bet_estimates.lockout_until(
            conn, now_ms=now
        )
        # The pass count (slice B6): the headline's unit becomes decisions,
        # not bets placed. Counts only, from `desk_passes` -- never joined
        # to outcomes, never rated.
        payload["passes"] = desk_passes.pass_summary(conn)
        return payload

    @app.get("/api/ledger")
    def ledger(
        conn=Depends(get_conn),
        limit: int = Query(200, le=1000),
        offset: int = Query(0, ge=0),
        max_id: Optional[int] = Query(None, ge=1),
    ) -> dict:
        """Every recommendation, surfaced or not.

        This is the evidence base: each row is scored on closing-line value
        whether or not it was bet, which is what makes 300 scored observations
        reachable without 300 wagers.

        Progress is reported in **independent games**, matching what the gate
        actually counts. Reporting rows here would put "412 of 300" on this page
        beside a Gate screen reading "9 of 300", and the flattering number is the
        one that gets believed. Both are returned so the ratio between them stays
        visible rather than being quietly folded away.

        **The payload says whether it is a slice or the table.** `rows` is
        windowed by `LIMIT`, and until `total` was returned beside it there was
        no way to tell 1,000 rows from all of them -- so any count computed off
        the payload was a claim about the most recent `limit` rows wearing the
        label of a claim about the record. `SELECT COUNT(*)` is the cheapest
        arithmetic in this file and it converts an unanswerable question into a
        subtraction.

        **And whether it is horizon-mixed.** `horizons` counts the whole table
        by `clv_horizon_hours`, not the returned window, because that is the one
        breakdown a slice cannot be trusted to report: the legacy 1.0h rows are
        the *oldest* ones and `ORDER BY created_ms DESC` is precisely the window
        that hides them. `primary_horizon_hours` names the anchor the gate
        counts, so a reader does not have to know which key is the current one.

        **`offset` exists so the table can be read whole.** `limit` caps at
        1,000 against 1,535 rows -- and `engine.persist_if_changed` writes a row
        only when the ask or the fair *moved*, so rows-per-game tracks price
        volatility and the newest slice is weighted toward volatile,
        wide-disagreement games. That is the direction that **inflates** an
        apparent edge, which is why paging is a prerequisite for a decisive
        measurement rather than a convenience.

        **`max_id` is the load-bearing half of that, and `offset` alone is a
        trap.** `ORDER BY created_ms DESC` sorts newest first, so a row written
        *during* a multi-page pull lands on page 0 and pushes every later page
        along by one. The recorder writes ~500-600 rows a day in sweeps, and
        **[MEASURED on live, 2026-08-10] one `created_ms` on this table carries
        84 rows**, so a sweep landing mid-pull shifts the window by most of a
        page. This is not hypothetical and it is not rare; it is what an active
        slate does.

        Reproduced directly, 120 rows pulled in four pages of 30 with one
        84-row sweep landing between page 0 and page 1:

            unpinned            returned 120, distinct  90, duplicated 30,
                                and 84 original rows never returned
            pinned to max_id    returned 120, distinct 120, duplicated  0

        **The failure is silent.** `returned` is 30 on every page, the four
        pages sum to 120, and `total` agrees -- so every check the payload
        supports passes while a quarter of the pull is duplicates and 84 rows
        are simply absent. A consumer would report a whole-table measurement
        over a multiset that is not the table.

        So a whole-table pull reads `max_id` from the first page and passes it
        back on every subsequent page. `id` is `INTEGER PRIMARY KEY
        AUTOINCREMENT`, so `id <= max_id` names a fixed prefix of the table that
        later writes cannot enter: the snapshot is immutable by construction
        rather than by hoping the recorder is idle. **`total` is counted under
        the same pin**, so paging until `offset + returned == total` terminates
        on the snapshot and not on a target that keeps moving.

        **The ordering also gains `id DESC`, and that one is hardening rather
        than a fix.** Ties are the normal case here -- [MEASURED] the newest
        1,000 rows carry only **169 distinct `created_ms` values** and 960 of
        them tie with at least one other row -- and within a tie
        `ORDER BY created_ms DESC` alone leaves the order unspecified by SQL,
        resting on whichever plan the query planner picks. It was measured to
        page consistently on a static table today, so no corruption is being
        claimed; but adding the `fair_prices` join below already changed the
        plan (`USE TEMP B-TREE FOR RIGHT PART OF ORDER BY`), and a paging
        contract that depends on a plan staying put is one optimiser change
        from being wrong. `(created_ms DESC, id DESC)` is a **total** order, so
        it cannot be. It also makes the route honest about "newest first":
        under the old ordering the 84 rows of one sweep came back
        oldest-`id`-first inside a descending page.
        """
        rows = conn.execute(
            # **The four devig methods travel with the row, not just the one
            # used.** `fair_probability` is `p_conservative` -- the *lowest*
            # reading across methods for the side being bought
            # (`devig.conservative_probability`) -- which is a deliberate
            # downward bias on fair value, and a downward bias mechanically
            # produces `edge <= 0`. Without the other three, no consumer can
            # ask what that policy costs, and `actionable = 0` cannot be
            # separated into "Kalshi is sharp" and "we chose a low fair".
            #
            # Raw columns rather than a computed spread or a server-side
            # histogram, on purpose: deploys are batched, so anything baked in
            # here costs a release to re-cut, while raw rows are re-cut for
            # free in a tested local module.
            #
            # `p_conservative` is sent beside the other four although it should
            # equal `fair_probability` exactly -- that equality is the check
            # that the `fair_price_id` join landed on the right row, and a
            # consumer cannot make it if only one of the pair is present.
            #
            # LEFT JOIN, and the four are `None` when it misses. `fair_price_id`
            # is nullable and the four `p_*` columns are themselves nullable in
            # `fair_prices`, so a missing method is a real state -- and per this
            # repo's rule it resolves to `None`, never `0`. A `0.0` here would
            # be a fair probability of zero, which is a legitimate value, so the
            # two states would be indistinguishable.
            #
            # **`market_width`, `book_count` and `books_used` are named here
            # for the same reason, and they had to be named.** `SELECT r.*`
            # does not reach them: all three live on `fair_prices`, not on
            # `recommendations`, so the join alone put nothing in the result
            # set and `_serialise` could not have emitted them however it was
            # written. ADR 0021's closing section records that these three were
            # never observed over the whole 1,564-row record, which left two of
            # the brief's registered predicates unanswerable; this is the half
            # of the fix that lives in SQL.
            #
            # They answer a question the five `p_*` columns cannot.
            # `market_width` is the books' disagreement and `book_count` is how
            # many opinions survived `runner.SHARP_BOOKS` anchoring -- so
            # ADR 0021 §7.2's tautology reading ("we tested Kalshi against the
            # only references plausibly as sharp as Kalshi") is checkable from
            # the record rather than only from a fixture captured on a
            # different day. `books_used` names *which* books, which is the
            # part no count can recover.
            #
            # **`anchored_on_sharp` is the fourth, and it is the one that
            # decides whether that reading holds at all.** The anchoring is
            # `selected = sharp or usable` (`backend/core/devig.py:288-289`), so
            # on a row where **no** sharp book quoted it falls back silently to
            # the full book set -- and that row was compared against a *wide*
            # consensus, not against the sharp reference class. Whether that
            # ever happened is data, not code, and `book_count` cannot reveal
            # it: three sharp books and three soft ones both read `3`. Without
            # this column §7.2's central claim is unfalsifiable on the record.
            # **`commence_ms` is the sportsbook's clock, never Kalshi's.** Until
            # 2026-08-21 this route joined nothing that carries a start time,
            # yet `_serialise` emitted the key anyway, so every row read
            # `commence_ms: null` and a consumer could not distinguish "never
            # joined" from "event unknown". The join deliberately does NOT go
            # through `kalshi_events.commence_ms`: that column stores
            # `occurrence_datetime` raw, which on game series is the expected
            # *end* -- about three hours late (ADR 0006) -- and this route is
            # the registered evidence route, where pre/post-commence bucketing
            # is exactly the axis a three-hour error poisons. `MIN` over the
            # fixture's snapshots is the scorer's own definition
            # (`backend/scoring.py:markets_awaiting_scoring`), so the ledger's
            # bucketing axis and the machinery that writes the clv fields agree
            # on when a game started. LEFT JOINs, so a row with no link or no
            # snapshot resolves to `None`, never a substitute.
            "SELECT r.*, "
            "       f.p_multiplicative, f.p_additive, f.p_power, f.p_shin, "
            "       f.p_conservative, "
            "       f.market_width, f.book_count, f.books_used, "
            "       f.anchored_on_sharp, "
            # The fixture id rather than its start: the kickoff is read below,
            # in one query bounded by this PAGE. The derived table that used to
            # sit here aggregated the whole of `odds_snapshots` -- unbounded by
            # the page, so a 25-row page paid for the entire record. Same
            # `MIN` per fixture, same value; only the bound changes.
            "       l.odds_event_id "
            "FROM recommendations r "
            "LEFT JOIN fair_prices f ON f.id = r.fair_price_id "
            "LEFT JOIN event_links l ON l.id = r.link_id "
            "WHERE (? IS NULL OR r.id <= ?) "
            "ORDER BY r.created_ms DESC, r.id DESC LIMIT ? OFFSET ?",
            (max_id, max_id, limit, offset),
        ).fetchall()
        # **This page's kickoffs, in one bounded query.** See the SELECT above:
        # the join it replaces grouped every snapshot ever recorded to answer a
        # question about at most `limit` rows.
        #
        # `MIN(commence_ms)` per fixture is the scorer's own definition
        # (`backend/scoring.py:markets_awaiting_scoring`), so the ledger's
        # bucketing axis and the clv machinery still agree on when a game
        # started -- and it is the sportsbook's clock, never
        # `kalshi_events.commence_ms`, which is `occurrence_datetime` raw and
        # about three hours late on game series (ADR 0006).
        #
        # `None` on a row with no link or no snapshot, never a substitute.
        _fixture_ids = sorted(
            {r["odds_event_id"] for r in rows if r["odds_event_id"]}
        )
        _kickoffs: dict[str, int] = {}
        if _fixture_ids:
            _marks = ",".join("?" * len(_fixture_ids))
            _kickoffs = {
                k["odds_event_id"]: k["commence_ms"]
                for k in conn.execute(
                    f"SELECT odds_event_id, MIN(commence_ms) AS commence_ms "
                    f"FROM odds_snapshots WHERE odds_event_id IN ({_marks}) "
                    f"GROUP BY odds_event_id",
                    _fixture_ids,
                ).fetchall()
            }
        _ledger_rows = []
        for r in rows:
            item = _serialise(r)
            item["commence_ms"] = _kickoffs.get(r["odds_event_id"])
            _ledger_rows.append(item)

        # Counted under the same pin as the rows, or paging to `total` never
        # terminates on an active slate: the target would grow while the pull
        # walks it. Unpinned, this is the whole table exactly as before.
        total = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM recommendations "
                "WHERE (? IS NULL OR id <= ?)",
                (max_id, max_id),
            ).fetchone()["n"]
        )
        # The newest id **in the table**, not in the page -- so a caller can
        # pin a snapshot from page 0 without having read the rows, and so a
        # pinned pull can still see that the table has moved on.
        newest_id = conn.execute(
            "SELECT MAX(id) AS m FROM recommendations"
        ).fetchone()["m"]
        # `null` for the unscored, keyed as a string because JSON object keys
        # are strings and `0.0` and `1.0` must stay distinguishable from each
        # other and from "not scored".
        horizons = {
            ("unscored" if r["h"] is None else f"{float(r['h']):g}"): int(r["n"])
            for r in conn.execute(
                "SELECT clv_horizon_hours AS h, COUNT(*) AS n "
                "FROM recommendations GROUP BY clv_horizon_hours"
            ).fetchall()
        }
        scored = clustered_clv(conn)

        return {
            "rows": _ledger_rows,
            "clv_scored": scored.n_clusters,
            "clv_scored_rows": scored.n_rows,
            "clv_required": gate.min_scored_recommendations,
            "gate_open": _gate_open(conn, gate),
            # Slice or table. `returned` is `len(rows)` and is sent anyway: the
            # comparison a reader needs is a one-glance one, and making them
            # count an array to make it is how the check stops being made.
            "total": total,
            "returned": len(rows),
            "limit": limit,
            # Echoed so a pull assembled from several pages can prove which
            # pages it holds. `total`, `returned` and `limit` alone cannot
            # distinguish "I fetched every page" from "I fetched page 0 twice".
            "offset": offset,
            # The pin in force on this response, echoed back rather than
            # assumed: `None` says the caller is reading a moving table and any
            # multi-page pull off it is unsound.
            "max_id": max_id,
            # The newest id in the table. Pass it back as `max_id` to pin a
            # snapshot. Under a pin it also reports how far the table has moved
            # since -- `newest_id > max_id` means rows arrived during the pull
            # and were correctly excluded, which is the check that the pin did
            # something rather than the check that it was unnecessary.
            "newest_id": newest_id,
            "horizons": horizons,
            "primary_horizon_hours": DEFAULT_HORIZON_HOURS,
        }
