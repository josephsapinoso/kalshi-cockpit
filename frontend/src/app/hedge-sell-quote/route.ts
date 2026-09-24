/**
 * Asking Kalshi's makers what they would pay for a combination Joe holds.
 *
 * The RFQ half of Joe's answer (A) to #63 -- both exit prices on `/hedge`,
 * read-only, no selling from the desk (#96). The backend's
 * `POST /api/hedge/positions/{id}/sell-quote` is auth-gated because it is an
 * outward-facing write: it creates a real Request for Quote on the exchange,
 * reads the answers and withdraws it. **No money moves** -- nothing on that
 * route accepts, and the accept route refuses an exit ask's quotes.
 *
 * The body carries a position id and nothing else. The ticker, the size and
 * the legs come from the desk's own row and from the venue, never from here.
 * The id travels in the BODY rather than the path because `middleware.ts`
 * matches `JSON_ROUTE_HANDLERS` exactly, and a dynamic segment would miss
 * that set and get the HTML login redirect a `fetch` reads as success.
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
    return demoRefusal("the makers cannot be asked");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;
  const body = parsed.body as { position_id?: unknown } | null;

  const positionId = Number(body?.position_id);
  if (!Number.isInteger(positionId) || positionId <= 0) {
    return NextResponse.json(
      { detail: "That is not a ticket. Nothing was asked." },
      { status: 400 },
    );
  }

  return relayToBackend(
    `/api/hedge/positions/${positionId}/sell-quote`,
    { method: "POST", token, body: {} },
    "The cockpit backend did not answer. Nothing was asked and no money moved.",
  );
}
