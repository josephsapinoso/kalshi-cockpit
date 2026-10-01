# 0191 — Every frontend write goes through one transport module, and each call states its own no-reply sentence

**Status:** Accepted on Joe's word, 2026-10-01 (architecture review candidate C, grilled in twelve questions; every recommended answer taken).
**Date:** 2026-10-01
**Tickets:** story #258 under epic #82; tasks #259 (lane: transport + non-spending writes), #260 (main: the five spend/order writes); blocked by #257 (the minimal refusal fix, ships first)
**Leaves standing:** ADR 0164/0165 (nothing on the RFQ accept path retries; a lost response is UNKNOWN), ADR 0112 (no brakes return), ADR 0063 (the gate never reads the hand path). This ADR changes how the browser talks to the cockpit's route handlers and nothing about what those routes decide.

## 1. Why

`frontend/src/lib/api.ts` (4,593 lines, 68 commits since 2026-09-01) holds about twenty POST helpers. Each one re-implements the same steps: fetch, parse, check the shape, extract `detail`, and turn it into words. They drifted apart:

- **Three failure styles.** `{ok:false, refusal}` (e.g. `acceptComboQuote`), `{ok:false, status, detail}` (`placeOrder`, so `isLockedDetail` can read it), and `throw` (`engageLockout`, `logEstimate`, `reviseEstimate`).
- **Refusal text in two forms.** Thirteen helpers used `String(detail)`, which renders a pydantic validation list as `[object Object]`. That includes `acceptComboQuote`, the call that spends. `postHedge` alone had been fixed to use `refusalText` (#257).
- **Some calls catch a dropped connection, some don't.** Those that catch it say different things, and only the spend paths say the state may be unknown.

## 2. The decision

1. **Every write goes through `frontend/src/lib/transport.ts`.** The module is React-free and is imported by relative path (`./transport`) so the node-run tests can load it. Reads are out of scope: `get<T>` (`api.ts:668`) is already a single helper.
2. **One result shape for every write:** `{ok:true, status, value} | {ok:false, status, refusal, detail}`. `refusal` always comes from `refusalText`. `detail` is the raw body, kept so `isLockedDetail` keeps working. The three throwers convert, and their callers stop using try/catch.
3. **No default sentence for a dropped connection or an unreadable reply.** Every call supplies both as required parameters. A call that can spend says the state is **unknown** and to check the Kalshi app. A missing reply, or a 5xx with an HTML body, can mean the order reached the venue, and CLAUDE.md already rules that a lost response is an UNKNOWN, not a failure. A default sentence would let the next spend call that forgets to override it tell Joe something false.
4. **The success-shape check is optional, and today's checks are kept exactly.** The refactor adds no new checks and so changes no behaviour, which means a red test is a real regression.
5. **Scope is the transport and nothing else.** Splitting `api.ts`'s types into one file per area, and moving its formatters into one format module (review candidate D), are separate tickets.
6. **Who builds it.** A Sonnet lane builds the transport and converts the writes that don't spend (#259). The main session converts `placeOrder`, `placeManualOrder`, `acceptComboQuote`, `placeComboBid` and `cancelComboBid` (#260), under the CLAUDE.md money-path rule.

## 3. What proves it

`tests/test_every_write_goes_through_the_transport.py` covers three things:

- **Behaviour,** run under node: a string, pydantic-list and object `detail`; a thrown fetch; a non-JSON body; a failed shape check; and a success.
- **Required wording:** the two sentences are required parameters.
- **Bypass:** no `method: "POST"` remains in `api.ts` outside the transport.

Every guard is checked by disabling it and watching its test go red.

## 4. Do not

- Add a default no-reply or unreadable sentence to the transport.
- Add a retry. Nothing on the spend path retries, ever (ADR 0164/0165).
- Reword a refusal sentence while converting a call. The words move; they don't change.
