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
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

from .. import gate
from ..gate import POPULATIONS

logger = logging.getLogger(__name__)

# Failure alerts collapse to one per kind per day. See the module docstring.
#
# **These are the kinds this module can actually send**, and the tuple is now
# read rather than decorative. It previously listed `("loop_failed",
# "credits_exhausted", "feed_died")` -- referenced by nothing in the tree, not
# even by this module, and **not one of its three strings matched the one kind
# ever sent**, which was the free-text `"Recording loop died"` at
# `scripts/run_loop.py`. A constant nobody reads cannot be wrong, so it was
# wrong for the life of the project.
#
# `Alerter._failure` now asserts membership, which is what turns it into a
# guard: a new failure kind must be declared here, and a typo at a call site
# raises in tests instead of opening a second dedupe bucket that silently
# doubles the phone traffic.
FAILURE_LOOP_DIED = "Recording loop died"
FAILURE_FEED_DIED = "Kalshi feed died"
FAILURE_CREDITS_EXHAUSTED = "Odds credits exhausted"
FAILURE_API_UNREACHABLE = "Cockpit API unreachable"
# The exact strings `DiscordNotifier` puts in the embed title, so the dedupe
# key and the thing Joe reads are the same name. `fee_mismatch` uses an em
# dash; matching it here is not cosmetic -- a near-miss would dedupe under a
# kind that appears nowhere on the phone.
FAILURE_FEE_MISMATCH = "Fee model mismatch — stop the line"

FAILURE_KINDS = (
    FAILURE_LOOP_DIED,
    FAILURE_FEED_DIED,
    FAILURE_CREDITS_EXHAUSTED,
    FAILURE_API_UNREACHABLE,
    FAILURE_FEE_MISMATCH,
)


#: How many **change-alert** pushes one budget day may carry, across all rungs.
#: The scheduled daily card does not spend this and does not need to; see
#: `PARLAY_DAILY_KIND`.
#:
#: **The dedupe key alone is not a ceiling, and the reason is the candidate
#: filter.** `parlays.ladder_candidates` takes pre-game fixtures only
#: (`commence_ms > now`), so every kickoff drops a game out of the pool. If that
#: game was in a card, the leg set changes, the key changes, and the card is
#: legitimately "new". On a 14-fixture MLB night that is up to fourteen pushes
#: per rung -- each one correct by the dedupe rule and collectively a phone
#: nobody leaves un-muted.
#:
#: **This was 6, and it is 3 because the day now has two channels rather than
#: one.** The old comment justified 6 as "two full ladders" when every parlay
#: push came through here. The scheduled card is now bounded by construction at
#: `len(PUSHED_CARD_KEYS)` per day, so 3 + 3 keeps the worst-case day total
#: exactly where the original reasoning put it. Joe chose that total when the
#: split was put to him: *keep 6 at the worst*.
#:
#: Past it the day's change alerts stop and the screen still has everything; a
#: desk that keeps buzzing is one that manufactures action, which ADR 0071 says
#: this tool does not do.
MAX_PARLAY_PUSHES_PER_DAY = 3

#: The `notifications.kind` of the guaranteed once-a-day card.
#:
#: **A separate kind from `parlay_card`, so it has a separate ceiling and a
#: separate dedupe bucket.** Keyed on `<day_start_ms>:<card_key>` -- the budget
#: day and not the calendar day, for `daily_digest`'s reason: a boundary that
#: disagrees with the credit meter's would split one night's slate across two
#: reports.
PARLAY_DAILY_KIND = "parlay_daily"

#: The `notifications.kind` of the composition-changed alert. Named rather than
#: spelled twice, because the scheduled push burns this key as well as its own
#: (see `parlay_cards`) and a near-miss between the two spellings would open a
#: second dedupe bucket that doubles the phone traffic -- the exact failure
#: `FAILURE_KINDS` above was made a read constant to prevent.
PARLAY_CHANGE_KIND = "parlay_card"

