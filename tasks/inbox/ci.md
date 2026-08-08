# Inbox — ci lane

Lane: `.github/workflows/**`. Branch `lane/ci`.

## The checklist item was wrong in both directions

`tasks/NEXT.md` section 3 lists **"GitHub Actions — tests, `dbt build`, and
secret scanning on push"** as unbuilt. It was built in the first commit
(`330fe04`), and two of its three legs have been green from the start:

| Job | State before this branch |
|---|---|
| Tests + warehouse | green — pytest on 3.11, both requirements files, then `seed_demo` → `publish` → `dbt build` |
| Frontend | green — `npm ci` + `next build`, node 22 |
| Secret scan | **red on 36 consecutive pushes** |

So the item should be ticked, with the secret scan's repair noted — not built
from scratch.

## What was actually broken

The secret scan's `Project-specific checks` step grepped for the *phrase*:

    git grep -nE 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' -- . ':!*.yml'

Two files legitimately contain it, and both exist *because* of key hygiene:

- `docker/entrypoint.sh:94` — validating that the decoded key is an RSA PEM and
  not OpenSSH format.
- `tests/test_logging_redaction.py:89` — proving the redactor strips a PEM block
  out of a log line.

CI went red on the push that added the first of those (`1d238c2`, 2026-08-07
19:17Z) and stayed red for every push since. **A check that is always red is
not a check**: the run that finds a real key looks exactly like the 36 that
found a comment about one, and red becomes CI's resting state rather than a
signal. Every one of those 36 runs had a green test job and a green frontend
job underneath a red overall result, so the whole workflow's verdict had
stopped carrying information.

The `:!*.yml` exclusion existed only to stop the workflow matching its own
pattern, and it cost more than it saved: a key pasted into
`warehouse/profiles.yml` — a file whose job is to hold a connection — was
unscannable.

## What replaced it

Match key *material*, not the words for it. Two patterns:

    own_line  ^[[:space:]]*-----BEGIN( [A-Z0-9]+)* PRIVATE KEY-----[[:space:]]*$
    inline    -----BEGIN( [A-Z0-9]+)* PRIVATE KEY-----[^A-Za-z0-9+/]{0,4}[A-Za-z0-9+/]{40,}

A header standing alone on its line is a key pasted verbatim, at any
indentation. A header followed immediately by a base64 body is the `.env`/JSON
escaped form. A header quoted inside source with nothing after it is a program
*talking about* a key, and matches neither. The path exclusion is gone, and the
extension check now also refuses `.pfx`/`.p12`.

It also covers three header forms the old pattern did not: bare PKCS#8
(`BEGIN PRIVATE KEY`), `ENCRYPTED`, and `DSA`.

**The step now proves its own patterns before trusting them.** It writes three
canaries to a temp dir — a pasted key, an escaped key, and a quoted header,
with a random base64 body, never a real key — and fails if the first two are
not matched or the third is. A regex that has quietly stopped matching anything
passes the real check forever and is indistinguishable from a clean repo; that
is the same failure as the 36 red pushes, pointing the other way. It earned its
place on the first local run by catching a real bug in the new step: `grep`
read `-----BEGIN…` as a bundle of options, so `-e` is now used throughout.

Stated in the step, because it is a limit and not a bug: this reads the tree at
HEAD, so a key committed and later deleted is invisible to it, and gitleaks is
scoped to the push. Neither net scans history. If a key is ever suspected,
rotate first and run `gitleaks detect --log-opts=--all` by hand second.

## Defects found outside this lane — recorded, not fixed

1. **`.gitignore` ignores `*.pfx` and says nothing about `*.p12`.** A PKCS#12
   bundle is a private key in a container; `git add secrets.p12` succeeds today
   with no warning. CI now refuses it, but the two files should agree.
   (`.gitignore` is not in the ci lane.)

2. **`ruff~=0.9` is a declared dev dependency that nothing configures and
   nothing runs.** There is no `pyproject.toml` and no `ruff.toml` anywhere, so
   `ruff check .` runs the default ruleset and reports **491 findings** (420
   auto-fixable). This is the `built but never called` pattern again. I
   deliberately did **not** add a lint job: it would be red on the first push,
   which is the failure this task was set to remove, not add. Either pick a
   ruleset and wire it up, or drop the dependency — a linter in
   `requirements-dev.txt` that no one runs reads as a repo that lints.

3. **Node 20 deprecation warnings** on `actions/checkout@v4`,
   `actions/setup-python@v5`, `actions/setup-node@v4` and
   `gitleaks/gitleaks-action@v2` — all forced onto Node 24 by the runner. A
   warning today, a breakage whenever GitHub finishes the migration. I did not
   bump them: a GitHub Action cannot be executed locally, so the bump would be
   exactly the unverified workflow change this task exists to avoid. It needs
   one throwaway push to a branch to verify, which is a two-minute job for
   whoever is next at a terminal.

4. **gitleaks never scans history or the tree — only the commits in the push.**
   Observed command line from run `31242612673`:
   `gitleaks detect --redact -v --exit-code=2 … --log-opts=-1`, reporting
   `1 commits scanned … ~1303 bytes`. That is correct behaviour for a
   single-commit push and it is worth knowing when someone asks "has this repo
   ever leaked?" — the answer is not in CI. The project-specific step is the
   only thing that looks at the whole tree, which is most of its justification.

## Lesson, for `tasks/lessons.md`

**A secret scanner that matches the name of a secret rather than the material
fires on the files that exist because of good hygiene.** The format validator
and the redaction test both have to contain the header they defend against; a
grep for the phrase cannot tell them from a leak. Match the shape money takes,
not the word for it — and give the check a canary, so "found nothing" and
"cannot find anything" stop looking the same.

**Corollary, and the more expensive half:** a guard that fails on every run has
the same information content as a guard that passes on every run. 36 red CI
runs sat under commits that were individually fine, and the two jobs that would
have caught a real regression were green underneath a red verdict nobody could
read.
