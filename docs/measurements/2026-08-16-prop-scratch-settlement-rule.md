# Kalshi settles a scratched player prop at *fair market price* — not YES, not NO, not a refund

**Source:** `rules_secondary` on live market payloads, captured in
`tests/fixtures/events_mlb_props_nested.json`. Venue-authored text, read
verbatim.
**Asked because:** `sharp-bettor` flagged this as potentially fatal to the
prop-model plan and worth fifteen minutes before writing any code — if Kalshi
settled a scratch **NO**, every book-derived comparison on props would be wrong
at the root, since sportsbooks **void**.
**Answer:** it is neither, and the plan survives.

## The rule, verbatim

`KXMLBKS` (pitcher strikeouts):

> **Player Participation & Settlement Criteria**
> If Anthony Kay is scratched or is not a starting pitcher, the market will
> resolve to the fair market price.
> If Anthony Kay is not a starting pitcher but later enters the game, the market
> will resolve to the fair market price, relief appearances will not count
> towards this market.
> If Anthony Kay is a starting pitcher and records at least one pitch the market
> will settle based on strikeouts recorded.

`KXMLBTB` (total bases) is the same shape with the batter's conditions:

> If Andrew Benintendi is scratched or not included in the starting lineup, the
> market will resolve to the fair market price.
> If Andrew Benintendi starts the game but does not record a plate appearance,
> the market will resolve to the fair market price.
> If Andrew Benintendi is not in the starting lineup but later enters the game,
> the market will resolve to the fair market price, pinch hit at bats will not
> count towards the market.
> If Andrew Benintendi is in the starting lineup and records at least one plate
> appearance the market will settle based on total bases recorded.

Two of the five series read; both agree. `rules_primary` carries **none** of
this — it is the bare "if X records N+, resolves Yes" sentence, and reading only
that field implies a NO settlement on a scratch. **The participation rule lives
in `rules_secondary` and nothing in this repo reads that field.**

## What it means, and what it does not

**It does not settle NO.** The failure the check was run to rule out is ruled
out. A pre-lineup Kalshi prop price is therefore a probability **conditional on
the player starting**, which is the same conditioning a sportsbook's voided prop
carries. Book-derived comparison on props is not broken at the root.

**It is not a void either, and the difference is real but small.** A book's void
returns your stake — you exit at the price you paid. Kalshi marks you out at
"fair market price", so you exit at whatever the market says at settlement. If
the market moved against you between entry and the scratch, you lose that
movement. So Kalshi's handling is *slightly worse for the bettor* than a void,
and it introduces a **discretionary term**: nothing in the rules text defines
how "fair market price" is determined, or at what instant.

**It shrinks one input to the lineup-driven plan and leaves the rest.** The
largest lineup-driven effect — the player is out entirely — is neutralised by
the venue, so it cannot be an edge. What survives is the effect the plan was
actually built on: the **batting-order slot**, worth roughly half a plate
appearance between second and seventh, which the rule does not touch. The
pitcher series gains a condition worth noting — a starter pulled early still
settles on strikeouts recorded, because he recorded at least one pitch.

## Two consequences for code that already exists

1. **`backend/agents/scout.py:48` and `backend/agents/skeptic.py:14,52` both
   treat "was the starting pitcher scratched" as a live risk to suppress on.**
   On these five prop series the venue already handles it. That does not make
   the prompts wrong — they were written for game markets, where a scratch moves
   the line and nothing refunds you — but it means the reason must not be
   applied to props without saying which market type it is about. Neither agent
   has a production caller (ADR 0022), so nothing is currently misfiring.
2. **`rules_secondary` is not captured anywhere in `backend/kalshi/`.** The
   field is present on the wire and in the fixture. Any future settlement or
   fee reconciliation on props needs it, and reading `rules_primary` alone gives
   the *opposite* answer to the truth.

## What this does not establish

- **Three of the five series are unread.** `KXMLBHIT`, `KXMLBHR` and `KXMLBRBI`
  were not in the fixture with `rules_secondary` populated. Two agreeing is not
  five.
- **It is a fixture, not a live read.** Rules text is venue-authored and stable
  per series, but this was captured earlier and has not been re-fetched.
- **Nothing about how "fair market price" is computed.** No instant, no method,
  no source is stated in the rules text. That is an open question and it is the
  part with money in it — a discretionary settlement is a term you cannot model.
- **Nothing about non-MLB props**, or about whether game markets carry a
  comparable participation clause.
- **Nothing about frequency.** How often a scratch actually happens on a market
  this tool would have quoted is unmeasured.
