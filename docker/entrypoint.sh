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

# ---------------------------------------------------------------------------
# Maintenance hold: keep the container alive when the normal boot cannot run.
#
# **Why this exists.** On 2026-08-16 the live volume filled. `migrate_db.py` is
# the first thing this script runs and it opens the database for write, so the
# boot died one second in, every time, until Fly gave up at its restart cap.
# `flyctl ssh console` needs a running machine, so the one-second window was not
# usable -- and the committed inspectors that could have said what filled the
# volume are invoked *through* that shell. The diagnosis tooling was locked
# inside the thing that was broken.
#
# Holding here, before any write, breaks that circularity: ssh comes up with the
# volume mounted and `scripts/inspect_live_disk.py` can run. It is the sickbay
# door, and it must stay ahead of the migration for the same reason a sickbay
# door is not inside the ward.
#
# **It is deliberately not a recovery mode.** It starts nothing, migrates
# nothing, deletes nothing, and reaches no network. The container simply stays
# up so a human -- or an agent under the ssh governance rule -- can run a
# read-only script against a volume the normal boot cannot survive. Every
# repair stays an explicit, separately reviewed act.
#
# **Set it in `fly.*.toml` and deploy, never as an ad-hoc secret.** The point is
# that the machine's state is readable from git: a volume in maintenance is a
# committed line someone can find, not an invisible override. Revert the line
# and deploy again to leave.
#
# `sleep infinity` rather than a bounded wait: a hold that silently expires
# would drop the machine back into the crash loop mid-diagnosis, and the health
# check is already failing -- there is nothing left for a timeout to protect.
if [ "${MAINTENANCE_HOLD:-}" = "1" ]; then
  echo "[entrypoint] MAINTENANCE_HOLD=1 -- NOT starting the app."
  echo "[entrypoint] Nothing is migrated, served, recorded or deleted."
  # The bare filename, deliberately, with no directory. `test_has_callers.py`
  # derives which scripts the entrypoint RUNS by regexing `scripts/*.py` out of
  # its non-comment lines, and an echoed path is indistinguishable from an
  # executed one to that scanner -- so writing the full path here would make
  # the derived guard believe this hold runs a script, when it runs nothing.
  # Keeping the guard honest is worth more than the four characters.
  echo "[entrypoint] The volume is mounted and ssh is up."
  echo "[entrypoint] Read it with inspect_live_disk.py (under /app/scripts) over ssh."
  echo "[entrypoint] Remove MAINTENANCE_HOLD from fly.live.toml and redeploy to exit."
  sleep infinity
fi

# The demo instance regenerates its database on every boot. It holds no
# credentials and reaches no network, so there is nothing to preserve -- and a
# fresh seed means the deployed demo always matches the screenshots.
#
# `--anchor-now` puts the slate on the current clock. The actionable window is
# measured against real time, so a slate frozen at a fixed timestamp would show
# a permanently closed window next to prices that look live -- the two halves
# of one screen contradicting each other. Local runs keep the fixed stamp, so
# tests stay reproducible.
if [ "${INSTANCE_MODE}" = "demo" ]; then
  echo "[entrypoint] seeding demo database (no credentials, no network)"
  python -m backend.seed_demo --db "${DB_PATH}" --anchor-now
fi

# Migrate BEFORE anything opens the database, which means before uvicorn.
#
# The API opens read-only and `store.db.open_db` refuses a schema version it
# does not recognise -- deliberately, because reading old columns under new
# meanings is the silent failure the version stamp exists to catch. So the API
# cannot migrate its way out of a stale volume: without this line it would 500
# on every page until the chain runner happened to call `init_db`, and
# `/api/health` would stay green throughout because it touches no database.
#
# Idempotent, and `set -e` makes a failure here abort the boot rather than
# continue on a half-migrated volume -- the record on that volume is the one
# thing in this project that cannot be recreated.
echo "[entrypoint] checking database schema"
python scripts/migrate_db.py --db "${DB_PATH}"

