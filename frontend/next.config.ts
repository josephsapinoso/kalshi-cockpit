import type { NextConfig } from "next";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Traces only the files actually imported, so the runtime image ships a few
  // MB of server bundle instead of the whole node_modules tree.
  output: "standalone",

  // Proxy /api to the Python backend so the browser sees one origin. Keeps the
  // auth token out of client-side CORS handling and means the deployed image
  // serves both halves from the same host.
  //
  // Note this rewrite only covers requests the *browser* makes to Next. Server
  // components run on the Node side with no page origin, so `lib/api.ts`
  // resolves an absolute URL there instead — see the comment on `BASE`.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },

  // **The image optimizer is off, and this is a security decision — ADR 0117.**
  //
  // `/_next/image` is a server-side image processor that decodes bytes chosen
  // by the caller. `middleware.ts` excludes it from the auth matcher, so on the
  // deployed instance it answered unauthenticated requests with the optimizer's
  // own validation strings while every other route redirected to `/login`. It
  // inherited that exemption from `_next/static`, which sits beside it in the
  // same regex and really is inert hashed assets.
  //
  // On 2026-09-09 that endpoint carried a CVSS 9.5 unauthenticated RCE
  // (AVIF decode) and its `sharp`/libheif dependency carried another. Both are
  // patched. This turns the endpoint off so the NEXT one does not reach us:
  // with `unoptimized`, `next/image` serves its `src` unchanged and the
  // optimizer route is not mounted at all.
  //
  // **The cost is zero here and that is why this is cheap rather than brave.**
  // Nothing in `src/` imports `next/image` — the only two matches in the whole
  // frontend are the comment in `components/CrewAvatar.tsx` saying it
  // deliberately draws inline SVG instead, and the matcher string itself.
  // `public/` holds only `robots.txt`. If a future component does want
  // `next/image`, re-enabling this is one line — and that line is the moment to
  // decide whether `_next/image` should also come inside the auth matcher,
  // because turning the optimizer back on without that restores the exemption
  // too.
  images: { unoptimized: true },

  // Next.js 16 writes `frontend/CLAUDE.md` and `frontend/AGENTS.md` on every
  // `next dev` run, by default. This repo keeps **one** spine `CLAUDE.md` at
  // the root and says so in it; an untracked second one in a subdirectory is
  // one `git add -A` away from being committed, and it is regenerated often
  // enough that deleting it is not a fix. Turned off rather than gitignored so
  // the file is never written at all.
  agentRules: false,
};

export default nextConfig;
