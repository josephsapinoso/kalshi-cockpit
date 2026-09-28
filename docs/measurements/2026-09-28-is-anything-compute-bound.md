# Is anything compute-bound? The two numeric kernels, timed on a laptop

**Date:** 2026-09-28
**Prompt:** Joe: "perform an exploratory analysis to see if we can use a more
optimal codebase for performance. For example, would we benefit from using
rust versus python for any part of the stack? Be it analysis or performance."
The repo put the same question to itself on 2026-08-08
(`tasks/archive/next-2026-08-08.md:626-640`, item 4). It answered with a
plan that was never carried out.
**Instruments:** `scripts/measure_kernel_timings.py --reps 9`, run three
times on the laptop (§A). §B, the live box's CPU time, is **pending**. It
will come from `scripts/inspect_live_proc.py --diff`, whose CPU fields
landed in `c12c704` (CI green). That commit is not yet on the live machine.
**Cost:** zero odds credits, zero tokens, no database reads, no live reads.
**Audited:** measurement-skeptic, 2026-09-28. The verdict on the first draft
was OVERSTATED. This version carries its corrections: like-for-like timing,
"Genz CDF" in place of "exact", no claim that §B was taken, and the added
limits below.
**Decision it feeds:** ADR 0188.

## What this establishes

- On a laptop, devig for 145 two-way markets × 20 books costs **94–108 ms**
  (32–37 µs a book). That is the scale of one pass's written fair prices
  on 2026-08-26, not a count of devig calls.
- The Monte Carlo copula costs **10–26 ms a call** at 2–6 legs. A ladder
  build makes **up to 30** (6 cards × the conservative joint plus 4
  methods, `core/ladder.py:572-593`), fewer after the memo dedups them. Of
  the two kernels timed, it is the only one whose cost a person could
  notice.
- scipy's multivariate-normal CDF (Genz), timed **end to end** on the same
  legs, is **23–30× faster at 2 legs and 5.5–13× faster at 3–6 legs**. It
  differs from the 200k-draw estimate by **0.01–0.13 points**. That is
  consistent with no bias between the two, but it cannot exclude a bias
  below about two Monte Carlo standard errors (~0.1–0.2 points).

## What this does not establish

- **Nothing about the live box.** The laptop is an Intel Family 6 Model 154,
  Python 3.11.9, numpy 2.4.6 and scipy 1.17.1. Fly's `shared-cpu-2x` is
  slower and shared, so these numbers rank the kernels against one another.
  They do not price them in production. §B is the live reading, and it is
  pending.
- **Anything about CPU time anywhere else.** Every other cost in the record
  was attributed by wall clock, not CPU time (ADR 0188 §2).
- **The inputs are synthetic.** Devig markets are drawn with a fixed seed.
  Copula legs are all 0.55, with pairwise correlations of 0.2–0.3 supplied
  as overrides. The ladder passes no overrides, so its real correlations
  are the defaults (0.02–0.05). More than 6 legs are never timed, and the
  speed ratio shrinks as legs are added: ~2.5× at 12 legs in an unrecorded
  probe. The ladder's maximum is 6 (`ladder.py:279`).
- **The Genz CDF is exact only at 2 legs.** scipy 1.17 uses a closed form
  (`_bvn`) at 2 legs. At 3+ it uses randomized quasi-Monte Carlo, which
  stops at 3×SE ≤ 1e-5 absolute: at most ~0.0005 points, about a hundredth
  of the Monte Carlo's error. It is a far more precise estimate, not an
  exact one. Its 3+-leg values can move in the fifth decimal between runs
  that build the distribution differently.
- **The agreement is at four inputs that share one Monte Carlo seed.** It
  is not four independent checks, and it says nothing about the rows the
  ladder and the hedge actually price.
- **The ranges are three runs' spread, not bounds.** The skeptic's own run
  gave 28.24 ms at 6 legs, outside the range above.
- **No compiled version was built or timed.** Anything said here about what
  Rust would buy is an estimate. The measured side is Python against Python.

## §A — The two numeric kernels, timed on the laptop

