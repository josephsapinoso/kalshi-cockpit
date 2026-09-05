"""Row -> JSON for a `recommendations` row: `_serialise` and its helpers.

Moved here verbatim on 2026-09-04 from `backend/api/routes.py`, which had
grown past the 262,144-byte ceiling at which the Read tool refuses a file
(`tests/test_session_files_are_readable.py`; the plan is
`docs/decisions/2026-09-04-routes-split-map.md`). `_serialise` is the one
genuinely shared dependency in that split -- `/api/board`, `/api/slate`,
`/api/market/{ticker}` and `/api/ledger` all render through it -- which is
why it has a module of its own rather than travelling with a router.
`routes.py` imports `_serialise`, `_is_prop_market` and `_decode_books_used`
back, so the names tests pin on its namespace still resolve there.

Every function here is a pure function of a row: no connection, no clock it
does not receive as `now_ms`, no limit it does not receive as an argument.
The live-age reconstruction is `gate.live_ages` and never a copy of it -- see
`_live_ages`, and the reason it is written as a call rather than as
arithmetic.
"""

from __future__ import annotations

import json
import math
from statistics import NormalDist
from typing import Optional

from ..config import StalenessConfig
from ..core.prices import format_price, format_probability, tenths_to_dollars
from ..core.trust import TrustThresholds, method_spread_points, score_trust
from ..gate import live_ages
from ..kalshi.props import MARKET_TYPE_PROP


def _live_ages(
    row,
    *,
    now_ms: Optional[int],
    staleness: Optional[StalenessConfig],
) -> dict:
    """Each stored age, moved forward to now, and whether both still pass.

    **The reconstruction is `gate.live_ages`, not a copy of it.** This used to
    restate the arithmetic beside a comment promising it matched the order
    endpoint's, which is the shape this repo keeps getting caught by: two paths
    that agree until one of them learns something. It learned something --
    `last_confirmed_ms` moves the instant a row is measured from -- and a Board
    still measuring from `created_ms` would strike through rows the server would
    happily sell.

    Returns `actionable: False` when there is no clock to measure against, and
    when an age is unreadable. An age that cannot be determined is not a fresh
    one -- the same refusal the order endpoint makes.

    **`actionable` is the odds clock, not both clocks.** The order endpoint
    re-reads the Kalshi quote inside the request (`kalshi/quotes.py`), so the
    recorded quote's age no longer decides whether an order is accepted --
    which makes a row struck through for a stale *quote* a row the server would
    happily sell. That is the two-screens-disagree failure with the conservative
    sign, and it is not harmless: between thirty seconds and fifteen minutes
    after a pass, which is most of the window, every sized row was being buried
    under "the moment has passed".

    What the recorded quote age still decides is whether the **price on the
    card** is the price you would pay, which is a different claim and gets its
    own field. Both are sent, because a page that showed only the first would
    offer a sized bet at a number the order will not honour.
    """
    if now_ms is None or staleness is None:
        return {}

    ages = live_ages(row, now_ms=now_ms)
    quote, odds = ages.quote_age_ms, ages.odds_age_ms
    readable = quote is not None and odds is not None and quote >= 0 and odds >= 0
    return {
        "quote_age_now_ms": quote,
        "odds_age_now_ms": odds,
        # The consensus cannot be refreshed without spending a credit, so this
        # is the limit that actually ends a row's life.
        "actionable": readable and odds <= staleness.max_odds_age_s * 1000,
        # The Kalshi half. False means "orderable, but expect the price to move
        # under you" -- not "expired".
        "price_is_current": readable and quote <= staleness.max_kalshi_quote_age_s * 1000,
        # Surfaced so the Board can say *why* a row is still live. A price
        # re-checked fifteen seconds ago and a price nobody has looked at since
        # it was written are different claims, and only one should reassure.
        "freshness_confirmed": ages.confirmed,
        "freshness_measured_from_ms": ages.measured_from_ms,
    }


