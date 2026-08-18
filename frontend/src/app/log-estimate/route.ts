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

import { NextResponse, type NextRequest } from "next/server";

/** The Python backend, over loopback inside the container. */
const BACKEND = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

export async function POST(request: NextRequest) {
  const token = process.env.APP_AUTH_TOKEN;
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

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { detail: "The request body was not JSON." },
      { status: 400 },
    );
  }

  // Forwarded rather than reconstructed: the backend owns the bounds check
  // and the schema owns write-once. Re-validating here would be a second
  // implementation of one rule, and the two would drift.
  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/estimates`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
      body: JSON.stringify(body),
    });
  } catch {
    return NextResponse.json(
      { detail: "The backend could not be reached. The estimate was NOT logged." },
      { status: 502 },
    );
  }

  const payload = await upstream.json().catch(() => null);
  return NextResponse.json(
    payload ?? { detail: "The backend answered with something that was not JSON." },
    { status: upstream.status },
  );
}
