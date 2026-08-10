"""Repeat-poll capture for the `last_update` scrape-clock question. SPENDS 24 CREDITS.

Executes the capture half of
`docs/measurements/2026-08-10-preregistration-odds-last-update-repeat-poll.md`.
**Read that registration before changing anything here.** Every constant below
is fixed by it and none may be re-derived after the run.

    .venv\\Scripts\\python.exe scripts/capture_odds_repeat_poll.py --dry-run
    .venv\\Scripts\\python.exe scripts/capture_odds_repeat_poll.py --confirm-spend-24

Four polls of one sport at `T0`, `+60 s`, `+300 s`, `+900 s`. Six credits each,
24 total, ~15 minutes wall clock. **There is no second attempt at a slate** --
if this aborts halfway the credits are gone and the slate has moved.

**This script captures and does not analyse.** It writes four raw payloads and
stops. `scripts/analyse_odds_repeat_poll.py` reads only those files and computes
every number. That split is precondition P6: it makes the analysis re-runnable
offline forever at zero credit cost, so a bug in the statistic costs nothing.

**The parser is the deployed one (P5).** Rows come from `OddsClient._parse`, so
the population analysed is the one the deployed `stale_odds` guard actually
sees -- `h2h_lay` excluded, market-level `last_update` preferred over
bookmaker-level. A bespoke parser here would answer a question about a
different set of rows, which is how this repo previously published a
denominator of 335 that should have been 320.

**The credential must not reach a file or a log line (P2).** The Odds API takes
its key as a **query parameter** and `httpx` logs full URLs at INFO -- that is
exactly how it leaked once, and `backend/logging_setup.py` exists because of
it. So: `configure_logging()` is the first statement; `response.url` is never
read, logged, or serialised; and every artefact is asserted free of both the
key and the string `apiKey` *before* it is written. **The repo is public and
these files are world-readable the moment they are pushed.**

**A `[]` return is a refusal, not a slate.** `fetch_odds` returns `[]` when the
budget refuses (`client.py:233`), which at the call site is indistinguishable
from an empty slate. Any empty poll aborts the capture and is recorded as an
abort, never analysed as a finding.

## What this script does NOT establish

Nothing. It is a recorder. It computes no statistic, prints no verdict, and
deliberately does not import the analysis module -- so no result can be
previewed while the capture is still running and the schedule could still be
altered in response to it. The registration fixes `S >= 0.90` for CONFIRMED and
`S <= 0.20` for REFUTED; both live in the analysis script.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import OddsConfig  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402
from backend.odds.budget import CreditBudget, sweep_cost  # noqa: E402
from backend.odds.client import OddsClient  # noqa: E402
from backend.store import db  # noqa: E402

logger = logging.getLogger("capture_repeat_poll")

# --- Fixed by the registration. Do not tune. ---------------------------------

# §5.1. Offsets from T0 in seconds. The primary pair is index 1 -> 3 (300 s),
# BY INDEX and never by realised interval -- selecting the pair closest to 300 s
# after the fact would be choosing a cut from the data (§5.1, interval slippage).
POLL_OFFSETS_S: tuple[int, ...] = (0, 60, 300, 900)

# §P1 / §C4. Four calls at markets x regions = 3 x 2 = 6 credits each.
REQUIRED_CREDITS = 24

# §P4. The slate rule, both halves measured from a zero-credit source.
NO_COMMENCE_WITHIN_S = 20 * 60      # nothing may start in the 20 min after T0
MIN_EVENTS_WITHIN_S = 6 * 3600      # at least 5 must start within 6 h
MIN_EVENTS_IN_WINDOW = 5

DEFAULT_SPORT = "baseball_mlb"


def _utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# P2 -- the credential guard. Applied to every artefact before it is written.
# ---------------------------------------------------------------------------


def assert_no_credential(text: str, api_key: str, *, what: str) -> None:
    """Refuse to write anything carrying the key, or a query string that could.

    Two checks, not one. The key itself is the obvious hazard; `apiKey` catches
    a serialised request URL that would carry it even if this particular key
    were later rotated. Raises rather than warns -- a warning nobody reads is
    not a control, and this file is destined for a public repository.
    """
    if api_key and api_key in text:
        raise RuntimeError(
            f"REFUSING TO WRITE {what}: it contains the live ODDS_API_KEY. "
            "The key is now in this process's memory only -- do not paste any "
            "part of this payload anywhere. Rotate if it reached disk."
        )
    if "apiKey" in text:
        raise RuntimeError(
            f"REFUSING TO WRITE {what}: it contains the string 'apiKey', which "
            "means a request URL has been serialised. The Odds API puts the "
            "credential in the query string. See tasks/lessons.md."
        )


class _RawCapturingClient(httpx.AsyncClient):
    """An `AsyncClient` that keeps each response's raw body text.

    Needed because `OddsClient.fetch_odds` hands `response.json()` to the
    parser, and the registration's TEXT_FLOAT_MISMATCH check (§5.3) needs the
    **original JSON price tokens**, not floats that have already round-tripped
    through Python. `json.loads(text, parse_float=str)` recovers them exactly.

    It keeps the body only. **`response.url` is never touched** -- that is where
    the credential lives.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.last_body: Optional[str] = None
        self.last_headers: dict[str, str] = {}

    async def send(self, *args: Any, **kwargs: Any) -> httpx.Response:
        response = await super().send(*args, **kwargs)
        await response.aread()
        self.last_body = response.text
        # Only the two credit headers, copied by name. Never the whole header
        # set and never the request.
        self.last_headers = {
            k: response.headers[k]
            for k in ("x-requests-remaining", "x-requests-used")
            if k in response.headers
        }
        return response


