"""Run the joint bound over the recommendation record, and report all 14 items.

Governed by `docs/measurements/2026-08-10-preregistration-joint-bound.md`. This
script is the extraction (§S1) and the report (§S2); every quantity it prints is
computed by `backend/analysis/joint_bound.py`, which is the tested kernel. No
statistic, bucket edge, population or output field is chosen here.

    .venv\\Scripts\\python.exe scripts\\run_joint_bound.py
    .venv\\Scripts\\python.exe scripts\\run_joint_bound.py --from-cache

The pull is cached to `docs/measurements/2026-08-10-joint-bound-pull.json` so the
analysis is re-cuttable without re-pulling. **The token is never written to that
file, never logged and never printed** -- it is read from the repo-root `.env`,
handed to one form POST, and held only in memory. `configure_logging()` is
called before any client is constructed, because `httpx` logs full request URLs
at INFO and this repo has already put a working credential into a transcript
that way.

What this harness does NOT establish
------------------------------------
- **If the bound returns 0, the honest finding is "Kalshi is not mispriced
  relative to a consensus it may itself lead."** It is **NOT** "no edge exists
  at Kalshi." `tasks/lessons.md` already suspects Kalshi is the sharp side, in
  which case "Kalshi versus devigged sportsbook consensus" is close to empty
  **by construction** -- the comparison would be Kalshi against a lagging shadow
  of itself, and finding nothing there is a fact about the instrument's
  geometry, not about the venue. Any write-up containing the broader sentence is
  defective and must be corrected. (Registration §10, first bullet, and item 14
  of the report reproduces the rest of §10 verbatim from the registration file
  rather than paraphrasing it here.)
- **A newest-1,000 slice run proves nothing about the table.** The registration's
  D-gate forbids writing an ADR, a CLAUDE.md edit or a line closure from one,
  and §10's last bullet records that labelling a slice has already failed to
  stop it being quoted. If this script prints `PROVISIONAL SLICE`, the numbers
  below are a property of 1,000 rows and of nothing else.
- **A zero fee is not a realisable state**, so the primary's `K` may never be
  quoted as an estimate of how many rows would be actionable in practice.
- **`D_swept = 16.7` is a maximum over a *swept* space, not over all lines**
  (Amendment 1 §A5). The sweep is two-outcome, proportional-overround,
  favourite <= 99%, hold <= 20%. Three-way markets, non-proportional vig
  allocation -- which is what real books actually do to longshots -- and holds
  above 20% are outside it. `D* > 16.7` means above every spread **that sweep**
  could produce, not above every conceivable devig spread.
- **The bound is a census of rows already written**, downstream of discovery and
  of `persist_if_changed`'s movement-only write rule. A market never polled
  contributes no row and cannot clear the bound.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.analysis import joint_bound as jb  # noqa: E402
from backend.core.ev import edge_after_fees_tenths  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "https://kalshi-cockpit.fly.dev"
CACHE_PATH = ROOT / "docs" / "measurements" / "2026-08-10-joint-bound-pull.json"
REGISTRATION_PATH = (
    ROOT / "docs" / "measurements" / "2026-08-10-preregistration-joint-bound.md"
)
PAGE_SIZE = 1000

# §S2's two D-gate verdicts. There is no third.
WHOLE_TABLE = "WHOLE TABLE"
PROVISIONAL_SLICE = "PROVISIONAL SLICE"


# ---------------------------------------------------------------------------
# Output. Provisional runs carry §S1's label on every line.
# ---------------------------------------------------------------------------


class Report:
    """Collects the report, prefixing every line when the run is provisional.

    §S1 requires *every output* of a slice run to carry the label, not just the
    header -- §10's last bullet records that a label at the top has already
    failed to travel with the number it qualifies. A per-line prefix is ugly and
    that is the intended cost: a reader cannot copy one line out of it without
    copying the disclaimer.
    """

    def __init__(self, provisional: bool) -> None:
        self.prefix = f"{jb.PROVISIONAL_PREFIX} | " if provisional else ""
        self.lines: list[str] = []

    def __call__(self, line: str = "") -> None:
        text = f"{self.prefix}{line}".rstrip()
        self.lines.append(text)
        print(text)

    def rule(self, title: str) -> None:
        self("")
        self("=" * 78)
        self(title)
        self("=" * 78)


def fmt(value: Optional[float], places: int = 1) -> str:
    """`None` prints as `None`, never as 0. The repo's rule, in the formatter."""
    if value is None:
        return "None"
    return f"{value:+.{places}f}" if places else str(value)


def fmt_plain(value: Optional[float], places: int = 1) -> str:
    return "None" if value is None else f"{value:.{places}f}"


# ---------------------------------------------------------------------------
# §S1 -- the extraction
# ---------------------------------------------------------------------------


def read_token(env_path: Path) -> Optional[str]:
    """The live `APP_AUTH_TOKEN` from `.env`. Returned, never logged or printed."""
    if not env_path.exists():
        return None
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("APP_AUTH_TOKEN="):
            value = raw.split("=", 1)[1].strip().strip("'\"")
            return value or None
    return None


