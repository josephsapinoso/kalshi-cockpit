"""Where real money moved: hand bets, refusals, settlements, the study arm.

Queries: `manual-orders-audit`, `manual-order-refusals`, `study-stop`,
`h4-settlement-balance`, `h4-balance-spans`, `estimate-match-status`.

This is the one module whose tables are downstream of Joe's own taps rather
than of the recorder, and the rules on it are correspondingly narrow.
`manual-orders-audit` reports **structure and counts only** -- no P&L, no
profit, no win rate, no CLV, no settled outcome, no typed estimate -- because
the 2026-08-29 registration fixes which of those may ever carry a verdict,
and an inspector that leaked one would let the rule be chosen after the
answer. The H4 queries emit independent sections and compute **no delta**: a
join would need a tolerance, and a tolerance is a matching decision. The one
ratio printed anywhere here is the largest ticker's share, which CLAUDE.md's
measurement rules require beside any aggregate.

`study-stop` mirrors ADR 0044 A2's formula and refuses with CANNOT KNOW
rather than reporting "not stopped".

**Every SQL string in this module is a constant.** This module is imported by
`inspect_live_db.py`, is never run directly, and inherits every disclaimer in
that file's docstring.
"""

from __future__ import annotations

import sqlite3
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from inspect_live_db_common import (
    Section,
    _derive_iso,
    _fetch,
    _iso,
)


# ---------------------------------------------------------------------------
# The hand-bet record: structure and counts, and deliberately nothing else.
# ---------------------------------------------------------------------------
#
# **The firewall is in the SQL, not only in the docstring.** Not one string
# below names `venue_settlements`, `settlements`, `closing_lines`, `fills` or
# `clv_tenths`, and none of them selects `p_yes_bp`. That is asserted by
# `tests/test_inspect_live_db.py`, because a prohibition that lives only in
# prose is a prohibition the next edit does not see.
#
# The reason is `docs/measurements/2026-08-29-preregistration-operator-self-
# assessment.md`, committed the same day as this query. It fixes, before any
# result has been seen, which panels may carry a verdict and at what `G`. An
# inspector that could print a win rate would let the rule be chosen after the
# answer, which is the one failure the whole registration exists to prevent --
# and its §0 records that the row count here was *deliberately* not obtained
# while the file was being written, precisely so no floor could be tuned to it.
#
# The vocabulary of statuses is spelled out so an absent bucket reads as zero
# rather than as unknown, and anything OUTSIDE the vocabulary is surfaced on
# its own rows with `outside_vocabulary = 1`. `dry_run` is in the vocabulary
# because the placer writes it by design on every unarmed rehearsal
# (`kalshi/orders.STATUS_DRY_RUN`) -- flagging it as unmodelled would be a
# false claim. `resting` is deliberately NOT: a manual order is always
# immediate-or-cancel, so a resting status here would be genuinely anomalous
# and deserves the flag.
_MANUAL_STATUS_VOCABULARY = (
    "VALUES ('filled'), ('partially_filled'), ('unfilled'), "
    "('rejected'), ('unrecognised_response'), ('pending'), ('dry_run')"
)

# `LIKE 'KXMVE%'` rather than a join: `backend/kalshi/discovery.py` drops that
# prefix as junk, so a combination has no `kalshi_markets` row to join to and
# the ticker text is the only thing that classifies it. No underscore in the
# pattern, so SQLite's single-character `_` wildcard cannot widen it.
_MANUAL_COMBO_CLASS = (
    "CASE WHEN UPPER(TRIM(ticker)) LIKE 'KXMVE%' "
    "THEN 'combo (KXMVE)' ELSE 'single market' END"
)

_SQL_MANUAL_CENSUS = (
    "SELECT COUNT(*) AS n_rows, "
    "COALESCE(SUM(CASE WHEN dry_run = 0 THEN 1 ELSE 0 END), 0) AS real_orders, "
    "COALESCE(SUM(CASE WHEN dry_run = 1 THEN 1 ELSE 0 END), 0) AS dry_runs, "
    "COALESCE(SUM(CASE WHEN kalshi_order_id IS NOT NULL THEN 1 ELSE 0 END), 0) "
    "  AS with_kalshi_order_id, "
    "COUNT(DISTINCT ticker) AS distinct_tickers, "
    "MIN(submitted_ms) AS first_submitted_ms, "
    "MAX(submitted_ms) AS last_submitted_ms "
    "FROM manual_orders"
)

