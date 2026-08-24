"""`scripts/fetch_live_route.py`: the loopback fetcher's guards, pinned.

The script exists so a session can read what the backend actually served
instead of reconstructing it from the database. Its safety rests on three
structural properties -- GET-only, exact-path allowlist, hardcoded loopback
target -- and every one of them is pinned here, the set-valued ones
byte-exactly, the structural ones by AST so a future edit cannot reintroduce
a method or a configurable target without a test going red.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about the live backend.** The one HTTP exchange here runs against
  a throwaway server on a random localhost port; no test has ever seen port
  8000 on the Fly machine, its routes, or their payloads. A green suite says
  the guards hold, not that `/api/slate` serves anything.
- **Nothing about the image.** `!scripts/fetch_live_route.py` reaching the
  container is asserted in `tests/test_has_callers.py` (the ssh-invoked
  class), not here.
- **Nothing about the ssh convention.** That only a committed script runs
  over `flyctl ssh console` is a convention the agent keeps and Joe audits;
  no test can enforce it.
- **Nothing about the middleware.** The public 401 on port 3000 is
  `frontend/src/middleware.ts`'s contract and is untouched by this suite.
"""

from __future__ import annotations

import ast
import http.server
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fetch_live_route import (  # noqa: E402
    ALLOWED_PATHS,
    ALLOWED_QUERY_KEYS,
    BASE_URL,
    STDOUT_CAP_BYTES,
    PathNotAllowed,
    QueryNotAllowed,
    fetch,
    resolve_url,
    truncate_for_stdout,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_live_route.py"


def _module_ast() -> ast.Module:
    return ast.parse(SCRIPT.read_text(encoding="utf-8"))


class TestTheAllowlistIsPinned:
    def test_the_allowlist_is_exactly_the_nine_agreed_paths(self):
        # /api/parlays joined 2026-08-23 (ADR 0070) so the parlay desk's
        # served payload is verifiable on live; the lookup POST stays out --
        # this instrument is GET-only and a lookup mints a market.
        assert ALLOWED_PATHS == frozenset(
            {
                "/api/slate",
                "/api/gate",
                "/api/window",
                "/api/ledger",
                "/api/bets",
                "/api/board",
                "/api/health",
                "/api/scout",
                "/api/parlays",
            }
        )

    def test_query_keys_exist_only_for_ledger_and_bets(self):
        assert ALLOWED_QUERY_KEYS == {
            "/api/ledger": frozenset({"limit", "offset", "max_id"}),
            "/api/bets": frozenset({"limit"}),
        }

    def test_every_query_bearing_path_is_itself_allowlisted(self):
        assert set(ALLOWED_QUERY_KEYS) <= ALLOWED_PATHS


class TestNonAllowlistedRequestsAreRefused:
    def test_an_unknown_path_is_refused_and_the_error_names_the_allowlist(self):
        with pytest.raises(PathNotAllowed) as excinfo:
            resolve_url("/api/orders")
        for path in ALLOWED_PATHS:
            assert path in str(excinfo.value)

    def test_a_prefix_match_is_not_a_match(self):
        with pytest.raises(PathNotAllowed):
            resolve_url("/api/slate/extra")

    def test_a_full_url_cannot_smuggle_in_another_host(self):
        with pytest.raises(PathNotAllowed):
            resolve_url("http://example.com/api/slate")

    def test_a_scheme_relative_url_cannot_either(self):
        with pytest.raises(PathNotAllowed):
            resolve_url("//example.com/api/slate")

    def test_a_query_on_a_path_with_no_query_allowance_is_refused(self):
        with pytest.raises(QueryNotAllowed):
            resolve_url("/api/health?verbose=1")

    def test_an_unknown_query_key_on_ledger_is_refused(self):
        with pytest.raises(QueryNotAllowed):
            resolve_url("/api/ledger?db=/data/cockpit.db")

    def test_an_allowed_ledger_query_resolves_to_the_loopback(self):
        assert (
            resolve_url("/api/ledger?limit=1000&offset=2000")
            == "http://127.0.0.1:8000/api/ledger?limit=1000&offset=2000"
        )

    def test_a_bare_allowed_path_resolves_to_the_loopback(self):
        assert resolve_url("/api/slate") == "http://127.0.0.1:8000/api/slate"


class TestAMutationIsUnrepresentable:
    """GET-only is structural: no code path can carry a method or a body.

    Pinned by AST rather than by behaviour, because the property being claimed
    is about what the source *cannot express*, and only the source can show
    that.
    """

    def test_no_call_anywhere_passes_a_method_or_data_keyword(self):
        for node in ast.walk(_module_ast()):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    assert kw.arg not in ("method", "data"), (
                        f"a call at line {node.lineno} passes {kw.arg!r} -- "
                        f"that is the door a mutation walks through"
                    )

    def test_the_only_request_constructor_used_is_urlopen(self):
        """`urllib.request.Request` never appears.

        `urlopen` on a bare string with no `data` is a GET by stdlib
        definition; a `Request` object is the one place a method string could
        be attached.
        """
        for node in ast.walk(_module_ast()):
            if isinstance(node, ast.Attribute):
                assert node.attr != "Request"
            if isinstance(node, ast.Name):
                assert node.id != "Request"

    def test_urlopen_is_called_with_one_positional_and_only_a_timeout(self):
        calls = [
            node
            for node in ast.walk(_module_ast())
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "urlopen"
        ]
        assert len(calls) == 1, "exactly one network call exists"
        (call,) = calls
        assert len(call.args) == 1
        assert [kw.arg for kw in call.keywords] == ["timeout"]

    def test_the_cli_takes_no_method_flag(self):
        """No argparse argument is spelled anything like a method.

        Every `add_argument` name is enumerated and none of them is `method`
        or a flag; the parser defines exactly one positional, `path`.
        """
        names: list[str] = []
        for node in ast.walk(_module_ast()):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
            ):
                for arg in node.args:
                    assert isinstance(arg, ast.Constant)
                    names.append(arg.value)
        assert names == ["path"]


