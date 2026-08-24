/**
 * The pass record's server side: session cookie in, bearer token out.
 *
 * Same shape and same reasoning as `/scout-desk`: the backend's
 * `POST /api/desk/pass` requires `APP_AUTH_TOKEN` because it is a mutation
 * (every mutating route is gated, CLAUDE.md Security), and the browser
 * deliberately does not hold that token -- `lib/session.ts` issues a cookie
 * that proves knowledge of it without carrying it. So the token stays
 * server-side and this handler holds it.
 *
 * What this widens: nothing toward money. A pass writes one append-only row
 * saying "Joe looked and chose not to bet". It moves no funds, arms nothing,
 * and cannot be edited or deleted afterwards (tests/test_desk_passes.py greps
 * the whole backend for UPDATE/DELETE on the table).
 *
 * Deliberately at `/pass` rather than under `/api/`, because that prefix
 * belongs to the `next.config.ts` rewrite; `middleware.ts` names this path in
 * `JSON_ROUTE_HANDLERS` so an unauthenticated call gets JSON 401 rather than
 * an HTML login redirect a `fetch` would read as success.
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
    // The demo. It holds no credentials; there is no record here to write
    // to, and saying so is the honest answer rather than a 500.
    return demoRefusal("a pass cannot be recorded");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;
  const body = parsed.body;

  const ticker =
    body && typeof body === "object" && "ticker" in body
      ? String((body as { ticker: unknown }).ticker)
      : "";
  if (!ticker) {
    return NextResponse.json(
      { detail: "No ticker named. A pass records which market was passed." },
      { status: 400 },
    );
  }
  // Forwarded only when it is a real string: the backend stores a blank
  // reason as NULL anyway, but there is no need to send it shapes it never
  // asked for.
  const reason =
    body && typeof body === "object" && "reason" in body
      ? (body as { reason: unknown }).reason
      : null;

  // Forwarded rather than reconstructed: the backend owns the uppercase
  // normalisation, the length caps, and the append-only write, and it is the
  // side that has to be right.
  return relayToBackend(
    "/api/desk/pass",
    {
      method: "POST",
      token,
      body:
        typeof reason === "string" && reason.trim().length > 0
          ? { ticker, reason }
          : { ticker },
    },
    "The cockpit backend did not answer. Nothing was recorded.",
  );
}
