# Result — `last_update` is not a per-line reprice timestamp

**Registration:** `docs/measurements/2026-08-10-preregistration-odds-last-update-repeat-poll.md`,
including **Amendment A** and **Amendment B**. The registration was fixed
before any poll was fired; nothing below chose a rule after seeing a number.

**Captured:** 2026-08-11, `T0 = 18:00:01Z`, four polls at `T0 + {0, 60, 300,
900}` s, complete at 18:15:02Z. 24 credits, spent once. Fired by a Windows
scheduled task decoupled from any session, so that no session's death could
either lose the window or fire it twice.

**Artefacts:** `docs/measurements/data/repeat_poll_20260811T180001Z_p{1,2,3,4}.json`,
committed (force-added past `.gitignore:33`) because the spend is not
repeatable — the window closed at 22:00Z and 2026-08-12 was too thin all day.

**Audited by `measurement-skeptic` before entering the record.** Verdict
**SURVIVES NARROWED**. The narrowings are §4 and §5 below and are part of the
result, not commentary on it.

---

## 1. The verdict

**CONFIRMED — `last_update` is NOT a per-line reprice timestamp.**

`S = 0.9376` over `N_adv = 31` books, at the pre-registered primary pair
**poll 1 → poll 3** (~300 s), with PC1–PC6 all met.

**The mandatory qualifier (§7, `S_strict = 0.2903 < 0.90`), in the words the
registration fixed in advance:**

> the confirmation rests on pair-level identity; the stamp is book-scoped, so a
> reprice on another game in the same slate cannot be excluded as the cause of
> the advance.

**ADR 0020 is therefore restricted to the claim that `odds_age_ms` is not a
per-line freshness measure.**

This wording is not a hedge added afterwards. §7 `:690-695` fixed both legs
before the capture, and the leg that fired is the one quoted. **Amendment B's
paragraph is NOT licensed here** — it applies only at `S_strict >= 0.90`, and
it asserts *"No price change was observed anywhere in the captured slate
between poll 1 and poll 4"*, which is **false in this capture**: 22 of 31 books
moved a price over that span. A first reading of this result had the two legs
the wrong way round and would have published that sentence.

**Amendment B §B3's registered arithmetic came true.** It predicted the
`>= 0.90` leg is unreachable when `N_adv = n_books` and `n_books < 50`.
Observed `N_adv = n_books = 31`: three movers tolerated inside, zero available
outside, against PC5's `>= 5`. **The strong-wording leg had no opportunity to
fire.** That was written down before poll 1, and it is why the qualifier is not
a disappointment.

## 2. The cells

| | | |
|---|---:|---|
| A advanced & identical | **436** | confirming |
| B advanced & changed | **29** | refuting |
| C static & identical | 0 | uninformative |
| D static & changed | 0 | defect cell |
| BOTH | 465 | = 15 events × 31 books |

`R = 465/465 = 1.0000` — every pair's stamp advanced. Attrition, `regressed`,
`KEY-DEGENERATE`, `TEXT_FLOAT_MISMATCH` and `NO-STAMP` were all zero.

**`D = 0` and `regressed = 0` were forced, not observed.** `advanced` held on
all 465 pairs, so the static row of the 2×2 was arithmetically empty. **They
must not be quoted as "no reprice-without-advance was found."** `NO-STAMP = 0`
*is* observed: zero market objects and zero bookmaker objects lacked
`last_update` in the raw payload.

## 3. The rival, priced before the number (ADR 0026)

§5.1's rival — a genuinely busy slate repricing most pairs inside 300 s — needs
a reprice rate `>= 80%`. **Observed: `(B + D) / BOTH = 29/465 = 0.0624`.** The
rival is not in play.

