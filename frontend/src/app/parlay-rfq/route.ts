/**
 * The RFQ's server side: session cookie in, bearer token out.
 *
 * Same shape as `/parlay-lookup`, and for a sharper reason. The backend's
 * `POST /api/parlays/rfq` is auth-gated because it is an outward-facing
 * write — it creates a real Request for Quote on the exchange, which is how
 * a combination is actually priced. **No money moves**: only accepting a
 * quote binds the requester, and that route does not exist.
 *
 * The body is forwarded as-is and is deliberately tiny — a ticker and a
 * target cost. The backend reads the legs, the collection and the fair value
 * from that ticker's own recorded lookup rather than from this request, so
 * nothing here can talk it into pricing a combination the desk never built.
 *
 * The mechanics (origin, demo refusal, transport guard, relay) come from
 * `lib/proxy.ts`. `middleware.ts` names `/parlay-rfq` in
 * `JSON_ROUTE_HANDLERS` so an unauthenticated call gets a JSON 401 rather
 * than an HTML login redirect a `fetch` would read as success.
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
    return demoRefusal("the market cannot be asked for a price");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;

  return relayToBackend(
    "/api/parlays/rfq",
    { method: "POST", token, body: parsed.body },
    "The cockpit backend did not answer. Nothing was asked and no money moved.",
  );
}
