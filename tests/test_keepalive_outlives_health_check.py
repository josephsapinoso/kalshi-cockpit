"""Both keep-alive timers must outlive the health check interval, on every deploy.

**What this establishes.** That `docker/entrypoint.sh` sets an explicit
keep-alive on *both* hops the health check traverses — `KEEP_ALIVE_TIMEOUT` for
Next on port 3000, `--timeout-keep-alive` for uvicorn on port 8000 — that each
clears the `interval` of every `[checks.health]` block in every `fly*.toml`
with slack, that the inner hop outlives the outer one, and that Next's stays
below Node's 60s `headersTimeout`.

**What it does not.** It reads config files and never opens a socket, so it
cannot show the flapping has stopped; only live can. It does not cover any hop
added later — a third proxy would need its own line here.

**Why it exists, and why it names two hops rather than one.** Fly checks port
3000 (Next) and Next proxies to 8000 (uvicorn). Both processes defaulted to a
**5 second** keep-alive against a **15s** (live) or **30s** (demo) check, so on
both hops the pooled connection was always dead when reused: ECONNRESET, "socket
hang up", machine marked unhealthy while the backend was entirely fine.

The two-hop shape is the whole lesson. uvicorn was fixed first, on the strength
of the proxy's own error line naming port 8000 — and demo, deployed with that
fix, still failed **5 of 10** at 15s spacing in exactly the same alternating
pattern. One hop's error message is not evidence about the other hop, and a
fix that is not measured after deploying is not a fix. Measurements in
`docs/measurements/2026-08-19-health-flap-is-the-proxy-hop.md`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = REPO_ROOT / "docker" / "entrypoint.sh"

# Node arms `headersTimeout` at 60s and Next's standalone server never raises
# it (`start-server.js` sets `keepAliveTimeout` and nothing else), so a
# keep-alive above this is destroyed by the other timer instead of helping.
NODE_HEADERS_TIMEOUT_S = 60.0

# The slack a keep-alive needs over the interval it is clearing. Absolute, not
# a ratio: what has to be absorbed is a *late* check -- the check's own timeout
# plus event-loop delay on a box measured stalling at 90% IO pressure -- and
# that lateness does not grow with the interval.
REQUIRED_SLACK_S = 10.0

_DURATION = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m|h)")
_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def parse_duration_seconds(text: str) -> float:
    """`15s`, `1m30s`, `500ms` -> seconds. Refuses anything else."""
    matches = _DURATION.findall(text.strip())
    if not matches:
        raise ValueError(f"unparseable Fly duration: {text!r}")
    consumed = "".join(f"{value}{unit}" for value, unit in matches)
    if consumed != text.strip():
        raise ValueError(f"unparseable Fly duration: {text!r}")
    return sum(float(value) * _UNIT_SECONDS[unit] for value, unit in matches)


def _entrypoint() -> str:
    return ENTRYPOINT.read_text(encoding="utf-8")


def uvicorn_keep_alive_s() -> float:
    """`--timeout-keep-alive`, off the actual uvicorn invocation."""
    source = _entrypoint()
    # Scoped to the invocation on purpose: matching anywhere in the file would
    # let the explanatory comment above it satisfy this test, and that comment
    # quotes both flag names.
    invocation = re.search(r"python -m uvicorn\b(?:[^\n]|\\\n)*?&", source)
    assert invocation is not None, "no `python -m uvicorn` invocation found"
    flag = re.search(r"--timeout-keep-alive[= ]+(\d+)", invocation.group(0))
    assert flag is not None, (
        "uvicorn is started without --timeout-keep-alive, so it defaults to 5s"
    )
    return float(flag.group(1))


def next_keep_alive_s() -> float:
    """`KEEP_ALIVE_TIMEOUT`, off the actual node invocation. Env is in ms."""
    source = _entrypoint()
    invocation = re.search(r"^[^\n#]*\bnode frontend/server\.js\b[^\n]*$",
                           source, re.MULTILINE)
    assert invocation is not None, "no `node frontend/server.js` line found"
    setting = re.search(r"KEEP_ALIVE_TIMEOUT=[\"']?\$?\{?KEEP_ALIVE_TIMEOUT"
                        r":-(\d+)\}?[\"']?", invocation.group(0))
    if setting is None:
        setting = re.search(r"KEEP_ALIVE_TIMEOUT=[\"']?(\d+)[\"']?",
                            invocation.group(0))
    assert setting is not None, (
        "node is started without KEEP_ALIVE_TIMEOUT, so Node defaults "
        "server.keepAliveTimeout to 5s -- this is the hop Fly checks"
    )
    return float(setting.group(1)) / 1000.0


def health_checks() -> dict[str, dict[str, float | int]]:
    """Every `[checks.health]` in every Fly config, by filename."""
    found: dict[str, dict[str, float | int]] = {}
    for config in sorted(REPO_ROOT.glob("fly*.toml")):
        text = config.read_text(encoding="utf-8")
        block = re.search(
            r"\[checks\.health\](?P<body>(?:\n(?:[ \t]+[^\n]*|\s*))*)", text
        )
        if block is None:
            continue
        body = block.group("body")
        interval = re.search(
            r"^\s*interval\s*=\s*[\"']([^\"']+)[\"']", body, re.MULTILINE)
        timeout = re.search(
            r"^\s*timeout\s*=\s*[\"']([^\"']+)[\"']", body, re.MULTILINE)
        port = re.search(r"^\s*port\s*=\s*(\d+)", body, re.MULTILINE)
        assert interval is not None, f"{config.name}: no interval"
        assert timeout is not None, f"{config.name}: no timeout"
        assert port is not None, f"{config.name}: no port"
        found[config.name] = {
            "interval": parse_duration_seconds(interval.group(1)),
            "timeout": parse_duration_seconds(timeout.group(1)),
            "port": int(port.group(1)),
        }
    return found


CONFIGS = ["fly.live.toml", "fly.demo.toml"]


class TestBothHopsOutliveTheCheck:
    def test_every_deploy_config_is_actually_found(self) -> None:
        """An empty comparison passes every assertion below it.

        A regex that stops matching returns `{}`, and `for c in {}` checks
        nothing while reporting green. Naming the files makes a renamed config
        fail here rather than quietly leave a deploy unguarded.
        """
        assert set(health_checks()) == set(CONFIGS), health_checks()

    @pytest.mark.parametrize("config", CONFIGS)
    def test_check_rides_the_next_hop(self, config: str) -> None:
        """The premise, asserted rather than assumed.

        Were the check pointed at 8000 there would be no Next hop in front of
        it and the `KEEP_ALIVE_TIMEOUT` half of this file would be guarding
        nothing.
        """
        assert health_checks()[config]["port"] == 3000

    def test_next_keep_alive_is_explicit(self) -> None:
        assert next_keep_alive_s() > 5.0, "5s is Node's default -- the bug"

    def test_uvicorn_keep_alive_is_explicit(self) -> None:
        assert uvicorn_keep_alive_s() > 5.0, "5s is uvicorn's default -- the bug"

    @pytest.mark.parametrize("config", CONFIGS)
    def test_next_clears_the_interval_with_slack(self, config: str) -> None:
        check = health_checks()[config]
        required = check["interval"] + check["timeout"] + REQUIRED_SLACK_S
        assert next_keep_alive_s() >= required, (
            f"{config}: Next drops idle connections after "
            f"{next_keep_alive_s()}s, but a check every {check['interval']}s "
            f"with a {check['timeout']}s timeout needs {required}s of "
            "keep-alive to survive a late one"
        )

    @pytest.mark.parametrize("config", CONFIGS)
    def test_uvicorn_clears_the_interval_with_slack(self, config: str) -> None:
        check = health_checks()[config]
        required = check["interval"] + check["timeout"] + REQUIRED_SLACK_S
        assert uvicorn_keep_alive_s() >= required, (
            f"{config}: uvicorn drops idle connections after "
            f"{uvicorn_keep_alive_s()}s against a {check['interval']}s check"
        )

    def test_inner_hop_outlives_outer_hop(self) -> None:
        """uvicorn must hang up after Next does, never before.

        If the backend closed first, Next would keep pooling a socket to a
        process that had already gone -- which is the same bug one hop in, and
        is what the `Failed to proxy ... socket hang up` line in the app log
        was reporting.
        """
        assert uvicorn_keep_alive_s() > next_keep_alive_s(), (
            f"uvicorn {uvicorn_keep_alive_s()}s must exceed Next "
            f"{next_keep_alive_s()}s"
        )

    def test_next_stays_under_nodes_headers_timeout(self) -> None:
        """Raising this past 60s swaps one timer killing the socket for another.

        Next's standalone server sets `keepAliveTimeout` and leaves
        `headersTimeout` at Node's 60s default, so there is a ceiling here as
        well as a floor. Both bounds are load-bearing and this is the one that
        is easy to miss while fixing the other.
        """
        assert next_keep_alive_s() < NODE_HEADERS_TIMEOUT_S, (
            f"{next_keep_alive_s()}s is at or past Node's "
            f"{NODE_HEADERS_TIMEOUT_S}s headersTimeout, which Next does not raise"
        )

    def test_the_two_bounds_leave_room(self) -> None:
        """The floor and the ceiling must not have crossed.

        If a check interval is ever raised far enough, the slack rule demands
        more than the headersTimeout ceiling allows and there is no legal
        value. That is a real design change -- the check would have to move or
        Node's other timer be raised in a custom server -- and it should fail
        here loudly rather than be resolved by quietly picking the bound whose
        test was written last.
        """
        worst = max(c["interval"] + c["timeout"] for c in health_checks().values())
        assert worst + REQUIRED_SLACK_S < NODE_HEADERS_TIMEOUT_S, (
            f"a check needing {worst + REQUIRED_SLACK_S}s of keep-alive cannot "
            f"be satisfied under Node's {NODE_HEADERS_TIMEOUT_S}s headersTimeout"
        )


class TestDurationParsing:
    @pytest.mark.parametrize(
        "text,expected",
        [("15s", 15.0), ("30s", 30.0), ("1m", 60.0), ("1m30s", 90.0),
         ("500ms", 0.5), ("1h", 3600.0)],
    )
    def test_parses_fly_durations(self, text: str, expected: float) -> None:
        assert parse_duration_seconds(text) == expected

    @pytest.mark.parametrize("text", ["", "soon", "15", "15 seconds", "15x"])
    def test_refuses_what_it_cannot_read(self, text: str) -> None:
        """Unreadable resolves to a refusal, never to a number.

        `CLAUDE.md`: a caller refuses rather than substitutes. A parser
        returning 0.0 for an unrecognised unit would make every comparison
        above pass.
        """
        with pytest.raises(ValueError):
            parse_duration_seconds(text)
