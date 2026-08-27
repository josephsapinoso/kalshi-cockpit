"""GET-only loopback fetcher for the live HTTP routes, invoked by path.

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/fetch_live_route.py /api/slate"

Why this file exists
--------------------
No session can read any live HTTP route except `/api/health`: `curl` is not in
the runtime image, and `frontend/src/middleware.ts` 401s everything else on the
public surface (uvicorn binds 127.0.0.1:8000 inside the container, unpublished;
Next on 3000 is the only published port). So every past handoff sentence of the
form "the screen shows X" was a database reconstruction, never a reading of the
served payload -- the "verification methods that lie" family. This script is
the reading: it runs inside the container, over the same loopback the Next
proxy uses, and prints what the backend actually served.

It lives under the same governance as `inspect_live_db.py`: `flyctl ssh
console` may only invoke a committed, reviewed script by path, so every line
that runs against the money box was reviewable in git before it ran.

Three structural properties, not conventions
--------------------------------------------
**A mutation is unrepresentable.** The one network call is
`urllib.request.urlopen(url, timeout=...)` with no `data` and no `Request`
object, which the stdlib defines as a GET. There is no method argument
anywhere -- not on the CLI, not on any function -- so a POST is not refused,
it cannot be expressed. `tests/test_fetch_live_route.py` pins this by AST.

**The target is hardcoded to the backend loopback.** `BASE_URL` is a module
constant, read from no argument and no environment variable. The caller
supplies a path; a full URL, a scheme, or a netloc in the argument is refused,
so the script cannot be pointed at anything but 127.0.0.1:8000.

**Only named paths pass, and almost no query strings.** `ALLOWED_PATHS` is an
exact-match set -- no prefixes, no wildcards -- and a query string is refused
unless the path has an entry in `ALLOWED_QUERY_KEYS` naming that exact key.
Anything else exits with a named error that lists the allowlist.

No credential is accepted, read, or printed. The backend requires none on
loopback GETs: `require_auth` in `backend/api/routes.py` is attached only to
mutating routes, and none of those is representable here.

What this does not establish
----------------------------
- **Nothing about the public surface.** This reads port 8000 behind the
  middleware. What a phone sees on port 3000 -- the middleware's auth, Next's
  proxying, the rendered page -- is a different pipeline, and a clean payload
  here does not certify any of it.
- **Nothing about freshness.** The payload is whatever the backend served at
  that instant. Staleness contracts live in the payload's own fields; this
  script does not interpret them.
- **Nothing about the data being right.** It prints what was served. Whether
  what was served is true is the whole project's question, not this script's.
- **Nothing about the ssh convention being followed.** The rule that only a
  committed script runs over `flyctl ssh console` is a convention the agent
  keeps and Joe audits; no script can enforce the rule it runs under.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.parse
import urllib.request

# The backend loopback, behind the Next middleware. Hardcoded deliberately:
# this script must not be pointable at a public URL, another host, or another
# port, so there is no argument and no environment variable that feeds it.
BASE_URL = "http://127.0.0.1:8000"

# Exact paths only. No prefixes, no wildcards: "/api/slate/anything" does not
# match "/api/slate". Every entry is a GET route in backend/api/routes.py with
# no auth dependency.
ALLOWED_PATHS = frozenset(
    {
        "/api/slate",
        "/api/gate",
        "/api/window",
        "/api/ledger",
        "/api/bets",
        "/api/board",
        "/api/health",
        "/api/scout",
        # The parlay desk's ladder (ADR 0070). GET, no auth, no query keys;
        # the lookup POST is deliberately NOT here -- this instrument is
        # GET-only by AST pin, and a lookup mints a market.
        "/api/parlays",
        # The held-parlay screen (ADR 0078). Same three properties as
        # `/api/parlays`: GET, no `require_auth`, no query keys. **The three
        # hedge POSTs stay out** -- `/api/hedge/positions`,
        # `/api/hedge/legs/{id}/resolve` and `.../close` all write, and this
        # instrument cannot express a POST at all.
        #
        # It is here for the reason the module docstring gives: without it,
        # every sentence about what the hedge screen shows on live would be a
        # database reconstruction rather than a reading of the served payload.
        # This route reaches the venue for a live book, so reconstructing it
        # from the database is not even possible.
        "/api/hedge",
    }
)

# The only query keys any allowlisted path may carry. A path absent from this
# mapping accepts no query string at all. The keys mirror the FastAPI Query
# parameters on the route: /api/ledger takes limit/offset/max_id (offset exists
# so the table can be read whole), /api/bets takes limit.
ALLOWED_QUERY_KEYS: dict[str, frozenset[str]] = {
    "/api/ledger": frozenset({"limit", "offset", "max_id"}),
    "/api/bets": frozenset({"limit"}),
}

# Stdout cap, so a huge payload cannot flood a transcript. ~100KB.
STDOUT_CAP_BYTES = 100_000

TIMEOUT_S = 30.0


class PathNotAllowed(Exception):
    """The requested path is not on the allowlist."""


class QueryNotAllowed(Exception):
    """The requested path carries a query string it is not allowed."""


def resolve_url(raw: str) -> str:
    """Turn a caller-supplied path into the one URL it is allowed to mean.

    Refuses anything with a scheme or netloc (so a full URL cannot smuggle in
    a different host), anything not on ``ALLOWED_PATHS`` byte-for-byte, and
    any query key not explicitly allowed for that path.
    """
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme or parts.netloc:
        raise PathNotAllowed(
            f"a full URL is refused; give a path only. Allowed: "
            f"{_allowlist_for_humans()}"
        )
    if parts.path not in ALLOWED_PATHS:
        raise PathNotAllowed(
            f"{parts.path!r} is not on the allowlist. Allowed: "
            f"{_allowlist_for_humans()}"
        )
    if parts.fragment:
        raise QueryNotAllowed(f"{raw!r}: a fragment has no meaning here; drop it")
    if parts.query:
        allowed_keys = ALLOWED_QUERY_KEYS.get(parts.path, frozenset())
        pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        for key, _ in pairs:
            if key not in allowed_keys:
                raise QueryNotAllowed(
                    f"query key {key!r} is not allowed on {parts.path}. "
                    f"Allowed keys here: {sorted(allowed_keys) or 'none'}"
                )
        query = urllib.parse.urlencode(pairs)
        return f"{BASE_URL}{parts.path}?{query}"
    return f"{BASE_URL}{parts.path}"


def fetch(url: str) -> tuple[int, bytes]:
    """One GET against ``url``; returns (status, body).

    ``urlopen`` with a bare string and no ``data`` is a GET by construction --
    there is nothing here a method could be passed to. An HTTP error status
    still has a body worth reading (FastAPI's JSON error detail), so it is
    returned rather than raised.
    """
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def truncate_for_stdout(body: bytes, cap: int = STDOUT_CAP_BYTES) -> tuple[bytes, str]:
    """Cap the body and say so; returns (what to print, note-or-empty)."""
    if len(body) <= cap:
        return body, ""
    note = f"[truncated: showing first {cap} of {len(body)} bytes]"
    return body[:cap], note


def _allowlist_for_humans() -> str:
    return ", ".join(sorted(ALLOWED_PATHS))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "GET one allowlisted route from the backend loopback "
            "(127.0.0.1:8000) and print the body to stdout."
        )
    )
    parser.add_argument(
        "path",
        help=(
            f"route path, e.g. /api/slate -- one of: {_allowlist_for_humans()}"
        ),
    )
    args = parser.parse_args(argv)

    try:
        url = resolve_url(args.path)
    except (PathNotAllowed, QueryNotAllowed) as err:
        print(f"{type(err).__name__}: {err}", file=sys.stderr)
        return 2

    try:
        status, body = fetch(url)
    except urllib.error.URLError as err:
        print(f"could not reach {BASE_URL}: {err.reason}", file=sys.stderr)
        return 3

    shown, note = truncate_for_stdout(body)
    print(f"HTTP {status} {url}", file=sys.stderr)
    sys.stdout.buffer.write(shown)
    sys.stdout.buffer.write(b"\n")
    if note:
        print(note, file=sys.stderr)
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    sys.exit(main())
