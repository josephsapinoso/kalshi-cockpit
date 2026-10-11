"""One phone push when the AI account runs out of credit (#368).

Joe tops the Anthropic balance up by hand (his (B) to #367). The 2026-10-10
23:50Z outage lasted ~15 minutes and was invisible on every screen, so the
first credit failure of a budget day pushes ONE notification.

Dedupe is the existing `notifications` ledger: kind `ai_credit`, key = the
budget day's start in ms (`AgentBudget.day_start_ms`), so a second credit
failure the same budget day claims nothing and sends nothing. `kind` is free
TEXT in the schema (no CHECK), so no schema change is needed.

The text carries no key, no config name and never the raw exception envelope.

Does NOT establish: that Discord delivered it (the row's `delivered` column
says), nor that the account was really out of credit -- only that the call
failure matched `is_credit_exhausted`.
"""

from __future__ import annotations

import logging
from typing import Optional

from .alerts import Alerter
from .discord import DiscordConfig, DiscordNotifier

logger = logging.getLogger(__name__)

AI_CREDIT_KIND = "ai_credit"
CREDIT_VERDICT = "api_error:credit"


def make_notifier() -> DiscordNotifier:
    """A notifier from the environment; disabled (no-op) when unconfigured.
    Tests replace this."""
    return DiscordNotifier(DiscordConfig.from_env())


async def push_if_credit_failed(
    budget, verdict: Optional[str], now_ms: int, *, notifier=None
) -> Optional[bool]:
    """After a call settles: if it settled `api_error:credit`, push once per
    budget day. Returns None when nothing was sent. Never raises."""
    if verdict != CREDIT_VERDICT:
        return None
    try:
        day_key = str(budget.day_start_ms(now_ms))
        if notifier is not None:
            return await _push(budget.conn, notifier, day_key, now_ms)
        async with make_notifier() as owned:
            return await _push(budget.conn, owned, day_key, now_ms)
    except Exception:                                         # noqa: BLE001
        logger.exception("the credit alert failed; the call's own outcome stands")
        return None


async def _push(conn, notifier, day_key: str, now_ms: int) -> Optional[bool]:
    if not getattr(notifier, "enabled", False):
        return None
    return await Alerter(conn, notifier)._send(
        AI_CREDIT_KIND, day_key,
        notifier.ai_credit_exhausted,
        now_ms=now_ms, detail="ai account out of credit",
    )


#: What the record keeps for a credit failure (stored in a row's reason).
CREDIT_RECORD_REASON = "the call failed: the Anthropic account is out of credit"

#: What the screen says: plain words, no config name, no vendor jargon beyond
#: "the AI account" (lesson 2026-10-10: the stored reason and the screen's
#: sentence are two things).
CREDIT_SCREEN_SENTENCE = (
    "The AI account is out of credit. This is paused until it's topped up."
)


def screen_sentence(reason: Optional[str]) -> Optional[str]:
    """The screen's sentence for a stored reason that records a credit failure,
    else None (the caller keeps whatever it showed before)."""
    if reason and "out of credit" in reason.lower():
        return CREDIT_SCREEN_SENTENCE
    return None
