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
from dataclasses import asdict, dataclass
from typing import Optional

from .config import RiskConfig
from .core.devig import DevigResult
from .core.ev import edge_after_fees_tenths, evaluate
from .core.prices import PRICE_MAX, format_price
from .core.sizing import size_position, verify_positive_after_fees
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
    market_width: float
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
    current_position_dollars: float = 0.0,
    daily_pnl_dollars: float = 0.0,
    maker: bool = False,
    created_ms: Optional[int] = None,
) -> Recommendation:
    """Judge one candidate end to end.

    Never raises on a bad candidate -- it returns a suppressed row saying what
    was wrong. An exception here would drop the observation entirely, and a
    dropped observation is indistinguishable from one that was never generated.
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

    # Edge is quoted at the size we would actually send. A per-contract edge
    # computed independently of size is wrong for every size but one.
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
        contracts=sizing_contracts,
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

    # Final guard: sizing amortises the fee per contract, so re-check the whole
    # order. A bet that was marginal per-contract and negative in aggregate
    # must not slip through on a rounding difference.
    if contracts > 0 and not verify_positive_after_fees(
        side=candidate.side,
        ask_tenths=candidate.ask_tenths,
        contracts=contracts,
        fair_probability=fair,
        maker=maker,
    ):
        reasons.append(
            f"{contracts} contracts is not +EV once the whole-order fee is applied"
        )
        contracts = 0

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
        kalshi_quote_age_ms=candidate.kalshi_quote_age_ms,
        odds_age_ms=candidate.odds_age_ms,
        suppressed_reason=suppressed_reason,
        reason_text=_explain(candidate, fair, edge_tenths, contracts, reasons),
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
    fair_price = format_price(int(round(fair * PRICE_MAX)))
    ask = format_price(candidate.ask_tenths)
    head = (
        f"{candidate.outcome_name}: consensus fair {fair_price}, "
        f"Kalshi asks {ask} ({edge_tenths / 10:+.1f}c after fees)"
    )
    if problems:
        return f"{head}. Not actionable -- {'; '.join(problems)}."
    if contracts == 0:
        return f"{head}. No edge."
    return f"{head}. Buy {contracts}."


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
        "kelly_fraction, suggested_contracts, kalshi_quote_age_ms, odds_age_ms, "
        "suppressed_reason, reason_text) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rec.created_ms, rec.strategy_config_version, rec.ticker, rec.link_id,
            rec.fair_price_id, rec.side, rec.entry_ask_tenths, rec.depth_at_ask,
            rec.fair_probability, rec.model_probability, rec.edge_tenths,
            rec.fee_predicted, rec.ev_net_dollars, rec.kelly_fraction,
            rec.suggested_contracts, rec.kalshi_quote_age_ms, rec.odds_age_ms,
            rec.suppressed_reason, rec.reason_text,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


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
