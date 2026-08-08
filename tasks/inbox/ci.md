# CI lane report

Branch `lane/ci`, three commits (one per task), on top of `main` @ `a4f2c2c`.

**Note on base commit:** this worktree was created at `93e9201`, before the
prior `lane/ci` secret-scan repair (`491e194`) and the in-play research merge
(`0a6ec99`, `4b5ae44`) landed on `main`. `tasks/NEXT.md`'s "Three CI
follow-ups" item and the lessons.md entry named in the brief only exist from
`a4f2c2c` onward, so I re-pointed this branch at current local `main` before
starting (`git switch -c lane/ci main`) rather than working from the stale
base. Local `main` is itself 8 commits ahead of `origin/main` — nothing here
was pushed, but the integrator should know `origin/main` is behind whatever
`main` looks like on the machine doing the merge.

## Task 1 — `.gitignore` vs the CI secret scan (commit `198e89f`)

CI's tracked-key-file check (`.github/workflows/ci.yml`, "Project-specific
checks" step) refuses extensions `pem|key|p8|pkcs8|pfx|p12` (case-insensitive).
`.gitignore` only blocked `pem|key|p8|pfx`. **Two** extensions were missing,
not the one named in the brief: `.p12` (named) and `.pkcs8` (found while
reconciling the full list). Added both.

Verified by attempting `git add` on dummy `.p12` and `.pkcs8` files:
```
git add zz_dummy.p12    -> "ignored by one of your .gitignore files", exit 1
git add zz_dummy.pkcs8  -> "ignored by one of your .gitignore files", exit 1
```
Both now refuse exactly like `.pfx` already did. Dummy files removed before
committing.

**Residual gap, not fixed:** CI's grep is case-insensitive (`grep -Ei`);
`.gitignore` patterns are case-sensitive on the Ubuntu runner's filesystem. A
file named `KEY.PEM` would be caught by CI but not blocked by `.gitignore` at
`git add` time. Fixing this needs either every case permutation listed
explicitly (impractical) or `core.ignorecase` (a git config change, out of
scope per CLAUDE.md). Noting it rather than acting on it since it's a
single-user repo and an unforced-error scenario, not an adversarial one.

## Task 2 — the `ruff` decision (commit `b3279dd`)

**Decision: wired, not dropped.** Added `ruff.toml` at repo root and a
"Lint (ruff)" step in the `test` job of `ci.yml`, run right after `Install`.

**Measured numbers** (ruff 0.16.1, resolved from the existing `ruff~=0.9` pin —
see gotcha below):