_SQL_MANUAL_STATUS = (
    f"WITH vocabulary(status) AS ({_MANUAL_STATUS_VOCABULARY}) "
    "SELECT v.status AS status, 0 AS outside_vocabulary, "
    "COUNT(m.id) AS n_rows, "
    "COALESCE(SUM(CASE WHEN m.dry_run = 0 THEN 1 ELSE 0 END), 0) AS real_orders, "
    "COALESCE(SUM(CASE WHEN m.kalshi_order_id IS NOT NULL THEN 1 ELSE 0 END), 0) "
    "  AS with_kalshi_order_id "
    "FROM vocabulary v LEFT JOIN manual_orders m ON m.status = v.status "
    "GROUP BY v.status "
    "UNION ALL "
    "SELECT m.status, 1, COUNT(*), "
    "COALESCE(SUM(CASE WHEN m.dry_run = 0 THEN 1 ELSE 0 END), 0), "
    "COALESCE(SUM(CASE WHEN m.kalshi_order_id IS NOT NULL THEN 1 ELSE 0 END), 0) "
    "FROM manual_orders m "
    f"WHERE m.status NOT IN ({_MANUAL_STATUS_VOCABULARY}) "
    "GROUP BY m.status "
    "ORDER BY outside_vocabulary DESC, n_rows DESC, status"
)

_SQL_MANUAL_SNAPSHOT = (
    f"SELECT {_MANUAL_COMBO_CLASS} AS ticker_class, COUNT(*) AS n_rows, "
    "COALESCE(SUM(CASE WHEN consensus_fair_tenths IS NOT NULL THEN 1 ELSE 0 END), 0) "
    "  AS fair_value_present, "
    "COALESCE(SUM(CASE WHEN consensus_fair_tenths IS NULL THEN 1 ELSE 0 END), 0) "
    "  AS fair_value_null, "
    "COALESCE(SUM(CASE WHEN consensus_book_count IS NOT NULL THEN 1 ELSE 0 END), 0) "
    "  AS with_book_count, "
    "COALESCE(SUM(CASE WHEN consensus_anchored_on_sharp = 1 THEN 1 ELSE 0 END), 0) "
    "  AS anchored_on_sharp, "
    "COALESCE(SUM(CASE WHEN consensus_computed_ms IS NOT NULL THEN 1 ELSE 0 END), 0) "
    "  AS with_computed_ms, "
    "COALESCE(SUM(CASE WHEN consensus_fair_tenths IS NULL "
    "                   AND consensus_absent_reason IS NULL THEN 1 ELSE 0 END), 0) "
    "  AS null_and_unexplained "
    "FROM manual_orders "
    f"GROUP BY {_MANUAL_COMBO_CLASS} "
    "ORDER BY ticker_class"
)

_SQL_MANUAL_ABSENT_REASONS = (
    "SELECT COALESCE(consensus_absent_reason, '(none recorded -- pre-v28 row)') "
    "  AS absent_reason, "
    f"{_MANUAL_COMBO_CLASS} AS ticker_class, COUNT(*) AS n_rows "
    "FROM manual_orders WHERE consensus_fair_tenths IS NULL "
    f"GROUP BY absent_reason, {_MANUAL_COMBO_CLASS} "
    "ORDER BY n_rows DESC, absent_reason"
)

_SQL_MANUAL_TICKERS = (
    "SELECT ticker, COUNT(*) AS n_rows, "
    "ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM manual_orders), 1) "
    "  AS pct_of_rows, "
    "MIN(submitted_ms) AS first_submitted_ms, "
    "MAX(submitted_ms) AS last_submitted_ms "
    "FROM manual_orders GROUP BY ticker ORDER BY n_rows DESC, ticker"
)

_SQL_MANUAL_CONTRACTS = (
    'SELECT m."count" AS contracts, COUNT(*) AS n_rows, '
    "COALESCE(SUM(CASE WHEN m.dry_run = 0 THEN 1 ELSE 0 END), 0) AS real_orders "
    'FROM manual_orders m GROUP BY m."count" ORDER BY contracts'
)


#: The registered ceiling of the money arm, ADR 0044 §5 arm 3 as amended by A2.
#: Spelled here rather than imported: `inspect_live_db` imports nothing from
#: `backend`, so the number is duplicated on purpose and a guard asserts the two
#: agree -- the same treatment `FAILURE_LOG_NAME` gets.
STUDY_LOSS_CEILING_DOLLARS = 100.0

#: The venue's ways of saying "no result" on a settled position -- registration
#: A16 (2026-09-03). Duplicated from `backend.estimates.VOID_RESULTS` for the
#: reason above, and pinned equal by the same guard.
VOID_RESULTS = frozenset({None, "", "void"})

#: `meta` key holding the study's start instant. Absent means never opened.
STUDY_START_MS_KEY = "calibration_study_start_ms"


