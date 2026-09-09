# ADR 0121 — An independent dependency audit, because dependabot is permanently blind to `cryptography` on this repo

Status: accepted
Date: 2026-09-09

Closes the monitoring half of `tasks/NEXT.md` open item 3. The bump half stays
open and is Joe-gated. Amends nothing in ADR 0117; see that ADR's Amendment 2
for the correction this step produced.

## Context

ADR 0117 found two critical unauthenticated RCEs live on the public money box,
which nothing had surfaced until a routine push happened to trigger a rescan.
Chasing that, it found something worse than a stale alert.

**Alert #15 reports `cryptography` as `fixed` while `requirements.txt:9` still
pins `cryptography~=44.0`, resolving to 44.0.3, squarely inside the advisory's
vulnerable range.** The cause is not a scan lag: **GitHub's dependency graph
holds no resolved version for the package.** The SBOM carries two
`cryptography` entries and both have an empty `versionInfo`, and an advisory
cannot match a node with no version.

That distinction decides everything here. A stale alert self-corrects on the
next scan. **A package with no resolved version never matches an advisory
again** — including advisories not yet published. So `cryptography` is
invisible to dependabot on this repo permanently, and the session-start
dependabot query in `tasks/NEXT.md` cannot catch the next one.

The repo is public and the live instance holds real money. Watching alerts
more carefully was never going to fix this; only an instrument that does not
share dependabot's blind spot can.

## Decision

**A blocking `pip-audit` step runs in CI on every push, against
`requirements.txt`.**

- `--strict`, so a failure to *collect* a dependency is red rather than
  silently skipped. That is the identical failure mode dependabot is stuck in:
  a package nothing can resolve is a package no advisory can ever match.
- No `continue-on-error`, no `|| true`. A guard that cannot fail is not a
  guard.
- Placed before the lint and the suite, so a vulnerable dependency fails in
  about a minute rather than after the 15-minute cap.

**It audits `requirements.txt` and only that file**, because the Dockerfile's
stage 2 installs that file alone — it is the ship/no-ship boundary, and
anything the step reports is live exposure. Dev dependencies are out on
purpose: they cannot reach the live instance, `requirements-dev.txt` opens
with `-r requirements.txt` so auditing it re-reports every shipping finding
with nothing marking which is which, and a gate that blocks a real-money
deploy on a pytest CVE stops being a signal. Measured rather than assumed: the
dev-only surface is exactly one finding, pytest 8.4.2 / PYSEC-2026-1845, fixed
in 9.0.3, recorded here so it is not lost.

### The step is installed GREEN at rest, with every current advisory ignored by ID

This is the part that took a decision, because two of the repo's own rules
pull opposite ways:

- *A guard that cannot fail is not a guard* — hence no `continue-on-error`.
- *A check that is always red is not a check* — `ci.yml`'s own header, paid
  for with **36 consecutive red pushes** where nobody could tell the run that
  found a real key from the ones that found a comment about one.

The brief anticipated one advisory. **Nine findings fired, across seven
distinct advisories and two shipping packages.** Committing that red would
have recreated the 36-push scar exactly, and a red-at-rest gate is the worse
failure, because it teaches people to ignore the gate.

**A per-ID ignore list resolves both.** The step is green at rest and red on
anything new — which is the entire reason it exists. Each ignore is its own
flag with its own comment giving the ID, its aliases, what it is, the version
that fixes it, and why it is deferred. Never a wildcard, never a severity
floor. The header states that the list is **a record of open decisions, not a
suppression**, and that an entry is deleted the moment its bump lands.

Ignoring by ID also means a *new* advisory is not silenced — only these seven
are.

### The ignores, in two kinds that must not be confused

