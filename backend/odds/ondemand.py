"""The tap that buys fresh odds, and every ceiling standing between the two.

**Why this exists.** `_live_ages` in the API re-checks the stored odds against
*now* on every page load, so a row is dead `MAX_ODDS_AGE_S` after the sweep that
priced it whatever it looked like when it was written. The rolling refresh
(`docs/adr/0030`) keeps that window open across a planned kickoff cluster, which
covers the hour a bet is most likely to be placed in and covers nothing else. A
person who opens the cockpit two hours before first pitch sees a full slate
struck through, and the reason is a clock rather than a price.

Refreshing on demand is the missing half. It cannot be a free action -- every
refresh is a metered `/odds` call, and a player-prop refresh is twenty credits
for one fixture -- so the whole of this module is about what a tap is allowed to
cost.

**Single writer, on purpose.** The API process opens the database read-only
(`entrypoint.sh` runs it as a separate process from the chain runner, and
`routes.py:398` opens `read_only=True`), so a request cannot be a row. It is a
file, and only the API ever writes it. The runner reads and never writes back.
Two processes doing read-modify-write on one JSON file is a lost update waiting
for a busy evening, and the cooldown it would lose is the one thing here holding
the spend down.

The cost of single-writer is that the runner has no durable record of what it
has already served, so it keeps that in memory (`RefreshInbox.take`'s caller
holds the watermark). A runner restart therefore *ignores* requests older than
its start rather than replaying them -- the conservative direction: a tap whose
refresh was lost costs the person another tap, where a replayed one costs
credits nobody asked for a second time.

**Three ceilings, and they answer different questions.**

*Cooldown* -- may this key be requested again yet? The Odds API's `last_update`
is the aggregator's own scrape stamp, not our fetch time, so two calls a minute
apart routinely return the same numbers with the same age. The cooldown is not
politeness; below it a tap buys nothing and is billed anyway.

*Manual daily ceiling* -- how much of the day may taps have? The scheduled
window is what accumulates the evidence record, and it is planned ahead against
`remaining_today`. Taps arrive unplanned, so without a sub-ceiling a busy
evening of tapping empties the day and the planner discovers it as a refusal
after the fact. This ceiling exists to keep the tap from eating the schedule.

*The real budget* -- can the day afford this call at all? Read through
`CreditBudget.state`, the same implementation the planner uses, never a second
count of the same quantity.

**The manual tally over-counts, deliberately.** It is incremented when a request
is *accepted*, not when a call is served, and the runner may still refuse on
budget or find nothing to buy. Over-counting refuses a tap that would have fit;
under-counting authorises spend that is already gone. Only one of those two is
recoverable by tapping again.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .timing import DEFAULT_DAY_START_UTC_HOUR, day_start_ms

logger = logging.getLogger(__name__)


# How long before the same key may be refreshed again. Two minutes rather than
# thirty seconds because `odds_age_ms` is measured from The Odds API's own
# `last_update` -- a scrape stamp we do not control -- so a second call inside
# the aggregator's own cycle returns the same quotes at the same age. See the
# module docstring.
DEFAULT_COOLDOWN_MS = 120_000

# Credits a budget day may spend on taps, out of `ODDS_DAILY_CREDIT_BUDGET`.
#
# 150 of 700 (`fly.live.toml:222`). In tap terms that is 37 team refreshes, or
# 6 fixtures' props with a few team refreshes left over -- and the second of
# those is the one that sizes it, because a prop refresh is 24 credits against
# a team refresh's 4.
#
# Those two per-tap figures read 26 and 6 until 2026-08-24 (ADR 0071 section 4).
# Both are derived, not configured: a team sweep is `len(markets) x
# len(regions)` and a prop tap adds 10 prop keys x 2 regions on top, so
# `ODDS_MARKETS` gaining `spreads` on 2026-08-23 moved 2 -> 4 and 22 -> 24. The
# 6 was older still, from a three-market configuration that never ran on the
# box. Restating a derived number in a comment is how all three drifted.
#
# **Not a forecast and not a target.** A planned MLB + WNBA evening spends
# ~300-500 on the schedule (`fly.live.toml` carries the reconciled figure), so
# this is the slice the schedule can lose without a cluster going dark. If taps
# routinely hit it, the answer is a wider scheduled window, not a bigger slice:
# a tap buys one person one screen, where a scheduled sweep buys the record.
DEFAULT_MANUAL_DAILY_CREDITS = 150

# A request nobody served within this long is dropped rather than served late.
# Someone who tapped, waited, and put the phone down does not want a refresh
# five minutes later -- and would not see it. Comfortably above the 15s quote
# cadence that serves it.
DEFAULT_TTL_MS = 90_000

# The tail kept in the file. Only wide enough to enforce the cooldown across a
# realistic burst; this is not a log, and `odds_sweep_log` is.
_MAX_RETAINED = 64

_INBOX_FILENAME = "odds_refresh_inbox.json"


def inbox_path(db_path: str | os.PathLike[str]) -> Path:
    """The inbox beside the database.

    Derived from `db_path` rather than configured, because the two processes
    that must agree on this location already agree on that one -- the API takes
    it from `AppConfig` and the runner from `--db`. A separate setting is a
    second answer to a question the deployment has answered once, and the
    failure mode is silent: the API writes, the runner reads a different empty
    file, and every tap is accepted and never served.
    """
    return Path(db_path).resolve().parent / _INBOX_FILENAME


@dataclass(frozen=True)
class RefreshRequest:
    """One tap: a sport's team lines, and optionally one fixture's props."""

    sport_key: str
    # `None` means team lines only -- `h2h`/`spreads`/`totals` for the whole
    # slate, one call, `markets x regions` credits. Set means *additionally*
    # buy player props for this one fixture, which is where the money is.
    odds_event_id: Optional[str]
    requested_ms: int
    # What the API charged its own ceiling for this request, computed from the
    # deployed market and region lists at submit time. Carried so the runner's
    # log and the API's refusal can quote the same number.
    estimated_credits: int

    @property
    def key(self) -> str:
        """What the cooldown is enforced per.

        A per-fixture prop refresh and a slate-wide team refresh are different
        purchases and must not share a cooldown: blocking the second on the
        first would make one tap on one game silence the whole board.
        """
        return f"{self.sport_key}|{self.odds_event_id or '-'}"


@dataclass(frozen=True)
class Submission:
    """The answer to a tap, including every refusal, in the words to show."""

    accepted: bool
    detail: str
    estimated_credits: int
    # Milliseconds until this key may be tried again. Zero when the refusal is
    # not a cooldown -- a ceiling does not clear on a timer, and a countdown on
    # screen would promise it does.
    retry_after_ms: int = 0


def manual_cost(
    *,
    team_cost: int,
    prop_cost_per_event: int,
    odds_event_id: Optional[str],
) -> int:
    """Credits one tap is expected to spend.

    A prop refresh buys the team lines too, and that is not padding: the props
    endpoint is per event, the fixture list comes from the team slate, and
    `fetch_and_store_props` is only ever reached from a served team sweep. So
    the honest price of "refresh this game's props" includes the call that finds
    the game.
    """
    return team_cost + (prop_cost_per_event if odds_event_id else 0)


def _read(path: Path) -> list[dict]:
    """The retained tail, or an empty one.

    An unreadable inbox reads as empty rather than raising, and that is the
    right direction *here specifically*, against this repo's usual rule that
    unreadable resolves to `None` and the caller refuses. The rule protects
    money decisions from a fabricated zero. This value is a *cooldown history*,
    and an empty one is not permissive in the dangerous direction -- it allows
    one extra tap, which the manual ceiling and the real budget both still
    catch. Refusing instead would take the button offline the first time a
    partial write is observed.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        logger.warning("refresh inbox unreadable (%s); treating as empty", exc)
        return []
    try:
        decoded = json.loads(raw)
    except ValueError:
        logger.warning("refresh inbox is not JSON; treating as empty")
        return []
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, dict)]


