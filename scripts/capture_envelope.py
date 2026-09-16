"""A capture that does not record its request cannot make an ABSENCE readable.

This module is the gate every new fixture capture writes through. It is small on
purpose: it refuses one specific document, and the refusal is the whole feature.

The defect it exists for -- ADR 0157
------------------------------------
`tests/fixtures/odds_mlb_h2h_spreads_totals.json` carries

    "params": {"regions": ["us", "eu"], "markets": ["h2h", "spreads", "totals"]}

and its sibling `tests/fixtures/odds_mlb_player_props.json` carries no such
envelope at all. That asymmetry killed a real finding. The claim was *no sharp
book quotes player props, so four of the ten named bookmakers are dead weight on
the prop endpoint*. The prop capture returned nine books, every one of them a US
book, and not one of `pinnacle`, `matchbook` or `betfair_ex_eu`.

Nine US books and no EU book is **exactly what `regions=us` returns**. So

    "EU books do not quote player props"        (a fact about the world)
    "that capture never asked for EU"           (a fact about the request)

produce the byte-identical file. The parameter that decides between them is the
one the capture did not record, and no amount of re-reading the payload recovers
it. The finding is filed unverified; the confound is the durable part.

The general rule, which is bigger than the odds feed
----------------------------------------------------
**A present thing is evidence on its own. An absent thing is evidence only
against the question that was asked.** This repo reasons from absences
constantly -- which book is missing from a devig, which market key came back
empty, which series returned no events, whether a leg had no resting bid. Every
one of those readings is unavailable on a payload whose request is unknown.

So: a captured payload is not the response. It is the *pair* (request, response).
Storing half of it stores something that looks complete and is not.

What a recorded request must contain
------------------------------------
`request_envelope` builds it and refuses anything less:

    method    the HTTP verb, non-empty
    endpoint  the URL or path, non-empty -- a template like
              "/v4/sports/{sport}/odds" is fine, a bare "" is not
    params    the query parameters actually sent, non-empty

`params` must be non-empty because the empty dict is ambiguous in the same way
the missing envelope is: it cannot be told apart from an author who did not
bother. A genuinely parameterless endpoint records the fact explicitly, e.g.
`params={"none": "this endpoint takes no query parameters"}`.

The credential hazard this rule creates, and the refusal that closes it
----------------------------------------------------------------------
Recording query parameters is exactly the move that leaked the Odds API key
once: that vendor takes its credential **as a query parameter** and `httpx` logs
full URLs at INFO (`backend/logging_setup.py` exists because of it, and
`tasks/lessons.md` records it). A rule that says "write down every parameter you
sent" would, followed literally, commit the key into a public repo.

So `request_envelope` refuses a credential-shaped parameter by name and refuses
any value that matches a known credential env var, rather than silently dropping
it. Dropping would be worse than refusing: the envelope would then be a partial
record claiming to be a whole one, which is the defect this module exists to fix
wearing a different hat.

What this module does not do
----------------------------
- **It does not make an existing fixture readable.** The fixtures that predate
  it are dispositioned in `tests/test_captures_carry_their_request.py`; getting
  a request record back onto one of them means re-capturing it, which for the
  odds feed costs credits and is the operator's call.
- **It does not verify the request it is handed.** It records what the caller
  says it sent. A script that builds the envelope from constants and the request
  from `os.environ` can still lie; `capture_nfl_odds_fixture.py` avoids that by
  deriving both from the same module constants, and that coupling is the point.
- **It asserts nothing about the response.** A capture that aborts on an empty
  body is each script's own business.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

#: The key a capture document stores its request record under. One name, so a
#: reader never has to guess and a grep finds every capture that has one.
REQUEST_KEY = "request"

#: Parameter names that carry a secret on some vendor somewhere. Matched
#: case-insensitively against the parameter NAME. The Odds API uses `apiKey`;
#: the rest are here so the next vendor does not need this file edited under
#: time pressure.
CREDENTIAL_PARAM_NAMES = frozenset(
    {
        "apikey",
        "api_key",
        "key",
        "token",
        "access_token",
        "auth",
        "authorization",
        "secret",
        "password",
        "signature",
        "sig",
    }
)

#: Environment variables whose value must never appear inside an envelope, even
#: under an innocent-looking parameter name. Checked by VALUE, so a key smuggled
#: in as `{"q": "<the key>"}` is refused too.
CREDENTIAL_ENV_VARS = (
    "ODDS_API_KEY",
    "KALSHI_PRIVATE_KEY",
    "ANTHROPIC_API_KEY",
    "SESSION_SECRET",
    "API_TOKEN",
)


class CaptureEnvelopeError(RuntimeError):
    """A capture was about to be written without a usable request record."""


def _refuse_credentials(params: Mapping[str, Any]) -> None:
    """Refuse, never redact. See the module docstring on why not redact."""
    for name, value in params.items():
        if str(name).strip().lower() in CREDENTIAL_PARAM_NAMES:
            raise CaptureEnvelopeError(
                f"REFUSING to record the request parameter {name!r}: its name is "
                "credential-shaped. The Odds API puts its key in the query "
                "string and this repo is public. Record the request WITHOUT the "
                "credential -- omit the parameter entirely rather than blanking "
                "it, so nobody later reads a blank as 'no key was sent'."
            )
    rendered = json.dumps(params, default=str)
    for env_var in CREDENTIAL_ENV_VARS:
        secret = os.environ.get(env_var, "")
        if secret and secret in rendered:
            raise CaptureEnvelopeError(
                f"REFUSING to record a request whose parameters contain the live "
                f"{env_var}. It is in this process's memory only -- do not paste "
                "any part of this envelope anywhere. Rotate if it reached disk."
            )


def request_envelope(
    *,
    endpoint: str,
    params: Mapping[str, Any],
    method: str = "GET",
    note: str = "",
) -> dict[str, Any]:
    """The record of what was asked for. Raises rather than returning a partial.

    `params` must be non-empty: an empty mapping is indistinguishable from an
    author who did not fill it in, which is the exact ambiguity this module
    exists to remove. An endpoint that genuinely takes none says so in words.
    """
    if not str(method).strip():
        raise CaptureEnvelopeError("A request envelope needs a non-empty `method`.")
    if not str(endpoint).strip():
        raise CaptureEnvelopeError(
            "A request envelope needs a non-empty `endpoint`. A template such as "
            "'/v4/sports/{sport}/odds' is fine; the empty string is not."
        )
    if not isinstance(params, Mapping):
        raise CaptureEnvelopeError(
            f"`params` must be a mapping of what was sent, not {type(params).__name__}."
        )
    if not params:
        raise CaptureEnvelopeError(
            "A request envelope needs non-empty `params`. An empty dict reads "
            "exactly like a forgotten one -- if the endpoint takes no query "
            "parameters, say so: "
            'params={"none": "this endpoint takes no query parameters"}.'
        )
    _refuse_credentials(params)

    envelope: dict[str, Any] = {
        "method": str(method).strip().upper(),
        "endpoint": str(endpoint).strip(),
        "params": dict(params),
    }
    if note:
        envelope["note"] = note
    return envelope


def assert_records_its_request(document: Mapping[str, Any], *, what: str) -> None:
    """Refuse a capture document that cannot say what it asked for."""
    if not isinstance(document, Mapping):
        raise CaptureEnvelopeError(
            f"REFUSING TO WRITE {what}: a capture document must be a mapping, so "
            f"there is somewhere for its request to live; got {type(document).__name__}."
        )
    envelope = document.get(REQUEST_KEY)
    if envelope is None:
        raise CaptureEnvelopeError(
            f"REFUSING TO WRITE {what}: it carries no {REQUEST_KEY!r} block. A "
            "payload without its request cannot make an absence readable -- a "
            "book missing from it and a book never asked for produce the same "
            "file. See ADR 0157 and scripts/capture_envelope.py."
        )
    if not isinstance(envelope, Mapping):
        raise CaptureEnvelopeError(
            f"REFUSING TO WRITE {what}: {REQUEST_KEY!r} must be a mapping, "
            f"got {type(envelope).__name__}."
        )
    # Re-validate rather than trusting that `request_envelope` built it: a
    # caller can assemble the dict by hand, and a check that only runs on the
    # happy path is not a check.
    request_envelope(
        endpoint=str(envelope.get("endpoint", "")),
        params=envelope.get("params") if isinstance(envelope.get("params"), Mapping) else {},
        method=str(envelope.get("method", "")),
    )


def write_capture(
    path: Path,
    document: Mapping[str, Any],
    *,
    indent: int = 2,
    before_write: Callable[[str], None] | None = None,
) -> None:
    """Serialise and write a capture, or refuse it for having no request record.

    `before_write` receives the exact text about to hit disk, so a script's own
    guards -- the credential scan in `capture_nfl_odds_fixture.py`, say -- run
    against what is written rather than against what was intended.
    """
    assert_records_its_request(document, what=str(path))
    serialised = json.dumps(document, indent=indent, sort_keys=True)
    if before_write is not None:
        before_write(serialised)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialised, encoding="utf-8")