def _q_study_stop(conn: sqlite3.Connection, args) -> list[Section]:
    """Has the $100 money arm fired, and can it be computed at all?

    **Why this exists.** `POST /api/estimates` refuses with 423 -- *"The
    study is stopped and logging is closed, permanently"* -- once
    `estimates.study_loss_dollars` reaches the ceiling. Decision-map ticket
    #11 (resolved 2026-09-01) ruled the arm should stop gating that
    endpoint, and **nothing on the machine could report whether the arm had
    already fired** without smuggling SQL onto the money box.

    **It mirrors the registered formula verbatim** (A2): `sum(payout - cost -
    fee)` over study-period `venue_settlements`, where payout is
    `contracts x $1` on a win and `$0` on a loss, negated so a positive number
    is money lost. A second implementation of a decision-bearing formula is a
    liability, so `tests/test_study_stop_query.py` runs both this and
    `backend.estimates.study_loss_dollars` over the same fixtures and asserts
    they agree, including on every refusal.

    **The refusals are the point, and they are tri-state.** `None` is
    "cannot know", never "not stopped":

    - the study was never stamped open (no `study_start_ms`);
    - any study-period row carries a `market_result` outside {yes, no}
      that is not a registered void marker (`NULL`, `''`, `'void'` --
      A16, 2026-09-03). A void counts its fee as a loss and nothing
      else; anything else the venue might write still refuses, because
      the amendment named the venue's markers rather than licensing a
      guess;
    - any row has an unreadable fee, or a decided row an unreadable
      entry price.

    An empty settlement set with the study open is a true $0.00 and not a
    refusal.

    This does not breach the ADR 0044 embargo (A7; partner's ruling
    2026-08-18): §5 forbids aggregates over *the estimate log*, and this
    reads `venue_settlements` -- Joe's own money -- and no estimate row.

    What this does not establish
    ----------------------------
    - **Anything about the estimate log.** Not a win rate, not a count of
      logged bets, not a figure attributable to them. A7 forbids all three
      and this query cannot produce any of them: it never reads
      `bet_estimates`.
    - **That the endpoint is reachable.** The self-lockout is a second,
      independent 423 with its own clock, reported here as a separate row
      precisely so a reader does not take a clear money arm as "logging is
      open".
    - **Anything about unsettled positions.** The formula is over *realised*
      settlements by registration, so tonight's open risk is invisible to it
      by design.
    """
    start_text = None
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?", (STUDY_START_MS_KEY,)
    ).fetchone()
    if row is not None and row[0] is not None:
        start_text = str(row[0])

    refusal: Optional[str] = None
    loss: Optional[float] = None
    n_rows = 0

    if start_text is None:
        refusal = "the study was never stamped open (no study_start_ms in meta)"
    else:
        rows = conn.execute(
            "SELECT side, contracts, entry_price_tenths, fee_cost_tenths, "
            "market_result FROM venue_settlements WHERE settled_ms >= ?",
            (int(start_text),),
        ).fetchall()
        n_rows = len(rows)
        net_tenths = Decimal(0)
        for side, contracts_raw, entry, fee, result in rows:
            if fee is None:
                refusal = "a study-period settlement has an unreadable fee"
                break
            if result in VOID_RESULTS:
                # A16: the stake came back and the fee did not.
                net_tenths -= Decimal(fee)
                continue
            if result not in ("yes", "no"):
                refusal = (
                    f"a study-period settlement has market_result "
                    f"{result!r}, which is neither 'yes' nor 'no' nor a "
                    f"registered void marker (A16)"
                )
                break
            if entry is None:
                refusal = (
                    "a study-period settlement has an unreadable entry price"
                )
                break
            try:
                contracts = Decimal(str(contracts_raw))
            except InvalidOperation:
                refusal = "a study-period settlement has unreadable contracts"
                break
            if not contracts.is_finite() or contracts < 0:
                refusal = "a study-period settlement has negative contracts"
                break
            cost = contracts * entry
            payout = contracts * 1000 if result == side else Decimal(0)
            net_tenths += payout - cost - Decimal(fee)
        else:
            loss = float(-net_tenths / 1000)

    if refusal is not None:
        fired: Optional[bool] = None
        reading = "CANNOT KNOW -- and this may not be read as 'not stopped'"
    else:
        fired = loss is not None and loss >= STUDY_LOSS_CEILING_DOLLARS
        reading = (
            "FIRED -- POST /api/estimates returns 423 'logging is closed, "
            "permanently'"
            if fired
            else "not fired -- the money arm is not what is stopping logging"
        )

    # The self-lockout lives in its own table, not in `meta`: it is a
    # deliberate anti-tilt control with its own clock, and the write path
    # refuses on it independently of the money arm.
    lock_row = conn.execute(
        "SELECT MAX(until_ms) AS until_ms FROM self_lockouts WHERE until_ms > ?",
        (int(time.time() * 1000),),
    ).fetchone()
    lockout_ms = (
        int(lock_row[0]) if lock_row is not None and lock_row[0] is not None
        else None
    )

    # **How MANY rows are unreadable, not just that one is.** The formula
    # stops at the first bad row by registration, so the refusal above cannot
    # say whether this is one void or half the record -- and those are
    # different problems. Added 2026-09-01, when the live read came back
    # refusing on `market_result = ''` and the natural next question had no
    # instrument.
    result_mix: list[tuple[Any, ...]] = []
    if start_text is not None:
        result_mix = [
            (
                r[0] if r[0] not in (None, "") else (
                    "NULL" if r[0] is None else "'' (empty string)"
                ),
                r[1],
                "computable"
                if r[0] in ("yes", "no")
                else (
                    "void: its fee counts as a loss (A16)"
                    if r[0] in VOID_RESULTS
                    else "REFUSES the whole formula"
                ),
            )
            for r in conn.execute(
                "SELECT market_result, COUNT(*) FROM venue_settlements "
                "WHERE settled_ms >= ? GROUP BY market_result "
                "ORDER BY COUNT(*) DESC",
                (int(start_text),),
            ).fetchall()
        ]

    # **Which rows, not just how many.** A count says the arm is disabled; it
    # does not say whether the cause is one genuine void the formula should
    # tolerate or a poller gap that will recur. Those lead to different
    # repairs, and the repair is money-touching, so the reader needs the row.
    unreadable: list[tuple[Any, ...]] = []
    if start_text is not None:
        unreadable = [
            (
                r[0],
                _iso(r[1]),
                r[2],
                "KXMVE combo" if str(r[2] or "").startswith("KXMVE") else "single",
                r[3],
                r[4],
                "NULL" if r[5] is None else f"{r[5]!r}",
                "fee unreadable" if r[7] is None else (
                    "entry price unreadable" if r[6] is None
                    else "result unreadable"
                ),
            )
            for r in conn.execute(
                "SELECT id, settled_ms, ticker, side, contracts, "
                "market_result, entry_price_tenths, fee_cost_tenths "
                # A16: a void with a readable fee is computable and is not
                # listed here; a void's entry price is irrelevant.
                "FROM venue_settlements WHERE settled_ms >= ? "
                "AND (fee_cost_tenths IS NULL "
                "     OR (market_result IS NOT NULL "
                "         AND market_result NOT IN ('yes','no','','void')) "
                "     OR (market_result IN ('yes','no') "
                "         AND entry_price_tenths IS NULL)) "
                "ORDER BY settled_ms DESC",
                (int(start_text),),
            ).fetchall()
        ]

    return [
        Section(
            title=(
                "study-stop: has the $100 money arm fired? The formula is ADR "
                "0044 §5 arm 3 as amended by A2, mirrored verbatim and pinned "
                "against `backend.estimates.study_loss_dollars` by "
                "tests/test_study_stop_query.py. A refusal is 'cannot know' "
                "and NEVER 'not stopped'."
            ),
            columns=("quantity", "value", "note"),
            rows=[
                ("study_start_ms", start_text,
                 "absent means the study was never opened"),
                ("study-period settlements", n_rows,
                 "the population the formula runs over"),
                ("cumulative realised LOSS ($)", loss,
                 "positive is money lost; NULL is a refusal, not zero"),
                ("ceiling ($)", STUDY_LOSS_CEILING_DOLLARS,
                 "registered, not tunable here"),
                ("refusal", refusal, "why the figure could not be computed"),
                ("money arm fired", fired, reading),
                ("self-lockout until", _iso(lockout_ms),
                 "a SECOND and independent 423; a clear money arm does not "
                 "mean logging is open"),
            ],
            cap=args.limit,
        ),
        Section(
            title=(
                "study-stop: every market_result over the study period, so a "
                "refusal above can be read as 'one void' or 'the record is "
                "unreadable'. The formula stops at the FIRST bad row, so its "
                "message names one and cannot count them."
            ),
            columns=("market_result", "n", "effect on the formula"),
            rows=result_mix[:args.limit],
            truncated=len(result_mix) > args.limit,
            cap=args.limit,
        ),
        Section(
            title=(
                "study-stop: the rows that disable the formula, identified. A "
                "count says the arm is off; only the row says whether the "
                "cause is a genuine void the formula should tolerate or a "
                "poller gap that will recur -- and those need different "
                "repairs. EMPTY here with a refusal above means the refusal "
                "came from the study never being opened."
            ),
            columns=(
                "id", "settled_iso", "ticker", "kind", "side", "contracts",
                "market_result", "what is unreadable",
            ),
            rows=unreadable[:args.limit],
            truncated=len(unreadable) > args.limit,
            cap=args.limit,
        ),
    ]


