# Start prompt — paste this to open the next session

Written 2026-08-10. The session that landed ADR 0019, **found the reported bug
was misdiagnosed**, and watched a pre-registration stop itself on the guard the
joint bound was missing.

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read `CLAUDE.md`, `tasks/NEXT.md` and `tasks/lessons.md` first. NEXT.md is the
actionable checklist; `todo.md` is just the build log. **The top section of
NEXT.md supersedes everything below it.**

## THE REPO IS PUBLIC NOW — this changes what you may commit

Done in a parallel session on 2026-08-10, after a full-history secret audit
(gitleaks over `--all`, plus GitHub's own scan of the full history: **0
alerts**).

- **Every push publishes to the world immediately.** Before committing a
  measurement, fixture, log capture or screenshot, ask whether it should be
  world-readable. **Screenshots of the live UI are the sharp edge** — one live
  run away from showing a real position or bankroll. `.tmp_*` is now gitignored
  so probe and screenshot scratch output is no longer committable.
- **Push protection is ON.** A push containing anything credential-shaped is
  **rejected by GitHub**. That is the guard working. Do **not** bypass it —
  stop, look at what tripped, and rotate if it is real.
- **CI cancels superseded runs.** If you push twice quickly and the earlier run
  shows `cancelled`, that is `ci.yml`'s `concurrency` block doing its job. **Not
  a failure, not something to debug.** Judge CI by the run on your latest SHA.
- Public repos get unlimited Actions minutes, so the billing pressure that drove
  the CI caps is gone. The caps stay — they are a runaway backstop, not a cost
  measure.

## State

`main` is at the tip, pushed, in sync. **1,911 tests**, ruff clean, `next build`
clean. **Everything from the last two sessions is committed and UNDEPLOYED** —
live is unchanged.

**The undeployed set now includes a security patch, so "deploy whenever" is no
longer the right framing.** Dependabot surfaced a Next.js *middleware / proxy
bypass in App Router*; `frontend/package.json` is bumped 16.2.10 → 16.2.11 and
committed. Live still runs the vulnerable version.

State the blast radius accurately rather than either dismissing or inflating it:
`frontend/src/middleware.ts` **does** guard `/api/*` (reachable through
`next.config.ts` rewrites), so the bypass is not cosmetic — but the FastAPI
backend returns 401 on those routes **independently**, which is the control
CLAUDE.md actually relies on and which was verified directly on live. So this is
defence in depth with the **outer** layer down, not an open door. Deploying
closes it.