#: How many consecutive ladder builds a composition must hold before the change
#: channel will announce it.
#:
#: **Measured on live 2026-08-26: the whole day's ceiling spent in four
#: minutes.**
#:
#:     22:41:43Z  safe: LADATL-LAD | BOSMIA-BOS | MILNYM-MIL   (all MLB)
#:     22:45:10Z  safe: CHICONN-CHI | PDXDAL-DAL | GSCONN-GS   (all WNBA)
#:
#: The card swapped sport entirely and all three rungs re-pushed. Both pushes
#: were *correct* under the dedupe rule -- this is not a bug in the dedupe.
#: Sports are swept on independent clocks, `build_ladder` drops legs past
#: `MAX_ODDS_AGE_S`, and ranking is by probability, so whichever sport is
#: currently fresh owns the top of every card.
#:
#: Two is the smallest number that suppresses an alternation, which is the
#: shape the churn actually has. The cost is one build of latency: builds are
#: gated on `counts.odds_sweeps > 0 or kind == "full"`, so ~10 minutes while
#: someone is looking and up to an hour when nobody is. That delay is the
#: feature.
PARLAY_DEBOUNCE_BUILDS = 2

#: Which cards reach the phone. **Not every card the screen shows.**
#:
#: The ladder went from three cuts to six on 2026-08-26 (Longshot, Next 3
#: hours, Agreed). Six cards against the ceiling above means ONE ladder
#: spends the whole day's pushes, where that constant's own comment calls
#: six "two full ladders" -- and the day it was written, the existing three
#: already burned the ceiling in four minutes through per-sport sweep churn
#: (`tasks/lessons.md`, "Dedupe is not a rate limit").
#:
#: So the new cuts are screen-only until the trigger changes shape
#: (a scheduled daily card plus a two-build debounce, decided 2026-08-26,
#: not yet built). Adding a card must not silently change what the phone
#: does; a notifier that grows with the screen is one nobody leaves
#: un-muted.
PUSHED_CARD_KEYS: frozenset[str] = frozenset({"safe", "middle", "lottery"})


#: How many hedge pushes one budget day may carry, across every ticket.
#:
#: ADR 0072 Decision 4's lesson, applied before it can bite rather than after:
#: **a dedupe key bounds repetition and never volume.** The key below answers
#: "have I said this before?" and is silent on how fast a live game hands you
#: something new to say -- and a game in its closing minutes re-prices far
#: faster than a slate does.
#:
#: Four is deliberately below the parlay ceiling. A parlay card is an offer and
#: a missed one costs nothing; a hedge alert is about money already at risk, so
#: the ones that get through should be the ones that moved the figure most --
#: which the ratchet, not this constant, is what selects.
MAX_HEDGE_PUSHES_PER_DAY = 4

#: The step the ratchet climbs in, in integer tenths of a cent. $5.
#:
#: **A dollar figure rather than a fraction of the stake**, because the thing
#: being bounded is how often a phone buzzes and that is a fact about the
#: person, not about the ticket. A percentage rule would buzz four times over
#: a $5 slip and once over a $300 one, which is backwards.
HEDGE_RATCHET_STEP_TENTHS = 5_000


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def parlay_key(card: Mapping[str, Any]) -> Optional[str]:
    """The identity of a parlay card, for `notifications.UNIQUE (kind, key)`.

    `<card_key>:<ticker>|<ticker>|...`, tickers **sorted**.

    **Sorted, because leg order is not part of the card.** `build_ladder`
    orders legs by `(-p_conservative, commence_ms, ticker)`, so two probabilities
    that cross between passes reorder the same set of legs -- and an
    order-sensitive key would read that as a new card and push it again. The
    same three games are the same parlay whichever way they are listed.

    **`card_key` is in the key, because the shape is part of the product.** The
    same legs as a "Safe" and as a "Middle" are different suggestions -- the
    ladder's rungs are 2-3, 4 and 6 legs -- and collapsing them would silence
    the second.

    `None` when the card has no legs. A card with nothing in it has no identity
    to dedupe on, and returning a key like `"safe:"` would make every empty
    card the same card forever.
    """
    legs = card.get("legs") or []
    tickers = sorted(
        str(leg["ticker"]) for leg in legs if leg.get("ticker")
    )
    if not tickers:
        return None
    return f"{card.get('key')}:{'|'.join(tickers)}"


