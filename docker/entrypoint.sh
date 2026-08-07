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

# `wait -n` returns as soon as EITHER process exits. Whichever it was, we tear
# the container down so the platform restarts it cleanly.
#
# `|| true` because `set -e` would otherwise exit before the message below,
# losing the one line that says which half died.
wait -n || true

if kill -0 "${backend_pid}" 2>/dev/null; then
  echo "[entrypoint] FRONTEND exited -- restarting container"
else
  echo "[entrypoint] BACKEND exited -- every price is now stale. Restarting."
fi
shutdown
