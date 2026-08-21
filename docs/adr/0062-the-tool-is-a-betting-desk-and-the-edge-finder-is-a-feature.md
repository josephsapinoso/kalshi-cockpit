# 0062 — The tool is a betting desk, and the edge-finder is a feature

**Date:** 2026-08-21
**Status:** Accepted.
**Extends** [ADR 0038](0038-the-edge-hunt-is-closed-and-the-record-is-the-product.md) (the hunt is closed on
measurement) with the owner's ruling on purpose; retires the phrase "the
recorder costs nothing"; changes nothing about the gate, the dry-run
constant, or the suppression rules.
**Owns:** the retirement of the scheduled Skeptic
(`backend/agents/review.py::review_retired`, the `run_pricing_pass` default),
and the cost corrections in `fly.live.toml`, `.env.example`, and ADR 0002.

## 1. The ruling, in the owner's words

Joe, 2026-08-21, three messages in sequence:

1. *"in all honesty, is the 'kalshi edge' even a large factor? let's cut it
   out if it isnt."*
2. *"I mean, I am not betting big, so I really don't care about 1-2 cent
   diffs"*
3. *"Yes, I always wanted this to be a betting desk. the edge-finder should
   have been a feature, but not a determiner."*

The arithmetic behind it: the venue's cost advantage is 0.6–1.5 points
(ADR 0027/0028), which on his deployed position size (~$10) is about
**15 cents per bet**. ADR 0038 closed the signal hunt on measurement; this
ADR closes it on purpose. They agree.

## 2. What "a feature, not a determiner" decides

The edge surface — devig, fair value, edge points, `surfaced` — remains a
**column the desk can show as context** and stops being the thing that
organises a screen, a roadmap, or a spend. Concretely:

- No screen leads with an actionable/edge count as its headline number.
- No roadmap item is justified by "it improves edge detection."
- No metered spend is justified by guarding the edge surface (§3).
- The recorder keeps running: its rows feed the cluster accrual, the Board,
  and the scout desk's fixture linkage — not separable, so stopping the
  accrual stops the screen.

Untouched, deliberately: `backend/gate.py` and its 300 threshold,
`ORDERS_ARE_DRY_RUNS = True`, every suppression rule, the odds feed, and
ADR 0038's bar for reopening a hunt.

## 3. The scheduled Skeptic is retired, and why that was not free before

`fly.live.toml` asserted the only thing between the deployment and an
Anthropic bill was `surfaced` having been 0 for the life of the record. The
live `agent_calls` table refutes it: **2026-08-16, 24 metered Opus calls in
4m 22s** — the entire daily cap — re-reviewing the same four prop rows six
times at quote-pass cadence. `surfaced` still read 0 afterwards *because the
Skeptic blocked all 24*: the field is written after the spend it was credited
with preventing. A guard whose zero is produced by the thing being paid for
is a receipt, not a brake (`tasks/lessons.md`, 2026-08-21).

Under §2 that spend defends a decision nobody makes, so the deletion is now
free. `run_pricing_pass` defaults to `review_retired`: every surfaced row is
refused with `skeptic_unreviewed` / "retired (ADR 0062)" and **no Anthropic
call is made from any scheduled path**. Refusal rather than pass-through, on
purpose — retiring the reviewer must not quietly promote the rows it used to
review into orderable ones. `review_surfaced` stays importable for a caller
that deliberately opts back in; nothing scheduled does. Verified by
disabling: restoring the old default turns
`tests/test_agent_wiring.py::TestTheScheduledSkepticIsRetired` red.

Consequence for the record: from this date forward every would-be-surfaced
row persists suppressed as unreviewed. `surfaced` is frozen at its historical
values and is a historical column.

## 4. "The recorder costs nothing" is retired, with numbers

Marginally true, false at the plan. The recorder is ~70 Odds credits/day
measured (280 across four budgeted days) — 4.3× the free tier, and the sole
reason the $30/month 20K plan exists. Plus an always-on shared-cpu-1x/2GB
machine with a 5GB volume at its auto-extend limit (ADR 0002's "~$5/month"
described a 1GB machine and predates both incidents), plus Anthropic at a
rate the code itself flags as assumed. The phrase is retired from the
vocabulary; the recorder still runs, per §2.

Two numbers only the owner can supply, both open: **the Fly invoice and the
first Anthropic invoice.** Until they are read, every dollar figure in this
repo about either bill is an estimate and must say so. Whether the $30 Odds
tier stays paid is likewise the owner's call, not a session's.

## 5. What this does not decide

The betting-desk work list (his-record screen, refusal-on-real-data, CLV on
his own bets, scout-desk metering-then-promotion, landing-screen strip) is
direction from the 2026-08-21 partner ruling, recorded in `tasks/NEXT.md` —
not decided here. Each item lands on its own evidence.
