"""Capture ONE real Anthropic response, for the fixture ADR 0106 §5.2 wants.

**This spends money.** One `messages.parse` call on the scout's own shape --
`ScoutReport` output, the web-search tool, `max_tokens=6000`, `effort="high"`
-- which `backend/agents/base.py` costs at up to ~$0.08 plus per-search
charges. Authorised by Joe on 2026-09-05, once, to close the gap that
`scripts/build_agent_wire_fixture.py` deliberately could not: that script's
payloads are validated against the SDK's models and therefore cannot falsify
them, and only a real response settles what the wire looks like.

**It makes exactly one call and has no loop.** There is no retry
(`build_client` sets `max_retries=0` and this uses it), no batch, and no
argument that can raise the count. Re-running it spends again -- deliberately
un-ergonomic.

**The key is never read, echoed, logged or written.** It is loaded through
`AgentConfig.from_env`, the same path production uses, and only the
`AsyncAnthropic` client ever holds it. The capture writes the RESPONSE body
and nothing about the request's credentials.

**Why an httpx hook rather than serialising the returned object.** A safety
refusal makes `messages.parse` raise before it returns anything
(`tests/test_agent_wire_format.py` pins that), so serialising the return value
would lose both the payload and the money in exactly the case the fixture is
most wanted for. The hook sees the literal body whatever the SDK then does
with it.

**It writes to `data/`, which is gitignored, and stops.** Promoting a capture
into `tests/fixtures/` is a separate, deliberate step after a human has read
it: a real response carries live web-search results and a real game, and
CLAUDE.md's rule that this repo is public means nothing lands in the tree
unread.

Usage:

    .venv\\Scripts\\python.exe scripts/capture_agent_wire_fixture.py "Team A at Team B"
"""

from __future__ import annotations

import asyncio
import json
import sys

from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "data" / "agent_captures"


async def main(game: str) -> int:
    import anthropic
    import httpx

    from backend.agents.base import AgentConfig, HOUSE_CONTEXT
    from backend.agents.scout import SYSTEM, WEB_SEARCH_TOOL, ScoutReport
    from backend.config import ConfigError

    try:
        config = AgentConfig.from_env()
    except ConfigError as exc:
        # The message names the missing variable, never its value.
        print(f"STOP -- {exc}", file=sys.stderr)
        return 2

    captured: list[dict] = []

    async def on_response(response: httpx.Response) -> None:
        # `aread()` because the SDK streams the body; without it `.text` is
        # empty here and the SDK still gets its content.
        await response.aread()
        captured.append(
            {
                "status": response.status_code,
                "url": str(response.url),
                "body_text": response.text,
            }
        )

    http = httpx.AsyncClient(event_hooks={"response": [on_response]})
    client = anthropic.AsyncAnthropic(
        api_key=config.api_key, max_retries=0, http_client=http
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    error: str | None = None
    try:
        await client.messages.parse(
            model=config.model,
            max_tokens=6000,
            system=f"{HOUSE_CONTEXT}\n\n{SYSTEM}",
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Game: {game}\n\nGather what is publicly reported "
                        "about this game that a bettor would want to know."
                    ),
                }
            ],
            output_format=ScoutReport,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            tools=[WEB_SEARCH_TOOL],
        )
    except Exception as exc:                                 # noqa: BLE001
        # A refusal lands here, and its body is already captured. Recorded
        # rather than raised: the response is the artifact, not the return.
        error = f"{type(exc).__module__}.{type(exc).__name__}"
    finally:
        await http.aclose()

    if not captured:
        print("STOP -- no HTTP response was captured; nothing written.",
              file=sys.stderr)
        return 3

    for n, item in enumerate(captured, start=1):
        path = OUT_DIR / f"anthropic_scout_capture_{stamp}_{n}.json"
        try:
            body = json.loads(item["body_text"])
        except json.JSONDecodeError:
            body = {"_unparseable_body": item["body_text"]}
        path.write_text(
            json.dumps(
                {
                    "captured_utc": stamp,
                    "status": item["status"],
                    "url": item["url"],
                    "parse_raised": error,
                    "body": body,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {path.relative_to(REPO)}  status={item['status']}")

    if error:
        print(f"note: messages.parse raised {error} -- the body is still "
              "captured, and a refusal is a MORE useful fixture than a "
              "success. Read it before promoting anything.")
    print("Nothing has entered tests/fixtures/. Read the capture first.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        raise SystemExit(64)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
