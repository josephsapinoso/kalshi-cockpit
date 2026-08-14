# Runbook — the fee-calibration round, for Joe

**Written 2026-08-12.** Everything here is quoted from
`docs/measurements/2026-08-10-preregistration-fee-rate-attribution-round-three.md`
(the registration). Where I've paraphrased, the section number is next to it so
you can check me.

---

## READ THIS FIRST — you cannot place the first order yet, and it isn't a money problem

**§8 of the registration says: *"Q-W must have been run and reported before the
first order."*** That is a hard precondition, not a preference.

**Q-W has not been run, and cannot be run today.** It needs a `kalshi_quotes`
query inside `scripts/inspect_live_db.py`; that file has no such query, and a new
query reaches the live machine **only at the next deploy**. Deploys are yours.

**This blocks every version of the run, including the small one.** It is not a
"cell W" problem that you can dodge by skipping cell W:

- Skipping W legally requires Q-W to have **run and failed** (§1.3). It hasn't
  run, so W is **UNRESOLVED**, which is a different state.
- §Power only enumerates a **5-cell** branch and a **4-cell** branch. The 4-cell
  branch is licensed only by a failed Q-W. So **the $3.66 four-cell version is
  not currently legal**, and neither is any smaller version.

So: **do not place an order tonight.** Nothing is lost — the registration's hard
expiry is **2026-08-31 (UTC)**, which is about 19 days away.

---

## The one decision that is yours

You already authorised **$5.00** for this on 2026-08-10, so neither option below
asks you for more money. The choice is about *how* to clear the blocker.

### Option A — unblock Q-W properly, then run all five cells. **This is what I'd do.**

> **Joe chose A on 2026-08-13, and step 1 is DONE.** The query is
> `kalshi-quotes-band` in `scripts/inspect_live_db.py`. **Step 2 — your deploy —
> is now the only thing standing between here and the orders.** Nothing else on
> this page has changed.

1. ~~Next session, I add the `kalshi_quotes` query to `inspect_live_db.py`, with
   tests, and it gets reviewed.~~ **Done.** 36 tests, 23 mutations seen red,
   reviewed against venue behaviour: the derived-ask depth column and the
   3-hour `occurrence_datetime` offset were both re-derived from the writers
   rather than assumed. Two things the query reports but does **not** filter on,
   because a filter would be a threshold the registration never registered:
   how far ahead each fixture was, and any market not on a whole-cent grid.
