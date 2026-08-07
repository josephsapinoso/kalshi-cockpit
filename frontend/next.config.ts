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
};

export default nextConfig;
