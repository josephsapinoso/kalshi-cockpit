# Lessons

Dated, one lesson per entry. Written when something was got wrong, or when a
correction arrived. Reviewed at session start.

- **Write the pattern, not the incident.** "PR #42 broke staging" ages out;
  "unreadable must never resolve to zero" doesn't.
- **A lesson earns its place by preventing a repeat.** If it would not have
  changed what someone did, it is a note, not a lesson.
- **This file is the newest lessons plus an index; the rest live in
  `tasks/archive/lessons-YYYY-MM-DD.md`, verbatim.** The budget is 262,144
  bytes (`tests/test_session_files_are_readable.py`). Split at ~90%, checked
  with `wc -c` before writing; cut on a date boundary; name the archive for the
  split date; move the index lines in the same edit; verify by md5. Every
  split so far: `tasks/archive/lessons-split-log.md`.

---

## 2026-10-30 - Adding a value to an allow-list breaks every test that used it as the "not allowed" example

From the hundred-and-fifth session (CI red after `basketball_ncaab` entered `IN_SCOPE_LEAGUES`).

- **A negative example in a test is a claim about the allow-list, and it changes when the list does.** `test_a_prop_event_or_unlinked_fixture_is_not_a_game` picked `basketball_ncaab` as its out-of-scope sport. Both the lane and main ran the tests that import the list, and both were green. This test never imports the list, so neither run caught it, and CI went red on the merge. Before merging a scope addition, grep `tests/` for the literal value being added, not only for the name of the list.

## 2026-10-18 - An alarm compares at the instrument's own precision; rounding an input onto a coarser grid fires it on a model that held

From the hundred-and-first session (live "Fee model mismatch — stop the line" on a combo fill at $0.0071).

- **The input was rounded, not the model wrong.** `parse_fill` put a $0.0071 fill onto the tenths grid as $0.0070, and a one-sided alarm with a 1e-9 tolerance compared the venue's charge against a ceiling computed at the wrong price. Where a market ticks finer than the repo's money unit (combinations below 1c and above 99c), the comparison that decides an alarm reads the venue's exact value; the stored unit can stay coarse.
- **Print an alarm at the precision of what it measures.** A sub-cent fee printed `.2f` in the record and `.4f` on the push read "0.01 vs 0.01" and "$0.0077 vs $0.0077": the alarm said stop the line and showed no gap. Before diagnosing, get the raw venue row; it settled this in one read.
- **Check a lead's premise against source before chasing it.** The first lead (the fill fell back to the flat coefficient) rested on the ticker's classification, and one grep of the prefix refuted it.

## 2026-10-15 - A test that proves "it waited" by timing a sleep flakes at the clock's granularity; pin the ordering with a flag

From the ninety-ninth session (`test_signal_cache.py`, 2 of 5 runs red with nothing changed).

- **`time.sleep(0.3)` measured by `time.monotonic()` can read 0.297 on Windows.** A test asserting `elapsed >= 0.3` then fails on a clock tick, not on the code, and the full suite on main goes red at random. The claim was never the duration; it was that the route returned *after* the recompute. Set a flag inside the slow stub as it returns and assert the flag was set before the response came back. Keep any timing check as a second opinion with the granularity allowed for, never as the pin.
- **A flake found on the merged tree is fixed on main before the push, with its own mutation**, not retried until green: the lane's suite was green and so was yesterday's, which is what a flake looks like from either side.

## 2026-10-14 - A record that reports wins against expectation can hide a stake-weighted loss; print staked and net beside every rate cell

From the ninety-eighth session (Joe: "you can see that I am not winning parlays").

- **Your bets said the combinations won inside the range the prices imply, and the account was down the whole stake anyway.** Both were true: wins-vs-expected is per ticket, money is per dollar, and the dollars sat on the lowest-priced tickets. A rate table with no stake column cannot show that, and a reader who trusts it concludes "unlucky" when the answer is "shape". Beside every rate cell, print what was staked and what came back.
- **A cut chosen after reading the table is a description, not a finding.** The 15c line and the "5+ legs" bin that made the diagnosis vivid were drawn from the answer; the desk keeps its fixed bands and exact counts, and a tooltip must never fire at a threshold read off the record (ADR 0071 decision 2). Say which cuts were pre-registered and which were drawn afterwards, every time.
- **A glossary entry that cites a mechanism goes stale when the mechanism is removed.** `stake` and `bankroll` still told Joe the site's caps sized his bets, a month after ADR 0112 removed every cap. When a decision deletes a mechanism, grep the glossary for it.

## 2026-10-13 - A reviewer who has not read the refusals re-proposes them, and a lane's targeted recipe misses the cross-file pins