# ---------------------------------------------------------------------------
# Materialise the Kalshi RSA private key.
#
# The key has to be a FILE (`cryptography` loads PEM bytes) but must never be a
# file that survives anything: not baked into the image, and not on the Fly
# volume, where a snapshot would carry it forever. So it arrives as a
# base64 secret and is written to /dev/shm, which is tmpfs -- RAM only, gone
# when the machine stops.
#
# Nothing here echoes the key or any part of it. `set -x` must never be added to
# this script.
# ---------------------------------------------------------------------------
if [ "${INSTANCE_MODE}" != "demo" ]; then
  if [ -z "${KALSHI_PRIVATE_KEY_B64:-}" ]; then
    echo "[entrypoint] KALSHI_PRIVATE_KEY_B64 is not set."
    echo "[entrypoint] Set it with:"
    echo "[entrypoint]   fly secrets set KALSHI_PRIVATE_KEY_B64=\"\$(base64 -w0 key.pem)\" -a kalshi-cockpit"
    exit 1
  fi

  key_dir=/dev/shm/kalshi
  key_path="${key_dir}/private_key.pem"

  # 077 so the file is created 600 and is never briefly world-readable.
  (
    umask 077
    mkdir -p "${key_dir}"
    # Whitespace stripped first: a secret pasted from a terminal often carries
    # newlines, and some base64 implementations reject them.
    if ! printf '%s' "${KALSHI_PRIVATE_KEY_B64}" \
         | tr -d '[:space:]' \
         | base64 -d > "${key_path}" 2>/dev/null; then
      echo "[entrypoint] KALSHI_PRIVATE_KEY_B64 is not valid base64."
      exit 1
    fi
  ) || exit 1

  # Validate the shape without printing any of it. An ED25519 or OpenSSH-format
  # key decodes cleanly and then fails much later inside the signer, where the
  # error says nothing about which key was loaded.
  if ! grep -q -- "-----BEGIN \(RSA \)\?PRIVATE KEY-----" "${key_path}"; then
    if grep -q -- "-----BEGIN OPENSSH PRIVATE KEY-----" "${key_path}"; then
      echo "[entrypoint] the key is OpenSSH format. Kalshi needs an RSA PEM."
      echo "[entrypoint] Convert it: ssh-keygen -p -m PEM -f key.pem"
    else
      echo "[entrypoint] decoded key is not a PEM private key."
    fi
    rm -f "${key_path}"
    exit 1
  fi

  export KALSHI_PRIVATE_KEY_PATH="${key_path}"
  echo "[entrypoint] Kalshi key materialised to tmpfs ($(wc -c < "${key_path}") bytes)"
fi

pids=""

# `shutdown [exit_code]` -- the code is the whole point of the argument.
#
# This function has two callers with OPPOSITE meanings, and until 2026-08-26 it
# gave both the same answer:
#
#   * the INT/TERM trap. A deliberate stop -- a deploy, `fly machine stop`.
#     Exit 0 is correct: nothing failed.
#   * the teardown below, reached when `wait -n` returns because a child DIED.
#     Exit 0 is a lie, and it is a lie the platform believes.
#
# Measured on live, 2026-08-26. The chain runner raised `LoopFailed` after five
# consecutive failed passes, this function ran, and Fly logged:
#
#     machine exited with exit code 0, not restarting
#
# Fly's restart policy is on-failure, so a zero exit reads as "this container
# finished its job." The machine stayed STOPPED -- with `auto_stop_machines =
# "off"` and `min_machines_running = 1` set, because neither of those governs a
# container that exited successfully -- until an HTTP request woke it via
# `auto_start_machines`, at a measured 23-37 seconds of cold start. Between
# visits the recorder wrote nothing at all.
#
# So the teardown must exit non-zero. The comment at that call site has always
# said the tear-down exists "so the platform restarts it cleanly"; this is what
# makes that sentence true.
shutdown() {
  code="${1:-0}"
  echo "[entrypoint] shutting down (exit ${code})"
  for pid in ${pids}; do
    kill "${pid}" 2>/dev/null || true
  done
  wait || true
  exit "${code}"
}
# The trap keeps the zero: a signal is somebody asking, not something breaking.
trap 'shutdown 0' INT TERM

# `record_teardown <which child died>` -- one durable record per death,
# because stdout is not durable.
#
# The 2026-08-29 gap read established that every pass gap ends with a child
# dying and this script naming it -- in a log stream that retains ~10 minutes,
# so by the time anyone asked which child it was, the name was gone. Twice in
# one day. The volume is the only place a fact survives the restart that
# follows it, so the name, the memory headroom and the guest kernel's last
# words go there.
#
# `dmesg` is what decides the guest-OOM question: Fly's `oom_killed` flag is
# host-level and cannot see the guest kernel killing one process inside the
# VM. If the kernel did it, the words "Out of memory" are in this tail. It may
# print nothing as a non-root user under `kernel.dmesg_restrict`; recording
# the headroom still stands on its own.
#
# Appended, never truncated on boot -- the record before a death is the point
# -- and capped by dropping the oldest lines, because an uncapped diagnostic
# file on the data volume is how the 2026-08-16 outage started. Everything is
# best-effort: this runs on the way down, and a recording failure must not
# change the exit code the platform's restart policy reads.
record_teardown() {
  log="${TEARDOWN_LOG:-$(dirname "${DB_PATH}")/last_teardown.log}"
  {
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ${1}"
    grep -E '^(MemTotal|MemFree|MemAvailable)' /proc/meminfo 2>/dev/null
    dmesg 2>/dev/null | tail -n 40
  } >> "${log}" 2>/dev/null || true
  if [ "$(wc -c < "${log}" 2>/dev/null || echo 0)" -gt 262144 ]; then
    tail -n 500 "${log}" > "${log}.tmp" 2>/dev/null \
      && mv "${log}.tmp" "${log}" 2>/dev/null || true
  fi
}

