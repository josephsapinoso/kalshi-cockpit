# Kalshi cockpit -- one image, two processes.
#
# The Python backend holds a persistent Kalshi WebSocket, which rules out
# serverless: it needs a long-running process and a disk. Next.js serves the UI
# and proxies /api to uvicorn on loopback, so only one port is ever exposed.
#
# The SAME image runs both the public demo and the private live instance. What
# differs is entirely configuration: the demo gets INSTANCE_MODE=demo, no
# secrets, and no volume. Building two images would let them drift apart, and
# the one that must never drift is the one holding real money.

# ---------------------------------------------------------------------------
# Stage 1 -- build the frontend
# ---------------------------------------------------------------------------
FROM node:22-slim AS frontend

WORKDIR /build

# Dependencies first: this layer is cached unless package.json changes, which
# is the difference between a 10-second rebuild and a 2-minute one.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 -- Python dependencies
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS backend

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 3 -- runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Node is needed to run the Next standalone server. Copied from the official
# image rather than installed via apt, which pulls a much older version.
COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production \
    PORT=3000 \
    API_ORIGIN=http://127.0.0.1:8000 \
    DB_PATH=/data/cockpit.db

COPY --from=backend /opt/venv /opt/venv
COPY backend/ ./backend/
# The chain runner's entry point. The live entrypoint executes
# `scripts/run_loop.py`, so omitting this builds an image that starts, reports
# healthy, serves pages -- and cannot record anything, because the one process
# that grows the evidence record is missing from the filesystem.
COPY scripts/ ./scripts/

# The standalone output ships its own minimal node_modules; static/ and public/
# are not traced into it and must be copied alongside.
COPY --from=frontend /build/.next/standalone ./frontend/
COPY --from=frontend /build/.next/static ./frontend/.next/static
COPY --from=frontend /build/public ./frontend/public

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Non-root. The volume mount point is created and chowned here because Fly
# mounts it as root otherwise and the app cannot write its database.
RUN useradd --create-home --uid 10001 cockpit \
 && mkdir -p /data \
 && chown -R cockpit:cockpit /app /data
USER cockpit

EXPOSE 3000

# Both processes must be up. Checking only the Next port would report healthy
# while the backend -- and therefore every price on the page -- was dead.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request as u; \
u.urlopen('http://127.0.0.1:8000/api/health', timeout=4); \
u.urlopen('http://127.0.0.1:3000/', timeout=4)" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