Three Dependabot alerts were deliberately **not** taken (a `postcss` and a
`sharp` pinned inside next's own tree, needing `next@16.3.0`). Both were shown
unreachable here — there is no `<Image>` in `src/` and the build consumes only
our own CSS. Do not "finish the job" by taking an untested minor bump on the
frontend of a real-money instance.

**You can read the live record programmatically.** The live `APP_AUTH_TOKEN` is
on the `APP_AUTH_TOKEN=` line of `.env` (gitignored). Form-POST `token` to
`/session`, keep the cookie, then GET. A whole-table pull is: read `newest_id`
from page 0, pass it back as `max_id` on every page, and assert
`len(set(ids)) == total`. **Do not re-derive this** — `scripts/run_joint_bound.py`
and `scripts/run_clean_shortfall.py` both have it written.

Six agents in `.claude/agents/`: **`partner`** (directs the fleet — *delegation
is its call*), **`measurement-skeptic`**, **`pre-registrar`**, **`sharp-bettor`**,
**`kalshi-platform`**, **`runtime-realist`**.

**Standing instructions from Joe, which override defaults:**

1. **Call `partner` first** and let it set the queue.
2. **Parallelise by default** — but **two concurrent lanes, never more.**
3. **`measurement-skeptic` audits anything before it enters the record**,
   especially good news. It earned its cost again last session: it caught that a
   0/425 census was about to license a claim about a population it never
   sampled.
4. **Deploys are BATCHED**, and Joe runs them:
   `! gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit`
5. **Don't ask permission to continue.** Do ask before money or a re-deploy.

## BEFORE THE NEXT DEPLOY — a new way to fail to boot

ADR 0019 §6 added `assert_odds_age_limits_agree`, called at startup by **both**
`create_app` and `run_loop`. It **raises** when
`SuppressionConfig.max_odds_age_ms` (hardcoded `900_000`) disagrees with
`MAX_ODDS_AGE_S`. Deliberate — the divergence it catches is silent, and a
warning nobody reads is not a control — but a mismatch now **stops the container
instead of quietly skewing the window.**

Checked and safe today: `fly.live.toml:128` = `"900"`, `.env.example:71` = `900`,
`fly.demo.toml` omits it and takes the `900` code default.

**Not checkable from this machine: whether a Fly *secret* sets
`MAX_ODDS_AGE_S`.** A secret overrides `[env]` invisibly. Run
`flyctl secrets list` before deploying, or the first symptom is a crash loop.

## The reported bug was misdiagnosed — do not re-open it

Last session's start prompt led with *"`edge_within_method_noise` cannot fire on
the one input it was built for."* **It was not built for that input.** Its own
comment scopes it to method-choice ambiguity, and on a symmetric two-way line
method choice contributes genuinely zero ambiguity — every method returns 0.5
because the vig splits evenly. The guard passing means *"method choice does not
explain this edge"*, which is **true**.

The real defect was that **one book's dead line became a consensus** — a
`book_count` fact, already caught twice.

## ADR 0019 — what it decided, so it is not re-litigated

**The agreement family is blind to correlated garbage.** Method spread, market
width and book count are three readings of one question, and correlated lines
agree perfectly. **Measured:** two books quoting a symmetric line give
`fair = 0.5`, `market_width = 0.0`, `book_count = 2`, `reason=None` — they need
not even agree on the hold, since multiplicative devig of a symmetric line is
exactly 0.5 for any odds.

**No new guard was added, and three fixes were rejected with reasons.** A
dispersion refusal fires on exactly the rows two codes already fire on; an
epsilon floor is an off switch wearing a guard's clothes (the guard's median
demand on real live-path input is **1.3 tenths** against a **20.0-tenth** fee);
a symmetry detector targets the wrong feature, since **43.8% of h2h quotes
duplicate another book's**.

**What actually bounds it, and was never justified for the job:**
`edge_ceiling_tenths`. A fabricated 0.5 fair only surfaces at an ask in
**44.0c–47.9c**. Now declared and pinned — raising the ceiling to 50.0 was
**green across every pre-existing test** before that pin existed.

**Also landed:** strategy versioning was broken (adding a `Check` minted no
version, so two check vocabularies would have pooled — now `ALL_CHECK_NAMES` is
hashed); the false `stale_odds` message was corrected; and the duplicate
`SHARP_BOOKS` in `odds/client.py` was **deleted**, because the guard was on the
dead copy while the live set had none.

## The measurement stopped itself, and that is the guard working

