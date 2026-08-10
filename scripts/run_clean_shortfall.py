"""Run the clean-population shortfall distribution, and report §S items 1-13.

Governed **exactly** by
`docs/measurements/2026-08-10-preregistration-clean-shortfall-distribution.md`.
Every population, key, statistic, bucket edge, guard and output field is fixed
by that document. **Nothing is chosen here.** Where this file had a choice to
make that the registration did not fix -- there is exactly one, the median
convention in H3a -- it reuses the repo's already-tested
`joint_bound.percentile` (nearest rank) and prints the interpolated median
beside it as a diagnostic, so the convention cannot hide a sign reversal.

    .venv\\Scripts\\python.exe scripts\\run_clean_shortfall.py
    .venv\\Scripts\\python.exe scripts\\run_clean_shortfall.py --from-cache

The pull is pinned (§6): `newest_id` off page 0 becomes `max_id` on every page,
and `len(ids) == len(set(ids)) == total` is **asserted**. That assertion is the
only check that catches an incomplete pull -- `total`, `returned` and `limit`
all agree happily over a corrupted multiset.

The token is read from the repo-root `.env`, handed to one form POST to
`/session`, held in memory, and **never logged, printed, or written to the
cache file**. `configure_logging()` runs before any client is constructed
because `httpx` logs full request URLs at INFO and this repo has already put a
working credential into a transcript that way.

What this harness does NOT establish
------------------------------------
Reproduced from registration §10, because a harness carries its own limits.

- **The clean population is defined partly by the dependent variable.**
  `suspicious_edge` removes stored edges above 40.0 tenths and
  `edge_within_method_noise` removes stored edges in `(0, spread_tenths]`. So
  `max E1 <= 0` over the clean set is **not** evidence that no positive edge
  exists in the record. 45 rows carry one; all are suppressed. Anyone quoting
  this as "there is no edge" has read the wrong population.
- **The whole agreement family is uniformly blind to correlated garbage.** Two
  books at `1.85/1.85` produce `fair ~ 0.5`, `width = 0.0`, `book_count = 2`
  and `suppressed_reason = None` -- inside this measurement's population. H4 is
  the registered detector.
- **It is a census, not a sample.** No interval, no standard error, no p-value
  and no significance mark appears anywhere in this file, by design. Nothing
  here generalises to future rows, other months or other leagues, and any
  reader treating `n_obs` as a sample size has misread it.
- **The fee it measures against is `calculate_fee`'s bar, not Kalshi's.** The
  fee model is secondary-sourced and unverified and this project has zero
  fills, ever. If both candidate models are wrong, every number moves.
- **`fair_probability` is the worst of four devig methods**, so every `E1` is a
  deliberately shrunk number, shifted toward "falls short" by an unmeasured,
  price-dependent amount that is largest at the wings. H3a/H3b measure the
  *spread* of that input, not its *bias*.
- **The magnitude is not resolvable; only the sign is.** No statement of the
  form "the strategy nearly clears" or "clearly misses" is licensed at any `n`.
- **`n_obs` is not a count of independent observations** and neither is
  `n_claims`. Independence lives at the cluster, and §3's three named leaks all
  inflate the count.
- **It says nothing** about whether an edge exists at Kalshi, about
  calibration, about CLV, about the maker path, about combos, or about in-play.
- **The record is a census of rows already written**, downstream of discovery
  and of `persist_if_changed`'s movement-only write rule. A market never polled
  contributes no row and cannot appear.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.analysis.joint_bound import (  # noqa: E402
    Row,
    cluster_key,
    event_suffix,
    grid_b_bucket,
    percentile,
    series_prefix,
)
from backend.analysis.validate import BUCKETS as GRID_B  # noqa: E402
from backend.analysis.validate import MIN_EXPECTED_PER_SIDE  # noqa: E402
from backend.core.ev import edge_after_fees_tenths  # noqa: E402
from backend.core.fees import settlement_fee  # noqa: E402
from backend.core.prices import PRICE_MAX  # noqa: E402
from backend.core.suppression import ALL_CHECK_NAMES  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "https://kalshi-cockpit.fly.dev"
REGISTRATION = (
    "docs/measurements/"
    "2026-08-10-preregistration-clean-shortfall-distribution.md"
)
PAGE_SIZE = 1000

# §R2: the pin of §0.2. Rows at or below this id have already been measured.
PRIOR_PIN = 1549
# §1 H4's predicate. Deliberately NOT the `tasks/NEXT.md` ULP signature, which
# undercounts by dropping every row whose odds devigged to an exact 0.5.
DEGENERATE_TOL = 1e-12
# §1 H4: the window in which a fabricated 0.5 fair clears `0 < net <= 40.0`.
CONTAMINATION_BAND = (440, 479)
# §7 H2's declaration threshold, and §R3's saturation threshold.
MAX_GAME_SHARE = 0.50
SATURATION = 0.90
# §R1: `config.edge_ceiling_tenths`. A clean row with a positive stored edge
# requires `spread_tenths < edge_tenths <= 40.0`, so a row whose own spread is
# at or above 40.0 cannot carry one.
EDGE_CEILING_TENTHS = 40.0


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, line: str = "") -> None:
        self.lines.append(line.rstrip())
        print(line.rstrip())

    def rule(self, title: str) -> None:
        self("")
        self("=" * 78)
        self(title)
        self("=" * 78)


def f1(v: Optional[float], places: int = 2) -> str:
    """`None` prints as `None`, never as 0. The repo's rule, in the formatter."""
    return "None" if v is None else f"{v:.{places}f}"


def fs(v: Optional[float], places: int = 2) -> str:
    return "None" if v is None else f"{v:+.{places}f}"


# ---------------------------------------------------------------------------
# The deployed fee, computed from code rather than quoted (§4 Grid D, §5)
# ---------------------------------------------------------------------------


def fee_tenths(ask_tenths: int) -> float:
    """The deployed taker fee at one contract, in tenths of a cent."""
    fee = settlement_fee(ask_tenths, 1, False)
    if fee is None:
        raise ValueError(f"no fee for ask {ask_tenths}")
    return fee * PRICE_MAX


