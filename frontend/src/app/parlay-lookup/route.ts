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
 */

import { NextResponse, type NextRequest } from "next/server";

/** The Python backend, over loopback inside the container. */
const BACKEND = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

export async function POST(request: NextRequest) {
  const token = process.env.APP_AUTH_TOKEN;
  if (!token) {
    return NextResponse.json(
      {
        detail:
          "This is the demo instance. It holds no exchange credentials, so " +
          "a combination cannot be priced from here.",
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

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/parlays/lookup`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
      body: JSON.stringify(body),
    });
  } catch {
    return NextResponse.json(
      { detail: "The cockpit backend did not answer. Nothing was created." },
      { status: 502 },
    );
  }

  const payload: unknown = await upstream.json().catch(() => null);
  return NextResponse.json(
    payload ?? { detail: `backend returned ${upstream.status}` },
    { status: upstream.status },
  );
}
