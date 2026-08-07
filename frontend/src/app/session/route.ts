/**
 * Exchange the shared token for a session cookie.
 *
 * Deliberately at `/session` rather than under `/api/`: `next.config.ts`
 * rewrites `/api/:path*` to the Python backend, and a route handler competing
 * with a rewrite for the same prefix is the kind of ordering dependency that
 * works until someone reorders the config.
 */

import { NextResponse, type NextRequest } from "next/server";

import {
  COOKIE_NAME,
  SESSION_MAX_AGE_S,
  issueSession,
  sessionSecret,
  tokenMatches,
} from "@/lib/session";

/**
 * A 303 with a **relative** `Location`.
 *
 * `NextResponse.redirect` needs an absolute URL, and building one from
 * `request.url` inside the container yields the bind address rather than the
 * public host: behind Fly that redirected the browser to
 * `https://0.0.0.0:3000/ledger`. Reconstructing the origin from
 * `X-Forwarded-Host` would work but adds a header the deployment has to keep
 * getting right. A relative `Location` is valid per RFC 7231, is resolved
 * against the request URL by every browser, and cannot name the wrong host.
 */
function seeOther(location: string): NextResponse {
  return new NextResponse(null, { status: 303, headers: { Location: location } });
}

export async function POST(request: NextRequest) {
  const secret = sessionSecret();
  if (!secret) {
    // The demo has no token, so there is no session to issue and nothing that
    // needs one.
    return NextResponse.json(
      { detail: "This instance has no authentication configured." },
      { status: 404 },
    );
  }

  const form = await request.formData();
  const supplied = String(form.get("token") ?? "");
  const next = String(form.get("next") ?? "/");

  if (!supplied || !tokenMatches(supplied, secret)) {
    const query = new URLSearchParams({ error: "1" });
    if (next !== "/") query.set("next", next);
    return seeOther(`/login?${query}`);
  }

  // Only same-origin relative paths, so `?next=https://evil.example` cannot
  // turn the login into an open redirect.
  const destination = next.startsWith("/") && !next.startsWith("//") ? next : "/";

  const response = seeOther(destination);
  response.cookies.set({
    name: COOKIE_NAME,
    value: await issueSession(secret),
    httpOnly: true,
    sameSite: "lax",
    // Fly terminates TLS and `force_https` is on, so the cookie should never
    // travel in clear. Relaxed off HTTPS only so a local `next dev` still works.
    secure: request.nextUrl.protocol === "https:",
    path: "/",
    maxAge: SESSION_MAX_AGE_S,
  });
  return response;
}

export async function DELETE(request: NextRequest) {
  const response = NextResponse.json({ ok: true });
  response.cookies.set({ name: COOKIE_NAME, value: "", path: "/", maxAge: 0 });
  return response;
}
