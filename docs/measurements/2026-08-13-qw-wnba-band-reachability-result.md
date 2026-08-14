# Q-W result — WNBA band reachability, and cell `W`

**Run 2026-08-13.** Instrument: `scripts/inspect_live_db.py kalshi-quotes-band`,
invoked by path on `kalshi-cockpit` under the ssh ruling. Artefact:
`docs/measurements/data/qw_20260813T0616Z_kxwnbagame.json` (force-added past
`.gitignore:33`, credential-scanned before staging: 0 hits). Re-derivation:

```
.venv\Scripts\python.exe scripts\analyse_qw_result.py ^
  docs\measurements\data\qw_20260813T0616Z_kxwnbagame.json
```

Registration: `docs/measurements/2026-08-10-preregistration-fee-rate-attribution-round-three.md`,
§0.4 block at line 719. Q-W is that registration's §8 hard precondition: it must
have been run and reported **before the first order** of the fee-calibration
round.

---

## §1 Verdict

> **Q-W ACTIVATES on `KXWNBAGAME`** — first series in the registered order, no
> substitution. 781 of 797 pre-game polling instants (97.99%, bar 80%) and 13
> distinct events (bar 8), window `[2026-08-07T00:00Z, 2026-08-11T00:00Z)`, band
> 270–390 tenths on the derived ask `1000 − no_bid_tenths` excluding exactly
> 300, depth ≥ 1 at that ask.

**Cell `W` is registered.** §Power's five-cell branch governs; the four-cell
branch is not licensed, and never was — `W` was `UNRESOLVED`, not failed, which
is why the $3.66 version was refused on 2026-08-12.

## §2 The mandatory qualifier

Written by `measurement-skeptic` before the number entered the record, and
reproduced **verbatim**. It may not be paraphrased and may not be separated from
§1.

> **What Q-W establishes, and what it does not.** The 97.99% is a share of
> polling instants, and the loop polls every 15s while the odds window is open
> and every 900s when it is not (`backend/scheduler.py:113-183`), so 797 instants
> are not 797 independent looks. Deduplicated to one look per burst separated by
> more than five minutes — 288 looks over 76.3h, which reproduces the 900s
> cadence at one per 15.9 min and is therefore approximately time-uniform — the
> share is **272 of 288 = 94.4%**, and that is the figure this cell is certified
> on; the independent time-weighted denominator (5.07 unavailable hours of 76.3
> observed) agrees at 93.4%. Both bars still clear. The record covers
> **2026-08-07T19:33Z to 2026-08-10T23:48Z, 3.18 days, not the registered four**:
> the live runner was first deployed at 2026-08-07T19:35Z, so the window's first
> 19.5 hours contain no instants because no instrument existed, and they are
> absent from the denominator rather than scored as misses. The 16 misses are one
> contiguous episode on 2026-08-10 between 10:51Z and 15:55Z — read as an
> operator would place, that is a **five-hour continuous outage of the band**,
> not a 2% miss rate, and it is the only stretch of that time of day the record
> scores. Q-W registered no lower bound on lead time and imposes none: **six of
> the thirteen events had not tipped by the end of the window**, they supply
> **969 of 2,257 qualifying quotes (43%)**, and restricted to fixtures that
> actually started inside the window the event count is **7, below the bar of 8**
> — an unregistered restriction, published because §1.3's rationale for choosing
> 8 was reasoned against the events in the window. Nothing here measures the last
> three hours before any tip, which is where §Operability prefers the order
> placed and which §1.2 does cite for the `KXMLBSPREAD` cells; **no time-of-day
> and no time-to-tip figure exists for `W`**. Every number is a **displayed** ask
> and a **displayed** size: availability, not fill probability (§0.4e, R6). Event
> stamps emitted by `kalshi-quotes-band` are raw `occurrence_datetime`, i.e.
> expected *expiration*; true starts are three hours earlier (ADR 0006).

### §2.1 One correction to the qualifier, recorded rather than smoothed

The qualifier states the time-weighted figure as **93.4%**. Re-derived through
`analyse_qw_result.py` it is **93.3%**: the outage spans 5.078 h of 76.256 h
observed, giving 93.34%, which rounds to 93.3 at one decimal. 93.4 comes from
carrying 5.07 h against 76.3 h.

**The difference decides nothing** — both figures clear the 80% bar by more than
thirteen points. It is recorded because the repo's standing rule is that the
auditor's prose is still prose and anything load-bearing gets recomputed, and
because a figure that appears in two documents with two values is exactly how a
citation drift starts. **Cite 93.3%, from the script.**

## §3 The parts, per UTC day

A pooled share is not a finding until the parts agree. All four days clear the
80% bar independently.

| day | instants | qualifying | share |
|---|---|---|---|
| 2026-08-07 | 13 | 13 | 100.0% |
| 2026-08-08 | 167 | 167 | 100.0% |
| 2026-08-09 | 447 | 447 | 100.0% |
| 2026-08-10 | 170 | 154 | 90.6% |
| **all** | **797** | **781** | **98.0%** |

