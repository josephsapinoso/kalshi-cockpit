/**
 * Marking a leg won, lost or void — Joe's word, on a leg the venue cannot
 * settle for him.
 *
 * Needed rather than convenient: a sportsbook leg has no Kalshi ticker, so
 * `kalshi_markets.result` can never reach it, and without this the lock case is
 * unreachable for exactly the slips he asked about (ADR 0077).
 *
 * **`resolved_source` is not sent from here.** The backend fixes it at
 * `manual`. `venue` means the exchange's own result said so, and the two are
 * not equally good evidence; a client that could set the column would erase
 * that distinction the first time somebody found it convenient.
 */

import { NextResponse, type NextRequest } from "next/server";

import {
  backendToken,
  demoRefusal,
  readJsonBody,
  relayToBackend,
} from "@/lib/proxy";

const OUTCOMES = new Set(["won", "lost", "void"]);

export async function POST(request: NextRequest) {
  const token = backendToken();
  if (!token) {
    return demoRefusal("a leg cannot be settled");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;
  const body = parsed.body as { leg_id?: unknown; outcome?: unknown } | null;

  const legId = Number(body?.leg_id);
  const outcome = String(body?.outcome ?? "");
  if (!Number.isInteger(legId) || legId <= 0 || !OUTCOMES.has(outcome)) {
    return NextResponse.json(
      { detail: "That is not a leg and an outcome. Nothing was settled." },
      { status: 400 },
    );
  }

  return relayToBackend(
    `/api/hedge/legs/${legId}/resolve`,
    { method: "POST", token, body: { outcome } },
    "The cockpit backend did not answer. Nothing was settled.",
  );
}