# A week of betting at the rate this tool could ever support. Stated as a
# constant and sent with the probability it produces, so the screen cannot
# report the number against a different run length than the one it was
# computed for.
LOSING_RUN_BETS = 10


def _losing_run_probability(ev_dollars: float, sd_dollars: float) -> Optional[float]:
    """How often `LOSING_RUN_BETS` bets of this shape end down, edge and all.

    Normal approximation to the sum of ten independent bets, each with mean
    `ev_dollars` and deviation `sd_dollars`:
    ``P(sum < 0) = Phi(-sqrt(k) * mu / sigma)``.

    **`None` when there is no position**, never 0.5 and never 0. A row the
    engine did not size has no run to lose, and an unmeasurable probability
    that renders as a number is the failure this repo has recorded twice.

    Verified against the demo: its best-sized row is +$0.0135 with a $0.4728
    deviation, which gives 0.464.

    **The review quoted 45.6%, off a $0.2619 expectation and a $7.4778
    deviation. Those were 17 contracts at a $1,000 bankroll no instance
    deploys** -- see ADR 0041's 2026-08-18 amendment. The ratio barely moves
    because both terms scale with size; what moved is which row is "best" once
    the deployed caps flatten every size to 1.
    """
    if sd_dollars <= 0:
        return None
    return NormalDist().cdf(-math.sqrt(LOSING_RUN_BETS) * ev_dollars / sd_dollars)


def _decode_books_used(raw) -> Optional[list[str]]:
    """`fair_prices.books_used` (a JSON array in TEXT) -> a list, or `None`.

    **Never `[]` on failure.** An empty list is a real answer -- it says the
    consensus was built from no book at all, which would be a serious defect
    worth seeing -- so it cannot double as "this could not be read". Unreadable
    resolves to `None` and the caller refuses, per `tasks/lessons.md`.

    `None` in means the `LEFT JOIN` on `fair_prices` missed. Anything that is
    not a JSON array of strings means the column is corrupt, which has never
    been observed and would be a real finding rather than something to paper
    over with a default.
    """
    if raw is None:
        return None
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(decoded, list) or not all(isinstance(b, str) for b in decoded):
        return None
    return decoded


def _is_prop_market(row) -> bool:
    """Whether a joined `recommendations x kalshi_markets` row is a player prop.

    Read from the two RECORDED columns and never from the ticker string:
    `market_type` is what the runner classified the market as at discovery
    (`kalshi/props.PROP_SERIES` is the producer, `discovery.py:390-392`), and
    `player_name` is parsed only when that classification is `prop`
    (`discovery.py:664-669`), so a non-null player is a prop by construction
    even if `market_type` were ever missing. `market_type` alone is the
    primary: a prop whose subtitle could not be read carries `market_type =
    'prop'` and a NULL player, and must still be excluded.

    A row with neither column -- `/api/ledger` joins no `kalshi_markets` --
    resolves to "not a prop", which is the honest reading of "not recorded".
    """
    keys = row.keys()
    if "market_type" in keys and row["market_type"] == MARKET_TYPE_PROP:
        return True
    return "player_name" in keys and row["player_name"] is not None


