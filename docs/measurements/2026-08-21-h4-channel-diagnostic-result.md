# H4 channel diagnostic — result (2026-08-21)

Registered by Amendment 3 (A17) of
`2026-08-20-preregistration-h4-settlement-fee.md`, committed `9693847` at
**2026-08-21T02:19:10Z**. Analysis code
`scripts/analyze_h4_channel_diagnostic.py`, committed `7c78a32` at
**02:22:28Z** — before the pull, so the numbers could not shape it. Pull
taken **02:49:45Z**, **30m35s** after the amendment's commit, clearing
A17.6's 30-minute rule. This file was audited by the measurement-skeptic
before entering the record (A17.8): the first draft **FAILED** on eleven
prose defects (the arithmetic reproduced exactly, to the SHA), and this
version is the correction — the audit chain is at the foot, kept rather
than erased, per Look 1's precedent. Until the latest audit at the foot
resolves, this file is not part of the record.

**Pull attempt log (A17.6):** exactly one attempt, 02:49:45Z.
`flyctl ssh console -C` exited 1 with the JSON complete on stdout: all
five sections present, well-formed, all `truncated: false`, and section
B's last snapshot (02:47:27.126Z) consistent with a 02:49:45Z pull. No
prior record in this repo documents this exit code, so it is logged here
as an **unexplained non-zero exit with an intact payload**, not as a known
quirk. No re-attempt occurred.

**Raw artifact:** NOT committed — operator account data, per Joe's
2026-08-20 ruling. Held privately at
`data/captures/h4_spans_pull_2026-08-21T024945Z.json` (gitignored),
SHA-256
`b86d23a4b40832a916cf4e63e66da4e32175551fb2bb4cbefa8c207c3e5d51ef`.
Reproduction needs the operator's own pull. The per-winner table below
carries derived position facts (ticker, contracts, settled instant) under
the same tension Look 1's result file flagged for Joe; his ruling there
governs here.

## The verdict, with its denominator in the same sentence (A17.12)

> **BLIND, on a covered-winner denominator of 1.**

No eligible winner returned HIT-WIDE (and therefore none returned
HIT-STRICT), on an eligible-winner count of 1 — the weakest BLIND the rule
admits, and A17.12 requires that weakness stated wherever the verdict is
quoted. Claim D — *some winning settlement's predicted credit appears in
some adjacent balance delta* — is refuted **on this record**: one covered
winner, and 345 scanned adjacent deltas spanning ±24h of it — **of which
339 are exactly zero, leaving 6 non-zero cash movements for the scan to
match against** — produced no match.

What the verdict may and may not be read as, fixed by the audit before
this file entered the record: it may claim that no adjacent balance delta
within ±24h of the record's one covered winner sits within $0.002 of that
winner's $5.00 predicted credit. It may **not** be read as "the
cash-balance channel does not carry payouts" — the next section is why.

## The population, exactly as the query returned it

Sections: A = 13 settlements since study start, B = **783** balance
snapshots (2026-08-18T09:15:03.594Z → 2026-08-21T02:47:27.126Z), C = 16
fills, D = 783 balance polls, E = **35** settlements (whole table). Total
adjacent pairs **782**, of which **773** are COVERAGE-ONLY (contain no
settlement; per A16 they are coverage, never observations, and never vote).

| exclusion | n | note |
|---|---|---|
| D1 (result undefined) | 0 | |
| D2 (loser, predicted credit $0) | 28 | |
| D3 (UNCOVERED) | 6 | all six are pre-study winners settling 08-11 → 08-16, before the balance poller's first snapshot — exactly the population A17.2 said would land here, and not a finding |
| D4 (UNPOLLED) | 0 | every span's polls `ok = 1`, both endpoints non-NULL. D4's poll test is applied on the **closed** interval `[s_j, s_{j+1}]` — an interpretation the analyzer's docstring fixed before the pull and required stated here; it is moot on this pull, since no poll in the record has `ok = 0` |
| ineligible (`contracts <= 0`) | 0 | |

The whole record holds **7 winners ever**; the balance poller shipped with
the study, so the six pre-study winners have no snapshots to be seen in.
The denominator of 1 is a property of when the instrument began, not of
the diagnostic.

## The one covered winner (all registered quantities, A17.4)

| quantity | value |
|---|---|
| settlement | id 177, `KXEARNINGSMENTIONKLAR-26AUG18-WALM`, 5.0 contracts, settled 2026-08-18T14:54:02.349Z |
| predicted credit `P_i` | **5000** tenths ($5.00) |
| containing span | index 70: 14:51:03.990Z → 14:56:04.245Z, balance 15923 → 15923 |
| span `D_j` | **0** |
| span `P_j` / `n_win_j` / `tau_j` | 5000 / 1 / 2 |
| residual `r_j = D_j − P_j` | **−5000** |
| HIT-STRICT | no (`\|D_j − P_j\|` = 5000 against tolerance 2) |
| HIT-WIDE | no — 345 adjacent deltas scanned across ±24h (339 exactly zero, 6 non-zero), none within 2 tenths of 5000; there are therefore no lead/lag lines to print |

