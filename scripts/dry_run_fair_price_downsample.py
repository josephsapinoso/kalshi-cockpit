"""The `fair_prices` downsample dry run. Reports; **cannot delete**.

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/dry_run_fair_price_downsample.py"

This is the deciding instrument for
`docs/measurements/2026-09-01-preregistration-fair-prices-downsample.md`, and
the **only permitted source of the bytes figure**. Every other figure this
project has for `fair_prices` is a share of a share taken over a 44.4-hour
window whose accounting is an accounting identity rather than a corroboration.

Two structural properties
-------------------------
**It cannot delete.** The connection is opened `mode=ro`, so SQLite itself
raises `attempt to write a readonly database` on any write. That is prerequisite
P6 enforced rather than asserted -- and P6 is *also* checked the crude way,
`COUNT(*)` before and after, because a dry run that only claims to be read-only
is decoration.

**It prints `n` before the effect size**, and the order is registered rather
than chosen: prerequisites first, then counts, then the per-group view and the
largest contributor's share, then T-MECH, and only then the byte estimate. A
harness that prints them in any other order is not this harness.

What this does NOT establish
----------------------------
The registration's section 9 carries eleven of these and is reproduced in full
at the end of every run. The two that must appear here:

- **9.1 -- A downsampled `fair_prices` cannot support any analysis at sub-daily
  resolution, ever again**, for rows past the window.
  `docs/measurements/2026-08-10-sharp-anchoring-census.py:177-191` walks every
  h2h row and matches each `computed_ms` to its own odds-fetch instant; that
  could not be re-run over any downsampled period. The price is paid in advance,
  which is why the rule is registered rather than merely reviewed.
- **9.4 -- It does not establish that deleting rows moves free space at all, and
  this is the most important caveat here.** SQLite returns freed pages to a free
  list, not to the OS; only `VACUUM` gives bytes back, and section 7 of
  `docs/measurements/2026-09-01-the-volume-clock.md` shows that option is
  untested on this box and worth ~0.56 days. `estimated_freed_bytes` is an upper
  bound multiplied by a free-list revolution coefficient in [0, 1] that nothing
  here measures: **if that coefficient is 0, the rule frees no filesystem bytes
  however large the eligible set is.**

And one more, which changes what the rule is *for*: it only reaches rows older
than `retention_days`, so before the 2026-09-17 fill date it can only ever touch
rows written before ~2026-09-03. **It is a bound on long-run growth, not a
rescue for September.**
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.store import fair_price_downsample as fpd  # noqa: E402
from backend.store.db import now_ms  # noqa: E402

DEFAULT_DB = "/data/cockpit.db"

#: Amendment 1 sectionA4's absolute floor under P6b's gate. The perturbation bound is
#: proportional to the insert count, so a run that happened to see zero inserts
#: would have a gate of zero and P6b could never fire -- a check that cannot
#: fail, which is the failure mode P6 itself had in the other direction.
P6B_FLOOR_BYTES = 100_000

REGISTRATION = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "measurements"
    / "2026-09-01-preregistration-fair-prices-downsample.md"
)

#: Section F2's enumeration, as of 2026-09-01. P1 re-runs the grep at the moment
#: the dry run runs and compares against this, because F2 is a fact about a date
#: rather than a promise about the day the rule fires. A file here that is not in
#: the grep is fine (a reader was removed); a file in the grep that is not here
#: is P1 = NO.
F2_KNOWN_READERS = frozenset(
    {
        "backend/api/routes.py",
        "backend/store/manual_orders.py",
        "backend/parlays.py",
        # Writers and comment-only mentions, enumerated by F2 so the grep can be
        # compared against a complete list rather than a partial one.
        "backend/runner.py",
        "backend/engine.py",
        "backend/seed_demo.py",
        "backend/core/ladder.py",
        "backend/odds/client.py",
        "backend/slate.py",
        "backend/store/schema.sql",
        "backend/store/db.py",
        "backend/store/publish.py",
        "backend/store/retention.py",
        # This rule itself, and its switch.
        "backend/store/fair_price_downsample.py",
        "backend/config.py",
    }
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def check_p1() -> tuple[bool, str]:
    """Every module naming `fair_prices` is one F2 already accounted for.

    A reader that is neither bounded-window nor reached through
    `recommendations.fair_price_id` is not protected by D2, and the registration
    is amended rather than worked around. This cannot tell *which* kind a new
    file is -- it flags that a human has to look, which is the honest amount of
    automation for the question.
    """
    root = _repo_root()
    found: set[str] = set()
    for path in (root / "backend").rglob("*"):
        if path.suffix not in {".py", ".sql"} or not path.is_file():
            continue
        try:
            if "fair_prices" in path.read_text(encoding="utf-8"):
                found.add(path.relative_to(root).as_posix())
        except OSError:
            return False, "a file under backend/ could not be read"
    new = sorted(found - F2_KNOWN_READERS)
    if new:
        return False, "modules naming fair_prices that F2 does not list: " + ", ".join(new)
    return True, f"{len(found)} modules, all enumerated by F2"


def check_p2() -> tuple[bool, str]:
    """No second retention rule against this table has landed."""
    root = _repo_root()
    offenders = []
    for path in (root / "backend").rglob("*.py"):
        if path.name == "fair_price_downsample.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return False, "a file under backend/ could not be read"
        if re.search(r"DELETE\s+FROM\s+fair_prices", text, re.I):
            offenders.append(path.relative_to(root).as_posix())
    if offenders:
        return False, "a second rule deletes from fair_prices: " + ", ".join(offenders)
    return True, "no other module deletes from fair_prices"


def check_p4() -> tuple[bool, str]:
    raw = os.getenv("FAIR_PRICE_DOWNSAMPLE_ENABLED", "").strip().lower()
    if raw in {"", "0", "false", "no", "off"}:
        return True, f"FAIR_PRICE_DOWNSAMPLE_ENABLED={raw or '(absent)'}"
    return False, (
        f"FAIR_PRICE_DOWNSAMPLE_ENABLED={raw}: this table may already have been "
        "cut, so the eligible set is smaller than the one the decision is about"
    )


def _section(name: str) -> str:
    """One numbered section of the registration, verbatim.

    Reproduced from the document rather than re-typed, so an amendment reaches
    the output without anyone remembering to update it here.
    """
    text = REGISTRATION.read_text(encoding="utf-8")
    match = re.search(
        rf"^## {re.escape(name)}.*?(?=^## |\Z)", text, re.M | re.S
    )
    return match.group(0).rstrip() if match else f"[section {name} not found]"


def _pct(value: Optional[float]) -> str:
    """`UNKNOWN`, never `0.0%`. An absent fraction is not the number zero."""
    return "UNKNOWN" if value is None else f"{100.0 * value:.2f}%"


def probe_readonly(conn) -> bool:
    """Whether `conn` actually refuses writes. Probed, never assumed.

    Amendment 1 sectionA7: `mode=ro` is set in `main()`, but `report()` accepts any
    connection and the fixture tests already pass it a **writable** one. A
    prerequisite that reads a constant in a different function is not checking
    the object it was handed.

    The probe is a no-op on a writable connection -- a `DELETE` that matches no
    row -- so it is safe against the live database whatever the answer is.

    **Scoped to a SAVEPOINT rather than rolled back.** The first version called
    `conn.rollback()`, which is not a no-op: on a writable connection it
    discards whatever uncommitted work the caller already had open. A probe
    that can destroy the state it is inspecting is worse than no probe, and a
    test caught it doing exactly that. `ROLLBACK TO` undoes the probe and
    nothing else; `RELEASE` then drops the savepoint without touching the
    enclosing transaction.
    """
    try:
        conn.execute("SAVEPOINT _p6_probe")
    except sqlite3.OperationalError:
        # A read-only connection refuses even to open the savepoint on some
        # builds; that is itself the answer.
        return True
    try:
        conn.execute("DELETE FROM fair_prices WHERE 0")
    except sqlite3.OperationalError:
        writable = False
    else:
        writable = True
    finally:
        for statement in ("ROLLBACK TO _p6_probe", "RELEASE _p6_probe"):
            try:
                conn.execute(statement)
            except sqlite3.Error:
                pass
    return not writable


def report(
    conn,
    *,
    now: int,
    retention_days: int,
    expect_readonly: bool = False,
) -> tuple[fpd.DownsamplePlan, list[str]]:
    started = time.monotonic()
    before = conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0]
    plan = fpd.plan(conn, now=now, retention_days=retention_days)
    after = conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0]
    delta = after - before
    readonly = probe_readonly(conn)
    elapsed = time.monotonic() - started

    p1_ok, p1_why = check_p1()
    p2_ok, p2_why = check_p2()
    p3_ok = plan.closing_lines_rows > 0 and plan.scored_event_tickers > 0
    p4_ok, p4_why = check_p4()
    p5_value = plan.p5_no_commence_fraction
    p5_ok = p5_value is not None and p5_value <= fpd.P5_MAX_NO_COMMENCE_FRACTION
    # Amendment 1 sectionA4: the pass condition is "no row was REMOVED", plus a
    # probe that the connection this function was handed actually refuses
    # writes. The registered `before == after` tested a race -- a report that
    # finished between two recorder commits answered YES, one that straddled
    # one answered NO, and neither says anything about whether this instrument
    # deleted a row.
    p6_no_removal = after >= before
    p6_ok = p6_no_removal and (readonly or not expect_readonly)

    out = [
        f"# fair_prices downsample DRY RUN  (retention_days={retention_days})",
        "",
        "## 1. Prerequisites -- if any is NO, this result is void",
        f"  P1 readers still covered by D1/D2   {'YES' if p1_ok else 'NO'}  {p1_why}",
        f"  P2 no second retention rule         {'YES' if p2_ok else 'NO'}  {p2_why}",
        f"  P3 closing_lines resolves           {'YES' if p3_ok else 'NO'}  "
        f"{plan.closing_lines_rows:,} rows reaching "
        f"{plan.scored_event_tickers:,} distinct kalshi_markets.event_ticker",
        f"  P4 the rule is not already armed    {'YES' if p4_ok else 'NO'}  {p4_why}",
        f"  P5 anchor computable for >=90%      {'YES' if p5_ok else 'NO'}  "
        f"no commence_ms on {_pct(p5_value)} of the D1&D2&D3 rows "
        f"(threshold {_pct(fpd.P5_MAX_NO_COMMENCE_FRACTION)}); those rows are KEPT",
        f"  P6 no row was removed               {'YES' if p6_ok else 'NO'}  "
        f"COUNT(*) before {before:,}, after {after:,}, delta {delta:+,}"
        f"; connection refuses writes: {'YES' if readonly else 'NO'}"
        f"{'' if expect_readonly else ' (not required: expect_readonly=False)'}"
        f"; report took {elapsed:.1f}s",
        "",
        "## 2. n, before any effect size",
        f"  total_rows              {plan.total_rows:>12,}",
        f"  eligible_rows           {plan.eligible_rows:>12,}",
        f"  eligible_row_fraction   {_pct(plan.eligible_row_fraction):>12}"
        "   (a census, not a sample: exactly zero sampling error)",
        "",
        "  what each condition keeps, individually (overlapping, NOT additive)",
    ]
    for key, value in plan.per_condition.items():
        out.append(f"    {key:<28}{value:>12,}")
    out += [
        "",
        "## 3. The parts, because a pooled number is not a finding",
        f"  distinct link_id contributing   {len(plan.per_link):>8,}",
        f"  largest single contributor      {_pct(plan.largest_link_share):>8}",
    ]
    for link_id, rows in plan.per_link[:10]:
        share = rows / plan.eligible_rows if plan.eligible_rows else None
        out.append(f"    link_id {link_id:<10} {rows:>10,}  {_pct(share)}")
    if len(plan.per_link) > 10:
        out.append(f"    ... and {len(plan.per_link) - 10:,} more")

    t_mech_ok = plan.t_mech is not None and plan.t_mech >= fpd.T_MECH_THRESHOLD
    out += [
        "",
        "## 4. T-MECH -- does D4 actually do the work the premise claims?",
        f"  rows passing D1 & D2 & D3   {plan.d123_rows:>12,}",
        f"  of those, removed by D4     {_pct(plan.t_mech):>12}"
        f"   (threshold {_pct(fpd.T_MECH_THRESHOLD)})  "
        f"{'PASS' if t_mech_ok else 'FAIL -> PREMISE REFUTED'}",
        "",
        "## 5. The estimate, and it is the only estimator here",
        "  ESTIMATE "
        + (
            "UNKNOWN"
            if plan.estimated_freed_bytes is None
            else f"{plan.estimated_freed_bytes:,}"
        )
        + " bytes (uniform bytes/row across table + both indexes; see S5)",
        f"  family measured on live 2026-09-01: {fpd.FAIR_PRICE_FAMILY_BYTES:,} bytes",
        "",
        "## 6. The verdict, against a threshold fixed before any row was counted",
        f"  threshold   {fpd.ARMING_THRESHOLD_BYTES:,} bytes"
        "   = 2.00 days at 161.40 MB/day",
        f"  VERDICT     {plan.verdict}",
    ]

    # Amendment 1 sectionA4/sectionA6: P6b, the margin check. It can only ever VOID a
    # run, never rescue one -- concurrent inserts perturb `eligible_row_fraction`
    # and therefore the byte estimate, and a decision resting inside that
    # perturbation is not a decision. Printed rather than left in prose, which
    # is the state P6 itself was in when it broke.
    if plan.estimated_freed_bytes is None:
        out.append(
            "  P6b         NOT COMPUTABLE (estimated_freed_bytes is UNKNOWN)"
        )
    else:
        perturbation = (
            math.ceil(delta / before * fpd.FAIR_PRICE_FAMILY_BYTES)
            if before and delta > 0
            else 0
        )
        gate = max(perturbation, P6B_FLOOR_BYTES)
        margin = abs(plan.estimated_freed_bytes - fpd.ARMING_THRESHOLD_BYTES)
        out += [
            f"  P6b         perturbation {perturbation:,} B, gate {gate:,} B, "
            f"margin {margin:,} B  ->  {'PASS' if margin > gate else 'FIRES'}",
        ]
        if margin <= gate:
            out.append(
                "  ** P6b FIRES: UNRESOLVED - MARGIN INSIDE THE CONCURRENCY "
                "PERTURBATION. This run does not decide. **"
            )
    if not all((p1_ok, p2_ok, p3_ok, p4_ok, p5_ok, p6_ok)):
        out.append(
            "  ** A PREREQUISITE ANSWERED NO. The verdict above is VOID and the "
            "registration is amended rather than worked around. **"
        )
    out += ["", _section("6. The decision rule, with the multiplicity already counted")]
    out += ["", _section("9. What this cannot establish — drafted before the run")]
    return plan, out


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Dry run of the registered fair_prices downsample. Opens the "
            "database read-only and cannot delete anything."
        )
    )
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument(
        "--retention-days",
        type=int,
        default=fpd.REGISTERED_RETENTION_DAYS,
        help=(
            "the registered arming value is "
            f"{fpd.REGISTERED_RETENTION_DAYS}; any other value is a sensitivity "
            "sweep and cannot arm anything"
        ),
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help=(
            "additionally run the registered sensitivity set "
            f"{fpd.SENSITIVITY_RETENTION_DAYS}, after the deciding run"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    # The registration's sections are reproduced verbatim and contain `∧`, `—`
    # and `≥`. The live box is UTF-8; a Windows console is cp1252 and raises
    # part-way through printing, which would truncate the output at a random
    # point and leave a partial verdict on screen. Replace rather than raise:
    # a mangled character is a cosmetic loss, a half-printed report is a wrong
    # answer that looks like a whole one.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    if not os.path.exists(args.db):
        print(f"no such database: {args.db}", file=sys.stderr)
        return 2

    # `mode=ro`: SQLite refuses every write. This is P6 enforced rather than
    # promised, and it is the one line that makes this file reviewable once.
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        # Amendment 1 sectionA12(4): pin ONE read snapshot for the whole report, so
        # `total_rows`, `eligible_rows`, `d123_rows` and the per-`link_id` view
        # all describe one state of the database rather than nine.
        #
        # **Attempted, not assumed.** A read transaction against a `mode=ro`
        # WAL database has platform-dependent shared-memory requirements, and
        # the amendment requires that failure be recorded rather than papered
        # over -- so the fallback is the unpinned read and the output says which
        # one happened. `isolation_level = None` puts pysqlite in autocommit, so
        # BEGIN is ours to issue and is not silently wrapped.
        conn.isolation_level = None
        pinned = False
        try:
            conn.execute("BEGIN")
            pinned = True
        except sqlite3.Error:
            pinned = False

        plan, lines = report(
            conn,
            now=now_ms(),
            retention_days=args.retention_days,
            expect_readonly=True,
        )
        lines.insert(
            1,
            "  read snapshot: PINNED (one consistent state)"
            if pinned
            else "  read snapshot: NOT PINNED -- the census below reads nine "
            "states; P6's pass condition stays `after >= before`",
        )
        payload: dict[str, Any] = {"deciding_run": plan.as_dict(), "sensitivity": []}
        if args.sweep:
            for days in fpd.SENSITIVITY_RETENTION_DAYS:
                sweep_plan, sweep_lines = report(
                    conn, now=now_ms(), retention_days=days
                )
                payload["sensitivity"].append(sweep_plan.as_dict())
                lines += [
                    "",
                    "=" * 72,
                    f"SENSITIVITY - DELETES NOTHING - CANNOT ARM  ({days} days)",
                    "=" * 72,
                ] + sweep_lines
    finally:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        conn.close()

    print(json.dumps(payload, indent=2) if args.json else "\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
