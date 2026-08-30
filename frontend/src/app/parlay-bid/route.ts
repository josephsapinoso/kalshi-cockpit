/**
 * The resting bid's server side: session cookie in, bearer token out.
 *
 * Same shape and same reason as `/parlay-lookup`, with one difference worth
 * stating: this route SPENDS. The lookup mints a market and moves no money;
 * this rests a real bid on a real combination, and if someone takes it the
 * contracts are bought. The browser still never holds the token.
 *
 * The body is forwarded as-is. The backend owns the enter-only
 * acknowledgement, the shard's balance check, the spend ceiling and the
 * record — every one of those has to be server-side, because a client that
 * forgot to render a control must refuse the order rather than skip the
 * check (`CLAUDE.md`: never trust that the UI disabled a button).
 *
 * `middleware.ts` names `/parlay-bid` in `JSON_ROUTE_HANDLERS` so an
 * unauthenticated call gets a JSON 401 rather than an HTML login redirect a
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
    return demoRefusal("a bid cannot be placed");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;

  return relayToBackend(
    "/api/parlays/bid",
    { method: "POST", token, body: parsed.body },
    // Deliberately NOT "nothing was created". A bid whose request left the
    // cockpit and did not come back may be resting on the exchange, and this
    // is the one route where saying otherwise would send Joe to place a
    // second one.
    "The cockpit backend did not answer. The bid may have been placed — " +
      "check the resting bids panel and the Kalshi app before trying again.",
  );
}
