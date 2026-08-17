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

# A Discord webhook carries its token in the PATH, not in a query string or a
# header: `https://discord.com/api/webhooks/<id>/<token>`. That is the same
# hazard as the Odds API key, one URL shape further along -- and httpx logs the
# path just as readily as it logs the query. Anyone holding this string can post
# to the channel, so it is redacted from the id onward.
_WEBHOOK_PATTERN = re.compile(r"(?i)(/api/webhooks/)[\w./-]+")

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
    text = _WEBHOOK_PATTERN.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
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
        # `Formatter.format` caches the rendered traceback on the record, so a
        # record reaching a second handler can already carry one. Redacting it
        # here means the first handler's cache cannot defeat the second
        # handler's formatter. When it is still `None` -- the usual case at
        # filter time -- `CredentialRedactingFormatter` is what covers it.
        if isinstance(getattr(record, "exc_text", None), str):
            record.exc_text = redact(record.exc_text)
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


class CredentialRedactingFormatter(logging.Formatter):
    """Redacts credentials from the *rendered* record, tracebacks included.

    The filter cannot do this alone, and the reason is ordering. Filters run
    before formatting; a traceback does not exist until `Formatter.format`
    calls `formatException(record.exc_info)`. So a credential living only
    inside an exception's own text -- not in `record.msg`, not in
    `record.args` -- passes every filter and reaches the stream.

    `backend/odds/client.py` is the live site: it calls `logger.exception` on
    the one path that has just issued a request carrying the API key in its
    query string. Whether any `httpx` exception actually embeds the URL in its
    own message is **not established**, and this class deliberately does not
    depend on the answer -- the hole is closed by class rather than by
    enumerating which exception types leak.

    Redaction, never suppression. The traceback is still emitted in full; only
    the credential-shaped substrings inside it are replaced, so a redacted
    stack trace is still a debuggable one.
    """

    def formatException(self, ei: Any) -> str:  # noqa: N802 - stdlib's name
        return redact(super().formatException(ei))

    def format(self, record: logging.LogRecord) -> str:
        # `formatException` covers the traceback this call renders. A record
        # arriving with `exc_text` already cached -- rendered by an earlier
        # handler's plain formatter -- would bypass it, so the final string is
        # swept as well. Cheap, and it makes the guard independent of which
        # handler ran first.
        return redact(super().format(record))


def configure_logging(level: int = logging.INFO, **basic_config: Any) -> None:
    """Set up logging with redaction installed at the root.

    Call this once, early, in every entry point -- the API app, the runner
    scripts, and anything else that makes a request. `httpx` is additionally
    pinned to WARNING: its INFO line is one URL per request, which is both the
    leak above and pure noise at the volume the runner generates.

    The default format is set here rather than per call site because the
    container runs **two** of these processes and Fly interleaves their output
    into one stream. A line that says which process, at what level, from which
    logger is the difference between reading that stream and grepping it.
    """
    basic_config.setdefault(
        "format", "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    )
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
        # The formatter is what renders tracebacks, so it has to be swapped on
        # every handler too -- a filter cannot reach text that does not exist
        # yet. The format string is carried over rather than re-specified, so
        # this cannot silently change the layout `basicConfig` was given.
        if not isinstance(handler.formatter, CredentialRedactingFormatter):
            existing = handler.formatter
            handler.setFormatter(
                CredentialRedactingFormatter(
                    fmt=getattr(existing, "_fmt", None) or basic_config["format"],
                    datefmt=getattr(existing, "datefmt", None),
                )
            )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
