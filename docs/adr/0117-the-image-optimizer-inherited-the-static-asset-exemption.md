# 0117 — The image optimizer inherited the static-asset exemption, and nothing was watching the dependency queue

**Date:** 2026-09-09
**Status:** Accepted
**Supersedes:** nothing. **Amends:** nothing.

## Context

On 2026-09-09 at 03:25:53Z, a push to `main` triggered a GitHub dependency
rescan. The rescan closed one alert and opened three, all against
`frontend/package-lock.json`:

    #17  CRITICAL  cvss4 9.5  next 16.3.1   unauthenticated RCE in the Image
                                            Optimization API, via AVIF
    #16  CRITICAL             next 16.3.1   unauthenticated RCE on
                                            windows-hosted servers
    #18  HIGH      cvss4 8.9  sharp 0.35.3  libheif, GHSA-g89c-p67h-r497 and
                                            GHSA-2jg2-4ch7-h545

None of the three was on any of this repo's three queues. `tasks/NEXT.md`
tracks repo and infrastructure work, the decision map tracks screen
decisions, and decided-not-yet-built tracks specs. Dependabot alerts were on
none of them, and no session had read them.

### The exposure was read off the deployed machine, not inferred

CLAUDE.md's security section says a public URL must not be one config bug
away from the order path. The question was whether that description fits, so
it was answered against live rather than against the source.

`frontend/src/middleware.ts:160`:

    matcher: ["/((?!_next/static|_next/image).*)"],

`_next/image` is excluded from the auth middleware. The comment above the
matcher justifies the exclusion for `_next/static`, which really is inert
hashed build assets with nothing sensitive in them. `_next/image` is not a
static asset. It is a server-side image processor, and it inherited the
static-asset exemption by sitting next to one in a regex.

The consequences were confirmed by probing the live instance:

    GET /_next/whatever              -> 307 -> /login?next=%2F_next%2Fwhatever
    GET /_next/image?url=%2Frobots.txt&w=64&q=75
                                     -> 400 "The requested resource isn't a valid image."
    GET /_next/image?url=%2Frobots.txt&w=63&q=75
                                     -> 400 "\"w\" parameter (width) of 63 is not allowed"

A gated path redirects to login. `/_next/image` does not. It answers with the
optimizer's own parameter-validation strings to a request carrying no session
cookie. The `w=63` message can only come from the optimizer's validator, so
optimizer code was executing on unauthenticated input.

Supporting facts, each read rather than assumed:

- `frontend/next.config.ts:8` sets `output: "standalone"`. There is no
  `images` key at all, so `unoptimized` is never set. The resolved
  `required-server-files.json` — what the standalone server actually reads —
  confirms `"path": "/_next/image"` with `"unoptimized": false`.
- `docker/entrypoint.sh:301` runs `node frontend/server.js`, the full
  standalone server.
- `fly.live.toml:674-676` publishes `internal_port = 3000`, which is Next
  itself. `docker/entrypoint.sh:253-255` binds uvicorn to `127.0.0.1:8000`,
  loopback only. The Python backend sits *behind* Next, not in front. Nothing
  sanitises ahead of the optimizer.
- `sharp` 0.35.3 with native linux-x64 libvips is present in the running
  container, confirmed over `flyctl ssh`. It arrives as an
  optionalDependency of `next` at `^0.35.3`, installs because `Dockerfile:22`
  runs `npm ci` without `--omit=optional`, and is copied in wholesale with
  `.next/standalone` at `Dockerfile:93`. This is not the WASM-fallback case.
- `auto_stop_machines = "off"` and `min_machines_running = 1`, so there is no
  scale-to-zero window that reduced the exposure.

The application does not use `next/image` anywhere. `CrewAvatar.tsx:4`
carries a comment saying it deliberately avoids the pipeline, and
`frontend/public/` holds only `robots.txt`. **That is not a mitigation.** The
optimizer is mounted whenever it is enabled, independently of whether any
component calls it.