async def open_session(client: httpx.AsyncClient, token: Optional[str]) -> str:
    """Exchange the token for the session cookie. Returns a describable status.

    The cookie is `<expiry>.<hmac>` keyed on the token; it proves the holder knew
    the token and cannot be replayed as one (`frontend/src/lib/session.ts`). The
    token itself is passed once, as form data, and is not retained.
    """
    if not token:
        return "no APP_AUTH_TOKEN in .env -- proceeding unauthenticated"
    response = await client.post("/session", data={"token": token})
    if response.status_code == 404:
        return "instance has no authentication configured (demo)"
    if "cockpit_session" in client.cookies:
        return f"session cookie issued (HTTP {response.status_code})"
    return (
        f"NO session cookie issued (HTTP {response.status_code}). The token was "
        f"rejected or the route is absent."
    )


async def fetch_page(
    client: httpx.AsyncClient, *, offset: int, max_id: Optional[int]
) -> dict:
    params: dict[str, Any] = {"limit": PAGE_SIZE, "offset": offset}
    if max_id is not None:
        params["max_id"] = max_id
    response = await client.get("/api/ledger", params=params)
    response.raise_for_status()
    return response.json()


async def pull(base_url: str, token: Optional[str]) -> dict:
    """§S1's whole-table pull, with the runtime fallback to the slice.

    The deployed build is detected rather than assumed: if page 0 comes back
    without `newest_id`, the route predates the paging contract, there is no pin
    to be had, and §P1's provisional clause applies. Guessing from a version
    string or a deploy date would be a claim about the machine made from the
    repository, which is the exact confusion `runtime-realist` exists to catch.
    """
    async with httpx.AsyncClient(
        base_url=base_url, timeout=60.0, follow_redirects=False
    ) as client:
        session_status = await open_session(client, token)
        page0 = await fetch_page(client, offset=0, max_id=None)

        supports_paging = page0.get("newest_id") is not None
        if not supports_paging:
            return {
                "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
                "base_url": base_url,
                "session_status": session_status,
                "d_gate": PROVISIONAL_SLICE,
                "supports_paging": False,
                "pages": [page0],
            }

        max_id = int(page0["newest_id"])
        pages = [page0]
        offset = int(page0["returned"])
        total = int(page0["total"])
        while offset < total:
            page = await fetch_page(client, offset=offset, max_id=max_id)
            pages.append(page)
            total = int(page["total"])
            returned = int(page["returned"])
            if returned == 0:
                break
            offset += returned

        return {
            "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
            "base_url": base_url,
            "session_status": session_status,
            "d_gate": WHOLE_TABLE,
            "supports_paging": True,
            "max_id": max_id,
            "pages": pages,
        }


# ---------------------------------------------------------------------------
# §S2 -- the report
# ---------------------------------------------------------------------------