Three runs of `scripts/measure_kernel_timings.py --reps 9` (median of 9 reps
per run). Both copula methods are timed end to end: the correlation matrix,
the thresholds, and the draws or the CDF.

| kernel | run 1 | run 2 | run 3 |
|---|---|---|---|
| devig, 145 markets × 20 books | 93.87 ms | 107.95 ms | 106.17 ms |
| Monte Carlo, 2 legs | 11.23 ms | 10.17 ms | 10.86 ms |
| Monte Carlo, 3 legs | 15.37 ms | 14.66 ms | 14.64 ms |
| Monte Carlo, 4 legs | 17.19 ms | 17.35 ms | 17.62 ms |
| Monte Carlo, 6 legs | 21.34 ms | 25.76 ms | 21.31 ms |
| Genz CDF, 2 legs | 0.38 ms | 0.35 ms | 0.48 ms |
| Genz CDF, 3 legs | 1.23 ms | 1.41 ms | 1.11 ms |
| Genz CDF, 4 legs | 1.47 ms | 2.01 ms | 2.11 ms |
| Genz CDF, 6 legs | 3.41 ms | 3.01 ms | 3.84 ms |

The first draft timed only the Genz `cdf` call and left ~0.2 ms of setup
outside its timer. That read as ~200× at 2 legs. The harness now charges
both methods for the same setup.

The two estimators of one joint probability. The values are the same in
every run, because both use fixed seeds:

| legs | Monte Carlo | Genz CDF | Monte Carlo − Genz | Monte Carlo SE | z |
|---|---|---|---|---|---|
| 2 | 0.34906 | 0.35033 | −0.127 pts | 0.107 pts | −1.19 |
| 3 | 0.20145 | 0.20108 | +0.036 pts | 0.090 pts | +0.40 |
| 4 | 0.12552 | 0.12618 | −0.066 pts | 0.074 pts | −0.89 |
| 6 | 0.04979 | 0.04968 | +0.011 pts | 0.049 pts | +0.22 |

The SE is `sqrt(p(1−p)/200,000)` at the Genz value, the right error for a
proportion over 200,000 independent Cholesky draws
(`core/correlation.py:184-191`). Genz's own error adds almost nothing to it.

**What the numbers mean for a rewrite:**
- **Devig:** a compiled version would save at most ~100 ms of laptop time
  on a pass that runs every 15–900 s. Live is unmeasured and slower. The
  recorder's measured legs are seconds long
  (`2026-08-19-quote-pass-leg-attribution.md`). That doc has n = 1, uses
  wall clock, and leaves 27 s of a 44.6 s full pass in no timed leg.
- **Copula:** no compiled version was timed. What is measured is that the
  Genz CDF, in Python, is 5.5–30× faster than the Monte Carlo with about a
  hundredth of its sampling error. Before anyone considers a compiled
  sampler, this is the cheaper thing to try.

## §B — CPU time per process on the live box

**Pending.** `scripts/inspect_live_proc.py` now reads `utime`/`stime` per
process and `/proc/stat`'s steal and iowait, and subtracts two readings.
Five guards are verified by mutation. The fields reach the box with
`c12c704`, and no reading has been taken yet.

Until then, the record holds only wall clock:
- a quote pass took 75.0 s against a 15 s cadence on one shared vCPU
  (`fly.live.toml:977-992`);
- "a full pass costs 33–114s of saturated CPU every 900s on a shared vCPU"
  is asserted in `2026-08-26-serving-path-baseline.md:86` and was never
  profiled;
- the leg-attribution doc says of itself "Not a CPU measurement".

Fly's Prometheus endpoint returned 401, so no CPU, iowait or steal series
has been read (`2026-09-18-the-window-route-walked-every-odds-row.md`).

**What the missing reading leaves open.** For the recorder, ADR 0188 rests
on the absence of CPU evidence, not on a measurement that CPU is small. If
the reading shows `run_loop.py` near a full core, or high steal on the
shared vCPU, the recorder half of the question reopens. The next step would
then be a profile, not a rewrite.
