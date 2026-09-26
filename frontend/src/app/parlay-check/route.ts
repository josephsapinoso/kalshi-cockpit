/**
 * The parlay-check box's server side: session cookie in, bearer token out.
 *
 * Same shape as `/parlay-lookup` (copied from it): the backend's
 * `POST /api/parlays/check` is auth-gated because it is an outward-facing
 * write when the pasted text names a fresh combination — it can mint a real
 * combination market on the exchange (no money moves; it is what `/parlay-
 * lookup` already does for a card this desk built itself). The browser
 * deliberately never holds the token, so this handler does.
 *
 * The body is forwarded as-is: the backend owns reading the pasted link or
 * ticker, resolving its legs, and pricing them — it is the side that has to
 * be right.
 *
 * The mechanics (origin, demo refusal, transport guard, relay) come from
 * `lib/proxy.ts`; this file keeps only what is specific to this route, which
 * is its words. `middleware.ts` names `/parlay-check` in
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
    return demoRefusal("a parlay someone else built cannot be checked");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;

  return relayToBackend(
    "/api/parlays/check",
    { method: "POST", token, body: parsed.body },
    "The cockpit backend did not answer. Nothing was checked.",
  );
}
