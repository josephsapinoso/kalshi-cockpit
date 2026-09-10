"""The wire shapes the cockpit accepts: every request model the routes read.

Moved here verbatim on 2026-09-04 from `backend/api/routes.py`, which had
grown to 333,958 bytes -- past the 262,144-byte ceiling at which the Read tool
refuses a file outright, so no session could open it
(`tests/test_session_files_are_readable.py`; the plan is
`docs/decisions/2026-09-04-routes-split-map.md`). Nothing in a model changed
in the move, and `routes.py` imports every name back, so each handler
signature is exactly what it was.

The docstrings on the models are the contract, and several of them
(`OrderPlacementRequest`, `ManualOrderRequest`, `ComboBidRequest`) explain
why a field is REQUIRED rather than optional. That reasoning is the security
boundary `routes.py`'s own docstring names -- never trust that the UI
disabled a button -- so a model here is not a convenience type; it is the
first of the server-side checks.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from ..core.correlation import Leg
from ..parlays import DEFAULT_HORIZON, HORIZONS


class OrderPlacementRequest(BaseModel):
    """What the ticket sends. Deliberately minimal.

    The client names a recommendation and a size; it does not send a price, a
    ticker or a side. Everything that determines what is actually bought is
    read server-side from the recommendation, so a tampered or stale client
    cannot buy a different market or a better price than the one recorded.
    """

    recommendation_id: int
    contracts: int = Field(gt=0, le=10_000)
    # **Required, not optional, and that is the decision.** An optional
    # idempotency key is a guard that fires only when the client remembers it,
    # which is the shape of a check that cannot fail. Making it required is what
    # turns "two taps are two orders" from a property of the client into a
    # property of the endpoint.
    #
    # The charset is restricted because this string is a database key and is
    # echoed in refusals; a UUID from `crypto.randomUUID()` satisfies it, and so
    # does anything a script would reasonably generate.
    idempotency_key: str = Field(
        min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )


class DeskPassRequest(BaseModel):
    """One per-market pass: "I looked at this and chose not to bet it."

    `reason` is optional and stays optional (slice B6): a required reason is
    a toll on the correct boring action. The length caps are hygiene on a
    string that will be rendered back, not validation of the decision --
    a pass needs no justifying.
    """

    ticker: str = Field(min_length=1, max_length=80)
    reason: Optional[str] = Field(default=None, max_length=500)


class DeskAttentionRequest(BaseModel):
    """The heartbeat's optional body: which screen was open (v34).

    Every field here is **recorded and never acted on**. The sweep trigger
    reads `last_seen_ms` and the TTL; nothing in `odds/timing.py` may branch on
    anything in this model. That is why a body is acceptable on a route whose
    docstring long argued it should take none -- that argument was about a
    client-supplied *timestamp*, which is acted on, and the clock is still the
    server's.

    `max_length` is hygiene on a string that will be read back by a human, not
    validation: `attention.normalise_path` strips a query string, refuses an
    empty one to NULL, and truncates. The cap here is the outer bound so an
    oversized body is refused at the edge rather than silently shortened.
    """

    path: Optional[str] = Field(default=None, max_length=200)


class ManualOrderRequest(BaseModel):
    """What the manual ticket sends (ADR 0063). Everything is re-validated
    server-side; the one number the client DOES author — the price ceiling —
    is the one the design requires it to author.

    `max_price_tenths` is a ceiling, never a target: the order is refused
    when the live ask exceeds it, and the limit actually sent is the ask
    (bounded by this), snapped to the market's own grid.

    **`p_yes_bp` was removed 2026-09-09** (ADR 0131, superseding ADR 0065 §2)
    on Joe's instruction: the field was friction, and the consumer ADR 0065
    named to justify it was never built. The COLUMN survives, nullable, and
    the rows written while it was required keep their real values. A body that
    still carries the key is not refused — Pydantic ignores an extra field —
    but nothing reads it and nothing is written; a stale client records NULL,
    which is the truth about a number this server no longer asked for.
    """

    ticker: str = Field(min_length=1, max_length=80)
    side: str = Field(pattern=r"^(yes|no)$")
    # Wide enough that the SERVER's ceilings decide, not this schema. A
    # market at a tenth of a cent turns $3 into thousands of contracts, and a
    # schema bound tighter than `MANUAL_ORDER_MAX_CONTRACTS` would refuse with
    # a validation error instead of the named reason the route gives.
    contracts: int = Field(gt=0, le=1_000)
    max_price_tenths: int = Field(ge=1, le=999)
    idempotency_key: str = Field(
        min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )
    #: Required, and only meaningful, on a `KXMVE` combination ticker
    #: (ADR 0073). A FIELD rather than a client-side checkbox: the whole
    #: point is that the acknowledgement cannot be skipped by a client that
    #: forgets to render it, and a default of False means a client that has
    #: never heard of combos refuses them rather than buying one silently.
    combo_acknowledged: bool = False


class OddsRefreshRequest(BaseModel):
    """What the refresh button sends: a sport, and optionally one fixture.

    Both are validated against `odds_snapshots` in the handler rather than
    trusted, because this is the one authenticated route whose whole purpose is
    to spend money at a third party. A sport key that reaches `fetch_odds`
    unchecked is a paid request for a slate that does not exist.

    `odds_event_id` is what makes the request expensive -- the props endpoint is
    billed per event per market key per region, so naming a fixture turns a
    6-credit tap into a 26-credit one. It is one fixture, never a list: a list
    is how a tap becomes the 384-credit pass of 2026-08-15, and a person
    refreshing a screen is looking at one game.
    """

    sport_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    odds_event_id: Optional[str] = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )


class EstimateRequest(BaseModel):
    """What the bet-estimate form sends: §9.2's two typed fields plus the tap.

    `stated_probability_bp` is P(YES), always -- never "probability my side
    wins". The bounds mirror the schema CHECK so a bad value is refused with a
    422 the phone can render instead of an IntegrityError it cannot.
    """

    ticker: str = Field(min_length=1, max_length=80)
    stated_probability_bp: int = Field(ge=1, le=9999)
    # REQUIRED at the API, not just enforced by the form's disabled input.
    # "Never trust that the UI disabled a button" is this repo's own rule, and
    # the question must be answered BEFORE the number exists (§9.2) -- a
    # payload arriving without it answered is a payload that skipped the
    # ordering the study depends on. The schema column stays nullable because
    # §9.4 reserves the right to cut the field entirely.
    had_already_opened_kalshi: int = Field(ge=0, le=1)
    estimate_client_ms: Optional[int] = None


class EstimateRevisionRequest(BaseModel):
    """§7.4's correction path: a reason, and nothing editable."""

    reason: str = Field(min_length=1, max_length=500)


