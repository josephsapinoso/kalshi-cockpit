# ADR 0002 — Two deploys, one image

**Date:** 2026-08-06
**Status:** Accepted
**Context:** Build-order step 9

## The problem

This repo is intended to go public, and a live demo someone can click through
is worth far more than screenshots. But the same codebase holds Kalshi
credentials and, eventually, real money. A public URL must not be one config
bug away from the order path.

## Decision

**One Docker image, two Fly apps.** Everything that differs between them is
configuration:

| | `fly.demo.toml` | `fly.live.toml` |
|---|---|---|
| Data | Seeded on every boot | Real ingest |
| Credentials | None | Fly secrets |
| Volume | **None** | `cockpit_data` at `/data` |
| Auth | Public | Bearer token on every mutating route |
| Execution | `POST /api/orders` → **403** | 501 until step 12, then gated |
| Scale to zero | Yes | **Never** |

The rejected alternative was two images. Two images drift, and the one that
must never drift is the one holding real money — a security fix applied to the
demo build and missed on the live build is exactly the failure mode.

The second rejected alternative was a single instance serving seeded data to
logged-out visitors and real data to the owner. Elegant, but it puts demo and
live-money code paths in the same running process, and the isolation is then a
property of the request handler rather than of the deployment.

## Consequences worth stating

**The demo has no volume, deliberately.** Without one, its database is
regenerated from seed on every boot. Three things follow: the demo cannot
accumulate state, it always matches the screenshots in the README, and there is
nothing on that machine worth stealing.

**The live instance never scales to zero.** Not for latency — for evidence. A
stopped machine drops the Kalshi WebSocket, and more importantly records no
closing lines. Candlesticks age out, so an unrecorded close is an observation
lost permanently, and the live gate needs 300 of them.

**Both processes run in one container, and either dying kills it.** The naive
`uvicorn & exec node` pattern leaves a half-dead container: uvicorn exits, Next
keeps serving, the health check on port 3000 passes, and the cockpit shows
prices frozen at their last values. Frozen prices that look live are precisely
what the staleness contract exists to prevent, so `docker/entrypoint.sh` uses
`wait -n` and tears the container down if either process exits. The Docker
health check probes **both** ports for the same reason.

**The private key is a secret, not a file in the image or on the volume.** A
volume snapshot carries whatever is on it; an image layer is even worse.

## Cost

~$5/month for the live instance (shared-cpu-1x, 1GB, always on) plus a volume.
The demo is effectively free since it scales to zero.

**Correction, 2026-08-21 (ADR 0062):** this figure describes a machine that no
longer exists. The live machine is shared-cpu-1x with **2 GB** (doubled after
the 2026-08-19 OOM) and its 5 GB volume is at its auto-extend limit (2026-08-16
incident), so the real Fly line is roughly double this and only the invoice can
say exactly. The repo carries no other Fly price; do not cite this one.
