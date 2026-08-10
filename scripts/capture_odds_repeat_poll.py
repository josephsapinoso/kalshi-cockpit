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

**P1 clause 3 is read live from `/sports`, and a `None` refuses.** The Odds API
does not meter `/sports` -- `scripts/setup_odds_key.sh` `probe_key` has called
it since the key was installed -- so the account's own `x-requests-remaining`
costs nothing and is obtainable *before* poll 1. It used to be read from
`state.remaining_reported`, this database's cache of the last header it saw,
which is `None` on a laptop whose `api_credits` table is empty; the clause was
guarded by `is not None` and so could never fail. Clause 2 had the same shape.
**Two of P1's three registered clauses were unenforceable on the machine this
script is built to run on, and the script printed `P1 pass`.** See Amendment A
of the registration. Every clause now reports one of `PASS` / `FAIL` /
`NOT-APPLICABLE` explicitly, an unreadable probe is a `FAIL`, and the whole of
P1 cannot pass unless clause 3 is a live `PASS`.

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
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

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

# §P1 clause 3. `/sports` is NOT metered by The Odds API -- it is what
# `scripts/setup_odds_key.sh` `probe_key` (~:227-239) has called since the key
# was installed, and it returns the same `x-requests-remaining` header the
# metered endpoints do. So the account-truthful credit count is free, and it is
# free *before* poll 1, which is the only moment at which it is a precondition.
SPORTS_PROBE_PATH = "/sports"
PROBE_TIMEOUT_S = 20.0

# The three states a P1 clause can be in. Three, not two: a clause that does
# not bind must SAY so in the output. The defect this replaces was a clause
# that did not bind and said nothing at all.
CLAUSE_PASS = "PASS"
CLAUSE_FAIL = "FAIL"
CLAUSE_NOT_APPLICABLE = "NOT-APPLICABLE"

CLAUSE_DAILY = "clause 1 -- remaining_today (our daily cap)"
CLAUSE_MONTHLY = "clause 2 -- remaining_this_month (our own monthly ceiling)"
CLAUSE_SERVER = "clause 3 -- x-requests-remaining (live /sports probe)"


def _utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _now_ms() -> int:
    return int(time.time() * 1000)


def _as_int(raw: Any) -> Optional[int]:
    """Parse a header value to `int`, or `None`. Never `0` on failure.

    The repo rule, and the whole subject of Amendment A: unreadable resolves to
    `None`, and callers refuse or say so rather than substitute a number.
    """
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


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
# P1 -- the three clauses, each with an explicit state. Zero credits.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClauseResult:
    """One P1 clause and the state it resolved to.

    `state` is one of `PASS`, `FAIL`, `NOT-APPLICABLE`. The third exists so
    that a clause which genuinely does not bind is **visible as such** rather
    than contributing silence to a list of failures. Silence is what let two of
    P1's three clauses be unenforceable while the script printed `P1 pass`.
    """

    name: str
    state: str
    detail: str


async def probe_server_credits(
    config: OddsConfig, *, http: Optional[httpx.AsyncClient] = None
) -> tuple[Optional[int], str]:
    """Read the account's own `x-requests-remaining` from `/sports`. Free.

    Returns `(remaining, detail)`. **`remaining` is `None` on every failure
    path** -- transport error, non-200, absent header, unparseable header --
    and a `None` makes P1 clause 3 FAIL. It is never coerced to 0, never
    coerced to "assume plenty", and never skipped. `tasks/lessons.md`:
    *unreadable resolves to `None`, never `0`; callers refuse rather than
    substitute.* ADR 0024 is what the other direction costs.

    **P2 -- what is deliberately not read.** `response.url`,
    `response.request.url` and `config.api_key` are never touched, and on an
    exception only `type(exc).__name__` is returned: `httpx` puts the full
    request URL in its exception text, and this provider takes the credential
    as a query parameter. The repo is public.

    A dedicated short-lived client is used rather than the capture's
    `_RawCapturingClient`, so a probe body can never end up in a poll artefact.
    `http` is injectable for tests, which drive it through
    `httpx.MockTransport` and never over the network.
    """
    url = f"{config.base_url.rstrip('/')}{SPORTS_PROBE_PATH}"
    params = {"apiKey": config.api_key}

    async def _call(client: httpx.AsyncClient) -> tuple[Optional[int], str]:
        try:
            response = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            return None, (
                f"the /sports probe raised {type(exc).__name__}. Its message is "
                "deliberately not printed -- httpx puts the full request URL in "
                "exception text and the credential rides in the query string."
            )
        if response.status_code != 200:
            return None, (
                f"the /sports probe returned HTTP {response.status_code}. "
                "No credit count was obtained."
            )
        raw = response.headers.get("x-requests-remaining")
        if raw is None:
            return None, (
                "the /sports response carried no x-requests-remaining header."
            )
        parsed = _as_int(raw)
        if parsed is None:
            return None, (
                f"x-requests-remaining was present but not an integer: "
                f"{str(raw)[:32]!r}."
            )
        return parsed, "read live from the /sports response header (zero credits)."

    if http is not None:
        return await _call(http)
    async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_S) as client:
        return await _call(client)


