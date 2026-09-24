/**
 * Adopting a KXMVE combination the venue already shows Joe holds onto
 * `/hedge`'s watch, in one tap (#148).
 *
 * `unrecorded_at_venue` (served on every `/api/hedge` read) tells him
 * "Record it below" for a combination like this; `RecordParlay.tsx` has no
 * field for a combination ticker, so that instruction could not be followed
 * until this route existed. The backend's `POST /api/hedge/positions/adopt`
 * is auth-gated because it writes: it reads contracts, exposure and the legs
 * from the venue's own poll and market, and records a real
 * `parlay_positions` row. It places no order and spends nothing.
 *
 * The body carries the ticker alone, the same shape `/parlay-lookup` and
 * `/hedge-sell-quote` use for the fields the desk cannot supply itself.
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
    return demoRefusal("a combination cannot be adopted");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;
  const body = parsed.body as { ticker?: unknown } | null;

  const ticker = typeof body?.ticker === "string" ? body.ticker.trim() : "";
  if (!ticker) {
    return NextResponse.json(
      { detail: "That is not a ticker. Nothing was adopted." },
      { status: 400 },
    );
  }

  return relayToBackend(
    "/api/hedge/positions/adopt",
    { method: "POST", token, body: { ticker } },
    "The cockpit backend did not answer. Nothing was adopted.",
  );
}
