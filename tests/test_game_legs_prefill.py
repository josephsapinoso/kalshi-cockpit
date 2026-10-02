"""'Change a leg' opens /game with the card's legs pre-ticked (#295).

A game-script card links to `/game/<event>?legs=ticker:side,...`; the page
hands the raw value to `<GameLegs>`, which ticks those legs once, when the
listing first arrives.

Source assertions (this repo has no JS test runner), the pattern of
`tests/test_game_page_copy.py`.

What they establish: the link is built from the card's own legs and sides;
the page passes the query value through; the component ticks only legs that
the live listing offers, on a side that leg allows, and keeps the one-rung
rule; and the tick happens in the listing's arrival handler, not on every
render or effect run (so it cannot tick back a leg the reader removed).

What they do NOT establish: that the page renders, or how a stale link looks.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "frontend" / "src"
CARD = SRC / "components" / "GameScriptCard.tsx"
LEGS = SRC / "components" / "GameLegs.tsx"
PAGE = SRC / "app" / "game" / "[event]" / "page.tsx"


def _code(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


def test_change_a_leg_pre_ticks_the_cards_legs():
    card, legs, page = _code(CARD), _code(LEGS), _code(PAGE)

    # The card offers the link, built from its own legs and sides.
    assert "Change a leg" in card
    assert "?legs=" in card
    assert "`${leg.market_ticker}:${leg.side}`" in card

    # The page reads the query value and hands it on, unparsed.
    assert "searchParams" in page
    assert "initialLegs={initialLegs}" in page

    # The component ticks from it, once, when the listing arrives.
    assert "preTick(initialLegs, payload)" in legs
    assert "setTicked(wanted)" in legs
    fetch = legs[legs.index("fetchGameLegs(eventTicker)"):]
    fetch = fetch[: fetch.index("return () =>")]
    assert "preTick(" in fetch


def test_a_leg_the_listing_does_not_offer_is_ignored_never_invented():
    legs = _code(LEGS)
    body = legs[legs.index("function preTick"):]
    body = body[: body.index("\n}\n")]
    # Only tickers present in the listing are ticked.
    assert "const leg = byMarket.get(ticker);" in body  # no fallback leg
    assert "if (!leg" in body
    # A side the leg does not allow is not ticked.
    assert "leg.allowed_sides.includes(side)" in body
    # Kalshi's one-rung events keep one leg, as a hand tick would.
    assert "leg.one_per_event" in body and "takenEvents" in body
    # The only thing written to the ticket is a listed leg's ticker.
    assert "ticked[ticker] = side" in body


def test_the_query_value_is_parsed_defensively():
    legs = _code(LEGS)
    body = legs[legs.index("export function parseLegsParam"):]
    body = body[: body.index("\n}\n")]
    assert 'if (!raw) return []' in body
    assert 's === "yes" || s === "no"' in body
