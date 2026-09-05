"""Measure the desk's cached prompt prefixes against the model's minimum.

A `cache_control` breakpoint on a prefix shorter than the model's minimum
cacheable length **does nothing, silently**: no error, no warning,
`cache_creation_input_tokens: 0`. There is no way to notice from the code, and
this project already shipped one -- the breakpoint sat on `HOUSE_CONTEXT` (401
tokens) against a 512-token minimum for the whole life of the module.

So the number has to be measured, and re-measured whenever either half changes:

- the prompts, obviously
- **the model**, which is the trap. The minimum is model-specific and is *not*
  monotonic across releases: 512 tokens on Claude Opus 5, 1024 on Sonnet 5 and
  on Opus 4.8, 4096 on Opus 4.6. Moving `AGENT_MODEL` to an older model can
  silently switch the cache off.

What it measures, and why these four
------------------------------------
The prefix the breakpoint covers is `HOUSE_CONTEXT` plus the seat's own system
block (`base.structured_call` puts the breakpoint on the last system block).
Four seats spend money on live, all in `backend/agents/scout_desk.py`: the two
staff scouts (one template, rendered per team and venue), the master scout, and
the pro-bettor seat (`pro_bettor.SYSTEM`, ADR 0069). Those are what is counted.

**Until 2026-09-05 this script counted `skeptic`, `scout` and `historian`.**
Two of those modules are now deleted, and the third's `SYSTEM` is a schema
module's prompt that no live seat sends (`scout_desk` imports `ScoutReport`
and `WEB_SEARCH_TOOL` from it, not the prompt). So every figure it printed --
and the 2026-08-08 table above `HOUSE_CONTEXT` in `agents/base.py` -- was for
a prompt nothing bills. The desk's own seats had never been counted.

The staff template is rendered with a representative pair and the home venue
clause, the longer of the two, so the figure is the upper bound of the pair.
A team name's few tokens either way do not move a 1024-token threshold; the
away rendering is printed too so the spread is visible rather than assumed.

The model is `AGENT_MODEL` if set, else `DEFAULT_MODEL`. **Live pins
`claude-sonnet-5`** (`fly.live.toml`, ADR 0071 section 2.7), whose minimum is
1024 against Opus 5's 512 -- run with `AGENT_MODEL=claude-sonnet-5` to answer
the question that matters on the deployed machine.

What this does not establish
----------------------------
It counts tokens; it does not observe a cache hit. Confirming the breakpoint
actually produces one needs two real calls and a look at
`usage.cache_read_input_tokens` on the second -- which costs tokens, so it is
not done here. And it counts on whichever model the SDK's `count_tokens`
tokenises for; a minimum transcribed from documentation is a claim about the
model, not a measurement of it.

Run:
    .venv\\Scripts\\python.exe scripts/measure_agent_cache_prefix.py

Needs `ANTHROPIC_API_KEY`. `count_tokens` is free.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from backend.agents import pro_bettor, scout_desk  # noqa: E402
from backend.agents.base import DEFAULT_MODEL, HOUSE_CONTEXT  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402

# The published minimum cacheable prefix, per model. Transcribed from
# Anthropic's prompt-caching documentation, not measured -- a prefix below it
# produces no cache entry and no error, so there is nothing to observe.
MINIMUM_CACHEABLE_TOKENS = {
    "claude-opus-5": 512,
    "claude-fable-5": 512,
    "claude-opus-4-8": 1024,
    "claude-sonnet-5": 1024,
    "claude-sonnet-4-6": 1024,
    "claude-opus-4-7": 2048,
    "claude-opus-4-6": 4096,
    "claude-haiku-4-5": 4096,
}

# A representative rendering of the staff template. The names are the
# fixture pair the wiring tests use; what matters is that the two `.format`
# fields are filled with something of realistic length.
_REPRESENTATIVE_PAIR = ("Pittsburgh Pirates", "New York Mets")


def live_seat_prompts() -> list[tuple[str, str]]:
    """`(seat, system_text)` for every seat that bills on the deployed desk.

    Derived from the modules the desk actually sends rather than listed by
    hand: `scout_desk._staff_call` renders `STAFF_SYSTEM_TEMPLATE` with the
    team, the opponent and a venue clause; the master and the pro's seat send
    their constants unrendered.
    """
    home, away = _REPRESENTATIVE_PAIR
    staff_home = scout_desk.STAFF_SYSTEM_TEMPLATE.format(
        team=home, opponent=away, venue_clause=scout_desk.HOME_VENUE_CLAUSE,
    )
    staff_away = scout_desk.STAFF_SYSTEM_TEMPLATE.format(
        team=away, opponent=home, venue_clause=scout_desk.AWAY_VENUE_CLAUSE,
    )
    return [
        ("staff (home)", staff_home),
        ("staff (away)", staff_away),
        ("master", scout_desk.MASTER_SYSTEM),
        ("pro_bettor", pro_bettor.SYSTEM),
    ]


def main() -> int:
    configure_logging()
    load_dotenv()

    import anthropic

    client = anthropic.Anthropic()
    model = os.environ.get("AGENT_MODEL") or DEFAULT_MODEL

    def count(system_text: str) -> int:
        return client.messages.count_tokens(
            model=model,
            system=[{"type": "text", "text": system_text}],
            messages=[{"role": "user", "content": "x"}],
        ).input_tokens

    # A one-character system block, subtracted off, so the figures are the
    # prompt text alone rather than the envelope around it.
    envelope = count(".")
    house = count(HOUSE_CONTEXT) - envelope

    minimum = MINIMUM_CACHEABLE_TOKENS.get(model)
    print(f"model                          {model}"
          f"{'' if os.environ.get('AGENT_MODEL') else '   (DEFAULT_MODEL; live pins claude-sonnet-5)'}")
    if minimum is None:
        print("minimum cacheable prefix       UNKNOWN for this model -- add it "
              "to MINIMUM_CACHEABLE_TOKENS before trusting anything below")
    else:
        print(f"minimum cacheable prefix       {minimum} tokens")
    print()
    print(f"HOUSE_CONTEXT alone            {house:5d}   "
          f"{'CACHES' if minimum and house >= minimum else 'DOES NOT CACHE'}")
    print()
    print("cached prefix per live seat (breakpoint is on the last system block):")

    failures = 0
    for name, system in live_seat_prompts():
        total = count(HOUSE_CONTEXT + system) - envelope
        ok = minimum is not None and total >= minimum
        headroom = f"{total - minimum:+d}" if minimum is not None else "?"
        print(f"  {name:14s} {total:5d} tokens   headroom {headroom:>6s}   "
              f"{'ok' if ok else 'DOES NOT CACHE'}")
        if not ok:
            failures += 1

    print()
    if failures:
        print(f"{failures} seat(s) have a breakpoint that will not produce a "
              f"cache entry. `agents/base.py` records why that is accepted on "
              f"Sonnet rather than padded away; if the model or the prompts "
              f"change, re-read that note before deciding it still is.")
        return 1
    print("every live seat's cached prefix clears the minimum.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
