"""Build the Anthropic Messages wire fixtures the agent tests load.

**Read this before trusting the fixtures: they are SDK-DERIVED, not captured.**
CLAUDE.md's convention is that wire-format tests load *captured* payloads, and
these are not captures -- no Anthropic call was made to produce them and no
API key is needed to run this script. What they are is payloads validated
against the installed SDK's own pydantic models, which is a strictly weaker
claim and a strictly stronger test than what they replace.

**What they establish.** `Message.model_validate` rejects a payload the SDK
would not accept, so a field the wire requires cannot be quietly absent -- the
first draft of this file omitted `usage.server_tool_use.web_fetch_requests`
and was refused, which is precisely the class of error a hand-built stub
cannot catch. `parse_response` then runs the SDK's real text-block parsing
against `ScoutReport`, so the JSON must satisfy our own output model, and the
resulting object is a real `ParsedMessage` whose `parsed_output` is the real
property.

**What they do NOT establish**, and this is why ADR 0106 §5.2 stays open:
that Anthropic's wire actually looks like this. The SDK's models are our
belief about the wire, and a fixture derived from them cannot falsify that
belief -- if the SDK is wrong or drifts from the service, these payloads are
wrong in exactly the same direction and every test stays green. Only a
captured response settles that, and capturing one costs a real call on the
billed path (`scout.py` is live). This script exists so the *rest* of the gap
closes for nothing while that capture waits.

**Why it matters that the old stubs were worse.** `tests/test_agents.py:48`
and `tests/test_scout_desk.py:56` both build a fake response object and assign
`self.parsed_output = parsed` directly. `ParsedMessage.parsed_output` is a
**property** that walks `content` for the first text block carrying a parsed
value; assigning over it means the property never ran, the content blocks were
never populated, and the JSON was never validated against `ScoutReport`. The
tests asserted that `base.py` reads an attribute someone had just set.

Usage:

    .venv\\Scripts\\python.exe scripts/build_agent_wire_fixture.py

Writes `tests/fixtures/anthropic_scout_report.json` and
`anthropic_scout_refusal.json`, and re-running is idempotent.
"""

from __future__ import annotations

import json
import sys

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

FIXTURES = REPO / "tests" / "fixtures"

#: What the Scout is asked to produce, as `ScoutReport` requires it. Content is
#: invented and deliberately unremarkable -- one fresh finding and one stale
#: one, so `has_fresh_news` has something to separate, and a null `source_url`
#: so the optional field is exercised rather than assumed.
REPORT = {
    "game": "Milwaukee Brewers at New York Mets",
    "findings": [
        {
            "category": "injury",
            "fact": (
                "The Mets' scheduled right-hander was scratched with right "
                "elbow soreness; the club named a bullpen game instead."
            ),
            "source": "Associated Press",
            "source_url": "https://example.invalid/ap/mets-scratch",
            "reported_when": "2026-08-27, about three hours before first pitch",
            "likely_already_priced": False,
            "affects_side": "New York Mets",
        },
        {
            "category": "weather",
            "fact": "Rain is forecast from the sixth inning; the roof is open.",
            "source": "National Weather Service",
            "source_url": None,
            "reported_when": "2026-08-27, morning",
            "likely_already_priced": True,
            "affects_side": None,
        },
    ],
    "summary": (
        "A late scratch of the Mets starter is the only fresh item. The "
        "weather note has been public since morning."
    ),
    "searched_for": [
        "starting pitchers",
        "injury report",
        "lineup",
        "weather",
    ],
}

#: The usage block, with both server-tool counters present. `web_fetch_requests`
#: is required by the SDK's model and was missing from the first draft -- kept
#: named here so a future edit does not drop it again.
USAGE = {
    "input_tokens": 4211,
    "output_tokens": 623,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 3840,
    "server_tool_use": {"web_search_requests": 4, "web_fetch_requests": 0},
    "service_tier": "standard",
}


def envelope(*, content: list, stop_reason: str, extra: dict | None = None) -> dict:
    payload = {
        "id": "msg_01ExampleScoutCall00000000",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": USAGE,
    }
    payload.update(extra or {})
    return payload


def main() -> int:
    from anthropic.types import Message

    ok = envelope(
        content=[
            {
                "type": "text",
                "text": json.dumps(REPORT, indent=2),
                "citations": None,
            }
        ],
        stop_reason="end_turn",
    )
    # A safety refusal: HTTP 200, `stop_reason` "refusal", and content that
    # will not match the schema. `base.py` checks this BEFORE touching
    # `parsed_output`, and that ordering is the thing the fixture exists to
    # let a test exercise for real.
    refusal = envelope(
        content=[{"type": "text", "text": "", "citations": None}],
        stop_reason="refusal",
    )

    for name, payload in (
        ("anthropic_scout_report.json", ok),
        ("anthropic_scout_refusal.json", refusal),
    ):
        # Validate before writing: a fixture the SDK would reject is worse
        # than no fixture, because it makes a green test a false one.
        Message.model_validate(payload)
        path = FIXTURES / name
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
