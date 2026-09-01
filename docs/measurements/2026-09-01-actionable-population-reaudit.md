# RE-AUDIT — the actionable population, on the gate's own predicate

**Taken 2026-09-01 on live `228f716`.** Decision map ticket #14: `CLAUDE.md`
led with a figure dated 2026-08-23 while the live instance had moved. Read
with `inspect_live_db actionable-audit`, whose section A is the gate's own
predicate — `r.suppressed_reason IS NULL AND r.reference_contracts > 0`,
`backend/gate.py:330`.

## The figure

    rows                        51        (was 11 on 2026-08-23)
    distinct games              15        (was 6)
    rows with suggested > 0      0        (was 0)
    reference_contracts      1 - 50
    window        2026-08-15T19:52:14Z .. 2026-08-31T22:13:59Z

The oldest row is unchanged from the 2026-08-23 audit, so this is the same
population grown, not a different one.

## The parts, because a pooled number is not a finding until they agree

    11  KXWNBAGAME-26AUG25WSHPHX      21.6% of all rows
    10  KXWNBAGAME-26AUG23LVTOR
     4  KXMLBGAME-26SEP011845SEABOS
     4  KXMLBGAME-26AUG311845MIAWSH
     4  KXMLBGAME-26AUG282015PITSTL
     3  KXWNBAGAME-26AUG20INDDAL
     2  KXMLBGAME-26AUG312140PHIAZ
     2  KXNCAAFGAME-26SEP07SMUFSU

**Two WNBA games carry 21 of 51 rows — 41%.** 51 rows is not 51 observations;
the row count moves with how often the recorder re-evaluated the same market,
which is why the game count is the one to quote.

## The three quantities, named

The ticket's real complaint. Three different numbers circulate under the word
"actionable" and lanes have conflated all three:

1. **This audit's row count (51)** — rows ever written where the gate's
   predicate holds. A *row* count over the whole record.
2. **The Gate screen's game count (15)** — distinct games among those rows.
   This is the one the gate's 300-game floor is measured against.
3. **`slate.actionable_total`** (`backend/api/routes.py`) — a lifetime row
   count where `suppressed_reason IS NULL AND reference_contracts > 0`, served
   to the slate.

(1) and (3) are close relatives; (2) is a different unit entirely. A sentence
that says "actionable is N" without saying which of the three is unreadable.

## What has not changed, and it is the part that matters

- **`suggested_contracts = 0` on all 51.** Every row is evidence at the fixed
  $1,000 reference profile (ADR 0015 §3) and **unbuyable at the deployed
  bankroll**. None was ever rendered as a card.
- **15 games against the registered floor of 300.**
- **The actionable predicate still carries no multiplicity correction**, while
  the runner re-evaluates ~100 candidates every 900s against a growing record.

Every `reason_text` in the population ends "No edge." The rows are actionable
in the predicate's sense — not suppressed, priced against a reference
bankroll — and carry no edge after fees.

## Verdict

**Unchanged: treat 15 as unseparated from zero.** The count grew because the
recorder kept running, not because anything was found. The 2026-08-23 audit's
conclusion stands with a larger denominator behind it.

## What this does not establish

- **Anything about whether the rows are right.** The predicate says not
  suppressed and sized at a reference bankroll; it says nothing about whether
  the fair value is correct. ADR 0021's `beta = -0.141` bears on that and is
  negative.
- **The sharp-anchoring split.** The 2026-08-16 audit named a measurement
  nobody has run: split the *unsuppressed* population by `anchored_on_sharp`
  and report the `edge_tenths > 0` rate in each, clustered per game. Still not
  run; this audit did not run it either.
- **That the count will keep growing at this rate.** It spans a WNBA season
  ending and NCAAF starting.
