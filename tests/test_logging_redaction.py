"""The filter that exists because a live credential reached a transcript.

`backend/logging_setup.py` was written after a run put a working Odds API key
into a terminal: `httpx` logs the full request URL at INFO and The Odds API
takes its key as a query parameter, so making a request was enough. Nothing in
this project logged it deliberately.

**It had no tests.** A module whose entire job is to prevent one specific,
already-observed failure, and nothing checked that it does — which is the same
shape as `notify/discord.py` being imported by nothing, one layer down: the code
was written, the incident was documented, and the link between them was never
made.

What these tests do NOT establish
---------------------------------
That every credential shape is covered. Redaction here is deliberately broad and
pattern-based, and a pattern only catches what someone thought of. The two
covered below are the two this project has actually shipped: a key in a query
string, and a token in a URL path.
"""

from __future__ import annotations

import logging

from backend.logging_setup import (
    REDACTED,
    CredentialRedactingFilter,
    configure_logging,
    redact,
)

ODDS_URL = (
    "HTTP Request: GET https://api.the-odds-api.com/v4/sports/baseball_mlb/"
    "odds?apiKey=1f4a9c0e2b7d8a6f5e3c1b0d9a8f7e6c&regions=us%2Ceu "
    '"HTTP/1.1 200 OK"'
)
WEBHOOK_URL = (
    "https://discord.com/api/webhooks/1402938475610293847/"
    "xQ2v9LmT4pR7wYzB1nK6sHfJdA0cE8gU3iO5rV7tX9yZ2bN4mQ6pL1kS8jF0hD"
)


class TestTheIncidentThatCausedThisModule:
    def test_an_odds_key_in_a_query_string_is_removed(self):
        cleaned = redact(ODDS_URL)
        assert "1f4a9c0e2b7d8a6f5e3c1b0d9a8f7e6c" not in cleaned
        assert f"apiKey={REDACTED}" in cleaned

    def test_the_parameter_name_survives_so_the_line_stays_useful(self):
        """A line with the query stripped entirely is unusable for debugging.
        Keeping the name says what kind of request it was."""
        cleaned = redact(ODDS_URL)
        assert "baseball_mlb" in cleaned
        assert "regions=us%2Ceu" in cleaned

    def test_a_line_with_no_credential_is_left_alone(self):
        """A filter that mangles ordinary log lines gets turned off."""
        plain = "pricing pass: {'recommendations': 104, 'surfaced': 0}"
        assert redact(plain) == plain


class TestATokenInAPathNotAQueryString:
    """A Discord webhook is `.../api/webhooks/<id>/<token>`.

    Same hazard as the Odds key, one URL shape further along: anyone holding the
    string can post to the channel, and it never appears as `key=` or as a
    bearer header, so every pattern written for the original incident misses it.
    """

    def test_a_webhook_token_is_removed(self):
        cleaned = redact(f"HTTP Request: POST {WEBHOOK_URL}")
        assert "xQ2v9LmT4pR7wYzB1nK6sHfJdA0cE8gU3iO5rV7tX9yZ2bN4mQ6pL1kS8jF0hD" not in cleaned

    def test_the_webhook_id_goes_too(self):
        """The id alone is not a credential, but leaving it in a log next to a
        redacted token invites someone to think the pair is safe to paste."""
        assert "1402938475610293847" not in redact(WEBHOOK_URL)

    def test_it_is_still_recognisable_as_a_discord_post(self):
        cleaned = redact(f"POST {WEBHOOK_URL} 204")
        assert "discord.com/api/webhooks/" in cleaned
        assert REDACTED in cleaned


class TestPrivateKeyMaterial:
    def test_a_pem_block_never_survives(self):
        pem = (
            "loaded key:\n-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEAv3Nk9Q\nfakefakefake\n"
            "-----END RSA PRIVATE KEY-----\ndone"
        )
        cleaned = redact(pem)
        assert "MIIEowIBAAKCAQEAv3Nk9Q" not in cleaned
        assert cleaned.startswith("loaded key:")
        assert cleaned.endswith("done")


