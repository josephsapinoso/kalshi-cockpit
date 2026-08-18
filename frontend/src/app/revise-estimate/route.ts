/**
 * The correction path's server side. See `/log-estimate` for the pattern and
 * the security reasoning; this differs only in what it forwards to.
 *
 * Nothing here can edit a probability: the backend appends a revision row and
 * flags the estimate, and the database trigger rejects any UPDATE of the
 * number itself below every layer of this stack.
 */

import { NextResponse, type NextRequest } from "next/server";

const BACKEND = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

export async function POST(request: NextRequest) {
  const token = process.env.APP_AUTH_TOKEN;
  if (!token) {
    return NextResponse.json(
      { detail: "This is the demo instance. There is no log to revise." },
      { status: 403 },
    );
  }

  let body: { id?: unknown; reason?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { detail: "The request body was not JSON." },
      { status: 400 },
    );
  }

  const id = body.id;
  if (typeof id !== "number" || !Number.isInteger(id) || id <= 0) {
    return NextResponse.json(
      { detail: "id must be a positive integer." },
      { status: 400 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/estimates/${id}/revise`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
      body: JSON.stringify({ reason: body.reason }),
    });
  } catch {
    return NextResponse.json(
      { detail: "The backend could not be reached. Nothing was revised." },
      { status: 502 },
    );
  }

  const payload = await upstream.json().catch(() => null);
  return NextResponse.json(
    payload ?? { detail: "The backend answered with something that was not JSON." },
    { status: upstream.status },
  );
}