**The branch that fired coincides with a different rival, and this is named
rather than hidden:** a *book-scoped* reprice stamp predicts high `S` exactly as
the scrape-clock reading does. ADR 0026's table marks that pair as
**non-discriminating**. §7's mandatory qualifier exists for precisely this, and
it fired. The rival is not hypothetical here: in poll 1, **30 of 31 books carry
exactly one distinct `last_update` across the whole 15-game slate**, and every
one of the 465 (book, event) pairs carries a single distinct stamp. The stamp is
book-scoped in this data, and the qualifier-restricted claim is the only one
supported.

## 4. The second horizon — and it does not come out the same way

CLAUDE.md requires every measurement to re-run at a second horizon. This one
must be read with the result, not after it.

**All six pairs, not a chosen subset:**

| pair | Δ | A | B | reprice rate | `S` | |
|---|---:|---:|---:|---:|---:|---|
| 1→2 | 60 s | 297 | 3 | 0.0065 | 0.9900 | 165 pairs still static |
| 2→3 | 240 s | 439 | 26 | 0.0559 | 0.9441 | |
| **1→3** | **300 s** | **436** | **29** | **0.0624** | **0.9376** | **decides — CONFIRMED** |
| 3→4 | 600 s | 423 | 42 | 0.0903 | 0.9097 | |
| 2→4 | 840 s | 415 | 50 | 0.1075 | 0.8925 | mid-band |
| **1→4** | **900 s** | **412** | **53** | **0.1140** | **0.8860** | **mid-band — UNRESOLVED** |

At 60 s, **64.5% of pairs had advanced while 0.65% had repriced** — a ~99:1
decoupling, and §4 of the registration named that flat-advance / rising-change
signature in advance. It is why the qualifier-restricted claim reads as
mechanism rather than luck.

**At 900 s — which is the deployed `MAX_ODDS_AGE_S` — `S = 0.8860` and the
instrument declares nothing.** No rule was broken: the primary pair was fixed
by index at `analyse_odds_repeat_poll.py:162` before the data, PC2 passed, so
the fallback correctly never fired, and §5.2 forbids selecting a pair by
realised interval. §5.1 predicted this drain in advance and the data did exactly
what it said.

**Consequence for how this may be cited: the CONFIRMED verdict is a statement
about the ~300 s interval and must never be written interval-free.** The
descriptive rows above are ~65 cells with no standard errors anywhere; they
explain the shape, they do not declare.

## 5. What this does not establish

- **Not** any other league, sport, region, market, day, time of day, or
  aggregator. One MLB slate, 15 minutes, one day, 31 books, `us`+`eu`.
- **Not** in-play (ADR 0006), which §2 excludes by construction.
- **Not** "the odds are stale", and **not** anything about our polling cadence.
- **Not** edge, calibration, or `actionable`. **This result does not move
  `actionable` from 0 to 23.** ADR 0025 already showed the mechanism inverts: a
  scrape clock makes `odds_age_ms` a *lower* bound on true line age, so every
  rejection remains correct under either reading and the defect contaminates the
  **clean** set instead. What changes is what ADR 0020 may claim, not what the
  gate surfaces.
- **Not** a licence for the phrase "the strong wording", which Amendment B
  retired as defined nowhere.
- **Not** evidence of integrity from `D = 0`. See §2.

## 6. `S` is a pooled proportion on this data, and saying otherwise would flatter it

`S` is a bookmaker-clustered mean of within-book shares. Here **every one of the
31 books has exactly 15 pairs** — coverage was complete and every pair advanced
— and with equal cluster sizes the unweighted mean of within-cluster shares is
*algebraically* the pooled ratio. `S` and pooled `A/(A+B)` agree to the last
float bit (`0.9376344086021507` vs `...05`).

**Do not cite "bookmaker-clustered" as if it had downweighted a dominant book.**
The clustering is real code doing real work; it had nothing to reweight. The
registered protection is intact but unexercised.

The parts do agree. Every book contributes exactly 15 pairs (**cluster sizes
verified equal**), largest contributor 15/465 = 3.2%, and dropping any single
book leaves `S` in **0.9356–0.9489**. Per-book shares run 0.6000 (`nordicbet`)
to 1.0000 (13 books).