def _q_manual_orders_audit(conn: sqlite3.Connection, args) -> list[Section]:
    """The hand-bet record: how many, of what shape, and how much of it is
    interpretable. **Structure and counts only.**

    WHAT THIS MAY NEVER REPORT, AND WHY THE PROHIBITION IS IN THE CODE
    -----------------------------------------------------------------
    **No P&L, no profit, no win rate, no CLV, no settled outcome, and no typed
    estimate.** Not a hedge and not a default -- a rule.
    `docs/measurements/2026-08-29-preregistration-operator-self-assessment.md`
    fixes, before any result has been seen, which panels on Joe's own record
    may carry a verdict and at what `G`: win rate never (§2.2), P&L not for
    thousands of bets (§2.1), CLV only descriptively (§6c), calibration only
    at `G >= 300` (§6a). Its §0 records that the row count below was
    **deliberately not obtained** while it was written, so no floor could be
    tuned to `n`; this query makes the count available afterwards and is
    scoped so that obtaining it cannot also obtain the answer. The comment
    above `_MANUAL_STATUS_VOCABULARY` says why in full.

    Nothing here joins `venue_settlements`, `settlements`, `closing_lines` or
    `fills`, and nothing selects `p_yes_bp`. `tests/test_inspect_live_db.py`
    asserts that over the SQL strings, because a prohibition that lives only
    in a docstring is one the next edit does not see.

    THE SECTIONS
    ------------
    - **A** the census: rows, real against dry-run, the `submitted_ms` range,
      distinct tickers, and how many carry a `kalshi_order_id` -- a venue
      acknowledgement, and the only structural evidence that a request reached
      the exchange at all.
    - **B** the status buckets, over a fixed vocabulary so an absent status
      reads as zero rather than as unknown. A status outside the vocabulary
      gets its own row with `outside_vocabulary = 1`; that is a finding, not a
      formatting detail, since `unrecognised_response` already means the venue
      answered in a shape this code did not model.
    - **C** the consensus snapshot's coverage (ADR 0082), split by whether the
      ticker is a `KXMVE` combination. A combination has NO devigged
      consensus -- discovery drops the prefix, so no `kalshi_markets` row and
      therefore no `fair_prices` row can ever exist for one -- so NULL there is
      correct and NULL on a single market is a gap. `null_and_unexplained`
      should be exactly the rows written before v28; a post-v28 row in that
      column is a bug in the writer.
    - **D** why the absent ones are absent, over
      `store/manual_orders.ABSENT_*`. `lookup_failed` is the only value that
      means the recorder broke; the rest are honest absences.
    - **E** rows per ticker with the largest one's share, which is
      `CLAUDE.md`'s standing requirement that a pooled count be printed beside
      its largest contributor. At single-digit `n` one ticker can be most of
      the record.
    - **F** the distribution of `count` -- contracts per order.

    WHAT THIS DOES NOT ESTABLISH
    ----------------------------
    - **Nothing about whether the bets were good.** By construction. See above.
    - **Nothing about whether an order filled at the venue.** `status` is what
      this process wrote after reading the response; `unrecognised_response`
      means it could not tell, and a row that stayed `pending` means the
      outcome write never landed, not that nothing went out.
    - **Nothing about coverage of the snapshot going forward.** Section C is a
      census of what is on disk now. Rows predating v28 have NULL in every
      snapshot column and were never going to have anything else.
    - **Nothing about the fair value being right.** `beta = -0.141`: agreement
      with the devigged consensus is not evidence of correctness. C counts how
      often the number exists, never whether it was good.
    """
    census = _derive_iso(
        _derive_iso(
            _fetch(
                conn,
                _SQL_MANUAL_CENSUS,
                (),
                title="A. the hand-bet census (structure and counts only)",
                cap=args.limit,
            ),
            "first_submitted_ms",
            "first_submitted_iso",
        ),
        "last_submitted_ms",
        "last_submitted_iso",
    )
    statuses = _fetch(
        conn,
        _SQL_MANUAL_STATUS,
        (),
        title=(
            "B. status buckets over the fixed vocabulary. A zero is a real "
            "zero; outside_vocabulary = 1 is a status this code did not model"
        ),
        cap=args.limit,
    )
    snapshot = _fetch(
        conn,
        _SQL_MANUAL_SNAPSHOT,
        (),
        title=(
            "C. the consensus snapshot (ADR 0082) by ticker class. NULL on a "
            "KXMVE combination is correct -- there is no consensus to record"
        ),
        cap=args.limit,
    )
    reasons = _fetch(
        conn,
        _SQL_MANUAL_ABSENT_REASONS,
        (),
        title=(
            "D. why the snapshot is absent, where it is. lookup_failed is the "
            "only value that means the recorder broke"
        ),
        cap=args.limit,
    )
    tickers = _derive_iso(
        _derive_iso(
            _fetch(
                conn,
                _SQL_MANUAL_TICKERS,
                (),
                title="E. rows per ticker, largest first, with its share",
                cap=args.limit,
            ),
            "first_submitted_ms",
            "first_submitted_iso",
        ),
        "last_submitted_ms",
        "last_submitted_iso",
    )
    contracts = _fetch(
        conn,
        _SQL_MANUAL_CONTRACTS,
        (),
        title="F. contracts per order",
        cap=args.limit,
    )
    return [census, statuses, snapshot, reasons, tickers, contracts]