2. **You deploy.** (One tap-equivalent, but it's your call — ADR 0018.)
3. I run Q-W and publish its result *before* any order — instant count,
   percentage, event count — whether it passes or fails (§1.3).
4. You then place **five** orders. Max stake **$4.05**, max loss **$4.27**,
   **$4.81** if the one licensed re-attempt is used. All inside your $5.00.

**What it buys:** the full 5-cell design — 32 outcome vectors, each hypothesis
pinned to a unique one. If Q-W *fails*, you drop to four cells legitimately and
still run, at $3.66.

### Option B — amend the registration to drop cell W without running Q-W

Faster and cheaper ($3.66, no deploy). **But it changes a precondition after
we've learned we can't meet it**, which is the exact degree of freedom this whole
document family exists to prevent. It also costs real information: §Power says
the four-cell all-LOW vector **declares three hypotheses at once** (H-SERIES,
H-SPORT, H-NOTIONAL) and must be reported as a three-way non-separation.

**I'd avoid it.** Nineteen days is plenty of runway, and Option A is the honest
version.

> **Tell me which and I'll take it from there.** Everything below is the actual
> trading procedure, and it's identical either way. It's worth reading now so
> that on the night you're not reading it for the first time.

---

## The procedure, for the night you run it

### Before you start

- **One calendar date. One 120-minute window** from your first order (§8). Once
  the first order goes in, the date is fixed — no continuing tomorrow.
- **Evening is the good window** — 17:00–23:59 ET. The census found a qualifying
  cheap market at **189 of 189** instants in that window (§Operability). It's a
  preference, not a rule.
- **Every market must be pre-game.** Game not started, no score shown (P8).
- **I will be in session with you**, running the watcher live so you have the
  board. Never work from a sheet I generated earlier — a pre-generated sheet is
  stale quotes wearing a live board's look.

### The five orders, in this order

Place them **in this sequence**, with **at least 60 seconds between S1 and S2**
(§6).

| # | Cell | Series | Buy | Price band (the ask you cross) | Skip these prices |
|---|---|---|---:|---|---|
| 1 | **S1** | `KXMLBSPREAD` | **1** contract | **6–15c** | 10c |
| 2 | **S2** | `KXMLBSPREAD` | **20** contracts | **6–13c** | 10c |
| 3 | **S3** | `KXMLBSPREAD` | **1** contract | **27–39c** | 30c |
| 4 | **R** | `KXMLBGAME` | **1** contract | see the two passes below | 30c, 40c, 50c |
| 5 | **W** | whichever WNBA series Q-W picked | **1** contract | **27–39c** | 30c |

**Cell R has two passes** (§C5), and this matters — R is the cell that anchors
the whole round:

- **Pass 1:** scan for the first `KXMLBGAME` market with an ask in **47–52c**
  (not 50c). Prefer this.
- **Pass 2:** only if a *full* Pass-1 scan finds nothing — scan again for an ask
  in **27–52c** (not 30c, 40c, 50c).
- Tell me which pass you used.

**S1 and S3 on the two teams of the same game is fine and expected** (§3) — a
15c ask on one side against a 32c ask on the other. Both are YES buys.
**Never buy the NO side of anything.** That's forbidden for every cell.

### Where the cheap band actually lives — added 2026-08-12, because it isn't obvious

**A `KXMLBSPREAD` game lists six markets, not two.** Three strikes per team.
Live example, pulled 2026-08-12 17:57Z, one game, every market:

```
TB2   57c        ATH2   20c
TB3   46c        ATH3   14c   <- S1 can take this (6-15c)
TB4   36c  <- S3 ATH4    9c   <- only this one is inside S2's 6-13c
```

**The 6–13c band exists only at the deepest strike on the underdog's side.**
If you look at a game's first or default strike you will see something like 20c
and 57c and correctly conclude there is nothing in band. **You have to go down
the strike ladder on the cheap team.**

Note the two bands are not the same: `S1` is **6–15c** so 14c works for it;
`S2` is **6–13c** so it needs the 9c. One game can still serve all three MLB
cells — S1 and S2 both at 9c, S3 at 36c — which is the preferred shape.

*One event at one moment, not a census. It explains the shape; it is not a
claim about how often the band exists.*

### How to pick the market — the rule that stops you optimising

> Scan the app's list for that series **in its default order, top to bottom**.
> Take the **first** market whose displayed ask is inside the band, isn't an
> excluded price, whose displayed size at that ask is **≥ the number of contracts
> you're buying**, and whose game hasn't started. **Stop there.**

**No re-scanning. No comparing candidates. No waiting for a better price.** If
you skip a market you never go back to it.

If the ask moves between reading it and submitting: re-read. Still in band, use
it. Out of band, abandon that market and carry on down the list from the next
one. **At most two abandonments per cell** — on the third, that cell is
**NOT ATTEMPTED** and you move on. (This should be rare: the ask is unchanged in
98% of consecutive polls.)

If a full scan finds nothing qualifying, the cell is **NOT ATTEMPTED**. There is
no substitute band. That's a valid outcome, not a failure.

### The four-point check — every order, no exceptions

Round one lost its first fill because the app defaulted to a dollars-to-spend
buy and produced `count = 0.27`. **Before you press submit, confirm all four:**

1. The ticket says **"Limit order"** — not Market, not any dollars-to-spend mode.
2. The **contracts field reads exactly the number** — `1`, or `20` for S2 — as a
   whole number, not a dollar amount.
3. The **limit price equals the displayed ask exactly.**
4. The **estimated cost equals contracts × ask, to the cent.** `1 × 48c` must
   read **$0.48**. `20 × 8c` must read **$1.60**.

**If any of the four fails: cancel the ticket and re-enter it.** A submitted
order that fails check 2 is a dead cell, not a data point.

### After you submit — watch it for 60 seconds

- **Fills in full** → normal. Move to the next cell.
- **Doesn't fill in 60 seconds** → **CANCEL IT.** Report it as
  `NOT ATTEMPTED (DID NOT FILL)`. **Do not raise the price. Do not wait longer.
  Do not re-submit into that same market.** An unfilled order that sits there
  turns you into a maker, and a maker fill voids the cell.
- **Fills partially** → cancel the remainder immediately. Don't top it up.

**A "did not fill" is a genuine result** — it's the one thing the whole $4
buys that no amount of free data can produce: whether the displayed size was
real or a maker who pulled.

### What to write down, for every order

From the app, at placement (§3):

- ticker, and the series prefix
- side (always YES)
- displayed ask, and displayed size at that ask
- number of contracts
- the app's displayed **estimated cost**
- the app's displayed **fee**, if it shows one
- the timestamp
- the market's **scheduled first pitch**, and **minutes remaining** to it

The last two are required, not optional.

### After the last order — one final sweep

**Re-open every earlier order and re-read its fee** (P7). If any earlier fee has
*changed* after a later order, **stop and tell me** — that would mean Kalshi is
aggregating orders for fee purposes, and it changes what the round can conclude.

### Hard limits

- **6 orders, $4.57 of stake, maximum.**
- At most **one re-attempt, of one cell**, and only for R, S1, S3 or W, and only
  if that cell was killed by a mechanical problem (bad ticket, wrong series,
  in-play). **S2 gets no re-attempt.** R has first call.
- **A cancelled unfilled order doesn't count** against the 6 / $4.57 cap.
- **Hold the positions to settlement.** Don't sell out. A sell price can't be
  fixed in advance, so a sell isn't part of this measurement.

> **An order beyond the registered set is a protocol breach, not a bonus data
> point.** If you place one, tell me — it gets published as unregistered and the
> run's verdict has to say `BREACHED`. Round one placed two extras and they were
> useful, which is exactly why this is written down.

---

## What this is for, in one paragraph

Kalshi's published fee coefficient implies a break-even bar of 51.75%. The code
charges the conservative maximum across candidate models, so the bar it actually
applies is **52.00%**. Against a sportsbook's 52.38%, that's **0.38 points** of
headroom — and even that is an upper bound (ADR 0027). Six fills so far fit
`k = 0.035` on MLB and `k = 0.070` on ATP. **If the real coefficient is 0.035,
the taker bar drops to 50.88%** and the gap to a sportsbook goes from 0.38 points
to 1.12. That is the difference between "no edge exists here" and "an edge
exists". Five orders and about four dollars decide it.