**§2's refusal to exclude the exchanges held under its own test.** `matchbook`
is the second-worst book at 0.6667 and `betfair_ex_eu` sits at 0.9333, both
below `S`; they were retained, and dropping either would have raised the
statistic in the hypothesis's favour.

> **A correction that the record keeps rather than smooths.** The audit's prose
> called `matchbook` and `betfair_ex_eu` *"the two worst"*, and a first draft of
> this section repeated it. It is wrong, and the audit's own per-book table
> already showed it wrong. Re-derived here through the analyser's own
> `compare()` and `statistic_s()`: the worst book is **`nordicbet` at 0.6000,
> which is not an exchange**, and `betfair_ex_eu` at 0.9333 is mid-pack — 14
> books sit at that value. The load-bearing claim (the exchanges were kept, and
> keeping them cost the hypothesis) survives; the ranking did not. **Every
> number in §4 and §6 was recomputed from the artefacts before being written
> here, because this repo has been burned by a delegated figure that was
> confident, load-bearing and wrong.**

The margin is thin in absolute terms: moving 18 of 465 pairs (3.9%) from A to B
takes `S` to 0.8989 and the verdict to UNRESOLVED.

## 7. Three defects in the instrument, found by the audit and repaired at `12ecc03`

None changed the verdict — the analyser was re-run on the same four artefacts
after every repair and printed `S = 0.9376`, `A = 436`, `B = 29`, PC1–PC6 PASS.

1. **PC6 checked a number we wrote ourselves.** It summed `cost_credits`, a
   constant the capture script writes into each artefact, while the module
   docstring advertised it as asking *"the server's own credit delta precisely
   because the rest of this script would compute a clean `S` over four copies of
   one poll"*. **Four copies of one poll would have passed it.** It now reads
   `x_requests_used`: 114 → 138 = 24. The registered clause did hold on this
   capture — **but it held because an auditor checked it by hand.**
2. **The test fixture wrote the same `x_requests_used` to all four polls**, so
   every fixture in the file was, in credit terms, four copies of one poll. The
   new PC6 fails it, which is how it was found.
3. **§2's in-play exclusion was never implemented.** It was vacuous on this
   slate — earliest first pitch 266 minutes after poll 4 — so nothing was
   wrongly included. **A vacuous exclusion and an absent one print identically
   unless the count prints either way.** It does now, and an unreadable
   `commence_time` refuses rather than silently including the event.

**And the thirteenth guard that could not fail.** PC4's `cell_d` conjunct was
decoration: deleting it left all 43 tests green. Six counters — `D`, `C`,
`regressed`, `ABSENT-1`, `ABSENT-2`, `ROWSET-CHANGED` — read exactly zero here
and **no test drove any of them**. Each now has one; the suite is 56 tests and
six mutations were seen red, including that one.

## 8. What this instrument cannot be asked again

§8 forbids buying more of the same design without a new registration, and the
reason is in the arithmetic rather than the budget: **more credits buy
correlated copies, not precision.** The `advanced` bit is entirely
book-determined — one stamp per book across the slate — so `R = 465/465` is
`31/31` restated fifteen times, and if one scrape process serves every book the
effective `n` is 1. §10 registered that before the run.

**A mid-band `S` at 900 s is therefore permanently unresolvable by this
design.** Re-running it on another slate would answer a different question about
a different slate, not sharpen this one.

## 9. What is owed next

- **ADR 0020** may now be written, restricted as §1 requires. It is the direct
  consumer of this result.
- The **OPERATIONAL COROLLARY** (31/31 books advance inside the deployed 900 s
  window) is a count and carries no alpha. Nothing consumes it today —
  `n_adv900` appears only in the analyser, its tests, and the registration. Note
  it is **not independent**: given every book advanced by 300 s with
  `regressed = 0`, its `>= 0.90` branch was forced by the primary result.