**Deferred fixes (5), all `cryptography`** — `GHSA-jwv3-5hgf-82ww` (alert
#15's advisory), `GHSA-m959-cc7f-wv43`, `GHSA-r6ph-v2qm-q3c2`,
`GHSA-g6cj-pr64-35w5`, `GHSA-537c-gmf6-5ccf`. The installed version really is
vulnerable and the bump is genuinely wanted.

It was considered and **rejected** to reclassify four of these as unreachable.
`cryptography` is used in exactly one place — `backend/kalshi/auth.py`,
`load_pem_private_key` plus `sign(PSS(MGF1(SHA256)))` — with no X.509
verification, no PKCS#7 and no EC public-key loading, so on a strict
call-path reading four are unreached *today*. They stay classified as deferred
fixes anyway: future code reaches what today's code does not, `GHSA-537c` is
the statically linked OpenSSL underlying every primitive we *do* call, and
collapsing them into "known-bad match" would make the record read as "nothing
to do here", which is false. Reachability is recorded as a separate sentence
rather than as the classification.

**Known-bad matches (2), verified rather than assumed** — these are not
deferred fixes and are labelled distinctly:

- `GHSA-m2h6-j472-rp4c` / PYSEC-2026-3554 **does not apply to 44.0.3.**
  GitHub's reviewed record says `introduced 45.0.0`, enumerating 19 affected
  versions, none of them 44.x. The mirrored PYSEC record lost the lower bound
  (`introduced: 0`, 156 versions) and pip-audit takes the union. Re-evaluate
  the moment the pin reaches 45.x, at which point it becomes a real deferred
  fix.
- `pyarrow` `GHSA-rgxp-2hwp-jwgg` — the version range matches the 19.0.1 pin,
  but the advisory needs an Arrow **IPC file** read with pre-buffering, and a
  tree-wide search for `pyarrow.ipc`, `feather`, `RecordBatchFileReader`,
  `RecordBatchStreamReader`, `open_file`, `open_stream` and `pre_buffer`
  returns nothing outside `.venv`. The only pyarrow call touching a file is
  `pq.write_table` in `backend/store/publish.py:158` — a Parquet *write*.
  Re-evaluate if anything starts reading `.arrow` / `.feather`.

### The list is pinned by a test, so it cannot grow quietly

`TestThePipAuditIgnoreListIsPinned` (`tests/test_marts.py`, which already held
the one existing `ci.yml`-reading harness) asserts the exact ignore set, that
the step cannot be made non-blocking, that it audits the file the Dockerfile
installs, and that it runs before the suite.

The point is not the assertion, it is the friction: adding an eighth ignore
now requires editing a test that says out loud what is being silenced, which
makes it a deliberate act rather than the path of least resistance when CI
goes red at an awkward hour.

Verified by mutation: adding a fake eighth ID reddens the pin test by name
(`Extra items in the left set: 'GHSA-fake-sneaky-0000'`); adding
`continue-on-error: true` reddens the non-blocking test. Both revert clean.

## Consequences

The exact step, run verbatim: **`No known vulnerabilities found, 9 ignored`,
exit 0.** Nine rows through seven IDs — the extra two are duplicate OSV
records (a GHSA and its mirrored PYSEC entry) for advisories already listed.
About 60 seconds, ahead of a 15-minute cap.

**Its first run already earned it.** Dependabot showed one advisory; this
shows seven, and among them the finding that changes a decision already on the
record: `GHSA-g6cj-pr64-35w5` was introduced at 44.0.0 and is **not fixed
until 50.0.0**, so the deferred bump is **44 → 50, six majors across the
RSA-PSS request signer** — not the 44 → 49 / five majors written in ADR 0117
and `tasks/NEXT.md`. Stopping at 49.0.0 clears alert #15 and leaves a PKCS#7
decrypt oracle standing. Corrected in ADR 0117 Amendment 2.

Six of the seven are `cryptography` and one is `pyarrow`; the comment says so,
because five are on the signing path and one is the Parquet publish step, and
a reader hitting a red build at 2am needs that distinction in front of them.

## What this does not decide

- **The bump itself.** Still deferred, still Joe-gated: six majors on the code
  that signs real-money orders is a change to take with a human watching. It
  is now safer to take — `tests/test_auth_signature_roundtrip.py` verifies the
  signature by round-trip against 17 mutations of the signer, where the prior
  coverage asserted only that the header was non-empty and survived 16 of the
  17.
- **Why the dependency graph lost `cryptography`'s version.** The symptom is
  worked around, not cured; the SBOM entries are still empty. If they ever
  resolve, dependabot starts reporting these too, and the ignore list here is
  unaffected.
