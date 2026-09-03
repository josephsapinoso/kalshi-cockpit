# ADR DRAFT — The record corrects its own sentences, and a copy nobody reads is deleted rather than refreshed

**Status:** Draft; ordinal to be taken in the merge commit after `git fetch`, per `docs/adr/README.md`.
**Date:** 2026-09-03.
**Decides:** eight sentences the partner listed as refuted by the record, in
`start.md`, `.env.example`, `backend/runner.py`, `backend/store/schema.sql`,
`backend/gate.py`, `backend/agents/scout_desk.py`, `backend/model/margins.py`.
Built in Lane 3. No behaviour changes; two guards added.

## 1. Context

CLAUDE.md carries several paragraphs of the form *"this sentence used to say
X; the record shows Y; here is the file:line"*. That form exists because a
sentence in a docstring, a config comment or a hand-off file outlives the
fact it describes, and the next session reads the sentence rather than the
fact. The partner's 2026-09-03 sweep found eight more of these outside
CLAUDE.md. Each premise was re-verified in this lane before anything was
edited; one did not survive (§3).

The sentences, what refuted them, and where the evidence is:

| # | where | said | record shows |
|---|---|---|---|
| 1 | `start.md` (340 lines) | "The Scout — TABLED BY JOE. Do not start it unasked."; `BILLED_PATH_CALL_SITES` "cannot be satisfied by editing a list" | ADR 0060 switched the desk on 2026-08-21; `backend/agents/scout_desk.py` is an entry in that allowlist (`tests/test_has_callers.py:1399`); the "hypothetical tap" it priced is `POST /api/scout/{ticker}`. Zero references from `CLAUDE.md`, `tasks/NEXT.md`, `tasks/todo.md`, `tasks/lessons.md`, `README.md`; last commit `dafefaf` 2026-08-15 |
| 2 | `.env.example` agents header | "Scout / Skeptic / Historian" | only `scout_desk.py` spends (`BILLED_PATH_CALL_SITES`); the scheduled pass runs `review_retired` (ADR 0062, `runner.py:1776`), so the Skeptic cannot; the Historian is quarantined (`test_has_callers.py:1150`) |
| 4 | `runner.py` `_review_and_persist` | "the bill today is exactly zero calls, because `surfaced` has never been anything but zero" | 24 metered Opus calls in 4m22s on 2026-08-16, four prop rows six times each (`fly.live.toml:45-54`, `agent_calls`); the persisted `surfaced` read 0 only because the Skeptic blocked all 24 |
| 5 | `schema.sql` `desk_attention` | "Pruned by the retention pass like any other log" | `retention.py` deletes from `kalshi_quotes`, `unmatched_items`, legacy `unmatched_events`; `fair_price_downsample.py` from `fair_prices`; nothing deletes from `desk_attention` |
| 6 | `gate.py` `_fee_model_verified` | "`grep "INTO fills"` returns only `tests/`" | `portfolio_poll.py:482` inserts into `fills` with `source = 'venue_hand'`, run by `scripts/run_loop.py:1048` on live. `orders.py` still writes no engine row, so `total == 0` in production still holds |
| 7 | `scout_desk.py` staff brief | "copied from `scout.SYSTEM` verbatim" | two words differ: "the bet" → "any bet", "feed" → "desk"; no test compared them |
| 8 | `margins.py` docstring | "It gives no opinion on who wins — that is `elo.py`" | `elo.py` is quarantined with no production caller (`test_has_callers.py:1166`, CLAUDE.md); `margins.py` *is* live, via `routes.py` → `core/teaser.find_wong_candidates`, which consumes no probability at all |

## 2. Decision

1. **`start.md` is reduced to a pointer, not refreshed and not deleted.** It
   says where the session-start instruction lives (`CLAUDE.md`, then
   `tasks/NEXT.md`), that it used to be a third copy, and names the two stale
   claims it was carrying so the reason for the removal is on the page. It
   stays because Joe may paste-open it; a missing file and a stale file both
   send a session somewhere wrong, but only one of them does it confidently.
   Its content is not maintained anywhere else because a second maintained
   copy is how it got stale the first time.
