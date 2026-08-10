# Round three — phone sheet

**Five orders. By hand. On your phone. Then stop.**

Money authorised **$5.00** · worst case **−$4.27** · expected **~−$2.50**
Expires **2026-08-31 UTC**. Nothing spent yet.

Rules live in
`docs/measurements/2026-08-10-preregistration-fee-rate-attribution-round-three.md`
(+ Correction A). This sheet is the operator's copy. If the two disagree, **the
registration wins** — but don't go read 2,300 lines on a handset. Ask the agent.

---

## Read this first — it is the one that killed round one

Round one's app defaulted to **buy-in-dollars**. It bought **0.27 contracts**.
That fill was destroyed and could test nothing.

### THE FOUR-POINT CHECK — every order, no exceptions

Before you press submit:

- [ ] **1. It says "Limit order"** — not Market, not any spend-dollars mode
- [ ] **2. The shares field reads a WHOLE NUMBER** — `1`, or `20` for order 2
- [ ] **3. Limit price = the ask shown on screen**, exactly
- [ ] **4. Estimated cost = shares × ask** — `1 × 48c` must read **$0.48**;
      `20 × 8c` must read **$1.60**

**Point 4 is the one that catches point 2.** If any fail: cancel the ticket,
re-enter it. A submitted order that fails point 2 is a **wasted cell**.

Also, every order: **the game must not have started.**

---

## After every submit — watch it for 60 seconds

| What happens | What you do |
|---|---|
| **Filled in full** | Good. Next order. |
| **Not filled in 60s** | **CANCEL IT.** Write "DID NOT FILL". Move on. |
| **Filled partly** | **Cancel the rest.** Write it down. Do not top up. |

**Do not raise the price. Do not wait longer. Do not re-submit into that
market.**

> **A "did not fill" is a RESULT, not a mistake.** It is the one thing the whole
> census could not tell us — whether the size on screen is real. It is worth
> having. Don't rescue it.

---

## When to do this

**5pm–midnight ET.** On the days measured, the cheap band was on the board at
**every single instant** in that window, about four markets at a time.

All five orders in **one sitting, within 120 minutes**, on **one date**.
Round one did six in fourteen minutes. You have plenty of time.

---

## Ask the agent to run the watcher first

```
.venv\Scripts\python.exe scripts\watch_fee_bands.py --once
```

It prints the first qualifying market for each order. It shows **one** per
order on purpose — the rule is take the first, never shop around.

**If it says `R IS NOT PLACEABLE`, do not start.** Order 4 is the one the
round cannot survive without. Wait and re-run.

**If it says `STARTS SOON`,** that market's game is under 15 minutes away. It is
still the correct pick by the rules — but if the game starts before your order
fills, that cell is **wasted**. Either place it right now, deliberately, or
re-run the watcher later for a fresh board. Don't dawdle on a `STARTS SOON`.

---

## The five orders

Scan the app's list **top to bottom, in its default order**. Take the **first**
market in the band. **Never scroll back up to one you passed.**

---

### ORDER 1 — MLB run line · **1** contract

**Series:** `KXMLBSPREAD` (MLB run line / spread)
**Ask must be:** **6c – 15c** · **skip exactly 10c**
**Shares field:** `1`

👉 If that same market shows **21 or more** at an ask of **6c–13c**, **use it
again for order 2**. Note that now.

---

### ORDER 2 — same market if you can · **20** contracts

**Wait 60 seconds after order 1.**

**Ask must be:** **6c – 13c** · **skip exactly 10c**
**At least 20 showing** at that ask
**Shares field:** `20` ← *the big one. Check it twice.*

**📸 WRITE DOWN YOUR ACCOUNT BALANCE IMMEDIATELY BEFORE AND AFTER THIS ORDER —
every digit.** This is the only order that gives us a second, independent read
on the fee. A screenshot of each is fine.

If order 1's market didn't have 21+ showing, use the first `KXMLBSPREAD` market
with an ask in 6c–13c and 20+ showing.

---

### ORDER 3 — MLB run line, mid price · **1** contract

**Series:** `KXMLBSPREAD`
**Ask must be:** **27c – 39c** · **skip exactly 30c**
**Shares field:** `1`

This can be the **other team in the same game** as order 1 — that's normal and
expected. Still a YES buy at its own ask. **Never buy the NO side.**

---

### ORDER 4 — MLB game winner · **1** contract ⚠️ **THE IMPORTANT ONE**

**Series:** `KXMLBGAME` (who wins the game)
**Shares field:** `1`

**First look for an ask in 47c – 52c** (skip 50c). That is the preferred one.

**Only if a full scan finds none:** take the first with an ask in
**27c – 52c** (skip **30c, 40c, 50c**).

> **If you get nothing here, the round tells us much less.** Give this one the
> most patience — but still take the first qualifying market, and still never
> scroll back up.

---

### ORDER 5 — WNBA · **1** contract · ⛔ **ONLY IF TOLD**

**Do not place this unless an agent session has explicitly told you cell `W` is
active and named the series.**

Right now it is **UNRESOLVED** — the query that decides it reads the live
database, which the laptop does not have. Unresolved is **not** the same as
"no". If nobody has told you, **skip it. Four orders is a valid round.**

If told: ask **27c – 39c** (skip 30c), **shares `1`**, in the series named.

---

## Write this down for every order

Ticker · ask · **size showing at that ask** · shares · estimated cost · time ·
scheduled first pitch · minutes to first pitch · **FILLED / PARTIAL / DID NOT
FILL** and roughly how many seconds.

Photos of the ticket screens are fine. Do not rely on memory.

---

## Then stop

- **A sixth filled order is a protocol breach, not a bonus.**
- An order that didn't fill and was cancelled costs nothing and doesn't count.
- **At most two tries per cell.** Each try a different market, further down the
  list. Never back up.
- If anything feels wrong — the app looks different, the numbers don't add up,
  you're not sure — **stop and ask.** An unplaced order costs nothing. A wrong
  one costs the cell.

---

## What this is buying (one line, in case you want it)

Whether Kalshi's fee is set by the **price**, the **size**, the **series**, or
the **sport** — and whether the size showing on screen is **real**. That last
one is the only way to find out, and it needs a real order.
