/**
 * The accept's server side: session cookie in, bearer token out.
 *
 * **The one route in this family that spends.** Everything under
 * `/parlay-rfq` asks for a price and commits to nothing; this takes a quote.
 * It is gated exactly like `/manual-order`, which is the other door with real
 * money behind it.
 *
 * The body carries a quote id and nothing else — no price, no side. The
 * backend reads the price from its own record of the quote Joe was shown, so
 * nothing the browser sends can change what is bought or what it costs.
 *
 * `middleware.ts` names `/parlay-rfq-accept` in `JSON_ROUTE_HANDLERS` so an
 * unauthenticated POST gets a JSON 401 rather than an HTML login redirect a
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
    return demoRefusal("a quote cannot be accepted");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;

  return relayToBackend(
    "/api/parlays/rfq/accept",
    { method: "POST", token, body: parsed.body },
    // **Not "nothing happened".** An acceptance whose response is lost may
    // still have reached Kalshi, and this path has no idempotency key, so the
    // honest words are "go and look" rather than a reassurance this cannot
    // make.
    "The cockpit backend did not answer. Your acceptance may or may not have reached Kalshi — check the Kalshi app before tapping again.",
  );
}
