/**
 * The self-lockout's server side: session cookie in, bearer token out.
 *
 * Same pattern as `/log-estimate` and for the same reason -- the backend
 * route requires `APP_AUTH_TOKEN`, the browser deliberately does not carry
 * it, and "not tonight" has to be one tap, because a lockout that takes
 * typing a 43-character token is a lockout that loses to the impulse it
 * exists to interrupt.
 *
 * What a stolen cookie buys here: the ability to lock Joe OUT of his own
 * estimate log until the next day roll. Annoying, self-limiting, and biased
 * in the safe direction -- the attack makes betting harder, not easier.
 * There is no disengage endpoint on the backend for it to call.
 */

import { NextResponse, type NextRequest } from "next/server";

/** The Python backend, over loopback inside the container. */
const BACKEND = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

export async function POST(_request: NextRequest) {
  const token = process.env.APP_AUTH_TOKEN;
  if (!token) {
    return NextResponse.json(
      {
        detail:
          "This is the demo instance. The lockout guards the operator's " +
          "estimate log, and the demo has no operator to lock out.",
      },
      { status: 403 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/estimates/lockout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { detail: "The backend could not be reached. You are NOT locked out." },
      { status: 502 },
    );
  }

  const payload = await upstream.json().catch(() => null);
  return NextResponse.json(
    payload ?? { detail: "The backend answered with something that was not JSON." },
    { status: upstream.status },
  );
}
