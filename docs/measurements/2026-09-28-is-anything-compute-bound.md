# Is anything compute-bound? The two numeric kernels on a laptop, and the live box's first CPU-time reading

**Date:** 2026-09-28
**Prompt:** Joe: "perform an exploratory analysis to see if we can use a more
optimal codebase for performance. For example, would we benefit from using
rust versus python for any part of the stack? Be it analysis or performance."
The repo put the same question to itself on 2026-08-08
(`tasks/archive/next-2026-08-08.md:626-640`, item 4). It answered with a
plan that was never carried out.
**Instruments:**
- `scripts/measure_kernel_timings.py --reps 9`, run three times on the
  laptop (§A).
- `scripts/inspect_live_proc.py --json`, run twice on live 20 minutes
  apart, subtracted with `--diff` (§B). Its CPU fields are from `c12c704`,
  which Joe deployed himself at 20:53Z.
- `inspect_live_db.py walk-log -n 150` for the passes inside the interval.

**Cost:** zero odds credits, zero tokens. The live reads were `/proc` text
files and one JSONL file beside the database. No table was read.
**Audited:** measurement-skeptic, 2026-09-28, on §A. The verdict on the
first draft was OVERSTATED. This version carries its corrections:
like-for-like timing, "Genz CDF" in place of "exact", and the added limits
below. §B was taken after the audit, and the audit does not cover it.
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
- **On live, over 1,203.5 s** with the window open, one full pass and 43
  quote passes:
  - the whole box used **0.026 of its 2 cores (1.3% busy)**, with iowait
    0.1% and steal 0.0%;
  - the recorder used **27.4 CPU-seconds (0.023 cores)**, uvicorn 2.7 s and
    Next 0.4 s.
  - This is the first CPU-time reading the box has ever had. It
    contradicts, for this interval, the unprofiled claim that "a full pass
    costs 33–114s of saturated CPU every 900s". The whole interval's
    recorder CPU, full pass included, was 27.4 s.

## What this does not establish

- **§A says nothing about the live box.** The laptop is an Intel Family 6
  Model 154, Python 3.11.9, numpy 2.4.6 and scipy 1.17.1. Fly's
  `shared-cpu-2x` is slower and shared, so §A's numbers rank the kernels
  against one another. They do not price them in production.
- **§B is one 20-minute interval on one Monday evening, 31 minutes after a
  restart.** It is n = 1. A weekend slate, a tab left open on `/parlays`,
  or a busier catalogue walk loads the box differently. No page was
  deliberately loaded during it; uvicorn's 2.7 s says the API was nearly
  idle.
- **Steal of 0.0% says little.** A VM that is 1.3% busy has almost nothing
  to be stolen from, so this is not a reading of the shared vCPU's
  contention under load.
- **§B counts CPU seconds per process, not which code spent them.** It is
  not a profile.
- **Wall-clock costs elsewhere are not CPU costs.** Every other cost in the
  record was attributed by wall clock, not CPU time (ADR 0188 §2).
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

**Taken 2026-09-28, 21:25:28Z → 21:45:31Z (1,203.5 s)**, live on `c12c704`,
machine `7812601a239428`, 2 vCPU, 4 GB, `clk_tck` 100. The box had been up
0.517 h at the first reading. Two readings of
`inspect_live_proc.py --json`, subtracted with `--diff`:

    box: 0.026 of 2 cores busy  busy 1.3%  iowait 0.1%  steal 0.0%

        pid      cpu_s   cores  name
        699       27.4   0.023  python scripts/run_loop.py (the recorder)
        673        2.7   0.002  python -m uvicorn (the API)
          1        1.6   0.001  /fly/init
        698        0.4   0.000  next-server (v16.3.3)
        652        0.1   0.000  hallpass

**What ran inside it** (`walk-log -n 150`):
- **one full pass**, at 21:29:11Z. It walked 11,652 events, the whole
  catalogue.
- **43 quote passes** (narrowed, 27 series, 479 events). They ran every
  ~18–20 s, so the window was open and the recorder was in its busiest
  mode.

Lifetime averages at the second reading, since boot: recorder 0.0168 cores,
uvicorn 0.0030, Next 0.0005. Memory: 3,222 MiB available, 1,924 MiB cached,
recorder RSS 265 MiB.

**What it means.** The recorder used 27.4 CPU-seconds on a full catalogue
walk plus 43 quote passes, about 2% of one core. The unprofiled 2026-08-26
claim that "a full pass costs 33–114s of saturated CPU every 900s on a
shared vCPU" (`2026-08-26-serving-path-baseline.md:86`) does not hold for
this interval. That claim was written on a one-vCPU box, before ADR 0053
narrowed the walk and before the index fixes. Until today the record held
only wall clock for the recorder: the 75.0 s quote pass on one shared vCPU
(`fly.live.toml:977-992`), and a leg-attribution doc that says of itself
"Not a CPU measurement".

So for the recorder, ADR 0188 now rests on a CPU reading, not only on the
absence of CPU evidence: the box is nearly idle. Its latency, where it has
any, is not CPU. **Re-read it** (the same two commands, 15+ minutes apart)
on a busy weekend slate, or if a quote pass starts overrunning its cadence
again. That is the condition under which this reading could go stale.
