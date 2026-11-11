/**
 * Joe's tag for where a pick came from (v63), relayed to the backend's
 * `POST /api/pick-sources`. It writes one table, `pick_sources`, and
 * reaches no venue, places no order and spends nothing; it is gated because
 * every mutating route is.
 *
 * The body is the ticker and the tag (`null` clears it). The backend owns
 * the list of tags and refuses anything else in words.
 */

import { NextResponse, type NextRequest } from "next/server";

import {
  backendToken,
  demoRefusal,
  readJsonBody,
  relayToBackend,
} from "@/lib/proxy";

export async function POST(request: NextRequest) {
  const token = backendToken();
  if (!token) {
    return demoRefusal("a pick cannot be tagged");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;
  const body = parsed.body as {
    ticker?: unknown;
    source?: unknown;
    tailed_from?: unknown;
  } | null;

  const ticker = typeof body?.ticker === "string" ? body.ticker.trim() : "";
  if (!ticker) {
    return NextResponse.json(
      { detail: "That is not a ticker. Nothing was tagged." },
      { status: 400 },
    );
  }
  const source = typeof body?.source === "string" ? body.source : null;
  // ADR 0193 Amendment 1: who a tailed pick came from. The backend trims,
  // limits and refuses it in words; this only relays a string.
  const tailedFrom =
    typeof body?.tailed_from === "string" ? body.tailed_from : null;

  return relayToBackend(
    "/api/pick-sources",
    { method: "POST", token, body: { ticker, source, tailed_from: tailedFrom } },
    "The cockpit backend did not answer. Nothing was tagged.",
  );
}
