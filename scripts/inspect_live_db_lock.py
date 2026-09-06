"""The two registered instruments for `database is locked`.

Queries: `forward-lock`, `lock-attribution`.

They answer different, separately registered questions -- did ADR 0091 close
the symptom after its deploy, and does each burst land inside a poller cycle
-- and they are the only queries in this family that compute a **verdict**.
That is why they are one module rather than filed under loop health: every
threshold in here is a registered constant fixed before the data was seen,
and moving one is a visible diff in a file whose whole content is
registration arithmetic. Both refuse rather than report when a precondition
fails, and neither has an exonerating verdict.

They read the loop's own journals, so this module imports `FAILURE_LOG_NAME`
and `loop_rss_path` from `inspect_live_db_loop`; the dependency runs one way
only.

**Every SQL string in this module is a constant.** This module is imported by
`inspect_live_db.py`, is never run directly, and inherits every disclaimer in
that file's docstring.
"""

from __future__ import annotations

import bisect
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Optional

from inspect_live_db_common import (
    Section,
    _iso,
    _quantile,
)
from inspect_live_db_loop import (
    FAILURE_LOG_NAME,
    loop_rss_path,
)


#: The registered H1 window, in seconds, from
#: `docs/measurements/2026-09-01-lock-holder-attribution-registration.md` §5.
#:
#: The poller took SQLite's write lock at its first INSERT -- one Kalshi round
#: trip after the cycle stamp -- and held it until a commit three round trips
#: later; a victim then waits `BUSY_TIMEOUT_MS` (5,000 ms) before raising, and
#: is stamped at the raise. Bounding a round trip at 3 s gives 3*3 + 5 = 14.
#:
#: **Fixed before the join was computed.** Widening it after seeing the offsets
#: is the defect this constant exists to make visible in a diff.
LOCK_WINDOW_S = 14.0

#: Two-sided exact-binomial threshold, §6. 0.01 rather than 0.05 because this
#: record has run many tests and CLAUDE.md requires counting them.
LOCK_ALPHA = 0.01


def _binom_pmf(k: int, n: int, p: float) -> float:
    return math.comb(n, k) * (p ** k) * ((1.0 - p) ** (n - k))


def _binom_two_sided(k: int, n: int, p: float) -> float:
    """Exact two-sided binomial p-value, by the method-of-small-likelihoods.

    Sums every outcome at least as improbable as the observed one. No scipy on
    the machine -- and a normal approximation is exactly what CLAUDE.md's "read
    `n` before the effect size" rule forbids at these counts.
    """
    if n <= 0:
        return 1.0
    observed = _binom_pmf(k, n, p)
    tol = observed * (1.0 + 1e-7)
    return min(1.0, sum(
        _binom_pmf(i, n, p) for i in range(n + 1) if _binom_pmf(i, n, p) <= tol
    ))


#: §2.2's stated deploy of ADR 0091, 2026-08-31T15:29:19Z, as epoch ms. It
#: bounds the **pre-fix** window that C4 and C5 compare against, and it is the
#: one external timestamp this registration uses on purpose: `T0` is derived
#: from the database precisely so the *exposure* boundary needs no release
#: time, while the pre-fix baseline is a historical window whose edge the
#: registration fixes in prose. Using any other value would be choosing a
#: baseline after seeing the data.
ADR_0091_DEPLOY_MS = 1_788_190_159_000

#: C3's fallback when no pre-fix burst can be aged, in hours. §7 fixes it at
#: 2.0 -- "the largest round value below the 3.13 h longest observed post-fix
#: process life, so the precondition is reachable rather than automatically
#: failing."
A_PRE_FALLBACK_HOURS = 2.0

#: C3's required aged exposure, in fast cycles. §7: 30 is `1 / lambda_0`, one
#: pre-fix burst-equivalent of exposure in the aged regime.
C3_AGED_CYCLES_REQUIRED = 30

#: C4's pre-fix quantile, and C5's tolerance either way.
C4_PRE_QUANTILE = 0.25
C5_TEMPO_TOLERANCE = 0.25


def _read_rss_samples(db_path: str) -> tuple[list[dict], Optional[str]]:
    """`loop_rss.jsonl` as dicts in time order, plus a refusal reason.

    **`produced_by` absent and `produced_by: null` are different states and the
    whole of C3 turns on it.** A `null` is a process's first sample -- the
    restart marker the file otherwise lacks. An *absent* key is a line written
    before the field existed (2026-08-29), which says nothing about restarts.

    `entry.get("produced_by") is None` cannot tell them apart, and on the live
    file it counts **752** restarts where there are **44**. The error is
    seventeen-fold and it runs the flattering way: phantom restarts shorten
    every process age, which lowers `A_pre` and lets more cycles qualify as
    aged, so C3 gets *easier* to pass. This reader keys on presence.
    """
    path = loop_rss_path(db_path)
    try:
        raw = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], f"{path}: {exc}"

    samples: list[dict] = []
    for line in raw:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict) or not isinstance(entry.get("ms"), int):
            continue
        samples.append({
            "ms": entry["ms"],
            # Tri-state, deliberately: True = restart, False = not, None =
            # the field did not exist on this line and cannot be read either way.
            "restart": (
                (entry["produced_by"] is None)
                if "produced_by" in entry else None
            ),
            # `None` is "not measured" and `0` is "the WAL is empty". Never
            # substitute.
            "wal_kb": entry.get("wal_kb"),
        })
    samples.sort(key=lambda s: s["ms"])
    return samples, None