class TestTheFilterCatchesTheShapeHttpxActuallyUses:
    """`logger.info("GET %s", url)` keeps the URL in `record.args`.

    A filter that rewrote only `record.msg` would let the original leak straight
    through, because httpx never puts the URL in the message. This is the test
    that separates the working implementation from the obvious one.
    """

    def _record(self, msg, args):
        return logging.LogRecord(
            "httpx", logging.INFO, __file__, 1, msg, args, None
        )

    def test_a_credential_in_args_is_redacted(self):
        record = self._record("HTTP Request: %s", (ODDS_URL,))
        CredentialRedactingFilter().filter(record)
        assert "1f4a9c0e2b7d8a6f5e3c1b0d9a8f7e6c" not in record.getMessage()

    def test_a_credential_in_the_message_is_redacted(self):
        record = self._record(ODDS_URL, None)
        CredentialRedactingFilter().filter(record)
        assert "1f4a9c0e2b7d8a6f5e3c1b0d9a8f7e6c" not in record.getMessage()

    def test_dict_style_args_are_redacted_too(self):
        # Wrapped in a tuple: that is how `logging` itself passes a mapping.
        record = self._record("%(url)s", ({"url": ODDS_URL},))
        CredentialRedactingFilter().filter(record)
        assert "1f4a9c0e2b7d8a6f5e3c1b0d9a8f7e6c" not in record.getMessage()

    def test_the_filter_returns_true_so_the_record_is_still_emitted(self):
        """Redaction, not suppression. A filter that swallowed the record would
        hide the request entirely and look like a working redaction."""
        record = self._record(ODDS_URL, None)
        assert CredentialRedactingFilter().filter(record) is True


class TestItIsInstalledWhereRecordsActuallyConverge:
    """A filter on a logger runs only for records logged *directly* on it.

    So a root-logger filter never sees a child logger's records -- and every
    credential this project can leak comes from a child logger inside a library.
    Handlers are where every record converges.
    """

    def test_a_child_loggers_record_is_redacted_end_to_end(self, caplog):
        configure_logging(level=logging.INFO, force=True)
        root = logging.getLogger()

        emitted: list[str] = []

        class Capture(logging.Handler):
            def emit(self, record):
                emitted.append(record.getMessage())

        sink = Capture()
        for f in root.handlers[0].filters:
            sink.addFilter(f)
        root.addHandler(sink)
        try:
            # NOT `httpx`: `configure_logging` pins that logger to WARNING, so
            # an INFO record there is dropped before any filter runs -- which
            # would make this test pass for the wrong reason. Any other child
            # logger exercises the path that actually matters.
            logging.getLogger("some.library").info("HTTP Request: %s", ODDS_URL)
        finally:
            root.removeHandler(sink)

        assert emitted, "nothing reached the handler"
        assert "1f4a9c0e2b7d8a6f5e3c1b0d9a8f7e6c" not in emitted[0]

    def test_every_root_handler_carries_the_filter(self):
        configure_logging(level=logging.INFO, force=True)
        root = logging.getLogger()
        assert root.handlers
        for handler in root.handlers:
            assert any(
                isinstance(f, CredentialRedactingFilter) for f in handler.filters
            ), f"{handler!r} would emit records unredacted"

    def test_configuring_twice_does_not_stack_filters(self):
        """Entry points call this defensively; duplicated filters would redact
        an already-redacted line and make the cost grow with restarts."""
        configure_logging(level=logging.INFO, force=True)
        configure_logging(level=logging.INFO)
        root = logging.getLogger()
        for handler in root.handlers:
            assert (
                sum(
                    isinstance(f, CredentialRedactingFilter)
                    for f in handler.filters
                )
                == 1
            )

    def test_httpx_is_pinned_above_the_level_that_leaked(self):
        """The redaction is the belt; this is the braces. httpx's INFO line is
        one full URL per request, which at the runner's volume is both the leak
        and pure noise."""
        configure_logging(level=logging.INFO, force=True)
        assert logging.getLogger("httpx").level >= logging.WARNING
