# lane-342-dead-screens handoff

Orphaned by this lane, not deleted (not in the ticket's list; candidates for a follow-up):
- frontend/src/lib/betDirection.ts (only TicketSheet imported it; tests/test_bet_direction.py still tests the predicate)
- frontend/src/lib/sweepTone.ts and windowChip.ts (only WindowBanner/WindowSchedule used them; their predicate tests remain)
- lib/api.ts: edgeTone / EDGE_TONE_CLASS / hasSuppression may now have no component caller (test_board_screen still pins them)
- Stale comments naming deleted components remain in ManualTicket.tsx, Sheet.tsx, Hint.tsx, Term.tsx, lib/proxy.ts, lib/suppressionGloss.ts etc.
- Removed glossary keys `ev` and `fill` (rendered only by deleted pages; test_glossary_coverage orphan test).
- Removed wire types Dashboards, Ledger, Suppression, RecentEstimate, StudyStop, EstimateLogged, OrderPlaced, OrderQuote, OrderResult (Board kept: SlateData uses Board["slate"]).
- scripts/fetch_live_route.py:82 (/api/board) left as an API entry.
No backend file touched; #347 can remove the dead routes.
