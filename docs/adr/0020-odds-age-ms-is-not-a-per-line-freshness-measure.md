# 0020 — `odds_age_ms` is not a per-line freshness measure, at ~300 s, and the interval the code ships is undecided

**Date:** 2026-08-12
**Status:** Accepted as a **statement of what `odds_age_ms` measures and of what
may be said about it**. It changes no code, moves no threshold, and authorises
no measurement or spend.
**Number:** 0020, the number reserved for this since ADR 0025. The reservation is
now spent; the repo's numbering runs 0019 → **0020** → 0021 → 0024 → 0025 →
0026 → 0027.
**Evidence:** `docs/measurements/2026-08-11-odds-last-update-repeat-poll-result.md`,
the direct consumer relationship its §9 names. That file is the source of every
number below and is the file to read before quoting any of them.
**Registration:** `docs/measurements/2026-08-10-preregistration-odds-last-update-repeat-poll.md`,
including Amendments A and B, fixed before any poll was fired.
**Does not touch** ADR 0021's refutation, ADR 0025's decision (`stale_odds` is
not removed, relaxed or re-tuned), the deployed `MAX_ODDS_AGE_S`, or the
`actionable` counter.

---

## 0. What this ADR is restricted to, and whose restriction that is

**It may claim only that `odds_age_ms` is not a per-line freshness measure.**

That restriction is not a caution added here. It is §1 of the result file, which
imposes it because the capture's `S_strict` was `0.2903`, below the `0.90` that
the registration required for any wider wording. The qualifier the registration
fixed in advance, quoted rather than paraphrased:

> the confirmation rests on pair-level identity; the stamp is book-scoped, so a
> reprice on another game in the same slate cannot be excluded as the cause of
> the advance.

Amendment B's paragraph is **not licensed here** and must not be reached for.
B1 applies only at `S_strict >= 0.90`, and its sentence — *"No price change was
observed anywhere in the captured slate between poll 1 and poll 4"* — is **false
in this capture**: 22 of 31 books moved a price over that span. A first reading
of the result had those two legs the wrong way round.

The phrase *"the strong wording"* was retired by Amendment B as defined nowhere.
Do not use it.

---

## 1. What was measured

Four polls of The Odds API at `T0 = 18:00:01Z` on 2026-08-11 and `T0 + {60, 300,
900}` s, one MLB slate, 15 events × 31 books = 465 (book, event) pairs, `us`+`eu`.
24 credits, spent once, fired by a scheduled task decoupled from any session.
Artefacts are committed at `docs/measurements/data/repeat_poll_20260811T180001Z_p{1,2,3,4}.json`
because the spend is not repeatable.

At the pre-registered primary pair **poll 1 → poll 3 (~300 s)**:

| | | |
|---|---:|---|
| A advanced & identical | **436** | confirming |
| B advanced & changed | **29** | refuting |
| C static & identical | 0 | uninformative |
| D static & changed | 0 | defect cell |

`S = 0.9376` over `N_adv = 31` books, PC1–PC6 all met, **CONFIRMED at that ~300 s
interval**. `R = 465/465 = 1.0000` — every pair's stamp advanced.

The shape underneath the statistic is the reason it reads as mechanism rather
than luck, and the registration named it in advance: at 60 s, **64.5% of pairs
had advanced while 0.65% had repriced**, a ~99:1 decoupling. Stamps move on a
schedule; prices do not.

Audited by `measurement-skeptic` before entering the record. Verdict **SURVIVES
NARROWED**; §§3–4 below are those narrowings, not commentary on them.

---

## 2. The decision

> **`odds_age_ms` measures how long since the aggregator last scraped the book,
> not how long since the line moved. The `stale_odds` guard is therefore named
> for a check it does not perform, and this is now measured rather than
> inferred.**
>
> **Nothing else changes.** `stale_odds` is not removed, relaxed or re-tuned;
> `MAX_ODDS_AGE_S` stays at 900; no threshold moves; no code is patched by this
> ADR. Any remedy is a separate decision needing its own registration.

The code already carries the corrected reading in prose. `backend/core/suppression.py:239-243`
says *"this measures **how long since the aggregator last polled the book**, not
how long since the line moved"*, and the guard's user-facing message at `:248-250`
already reads `book last scraped ...`, having been corrected from a `last moved`
wording that was false. Before this capture, that prose rested on a 320-of-320
observational census (ADR 0021 §7.5). **It now rests on an experiment with a
pre-registered decision rule.**

That upgrade — from inference to measurement — is the entire content of this
ADR. It is what ADR 0025 §3 called the load-bearing premise, and the premise is
now paid for.

---

## 3. The interval that decides is not the interval the code ships

This section is mandatory reading with §1 and may not be separated from it.

| pair | Δ | A | B | reprice rate | `S` | |
|---|---:|---:|---:|---:|---:|---|
| 1→2 | 60 s | 297 | 3 | 0.0065 | 0.9900 | 165 pairs still static |
| 2→3 | 240 s | 439 | 26 | 0.0559 | 0.9441 | |
| **1→3** | **300 s** | **436** | **29** | **0.0624** | **0.9376** | **decides — CONFIRMED** |
| 3→4 | 600 s | 423 | 42 | 0.0903 | 0.9097 | |
| 2→4 | 840 s | 415 | 50 | 0.1075 | 0.8925 | mid-band |
| **1→4** | **900 s** | **412** | **53** | **0.1140** | **0.8860** | **mid-band — UNRESOLVED** |

**900 s is `MAX_ODDS_AGE_S`** (`backend/config.py:406`, default 900, consumed as
`max_odds_age_ms` by the `stale_odds` check at `backend/core/suppression.py:244-252`).
**At that interval the instrument declares nothing.**