# ---------------------------------------------------------------------------
# P4 -- the slate rule, decided from ESPN. Zero credits.
# ---------------------------------------------------------------------------


def check_slate(sport_key: str, t0_ms: int) -> tuple[bool, str, list[int]]:
    """P4: no kickoff in the 20 min after T0, and >=5 within 6 h.

    Uses the ESPN scoreboard path already in `measure_slot_coverage.py`: no key,
    no auth, no Odds API credit. Deciding the slate rule from a *paid* source
    would mean spending a credit to learn whether to spend credits, and the
    first poll would then be inside the window it was supposed to validate.

    Both UTC dates are fetched: a US evening slate straddles UTC midnight, so
    reading only "today" drops the late games this rule is mostly about.
    """
    from measure_slot_coverage import fetch_slate  # noqa: E402

    t0 = datetime.fromtimestamp(t0_ms / 1000, timezone.utc)
    dates = {t0.strftime("%Y%m%d"), (t0 + timedelta(days=1)).strftime("%Y%m%d")}

    games: list[int] = []
    for date in sorted(dates):
        for game in fetch_slate(date, sport_keys=[sport_key]):
            games.append(game.commence_ms)
    games = sorted(set(games))

    imminent = [g for g in games if t0_ms < g <= t0_ms + NO_COMMENCE_WITHIN_S * 1000]
    within = [g for g in games if t0_ms < g <= t0_ms + MIN_EVENTS_WITHIN_S * 1000]

    if imminent:
        return False, (
            f"P4 FAIL: {len(imminent)} event(s) commence within "
            f"{NO_COMMENCE_WITHIN_S // 60} min of T0 (first {_utc(imminent[0])}). "
            "In-play repricing would confound every cell."
        ), games
    if len(within) < MIN_EVENTS_IN_WINDOW:
        return False, (
            f"P4 FAIL: only {len(within)} event(s) commence within "
            f"{MIN_EVENTS_WITHIN_S // 3600} h of T0; the rule needs "
            f">= {MIN_EVENTS_IN_WINDOW}. A slate this thin cannot populate the "
            "cells and the books may not be actively quoted at all."
        ), games
    return True, (
        f"P4 pass: 0 kickoffs within {NO_COMMENCE_WITHIN_S // 60} min, "
        f"{len(within)} within {MIN_EVENTS_WITHIN_S // 3600} h "
        f"(of {len(games)} known)."
    ), games


# ---------------------------------------------------------------------------
# The capture
# ---------------------------------------------------------------------------