# ---------------------------------------------------------------------------
# h4-settlement-balance: the raw material for settling H4, four sections,
# deliberately NOT joined
# ---------------------------------------------------------------------------
#
# H4 (ADR 0026/0027): does settlement carry its own fee? The decisive
# observation is a balance step around a settlement that differs from
# recorded proceeds-minus-known-fees. A join would need a tolerance, a
# tolerance is a matching decision, and matching decisions are where the
# flattering error lives in this repo -- so this emits four independent
# sections keyed by their own clocks and computes NO delta. The human does
# the subtraction where the confounds are visible on the same screen.

# The calibration study's start instant, 2026-08-18 09:15:03.594Z. The H4
# population is the settlements the balance poller could have witnessed, and
# the poller shipped with the study.
_H4_STUDY_START_MS = 1_787_044_503_594
# +/- 900s around each settlement: ~3 balance snapshots per side at the
# poller's 300s cadence.
_H4_WINDOW_MS = 900_000

_SQL_H4_SETTLEMENTS = (
    "SELECT id, ticker, side, contracts, entry_price_tenths,"
    "       fee_cost_tenths, market_result, settled_ms "
    "FROM venue_settlements WHERE settled_ms >= :study_start "
    "ORDER BY settled_ms"
)

_SQL_H4_BALANCE = (
    "SELECT b.observed_ms, b.balance_tenths, b.portfolio_value_tenths "
    "FROM venue_balance_snapshots b WHERE EXISTS ("
    "  SELECT 1 FROM venue_settlements s WHERE s.settled_ms >= :study_start"
    "  AND b.observed_ms BETWEEN s.settled_ms - :half AND s.settled_ms + :half"
    ") ORDER BY b.observed_ms"
)