def parlay_card_due_ms(day_start_ms: int, hour_utc: int) -> int:
    """The instant this budget day's scheduled card becomes due.

    The first UTC `hour_utc` at or after `day_start_ms`. **Not
    `day_start.replace(hour=...)`**, which is only the same thing while the
    card hour is later in the clock than the budget day's start: the budget day
    begins at 10:00Z by default, so a card configured for 05:00Z belongs to the
    *next* calendar date and a plain `replace` would put it seventeen hours in
    the past and fire it instantly at the day roll.

    Pure, and module-level rather than a method, so the arithmetic can be
    tested without a database or a notifier.
    """
    start = datetime.fromtimestamp(day_start_ms / 1000, timezone.utc)
    due = start.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if due < start:
        due += timedelta(days=1)
    return int(due.timestamp() * 1000)


def hedge_key(position: Mapping[str, Any]) -> Optional[str]:
    """The identity of one hedge alert, for `notifications.UNIQUE (kind, key)`.

    `hedge_lock:<position id>:<floor, floored to the ratchet step>`.

    **A ratchet, because a dedupe key is not a threshold.** `UNIQUE (kind, key)`
    never repeats a key, which is exactly right for a parlay card -- its
    identity is fixed the moment its legs are chosen -- and exactly wrong for a
    lock, whose value moves every minute the game runs. Keying on the position
    alone would say it once and never again as the figure doubled; keying on the
    exact figure would say it on every tick.

    Flooring to a step gives both properties at once. The first lock worth
    having is announced; a materially better one is announced again, because it
    lands in a bucket nothing has claimed; and noise around a level is silent,
    because it does not. It needs no timestamp comparison and no threshold to
    tune, and it survives a restart -- the properties ADR 0072 Decision 3 chose
    the card key for.

    **It ratchets in one direction only, and that falls out rather than being
    coded.** A figure that rises then falls back re-enters a bucket already
    claimed, so it stays quiet. Only a genuinely new high says anything.

    `None` when there is nothing to announce: no hedge block, not a lock, no
    reachable rung, or a floor that is not a gain. A key like `hedge_lock:7:`
    would make every un-announceable state the same state forever.
    """
    block = position.get("hedge") or {}
    if block.get("kind") != "lock" or not block.get("guaranteed"):
        return None
    rung = block.get("best_available")
    if not rung or not rung.get("floor_is_a_gain"):
        return None
    floor = rung.get("floor_tenths")
    if floor is None:
        # The payload renders money as strings, so the raw figure rides along
        # only for this. Its absence means an older backend, and a key built
        # from a rendered string would re-announce on a rounding change.
        return None
    step = int(floor) // HEDGE_RATCHET_STEP_TENTHS
    return f"hedge_lock:{position.get('id')}:{step}"