async def run_capture(
    *, sport_key: str, out_dir: Path, db_path: str, dry_run: bool
) -> int:
    base_config = OddsConfig.load()
    cost = sweep_cost(base_config.markets, base_config.regions)
    total = cost * len(POLL_OFFSETS_S)

    print("=" * 72)
    print("REPEAT-POLL CAPTURE -- last_update scrape clock")
    print("registration: docs/measurements/"
          "2026-08-10-preregistration-odds-last-update-repeat-poll.md")
    print("=" * 72)
    print(f"sport          {sport_key}")
    print(f"markets x regions  {base_config.markets} x {base_config.regions}")
    print(f"cost per poll  {cost}   polls {len(POLL_OFFSETS_S)}   TOTAL {total}")
    print(f"offsets (s)    {list(POLL_OFFSETS_S)}")

    if total != REQUIRED_CREDITS:
        print(f"\nABORT: this capture would cost {total} credits, not the "
              f"{REQUIRED_CREDITS} the registration authorises. Config has "
              "moved; amend the registration rather than the arithmetic.")
        return 2

    conn = db.init_db(db_path)
    t0_ms = _now_ms()

    # --- P4, before anything is spent -------------------------------------
    ok, message, games = check_slate(sport_key, t0_ms)
    print(f"\n{message}")
    if games:
        print(f"  next kickoffs: "
              f"{', '.join(_utc(g) for g in games[:4])}")
    if not ok:
        print("\nP4 failed. Nothing spent. The registration says the capture "
              "waits for a day when the rule can be met -- it is not "
              "worked around.")
        return 3

    # --- P1, budget headroom, measured not assumed ------------------------
    #
    # The daily cap is deliberately raised to exactly the authorised spend and
    # no further. §C4: at the default 16 the THIRD call is the first refusal
    # (12 spent, 4 left, 6 needed) -- not the fourth. The monthly ceiling and
    # the server's own `x-requests-remaining` are NOT touched and still refuse.
    config = replace(base_config, daily_credit_budget=REQUIRED_CREDITS)
    budget = CreditBudget(
        conn,
        daily_budget=config.daily_credit_budget,
        monthly_budget=config.monthly_credit_budget,
        day_start_hour=config.budget_day_start_utc_hour,
    )
    state = budget.state(t0_ms)
    print("\nP1 -- budget headroom")
    print(f"  daily cap raised for this capture: "
          f"{base_config.daily_credit_budget} -> {config.daily_credit_budget} "
          f"(deliberate; monthly and server ceilings untouched)")
    print(f"  spent today            {state.spent_today}")
    print(f"  remaining today        {state.remaining_today}")
    print(f"  spent this month       {state.spent_this_month}")
    print(f"  remaining this month   {state.remaining_this_month}")
    print(f"  server remaining (last recorded)  {state.remaining_reported}")
    print(f"  server used     (last recorded)   {state.used_reported}")

    failures = []
    if state.remaining_today < REQUIRED_CREDITS:
        failures.append(f"remaining_today {state.remaining_today} < {REQUIRED_CREDITS}")
    if (state.remaining_this_month is not None
            and state.remaining_this_month < REQUIRED_CREDITS):
        failures.append(
            f"remaining_this_month {state.remaining_this_month} < {REQUIRED_CREDITS}"
        )
    if (state.remaining_reported is not None
            and state.remaining_reported < REQUIRED_CREDITS):
        failures.append(
            f"server x-requests-remaining {state.remaining_reported} "
            f"< {REQUIRED_CREDITS}"
        )
    if state.remaining_reported is None:
        print("  NOTE: no server credit count has ever been recorded in this "
              "database, so the third P1 check cannot be made in advance. It "
              "is enforced after poll 1 instead, against the live header.")

    if failures:
        print("\nP1 FAIL: " + "; ".join(failures))
        print("Nothing spent.")
        return 4
    print("  P1 pass (subject to the live header check after poll 1)")

    if dry_run:
        print("\n--dry-run: preconditions only. NOTHING SPENT, no poll made.")
        print("Re-run with --confirm-spend-24 to capture.")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    run_tag = datetime.fromtimestamp(t0_ms / 1000, timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    print(f"\nCAPTURING. ~{POLL_OFFSETS_S[-1] // 60} minutes. Do not interrupt.")
    print(f"artefacts -> {out_dir}/repeat_poll_{run_tag}_p*.json\n")

    written: list[Path] = []
    async with _RawCapturingClient(timeout=30.0) as http:
        async with OddsClient(config, budget, client=http) as odds:
            for index, offset in enumerate(POLL_OFFSETS_S, start=1):
                target = t0_ms + offset * 1000
                wait_s = max(0.0, (target - _now_ms()) / 1000)
                if wait_s > 0:
                    print(f"  waiting {wait_s:6.1f}s for poll {index} "
                          f"(T0+{offset}s)")
                    await asyncio.sleep(wait_s)

                fetched_ms = _now_ms()
                quotes = await odds.fetch_odds(sport_key, now_ms=fetched_ms)

                if not quotes:
                    print(f"\nABORT at poll {index}: fetch_odds returned []. "
                          "That is a budget REFUSAL or an empty slate, and the "
                          "two are indistinguishable at the call site (§P1). "
                          "No verdict may be issued from a partial capture.")
                    return 5

                body = http.last_body or ""
                headers = dict(http.last_headers)
                remaining = headers.get("x-requests-remaining")
                used = headers.get("x-requests-used")

                # The live P1 check, enforced from poll 1 onward against the
                # server's own count rather than our tally of it.
                still_needed = cost * (len(POLL_OFFSETS_S) - index)
                if remaining is not None and int(remaining) < still_needed:
                    print(f"\nABORT at poll {index}: server reports "
                          f"{remaining} credits remaining, {still_needed} still "
                          "needed. Stopping before a refusal is mistaken for an "
                          "empty slate.")
                    return 6

                artefact = {
                    "registration": (
                        "docs/measurements/"
                        "2026-08-10-preregistration-odds-last-update-repeat-poll.md"
                    ),
                    "poll_index": index,
                    "nominal_offset_s": offset,
                    "t0_ms": t0_ms,
                    "fetched_ms": fetched_ms,
                    "realised_offset_s": round((fetched_ms - t0_ms) / 1000, 3),
                    "sport_key": sport_key,
                    "markets": list(config.markets),
                    "regions": list(config.regions),
                    "cost_credits": cost,
                    "x_requests_remaining": remaining,
                    "x_requests_used": used,
                    "n_quotes_parsed": len(quotes),
                    # The verbatim body. NOT the URL -- that carries the key.
                    "payload": json.loads(body),
                    # Same body with every JSON float left as its ORIGINAL
                    # token, for the TEXT_FLOAT_MISMATCH check in §5.3.
                    "payload_raw_tokens": json.loads(body, parse_float=str),
                }
                serialised = json.dumps(artefact, indent=1, sort_keys=True)
                assert_no_credential(
                    serialised, config.api_key, what=f"poll {index} artefact"
                )

                path = out_dir / f"repeat_poll_{run_tag}_p{index}.json"
                path.write_text(serialised, encoding="utf-8")
                written.append(path)

                print(f"  poll {index}  T0+{offset:4d}s  "
                      f"realised +{artefact['realised_offset_s']:7.1f}s  "
                      f"quotes {len(quotes):5d}  "
                      f"server remaining {remaining}  -> {path.name}")

    final = budget.state(_now_ms())
    print("\nP1 recheck after poll 4")
    print(f"  spent today          {final.spent_today}")
    print(f"  server remaining     {final.remaining_reported}")
    print(f"  server used          {final.used_reported}")
    print(f"  our tally minus theirs (drift)  {final.drift}")

    print(f"\nCAPTURE COMPLETE. {len(written)} artefacts written.")
    print("Nothing has been analysed. Next, at zero credit cost:")
    print(f"  .venv\\Scripts\\python.exe scripts/analyse_odds_repeat_poll.py "
          f"{out_dir}/repeat_poll_{run_tag}_p*.json")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Repeat-poll capture. SPENDS 24 Odds API credits."
    )
    parser.add_argument("--sport", default=DEFAULT_SPORT)
    parser.add_argument("--db", default="kalshi.db")
    parser.add_argument(
        "--out-dir",
        default="docs/measurements/data",
        help="Where the four raw payloads are written.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check every precondition and stop. Spends nothing.",
    )
    parser.add_argument(
        "--confirm-spend-24",
        action="store_true",
        help="Required to actually spend. Without it this refuses to poll.",
    )
    args = parser.parse_args(argv)

    # First statement that matters. Not `logging.basicConfig`: httpx logs full
    # request URLs at INFO and the Odds API key rides in the query string.
    configure_logging(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not args.dry_run and not args.confirm_spend_24:
        print("Refusing to spend without --confirm-spend-24.")
        print("Run --dry-run first; it checks every precondition for free.")
        return 1

    return asyncio.run(
        run_capture(
            sport_key=args.sport,
            out_dir=Path(args.out_dir),
            db_path=args.db,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