class LegRequest(BaseModel):
    """One leg of a combination, as the Builder screen sends it."""

    label: str
    probability: float = Field(gt=0.0, lt=1.0)
    event_key: str
    league: str
    commence_ms: int

    def to_leg(self) -> Leg:
        return Leg(
            label=self.label,
            probability=self.probability,
            event_key=self.event_key,
            league=self.league,
            commence_ms=self.commence_ms,
        )


class CorrelationOverride(BaseModel):
    """A measured correlation for one specific pair.

    The only sanctioned way to price same-game legs. It is a required, explicit
    act by the caller rather than a default, because the sign varies by pair and
    a plausible guess here is worse than no number at all.
    """

    a: str
    b: str
    rho: float = Field(ge=-1.0, le=1.0)


class ParlayRequest(BaseModel):
    legs: list[LegRequest] = Field(min_length=2)
    offered_american: int
    correlation_overrides: list[CorrelationOverride] = Field(default_factory=list)
    kalshi_contracts_per_leg: int = Field(default=100, gt=0, le=1000)

    def overrides(self) -> Optional[dict[tuple[str, str], float]]:
        if not self.correlation_overrides:
            return None
        return {(o.a, o.b): o.rho for o in self.correlation_overrides}


class ParlayLookupLeg(BaseModel):
    event_ticker: str
    market_ticker: str


class ComboBidRequest(BaseModel):
    """One resting bid on a card's combination (ADR 0084).

    **`price_tenths` is Joe's own number and is never re-priced.** A
    combination book has no offer to hit -- 40 of 40 books this repo has read
    carried no resting YES bid -- so this order becomes the offer, and the
    price it rests at is a choice rather than a quote. The server snaps it to
    the venue's grid and refuses anything the grid cannot express; it does not
    move it towards fair value in either direction.

    `acknowledgement` is typed through before the confirm unlocks, the same
    friction the hand-bet ticket carries (ADR 0073): this is the first order
    shape in the repo that can fill while nobody is watching.
    """

    card_key: str
    legs: list[ParlayLookupLeg] = Field(min_length=2)
    #: Tenths of a cent, the project's unit everywhere in the risk path.
    price_tenths: int = Field(gt=0, lt=1000)
    #: What he is willing to commit if the whole bid is taken, in cents.
    stake_cents: int = Field(gt=0, le=1000)
    #: The same field, the same default and the same reason as
    #: `ManualOrderRequest.combo_acknowledged`: a client that has never heard
    #: of combinations refuses one rather than resting a bid on it silently.
    #: Every bid this route can place is on a combination, so it is never
    #: optional here.
    combo_acknowledged: bool = False


