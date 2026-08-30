"""Withdraw a resting bid when its first game starts.

ADR 0084. The desk places bids that outlive their request -- the first order
shape in this repo that can be taken while nobody is watching. That is the
whole point of a resting bid on an enter-only market, and it is also its one
real hazard: **a fill after a leg has kicked off is a bet on a game already
under way, at a price computed before it began.** Every number on the card --
the devigged consensus, the joint, the fair value -- is pre-game by
construction (`ladder_candidates` refuses a started game outright), so a fill
after kickoff is priced on evidence that no longer describes the market.

So the deadline is the earliest leg's `commence_ms`, frozen on the row when the
bid was placed, and this loop is what makes it real. Without it the deadline is
a number in a column that nothing reads -- the "built but never called" failure
this repo has recorded four times.

**Cancelling is the safe direction and that is why this runs unattended.** The
worst case of a cancel that should not have happened is a bet Joe has to place
again by hand. The worst case of a fill that should not have happened is a
position he did not choose, on a game in progress, that a combination book
gives him no way to exit.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That a bid was ever at risk of filling.** No combination book this repo has
  read carried a resting YES bid, so the counterparty this guards against has
  never actually been observed. It is a guard against a thing that would be
  very bad and is not known to be common.
- **That the cancel reached the venue.** A failed cancel is recorded and left
  working rather than marked cancelled: a row that says "cancelled" over an
  order still resting on Kalshi is worse than one that admits it tried.
- **Anything about fills.** This loop never reads whether a bid filled; that is
  the orders panel's job and the venue's record.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from .store import db
from .store.combo_orders import due_for_cancel, record_cancel

logger = logging.getLogger(__name__)

#: How often the deadline is checked.
#:
#: A minute, against kickoffs that are known to the second. The cost of being
#: up to a minute late is one minute of exposure on a bid nobody has ever been
#: observed taking; the cost of checking every second is a wakeup per second on
#: a box that has OOM-killed itself once.
BID_WATCH_INTERVAL_S = 60.0


async def cancel_due_bids(conn, api, *, now_ms: int) -> int:
    """Withdraw every bid whose first leg has started. Returns how many.

    Each cancel is independent: one failure must not strand the rest, because
    the rest are exactly the bids whose games have also started.
    """
    cancelled = 0
    for row in due_for_cancel(conn, now_ms=now_ms):
        order_id = row.get("kalshi_order_id")
        if not order_id:
            # No venue id: the create never came back. Marking it cancelled
            # here would be a claim about the exchange this process cannot
            # make, so it is left working and visible in the panel.
            logger.warning(
                "combo bid %s is past its deadline with no exchange order id; "
                "left working for a person to check",
                row.get("id"),
            )
            continue
        try:
            response = await api.cancel_order(
                order_id, exchange_index=row.get("exchange_index")
            )
        except Exception:                                        # noqa: BLE001
            # Left working on purpose. A row that says "cancelled" over an
            # order still resting on Kalshi is the one lie this table must
            # never tell.
            logger.exception(
                "cancelling combo bid %s at its deadline failed; it is left "
                "working and will be retried on the next pass",
                row.get("id"),
            )
            continue
        reduced = response.get("reduced_by") if isinstance(response, dict) else None
        try:
            reduced_by = None if reduced is None else float(reduced)
        except (TypeError, ValueError):
            reduced_by = None
        record_cancel(
            conn, int(row["id"]), now_ms=now_ms, reduced_by=reduced_by,
            reason="the first leg has started",
        )
        cancelled += 1
        logger.info(
            "withdrew combo bid %s at its deadline (%s contracts were still "
            "working)", row.get("id"), reduced_by,
        )
    return cancelled


async def watch_bids_forever(
    db_path,
    api_factory: Callable[[], object],
    *,
    interval_s: float = BID_WATCH_INTERVAL_S,
    max_passes: Optional[int] = None,
) -> None:
    """Check the deadlines forever. Never raises out of the loop.

    `api_factory` rather than a client, for the reason the hedge watcher takes
    a factory: this task owns the only connection it may use, and a Kalshi
    client built once at startup on a keyless instance would take the process
    down for a feature that instance does not expose.
    """
    passes = 0
    while max_passes is None or passes < max_passes:
        passes += 1
        conn = None
        try:
            conn = db.open_db(db_path)
            await cancel_due_bids(conn, api_factory(), now_ms=db.now_ms())
        except Exception:                                        # noqa: BLE001
            # A watcher that dies stops withdrawing bids, silently, and the
            # only symptom is a fill nobody expected hours later.
            logger.exception("the resting-bid watcher raised; continuing")
        finally:
            if conn is not None:
                conn.close()
        if max_passes is not None and passes >= max_passes:
            return
        await asyncio.sleep(interval_s)