@dataclass(frozen=True)
class AlertResult:
    """What one pass decided to say. Returned so the loop can log it.

    `skipped` is populated when an alert was *already sent*, which is a
    different state from having nothing to say and is the one that proves the
    dedupe is working rather than the notifier being broken.

    **`held` is a fourth state and not a flavour of `skipped`.** A card waiting
    out `PARLAY_DEBOUNCE_BUILDS` was a genuine candidate that was *not* deduped
    -- nothing about it had been sent before. Filing it under `alerts_deduped`
    would say the dedupe was working when what was working is the debounce, and
    the two have different remedies: a stuck `skipped` means the ladder is
    rebuilding identically, a stuck `held` means it is churning. That is the
    same distinction `PUSHED_CARD_KEYS` already draws for screen-only cuts,
    which are neither sent nor skipped.
    """

    sent: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    held: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "alerts_sent": list(self.sent),
            "alerts_failed": list(self.failed),
            "alerts_deduped": list(self.skipped),
            "alerts_held": list(self.held),
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

    def delivery_health(self, *, now_ms: int, window_ms: int = 24 * 3_600_000):
        """What the alerter has actually managed to send. For `/api/health`.

        **`notifications_configured` is a boolean about whether a string is
        non-empty**, so a revoked webhook and a quiet slate are the same
        reading. This is the difference, and it is not hypothetical: the live
        record on 2026-08-18 held exactly one `failure` row and it was
        `delivered = 0` -- the loop died, the alert was claimed, and nothing
        reached the phone. One for one, and nothing said so for months.

        Returns plain values rather than a dataclass because its one consumer
        serialises it straight to JSON.
        """
        row = self.conn.execute(
            "SELECT MAX(CASE WHEN delivered = 1 THEN sent_ms END) AS last_ok, "
            "SUM(CASE WHEN delivered = 0 AND sent_ms >= ? THEN 1 ELSE 0 END) "
            "AS failed_recent, COUNT(*) AS total "
            "FROM notifications",
            (now_ms - window_ms,),
        ).fetchone()
        # `None` for "never delivered anything", never 0 -- a zero timestamp is
        # 1970 and would render as a delivery. This repo's recurring defect.
        return {
            "last_delivered_ms": row["last_ok"],
            "undelivered_last_24h": int(row["failed_recent"] or 0),
            "total_ever": int(row["total"] or 0),
        }

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

        # **Only when something surfaced, and this is a measurement, not a
        # taste.** Queried on the live volume 2026-08-18:
        #
        #     digest       12   delivered 12
        #     window_open  93   delivered 93
        #     failure       1   delivered  0
        #     opportunity   -   NO ROWS AT ALL
        #
        # Ninety-three buzzes across twelve budget days -- about eight a day --
        # and **not one `opportunity` row has ever been written**, so every one
        # of those ninety-three opened onto a board with nothing on it. That is
        # not a hypothetical: the module docstring above warns that a
        # notification per non-event "would train you to ignore the channel,
        # which is worse than no channel", and the record says it already had
        # ninety-three goes at doing exactly that.
        #
        # What is lost, stated because it is real: the alert used to double as
        # proof the loop was alive. The daily digest already carries that, on a
        # cadence that cannot storm, so the heartbeat is not lost -- only its
        # duplicate. And the empty case was the *majority* of the signal, so
        # dropping it does not thin a useful stream; it removes the stream and
        # keeps the exceptions.
        #
        # `counts.surfaced` rather than re-querying: it is what this pass
        # actually wrote, and it is the same number the embed reports.
        if sweeps_this_pass > 0 and window is not None and counts.surfaced > 0:
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

    def _parlay_pushes_today(self, *, day_start_ms: int) -> int:
        """Delivered parlay pushes since the budget day began.

        Counts `delivered = 1` only. A push Discord rejected did not reach the
        phone, so charging it against a ceiling that exists to protect the
        phone would let an outage silence the rest of the day.
        """
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM notifications "
            "WHERE kind = 'parlay_card' AND delivered = 1 AND sent_ms >= ?",
            (int(day_start_ms),),
        ).fetchone()
        return int(row["n"] or 0)

    def _observe_candidate(
        self, card_key: str, key: Optional[str], *, now_ms: int
    ) -> int:
        """Record this build's composition for one card slot; return its run.

        The returned number is how many **consecutive** builds this slot has
        shown `key` for, counting this one. `0` when the slot built nothing.

        Three transitions, and each is a separate behaviour a test can pin:

        - **Same key as last build** -- the run continues, `builds += 1`, and
          `first_ms` is left alone so it keeps meaning "when this composition
          first appeared" rather than "when it was last seen".
        - **Different key** -- the row is *replaced*, run restarts at 1. Not
          accumulated: under churn the same two compositions alternate, so a
          counter that only ever went up would be satisfied by exactly the
          pattern being suppressed.
        - **No key at all** (an unbuilt card, `parlay_key` is `None`) -- the row
          is **deleted**. A composition that appears, vanishes and reappears has
          not held for two consecutive builds, and leaving the row would let it
          claim it had.

        Commits, because the caller is about to `await` a network send and a
        run counted only in an uncommitted transaction is a run that a crash
        between here and there silently rewinds.
        """
        if key is None:
            self.conn.execute(
                "DELETE FROM parlay_card_candidates WHERE card_key = ?",
                (card_key,),
            )
            self.conn.commit()
            return 0
        row = self.conn.execute(
            "SELECT key, builds FROM parlay_card_candidates WHERE card_key = ?",
            (card_key,),
        ).fetchone()
        if row is not None and row["key"] == key:
            builds = int(row["builds"]) + 1
            self.conn.execute(
                "UPDATE parlay_card_candidates SET builds = ? WHERE card_key = ?",
                (builds, card_key),
            )
        else:
            builds = 1
            self.conn.execute(
                "INSERT INTO parlay_card_candidates "
                "(card_key, key, first_ms, builds) VALUES (?, ?, ?, 1) "
                "ON CONFLICT (card_key) DO UPDATE SET "
                "key = excluded.key, first_ms = excluded.first_ms, builds = 1",
                (card_key, key, int(now_ms)),
            )
        self.conn.commit()
        return builds

    async def parlay_cards(
        self,
        ladder: dict,
        *,
        now_ms: int,
        day_start_ms: int,
        card_hour_utc: int,
    ) -> "AlertResult":
        """Push the day's scheduled card, and any composition that has held
        still long enough to be worth a second buzz.

        **Two channels, and separating them is the whole point of this method.**
        Until 2026-08-27 there was one, and `run_loop.py` justified it in these
        words: *"The daily card is the first build after the slate turns over;
        the material-change alert is any later pass whose legs differ. Same
        event seen twice, so one call."* Then it was measured on live, and the
        first build after the slate turns over is precisely the **least**
        trustworthy one -- see `PARLAY_DEBOUNCE_BUILDS` for the four minutes in
        which the day's whole ceiling went.

        **1. The scheduled card** (`PARLAY_DAILY_KIND`). Fires on the first
        build at or after `card_hour_utc`, keyed on the budget day so it goes
        once and once only. Immune to churn by construction rather than by
        policy: whatever the ladder says at that hour is the day's card.
        Deliberately **not** debounced -- a debounce could delay or skip the one
        push that is supposed to be guaranteed, and Joe picked the hour on the
        basis that the card would be there.

        It does not spend `MAX_PARLAY_PUSHES_PER_DAY`, because it cannot run
        away: its own key bounds it at `len(PUSHED_CARD_KEYS)` a day.

        **2. The change alert** (`PARLAY_CHANGE_KIND`), keyed on `parlay_key`
        and now gated on the composition surviving `PARLAY_DEBOUNCE_BUILDS`
        consecutive builds. The `notifications` claim is still what stops a
        re-push; the debounce only adds a condition, so nothing that used to be
        suppressed is now sent.

        **A successful scheduled push burns the change key for the same
        composition**, and without that the split would double every card. The
        two channels have different `kind`s, so `UNIQUE (kind, key)` does not
        see across them: the card sent at the stated hour would be re-announced
        by the change channel ten minutes later as soon as it had held two
        builds, having changed nothing at all. Claiming both is one
        composition, one buzz.

        **The asymmetry is deliberate and only runs one way.** A change alert
        earlier in the day does *not* stop the scheduled card re-sending the
        same legs at the stated hour. The daily card is the product and Joe
        expects it to be there; the change alert is a nudge. Paying for that
        with at most one duplicate a day is the trade that was chosen.

        `parlay_key` is the canonical card identity throughout: it is what
        `parlays.price_card_on_kalshi` compares to decide the slate has drifted
        under a tap, and what `parlay_lookups.selected_legs` stores. Any other
        key would be a second definition of "the same card".

        **Price drift alone does not re-send, deliberately.** The legs are the
        card; a re-quote of the same six legs is the same suggestion, and a
        phone that buzzes when a fair value moves a tenth of a cent is a phone
        that gets silenced.

        Unbuilt cards send nothing -- `DiscordNotifier.parlay_card` refuses them
        too, and both refusals are deliberate: a push saying "nothing tonight"
        is a notification with nothing behind it.
        """
        sent: list[str] = []
        failed: list[str] = []
        skipped: list[str] = []
        held: list[str] = []

        if not self.enabled:
            return AlertResult((), (), (), ())

        notes = ladder.get("notes") or {}
        scheduled_due = now_ms >= parlay_card_due_ms(day_start_ms, card_hour_utc)
        pushed_today = self._parlay_pushes_today(day_start_ms=day_start_ms)

        for card in ladder.get("cards") or []:
            card_key = str(card.get("key"))
            if card_key not in PUSHED_CARD_KEYS:
                # Neither sent nor skipped: a screen-only cut was never a
                # candidate for the phone, and counting it as `skipped`
                # would inflate `alerts_deduped` with rows that were never
                # deduped. Not tracked in `parlay_card_candidates` either --
                # a slot that cannot be pushed has no run worth counting, and
                # a key added to `PUSHED_CARD_KEYS` later correctly starts at
                # zero rather than inheriting a run it never earned.
                continue

            # **Observed before any of the send decisions, and for every
            # buildable slot.** The run is a fact about the ladder, not about
            # what was sent: skipping the write when the ceiling is spent, or
            # when the scheduled card has already gone, would leave a stale row
            # that the next eligible build would read as a continuing run.
            key = parlay_key(card)
            builds = self._observe_candidate(card_key, key, now_ms=now_ms)

            # **No `not_built_reason` check, and its absence is the decision.**
            # One was written, mutated, and observed GREEN: an unbuilt card
            # always serialises with `legs: []` (`Card.__post_init__`
            # guarantees legs-or-reason, and `_serialise_card` returns the
            # empty list), so `parlay_key` already returns None for exactly
            # that case. A second check that changes no answer reads like a
            # guard and is not one. `DiscordNotifier.parlay_card` keeps its own
            # refusal because it is reachable from elsewhere; this is not.
            if key is None:
                continue

            detail = f"{card_key}: {len(card.get('legs') or [])} legs"

            if scheduled_due:
                outcome = await self._send(
                    PARLAY_DAILY_KIND, f"{day_start_ms}:{card_key}",
                    lambda c=card: self.notifier.parlay_card(c, notes=notes),
                    now_ms=now_ms,
                    detail=detail,
                )
                if outcome is not None:
                    # Today's card for this rung has just gone out, or failed
                    # trying. Burn the change key for the same composition so
                    # the other channel cannot re-announce it; see the
                    # docstring. Claimed even on a failed delivery, because a
                    # change alert re-sending what the daily card could not
                    # deliver would arrive as if the card had changed.
                    self._claim(
                        PARLAY_CHANGE_KIND, key, now_ms=now_ms, detail=detail
                    )
                    (sent if outcome else failed).append(card_key)
                    continue
                # `None` means today's scheduled card already went. Fall
                # through: a composition that has since changed is exactly what
                # the other channel is for.

            if builds < PARLAY_DEBOUNCE_BUILDS:
                held.append(card_key)
                continue

            if pushed_today >= MAX_PARLAY_PUSHES_PER_DAY:
                # Deliberately no "you have hit the cap" notification. The one
                # thing a phone being told too much does not need is one more
                # message. `alerts_deduped` in the pass log is where this is
                # visible, which is where someone looking for it will be.
                skipped.append(card_key)
                continue

            outcome = await self._send(
                PARLAY_CHANGE_KIND, key,
                lambda c=card: self.notifier.parlay_card(c, notes=notes),
                now_ms=now_ms,
                detail=detail,
            )
            bucket = (
                skipped if outcome is None else sent if outcome else failed
            )
            bucket.append(card_key)
            if outcome:
                # **An optimisation, not a guard, and the comment here used to
                # claim otherwise.** It read "counted here rather than
                # re-queried per card: three rungs in one ladder must not all
                # pass a ceiling that only one of them has room for" -- which
                # would be true if a re-query could miss the send. It cannot:
                # `_send` commits the row before returning, so re-reading the
                # count per card gives the same answer. Mutating the increment
                # into a re-query was observed GREEN, which is what established
                # this. What makes three rungs share one budget is that the
                # count is committed, not that it is cached; this line only
                # avoids a query per card. The property itself is pinned
                # behaviourally by the ceiling tests.
                pushed_today += 1

        return AlertResult(
            tuple(sent), tuple(failed), tuple(skipped), tuple(held)
        )

    def _hedge_pushes_today(self, *, day_start_ms: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM notifications "
            "WHERE kind = 'hedge_lock' AND sent_ms >= ? AND delivered = 1",
            (day_start_ms,),
        ).fetchone()
        return int(row[0]) if row else 0

    async def hedge_locks(
        self, screen: Mapping[str, Any], *, now_ms: int, day_start_ms: int
    ) -> AlertResult:
        """Push the tickets whose hedge locks a gain. Nothing else.

        **Only locks reach the phone.** A ticket with several legs live has no
        guaranteed figure to state, and a push about it would be a buzz for a
        number the tool cannot stand behind. Those stay on the screen -- Joe's
        own choice, recorded in ADR 0078 Decision 2.

        **Only reachable locks.** `guaranteed` is computed from the rung bounded
        by the book's depth and by the observed balance; a lock nobody could
        buy is not a lock, and announcing one would be the first entry in the
        list of reasons to mute this channel.

        A screen-only ticket is **neither sent nor skipped**. Counting it as
        skipped would inflate `alerts_deduped` with rows that were never
        deduped -- the distinction ADR 0072 drew for a screen-only parlay card.
        """
        if not self.enabled:
            return AlertResult()

        sent: list[str] = []
        failed: list[str] = []
        skipped: list[str] = []
        notes = dict(screen.get("notes") or {})
        pushed_today = self._hedge_pushes_today(day_start_ms=day_start_ms)

        for position in screen.get("positions") or []:
            key = hedge_key(position)
            if key is None:
                continue
            if pushed_today >= MAX_HEDGE_PUSHES_PER_DAY:
                # Past the ceiling the day's pushes stop and the screen still
                # has everything. A desk that keeps buzzing manufactures
                # action, which ADR 0071 says this tool does not do.
                skipped.append(key)
                continue
            outcome = await self._send(
                "hedge_lock",
                key,
                lambda p=position: self.notifier.hedge_lock(p, notes=notes),
                now_ms=now_ms,
                detail=str(
                    (position.get("hedge") or {}).get("guaranteed_display") or ""
                ),
            )
            if outcome is None:
                skipped.append(key)
            elif outcome:
                sent.append(key)
                # Only a DELIVERED push spends the ceiling, so one Discord
                # outage cannot silence the rest of the day (ADR 0072 §4).
                pushed_today += 1
            else:
                failed.append(key)

        return AlertResult(
            sent=tuple(sent), failed=tuple(failed), skipped=tuple(skipped)
        )

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
            # **Both halves of `Recommendation.surfaced`.** `engine.py` defines
            # a surfaced row as sized above zero AND unsuppressed, and this
            # query carried only the first. They agree today -- `engine.py`
            # zeroes contracts on suppression, and `with_added_suppression`
            # zeroes all four fields -- so this was not a live bug. It is the
            # two-paths-one-definition shape the digest query below was already
            # repaired for: the day the sizer stops zeroing that field, this
            # announces suppressed rows to a phone and nothing says so.
            "WHERE r.created_ms = ? AND r.suggested_contracts > 0 "
            "AND r.suppressed_reason IS NULL "
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
        return await self._failure(
            kind, lambda: self.notifier.failure(kind, detail),
            detail=detail, now_ms=now_ms,
        )

    async def _failure(
        self, kind: str, coro_factory, *, detail: str, now_ms: int
    ) -> Optional[bool]:
        """The shared claim-and-send for every failure kind.

        Takes the coroutine factory rather than the text, so the callers below
        can use `DiscordNotifier`'s purpose-built methods -- `feed_died`,
        `credits_exhausted`, `fee_mismatch` -- each of which carries copy saying
        what the failure means for the numbers on screen. Those three had
        **zero production callers** until 2026-08-18: every reference in the
        tree was a test. Routing them through the generic `failure(kind,
        detail)` would have kept it that way while looking wired.

        The kind is asserted against `FAILURE_KINDS` because it is half of the
        dedupe key. A typo does not fail loudly -- it opens a second bucket, and
        the phone gets the same alert twice a day, which reads as the alerter
        being noisy rather than as a bug.
        """
        assert kind in FAILURE_KINDS, f"undeclared failure kind {kind!r}"
        if not self.enabled:
            return None
        return await self._send(
            "failure", f"{kind}:{_day(now_ms)}",
            coro_factory,
            now_ms=now_ms, detail=detail[:200],
        )

    async def check_feed(
        self, *, now_ms: int, hub_running: Optional[bool], markets_priced: int
    ) -> Optional[bool]:
        """Alert when the live feed is down while there is something to feed.

        **This is the alert the Board cannot substitute for**, and the reason is
        in `discord.py`'s own docstring: a dead feed makes the cockpit look
        *calm*. Prices stop moving, stale numbers render identically to fresh
        ones, and silence is the symptom.

        `markets_priced` is the denominator and it is not optional. Overnight
        with no slate there is nothing to quote, and a watchdog without this
        clause would buzz every night -- which is how a channel gets muted, and
        a muted channel is strictly worse than no channel.

        **`hub_running` crosses a process boundary, and the in-process
        alternative was checked and rejected.** The obvious local signal is the
        age of the newest `kalshi_quotes` row, but that table is written **only**
        by `runner.store_quotes_from_discovery`, at `source = 'rest'`, on every
        pass; `QuoteHub` writes nothing to it. So quote age measures this loop's
        own liveness and is blind to the WebSocket entirely -- and a loop cannot
        alert on its own death in any case. The hub lives in the uvicorn process
        (`routes.create_app`), which already publishes the canonical answer as
        `/api/health`'s `live_quotes_available`. Reading that is not a second
        implementation of the check: `docker/entrypoint.sh:176` polls the same
        endpoint on the same loopback address to decide the backend has started.

        `None` means the probe itself failed, which is a different and worse
        fact than the hub being down -- the API is not answering on loopback at
        all. It gets its own kind so the two cannot be confused on a phone.

        **What this does not cover: the container crash-looping.** That kills
        this process before any of this runs, and it is the failure that has
        actually happened to this instance (the 2026-08-16 volume-full
        incident). Nothing running *inside* the box can report the box being
        dead. That needs an external dead-man's switch and is not built here.
        """
        if markets_priced <= 0:
            return None
        if hub_running is None:
            return await self._failure(
                FAILURE_API_UNREACHABLE,
                lambda: self.notifier.failure(
                    FAILURE_API_UNREACHABLE,
                    "The loop could not reach the cockpit API on loopback, so "
                    "the live feed's state is unknown. Every price on the Board "
                    "may be frozen, and a frozen price renders exactly like a "
                    "fresh one.",
                ),
                detail="health probe failed",
                now_ms=now_ms,
            )
        if hub_running:
            return None
        return await self._failure(
            FAILURE_FEED_DIED,
            lambda: self.notifier.feed_died(
                f"The quote hub is not running while {markets_priced} market(s) "
                f"are being priced."
            ),
            detail=f"{markets_priced} markets priced",
            now_ms=now_ms,
        )

    async def check_credits(
        self, *, now_ms: int, remaining_today: int
    ) -> Optional[bool]:
        """Alert once when the day's odds credits are gone.

        Not a malfunction -- it is the budget working -- but it is invisible
        from the Board, which simply stops producing new rows. The notifier's
        own copy says exactly that, which is why this routes through
        `credits_exhausted` rather than the generic failure.
        """
        if remaining_today > 0:
            return None
        return await self._failure(
            FAILURE_CREDITS_EXHAUSTED,
            lambda: self.notifier.credits_exhausted(remaining_today),
            detail=f"{remaining_today} remaining",
            now_ms=now_ms,
        )

    async def check_fee(
        self, *, now_ms: int, ticker: str, predicted: float, actual: float
    ) -> Optional[bool]:
        """Alert when a real fill disagrees with `core/fees.py`.

        Keyed per *day* like every other failure rather than per ticker: a wrong
        fee model is wrong on every fill, and one alert saying "stop the line"
        is the whole message.

        **This one still has no production caller, and that is recorded rather
        than hidden.** `ORDERS_ARE_DRY_RUNS = True` (`store/orders.py:129`)
        means this instance has never placed an order, so there is no fill to
        reconcile and no honest place to call it from. It is here so the
        reconciliation path has one obvious hook when arming happens. The other
        two on this class were wired the same day; this one could not be.
        """
        return await self._failure(
            FAILURE_FEE_MISMATCH,
            lambda: self.notifier.fee_mismatch(ticker, predicted, actual),
            detail=f"{ticker} {predicted:.2f} vs {actual:.2f}",
            now_ms=now_ms,
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