def evaluate_p1(
    *,
    remaining_today: Optional[int],
    monthly_budget: Optional[int],
    remaining_this_month: Optional[int],
    live_remaining: Optional[int],
    probe_detail: str = "",
    required: int = REQUIRED_CREDITS,
) -> list[ClauseResult]:
    """The registration's three P1 clauses, each resolved to an explicit state.

    Pure: no I/O, no clock, no database. Everything it decides on is an
    argument, which is what makes "can this clause fail?" a testable question
    rather than an inspection.

    **The design decision on clause 2, stated rather than implied.** An unset
    `ODDS_MONTHLY_CREDIT_BUDGET` is `NOT-APPLICABLE`, not a `FAIL` -- and the
    reason is that clause 2 and clause 3 measure different things. Clause 3 is
    the **account's** remaining allowance for the period, which is the ceiling
    that actually stops answering; on this plan the Odds API's period *is* the
    calendar month, so clause 3 already binds the monthly quantity the
    registration cared about. Clause 2 is a **self-imposed** reservation whose
    stated purpose (`budget.py:186-191`) is to keep headroom for another lane,
    not to protect the account. An unset optional ceiling is a configured
    absence -- a decision not to reserve -- not a failed read of a fact that
    exists. Refusing on it would be refusing because nobody asked for a second
    limit.

    That is only defensible because of the coupling in `p1_passes`: **clause 3
    can never be `NOT-APPLICABLE`, and P1 cannot pass unless clause 3 is a live
    `PASS`.** So the state in which two of three clauses fail to bind -- the
    defect this replaces -- is now unreachable, whatever `.env` holds.

    And the converse is enforced: if a monthly ceiling **is** configured but
    its headroom reads `None`, that is an unreadable input to a clause that was
    asked for, and it `FAIL`s.
    """
    results: list[ClauseResult] = []

    if remaining_today is None:
        results.append(ClauseResult(
            CLAUSE_DAILY, CLAUSE_FAIL,
            "remaining_today is None -- unreadable, and an unreadable ceiling "
            "refuses. It is never substituted with a number.",
        ))
    elif remaining_today < required:
        results.append(ClauseResult(
            CLAUSE_DAILY, CLAUSE_FAIL,
            f"remaining_today {remaining_today} < {required}.",
        ))
    else:
        results.append(ClauseResult(
            CLAUSE_DAILY, CLAUSE_PASS,
            f"remaining_today {remaining_today} >= {required}.",
        ))

    if monthly_budget is None:
        results.append(ClauseResult(
            CLAUSE_MONTHLY, CLAUSE_NOT_APPLICABLE,
            "ODDS_MONTHLY_CREDIT_BUDGET is unset, so no self-imposed monthly "
            "ceiling exists to check. This is a configured absence, not a "
            "failed read. The account's own monthly allowance is clause 3, "
            "which is live and cannot be skipped.",
        ))
    elif remaining_this_month is None:
        results.append(ClauseResult(
            CLAUSE_MONTHLY, CLAUSE_FAIL,
            f"ODDS_MONTHLY_CREDIT_BUDGET is set to {monthly_budget} but its "
            "remaining headroom read as None. A ceiling that was asked for and "
            "cannot be read refuses.",
        ))
    elif remaining_this_month < required:
        results.append(ClauseResult(
            CLAUSE_MONTHLY, CLAUSE_FAIL,
            f"remaining_this_month {remaining_this_month} < {required} "
            f"(ceiling {monthly_budget}).",
        ))
    else:
        results.append(ClauseResult(
            CLAUSE_MONTHLY, CLAUSE_PASS,
            f"remaining_this_month {remaining_this_month} >= {required} "
            f"(ceiling {monthly_budget}).",
        ))

    if live_remaining is None:
        results.append(ClauseResult(
            CLAUSE_SERVER, CLAUSE_FAIL,
            "no live credit count was obtained, so the account's own headroom "
            "is unknown. Unknown refuses; nothing is spent. "
            + (probe_detail or ""),
        ))
    elif live_remaining < required:
        results.append(ClauseResult(
            CLAUSE_SERVER, CLAUSE_FAIL,
            f"the account reports {live_remaining} credits remaining this "
            f"period, < {required}.",
        ))
    else:
        results.append(ClauseResult(
            CLAUSE_SERVER, CLAUSE_PASS,
            f"the account reports {live_remaining} credits remaining this "
            f"period, >= {required}. " + (probe_detail or ""),
        ))

    return results