2. **Each of the seven other sentences is replaced by what the record shows,
   with the old wording quoted and dated in place** — the CLAUDE.md form. A
   silent fix leaves the next reader unable to tell whether the sentence was
   always right or was corrected, and in this repo that distinction has been
   load-bearing more than once (the actionable count, the recorder's cost,
   the combo row's reason).
3. **The four prompt copies of the no-forecast rule are pinned equal, not
   merged.** `tests/test_desk_prompts_share_the_no_forecast_rule.py` asserts
   that `scout.SYSTEM`, `scout_desk.STAFF_SYSTEM_TEMPLATE`,
   `scout_desk.MASTER_SYSTEM` and `pro_bettor.SYSTEM` each state the rule
   exactly once with a subject from `{the, any}`, that the rationale sentence
   follows it word for word wherever present, and that the master's omission
   of the rationale and the two deliberate word changes are decisions rather
   than accidents. **Why a pin and not an import:** the copies are not
   identical and are not meant to be — a staff scout covers a team, not a
   wager — so "make one import the other" would have meant changing a
   deployed prompt to satisfy a docs lane, which is a behaviour change in the
   one artefact whose token count decides whether prompt caching engages at
   all (`.env.example`, `AGENT_MODEL` comment). A shared constant with a
   `{subject}` slot would collide with `STAFF_SYSTEM_TEMPLATE`'s existing
   `.format` fields. The test costs nothing and lets the prompts stay as they
   are.
4. **`.env.example`'s `AGENT_MODEL` line is pinned to `base.DEFAULT_MODEL`**
   (`tests/test_agents.py::TestConfig::test_the_contract_file_carries_the_code_default`).
   The contract already said it keeps Opus "only because `base.py`'s
   DEFAULT_MODEL does, and the two disagreeing would be worse than either";
   that sentence described an intention with nothing holding it.
   `fly.live.toml`'s `claude-sonnet-5` is deliberately not read: the contract
   is what an operator copies, the deploy file is what one machine runs, and
   only the first has to equal the code.

## 3. What this does not establish

- **Item 3 of the partner's list was not a defect and nothing was changed for
  it.** The premise was that `.env.example` and `base.py:42` default to
  `claude-opus-5` while live pins `claude-sonnet-5`, and that the contract
  should say so. It already did, in those words, since ADR 0071 §2.7; the
  code default and the contract agree; `test_agents.py:81` already pins the
  code default. The only thing missing was a guard on the agreement, which
  is §2.4. **A sentence that is already correct is left alone**, however
  plausible the report that it is wrong.
- **No behaviour changes.** `desk_attention` is still unbounded — the
  corrected comment says so and stops there, because bounding it is a
  decision with its own retention window to choose. The gate still counts
  engine fills only (ADR 0043). No prompt byte changed. Live config is
  untouched.
- **`.env.example` is integrator-only** (`docs/adr/README.md`, Lane
  ownership). This lane edited it on the partner's explicit assignment; the
  merging session should treat the hunk as a comment-only change and check
  nothing else touched the file.
- **It does not sweep the rest of the record.** Eight sentences were named
  and eight were checked. The grep for `start.md` found eighteen further
  references in `docs/adr/` and `docs/measurements/`, all historical and
  all left alone: an ADR quoting what `start.md` said on its date is a
  record, not a claim about today.

## 4. Consequences

- A session that paste-opens `start.md` is sent to the two files that are
  actually maintained, in the right order, with one paragraph on why.
- The billed path is named in the contract file an operator reads before
  setting `ANTHROPIC_API_KEY`, rather than two seats that cannot spend.
- A one-word drift in any seat's no-forecast rule, or in the contract's
  model line, is a test failure rather than a discovery.
- **Lesson, pattern form:** *a sentence that names its own evidence ages
  better than one that states a conclusion.* Every corrected line here was a
  conclusion ("pruned by retention", "returns only tests/", "copied
  verbatim", "that is `elo.py`") whose premise had moved; the replacement
  names the file and line the reader can re-check in thirty seconds. The
  same lesson CLAUDE.md drew for the two-signal paragraph, now applied at
  the docstring level.