_SQL_H4_FILLS = (
    "SELECT f.id, f.ticker, f.filled_ms, f.count, f.price_tenths,"
    "       f.is_taker, f.fee_actual, f.source "
    "FROM fills f WHERE EXISTS ("
    "  SELECT 1 FROM venue_settlements s WHERE s.settled_ms >= :study_start"
    "  AND f.filled_ms BETWEEN s.settled_ms - :half AND s.settled_ms + :half"
    ") ORDER BY f.filled_ms"
)

_SQL_H4_POLLS = (
    "SELECT p.polled_ms, p.ok, p.row_count, p.error "
    "FROM poll_log p WHERE p.endpoint = 'balance' AND EXISTS ("
    "  SELECT 1 FROM venue_settlements s WHERE s.settled_ms >= :study_start"
    "  AND p.polled_ms BETWEEN s.settled_ms - :half AND s.settled_ms + :half"
    ") ORDER BY p.polled_ms"
)


def _q_h4_settlement_balance(conn: sqlite3.Connection, args) -> list[Section]:
    """H4's raw material: settlements, balance, fills and polls, unjoined.

    Section B emits `portfolio_value_tenths` even though it is NULL on every
    row today -- that NULL is `parse_portfolio_value_tenths`'s deliberate
    refusal (`backend/portfolio_poll.py:252`: any non-zero value is refused
    until the field's unit is pinned), and dropping the column would hide
    the very blocker ADR 0027's correction names.
    Section D includes `ok` on purpose: without the poll record, a missing
    balance snapshot reads as a zero delta instead of an outage.

    What this does not establish
    ----------------------------
    - **No verdict and no delta.** Rows only; the H4 arithmetic needs a
      registration first, and the subtraction belongs where these confounds
      are visible together.
    - **Deposits are unrecorded by design** (`backend/config.py:499`), so a
      balance step is not attributable to settlement activity by this data
      alone.
    - **Balance resolution is $0.001 against a $0.0063 quantity in
      dispute**: `dollars_to_tenths` discards a digit the venue supplies, so
      a per-settlement fee smaller than a tenth of a cent may be invisible
      here even if real.
    """
    settlements = _fetch(
        conn,
        _SQL_H4_SETTLEMENTS,
        {"study_start": _H4_STUDY_START_MS},
        title=(
            f"A. venue_settlements since study start {_iso(_H4_STUDY_START_MS)}"
        ),
        cap=args.limit,
    )
    settlements = _derive_iso(settlements, "settled_ms", "settled_iso")
    window = {"study_start": _H4_STUDY_START_MS, "half": _H4_WINDOW_MS}
    balance = _fetch(
        conn,
        _SQL_H4_BALANCE,
        window,
        title=(
            "B. venue_balance_snapshots within +/-900s of an A settlement "
            "(portfolio_value_tenths NULL = the parser's deliberate "
            "refusal, shown on purpose)"
        ),
        cap=args.limit,
    )
    balance = _derive_iso(balance, "observed_ms", "observed_iso")
    fills = _fetch(
        conn,
        _SQL_H4_FILLS,
        window,
        title="C. fills within the same windows (the fill confound, visible)",
        cap=args.limit,
    )
    fills = _derive_iso(fills, "filled_ms", "filled_iso")
    polls = _fetch(
        conn,
        _SQL_H4_POLLS,
        window,
        title=(
            "D. poll_log endpoint='balance' within the same windows, "
            "including ok (a missing snapshot must read as an outage, not "
            "a zero delta)"
        ),
        cap=args.limit,
    )
    polls = _derive_iso(polls, "polled_ms", "polled_iso")
    return [settlements, balance, fills, polls]


