"""Measure the agent fleet's cached prompt prefix against the model's minimum.

A `cache_control` breakpoint on a prefix shorter than the model's minimum
cacheable length **does nothing, silently**: no error, no warning,
`cache_creation_input_tokens: 0`. There is no way to notice from the code, and
this project already shipped one — the breakpoint sat on `HOUSE_CONTEXT` (401
tokens) against a 512-token minimum for the whole life of the module.

So the number has to be measured, and re-measured whenever either half changes:

- the prompts, obviously
- **the model**, which is the trap. The minimum is model-specific and is *not*
  monotonic across releases: 512 tokens on Claude Opus 5, 1024 on Opus 4.8,
  4096 on Opus 4.6. Moving `AGENT_MODEL` to an older model can silently switch
  the cache off.

What this does not establish
----------------------------
It counts tokens; it does not observe a cache hit. Confirming the breakpoint
actually produces one needs two real calls and a look at
`usage.cache_read_input_tokens` on the second — which costs tokens, so it is
not done here.

Run:
    .venv\\Scripts\\python.exe scripts/measure_agent_cache_prefix.py

Needs `ANTHROPIC_API_KEY`. `count_tokens` is free.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from backend.agents import historian, scout, skeptic  # noqa: E402
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


def main() -> int:
    configure_logging()
    load_dotenv()

    import anthropic

    client = anthropic.Anthropic()
    model = DEFAULT_MODEL

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
    print(f"model                          {model}")
    if minimum is None:
        print("minimum cacheable prefix       UNKNOWN for this model -- add it "
              "to MINIMUM_CACHEABLE_TOKENS before trusting anything below")
    else:
        print(f"minimum cacheable prefix       {minimum} tokens")
    print()
    print(f"HOUSE_CONTEXT alone            {house:5d}   "
          f"{'CACHES' if minimum and house >= minimum else 'DOES NOT CACHE'}")
    print()
    print("cached prefix per agent (breakpoint is on the last system block):")

    failures = 0
    for name, module in (("skeptic", skeptic), ("scout", scout),
                         ("historian", historian)):
        system = getattr(module, "SYSTEM", None)
        if not system:
            print(f"  {name:10s} no SYSTEM constant -- skipped")
            continue
        total = count(HOUSE_CONTEXT + system) - envelope
        ok = minimum is not None and total >= minimum
        headroom = f"{total - minimum:+d}" if minimum is not None else "?"
        print(f"  {name:10s} {total:5d} tokens   headroom {headroom:>6s}   "
              f"{'ok' if ok else 'DOES NOT CACHE'}")
        if not ok:
            failures += 1

    print()
    if failures:
        print(f"{failures} agent(s) have a breakpoint that will not produce a "
              f"cache entry. Lengthen the prompt, or accept the cost and "
              f"delete the breakpoint rather than leaving one that reads as "
              f"an optimisation and is not.")
        return 1
    print("every agent's cached prefix clears the minimum.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