def shortfall_block(
    out: Report,
    *,
    variant: str,
    population: str,
    rows: Sequence[jb.Row],
    shortfalls: Sequence[float],
    with_ladder: bool = True,
) -> None:
    """§6's fixed form, in this order and this shape. Not re-worded per run."""
    out("")
    out(f"JOINT BOUND — {variant}")
    out(
        f"population {population}     rows N = {len(rows)}"
        f"    clusters G = {jb.cluster_count(rows)}"
    )
    out("")

    if with_ladder:
        ladder = jb.k_ladder(rows)
        for points, _ in jb.DELTA_LADDER:
            k, g = ladder[points]
            tail = (
                "      [reachability rung — see §5]"
                if points == jb.REACHABILITY_DELTA_POINTS
                else ""
            )
            # §6's template aligns the `=` across rungs of different widths.
            out(f"  K(δ={points:.2f} pts)".ljust(17) + f"= {k} rows / {g} games{tail}")
        out("")

    if not rows:
        out("  NEAREST ROW      none — the population is empty")
        out("  NEAREST GAME     none — the population is empty")
        out("  S over rows      none")
        out("  S per-cluster    none")
        counts = jb.shortfall_histogram([])
    else:
        paired = sorted(zip(shortfalls, rows), key=lambda pair: pair[0])
        best_s, best_row = paired[0]
        out(
            f"  NEAREST ROW      S = {fmt(best_s)} tenths = "
            f"{fmt(best_s / 10.0, 2)} c short"
        )
        out(
            f"                   ticker {best_row.ticker}  side {best_row.side}  "
            f"ask {best_row.ask_tenths}  fair {best_row.fair_probability}  "
            f"created_ms {best_row.created_ms}"
        )
        out(
            f"                   cluster {jb.cluster_key(best_row.ticker, best_row.event_ticker)}"
            f"   suppressed_reason {best_row.suppressed_reason}"
        )

        per_cluster: dict[str, list[float]] = {}
        for s, row in paired:
            key = jb.cluster_key(row.ticker, row.event_ticker) or "<none>"
            per_cluster.setdefault(key, []).append(s)
        cluster_minima = {k: min(v) for k, v in per_cluster.items()}
        best_cluster = min(cluster_minima, key=lambda k: cluster_minima[k])
        out(
            f"  NEAREST GAME     best row in its cluster: "
            f"S = {fmt(cluster_minima[best_cluster])} tenths = "
            f"{fmt(cluster_minima[best_cluster] / 10.0, 2)} c short"
        )
        out(
            f"                   cluster {best_cluster}   "
            f"rows in cluster {len(per_cluster[best_cluster])}"
        )

        block = jb.percentile_block(shortfalls)
        # Amendment 1 §A3: `D*` is a REQUIRED derived print, on the line
        # immediately above `S`'s minimum, beside both verdict thresholds and
        # beside §C4's knob ceiling. It is a *reading* of the `S` distribution,
        # not a second estimand -- `S` stays primary. Points, because the
        # verdict compares the record's requirement against the devig knob's
        # reach and the knob is denominated in points.
        d_star = jb.d_star_points(shortfalls)
        out(
            f"  D* = min(S)/10   {fmt_plain(d_star, 3)} points   "
            f"[thresholds: D_realistic {jb.D_REALISTIC_POINTS}, "
            f"D_swept {jb.D_SWEPT_POINTS}; "
            f"whole fee+maker knob ceiling {jb.KNOB_CEILING_POINTS} pts (§C4)]"
        )
        if d_star is not None and d_star > 0:
            out(
                f"                   the knob is worth at most "
                f"{jb.KNOB_CEILING_POINTS} points against a requirement of "
                f"{d_star:.3f} — a factor of {d_star / jb.KNOB_CEILING_POINTS:.2f}"
            )
        out(
            "  S over rows      "
            + "  ".join(f"{k} {fmt(v)}" for k, v in block.items())
        )
        cluster_block = jb.percentile_block(cluster_minima.values())
        out(
            "  S per-cluster    minimum per cluster, then: "
            + "  ".join(
                f"{k} {fmt(cluster_block[k])}"
                for k in ("min", "p10", "p50", "p90", "max")
            )
        )
        counts = jb.shortfall_histogram(shortfalls)

    labels = [
        "(-inf,0]", "(0,10]", "(10,20.3]", "(20.3,50]",
        "(50,100]", "(100,200]", "(200,400]", "(400,inf)",
    ]
    values = [counts[cell] for cell in jb.SHORTFALL_CELLS]
    out(
        "  histogram        "
        + "  ".join(f"{label} {value}" for label, value in zip(labels[:4], values[:4]))
    )
    out(
        "                   "
        + "  ".join(f"{label} {value}" for label, value in zip(labels[4:], values[4:]))
    )
    out(f"  VERDICT READING  {jb.verdict(jb.d_star_points(shortfalls)) or 'none — empty population'}")


def composition_table(out: Report, rows: Sequence[jb.Row]) -> None:
    """§S2 item 3. Rows and clusters, side by side, on every stratum."""
    keys: dict[tuple, list[jb.Row]] = {}
    for row in rows:
        key = (
            "unscored" if row.clv_horizon_hours is None else f"{row.clv_horizon_hours:g}",
            jb.bankroll_era(row.created_ms),
            jb.series_prefix(row.ticker),
            row.strategy_config_version,
        )
        keys.setdefault(key, []).append(row)
    out(
        f"  {'horizon':>9}  {'era':>8}  {'series':<22}  {'config':<10}  "
        f"{'rows':>6}  {'clusters':>8}"
    )
    for key in sorted(keys, key=lambda k: tuple(str(x) for x in k)):
        members = keys[key]
        horizon, era, series, config = key
        out(
            f"  {horizon:>9}  {era:>8}  {str(series):<22}  {str(config):<10}  "
            f"{len(members):>6}  {jb.cluster_count(members):>8}"
        )

    sizes: dict[str, int] = {}
    for row in rows:
        key_s = jb.cluster_key(row.ticker, row.event_ticker) or "<none>"
        sizes[key_s] = sizes.get(key_s, 0) + 1
    if sizes:
        largest = max(sizes, key=lambda k: sizes[k])
        block = jb.percentile_block(float(v) for v in sizes.values())
        out("")
        out(
            "  rows per cluster  "
            + "  ".join(f"{k} {fmt_plain(v, 1)}" for k, v in block.items())
        )
        out(
            f"  largest cluster   {largest}  {sizes[largest]} rows  "
            f"= {100.0 * sizes[largest] / len(rows):.1f}% of the population"
        )


def _slice_section(text: list[str], heading_prefix: str) -> list[str]:
    start = next(
        (i for i, line in enumerate(text) if line.startswith(heading_prefix)), None
    )
    if start is None:
        return [f"{heading_prefix} not found in the registration file."]
    end = next(
        (i for i in range(start + 1, len(text)) if text[i].startswith("## ")),
        len(text),
    )
    return text[start:end]


def section_10_verbatim() -> list[str]:
    """§S2 item 14, plus §A5's caveat, which Amendment 1 appends to §10.

    Sliced out of the registration file at run time rather than transcribed.
    A paraphrase of the caveats is the one thing in this report that must not
    drift, because the caveats are what stop the number being over-read -- and
    §10's own last bullet records that labelling has already failed once.
    """
    if not REGISTRATION_PATH.exists():
        return [
            "REGISTRATION FILE NOT FOUND — §10 cannot be reproduced verbatim, so "
            "this run is incomplete per §S2 item 14."
        ]
    text = REGISTRATION_PATH.read_text(encoding="utf-8").splitlines()
    return (
        _slice_section(text, "## §10.")
        + ["", "--- Amendment 1 §A5, appended to §10 ---", ""]
        + _slice_section(text, "## A5.")
    )