From the ninety-sixth session (UI review, #385–#392).

- **The designer and the sharp-bettor each re-proposed a figure the repo deliberately refuses** — break-even beside fair (ADR 0071 §2.2) and friendly labels for refusal codes (#16A) — plus a nav change #18A settled. Partner caught all three, but only because it read the closed map tickets. **Brief any screen reviewer with the refusal list before it looks**: ADR 0071 §2.2, #16A, #17, #18A, #31, #10/#32, #343, and "no ranking by the gap".
- **Seven lanes each ran their ticket's grep-selected tests green, and CI still found three breaks**: a helper landing inside a slice another test pins colourless, a page drawing its own score line that `test_trust_surfaces` refuses, a regex pinned to the old inline form. A source-text pin can live in any test file and key on a sibling file. **Run the full suite on main after merging a lane batch, before pushing** — not one push per lane, which only buys cancelled CI runs.

## 2026-10-13 - A `**kwargs` stub accepts a parameter the real client does not have

From Joe's phone, the morning after #371.

- **#371 swapped `messages.parse` for `messages.create` and kept `output_format`, which only `parse` takes.** Every agent call on live raised `TypeError` before reaching the network: cards, leg verdicts, scouts. 909 agent tests stayed green because every client double was `async def create(self, **kwargs)`.
- **When a call site changes which SDK method it calls, bind the sent kwargs to that method's real signature** (`inspect.signature(AsyncMessages.create).bind(None, **sent)`), as `tests/test_structured_call_keeps_usage.py::TestTheRequestBindsToTheRealCreate` now does. A stub records what you sent; only the real signature says whether it can be sent.

## 2026-10-13 - An output cap on a structured seat fails worst on the richest inputs, and a fixed meter is not a fixed cause

From the ninety-third session (#377, #210).

- **#210 waited twenty days for a `complete` convening and none came.** The master scout's call sent `max_tokens=4000` with `effort="high"`, and adaptive thinking draws on that same allowance. The one row that stopped at exactly 4,000 output tokens was the convening with six findings in; the ones with none finished in 700. The cap bound on precisely the inputs the seat exists for.
- **#371 made the cut-off visible (`schema_mismatch`, tokens recorded) and the record read that as progress.** It was. But a meter that now reports the failure correctly does not change how often the failure happens; the ticket that depended on the seat succeeding was still waiting on the cause.
- **#338 had fixed the same defect on the card seat three weeks earlier** (3000 → 6000). The fix was not carried to the other seat with the same shape because nothing listed the seats.
- **The rule:**
  - Before trusting any `max_tokens`, read that seat's `output_tokens` for a row sitting exactly at the cap; one such row is proof the cap binds, whatever the median says. Set the cap from the seat's largest observed output plus headroom, and name it as a constant with the evidence beside it.
  - When a fix lands on one seat, grep every other `max_tokens=` in the package the same session and say on the ticket which seats were checked.
  - A meter fix and a cause fix are two tickets. When a meter fix lands, re-ask what the waiting ticket actually depends on.

## 2026-10-12 - Label the comparator before you divide by it; forecast which cap binds from the day that is coming; and a billed call that settles with no usage is a hole in the meter

From the ninety-second session (#370, #371, #372).

- **Session 91 forecast that web searches would bind next.** It was read off a Saturday of college-football cards. Sunday's NFL cards each cost 0.5–1.1M tokens, searches peaked at 61 of 100, and the token ceiling was the one at 90%. The forecast named the wrong cap because it was fitted to the wrong day shape.
- **The first reading of the card cost said "NFL is four times non-football."** The comparator population had not been labelled: the instrument's default shows the newest five cards, and the thirteen cards it did not show were all college football at 121K–227K. Once labelled, "football" and "near kickoff" both fell away as explanations and the NFL listing (921 legs against 105–322) was left. `measurement-skeptic` refused the ratio before the label existed; the ticket carries counts.
- **The master scout settled `filed_nothing` with NULL tokens on a call the vendor billed.** A schema mismatch raises inside `messages.parse`, the outcome carries no usage, and the budget records zero for a call that spent. #365 labelled the credit failure one path earlier; this is the next path along the same seam.
- **The rule:**
  - Before stating a ratio between two populations, print the label of every row in both. An unlabelled comparator is a guess with a denominator; the instrument that labels it costs one call.
  - A forecast of which ceiling binds is a function of the slate, not of the last day read. Say which day shape it was fitted to, and re-fit it the first time that shape changes (an NFL Sunday, the NBA's first week).
  - Every settle path that follows a billed request must carry usage, or the meter under-counts the day it is checked against. When adding a failure verdict, walk every `except` and every early return in the same call for the same gap.

## 2026-10-11 - A ticket that waits for a condition must depend on that condition; and a verification read covers the window it read, not the evening

From the ninety-first session (#338, #365).

- **#338 was parked "after a full budget day on the 5M ceiling" to check whether game-script cards still hit `max_tokens`.** The token ceiling and the per-call output cap are independent, and with automatic cards off a full budget day would hold almost no cards. The evidence was already in the record from the day before (13 metered cards, 7 above the old cap, 0 `max_tokens` refusals). `partner` caught it; the ticket closed a day early on the reading that existed.
- **Session 90 verified the deploy at ~00:30Z and called it healthy.** Forty minutes earlier the Anthropic account had run out of credit and seven calls failed. The ledger had settled six of them as `filed_nothing`, so a read of verdicts showed a quiet desk, not an outage.
- **The rule:**
  - Before parking a ticket on "wait for X", name the mechanism by which X changes the answer. If none exists, read the evidence that is already there and close or re-scope now.
  - A post-deploy read states the window it covered. Read the agent ledger's errors for the whole budget day, not only the minutes after the deploy, and never trust a verdict column to report an outage until a failure path is shown to write a failure verdict (#365 made that true for `call_error`).

## 2026-10-10 - A daily ceiling lowered below the day's recorded spend is a lockout, not a cap; and a stored refusal is not a sentence for the screen

From the ninetieth session (ADR 0190 Amendment 3).

- **The 2.5M token ceiling of #349 deployed at ~20:00Z into a budget day that had already recorded 2.84M.** `AgentBudget` gates every call on the day's recorded total, so from the deploy to the 10:00Z reset it refused every call, including the taps the change was meant to keep. Joe found out at kickoff of the Saturday late window, from a Parlays list that printed the morning's watcher refusals on every game.
- **The screen printed the stored reason verbatim** — "AGENT_MAX_TOKENS_PER_DAY 9000000 x (1 - SCOUT_AUTO_TAP_TOKEN_SHARE 0.75) = 2250000" — because `no_card_line` was written as "No card today: {reason}" and the reason was written for the record (it names the dial, and a test pins that). Two audiences, one string.
- **The rule:**
  - Before moving any daily ceiling down, read the budget day's recorded total (`agent-spend --days 1`) and set the new value above it, or time the deploy for after the reset. The check is one instrument call; the failure is an operator locked out for the rest of the day with the previous regime's refusals on his screen.
  - A reason stored for the record and a sentence shown to the operator are different strings with different tests. The record names the dial; the screen says what to do next ("Open the game and tap Build card"). When one function serves both, the screen test must assert that no config name reaches the sentence, with a positive control that a reason meant to be shown still is.

## 2026-10-10 - A test that an off switch "sends nothing" proves nothing until the same input is shown to send with the switch on

From the eighty-ninth session (#346, the parlay-push switch).

- **The first version of `test_off_a_built_ladder_sends_nothing` was green with the switch on, off, and with the guard deleted.** The hand-built ladder it fed `parlay_cards` could not send for a reason unrelated to the switch (the debounce holds a composition until it has been seen twice), so "nothing was sent" was true of every code path. The runner-side gate test went red under mutation; the send-side test did not, and only the mutation pass noticed.
- **A screen-level review found the same shape elsewhere the same day:** `tests/test_fair_value_steps.py` pinned `(overround - 1) * 100` as source text and stayed green while every market page printed a negative house cut, because a pin on an expression asserts the expression, not the number it produces.
- **The rule:**
  - A test for a refusal, an off switch or a guard starts with a positive control: the same input, through the same helper, reaching the thing the guard blocks. Without it the assertion cannot tell the guard from any other reason the action did not happen.
  - A source-text pin on an arithmetic expression is not a test of the arithmetic. Beside it, assert one concrete value (0.033 → "103.3%" and "3.3 points"); when the repo has no renderer, assert the formula on the number, not on the string of the formula.
  - Mutation-check every guard separately. Two guards behind one switch are two mutations; the one you skip is the one that was decoration.

## 2026-10-09 - A deletion lane's red is in a registry, not a caller: run the full suite before the merge, not after

From the eighty-eighth session (#332).

- **Lane #332 deleted `ParlayValuation` and grepped every caller clean**, ran eight test files and was green. CI went red on `test_no_priced_surface_claims_the_edge_is_real.py`, a registry that lists `types/parlays.ts` as a priced surface because that type carried `total_cost_dollars`. A registry keyed on a *file* holding a *word* is invisible to a grep for the deleted *name*. Second session running where the red was a pin outside the lane's grep set (2026-10-08, `test_api`).
- **The rule:**
  - A lane that deletes a type, field or module runs the full suite before it reports done; the targeted set is for iteration, not for the hand-back.
  - Main runs the full suite locally on the merged tree before pushing a deletion merge, or accepts that the first CI run is the full suite and holds the deploy for it.

## 2026-10-09 - An as-of rebuild must take EVERY input as of the time, status flags included; and a write-up quotes a registration's direction, it does not re-derive it

From the eighty-seventh session, look A of the combo-markup measurement (#327, #336).

- **The `g` rebuild read each leg's fair rows as of the lookup and its market's status as of today.** Every leg was `finalized` by the time the look ran, the ladder dropped every one, and the rebuild's catch-all label said "no fair row". The fixture that passed had seeded the market `open`, so the test could not see it. The measurement-skeptic found it by reading the ladder, not the data.
- **The draft result stated the registered confound backwards.** §10 says the pessimistic fair OVERSTATES markup, more on longer cards, so it biases the slope up; the draft said the opposite and used it to explain a negative slope. The skeptic caught it against the registration's own text.
- **The rule:**
  - When reconstructing anything "as of" a time, list every input the downstream code branches on (status, eligibility, horizon, retention) and freeze each at that time; a fixture for it seeds the AFTER state (settled, pruned, delisted), not the convenient one.
  - A write-up quotes the registration's stated direction of every named confound verbatim and reasons from the quote; a sign re-derived from memory under time pressure inverts.
  - A pooled descriptive whose parts disagree with it by a factor of five is not a number for CLAUDE.md, however clean the median looks.

## 2026-10-08 - A wrong number can be inherited without anyone typing it: from an old sentence, from a guess about retention, from a registration that names a clock the repo already refuted

From the eighty-seventh session (#320 to #334, Joe's parlay challenge).

- **A changed sentence has pins you cannot find by file name.** Lane #321 replaced the "−Y% EV. Don't." sentence, grepped the tests for the words it removed, and was green; CI went red on `tests/test_api.py`, which reached the sentence through a route and asserted "holds". The recipe's file-name grep cannot see a test that exercises a route.
- **"Lost for good" is a claim about retention, and retention is a measured number.** The sharp-bettor wrote that every week without the per-leg record was data lost for good; the partner read ADR 0016 and found Kalshi keeps candlesticks about 80 days, so nearly the whole history was recoverable and the real deadline was the retention window. The build order changed on that one fact.
- **A registration can name a column the repo has already measured wrong, and a faithful lane will build on it.** The markup registration defined its six-hour band on `kalshi_events.commence_ms`, which `scoring.py` refuses because it runs about three hours late; lane #327 implemented it exactly. The amendment landed before any row was read, which is the only time it can.
- **The rule:**
  - When a served sentence changes, grep the tests for every distinctive word of the OLD sentence, not only the words being removed, and run the route tests that could render it.
  - Before calling any data unrecoverable, read the venue's retention from the record (ADR 0016 for candlesticks); state the deadline as a date.
  - Before a registration names a timestamp column, check `backend/match/linker.py` for a measured offset on it. A wrong clock found after the look cannot be fixed by re-running; found before, it is one amendment.

## 2026-10-06 - The failure you are waiting to capture may already be in a capture you have; a test that asserts a capture is clean pins the blind spot

From the eighty-fifth session (#316, #319).

- **Session 83 built a recorder for web-search error codes and waited for the first natural failure to capture the wire shape.** Five failures then recorded `{}`. The shape was in `tests/fixtures/anthropic_scout_captured.json` the whole time: a `code_execution_tool_result` with `return_code: 1` and `stderr: "Server tool use limit exceeded during code execution."`. The recorder matched `error_code`, which that path never emits. The capture's own test said "four code-execution results all succeeded", written from belief, and it stayed green over a fixture that contradicted it.
- **The cause was ours, and the billing count said so.** The vendor does not bill a failed search, and every failed call billed exactly the cap. A tool that batches several calls in one script loses the whole script on the cap-plus-one call, so "unavailable on every attempt" was the cap, not an outage.
- **The handoff said CI was green.** It was green for the commit before; the fixture commit after it failed on both pushes, and nobody read the run for HEAD.
- **The rule:**
  - Before waiting on the next natural failure, grep the captures you already hold for the failure text the model paraphrased.
  - A test on a capture asserts what the capture contains, never that it is clean; "no errors" is a claim to read off the file, not to write.
  - When a server tool runs inside another (search inside code execution), the error surfaces in the OUTER tool's result; match on exit status and stderr, not only on the inner tool's error code.
  - A per-call cap times a billed count equal to it is a signature; read the cap before theorising about the vendor.
  - "CI green" names a sha. Read the run for HEAD before writing it, and `gh run list` before the first push of a session.

## 2026-10-05 - A retrying client's final status describes only its last attempt

From the eighty-fourth session (#318).

- **"A 4xx proves the venue refused" was wrong for one reason: `KalshiRestClient.request` retries POSTs.** A first attempt can create the RFQ and lose its answer, and the retry then meets `already_exists`. The code read that as "one of ours, asked at another size", and the screen said "Nothing was asked" about the very request it had just made. The first build of #318 missed this; the second `kalshi-platform` review found it.
- **The rule:**
  - Before classifying a failed write by its status code, check whether the client retried. If it did, the status describes the last attempt only, and every earlier lost answer (a transport error or a 5xx) makes the outcome unknown.
  - Carry "an earlier attempt was lost" on the exception, rather than inferring it from the final status.
  - The default that flatters is "nothing happened". Call an outcome refused only on proof.

## 2026-10-05 - A fallback string that drops the exception turns an outage into a content judgement

From the eighty-second session (#220, #309, #313).

- **The Anthropic credit balance ran out at 10:19Z. For seven hours every agent call failed, and nothing named the cause.** The card writer stored "the call returned nothing", the screen said "No clean story", and leg verdicts and the scout desk "filed nothing". The exception (a 400, "credit balance is too low") existed only in Fly's logs. A sharp-bettor review theorised a max-token truncation, and the scout desk's 0.4-second failure looked like a new bug.
- **The count hid it too.** `status` × count showed 61 `refused_invalid` rows, which reads as a validation problem. Grouping by the reason *text* showed one reason was 65 of 65.
- **The rule:**
  - A fallback reason for a failed external call carries the exception class and message (#309 now does).
  - When every call of a kind fails at once, read the error itself (the logs, or the stored reason grouped by text) before theorising about content, prompts or token caps.
  - When a status count looks wrong, group by the reason text before reading anything into the count.

## 2026-10-03 - A budget gate that drops work without stamping it makes the work look done-and-empty

From the eightieth session (#289 follow-through).

- **Five cards Joe had minted were never re-checked two hours before kickoff, and nothing said so.** `decide_rechecks` gated on the unattended token share, which the T-24h builds had spent: 4.47M of a 4.5M line by 22:35Z. A card past the line was "simply not chosen", so its `recheck_status` stayed NULL, and NULL rendered as "not re-checked". That was literally true and told Joe nothing. It surfaced only because the review wanted to say whether a drop-if had fired.
- **The rule:**
  - A gate that declines work must leave a mark on the thing it declined (a status or a reason), or the decline is indistinguishable from never being due.
  - When two kinds of spend share one allowance, check whether the earlier, bulk kind can starve the later one Joe asked for.

## 2026-10-02 - A background wait that prints a word has to be read before the next action, and a remembered command form is the command

From the eightieth session (#301).

- **A CI wait printed `failure`, and in the same tool call I ran the deploy.** The workflow's default sent it to demo, so live was never at risk. It would have reached live had I typed the right form, because the deploy did not depend on the CI result I had just printed.
- **Memory held the exact live deploy form** (`-f instance=live -f confirm_live=kalshi-cockpit`). I typed the bare `gh workflow run deploy.yml` instead. The run went green, deployed demo, and only `/api/health`'s `git_sha` showed that live had not moved.
- **A source pin's span is a range of the file.** `test_exposure_route` reads everything between two decorators, so a new handler placed between them is inspected as part of the old one.
- **The rule:**
  - Gate a deploy on the CI conclusion inside the same command (`[ "$c" = success ] && gh workflow run ...`), never on reading it afterwards.
  - Copy deploy commands from memory verbatim.
  - Add new handlers outside any span that a test splits on, and grep `tests/` for the file name before choosing where.

## 2026-10-02 - A lane's "stopped at 39%, no failures" is an unrun inventory, and GitHub caps a parent at 100 sub-issues

From the seventy-ninth session (parlay town hall, #269).

- **Lane F reported its whole-tree inventory as "stopped at 39% with no failures" and asked the integrator to rerun it.** I ran three inventory files and not the source-reading pins (`test_desktop_tier`, `test_wire_types_live_by_area`). CI failed on exactly those, one push later. A partial run that found nothing is not a pass; it is an unrun check with a reassuring sentence attached.
- **Map #3 hit GitHub's hard cap of 100 sub-issues mid-session** (HTTP 422 on the 101st link). The board, the frontier query and the Question-for-Joe test all assume #3 can always take another child. When it can't, a new question has nowhere visible to go. Opened #292.
- **The rule:**
  - When a lane names a check it did not finish, the integrator runs that whole check before pushing. Include every test that greps the files the lane touched, not only the ones the lane named.
  - Before opening several of Joe's questions in one go, count #3's children (`gh api .../issues/3/sub_issues --paginate --jq length`). At 100, use the continuation map, not an unrelated epic.

## 2026-10-01 - An open ticket is not proof the work is undone, and a pin list written from memory is not the pin list; grep for both before dispatching

From the seventy-seventh session (#266, S3 of ADR 0192).

- **Two Sonnet lanes were dispatched on tickets that had already shipped.** #210 had been live since 09-29 and was kept open for a live read. #255 part 1 had been committed in `cd5b216`. The board lists open tickets, partner ranks what the board lists, and neither reads `git log`. Both lanes came back with nothing to do. They cost two lane runs and nothing worse, but on a money-path ticket the same gap would mean a second build of something already live.
- **ADR 0192 §2.8 named four location pins. Moving the handler broke nine.** One of the missed ones, the leg-verdicts pin, did not break at all: it found the new thin adapter by name and kept passing **vacuously**. A pin that locates code by function name survives a move by checking the wrong body.
- **The rule:**
  - Before dispatching any ticket, run `git log --oneline --grep "#NN"` and read the ticket's last comment. "Kept open for a live check" is not "unbuilt".
  - Before moving code that tests pin by location, grep `tests/` for the file path, the function name, and every helper that moves. Do not trust a list written when the move was planned.
  - After the move, make each pin fail on purpose by breaking its guard at the NEW location. A pin that stays green under that mutation is pointed at the wrong body.

## 2026-10-01 - A rule the backend obeys can be broken by the screen's fallback sentence; check every hand-written failure string on a spend path against it

From the seventy-sixth session (architecture review, #257–#260, ADR 0191).

- **CLAUDE.md has said "a lost response is an UNKNOWN, not a failure" since
  ADR 0164, and the backend obeys it.** Meanwhile the armed hand-bet path's
  browser helper (`placeManualOrder`) answered a dropped connection with
  "Nothing was sent to the exchange", and a drop after the cockpit had
  forwarded the order would have made that false. The combo-accept helper
  rendered a pydantic refusal as `[object Object]`, the exact bug `postHedge`
  had already fixed nearby. Neither was found by looking for a bug. Both
  turned up because an architecture review counted copies of one mechanism,
  14 hand-rolled POST helpers, and the copies disagreed.
- **The rule:** when a rule about money states governs a path, grep every
  hand-written fallback string on that path, meaning catch blocks and
  "unreadable" branches, and read each one against the rule. A sentence
  written for the case that "can't happen" is the one nobody re-reads. And
  where a mechanism is copied N times, put it behind one module whose
  failure sentences are required parameters with no default. Then a new call
  cannot inherit a sentence that is false for it.
- **Lane hygiene:** a lane that leaves background work running re-sends its
  final report every time that work stops. End a dispatch prompt with "once
  you have reported, stop".

## 2026-10-01 - A retention rule can quietly cut a registered measurement's population; list the registrations that read a table before shortening how long it is kept

From the seventy-fifth session (#226, the CLV signal test's stopping-rule pull).

- **#122 set a 60-day retention on `kalshi_quotes` (2026-09-23), and the
  registered signal test reads its half-spread control from that table.**
  The harness drops a row without a control, so from about 2026-10-07 a
  re-pull would have returned a smaller, different population than the one
  the 2026-09-30 cut note fixed. Nobody wrote that deadline down; partner
  found it at session start, with six days to spare. The pull ran in time.
- **The rule:** before shortening any table's retention, grep
  `docs/measurements/*preregistration*` and `backend/analysis/` for that
  table and list every open registration that joins it. Then either pull
  first, or state the date each one's population starts to erode in the
  retention ADR. A retention change is a change to every measurement that
  reads the table.

## 2026-09-30 - Parallel lanes pass their own tests and break each other's pins; run the full suite on merged main before every push

From the seventy-fourth session (epic #244, eight lanes in one afternoon).

- **Three tests went red on main, and no lane's own recipe could see any of
  them.** #248 regrouped /bets, which killed `test_record_chart`'s anchor
  string. #250 moved the live predicate into `lib/api.ts`, which broke two
  hedge tests that grep `HedgePositions.tsx` for it. Each lane ran "every
  test that greps the files I edited". But those tests grep for a *string*
  that had moved, not for the file name, and they belonged to an older
  feature. Two pushes (`28ce70a`, `864a303`) went out red before the full
  run caught it.
- **The rule:** a lane's targeted recipe proves the lane. Only a full
  `pytest -q` on the merged tree proves the batch. Run it after merging and
  before `git push`, every time, even when every lane reported green. It
  takes 12 minutes. A red main costs a CI run, and it risks a deploy of a
  tree nobody ran.

## 2026-09-30 - A restatement of a threshold can silently change its unit; a correction lands in one place and every restatement keeps the old claim

From the seventy-fourth session (all-hands conference).

- **CLAUDE.md turned the registration's "G ≥ 713" into "G_eff = 713"**, and
  then concluded the look "is not coming". The registration's §B7 says in so
  many words that restating the floor in `G_eff` is the forbidden move. The
  chair of the conference walked in believing the spine, and the code had
  already taken the look on a page load. **When a sentence says a threshold
  is unreachable, cite the registration's own line for its unit, not the
  spine's paraphrase; the code that takes the look is the second witness.**
- **Same shape, three more times in one audit.** ADR 0112 removed the
  hand-bet brakes and the backend comment was corrected, but three screens
  above the Buy button kept listing them, and a test *required* the Gate to
  name two of them. The same-game fix learned in `gate.py` (ADR 0029) was
  re-broken in the hedge. The hedge's "no floor" guard checked the summary
  object while every rung underneath carried the flattering floor. **After a
  correction, grep for every restatement of the old claim, tests included; a
  test that pins old copy is a restatement too.**

## 2026-09-30 - A model seat does not know what day it is unless the prompt says so; a refusal that writes no row reads as "never asked" once the screen reloads

From the seventy-second session (Joe's phone, the long-ladder card).

- **The leg scout PASSed a game kicking off that morning because it was
  "over a year away".** No seat's prompt carried the current date, and the
  prompts gave kickoff as an ISO timestamp. A model dates that against its
  training data, and most verdicts were saved only because a search happened
  to return current news. Every test passed, because a stub client has no
  sense of time. **Any prompt that asks a model to judge recency or distance
  in time must state now**, which now means one uncached block in
  `structured_call`. A new call path that bypasses it needs the same.
- **One leg of six showed "nobody has asked yet" after Joe had asked.** A
  refusal writes no row by design (#155), so its reason lives only in the
  POST response held by the component. Once the component remounts (after a
  filter change or a reload), the GET finds nothing and says the leg was
  never asked, which is false. The cause could not be recovered afterwards.
  **A state held only in client memory is lost on the next render path that
  does not carry it. If the screen needs to say something after a
  remount, the server has to keep it.** #223 now writes the `refused` row the
  schema already allowed.

## 2026-09-29 - Two writers of one column must share the derivation; an asyncio lock guards one process; a module nothing reaches merges together with its caller

From the seventy-first session (#214–#217, ADR 0190).

- **The watcher's refusal rows wrote `sport_key = 'americanfootball_nfl'`
  while the tap's built rows wrote `'nfl'`, in one table.** Two lanes each
  took the value nearest to hand: the odds fixture's key and the Kalshi
  ticker's prefix. Neither lane's tests could see the other writer. **When a
  second writer of a column appears, grep for the first writer's derivation
  and call that one function.** A named `sport_key_for` existed, and main
  asked for it, a round before the second writer arrived.
- **The card route's `asyncio.Lock` looks like it serialises every card
  build, and it does not.** The watcher runs in `scripts/run_loop.py` and the
  tap runs in the API process, so each has its own lock. **Before trusting
  an in-memory lock or dedupe to bound spend, name every process that can
  reach the guarded call.** Across processes only the database check holds.
  Write the gap in the docstring if it is accepted.
- **A lane that adds a module with no caller cannot merge by itself here.**
  `test_has_callers` fails closed on an unreached module, and a placeholder
  disposition would be a false claim that the "escaped" test then flips.
  **Plan the lane and its wiring to land in one merge commit** (merge
  `--no-commit`, wire it, commit), or give the lane the call site.
- **A seat "shaped like" the leg verdict cost 4.8x the leg verdict.** The
  design costed it by analogy (~51K), but a card is sent a whole game's leg
  listing plus search results. It read 289K, and 99% of that was input.
  **An analogue carries the output shape, not the input size. Cost a new
  seat by what it is sent**, and keep gating the arm on one real reading.
  That gate is what stopped a 60K reservation from spending into Joe's half.

## 2026-09-29 - A covering index makes each row cheap, not the range small; a cited line in a "does not establish" note is still a claim; an absence needs a grep of the writer

From the seventieth session (#197–#208, ADR 0189).

- **The rest chip's first reader went to the 10M-row table for facts a
  per-game table already held.** Its `GROUP BY odds_event_id` over
  `odds_snapshots` read every snapshot of every game to recover three names.
  Its "covered" window walked 16 days of one sport's index entries, and both
  ran on every `/api/parlays`. Plan tests passed on 2,400 seeded rows.
  `odds_fixtures` (one trigger-maintained row per game) answered both with PK
  seeks and a ~1,000-row range. **Before reading identity or schedule off
  `odds_snapshots`, ask how many rows the range holds on live, and whether a
  one-row-per-entity table carries the same fact.** A plan test on a small
  seed proves the index is used, not that the range is small.
- **#170's script said, under "what this does not establish", that NO-side
  spread legs "are already priced (`parlays.py:1080`)".** They are not: the
  pool offers only the favourite's cover (`parlays.py:986-991`). #198's lane
  inherited the claim as a gate that called every NO spread priced. **A line
  number cited in an exclusion is a claim like any other. Open the line
  before building on the sentence.**
- **The partner planned around "parlay checks are not persisted".**
  `parlay_check.py` writes a `parlay_lookups` row with `card_key = 'checked'`
  on every check. **Before designing around an absence, grep for the writer
  (INSERT, `_record_*`), not only the reader.**
- **A count of what Joe did is not a veto on what he asks for next.** The
  census found same-game combos in 5 of 94 of his combos, under the
  pre-fixed bar, yet his #200 answer asked for game-script building. Both
  held: the same-game page was built on his word, and the census moved the
  rest chip onto the cross-game legs he actually bets. **When a count and his
  request point different ways, build what he asked for, and put the shared
  facts where the count says his bets are.**
- **A combo series named for a scope is not necessarily where that scope
  trades.** `KXMVENFLSINGLEGAME` had no open collection; same-game NFL combos
  are minted in the catch-all `-R` collections. **Read which collections are
  open and list the fixture before choosing where to mint.**

## 2026-09-29 - Batching N reads into one widens the blast radius to N; one client cannot tell its own path from the far side; check a bind address before planning an arm on it

From the sixty-eighth session (#191, #193, #194).

- **Merging twelve per-leg reads into one `GET /markets?tickers=` made one bad
  input able to blank all twelve.** In the old loop a malformed hand-typed
  leg ticker failed alone. In a comma-joined list it could 400 the whole
  request, blanking every leg on `/hedge` and silencing the watcher for as
  long as that position stayed open. The capture had only proved that a
  *well-formed* unknown ticker is dropped quietly. kalshi-platform caught it
  before merge. **When a loop of independent calls becomes one batched
  call, re-ask what one bad element does**, and filter at the batch
  boundary. Inputs that don't fit go down the old single path, so they
  still fail alone.
- **Every external reading of #193's stall came from one laptop, and the
  first §F draft still concluded the 3 s was added "on Fly's side".**
  measurement-skeptic: nothing had separated the client's own network path
  from the server's. A bisect that walks inward from one client clears the
  hops it can see; it cannot name the far side without a second vantage
  point. **Before attributing a delay to the other end, run a second client
  on a different network in the same window** (`.github/workflows/probe.yml`
  now does this). The same draft also compared a rate against a rate at a
  different request cadence. Compare per request.
- **The 6PN arm of the §F reading was written into the plan and then could
  not connect.** Next binds `HOSTNAME=0.0.0.0` (IPv4 only,
  `docker/entrypoint.sh`), and `fly proxy` reaches the machine over IPv6, so
  every request was reset. It cost nothing only because it was checked
  before the window opened. **Before planning a measurement arm through a
  private or alternate path, read the server's bind address**, or send one
  request down that path, before you register the arm.
- **A commit that pre-registered #193's last reading closed #193 before the
  reading ran.** Its message said "The stop-loss closes #193 after this
  window". GitHub parses "closes #N" (also "fixes" and "resolves") as a
  closing keyword anywhere in a commit pushed to the default branch, even
  mid-sentence. The ticket then sat closed for the whole measurement, and
  `gh issue close --comment` afterwards reported "already closed" without
  posting the comment. **In a commit message, never put "close", "fix" or
  "resolve" directly before an issue number unless the push should close
  it.** Write "#193 is closed after this window" instead.
- **A latency window ran on the laptop while a lane ran three full
  `-n auto` suites on it.** The reading survived only by luck of the
  signal's shape: the stall is a fixed 3.1 s, and nothing fell between 500
  and 2,900 ms. Load cannot fake that, but no check for it had been
  registered, and a smeared tail would have been unreadable. **Keep a
  measurement window clear of lane test runs on the same machine**, or name
  the contamination check in the rule before the window opens. Also kept,
  because it worked: committing and pushing the decision rule (`4eee37e`)
  before the reading.

## 2026-09-28 - A speed comparison must charge both arms for the same work; a new opener must carry the old one's guards; Git Bash rewrites a leading "/"

From the sixty-seventh session (ADR 0188, #185–#190).

- **The first kernel harness reported the Genz CDF as ~200× faster than
  the Monte Carlo at 2 legs.** It was ~25×. The Monte Carlo timer covered
  `joint_probability_all` end to end: matrix, thresholds, draws. The Genz
  timer covered only the `cdf` call and left ~0.2 ms of setup outside it,
  which was most of its cost. measurement-skeptic caught it before commit.
  **When two methods race, wrap each in one function that goes from the
  same inputs to the same output, and time those two functions.** A ratio
  where one arm's setup was done outside its timer measures where the timer
  was placed, not the method.
- **`gh issue create --title "/api/signal serves…"` published
  "C:/Program Files/Git/api/signal serves…".** Git Bash (MSYS) converts any
  argument that begins with `/` into a Windows path, silently, before the
  program sees it. This was the one of five titles that began with a route.
  **Prefix `MSYS_NO_PATHCONV=1` to any command whose arguments begin with
  `/`, or reword so they don't.** Then read the published text back:
  `scripts/board.py` is where this one showed.
- **A lane that opens its own database connection skipped the guard the
  request path's connection carries.** #187's background refresh called
  `db.open_db(..., read_only=True)` with no `statement_budget_ms`, so the
  one query ADR 0135 bounds for every API read ran unbounded off the
  request path. Its tests were green, because nothing asserted the budget.
  **When new code opens a resource beside an existing opener (connection,
  client, session), diff its arguments against that opener's**, and pin
  the ones that are guards.
- **A published release is not a resolvable tag.** `astral-sh/setup-uv`
  has `v10.2.0` and no floating `v10`. The job died in "Set up job" with
  "unable to find version", before any test ran. Local tests passed
  because nothing local resolves an action ref. **Before pinning an action,
  list its tags** (`gh api repos/<o>/<r>/git/matching-refs/tags/v10`). Also
  read what an input does before trusting its name: setup-uv's
  `python-version` only sets `UV_PYTHON` and puts nothing on PATH.

## 2026-09-28 - A look recipe written for neutral counts does not transfer to a money result; merge approval covers the PRs it named

From the sixty-sixth session (#174–#177, #182).

- **The HUD recipe said "headline numbers as a lit readout".** It was
  written against counts ("On the slate 100"). The Your bets lane met
  a headline that is a verdict on Joe's own money (net −$126), kept its
  red, and added the glow. Joe took it off the same day: it made his
  biggest loss the brightest thing on the page. **When a style rule
  meets a figure that carries a verdict (P&L, a hedge estimate, a
  TAKE/PASS), treat that figure as the exception and ask before
  shipping.** The /hedge lane was told this up front, got it right, and
  cost nothing.
- **"Merge, deploy and check" for one PR was not approval for the next
  three.** The next merge was refused `[Merge Without Review]` and cost
  a round trip. **When dispatching parallel lanes, ask once for the whole
  batch** ("merge each once CI passes?") before the lanes finish, not
  after the first is blocked.

## 2026-09-26 - A named test list is the tests you thought of; a trap recorded in memory is invisible if its index line doesn't name it

From the sixty-fifth session (#171, #172).

- **The lane ran every test its ticket named, all green, and CI failed
  on a test in another file.** `test_watcher_decides_from_fresh_facts.py`
  pins that `Nav.tsx` holds exactly one poll timer, and the lane added a
  second. Source-reading tests pin a frontend file from anywhere in
  `tests/`. **Before merging, run every test that mentions a file the
  lane edited** (`grep -lE "Nav\.tsx|…" tests/*.py`). The ticket template
  now says so.
- **I leaked a one-hour session cookie through Playwright's run_code
  echo, a trap memory had recorded the day before.** The fix was in the
  memory file's body, and the MEMORY.md index line named a different
  trap. **When a memory's body gains a new hazard, update its index line
  in the same edit**, because the index is the only part a session reads
  first.

## 2026-09-26 - A vivid case is usually inside the count; "does X trigger Y" needs both ends of the wire

From the sixty-third session (#165, #170).

- **One held combo carrying 5 NO-side legs looked like it refuted "2
  of 150", and it was one of the 2.** The recount on a committed
  instrument gave 2 of 82. The case that made the count look wrong was
  already inside it. **Before calling a population count contradicted
  by a case in front of you, check whether that case is one of the
  counted.** A salient example says the category exists. It says
  nothing about how often it occurs.
- **A fact-scout reported that the /parlays page buys no attention,
  from a grep of backend routes.** The heartbeat is sent by the client
  (`Nav.tsx` → `/desk-attention`), and the only backend writer sits
  under an unrelated router name. **To ask whether a screen triggers a
  server behaviour, grep the client for the call and the server for
  the writer.** A negative from one end is not a finding. Say so in
  the scout's brief.

## 2026-09-26 - A link can be the right shape and name a group; an answered question lives in the ADR's decision lines

From the sixty-second session (#165, #169).

- **The parser read a real kalshi.com combo link correctly and still
  could not resolve most of them.** The link names an event, and 36 of
  57 events behind Joe's combos hold more than one combination (one held
  34). Session 61 checked the link's shape against one real instance,
  and that instance happened to be a single-market event. **When an
  identifier resolves one-to-many, measure the cardinality on the real
  population before trusting the resolver.** One real example proves
  the shape. It does not prove the mapping.
- **I re-asked Joe two questions he had answered the day before.** The
  answers were in ADR 0187's decision lines, and I read NEXT.md's Still
  open list and the ticket bodies instead. **Before any button question,
  grep the ADR the ticket cites for the answer.** The ADR's opening
  lines are where a decision is recorded, and the Still-open line only
  says what is left.

## 2026-09-26 - A parser tested on an example written from memory is green and useless; a name is not a field

From the sixty-first session (#166).

- **The link parser shipped round 1 green, and could not resolve a
  single real kalshi.com link.** Its test used a URL the lane invented,
  and it asserted an event ticker as if it were a market ticker. A real
  combination URL carries the series and the event, never the market.
  One web search found two real ones. **Before writing a parser for a
  string someone else formats (a URL, a share link, a filename), find
  one real instance and put that in the test.** When the owner has none
  to hand, a public page is still better than a guess. This is the
  captured-payload rule, applied to the input and not only to the
  response.
- **A ticker with no `SHARD1` in its name sat on shard 1.** Any
  inference from how an identifier is spelled is a guess about a field
  the payload already carries. Read `exchange_index`; never parse it
  out of the name.
- **Copy that says "ask instead" beside a withheld Ask button is the
  same lie as a missing button.** When a control is gated, grep the
  surrounding words for the action it performs, and gate them on the
  same condition.

## 2026-09-25 - Display rounding can manufacture the zero the data refused; a comment that lists a dependency is not the dependency list

From the sixtieth session (#161, #162).

- **A formatter that rounds a probability to whole points prints "0%"
  for a real longshot reading.** The backend kept "no reading" as `None`
  and never 0, and then `Math.round(p * 100)` turned a 0.06% reading into
  "Desk's chance: 0%" on the first live render. The unreadable-is-not-zero
  rule has to hold at the last formatting step too. **Format small
  probabilities with enough places to stay non-zero, and floor with
  "under X", never with 0.** Test on the smallest real value on the record,
  not a round synthetic 0.34.
- **An effect whose comment says "recomputed when the side changes" and
  whose dependency array does not list `side` recomputes only when the
  side's other inputs happen to change too.** Two sides quoting the same
  ask were a live, reachable case, and Confirm stayed dark on a buyable
  bet. **When a comment names the triggers of an effect, read the array
  against it.** This is the justifications-decay pattern at the scale of
  one line.
- **A green Deploy run on a workflow with a default target proves the
  default.** Ours defaults to `demo`. Read the live `/api/health`
  `build.git_sha`, never the run's colour.

## 2026-09-25 - A container's safety promise is only as strong as each child's own exit; preview money screens through a proxy that refuses writes

From the fifty-ninth session (#158).

- **A container that promises an invariant inherits every child's
  ability to break it.** The new buy panel refused Escape and backdrop
  while an order was in flight. But the order ticket inside it had its
  own Escape listener and Close button, and both still worked mid-send.
  Closing cleared the intent key, released the panel's lock, and made a
  second real order with a fresh key reachable. **When you write "X will
  not happen while Y", list every child that can perform X on its own and
  guard each one too.** A review that reads only the container's diff will
  pass it.
- **To see a money screen with real data before deploying, put a local
  proxy between the dev server and live that forwards GETs and refuses
  every other method.** Every tap that would spend (RFQ, order, scout
  POST, price lookup) comes back as a local 403 and never leaves the
  machine. You can then click through each tab and state at both widths.
  Tests that scan source text cannot show that a sheet is too short or a
  label wraps, and screenshots can.

## 2026-09-25 - A brake that reads settled spend admits the whole burst; a refusal that writes nothing reaches only its caller

From the fifty-eighth session (#155, #156).

- **When spend is recorded only after the work settles, a ceiling
  checked against recorded spend admits every concurrent request.**
  Sixteen leg verdicts were admitted in 11 seconds, all at 334,711
  recorded, and the day closed at 1,120,442 against 500,000. The existing
  rule "a brake overshoots by the last call" assumes calls run one at a
  time. **For any fan-out, reserve in-flight work at an estimate** (the
  running rows times a measured mean), inside the one ceiling
  implementation. Age the reservation out on the same window that stops
  calling a row pending. Check the other two meters before reserving
  them too: the call count was already written at call start.
- **A refusal that deliberately writes no row is visible only to the
  code that received the response.** Every trigger fired `void
  requestLegVerdicts(...)`, so a server refusal never reached the
  screen. The poll then read `none` and said "nobody has asked yet".
  Rewording the refusal (#154) changed text nobody could see. **Never
  discard the response of a request whose answer can be a refusal. Before
  improving a message, check that it can reach the screen at all.**
- **A per-unit cost read at n = 1 was the low end, not the middle.**
  31,640 tokens a verdict became a mean of ~51K over 17 (range 29K–90K),
  so a ceiling sized on the first reading held 60% of what it claimed.
  Quote the range once there is one.

## 2026-09-25 - A poll that stops on "nothing yet" never sees a request made after it mounted

From the fifty-seventh session (#153 review).

- **A component that polls only while a row is `pending` goes blind to a
  request fired after it mounted.** The per-leg verdict line rendered inside
  a closed `<details>` on page load. It read `none` and stopped. Opening the
  panel fired the request, but nothing re-read, so the verdict would never
  have appeared. The lane's own tests were source scans and could not see
  it. **When a trigger and a reader are separate components, have the
  trigger stamp a request time. Make that stamp a dependency of the
  reader's poll, and wait through `none` for a grace window after it.**
  In review, ask of every poll loop: what starts it again?
- **A feature that only fires from a step the user hasn't taken is
  invisible, and "it's live" means nothing to them.** The leg scout shipped
  wired to two buy steps. Joe opened the page, saw no TAKE or PASS, and
  reported it missing. **Every feature that costs a tap needs a visible
  entry point on the screen it serves**, and "done" means seeing it from the
  user's side, not getting a 202 from the API.

## 2026-09-25 - An event ticker is not a game: Kalshi puts the series in it

From the fifty-sixth session (#150).

- **A Kalshi `event_ticker` names a (series, game) pair, not a game.**
  `KXWNBAGAME-26SEP24CHIWSH` and `KXWNBASPREAD-26SEP24CHIWSH` are one game
  on two series. A join on `event_ticker` that means "the same game" misses
  every other series. Every test seeded one series only, so none could see
  it. **When a join means "the same game", seed a second series in its
  test.** Match on the fixture segment (after the first `-`) inside one
  `kalshi_series.league`, never on the segment alone: two leagues can share
  a date-and-teams string.
- **Before building on a striking zero, build the read that splits it.**
  "0 of 39 briefed" was 34 real misses plus 2 join misses (plus 3
  failures). One CHEAP query that printed both counts per leg separated
  them. Asking Joe about scouting spend on the raw zero would have mixed
  the two.

## 2026-09-24 - A rule's default population can be the wrong one to capture from; a flag's default value cannot double as "unset"

Two patterns from the fifty-sixth session (#107, #149).

- **When a capture rule excludes the only population that shows the
  thing, measure that first, then ask to redact rather than hunt.** The
  held-ticker lesson says to capture on a market the account does not
  hold. But 0 of 45 non-held combination books carried a YES bid, and 2 of
  4 held ones did. Before hunting, check which fields actually identify
  the market. An orderbook response carries none, so replacing the
  request's ticker was the whole redaction. Joe allowed it in one tap.
  **Name which fields identify the market before deciding a capture is
  forbidden**, and pin the redaction with a test that fails on any other
  ticker in the file.

- **A sentinel equal to a flag's default silently overrides a caller who
  typed that value.** A lane gave one query a larger default by treating
  the shared `-n` default (5) as "unset", so `-n 5` returned 20. The lane
  documented the collision and shipped it anyway. **Give the query its own
  argparse default (`default=None`) or live with the shared one.** Never
  infer intent from a value the caller can also type. In review, grep a
  lane's diff for `== <default>` comparisons on parsed args.

## 2026-09-24 - A fixture captured on the operator's own holding is operator data, whatever fields were redacted; an "ignored" filter may be the wrong filter name; a lane's targeted run misses the whole-tree inventories

Three patterns from the fifty-fifth session (#147, #148).

- **The market a fixture is captured on can itself be operator data.**
  #147's lane redacted `creator_user_id` and `creator_id`, but it captured
  the list on one of Joe's held combinations. The market ticker and all
  eight legs identified his position, and the file still said
  `market_ticker_redacted: true`. The commit only got caught because the
  `kalshi-platform` review ran before the push. Its sibling was not caught.
  #96's `combo_rfq_quotes_sell_side.json` had shipped the same held ticker
  and legs publicly, in `2d92786`, the session before. It was redacted
  going forward, and the writer now redacts tickers
  (`capture_sell_side_rfq.redact_tickers`). **Capture on a market the
  account does not hold.** Redact every identifying field (tickers, legs,
  collection), not just the ones named "user". Before merging a lane that
  adds a fixture, grep its whole diff (`git log -p main..lane`) for the
  held tickers. When a leaked commit was never pushed, drop it with
  `reflog expire` + `gc --prune=now`.

- **Before you record "the endpoint ignores this filter", check the filter
  is that endpoint's own parameter.** The previous entry below says
  `rfq_user_filter=self` is "silently ignored" on `GET
  /communications/rfqs`. It is. But `rfq_user_filter` is the QUOTES
  endpoint's parameter. The RFQ list's own is `user_filter=self`, and that
  narrowed the list from 100 rows to 0. **Read the endpoint's reference
  for the parameter name before concluding a venue cannot filter.** The
  wrong conclusion cost a heuristic (`creator_user_id`, n = 1) where a
  server-side filter existed. It also hid a limit=100 miss.

- **A lane's targeted test run does not collect the tests that inventory
  the whole tree.** Both lanes reported green, and main went red three times.
  A new fixture was not classified (`test_captures_carry_their_request`), a
  new Next route handler was missing from `test_token_proxy_routes`, and a
  vocabulary word had no gloss (`test_glossary_coverage`). None of these
  tests imports the file that changed, so `-k hedge` never reaches them.
  **A lane that adds a fixture, a route handler or user-facing copy runs
  those inventory tests by name**, and they are now in the ticket
  template's verification recipe.

## 2026-09-24 - A list filtered by a parameter the endpoint ignores is everyone's list; a precondition written as "wait until it holds" must be re-read, not re-inherited

Two patterns from the fifty-fourth session (#129, #96).

- **Prove a filter narrows before trusting what it returns as "ours".**
  `GET /communications/rfqs?market_ticker=` lists every requester's RFQs,
  and `rfq_user_filter=self` (which DOES narrow `/communications/quotes`) is
  silently ignored there. `open_rfq_for` and a capture script both read "an
  open RFQ on this market" as "our open RFQ", and the script refused all
  three held combinations because strangers were asking about them. The
  cheap test: call with and without the filter and compare row counts
  (100 = 100 here), and look for a field that differs between your row and
  others' (`creator_user_id`, set on ours only). **Where the venue has a
  per-requester rule (one live RFQ per market), its 409 is a better "ours"
  signal than any list.** #147.

- **A "blocked until X" line in the handoff decays into "X hasn't
  happened" without anyone checking X.** #129 and #96 sat as "waiting on Joe
  holding an order-linked combination; do not poll" while the venue's own
  positions read showed three held combinations. The instrument needed the
  VENUE's population, not the desk's (`/api/hedge` showed them as
  unrecorded). **When a ticket is parked on a world-state precondition,
  write the one read that checks it, and run that read at the next session
  start** instead of copying the parked line forward.

## 2026-09-24 - An owed read must name where the evidence persists; a brake on the wrong unit protects nothing; a fixed date in a clock-relative test is a timer

Three patterns from the fifty-third session.

- **When something is armed, the handoff's "read it next session" must name
  a durable place.** #139's owed read pointed at prune log lines, which
  stdout keeps for about ten minutes, and at `prune-frontier`, which reads a
  different table and walks the file. The next session could not take either
  read. **Before writing an owed read, check that the evidence outlives the
  gap between sessions.** A table row, a meta cursor or a committed
  instrument works. If nothing durable exists, build the instrument (#144)
  in the same session that arms the feature.

- **Check which unit a brake counts before trusting it to protect
  something.** `reserve_taps` held back calls and searches for Joe's taps,
  but the ceiling that bound was tokens, and the token brake only refuses
  once the recorded total has already crossed the line. Two convenings
  recorded 759K against 500K and refused his taps anyway. **Name the ceiling
  that actually binds, then make sure the reserve is in that unit** (#145).
  Note also that "two leave roughly one tap" had been derived from days with
  three *partial* convenings. A per-unit cost taken from a different mix of
  runs is not a cost.

- **A fixed calendar date in a test whose query is relative to the clock
  runs out.** A test seeded 2026-08-09 and asked for `days=45`. Its own
  comment said it was "comfortably inside" the window, which stayed true for
  three days. Derive the seed date from `now`. When CI goes red in a file
  nobody touched, grep that file for a literal date before suspecting the
  change.

- **A registration can be unpassable by construction, and implementing it
  is what shows that.** The Elo floor gated on a team-clustered `G_eff >=
  300`, which can never exceed the number of teams (about 30). Nobody saw it
  until someone had to write the formula down. **Before running a
  registered look, write its code-level definitions as an amendment**. It
  costs one agent call before any data is read, and here it saved a 6.5 GB
  copy on the live box (#146).

## 2026-09-23 (fourth) - Before widening a CHECK, look at who references the table; and a "the desk did it" flag can be its own column

- **A column-level CHECK in SQLite cannot be altered, only rebuilt.** If
  another table references this one by foreign key, the rebuild's
  `DROP TABLE` runs with `foreign_keys = ON`, inside the migration's
  transaction, where the pragma cannot be turned off. #143 wanted a third
  `closed_source` value on `parlay_positions`, which the legs table
  references. **Before planning a new CHECK value, grep `REFERENCES <table>`
  in `schema.sql`.** If it has children, add a nullable column instead: an
  `ADD COLUMN` step, the shape this runner already takes.

- **Keep "who established the fact" apart from "why the row moved."**
  Adding the reason column kept `closed_source` meaning what it already
  meant, and still left a desk close and a tap distinguishable.

## 2026-09-23 (third) - A field named for one meaning often carries several: filter on the codes the decision names, never on non-empty; and a figure told to the user is one they can act on

Two patterns from the fifty-first session, both caught in review before
merge.

- **"Suppressed" was one word for a dozen codes.** #79 asked Joe whether the
  parlay builder should refuse a leg the singles screen suppresses "as a
  probable bug", and named three codes. The lane refused any non-empty
  `suppressed_reason`. That field also carries `edge_within_method_noise`
  ("No edge"), which is on nearly every row, so merged as written it would
  have emptied the parlay screen. Its tests all passed because they seeded
  only `suspicious_edge`. **Before filtering on a reason field, list its
  vocabulary (`ALL_CHECK_NAMES`) and filter on the codes the decision
  named.** Add a test with the commonest harmless code, and check that it
  is kept.

- **A figure told to the user must pass the check that produced it.** The
  shard refusal printed the wall with `:.2f`. At 0.90 the example happened
  to round down; at 0.99 it printed "$3.90", which the same wall refuses.
  Floor any "the most you can ask for" figure. The test asks for exactly
  the printed figure and must pass.

## 2026-09-23 (second) - A SQL fragment copied from a sibling query carries that sibling's column meaning; and a lane's test count is read, not quoted

Two patterns from the fiftieth session, both caught while merging #137.

- **Before reusing a sibling query's expression, check that your column
  means the same thing as its column.** `scout-watch-log` labels a budget
  day with `(budget_day_ms + offset)`, which is correct because that
  column is already a day start. The lane copied it onto raw `called_ms`,
  where it moves the day boundary from 10:00Z to 14:00Z. Every test seeded
  calls at 11:00Z, where the right and wrong conventions agree, so all of
  them passed. **A test of a boundary needs a row on each side of it.**
  One test with 09:59Z and 10:01Z calls turns the mutation red.

- **Start a running-sum window on the boundary it sums over.** `now - n
  days` cuts the oldest day partway through. That day's total then looks
  whole but is only part of the day.

- **Count a lane's tests yourself.** The report said 10 and the file had 6.
  Nothing broke, but a count in a report is a claim like any other.

## 2026-09-23 - A claim about how a counter behaves across a restart is a claim about where it is stored; and a number spliced from a registration carries its errors with it

Two patterns from the forty-ninth session, which filled #118's result
document. Both were caught by `measurement-skeptic` before commit, not by
the session that wrote them.

- **Before writing that a restart resets a counter, or that a counter shows
  no gap, read the writer.** The skeleton said the 15:48Z deploy "restarted
  the runner, which resets `scout_watch_log.cycle_count`", and the filling
  session then read "126 counts over 125.01 intervals" as proof that no
  cycle was lost. Both claims were wrong: the counter is a database upsert
  (`cycle_count = cycle_count + 1`), so nothing resets it, and the day
  before showed 92 counts over 89.71 intervals across three restarts. A
  boot can *add* a count, so a lost cycle plus a boot cycle gives the same
  total. A count that matches the span is consistent with continuity, and
  that is all it shows.

- **A figure copied from a registration into its result is re-derived, not
  trusted.** The registration's "3.75 h of 24 (15.6%)" for the partial day
  was 4.25 h (17.7%): 10:00Z → 14:15Z. The skeleton copied it and the
  filled draft kept it. The registration is not edited, since it is the
  record of what was fixed in advance. The result says the number was
  wrong, and gives the right one beside it.

## 2026-09-22 (sixth) - An ordering recorded only in a ticket's prose is invisible to the board that dispatches from it; a scheduled task that must wake the machine depends on power-plan state its own XML does not show; and a result document written before its data is a registration one level down

Three patterns from the forty-eighth session, a short one taken twelve
hours before a one-shot read.

- **When Joe orders one ticket after another, encode it as the dependency
  edge the board reads, and write on the ticket the date the edge comes
  off.** Joe's (b) to #117 put #115 behind #58; it was recorded in a
  comment, and `board.py` — which reads
  `issue_dependencies_summary.blocked_by` and nothing else — listed #115
  READY under `owner:main` for three sessions. Prose on a ticket is read by
  a person once; an edge is read by the board every session. The
  auto-unblock date (10-06) is the same kind of decaying clause, so it goes
  on the ticket beside the edge as the instruction to remove it, not as a
  fact a later session must rediscover.

- **`WakeToRun=True` in a task's XML is a request, not a guarantee; the
  power plan decides whether wake timers are honoured, and it can differ
  by AC and DC.** The laptop arm for #118's T1 was rehearsed green with
  the machine awake, which proves nothing about 02:05 AM. `powercfg /query
  SCHEME_CURRENT SUB_SLEEP RTCWAKE` showed wake timers enabled on AC and
  disabled on battery; `HIBERNATEIDLE` showed hibernate after 15 minutes
  on AC. Neither is visible from `schtasks` or `Get-ScheduledTask`. **When
  an arm's failure mode is "the machine was asleep", read the power plan,
  not the task.** The finding went to Joe as one sentence — the fix was
  his to make and Arm A did not need it — rather than as a power-plan
  edit twelve hours before the window.

- **Write the result document's skeleton before any row of its data
  exists: every outcome branch with its consequence, the VOID checks
  first, every datum a slot.** A branch written after one is true reads as
  the finding; five branches written before any is true read as the
  partition, and a reader can check that it was applied rather than
  chosen. The skeleton also moves the "which read counts" and "which
  checks come first" decisions to the day before, when no read can
  flatter them. The marker guard
  (`tests/test_a_question_for_joe_has_a_ticket.py`) fired on a template
  line in the skeleton — the marker with a placeholder number — and the line was
  reworded: a skeleton is in the record from the moment it is committed
  and is held to the same rule as a result.

## 2026-09-22 (fifth) - A fixed-window reading nobody can attend is taken by two schedulers with different failure modes, and the rule for choosing among their reads is registered before any of them fires; an amendment's number is read from the file it amends

Two patterns from the forty-seventh session. The first is the session's
whole build; the second was caught by the `pre-registrar` before commit.

- **When a pre-registered window falls at an hour no session survives to,
  automate the read with two arms whose failure modes differ, rehearse
  both today on the same read-only path, and register in advance which of
  the several resulting reads counts.** T1 was 55 minutes at 02:00 PDT,
  `n = 1`, one slip landing at 02:00 PDT again. A GitHub cron is late, not
  absent (245-minute max gap on record), so it fires four times inside the
  window; a laptop task is punctual but sleeps; each covers the other's
  hole. Several reads then exist, and *choosing* among them after seeing
  them is the degree of freedom the registration exists to remove — so the
  rule (latest qualifying read; monotone counters make that the
  conservative one) went into the registration before the first fire. **A
  rehearsal is free only if the path is provably read-only**; check the
  route and the QueryDef cost class at file:line before calling it free.

- **An amendment's ordinal comes from the file it amends, not from the
  session's memory of other files.** "Amendment 3" was assigned because
  another registration in the same directory had Amendments 1 and 2; this
  one had none. A sequence with a gap reads as two lost amendments, which
  is exactly the quiet defect a registration must not carry. Grep the
  target file for `^## Amendment` before numbering, and say so in the
  brief to whoever writes it.

## 2026-09-22 (fourth) - A pass placed behind a liveness gate never runs on the population it is for; an invariant a sibling table got at birth may be structurally unavailable to the one you extend; and a new write ahead of a cycle's decision variable inherits that variable's default on failure

Three patterns from the forty-sixth session. The first was caught by
reading the gate before accepting the placement; the second by reading the
migration precedent before writing the column; the third by the runtime
review, after the tests were green.

- **Before placing a periodic pass behind an existing gate, ask what the
  gate is false for — that is usually the population the pass exists
  for.** `anything_in_progress` is true while an open position has a
  pending leg whose game has started; it is false once every leg has
  resolved, which is the common state of a combination the venue has
  settled. A close pass inside `watch_once` would therefore have closed
  settled rows only while some *other* ticket was live, and a quiet desk
  would have kept dead rows open indefinitely. The proposal read naturally
  ("settle, then close, then re-price") and was wrong for the rows that
  mattered. **Run the gate's predicate against the state the new pass is
  meant to act on before accepting the placement.**

- **A table-level CHECK cannot be added by `ALTER TABLE`, so an invariant
  a sibling table got at birth may be structurally unavailable to the
  table you are extending — state the asymmetry, or a later session will
  "fix" it with a rebuild on the live record.** `parlay_position_legs`
  carries `(outcome = 'pending') = (resolved_source IS NULL)` because it
  was created with it. `parlay_positions.closed_source` cannot have its
  twin: the column arrives by `ADD COLUMN`, only a column-level CHECK can
  ride it, and every row closed before the column would violate the
  invariant anyway. The writer enforces it instead. **When two tables
  share a pattern and one of them is being retrofitted, write down which
  guarantees the retrofit cannot carry and why**, in the ADR and beside
  the column, so the missing CHECK reads as a decision and not a gap.

- **A new statement placed ahead of a cycle's decision variable inherits
  that variable's default when it raises — and the default is usually
  "do nothing".** `busy = False; try: <new pass>; busy = gate(); if busy:
  watch_once()`. Green tests, correct behaviour, and one `database is
  locked` from the new write would have skipped the settle, the re-price
  and every push, then slept the idle interval while a game was live —
  hedge alerting silently off, into a log stream with ten minutes of
  retention. The tests could not see it because none of them made the new
  pass fail. **When adding a step before the line that decides what the
  rest of the cycle does, give it its own handler and write the test that
  makes it raise on the busy path.** The runtime review found this, not
  the suite; a unit suite tests the step, not what the step's failure
  does to its neighbours.

## 2026-09-22 (third) - Read a ticket's Done-when against the tree before dispatching it; a Must-not-touch can contain a file the change falsifies; a loose prefix turns a drift guard into a phantom-defect reporter; and the machine's clock is not the clock

Five patterns from the forty-fifth session. The first four were caught
before a lane started, by reading each ticket's executable line against
the current tree rather than trusting that last session wrote it. The
fifth was caught after the deploy, by a timestamp GitHub wrote.

- **A ticket written at the end of one session is not dispatchable at the
  start of the next until its Done-when has been run against the tree.**
  #132's recipe required a test file green whose line 98 pinned the exact
  literal the change removes, and that file was not in Lane owns. A lane
  either stalls or keeps a dead `=== 0` filter to satisfy the pin — and
  the second is a bug that the ticket's own regex Done-when would have
  passed. **Before dispatching, grep the tree for every literal the change
  removes and see which test pins it; that test is in Lane owns or the
  ticket is not ready.** This is the third ticket in a week wrong in its
  executable line (#124, #95, now #132) and the first caught before a lane
  ran.

- **A source-regex Done-when that names two fields passes while the
  change drops rows from the screen.** "The live predicate names both
  `pending_legs` and `venue_settlement`" is satisfied by editing one of
  two hand-written filters, after which a row can match neither and
  vanish. **When a partition is two filters, the spec is one predicate and
  its negation, and the Done-when pins the negation** — exhaustive and
  disjoint by construction is a property of the code shape, not of a
  regex over it.

- **A ticket's Must-not-touch list can contain a file whose comment the
  ticket's own change falsifies.** #132 broadened what `nothing_pending`
  means while `api.ts`, whose doc comment defined the old meaning, was
  forbidden. Same rule as the screen copy
  (`test_no_screen_still_tells_him_that_closing_the_page_buys_more`): the
  fix and the words ship together or the words lie in the interval.
  **When a change redefines a reason string, grep every comment that
  defines it, in every language in the repo, and put those lines in Lane
  owns.**

- **Do not plan anything against a clock window on the machine's own
  clock until it has agreed with a remote one.** The session's first
  `date -u` printed `07:40:58 UTC`; it was 14:40Z. Every clock statement
  in the plan ("the target day opens in ~2h", "nothing dated is due
  today") was seven hours wrong, and the deploy that was reasoned to land
  *before* the #118 measurement day landed six hours *into* it. It was
  caught only because GitHub stamped the deploy run at 15:48Z. Nothing was
  voided this time, because the VOID rule's deploy criterion is about a
  value changing, not a restart — but a registration with a "no deploy
  inside the day" criterion would have been void before the session knew
  what day it was. **At session start, read `curl -sI https://api.github.com`'s
  `Date` header beside `date -u`; if they disagree, the machine's one is
  the wrong one.** The same fixed-window discipline the #118 registration
  demands of the instrument (`spend.day_start_ms` must equal the day you
  meant) applies to the session's own sense of when it is.

- **A drift guard built on a constant prefix inherits every constant that
  shares the prefix.** `COMBO_BOOK_` collects the four state constants as
  well as the three reason constants, so a guard that compares that set
  to the `combo_book_reason` union is red on a clean tree — and a ticket
  that says "report drift, do not fix" then reports a defect that does
  not exist into the record. **State the prefix exactly, state the
  exclusion, and verify by hand that the sets match today before the
  ticket says they should.**

## 2026-09-22 (second) - A venue action takes its population from the venue at the moment it acts; a board's READY count can be eleven and dispatch nothing; and a dated count in a code comment decays like one in a doc

Four patterns from the forty-fourth session. The first cost nothing tonight
because the instrument was built to read the venue; it would have cost a
wrong RFQ if the operator's list had been trusted instead.

- **A mirror's "live" row is a fact about the mirror. An instrument that
  acts at the venue re-derives its population from the venue at the moment
  it acts.** `/api/hedge` at 03:55Z listed two positions with pending legs;
  the sell-side ask at 05:11Z was refused on both as *not held*, because
  Kalshi had finalized both combinations at 04:23Z and 04:33Z while the
  desk's legs -- resolved from the runner's market-results pass -- still
  read `pending`. The screen was right about the record and wrong about the
  world by one pass. **Pick tickers for a venue write off the venue's own
  positions read, never off a screen, and let the instrument refuse when
  the two disagree** -- that refusal is the measurement, not a failure.
  Same shape as `at_venue` (ADR 0136): the desk says what it cannot see.

- **`READY N` on the board counts open, unblocked, unassigned leaves and
  says nothing about who can take them.** Eleven READY tonight: eight
  `owner:joe`, three `owner:main` with a start date or an appointment,
  **zero `owner:agent`** -- the lane fleet had nothing to do and every
  session was collapsing into main doing everything. The fix was to write
  tickets (two landed under #82), not a board warning: four sessions of
  tooling was the pattern to break. **Read the owner split under
  FRONTIER before calling the frontier full.**

- **A count with a date in a source comment decays exactly as it does in a
  doc (ADR 0162), and a lane will write one.** The #130 lane put "41 of 43
  open positions live 2026-09-22" into `api.ts`'s type comment. It was true
  at 03:55Z and wrong by 05:11Z. Trimmed on merge to "most rows; re-read
  `/api/hedge`". **When reviewing a lane diff, grep it for a digit followed
  by a date before merging.**

- **A "decayed justification" claim is itself a claim; read the WHERE
  clause before ticketing it.** `partner` said `watched_tickers`' docstring
  ("bounded by how many tickets one person holds") had decayed to "ever
  held" because nothing auto-closes a position. Its SQL filters
  `l.outcome = 'pending'`, so the list is bounded by live legs regardless
  of `status`. No ticket was opened. The reviewer was right about the
  screen (`positions.map` over every open row) and wrong about the watcher,
  and the two claims arrived in one paragraph with equal confidence.

## 2026-09-22 - A new read on a request path inherits the old read's population or it drifts; and a tripwire on a shared symbol fires for whichever path reaches it first

Two patterns from wiring #95's reader (#128). The review caught the first;
a failing test caught the second.

- **When a new venue read joins a request path that already has one, hold
  it to the predicate the existing read uses, or the two populations drift
  apart on the same screen.** `/api/hedge` already read leg quotes for
  `DISTINCT` tickers with `outcome = 'pending'`. The new combination-book
  read was looped over `open_positions` -- `status = 'open'`, which on this
  desk means unclosed bookkeeping, not a live game: 43 rows open, 2 with a
  pending leg. Shipped as first written, every page load would have made 38
  venue reads in series for 36 books with nothing left to sell into, on an
  unauthenticated route under a 30 s proxy ceiling, on the same client and
  limiter the armed order path queues behind. I had filed that as "measure
  the latency on live, then decide"; the reviewer filed it as "guard before
  merge", because the states to degrade into already existed and the guard
  cost ten lines. **The check is mechanical: list every venue read the
  route already makes and the predicate on each; a new read with a looser
  predicate than its neighbours is the defect, before any timing is taken.**
  The second half of the same rule: **bound the wait, not just the count** --
  a per-read `wait_for` into an existing "unreadable" state is what keeps one
  hung ticker from taking the whole screen down.

- **A tripwire on a shared symbol proves nothing about the path you meant
  until every other path to that symbol is stubbed.** The demo test
  recorded `KalshiConfig.load` to prove the combination reader was never
  constructed on a keyless instance. It fired -- from the LEG quote path,
  whose lazily built `LiveQuoteSource` calls `load` itself and then dials
  the real venue with four retries a leg. The same unstubbed path made the
  timeout test measure a fifteen-second wait that had nothing to do with the
  timeout. Neither test was wrong about the wiring; both were wrong about
  what they were observing. **Before asserting "X was never called", grep
  for every caller of X the app under test can reach, and stub each one
  the test does not mean to exercise** -- the existing `quote_source=`
  injection on `create_app` was there for exactly this and three other test
  files already used it.

## 2026-09-21 (third) - A sample's negative result becomes a universal about the world in one sentence; a ladder's rungs can all be the same number; and an instrument that reports "today" cannot report yesterday

Five patterns from the orchestration session. The first one is mine and it is
the one that would have reached a screen.

- **A negative result from a sample gets written as a universal about the
  world, and the flattering direction is "this thing does not exist" - because
  absence licenses a smaller build.** #107's capture failed a third time, and I
  wrote *"across three attempts, a non-empty combination YES side has never
  been observed"* into a ticket comment **and** into a lane brief. It is false:
  `2026-09-17-combinations-can-be-exited.md:40-41` measured resting public-book
  YES bids of 5.10c/38,709 deep and 0.32c/24,900 deep. **The same comment
  contained its own counterexample two paragraphs later** - the careful version
  ("different population, not refuted") and the overreaching version were
  written side by side, and the overreaching one is what a lane transcribes
  into a docstring and from there into copy. The true claim was always
  narrower and was about **this repo's disk**: *no committed capture fixture
  carries one*. **When a sample comes back empty, write the sentence about the
  sample, and say where the sample was drawn from in the same sentence.** This
  was the fourth frequency clause about combination liquidity to be written and
  withdrawn (three earlier ones are catalogued in `parlays/page.tsx:95-127`)
  and the first caught before shipping - by a review, not by me.

- **When a decision is presented as a ladder, an effective ceiling is the raw
  cap MINUS the consumer's own reservation - and computing it without that
  makes two rungs look different when they are identical.** Joe was asked #116
  against *3 convenings -> searches at 5/day -> calls at 6/day -> tokens*. The
  5/day is `60 / 12` with the watcher's reserve left out:
  `scout_watch.py:198` holds back `STAFF_PAIR_SEARCHES_WORST_CASE * (1 +
  reserve_taps)` = 36, so it refuses above 24 used - **three convenings,
  identical to the allowance**, while tokens allow 2.9. Three rungs, one
  number. The 5/day figure was real but described a **tap**, which reserves
  only 12. **Read the consumer's reservation, not the config value, before
  ranking anything** - and when the rungs coincide, say the ordering question
  is unanswerable rather than sizing a sample for it.

- **An instrument that reports "today" cannot report yesterday, and a read
  window planned without that lands outside the population it means to read.**
  The #118 trip was planned for 09-23 10:30-14:00Z. `/api/scout` reports spend
  for the budget day containing *now*, and the day rolls at 10:00Z - so that
  snapshot describes 09-23 (thirty minutes old), not the 09-22 day being read.
  The whole token half would have collapsed to "not separable" **by
  construction**, and the write-up would have blamed the instrument. **Check
  which period an instrument's numbers cover against the period you mean to
  measure, at the moment you pick the clock time.** The fix was a second
  reading *inside* the target day, with a self-verifying pre-condition
  (`spend.day_start_ms` must equal the day you meant) so a mistimed trip voids
  itself instead of reporting.

- **A hunt that fails three times is usually sampling the wrong population,
  not running out of luck.** #107 sampled currently-quoted combinations at an
  arbitrary instant, three times, and found nothing - while the reading it was
  trying to reproduce came from a combination Joe had **just bought**, where
  ADR 0164 says a resting bid is residue of a recent print. The defect was the
  **trigger**, not the sample size: a calendar cannot find a residue. **Before
  scheduling a fourth attempt, ask what the successful observation had that the
  failures did not** - here, a live position, which is one call to check and
  which no amount of re-sampling would have supplied.

- **A "Done when" is the executable line, and a re-scope recorded anywhere else
  does not amend it.** Two ran into this in one session. #95 was re-scoped to
  absence-first in a review comment while its Done-when still demanded a test
  that the payload *attaches the resting YES bid* - unprovable, so a literal
  lane stalls or invents. #124's own profile comment said not to raise
  `timeout-minutes`, while its Done-when still said *"the workflow change is on
  main AND a CI run has completed green with the new configuration"* - so a
  literal lane does the one thing the ticket forbids. Both bodies were correct
  in prose and wrong in the one line an agent executes. **Rewrite the Done-when
  in the same action as the re-scope**, and generalising last session's lesson:
  its named test must be runnable - check the harness exists, not just the
  instrument. #95's said "a named frontend test" and **`frontend/` has no test
  runner at all**, so satisfying it literally meant standing up vitest.

---

## 2026-09-21 (second) - A deadline can expire into a missing instrument; a ruling recorded only as a ticket comment decays like a question recorded only as a line; and a guard with a backstop behind it tests green either way

Five patterns from the session that armed the record behind unattended
scouting. Three of them come from things that were already decided or already
measured and were invisible to the thing that reads the queue.

- **A ticket's "Done when" can name a reading no committed instrument can
  take, and nobody notices until the clock expires.** #118 shipped with a
  24-72h deadline for a reading of `trigger = 'auto'` rows by budget day.
  Three hours in, a grep found **zero readers of `scout_briefings` anywhere
  in `scripts/`** - no QueryDef in either registry named the table - and
  `flyctl ssh` may only run a committed script by path. The reading was
  BLOCKED ON INSTRUMENT from the moment the deadline was written, and a new
  QueryDef needs a deploy before it can be read on live, so discovering this
  at 14:15Z tomorrow would have meant building, deploying and reading late.
  **Check the instrument exists when the deadline is WRITTEN, not when it
  expires.** The same check catches the cheaper half: `/api/scout` serves
  briefings but its SELECT never reads `trigger`, so no served surface could
  separate an unattended convening from one Joe tapped - which is the entire
  purpose of the v51 column.

- **A ceiling that was ranked last is the one that binds, and the arithmetic
  that ranked it was ours.** The ladder put to Joe on #116 ran *3 convenings
  -> searches at 5/day -> calls at 6/day -> then tokens*. Measured on the
  first afternoon: the search figure was right to the decimal (5.0) and
  **tokens bound first**, at ~170K a convening against a 500K budget - 2.9 a
  day, tighter than the 3-convening brake he approved. He answered a question
  about the wrong brake. **When a decision is presented as a ladder, the
  cheapest check is to divide the budget by one observation of the unit cost,
  for every rung, before asking.** Nobody had ever measured a convening's
  token cost; the ranking was structural reasoning presented as arithmetic.

- **A partner's re-spec recorded only as a ticket comment decays exactly like
  a question for Joe recorded only as a NEXT.md line.** CLAUDE.md step 7 gave
  "ask Joe" a forcing function - a numbered sub-issue - because a line decays
  into the instrument that raised it. A ruling that changes a ticket's *scope
  or dependencies* has no such function. #107's 2026-09-20 comment said "#95
  ships the absence path first ... not yet executed"; a day later #95 was
  still `blocked:1` and invisible to the board, because `scripts/board.py`
  reads GitHub's `blocked_by` **edge**, not the comment thread. **A decision
  that changes what the queue shows must be written where the queue reads,
  in the same session it is made.**

- **A guard with a backstop behind it passes its own test either way, and
  only the mutation says so.** `record_watch_outcome` refuses an unknown
  outcome before touching the database. Its first test asserted "no row was
  written" - and stayed **green with the guard deleted**, because the table's
  own CHECK rejects the insert and the function's broad `except` swallows it.
  Identical observable, guard or no guard. **When a guard sits in front of a
  second mechanism that produces the same end state, the test must pin what
  the guard uniquely changes** - here, that the connection is never touched
  (a stub raising on `execute`) and the reason is logged at ERROR rather than
  appearing as a swallowed traceback. Same family as the 2026-09-18 lesson
  that a fake modelling the venue's good behaviour cannot test a guard
  against its bad behaviour.

- **A ceiling that refuses before it writes leaves the schema unable to
  answer the question the schema was given a column for.**
  `scout_briefings.refusal_reason`'s own comment says "which ceiling
  refused", and **none of the four ceilings that gate a convening writes it**:
  all three pre-flight paths return or raise before their `INSERT`, so a row
  reaches `status = 'refused'` only from inside a desk run already under way.
  This is the #71 shape (`SHARD_HEADROOM` refuses with a 400 and writes no
  row) and the `odds_sweep_log` shape (a refused sweep left no trace, and
  odds fetching ran 17+ hours behind a green health check) in a third place.
  **When adding a brake, ask where its refusal is written before asking
  whether it works** - and record it as its own table, because absence never
  borrows presence's representation: a synthetic row in the presence table
  gets counted by every reader that counts presence.



Seven patterns from the session that turned unattended scouting on and
diagnosed the disk. Five of them come from `measurement-skeptic` returning
**OVERSTATED - do not enter as written** on the first draft of the
measurement, before it was committed. The audit was right on every count
that mattered, and the corrections are worth more than the finding.

- **When a diagnosis has candidate locations, ask which instrument separates
  them at zero cost - and run that one first.** The handoff named `db-sizes`
  (`WALKS_THE_FILE`) as the next step for "what grew?". But two of the three
  candidate homes for the missing 1.22 GB were not inside the database at all
  (a WAL that could not checkpoint; a leftover `VACUUM INTO` copy), and
  `inspect_live_disk.py` separates all three for **nothing** - `statvfs`,
  `walk` and `stat`, never opening a file it lists. It killed both
  non-database hypotheses (the WAL was 3.4 MB against a 1.22 GB question)
  before one expensive page was read. The free read was also the
  **like-for-like** one: it is the instrument that produced the baseline file
  size being compared against, which `db-sizes` is not. **Order the
  instruments by cost before ordering them by how much you want the answer.**

- **Before spending a `WALKS_THE_FILE` read, grep the record for what the
  LAST one was asked to also collect.** `docs/measurements/2026-09-18-where-the-database-bytes-are.md:104-111`
  ends: *"One extra column on the next `db-sizes` run settles it"* - meaning
  `dbstat.unused`, which separates "rows were added" from "pages bloated".
  The next `db-sizes` run was 2026-09-21 and it went **without the column**.
  A whole-file walk was spent, the desk lost its page cache, and the question
  that walk had been queued to answer is still open - which is exactly why
  the diagnosis came back "two explanations, cannot separate them". **An
  expensive instrument accumulates a to-do list in the documents that last
  used it, and that list is not attached to the instrument.**

- **A cheap moment to spend a cache flush and a quiet moment are the same
  moment, so choosing the reading on cost is choosing it on the outcome.**
  The third file-size point was taken over 14.1 hours "ahead of the kickoff
  windows", got 26.7 MB/day against a flagged 580, and was written up as
  falsifying it. That window is Sunday evening into Monday morning - the
  quietest stretch of the football week - while the 580 window held the whole
  Saturday college slate and the whole Sunday NFL slate. Both growing tables
  are duty-cycled to game action by design (`kalshi_quotes` is a change log
  that writes only when a price moves, ADR 0055; `odds_snapshots` drops to
  the hourly floor unattended). **A 22x ratio is what a *stationary* recorder
  with that duty cycle predicts.** A re-measurement must be **phase-matched**
  to what it is re-measuring: same clock time on consecutive days, or a
  window holding exactly one of each weekday. Adjacent is not comparable.

- **Correcting someone else's comparator choice is itself a comparator
  choice, and it runs the same risk in the opposite direction.** The draft
  accused the previous session of quoting 580 against "the registered
  ~85-110 MB/day" - the smallest of three circulating quantities, which
  maximised the gap - and re-framed it as "1.8x" against
  `CURRENT_GROWTH_RATE = 326.6` (`backend/store/volume.py:149`), "the
  constant the system actually runs on". But 326.6 was measured **2026-09-09,
  before the dedup shipped**, and its own comment says it is expected to fall
  to ~142. So the draft picked the comparator that *minimised* the gap, while
  accusing its predecessor of picking the one that maximised it, **on a
  result that was good news.** Against the post-dedup expectation, 580 is
  ~4-7x and the predecessor was approximately right. **When a name covers
  three numbers, print all three with what each was measured on and when -
  do not pick one and call it "the" registered rate.** (CLAUDE.md's
  `actionable` rule, on a new quantity.)

- **A prune in perfect health and a broken prune look identical from outside,
  because a prune's instruments are scoped to the rows it is allowed to
  touch.** `kalshi_quotes` grew 0.80 GB in three days while `prune-frontier`
  reported `backlog_rows 0` and a frontier **54 seconds ahead of** the 3-day
  cutoff - flawless, and ~53 M rows deleted over its life. The growth is in
  the **exemption**: `retention.py:231` spares any quote whose ticker is in
  `recommendations`, that table has no `DELETE` anywhere, so the spared set
  is strictly monotonic and is now 26.2% of all rows. **When a table with a
  retention rule grows, measure the exempt population, not the prune's
  progress.**

- **Two mechanisms that predict the same observation are not a finding, and
  "the next reading will tell us" is only true if it can.** The draft argued
  the exemption set was too small to explain 0.80 GB (4.6 M rows needed
  against 3.04 M exempt, at the family's average 172 bytes/row) and concluded
  the season must also be contributing. Inverted, the exempt rows alone cover
  it at 263 bytes/row - a factor of only 1.53 - and page bloat in a
  continuously-pruned random-order index covers it completely and
  independently. The signature was in the draft's own numbers, reported as
  corroboration: index +79.3% against table +57.7%, and a freelist that
  quadrupled. Worse, the planned follow-up (`MAX(rowid)` differencing) is
  **blind to fragmentation**, so the stated decision rule - flat inserts plus
  rising bytes implies the exemption - names the fragmentation signature and
  reads it as the opposite. **Before writing "the next reading separates
  them", check that it separates them.**

- **A guard can be green because it cannot see the failure.**
  `tests/test_a_question_for_joe_has_a_ticket.py` passed on a measurement
  that raised a decision only Joe can make and carried **no ticket at all**.
  It refuses a `Question for Joe:` marker without a number; it cannot refuse
  a *missing* marker, so the omission that the rule exists to catch is
  precisely the one it is blind to. The audit caught it, not the suite.
  Related, same session and same shape: the standing "never hand-type a git
  sha" lesson was applied correctly on the deploy path and then violated in a
  **GitHub issue close comment** - permanent, public, and read by future
  sessions as fact. **Apply a lesson to every surface its hazard reaches, not
  to the one where it first burned you**; the tell is identical everywhere -
  a sha not pasted from a command's output in this session.

- **A test that picks its branch from the AMBIENT environment is a
  coincidence, not a guard - and "green here" proves nothing about there.**
  `_q_db_sizes` wraps its `dbstat` query in `try/except OperationalError`.
  This repo's dev `sqlite3` (3.45.1) has **no `dbstat` compiled in**; CI's
  interpreter and the deployed image both **do**. A lane wrote fallback
  tests that exercised the except branch "for real, with no monkeypatching
  needed" - true locally, false on CI - and **three tests went red on CI on
  a commit whose production code was correct and had already served a good
  live reading**. Two rules fall out. **Force the branch you claim to
  cover**: a connection subclass whose `execute` raises on the exact
  production statement (`sql.startswith(_SQL_DBSTAT)` - narrow, because a
  build without the vtab can still `CREATE TABLE dbstat`) makes both
  branches reachable from either interpreter, and where a path genuinely
  cannot be forced, assert only the invariant that holds on both. And
  **never write a guard that fails when the environment gains a
  capability** - the lane's `assert _real_dbstat_available() is False` was
  meant to flag a stale skip and instead turned more coverage into a red
  build. The related over-claim is worth naming too: the finding was
  reported as "the real branch has never been exercised, locally or in CI."
  Only the local half was true. **A capability absent on your machine is
  not absent everywhere - check the other machine before writing "never".**

- **A test of an interceptor must send the traffic the interceptor is aimed
  at - and the fix for an environment-coupled test can be environment-
  coupled in the same way.** Having diagnosed the above and written
  `_NoDbstatConnection` to FORCE the fallback, the test proving the
  interceptor works probed it with an ad-hoc `SELECT * FROM dbstat` while
  the interceptor was deliberately pinned to `_SQL_DBSTAT`. It never
  matched. Locally the probe raised anyway - this venv has no `dbstat` at
  all - so the test passed **without the interceptor ever running**, and CI
  returned `DID NOT RAISE`. **Two CI runs, ~20 minutes, to the same class of
  bug in the fix for that class of bug.** Three habits fall out, all cheap:
  drive the assertion from the **subject's own output** (read the emitted
  title to learn which branch ran, rather than re-probing the environment
  and assuming the two agree); **simulate the other environment locally**
  before pushing - here, a plain table named `dbstat` makes the success
  branch reachable on an interpreter that has no vtab, and that one probe
  would have caught both failures; and when a test passes, ask **which line
  would have failed if the thing under test were absent.**

- **Never put prose through `bash -c "..."`; backticks inside a
  double-quoted shell string are COMMAND SUBSTITUTION, and the loss is
  silent.** Twice in one session a Python one-liner that wrote Markdown was
  invoked as `python -c "..."`, and bash expanded every `` `backticked` ``
  term before Python ever saw the string. Both times the write "succeeded" -
  it printed `updated` - and every code-span in the result was **replaced by
  empty string**, leaving grammatical sentences with the identifiers missing:
  *"so `` `` 's real branch"*. The second occurrence also executed fragments
  of the file's own contents as commands, including a bare `flyctl`, an
  `unlink` and a `truncate`; they failed only because they had no operands.
  This repo already carries "heredocs mangle backslashes - use Write for
  regexes"; the same hazard reaches **any** shell-quoted content, and
  Markdown full of code spans is the most exposed thing there is. **Write
  prose with the Write or Edit tool, always.** The tell after the fact is a
  sentence that reads fine but has a gap where a name should be.

---

## 2026-09-20 (second) - A constant in the source beats a week of sampling; a plan shape is not a cost in either direction; and a Done-when can expire with nothing going red

Five patterns from the session that answered #116 without the week it had
been told to wait for, and timed two index changes on live.

- **Before scheduling a measurement, ask what BOUNDS the quantity, not what
  it usually is.** #116 asks how much unattended scouting costs a night. The
  previous session took one reading (9 fixtures), correctly said one reading
  is not a rate, built a 7-day series and parked the ticket behind "a deploy
  first and then a week". The binding number was a constant: `CARD_SHAPES`
  is nine fixed recipes whose `max_legs` sum to 30 at one leg per game, so a
  night's ladder can carry **at most 30 distinct fixtures, ever** - no
  sampling, and true of every future night as well as every past one. A
  sample describes the nights it saw; a structural ceiling describes all of
  them.

- **An instrument built to answer a question can measure the question next
  door, and its own docstring may already say so.** `ladder-fixtures` was
  built for #116 and counts fixtures with a fresh team-market leg - the
  candidate **pool**. The convener walks the ladder **payload's** distinct
  fixtures (`scout_watch.py:178`, the same `build_ladder_payload_widening`
  the route calls). The gap is an order of magnitude: 135 in the pool on
  2026-09-08 against 6 on the cards. The docstring said it plainly - "best
  read as a loose UPPER BOUND ... not the number the ladder actually built
  cards from" - and the handoff still carried it as the number Joe would be
  asked to fund against. **Open the line of code that CONSUMES the quantity
  you are funding, and check the instrument computes that one.** Reading the
  consumer also found that the watcher calls the *widening* builder, so
  "tonight's ladder" is tomorrow's games whenever tonight is empty - a
  property of the flag nothing in the ADR or the ticket stated.

- **"It scans the whole index" is not a cost claim, and a plan shape is not
  a stopwatch - in BOTH directions.** This record already carried `2e66f36`,
  where an index was dropped because a plan said it changed nothing and had
  to be restored: *"the plan was never the cost."* Tonight the mirror image.
  #87 added a `WHERE` to bound a `GROUP BY odds_snapshots` whose plan said
  SCAN, the plan afterwards said SEARCH, and the stopwatch on live found
  **no improvement at all** (489.3 ms bounded and cold against 423.5 ms
  unbounded and warm, row sets agreeing at 249). The reason: the aggregate
  rode a *covering* index shaped exactly for it, so the "whole-index scan"
  was one ordered pass collapsing 5.4 M entries into 1,292 groups, and
  replacing it with 930 seeks plus a scan of `event_links` is not cheaper.
  **A covering index makes a full pass cheap; 5.4 M rows over 1,292 groups
  is a ratio to check before calling an aggregate expensive.** (The fix was
  not reverted - it is correct and scales with the smaller table. What did
  not survive is the claim that it bought something.)

- **A ticket's Done-when can expire without anything going red.** #88 asked
  for a timing "run twice on live (before task 02 merges/deploys, and
  after)". #87 merged and deployed, the "before" became permanently
  unobtainable, and the ticket sat on the frontier looking runnable, because
  the board checks blockers and assignees and not whether a completion
  criterion is still *reachable*. A Done-when naming an **artifact** (a test,
  a file) keeps; one naming a **state of the world** has an expiry nobody
  wrote down. The re-spec was also the better measurement - both texts timed
  back to back on one connection beats a before/after across a deploy, which
  would confound the edit with a restart and a different cache.

- **Two registries can guard one surface from different files, and a
  ticket's named tests reach only one.** Adding a `QueryDef` to
  `scripts/inspect_live_db.py` must also be added to `SUBCOMMANDS` in
  `tests/test_inspect_live_db_modules.py`, which asserts in both directions
  so the list cannot rot into a subset. The failing file is not the file the
  query is registered in, so a targeted run of the ticket's own tests passes
  and CI does not. Both main and the Sonnet lane hit it independently in one
  evening. **When a change adds a NAME to a surface, grep the tests for an
  existing name on that surface before running anything** - the pin that
  will catch you is wherever that grep lands, not where you edited.

- **A merged lane is not a finished lane: removing its worktree while it is
  still running destroys whatever it is mid-way through.** Main merged
  `fbf8601`, applied the one fix the lane had been told to make, and removed
  the worktree - while the lane was part-way through a full-suite re-run of
  that same fix, which it had independently redone in its own tree. It lost
  the run and reported finding only an empty `.pytest_cache` where its
  worktree had been. Nothing was lost here because the work was a duplicate
  of main's, and that is luck, not design. **A lane's commit landing on main
  says its output arrived, not that the agent has stopped.** Wait for the
  hand-back, or tell it explicitly that the work is already on main and it
  should stop, before taking its tree away.

- **Before splitting a question into "his half" and "ours", re-read the
  ticket: the thing you were about to ship unasked may already be one of his
  lettered options.** The session's direction proposed shipping half of #79
  on the argument that *refusing* a suppressed parlay leg changes what Joe
  can bet while merely *marking* it does not, so the mark was ours to ship.
  #79 offers four options and **(b) is "carry the leg but mark the card"**,
  framed as a trade-off against (a). Shipping it would have chosen (b) for
  him and then asked him to choose. The reasoning was sound in general and
  wrong against this ticket, and only the body shows which. **A ticket that
  lists an option has already claimed it.**

---

## 2026-09-20 (first) - A lane is cut from where the session started, not from where main is; and an allowlist keyed on who names a symbol moves to whoever you hand the symbol to

Two patterns from the session that let the scout desk be sent unattended
(ADR 0180), plus two recurrences.

- **An Agent worktree is cut from the commit `main` was on when the
  session began.** Four lanes were spawned across the evening; every one
  started from the same commit, including the one spawned *after* main had
  committed the config class and schema column it depended on. The lane
  would have built against a tree where its inputs did not exist and
  reported green on tests it wrote against that tree. `git worktree list`
  shows the base beside every lane; read it after spawning. A brief that
  depends on a mid-session commit says so and tells the lane to
  `git merge` it first, and to grep for the symbol before building.

- **A billed-path allowlist keyed on which module *names* the symbol is
  moved by a factory argument.** The scanner allowlists modules that name
  `build_client`; the lane, told to "pass `build_client` as a factory",
  put the name in `scripts/run_loop.py`, and the only green fix on its
  side was to admit the whole loop script as a spender. The right fix was
  on the other side: default the factory at the site already allowlisted,
  and let the new caller pass nothing. **Whoever holds the name holds the
  ceiling's paperwork; design so the name stays where the meter is.** A
  lane executes the brief literally (2026-09-18 twenty-sixth), so this is
  a choice the brief should have made.

- **Two recurrences, recorded as such.** `git checkout <file>` to undo a
  mutation erased the uncommitted real work in the same file (the
  mutation-testing hazard already in this record); the later mutations
  restored from a `$TEMP` copy with `cmp` proving byte identity. And a
  test seeded a table with `INSERT OR IGNORE`, which swallowed a NOT NULL
  failure and left the table empty, so the test asserted `absent` for a
  game that had a briefing (2026-08-10, "`INSERT OR IGNORE` will happily
  ignore your fixture"). A lesson that recurs twice in six weeks is one the
  session start does not reach; both are now in the memory index as well.

---

# The pattern index

Every lesson ever written, newest date first, one line each. The full text of
each is in the linked archive file, unchanged; the sections marked *in this
file, above* are the ones not yet archived. Regenerate it from the headings in
the same edit as the entry — an index that is not is stale by one entry
immediately and by dozens within a week.

### 2026-10-11 — in this file, above

- A ticket that waits for a condition must depend on that condition; and a verification read covers the window it read, not the evening

### 2026-10-10 — in this file, above

- A daily ceiling lowered below the day's recorded spend is a lockout, not a cap; and a stored refusal is not a sentence for the screen
- A test that an off switch "sends nothing" proves nothing until the same input is shown to send with the switch on

### 2026-10-09 — in this file, above

- A deletion lane's red is in a registry, not a caller: run the full suite before the merge, not after
- An as-of rebuild must take EVERY input as of the time, status flags included; and a write-up quotes a registration's direction, it does not re-derive it

### 2026-10-08 — in this file, above

- A wrong number can be inherited without anyone typing it: from an old sentence, from a guess about retention, from a registration that names a clock the repo already refuted

### 2026-10-06 — in this file, above

- The failure you are waiting to capture may already be in a capture you have; a test that asserts a capture is clean pins the blind spot

### 2026-10-05 — in this file, above

- A retrying client's final status describes only its last attempt
- A fallback string that drops the exception turns an outage into a content judgement

### 2026-10-03 — in this file, above

- A budget gate that drops work without stamping it makes the work look done-and-empty

### 2026-10-02 — in this file, above

- A background wait that prints a word has to be read before the next action, and a remembered command form is the command
- A lane's "stopped at 39%, no failures" is an unrun inventory, and GitHub caps a parent at 100 sub-issues

### 2026-10-01 — in this file, above

- An open ticket is not proof the work is undone, and a pin list written from memory is not the pin list; grep for both before dispatching
- A rule the backend obeys can be broken by the screen's fallback sentence; check every hand-written failure string on a spend path against it
- A retention rule can quietly cut a registered measurement's population; list the registrations that read a table before shortening how long it is kept

### 2026-09-30 — in this file, above

- Parallel lanes pass their own tests and break each other's pins; run the full suite on merged main before every push
- A restatement of a threshold can silently change its unit; a correction lands in one place and every restatement keeps the old claim
- A model seat does not know what day it is unless the prompt says so; a refusal that writes no row reads as "never asked" once the screen reloads

### 2026-09-29 — in this file, above

- Two writers of one column must share the derivation; an asyncio lock guards one process; a module nothing reaches merges together with its caller
- A covering index makes each row cheap, not the range small; a cited line in a "does not establish" note is still a claim; an absence needs a grep of the writer
- Batching N reads into one widens the blast radius to N; one client cannot tell its own path from the far side; check a bind address before planning an arm on it

### 2026-09-28 — in this file, above

- A look recipe written for neutral counts does not transfer to a money result; merge approval covers the PRs it named

### 2026-09-23 — in this file, above

- A field named for one meaning often carries several: filter on the codes the decision names, never on non-empty; and a figure told to the user is one they can act on
- A SQL fragment copied from a sibling query carries that sibling's column meaning; and a lane's test count is read, not quoted
- A claim about how a counter behaves across a restart is a claim about where it is stored; and a number spliced from a registration carries its errors with it

### 2026-09-22 — in this file, above

- An ordering recorded only in a ticket's prose is invisible to the board that dispatches from it; a scheduled task that must wake the machine depends on power-plan state its own XML does not show; and a result document written before its data is a registration one level down
- A fixed-window reading nobody can attend is taken by two schedulers with different failure modes, and the rule for choosing among their reads is registered before any of them fires; an amendment's number is read from the file it amends
- A pass placed behind a liveness gate never runs on the population it is for; an invariant a sibling table got at birth may be structurally unavailable to the one you extend; and a new write ahead of a cycle's decision variable inherits that variable's default on failure
- Read a ticket's Done-when against the tree before dispatching it; a Must-not-touch can contain a file the change falsifies; a loose prefix turns a drift guard into a phantom-defect reporter; and the machine's clock is not the clock
- A venue action takes its population from the venue at the moment it acts; a board's READY count can be eleven and dispatch nothing; and a dated count in a code comment decays like one in a doc
- A new read on a request path inherits the old read's population or it drifts; and a tripwire on a shared symbol fires for whichever path reaches it first

### 2026-09-21 — in this file, above

- A deadline can expire into a missing instrument; a ruling recorded only as a ticket comment decays like a question recorded only as a line; and a guard with a backstop behind it tests green either way
- A cheap reading and a quiet reading can be the same reading; correcting a comparator is itself a comparator choice; and an expensive instrument may already have a column queued onto it

### 2026-09-20 — in this file, above

- A constant in the source beats a week of sampling; a plan shape is not a cost in either direction; and a Done-when can expire with nothing going red
- A lane is cut from where the session started, not from where main is; and an allowlist keyed on who names a symbol moves to whoever you hand the symbol to

### 2026-09-19 — [`archive/lessons-2026-10-10.md`](archive/lessons-2026-10-10.md)

- A queue that lives in prose is re-derived every session; a queue that lives in tickets is dispatched -- and a brief that names a sibling lane's deliverable as existing sends the lane to check

### 2026-09-18 — [`archive/lessons-2026-10-10.md`](archive/lessons-2026-10-10.md)
- A fake that models the venue's good behaviour cannot test the guard against its bad behaviour, and a fixture can exclude a case by arithmetic nobody wrote
- A docstring that says a thing has never been observed is a claim about a date, and other modules quote it as if it were about the world
- a check handed forward is a to-do, a citation is a claim, and a clock that counts free space has to name the filesystem
- A justification can decay into being RIGHT by accident, and an agent drifts from a convention it cannot be stopped from breaking
- A fresh database passes whatever the migration does, and a mutation pattern that matches twice patches the wrong one
- A fixture offset by a DURATION against a bound that is a ROLLOVER fails for a fixed slice of every day
- A stated blocker is an inference until it quotes the source; the answer is often already on disk; and a mutation that cannot change behaviour is not a weak test
- Check a money claim against a captured payload, not against the tests; and a threshold taken from the wrong clock cannot ever be false
- An index that makes a walk covering does not make it small; a read's cost should scale with its ANSWER, and a diagnostic that reads the whole file is a write to the cache

### 2026-09-17 — [`archive/lessons-2026-10-10.md`](archive/lessons-2026-10-10.md)
- A resource the browser fetches WITHOUT the cookie is invisible to a cookie gate; and an `env()` safe-area term is 0 until something opts into it
- Commit BEFORE you mutate, every time; and a venue that says no is not a venue that went quiet
- A state whose name sounds final is not evidence of the thing it sounds like; only the state that moves money is
- A census of the surface you happen to read is not a census of the mechanism; an empty book can mean "quoted elsewhere"
- A document that must describe a guarded format will quote it and then claim it did not; name the canonical file instead of restating the form
- A deploy verified at the moment it happened stops being true if anything merges after it; and "the executable queue is empty" is a claim about how many queues you read
- Before extending an instrument, read what its tests FORBID it from emitting; a registered instrument's scope is a contract, and the obvious extension is the one that breaks it

### 2026-09-16 — [`archive/lessons-2026-10-10.md`](archive/lessons-2026-10-10.md)
- A mutation that changes nothing reports the same green as a guard that is watching; the harness has to refuse the no-op, and a mutation that only ADDS to a pattern has not disabled it
- A median does not bound a tail, so a measurement of the centre cannot falsify a condition written about the worst case; and the regime you can measure cheaply is usually the one where the effect is known not to occur
- A copy guard that pins a field by NAME pins the name, not the claim; and a correction trail that quotes the killed phrase re-triggers the guard while a line-wrapped one dodges it
- When a universal dies, a test on one surface certifies nothing about the others; enumerate every surface that carries the sentence and sweep for strays
- An unasked question decays into the measurement that produced it, because the measurement is the part a session can execute alone
- A before/after measurement taken thirty minutes apart is a drift measurement; interleave the arms or do not compare them
- A copy that restarts whenever its source is written cannot outlast the writer's cadence, and it reports the restart as progress
- The planner can DECLINE an index; before pricing one, check which plan it actually picks -- and ask whether what is missing is statistics
- A merged lane is not a finished lane; do not remove a worktree until its agent has reported
- A bound you can read in the SQL is a hypothesis about the planner; EXPLAIN the before, the after, AND the no-flag case
- When an input and its measurement both exist, read the measurement; the input can only flatter or frighten
- A dispatch whose branches return identical results cannot be guarded by a test that reads the results

### 2026-09-15 — [`archive/lessons-2026-09-18.md`](archive/lessons-2026-09-18.md)
- A comment that names future work becomes a phantom backlog item the moment that work ships
- When a call changes what it SENDS, the row that records it is part of the change
- A cost lever is proposed from the formula and must be validated against the data; the multiplier may be carrying something
- Fix every reader in the function, not the one whose symptom you saw; the card that would have shown the other one may be the card nobody taps
- A write-up drifts toward the flattering sign; a count copied from the spine is a count nobody re-read
- EXISTS does not short-circuit for the rows that fail it; when one parameter value is fast and its sibling times out, the plan is walking the non-matches
- A refusal carries its premise; before inheriting the refusal, re-read the premise against what the record now holds
- A guard that pins a coordinate goes red on an unrelated edit; update the pin, never loosen the guard, and say in the pin what it is really guarding
- A warning improved but not persisted is the same warning; when you fix what a log line says, ask what retains it

### 2026-09-14 — [`archive/lessons-2026-09-18.md`](archive/lessons-2026-09-18.md)
- The steps after a refusal run only on the first success, and an "unexplained" venue response is a claim about your own request until you have re-read it
- A measurement of a state is not a property of the system, and the tell is a sentence with no "while" in it
- A remedy is a claim about the world, and it decays faster than the code that names it
- A sentence that explains a number must be selected by the predicate that produced it, and a refusal's remedy has to travel to the screen that shows it
- A load-bearing count is named with its table, because collapsed quantities survive review by looking consistent
- A wall-clock time in a registration is not a schedule; it is a person, and the person must be named

### 2026-09-11 — [`archive/lessons-2026-09-18.md`](archive/lessons-2026-09-18.md)
- Before a missing number becomes a migration, check whether the row already determines it
- A caveat that names one error term is a claim about all the others
- Never hand-type an identifier into the mechanism whose job is to report identity
- A screen whose content depends on sweep phase will be mistaken for a property of the slate
- A reachability guard that walks modules cannot see an orphaned symbol inside a reached one

### 2026-09-10 — [`archive/lessons-2026-09-18.md`](archive/lessons-2026-09-18.md)
- "Cold start variance" was two states with one name, and the warm reading was the one I took first
- A component that swallows every error needs a test more than a loud one does
- An index that changes no plan can still change the cost by orders of magnitude; EXPLAIN reports the method, not the rows
- "The query admits this market" is not "the desk holds this market", and only one of them is a fact about live
- A rewound clock turns an indexed query into a cold-file scan
- A warning keyed on a count the failure itself suppresses goes quiet exactly when it is needed
- A test that pins a predicate's spelling blocks the fix that keeps its claim
- When one blocker is expensive, look for the free one; the expensive blocker gets all the attention
- A guard test needs a bed where the UNGUARDED code would answer differently; "both paths refuse" is not that bed
- A stopping rule that names an outcome manufactures that outcome, and the arm it names will look like the finding
- An operation that reads can also write, and "it spends no money" is not the test for whether it is inert
- A read-only scan on live is not free for the desk: it evicts the page cache, and the next reader pays for it
- The cost of a scan is not its wall-clock, and a floor widened for a correct reason still has to be re-timed on live before it ships

### 2026-09-09 — [`archive/lessons-2026-09-18.md`](archive/lessons-2026-09-18.md)
- The column you exclude from a comparison key is where the duplicates' real payload hides
- Mutating a constant tests nothing unless every consumer actually derives from it
- A lane's green suite is a weaker claim than main's, and this repo skips its integration guards off the integration branch on purpose
- An append-only record reports the last state it saw forever after that state ends, so "the newest row for X" cannot see X going away
- A decision that turned on a named consumer must be re-opened when the consumer is never built, and nothing notices that it was not
- A replay test can pass through the crash point the guard is for, and then the guard is unverified while the test's name says otherwise
- A true sentence with the wrong scope cannot be caught by any guard that checks its facts, and a sourcing guard makes that harder to see rather than easier
- A test can enshrine the defect as intended behaviour, and then the guard's absence is *documented* rather than merely missing
- Arming an entry without arming its exit is a whole class of defect, and the linkage columns are usually already there
- Re-verify a question before asking it, not just a task before doing it - and never `Write` to a path without checking what is there
- A justification decays into a lie, and the one most likely to is the one that explains why something is safe to leave undone
- A helper with no caller may be the *losing side of a decision*, not an unrun feature, and only the neighbouring docstring tells them apart
- A test that `skip`s on missing input cannot tell a legitimately absent case from the regression it exists to catch
- `flyctl ssh console` starts a shell that does NOT carry the app's Fly secrets; the credentials live on the app's own child process
- A push may cancel an in-flight CI run only when the new tree strictly contains the cancelled commit, and a rule with a redundant clause is worse than no clause
- An exemption list groups by syntax, not by kind, and the dangerous member is the one that merely looks like the safe ones
- A tool's summary of its own scan describes the state before the scan you just triggered, and its per-item verdict can be wrong in the safe-looking direction
- A config value can be malformed in a way that reads as fluent English, and the artifact then does not exist rather than failing

### 2026-09-08 — [`archive/lessons-2026-09-11.md`](archive/lessons-2026-09-11.md)
- A spine that records its own corrections inline grows without bound, and the corrected fact is the only part a session needs
- "This route has no guard" is a claim about the whole dependency chain, not about the route body
- A guard that reads the code but not the decisions is half a guard
- Removing a brake server-side leaves it on the screen, and that direction of the mismatch is invisible
- A count or a "not yet" copied into a new session entry is a present-tense claim from a past reading
- A consumer that restates a predicate is not covered by the test that pins it
- A mechanism that relabels spend is not a saving
- A mutation that stays green has two readings, and only the code tells you which
- A capture script that reads the environment captures the laptop, not the deployment

### 2026-09-07 — [`archive/lessons-2026-09-11.md`](archive/lessons-2026-09-11.md)
- "It might be slow" is not a tolerance; find the bound
- "Expect the count to fall" is a claim about a delete that may not exist
- An instrument is not verified until it has been run against the real data once
- The check and the instrument for the check are two deliverables, and only one of them gets planned
- A screen that names one failure lets every other failure wear the quiet's clothes

### 2026-09-06 — [`archive/lessons-2026-09-11.md`](archive/lessons-2026-09-11.md)
- Two true docstrings, one false conjunction
- A caveat loses to the variable name it sits under
- A test that restates the code's own formula agrees with the code whatever the code says
- A guard that substring-matches an element name is green on a renamed element
- A hand-typed sha is a fabricated sha, and noticing that it looks wrong is not the same as checking it
- A section truncated by `head` looks exactly like a section with no rows, because the header prints before the data
- A scripted edit meant to change a few bytes rewrites every line ending in the file, and a normal diff cannot show it
- A date-triggered falsifying check must be dated from the event's END, and from a looked-up calendar rather than a remembered one

### 2026-09-05 — [`archive/lessons-2026-09-11.md`](archive/lessons-2026-09-11.md)
- A stub that assigns over a property tests the assignment; the SDK's own parser is the only thing that runs the SDK's parsing
- An error handler ordered after a call that raises is not an ordering, it is dead code with a comment explaining it
- Audit each item of a list you were handed; "three of X" is a claim about all three
- Reading the aggregates to scope a measurement is what disqualifies them from being its result
- A `--` comment inside a CREATE TABLE column list breaks DROP COLUMN, and the failure names a table the change never touched
- When a guard asserts the mechanism instead of the property, the fix that changes the mechanism looks like a regression
- Test at the level the defect lives; a substring test cannot tell a mention in a live branch from a mention in a dead one
- A link is a claim about its destination, and only the destination knows whether it can keep it
- A deadness grep scoped to the source directories misses the callers that matter most, because the loudest ones live outside them
- A clean merge is a statement about text; two lanes can each be right about a file and wrong about each other

### Removed as duplicates 2026-09-08 — [`archive/lessons-2026-09-08-dedup.md`](archive/lessons-2026-09-08-dedup.md)
- An item written from the shape of a known lesson is a hypothesis, not a finding
- `git checkout <file>` restores the INDEX, so it deletes uncommitted work while looking like an undo
- `assert str(CONSTANT) in text` passes just as happily on a typed digit, so it does not test that the text is sourced
- Run a new guard against the code before the fix; a green suite proves the test agrees with the fix, not that it would have caught the defect
- A test that recompiles identical bytes once per case is a tax on every future run, and the fixture that fixes it is three lines
- A guard that greps for a component name finds the comment explaining the component, and a prefix is a substring of every longer identifier
- A "has a caller" check is only as deep as its walk, and a one-level walk is satisfied by a referrer that is itself dead

### 2026-09-04 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- An absence pin that greps for a literal name finds it in `__pycache__`, because CPython folds `"a" + "b"` at compile time
- A rate limit is a pause, not a loss: an agent with a worktree resumes with its context
- "The largest contributor" is a set until proven a singleton, and `max()` on a dict picks a member silently
- A precondition written as the failure of one named mechanism does not fire when a different mechanism fails the same way
- A date read off a local clock is a different date; every registered instant is UTC
- A fixture set that only ever states the deployed value cannot detect a hardcoded copy of it
- Match a source anchor against the file's own line ending; a normalising reader will tell you it exists when a byte reader cannot find it
- The session scratchpad is shared across parallel lanes

### 2026-09-03 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- A counter that emits on a cadence while a condition holds measures the condition's duration, not its occurrences
- "One predicate, two spellings" is an architectural fault, not a run of incidents
- A binder proposed from a remembered lesson is a hypothesis, and it enters the record only after the check
- A screen promoted into a slot inherits the slot's traffic, not the old screen's fixes
- A gate that mounts a self-heal only when the screen is empty stops healing the moment it has anything

### 2026-09-02 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- A link to a screen is a claim that the screen exists, and the claim is pinned or it rots
- "Restore the guard" with `git checkout` restores the COMMIT, not your edit
- When a single look is registered, the look that counts is the FIRST one past the stopping rule
- A retention cap on a diagnostic file is a deletion of whatever measurement reads its oldest lines
- Before ranking work on a screen, read the instrument that says whether anyone is looking at it
- A doctrine comment is a claim about the tree; grep before citing it

### 2026-09-01 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- Under `set -e`, a guard downstream of an abort is decoration
- Isolate any subagent that WRITES, not just one that mutates code
- A test that asserts copy's TEXT freezes it; assert its SOURCE
- A clearing statement in an ADR is a claim about a population, and needs its boundary as precisely as a finding does
- A CI run that reports on your branch may not be reporting on your commit
- Adding a SHAPE to a shared artifact is a wider change than adding a field
- A registration's "what we cannot measure" list is a claim, and getting it wrong retires the falsifying test
- A subagent with Bash mutates the tree you are committing from
- Check a ticket against the tree before scheduling it
- A flag whose TRUE value has two causes is not an instrument, however carefully it is recorded
- A test that addresses its subject by POSITION can keep passing against the wrong subject
- Find the change point before you name the cause
- A group selected by an outcome cannot report a rate on that outcome
- A writer with no reader is an instrument that does not exist

### 2026-08-31 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- A cost that does not change with the row limit is not in the rows
- A header you set is not a header the framework sends
- A guard on the code must not be able to read the comment beside it
- Text can overflow a correctly-sized box, so hunt overflow with scrollWidth and not with rects
- A fix that does not move the number has not been shown to work
- A layout measurement measures tonight's data as much as the CSS, so one clean read is not a clean bill
- A tool that reports success has not necessarily done anything; measure the state it claims to have set
- Code and its own comment agreeing is not verification; both can be wrong together about the rule they serve
- A test named for a relationship between two artifacts must read both of them
- A number cannot be checked against itself, so put a second independent rendering of it on the same row
- A component that inherits its type size has no typography
- Never hold a database write transaction across an `await` that does I/O
- A wording rule can be defeated by typography, and no source test will see it

### 2026-08-30 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- Split a before/after on evidence of the change, never on when you think you made it
- A test double that is kinder than the real object hides the bug it exists to catch
- When two code paths can produce the same end state, an assertion on the state guards neither
- Check the REGRESSOR moved before you read the outcome; a constant explains nothing
- An instrument sampled at pass START repeats itself when a pass fails, and the repeat is the signal
- When you change a cadence, re-read every predicate that compares against a timestamp it produces
- A test that names a symbol is not a guard on that symbol
- A failure recorder that shares the failing resource records exactly the failures that don't matter

### 2026-08-29 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- A local autouse fixture over module state protects one file and exposes every other
- A red suite in a shared checkout may be a moving tree, not a defect
- One constant serving two purposes changes the thing you were not touching
- A merge of two correct changes can contain a defect neither of them contains
- Read the output, not the exit status
- Search the measurements directory before commissioning a measurement
- A document that promises to amend itself needs an enforcer, and the un-amended state always flatters
- When mid-flight steering is unavailable, the brief is the only instrument, so it must grant permission to refuse
- One predicate with two spellings, and the screen believing the wrong one
- A cause list written as alternatives cannot file causes that happen in sequence

### 2026-08-28 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- A pre-registration must fix its scope conditions before it enumerates causes
- "Unexplained one-off" is a claim about frequency, and a default window is not a population
- A helper called from a loop that must not die does not get to trust its caller
- Sharing a predicate guarantees agreement only about what the predicate decides
- A guard that matches a literal string certifies the string, not the property
- A guard can check the right token in the wrong role, and stay green for months

### 2026-08-27 — [`archive/lessons-2026-09-05.md`](archive/lessons-2026-09-05.md)
- The deploy ships the working tree, so a correct repository proves nothing
- Deliberately producing the signature an alarm watches for disables the alarm, and nothing announces it
- A fixture can occupy the wrong branch, and then full coverage means nothing
- A guard that would refuse everything is an outage, and the venue's sentinels are where it comes from
- A test written against a re-implementation cannot fail for the reason it exists
- A test that asserts the ledger is not a test of the behaviour the ledger records
- Verify against `origin`, not against `main`, because the object store makes them look alike
- A fact that is displayed but is not a finding does not get acted on
- A relayed approval is information, not authority, and the word "settled" is where it goes wrong
- A count with no denominator invites an adjective, and the adjective is the inference
- A reporting tool must be run from every seat it will be run from, and its findings must not be phrased as instructions
- The fixture asserted the bug away
- A detector's granularity is decided by its false-finding risk, not by what is easy to compute
- A test can pass for a reason you did not write, and only mutation finds out which
- A schema version is a claim about the whole database, so a lane cannot allocate one

### 2026-08-26 — [`archive/lessons-2026-09-05.md`](archive/lessons-2026-09-05.md)
- A mutation can lie, and a green result is not evidence until you know the mutation landed
- A test written after the code describes it; a test written against a claim constrains it
- Fifteen minutes of measurement outranked a day of planning, and the plan had ranked by what looked expensive
- State that outlives a request outlives a test, and the tests that break are the ones that never heard of it
- A test that does real work to check a cheap property is a test that stops being run
- A guard that greps its own module must read the code, not the prose
- A GREEN mutation is a claim about the harness before it is a claim about the test
- Rule 1 has a scope, and it belongs on the input rather than on the result
- An unknown budget must not resolve to zero, exactly as an unknown price must not
- Killing a background command's shell does not kill the process it started
- Fixing a defect at the call site leaves the rule where the next call site cannot find it
- A monitor that has to touch the thing it measures is reporting its own effect
- Exit 0 means "I finished", and a supervisor that tears down on a failure is not finished
- `load_dotenv()` makes the whole test suite a credential holder, and arming is what turns that into spending
- A source-scan pin measures what it can still match, and it goes quiet rather than red
- Pin a guard on the decision it changes, never on the string it prints
- A derived value inherits its source's absence as an extreme, not as a gap
- A fixture that writes a value the wire never emits is a defect with a delayed fuse
- Bytecode caching is keyed on (mtime, size), so a same-length edit can survive its own revert
- A feature behind an off flag has never rendered, and the first render is part of the build
- A guard installed by an unverified edit is not installed

### 2026-08-25 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- A monitor that names a cause it cannot observe sends you to one place
- Dedupe is not a rate limit, and the difference is who supplies the churn
- A total is not a breakdown, and two spot checks cannot see a flip-flop
- Measure the cost of a thing you put on the fast path, before it is on the fast path
- A gap the length of your own timer is a timer, not a fault
- A refusal that names its own predicate describes a symptom, not a cause
- The only thing left in a quiet log is not the thing that quietened it
- Fixing a lie can move it rather than remove it
- A test fixture that spends is also a fixture that paces
- A registered rule implemented as an optional parameter is not implemented
- `G` is not evidence; leverage is

### 2026-08-24 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- An access-control finding names the layer it was read at
- A baseline taken while you edit is not a baseline
- A pin verifies the shape you saw, not the branch you rely on

### 2026-08-23 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- A wire format that was pinned but never exercised is a belief wearing a pin
- A pinned fixture clock against a wall-clock instrument is a test with an expiry date
- "The screen shows X" must come from the screen, not from the database that feeds it

### 2026-08-21 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- A field written after the spend is not a spend gate
- When a rule and its floor are defined over different units, the smaller unit's zero-information observations vote

### 2026-08-20 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- A stored number answers the question it was stored for, not the question you are asking now
- Log redaction does not reach exceptions: raise_for_status prints the URL, key and all
- A claim about git state is verified with git, never asserted from prose
- Two readers can share a word and not a definition, and the disagreement will be filed as a stale value
- A status that can only be stamped after an event must never be stamped by a clock alone
- Undo walks run in reverse, and a walk that happens to work forwards is a latent bug, not a working one
- Fixing a stale-flag read at one use site does not fix the flag; every other reader is still wrong
- A number that explains a mystery is captured and committed the day it is seen, or it is a rumour
- When local and CI disagree, do not ask which to trust. Ask which one matches production, because the answer can be neither
- "One source of truth" is a claim about the *clock* as much as the source. A flag written at the end of a step and read at the start of the next is already two clocks
- A job that only runs when a gate is open looks exactly like a job that has died. Poll the thing that says it ran, not the thing it changes

### 2026-08-19 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- A schema change costs its time at boot, under a health check that does not wait; and rehearse the migration before writing it
- `GROUP BY` treats NULLs as equal; a `UNIQUE` index treats them as distinct. A guard written on the all-NULL case cannot see the difference
- Do not diagnose a resource-starved machine by consuming that resource; and a process that is *stuck* looks nothing like a process that is slow
- A read-only handle to a WAL database reports the last checkpoint and calls it the present; and "the file stopped growing" is not "the table stopped growing"
- An error message names the hop it was thrown on, not the hop that is broken; and a fix is not a fix until it is measured after deploying
- A performance number expires when the thing it measured grows, and a benchmark that "isolates" a cost usually removes the cost
- `flyctl volumes list` and `df` disagreed for three days, and the optimistic one is the one you type
- "I checked and it was fine" is not monitoring, and the alarm you built is not evidence until you read the channel
- Attribute cost by measuring the parts, because the expensive-looking part usually is not
- A screenshot proves what the tab context says it does, not what the picture looks like
- Two columns that must be equal are not checked by anyone, and rendering both is what finds them
- A picture whose axis is set by its loudest number shows nothing about its quietest

### 2026-08-18 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- Find the render sites by scanning, not by remembering, and check that the guard's mutation is the one you meant
- A query plan is a shape, not a cost, and the monitoring you add is code that can take the box down
- An alert that cannot fire on the failure that happens is not coverage, and the count of alerts hides that
- A default is a decision nobody made, and it is invisible from inside the running system
- A guard written against one cause leaves the other causes uncovered, and the symptom is identical
- `git checkout <file>` is a destroyer of uncommitted work, and guard-verification is exactly when you reach for it
- The screen you verify against may be rendering a configuration nothing deploys, and a test that reads config text cannot tell you
- Hand a reviewer your hypothesis and require it to be refutable, then let it win

### 2026-08-17 — [`archive/lessons-2026-08-29.md`](archive/lessons-2026-08-29.md)

- A handoff written the night before states tomorrow in the past tense, and "the deadline has passed" is a claim that creates work
- Scrutiny was spent asymmetrically, and the unguarded direction was the one that created work
- A guard that is structurally always true reads exactly like a guard that fires, and "this condition is checked" is not evidence the condition varies
- A decision justified by a statistic computed under a *different definition* than the one the decision affects, and the codebase already had the difference written down
- An acceptance criterion carries implicit scope, and the person who sets it owns that scope
- A boundary borrowed from another subsystem answers a question it was never about, and the reasoning for borrowing it reads well
- An instrument that does not select the column its predicate turns on reports the absence of what it cannot see
- A feature and the one path that invokes it are two deliverables, and only the second one ships
- A document that has outgrown its reader is unread, and it reads as compliance

### 2026-08-17 — [`archive/lessons-2026-08-17.md`](archive/lessons-2026-08-17.md)

- A ceiling is not a spend
- `.env.example` is a contract, not a configuration
- A collective noun is not a measurement
- An exclusion count describes the filter, not the world

### 2026-08-16 — [`archive/lessons-2026-08-16.md`](archive/lessons-2026-08-16.md)

- "X requires Y" is a necessary condition, and meeting it does not elect X
- A stopping rule may only be amended in the file that registered it
- A negative claim inherits its instrument's WHERE clause
- A diagnostic reachable only through the healthy path cannot diagnose the unhealthy one
- Docker builds from the working tree, so a byte-level write bypasses .gitattributes
- An absent environment variable means the default applies, not that the feature is off
- An alias between two constants is a bet that they answer the same question
- Two identifiers that are equal by construction render as a bug
- A defect written down beside a guard is not written down in it
- A probe's request parameters are part of its finding, and they do not travel with the sentence
- A ratio against a control assumes the control is one number
- "Unreadable" and "empty" are different, and the wire decides which one you get
- A new caller that makes an existing call is indistinguishable from the existing caller
- SQLite rewrites your CREATE TABLE text, so a comment above the last column can break the table
- A default is not the behaviour, because the caller may override it — and relaying to Joe is publication
- A count that exactly equals a natural subpopulation is a bug in the counter, not a finding about the data
- Calling a registered precondition "just a diagnostic" is how the precondition gets skipped
- An agreement forced by the writer looks exactly like a clean measurement

### 2026-08-15 — [`archive/lessons-2026-08-15.md`](archive/lessons-2026-08-15.md)

- A guard copied from a neighbouring path inherits its *assumptions*, not its safety
- A cost estimated from an assumed input is not an estimate, it is the assumption restated
- A test's *invented* example can turn out to be real, and it fails on the axis it was never about
- A mutation refuted a code comment, and the comment was the thing that had to change

### 2026-08-14 — [`archive/lessons-2026-08-14.md`](archive/lessons-2026-08-14.md)

- A cleanup that did not run is invisible; the next run then canonises the damage
- The money rule is `Decimal`; an *analysis* that reconciles money in floats invents findings

### 2026-08-13 — [`archive/lessons-2026-08-13.md`](archive/lessons-2026-08-13.md)

- A derived guard covers exactly the class it derives from, and the class it cannot see looks identical from outside

### 2026-08-11 — [`archive/lessons-2026-08-11.md`](archive/lessons-2026-08-11.md)

- Mutation testing belongs in its own worktree, not in the shared one
- Scoping `git add` leaves `git commit` binding, and the symptom is unchanged
- Evidence a decision already cites is not grounds to re-open it
- An instrument whose every branch points one way is uninformative, and that is a reason to re-price it, not to cancel it
- A count written into a handoff cannot include its own commit
- A test that constructs the parameter it is checking cannot detect that no caller constructs it
- A default on a guard input is a decision about what happens when nobody knows, and on a limit it is always the permissive one
- A readout verified on the demo instance can be structurally blind on the live one
- An observability fix that stops at the API boundary has not been made
- A demo that renders healthy beside a live instance that renders empty is an argument machine for the wrong conclusion
- The file-ownership map between parallel lanes is a design artefact, and getting it wrong is the director's error
- A verdict the instrument cannot emit was written into two handoffs as a result
- The exclusion outranks the copy, and it is the copy that gets cited
- A mutation that cannot change behaviour is a green light you awarded yourself
- Two rows that name the same outcome are not a pair, and pairing them halves nothing
- A lower bound rejects correctly; it is the acceptances that are unproven
- Two artefacts that agree on the number you check are how a pin swap goes unnoticed
- A registered decision rule can be logically defective, and pre-registration is exactly what stops you noticing
- The anchor where the error vanishes keeps getting chosen, and it looks like the natural place to measure
- Fixing how a wrong row is drawn leaves the query that chose it
- A "decisions already made" list is a cache with no invalidation
- Deployment cannot be inferred from commit times in this repo
- A repeated row is not an independent observation, and the denominator that flatters a claim is usually the row count

### 2026-08-10 — [`archive/lessons-2026-08-10.md`](archive/lessons-2026-08-10.md)

- "Unblocked" is a scheduling property, not an evidentiary one
- A number quoted from your own project's prose is an assumed number
- Tracing a number to code is only half the check
- A pull can be incomplete while every check on it adds up
- A reachability guard has to run in both directions
- The guard that cannot fire on the input it was built for
- Count guard families, not guards
- The false reassurance in a comment outlives the code it describes
- Six built-never-called modules is a process gap, not a run of bad luck
- CI cost is job count and trigger breadth, not job duration
- A scanner that only reads the current push leaves history unverified
- A borrowed number must overlap the population you spend it on, in *time*
- SQL written into a document is code, and unrun SQL is a guess
- An allowlist cannot report what is missing from it
- A detector's "production" must be the deployment's "production"
- The safety was an accident of the boot script, not a design
- An empty endpoint is not an empty account
- Reachability has two halves, and this project keeps checking one
- A measurement is not new until you have grepped for its own value
- A number produced by calling a function once is not a claim about a loop that calls it ninety-six times
- A permission grant is not the guarantee it is described as
- The cheapest fix for a mutation is a mutation already scheduled
- A control that swaps the data source still shares the estimator
- Read the coverage line, not the slot list
- Consecutive date buckets tile, and overlap is the safe direction
- A command in a handoff has the status of a test never seen red
- A fixed-sample threshold quoted for a design that peeks inflates its own power about threefold
- A measurement with no committed artifact is a rumour, and a handoff can promote it to a verdict in one line
- A subagent's confident negative is the one result you must re-run yourself
- "Routed separately" names no owner, and the wrong sentence stays where people read it
- An amended registration's body is not the registration, and the superseded sentence is the one that reads best
- The power of an instrument is not the power of the question, and the gap is invisible from inside the arithmetic
- The rule about other agents' confident negatives applies to your own, and you will not notice

### 2026-08-09 — [`archive/lessons-2026-08-09.md`](archive/lessons-2026-08-09.md)

- A comment before the last column breaks `DROP COLUMN`
- Three guards, three green disable-checks, three missing tests
- A fixture that omits a new column reports the code refusing
- The population was 962; the logs showed 94, and nobody compared the two
- The counter that decides the project was behind an auth wall
- Sampling the wrong pages proves absence with total conviction
- Run the control before believing the estimator
- Two paths pinned by a test agreed, and were both wrong
- The fourth wrong wire key, and the cheap test that finds all of them
- A frozen counter is not evidence of a stuck mechanism
- A guard written to prove a property the code cannot violate
- The control that cannot reach the confound it was built for
- Two clocks that never overlap, so the test cannot be run
- A risk control can be a threshold on the wrong quantity entirely
- A measurement can be switched off by a number that is not about measurement
- An enumeration is not a proof, and "every" is the word to distrust
- A schema comment is code that nothing executes
- A guard standing behind a stricter guard is decoration
- A once-only WRITE behind an unbounded READ is not once-only
- A break that is equivalent to the original proves nothing
- "It probably fits in one page" is a fact you can just measure
- A sample whose strata do not overlap the target proves nothing, at any `n`
- A term that is zero everywhere has an unobservable sign
- A defence built for one axis of a classifier is not a defence for the classifier
- Arithmetic that reproduces to the digit says nothing about its inputs
- "Read-only" is not a scope boundary; name the environment
- The census must apply the same filter the storage path applies

### 2026-08-08 — [`archive/lessons-2026-08-08.md`](archive/lessons-2026-08-08.md)

- Deduplicating the record made the record unusable
- A rate limit belonging to one dependency was applied to both
- The user-facing explanation of a limit outlives the limit
- Two guards passed their tests on the first run, and both were broken
- Re-deriving a decision at a new price is one-sided unless you say otherwise
- Kalshi sends "0.0000", not a missing field
- A ticker's failure mode is silence that looks like calm
- A test asserted the order of a command that was not in the image
- The counter you are told to watch was counting the other population
- A wrong value that is still legal never announces itself
- A guard that fails every time says exactly as much as one that never fails
- Two implementations of one money quantity, neither ever run
- An enumeration of the safe cases is a list you will forget to extend
- The value you already had is not a value you chose
- A guard tightened for a false negative fires on the file explaining it
- `occurrence_datetime` is a shifted start, and both stories had real evidence
- A green suite that depended on what time you ran it
- A component that only exists after a tap is invisible to every check you have
- One environment variable, two readers, two different times
- Sync code that is only ever called from a coroutine
- A secret in `.env` makes the test suite behave differently per machine
- The schema file runs against databases that already exist
- An optional safety parameter is a guard that cannot fail
- One signal asked to be both an alert and a status, and oscillated
- The counter you were told to watch was filtered out at zero
- A filter's vocabulary is not the field's vocabulary
- Adding a NOT NULL column silently disarms every `INSERT OR IGNORE`
- Recovering structure by parsing free text, in a boot path

### 2026-08-07 — [`archive/lessons-2026-08-07.md`](archive/lessons-2026-08-07.md)

- Every per-cell guard can pass and the conclusion still be wrong
- Computing the right statistic and then ignoring it
- A window resize is not a viewport change
- A true measurement licensed a false conclusion
- The WebSocket path was dead and 611 tests said otherwise
- Four audits, one failure shape
- One observation recorded thirty times is one observation
- An idle threadpool hides every thread-safety bug you have
- The zero that means "no measurement" passes every threshold
- Code with no caller is not a feature, it is a plan
- A live credential can leak with nobody logging it
- Two limits on one quantity, and the tighter one wins in silence
- A captured fixture that no test loads is decoration
- The null for one proportion is not the null for a difference
- A guard that routes around thin data into a fallback built from it
- A threshold that is valid once is not valid every time you look
- `INSERT OR IGNORE` will happily ignore your fixture
- Suppressing a conclusion is not suppressing the finding
- A budget that says *whether* and never *when*
- A stored age rendered as a current one
- Two populations in one record, told apart by dispersion
- A detector that counts prose about the bug as evidence against it

### 2026-08-06 — [`archive/lessons-2026-08-06.md`](archive/lessons-2026-08-06.md)

- Unreadable must never resolve to zero
- Clamping is for values you trust
- A test that passes on the bug is not a test
- The conservative fee model is a hedge with an expiry date
- A bashism under `#!/bin/sh` is a crash loop with no cause
- Two bugs that only a running app could show
- "No result" and "rejected" are different outcomes
- A redundant special case can silently delete a whole method
- The devig spread depends on line shape, and I had it wrong
- Test that the filter's *exclusions* are decisions
- Measure the style rule before believing it
- When a document and the live API disagree, the API wins
- Kalshi may be the sharp side, not the soft one
- CLV needs hundreds of bets, not dozens
- A sign convention agreed with its own test, and both were wrong
- Synthetic data that is right on the mean and wrong on the variance
- An empirical distribution cannot be slid sideways