class TestTheTargetIsHardcodedLoopback:
    def test_the_base_url_is_the_backend_loopback_byte_exactly(self):
        assert BASE_URL == "http://127.0.0.1:8000"

    def test_the_base_url_is_a_literal_not_a_lookup(self):
        assignments = [
            node
            for node in _module_ast().body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "BASE_URL"
                for t in node.targets
            )
        ]
        assert len(assignments) == 1
        assert isinstance(assignments[0].value, ast.Constant)

    def test_no_environment_variable_is_read_anywhere(self):
        for node in ast.walk(_module_ast()):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv"), (
                    f"line {node.lineno} reads the environment -- the target "
                    f"must not be steerable"
                )

    def test_resolved_urls_always_start_with_the_loopback(self):
        for path in sorted(ALLOWED_PATHS):
            assert resolve_url(path).startswith("http://127.0.0.1:8000/")


class TestTheOutputCannotFloodATranscript:
    def test_a_small_body_passes_through_untouched_with_no_note(self):
        body, note = truncate_for_stdout(b'{"ok": true}')
        assert body == b'{"ok": true}'
        assert note == ""

    def test_a_body_over_the_cap_is_cut_and_the_note_counts_both_sizes(self):
        big = b"x" * (STDOUT_CAP_BYTES + 12345)
        body, note = truncate_for_stdout(big)
        assert len(body) == STDOUT_CAP_BYTES
        assert str(STDOUT_CAP_BYTES) in note
        assert str(STDOUT_CAP_BYTES + 12345) in note

    def test_the_cap_is_about_100kb(self):
        assert STDOUT_CAP_BYTES == 100_000


class TestFetchIsObservedToBeAGet:
    """One live exchange, against a throwaway localhost server.

    The handler records the request method; anything but GET would be recorded
    as such. This is the behavioural echo of the AST pins above -- it fails if
    `fetch` ever starts sending something else.
    """

    def test_fetch_sends_a_get_and_returns_status_and_body(self):
        seen: list[str] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - stdlib naming
                seen.append(self.command)
                payload = b'{"status": "ok"}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):  # quiet
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, body = fetch(f"http://127.0.0.1:{port}/api/health")
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
        assert status == 200
        assert body == b'{"status": "ok"}'
        assert seen == ["GET"]

    def test_an_http_error_status_still_yields_its_body(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - stdlib naming
                payload = b'{"detail": "not found"}'
                self.send_response(404)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, body = fetch(f"http://127.0.0.1:{port}/api/health")
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
        assert status == 404
        assert body == b'{"detail": "not found"}'


class TestTheCliRefusesBeforeItConnects:
    """A refused path exits 2 without any socket being opened.

    BASE_URL points at port 8000, which is not listening on the test machine;
    if a refused path ever reached `fetch`, this test would exit 3 (or hang)
    instead of 2, so the pass genuinely demonstrates refusal-before-connect.
    """

    def test_a_refused_path_exits_2_and_names_the_error_on_stderr(self, capsys):
        from fetch_live_route import main

        code = main(["/api/orders"])
        assert code == 2
        err = capsys.readouterr().err
        assert "PathNotAllowed" in err
        assert "/api/slate" in err  # the allowlist is in the message

    def test_a_refused_query_exits_2(self, capsys):
        from fetch_live_route import main

        code = main(["/api/health?verbose=1"])
        assert code == 2
        assert "QueryNotAllowed" in capsys.readouterr().err
