/**
 * Cancelling a resting bid: session cookie in, bearer token out.
 *
 * A separate handler from `/parlay-bid` rather than a method on it, because
 * the two carry opposite risks and should not share a code path: placing
 * commits money, cancelling releases it. The one that must never fail quietly
 * is this one — a cancel that silently does nothing leaves an offer standing
 * that Joe believes he withdrew.
 *
 * The bid id is taken from the body rather than the path so this stays one
 * static route: `middleware.ts` matches `JSON_ROUTE_HANDLERS` by exact
 * pathname, and a dynamic segment would fall through to the HTML login
 * redirect that a `fetch` reads as success.
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
    return demoRefusal("a bid cannot be cancelled");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;

  const body = parsed.body as { bid_id?: unknown; reason?: unknown };
  const bidId = Number(body?.bid_id);
  if (!Number.isInteger(bidId) || bidId <= 0) {
    return Response.json(
      { detail: "which bid? `bid_id` is required and must be a row id." },
      { status: 422 },
    );
  }

  return relayToBackend(
    `/api/parlays/bids/${bidId}/cancel`,
    {
      method: "POST",
      token,
      body: { reason: typeof body.reason === "string" ? body.reason : undefined },
    },
    "The cockpit backend did not answer. The bid may still be resting — " +
      "check the Kalshi app.",
  );
}