def analyse(pull_data: dict) -> None:
    provisional = pull_data["d_gate"] == PROVISIONAL_SLICE
    out = Report(provisional)
    pages = pull_data["pages"]
    payload_rows = [row for page in pages for row in page["rows"]]
    rows = [jb.Row.from_ledger_payload(r) for r in payload_rows]

    # -- 1. The frame -------------------------------------------------------
    out.rule("1. THE FRAME")
    out(f"  pulled_at_utc          {pull_data['pulled_at_utc']}")
    out(f"  base_url               {pull_data['base_url']}")
    out(f"  session                {pull_data['session_status']}")
    out(f"  total                  {pages[-1].get('total')}")
    out(f"  returned (summed)      {sum(int(p['returned']) for p in pages)}")
    out(f"  offset (last page)     {pages[-1].get('offset')}")
    out(f"  max_id                 {pull_data.get('max_id')}")
    out(f"  newest_id              {pages[0].get('newest_id')}")
    out(f"  pages                  {len(pages)}")

    total = pages[-1].get("total")
    ids = [r["id"] for r in payload_rows]
    if pull_data["supports_paging"]:
        last_offset = int(pages[-1]["offset"])
        last_returned = int(pages[-1]["returned"])
        check_a = (last_offset + last_returned) == int(total)
        check_b = len(set(ids)) == int(total)
        out("")
        out("  P2 assertions, as executed:")
        out(
            f"    offset + returned == total   "
            f"{last_offset} + {last_returned} == {total}   -> {check_a}"
        )
        out(
            f"    len(set(ids)) == total       "
            f"{len(set(ids))} == {total}                 -> {check_b}"
        )
        if not (check_a and check_b):
            out("    A pull failing either is DISCARDED, not patched (§P2).")
    else:
        out("")
        out("  P2 assertions: NOT APPLICABLE — the deployed route serves no")
        out("  `newest_id`, so there is no pin and no paged pull to verify.")
        out(f"    distinct ids in the slice    {len(set(ids))} of {len(ids)}")

    created = [r.created_ms for r in rows if r.created_ms is not None]
    if created:
        oldest = min(created)
        ties = sum(1 for c in created if c == oldest)
        out("")
        out(
            f"  boundary-tie count     {ties} rows share the oldest created_ms "
            f"({oldest}) in this pull"
        )
        out(
            "                         a split boundary group makes even the "
            "slice non-reproducible at its edge (§S1)"
        )
    out("")
    out(f"  D-GATE VERDICT         {pull_data['d_gate']}")
    if provisional:
        out(
            "                         no ADR, no CLAUDE.md edit and no line "
            "closure may be written from this run (§7)"
        )

    # -- 2. The population ladder ------------------------------------------
    out.rule("2. THE POPULATION LADDER")
    pops = jb.populations(rows)
    for name in jb.POPULATION_NAMES:
        members = pops[name]
        out(
            f"  {name}   n_rows = {len(members):>6}   "
            f"G = {jb.cluster_count(members):>5}"
        )
    violations = jb.nesting_violations(pops)
    out("")
    out(f"  nesting invariant P3 ⊆ P1, P2 ⊆ P0 asserted -> {not violations}")
    for violation in violations:
        out(f"    VIOLATION: {violation}")

    excluded: dict[str, int] = {}
    for row in rows:
        reason = jb.exclusion_reason(row)
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
    out("")
    out("  excluded rows, by reason (§2):")
    if not excluded:
        out("    none")
    for reason, count in sorted(excluded.items()):
        out(f"    {reason:<24} {count}")

    p0 = pops["P0"]

    # -- 3. The composition -------------------------------------------------
    out.rule("3. THE COMPOSITION, BEFORE ANY COUNT")
    composition_table(out, p0)

    # -- 4. Cluster-key integrity ------------------------------------------
    out.rule("4. CLUSTER-KEY INTEGRITY (Lane A §4 defect 1)")
    prefixes = sorted({jb.series_prefix(r.ticker) or "<none>" for r in p0})
    out(f"  distinct series prefixes ({len(prefixes)}): {', '.join(prefixes)}")
    by_suffix: dict[str, set] = {}
    for row in p0:
        suffix = jb.event_suffix(row.ticker)
        if suffix:
            by_suffix.setdefault(suffix, set()).add(jb.series_prefix(row.ticker))
    shared = {s: p for s, p in by_suffix.items() if len(p) > 1}
    out(
        f"  <DATE+TEAMS> suffixes under more than one prefix: {len(shared)}"
    )
    for suffix, prefixes_seen in sorted(shared.items())[:20]:
        out(f"    {suffix}: {sorted(prefixes_seen)}")
    if shared:
        out("    a non-zero count here means G is INFLATED (§3, §10)")
    unclustered = sum(1 for r in p0 if not r.event_ticker)
    out(
        f"  unclustered rows (no event_ticker on the payload): {unclustered} "
        f"of {len(p0)}"
    )
    out(
        "    over HTTP only `ticker` is available, so every key here comes from "
        "the Lane A §4 fallback"
    )

    # -- 5. PRIMARY shortfall blocks ---------------------------------------
    out.rule("5. PRIMARY SHORTFALL BLOCKS")
    shortfalls_by_pop: dict[str, list[float]] = {}
    ladders: dict[str, dict[float, tuple[int, int]]] = {}
    for name in jb.POPULATION_NAMES:
        members = pops[name]
        shortfalls = [jb.primary_shortfall_tenths(r) for r in members]
        shortfalls_by_pop[name] = shortfalls
        ladders[name] = jb.k_ladder(members)
        shortfall_block(
            out,
            variant="PRIMARY dominating, stacked, fee=0",
            population=name,
            rows=members,
            shortfalls=shortfalls,
        )

    out("")
    k0 = ladders["P0"][0.00][0]
    nearest_row = min(shortfalls_by_pop["P0"]) if p0 else None
    per_cluster_min: dict[str, float] = {}
    for s, row in zip(shortfalls_by_pop["P0"], p0):
        key = jb.cluster_key(row.ticker, row.event_ticker) or "<none>"
        per_cluster_min[key] = min(per_cluster_min.get(key, math.inf), s)
    nearest_game = min(per_cluster_min.values()) if per_cluster_min else None
    out("HEADLINE (§6, fixed wording; K is read at the δ=0.00 rung):")
    out(
        f"  {k0} rows of {len(p0)} clear the joint bound. The nearest row is "
        f"{fmt_plain(None if nearest_row is None else nearest_row / 10.0, 2)}c "
        f"short of a fee-free ask at the loosest devig reading available to "
        f"this project; the nearest game's best row is "
        f"{fmt_plain(None if nearest_game is None else nearest_game / 10.0, 2)}c "
        f"short."
    )

    # -- 6. The reachability rung ------------------------------------------
    out.rule("6. THE REACHABILITY RUNG")
    k_reach = ladders["P0"][jb.REACHABILITY_DELTA_POINTS][0]
    out(f"  K(δ={jb.REACHABILITY_DELTA_POINTS:.2f}) on P0 = {k_reach}")
    if k_reach == 0:
        out(
            "  K(10.00) = 0 -> the harness is treated as SUSPECTED DEFECTIVE and "
            "NO BRANCH IS DECLARED (§7),"
        )
        out(
            "  until it is shown to return K >= 1 on a constructed row whose ask "
            "sits one tenth below its fair."
        )
        out(
            "  That construction is asserted in "
            "tests/test_joint_bound.py::TestAnAskOneTenthBelowItsFairClears."
        )
    else:
        out("  reachable — the rung the ladder was built to reach is non-empty.")

    # -- 7. Branch Z / Z-NARROW / Branch N ----------------------------------
    out.rule("7. BRANCH DECLARATION")

    # §A4's ARGMIN INTEGRITY precondition, checked BEFORE any branch. min(S) is
    # decided by a single row, and a corrupt row understates closure while a
    # missing row overstates it -- §P2's id check is the only defence against
    # the second, which is why the paging pin is a prerequisite and not a
    # nicety.
    out("  PRECONDITION — ARGMIN INTEGRITY (§A4)")
    if not p0:
        out("    no rows; there is no argmin to check")
        d_star = None
    else:
        paired = sorted(zip(shortfalls_by_pop["P0"], p0), key=lambda pair: pair[0])
        argmin_s, argmin_row = paired[0]
        out(
            f"    ticker {argmin_row.ticker}   side {argmin_row.side}   "
            f"ask {argmin_row.ask_tenths}   fair {argmin_row.fair_probability}"
        )
        out(
            f"    created_ms {argmin_row.created_ms}   "
            f"cluster {jb.cluster_key(argmin_row.ticker, argmin_row.event_ticker)}   "
            f"suppressed_reason {argmin_row.suppressed_reason}"
        )
        out(
            f"    clv_horizon_hours {argmin_row.clv_horizon_hours}   "
            f"strategy_config_version {argmin_row.strategy_config_version}   "
            f"era {jb.bankroll_era(argmin_row.created_ms)}"
        )
        out(
            f"    S = {fmt(argmin_s)} tenths.  CLAUDE.md rule 1: a large apparent "
            f"edge is a BUG until proven otherwise."
        )
        out(
            "    No automated implausibility threshold is registered, so this is "
            "a print for a human to read, not a gate."
        )
        block = jb.percentile_block(shortfalls_by_pop["P0"])
        out(
            f"    min beside its neighbours: min {fmt(block['min'])}  "
            f"p1 {fmt(block['p1'])}  p5 {fmt(block['p5'])}  p10 {fmt(block['p10'])}"
            f"   — a lone outlier is visible as one"
        )
        without = [s for s, _ in paired[1:]]
        out(
            f"    D* excluding the argmin row: "
            f"{fmt_plain(jb.d_star_points(without), 3)} points   "
            f"(the bound reported both with and without it, §A4)"
        )
        d_star = jb.d_star_points(shortfalls_by_pop["P0"])

    out("")
    out(f"  PRECONDITION reachability: K(10.00) >= 1  -> {k_reach >= 1}")
    out(f"  PRECONDITION coverage (D-gate): WHOLE TABLE -> {not provisional}")
    out("")
    out(f"  D* on P0 = {fmt_plain(d_star, 3)} points")
    out(
        f"    D* <= {jb.D_REALISTIC_POINTS}  -> BRANCH N;  "
        f"{jb.D_REALISTIC_POINTS} < D* <= {jb.D_SWEPT_POINTS} -> Z-NARROW;  "
        f"D* > {jb.D_SWEPT_POINTS} -> BRANCH Z    (§A1)"
    )
    reading = jb.verdict(d_star)
    out(f"  VERDICT READING: {reading or 'none — the population is empty'}")
    out("")

    if provisional or k_reach == 0 or reading is None:
        out("  NO BRANCH DECLARED. A precondition is unmet, and it is named above.")
        out("  Everything below is the reading the run WOULD support, not a declaration.")
        out("  `UNRESOLVED` is a real answer (§9).")
        out("")

    if reading == jb.BRANCH_N:
        cleared = {points: ladders["P0"][points][0] for points, _ in jb.DELTA_LADDER}
        smallest = min(p for p, k in cleared.items() if k >= 1)
        out(
            f"  BRANCH N: the smallest clearing δ is {smallest:.2f}, with "
            f"K = {cleared[smallest]} rows / {ladders['P0'][smallest][1]} games on P0."
        )
        out("  Per-population K at that δ:")
        for name in jb.POPULATION_NAMES:
            out(f"    {name}  K = {ladders[name][smallest][0]}")
        out(
            "  Branch N authorises per-knob decomposition and NOTHING ELSE — not "
            "a trade, not a sizing change, not a claim of edge."
        )
    elif reading == jb.Z_NARROW:
        out(
            f"  Z-NARROW: closed against realistic slates (worst spread at "
            f"favourite <= 85%, overround <= 6% is {jb.D_REALISTIC_POINTS} pts),"
        )
        out(
            f"  NOT closed against lopsided or high-hold lines (the swept worst "
            f"case is {jb.D_SWEPT_POINTS} pts)."
        )
        out(
            "  In Z-NARROW the CONFIRMATORY run after the deploy becomes "
            "DECISION-BEARING rather than a footnote, and the ADR WAITS for it."
        )
    elif reading == jb.BRANCH_Z:
        out(
            "  BRANCH Z: K(16.70) = 0 on P0. The finding is written in these "
            "words and no broader ones:"
        )
        out('    "Kalshi is not mispriced relative to a consensus it may itself lead."')
        out('  The sentence "no edge exists at Kalshi" is FORBIDDEN (§10).')
        out(
            f"  And §A5's caveat travels with it: D_swept = {jb.D_SWEPT_POINTS} "
            f"is a maximum over a SWEPT space — two-outcome, proportional"
        )
        out(
            "  overround, favourite <= 99%, hold <= 20%. Three-way markets, "
            "non-proportional vig and holds above 20% are outside it."
        )

    # -- 8. Branch M — the maker line --------------------------------------
    out.rule("8. BRANCH M — THE MAKER LINE (R3)")
    band = [r for r in p0 if jb.in_maker_band(r.ask_tenths)]
    band_clusters = jb.cluster_count(band)
    low, high = jb.MAKER_BAND_TENTHS
    out(f"  band [{low}, {high}] tenths: {len(band)} rows / {band_clusters} clusters")
    if band:
        shortfall_block(
            out,
            variant="PRIMARY dominating, stacked, fee=0 — RESTRICTED TO THE MAKER BAND",
            population="P0 ∩ [173, 827]",
            rows=band,
            shortfalls=[jb.primary_shortfall_tenths(r) for r in band],
        )
    out("")
    for basis, label in (
        (jb.ALT_0, "ALT-0 (max fee, taker, N=1) — baseline"),
        (
            jb.ALT_2,
            f"ALT-2 (max fee, maker, N={jb.ALT_2.contracts}) — DECISION-BEARING (§A2)",
        ),
        (
            jb.ALT_2_SECONDARY,
            f"ALT-2 (max fee, maker, N={jb.ALT_2_SECONDARY.contracts}) — "
            f"NON-DECISION-BEARING SECONDARY",
        ),
    ):
        s_band = [jb.primary_alt_shortfall_tenths(r, basis) for r in band]
        counts = " ".join(
            f"K({p:.2f})={jb.k_at_delta(s_band, p)}" for p, _ in jb.DELTA_LADDER
        )
        out(f"  {label:<62} {counts}")
    alt0_clear = {
        r.id
        for r in band
        if jb.primary_alt_shortfall_tenths(r, jb.ALT_0) < 0.0
    }
    alt2_clear = {
        r.id
        for r in band
        if jb.primary_alt_shortfall_tenths(r, jb.ALT_2) < 0.0
    }
    gained = alt2_clear - alt0_clear
    out("")
    out(f"  rows ALT-2 clears that ALT-0 does not (at δ=0.00): {len(gained)}")
    named = band_clusters >= jb.MAKER_BAND_MIN_CLUSTERS and len(gained) >= 1
    out(
        f"  Branch M NAMED -> {named}   "
        f"(needs >= {jb.MAKER_BAND_MIN_CLUSTERS} clusters in the band AND "
        f">= 1 row ALT-2 clears that ALT-0 does not)"
    )
    if band_clusters < jb.MAKER_BAND_MIN_CLUSTERS:
        out(
            "  Fewer than 5 clusters in the band: the maker line closes with "
            "everything else."
        )
    out(
        "  Naming authorises a CANCEL PATH and the FREE MARKOUT HARNESS. Not a "
        "strategy, not a maker order, not a sizing change."
    )
    out(
        "  Nothing in this arithmetic addresses FILL PROBABILITY at all; ADR "
        "0017's 1.50c adverse-selection counterargument stands unmodified."
    )

    # -- 9. CONFIRMATORY ----------------------------------------------------
    out.rule("9. CONFIRMATORY SHORTFALL BLOCKS")
    with_methods = [r for r in p0 if jb.loosest_fair(r) is not None]
    if not with_methods:
        out(
            "  BLOCKED — payload carries no per-method probabilities (needs the "
            "deploy)."
        )
        out(
            "  §P4: `routes.py` at HEAD already LEFT JOINs `fair_prices` and "
            "returns p_multiplicative, p_additive, p_power, p_shin,"
        )
        out(
            "  p_conservative. The confirmatory variant is blocked on a DEPLOY, "
            "not on a code change."
        )
        out(
            f"  rows dropped for a missing p_*: {len(p0)} of {len(p0)} "
            f"(dropped and counted, never imputed)"
        )
    else:
        dropped = len(p0) - len(with_methods)
        out(f"  rows carrying all four methods: {len(with_methods)} of {len(p0)}")
        out(f"  rows dropped for a missing p_*: {dropped} (never imputed)")
        for basis in (jb.ALT_0, jb.ALT_1, jb.ALT_2):
            shortfalls = [
                s
                for r in with_methods
                if (s := jb.confirmatory_shortfall_tenths(r, basis)) is not None
            ]
            shortfall_block(
                out,
                variant=f"CONFIRMATORY exact, {basis.name}",
                population="P0",
                rows=with_methods,
                shortfalls=shortfalls,
                with_ladder=False,
            )
            out(f"  rows clearing under {basis.name} alone: "
                f"{sum(1 for s in shortfalls if s < 0.0)}")
        union = [jb.exact_bound_clears(r) for r in with_methods]
        out("")
        out(
            f"  EXACT BOUND (ALT-1 or ALT-2, individually — a UNION): "
            f"{sum(1 for c in union if c)} rows clear"
        )
    out("")
    out(
        "  THE STACKED COUNT IS NOT COMPUTED. Stacking the cheaper-fee knob onto "
        "the maker knob is worth up to a further"
    )
    out(
        "  10.0 tenths per contract beyond the better alternative (§C4), and "
        "reporting it as the exact bound would be a"
    )
    out(
        "  fabrication of exactly that size. `FeeBasis` refuses to be "
        "constructed in the stacked configuration."
    )

    # -- 10. Invariants -----------------------------------------------------
    out.rule("10. INVARIANTS, ASSERTED AND PRINTED")
    fee_violations = jb.fee_knob_delta_violations()
    out(
        f"  §C4  E1min − E1 == Δ(price), exhaustive over 999 prices  -> "
        f"{not fee_violations}  ({len(fee_violations)} violations)"
    )
    p5 = jb.p5_violations(p0)
    out(
        f"  §P5  p_conservative == min(four) == fair_probability     -> "
        f"{not p5}  ({len(p5)} violations)"
    )
    if not with_methods:
        out(
            "       (vacuous — no row carries the four methods on this payload)"
        )
    ladder_violations = jb.k_ladder_monotonicity_violations(ladders["P0"])
    pop_violations = jb.population_monotonicity_violations(ladders)
    out(
        f"       K monotone non-decreasing in δ on P0               -> "
        f"{not ladder_violations}"
    )
    out(
        f"       K monotone non-increasing along P3⊆P1, P2⊆P0       -> "
        f"{not pop_violations}"
    )
    for violation in fee_violations[:5] + p5[:5] + ladder_violations + pop_violations:
        out(f"    VIOLATION: {violation}")
    zero_fee = jb.maker_model_b_nonzero_cases()
    out(
        f"  §C3  stacked generous fee is zero at all 7,992 cases     -> "
        f"{not zero_fee}"
    )

    # -- 11. Diagnostics ----------------------------------------------------
    out.rule("11. DIAGNOSTICS — recomputed minus stored edge_tenths")
    out(
        "  The stored `edge_tenths` and `fee_predicted` columns are DIAGNOSTIC "
        "ONLY and enter no quantity above."
    )
    out(
        "  Recomputation is at ALT-0 (max fee model, taker, N=1); the stored "
        "column's own divisor is not recoverable from the row,"
    )
    out("  which is exactly why it may not be used (§6, Lane A §6).")
    diffs = []
    for row in p0:
        if row.stored_edge_tenths_DO_NOT_USE is None:
            continue
        recomputed = edge_after_fees_tenths(
            ask_tenths=row.ask_tenths,
            contracts=1,
            fair_probability=row.fair_probability,
            maker=False,
        )
        diffs.append(recomputed - row.stored_edge_tenths_DO_NOT_USE)
    if diffs:
        block = jb.percentile_block(diffs)
        out(
            f"  n = {len(diffs)}   "
            + "  ".join(f"{k} {fmt(v)}" for k, v in block.items())
        )
    else:
        out("  no row carries a stored edge_tenths")

    # -- 12. Grid B ---------------------------------------------------------
    out.rule("12. GRID B CROSS-TAB — DESCRIPTIVE — CANNOT PRODUCE A FINDING")
    out("  Bucketed on entry_ask_tenths, the derived ask, the price actually paid.")
    out(
        f"  {'bucket':<14}{'rows':>7}{'clusters':>10}{'min S':>10}   "
        + "  ".join(f"K({p:.2f})" for p, _ in jb.DELTA_LADDER)
    )
    for bucket in jb.GRID_B:
        members = [r for r in p0 if jb.grid_b_bucket(r.ask_tenths) == bucket]
        shortfalls = [jb.primary_shortfall_tenths(r) for r in members]
        ks = "  ".join(
            f"{jb.k_at_delta(shortfalls, p):>7}" for p, _ in jb.DELTA_LADDER
        )
        out(
            f"  {str(bucket):<14}{len(members):>7}{jb.cluster_count(members):>10}"
            f"{fmt(min(shortfalls)) if shortfalls else 'None':>10}   {ks}"
        )

    # -- 13. The rule of three ---------------------------------------------
    out.rule("13. THE RULE-OF-THREE RATE BOUND")
    g = jb.cluster_count(p0)
    bound = jb.rule_of_three(g)
    g_clearing = ladders["P0"][jb.D_SWEPT_POINTS][1]
    out(f"  Measured G = {g}.  Clearing clusters at the top rung: {g_clearing}.")
    if g_clearing > 0:
        # The rule of three is the zero-events bound. Printing it beside a
        # non-zero count would be a sentence contradicted by the data one line
        # above it, which is precisely how a number gets quoted out of a report.
        out(
            "  THE RULE OF THREE DOES NOT APPLY TO THIS RUN. It is the upper "
            "bound on a rate given ZERO observed events,"
        )
        out(
            f"  and this run observed {g_clearing} clearing clusters. The "
            f"generalisation question it answers does not arise:"
        )
        out(
            "  the record does not need a bound on an unseen rate when the rate "
            "is seen. The table below is printed as the"
        )
        out("  registered reference (§S2 item 13) and is NOT a result of this run.")
    else:
        out(
            f"  With 0 clearing games out of G clusters, the one-sided 95% upper "
            f"bound on the per-game rate is 3/G = "
            f"{'None' if bound is None else f'{100.0 * bound:.1f}%'}."
        )
    out("")
    for reference in (29, 60, 100, 300, 1000):
        marker = "  <== measured G is nearest here" if reference == min(
            (29, 60, 100, 300, 1000), key=lambda x: abs(x - g)
        ) else ""
        out(
            f"    G = {reference:>5}   bound "
            f"{100.0 * jb.rule_of_three(reference):>5.1f}%{marker}"
        )
    out("")
    if g_clearing > 0:
        out(
            "  No generalising sentence is authorised by this run in either "
            "direction."
        )
    else:
        out(
            '  No sentence of the form "actionable rows do not occur" may be '
            "written — only:"
        )
        out(
            f'    "no actionable row occurs in this record, and at G = {g} the '
            f"per-game rate is bounded above by "
            f'{"None" if bound is None else f"{100.0 * bound:.1f}"}% with 95% '
            f'confidence."'
        )

    # -- 14. §10 verbatim ---------------------------------------------------
    out.rule("14. §10 — WHAT THIS MEASUREMENT CANNOT ESTABLISH (VERBATIM)")
    for line in section_10_verbatim():
        out(line)


def main() -> int:
    configure_logging()
    # The registered output contains `δ`, `⊆`, `∩` and the em-dash of §S1's
    # provisional label. A Windows console defaults to cp1252 and raises on all
    # four, which would kill the run somewhere in the middle of the report and
    # leave a truncated artefact that still looks like a result.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="re-cut the analysis from the cached pull, spending no request",
    )
    parser.add_argument("--cache", type=Path, default=CACHE_PATH)
    args = parser.parse_args()

    if args.from_cache:
        if not args.cache.exists():
            print(f"no cached pull at {args.cache}", file=sys.stderr)
            return 1
        pull_data = json.loads(args.cache.read_text(encoding="utf-8"))
    else:
        token = read_token(ROOT / ".env")
        pull_data = asyncio.run(pull(args.base_url, token))
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        args.cache.write_text(
            json.dumps(pull_data, indent=1, sort_keys=True), encoding="utf-8"
        )

    analyse(pull_data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