The demo instance runs the same image and has no `APP_AUTH_TOKEN`, so its
Next middleware gates nothing at all. It holds no credentials and reseeds its
database per boot, so a compromise there does not reach the money path — but
it was the same vulnerable surface, more exposed.

## Decision

**Bump `next` to 16.3.3 and `sharp` to 0.35.4, and deploy both instances.**

`sharp` needed no `overrides` entry. `next` declares it at `^0.35.3`, which
already admits 0.35.4; the lockfile was merely pinning an older resolution,
so `npm update sharp` moved it inside the existing range.

**Add dependency alerts to the session-start read.** This is the durable half
of the decision. The bump is a one-line fix that any session could have made;
what allowed two critical unauthenticated RCEs to sit on a public money box
is that nothing looked. `tasks/NEXT.md`'s session-start box now names the
alerts query beside the CI query.

## What this decision does NOT claim

**Reachable is established. Exploitable is not.** `remotePatterns` is empty,
so the optimizer cannot fetch a remote image. `localPatterns` is `**`, and
the live probe proves it will fetch an arbitrary same-origin path and hand
the bytes to the decoder — `/robots.txt` reached "isn't a valid image", which
is a decode failure rather than an access refusal. Whether any local path can
be made to return attacker-influenced bytes was not determined. That is a
route-surface question and it was not answered. This ADR records that the
vulnerable endpoint was exposed, not that it was exploited or exploitable.

**Whether `sharp` was loaded into the Next process, as opposed to present on
disk, was not established.** Proving it needs a successful optimization, and
the instance serves no valid image to drive one.

**Whether `formats: ["image/webp"]` constrains input decoding was not
established.** That setting governs output negotiation. Do not treat it as
mitigation without checking Next's behaviour.

**#16 did not reach production.** The container is Debian trixie on
`Linux 6.12.105-fly`. The windows-hosted-server RCE applies to `next dev` on
the operator's Windows 11 box, not to Fly. The same patch closes both, so no
time was spent deciding.

**The exposure window was not measured.** `next` 16.3.1 was in the tree
before this session; when the advisory published and when the vulnerable
version first deployed were not established, so no duration is claimed.

## The instrument lied, and that is its own finding

Alert #15 (`cryptography`, high) was marked **fixed** by the same rescan, at
`fixed_at: 2026-09-09T03:25:53Z`. `requirements.txt:9` pins
`cryptography~=44.0`, the installed version is 44.0.3, and the advisory's
vulnerable range is `>= 42.0.0, <= 48.0.0` with the fix in 49.0.0. The pin is
inside the vulnerable range and nothing about it changed in that push.

GitHub says fixed. The pin says otherwise. **This ADR does not resolve the
contradiction and does not treat "fixed" as true.** It is recorded because it
bears directly on the other three: if dependabot's state is unreliable here,
its state on #16, #17 and #18 is not self-certifying either — and the fix for
those was verified by reading the versions out of the running container
rather than by believing the alert closed.

Bumping `cryptography` five majors is not undertaken here. It is the RSA-PSS
signing path that authenticates real-money orders, `requirements.txt` marks
it "not optional, not swappable", and a major-version jump on that path
deserves its own decision rather than being smuggled into a security patch.
**This is left open and named in `tasks/NEXT.md`.**

## Consequences

- Two critical unauthenticated RCEs are off the public surface. Verified by
  reading `next` 16.3.3 and `sharp` 0.35.4 out of the live container, not by
  the deploy's own output.
- Live and demo are both on `88ac4ec`. Live stayed on machine
  `7812601a239428` across the deploy, so no volume was replaced and no credit
  fact inverted.
- The three money doors are unchanged: `manual_orders` armed,
  `combo_bids` dry, `engine_orders` dry. Nothing here touches arming.
- `_next/image` remains outside the auth matcher. **The patch fixes the
  vulnerable code; it does not fix the exemption.** Whether the optimizer
  should be behind auth, or disabled outright given the app has zero image
  usage, is a separate decision and is left open. Disabling it via
  `images: { unoptimized: true }` would remove this class of exposure
  permanently rather than one advisory at a time.
- The `cryptography` pin question is open.
