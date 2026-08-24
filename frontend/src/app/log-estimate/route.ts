/**
 * The estimate form's server side: session cookie in, bearer token out.
 *
 * Same pattern and same reasoning as `/refresh-odds`: `POST /api/estimates`
 * on the Python backend requires `APP_AUTH_TOKEN`, the browser deliberately
 * does not have it, and typing a 43-character token per bet would kill a flow
 * whose entire design budget is ~12 seconds on a phone. The token stays
 * server-side and this handler holds it.
 *
 * What a stolen cookie buys here: the ability to write noise rows into Joe's
 * own calibration log -- which the revision path can flag and §2 excludes.
 * It does not widen toward money: the order path still demands the token
 * itself.
 *
 * Outside `/api/` so it cannot race the rewrite in `next.config.ts`;
 * `middleware.ts` names this path so an unauthenticated call gets 401 JSON
 * rather than a redirect an HTML login page a `fetch` would read as success.
 */

import { type NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { backendToken, readJsonBody, relayToBackend } from "@/lib/proxy";

export async function POST(request: NextRequest) {
  const token = backendToken();
  if (!token) {
    // The demo. It is a public portfolio page; a public visitor's numbers
    // must not be able to land in a measurement record.
    return NextResponse.json(
      {
        detail:
          "This is the demo instance. The calibration log records the " +
          "operator's estimates, and the demo has no operator.",
      },
      { status: 403 },
    );
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;

  // Forwarded rather than reconstructed: the backend owns the bounds check
  // and the schema owns write-once. Re-validating here would be a second
  // implementation of one rule, and the two would drift.
  return relayToBackend(
    "/api/estimates",
    {
      method: "POST",
      token,
      body: parsed.body,
      unreadable: "The backend answered with something that was not JSON.",
    },
    "The backend could not be reached. The estimate was NOT logged.",
  );
}