def derive_grid_d() -> tuple[tuple[int, int], ...]:
    """Grid D: the coarsest partition on which the bar a row must clear is
    constant. Derived by sweeping the fee curve, never typed in."""
    cells: list[list[int]] = []
    prev: Optional[float] = None
    for p in range(1, PRICE_MAX):
        f = fee_tenths(p)
        if prev is None or abs(f - prev) > 1e-9:
            cells.append([p, p])
        else:
            cells[-1][1] = p
        prev = f
    return tuple((lo, hi) for lo, hi in cells)


# ---------------------------------------------------------------------------
# §6 -- the extraction. Pinned, complete, duplicate-free.
# ---------------------------------------------------------------------------


def read_token(env_path: Path) -> Optional[str]:
    """The live `APP_AUTH_TOKEN` from `.env`. Returned, never logged."""
    if not env_path.exists():
        return None
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("APP_AUTH_TOKEN="):
            value = raw.split("=", 1)[1].strip().strip("'\"")
            return value or None
    return None


async def open_session(client: httpx.AsyncClient, token: Optional[str]) -> str:
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
    """§6's pinned whole-table pull.

    P1 is a hard stop: if page 0 comes back without `newest_id`, the deployed
    build predates the paging contract, there is no pin to be had, and **no run
    happens** -- a slice is not a population here and labelling one has already
    failed to travel with the number.
    """
    async with httpx.AsyncClient(
        base_url=base_url, timeout=60.0, follow_redirects=False
    ) as client:
        session_status = await open_session(client, token)
        page0 = await fetch_page(client, offset=0, max_id=None)

        if page0.get("newest_id") is None:
            return {
                "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
                "base_url": base_url,
                "session_status": session_status,
                "supports_paging": False,
                "pages": [page0],
            }

        pin = int(page0["newest_id"])
        # Page 0 was fetched unpinned to learn the pin. Re-fetch it under the
        # pin so every page in the pull comes from one snapshot -- an unpinned
        # page 0 can carry rows above the pin, and `id <= pin` is the whole
        # basis on which the snapshot is immutable.
        pages = [await fetch_page(client, offset=0, max_id=pin)]
        offset = int(pages[0]["returned"])
        total = int(pages[0]["total"])
        while offset < total:
            page = await fetch_page(client, offset=offset, max_id=pin)
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
            "supports_paging": True,
            "pin": pin,
            "pages": pages,
        }


# ---------------------------------------------------------------------------
# §3 -- the unit of observation
# ---------------------------------------------------------------------------


def ticker_suffix(ticker: str) -> str:
    return ticker.split("-")[-1] if ticker else ""


@dataclass(frozen=True)
class Obs:
    """One clean row, with everything §7 consumes.

    `raw` is the verbatim payload dict, kept because §7's enumeration clauses
    name `depth_at_ask`, `odds_age_ms` and `kalshi_quote_age_ms`, which the
    tested `Row` does not carry. Nothing in a decision reads it.
    """

    row: Row
    raw: dict
    cluster: str
    claim: Any
    e1: float
    shortfall: float
    spread_tenths: Optional[float]
    normalisable: bool

    @property
    def id(self) -> int:
        return self.row.id


def spread_of(row: Row) -> Optional[float]:
    """`(max - min over the four p_*) x 1000`. `None` if any is NULL (P5)."""
    ps = [row.p_multiplicative, row.p_additive, row.p_power, row.p_shin]
    if any(p is None for p in ps):
        return None
    return (max(ps) - min(ps)) * PRICE_MAX  # type: ignore[type-var]


def build_claims(rows: Sequence[Row]) -> tuple[dict[str, set[str]], set[str]]:
    """§3 step 1: the suffix set per cluster, over the **whole pinned pull**."""
    suffixes: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        key = cluster_key(r.ticker, r.event_ticker)
        if key:
            suffixes[key].add(ticker_suffix(r.ticker))
    non_normalisable = {k for k, t in suffixes.items() if len(t) != 2}
    return suffixes, non_normalisable


def claim_of(row: Row, cluster: str, suffixes: dict[str, set[str]]) -> tuple[Any, bool]:
    """§3 step 2. Returns `(claim, normalisable)`."""
    suffix = ticker_suffix(row.ticker)
    t = suffixes.get(cluster, set())
    if row.side == "yes":
        return suffix, True
    if row.side == "no" and len(t) == 2:
        other = next(iter(t - {suffix}), None)
        if other is not None:
            return other, True
    return ("NO", suffix), False


def dedup(obs: Sequence[Obs], key) -> list[Obs]:
    """§3's representative rule: **largest `E1`**, ties by **lowest `id`**.

    Conservative in the direction that matters -- keeping the most favourable
    row maximises the chance of falsifying H1, so dedup cannot manufacture the
    null -- and it makes the deduplicated maximum exactly the row maximum, so
    H1's answer cannot move because of a key choice.
    """
    best: dict[Any, Obs] = {}
    for o in obs:
        k = key(o)
        cur = best.get(k)
        if cur is None or (o.e1, -o.id) > (cur.e1, -cur.id):
            best[k] = o
    return list(best.values())


OBS_KEY = lambda o: (o.cluster, o.row.created_ms, o.claim)  # noqa: E731
CLAIM_KEY = lambda o: (o.cluster, o.claim)  # noqa: E731


# ---------------------------------------------------------------------------
# §7 -- the five claims, each as a pure function of a population
# ---------------------------------------------------------------------------


def verdict_h1(obs: Sequence[Obs]) -> Optional[bool]:
    if not obs:
        return None
    return max(o.e1 for o in obs) <= 0.0


def verdict_h2(obs: Sequence[Obs]) -> Optional[bool]:
    if not obs:
        return None
    counts = Counter(o.cluster for o in obs)
    return (max(counts.values()) / len(obs)) <= MAX_GAME_SHARE


def _paired(obs: Sequence[Obs]) -> list[float]:
    return [
        o.shortfall - o.spread_tenths
        for o in obs
        if o.spread_tenths is not None
    ]


def verdict_h3a(obs: Sequence[Obs]) -> Optional[bool]:
    d = sorted(_paired(obs))
    if len(d) < MIN_EXPECTED_PER_SIDE:
        return None
    med = percentile(d, 50)
    return med is not None and med > 0.0


