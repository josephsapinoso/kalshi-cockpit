"""What to alert on, and the record of having done it.

`notify/discord.py` has been complete, tested and **imported by nothing** since
it was written -- the third module in this project to be finished as a component
and never joined to anything (after `score_recommendations` and the agent
fleet). Its ~20 tests all call the notifier directly, so they demonstrate that
an embed is well-formed and say nothing about whether an embed is ever sent.

This module is the missing caller. It holds the *policy* -- which events are
worth a phone buzzing -- and keeps it separate from the transport, so the
question "does the loop alert?" has one place to look.

Four events, and the ranking between them is deliberate
-------------------------------------------------------
**The window is open.** The one alert without which the tool cannot be used at
all. Odds are affordable twice a day and go stale in fifteen minutes, so if you
are not told at the moment it happens you will not be looking. Sent when a pass
actually spends a credit, not when one is planned -- a plan that fails to fetch
must not announce a window that does not exist.

**A surfaced opportunity.** Only surfaced ones, and only rows written by this
pass. A notification for every suppressed candidate would train you to ignore
the channel, which is worse than no channel.

**A daily digest**, at the budget-day roll: what was recorded, what was scored,
and progress toward the 300-game floor. This is the "how past picks scored"
answer, and it belongs on a day boundary rather than per-pass because CLV is a
statement about accumulation.

**Failure.** Rate-limited to once per kind per day, because the failure mode
that matters is a broken feed, and a broken feed produces the *same* failure on
every pass. An alert that fires ninety-six times is one alert and ninety-five
reasons to mute the channel.

Why the database and not a set in memory
----------------------------------------
The loop dies loudly after repeated failure and the platform restarts it. A
policy remembering what it had sent in process memory would re-announce the
whole slate on every restart, so a crash loop would arrive on the phone looking
exactly like a busy night. `notifications` carries `UNIQUE (kind, key)` and the
claim is made *before* the send, so a crash between claiming and sending costs
one missed alert rather than an unbounded number of duplicates. Losing an alert
is recoverable by opening the cockpit; being trained to ignore the channel is
not.

What this does not establish
----------------------------
That an alert is worth acting on. "The window is open" is a statement about
freshness; most windows open onto an empty Board, and the digest exists partly
to keep that fact in front of you.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from .. import gate
from ..gate import POPULATIONS

logger = logging.getLogger(__name__)

# Failure alerts collapse to one per kind per day. See the module docstring.
FAILURE_KINDS = ("loop_failed", "credits_exhausted", "feed_died")


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


@dataclass(frozen=True)
class AlertResult:
    """What one pass decided to say. Returned so the loop can log it.

    `skipped` is populated when an alert was *already sent*, which is a
    different state from having nothing to say and is the one that proves the
    dedupe is working rather than the notifier being broken.
    """

    sent: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "alerts_sent": list(self.sent),
            "alerts_failed": list(self.failed),
            "alerts_deduped": list(self.skipped),
        }


class Alerter:
    """Decides what to send, records it, and never raises into the caller.

    Alerting is optional infrastructure. A Discord outage, a revoked token or a
    missing channel id must degrade the tool to "no push notifications" and
    must never stop the loop that is recording evidence -- that record is the
    only thing this project cannot recreate later.
    """

    def __init__(self, conn, notifier):
        self.conn = conn
        self.notifier = notifier

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.notifier, "enabled", False))

    # -- the ledger of what was said ---------------------------------------

    def _claim(self, kind: str, key: str, *, now_ms: int, detail: str = "") -> bool:
        """Reserve one alert. False when it has already been made.

        `ON CONFLICT DO NOTHING` rather than `INSERT OR IGNORE`: the latter
        suppresses *every* constraint failure on the statement, including a
        `NOT NULL` that means the row is malformed. That is how a gate-test
        fixture in this repo silently inserted nothing for the life of the
        project. This form still raises on a broken row and only swallows the
        conflict it is written for.
        """
        cursor = self.conn.execute(
            "INSERT INTO notifications (sent_ms, kind, key, delivered, detail) "
            "VALUES (?, ?, ?, 0, ?) ON CONFLICT (kind, key) DO NOTHING",
            (now_ms, kind, key, detail or None),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def _record_delivery(self, kind: str, key: str, delivered: bool) -> None:
        self.conn.execute(
            "UPDATE notifications SET delivered = ? WHERE kind = ? AND key = ?",
            (1 if delivered else 0, kind, key),
        )
        self.conn.commit()

    async def _send(self, kind: str, key: str, coro_factory, *, now_ms: int,
                    detail: str = "") -> Optional[bool]:
        """Claim, send, record. `None` means it was already sent."""
        if not self._claim(kind, key, now_ms=now_ms, detail=detail):
            return None
        try:
            delivered = bool(await coro_factory())
        except Exception:                                     # noqa: BLE001
            logger.exception("alert %s/%s raised; treating as undelivered", kind, key)
            delivered = False
        self._record_delivery(kind, key, delivered)
        return delivered

    # -- the four events ---------------------------------------------------

    async def after_pass(
        self,
        *,
        pass_ms: int,
        counts,
        window,
        sweeps_this_pass: int,
    ) -> AlertResult:
        """Alert on what this pass produced. Safe to call every pass.

        `sweeps_this_pass` rather than `window.next_slot` or a plan: a window is
        announced only when a credit was actually spent and quotes were actually
        stored. Announcing an intended sweep would put "the window is open" on a
        phone at the exact moment the odds API was down.
        """
        if not self.enabled:
            return AlertResult()

        sent: list[str] = []
        failed: list[str] = []
        skipped: list[str] = []

        def note(kind: str, outcome: Optional[bool]) -> None:
            if outcome is None:
                skipped.append(kind)
            elif outcome:
                sent.append(kind)
            else:
                failed.append(kind)

        if sweeps_this_pass > 0 and window is not None:
            key = str(window.last_sweep_ms or pass_ms)
            note(
                "window_open",
                await self._send(
                    "window_open", key,
                    lambda: self.notifier.window_open(
                        window=window, surfaced=counts.surfaced
                    ),
                    now_ms=pass_ms,
                    detail=f"{window.fixtures_fresh} fixtures fresh",
                ),
            )

        for rec in self._surfaced_this_pass(pass_ms):
            note(
                "opportunity",
                await self._send(
                    "opportunity", str(rec["id"]),
                    lambda r=rec: self.notifier.opportunity(_RecView(r)),
                    now_ms=pass_ms,
                    detail=rec["ticker"],
                ),
            )

        return AlertResult(tuple(sent), tuple(failed), tuple(skipped))

    def _surfaced_this_pass(self, pass_ms: int) -> Sequence:
        """Rows this pass wrote that the engine sized above zero.

        Scoped to `created_ms = pass_ms` rather than "everything surfaced",
        because `persist_if_changed` does not rewrite an unchanged row -- so
        querying the whole table would re-announce the same opportunity on every
        pass for as long as its price held.
        """
        return self.conn.execute(
            "SELECT r.*, m.yes_side_team AS team FROM recommendations r "
            "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
            "WHERE r.created_ms = ? AND r.suggested_contracts > 0 "
            "ORDER BY r.edge_tenths DESC",
            (pass_ms,),
        ).fetchall()

    async def daily_digest(
        self, *, now_ms: int, day_start_ms: int, gate_required: int
    ) -> Optional[bool]:
        """One summary per budget day. `None` when today's has already gone.

        Keyed on the budget day rather than the calendar day so the digest
        covers the same span the credit meter does -- a summary whose boundary
        disagrees with the budget's would split one night's slate across two
        reports.
        """
        if not self.enabled:
            return None

        stats = self._digest_stats(day_start_ms, now_ms)
        return await self._send(
            "digest", str(day_start_ms),
            lambda: self.notifier.daily_digest(
                surfaced=stats["surfaced"],
                suppressed=stats["suppressed"],
                no_edge=stats["no_edge"],
                scored=stats["scored"],
                scored_actionable=stats["scored_actionable"],
                required=gate_required,
                suppression_counts=stats["reasons"],
            ),
            now_ms=now_ms,
            detail=(
                f"{stats['surfaced']} surfaced, {stats['scored']} scored "
                f"({stats['scored_actionable']} actionable)"
                + (
                    f"; only {stats['buyable']} fundable at the configured "
                    f"bankroll"
                    if stats["buyable"] != stats["surfaced"]
                    else ""
                )
            ),
        )

    def _digest_stats(self, since_ms: int, now_ms: int) -> dict:
        # **Built from `gate.POPULATIONS`, not restated.** This query used to
        # spell the three predicates out again, and they agreed with the gate's
        # right up until the gate started counting `reference_contracts` instead
        # of `suggested_contracts` (ADR 0015). At that moment the digest would
        # have gone on filing "the strategy had a bet but the balance could not
        # fund it" under **no_edge** -- a phone notification quietly relabelling
        # a funding limit as an absence of opportunity. Two SQL fragments
        # encoding one definition is the failure this repo records under
        # "delete one of the paths".
        populations = ", ".join(
            f"SUM(CASE WHEN {predicate} THEN 1 ELSE 0 END) AS {name}"
            for name, predicate in POPULATIONS.items()
        )
        row = self.conn.execute(
            f"SELECT {populations}, "  # noqa: S608
            "  SUM(CASE WHEN r.suppressed_reason IS NULL "
            "           AND r.suggested_contracts > 0 THEN 1 ELSE 0 END) AS buyable "
            "FROM recommendations r "
            "WHERE r.created_ms >= ? AND r.created_ms < ?",
            (since_ms, now_ms),
        ).fetchone()

        reasons: dict[str, int] = {}
        for r in self.conn.execute(
            "SELECT suppressed_reason AS reason, COUNT(*) AS n FROM recommendations "
            "WHERE created_ms >= ? AND created_ms < ? AND suppressed_reason IS NOT NULL "
            "GROUP BY suppressed_reason",
            (since_ms, now_ms),
        ):
            reasons[r["reason"]] = int(r["n"])

        # Scored on CLV, counted the way the gate counts it: independent games,
        # not rows. Reporting rows here would put a flattering number on a
        # phone beside the Gate screen's honest one.
        #
        # **Through the gate's own function, not a second query.** This had its
        # own SQL saying it counted "the way the gate counts it" -- true, and
        # the gate's way pooled every scored row regardless of whether the
        # strategy would have bet it, so both screens agreed on a number that
        # described any market the instance happened to poll. Two paths that
        # agree today diverge the moment one is fixed, and the digest is the one
        # that reaches a phone. The predicates also differed already: this asked
        # for `clv_tenths IS NOT NULL` while the gate additionally required
        # `clv_scored_ms IS NOT NULL`.
        groups = gate.clv_by_population(self.conn)

        return {
            # `surfaced` is the gate's `actionable`: rows where the strategy
            # had a bet, judged at the reference bankroll. `buyable` is how many
            # of those the balance could actually fund, and it is a smaller
            # number at a small bankroll. Reporting only the second would say
            # "nothing surfaced" on a night the strategy found things and the
            # account could not pay for them, which is a different message and
            # calls for a different response.
            "surfaced": int(row["actionable"] or 0),
            "buyable": int(row["buyable"] or 0),
            "suppressed": int(row["suppressed"] or 0),
            "no_edge": int(row["no_edge"] or 0),
            "scored": groups["pooled"].n_clusters,
            # The population the floor is *about*. Still 0 on the live record,
            # and a 0 that is explained is worth more than a 16 that is not.
            "scored_actionable": groups["actionable"].n_clusters,
            "reasons": reasons,
        }

    async def failure(self, kind: str, detail: str, *, now_ms: int) -> Optional[bool]:
        """One alert per kind per day. A broken feed fails on every pass."""
        if not self.enabled:
            return None
        return await self._send(
            "failure", f"{kind}:{_day(now_ms)}",
            lambda: self.notifier.failure(kind, detail),
            now_ms=now_ms, detail=detail[:200],
        )


class _RecView:
    """A `recommendations` row in the shape `DiscordNotifier.opportunity` reads.

    The notifier was written against the engine's `Recommendation` dataclass and
    the loop has a sqlite `Row`. Adapting here rather than changing the notifier
    keeps its ~20 existing tests meaningful, and keeps one column name --
    `entry_ask_tenths` -- from being renamed across a money path for the sake of
    an alert.
    """

    __slots__ = ("_row",)

    def __init__(self, row):
        self._row = row

    def __getattr__(self, name: str):
        try:
            return self._row[name]
        except (IndexError, KeyError) as exc:
            raise AttributeError(name) from exc