def _serialise(
    row,
    *,
    now_ms: Optional[int] = None,
    staleness: Optional[StalenessConfig] = None,
    trust_thresholds: Optional[TrustThresholds] = None,
    scout: Optional[dict] = None,
) -> dict:
    """Row -> JSON, with prices rendered for display alongside the raw tenths.

    Both forms are sent deliberately: the frontend must never re-derive a price
    from a float, and a human reading the payload should be able to see `50.3c`
    without doing arithmetic.

    `kalshi_quote_age_ms` and `odds_age_ms` stay exactly as recorded, because on
    the Ledger they are a historical fact about the observation and must not
    move. Pass `now_ms` and `staleness` to add the *current* ages beside them
    under distinct names, which is what the Board needs and what the Ledger
    must not silently be given: one field name meaning "then" on one screen and
    "now" on another is how the two screens come to disagree.

    Pass `trust_thresholds` (and `scout`) to add the sweet spot -- ADR 0090's
    evidence score, the same one the parlay card carries. **The key is absent
    entirely when no thresholds arrive**, never computed against defaults: a
    limit written down twice is the drift `StalenessLimitsDisagree` refuses to
    boot on, and a silently-defaulted score would be exactly that with no error
    to announce it. That is why the Ledger, which calls this with neither,
    serves no score rather than a stale one.
    """
    # **Argument validation before any work**, and before any column is read:
    # a caller that asked for a score it cannot honestly get should be told so
    # rather than handed a payload it half-filled.
    if trust_thresholds is not None:
        if now_ms is None or staleness is None:
            # Refuse rather than score against ages that were never computed.
            # Without `live` there is no `odds_age_now_ms`, so every age check
            # would read `unknown` -- a score that looks measured and is not,
            # on a screen offering a money decision.
            raise ValueError(
                "trust_thresholds needs now_ms and staleness: without them "
                "the age checks score as unknown and the row looks examined"
            )
        if "p_conservative" not in row.keys():
            # The devig join is what supplies the readings, the book count and
            # the width. Missing, the score would still render -- with
            # `methods_agree` reading "fewer than two devig methods solved",
            # which is a claim about the DEVIG when the truth is that the
            # caller never joined `fair_prices`. Refuse rather than say that.
            raise ValueError(
                "trust_thresholds needs the fair_prices join: without it the "
                "score reports an unsolved devig where none was attempted"
            )

    ask = row["entry_ask_tenths"]
    live = _live_ages(row, now_ms=now_ms, staleness=staleness)
    contracts = row["suggested_contracts"] or 0
    fee = row["fee_predicted"] or 0.0
    # A binary contract settles at $1 or $0, so one contract's payoff has a
    # spread of exactly $1 and a standard deviation of sqrt(p(1-p)). The fee is
    # deterministic and adds no variance, so the position's deviation is just
    # that times the size. Reproduced against the demo's best row before
    # anything derived from it was rendered: 15 contracts at p=0.5385 gives
    # $7.478, against $0.262 expected -- 29 times the mean.
    fair = row["fair_probability"]
    sd = contracts * math.sqrt(max(0.0, fair * (1.0 - fair)))
    # Cost stays in integer tenths until the last step. `ask * contracts` is
    # exact; `tenths_to_dollars(ask) * contracts` is not.
    stake = tenths_to_dollars(ask * contracts)
    # **All four devig readings, when the caller joined them in.** Present only
    # on the Ledger, which is the one route that joins `fair_prices` through
    # `recommendations.fair_price_id`; the Board and the market detail select
    # from `recommendations` alone and get `{}` here rather than five null keys
    # pretending the join was attempted and empty.
    #
    # `row.keys()` rather than a parameter, matching how `yes_side_team` and
    # `event_title` are already handled: the shape of the row is what decides,
    # so a caller cannot ask for the fields and silently get nulls because its
    # query lacked the join.
    methods = (
        {
            "p_multiplicative": row["p_multiplicative"],
            "p_additive": row["p_additive"],
            "p_power": row["p_power"],
            "p_shin": row["p_shin"],
            # Should equal `fair_probability` exactly. Sent so a consumer can
            # check the join landed on the right `fair_prices` row rather than
            # assuming it.
            "p_conservative": row["p_conservative"],
        }
        if "p_conservative" in row.keys()
        else {}
    )
    # **How much consensus there was, and whose.** Same join, same route, same
    # presence rule as `methods` above -- these three live on `fair_prices` and
    # only the Ledger reaches them.
    #
    # ADR 0021's closing section records that these were *never observed* over
    # the whole 1,564-row record, so two of the predicates the measurement brief
    # registered went unanswered. The reason was never that the join was
    # missing: it has been there since the four devig readings were added. The
    # SELECT list simply named five `f.` columns and not eight, and this dict is
    # hand-built and named none of them. Both halves had to change.
    #
    # What they make answerable, which the five `p_*` columns cannot:
    #
    # - `book_count` is how many books survived `runner.SHARP_BOOKS` anchoring.
    #   ADR 0021 §7.2 argues the whole refutation may be a tautology -- Kalshi
    #   compared only against references as sharp as Kalshi -- and quotes a
    #   magnitude ("a median of 26 of 29 usable books discarded") measured on a
    #   *fixture captured 5.65 hours before the record's earliest odds
    #   observation*, overlapping it on zero of 1,564 rows. This column is what
    #   replaces that borrowed number with one measured on the record itself.
    # - `market_width` is the surviving books' disagreement, and it is the
    #   suppression input behind `too_few_books` / `no_market_width`.
    # - `books_used` names *which* books. No count recovers that, and "three
    #   books agreed" means something different when the three are two
    #   exchanges and Pinnacle.
    #
    # **`market_width = None` on a joined row is a real state, not a gap.** One
    # book cannot disagree with itself, so there is no width to report, and
    # `0.0` is simultaneously a legitimate reading (two books quoting
    # identically). `core/devig.py` splits them for exactly that reason and this
    # payload must not collapse them back -- see `tasks/lessons.md`, *the zero
    # that means "no measurement" passes every threshold*.
    #
    # **`book_count` is the join's own tell.** It is `NOT NULL` in
    # `fair_prices`, so `book_count is None` on a row where the key is present
    # means the `LEFT JOIN` missed and nothing else. That is what lets a
    # consumer read `market_width is None` as "unmeasurable" rather than as
    # "unjoined" without guessing.
    consensus = (
        {
            "market_width": row["market_width"],
            "book_count": row["book_count"],
            # Stored as a JSON array in a TEXT column; decoded here so a
            # consumer is not handed JSON inside JSON. `None` rather than `[]`
            # on anything unreadable -- an empty list is a claim that no book
            # was used, which is a different fact from "we could not tell".
            "books_used": _decode_books_used(row["books_used"]),
            # **Did the sharp anchoring actually bind on this row?**
            # `selected = sharp or usable`, so `False` means no sharp book
            # quoted and the fair value came from the *full* book set -- a wide
            # consensus wearing a sharp consensus's name.
            #
            # Stored as INTEGER 0/1 and surfaced as a real bool, because
            # `0` and `False` read identically in JSON while `None` must stay
            # distinct: the column is `NOT NULL DEFAULT 0` in `fair_prices`, so
            # `None` here means the LEFT JOIN missed and nothing else.
            "anchored_on_sharp": (
                None
                if row["anchored_on_sharp"] is None
                else bool(row["anchored_on_sharp"])
            ),
        }
        if "book_count" in row.keys()
        else {}
    )
    # **The sweet spot, on the two screens Joe asked for it on** (ADR 0090's
    # open item: he chose the parlay card, the slate row and the market
    # detail; the card shipped first). The same `score_trust` the card calls,
    # not a second scorer -- which is why `core/trust.py` takes primitives and
    # owns no query: three surfaces feeding one function is what stops them
    # disagreeing about whether a row is well-evidenced.
    #
    # Three arguments are worth reading twice:
    #
    # - `skeptic="checked"` is true BY CONSTRUCTION here and is not a guess.
    #   This function serialises a `recommendations` row, and the existence of
    #   that row is precisely what `parlays.leg_facts` looks up to decide
    #   between `checked` and `absent`. The parlay path has to ask because it
    #   starts from a leg; this path starts from the answer.
    # - `depth_at_ask` is the depth RECORDED WITH THE ROW, not a fresh read.
    #   That is the honest pairing: every other input here is the same
    #   observation's, and `quote_fresh` is the check that says how old the
    #   whole set is. Re-reading the book for this one field would score a
    #   row's depth against a different instant from its price.
    # - `market_width=None` reaches `score_trust` as a FAILURE, not an
    #   unknown, and that is the module's own rule: fewer than two books
    #   contributed, so there was no second book to disagree with.
    trust = None
    if trust_thresholds is not None:
        # **A row the devig join missed gets no score at all.** `book_count`
        # is `NOT NULL` in `fair_prices`, so `None` here means the LEFT JOIN
        # found nothing -- the tell `consensus` above already documents. Four
        # of the eight checks read off that row, and scoring anyway would
        # publish "fewer than two devig methods solved", which is a claim
        # about the DEVIG when the truth is that there was no fair price to
        # read. Four unknowns from one missing join is also not the same
        # quantity as four separately unmeasured checks, and the payload has
        # no way to say which it is holding.
        #
        # `None` rather than a partial score, which is this repo's convention
        # in one line: unreadable resolves to `None`, never to a number that
        # looks measured.
        if row["book_count"] is not None:
            scout_facts = scout or {}
            trust = score_trust(
                max_odds_age_s=trust_thresholds.max_odds_age_s,
                max_kalshi_quote_age_s=trust_thresholds.max_kalshi_quote_age_s,
                min_book_count=trust_thresholds.min_book_count,
                max_market_width=trust_thresholds.max_market_width,
                min_depth_contracts=trust_thresholds.min_depth_contracts,
                odds_age_ms=live.get("odds_age_now_ms"),
                quote_age_ms=live.get("quote_age_now_ms"),
                book_count=row["book_count"],
                market_width=row["market_width"],
                method_spread_points=method_spread_points(
                    (
                        row["p_multiplicative"],
                        row["p_additive"],
                        row["p_power"],
                        row["p_shin"],
                    )
                ),
                depth_at_ask=row["depth_at_ask"],
                skeptic="checked",
                suppressed_reason=row["suppressed_reason"],
                scout=scout_facts.get("scout", "absent"),
                scout_flags=scout_facts.get("scout_flags") or [],
            ).as_payload()

    return {
        **live,
        **methods,
        **consensus,
        **({"trust": trust} if trust_thresholds is not None else {}),
        "id": row["id"],
        "ticker": row["ticker"],
        "created_ms": row["created_ms"],
        "strategy_config_version": row["strategy_config_version"],
        "side": row["side"],
        # `team` is the YES-side team on BOTH rows of a market -- that is what
        # `kalshi_markets.yes_side_team` is -- so on a NO row it names the
        # opponent of the side being priced. Kept as-is: it is what the
        # picks block, `betDirection.ts` and the ticket sheet read, and each
        # of them relies on it meaning exactly that.
        "team": row["yes_side_team"] if "yes_side_team" in row.keys() else None,
        # **The team (or Over/Under) this row's own side pays on.** Ticket #6:
        # the Games row printed `team` under a NO row and so named the wrong
        # side, on 98.9% of tickers with both sides present at once, the
        # same name on two adjacent rows with different asks. This is
        # `fair_prices.outcome_name` on the row's own `fair_price_id`, which
        # `runner.py` binds per side (`side_outcome` there: YES to the
        # market's outcome, NO to the other one; `tests/test_runner.py`
        # pins that the two sides resolve to different names). It is read,
        # never derived: renaming sides inside a route by string
        # manipulation is refused above (the picks block), because a
        # derivation that goes wrong produces the *other* team's name, which
        # looks entirely plausible on screen.
        #
        # `None` when the caller did not join `fair_prices` (the ledger) or
        # the row has no fair price -- never `team`, which on a NO row is the
        # defect this field exists to end. On a total this is "Over" or
        # "Under": the row IS about a side of a total, so that is the honest
        # name, and it is why this is a second field rather than an
        # overwrite of `team`.
        "side_outcome": row["outcome_name"] if "outcome_name" in row.keys() else None,
        "event_title": row["event_title"] if "event_title" in row.keys() else None,
        "commence_ms": row["commence_ms"] if "commence_ms" in row.keys() else None,
        "ask_tenths": ask,
        "ask_display": format_price(ask),
        "ask_dollars": tenths_to_dollars(ask),
        "fair_probability": row["fair_probability"],
        "fair_display": format_price(int(round(row["fair_probability"] * 1000))),
        # The same number as a percentage, which is what it actually is. Kept
        # beside `fair_display` rather than replacing it because the ticker,
        # the ledger and any script reading this payload move at different
        # speeds -- but nothing on screen may render the `c` form any more.
        "fair_percent_display": format_probability(row["fair_probability"]),
        "edge_tenths": row["edge_tenths"],
        "edge_cents": row["edge_tenths"] / 10.0,
        "fee_predicted": row["fee_predicted"],
        "ev_net_dollars": row["ev_net_dollars"],
        "suggested_contracts": row["suggested_contracts"],
        # **The size the record counts, beside the size you may buy.** These are
        # two different questions and the payload used to answer only the first,
        # which made the second unanswerable from anywhere but a log line:
        # `gate.POPULATIONS` splits `actionable` on `reference_contracts`, so a
        # consumer holding only `suggested_contracts` cannot tell why a row was
        # or was not counted, and at the deployed $100 bankroll the two columns
        # genuinely differ on every row written since 78b5790. See ADR 0015.
        #
        # `None` is passed through rather than coerced to 0. A NULL here means a
        # row that predates schema v6 and escaped the backfill, which is a
        # different state from "the strategy had no bet", and the repo's rule is
        # that unreadable resolves to `None`, never `0`.
        "reference_contracts": row["reference_contracts"],
        "kelly_fraction": row["kelly_fraction"],
        "kalshi_quote_age_ms": row["kalshi_quote_age_ms"],
        "odds_age_ms": row["odds_age_ms"],
        "depth_at_ask": row["depth_at_ask"],
        "suppressed_reason": row["suppressed_reason"],
        "reason_text": row["reason_text"],
        "clv_tenths": row["clv_tenths"],
        # **Which anchor produced `clv_tenths`, carried rather than inferred.**
        #
        # `clv_tenths` is a bare number and nothing else in this payload says
        # what it was measured against, so without this a consumer counting
        # scored rows silently pools the current 0.0h anchor with the legacy
        # 1.0h one that migration v5 tags and deliberately never re-scores.
        # That mixture is not neutral: a 1h line is a weaker benchmark (a market
        # sharpens as the event approaches -- `analysis/clv.py`), so pooling
        # biases any resulting number in the **flattering** direction. It is
        # exactly how a reconnaissance pass counted 743 scored rows against the
        # 476 the gate reports at the primary horizon.
        #
        # `None` means unscored, and is distinct from any horizon value --
        # including 0.0, which is a legitimate anchor and must never be tested
        # for truthiness.
        "clv_horizon_hours": row["clv_horizon_hours"],
        # -- what it costs, and what it costs you when it loses ---------------
        #
        # The card showed `COST` as stake alone and `FEE` beside it with no
        # total anywhere, which understates what leaves the account by 3.6% at
        # 50c and 10% at 10c. Computed here and not in the browser: the fee
        # curve is an unresolved hedge between two disagreeing sources, and a
        # second implementation of it in TypeScript would be two money
        # calculations one refresh apart.
        "stake_dollars": stake,
        "total_cost_dollars": stake + fee,
        "sd_dollars": sd,
        # How often a run of `LOSING_RUN_BETS` bets this shape ends down, if the
        # edge is entirely real. The answer on the demo's best row is 46%, and
        # that is the number a beginner does not supply from memory: without it
        # a losing week reads as a broken tool or an invitation to double up.
        "losing_run_bets": LOSING_RUN_BETS,
        "losing_run_probability": _losing_run_probability(
            row["ev_net_dollars"], sd
        ),
    }
