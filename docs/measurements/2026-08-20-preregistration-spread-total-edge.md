# Pre-registration — the spread/total falsification test (fleet convening item 8)

Written 2026-08-20 ~17:45Z, before the sweep it registers. The convening's
decision: *"buy ONE `spreads,totals` sweep on one MLB slate. 4 credits. If the
fee-net edge is centred at or below zero — as h2h is — it dies for 4 credits
and no blocker gets written."* This file fixes how that sentence is scored
before anyone sees a number.

## 0. Declared contaminations, in full

- I have seen `docs/measurements/2026-08-09-halfspread-dispersion.md`'s cell
  showing KXMLBSPREAD at 5.0 tenths half-spread inside 720 minutes of kickoff,
  and the convening's read of 1.0c median width at 13,517 median ask depth,
  15/15 games sharp-quoted at a Kalshi-listed line. Those are venue-side facts
  about *tradability*; none is an edge number, and no fee-net edge against a
  devigged consensus has ever been computed on this venue's spread markets by
  this repo. The decision statistic below has never been seen.
- I captured `tests/fixtures/series_fee_fields.json` today: `fee_multiplier`
  0.5 on KXMLBGAME/KXMLBSPREAD, 1 on KXATPDOUBLES/KXWNBAGAME, verified by
  predicting all 11 attributed fills to $0.0001. The charged-fee arm below
  uses it. This is a fact about fees, not about edges.
- The h2h verdict (`beta = -0.141`, ADR 0021/0034) is known and is the prior:
  the expected outcome of this test is REFUTED.

## 1. The question

Does a devigged multi-book consensus on MLB **spread and total** lines,
matched to Kalshi markets at the **exact same line**, show a positive fee-net
edge against Kalshi's derived ask — at the fee the venue actually charges?

## 2. The claims, stated so they can come back false

- **C1 (the edge claim under test):** the median fee-net edge on
  sharp-anchored rows is > 0 at the charged fee. Expected FALSE.
- **C2 (the overlap premise):** at least one book quotes both sides of a line
  Kalshi lists, for at least half the matched games. If C2 fails, the test is
  NOT a refutation of C1 — it is a finding that the comparison cannot be made,
  reported as NO-OVERLAP.

## 3. The population, the unit, and the cut

- **One sweep**, `markets=spreads,totals`, `regions=us,eu` (4 credits), for
  `baseball_mlb`, taken **inside the next `baseball_mlb` window that opens
  after this file is committed**, at least 15 minutes before the earliest
  stored commence of that slate. One look; no re-sweep on a thin result.
- **Kalshi side:** every `KXMLBSPREAD` and `KXMLBTOTAL` market whose event is
  in that slate and not yet commenced, book read via REST within 5 minutes of
  the odds sweep. If either series does not exist or lists nothing, that is
  reported, not skipped.
- **The unit of independence is the game.** Rows (market × side) cluster by
  game and the per-game view prints beside every aggregate.
- **Nothing is written to any production table.** Raw payloads are saved as
  files; the runner, linker, and odds store are untouched. This is the
  engineering-safety condition of the convening and it is part of the
  registration.

## 4. Matching — exact, refusing, and counted

The blocker the convening called dangerous is silent line-mixing: books at
−1.0 pooling with books at −1.5 moves a devigged probability by 2–4× the fee
bar. Therefore:

- A book's quote joins a Kalshi market only on **exact line equality**
  (`outcome_point == strike`, no tolerance, no conversion beyond sign
  convention), and — for spreads — on the **same team**, resolved through the
  repo's own alias normalisation. Any row whose team or sign convention
  cannot be resolved without guessing is **excluded and counted**, never
  approximated.
- A book contributes only if it quotes **both sides at that same line**
  (a one-sided quote cannot be devigged).
- A Kalshi row with fewer than 2 contributing books is excluded and counted.

## 5. The statistic

Per contributing book: implied probabilities from the two-sided pair at the
matched line → all four devig methods (`core/devig.py`, the production code)
→ per-book fair for the Kalshi YES outcome = the **minimum across methods**
(worst-of-four, rule 2). Consensus fair = **median across books**. Then

    fee_net_edge_tenths = 1000·fair − (derived_ask_tenths + fee_tenths)

with `fee_tenths` at C = 1 taker from `ceil(k·P(1−P))` on the $0.0001 grid:

- **decision arm:** k = 0.07 × 0.5 = **0.035** (the charged fee on MLB
  series, fixture-verified today);
- **sensitivity arm:** k = **0.07** (the deployed conservative bar), reported
  beside it, never deciding.

A row is **sharp-anchored** if Pinnacle contributes at that exact line. The
distribution is reported split by this flag; the decision reads the
sharp-anchored rows, because unanchored h2h rows are already known to
manufacture apparent edge (ADR 0021).

## 6. The decision rule, and the floor before the effect

Read `n` first: fewer than **8 sharp-anchored rows** or fewer than **3
distinct games** ⇒ verdict **UNDERPOWERED** — no pass, no fail, and the
quadrant row is unchanged. Otherwise:

- median fee-net edge (sharp-anchored, charged fee) **≤ 0** ⇒ **REFUTED**:
  the quadrant stays closed, the four blockers stay unwritten, and the row in
  CLAUDE.md's table gains this measurement as its citation.
- median **> 0** ⇒ **NOT REFUTED** — which opens nothing and changes no code:
  it buys exactly one thing, a second registered look with a real sample-size
  target, and any reopening still needs to name the ADR 0038 row it overturns.

Spreads and totals are **reported separately and decided separately** (two
looks, declared now). A pooled number may be printed only beside its parts.

## 7. What would falsify the setup rather than the claim

- No window opens, or the slate empties: UNTAKEN, retry next slate, no cost.
- C2 fails (no exact-line overlap): NO-OVERLAP, a real finding about the
  join, and C1 is untested.
- The books' spread points systematically miss Kalshi's listed lines by 0.5:
  same as C2, and worth recording as its own fact.

## 8. What this does not establish

- Nothing about CLV: no closing lines are read and no signal-test cluster is
  touched — the G-counter and `clv_signal.py`'s cluster key are unaffected,
  which is the fourth blocker deliberately left unbuilt.
- Nothing about execution: depth and width are reported as context, not
  modelled.
- Nothing about any sport but MLB, or any date but this slate.
- A REFUTED verdict here does not strengthen the h2h refutation; it extends
  the same conclusion to a market type at the venue's better prices, which is
  exactly why it is worth 4 credits.