Every miss is on 2026-08-10, and they are contiguous — see §2.

## §4 The board an operator would have seen

Median **3** qualifying markets per instant, max 6, and only **20 of 797**
instants had exactly one. Within `KXWNBAGAME` the two sides of one event cannot
both sit in 27–39c — they sum to ~100c — so three qualifying markets means
roughly three distinct events. **The breadth is real**, which matters because
§3's scan rule forbids fixing on a single market.

Depth is the weaker half: `min_depth` is **1 contract** on the four largest
contributors. The registered bar is ≥1 and it is met, but this is not the
`KXMLBSPREAD` situation, where §S2 certified 695 of 695 instants at **≥20**
displayed. **`W` has no depth-durability figure and must not inherit one.**

## §5 Lead time — the residual the registration did not price

Six of thirteen events had not tipped when the window closed. True starts, ADR
0006-corrected:

| event | true start | qualifying quotes |
|---|---|---|
| `KXWNBAGAME-26AUG10TORATL` | 2026-08-11T00:00Z | 12 |
| `KXWNBAGAME-26AUG11NYIND` | 2026-08-11T23:30Z | 447 |
| `KXWNBAGAME-26AUG11WSHLV` | 2026-08-12T02:00Z | 458 |
| `KXWNBAGAME-26AUG12TORDAL` | 2026-08-13T00:00Z | 33 |
| `KXWNBAGAME-26AUG12CHIGS` | 2026-08-13T02:00Z | 16 |
| `KXWNBAGAME-26AUG12MINPDX` | 2026-08-13T02:00Z | 3 |

969 of 2,257 qualifying quotes, **43%**. Restricted to fixtures that tipped
inside the window the event count is **7 — below the bar of 8**.

**That restriction is unregistered and cannot un-activate `W`.** The registered
rule has already fired, and letting a post-hoc cut reverse a pre-registered
verdict is the exact freedom the registration exists to remove. It is published
because §1.3's stated rationale for choosing 8 was *"roughly half the 18 WNBA
events the record holds over the window"*, and a later reader would otherwise
take "13 against a bar of 8" as clearing by 62%.

## §6 What was ruled out, and what was not

**Ruled out — half-cent rounding.** A half-cent ask inside the band (e.g. 305)
would satisfy the predicate and round *down* into the excluded hole at 300 when
a limit is placed: reachable on paper, untakeable in fact.
`non_linear_cent_quotes = 0` across all 13 events. Measured, not assumed.

**Ruled out — the wrong depth column.** The derived ask is `1000 − no_bid_tenths`
and the depth standing at it is `no_bid_qty`, because `backend/runner.py:1030-1037`
writes `(no_bid_tenths, yes_ask_size)` into `(no_bid_tenths, no_bid_qty)`.
`yes_bid_qty` is populated on nearly every row, so reading depth off the
obvious-looking column would have passed almost everything. Confirmed against a
captured payload rather than the field name, and pinned by a test at an anchor
where the two answers differ.

**Ruled out — bar-shopping.** One query, two bars, three series in registered
order, activated on the first. The bars (80%, 8) were fixed on 2026-08-10 by an
author who could not read the answer: `inspect_live_db.py` was not in the
deployed image until `b5419eb` on 2026-08-13. **That is the strongest property
of this result.**

**NOT ruled out — fillability.** Every ask and size here is a *displayed* quote.
Availability is not fillability; the separating observation is one small order.

**NOT ruled out — the placement window.** Nothing measures the last three hours
before tip, or time of day. §1.2 cites both for `KXMLBSPREAD` (37.1% within 3h;
189 of 189 instants in 17:00–23:59 ET). **`W` has neither.**

**NOT ruled out — extrapolation across dates.** Measured 2026-08-07 to
2026-08-10; placement is on or after 2026-08-13, under §8's 2026-08-31 expiry.
Shared with the MLB cells.

## §7 What this does not establish

- **Nothing about the fee.** Q-W's inputs are prices, depths and timestamps.
  **It cannot see a fee**, and it moves neither `k = 0.035` nor `k = 0.070`. It
  removes a precondition; it answers nothing about the coefficient.
- **Nothing about `actionable`.** The tool still surfaces zero rows and this
  does not change that. ADR 0025's inversion is untouched.
- **Nothing about WNBA beyond this window**, and nothing about `KXWNBASPREAD` or
  `KXWNBATOTAL`, which were never reached.

## §8 Consequence

The §8 precondition is **satisfied**. §Power's five-cell design is licensed: five
orders, max stake $4.05, max loss $4.27, $4.81 if the one licensed re-attempt is
used — all inside the $5.00 authorised on 2026-08-10. Expiry **2026-08-31 UTC**.

Placement is Joe's, on his clock, per `docs/JOE-fee-round-three-runbook.md`.
**The watcher runs at the moment he places, never in advance** — a pre-generated
sheet is stale quotes wearing a live board's look.
