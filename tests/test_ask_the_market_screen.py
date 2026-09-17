"""The empty-book screen offers the ask instead of a dead end.

Source-reading tests, in the style of `test_buy_controls.py`: these pin what
the screen *says* and which control it renders, which is where this repo's
named failure keeps recurring -- a screen promising or refusing an action the
server does not match.

What these do not establish
---------------------------
- Nothing about what the component renders at runtime; there is no React test
  runner in this repo. They pin the source.
- Nothing about whether a quote is worth taking. That is exactly what they
  forbid the screen from claiming.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).parent.parent / "frontend" / "src"
ASK = FRONTEND / "components" / "AskTheMarket.tsx"
PRICE = FRONTEND / "components" / "PriceOnKalshi.tsx"
PROXY = FRONTEND / "app" / "parlay-rfq" / "route.ts"
MIDDLEWARE = FRONTEND / "middleware.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _prose(path: Path) -> str:
    """The copy a READER sees: comments stripped, whitespace collapsed.

    Both halves are load-bearing and both were learned by this file failing.

    **Comments must go.** The first version scanned raw source for words a
    screen may not say, and tripped on this component's own docstring
    explaining that it must never call a quote cheap or an edge. A guard that
    fires on the comment forbidding the thing is a guard that teaches the next
    author to delete the explanation.

    **Whitespace must collapse.** JSX wraps prose across lines at arbitrary
    points, so `"commits you to nothing"` is `"commits you to\\n nothing"` in
    the file. A raw substring check silently passes for the wrong reason the
    moment a line re-wraps -- and silently fails when the copy is correct,
    which is worse.
    """
    source = _read(path)
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)
    source = re.sub(r"^\s*//.*$", " ", source, flags=re.MULTILINE)
    # JSX entities the reader sees as punctuation, not as markup.
    for entity, plain in (("&mdash;", "--"), ("&rsquo;", "'"), ("&hellip;", "...")):
        source = source.replace(entity, plain)
    return re.sub(r"\s+", " ", source)


class TestTheDeadEndIsGone:
    def test_an_empty_book_renders_the_ask_control(self):
        """`book_empty` used to render words and stop.

        It sent Joe to the Kalshi app on markets makers were pricing all day.
        """
        source = _read(PRICE)
        assert 'value.status === "book_empty"' in source
        assert "<AskTheMarket" in source
        assert "AskTheMarket" in source.split("export default")[0], (
            "the component must be imported, not merely mentioned"
        )

    def test_the_screen_no_longer_sends_him_to_the_kalshi_app_to_price_it(self):
        """The one piece of advice the fix makes obsolete.

        Copy naming a condition to wait for is falsified by fixing the
        condition, so this must not survive the change that removed the need
        for it.
        """
        for path in (PRICE, ASK):
            source = _read(path)
            assert "Build it in the Kalshi app" not in source, path.name

    def test_the_ask_says_it_commits_to_nothing_before_it_is_tapped(self):
        """A money-adjacent-looking button that is free must say so first.

        Creating an RFQ obligates nothing -- only accepting a quote binds --
        and a reader who does not know that will not tap it.
        """
        prose = _prose(ASK)
        assert "commits you to nothing" in prose
        assert "Ask the market for a price" in prose


class TestTheScreenMakesNoClaimItCannotKeep:
    @pytest.mark.parametrize(
        "forbidden",
        ["an edge", "cheap", "good price", "value bet", "free money", "guaranteed"],
    )
    def test_a_quote_is_never_sold_as_an_edge(self, forbidden: str):
        """`beta = -0.141`.

        The gap between a quote and the card's fair value is the
        consensus-vs-Kalshi gap under another name, and ordering by it puts
        the least trustworthy rows first (ADR 0071 s2.5). The screen shows
        both numbers and draws no conclusion.
        """
        assert forbidden not in _prose(ASK).lower()

    def test_the_take_button_does_not_appear_while_the_path_is_unarmed(self):
        """A control labelled "Take it" that silently does nothing is this
        repo's named failure, run a fourth time.

        So the armed state travels WITH the price (`accepts_are_armed`) and
        the component refuses rather than rendering a dead button. Pinning
        the guard, not the wording: what must not happen is the button
        existing unconditionally.
        """
        prose = _prose(ASK)
        assert "if (!armed)" in prose, (
            "the take control is not gated on the armed flag"
        )
        assert "built but not switched on" in prose

    def test_the_take_path_never_offers_a_retry(self):
        """Every other refusal on this screen offers "Ask again".

        This one must not: an RFQ acceptance carries no idempotency key, so a
        second tap after a lost response is a second real trade. A retry
        button is an invitation to make one.
        """
        source = _read(ASK)
        take = source[source.index("function TakeIt("):]
        assert "RetryButton" not in take, (
            "the accept path offers a retry; a second accept is a second trade"
        )

    def test_it_does_not_promise_the_quote_is_still_standing(self):
        """The retry stays reachable after a good answer.

        A quote is live state with a maker behind it, and the request is
        withdrawn the moment anything else happens to it.
        """
        assert "Ask again" in _prose(ASK)


class TestTheDoorIsRegistered:
    def test_the_proxy_forwards_to_the_backend_route(self):
        source = _read(PROXY)
        assert '"/api/parlays/rfq"' in source
        assert "backendToken" in source and "demoRefusal" in source

    def test_middleware_gives_an_unauthenticated_post_a_json_401(self):
        """Without the entry a `fetch` gets an HTML login redirect and reads
        it as success -- the failure mode every other JSON route here was
        registered to avoid."""
        assert '"/parlay-rfq"' in _read(MIDDLEWARE)

    def test_the_proxy_says_no_money_moved_when_the_backend_is_silent(self):
        assert "no money moved" in _read(PROXY)
