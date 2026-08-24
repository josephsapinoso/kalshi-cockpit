/**
 * The parlay lookup's server side: session cookie in, bearer token out.
 *
 * Same shape as `/pass` and `/scout-desk`: the backend's
 * `POST /api/parlays/lookup` is auth-gated because it is an outward-facing
 * write — it mints a real combination market on the exchange (no money
 * moves; it is what the Kalshi app does when anyone taps legs, and combo
 * lookups are on the authorized-actions list). The browser deliberately
 * never holds the token, so this handler does.
 *
 * The body is forwarded as-is: the backend re-derives the card and refuses
 * a drifted one, owns leg validation, and records every outcome — it is the
 * side that has to be right.
 *
 * The mechanics (origin, demo refusal, transport guard, relay) come from
 * `lib/proxy.ts`; this file keeps only what is specific to this route, which
 * is its words. `middleware.ts` names `/parlay-lookup` in
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
    return demoRefusal("a combination cannot be priced");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;

  return relayToBackend(
    "/api/parlays/lookup",
    { method: "POST", token, body: parsed.body },
    "The cockpit backend did not answer. Nothing was created.",
  );
}
