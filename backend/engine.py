"""The recommendation engine: ingest -> match -> devig -> EV -> size -> suppress.

One function does the whole chain for a single (market, side) pair and returns
a row. Two design choices in it are load-bearing.

**Every candidate produces a row, suppressed or not.** Suppressed rows carry a
reason and a `suggested_contracts` of zero, but they are stored, and they are
scored on closing-line value exactly like surfaced ones. That is what makes 300
scored observations reachable in a reasonable time without placing 300 bets --
and it is also what turns the suppression log into evidence rather than a bin.

**Every row records its `strategy_config_version`.** Without it, "did loosening
that threshold help?" is unanswerable: you cannot segment outcomes by the rules
that produced them, so the learning loop silently overfits to the last twenty
bets. With it, the question is a `GROUP BY`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, replace
from typing import Optional

from .config import RiskConfig
from .core.devig import DevigResult
from .core.ev import edge_after_fees_tenths, evaluate
from .core.prices import PRICE_MAX, format_price, format_probability
from .core.sizing import size_position
from .core.suppression import SuppressionConfig, evaluate_suppression
from .store.db import now_ms

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Candidate:
    """Everything needed to judge one side of one market."""

    ticker: str
    side: str                       # yes | no
    outcome_name: str               # the team this side pays on
    ask_tenths: int                 # DERIVED ask -- never a mid
    depth_at_ask: Optional[float]
    kalshi_quote_age_ms: int

    link_id: Optional[int]
    fair_price_id: Optional[int]
    devig: DevigResult
    book_count: int
    # `None` when fewer than two books contributed, so it could not be
    # measured. Suppression refuses on it rather than treating it as zero
    # disagreement -- see `core.suppression`.
    market_width: Optional[float]
    odds_age_ms: int
    commence_skew_ms: Optional[int]

    model_probability: Optional[float] = None


@dataclass(frozen=True)
class Recommendation:
    """A judged candidate, ready to persist. Suppressed ones are kept."""

    created_ms: int
    strategy_config_version: int
    ticker: str
    link_id: Optional[int]
    fair_price_id: Optional[int]
    side: str
    entry_ask_tenths: int
    depth_at_ask: Optional[float]
    fair_probability: float
    model_probability: Optional[float]
    edge_tenths: float
    fee_predicted: float
    ev_net_dollars: float
    kelly_fraction: float
    suggested_contracts: int
    # The same decision sized against a **fixed reference bankroll** instead of
    # the operator's. This is the column the gate's `actionable` counter reads,
    # and the two are different questions: `suggested_contracts` says what may be
    # bought today, `reference_contracts` says whether the strategy had a bet
    # here at all. Defining the evidence floor on the first made the deposit
    # decide what counted as evidence — at a $100 bankroll it is structurally
    # zero, so the 300-game counter could never move and nothing on the screen
    # would say why. See `config.RiskConfig.reference` and `docs/adr/0015`.
    reference_contracts: int
    kalshi_quote_age_ms: int
    odds_age_ms: int
    suppressed_reason: Optional[str]
    reason_text: str

    @property
    def surfaced(self) -> bool:
        return self.suppressed_reason is None and self.suggested_contracts > 0


def build_recommendation(
    candidate: Candidate,
    *,
    risk: RiskConfig,
    suppression: SuppressionConfig,
    strategy_config_version: int,
    current_exposure_dollars: Optional[float],
    current_position_dollars: Optional[float],
    daily_pnl_dollars: Optional[float],
    maker: bool = False,
    created_ms: Optional[int] = None,
) -> Recommendation:
    """Judge one candidate end to end.

    Never raises on a bad candidate -- it returns a suppressed row saying what
    was wrong. An exception here would drop the observation entirely, and a
    dropped observation is indistinguishable from one that was never generated.

    **The three risk-state inputs have no defaults**, and pass straight through
    to `size_position`, which refuses on `None`. They used to default to `0.0`
    and no caller supplied them, so the position cap and the daily loss limit
    were computed against a number this function invented. See `core.sizing`.
    """
    created = created_ms if created_ms is not None else now_ms()

    fair = candidate.devig.conservative_probability(candidate.outcome_name)
    method_spread = candidate.devig.method_spread(candidate.outcome_name)

    # Size first, because the fee -- and therefore the edge -- depends on it.
    sizing = size_position(
        side=candidate.side,
        ask_tenths=candidate.ask_tenths,
        fair_probability=fair,
        risk=risk,
        current_exposure_dollars=current_exposure_dollars,
        current_position_dollars=current_position_dollars,
        daily_pnl_dollars=daily_pnl_dollars,
        maker=maker,
    )

    # And again at the reference profile, which is what the *record* counts.
    #
    # Against a clean book -- zero exposure, zero position, zero P&L -- on
    # purpose. Whether this game is evidence that the strategy can pick must not
    # depend on what else happened to be open at the time, any more than it
    # depends on the size of the deposit. `current_exposure_dollars` is still
    # passed to the sizing above, where it belongs: it governs what may be
    # bought, which is the question the caps exist to answer.
    #
    # **All three zeros are written out, and that is the point of writing them.**
    # They used to be *omissions* that the sizer's defaults turned into zeros --
    # indistinguishable, at this call site, from the bug on the line above,
    # where the same omission meant "nobody ever measured this". Stated
    # explicitly, a zero here is a claim this function is making on purpose:
    # the reference profile is a clean book by definition. `tests/test_has_
    # callers.py` relies on the distinction, and requires at least one
    # production call site to supply a value it *computed* rather than a
    # literal, so these zeros cannot stand in for the wiring.
    reference = size_position(
        side=candidate.side,
        ask_tenths=candidate.ask_tenths,
        fair_probability=fair,
        risk=risk.reference(),
        current_exposure_dollars=0.0,
        current_position_dollars=0.0,
        daily_pnl_dollars=0.0,
        maker=maker,
    )

    # Edge is quoted at the size we would actually send. A per-contract edge
    # computed independently of size is wrong for every size but one.
    #
    # **At the offer's size, not the reference's**, and the difference is a
    # stated approximation rather than a second column: it is only the fee's
    # per-order rounding, measured at most 0.13c per contract between 5 and 25
    # contracts and exactly 0.00c at 50c. So the record's actionability is
    # judged on an edge computed for a possibly smaller order, which can only
    # make a marginal row *less* likely to count -- the safe direction.
    #
    # **`fee_predicted` therefore means three different things and the column
    # name says none of them.** The `max(1, ...)` is correct here -- an edge
    # needs *some* size to be computed at -- but it leaves the persisted field
    # ambiguous to every later reader:
    #
    #   sizing.contracts == N > 0   ->  the whole order's fee
    #   sizing.contracts == 0       ->  one contract's fee
    #   suppressed after sizing     ->  the fee for the order that was then
    #                                   refused, because `with_added_suppression`
    #                                   zeroes the size without touching the fee
    #
    # Observed on the seeded database: a row with `suggested_contracts = 0` and
    # `fee_predicted = 0.7877`, which is neither per-contract nor payable.
    # `OpportunityCard` reads it correctly today only because it renders it
    # inside a `suggested_contracts > 0` guard. **Anything that reads this
    # field outside that guard must divide by nothing and assume nothing** --
    # compute the per-contract figure from the ask instead. Not renamed or
    # split here because the column is persisted and that is a migration.
    sizing_contracts = max(1, sizing.contracts)
    edge_tenths = edge_after_fees_tenths(
        ask_tenths=candidate.ask_tenths,
        contracts=sizing_contracts,
        fair_probability=fair,
        maker=maker,
    )

    ev = evaluate(
        side=candidate.side,
        ask_tenths=candidate.ask_tenths,
        contracts=sizing_contracts,
        fair_probability=fair,
        maker=maker,
    )

    result = evaluate_suppression(
        config=suppression,
        kalshi_quote_age_ms=candidate.kalshi_quote_age_ms,
        odds_age_ms=candidate.odds_age_ms,
        commence_skew_ms=candidate.commence_skew_ms,
        depth_at_ask=candidate.depth_at_ask,
        # The **larger** of the two sizes, so one depth check governs both
        # claims. `insufficient_depth` asks whether the order can be filled, and
        # the reference order is usually the bigger one -- at a $100 bankroll
        # against the $1,000 reference it is roughly five times bigger. Checking
        # only the offer's size would let a row count toward the evidence floor
        # at a size the book could not have filled, which is the flattering
        # direction and the one this project refuses. Checking only the
        # reference's would be exactly what the $1,000 deployment has always
        # done, so the counter's meaning does not change; it just also applies
        # to the smaller offer, which is conservative and cheap.
        contracts=max(sizing_contracts, reference.contracts),
        market_width=candidate.market_width,
        book_count=candidate.book_count,
        edge_tenths=edge_tenths,
        method_spread_probability=method_spread,
    )

    reasons: list[str] = []
    if result.suppressed:
        reasons.append(result.detail)
    if sizing.refused:
        reasons.append(sizing.refusal_reason or "sizing refused")

    contracts = 0 if (result.suppressed or sizing.refused) else sizing.contracts
    reference_contracts = (
        0 if (result.suppressed or reference.refused) else reference.contracts
    )

    # The whole-order fee check used to live here, duplicating the one inside
    # `size_position` exactly -- same function, same arguments, same size. Two
    # paths encoding one rule is the failure this repo records under "delete one
    # of the paths"; the sizer owns it now. The order endpoint keeps its own
    # call because the size it sends is `min(requested, authorised, resized)`
    # and can be genuinely smaller than the one evaluated here.

    suppressed_reason = result.reason
    if sizing.refused and not suppressed_reason:
        suppressed_reason = f"sizing:{sizing.binding_constraint}"

    return Recommendation(
        created_ms=created,
        strategy_config_version=strategy_config_version,
        ticker=candidate.ticker,
        link_id=candidate.link_id,
        fair_price_id=candidate.fair_price_id,
        side=candidate.side,
        entry_ask_tenths=candidate.ask_tenths,
        depth_at_ask=candidate.depth_at_ask,
        fair_probability=fair,
        model_probability=candidate.model_probability,
        edge_tenths=edge_tenths,
        fee_predicted=ev.fee_dollars,
        ev_net_dollars=ev.ev_dollars if contracts else 0.0,
        kelly_fraction=sizing.kelly_fraction_used,
        suggested_contracts=contracts,
        reference_contracts=reference_contracts,
        kalshi_quote_age_ms=candidate.kalshi_quote_age_ms,
        odds_age_ms=candidate.odds_age_ms,
        suppressed_reason=suppressed_reason,
        reason_text=_explain(candidate, fair, edge_tenths, contracts, reasons),
    )


def with_added_suppression(
    rec: Recommendation, *, reason: str, problem: str
) -> Recommendation:
    """A judged row, re-stated as refused for one more reason.

    **Four fields move together or the screens disagree.** `suppressed_reason`
    alone is enough to stop `POST /api/orders` -- it refuses on a reason before
    it looks at anything else -- but the Board splits on `suggested_contracts`
    first, so a row carrying a reason *and* a positive size renders as an
    actionable card the server then refuses with a 422. That is the failure this
    repo already names: a screen offering a row the server will not sell. And
    `reason_text` is what the card actually shows, so leaving it reading
    "Buy 3." beside a refusal is the same defect in prose.

    `ev_net_dollars` goes to zero for consistency with `build_recommendation`,
    which records `0.0` on any row it sizes at zero contracts.

    **`reference_contracts` goes to zero too**, and that is the fourth field.
    The gate's floor counts games this strategy would have bet; a row its own
    reviewer refused is not one, whatever a reference bankroll would have sized
    it to. Leaving it positive here would let rejected rows accumulate evidence
    for a strategy that declined to make those bets — the same defect ADR 0005
    exists to prevent, arriving through a column that did not exist when it was
    written.

    The decision clause is replaced rather than appended. This is only ever
    called on a surfaced row, whose `reason_text` ends in `". Sized at {n}."`
    (`". Buy {n}."` before 2026-08-17 -- see `_explain`), so the last `". "` is
    the boundary between the head and the decision -- including on a team whose
    own name contains one ("St. Louis Cardinals"), which is why the split is
    from the right. **The split does not depend on the wording**, only on that
    final `". "`, which is why changing the verb did not touch this function.
    """
    head = rec.reason_text.rsplit(". ", 1)[0]
    return replace(
        rec,
        suppressed_reason=reason,
        suggested_contracts=0,
        reference_contracts=0,
        ev_net_dollars=0.0,
        reason_text=f"{head}. Not actionable -- {problem}.",
    )


def _explain(
    candidate: Candidate,
    fair: float,
    edge_tenths: float,
    contracts: int,
    problems: list[str],
) -> str:
    """Plain language for the Board.

    Written for someone deciding in a few seconds on a phone, so it leads with
    the comparison that matters -- fair versus what you pay -- rather than with
    the machinery that produced it.
    """
    # **A percentage, not a cent suffix.** This sentence renders verbatim on
    # every card, immediately under the fair value and beside the real ask, and
    # `consensus fair 53.8c` put a probability in a price's clothes at the one
    # spot where a left-to-right scan reads the wrong number as the thing you
    # pay. Through `format_probability` rather than a local `f"{p*100:.1f}%"`,
    # so this and the card's own figure derive from the same integer tenths and
    # cannot disagree by a rounding step.
    fair_percent = format_probability(fair)
    ask = format_price(candidate.ask_tenths)
    head = (
        f"{candidate.outcome_name}: consensus fair {fair_percent}, "
        f"Kalshi asks {ask} ({edge_tenths / 10:+.1f}c after fees)"
    )
    if problems:
        return f"{head}. Not actionable -- {'; '.join(problems)}."
    if contracts == 0:
        return f"{head}. No edge."
    # **Indicative, not imperative, and the mood is the whole edit.** This
    # returned `Buy {contracts}` until 2026-08-17. Everything in `head` survives
    # ADR 0038 -- `beta` refuted that `edge_tenths` predicts Kalshi's close, not
    # that the devig is wrong or the ask is misread, and those are facts already
    # bought and stored. The instruction did not survive: a tool whose own
    # registered statistic says its edge number carries no information may
    # report a size, but it may not tell anyone to take it.
    #
    # The count itself stays, deliberately. `reference_contracts` is what the
    # gate's `actionable` predicate counts (`backend/gate.py`), so dropping it
    # from the sentence to make the screen read better would be changing what is
    # measured in order to reach a target. Record the number; drop the verb.
    return f"{head}. Sized at {contracts}."


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def ensure_strategy_config(
    conn, config_dict: dict, rationale: str, *, now: Optional[int] = None
) -> int:
    """Return the current config version, creating one if the config changed.

    A new version is minted only when the config actually differs, so an
    unchanged restart does not fragment the record into versions that cannot
    be compared for lack of sample.
    """
    stamp = now if now is not None else now_ms()
    payload = json.dumps(config_dict, sort_keys=True)

    row = conn.execute(
        "SELECT version, config_json FROM strategy_configs "
        "WHERE effective_to_ms IS NULL ORDER BY version DESC LIMIT 1"
    ).fetchone()

    if row and row["config_json"] == payload:
        return int(row["version"])

    if row:
        conn.execute(
            "UPDATE strategy_configs SET effective_to_ms = ? WHERE version = ?",
            (stamp, row["version"]),
        )

    version = (int(row["version"]) + 1) if row else 1
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "effective_to_ms, config_json, rationale, approved_by_user) "
        "VALUES (?, ?, ?, NULL, ?, ?, 0)",
        (version, stamp, stamp, payload, rationale),
    )
    conn.commit()
    return version


def persist_recommendation(conn, rec: Recommendation) -> int:
    """Store a recommendation, suppressed or not, and return its id."""
    cursor = conn.execute(
        "INSERT INTO recommendations ("
        "created_ms, strategy_config_version, ticker, link_id, fair_price_id, "
        "side, entry_ask_tenths, depth_at_ask, fair_probability, "
        "model_probability, edge_tenths, fee_predicted, ev_net_dollars, "
        "kelly_fraction, suggested_contracts, reference_contracts, "
        "kalshi_quote_age_ms, odds_age_ms, suppressed_reason, reason_text) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rec.created_ms, rec.strategy_config_version, rec.ticker, rec.link_id,
            rec.fair_price_id, rec.side, rec.entry_ask_tenths, rec.depth_at_ask,
            rec.fair_probability, rec.model_probability, rec.edge_tenths,
            rec.fee_predicted, rec.ev_net_dollars, rec.kelly_fraction,
            rec.suggested_contracts, rec.reference_contracts,
            rec.kalshi_quote_age_ms, rec.odds_age_ms,
            rec.suppressed_reason, rec.reason_text,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


# Two prices are "the same decision" if the derived ask is identical and the
# fair probability agrees to this many places. Both are computed deterministically
# from the same inputs, so an unchanged slate reproduces them bit-for-bit; the
# rounding only guards against float noise.
_FAIR_PRECISION = 9


def confirm_recommendation(
    conn,
    recommendation_id: int,
    *,
    confirmed_ms: int,
    kalshi_quote_age_ms: int,
    odds_age_ms: int,
) -> None:
    """Record that this row was re-derived, unchanged, at `confirmed_ms`.

    **The distinction this exists to make.** `persist_if_changed` writes no
    second row for an unchanged decision, which is right for the record and was
    wrong for freshness, because every freshness check measured from
    `created_ms`. So a row went stale on a market that had not moved: the price
    was current and the *observation* was old, and one column meant both.

    A confirmation is a complete re-statement about one instant -- at
    `confirmed_ms` this exact decision was re-derived from a Kalshi quote of
    `kalshi_quote_age_ms` and a consensus of `odds_age_ms`. Both ages, never
    just the quote: the odds are the binding limit at fifteen minutes, and a
    confirmation that reset the quote clock alone would keep a row bettable
    forever on a consensus that had aged out. See `gate.live_ages`.

    `created_ms` is untouched, so nothing about the record changes -- the row
    still says when the decision was made, and CLV still scores it against a
    closing line observed after that instant.
    """
    conn.execute(
        "UPDATE recommendations SET last_confirmed_ms = ?, "
        "last_confirmed_quote_age_ms = ?, last_confirmed_odds_age_ms = ? "
        "WHERE id = ?",
        (confirmed_ms, kalshi_quote_age_ms, odds_age_ms, recommendation_id),
    )
    conn.commit()


def persist_if_changed(conn, rec: Recommendation) -> Optional[int]:
    """Store a recommendation unless it repeats the previous one for this side.

    **Why this exists.** The runner re-prices every market on every pass. With a
    15-minute interval and an odds budget that affords two sweeps a day, most
    passes see an unchanged Kalshi quote and unchanged odds, and re-record an
    identical decision. Measured on a real two-pass run: 152 rows carrying 77
    distinct `(ticker, side, ask, fair)` combinations -- half the record was
    repetition, and at ~96 passes a day it would be about 98%.

    That is not a statistical problem: the gate clusters by game, so repeats
    already count once. It is an *evidence* problem. A Ledger where 98% of rows
    are the same row is unreadable, and a suppression summary dominated by the
    same candidate rejected 96 times says nothing about which rules matter --
    the failure named in `tasks/lessons.md` as "if most inputs trigger it, it is
    a state, not an exception".

    **Consecutive, not global.** Only a row identical to the *most recent* row
    for that `(ticker, side)` is skipped. A price that moves 47 -> 48 -> 47 must
    record three observations, because the return to 47 is a genuine second
    opportunity at that price and dropping it would silently thin the record
    exactly where the market is moving most.

    **What this deliberately loses.** A candidate whose only change is ageing
    odds -- surfaced at 60s, suppressed at 900s -- records once, not twice. The
    transition is reconstructable from `created_ms` and the staleness limits, and
    logging it every pass is what would drown the suppression log.

    **Unchanged is confirmed, not discarded.** The skipped row is stamped with
    this pass's ages via `confirm_recommendation`, so "we did not re-record it"
    stops meaning "we never looked again". Without that the record was correct
    and the row was unbettable thirty seconds later on a market that had not
    moved.

    Returns the new row id, or `None` if the row was confirmed rather than
    re-recorded.
    """
    previous = conn.execute(
        "SELECT id, entry_ask_tenths, fair_probability FROM recommendations "
        "WHERE ticker = ? AND side = ? ORDER BY created_ms DESC, id DESC LIMIT 1",
        (rec.ticker, rec.side),
    ).fetchone()

    if previous is not None:
        same_ask = int(previous["entry_ask_tenths"]) == rec.entry_ask_tenths
        same_fair = round(
            float(previous["fair_probability"]), _FAIR_PRECISION
        ) == round(rec.fair_probability, _FAIR_PRECISION)
        if same_ask and same_fair:
            confirm_recommendation(
                conn,
                int(previous["id"]),
                confirmed_ms=rec.created_ms,
                kalshi_quote_age_ms=rec.kalshi_quote_age_ms,
                odds_age_ms=rec.odds_age_ms,
            )
            return None

    return persist_recommendation(conn, rec)


def suppression_summary(conn, since_ms: int) -> dict[str, int]:
    """How often each rule fired. The suppression log as evidence.

    A rule firing constantly is either miscalibrated or catching a real
    upstream problem, and both are findings worth acting on.
    """
    rows = conn.execute(
        "SELECT suppressed_reason, COUNT(*) AS n FROM recommendations "
        "WHERE created_ms >= ? AND suppressed_reason IS NOT NULL "
        "GROUP BY suppressed_reason",
        (since_ms,),
    ).fetchall()

    counts: dict[str, int] = {}
    for row in rows:
        # A row can fail several checks; the reason is a comma-joined list.
        for name in (row["suppressed_reason"] or "").split(","):
            if name:
                counts[name] = counts.get(name, 0) + int(row["n"])
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