# ---------------------------------------------------------------------------
# h4-balance-spans: Look 2's unwindowed raw material (Amendment 1, A12.3)
# ---------------------------------------------------------------------------
#
# The span design (A12.2) drops the +/-900s window entirely: every adjacent
# balance-snapshot pair is an observation, and the prediction P_j sums over
# EVERY settlement in the table, pre-study rows included. So sections B-D
# filter only on their own clock >= study start, and a fifth section carries
# the whole `venue_settlements` table. Still no join and no computed delta --
# a tolerance is a matching decision, and the analyzer owns those.

_SQL_H4_SPAN_BALANCE = (
    "SELECT observed_ms, balance_tenths, portfolio_value_tenths "
    "FROM venue_balance_snapshots WHERE observed_ms >= :study_start "
    "ORDER BY observed_ms"
)

_SQL_H4_SPAN_FILLS = (
    "SELECT id, ticker, filled_ms, count, price_tenths,"
    "       is_taker, fee_actual, source "
    "FROM fills WHERE filled_ms >= :study_start ORDER BY filled_ms"
)

_SQL_H4_SPAN_POLLS = (
    "SELECT polled_ms, ok, row_count, error "
    "FROM poll_log WHERE endpoint = 'balance'"
    " AND polled_ms >= :study_start ORDER BY polled_ms"
)

_SQL_H4_ALL_SETTLEMENTS = (
    "SELECT id, ticker, side, contracts, entry_price_tenths,"
    "       fee_cost_tenths, market_result, settled_ms "
    "FROM venue_settlements ORDER BY settled_ms"
)


def _q_h4_balance_spans(conn: sqlite3.Connection, args) -> list[Section]:
    """Look 2's raw material under the span design: unwindowed, unjoined.

    Registered by Amendment 1 (A12.3) of
    `docs/measurements/2026-08-20-preregistration-h4-settlement-fee.md`.
    Sections A-D mirror `h4-settlement-balance` but carry everything since
    study start on each table's own clock -- no `EXISTS` window, because the
    span design has no window. Section E is the WHOLE `venue_settlements`
    table: `P_j` sums winning settlements inside each snapshot pair whether
    or not they post-date the study, so a study-start filter here would
    silently zero pre-study terms out of the prediction.

    What this does not establish
    ----------------------------
    - **No verdict, no delta, no pairing.** Rows only. Adjacent-pair
      residuals, tolerances and cluster classification belong to the
      registered analyzer, committed before the pull as Look 1's was.
    - **Deposits are unrecorded by design** (`backend/config.py:499`); an
      interval can be long under this design, so an unrecorded transfer has
      more room to land in one. A9.2/A3's voting floor is the registered
      countermeasure, not anything in this query.
    - **The channel may still be blind**: if settled proceeds never credit
      the cash balance, no horizon reaches the charge (A14), and this query
      cannot detect that condition -- only the analyzer's positive-control
      gate (A10) can.
    """
    since = {"study_start": _H4_STUDY_START_MS}
    settlements = _fetch(
        conn,
        _SQL_H4_SETTLEMENTS,
        since,
        title=(
            f"A. venue_settlements since study start {_iso(_H4_STUDY_START_MS)}"
        ),
        cap=args.limit,
    )
    settlements = _derive_iso(settlements, "settled_ms", "settled_iso")
    balance = _fetch(
        conn,
        _SQL_H4_SPAN_BALANCE,
        since,
        title=(
            "B. venue_balance_snapshots since study start, UNWINDOWED "
            "(portfolio_value_tenths NULL = the parser's deliberate "
            "refusal, shown on purpose)"
        ),
        cap=args.limit,
    )
    balance = _derive_iso(balance, "observed_ms", "observed_iso")
    fills = _fetch(
        conn,
        _SQL_H4_SPAN_FILLS,
        since,
        title=(
            "C. fills since study start, UNWINDOWED "
            "(the fill confound, visible)"
        ),
        cap=args.limit,
    )
    fills = _derive_iso(fills, "filled_ms", "filled_iso")
    polls = _fetch(
        conn,
        _SQL_H4_SPAN_POLLS,
        since,
        title=(
            "D. poll_log endpoint='balance' since study start, UNWINDOWED, "
            "including ok (a missing snapshot must read as an outage, not "
            "a zero delta)"
        ),
        cap=args.limit,
    )
    polls = _derive_iso(polls, "polled_ms", "polled_iso")
    all_settlements = _fetch(
        conn,
        _SQL_H4_ALL_SETTLEMENTS,
        {},
        title=(
            "E. venue_settlements, WHOLE TABLE incl. pre-study "
            "(P_j sums every settlement inside a span, A12.2)"
        ),
        cap=args.limit,
    )
    all_settlements = _derive_iso(all_settlements, "settled_ms", "settled_iso")
    return [settlements, balance, fills, polls, all_settlements]


