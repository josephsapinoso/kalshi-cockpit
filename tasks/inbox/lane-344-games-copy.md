# lane-344-games-copy handoff

Needed from main (not touched, out of lane):

1. `backend/api/routes.py` ~line 1669 (picks block): serve the withheld ask as a
   new key beside `ask_display`, e.g. `"last_ask_display": best["ask_display"]`
   when `price_is_current` is false (else None). `tests/test_slate_picks.py`
   walks every key for profit-shaped names; `last_ask_display` is a price, not
   an edge. `GoodChancePicks.tsx` reads it through a local cast
   (`lastAsk()`), so `frontend/src/lib/api.ts` `SlatePick` should gain
   `last_ask_display?: string | null` and the cast can go. Until the server
   serves it, a stale Picks row prints "quote Nm old" + the remedy and no
   greyed ask.
2. The Games evidence line "Kalshi quote 379s old, limit 30s" is `TrustNote`
   (shared component) printing `backend/core/trust.py:_age_check`'s detail. It
   was left: this lane removed the orange StatusLine sentence, so a stale row now
   says it twice (red chip + evidence line), not three times. Dropping the
   third needs an `omit`-style prop on TrustNote or a change in trust.py.
3. "0/5 books under" beside "1 book(s), need 2" was not addressed (ticket Build
   list does not name it).
4. `routes.py:1884` "...combined into nothing" stays main's.
