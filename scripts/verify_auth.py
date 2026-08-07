"""Settle Kalshi's request-signing rules empirically.

Two questions, both of which produce 401s that look exactly like bad
credentials, and both of which cost hours to debug by guessing:

1. **Does Kalshi sign the full path** (`/trade-api/v2/portfolio/balance`) or the
   bare path (`/portfolio/balance`)? The previous project confirmed *full*, and
   this re-confirms it rather than trusting a note.

2. **Are query strings part of the signed message?** This one is genuinely
   unresolved — the project handoff brief says query params must be appended
   before signing, and the previous repo's own skill file says they must not be
   and that filtered `get_orders`/`get_fills` 401 because of it. They cannot
   both be right.

Run:

    .venv\\Scripts\\python.exe scripts\\verify_auth.py

Then write the answer into `backend/kalshi/auth.py:SIGN_QUERY_STRING` and into
`.claude/skills/kalshi-api/SKILL.md`, and delete the uncertainty from both.

SAFETY
------
This script is **read-only**. It calls `GET /portfolio/balance` and
`GET /portfolio/fills`, and never places, cancels, or modifies anything.

It prints **pass/fail and HTTP status codes only** — never key material, never
a signature, never a balance. Nothing here is safe to change in that respect:
this output is exactly the kind of thing that ends up pasted into an issue.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ConfigError, KalshiConfig  # noqa: E402
from backend.kalshi.auth import KalshiAuth  # noqa: E402

TIMEOUT = 15.0


def _sign_and_call(
    auth: KalshiAuth,
    client: httpx.Client,
    base_url: str,
    request_path: str,
    signed_as: str,
    query: str = "",
) -> int:
    """Request `request_path` while signing `signed_as`. Returns the status code.

    Deliberately allows the signed string and the requested URL to differ --
    that mismatch is the entire experiment.
    """
    timestamp = str(int(time.time() * 1000))
    message = f"{timestamp}GET{signed_as}"
    headers = {
        "KALSHI-ACCESS-KEY": auth.api_key,
        "KALSHI-ACCESS-SIGNATURE": auth._sign(message),
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "Content-Type": "application/json",
    }
    url = f"{base_url}{request_path}"
    if query:
        url = f"{url}?{query}"
    try:
        return client.get(url, headers=headers, timeout=TIMEOUT).status_code
    except httpx.HTTPError as exc:
        print(f"    network error: {type(exc).__name__}")
        return -1


def main() -> int:
    try:
        cfg = KalshiConfig.load()
    except ConfigError as exc:
        print(f"FAIL  configuration: {exc}")
        return 2

    auth = KalshiAuth(cfg.api_key, cfg.private_key_path)
    # e.g. "/trade-api/v2" -- derived, never hardcoded, so the signed string and
    # the requested URL cannot drift apart.
    prefix = httpx.URL(cfg.rest_url).path.rstrip("/")
    origin = cfg.rest_url[: len(cfg.rest_url) - len(prefix)].rstrip("/")

    results: dict[str, bool] = {}

    with httpx.Client() as client:
        # -------------------------------------------------------------------
        # Question 1: full path vs bare path
        # -------------------------------------------------------------------
        print("\nQ1  Which path does Kalshi sign?")
        path = "/portfolio/balance"

        full_status = _sign_and_call(
            auth, client, origin, f"{prefix}{path}", signed_as=f"{prefix}{path}"
        )
        print(f"    signed FULL path ({prefix}{path}) -> HTTP {full_status}")

        bare_status = _sign_and_call(
            auth, client, origin, f"{prefix}{path}", signed_as=path
        )
        print(f"    signed BARE path ({path}) -> HTTP {bare_status}")

        if full_status == 200 and bare_status == 401:
            print("    RESULT: sign the FULL path, including the API prefix.")
            results["full_path"] = True
        elif full_status == 200 and bare_status == 200:
            print("    RESULT: INCONCLUSIVE -- both accepted. Kalshi may have "
                  "relaxed this. Prefer the full path anyway.")
            results["full_path"] = True
        elif full_status == 401 and bare_status == 200:
            print("    RESULT: SURPRISE -- sign the BARE path. Update auth.py "
                  "and the skill file; this reverses prior behaviour.")
            results["full_path"] = False
        else:
            print("    RESULT: FAILED -- neither worked. Check that the key is "
                  "RSA (not ED25519), the key id is the *id*, and the clock is "
                  "not skewed.")
            results["full_path"] = False

        # -------------------------------------------------------------------
        # Question 2: are query strings signed?
        # -------------------------------------------------------------------
        print("\nQ2  Are query strings part of the signed message?")
        path = "/portfolio/fills"
        query = "limit=1"

        without = _sign_and_call(
            auth, client, origin, f"{prefix}{path}",
            signed_as=f"{prefix}{path}", query=query,
        )
        print(f"    query sent, signed WITHOUT it -> HTTP {without}")

        with_query = _sign_and_call(
            auth, client, origin, f"{prefix}{path}",
            signed_as=f"{prefix}{path}?{query}", query=query,
        )
        print(f"    query sent, signed WITH it    -> HTTP {with_query}")

        if without == 200 and with_query != 200:
            print("    RESULT: query strings are NOT signed. "
                  "Set SIGN_QUERY_STRING = False.")
            results["query"] = True
        elif with_query == 200 and without != 200:
            print("    RESULT: query strings ARE signed. "
                  "Set SIGN_QUERY_STRING = True.")
            results["query"] = True
        elif without == 200 and with_query == 200:
            print("    RESULT: both accepted -- Kalshi ignores the query in the "
                  "signature check. Set SIGN_QUERY_STRING = False (simpler, and "
                  "matches the unsigned reading).")
            results["query"] = True
        else:
            print("    RESULT: FAILED -- neither worked. If Q1 also failed this "
                  "is a credential problem, not a signing-rule problem.")
            results["query"] = False

    print("\n" + "=" * 60)
    ok = all(results.values())
    print("ALL CHECKS RESOLVED" if ok else "UNRESOLVED -- see above")
    print("Record the answers in backend/kalshi/auth.py and "
          ".claude/skills/kalshi-api/SKILL.md.")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