This is the same settlement and the same flat stretch Look 1 classified
BANKING-CONTAMINATED and A15 disclosed; the diagnostic re-reads it under a
rule fixed before this pull, over the whole unwindowed record rather than
±900s.

## What section C shows, stated because the verdict does not carry it

Found by the audit's independent reconciliation, recorded here as the
correction of the first draft's one material omission. Every non-zero
delta in the record but two reconciles against contemporaneous fills to
within **0.5 tenth** (`sum(count × price_tenths) + fee_actual × 1000`), so
the channel is demonstrably sensitive to cash movement at this resolution.
The two that do not:

- **Span idx 50** (2026-08-18T13:17:52Z → 13:22:52Z) contains exactly one
  recorded event — a 5.0-count maker fill at 10 tenths on **the winner's
  own ticker**, `fee_actual` 0 — whose own cash effect is bounded at ±50
  tenths. The observed movement is **+4950**, which differs from
  `P_i` = 5000 by exactly that fill's own notional (5.0 × 10 = 50
  tenths) — the whole reason `tau_i = 2` could not see it — landing
  **1h31m10s before** `settled_ms`.
  Under A17.4's registered `tau_i = 2` against the raw delta this is not a
  hit (`|4950 − 5000| = 50`), and the verdict stands as computed. It is
  recorded because it admits two readings the pull cannot separate —
  section C carries no buy/sell action column — **(a)** the position was
  offset at 13:22 and the $5.00 netted to cash then, the channel carrying
  the payout **early** (A11.1's EARLY-CREDIT case); or **(b)** the
  position was closed before settlement, so **no credit was ever due** at
  14:54, the predicted `P_i` is a false prediction, and the effective
  covered-winner denominator is zero — the configuration A17.5 routes to
  UNTESTED, not BLIND. **Neither reading is "the cash-balance channel
  does not carry payouts."** The instrument's blind spot demonstrated
  here: HIT-WIDE compares a raw delta to `P_i` and cannot see a payout
  arriving net of a contemporaneous fill.
- **Span idx 12** (10:07:44Z → 10:12:46Z) moved **−2000** with no fill and
  no settlement inside it: one unexplained $2.00 debit, showing unrecorded
  cash movement is real on this account, not merely conceded as possible.

## The registered caveats, written into the verdict as A17 requires

- **The masking confound (A17.10):** on a denominator of 1, a
  transfer-induced false BLIND requires only **one** event — a withdrawal
  of $5.00 ± $0.002 inside the five-minute span 14:51–14:56Z — not the
  universal coincidence the clause calls implausible at larger
  denominators. Joe's §6.1 answer for exactly this interval is already on
  record as **cannot recall** (`30f1c2e`), and per A13 the question is not
  re-asked. And it is **not the strongest reason to distrust this BLIND on a
  denominator of 1**: the pull itself carries the +4950 movement in the winner's own payout
  window and the unexplained $2.00 debit (both above), which are observed,
  where the masking withdrawal is hypothetical.
- **The ±24h neighbourhood (A18):** a credit landing more than a day from
  its settlement would read as blindness. Fixed before the pull; noted as
  the caveat most likely to overturn a BLIND — this one on a denominator
  of 1.
- **The fused explanations (A18, A11.3, plus one added on this record):**
  this BLIND on a denominator of 1 does not separate "proceeds never
  credited to cash", "credited outside ±24h", "credited to a channel this
  study does not read", and — added on this record rather than in advance
  — "credited to this channel but not within `tau_i` of `P_i`, because a
  same-span fill moved cash too", which is indistinguishable here from
  "the position was closed before settlement, so no credit was due." It
  names the fused state.

## Consequences, enacted exactly as fixed in A17.5

- **Look 2 is written up early as BLOCKED ON INSTRUMENT**, at this
  diagnostic's date (2026-08-21) rather than on 2026-09-03. Per §10 that
  write-up is owed in
  `docs/measurements/2026-08-21-h4-settlement-fee-result.md` (§10's
  `2026-08-2X-…` template), and its absence would be a protocol violation. It is
  written beside this file.
- **Look 3 is cancelled. The H4 look series closes.**
- **The A9–A12 analyzer is never built.** `h4-balance-spans` stays
  shipped but unused (and fed this diagnostic once).
- **ADR 0027's upper-bound caveat stands permanently as worded.**
  `settlement_fee()`'s docstring stays **UNTESTED** — not confirmed, not
  refuted.
- Per A17.11, this BLIND — on a covered-winner denominator of 1 — is
  **terminal for the cash-balance instrument**. It may **not** be
  overturned by a later look at the same channel, a wider horizon, a
  faster poll cadence, a re-run of `h4-balance-spans`, a re-reading of
  the same pull, a new analyzer over the same rows, more settlements
  accumulating, or any argument about what the record "would show with
  more data". It may be overturned by exactly one thing: a further dated
  amendment shipping a new instrument on a **different channel**, which
  (a) names the channel, (b) states why that channel carries settlement
  proceeds where the balance channel does not, (c) ships its query with
  mutation-verified guards **before** any pull, and (d) registers its own
  decision rule with both consequences fixed. The three candidate
  channels A17.11 named: a settlement-time endpoint reporting proceeds
  directly; `portfolio_value` after its unit is pinned
  (`backend/portfolio_poll.py:252-266`); a venue-issued transaction
  ledger or statement. **BLIND is not a verdict about the venue.**
  Nothing here is evidence that any of the three candidate channels
  carries settlement proceeds; A17.11 (b) requires a future amendment to
  establish that, and this diagnostic does not.

## What this does not establish

- **Nothing about H4 and nothing about Kalshi.** A17 tested the
  instrument. Whether settlement carries its own fee is exactly as
  untested as it was on 2026-08-20, and per §6 (carried into A17.5) the
  words "zero", "no settlement fee" and "H4 confirmed" may not be used of
  this result — they are quoted here only as the prohibition.
- **No standard error and no p-value attach to an existential over an
  enumerated record** (A17.3), and none appears here.
- **A BLIND on 1 covered winner is the weakest statement the rule can
  emit**, and on this record its own pull carries a movement its
  tolerance could not credit, on either of the two readings the pull
  cannot separate. It closes the series because A17.5
  fixed that consequence before the pull — not because the evidence is
  strong, and the write-up says so in the verdict sentence itself.

## Audit record (A17.8)

- **Audit 1 (measurement-skeptic, 2026-08-21): FAILED**, eleven defects,
  all prose — every re-derived quantity, the SHA-256, and the A17.6
  timing chain reproduced exactly. The material finding was the first
  draft's omission of the section C reconciliation (the +4950 movement in
  the winner's own payout window and the unexplained −2000), which made
  BLIND read stronger than the record supports; the remaining defects:
  the 345-delta count presented without its 339 zeros, the incomplete
  fused-explanation list, the mis-billed strongest masking threat, three
  denominator-rule breaches (A17.12), the unstated D4 closed-interval
  interpretation, a header asserting a completed audit while the foot
  said PENDING, an undocumented "known quirk" claim in the attempt log,
  "closed early" where A17.5 says "written up early" (and the §10
  write-up obligation unstated), a sign inconsistency in the winner
  table, and an A17.11 restatement that dropped conditions (c), (d) and
  the negative list. All eleven are corrected in this version.
- **Audit 2 (measurement-skeptic, 2026-08-21): FAILED**, nine defects
  (ten of the eleven Audit 1 corrections verified fully discharged, the
  eleventh — the header — only partially; three of the nine lay inside
  corrected text rather than around it; every number re-verified): three
  material — two false factual assertions in the
  Look 2 write-up ("every fill" where the record reconciles 15 of 16;
  "equal to that payout" for a +4950 that misses `P_i` by the fill's own
  50-tenth notional) and a false blinding claim ("before any of this
  data existed", of an amendment written after Look 1's residuals were
  seen) — plus an unsupported forward claim appended to the A17.5
  section, one new A17.12 breach, a header out-running the PENDING foot,
  and three minors (a presumed fill sign, a dangling template marker, a
  sentence picking reading (a)). All nine are corrected in this version.
- **Audit 3 (measurement-skeptic, 2026-08-21): PASSED.** All nine
  Audit 2 defects discharged and every quantity re-derived independently
  from the pull for a third time — 782 adjacent pairs, 773 COVERAGE-ONLY,
  D1–D4 = 0/28/6/0, 7 winners ever, denominator 1, `P_i` 5000, span 70
  `D_j` 0, `r_j` −5000, 345 deltas scanned of which 339 are zero, idx 50
  `+4950`, idx 12 `−2000`, SHA-256 unchanged — with Look 1's pull
  independently confirming the `2026-08-20T04:20:39.418Z` read extent
  the Look 2 write-up cites. Two residual defects were raised and
  corrected in this version: the Audit 2 foot bullet overstated the
  Audit 1 corrections as fully discharged when one was partial, and the
  Look 2 write-up called the predicted credit a "payout". **The verdict
  BLIND, on a covered-winner denominator of 1, is within what was
  measured; it does not extend to any claim about H4, about Kalshi, or
  about whether the cash-balance channel carries payouts, and the record
  now carries the section C reconciliation that is the reason for that
  last limit.**