# ---------------------------------------------------------------------------
# estimate-match-status: the calibration study's coverage cells
# ---------------------------------------------------------------------------

_SQL_MATCH_STATUS_POSITIONS = (
    "SELECT estimate_match_status, COUNT(*) AS n,"
    "       MIN(settled_ms) AS min_settled_ms, MAX(settled_ms) AS max_settled_ms "
    "FROM venue_settlements GROUP BY estimate_match_status ORDER BY n DESC"
)

# The benign explanation for `out_of_scope = everything` is "every one is a
# multi-leg combo". `venue_settlements` carries no multi-leg flag, so the
# ticker prefix is the observable: KXMVE is the combo series. Splitting the
# status counts by that prefix is what lets a single non-combo `out_of_scope`
# row show up instead of drowning in the aggregate.
_SQL_MATCH_STATUS_POSITIONS_BY_KIND = (
    "SELECT estimate_match_status,"
    "       CASE WHEN ticker LIKE 'KXMVE%' THEN 'combo' ELSE 'single' END AS kind,"
    "       COUNT(*) AS n "
    "FROM venue_settlements "
    "GROUP BY estimate_match_status, kind ORDER BY n DESC"
)

_SQL_MATCH_STATUS_NONCOMBO_ROWS = (
    "SELECT id, ticker, side, contracts, settled_ms, estimate_match_status "
    "FROM venue_settlements "
    "WHERE ticker NOT LIKE 'KXMVE%' "
    "ORDER BY settled_ms DESC"
)

_SQL_MATCH_STATUS_ESTIMATES = (
    "SELECT match_status, COUNT(*) AS n,"
    "       MIN(match_status_ms) AS min_status_ms,"
    "       MAX(match_status_ms) AS max_status_ms "
    "FROM bet_estimates GROUP BY match_status ORDER BY n DESC"
)


def _q_estimate_match_status(conn: sqlite3.Connection, args) -> list[Section]:
    """The §7.5 coverage cells: position-side and estimate-side status counts.

    Emits rows and no verdict. The zero being checked -- 0 `position_unlogged`
    against 35 `out_of_scope` on the first classify pass -- is interesting
    exactly if a NON-combo position sits in `out_of_scope`, which section 3
    lists row by row.
    """
    positions = _fetch(
        conn,
        _SQL_MATCH_STATUS_POSITIONS,
        (),
        title="venue_settlements by estimate_match_status (NULL = not yet examined)",
        cap=args.limit,
    )
    positions = _derive_iso(positions, "min_settled_ms", "min_settled_iso")
    positions = _derive_iso(positions, "max_settled_ms", "max_settled_iso")
    by_kind = _fetch(
        conn,
        _SQL_MATCH_STATUS_POSITIONS_BY_KIND,
        (),
        title="the same statuses split combo (KXMVE) vs single-market ticker",
        cap=args.limit,
    )
    noncombo = _fetch(
        conn,
        _SQL_MATCH_STATUS_NONCOMBO_ROWS,
        (),
        title="every non-combo position row, newest first",
        cap=args.limit,
    )
    noncombo = _derive_iso(noncombo, "settled_ms", "settled_iso")
    estimates = _fetch(
        conn,
        _SQL_MATCH_STATUS_ESTIMATES,
        (),
        title="bet_estimates by match_status (NULL = never examined)",
        cap=args.limit,
    )
    estimates = _derive_iso(estimates, "min_status_ms", "min_status_iso")
    estimates = _derive_iso(estimates, "max_status_ms", "max_status_iso")
    return [positions, by_kind, noncombo, estimates]


_SQL_MANUAL_ORDER_REFUSALS = (
    "SELECT id, created_ms, check_number, check_name, http_status, detail,"
    "       ticker, side, requested_contracts, max_price_tenths,"
    "       idempotency_key, ask_tenths "
    "FROM manual_order_refusals ORDER BY created_ms DESC"
)


def _q_manual_order_refusals(conn: sqlite3.Connection, args) -> list[Section]:
    """Every refused hand bet, newest first (v29, 2026-08-30).

    Emits rows and no verdict. The population is Joe's own refused taps --
    single digits -- so the whole table prints. The `detail` column is the
    exact string the ticket showed him, which is the finding; `check_name`
    says which of the route's numbered brakes fired. An empty result on a
    night he reports a refusal means the write was journalled instead:
    read `/data/manual_order_refusals.jsonl` beside the database.
    """
    rows = _fetch(
        conn,
        _SQL_MANUAL_ORDER_REFUSALS,
        (),
        title="manual_order_refusals, newest first (empty = no brake has fired)",
        cap=args.limit,
    )
    rows = _derive_iso(rows, "created_ms", "created_iso")
    return [rows]