def _process_start_index(samples: list[dict]) -> list[tuple[int, int]]:
    """`(ms, process_start_ms)` for every sample that can be aged.

    A sample is aged against the newest **true** restart marker at or before
    it. Samples before the first such marker are dropped rather than aged
    against the file's first line: an append-only log that spans container
    lifetimes has no reason to begin at a boot, and assuming it does invents
    an age.
    """
    out: list[tuple[int, int]] = []
    start: Optional[int] = None
    for sample in samples:
        if sample["restart"] is True:
            start = sample["ms"]
        if start is not None:
            out.append((sample["ms"], start))
    return out


def _age_at(aged: list[tuple[int, int]], ms: int) -> Optional[float]:
    """Process age in hours at `ms`, or `None` if it cannot be attributed."""
    idx = bisect.bisect_right([a[0] for a in aged], ms) - 1
    if idx < 0:
        return None
    return (ms - aged[idx][1]) / 3_600_000.0


#: Section 6.3's band, in seconds. A burst is in-band if its offset from its matched
#: cycle start lies here. `BUSY_TIMEOUT_MS = 5_000`, so a lock held by the
#: poller surfaces just past 5 s; the upper edge is the registered one.
FORWARD_LOCK_BAND_S = (5.000, 8.000)

#: Section 6.3's e-value alarm. SIGNATURE PERSISTS is declarable at ANY time, which
#: is the only verdict exempt from the `E >= E*` gate.
FORWARD_LOCK_E_ALARM = 200.0

#: Section 8's registered stopping point, in fast cycles. Section 7's C6 may RAISE this
#: and may never lower it.
FORWARD_LOCK_E_STAR = 160

#: C6's floor: `E* = 160` delivers p <= 0.005 only if `lambda_0` is at least
#: this. Below it, C6 raises `E*` rather than accepting a weaker test.
FORWARD_LOCK_LAMBDA_FLOOR = 0.03257

#: Section 6.3's `p0` numerator, in seconds: the width of the band as a share of the
#: cycle. `p0 = 3.000 / C`, C being the median observed cycle gap.
FORWARD_LOCK_BAND_WIDTH_S = 3.000


