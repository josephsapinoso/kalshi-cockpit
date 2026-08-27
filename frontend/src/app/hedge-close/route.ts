/**
 * Closing a held ticket: stop watching it.
 *
 * Nothing is deleted — the row keeps its legs and their history, and only
 * leaves the screen. A record that could be erased would make a lock computed
 * against it unauditable afterwards, which is the property the whole hedge
 * surface rests on.
 */

import { NextResponse, type NextRequest } from "next/server";

import {
  backendToken,
  demoRefusal,
  readJsonBody,
  relayToBackend,
} from "@/lib/proxy";

const STATUSES = new Set(["settled", "closed", "void"]);

export async function POST(request: NextRequest) {
  const token = backendToken();
  if (!token) {
    return demoRefusal("a ticket cannot be closed");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;
  const body = parsed.body as { position_id?: unknown; status?: unknown } | null;

  const positionId = Number(body?.position_id);
  const status = String(body?.status ?? "");
  if (!Number.isInteger(positionId) || positionId <= 0 || !STATUSES.has(status)) {
    return NextResponse.json(
      { detail: "That is not a ticket and a status. Nothing was closed." },
      { status: 400 },
    );
  }

  return relayToBackend(
    `/api/hedge/positions/${positionId}/close`,
    { method: "POST", token, body: { status } },
    "The cockpit backend did not answer. Nothing was closed.",
  );
}
