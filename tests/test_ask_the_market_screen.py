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
class TestHeChoosesTheSize:
    """Issue #62, answered (A) on 2026-09-18.

    The size was a hardcoded `"5.0000"` in the mount, trimmed server-side to
    90% of the combinations shard. Two independent limits on one quantity,
    swapping over at $5.5556 of balance **with no change in symptom**, because
    no screen printed the dollars either way.
    """

    def test_the_size_is_not_hardcoded_into_the_mount(self):
        assert "5.0000" not in _read(PRICE), (
            "the mount hardcoded the size the one measured RFQ happened to "
            "use; it is typed now"
        )
        assert "targetCostDollars=" not in _read(PRICE)

    def test_the_screen_takes_a_typed_dollar_amount(self):
        source = _read(ASK)
        assert 'type="number"' in source
        assert "rfq-size-" in source, "the input needs a stable id"

    def test_the_last_size_is_remembered_and_may_fail_to_be(self):
        """A remembered convenience that throws must not take the price
        control down with it -- private mode, blocked site data, or a server
        render all make `localStorage` unavailable."""
        source = _read(ASK)
        assert "localStorage" in source
        assert source.count("catch") >= 3, (
            "every localStorage access needs its own catch"
        )

    def test_the_words_say_the_size_is_spent_not_capped(self):
        """A quote is all-or-nothing at the size asked for. Reading the field
        as a maximum is how Joe ends up asking for more than the shard can
        pay, which is the refusal that burned 28 makers' answers."""
        prose = _prose(ASK)
        assert "all-or-nothing" in prose
        assert "not a maximum" in prose


class TestBothSurfacesAreShown:
    """Issue #66. Neither the public book nor the RFQ dominates: measured
    2026-09-17, the book beat the RFQ on two of three held combinations and
    the RFQ was the only price on the third."""

    def test_the_public_book_ask_renders_beside_the_quote(self):
        assert "book_ask_display" in _read(ASK)

    def test_asking_is_offered_on_a_book_that_already_has_an_ask(self):
        """It used to be the empty-book branch only, so a priced book was a
        dead end in the other direction: the desk would sell him the book's
        price without showing him the one it could have asked for."""
        # The mount, not the mentions: the module docstring names the
        # component too, and a test that counts prose fails on an edit to a
        # comment.
        source = _read(PRICE)
        assert source.count("<AskTheMarket marketTicker=") == 2, (
            "the ask belongs on the priced branch as well as the empty one"
        )

    def test_neither_surface_is_called_the_better_one(self):
        """Showing two prices is transparency; ordering them is a claim, and
        `beta = -0.141` is why this desk does not make it."""
        prose = _prose(ASK)
        for forbidden in ("better price", "cheaper than", "beats the book"):
            assert forbidden not in prose.lower()


class TestAQuoteShowsItsAge:
    """Issue #67. A maker stands behind a combination quote for about three
    seconds, against thirty elsewhere."""

    def test_the_age_is_rendered_and_ticks(self):
        source = _read(ASK)
        assert "asked_ms" in source
        assert "setInterval" in source, (
            "an age rendered once is a stamp that stops being true while the "
            "reader looks at it"
        )

    def test_an_old_quote_is_relabelled_and_never_blocked(self):
        """Disabling the button on age would be a new ceiling on a hand bet,
        and ADR 0112 removed all five of those on Joe's word."""
        source = _read(ASK)
        assert "QUOTE_GETTING_ON_MS" in source
        assert "disabled={state.kind === \"sending\"}" in source, (
            "the only thing that may disable the button is a send in flight"
        )

    def test_the_screen_claims_no_expiry_it_has_not_measured(self):
        """The first version warned "probably expired" past three seconds --
        which is the maker's post-acceptance CONFIRMATION window, not a
        quote's shelf life, and which would have fired on every first paint
        because `asked_ms` predates a mandatory four-second poll. A warning
        that is always on is a warning that gets skipped."""
        prose = _prose(ASK)
        for forbidden in ("probably expired", "has expired", "no longer valid"):
            assert forbidden not in prose.lower()
        assert "not something this desk has measured" in prose

    def test_the_threshold_is_above_the_time_the_ask_itself_takes(self):
        """`asked_ms` is stamped at route entry, before a four-second poll
        loop, so any threshold under that fires before the reader sees the
        page at all."""
        source = _read(ASK)
        match = re.search(r"QUOTE_GETTING_ON_MS = ([\d_]+)", source)
        assert match, "the threshold must be a named constant"
        assert int(match.group(1).replace("_", "")) > 10_000


class TestTheButtonSaysWhatLeavesTheAccount:
    """Issue #68, and #39's settled precedent on the singles ticket."""

    def test_the_take_button_prints_the_all_in_dollars(self):
        assert "all_in_display" in _read(ASK)
        assert "all in" in _prose(ASK)

    def test_the_fee_is_named_as_charged_on_top(self):
        prose = _prose(ASK)
        assert "charged on top" in prose

    def test_a_quote_with_no_size_admits_it_cannot_say(self):
        """Printing the contracts alone would be a smaller, friendlier,
        wrong number."""
        source = _read(ASK)
        assert 'quote.all_in_display === null\n      ? "Take it"' in source
        prose = _prose(ASK)
        assert "cannot tell you the total" in prose


class TestTheJargonTeachesItself:
    """Issue #70. Joe's standing instruction: every betting term the site uses
    must teach itself at first use."""

    def test_the_new_terms_are_in_the_glossary(self):
        glossary = _read(FRONTEND / "lib" / "glossary.ts")
        for key in ("rfq:", "maker:", "maker_quote:", "shard:"):
            assert key in glossary, f"{key} has no definition"

    def test_they_are_wrapped_where_the_screen_uses_them(self):
        source = _read(ASK)
        for key in ("rfq", "maker", "maker_quote", "shard"):
            assert f'<Term k="{key}">' in source, f"{key} is used unwrapped"