`docs/measurements/2026-08-10-clean-shortfall-distribution-result.md` tripped
`STOP THE LINE` on R3 saturation (Grid D's middle cell holds 99.1%). **H4, H2,
H3a, H3b and H1 are WITHHELD — none declared, none refuted.** Do not quote a
verdict from it.

**This is the joint bound's missing symmetric guard, installed and firing.** The
joint bound died because nothing checked whether its decision value was
reachable. This one checked, in both directions, and stopped itself.

The census statistics print regardless and close ADR 0019's open input:
`n_degen(clean) = 0`, `n_degen(suppressed) = 21`. All 21 are **one-book** fairs
in 2 WNBA games, every one suppressed. **The two-book case is reachable and has
not occurred.**

## The queue

1. **ADR 0020 — `stale_odds` reads a scrape clock.** `odds_age_ms` comes from The
   Odds API `last_update`, a **scrape** timestamp: **335 of 335** book+event
   pairs quoting more than one market share one stamp across every market they
   quote, and **27 of 30** books carry exactly one stamp across fifteen games.
   The payload holds 19 distinct stamps spanning 115s, the latest 9s before our
   fetch. It measures our polling cadence, not line freshness. The false message
   is already fixed; the remedy has three live options.

   **Quote 335, not the 440 this file used to say.** 105 of the 440 pairs quote
   one market, where unanimity is vacuous. Corrected 2026-08-09 in four places.
2. **Re-register the shortfall measurement**, deciding what to do about R3. Grid
   D saturating at 99.1% is a fact about the record, not a defect, and a rule
   that can never clear it is a rule that can never report. **H3b is the live
   question:** the 2.1-tenth shortfall sits *inside* the measured devig spread
   `[0.32, 4.61]`, so *"the nearest is 0.21c short"* may not be writable at all.
3. **The refutation ADR** — still blocked, now on item 2. Provisional in exactly
   the way an n=29 null is provisional; say so in its own named section. The
   honest claim is *"Kalshi is not mispriced relative to a consensus it may
   itself lead"*, **never** *"no edge exists at Kalshi"*. And note what the
   comparison actually was: sharp anchoring discards a **median of 26 of 29**
   books, keeping `betfair_ex_eu + matchbook (± pinnacle)` — we have been
   testing Kalshi against the only references plausibly as sharp as Kalshi.

## Waiting on Joe

- **A deploy, and it now carries the Next.js middleware-bypass patch.** Batched
  and his alone:
  `! gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit`
  **Run `flyctl secrets list` first** — see the boot-failure warning above.
- **24 Odds API credits** against 400/day. Two polls of the same games at a short
  interval, checking whether `last_update` advances while prices are
  byte-identical. **The repeat poll is the primary purpose** — it converts the
  scrape-clock finding from inference to proof and generalises past one league.

**Both of the old items here are DONE — do not re-raise them.** The repo is
public (audit clean, 0 alerts), and the Actions spending limit is moot because
public repos get unlimited minutes.

## Settled — do not re-derive or re-propose

- **One signal, not two.** `model_probability` is NULL on every row. Do not wire
  `elo.py` up: the documented design was a conjunction, and an AND-gate on an
  empty set leaves it empty.
- **The joint bound is dead on every population.** Branch Z was arithmetically
  unreachable before the data existed.
- **Arming real trading is a code change** (ADR 0018).
- **The account has zero fills, ever.** Run `scripts/capture_fills_fixture.py`
  the moment trades fill, **before** writing any parser.
- **There is no minimum order size.** `MIN_ORDER_CONTRACTS` was retired; ADR 0017
  §1 Correction 1 says otherwise and is superseded by its own Addendum A.2.
- **Kalshi's `occurrence_datetime` runs exactly 3 hours late**, recorded rather
  than corrected away.
- **Six modules have been built and never called.** `test_has_callers.py` cannot
  catch them — `MUST_HAVE_CALLERS` is opt-in, so absence from the list is
  indistinguishable from having a caller.

## Traps

- **On live the Anthropic bill is held at zero by `surfaced == 0`**, not by a
  missing key. The spend switches itself on precisely when the project starts
  working. **Set a spend limit.**
- **`$CLAUDE_JOB_DIR/tmp` is not empty at session start.** Give scratch files
  task-specific names and check `git log -1 --format=%s` after any scripted
  commit.
- **A committed registration must never be edited in place.** Amendments are
  appended, superseded text marked in place, deleted never.
- **Two sessions in one working tree will fight over git.** Last session a
  parallel session switched the shared branch mid-run. Nothing was lost because
  the work was already committed and pushed — commit early, add by explicit
  path, and never `git add -A` while another session is live. **`git pull`
  before touching `.github/workflows/**` or `.gitignore`**, which a parallel
  session edited.
- **A `cancelled` CI run is not a broken build.** See the public-repo section.
- **`?event_ticker=` ignores `limit` entirely** on Kalshi.
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.**

## The decision that is Joe's

If the refutation stands, **continuing is not a smaller version of this project —
it is a different one**: liquidity provision, or Kalshi as the sharp reference
against another venue. **Make the call after the ADR is written**, not before.
