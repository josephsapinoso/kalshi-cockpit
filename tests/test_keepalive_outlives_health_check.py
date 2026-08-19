"""uvicorn's keep-alive must outlive the health check interval, on every deploy.

**What this establishes.** That `docker/entrypoint.sh` passes an explicit
`--timeout-keep-alive` to uvicorn, and that its value is larger than the
`interval` of every `[checks.health]` block in every `fly.*.toml` in the repo.

**What it does not.** It does not prove the proxy hop is healthy -- it reads two
config files and never opens a socket. It cannot see Next's own outbound pool
timeout, which is the other half of the race and is not configured here. And it
says nothing about whether the backend answers, which is the failure everyone
assumed this was and which measurement ruled out.

**Why it exists.** uvicorn defaults `--timeout-keep-alive` to 5s. Fly checks
port 3000 -- Next -- every 15s on live and 30s on demo, and Next proxies to
uvicorn over a connection it pools between those checks. Whenever the upstream
closes first, the pooled socket is dead when it is next used and the check fails
with ECONNRESET while the backend is entirely healthy. Measured on live
2026-08-19: 5 failures in 10 at a 15s gap, 0 in 10 at a 3s gap, alternating
exactly. The direct backend answered 50 of 50 probes in the same window.

The two numbers live in different files and neither one mentions the other, so
raising a check interval past 75s would silently reintroduce the bug. That is
what this test is for: it fails when the *relationship* breaks, not when either
number changes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = REPO_ROOT / "docker" / "entrypoint.sh"

# `1h`/`1m30s` are legal in Fly's duration syntax, so the seconds are parsed
# rather than assumed. A config using a unit this does not understand fails
# loudly below instead of being skipped -- an interval that cannot be read is
# not an interval that can be trusted to be smaller.
_DURATION = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m|h)")
_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def parse_duration_seconds(text: str) -> float:
    matches = _DURATION.findall(text.strip())
    if not matches:
        raise ValueError(f"unparseable Fly duration: {text!r}")
    consumed = "".join(f"{value}{unit}" for value, unit in matches)
    if consumed != text.strip():
        raise ValueError(f"unparseable Fly duration: {text!r}")
    return sum(float(value) * _UNIT_SECONDS[unit] for value, unit in matches)


def keep_alive_seconds() -> float:
    """The `--timeout-keep-alive` the entrypoint hands uvicorn."""
    source = ENTRYPOINT.read_text(encoding="utf-8")
    # Only the uvicorn invocation counts. Matching anywhere in the file would
    # let a commented-out example satisfy this test, and the comment above the
    # invocation quotes the flag by name.
    invocation = re.search(
        r"python -m uvicorn\b(?P<args>(?:[^\n]|\\\n)*?)&", source
    )
    assert invocation is not None, "no `python -m uvicorn` invocation found"
    flag = re.search(
        r"--timeout-keep-alive[= ]+(\d+)", invocation.group("args")
    )
    assert flag is not None, (
        "uvicorn is started without --timeout-keep-alive, so it defaults to 5s "
        "-- shorter than every health check interval in this repo"
    )
    return float(flag.group(1))


def health_check_intervals() -> dict[str, float]:
    """Every `[checks.health] interval` in every Fly config, by filename."""
    found: dict[str, float] = {}
    for config in sorted(REPO_ROOT.glob("fly*.toml")):
        text = config.read_text(encoding="utf-8")
        block = re.search(
            r"\[checks\.health\](?P<body>(?:\n(?:[ \t]+[^\n]*|\s*))*)", text
        )
        if block is None:
            continue
        interval = re.search(
            r"^\s*interval\s*=\s*[\"']([^\"']+)[\"']",
            block.group("body"),
            re.MULTILINE,
        )
        assert interval is not None, (
            f"{config.name} declares [checks.health] with no interval"
        )
        found[config.name] = parse_duration_seconds(interval.group(1))
    return found


class TestKeepAliveOutlivesHealthCheck:
    def test_both_deploy_configs_are_actually_found(self) -> None:
        """The comparison is worthless if it silently compares nothing.

        A regex that stops matching returns an empty dict, and every
        `assert x > y` over an empty dict passes. Naming the files here means a
        renamed or restructured config fails this test instead of quietly
        removing a deploy from the check.
        """
        intervals = health_check_intervals()
        assert set(intervals) == {"fly.demo.toml", "fly.live.toml"}, intervals

    def test_keep_alive_is_explicit(self) -> None:
        assert keep_alive_seconds() > 5.0, (
            "5s is uvicorn's default; setting it to the default is the bug"
        )

    @pytest.mark.parametrize("config", ["fly.live.toml", "fly.demo.toml"])
    def test_keep_alive_exceeds_interval(self, config: str) -> None:
        interval = health_check_intervals()[config]
        keep_alive = keep_alive_seconds()
        assert keep_alive > interval, (
            f"{config} checks every {interval}s but uvicorn drops idle "
            f"connections after {keep_alive}s, so the connection Next pools "
            f"between checks is dead when it is reused"
        )

    @pytest.mark.parametrize("config", ["fly.live.toml", "fly.demo.toml"])
    def test_margin_is_not_marginal(self, config: str) -> None:
        """Strictly greater is not enough when both ends are timers.

        The failure this guards is a race between two independent clocks under
        IO stall -- live measured 90% full IO pressure while this was
        happening. A keep-alive one second past the interval satisfies the
        test above and still loses the race whenever a check is late. 2x is
        arbitrary; being explicit that a bare inequality was considered and
        rejected is not.
        """
        interval = health_check_intervals()[config]
        assert keep_alive_seconds() >= 2 * interval, (
            f"{config}: keep-alive should clear the {interval}s interval with "
            "margin, not tie with it"
        )

    def test_check_targets_the_proxy_not_the_backend(self) -> None:
        """The premise of this whole test, asserted rather than assumed.

        If Fly ever checked port 8000 directly there would be no pooled
        connection between it and uvicorn and none of the above would matter.
        It checks 3000 -- Next -- which is why an entirely healthy backend can
        fail the check.
        """
        for name in ("fly.live.toml", "fly.demo.toml"):
            text = (REPO_ROOT / name).read_text(encoding="utf-8")
            block = re.search(
                r"\[checks\.health\](?P<body>(?:\n(?:[ \t]+[^\n]*|\s*))*)", text
            )
            assert block is not None, name
            port = re.search(
                r"^\s*port\s*=\s*(\d+)", block.group("body"), re.MULTILINE
            )
            assert port is not None and port.group(1) == "3000", (
                f"{name}: health check no longer targets the Next proxy"
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

        `CLAUDE.md`'s conventions: a caller refuses rather than substitutes. A
        parser that returned 0.0 for an unrecognised unit would make every
        comparison above pass.
        """
        with pytest.raises(ValueError):
            parse_duration_seconds(text)
