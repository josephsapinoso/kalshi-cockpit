/**
 * The correction path's server side. See `/log-estimate` for the pattern and
 * the security reasoning; this differs only in what it forwards to.
 *
 * Nothing here can edit a probability: the backend appends a revision row and
 * flags the estimate, and the database trigger rejects any UPDATE of the
 * number itself below every layer of this stack.
 */

import { NextResponse, type NextRequest } from "next/server";

import { backendToken, readJsonBody, relayToBackend } from "@/lib/proxy";

export async function POST(request: NextRequest) {
  const token = backendToken();
  if (!token) {
    return NextResponse.json(
      { detail: "This is the demo instance. There is no log to revise." },
      { status: 403 },
    );
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;
  const body = parsed.body as { id?: unknown; reason?: unknown };

  const id = body?.id;
  if (typeof id !== "number" || !Number.isInteger(id) || id <= 0) {
    return NextResponse.json(
      { detail: "id must be a positive integer." },
      { status: 400 },
    );
  }

  return relayToBackend(
    `/api/estimates/${id}/revise`,
    {
      method: "POST",
      token,
      body: { reason: body?.reason },
      unreadable: "The backend answered with something that was not JSON.",
    },
    "The backend could not be reached. Nothing was revised.",
  );
}
