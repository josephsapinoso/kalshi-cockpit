"""Kalshi API authentication: RSA-PSS request signing.

Ported from ``kalshi_orderbook_monitor/kalshi_auth.py``. The signing itself is
unchanged -- it works, and it cost hours to get right. What is added here is the
``signed_path`` helper, which the old repo had to retrofit after the bare-path
bug bit three separate call sites.

**It is RSA-PSS, not ED25519.** The old repo's README and CLAUDE.md both claimed
ED25519 for most of the project's life while the code did RSA-PSS. Anyone who
generates an ED25519 key will fail to authenticate with errors that look like
bad credentials.

The signed message is exactly, with no separators::

    {timestamp_ms}{HTTP_METHOD}{path}

Headers on every request:

===========================  ===============================================
``KALSHI-ACCESS-KEY``        the API key **id** (not a secret blob)
``KALSHI-ACCESS-SIGNATURE``  base64 RSA-PSS signature
``KALSHI-ACCESS-TIMESTAMP``  the same milliseconds used in the message
===========================  ===============================================

Sign the FULL path
------------------
Kalshi signs the full request path **including the ``/trade-api/v2`` prefix**.
This was confirmed empirically -- signing the bare path returns 401 while
signing the prefixed path returns 200 on an otherwise identical request. A 401
here looks exactly like bad credentials, which is what makes it expensive.

Derive the prefix from the base URL with :func:`signed_path` rather than
hardcoding it, so the signed string and the requested URL cannot drift apart.

Never use ``rstrip("/trade-api/v2")`` to strip that prefix. ``rstrip`` removes a
*character set*, not a suffix. It happens to produce the right answer for
``https://api.elections.kalshi.com/trade-api/v2`` (it stops at the ``m`` of
``.com``) but silently eats hostname characters for any base URL ending in any
of ``/ t r a d e - p i v 2``, including a trailing slash. Use ``removesuffix``.

Query strings are NOT signed -- verified 2026-08-06
---------------------------------------------------
Settled empirically by ``scripts/verify_auth.py`` against the live API, on an
otherwise identical ``GET /portfolio/fills?limit=1``::

    query sent, signed WITHOUT it  -> 200 OK
    query sent, signed WITH it     -> 401

**Kalshi signs the path only.** Appending the query string before signing
produces a 401 that looks exactly like bad credentials.

Note this contradicts the project handoff brief, which stated that query params
must be appended to the path before signing. The brief is wrong on this point;
the live API is the authority. Sign the path, send the query.

Key handling
------------
The private key is read from disk, used to sign, and never leaves this module.
Never read, echo, log, or write it. If a key is ever pasted into a transcript,
treat it as compromised and rotate it.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

# Kalshi signs the path only, NOT the query string. Verified 2026-08-06 by
# scripts/verify_auth.py: signing with the query returned 401 on a request that
# returned 200 when signed without it. See the module docstring.
SIGN_QUERY_STRING: bool = False


def signed_path(base_url: str, path: str, query: str = "") -> str:
    """Build the exact path string to sign for a request to ``base_url + path``.

    Derives the API prefix from ``base_url`` so the signed string cannot drift
    from the requested URL. ``path`` is the portion after the prefix, e.g.
    ``/portfolio/balance``.

    Args:
        base_url: e.g. ``https://api.elections.kalshi.com/trade-api/v2``
        path: the endpoint path, leading slash included.
        query: query string without the leading ``?``. Accepted so call sites
            can pass it uniformly, but **excluded** from the signed result --
            Kalshi signs the path only. Send the query on the URL; leave it out
            of the signature.

    Returns:
        The full path to sign, e.g. ``/trade-api/v2/portfolio/balance``.
    """
    prefix = urlsplit(base_url).path.rstrip("/")
    full = f"{prefix}{path}"

    if query and SIGN_QUERY_STRING:
        return f"{full}?{query}"
    return full


class KalshiAuth:
    """Handles RSA-PSS authentication for the Kalshi API."""

    def __init__(self, api_key: str, private_key_path: Path):
        self.api_key = api_key
        self.private_key = self._load_private_key(Path(private_key_path))

    def _load_private_key(self, path: Path) -> rsa.RSAPrivateKey:
        """Load the RSA private key from a PEM file.

        Checks existence and readability separately so the failure message says
        which one went wrong -- a permissions problem and a missing file look
        identical from a stack trace otherwise.
        """
        if not path.exists():
            raise FileNotFoundError(f"Private key file not found: {path}")
        if not os.access(path, os.R_OK):
            raise PermissionError(f"Cannot read private key file: {path}")

        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)

    def _sign(self, message: str) -> str:
        """Sign a message using RSA-PSS, MGF1(SHA-256), max salt length."""
        signature = self.private_key.sign(
            message.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def _headers(self, message: str, timestamp: str) -> dict[str, str]:
        return {
            "KALSHI-ACCESS-KEY": self.api_key,
            "KALSHI-ACCESS-SIGNATURE": self._sign(message),
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
        }

    def get_ws_headers(self, ws_path: str = "/trade-api/ws/v2") -> dict[str, str]:
        """Generate authentication headers for a WebSocket connection."""
        timestamp = str(int(time.time() * 1000))
        return self._headers(f"{timestamp}GET{ws_path}", timestamp)

    def get_rest_headers(self, method: str, path: str) -> dict[str, str]:
        """Generate authentication headers for a REST request.

        ``path`` must be the **full** signed path including the API prefix --
        build it with :func:`signed_path`, never by hand.
        """
        timestamp = str(int(time.time() * 1000))
        headers = self._headers(f"{timestamp}{method}{path}", timestamp)
        headers["Content-Type"] = "application/json"
        return headers
