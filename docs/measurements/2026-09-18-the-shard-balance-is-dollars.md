# The shard balance is dollars, and the payload proves it to itself

**Question (#75):** `read_shard_funds` gates money on the RFQ path and parsed
`balance_breakdown[].balance` as *"dollars as a 4dp string"* on a comment with
no captured payload behind it. Kalshi's top-level `balance` is classically an
integer in **cents**. If the breakdown were cents too, `available_tenths` would
be **100x high and the shard wall would never fire** — the refusal arriving from
the venue instead, after the makers had answered.

**Answer: the breakdown is dollars. The comment was right, the code was right,
and the wall is not loose.** `read_shard_funds` needed one change and it is not
the units — see §4.

**No venue call was made.** The ticket's "smallest build" asked for one
authenticated `GET /portfolio/balance`. It was not needed: **72 real payloads
were already on disk**, captured 2026-09-14 by an unrelated piece of work, and
they answer the question more strongly than a single fresh call would have.

---

## 1. The population

    source      data/captures/target_allocation_20260914T*.json
    files       70
    payloads containing BOTH `balance` and a non-empty `balance_breakdown`   72
    captured    2026-09-14, ~22:29Z to ~22:31Z, one session

**Those files are gitignored** (`.gitignore:33`, `data/`) and stay that way.
They are Joe's account balances, and his standing ruling is that account and
fills data never enter this public repo, even sanitized. **No figure from them
appears in this document**, which is why §2 is written as a shape and a
relation rather than as numbers.

## 2. What the 72 payloads show

**One shape. No variation across all 72.**

    top-level  "balance"                       int
    each       "balance_breakdown[].balance"    str, matching \d+\.\d{4}

Four breakdown rows in every payload, `exchange_index` 0–3.

**And the payload cross-checks its own units**, which is what turns this from a
shape observation into a measurement:

    read the top level as CENTS and the rows as DOLLARS:
        | balance/100 - sum(rows) |  <=  0.0065 dollars   on ALL 72 payloads

    read the rows as CENTS instead:
        the same comparison is off by a factor of ~100

So the two fields are in **different units in the same payload**, and each one
pins the other. No single reading of either field alone could have established
this; the agreement between them is the evidence.

The residual 0.0065 dollars is 0.65 cents. It is not explained here and does not
need to be for the units question — candidates are a shard the top-level figure
does not sum over, or truncation in the top-level integer. **Named rather than
resolved**, because a 0.65-cent residual cannot be confused with a 100x error.

## 3. Corroboration already in the repo, and why it was not enough

`backend/kalshi/rest.py` quotes two 2026-08-30 readings that *look* like dollars.
The ticket's own words: **"Suggest is not pin."** Correct — a value like `21.4120`
is consistent with dollars and also with a cents figure the venue happened to
format with a decimal point, and neither reading is excluded by one number. The
cross-check in §2 is what excludes one.

## 4. What changed, and it is not the units

The units needed no change. One thing did:

    before   available_tenths=int(round(float(raw) * 1000))
    after    available_tenths=math.floor(float(raw) * 1000)

**A 4dp dollar figure is hundredths of a cent — finer than this project's
tenth-of-a-cent unit**, so the conversion cannot be exact. This is the same
centi-cent resolution ADR 0172 found on combination quotes, arriving on a
different field the same week.

`round` can round a balance **up** by as much as half a tenth of a cent. The
magnitude is trivial. **The direction is not:** a headroom check that
over-reports the balance is a money guard erring in the one direction this repo
refuses, and the fix is free. The two fields get opposite treatment for a
stated reason:

| | a combination quote (ADR 0172) | a shard balance (here) |
|---|---|---|
| what it is | a **price** | a **ceiling on spending** |
| too-fine value | **refused outright** | **floored** |
| why | a rounded price is a price the venue never offered | a ceiling may be understated, never overstated |

## 5. Verification

`tests/test_shard_balance_shape.py`, 9 tests, plus the RFQ route suite: **40
passed.** **Six mutations, all red:**

| | mutation | result |
|---|---|---|
| M1 | `floor` becomes `round` (a balance can be reported up) | red |
| M2 | the breakdown is read as cents — **the 100x bug** | red, 28 failed |
| M3 | a missing shard row falls back to zero | red |
| M4 | an unreadable balance becomes zero | red |
| M5 | the fixture's shard string loses its 4dp shape | red |
| M6 | the fixture's top-level balance becomes a string | red |

M3's first pattern matched three identical `return` statements and had to be
re-anchored on the preceding comment. A mutation script that silently patches
one of three matches proves nothing about which guard it tested.

**The fixture committed is SYNTHETIC** — `tests/fixtures/portfolio_balance_shape.json`
— and that is the deliberate exception, on the ADR 0035 MLBAM precedent: a
synthetic payload plus a shape assertion, because the real payload is operator
data. Its figures are round numbers chosen so the unit arithmetic is legible,
and the §2 cross-check holds on them too, including the assertion that a cents
reading of the breakdown is visibly ~100x off. **If that separation ever stops
holding on the fixture, the test says so rather than passing quietly.**

## 6. WHAT THIS DOES NOT ESTABLISH

- **Nothing about a fresh payload.** Every reading is from one ~2-minute window
  on 2026-09-14. A shape held across 72 payloads captured in one session is
  **not a contract**; it is one session. If the venue changes the field, the
  test in §5 is wrong and must be re-derived, not adjusted.
- **Nothing about the other three shards.** The wall reads
  `exchange_index = 1`. The shape holds for all four rows, but nothing here
  says what shards 2 and 3 are for.
- **Nothing about whether the 10% margin the wall keeps is right.** That is a
  question for Joe and it is **#71** — and its premise was already refuted on
  2026-09-18 (the fee is inside the venue's fee-inclusive target), which is why
  it is a question and not a build.
- **Nothing about the 0.65-cent residual** in §2, per §2.
- **Nothing about whether the wall has ever fired.** This measurement is about
  the number it compares against, not about the comparison. No count of
  refusals was taken.
- **It does not establish that the guard would have been wrong.** It establishes
  that it was right on no evidence, and now has some. The ticket said this was
  the good outcome and still worth writing down; it was the good outcome.
