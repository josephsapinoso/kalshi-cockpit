/**
 * The hand bet's server side: session cookie in, bearer token out.
 *
 * **New 2026-09-08, and it exists to remove a typed credential rather than to
 * add a feature.** Until this route, `ManualTicket.tsx` made Joe retype a
 * 43-character bearer token from scratch on every single order, while the
 * combination routes next to it (`/parlay-lookup`, `/parlay-bid`) had never
 * asked for anything typed. That asymmetry was drift, not design. He removed
 * the typed act -- `docs/adr/0112-the-caps-come-off-the-hand-bet-path.md` §1,
 * answer 3 -- after being told what it cost, which is the part worth
 * recording:
 *
 * **The typed token was not only friction, it was the credential.** The old
 * note on `ManualTicket` said "a session cookie must never place a bet", and
 * that is exactly what this route makes possible. Before it, a person holding
 * Joe's unlocked phone with the cockpit open could not bet his money without
 * producing 43 characters they did not have. After it, being signed in is
 * enough. He was shown that sentence and chose this anyway; ADR §5 reserves
 * reversing it to him.
 *
 * **Auth is not weakened at the API.** `require_auth` still guards
 * `/api/manual-orders` and every other mutating route, and `CLAUDE.md`'s rule
 * -- every mutating route requires auth -- still holds literally. What moved
 * is where the bearer comes from: the server rather than his fingers. The
 * browser still never holds it.
 *
 * The body is forwarded as-is. Every check that matters is server-side and
 * none is waivable from here -- the idempotency key, the desk lockout, the
 * KXMVE acknowledgement, the stale-ask refusal, depth at the ask, the netting
 * guard, the surviving exposure ceiling and reserve-then-check under the write
 * lock. A client that forgot to render a control must have its order refused
 * rather than have the check skipped (`CLAUDE.md`: never trust that the UI
 * disabled a button).
 *
 * `middleware.ts` names `/manual-order` in `JSON_ROUTE_HANDLERS` so an
 * unauthenticated call gets a JSON 401 rather than the HTML login redirect a
 * `fetch` would read as success.
 */

import { type NextRequest } from "next/server";

import {
  backendToken,
  demoRefusal,
  readJsonBody,
  relayToBackend,
} from "@/lib/proxy";

export async function POST(request: NextRequest) {
  const token = backendToken();
  if (!token) {
    return demoRefusal("a bet cannot be placed");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;

  return relayToBackend(
    "/api/manual-orders",
    { method: "POST", token, body: parsed.body },
    // The strong wording, for the same reason `/parlay-bid` uses it and with
    // more force: this order is immediate-or-cancel against a live book. A
    // request that left the cockpit and did not come back may have FILLED.
    // Telling him nothing happened is how he buys the same contracts twice.
    "The cockpit backend did not answer. The bet may have gone through — " +
      "check the Kalshi app before trying again. The idempotency key means " +
      "retrying the same ticket is safe; starting a new one is not.",
  );
}
