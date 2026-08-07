#!/usr/bin/env bash
# Start both processes and make sure the container dies if either one does.
#
# The naive `uvicorn & exec node` pattern leaves a half-dead container running:
# uvicorn exits, Next keeps serving, the health check on port 3000 passes, and
# the cockpit shows prices frozen at whatever it last read. Frozen prices that
# look live are the exact failure the staleness contract exists to prevent, so
# a dead backend must take the whole container with it and let Fly restart it.
#
# BASH, not sh, and that is load-bearing. `wait -n` -- the whole mechanism
# below -- is a bash 4.3+ builtin, not POSIX. On this image /bin/sh is dash,
# where it fails instantly with "Illegal option -n" and returns 2. Written
# with a #!/bin/sh shebang, this script started both processes correctly and
# then immediately tore the container down, which on a platform that restarts
# unhealthy containers presents as a crash loop with no obvious cause.

set -euo pipefail

INSTANCE_MODE="${INSTANCE_MODE:-demo}"
DB_PATH="${DB_PATH:-/data/cockpit.db}"

echo "[entrypoint] instance_mode=${INSTANCE_MODE} db=${DB_PATH}"

# The demo instance regenerates its database on every boot. It holds no
# credentials and reaches no network, so there is nothing to preserve -- and a
# fresh seed means the deployed demo always matches the screenshots.
if [ "${INSTANCE_MODE}" = "demo" ]; then
  echo "[entrypoint] seeding demo database (no credentials, no network)"
  python -m backend.seed_demo --db "${DB_PATH}"
fi

pids=""

shutdown() {
  echo "[entrypoint] shutting down"
  for pid in ${pids}; do
    kill "${pid}" 2>/dev/null || true
  done
  wait || true
  exit 0
}
trap shutdown INT TERM

echo "[entrypoint] starting backend on 127.0.0.1:8000"
python -m uvicorn backend.api.routes:create_app --factory \
  --host 127.0.0.1 --port 8000 --no-access-log &
backend_pid=$!
pids="${pids} ${backend_pid}"

# Wait for the backend before starting Next. Without this, the first page
# render races the backend's startup and shows "Backend unreachable" to
# whoever happened to hit the instance during its first second.
i=0
until python -c "import urllib.request,sys; \
urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" 2>/dev/null; do
  i=$((i + 1))
  if [ "${i}" -gt 30 ]; then
    echo "[entrypoint] backend did not become healthy in 30s -- aborting"
    exit 1
  fi
  # If it died rather than being slow, say so now instead of timing out.
  if ! kill -0 "${backend_pid}" 2>/dev/null; then
    echo "[entrypoint] backend exited during startup"
    exit 1
  fi
  sleep 1
done
echo "[entrypoint] backend healthy after ${i}s"

echo "[entrypoint] starting frontend on 0.0.0.0:${PORT:-3000}"
HOSTNAME=0.0.0.0 node frontend/server.js &
frontend_pid=$!
pids="${pids} ${frontend_pid}"

# The chain runner. Live only: the demo holds no credentials and reaches no
# network, so starting it there would crash-loop the public instance on a
# missing KALSHI_API_KEY -- and the demo's data is seeded, not recorded.
#
# This is the process that accumulates the evidence record. The gate needs 300
# independent games, which is about three weeks of unbroken recording, so an
# instance that serves pages without running this looks completely healthy
# while making no progress at all toward answering the project's question.
loop_pid=""
if [ "${INSTANCE_MODE}" != "demo" ]; then
  echo "[entrypoint] starting chain runner (interval=${RUNNER_INTERVAL_S:-900}s)"
  python scripts/run_loop.py \
    --db "${DB_PATH}" --interval "${RUNNER_INTERVAL_S:-900}" &
  loop_pid=$!
  pids="${pids} ${loop_pid}"
else
  echo "[entrypoint] demo instance -- chain runner not started (no credentials)"
fi

# `wait -n` returns as soon as EITHER process exits. Whichever it was, we tear
# the container down so the platform restarts it cleanly.
#
# `|| true` because `set -e` would otherwise exit before the message below,
# losing the one line that says which half died.
wait -n || true

if ! kill -0 "${backend_pid}" 2>/dev/null; then
  echo "[entrypoint] BACKEND exited -- every price is now stale. Restarting."
elif [ -n "${loop_pid}" ] && ! kill -0 "${loop_pid}" 2>/dev/null; then
  # The runner gives up only after MAX_CONSECUTIVE_FAILURES, so reaching here
  # means repeated failure, not a blip. Sitting on it would leave the cockpit
  # serving a record that has silently stopped growing -- which reads as a
  # quiet slate, not as a broken instance.
  echo "[entrypoint] CHAIN RUNNER exited -- the record has stopped growing. Restarting."
else
  echo "[entrypoint] FRONTEND exited -- restarting container"
fi
shutdown
