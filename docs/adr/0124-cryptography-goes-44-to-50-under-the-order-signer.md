# ADR 0124 — `cryptography` goes 44 → 50 under the order signer, and the ignore list drops from seven to one

Status: accepted
Date: 2026-09-09

Closes the bump half of `tasks/NEXT.md` open item 3, open since 2026-09-09
(ADR 0117). The monitoring half was closed by ADR 0121, which is what made this
decision possible to take correctly.

## Context

`cryptography` performs the RSA-PSS signing that authenticates every order the
cockpit sends to Kalshi. `requirements.txt` marks it *"Not optional, not
swappable."* The pin was `~=44.0`, resolving to 44.0.3.

Three things had to be true before this could be taken, and by 2026-09-09 all
three were:

1. **The real size of the change had to be known.** ADR 0117 recorded it as
   "five majors, fixed in 49.0.0" — the fix version for dependabot alert #15's
   advisory alone. That was wrong, and wrong in the direction of understating
   it. `GHSA-g6cj-pr64-35w5` (PYSEC-2026-3552, CVE-2026-69247, a PKCS#7 decrypt
   oracle) was **introduced at 44.0.0 and is not fixed until 50.0.0**, so
   stopping at 49 would have cleared the alert everyone was watching and left
   that one standing. ADR 0117 Amendment 2 corrects the record.

2. **An instrument that could see all of it.** Dependabot is permanently blind
   to this package here — its dependency graph holds no resolved version, so no
   advisory can match (ADR 0117). It showed **one** advisory. The `pip-audit`
   gate installed by ADR 0121 showed **six**, and found the 50.0.0 requirement
   on its first run.

3. **A test on the signer that can actually fail.** Until 2026-09-09 the only
   coverage asserted the signature header was *truthy* — it survived 16 of 17
   mutations of the signing code. `tests/test_auth_signature_roundtrip.py` now
   verifies by round-trip and each of 17 mutations reddens it.

**Joe was asked and said yes, with the condition that he be at a screen.** He
was, and the work was done in front of him.

## Decision

**`cryptography~=50.0`**, resolving to 50.0.1.

**And the pip-audit ignore list drops from seven entries to one**, because six
of the seven were this package. They are *gone*, not silenced: `pip-audit -r
requirements.txt --strict` with **no ignores at all** now reports exactly one
finding. Deleting an ignore the moment its bump lands is the rule that list was
written under; this is the first time that rule has been exercised.

The single remaining entry is `pyarrow` `GHSA-rgxp-2hwp-jwgg`, a **known-bad
match** rather than a deferred fix: the flaw needs an Arrow **IPC file** read
with pre-buffering, and nothing in this repo ever reads one — the only pyarrow
call touching a file is `pq.write_table`, a Parquet *write*.

## How it was verified

Test suites passing is necessary and was never going to be sufficient here,
because **every test in this repo signs and verifies within a single version**.
That cannot detect the failure that actually matters: the library changing what
it puts on the wire, which Kalshi would reject as a 401 that looks exactly like
bad credentials.

So the decisive check was **cross-version**:

    sign a fixed message with a throwaway key under 44.0.3
    -> upgrade to 50.0.1
    -> verify that same signature under 50.0.1

| check | result |
|---|---|
| a 44.0.3 signature verifies under 50.0.1 | **PASS** |
| a fresh 50.0.1 signature verifies under 50.0.1 | **PASS**, 256 bytes |
| a *different* message is rejected | **PASS** — the verifier is live, not rubber-stamping |

The third row is the one that makes the first two mean anything; without it a
verifier that accepted everything would have reported success. The real Kalshi
key was never read — the key is generated in the check and thrown away.

Then, in order: 77 signing tests green under 44.0.3 before the bump; 142 tests
across the signing, REST, WebSocket and log-redaction paths green under 50.0.1
after it; `pip check` reports no broken requirements; `ruff` clean; the full
suite green.

## Consequences

- `requirements.txt:9` — the pin, with the reasoning inline: seven advisories
  not one, 50 not 49 and why, and the cross-version check.
- `.github/workflows/ci.yml` — six ignores deleted, the header rewritten from
  "the bump is 44 → 50" (a pending decision) to "the bump is done" (history).
- `tests/test_marts.py` — `TestThePipAuditIgnoreListIsPinned` updated. **It
  went red on the change, by name, before it was updated**, which is the whole
  point of pinning the list: the shrink was noticed rather than assumed.

### What the sequence demonstrates, and it is the reusable part

The instrument was built **before** the decision it informed, and it changed
the decision. Had the bump been taken on 2026-09-08 with dependabot as the
only instrument, it would have gone to 49.0.0, closed the visible alert, left a
decrypt oracle in place, and looked completely successful. **The gate that
"only" reported known-unfixable advisories paid for itself on its first run**
by making the target version correct.

## What this does not decide

- **`pyarrow` 19.0.1 → 23.0.1.** Four majors on the Parquet publish path, on an
  advisory established as unreachable here. It touches no money path and has
  its own owner; not smuggled in behind a security bump, which is the mistake
  ADR 0117 explicitly refused to make in the other direction.
- **Whether the deployed instance runs this yet.** The pin is a repo change;
  live still runs the image built from the previous one until a deploy. Read
  the version out of the container, not the deploy output — that is how the
  `next`/`sharp` fixes were confirmed (ADR 0117) and it is the only check that
  has ever been trusted here.
- **Anything about `cryptography`'s other APIs.** This repo uses exactly
  `load_pem_private_key` and `sign(PSS(MGF1(SHA256)))`. Six of the seven
  advisories were in X.509, PKCS#7 and EC paths this code never touches, which
  is why the bump was safe to defer at all — and is not a reason to defer the
  next one.