No rule was broken. The primary pair was fixed by index —
`PRIMARY_PAIR = (1, 3)  # §5.2, BY INDEX` at
`scripts/analyse_odds_repeat_poll.py:173` — before the data, PC2 passed, so the
fallback correctly never fired (`:581-582`), and §5.2 of the registration forbids
selecting a pair by realised interval. §5.1 predicted this drain in advance and
the data did exactly what it said.

> **Citation drift, re-verified rather than inherited.** The result file cites
> `:162` for this. `:162` is an import today; the constant is at `:173`. The
> claim is unaffected — `PRIMARY_PAIR = (1, 3)` is there and carries the `BY
> INDEX` comment — but the line number moved, most likely when the three §7
> repairs landed at `12ecc03`. This is the second citation drift the record has
> caught in a week (NEXT.md logs ADR 0021 §7.6's). Every line number in this ADR
> was opened and read on 2026-08-12, not copied.

**So the citation rule is:** the verdict is a statement about the ~300 s interval
and **may never be written interval-free**. An ADR, handoff or commit message
that recommends a remedy for the 900 s window while citing the 300 s verdict is
citing interval-free, which the result file forbids. The descriptive rows above
are ~65 cells with no standard errors anywhere; they explain the shape, they do
not declare.

**And this gap cannot be closed by buying more.** Result §8: the `advanced` bit
is entirely book-determined — one stamp per book across the slate — so
`R = 465/465` is `31/31` restated fifteen times, and if one scrape process serves
every book the effective `n` is 1. More credits buy correlated copies, not
precision. **A mid-band `S` at 900 s is permanently unresolvable by this design.**
Re-running on another slate answers a different question about a different slate.

---

## 4. Why this is not a runway, and the arithmetic is ADR 0025's

**This result does not move `actionable` from 0 to 23, and no session may read it
as licence to build a surfacing path.**

ADR 0025 §3 established the inversion before this capture existed: under a scrape
clock, `odds_age_ms` is a **lower bound** on true line age. A row rejected at 259
minutes carries price information *at least* 259 minutes old under **either**
candidate reading, so **the rejection is correct either way**. Only the opposite
semantics — `last_update` as a reprice timestamp, where an old stamp means a
confirmed-unmoved line — would make the 23 wrongly discarded, and that is the
reading this capture **refutes** at ~300 s.

The defect a scrape clock produces therefore contaminates the **clean**
population, not the discarded one: rows that pass `stale_odds` are not proven
fresh. That is ADR 0021 §7.5's *"the clean 323 carries unmeasured staleness"*.

**What changed is what may be claimed, not what the gate surfaces.**

---

## 5. What this does not establish

- **Not** any other league, sport, region, market, day, time of day, or
  aggregator. One MLB slate, 15 minutes, one day, 31 books, `us`+`eu`.
- **Not** in-play (ADR 0006), excluded by the registration's §2.
- **Not** *"the odds are stale"*, and **not** anything about our polling cadence.
- **Not** edge, calibration, or `actionable`.
- **Not** a finding from `D = 0` or `regressed = 0`. Both were **forced, not
  observed** — `advanced` held on all 465 pairs, so the static row of the 2×2 was
  arithmetically empty. They must not be quoted as *"no reprice-without-advance
  was found."* `NO-STAMP = 0` **is** observed.
- **Not** a discrimination against the book-scoped-reprice rival, which predicts
  a high `S` exactly as the scrape-clock reading does and which ADR 0026's table
  marks **non-discriminating**. That rival is not hypothetical here: in poll 1,
  **30 of 31 books carry exactly one distinct `last_update` across the whole
  15-game slate**. §0's qualifier exists for precisely this, and it fired.

Two things the record keeps rather than smooths, because a future session will
otherwise over-read them:

- **`S` is a pooled proportion on this data.** Every book contributed exactly 15
  pairs, and with equal cluster sizes the bookmaker-clustered mean is
  *algebraically* the pooled ratio. Do not cite "bookmaker-clustered" as if it
  had downweighted a dominant book; the protection is intact but unexercised.
  The parts do agree — largest contributor 3.2%, leave-one-book-out `S` in
  **0.9356–0.9489**, per-book shares 0.6000 (`nordicbet`) to 1.0000 (13 books) —
  and the exchanges were retained despite sitting below `S`, which cost the
  hypothesis rather than helped it.
- **The margin is thin in absolute terms.** Moving **18 of 465 pairs (3.9%)**
  from A to B takes `S` to 0.8989 and the verdict to UNRESOLVED.

---

## 6. Consequences

1. **`odds_age_ms` and `stale_odds` may be described as scrape-clock quantities
   without hedging**, at the ~300 s interval, citing this ADR. The prose already
   in `backend/core/suppression.py:232-252` is correct and needs no change.
2. **The 900 s window is an open question and must be written as one.** It is not
   answerable by another run of this instrument.
3. **No remedy is authorised.** Patching `MAX_ODDS_AGE_S`, adding a second
   freshness signal, or re-scoring the 23 rows each need their own decision, and
   any measurement behind one needs its own pre-registration.
4. **The clean set, not the suppressed set, is where the unmeasured staleness
   lives.** Any future work on freshness should start there.
5. The **operational corollary** in result §9 — 31/31 books advance inside the
   deployed 900 s window — **carries no alpha and is not independent**: given
   every book advanced by 300 s with `regressed = 0`, its `>= 0.90` branch was
   forced by the primary result. `n_adv900` has no consumer outside the analyser,
   its tests and the registration. Do not build on it.