def _q_forward_lock(conn: sqlite3.Connection, args) -> list[Section]:
    """Did ADR 0091 close the `database is locked` symptom, after `T0`?

    Implements §11 of `docs/measurements/2026-09-01-forward-lock-instrument-
    registration.md`, which fixed three missing capabilities **before** any
    post-`T0` burst was read. Read it before quoting anything here; this
    docstring restates it and does not amend it.

    Why this is a separate subcommand from `lock-attribution`
    --------------------------------------------------------
    `lock-attribution` implements a different, **completed** registration
    whose result is already in the record (`n = 13, k = 13,
    p = 4.890e-18`); changing what it prints would break that measurement's
    reproducibility. And the two verdict vocabularies differ (POLLER
    IMPLICATED / NOT ESTABLISHED against FIX CONFIRMED / SIGNATURE PERSISTS /
    MIRROR RESIDUAL / UNRESOLVED), so one function printing both would be a
    mixture with no column saying which question a line answers.

    The three capabilities, and where each lives
    --------------------------------------------
    1. **`T0`** (§2.1): `MIN(polled_ms) WHERE endpoint = 'mirror'` -- a durable
       in-database deploy marker, so the boundary needs no Fly release
       timestamp. `lock-attribution` pools pre- and post-deploy bursts; this
       refuses to.
    2. **MIRROR/FAST** (§4): a cycle is MIRROR if any `poll_log` row at its
       stamp carries `endpoint = 'mirror'`, else FAST.
    3. **`E`, `E*` and `E_n`** (§6.3), and the refusal to print a rate verdict
       below `E*`.

    The one verdict exempt from `E*`
    --------------------------------
    **SIGNATURE PERSISTS is always-valid** and may be declared at any `E`,
    because an e-value is a martingale under the null: `E_n >= 200` controls
    the type-I error at any stopping time, including one chosen by looking.
    Every other verdict is gated on `E >= E*` and this function refuses to
    print one below it.

    What this does NOT establish
    ----------------------------
    - **Nothing, before `E >= E*`, except SIGNATURE PERSISTS.** Section 6.3 says so
      in those words. A small `K` at small `E` is what the null predicts.
    - **That the poller is the only holder.** Attribution and efficacy are
      different claims; this one is efficacy and takes the attribution result
      as given rather than re-deriving it.
    - **C3, C4 and C5 read `loop_rss.jsonl` and can each answer NOT
      COMPUTED.** An uncomputable precondition is **not** a pass: section 6.3
      conditions FIX CONFIRMED on every one of C1-C6, and a failed or
      unevaluable one is reported BY NAME rather than shortened to UNRESOLVED.
    - **The pre-fix baseline is bounded by ADR 0091's deploy, not by `T0`.**
      Section 2.2's discarded interval sits between them and belongs to neither arm,
      so C4's and C5's "pre-fix window" ends at `ADR_0091_DEPLOY_MS`. That is
      the one external timestamp used here, and deliberately: `T0` is derived
      from the database so the *exposure* boundary needs no release time, while
      the pre-fix baseline is a historical window the registration fixes in
      prose.
    - **`produced_by` absent and `produced_by: null` are different states**,
      and C3 turns on the difference. See `_read_rss_samples`.
    - **Anything about the excluded interval** (section 2.2), the ~19 hours between
      ADR 0091's deploy and `T0`. It is descriptive context and may not enter
      either arm.
    """
    band_lo, band_hi = FORWARD_LOCK_BAND_S
    cap = args.limit

    # --- T0, the in-database deploy marker (C2) ------------------------------
    t0_row = conn.execute(
        "SELECT MIN(polled_ms) FROM poll_log WHERE endpoint = 'mirror'"
    ).fetchone()
    t0 = t0_row[0] if t0_row else None

    if t0 is None:
        return [Section(
            title=(
                "forward-lock: C2 FAILED -- no `endpoint = 'mirror'` row, so "
                "the build carrying the marker is NOT LIVE. This is 'the "
                "instrument is not there', never 'no bursts'."
            ),
            columns=("check", "value", "reading"),
            rows=[
                ("T0", "ABSENT", "MIN(polled_ms) WHERE endpoint = 'mirror'"),
                ("verdict", "UNRESOLVED - C2", "section 7: refuses a verdict"),
                ("added by", "ea4c1a3",
                 "merged 56f4572, deployed 265bc9a; no earlier build writes it"),
            ],
            cap=cap,
        )]

    # --- cycles, split MIRROR/FAST (capability 2) ----------------------------
    cycle_rows = conn.execute(
        "SELECT polled_ms, "
        "       MAX(CASE WHEN endpoint = 'mirror' THEN 1 ELSE 0 END) AS is_mirror "
        "FROM poll_log GROUP BY polled_ms ORDER BY polled_ms ASC"
    ).fetchall()
    cycles = [(int(r[0]), bool(r[1])) for r in cycle_rows if r[0] is not None]
    stamps = [ms for ms, _ in cycles]
    is_mirror = {ms: mirror for ms, mirror in cycles}

    # `E` counts FAST cycles at or after T0. The mirror branch is a different
    # code path with its own history, so pooling them would answer a question
    # nobody registered.
    fast_after_t0 = [ms for ms, mirror in cycles if ms >= t0 and not mirror]
    e_count = len(fast_after_t0)

    # --- the journal population ---------------------------------------------
    path = Path(args.db).resolve().parent / FAILURE_LOG_NAME
    try:
        journal_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [Section(
            title=(
                "forward-lock: THE JOURNAL IS NOT THERE -- this is not "
                "'no failures'"
            ),
            columns=("problem", "path", "writer"),
            rows=[(str(exc), str(path),
                   "backend.store.db.record_loop_failure_durably")],
            cap=cap,
        )]

    failures: list[dict] = []
    for raw in journal_lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        if not isinstance(kind, str):
            kind = "diagnosis" if "diagnosis" in entry else "failure"
        if kind != "failure":
            continue
        if "database is locked" not in str(entry.get("error") or ""):
            continue
        if entry.get("consecutive_failures") != 1:
            continue
        if isinstance(entry.get("ms"), int):
            failures.append(entry)
    failures.sort(key=lambda e: e["ms"])

    # --- match each burst to its cycle, then apply the T0 rule (section 2.4) --------
    #
    # The assignment is by the MATCHED CYCLE's stamp, never by the burst's own
    # `failed_ms`: a failure stamped after T0 whose newest preceding cycle
    # started before it belongs to a pre-marker cycle and is EXCLUDED. At most
    # one burst can be in that class, and it is named individually below.
    matched: list[dict] = []
    straddlers: list[dict] = []
    unmatched: list[dict] = []
    for entry in failures:
        ms = entry["ms"]
        idx = bisect.bisect_right(stamps, ms) - 1
        if idx < 0:
            unmatched.append(entry)
            continue
        cycle_ms = stamps[idx]
        record = {
            "ms": ms,
            "cycle_ms": cycle_ms,
            "offset_s": (ms - cycle_ms) / 1000.0,
            "mirror": is_mirror[cycle_ms],
        }
        if cycle_ms < t0:
            (straddlers if ms >= t0 else unmatched).append(record)
            continue
        matched.append(record)

    # `K` collapses bursts sharing a matched cycle to one: two failures inside
    # one cycle are one draw about that cycle, not two.
    by_cycle: dict[int, dict] = {}
    for record in matched:
        by_cycle.setdefault(record["cycle_ms"], record)
    k_bursts = sorted(by_cycle.values(), key=lambda r: r["ms"])
    k_count = len(k_bursts)

    fast_bursts = [r for r in k_bursts if not r["mirror"]]
    h_bursts = [
        r for r in fast_bursts if band_lo <= r["offset_s"] <= band_hi
    ]
    h_count = len(h_bursts)

    # --- C, p0 and the e-value (capability 3) --------------------------------
    gaps = sorted(
        (b - a) / 1000.0 for a, b in zip(stamps, stamps[1:]) if b >= t0
    )
    median_gap_s = gaps[len(gaps) // 2] if gaps else None
    p0 = (
        None if not median_gap_s
        else FORWARD_LOCK_BAND_WIDTH_S / median_gap_s
    )

    # `E_n` is a running product over FAST-matched bursts in TIME ORDER --
    # order matters because an e-value is a martingale and the sequence is the
    # object, not the final count.
    e_value = 1.0
    e_trace: list[tuple] = []
    if p0 is not None and 0.0 < p0 < 1.0:
        for record in fast_bursts:
            in_band = band_lo <= record["offset_s"] <= band_hi
            factor = 0.5 / p0 if in_band else 0.5 / (1.0 - p0)
            e_value *= factor
            e_trace.append((
                _iso(record["ms"]),
                f"{record['offset_s']:.3f}",
                "IN" if in_band else "out",
                f"{factor:.4f}",
                f"{e_value:.4f}",
            ))

    # --- C6: does lambda_0 support the registered E*? ------------------------
    #
    # `lambda_0` is the per-cycle probability of a burst under the null. The
    # registration's own figure is recomputed here rather than assumed, and C6
    # RAISES `E*` when it is too small. `E*` is never lowered.
    lambda_0 = (k_count / e_count) if e_count else None
    e_star = FORWARD_LOCK_E_STAR
    c6_note = "lambda_0 not computable (E = 0)"
    if lambda_0 is not None:
        if lambda_0 >= FORWARD_LOCK_LAMBDA_FLOOR:
            c6_note = (
                f"lambda_0 = {lambda_0:.5f} >= {FORWARD_LOCK_LAMBDA_FLOOR}; "
                f"E* stays {FORWARD_LOCK_E_STAR}"
            )
        elif lambda_0 <= 0.0:
            c6_note = (
                "lambda_0 = 0 (no burst yet): E* CANNOT be computed from it "
                f"and stays at the registered {FORWARD_LOCK_E_STAR}"
            )
        else:
            raised = math.ceil(math.log(0.005) / math.log(1.0 - lambda_0))
            e_star = max(FORWARD_LOCK_E_STAR, raised)
            c6_note = (
                f"lambda_0 = {lambda_0:.5f} < {FORWARD_LOCK_LAMBDA_FLOOR}; "
                f"E* RAISED to {e_star} (never lowered)"
            )

    # --- C3, C4, C5: the loop_rss.jsonl preconditions (section 7) -------------------
    samples, rss_error = _read_rss_samples(args.db)
    aged = _process_start_index(samples)
    aged_stamps = [a[0] for a in aged]

    def age_hours(ms: int) -> Optional[float]:
        """Process age in hours at `ms`, or `None` if it cannot be known.

        **Liveness has to be evidenced, not extrapolated.** The first version
        aged any timestamp against the newest preceding restart marker, so a
        cycle after the last `loop_rss` line inherited an age that grew without
        bound -- a process that died an hour ago scored as one that had been up
        for hours, and C3 passed on cycles for which there was no evidence the
        process was running at all.

        A cycle is aged only if some `loop_rss` sample **at or after it**
        belongs to the same process life. That sample is the evidence.
        """
        idx = bisect.bisect_right(aged_stamps, ms) - 1
        if idx < 0:
            return None
        start = aged[idx][1]
        after = bisect.bisect_left(aged_stamps, ms)
        if after >= len(aged) or aged[after][1] != start:
            return None
        return (ms - start) / 3_600_000.0

    # C3. `A_pre` is the median process age at which the PRE-FIX bursts
    # occurred. "Pre-fix" is before ADR 0091's deploy, not before `T0` --
    # section 2.2's discarded interval sits between them and belongs to neither arm.
    pre_fix_bursts = [f for f in failures if f["ms"] < ADR_0091_DEPLOY_MS]
    pre_fix_ages = sorted(
        h for h in (age_hours(f["ms"]) for f in pre_fix_bursts) if h is not None
    )
    if pre_fix_ages:
        a_pre_h = pre_fix_ages[len(pre_fix_ages) // 2]
        a_pre_why = (
            f"median of {len(pre_fix_ages)} aged pre-fix bursts "
            f"(of {len(pre_fix_bursts)} pre-fix)"
        )
    else:
        a_pre_h = A_PRE_FALLBACK_HOURS
        a_pre_why = (
            f"FALLBACK {A_PRE_FALLBACK_HOURS} h -- no pre-fix burst could be "
            "aged (the lines rolled off, or predate `produced_by`)"
        )

    aged_fast_cycles = [
        ms for ms in fast_after_t0
        if (h := age_hours(ms)) is not None and h >= a_pre_h
    ]
    c3_ok = len(aged_fast_cycles) >= C3_AGED_CYCLES_REQUIRED

    # C4. Median `wal_kb` post-`T0` against the pre-fix 25th percentile.
    # A sample with no `wal_kb` is EXCLUDED, never read as 0: "not measured"
    # and "the WAL is empty" are different states and this file carries both.
    post_wal = sorted(
        s["wal_kb"] for s in samples
        if s["ms"] >= t0 and isinstance(s["wal_kb"], (int, float))
    )
    pre_wal = sorted(
        s["wal_kb"] for s in samples
        if s["ms"] < ADR_0091_DEPLOY_MS and isinstance(s["wal_kb"], (int, float))
    )
    post_wal_median = _quantile(post_wal, 0.5)
    pre_wal_q25 = _quantile(pre_wal, C4_PRE_QUANTILE)
    c4_ok = (
        post_wal_median is not None
        and pre_wal_q25 is not None
        and post_wal_median >= pre_wal_q25
    )

    # C5. Passes per hour, as `loop_rss.jsonl` lines per hour, within +/-25%.
    def lines_per_hour(lo: Optional[int], hi: Optional[int]) -> Optional[float]:
        window = [
            s["ms"] for s in samples
            if (lo is None or s["ms"] >= lo) and (hi is None or s["ms"] < hi)
        ]
        if len(window) < 2:
            return None
        span_h = (window[-1] - window[0]) / 3_600_000.0
        return None if span_h <= 0 else len(window) / span_h

    post_tempo = lines_per_hour(t0, None)
    pre_tempo = lines_per_hour(None, ADR_0091_DEPLOY_MS)
    c5_ok = (
        post_tempo is not None
        and pre_tempo is not None
        and pre_tempo > 0
        and abs(post_tempo - pre_tempo) / pre_tempo <= C5_TEMPO_TOLERANCE
    )

    # A precondition that could not be evaluated is NOT a pass. Each carries
    # its own state so a refusal is reported by name, as section 7 requires.
    def state(ok: bool, computable: bool) -> str:
        if not computable:
            return "NOT COMPUTED"
        return "PASS" if ok else "FAIL"

    c3_computable = bool(aged) and bool(fast_after_t0)
    c4_computable = post_wal_median is not None and pre_wal_q25 is not None
    c5_computable = post_tempo is not None and pre_tempo is not None

    # --- C1: does poll_log span the window? ----------------------------------
    newest_scored = max((r["ms"] for r in k_bursts), default=None)
    c1_ok = bool(stamps) and stamps[0] <= t0 and (
        newest_scored is None or stamps[-1] >= newest_scored
    )

    # --- the verdict, in section 6.3's own order ------------------------------------
    #
    # SIGNATURE PERSISTS is tested FIRST and is the sole verdict exempt from
    # the `E >= E*` gate.
    reached = e_count >= e_star
    if e_value >= FORWARD_LOCK_E_ALARM:
        verdict = "SIGNATURE PERSISTS - ADR 0091 DID NOT CLOSE THE SYMPTOM"
        why = f"E_n = {e_value:.2f} >= {FORWARD_LOCK_E_ALARM} (always-valid)"
    elif not c1_ok:
        verdict = "UNRESOLVED - C1 (poll_log does not span the window)"
        why = "an offset against a stamp hours away measures a hole, not a lock"
    elif k_count >= 2 and not fast_bursts and h_count == 0:
        verdict = "MIRROR RESIDUAL"
        why = (
            f"K = {k_count} >= 2, every burst MIRROR-matched, H = 0; "
            "does not bear on ADR 0091 in either direction"
        )
    elif not reached:
        verdict = f"UNRESOLVED - E = {e_count} < E* = {e_star}"
        why = (
            "section 6.3: no verdict of any kind may be quoted before E >= E*, "
            "except SIGNATURE PERSISTS"
        )
    elif k_count == 0 and e_value < FORWARD_LOCK_E_ALARM:
        # section 6.3 conditions FIX CONFIRMED on EVERY precondition C1-C6. A
        # precondition that could not be evaluated is NOT a pass, and a failed
        # one is named -- "never shortened to UNRESOLVED alone".
        failed = [
            name for name, ok, computable in (
                ("C3", c3_ok, c3_computable),
                ("C4", c4_ok, c4_computable),
                ("C5", c5_ok, c5_computable),
            ) if not (computable and ok)
        ]
        if failed:
            verdict = f"UNRESOLVED - {'/'.join(failed)}"
            why = (
                "E, K and E_n would license FIX CONFIRMED; section 7 does not. "
                "A precondition that is uncomputable is not a pass."
            )
        else:
            verdict = "FIX CONFIRMED ON LIVE EVIDENCE"
            why = (
                f"E = {e_count} >= {e_star}, K = 0, E_n < "
                f"{FORWARD_LOCK_E_ALARM}, and C1-C6 all hold. One-sided exact "
                f"binomial p = (1 - lambda_0)^E"
            )
    else:
        verdict = f"UNRESOLVED - E = {e_count} >= E* with K = {k_count} > 0"
        why = "section 6.3's catch-all: reached exposure, but bursts remain"

    sections = [
        Section(
            title=(
                "forward-lock: THE BOUNDARY AND THE SPLIT -- section 11 capabilities "
                "1 and 2. Registration: docs/measurements/"
                "2026-09-01-forward-lock-instrument-registration.md, committed "
                "in feca481 BEFORE any post-T0 burst was read."
            ),
            columns=("quantity", "value", "reading"),
            rows=[
                ("T0", _iso(t0),
                 "MIN(polled_ms) WHERE endpoint='mirror' -- an in-DB deploy "
                 "marker, not a Fly release timestamp"),
                ("cycles total", len(cycles), "one stamp per cycle"),
                ("cycles >= T0 (FAST)", e_count, "this is E"),
                ("cycles >= T0 (MIRROR)",
                 sum(1 for ms, m in cycles if ms >= t0 and m),
                 "a different code path; excluded from E by section 4"),
                ("median cycle gap C",
                 "UNKNOWN" if median_gap_s is None else f"{median_gap_s:.3f}s",
                 "section 6.3's C, over cycles at or after T0"),
                ("p0 = 3.000 / C",
                 "UNKNOWN" if p0 is None else f"{p0:.5f}",
                 "the null probability a burst lands in the band"),
            ],
            cap=cap,
        ),
        Section(
            title=(
                "forward-lock: THE POPULATION -- bursts assigned by their "
                "MATCHED CYCLE's stamp, never by their own failed_ms (section 2.4)"
            ),
            columns=("class", "n", "reading"),
            rows=[
                ("journal bursts (locked, consecutive=1)", len(failures),
                 "before any T0 rule"),
                ("K -- matched cycle >= T0, collapsed", k_count,
                 "the registered population; bursts sharing a cycle are ONE"),
                ("of which FAST-matched", len(fast_bursts),
                 "the arm E_n runs over"),
                ("H -- FAST and in band "
                 f"[{band_lo:.3f}, {band_hi:.3f}]s", h_count,
                 "the signature ADR 0091 was supposed to remove"),
                ("EXCLUDED -- straddlers (section 2.4)", len(straddlers),
                 "stamped >= T0 but matched to a PRE-T0 cycle; at most one "
                 "can exist, and each is named below"),
                ("EXCLUDED -- pre-T0 or unmatchable", len(unmatched),
                 "section 2.2's discarded interval and any burst before the "
                 "first cycle"),
            ],
            cap=cap,
        ),
    ]

    if straddlers:
        sections.append(Section(
            title=(
                "forward-lock: THE STRADDLERS, NAMED INDIVIDUALLY as section 2.4 "
                "requires -- excluded from both arms"
            ),
            columns=("failed_at", "matched_cycle", "offset_s", "branch"),
            rows=[(
                _iso(r["ms"]), _iso(r["cycle_ms"]),
                f"{r['offset_s']:.3f}", "MIRROR" if r["mirror"] else "FAST",
            ) for r in straddlers],
            cap=cap,
        ))

    if e_trace:
        sections.append(Section(
            title=(
                "forward-lock: THE E-VALUE, in time order -- E_n is a running "
                "product and the SEQUENCE is the object, not the final count"
            ),
            columns=("failed_at", "offset_s", "band", "factor", "E_n"),
            rows=e_trace,
            cap=cap,
        ))

    sections.append(Section(
        title=(
            "forward-lock: PRECONDITIONS -- section 7. A failed one is reported "
            "BY NAME and never shortened to UNRESOLVED alone."
        ),
        columns=("check", "state", "reading"),
        rows=[
            ("C1 poll_log spans the window", "PASS" if c1_ok else "FAIL",
             f"MIN={_iso(stamps[0]) if stamps else 'n/a'} <= T0 and "
             f"MAX={_iso(stamps[-1]) if stamps else 'n/a'} >= newest burst"),
            ("C2 T0 exists", "PASS", _iso(t0)),
            ("C3 restart coverage", state(c3_ok, c3_computable),
             f"A_pre = {a_pre_h:.2f} h ({a_pre_why}); "
             f"{len(aged_fast_cycles)} fast cycles at age >= A_pre, "
             f"need {C3_AGED_CYCLES_REQUIRED}"),
            ("C4 WAL comparability", state(c4_ok, c4_computable),
             f"median wal_kb post-T0 = "
             f"{'UNKNOWN' if post_wal_median is None else f'{post_wal_median:.0f}'}"
             f" vs pre-fix q25 = "
             f"{'UNKNOWN' if pre_wal_q25 is None else f'{pre_wal_q25:.0f}'}"
             f"; n={len(post_wal)}/{len(pre_wal)} samples carrying wal_kb"),
            ("C5 victim tempo", state(c5_ok, c5_computable),
             f"post-T0 = "
             f"{'UNKNOWN' if post_tempo is None else f'{post_tempo:.2f}'}/h vs "
             f"pre-fix = "
             f"{'UNKNOWN' if pre_tempo is None else f'{pre_tempo:.2f}'}/h; "
             f"tolerance +/-{int(C5_TEMPO_TOLERANCE * 100)}%"),
            ("C6 lambda_0 supports E*", "PASS", c6_note),
        ],
        cap=cap,
    ))

    sections.append(Section(
        title=f"forward-lock: THE REGISTERED TEST -- {verdict}",
        columns=("quantity", "value", "note"),
        rows=[
            ("E (fast cycles >= T0)", e_count, f"E* = {e_star}"),
            ("K (bursts)", k_count, "collapsed by matched cycle"),
            ("H (fast, in band)", h_count, "the removed signature"),
            ("E_n", f"{e_value:.4f}",
             f"alarm at {FORWARD_LOCK_E_ALARM}; always-valid, no E* gate"),
            ("VERDICT", verdict, why),
            ("exposure reached", "YES" if reached else "NO",
             "below E*, only SIGNATURE PERSISTS may be quoted"),
        ],
        cap=cap,
    ))
    return sections


def _q_lock_attribution(conn: sqlite3.Connection, args) -> list[Section]:
    """Does each `database is locked` burst land inside a poller cycle?

    The registered analysis of `tasks/NEXT.md` open item 2 -- *"Before
    crediting ADR 0091, attribute the holder"* -- run to the rule fixed in
    `docs/measurements/2026-09-01-lock-holder-attribution-registration.md`
    **before** the join was computed. Read that document before quoting
    anything here; this docstring restates it, it does not amend it.

    The question
    ------------
    ADR 0091 made `poll_portfolio_forever`'s fast branch commit before each
    network call; before it the write lock was held across three Kalshi round
    trips every 300 s. The ADR's argument is a rate, and a rate is not an
    attribution: **nothing had placed one observed failure inside one poller
    window.** This does.

    The join
    --------
    For every burst, the offset from the newest `poll_log.polled_ms` at or
    before it. `polled_ms` is the poller's **cycle start**: `now_ms` is taken
    once at the top of the loop body and handed to every `log_poll_attempt` in
    that cycle, so all of a cycle's rows share one stamp.

    **`poll_log` records no cycle DURATION, only its CADENCE.** The gap
    between consecutive cycle starts is `median_gap_s` below -- the forward-
    lock registration's `C`, whose §11 called an earlier version of this
    sentence out for conflating the two. How long a cycle *ran* is what would
    let an offset read as "inside the cycle" rather than "after its start";
    that is the instrument's limit, and it is why §7 of this registration
    allows no exonerating verdict.

    The unit is the BURST
    ---------------------
    `consecutive_failures == 1`. `Tempo.pass_kind` re-arms a full pass the
    moment one fails, so the failures inside a burst are one draw, not four.
    Section 2 lists every failure so the drop is visible; the test in section 3
    runs on bursts alone.

    The verdicts, and the one that does not exist
    ---------------------------------------------
    - **POLLER IMPLICATED** -- two-sided exact binomial p < 0.01.
    - **NOT ESTABLISHED** -- everything else.

    There is deliberately **no POLLER EXONERATED**. At n ~ 13 and
    p0 = 14/300 = 0.047 the expected count under the null is 0.61, so the
    design can convict and cannot clear: a k of 0 is what the null predicts.
    Section 3 prints that sentence beside the verdict, because the next
    session reads the screen.

    What this does not establish
    ----------------------------
    - **That the poller is the ONLY holder.** `maybe_checkpoint`, the API's
      per-request connections and `store_closing_line` raise the same error,
      and a conviction here does not partition the population between them.
    - **That ADR 0091 worked.** Attribution and efficacy are different claims.
      Efficacy is open item 1 and is separately blocked -- its quiet window
      contains thirteen process restarts, and a restart is this class's own
      documented cure.
    - **Anything if `poll_log` does not span the journal.** A burst scored
      against a cycle stamp that is hours old is not a measurement, so
      section 1 REFUSES rather than reporting a large offset. A poller cycle
      that died before its commit leaves no stamp at all, which inflates a
      neighbouring offset and biases the test **against** H1.
    - **Anything before 2026-08-30**, when the durable journal landed.
    """
    path = Path(args.db).resolve().parent / FAILURE_LOG_NAME
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [
            Section(
                title=(
                    "lock-attribution: THE JOURNAL IS NOT THERE -- this is "
                    "not 'no failures'"
                ),
                columns=("problem", "path", "writer"),
                rows=[(
                    str(exc), str(path),
                    "backend.store.db.record_loop_failure_durably",
                )],
                cap=args.limit,
            )
        ]

    failures: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        if not isinstance(kind, str):
            kind = "diagnosis" if "diagnosis" in entry else "failure"
        if kind != "failure":
            continue
        if "database is locked" not in str(entry.get("error") or ""):
            continue
        if isinstance(entry.get("ms"), int):
            failures.append(entry)

    failures.sort(key=lambda e: e["ms"])
    bursts = [e for e in failures if e.get("consecutive_failures") == 1]

    # Distinct cycle stamps. All four endpoints of one cycle share `now_ms`,
    # so DISTINCT is what turns rows into cycles.
    stamps = [
        int(row[0])
        for row in conn.execute(
            "SELECT DISTINCT polled_ms FROM poll_log ORDER BY polled_ms ASC"
        ).fetchall()
        if row[0] is not None
    ]
    total_rows = conn.execute("SELECT COUNT(*) FROM poll_log").fetchone()[0]

    cap = args.limit
    if not failures:
        return [Section(
            title=(
                "lock-attribution: no `database is locked` failure in the "
                "journal -- nothing to attribute (this is not a verdict about "
                "the poller)"
            ),
            columns=("journal", "lines_read"),
            rows=[(str(path), len(lines))],
            cap=cap,
        )]

    oldest, newest = failures[0]["ms"], failures[-1]["ms"]
    covered = bool(stamps) and stamps[0] <= oldest and stamps[-1] >= newest

    gaps = [
        (b - a) / 1000.0
        for a, b in zip(stamps, stamps[1:])
        if oldest - 3_600_000 <= a <= newest
    ]
    gaps.sort()
    median_gap_s = gaps[len(gaps) // 2] if gaps else None

    preconditions = Section(
        title=(
            "lock-attribution: PRECONDITIONS -- read this before section 3. "
            "The registration is docs/measurements/"
            "2026-09-01-lock-holder-attribution-registration.md, written "
            "before this join was computed."
        ),
        columns=("check", "value", "reading"),
        rows=[
            ("journal failures (locked)", len(failures),
             "the population; the loop_failures TABLE is a floor and is not used"),
            ("bursts (consecutive_failures = 1)", len(bursts),
             "the UNIT; a burst is one draw, its repeats are not"),
            ("poll_log rows", total_rows, "all endpoints, all cycles"),
            ("poll_log distinct cycles", len(stamps),
             "one stamp per cycle; every endpoint in a cycle shares it"),
            ("journal window", f"{_iso(oldest)} .. {_iso(newest)}", ""),
            ("poll_log window",
             f"{_iso(stamps[0]) if stamps else None} .. "
             f"{_iso(stamps[-1]) if stamps else None}", ""),
            ("poll_log spans the journal", covered,
             "FALSE means section 3 REFUSES: an offset measured against a "
             "stamp hours away is not a measurement"),
            ("median cycle gap (s)", median_gap_s,
             "C in the null; read from the data, not assumed to be 300"),
            ("registered window W (s)", LOCK_WINDOW_S,
             "3 round trips at 3 s + BUSY_TIMEOUT_MS 5 s; fixed before looking"),
        ],
        cap=cap,
    )

    # **The poller's cycle DURATION, which the registration said was not
    # recorded.** §4 and §7 both claimed only the cycle START exists, and used
    # that to rule out any exonerating verdict. It is wrong, and an audit on
    # 2026-09-01 caught it: the poller sleeps AFTER its cycle
    # (`portfolio_poll.py`), so the gap to the NEXT stamp is
    # `cycle_wall + 300 + overshoot` and therefore bounds the cycle above.
    #
    # It is the falsifying check, not a confirming one. H1 says a victim's
    # synchronous busy-wait freezes the shared event loop, so on a cycle that
    # produced a failure the poller cannot have committed for ~5 s and its
    # span must run LONG. If a matched cycle instead spans the median, the
    # poller finished normally while something else held the lock, and the
    # attribution moves to a third party that merely happens to be
    # phase-locked to it.
    def _cycle_span_s(ms: Any) -> Optional[float]:
        if not isinstance(ms, int):
            return None
        prior = [t for t in stamps if t <= ms]
        if not prior:
            return None
        after = [t for t in stamps if t > prior[-1]]
        return None if not after else (after[0] - prior[-1]) / 1000.0

    def _offset_s(ms: int) -> Optional[float]:
        prior = [s for s in stamps if s <= ms]
        return None if not prior else (ms - prior[-1]) / 1000.0

    detail = Section(
        title=(
            f"lock-attribution: every locked failure, oldest first "
            f"({len(failures)} of them, {len(bursts)} bursts). `offset_s` is "
            f"from the newest poller CYCLE START at or before it. Only "
            f"is_burst = True rows enter the test; the rest are shown so the "
            f"drop is visible rather than assumed."
        ),
        columns=(
            "iso", "pass_number", "consecutive_failures", "pass_kind",
            "is_burst", "offset_s", "within_W", "cycle_span_s",
        ),
        rows=[
            (
                _iso(e["ms"]), e.get("pass_number"),
                e.get("consecutive_failures"), e.get("pass_kind"),
                e.get("consecutive_failures") == 1,
                _offset_s(e["ms"]),
                None if _offset_s(e["ms"]) is None
                else _offset_s(e["ms"]) <= LOCK_WINDOW_S,
                _cycle_span_s(e["ms"]),
            )
            for e in failures[:cap]
        ],
        truncated=len(failures) > cap,
        cap=cap,
    )

    if not covered or median_gap_s is None or not median_gap_s:
        return [preconditions, detail, Section(
            title=(
                "lock-attribution: REFUSED -- the preconditions in section 1 "
                "are not met, so no verdict is computed. An offset scored "
                "against a cycle stamp outside the journal's window measures "
                "the gap in poll_log, not the poller's lock."
            ),
            columns=("blocker",),
            rows=[
                ("poll_log does not span the journal window",)
                if not covered else
                ("no usable cycle gap: poll_log has fewer than two cycles "
                 "near the journal window",)
            ],
            cap=cap,
        )]

    offsets = [_offset_s(e["ms"]) for e in bursts]
    usable = [o for o in offsets if o is not None]
    n = len(usable)
    k = sum(1 for o in usable if o <= LOCK_WINDOW_S)
    p0 = min(1.0, LOCK_WINDOW_S / median_gap_s)
    expected = n * p0
    p_value = _binom_two_sided(k, n, p0)
    implicated = p_value < LOCK_ALPHA and k > expected

    spans = [
        v for v in (_cycle_span_s(e["ms"]) for e in bursts) if v is not None
    ]
    verdict = "POLLER IMPLICATED" if implicated else "NOT ESTABLISHED"

    return [
        preconditions,
        detail,
        Section(
            title=(
                f"lock-attribution: THE REGISTERED TEST -- {verdict}. "
                f"NO EXONERATING VERDICT EXISTS IN THIS DESIGN: at n = {n} "
                f"and p0 = {p0:.4f} the null EXPECTS {expected:.2f}, so a "
                f"small k is what the null predicts and may NOT be reported "
                f"as 'the poller is cleared'. Only k large enough to give "
                f"p < {LOCK_ALPHA} convicts. Attribution is not efficacy: "
                f"whether ADR 0091 WORKED is open item 1 and is blocked "
                f"separately."
            ),
            columns=("quantity", "value", "note"),
            rows=[
                ("n (bursts scored)", n, "unit = burst, not pass"),
                ("k (offset <= W)", k, f"W = {LOCK_WINDOW_S} s, fixed before looking"),
                ("p0 = W / C", round(p0, 5),
                 f"C = {median_gap_s} s, the observed median cycle gap"),
                ("expected under H0", round(expected, 3), "n * p0"),
                ("two-sided exact binomial p", f"{p_value:.3e}",
                 "exact; a normal approximation is refused at this n"),
                ("threshold", LOCK_ALPHA, "0.01, because this record runs many tests"),
                ("matched-cycle span, min (s)",
                 min(spans) if spans else None,
                 "the poller cycle each burst landed in, bounded above by the "
                 "gap to the next stamp"),
                ("matched-cycle span, median (s)",
                 sorted(spans)[len(spans) // 2] if spans else None,
                 f"compare against the population median of {median_gap_s} s: "
                 f"a matched cycle at the median means the poller finished "
                 f"normally and did NOT hold the lock through the failure"),
                ("VERDICT", verdict,
                 "POLLER IMPLICATED requires p < 0.01 AND k above expectation"),
            ],
            cap=cap,
        ),
    ]
