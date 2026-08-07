"""Logging that cannot print a credential.

Written after a live run put a working Odds API key into a terminal transcript.
Nothing in this project logged it deliberately: `httpx` logs the full request
URL at INFO, and The Odds API takes its key as a **query parameter**, so simply
making a request was enough.

    INFO httpx: HTTP Request: GET https://api.the-odds-api.com/v4/sports/
    baseball_mlb/odds?apiKey=<the real key>&regions=us%2Ceu ... "HTTP/1.1 200 OK"

That is the whole failure. No code had to be careless -- a third-party library's
default log format did it, and it would have done it on every deploy, in Fly
logs, for as long as the runner ran.

The fix is a redaction filter on the **root** logger rather than a tidier call
site, because the leak did not come from a call site. A filter installed at the
root catches every logger in the process, including ones added later by
libraries nobody thought about.

Redaction is deliberately pattern-based and broad: it is cheaper to redact a
harmless string than to miss a live one.
"""

from __future__ import annotations

import logging
import re
from typing import Any

# Query parameters whose values are credentials. Matched case-insensitively.
_SECRET_QUERY_KEYS = ("apikey", "api_key", "key", "token", "access_token", "secret")

_QUERY_PATTERN = re.compile(
    r"(?i)\b(" + "|".join(_SECRET_QUERY_KEYS) + r")=([^&\s\"'<>]+)"
)

# Bearer tokens and PEM material, in case either ever reaches a log line.
_BEARER_PATTERN = re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._\-]{8,})")
_PEM_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)

REDACTED = "<redacted>"


def redact(text: str) -> str:
    """Remove credential-shaped substrings from a log line.

    Keeps the parameter *name* and drops the value, so a redacted line still
    says what kind of request it was -- `apiKey=<redacted>` is far more useful
    when debugging than a line with the query string stripped entirely.
    """
    if not text:
        return text
    text = _PEM_PATTERN.sub(f"{REDACTED} (private key)", text)
    text = _QUERY_PATTERN.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
    text = _BEARER_PATTERN.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    return text


class CredentialRedactingFilter(logging.Filter):
    """Redacts credentials from the message and from any string arguments.

    Both matter. `logger.info("GET %s", url)` keeps the URL in `record.args`
    until formatting, so a filter that only rewrote `record.msg` would let the
    key through -- which is exactly the shape `httpx` uses.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact(a) if isinstance(a, str) else a for a in record.args
                )
        return True


def configure_logging(level: int = logging.INFO, **basic_config: Any) -> None:
    """Set up logging with redaction installed at the root.

    Call this once, early, in every entry point -- the API app, the runner
    scripts, and anything else that makes a request. `httpx` is additionally
    pinned to WARNING: its INFO line is one URL per request, which is both the
    leak above and pure noise at the volume the runner generates.
    """
    logging.basicConfig(level=level, **basic_config)

    root = logging.getLogger()
    if not any(isinstance(f, CredentialRedactingFilter) for f in root.filters):
        root.addFilter(CredentialRedactingFilter())

    # A filter on the root logger does NOT apply to records emitted by child
    # loggers -- filters attached to a logger only run for records logged
    # directly on it. Handlers are where every record actually converges, so
    # the filter goes on each of them too.
    for handler in root.handlers:
        if not any(isinstance(f, CredentialRedactingFilter) for f in handler.filters):
            handler.addFilter(CredentialRedactingFilter())

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