def _write(path: Path, items: Sequence[dict]) -> None:
    """Replace the inbox atomically.

    `os.replace` over a temp file in the same directory, so a reader never sees
    a half-written file. The runner reads this on a 15s cadence with no lock,
    which only works because the swap is atomic.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".inbox-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(list(items), handle)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _decode(item: dict) -> Optional[RefreshRequest]:
    """One stored entry back to a request, or `None` if it is not one.

    Every field is checked rather than trusted. This file is the one input to
    the spend path that is not a database row, so a hand-edited or truncated
    entry must be dropped here rather than reaching `fetch_odds` as a sport key
    of `None`.
    """
    sport = item.get("sport_key")
    requested = item.get("requested_ms")
    cost = item.get("estimated_credits")
    event = item.get("odds_event_id")
    if not isinstance(sport, str) or not sport:
        return None
    if not isinstance(requested, int) or requested <= 0:
        return None
    if not isinstance(cost, int) or cost < 0:
        return None
    if event is not None and (not isinstance(event, str) or not event):
        return None
    return RefreshRequest(
        sport_key=sport,
        odds_event_id=event,
        requested_ms=requested,
        estimated_credits=cost,
    )


def _reserved_since(decoded: list[RefreshRequest], start_ms: int) -> int:
    return sum(r.estimated_credits for r in decoded if r.requested_ms >= start_ms)


def manual_spent_today(
    path: Path,
    now_ms: int,
    *,
    day_start_hour: int = DEFAULT_DAY_START_UTC_HOUR,
) -> int:
    """What today's taps have reserved, in credits, for a screen to say.

    The same file and the same arithmetic `submit` refuses against -- via
    `_reserved_since`, so there is exactly one implementation of the tally and
    a screen can never quote a ceiling the refusal does not enforce. Like that
    tally it deliberately over-counts: a request is counted when it is
    accepted, whether or not the runner ever serves it.
    """
    decoded = [r for r in (_decode(item) for item in _read(path)) if r is not None]
    return _reserved_since(decoded, day_start_ms(now_ms, hour=day_start_hour))


def submit(
    path: Path,
    *,
    sport_key: str,
    odds_event_id: Optional[str],
    now_ms: int,
    estimated_credits: int,
    budget_refusal: Optional[str] = None,
    cooldown_ms: int = DEFAULT_COOLDOWN_MS,
    manual_daily_credits: int = DEFAULT_MANUAL_DAILY_CREDITS,
    day_start_hour: int = DEFAULT_DAY_START_UTC_HOUR,
) -> Submission:
    """Accept a tap, or refuse it and say which ceiling refused.

    The order of the checks is cheapest-and-most-decisive first, matching
    `/api/orders`: a key still cooling down never reaches the budget read, and
    nothing writes the file until every check has passed.

    `budget_refusal` is the caller's `CreditBudget.refusal_reason(...)` -- passed
    in rather than computed, because the budget needs a database connection and
    this module deliberately has none. `None` means the day can afford it.

    The write happens last and includes this request, so the cooldown it starts
    applies to the tap that was just accepted. A caller that wrote first and
    checked after would let a double-tap through, which on a prop refresh is 52
    credits for one screen.
    """
    request = RefreshRequest(
        sport_key=sport_key,
        odds_event_id=odds_event_id,
        requested_ms=now_ms,
        estimated_credits=estimated_credits,
    )
    retained = _read(path)
    decoded = [r for r in (_decode(item) for item in retained) if r is not None]

    previous = [r for r in decoded if r.key == request.key]
    if previous:
        last = max(r.requested_ms for r in previous)
        elapsed = now_ms - last
        if 0 <= elapsed < cooldown_ms:
            wait = cooldown_ms - elapsed
            return Submission(
                accepted=False,
                detail=(
                    f"{_describe(request)} was refreshed {elapsed / 1000:.0f}s "
                    f"ago. The books' own scrape is slower than that, so "
                    f"another call would buy the same numbers at the same age. "
                    f"Try again in {wait / 1000:.0f}s."
                ),
                estimated_credits=estimated_credits,
                retry_after_ms=wait,
            )

    start = day_start_ms(now_ms, hour=day_start_hour)
    spent = _reserved_since(decoded, start)
    if spent + estimated_credits > manual_daily_credits:
        return Submission(
            accepted=False,
            detail=(
                f"on-demand refreshes have used {spent} of "
                f"{manual_daily_credits} credits reserved for them today and "
                f"this one costs {estimated_credits}. The rest of the day's "
                f"budget is held for the scheduled windows, which are what "
                f"build the record."
            ),
            estimated_credits=estimated_credits,
        )

    if budget_refusal is not None:
        return Submission(
            accepted=False,
            detail=f"the day's odds budget refuses this call: {budget_refusal}",
            estimated_credits=estimated_credits,
        )

    _write(
        path,
        [
            {
                "sport_key": r.sport_key,
                "odds_event_id": r.odds_event_id,
                "requested_ms": r.requested_ms,
                "estimated_credits": r.estimated_credits,
            }
            # Newest first, so the cap trims the oldest.
            for r in sorted(
                [*decoded, request], key=lambda r: r.requested_ms, reverse=True
            )[:_MAX_RETAINED]
        ],
    )
    return Submission(
        accepted=True,
        detail=(
            f"buying {_describe(request)} now -- {estimated_credits} credits. "
            f"The board updates within about 15 seconds."
        ),
        estimated_credits=estimated_credits,
    )


def _describe(request: RefreshRequest) -> str:
    if request.odds_event_id:
        return f"player props for {request.sport_key} fixture {request.odds_event_id}"
    return f"{request.sport_key} team lines"


def take(
    path: Path,
    *,
    now_ms: int,
    after_ms: int,
    ttl_ms: int = DEFAULT_TTL_MS,
) -> list[RefreshRequest]:
    """Requests the runner should serve on this pass, oldest first.

    `after_ms` is the caller's watermark -- the newest `requested_ms` it has
    already served, or its own start time. **The file is not modified**, which
    is what keeps the API the only writer; a request stays in the tail until it
    is trimmed, and is served exactly once because the watermark moves past it.

    Two filters, and they are not the same filter:

    * `requested_ms > after_ms` -- not served yet by *this* process.
    * `now_ms - requested_ms <= ttl_ms` -- still wanted. A tap from ten minutes
      ago belongs to a screen nobody is looking at, and serving it spends
      credits to update a page that has since gone dark.

    A restart resets the watermark forward to the restart instant, so requests
    that predate it are dropped by the first filter rather than replayed. That
    is deliberate and is argued in the module docstring.
    """
    decoded = [r for r in (_decode(item) for item in _read(path)) if r is not None]
    due = [
        r
        for r in decoded
        if r.requested_ms > after_ms and 0 <= now_ms - r.requested_ms <= ttl_ms
    ]
    return sorted(due, key=lambda r: r.requested_ms)
