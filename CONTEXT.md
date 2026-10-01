# CONTEXT

Domain and architecture terms for this repo, one line each, with the record that defines them. Started 2026-10-01 by the architecture review. Add a term when a module is named after a concept that is not here yet.

- **Transport module.** `frontend/src/lib/transport.ts`, the one place a browser write to a cockpit route handler is sent, read and turned into `{ok, status, refusal, detail}`. Each call supplies its own no-reply and unreadable-reply sentences; there is no default. ADR 0191.
- **Refusal.** A route's "no", rendered as words by `refusalText` (`frontend/src/lib/api.ts`), whatever shape `detail` arrived in: a string, a pydantic list or an object. A refusal is not a dropped connection; on a spend path a dropped connection is **UNKNOWN** (CLAUDE.md, ADR 0164/0165).
- **Spend write.** A write that can move money at the venue: `placeOrder` (dry engine path), `placeManualOrder`, `acceptComboQuote`, `placeComboBid`/`cancelComboBid` (bid path, disarmed). The main session owns changes to these; Sonnet lanes do not.
