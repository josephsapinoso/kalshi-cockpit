"""Call accounting for the Anthropic fleet, in the shape `odds/budget.py` uses.

**The defect this exists to close.** Until 2026-08-11 the Anthropic spend path
had no ceiling of any kind: `review._review_batch` fanned `asyncio.gather` over
every surfaced candidate with no cap, no concurrency limit, and no per-pass or
per-day bound, on a loop that runs up to ~96 passes a day. The only two things
holding the bill at zero were (1) an early return on an empty candidate list and
(2) `AgentConfig.from_env()` returning `None` when `ANTHROPIC_API_KEY` is unset.
On the live instance the key **is** set, so (1) was the only binding guard --
and (1) is a *measurement outcome*, not a configuration value. `surfaced` has
been 0 for the life of the project. The system was therefore arranged to begin
spending, unmetered, at the exact moment the project first succeeded.

That is this repo's named **two limits on one quantity** shape seen from its
worst angle: the remedy for a different open question (whether the `stale_odds`
guard is wrong, which could move `actionable` from 0 to 23) would have disarmed
the only spend guard as a silent side effect.

Three properties, taken from `odds/budget.py` deliberately rather than invented:

**It refuses rather than warns.** `allowance` returning fewer calls than the
caller asked for blocks those calls. A budget that logs and proceeds is not a
budget.

**The daily cap is the money control. The per-pass cap is not a second one.**
Until 2026-08-11 this paragraph said "neither implies the other: 96 passes at 8
calls each is 768 calls". That describes a system this file does not implement.
`allowance` is `max(0, min(per_pass, remaining_today))` -- both ceilings are in
the *same* `min()`, so the day's total is 24 for **any** `per_pass` in [1, 24]
and 768 is not reachable by any configuration.

What the per-pass cap actually controls is **fan-out width, and therefore how
the day's 24 calls are distributed across the day's passes**. On a 23-row slate
with `per_pass=8`: pass 1 reviews 8 and refuses 15, and the day's 24 are spread
over three passes. Without it (`per_pass >= 24`): pass 1 reviews all 23 and
refuses none, and pass 2 reviews 1 and refuses 22 -- the day is spent by the
second pass of ~96. That is a real difference and it is why the cap is not
decoration; it is *not* a spend ceiling, and calling it one was how a false
$35/day figure stayed in three files for a day.
`tests/test_agent_budget.py::TestThePerPassCapDistributesTheDayItDoesNotShrinkIt`
asserts both halves of that arithmetic.

**Its state is on disk, not in the process.** `spent_today` is `COUNT(*)` over
`agent_calls`, so a restart -- a deploy, a crash loop, a Fly machine
migration -- cannot reset the day's tally. `PassCounts.skeptic_reviewed` is the
in-memory alternative and it is why there was, until now, no durable record
anywhere that a Skeptic call had ever happened.

**A row is written before the call, not after, so a crash over-counts.** The
first version of this module recorded after `asyncio.gather` returned, which
meant a process death mid-batch left up to 8 billed calls with no row -- and
because `spent_today` is `COUNT(*)`, the next pass would then see a *larger*
allowance than it was owed. In a crash loop (`docker/entrypoint.sh` restarts,
`run_loop` re-prices the same slate, the same rows surface) that repeats with
nothing in this repo bounding it. `reserve` now writes the rows first and
`settle` fills the verdict in afterwards, so an interrupted batch counts calls
it may not have made. **That is the correct direction for a money guard:
over-counting costs reviews, under-counting costs money, and only one of those
is recoverable by waiting for tomorrow.**

`CreditBudget` (`odds/client.py`) still records after its call, and that is not
the same defect at a different address: its window is **one** call wide, and one
uncounted credit is not eight uncounted dollars-and-a-crash-loop.

The **day** is the sports day used everywhere else in this project (10:00 UTC by
default, `odds/timing.py`), not the calendar day. Reusing it is not decoration:
the odds sweep, the slate and the agent spend are all consequences of the same
night's games, and a ceiling that rolled at a different hour would report an
evening's spend split across two buckets from the sweep that caused it. There is
no provider-side month to reconcile against here, so unlike `CreditBudget` there
is no monthly ceiling -- a day's cap times a month is the whole bound, because
no caller can spend at more than one call per row per pass.

What this module does NOT establish
-----------------------------------
**That the defaults are right.** They are not measured, because the population
they would be measured on has never existed -- `surfaced` has been 0 on every
live pass. They are chosen to bind early and be raised deliberately; see
`AgentBudget.from_config`.

**That a call costs what the docstring says.** The dollar figure there is
arithmetic over list prices and a token estimate, not an invoice. Nothing here
reads an Anthropic-reported balance, so unlike `CreditBudget` -- which
reconciles against `x-requests-remaining` -- this meter has no second opinion.
If the count here drifts from what Anthropic bills, nothing in this repo can
see it.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Optional

from ..config import configured_day_start_utc_hour
from ..odds.timing import DEFAULT_DAY_START_UTC_HOUR, day_start_ms

from .base import CallUsage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentBudgetState:
    per_pass_budget: int
    daily_budget: int
    spent_today: int
    # The token meter (v17). Sums over today's SETTLED usage; a reserved call
    # whose response never arrived contributes nothing here and is counted in
    # `calls_unmetered_today` instead -- the sums must state what they do not
    # cover, and the call cap (which needs no response) stays the outer bound.
    searches_today: int = 0
    tokens_today: int = 0
    searches_daily_budget: int = 0
    tokens_daily_budget: int = 0
    calls_unmetered_today: int = 0

    @property
    def remaining_today(self) -> int:
        return max(0, self.daily_budget - self.spent_today)


@dataclass(frozen=True)
class AgentSpendSummary:
    """Today's Anthropic spend, in the three numbers an operator asks for.

    The operator runs this tool from a phone (`tasks/lessons.md`), and
    `fly.live.toml` tells them to "raise deliberately, after the first real
    bill" -- an instruction with no phone-reachable way to answer "how much of
    today's 24 have I spent?". `agent_calls` appears in exactly two files and
    nothing outside this module reads `spent_today`.

    Deliberately a **count**, not a dollar figure. The per-token rate is marked
    [ASSUMED, uncited] in `agents/base.py` and this object must not be the place
    an unverified rate turns into a number on a screen.
    """

    calls_today: int
    daily_budget: int
    remaining_today: int
    per_pass_budget: int
    day_start_ms: int
    day_start_hour: int
    # The token meter (v17): sums of settled usage, plus the count of calls
    # whose usage never arrived -- so the sums always say what they miss.
    searches_today: int = 0
    searches_daily_budget: int = 0
    tokens_today: int = 0
    tokens_daily_budget: int = 0
    calls_unmetered_today: int = 0


class AgentBudget:
    """Meters Anthropic calls against `agent_calls`, refusing what breaches it.

    `conn` is required and there is no in-memory fallback, deliberately. A
    budget that quietly degrades to a per-process counter when it cannot reach
    the database is a budget that resets on every restart -- and the restart is
    exactly the event a daily cap has to survive.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        per_pass_budget: int,
        daily_budget: int,
        *,
        day_start_hour: int = DEFAULT_DAY_START_UTC_HOUR,
        searches_daily_budget: int = 0,
        tokens_daily_budget: int = 0,
    ):
        self.conn = conn
        self.per_pass_budget = per_pass_budget
        self.daily_budget = daily_budget
        self.day_start_hour = day_start_hour
        # 0 means "no separate token/search ceiling" -- the call caps alone
        # bound the day. `from_config` always passes real ceilings; the 0
        # default keeps the many existing test constructors meaning what they
        # meant (call caps only), rather than silently gaining two brakes.
        self.searches_daily_budget = searches_daily_budget
        self.tokens_daily_budget = tokens_daily_budget

    @classmethod
    def from_config(cls, conn: sqlite3.Connection, config) -> "AgentBudget":
        """Build from an `AgentConfig`, which is where the two limits are read.

        The limits live on `AgentConfig` rather than being read here because
        `AgentConfig.from_env` is already the fleet's single env-reading site,
        and two places parsing `AGENT_MAX_CALLS_PER_DAY` would drift.

        **The roll hour does not, and until 2026-08-11 that was a lie in
        `.env.example`.** That file said the agent day "rolls at
        `ODDS_BUDGET_DAY_START_UTC_HOUR`, the same sports day the odds budget
        uses" while this constructor passed nothing and took the hardcoded
        `DEFAULT_DAY_START_UTC_HOUR` -- true at the default, false the moment
        anyone set the variable, and the doc would have kept saying otherwise.
        `configured_day_start_utc_hour` is the single parse of that variable
        (`OddsConfig` uses it too), which is why reading it here is not the
        second-parser drift the paragraph above objects to. The direction of the
        old failure was money-shaped: a later day start means fewer of today's
        `agent_calls` rows fall inside the window, so `spent_today` reads low
        and the daily cap lets *more* calls through.
        """
        return cls(
            conn,
            per_pass_budget=config.max_calls_per_pass,
            daily_budget=config.max_calls_per_day,
            day_start_hour=configured_day_start_utc_hour(),
            searches_daily_budget=config.max_searches_per_day,
            tokens_daily_budget=config.max_tokens_per_day,
        )

    def day_start_ms(self, now_ms: int) -> int:
        return day_start_ms(now_ms, hour=self.day_start_hour)

    def state(self, now_ms: int) -> AgentBudgetState:
        row = self.conn.execute(
            # COALESCE on the SUMs, not the columns: a NULL usage row is a
            # call the meter could not see, and it must raise
            # `calls_unmetered_today` rather than quietly add 0 to a sum.
            "SELECT COUNT(*) AS calls, "
            "COALESCE(SUM(web_searches), 0) AS searches, "
            "COALESCE(SUM(input_tokens), 0) + COALESCE(SUM(output_tokens), 0) "
            "AS tokens, "
            "SUM(CASE WHEN input_tokens IS NULL THEN 1 ELSE 0 END) "
            "AS unmetered "
            "FROM agent_calls WHERE called_ms >= ?",
            (self.day_start_ms(now_ms),),
        ).fetchone()
        return AgentBudgetState(
            per_pass_budget=self.per_pass_budget,
            daily_budget=self.daily_budget,
            spent_today=int(row["calls"]),
            searches_today=int(row["searches"]),
            tokens_today=int(row["tokens"]),
            searches_daily_budget=self.searches_daily_budget,
            tokens_daily_budget=self.tokens_daily_budget,
            calls_unmetered_today=int(row["unmetered"] or 0),
        )

    def allowance(self, now_ms: int) -> int:
        """How many calls this fan-out may make, right now. Never negative.

        This is the primitive the caller wants, and it is not the same question
        as `can_afford`. A batch of 23 rows against a per-pass ceiling of 8 is
        not "refused" -- 8 of it is affordable and 15 of it is not, and the
        caller has to be able to tell those apart in order to be honest about
        which rows were reviewed.
        """
        state = self.state(now_ms)
        return max(0, min(state.per_pass_budget, state.remaining_today))

    def refusal_reason(
        self, requested: int, now_ms: int, *, searches_worst_case: int = 0
    ) -> Optional[str]:
        """Which ceiling refuses part of a `requested`-call fan-out, or `None`.

        Checked hardest-to-recover-from first, as in `odds/budget.py`: the
        three daily caps need a rollover, the per-pass cap needs only a
        smaller batch.

        **The token and search brakes are evaluated over spend already
        recorded, before the next reserve** -- never over a field the call
        being gated will write (`tasks/lessons.md`: a field written after the
        spend is a receipt, not a brake). The caller states the fan-out's
        `searches_worst_case` (the sum of its tools' `max_uses`) because a
        search, unlike a token, has a pre-known per-call ceiling; tokens are
        gated on the recorded total alone. A ceiling of 0 means "not
        configured" and refuses nothing -- `from_config` always configures
        both.

        **The reason is returned as well as logged.** It is written onto the
        rows that went unreviewed, where the operator actually looks -- a phone
        screen -- rather than only into a 100-line log buffer that drops it.
        `None` for "no objection", so a refusal and an empty reason cannot be
        confused.
        """
        state = self.state(now_ms)
        if state.remaining_today < requested:
            reason = (
                f"{state.spent_today} of {self.daily_budget} Anthropic calls "
                f"already made today, and this pass asked for {requested}"
            )
            logger.warning("refusing part of a %d-call batch: %s", requested, reason)
            return reason
        if (
            self.tokens_daily_budget > 0
            and state.tokens_today >= self.tokens_daily_budget
        ):
            reason = (
                f"{state.tokens_today} of {self.tokens_daily_budget} Anthropic "
                f"tokens already recorded today"
            )
            logger.warning("refusing a %d-call batch: %s", requested, reason)
            return reason
        if (
            self.searches_daily_budget > 0
            and state.searches_today + searches_worst_case
            > self.searches_daily_budget
        ):
            reason = (
                f"{state.searches_today} of {self.searches_daily_budget} web "
                f"searches already recorded today, and this pass could spend "
                f"{searches_worst_case} more"
            )
            logger.warning("refusing a %d-call batch: %s", requested, reason)
            return reason
        if state.per_pass_budget < requested:
            reason = (
                f"one pass may make at most {self.per_pass_budget} Anthropic "
                f"calls, and this pass asked for {requested}"
            )
            logger.warning("refusing part of a %d-call batch: %s", requested, reason)
            return reason
        return None

    def can_afford(
        self, requested: int, now_ms: int, *, searches_worst_case: int = 0
    ) -> bool:
        """Whether the whole fan-out fits, defined in terms of `refusal_reason`.

        One implementation of the ceilings, for the reason `CreditBudget`
        gives: two would drift, and the drift would be invisible -- the guard
        would still refuse and the recorded reason would name the wrong limit.
        """
        return (
            self.refusal_reason(
                requested, now_ms, searches_worst_case=searches_worst_case
            )
            is None
        )

    def today_summary(self, now_ms: int) -> AgentSpendSummary:
        """The read side of the meter: what has been spent today, and of what.

        Nothing outside this module read `spent_today` before this existed. See
        `AgentSpendSummary` for why it reports counts and not dollars.

        **Outstanding:** `/api/health` should carry these three numbers so the
        answer is one tap from a phone. `backend/api/routes.py` is not this
        change's to edit; the route is a two-line addition on top of this.
        """
        state = self.state(now_ms)
        return AgentSpendSummary(
            calls_today=state.spent_today,
            daily_budget=state.daily_budget,
            remaining_today=state.remaining_today,
            per_pass_budget=state.per_pass_budget,
            day_start_ms=self.day_start_ms(now_ms),
            day_start_hour=self.day_start_hour,
            searches_today=state.searches_today,
            searches_daily_budget=state.searches_daily_budget,
            tokens_today=state.tokens_today,
            tokens_daily_budget=state.tokens_daily_budget,
            calls_unmetered_today=state.calls_unmetered_today,
        )

    def reserve(
        self,
        *,
        called_ms: int,
        agent: str,
        model: str,
        ticker: Optional[str] = None,
        side: Optional[str] = None,
    ) -> int:
        """Claim one call's worth of the day's allowance, **before making it**.

        Returns the `agent_calls` row id, which `settle` needs. The row lands
        with `verdict` and `blocked` NULL, which is the same shape a call that
        came back with no opinion leaves behind -- deliberately, because until
        `settle` runs those two facts are genuinely indistinguishable.

        **Reserving up front is the whole point, and the error direction is
        why.** If the process dies between here and `settle`, the day is charged
        for a call that may not have been billed: the meter over-counts, the
        next pass gets a smaller allowance, and the cost is a review that does
        not happen. Recording afterwards inverts that -- a crash mid-fan-out
        leaves up to `AGENT_MAX_CALLS_PER_PASS` billed calls with no row, and
        `spent_today` being `COUNT(*)` means the restart that follows sees a
        *larger* allowance than it is owed. On a restarting loop that re-prices
        the same slate, that is unbounded.

        Every call is reserved, including the ones that will fail. A call that
        errored, was refused by a safety classifier, or returned unparseable
        output still cost money and still consumed the day's allowance.
        """
        cursor = self.conn.execute(
            "INSERT INTO agent_calls (called_ms, agent, model, ticker, side, "
            "verdict, blocked) VALUES (?, ?, ?, ?, ?, NULL, NULL)",
            (called_ms, agent, model, ticker, side),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def settle(
        self,
        call_id: int,
        *,
        verdict: Optional[str] = None,
        blocked: Optional[bool] = None,
        usage: Optional[CallUsage] = None,
    ) -> None:
        """Fill in what a reserved call came back with. Never adds to the count.

        `blocked` is `None` rather than `False` when there was no verdict to
        fold in. "The Skeptic looked and did not block" and "the Skeptic said
        nothing" are different facts and must not share a value -- so a call
        that returned nothing settles to exactly the NULLs `reserve` wrote, and
        that is correct rather than a no-op worth optimising away.
        """
        self.conn.execute(
            "UPDATE agent_calls SET verdict = ?, blocked = ?, "
            "input_tokens = ?, output_tokens = ?, web_searches = ? "
            "WHERE id = ?",
            (
                verdict,
                None if blocked is None else int(blocked),
                # NULL, never 0, when no response carried a usage block: a
                # crashed call's cost is unknown, and `calls_unmetered_today`
                # counts the row so the sums say what they do not cover.
                None if usage is None else usage.input_tokens,
                None if usage is None else usage.output_tokens,
                None if usage is None else usage.web_searches,
                call_id,
            ),
        )
        self.conn.commit()
