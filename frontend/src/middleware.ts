/**
 * The gate in front of the live cockpit.
 *
 * Why here and not in the backend: uvicorn binds `127.0.0.1:8000` inside the
 * container and is never published. The only public surface is Next on 3000,
 * and `/api/*` is reachable only because `next.config.ts` rewrites it. Next
 * middleware runs *before* rewrites, so one gate here covers every page and
 * every proxied API route -- while server components keep calling the backend
 * directly over loopback with no token to manage.
 *
 * The demo instance has no `APP_AUTH_TOKEN` and is therefore ungated, which is
 * what the portfolio link needs.
 */

import { NextResponse, type NextRequest } from "next/server";

import { COOKIE_NAME, sessionSecret, verifySession } from "@/lib/session";

/**
 * Paths that must answer without a session.
 *
 * `/api/health` is the load-bearing one. Fly's health check
 * (`[checks.health] path = "/api/health"` in fly.live.toml) arrives with no
 * cookie, so gating it would fail every check, restart the machine, fail again,
 * and present as a crash loop caused by adding a login page.
 */
const PUBLIC_PATHS = new Set([
  "/login",
  "/session",
  "/api/health",
  "/favicon.ico",
  "/icon.svg",
  "/robots.txt",
]);

export async function middleware(request: NextRequest) {
  const secret = sessionSecret();
  // No shared secret configured -- this is the demo. Nothing to protect.
  if (!secret) return NextResponse.next();

  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.has(pathname)) return NextResponse.next();

  if (await verifySession(request.cookies.get(COOKIE_NAME)?.value, secret)) {
    return NextResponse.next();
  }

  // An API caller gets a status code it can act on. Redirecting these would
  // hand a JSON client an HTML login page and a 200, which reads as success.
  if (pathname.startsWith("/api/")) {
    return NextResponse.json(
      { detail: "Not authenticated. Sign in at /login." },
      { status: 401 },
    );
  }

  const login = new URL("/login", request.url);
  // Preserved so a deep link survives the round trip -- the difference between
  // opening a phone notification and landing where you meant to.
  if (pathname !== "/") login.searchParams.set("next", pathname);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except Next's own static output. Those are hashed build assets
  // with nothing sensitive in them, and gating them would break the login page
  // itself.
  matcher: ["/((?!_next/static|_next/image).*)"],
};
