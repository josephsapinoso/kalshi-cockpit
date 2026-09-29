"""`scripts/probe_loopback_latency.py`: the in-box probe that bisects #193's stall.

No network in these tests except one local `http.server` on an ephemeral port.
The probe's own targets are loopback constants on the live box, and nothing
here reaches them.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about the live box.** Every timing below was produced by this file.
- **Nothing about where the stall is.** A green suite says the instrument
  times what it is pointed at and cannot be pointed anywhere else. The
  reading is taken on the box, and it is interpreted in the measurement doc.
"""

from __future__ import annotations

import ast
import http.server
import re
import threading
from pathlib import Path

import pytest

from scripts import probe_loopback_latency as probe

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probe_loopback_latency.py"


def _module_ast() -> ast.Module:
    return ast.parse(SCRIPT.read_text(encoding="utf-8"))


class TestTheTargetsAreFixedLoopback:
    def test_the_three_targets_are_exactly_the_agreed_urls(self):
        assert probe.TARGETS == (
            ("uvicorn", "http://127.0.0.1:8000/api/health"),
            ("next-proxy", "http://127.0.0.1:3000/api/health"),
            ("next-only", "http://127.0.0.1:3000/login"),
        )

    def test_no_argument_names_a_url_host_port_or_path(self):
        """Mutation: add a `--url` flag. Its option string names it here."""
        flags = set()
        for node in ast.walk(_module_ast()):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
            ):
                flags.update(a.value for a in node.args if isinstance(a, ast.Constant))
        assert flags == {"--seconds", "--interval", "--slow-ms", "--json"}

    def test_no_environment_variable_is_read(self):
        source = SCRIPT.read_text(encoding="utf-8").split('"""', 2)[-1]
        assert "environ" not in source and "getenv" not in source


class TestAMutationIsUnrepresentable:
    def test_no_call_passes_a_method_or_data_keyword(self):
        for node in ast.walk(_module_ast()):
            if isinstance(node, ast.Call):
                keywords = {k.arg for k in node.keywords}
                assert not keywords & {"data", "method"}, ast.unparse(node)

    def test_no_request_object_is_built(self):
        for node in ast.walk(_module_ast()):
            if isinstance(node, (ast.Attribute, ast.Name)):
                name = node.attr if isinstance(node, ast.Attribute) else node.id
                assert name != "Request", "urllib.request.Request can carry a method"

    def test_the_opener_is_called_with_one_positional_and_only_a_timeout(self):
        calls = [
            node
            for node in ast.walk(_module_ast())
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "opener"
        ]
        assert len(calls) == 1
        (call,) = calls
        assert len(call.args) == 1
        assert [k.arg for k in call.keywords] == ["timeout"]

    def test_nothing_is_written_or_spawned(self):
        source = SCRIPT.read_text(encoding="utf-8").split('"""', 2)[-1]
        for pattern in (
            r"\bunlink\b",
            r"\bsubprocess\b",
            r"write_text|write_bytes",
            r"open\([^)]*[\"'](?:w|a|r\+)[\"']",
            r"\bsqlite3\b",
        ):
            assert not re.search(pattern, source), pattern


class TestTheBoundsAreEnforced:
    """`run` is stubbed, so a missing guard fails in milliseconds.

    Without the stub, dropping a guard would really start a 901 s probe (it
    did once, 2026-09-28). A test that hangs for 15 minutes is not a red test.
    """

    @pytest.fixture
    def ran(self, monkeypatch):
        calls: list = []
        monkeypatch.setattr(probe, "run", lambda *a, **k: calls.append(a) or {
            "slow": [], "summary": {},
        })
        return calls

    @pytest.mark.parametrize("seconds", ["0", "-1", "901"])
    def test_seconds_outside_the_cap_is_refused(self, seconds, ran):
        """Mutation: drop the `--seconds` check -- `run` is called."""
        with pytest.raises(SystemExit):
            probe.main(["--seconds", seconds])
        assert ran == []

    def test_an_interval_under_the_floor_is_refused(self, ran):
        """Mutation: drop the `--interval` check -- `run` is called."""
        with pytest.raises(SystemExit):
            probe.main(["--seconds", "1", "--interval", "0.1"])
        assert ran == []

    def test_the_cap_itself_is_allowed(self, ran):
        assert probe.main(["--seconds", "900", "--interval", "0.25"]) == 0
        assert ran == [(900.0, 0.25, 1000.0)]


class _FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, s):
        self.now += s


class TestTheRunReportsWhatItTimed:
    def test_a_slow_answer_is_echoed_and_counted_against_its_own_target(self):
        clock = _FakeClock()
        echoed: list[str] = []

        def get(url):
            # next-proxy is slow on the second round only.
            slow = url.endswith(":3000/api/health") and clock.now >= 1.0
            return 200, 3100.0 if slow else 90.0, None

        result = probe.run(
            2.0, 1.0, 1000.0,
            get=get, monotonic=clock.monotonic, sleep=clock.sleep,
            stamp=lambda: "T", echo=echoed.append,
        )
        summary = result["summary"]
        assert summary["uvicorn"]["slow"] == 0
        assert summary["next-proxy"]["slow"] == 1
        assert summary["next-only"]["slow"] == 0
        assert summary["next-proxy"]["n"] == 2
        assert summary["next-proxy"]["max_ms"] == 3100.0
        assert echoed == ["SLOW T next-proxy status=200 3100 ms error=None"]

    def test_a_connection_failure_is_an_error_not_a_timing(self):
        """Mutation: append the failed request's ms to samples -- p50 moves."""
        clock = _FakeClock()

        def get(url):
            if url.startswith("http://127.0.0.1:8000"):
                return None, 30000.0, "URLError"
            return 200, 80.0, None

        result = probe.run(
            1.0, 1.0, 1000.0,
            get=get, monotonic=clock.monotonic, sleep=clock.sleep,
            stamp=lambda: "T", echo=lambda _: None,
        )
        uvicorn = result["summary"]["uvicorn"]
        assert uvicorn["errors"] == 1
        assert uvicorn["n"] == 0
        assert uvicorn["p50_ms"] is None
        assert result["slow"][0]["error"] == "URLError"

    def test_percentiles_are_nearest_rank(self):
        ms = [float(v) for v in range(1, 21)]  # 1..20
        assert probe.percentile(ms, 0.50) == 10.0
        assert probe.percentile(ms, 0.95) == 19.0
        assert probe.percentile([], 0.5) is None

    def test_render_prints_one_row_per_target(self):
        clock = _FakeClock()
        result = probe.run(
            1.0, 1.0, 1000.0,
            get=lambda url: (200, 100.0, None),
            monotonic=clock.monotonic, sleep=clock.sleep,
            stamp=lambda: "T", echo=lambda _: None,
        )
        text = probe.render(result)
        for name, _ in probe.TARGETS:
            assert re.search(rf"^{re.escape(name)}\s+1\s+0\s+0\s+100", text, re.M), name


class TestTimedGetIsObservedToBeAGet:
    def test_it_sends_a_get_and_returns_the_status(self):
        seen: list[str] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                seen.append(self.command)
                self.send_response(204)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, ms, error = probe.timed_get(f"http://127.0.0.1:{server.server_port}/x")
        finally:
            server.shutdown()
        assert (status, error) == (204, None)
        assert ms >= 0
        assert seen == ["GET"]
