# 0188 — Python stays: the desk's measured costs are storage and query shape, not the language

**Status:** Proposed 2026-09-28, and it becomes Accepted when the live box's CPU reading (measurement doc §B) lands. This answers Joe's request for an exploratory analysis of whether any part of the stack should be rewritten in Rust. The number is 0188 on `main` because 0187 was the highest and no lane held a draft.
**Date:** 2026-09-28
**Evidence:** `docs/measurements/2026-09-28-is-anything-compute-bound.md`. §A of that doc holds the kernel timings; §B, the live CPU reading, is pending. Nine of the measured bottlenecks already in `docs/measurements/` are tabulated in §2 below, with their sources. The measurement-skeptic audit (2026-09-28) is applied throughout.
**Tickets:** epic #185 under root #80, tasks #186–#191 (#188 parked).
**Closes:** `tasks/archive/next-2026-08-08.md:626-640`, item 4 ("Is Python the right language everywhere?"). That item asked for this finding to be written as an ADR "so it is not re-litigated", and it never was.
**Leaves standing:** ADR 0182 (Joe: no VACUUM for now), ADR 0183 (the cap on the `kalshi_quotes` exemption), ADR 0163 (4 GB, not 8), ADR 0141 (an index is bought only on a timing), ADR 0168 (a whole-file inspection query needs `--i-accept-the-cache-flush`).

## 1. The decision

**No module is rewritten in Rust, C++, Cython or numba, and no PyO3/maturin toolchain enters the repo.** Rust stays where it already pays, inside the libraries: pydantic v2's core, ruff, parts of `cryptography`, and `uv` if #190 lands. DuckDB (C++) carries the analysis.

**What the decision rests on, stated at its real strength:**
- Only one row of §2 is CPU: the copula. It was fixed with a memo, and there is a faster Python method for it (§4).
- Every other row was attributed to SQL, the page cache or the HTTP walk by **wall clock**. None was measured as CPU time.
- So for the **routes** and the **analysis**, the decision rests on measured causes. Each was fixed by an index, a query shape or a table, and a language change would not have touched it.
- For the **recorder**, it rests on the **absence of CPU evidence**, not on a measurement that CPU is small. §B is the first reading that could supply that evidence.

**Reopening requires** naming a stage of the recorder, or of a route, whose **CPU time** (not wall time) is a material share of its cost. Measure it with `scripts/inspect_live_proc.py --diff` on live, then attribute it with a profiler.

## 2. Why: every cost measured so far was attributed to SQL, the page cache or the HTTP walk, by wall clock rather than CPU time

| where the time went | measured | category | what fixed it |
|---|---|---|---|
| quote pass, 1 shared vCPU (08-19) | 27.1 → 77.1 s against a 15 s cadence | HTTP walk (~56 pages at 8 req/s), attributed by elimination and not profiled. Inserts (0.17 s) and parsing (~0.46 s, scaled from a laptop fixture) ruled out. The source says "transfer and TLS on a throttled shared vCPU" | a narrower walk, ADR 0053: walk 15.21 → 3.13 s. It cut bytes, which also cuts decode CPU, so the fix cannot separate the two |
| per-candidate scan in the recorder (08-26) | persist leg 34,166 ms | SQL: a full scan plus a temp sort, ~350 times a pass | `idx_recs_ticker_side` |
| candidate scan (08-30) | p50 407 ms (n = 46); max 11,202 in the 182-pass series | SQL plan | covering index: p50 60 ms (n = 102), `2026-08-30-the-candidate-scan-index.md:101-109` |
| ladder scan OOM (09-10) | 6,561,382 rows pulled through; OOM kills at 1,126,076 and 1,884,640 kB | SQL plus memory | partial index, ADR 0134: 72–75 ms |
| parlay subquery (09-10) | 26,719 ms | SQL: the index lacked `commence_ms` | ADR 0141: 327.9 ms |
| cold cache after a whole-table read (09-10) | 74.8 s cold vs 2.15 s warm | page-cache eviction | boot warm-up, 4 GB, the ADR 0168 flag |
| `/api/window` (09-17) | 6,974 ms median; pages 8–15 s | SQL shape | `odds_fixtures`, ADR 0167: 119 ms |
| `/api/signal` miss | 3.1–13.8 s (n = 4 observations) | cache plus SQL | **open**: #187 |
| `/api/parlays` payload build (08-26) | 345 ms in-process on a seeded fixture, attributed to the copula | **CPU (numpy)**, the only CPU row | module-level memo: 2 ms on a hit |

