/**
 * Recording a parlay Joe already holds: session cookie in, bearer token out.
 *
 * Same shape and same reasoning as `/pass` — the backend's
 * `POST /api/hedge/positions` is a mutation and every mutating route is gated
 * (CLAUDE.md Security), while the browser deliberately never holds
 * `APP_AUTH_TOKEN`.
 *
 * What this widens: nothing toward money. It writes a note saying "I hold this
 * ticket, for this stake, to return this much". It reaches no venue, places no
 * order, and `backend/gate.py` may never read the rows it creates (ADR 0078 §4)
 * — so a form cannot move the live-trading interlock.
 *
 * The body is relayed rather than reconstructed: the backend owns the
 * cents-to-tenths conversion, the odds-range refusal and the leg validation,
 * and it is the side that has to be right.
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
    return demoRefusal("a ticket cannot be recorded");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;

  const body = parsed.body;
  if (!body || typeof body !== "object" || !Array.isArray((body as { legs?: unknown }).legs)) {
    return NextResponse.json(
      { detail: "A ticket needs its legs. Nothing was recorded." },
      { status: 400 },
    );
  }

  return relayToBackend(
    "/api/hedge/positions",
    { method: "POST", token, body },
    "The cockpit backend did not answer. Nothing was recorded.",
  );
}