| Selection | Rules enabled | Findings today |
|---|---|---|
| Ruff's own current default (`ruff check . --isolated`, no config file anywhere) | 413 | 513, across 30 rule codes |
| Chosen baseline before exclusions (`select = ["E4","E7","E9","F"]`) | 59 | 32, across 4 rule codes |
| Chosen baseline after exclusions (what's wired) | 55 | **0** |

Excluded rule codes and why (all violations are in `backend/**`, `scripts/**`
or `tests/**`, none of which this lane may edit):
- `F401` unused-import — 25 violations
- `F841` unused-variable — 2 violations
- `F541` f-string-missing-placeholders — 1 violation
- `E741` ambiguous-variable-name — 4 violations (`backend/api/routes.py`,
  `scripts/demo_builder.py`)

**Gotcha worth flagging:** `ruff~=0.9` does not mean "0.9.x". PEP 440's
compatible-release operator strips only the last version segment, so
`~=0.9` means `>=0.9, ==0.*` — it floats across every 0.x release ruff has
ever shipped. It resolves to 0.16.1/0.16.2 today. Ruff's own "default"
ruleset has also grown substantially since the historical `E4,E7,E9,F`
(413 rules now, confirmed with `--isolated` so it isn't a stray config file
on this machine). I did not tighten the pin — not asked, and low risk since
new rules always get new codes rather than silently joining `F`/`E7`/etc. —
but the integrator should know the "ruleset" a plain `pip install
ruff~=0.9` gives today is not what that pin historically implied.

**Verification, exact commands and exit codes** (run from the worktree root
with the venv at `..\..\..\..\.venv\Scripts\python.exe`, which is what CI's
`ruff check .` resolves to after `pip install -r requirements-dev.txt`):

```
$ python -m ruff check .
All checks passed!
$ echo $?
0
```

Planted a canary (`zz_ruff_canary.py`, at repo root, never committed):
```python
def canary():
    return undefined_name_that_does_not_exist
```
```
$ python -m ruff check .
F821 Undefined name `undefined_name_that_does_not_exist`
 --> zz_ruff_canary.py:2:12
Found 1 error.
$ echo $?
1
```
Removed the canary, re-ran:
```
$ python -m ruff check .
All checks passed!
$ echo $?
0
```
`F821` (undefined-name) is not one of the 4 excluded codes, so this proves the
selected ruleset still catches real bugs, not just decoration.

## Task 3 — Node 20 deprecation (commit `1420fe5`)

Bumped via `gh release list` / `gh api .../action.yml` against each action's
own repo (not guessed):

| Action | Was | Now | Confirmed `node24` at that tag |
|---|---|---|---|
| `actions/checkout` | v4 (node20) | v7 (v7.0.1) | yes |
| `actions/setup-python` | v5 (node20) | v7 (v7.0.0) | yes |
| `actions/setup-node` | v4 (node20) | v7 (v7.0.0) | yes |
| `gitleaks/gitleaks-action` | v2 (node20) | v3 (v3.0.0) | yes |

Bumped `checkout@v4` everywhere it appears, including `deploy.yml` (not just
`ci.yml`) — leaving it on v4 there would still emit the deprecation warning on
every deploy run. `ops.yml` and `secrets.yml` don't use `checkout` at all
(only `superfly/flyctl-actions/setup-flyctl@master`, out of scope — not in the
brief's action list, and it isn't version-pinned to begin with).

Inputs checked against each action's release notes for breaking changes:

- **checkout**: only breaking change across v5→v7 is a v6.1/v7 change to
  default checkout behaviour for `pull_request_target`/`workflow_run` forks
  (github.blog/changelog/2026-06-18). This repo's workflows trigger on
  `push`, `pull_request`, and `workflow_dispatch` only — never
  `pull_request_target` or `workflow_run` — so it doesn't apply. Checked: no
  inputs beyond the implicit default, plus `fetch-depth: 0` in the secrets
  job (unaffected).
- **setup-python**: v6.0.0's breaking change *is* the node24 migration
  itself. v7.0.0 removed the `pip-install` input — this repo never sets it.
  Checked: `python-version: "3.11"`, `cache: pip` — both untouched by any
  release between v5 and v7.
- **setup-node**: v5.0.0 and v6.0.0's breaking changes are about *automatic*
  caching triggered by a `packageManager` field in `package.json`.
  `frontend/package.json` has no such field, so this is a no-op here.
  Checked: `node-version: "22"`, `cache: npm`,
  `cache-dependency-path: frontend/package-lock.json` — all untouched.
- **gitleaks-action**: v3.0.0 release notes state explicitly: "No changes to
  inputs, outputs, or behavior." Checked: only `GITHUB_TOKEN` env is set,
  untouched.

**Timing context found during research, not previously called out anywhere
in this repo:** GitHub flipped hosted runners to Node 24 by default on
2026-06-02 — node20-declared actions now need
`ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true` to run at all — and removes
Node 20 outright on 2026-09-16. Today is 2026-08-07/08. This is not purely
cosmetic; the old pins may already be degraded and have roughly five weeks
left before they stop working entirely regardless.

**Unverified until pushed**, stated plainly per the brief: an Action cannot
run locally, and this lane does not push. What the integrator should watch on
the first push:
1. All four jobs (`Tests + warehouse`, `Frontend`, `Secret scan`, `Deploy`)
   start at all — no "this run references an action that's no longer
   supported" or unsupported-runner failures.
2. The secret scan step's own canaries still fire (see the finding below —
   there's a reason to look closely at this job specifically).
3. `Frontend`'s `npm ci` cache-restore step still resolves — setup-node's
   caching internals changed materially across v5/v6 even though the inputs
   this repo passes didn't.
4. `gitleaks` step reports the same behavior as before (should be a no-op
   per its own release notes, but it's the security-critical one).

## Found and could not own: the secret scan is currently red on `main`

Not one of the three tasks — found incidentally while extract-and-running the
secret scan to verify task 1 didn't disturb it (same method the prior
`lane/ci` session used, per the brief).

**The final, unconditional `git grep` step in the "Project-specific checks"
job (`ci.yml`, no path exclusions by design) currently fails on
`tasks/lessons.md:1821`:**
```
tasks/lessons.md:1821:KEY = """-----BEGIN RSA PRIVATE KEY-----
```
This is the lesson's own illustrative example of the "quoted" shape the scan
was built to catch (a key pasted right after an opening triple-quote) — it's
not a real key, but it reproduces the exact trigger byte-for-byte, and the
lesson entry that describes this incident is not exempted anywhere.

Verified by extracting the step's shell into a standalone script and running
it under bash: exit 1, with the above as the only tree-wide match (the
`own_line`/`inline`/`quoted` canaries all pass; I mistyped my first
transcription of the script — a single `\n` instead of the real step's `\\n`
— which produced a false canary failure on my end, fixed, and the remaining
failure is real and reproducible).

**Why I didn't fix it myself:** I considered adding `tasks/lessons.md` to the
existing `for legit in docker/entrypoint.sh tests/test_logging_redaction.py`
loop, since `ci.yml` is in my lane. That loop is *not* an exclusion
mechanism, though — it's a regression assertion that those files' content
should **not** match the patterns (there is deliberately no path-exclusion in
this design; see the comments immediately above it). Adding
`tasks/lessons.md` there would just make that assertion fail too, with the
same message, because its content genuinely does match. The only fixes I can
see are:
1. Reword the line in `tasks/lessons.md` so it doesn't reproduce the exact
   trigger shape (e.g. break the line, or use a placeholder) — requires
   editing `tasks/lessons.md`, which is forbidden to me.
2. Add a real path-based exclusion for that one file to the final `git grep`
   step — technically in my lane, but it directly reverses the design
   decision the immediately-preceding commit made on purpose ("There is no
   path exclusion any more... it made a key pasted into
   `warehouse/profiles.yml` unscannable"), and reopens the same class of
   blind spot for a file that will keep growing with hand-written incident
   narratives. That's a security-posture call, not a plumbing fix, and I
   don't think it's mine to make unilaterally.

Flagging this as the most urgent item in this report: **CI is red on `main`
right now**, independent of anything in this branch, for the exact class of
reason the lesson two commits ago is about.

## Verification summary

```
python -m ruff check .                          -> "All checks passed!"   exit 0
pytest -q (1139 tests, whole worktree)           -> 1139 passed            exit 0
git add zz_dummy.p12 / zz_dummy.pkcs8            -> refused by .gitignore  exit 1 (expected)
secret-scan extract-and-run (corrected script)   -> fails on tasks/lessons.md:1821, exit 1 (pre-existing, not mine)
```

## Needed and could not own

- `tasks/lessons.md` — the false-positive above lives here; I can name the
  fix but not make it.
- `tasks/NEXT.md` — would normally check this item off; leaving that to the
  integrator.