def p1_passes(results: Sequence[ClauseResult]) -> bool:
    """P1 passes only if nothing failed **and** clause 3 is a live `PASS`.

    The second condition is the structural guard, not a belt-and-braces one.
    Without it a future edit that reintroduced a skippable clause 3 would once
    again make P1 pass on a machine that had never asked the account anything.
    `NOT-APPLICABLE` is a legitimate state for the self-imposed monthly ceiling
    and is not a legitimate state for the account's own.
    """
    if any(r.state == CLAUSE_FAIL for r in results):
        return False
    server = [r for r in results if r.name == CLAUSE_SERVER]
    if len(server) != 1 or server[0].state != CLAUSE_PASS:
        return False
    return True


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
    *,
    sport_key: str,
    out_dir: Path,
    db_path: str,
    dry_run: bool,
    probe_client: Optional[httpx.AsyncClient] = None,
) -> int:
    """Run the capture. `probe_client` is a test seam for the `/sports` probe.

    `probe_client` is `None` in every production path, so the probe opens and
    closes its own client. Tests pass an `httpx.MockTransport`-backed client;
    nothing in this module reaches the network under test.
    """
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
    # (12 spent, 4 left, 6 needed) -- not the fourth.
    #
    # **Clause 3 is now read live from a zero-credit `/sports` probe, and an
    # unreadable answer refuses.** It used to be read from
    # `state.remaining_reported` -- this database's cache of the last header it
    # happened to see -- and guarded by `is not None`. On a laptop whose
    # `api_credits` table is empty that cache is `None`, so the clause could not
    # append a failure; clause 2 was in the same shape whenever
    # `ODDS_MONTHLY_CREDIT_BUDGET` was unset. Two of the three registered
    # clauses were unenforceable on the machine this script runs on and it
    # printed `P1 pass` anyway. See Amendment A of the registration.
    config = replace(base_config, daily_credit_budget=REQUIRED_CREDITS)
    budget = CreditBudget(
        conn,
        daily_budget=config.daily_credit_budget,
        monthly_budget=config.monthly_credit_budget,
        day_start_hour=config.budget_day_start_utc_hour,
    )
    state = budget.state(t0_ms)

    live_remaining, probe_detail = await probe_server_credits(
        config, http=probe_client
    )

    print("\nP1 -- budget headroom")
    print(f"  daily cap raised for this capture: "
          f"{base_config.daily_credit_budget} -> {config.daily_credit_budget} "
          f"(deliberate; the account's own ceiling is clause 3 and is live)")
    print(f"  spent today            {state.spent_today}")
    print(f"  remaining today        {state.remaining_today}")
    print(f"  spent this month       {state.spent_this_month}")
    print(f"  remaining this month   {state.remaining_this_month}")
    print(f"  monthly ceiling (ours) {config.monthly_credit_budget}")
    print(f"  live /sports probe     {live_remaining}   ({probe_detail})")
    print(f"  cached header, THIS DB, not a P1 input: "
          f"remaining={state.remaining_reported} used={state.used_reported}")

    results = evaluate_p1(
        remaining_today=state.remaining_today,
        monthly_budget=config.monthly_credit_budget,
        remaining_this_month=state.remaining_this_month,
        live_remaining=live_remaining,
        probe_detail=probe_detail,
    )
    for result in results:
        print(f"  [{result.state:>14}] {result.name}")
        print(f"                   {result.detail}")

    if not p1_passes(results):
        print("\nP1 FAIL. Nothing spent. The registration is amended rather "
              "than worked around.")
        return 4
    print("  P1 pass -- all three clauses evaluated, none skipped, and the "
          "account's own count was read live before anything was spent.")

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

                # The in-flight backstop, not P1. P1 already established
                # `live >= 24` against the account before poll 1, so this asks
                # only the weaker in-capture question -- can the REMAINING
                # polls still be paid for -- hence `still_needed` counts the
                # polls not yet made (18 at poll 1, not 24). It is a backstop
                # against the account being drained by another instance
                # mid-capture, which is the per-database/per-account gap
                # `tasks/NEXT.md` records.
                #
                # An absent or unparseable header here does NOT abort. The
                # spend is already bounded three ways -- the daily cap is
                # exactly 24, P1 read the account live, and §8 fixes the
                # capture at four calls -- and aborting a one-shot capture on a
                # transient header would burn the credits already spent for
                # nothing. It is printed loudly instead of skipped silently,
                # which is the difference that matters.
                still_needed = cost * (len(POLL_OFFSETS_S) - index)
                remaining_int = _as_int(remaining)
                if remaining_int is None:
                    print(f"  WARNING poll {index}: no readable "
                          f"x-requests-remaining header (value {remaining!r}). "
                          "The in-flight backstop cannot evaluate this poll. "
                          "Continuing: P1 read the account live before poll 1 "
                          "and the daily cap is pinned at "
                          f"{REQUIRED_CREDITS}.")
                elif remaining_int < still_needed:
                    print(f"\nABORT at poll {index}: server reports "
                          f"{remaining_int} credits remaining, {still_needed} "
                          "still needed. Stopping before a refusal is mistaken "
                          "for an empty slate.")
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