**The file and the memory.** The live file was 7.72 GB on 2026-09-21. On 2026-09-18, when the file was 6.3 GB, the box had ~3.1 GB of memory available (`2026-09-18-the-window-route-walked-every-odds-row.md:44`). That figure is available memory, not the size of the page cache. Whether a request is fast depends mostly on whether its pages are resident, and a faster language changes neither number.

**The unmeasured counter-claim.** `2026-08-26-serving-path-baseline.md:86` asserts that "a full pass costs 33–114s of saturated CPU every 900s on a shared vCPU". That was never profiled. The recorder evidence against it (`2026-08-19-quote-pass-leg-attribution.md`) is n = 1, wall clock, and says of itself "Not a CPU measurement"; 27 s of its 44.6 s full pass fall in no timed leg. Neither side is a CPU measurement, which is why §B exists.

**The two numeric kernels, timed** (laptop, measurement doc §A):
- **Devig:** 94–108 ms a pass (145 markets × 20 books). A compiled version would save at most ~100 ms of laptop time on a pass that runs every 15–900 s.
- **The copula:** 10–26 ms a call. It is the only kernel of the two whose cost a person could notice. No compiled version was timed. The measured alternative is scipy's Genz CDF, in Python: 23–30× faster at 2 legs and 5.5–13× at 3–6, timed end to end. It is within 1.2 Monte Carlo standard errors of the draws, at four synthetic inputs.

**CPU on the live box:** pending, measurement doc §B.

## 3. What would make the desk faster instead (epic #185)

Ranked by what changes on screen (partner, 2026-09-28):
1. **#187:** `/api/signal` serves its last report while one refresh runs, and the TTL rises from 5 minutes to 1 hour. The registered SQL is untouched. This is the only ticket that takes seconds off a screen: a miss costs 3.1–13.8 s.
2. **#191** (owner:main): `/api/hedge` takes ~2 s on the screen Joe uses mid-game. `read_books` reads each watched ticker's book one after another, and "open" positions mean unclosed bookkeeping, not live games. Count the tickers first.
3. **#186:** pages fetch in parallel. `slate/page.tsx:112-115` awaits four fetches in sequence, and three other pages do the same, so a page costs the sum of its calls.
4. **#190:** CI installs with `uv`, and runs under `pytest-xdist` only if the suite proves order-independent. The last green run took ~10.5 min against a 15-minute cap.
5. **#189:** `pandas` leaves `requirements.txt`, because nothing imports it.
6. **#188, parked:** four `async def` routes run synchronous SQLite and the copula on uvicorn's only event loop, so the SSE stream and the WebSocket **can** stall while one computes. **Nobody has measured that stall.** `/api/hedge`'s ~2 s is awaited venue reads, which do not block the loop. Build this only after a loop-lag reading shows the stall is real.

**The biggest lever is left off this list on purpose.** The file is well over twice the memory the box can give it, and it carries 1.22 GB of dead space across 14 btrees (`2026-09-21-what-actually-grew-is-kalshi-quotes.md`). Shrinking it is Epic #81's work and Joe's word. He said **no VACUUM for now** (#58, ADR 0182), and the `kalshi_quotes` exemption is already capped (ADR 0183). This ADR reopens neither.

## 4. The Genz CDF swap is deferred, not adopted

A swap would move every correlated parlay and hedge chance by about one Monte Carlo standard error (~0.05–0.11 points at the timed inputs). Leg sets whose matrix is the identity already take the exact-product path (`core/correlation.py:180-182`) and would not move.

**Where the copula runs.** The ladder builds on the `GET /api/parlays` request path whenever `_JOINT_CACHE` misses (`backend/core/ladder.py:505-543`: 256 entries, keyed on the leg prices, so any price move misses). A build is up to 30 copula calls, about 0.3–0.9 s on the laptop and unmeasured on live. `/api/hedge`, `/api/parlays/lookup` and `/check` make a few more each, on the event loop (#188, parked).

**Whether a swap would be visible** depends on the memo's hit rate on live, which nothing has read. So this is a **deferred build decision**, not a question for Joe yet. It becomes one if a warm `/api/parlays` read on live shows the ladder build as a material share of the route's time. At that point the swap goes to Joe as a ticket under map #3, with a check against recorded rows rather than four synthetic inputs.

## 5. What this does not establish

- **No profile.** `inspect_live_proc.py` counts CPU seconds per process. It cannot say which line spends them.
- **§2's kernel timings are laptop numbers.** They rank the kernels against one another. They do not price them on `shared-cpu-2x`.
- **The live reading, when taken, will be one interval on one evening.** A weekend of games, or a tab left open on `/parlays`, loads the box differently. The instrument is committed so that the next reading costs one command.
- **Nothing here says the desk is fast enough.** It says the next gains are in §3, and in the storage lever §3 leaves to Joe, not in a language.