echo "[entrypoint] starting backend on 127.0.0.1:8000"
# `--timeout-keep-alive` must exceed the health check interval, and uvicorn's
# default of 5s does not. Fly checks port 3000 every 15s on live and every 30s
# on demo; Next proxies that to uvicorn over a pooled connection it keeps
# between checks. With the upstream closing at 5s, the socket Next reuses is
# already gone -- the request dies with ECONNRESET, Next logs "Failed to proxy
# http://127.0.0.1:8000/api/health Error: socket hang up", and Fly marks the
# machine unhealthy while the backend is perfectly fine.
#
# Measured on the live machine 2026-08-19, driving the proxy on port 3000 over
# one reused connection:
#
#     15s between requests (Fly's live interval)   5 failures of 10
#      3s between requests (inside the 5s window)  0 failures of 10
#
# and the failures alternate exactly -- reuse dies, reconnect succeeds, next
# reuse dies -- which is the signature of the upstream closing first rather
# than of anything being slow. In the same window `/api/health` on port 8000
# answered 50 of 50 direct probes, worst case 1.6s, while IO pressure on the
# box hit 90%. **The backend was never the thing failing**, which is why three
# earlier sessions attributed this flapping to CPU saturation from long passes
# and none of the fixes stopped it. See
# `docs/measurements/2026-08-19-health-flap-is-the-proxy-hop.md`.
#
# 75s clears both intervals with room. The guard that keeps it clearing them is
# `tests/test_keepalive_outlives_health_check.py`, which reads the interval out
# of every fly config rather than trusting this comment.
python -m uvicorn backend.api.routes:create_app --factory \
  --host 127.0.0.1 --port 8000 --no-access-log \
  --timeout-keep-alive 75 &
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
# **This is the hop Fly's health check actually rides on**, and it is the one
# that was flapping. Node defaults `server.keepAliveTimeout` to 5s; Fly checks
# port 3000 every 15s on live and 30s on demo over a connection its edge pools
# between checks, so the socket is always closed before it is reused. Measured
# on demo 2026-08-19 at 15s spacing over one reused connection: `.X.X.X.X.X` --
# five failures of ten, perfectly alternating, which is the signature of the
# server closing rather than of anything being slow.
#
# `KEEP_ALIVE_TIMEOUT` (milliseconds) is the only way in: Next's standalone
# `server.js` reads it and passes it to `startServer`, which sets
# `server.keepAliveTimeout` and nothing else -- see `start-server.js:248`. In
# particular it does **not** raise `headersTimeout`, which Node defaults to
# 60s, so this value must stay below 60000 or idle connections get destroyed by
# the other timer instead.
#
# The uvicorn `--timeout-keep-alive` below is 75s, deliberately longer: the
# inner hop must outlive the outer one, or Next pools a socket to a backend
# that has already hung up. Both were measured failing independently, and
# fixing only uvicorn left this one failing 5 of 10 unchanged -- which is how
# the second hop was found. See
# `docs/measurements/2026-08-19-health-flap-is-the-proxy-hop.md`.
KEEP_ALIVE_TIMEOUT="${KEEP_ALIVE_TIMEOUT:-50000}" HOSTNAME=0.0.0.0 node frontend/server.js &
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
  echo "[entrypoint] starting chain runner (full=${RUNNER_INTERVAL_S:-900}s quote=${RUNNER_FAST_INTERVAL_S:-15}s)"
  python scripts/run_loop.py \
    --db "${DB_PATH}" --interval "${RUNNER_INTERVAL_S:-900}" \
    --fast-interval "${RUNNER_FAST_INTERVAL_S:-15}" &
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
  record_teardown "BACKEND exited"
elif [ -n "${loop_pid}" ] && ! kill -0 "${loop_pid}" 2>/dev/null; then
  # The runner gives up only after MAX_CONSECUTIVE_FAILURES, so reaching here
  # means repeated failure, not a blip. Sitting on it would leave the cockpit
  # serving a record that has silently stopped growing -- which reads as a
  # quiet slate, not as a broken instance.
  echo "[entrypoint] CHAIN RUNNER exited -- the record has stopped growing. Restarting."
  record_teardown "CHAIN RUNNER exited"
else
  echo "[entrypoint] FRONTEND exited -- restarting container"
  record_teardown "FRONTEND exited"
fi
# Non-zero, so Fly's on-failure restart policy actually fires. See `shutdown`.
shutdown 1