def verdict_h3b(obs: Sequence[Obs]) -> Optional[bool]:
    with_spread = [o for o in obs if o.spread_tenths is not None]
    if len(with_spread) < MIN_EXPECTED_PER_SIDE:
        return None
    s_min = min(o.shortfall for o in with_spread)
    tied = [o for o in with_spread if o.shortfall == s_min]
    # Ties are broken by the **largest** `spread_at_min` -- the reading least
    # likely to declare.
    spread_at_min = max(o.spread_tenths for o in tied)  # type: ignore[type-var]
    return s_min > spread_at_min


def verdict_h4(clean_rows: Sequence[Row]) -> Optional[bool]:
    return sum(1 for r in clean_rows if is_degenerate(r)) == 0


def is_degenerate(row: Row) -> bool:
    p = row.p_multiplicative
    return p is not None and abs(p - 0.5) < DEGENERATE_TOL


def is_degenerate_ulp(row: Row) -> bool:
    """The narrower `tasks/NEXT.md` signature, printed so its undercount is a
    number rather than an argument."""
    pm, pp = row.p_multiplicative, row.p_power
    if pm is None or pp is None:
        return False
    return abs(pm - 0.5) < DEGENERATE_TOL and 0.0 < (0.5 - pp) < 1e-9


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def analyse(pull_data: dict, out: Report) -> dict:
    stop_the_line: list[str] = []

    # -- §S1. The frame -----------------------------------------------------
    out.rule("§S1 — THE FRAME. Read this before `n`, and `n` before any effect size.")

    pulled_at = pull_data["pulled_at_utc"]
    base_url = pull_data["base_url"]
    pages = pull_data["pages"]
    supports_paging = pull_data.get("supports_paging", False)

    out(f"pulled_at_utc          {pulled_at}")
    out(f"base_url               {base_url}")
    out(f"session                {pull_data['session_status']}")
    out(f"registration           {REGISTRATION}")
    out("")

    p1 = supports_paging
    out(f"P1  deployed route serves the pin ......... {'MET' if p1 else 'UNMET'}")
    if not p1:
        out("")
        out("STOP THE LINE — P1 UNMET. Page 0 returned no `newest_id`, so there is")
        out("no pin to be had. A slice is not a population here. NO RUN HAPPENS.")
        return {"stopped": ["P1"], "lines": out.lines}

    pin = int(pull_data["pin"])
    total = int(pages[0]["total"])
    payload_rows = [r for page in pages for r in page["rows"]]
    ids = [int(r["id"]) for r in payload_rows]
    newest_after = pages[-1].get("newest_id")

    p2 = len(ids) == len(set(ids)) == total
    out(f"P2  pull complete and duplicate-free ...... {'MET' if p2 else 'UNMET'}")
    out(f"      pin {pin}   total {total}   pages {len(pages)}   "
        f"len(ids) {len(ids)}   len(set(ids)) {len(set(ids))}")
    out(f"      newest_id at end of pull {newest_after}  "
        f"({'table moved during the pull; the pin excluded those rows' if newest_after and int(newest_after) > pin else 'table did not move'})")
    out(f"      max(id) in pull {max(ids) if ids else None}  "
        f"(must be <= pin)")
    if not p2 or (ids and max(ids) > pin):
        out("")
        out("STOP THE LINE — P2 UNMET. The pull is not the population it claims")
        out("to be. `total`, `returned` and `limit` agree over a corrupted")
        out("multiset; this assertion is the only one that does not.")
        return {"stopped": ["P2"], "lines": out.lines}

    rows = [Row.from_ledger_payload(r) for r in payload_rows]
    raw_by_id = {int(r["id"]): r for r in payload_rows}

    # P4 -- the empty string would make the population predicate ambiguous.
    n_empty_reason = sum(1 for r in rows if r.suppressed_reason == "")
    p4 = n_empty_reason == 0
    out(f"P4  `suppressed_reason` never empty ....... {'MET' if p4 else 'UNMET'}"
        f"   (count {n_empty_reason})")

    # §2 -- the population.
    clean_all = [r for r in rows if r.suppressed_reason is None]
    dropped_price = [
        r for r in clean_all
        if r.ask_tenths is None or not (1 <= int(r.ask_tenths) <= PRICE_MAX - 1)
    ]
    dropped_fair = [
        r for r in clean_all
        if r.fair_probability is None and r not in dropped_price
    ]
    clean = [
        r for r in clean_all
        if r.ask_tenths is not None
        and 1 <= int(r.ask_tenths) <= PRICE_MAX - 1
        and r.fair_probability is not None
    ]
    p3 = not dropped_price
    out(f"P3  every clean `ask_tenths` in [1, 999] .. {'MET' if p3 else 'UNMET'}"
        f"   (dropped, never clamped: {len(dropped_price)})")
    out(f"     `fair_probability` non-NULL .......... "
        f"{'MET' if not dropped_fair else 'UNMET'}   (dropped: {len(dropped_fair)})")

    # P5 -- the four p_* on the clean population.
    n_null_p = sum(1 for r in clean if spread_of(r) is None)
    p5 = n_null_p == 0
    out(f"P5  four `p_*` non-NULL on the clean set .. {'MET' if p5 else 'UNMET'}"
        f"   ({n_null_p} rows excluded from H3a/H3b only, counted, never imputed)")

    # P6 -- the join landed on the right row.
    p6_fair_viol = [
        r for r in clean
        if r.p_conservative is not None
        and abs(r.p_conservative - (r.fair_probability or 0.0)) > 1e-12
    ]
    p6_min_viol = []
    for r in clean:
        ps = [r.p_multiplicative, r.p_additive, r.p_power, r.p_shin]
        if r.p_conservative is None or any(p is None for p in ps):
            continue
        if abs(r.p_conservative - min(ps)) > 1e-12:  # type: ignore[type-var]
            p6_min_viol.append(r)
    n_p_cons_null = sum(1 for r in clean if r.p_conservative is None)
    p6 = not p6_fair_viol and not p6_min_viol
    out(f"P6  p_conservative == fair_probability .... {'MET' if not p6_fair_viol else 'UNMET'}"
        f"   ({len(clean) - n_p_cons_null - len(p6_fair_viol)}/"
        f"{len(clean) - n_p_cons_null} checkable rows agree)")
    out(f"     p_conservative == min(four methods) .. "
        f"{'MET' if not p6_min_viol else 'UNMET'}   "
        f"({len(p6_min_viol)} violations)")

    # P7 -- the added check, if the deployed build carries it, never fires.
    all_tokens = Counter()
    for r in rows:
        if r.suppressed_reason:
            all_tokens.update(r.suppressed_reason.split(","))
    n_icm = all_tokens.get("inconsistent_consensus_metadata", 0)
    p7 = n_icm == 0
    out(f"P7  `inconsistent_consensus_metadata` ..... {'MET' if p7 else 'UNMET'}"
        f"   (occurrences in the whole record: {n_icm})")
    if not p7:
        out("     §V's void condition is MET — the clean population moved.")
        stop_the_line.append("P7 / §V void condition")

    # -- build the observations --------------------------------------------
    suffixes, non_normalisable = build_claims(rows)
    observations: list[Obs] = []
    for r in clean:
        key = cluster_key(r.ticker, r.event_ticker)
        if key is None:
            continue
        claim, normalisable = claim_of(r, key, suffixes)
        e1 = edge_after_fees_tenths(
            ask_tenths=int(r.ask_tenths),  # type: ignore[arg-type]
            contracts=1,
            fair_probability=float(r.fair_probability),  # type: ignore[arg-type]
            maker=False,
        )
        observations.append(
            Obs(
                row=r,
                raw=raw_by_id[r.id],
                cluster=key,
                claim=claim,
                e1=e1,
                shortfall=-e1,
                spread_tenths=spread_of(r),
                normalisable=normalisable,
            )
        )

    obs = dedup(observations, OBS_KEY)
    obs_claims = dedup(observations, CLAIM_KEY)
    n_rows = len(observations)
    n_obs = len(obs)
    n_claims = len(obs_claims)
    clusters = sorted({o.cluster for o in obs})
    G = len(clusters)
    n_ticker_side_instants = len(
        {(o.cluster, o.row.created_ms, o.row.ticker, o.row.side) for o in observations}
    )

    # -- §S2. The guards ----------------------------------------------------
    out.rule("§S2 — THE GUARDS. Evaluated and printed BEFORE any claim.")

    # R1 -- H1's falsifier must be arithmetically reachable.
    n_window = sum(
        1 for o in obs if o.spread_tenths is not None
        and o.spread_tenths < EDGE_CEILING_TENTHS
    )
    n_window_unknown = sum(1 for o in obs if o.spread_tenths is None)
    r1_trips = n_window == 0
    out(f"R1  n_window = {n_window} of {n_obs} clean deduplicated observations "
        f"have own spread < {EDGE_CEILING_TENTHS:.1f} tenths")
    out(f"      ({n_window_unknown} have a NULL p_* and no computable spread)")
    out(f"      {'TRIPS — H1 could not have returned its falsifier' if r1_trips else 'PASS — the falsifier of H1 is reachable'}")
    if r1_trips:
        stop_the_line.append("R1 (n_window == 0)")

    # R2 -- H1 must be able to return something other than its known value.
    n_new = sum(1 for r in clean if r.id > PRIOR_PIN)
    out(f"R2  n_new = {n_new} clean rows with id > {PRIOR_PIN}")
    out(f"      {'H1 is a CHECKSUM, not a measurement — label REPRODUCTION — NOT A NEW OBSERVATION' if n_new == 0 else 'H1 additionally evaluated on the id > %d suffix alone' % PRIOR_PIN}")
    out("      (labelling rule, never a stop. H2/H3a/H3b/H4 are live at any n_new.)")

    # R3 -- no cut may saturate. And the twin: G >= 2.
    grid_d = derive_grid_d()
    out(f"R3  Grid D derived from the deployed fee curve: "
        f"{' '.join(f'[{lo},{hi}]' for lo, hi in grid_d)}")

    def saturation_report(label: str, counts: Counter) -> bool:
        if not counts or n_obs == 0:
            out(f"      {label:<22} no observations")
            return False
        top, top_n = counts.most_common(1)[0]
        share = top_n / n_obs
        degenerate = share >= SATURATION
        out(f"      {label:<22} largest cell {str(top):<24} "
            f"{top_n}/{n_obs} = {share:.1%}  "
            f"{'DEGENERATE — DOES NOT DISCRIMINATE' if degenerate else 'discriminates'}")
        return degenerate

    def d_cell(o: Obs):
        return next(
            ((lo, hi) for lo, hi in grid_d if lo <= int(o.row.ask_tenths) <= hi),
            None,
        )

    def b_cell(o: Obs):
        return grid_b_bucket(int(o.row.ask_tenths)) or "outside"

    grid_d_counts = Counter(d_cell(o) for o in obs)
    grid_b_counts = Counter(b_cell(o) for o in obs)
    prefix_counts = Counter(series_prefix(o.row.ticker) for o in obs)

    d_sat = saturation_report("Grid D", grid_d_counts)
    b_sat = saturation_report("Grid B", grid_b_counts)
    p_sat = saturation_report("series prefix", prefix_counts)
    if d_sat or b_sat or p_sat:
        tripped = [
            n for n, s in
            (("Grid D", d_sat), ("Grid B", b_sat), ("series prefix", p_sat))
            if s
        ]
        stop_the_line.append(f"R3 (saturated: {', '.join(tripped)})")

    out(f"    G = {G} distinct clusters   "
        f"{'TRIPS — no per-group view exists' if G < 2 else 'PASS'}")
    if G < 2:
        stop_the_line.append("R3 twin (G < 2)")

    # R4's H4 twin -- a zero-count claim needs a non-zero control.
    n_degen_clean = sum(1 for o in observations if is_degenerate(o.row))
    suppressed_rows = [r for r in rows if r.suppressed_reason is not None]
    n_degen_supp = sum(1 for r in suppressed_rows if is_degenerate(r))
    twin_trips = n_degen_clean == 0 and n_degen_supp == 0
    out(f"R4  H4 twin: degenerate predicate returns {n_degen_clean} on the clean "
        f"population and {n_degen_supp} on the suppressed one")
    out(f"      {'TRIPS — the predicate itself is suspect; §0.2 measured 21 under a NARROWER signature, so a broader one returning fewer is arithmetically impossible' if twin_trips else 'PASS — the predicate demonstrably fires somewhere'}")
    if twin_trips:
        stop_the_line.append("R4's H4 twin (predicate returns 0 on both populations)")

    out("")
    if stop_the_line:
        out("*** STOP THE LINE ***")
        for g in stop_the_line:
            out(f"    tripped: {g}")
        out("    NO CLAIM IS DECLARED. §9's refutation ADR is not written from this")
        out("    run. Everything below is printed as §S requires and is DESCRIPTIVE")
        out("    ONLY — no cell below may be reported as a finding.")
    else:
        out("ALL GUARDS PASS. The five claims may be declared.")

    declare = not stop_the_line

    # -- §S3. The five counts ----------------------------------------------
    out.rule("§S3 — THE FIVE COUNTS. No count here is a count of independent observations.")
    out(f"  n_rows                      {n_rows:>6}   clean rows — this is UPTIME")
    out(f"  n_ticker_side_instants      {n_ticker_side_instants:>6}   integrity: MUST equal n_rows"
        f"   {'OK' if n_ticker_side_instants == n_rows else '*** RECORDER IS DOUBLE-WRITING ***'}")
    out(f"  n_obs                       {n_obs:>6}   distinct (cluster, created_ms, claim) — THE REGISTERED UNIT")
    out(f"  n_claims                    {n_claims:>6}   distinct (cluster, claim) — the hardest floor")
    out(f"  G                           {G:>6}   distinct clusters — THE INDEPENDENCE UNIT")
    out("")
    out(f"  dedup ratio n_rows / n_obs  {n_rows / n_obs:.3f}" if n_obs else "  dedup ratio  n/a")
    out(f"  non-normalisable clusters   {len(non_normalisable)}"
        f"   (A1's detector: a cluster whose suffix set is not exactly two members)")
    if non_normalisable:
        for k in sorted(non_normalisable)[:20]:
            out(f"      {k}  suffixes={sorted(suffixes[k])}")

    # Near-duplicate instants (§3 leak 1) -- printed, never collapsed.
    by_claim: dict[Any, list[int]] = defaultdict(list)
    for o in obs:
        if o.row.created_ms is not None:
            by_claim[(o.cluster, o.claim)].append(int(o.row.created_ms))
    near_pairs = 0
    for stamps in by_claim.values():
        s = sorted(stamps)
        for i in range(len(s)):
            for j in range(i + 1, len(s)):
                if s[j] - s[i] <= 1000:
                    near_pairs += 1
                else:
                    break
    out(f"  near-duplicate instants     {near_pairs}"
        f"   claim-pairs with |Δ created_ms| <= 1000 ms — NOT collapsed")

    # -- §S4. Cluster-key integrity -----------------------------------------
    out.rule("§S4 — CLUSTER-KEY INTEGRITY")
    prefixes = Counter(series_prefix(r.ticker) for r in rows)
    out(f"  distinct series prefixes, whole pull: "
        f"{', '.join(f'{k}={v}' for k, v in prefixes.most_common())}")
    suffix_prefixes: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        es, sp = event_suffix(r.ticker), series_prefix(r.ticker)
        if es and sp:
            suffix_prefixes[es].add(sp)
    collisions = {k: v for k, v in suffix_prefixes.items() if len(v) > 1}
    out(f"  <DATE+TEAMS> suffixes under more than one prefix: {len(collisions)}")
    out(f"    {'G is NOT inflated by the known defect' if not collisions else '*** G IS INFLATED — ' + str(collisions)}")

    groups: dict[Any, list[Obs]] = defaultdict(list)
    for o in observations:
        groups[OBS_KEY(o)].append(o)
    collapsed = [g for g in groups.values() if len(g) >= 2]
    fair_ranges = [
        max(float(x.row.fair_probability) for x in g)  # type: ignore[arg-type]
        - min(float(x.row.fair_probability) for x in g)  # type: ignore[arg-type]
        for g in collapsed
    ]
    ask_ranges = [
        max(int(x.row.ask_tenths) for x in g) - min(int(x.row.ask_tenths) for x in g)
        for g in collapsed
    ]
    out(f"  collapsed groups (size >= 2): {len(collapsed)}")
    max_fair_range = max(fair_ranges) if fair_ranges else 0.0
    out(f"  within-group fair_probability range: max {max_fair_range:.12g}"
        f"   {'OK — C2 structural identity holds' if max_fair_range <= 1e-12 else '*** NON-ZERO — the fair_price_id join or the opponent lookup does not behave as runner.py:665-693 says ***'}")
    if ask_ranges:
        sa = sorted(ask_ranges)
        out(f"  within-group ask_tenths range (expected non-zero sometimes; "
            f"reported, not asserted):")
        out(f"      min {sa[0]}  p25 {percentile(sa, 25)}  median {percentile(sa, 50)}"
            f"  p75 {percentile(sa, 75)}  max {sa[-1]}   "
            f"zero-range groups {sum(1 for x in sa if x == 0)}/{len(sa)}")

    # -- §S5. Composition, before any rate ----------------------------------
    out.rule("§S5 — COMPOSITION, BEFORE ANY RATE")
    strata = Counter(
        (series_prefix(o.row.ticker), o.row.strategy_config_version,
         o.row.clv_horizon_hours)
        for o in obs
    )
    strata_clusters: dict[Any, set[str]] = defaultdict(set)
    for o in obs:
        strata_clusters[
            (series_prefix(o.row.ticker), o.row.strategy_config_version,
             o.row.clv_horizon_hours)
        ].add(o.cluster)
    out(f"  {'prefix':<12} {'strategy_config_version':<26} {'clv_h':>6} "
        f"{'obs':>6} {'share':>7} {'clusters':>9}")
    for k, v in strata.most_common():
        pfx, ver, hz = k
        out(f"  {str(pfx):<12} {str(ver)[:26]:<26} {str(hz):>6} "
            f"{v:>6} {v / n_obs:>6.1%} {len(strata_clusters[k]):>9}")
    versions = {o.row.strategy_config_version for o in obs}
    out(f"  distinct strategy_config_version on the clean set: {len(versions)}")
    out(f"    {'single configuration' if len(versions) <= 1 else '*** THE RECORD IS ALREADY A MULTI-CONFIGURATION MIXTURE — §V detector 1 ***'}")

    per_cluster = Counter(o.cluster for o in obs)
    sizes = sorted(per_cluster.values())
    largest_cluster, largest_n = per_cluster.most_common(1)[0] if per_cluster else (None, 0)
    out("")
    out(f"  observations per cluster: min {sizes[0] if sizes else None}  "
        f"p25 {percentile(sizes, 25)}  median {percentile(sizes, 50)}  "
        f"p75 {percentile(sizes, 75)}  max {sizes[-1] if sizes else None}")
    out(f"  LARGEST CLUSTER: {largest_cluster}  {largest_n}/{n_obs} = "
        f"{largest_n / n_obs:.1%}" if n_obs else "  no observations")

    # -- §S6. H4, first, because it can contaminate H1 ----------------------
    out.rule("§S6 — H4. FABRICATED FAIRS IN THE CLEAN POPULATION. Reported FIRST.")
    out(f"  predicate: abs(p_multiplicative - 0.5) < {DEGENERATE_TOL:g}")
    out(f"  n_degen, CLEAN population (pre-dedup, so nothing hides in a "
        f"collapsed group):  {n_degen_clean}")
    out(f"  n_degen, SUPPRESSED population (the paired non-zero control):     "
        f"{n_degen_supp}")
    n_ulp_clean = sum(1 for o in observations if is_degenerate_ulp(o.row))
    n_ulp_supp = sum(1 for r in suppressed_rows if is_degenerate_ulp(r))
    out(f"  narrower `tasks/NEXT.md` ULP signature: clean {n_ulp_clean}, "
        f"suppressed {n_ulp_supp}")
    out(f"    the undercount, as a number: {n_degen_supp - n_ulp_supp} suppressed "
        f"rows are degenerate and the ULP signature misses them")
    degen_band = [
        o for o in observations if is_degenerate(o.row)
        and CONTAMINATION_BAND[0] <= int(o.row.ask_tenths) <= CONTAMINATION_BAND[1]
    ]
    out(f"  clean degenerate rows in ask ∈ [{CONTAMINATION_BAND[0]}, "
        f"{CONTAMINATION_BAND[1]}] (where a fabricated 0.5 clears): "
        f"{len(degen_band)}")
    h4 = verdict_h4([o.row for o in observations])
    if n_degen_clean:
        out("  every clean degenerate row, enumerated:")
        for o in observations:
            if not is_degenerate(o.row):
                continue
            r = o.row
            out(f"    id={r.id} {r.ticker} {r.side} ask={r.ask_tenths} "
                f"pm={r.p_multiplicative!r} pa={r.p_additive!r} "
                f"pp={r.p_power!r} ps={r.p_shin!r} "
                f"odds_age_ms={o.raw.get('odds_age_ms')!r} "
                f"created_ms={r.created_ms}")
    out("")
    out(f"  H4 VERDICT: {_verdict_line('H4', h4, declare, 'n_degen == 0')}")
    if declare and h4 is False:
        out("  *** H1 IS FLAGGED CONTAMINATED. A clean row built on a fabricated")
        out("      fair is not evidence about the strategy either way. ***")

    # -- §S7. H2 ------------------------------------------------------------
    out.rule("§S7 — H2. CONCENTRATION.")
    max_game_share = largest_n / n_obs if n_obs else None
    out(f"  max_game_share = {f1(max_game_share, 4)}   threshold <= {MAX_GAME_SHARE}")
    h2 = verdict_h2(obs)
    out(f"  H2 VERDICT: {_verdict_line('H2', h2, declare, 'max_game_share <= 0.50')}")
    if declare and h2 is False:
        out("  *** THE POOLED DISTRIBUTION IS ONE GAME'S DISTRIBUTION. Every pooled")
        out("      quantile below is struck through and replaced by the per-game table. ***")
    out("")
    out("  PER-GAME TABLE (every cluster, beside every aggregate, per CLAUDE.md)")
    out(f"  {'cluster':<32} {'obs':>5} {'share':>7} {'min S':>9} {'max S':>9} {'max E1':>9}")
    for c in sorted(per_cluster, key=lambda k: -per_cluster[k]):
        co = [o for o in obs if o.cluster == c]
        out(f"  {c:<32} {len(co):>5} {len(co) / n_obs:>6.1%} "
            f"{min(o.shortfall for o in co):>9.2f} "
            f"{max(o.shortfall for o in co):>9.2f} "
            f"{max(o.e1 for o in co):>+9.2f}")

    # -- §S8. H3a then H3b --------------------------------------------------
    out.rule("§S8 — H3a (TYPICAL ROW), THEN H3b (THE NEAREST ROW).")
    with_spread = [o for o in obs if o.spread_tenths is not None]
    n_spread = len(with_spread)
    out(f"  n_spread = {n_spread}   (clean deduplicated observations with all "
        f"four p_* non-NULL)")
    out(f"  MIN_EXPECTED_PER_SIDE = {MIN_EXPECTED_PER_SIDE}   "
        f"{'H3a and H3b are UNRESOLVED — n before effect size' if n_spread < MIN_EXPECTED_PER_SIDE else 'sufficient'}")

    h3a = verdict_h3a(obs)
    h3b = verdict_h3b(obs)
    d = sorted(_paired(obs))
    if d:
        med_nr = percentile(d, 50)
        med_interp = statistics.median(d)
        out("")
        out(f"  paired median (S - spread_tenths), nearest rank: {fs(med_nr)}")
        out(f"  paired median (S - spread_tenths), interpolated: {fs(med_interp)}"
            f"   {'— agrees in sign' if med_nr is not None and (med_nr > 0) == (med_interp > 0) else '*** THE TWO MEDIAN CONVENTIONS DISAGREE IN SIGN ***'}")
        n_exceed = sum(1 for o in with_spread if o.shortfall > o.spread_tenths)
        out(f"  share of observations with S > spread_tenths: "
            f"{n_exceed}/{n_spread} = {n_exceed / n_spread:.1%}")
        out("")
        out(f"  {'':<16} {'min':>9} {'p25':>9} {'median':>9} {'p75':>9} {'max':>9}")
        for label, vals in (
            ("S (shortfall)", sorted(o.shortfall for o in with_spread)),
            ("spread_tenths", sorted(o.spread_tenths for o in with_spread)),  # type: ignore[misc]
        ):
            out(f"  {label:<16} {percentile(vals, 0):>9.2f} "
                f"{percentile(vals, 25):>9.2f} {percentile(vals, 50):>9.2f} "
                f"{percentile(vals, 75):>9.2f} {percentile(vals, 100):>9.2f}")
    out("")
    out(f"  H3a VERDICT: {_verdict_line('H3a', h3a, declare, 'median(S - spread_tenths) > 0')}")

    out("")
    out("  H3b — THE ONE THAT GOVERNS THE CITABLE SENTENCE.")
    if with_spread:
        s_min = min(o.shortfall for o in with_spread)
        tied = [o for o in with_spread if o.shortfall == s_min]
        spread_at_min = max(o.spread_tenths for o in tied)  # type: ignore[type-var]
        out(f"  S_min          = {s_min:.4f} tenths = {s_min / 10:.4f}c")
        out(f"  spread_at_min  = {spread_at_min:.4f} tenths"
            f"   (largest among {len(tied)} tied observation(s) — the reading "
            f"least likely to declare)")
        out("  the attaining observation(s), in full:")
        for o in tied:
            r = o.row
            out(f"    id={r.id} {r.ticker} side={r.side} ask={r.ask_tenths} "
                f"fair={r.fair_probability!r}")
            out(f"      p_mult={r.p_multiplicative!r} p_add={r.p_additive!r} "
                f"p_pow={r.p_power!r} p_shin={r.p_shin!r} "
                f"spread={f1(o.spread_tenths, 4)} E1={fs(o.e1, 4)}")
    out("")
    out(f"  H3b VERDICT: {_verdict_line('H3b', h3b, declare, 'S_min > spread_at_min')}")
    if declare and h3a and h3b is False:
        out("  *** H3a HAS NOT ANSWERED H3b. The nearest clean observation is NOT")
        out("      distinguishable from clearing. No sentence of the form")
        out('      "the nearest is X.XXc short" may be written. Existing')
        out("      occurrences in tasks/NEXT.md and 2026-08-10-joint-bound-result.md")
        out("      require annotation. ***")

    # -- §S9. H1, last ------------------------------------------------------
    out.rule("§S9 — H1. REPRODUCTION, NOT DISCOVERY. Reported LAST, deliberately.")
    max_e1 = max(o.e1 for o in obs) if obs else None
    h1 = verdict_h1(obs)
    label = ("REPRODUCTION — NOT A NEW OBSERVATION" if n_new == 0
             else f"evaluated on the whole table AND on the id > {PRIOR_PIN} suffix")
    out(f"  R2 label: {label}")
    out(f"  max E1 over clean deduplicated observations: {fs(max_e1)} tenths"
        f"  ({fs((max_e1 or 0) / 10, 3)}c)")
    out(f"  H1 VERDICT: {_verdict_line('H1', h1, declare, 'max E1 <= 0')}")
    positive = sorted((o for o in obs if o.e1 > 0), key=lambda o: -o.e1)
    if positive:
        out("  every clean deduplicated observation with E1 > 0, enumerated:")
        for o in positive:
            r = o.row
            out(f"    id={r.id} {r.ticker} {r.side} ask={r.ask_tenths} "
                f"fair={r.fair_probability!r} E1={o.e1:+.3f}")
            out(f"      p_mult={r.p_multiplicative!r} p_add={r.p_additive!r} "
                f"p_pow={r.p_power!r} p_shin={r.p_shin!r} "
                f"spread={f1(o.spread_tenths)}")
            out(f"      depth_at_ask={o.raw.get('depth_at_ask')!r} "
                f"odds_age_ms={o.raw.get('odds_age_ms')!r} "
                f"kalshi_quote_age_ms={o.raw.get('kalshi_quote_age_ms')!r}")
    if n_new > 0:
        suffix_obs = [o for o in obs if o.row.id > PRIOR_PIN]
        out(f"  id > {PRIOR_PIN} suffix: {len(suffix_obs)} observations, "
            f"max E1 {fs(max((o.e1 for o in suffix_obs), default=None))}"
            f"   — ONLY this result may be described as new")

    # -- §S10. Diagnostics --------------------------------------------------
    out.rule("§S10 — DIAGNOSTICS")
    residuals = []
    for o in observations:
        expected = (
            PRICE_MAX * float(o.row.fair_probability)  # type: ignore[arg-type]
            - int(o.row.ask_tenths) - fee_tenths(int(o.row.ask_tenths))
        )
        residuals.append(abs(o.e1 - expected))
    out(f"  per-row identity E1 == 1000·fair - ask - fee_tenths(ask): "
        f"max |residual| = {max(residuals) if residuals else 0.0:.3e}   "
        f"{'HOLDS' if not residuals or max(residuals) < 1e-9 else '*** VIOLATED ***'}")

    basis = [
        o.e1 - float(o.row.stored_edge_tenths_DO_NOT_USE)
        for o in observations
        if o.row.stored_edge_tenths_DO_NOT_USE is not None
    ]
    if basis:
        sb = sorted(basis)
        out(f"  E1 - stored edge_tenths (the size-basis artefact of §5, as a "
            f"printed number rather than an argument):")
        out(f"      min {sb[0]:+.2f}  p25 {percentile(sb, 25):+.2f}  "
            f"median {percentile(sb, 50):+.2f}  p75 {percentile(sb, 75):+.2f}  "
            f"max {sb[-1]:+.2f}   nonzero on {sum(1 for x in sb if abs(x) > 1e-9)}"
            f"/{len(sb)} rows")

    out("")
    out(f"  per-code counts over the SUPPRESSED population "
        f"({len(suppressed_rows)} rows), exact token match on the split — no "
        f"wildcard surface (§C1):")
    vocabulary = sorted(set(ALL_CHECK_NAMES) | set(all_tokens))
    for code in vocabulary:
        n = sum(
            1 for r in suppressed_rows
            if code in (r.suppressed_reason or "").split(",")
        )
        out(f"      {code:<38} {n:>6}"
            + ("   (declared in ALL_CHECK_NAMES, never observed)"
               if n == 0 and code in ALL_CHECK_NAMES else "")
            + ("   *** OBSERVED BUT NOT IN THE DECLARED VOCABULARY ***"
               if code not in ALL_CHECK_NAMES and not code.startswith("sizing:")
               and n else ""))
    tfb = {r.id for r in suppressed_rows
           if "too_few_books" in (r.suppressed_reason or "").split(",")}
    nmw = {r.id for r in suppressed_rows
           if "no_market_width" in (r.suppressed_reason or "").split(",")}
    out(f"      too_few_books vs no_market_width: symmetric difference "
        f"{len(tfb ^ nmw)}   "
        f"{'ONE SIGNAL, NOT TWO' if not (tfb ^ nmw) else 'they have diverged'}")

    # -- §S11. Grid D then Grid B -------------------------------------------
    out.rule("§S11 — GRID D, THEN GRID B.  DESCRIPTIVE — CANNOT PRODUCE A FINDING")
    for title, cell_of, cells, banner in (
        ("Grid D (the deployed fee's own step function)", d_cell,
         list(grid_d), d_sat),
        ("Grid B (analysis.validate.BUCKETS, verbatim)", b_cell,
         list(GRID_B) + ["outside"], b_sat),
    ):
        out("")
        out(f"  {title}"
            + ("   *** DEGENERATE — DOES NOT DISCRIMINATE ***" if banner else ""))
        out(f"  {'cell':<16} {'obs':>6} {'share':>7} {'min S':>9} {'median S':>9} "
            f"{'max E1':>9}")
        for cell in cells:
            co = [o for o in obs if cell_of(o) == cell]
            if not co:
                out(f"  {str(cell):<16} {0:>6} {0.0:>6.1%}"
                    f" {'—':>9} {'—':>9} {'—':>9}")
                continue
            ss = sorted(o.shortfall for o in co)
            out(f"  {str(cell):<16} {len(co):>6} {len(co) / n_obs:>6.1%} "
                f"{ss[0]:>9.2f} {percentile(ss, 50):>9.2f} "
                f"{max(o.e1 for o in co):>+9.2f}")

    # -- §S12. The one-way downgrades ---------------------------------------
    out.rule("§S12 — THE ONE-WAY DOWNGRADES. Strictly one-way: never raises a verdict.")
    base = {
        "H1": h1, "H2": h2, "H3a": h3a, "H3b": h3b,
        "H4": verdict_h4([o.row for o in observations]),
    }
    downgraded: dict[str, list[str]] = defaultdict(list)
    for c in clusters:
        red_obs = [o for o in obs if o.cluster != c]
        red_rows = [o.row for o in observations if o.cluster != c]
        got = {
            "H1": verdict_h1(red_obs), "H2": verdict_h2(red_obs),
            "H3a": verdict_h3a(red_obs), "H3b": verdict_h3b(red_obs),
            "H4": verdict_h4(red_rows),
        }
        for k, v in got.items():
            if base[k] is not None and v is not None and v != base[k]:
                downgraded[k].append(f"leave-one-game-out: {c}")
    claims_key = {
        "H1": verdict_h1(obs_claims), "H2": verdict_h2(obs_claims),
        "H3a": verdict_h3a(obs_claims), "H3b": verdict_h3b(obs_claims),
        "H4": base["H4"],
    }
    for k, v in claims_key.items():
        if base[k] is not None and v is not None and v != base[k]:
            downgraded[k].append("the n_claims key (all instants collapsed)")
    for k in ("H4", "H2", "H3a", "H3b", "H1"):
        if downgraded[k]:
            out(f"  {k}: DOWNGRADED TO UNRESOLVED — reversed by "
                f"{'; '.join(downgraded[k][:6])}"
                + (f" (and {len(downgraded[k]) - 6} more)"
                   if len(downgraded[k]) > 6 else ""))
        else:
            out(f"  {k}: survives leave-one-game-out over all {G} clusters "
                f"and the n_claims key")

    return {
        "stopped": stop_the_line,
        "lines": out.lines,
        "pin": pin,
        "pulled_at_utc": pulled_at,
        "total": total,
        "n_rows": n_rows,
        "n_obs": n_obs,
        "n_claims": n_claims,
        "G": G,
        "n_new": n_new,
        "n_window": n_window,
        "n_degen_clean": n_degen_clean,
        "n_degen_supp": n_degen_supp,
        "max_e1": max_e1,
        "max_game_share": max_game_share,
        "verdicts": base,
        "downgraded": {k: v for k, v in downgraded.items() if v},
        "declare": declare,
    }


