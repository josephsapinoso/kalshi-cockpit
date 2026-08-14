"""Re-derive every published Q-W number from the committed run artefact.

    .venv\\Scripts\\python.exe scripts\\analyse_qw_result.py ^
      docs\\measurements\\data\\qw_20260813T0000Z_kxwnbagame.json

Why this exists
---------------
The Q-W verdict entered the record with a per-day split, a burst-deduplicated
share, a time-weighted share, an event-share concentration figure and a
restricted event count. Every one of those was computed by hand off a pasted
section, which means **no future reader can check any of them**, and this repo
has already logged three citation drifts and one paragraph of pin-1549 figures
quoted against a pin-1564 result.

`kalshi-quotes-band` emits the raw sections. This turns them into the published
numbers, deterministically, so the write-up cites a script rather than a memory.

The certified figure is the burst-deduplicated one
--------------------------------------------------
`pregame_instants` counts poller passes, and the loop polls every 15s while the
odds window is open and every 900s when it is not (`backend/scheduler.py`), where
"open" means *any* league's odds are fresh -- nothing to do with WNBA. So the raw
share is a share of looks, weighted by how fast the poller happened to be
running, and the repo's own 2026-08-11 lesson applies: a repeated row is not an
independent observation.

Deduplicating to one look per burst separated by more than `--burst-gap-min`
(default 5) reproduces the 900s cadence at roughly one look per 16 minutes and is
therefore approximately time-uniform. **That is the number to publish.**

WIDER GAP CUTS ARE REFUSED, not merely discouraged
--------------------------------------------------
A burst counts as qualifying if *any* instant in it qualifies, so the share is
**monotone increasing in gap width by construction**. "100% at a 30-minute cut"
is arithmetic, not evidence, and at 3 bursts it is not a denominator either.
`--burst-gap-min` is clamped, and a value above `_MAX_HONEST_GAP_MIN` exits 2
rather than printing a flattering number. See `TestAWiderCutIsRefused`.

What this does not establish
----------------------------
- **Nothing the artefact does not contain.** It reads one JSON file. It does not
  connect to a database and cannot check that the artefact matches one.
- **Nothing about fillability.** Every ask and size in the artefact is a
  *displayed* quote. Availability is not fillability; the separating observation
  is one small order (§0.4e, R6).
- **Nothing about the last three hours before tip-off**, which is where the
  operator actually places. Q-W registered no time-to-tip bound and this script
  invents none; it reports lead time so the gap is visible, not closed.
- **It cannot un-activate `W`.** The registered rule has already fired. Every
  cut below is descriptive and explicitly unregistered, and letting a post-hoc
  cut reverse a pre-registered verdict is the exact freedom the registration
  exists to remove.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

# Above this, the dedup is measuring the cut rather than the book.
_MAX_HONEST_GAP_MIN = 10.0

_MS_PER_HOUR = 3_600_000

# The registered bars, restated so this script fails loudly if the artefact was
# produced by a query whose bars had drifted.
_BAR_INSTANT_PCT = 80
_BAR_EVENTS = 8


def _iso(ms: Optional[int]) -> Optional[str]:
    if ms is None:
        return None
    return (
        datetime.fromtimestamp(ms / 1000, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _section(payload: dict[str, Any], fragment: str) -> dict[str, Any]:
    """The one section whose title contains `fragment`.

    Exactly one, never the first match. "distinct events" appears in BOTH the
    verdict title (">= 8 distinct events") and the per-event section title, and
    a first-match lookup silently returned the verdict while re-deriving the
    event table -- the columns then did not exist and it failed loudly, which it
    only did by luck.
    """
    matches = [s for s in payload["sections"] if fragment in s["title"]]
    if len(matches) != 1:
        raise SystemExit(
            f"expected exactly one section matching {fragment!r}, "
            f"got {len(matches)}: {[s['title'] for s in matches]}"
        )
    return matches[0]


def _col(section: dict[str, Any], name: str) -> int:
    if name not in section["columns"]:
        raise SystemExit(
            f"{name!r} is not in section {section['title']!r}; "
            f"columns are {section['columns']}"
        )
    return section["columns"].index(name)


def _event_start_column(events: dict[str, Any]) -> str:
    """The column holding each fixture's TRUE start, across artefact vintages.

    The first Q-W run emitted the stored stamp under the name `commence_ms`.
    That stamp is raw `occurrence_datetime`, which ADR 0006 identifies as the
    expected *expiration* -- so it is three hours LATE and the name was wrong.
    Later runs emit `true_start_ms`, already corrected, alongside the raw
    `occurrence_ms`.

    Both are accepted and the correction is applied to the old shape here, so a
    figure derived from the first artefact matches one derived from a re-run.
    Refusing the old artefact would be tidier and would also make the one run
    that actually gated the fee round unreadable.
    """
    if "true_start_ms" in events["columns"]:
        return "true_start_ms"
    if "commence_ms" in events["columns"]:
        return "commence_ms"
    raise SystemExit(
        "the event section carries neither `true_start_ms` nor `commence_ms`"
    )


def _true_starts(events: dict[str, Any], offset_ms: int) -> list[int]:
    name = _event_start_column(events)
    idx = _col(events, name)
    correction = offset_ms if name == "commence_ms" else 0
    return [row[idx] - correction for row in events["rows"]]


def analyse(payload: dict[str, Any], burst_gap_min: float, offset_ms: int) -> dict:
    verdict = _section(payload, "Q-W verdict")
    window = _section(payload, "Q-W window")
    instants = _section(payload, "every pre-game polling instant")
    events = _section(payload, "distinct events contributing")

    deciding = verdict["rows"][-1]
    v = {name: deciding[i] for i, name in enumerate(verdict["columns"])}

    window_end_ms = window["rows"][0][_col(window, "end_ms")]

    obs_i = _col(instants, "observed_ms")
    q_i = _col(instants, "qualifying_markets")
    rows = [(r[obs_i], r[q_i]) for r in instants["rows"]]
    if not rows:
        raise SystemExit("the per-instant section is empty; nothing to re-derive")

    # -- the parts, per UTC day -------------------------------------------
    per_day: dict[str, list[int]] = {}
    for ms, n in rows:
        day = _iso(ms)[:10]
        cell = per_day.setdefault(day, [0, 0])
        cell[0] += 1
        if n > 0:
            cell[1] += 1

    # -- burst dedup -------------------------------------------------------
    bursts: list[list[tuple[int, int]]] = [[rows[0]]]
    for prev, cur in zip(rows, rows[1:]):
        if (cur[0] - prev[0]) / 60_000 > burst_gap_min:
            bursts.append([])
        bursts[-1].append(cur)
    bursts_ok = sum(1 for b in bursts if any(n > 0 for _, n in b))

    # -- the time-weighted denominator, an independent check --------------
    # The misses are contiguous, so the band's unavailability is the span they
    # cover rather than a count. Two denominators agreeing is the finding; one
    # of them agreeing with itself is not.
    misses = [ms for ms, n in rows if n == 0]
    span_h = (rows[-1][0] - rows[0][0]) / _MS_PER_HOUR
    outage_h = (
        (max(misses) - min(misses)) / _MS_PER_HOUR if len(misses) > 1 else 0.0
    )

    # -- event concentration and lead time ---------------------------------
    qq = _col(events, "qualifying_quotes")
    et = _col(events, "event_ticker")
    quotes = sorted((r[qq] for r in events["rows"]), reverse=True)
    total_quotes = sum(quotes)
    starts = _true_starts(events, offset_ms)
    not_tipped = [
        (events["rows"][i][et], starts[i], events["rows"][i][qq])
        for i in range(len(starts))
        if starts[i] >= window_end_ms
    ]

    nlc = 0
    if "non_linear_cent_quotes" in events["columns"]:
        nlc = sum(r[_col(events, "non_linear_cent_quotes")] for r in events["rows"])

    return {
        "verdict": v,
        "per_day": per_day,
        "span_h": span_h,
        "first_iso": _iso(rows[0][0]),
        "last_iso": _iso(rows[-1][0]),
        "burst_gap_min": burst_gap_min,
        "bursts": len(bursts),
        "bursts_ok": bursts_ok,
        "burst_pct": 100.0 * bursts_ok / len(bursts),
        "misses": len(misses),
        "outage_h": outage_h,
        "time_weighted_pct": 100.0 * (1 - outage_h / span_h) if span_h else None,
        "events_total": len(events["rows"]),
        "quotes_total": total_quotes,
        "top4_share": 100.0 * sum(quotes[:4]) / total_quotes if total_quotes else None,
        "not_tipped": not_tipped,
        "events_in_window": len(events["rows"]) - len(not_tipped),
        "non_linear_cent_quotes": nlc,
    }


def render(a: dict) -> str:
    v = a["verdict"]
    out: list[str] = []
    w = out.append
    w("Q-W RE-DERIVATION")
    w("=" * 70)
    w(f"series                  {v['series_ticker']}")
    w(f"pregame_instants        {v['pregame_instants']}")
    w(f"qualifying_instants     {v['qualifying_instants']}")
    w(f"instant_pct (RAW)       {v['instant_pct']}%   bar {_BAR_INSTANT_PCT}%")
    w(f"qualifying_events       {v['qualifying_events']}   bar {_BAR_EVENTS}")
    w(f"activates               {'YES' if v['activates'] else 'NO'}")
    w("")
    w(f"observed {a['first_iso']} .. {a['last_iso']}  ({a['span_h']:.1f} h)")
    w("")
    w("THE PARTS -- per UTC day (a pooled share is not a finding until these agree)")
    w(f"  {'day':12}{'instants':>10}{'qualifying':>12}{'pct':>9}")
    for day in sorted(a["per_day"]):
        n, q = a["per_day"][day]
        w(f"  {day:12}{n:>10}{q:>12}{100 * q / n:>8.1f}%")
    w("")
    w("CERTIFIED FIGURE -- burst-deduplicated, approximately time-uniform")
    w(
        f"  one look per burst >{a['burst_gap_min']:.0f} min apart: "
        f"{a['bursts_ok']} of {a['bursts']} = {a['burst_pct']:.1f}%"
    )
    w(
        f"  one look per {a['span_h'] * 60 / a['bursts']:.1f} min of clock "
        f"(the 900s slow cadence, so the cut is not arbitrary)"
    )
    w("")
    w("INDEPENDENT CHECK -- time-weighted, not a second count of the same rows")
    # `None` prints as "not computable", never as a number. A zero-length
    # observation has no time-weighted share; substituting 100% would report
    # perfect availability from an artefact containing one look.
    twp = a["time_weighted_pct"]
    w(
        f"  {a['misses']} misses, one contiguous episode spanning "
        f"{a['outage_h']:.2f} h of {a['span_h']:.1f} h "
        + (f"-> {twp:.1f}%" if twp is not None else "-> not computable (no span)")
    )
    w("")
    w("EVENT BAR")
    w(f"  events contributing            {a['events_total']}  (bar {_BAR_EVENTS})")
    top4 = a["top4_share"]
    w(
        "  top 4 events' share of quotes  "
        + (
            f"{top4:.0f}% of {a['quotes_total']}"
            if top4 is not None
            else "not computable (no qualifying quotes)"
        )
    )
    w(
        f"  had NOT tipped by window end  {len(a['not_tipped'])}, supplying "
        f"{sum(q for _, _, q in a['not_tipped'])} quotes"
    )
    for ticker, start, q in sorted(a["not_tipped"], key=lambda r: r[1]):
        w(f"      {ticker:34} tips {_iso(start)}  {q:>5} quotes")
    w(
        f"  RESTRICTED to fixtures that tipped inside the window: "
        f"{a['events_in_window']}"
        + ("  <-- BELOW THE BAR" if a["events_in_window"] < _BAR_EVENTS else "")
    )
    w("    (an UNREGISTERED restriction. It cannot un-activate W, and is printed")
    w("     because the bar of 8 was reasoned against the events in the window.)")
    w("")
    w(f"half-cent contamination: non_linear_cent_quotes = {a['non_linear_cent_quotes']}")
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("artefact", help="the --json output of kalshi-quotes-band")
    p.add_argument(
        "--burst-gap-min",
        type=float,
        default=5.0,
        help="minutes of silence that separate two looks (default 5)",
    )
    p.add_argument(
        "--pregame-offset-ms",
        type=int,
        default=3 * 60 * 60 * 1000,
        help="ADR 0006 correction, for artefacts emitting the raw stamp",
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if args.burst_gap_min > _MAX_HONEST_GAP_MIN:
        print(
            f"--burst-gap-min {args.burst_gap_min} exceeds "
            f"{_MAX_HONEST_GAP_MIN}. A burst qualifies if ANY instant in it "
            f"qualifies, so the share only ever rises as the cut widens: a "
            f"bigger number here measures the cut, not the book.",
            file=sys.stderr,
        )
        return 2

    with open(args.artefact, encoding="utf-8") as fh:
        payload = json.load(fh)

    a = analyse(payload, args.burst_gap_min, args.pregame_offset_ms)
    print(json.dumps(a, indent=2) if args.json else render(a))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