class ComboBidCancelRequest(BaseModel):
    """Take one resting bid back. The row id, not the venue's order id.

    The desk's own id is the addressable one because the row exists before the
    request leaves: a bid whose create timed out has a row and no
    `kalshi_order_id`, and that is exactly the bid most in need of cancelling.
    """

    reason: str = "cancelled from the desk"


class ParlayLookupRequest(BaseModel):
    """One "Price on Kalshi" tap (ADR 0070).

    The legs are echoed back because they ARE the card the user saw, and a
    lookup mints a real market: the server re-checks each one against the
    current candidate pool (`resolve_requested_legs`) and prices the set the
    reader tapped. It does NOT require that the desk would still compose the
    same card -- that rule shipped until 2026-08-30 and made the button
    unusable whenever a quote pass landed between the render and the tap.

    **`horizon` travels with the tap, since 2026-09-10.** Until then the
    lookup priced every card at `tonight` regardless of which window built
    it, so a card built under "Through tomorrow" or "Next two nights" had
    every future leg refused by a lookup that never learned the window had
    moved -- item 0, `docs/adr/DRAFT-a-lookup-prices-the-window-the-card-
    was-built-in.md`. The client sends back `GET /api/parlays`'s own
    `window.key`, the same echo `WindowPicker` already renders, so the two
    calls agree by construction rather than by two callers remembering the
    same default.
    """

    card_key: str
    stake_cents: int = Field(default=500, gt=0, le=100_000)
    legs: list[ParlayLookupLeg] = Field(min_length=2)
    horizon: str = DEFAULT_HORIZON

    @field_validator("horizon")
    @classmethod
    def _known_horizon(cls, value: str) -> str:
        """The POST's own refusal, worded identically to the GET's.

        Two spellings of "unknown window" is how one of them drifts stale;
        `HORIZONS` is the single list both read from.
        """
        if value not in HORIZONS:
            raise ValueError(
                f"'{value}' is not a window this desk carries. "
                f"Choose one of: {', '.join(HORIZONS)}."
            )
        return value


class HeldLegRequest(BaseModel):
    """One leg of a ticket Joe already holds (ADR 0078).

    `ticker` is optional and that is the sportsbook case: a leg the venue does
    not list has no market to quote, no result to read and no hedge to buy. It
    is carried so the ticket's arithmetic is complete, and every surface says
    such a leg cannot be priced rather than treating an absent quote as a bad
    one.
    """

    ticker: Optional[str] = Field(default=None, max_length=80)
    side: str = Field(pattern="^(yes|no)$")
    label: str = Field(min_length=1, max_length=120)
    event_ticker: Optional[str] = Field(default=None, max_length=80)
    league: Optional[str] = Field(default=None, max_length=40)
    commence_ms: Optional[int] = None


class HeldPositionRequest(BaseModel):
    """A parlay Joe holds, in the figures the slip actually shows him.

    Money arrives in **cents**, because that is what a bet slip is denominated
    in and a form that asked for tenths of a cent would be answered wrongly.
    It is converted to tenths at this boundary, once, the way `RiskConfig`
    converts dollars.

    `return_cents` is the TOTAL returned on a win, stake included -- not "to
    win". The equalising hedge is exactly that many dollars of contracts, so
    the ambiguity would land straight in the size.
    """

    source: str = Field(pattern="^(kalshi_combo|sportsbook)$")
    label: str = Field(min_length=1, max_length=80)
    stake_cents: int = Field(gt=0, le=10_000_000)
    return_cents: int = Field(gt=0, le=10_000_000)
    legs: list[HeldLegRequest] = Field(min_length=1, max_length=20)
    book: Optional[str] = Field(default=None, max_length=40)
    placed_ms: Optional[int] = None
    combo_ticker: Optional[str] = Field(default=None, max_length=80)
    parlay_lookup_id: Optional[int] = None
    note: Optional[str] = Field(default=None, max_length=400)


class ResolveLegRequest(BaseModel):
    """Joe's word on a leg the venue cannot settle for him.

    `source` is fixed at `manual` by the route rather than accepted from the
    client: the venue path writes its own rows, and letting a request claim
    `venue` would put his word into the column that means the exchange said so.
    """

    outcome: str = Field(pattern="^(won|lost|void)$")


class ClosePositionRequest(BaseModel):
    status: str = Field(pattern="^(settled|closed|void)$")