def _verdict_line(name: str, v: Optional[bool], declare: bool, rule: str) -> str:
    """On a stop, the verdict is **withheld, not parenthesised**.

    Printing "would have been DECLARED" is a declaration in all but name, and
    worse: it would hand a future registrar the five answers, so any amendment
    relaxing the tripped guard would be written with the results already
    visible. That is the contamination the whole document exists to prevent.
    The §S-mandated descriptive statistics are printed either way; only the
    verdict is withheld.
    """
    if not declare:
        return f"WITHHELD — STOP THE LINE. `{rule}` was not evaluated for a verdict."
    if v is None:
        return f"UNRESOLVED (`{rule}` not evaluable)"
    return f"{'DECLARED' if v else 'REFUTED'} on `{rule}`"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--from-cache", action="store_true")
    parser.add_argument("--cache", default=None)
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    configure_logging()

    run_date = datetime.now(timezone.utc).date().isoformat()
    cache_path = Path(args.cache) if args.cache else (
        ROOT / "docs" / "measurements" / f"{run_date}-clean-shortfall-pull.json"
    )

    if args.from_cache:
        pull_data = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        token = read_token(ROOT / ".env")
        pull_data = asyncio.run(pull(args.base_url, token))
        cache_path.write_text(json.dumps(pull_data), encoding="utf-8")

    out = Report()
    out.rule(
        "CLEAN-POPULATION SHORTFALL DISTRIBUTION — §S OUTPUT, IN THE REGISTERED ORDER"
    )
    result = analyse(pull_data, out)

    out.rule("§S13 — WHAT THIS MEASUREMENT CANNOT ESTABLISH (registration §10)")
    for line in (__doc__ or "").split("What this harness does NOT establish")[-1].splitlines()[2:]:
        out(line)

    log_path = cache_path.with_name(f"{run_date}-clean-shortfall-run.txt")
    log_path.write_text("\n".join(out.lines) + "\n", encoding="utf-8")
    print(f"\n[written] {log_path}")
    print(f"[written] {cache_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
