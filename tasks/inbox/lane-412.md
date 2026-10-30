# #412 handoff

`RefreshOddsPanel` now takes `compact?: boolean` (default false). The panel
cannot know it is urgent by itself, and `frontend/src/app/slate/page.tsx` is
not in this lane. To finish the goal, main must pass `compact` where the panel
is rendered on top:

    slate/page.tsx ~L262:  refreshIsUrgent(...) && <RefreshOddsPanel compact ... />

The below-the-rows render (~L355, not urgent) stays non-compact. The trigger
(`refreshUrgency.ts`) is untouched. Also: `eslint` is not installed in the main
node_modules (`npm run lint` fails), so lint was not run; tsc is clean.
