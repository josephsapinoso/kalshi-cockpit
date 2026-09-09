"""The game screen's "is an ask on this page" verdict, executed rather than read.

**Why this file runs `node` instead of asserting on source text.** The defect
ticket #24 records is a *wrong verdict*, not a missing field: the market screen
passed `priceAlreadyVisible` as a constant `true`, so the hand-bet ticket said
"the price is already on this screen, so that number is anchored by it" in the
states where the quote strip prints nothing at all. A substring assertion passes
unchanged on a predicate that has been exactly inverted, which makes it the
wrong instrument for this claim and worth nothing as proof of the fix. Same
reasoning, same machinery, as `tests/test_sweep_tone_predicate.py`.

`frontend/src/lib/quoteVisibility.ts` is therefore plain TypeScript with no
React import and no dependency on `lib/api`, and node v24 strips types
natively, so the real shipped function can be called with real detail shapes.
It has no imports of its own, so unlike the sweep-tone driver this one needs no
resolve hook.

What this establishes: that `quoteVisibility` maps each recorded market state
to the outcome the strip actually renders; that the three clauses
distinguishing them are each load-bearing (verified by mutation, not by
reading); and that the strip reads this one function rather than spelling the
predicate a second time inline.

**`askIsVisible` and the ticket's `priceAlreadyVisible` flag are gone**
(2026-09-09, ADR DRAFT-the-ticket-stops-asking-for-a-probability). They named
which of two masked-ask wordings the hand-bet ticket should use, and the mask
went with the P(YES) field. The pins below are inverted rather than deleted:
what is asserted now is that the ticket is handed no such flag, so a future
session cannot restore a constant `true` and reintroduce ticket #24's defect
without this going red.

What this does **not** establish: that the server computes `price_is_current`
or `quote_age_now_ms` correctly -- that is the backend's own tests, and this
predicate deliberately only reads them; that the copy beside a rendered ask is
accurate (`tests/test_buy_controls.py`); or that the search link points
anywhere useful (below, separately, and by source text -- a link's `href` is a
field, not a verdict, so a substring test is the right tool there).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "frontend" / "src" / "lib"
VISIBILITY_TS = LIB / "quoteVisibility.ts"
MARKET_PAGE = REPO / "frontend" / "src" / "app" / "market" / "[ticker]" / "page.tsx"
SEARCH = REPO / "frontend" / "src" / "components" / "MarketSearch.tsx"

NODE = shutil.which("node")

requires_node = pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: this guard is real "
        "where node exists (CI and both dev machines) and a missing runtime is "
        "an environment fact, not a pending failure."
    ),
)

NOW = 1_788_600_000_000
MINUTE = 60_000


# ---------------------------------------------------------------------------
# The recorded states
# ---------------------------------------------------------------------------
# Shapes taken from `MarketDetail` as `/api/market/{ticker}` serves it. The
# optional fields are optional on the wire too -- a backend one version behind
# omits them -- which is why two fixtures below leave them out entirely rather
# than setting them null.

#: The ordinary case: an open market whose recorded ask the server vouches for.
CURRENT = {
    "market_status": "active",
    "close_ms": NOW + 6 * 60 * MINUTE,
    "quote_age_now_ms": 40_000,
    "price_is_current": True,
}

#: The recorder priced this ticker, but not recently enough to transact on.
#: The strip refuses it in words rather than greying it, so the page shows no
#: number -- and this is one of the two states the old flag lied about.
STALE = {**CURRENT, "price_is_current": False}

#: **The backend-one-version-behind case.** `price_is_current` is absent, not
#: false. An absent judgement is not a judgement of "current": unreadable
#: resolves to the refusal, never to the permissive branch.
NO_JUDGEMENT = {
    "market_status": "active",
    "close_ms": NOW + 6 * 60 * MINUTE,
    "quote_age_now_ms": 40_000,
}

#: Vouched-for but ageless. There is no honest way to render "quote checked N
#: ago" without the N, so the strip refuses on this alone.
NO_AGE = {
    "market_status": "active",
    "close_ms": NOW + 6 * 60 * MINUTE,
    "quote_age_now_ms": None,
    "price_is_current": True,
}

#: Past its close. The strip returns nothing at all, so there is no price on
#: the page however current the last recorded quote was.
CLOSED = {**CURRENT, "close_ms": NOW - MINUTE}

#: Settled and finalized: the same absence, reached by the status field rather
#: than by the clock. Both spellings appear in `kalshi_markets`.
SETTLED = {**CURRENT, "market_status": "settled", "close_ms": NOW + MINUTE}
FINALIZED = {**CURRENT, "market_status": "finalized", "close_ms": NOW + MINUTE}

#: An open market with no status string at all. Must not read as dead: the
#: `?? ""` in the predicate exists so a missing status is "not finalized",
#: not "finalized".
NO_STATUS = {**CURRENT, "market_status": None}


# ---------------------------------------------------------------------------
# Running the real function
# ---------------------------------------------------------------------------

_DRIVER = """
import {{ quoteVisibility }} from "{module}";
const input = JSON.parse(process.argv[2]);
const detail = input.detail;
console.log(JSON.stringify({{
  visibility: quoteVisibility(detail, input.now),
}}));
"""


def verdict(detail, *, now: int = NOW, source: str | None = None, tmp_path=None):
    """Call the shipped predicate and return its verdict.

    `source` substitutes a mutated copy of the module, which is how the
    disabling checks below prove a clause is load-bearing. The module has no
    imports, so a mutated copy stands alone in `tmp_path`.
    """
    if source is None:
        module_dir = VISIBILITY_TS.parent
    else:
        module_dir = tmp_path
        (module_dir / "quoteVisibility.ts").write_text(source, encoding="utf-8")

    driver = module_dir / "_visibility_driver.mjs"
    driver.write_text(_DRIVER.format(module="./quoteVisibility.ts"), encoding="utf-8")
    try:
        out = subprocess.run(
            [
                NODE,
                "--experimental-strip-types",
                str(driver),
                json.dumps({"detail": detail, "now": now}),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(module_dir),
        )
    finally:
        driver.unlink(missing_ok=True)

    assert out.returncode == 0, (
        f"node failed running the predicate:\n{out.stdout}\n{out.stderr}"
    )
    parsed = json.loads(out.stdout.strip())
    return parsed["visibility"]


def _without_comments(ts: str) -> str:
    """TypeScript source with comments removed, so a pin on what the code
    *does* is not satisfied or defeated by prose about what it used to do."""
    ts = re.sub(r"/\*.*?\*/", "", ts, flags=re.S)
    return re.sub(r"//[^\n]*", "", ts)


@requires_node
class TestThePairThatDecidesTheFix:
    """The two states the fix must tell apart. If it cannot, it is not a fix."""

    def test_a_current_ask_is_visible(self):
        assert verdict(CURRENT) == "ask"

    def test_a_refused_stale_ask_is_not_a_visible_price(self):
        """The defect, stated as a test. Before ticket #24 the ticket claimed
        a price was on this screen in exactly this state."""
        assert verdict(STALE) == "stale"

    def test_no_detail_row_is_not_a_visible_price(self):
        """The other half of the defect: the page renders "the recorder never
        priced this ticker" and mounts no strip at all."""
        assert verdict(None) == "absent"


@requires_node
class TestTheStatesThatRenderNothing:
    def test_past_the_close(self):
        assert verdict(CLOSED) == "absent"

    def test_settled(self):
        assert verdict(SETTLED) == "absent"

    def test_finalized(self):
        assert verdict(FINALIZED) == "absent"

    def test_a_missing_status_is_not_a_dead_market(self):
        """`?? ""` means absent reads as "not finalized". A market with no
        status string is open until something says otherwise."""
        assert verdict(NO_STATUS) == "ask"


@requires_node
class TestUnreadableResolvesToRefusal:
    """This repo's standing rule, applied to the two optional fields: a
    caller refuses rather than substituting. Both of these would be an
    invented price if they resolved the other way."""

    def test_an_absent_currency_judgement_refuses(self):
        assert verdict(NO_JUDGEMENT) == "stale"

    def test_a_vouched_price_with_no_age_refuses(self):
        assert verdict(NO_AGE) == "stale"


@requires_node
class TestEveryClauseIsLoadBearing:
    """Each mutation deletes one clause and asserts the verdict moves.

    Every one asserts `mutated != source` first. A mutation test whose
    mutation no longer applies is a test that passes for free, and this repo
    has been bitten by exactly that (`tests/test_sweep_tone_predicate.py`
    records it).
    """

    def test_deleting_the_null_check_makes_an_unpriced_ticker_crash_or_lie(
        self, tmp_path
    ):
        source = VISIBILITY_TS.read_text(encoding="utf-8")
        mutated = source.replace(
            '  if (detail === null || detail === undefined) return "absent";\n',
            "",
        )
        assert mutated != source, "the null-check mutation no longer applies"
        with pytest.raises(AssertionError):
            verdict(None, source=mutated, tmp_path=tmp_path)

    def test_deleting_the_dead_check_shows_a_price_on_a_settled_market(
        self, tmp_path
    ):
        source = VISIBILITY_TS.read_text(encoding="utf-8")
        mutated = source.replace('  if (dead) return "absent";\n', "")
        assert mutated != source, "the dead-market mutation no longer applies"
        assert verdict(SETTLED, source=mutated, tmp_path=tmp_path) == "ask"

    def test_deleting_the_currency_check_shows_a_stale_ask_as_a_price(
        self, tmp_path
    ):
        source = VISIBILITY_TS.read_text(encoding="utf-8")
        mutated = source.replace(
            '  if (detail.price_is_current !== true) return "stale";\n', ""
        )
        assert mutated != source, "the currency mutation no longer applies"
        assert verdict(STALE, source=mutated, tmp_path=tmp_path) == "ask"

    def test_deleting_the_age_check_shows_an_ageless_ask_as_a_price(
        self, tmp_path
    ):
        source = VISIBILITY_TS.read_text(encoding="utf-8")
        mutated = source.replace(
            '  if (age === null || age === undefined) return "stale";\n', ""
        )
        assert mutated != source, "the age mutation no longer applies"
        assert verdict(NO_AGE, source=mutated, tmp_path=tmp_path) == "ask"

    def test_inverting_the_verdict_is_caught(self, tmp_path):
        """The check a substring test cannot make. An exactly inverted
        predicate keeps every field name, every literal and every line."""
        source = VISIBILITY_TS.read_text(encoding="utf-8")
        mutated = source.replace(
            '  if (detail.price_is_current !== true) return "stale";\n',
            '  if (detail.price_is_current === true) return "stale";\n',
        )
        assert mutated != source, "the inversion mutation no longer applies"
        assert verdict(CURRENT, source=mutated, tmp_path=tmp_path) == "stale"


class TestOnePredicateOneSpelling:
    """One function decides whether the strip shows a price, and only the
    strip reads it. These are source-text pins on purpose -- "does this file
    call that function" is a question about text.
    """

    def test_the_ticket_is_handed_no_price_visibility_flag(self):
        """**Inverted 2026-09-09, not deleted, and not to make it pass.**

        This asserted `askIsVisible(detail, now)` was passed to the ticket --
        ticket #24's fix, which made the mask's flag DERIVED rather than a
        constant `true`. The mask it fed is gone with the P(YES) field (ADR
        DRAFT-the-ticket-stops-asking-for-a-probability, superseding ADR 0065
        §2), so the flag has no meaning left to derive.

        What is pinned instead is the property that made #24 a defect: the
        ticket must not be told a price is on screen. A bare
        `priceAlreadyVisible` restored here would be exactly the original bug
        with no wording behind it, and the prop no longer exists on the
        component, so it can only arrive as drift.

        Mutation observed red: add `priceAlreadyVisible` back to the mount.
        """
        page = _without_comments(MARKET_PAGE.read_text(encoding="utf-8"))
        assert "priceAlreadyVisible" not in page, (
            "the market screen passes a price-visibility flag to a ticket "
            "that has no such prop and masks nothing (ADR "
            "DRAFT-the-ticket-stops-asking-for-a-probability)"
        )
        assert "askIsVisible" not in page, (
            "`askIsVisible` is read again -- it was removed with its only "
            "caller, and a re-derivation here is the second spelling this "
            "file exists to prevent"
        )

    def test_the_strip_reads_the_shared_predicate_rather_than_respelling_it(self):
        """The half that keeps the fix from rotting. If the strip goes back to
        testing `price_is_current` inline, the page's flag and the strip's
        render are two spellings again and the next condition added to one
        will not reach the other."""
        page = _without_comments(MARKET_PAGE.read_text(encoding="utf-8"))
        strip = page[page.index("function QuoteStrip") :]
        strip = strip[: strip.index("export default function")]
        assert "quoteVisibility(detail, now)" in strip, (
            "the quote strip no longer reads the shared predicate"
        )
        assert "price_is_current" not in strip, (
            "the quote strip re-derives the staleness rule inline -- one "
            "predicate with two spellings, which is the shape this fix exists "
            "to remove"
        )


class TestTheSearchResultReachesThePrice:
    """Ticket #24, Joe's option A: alongside the ticket, never instead of it.

    `tests/test_buy_controls.py` pins the `<ManualTicket` mount from the other
    direction; this asserts the link exists and that adding it did not
    displace the ticket.
    """

    def test_a_result_links_to_the_game_screen(self):
        search = SEARCH.read_text(encoding="utf-8")
        assert "/market/${encodeURIComponent(market.ticker)}" in search, (
            "a search result no longer reaches the market screen, so after "
            "first pitch the only door to a market is still an order form"
        )

    def test_the_link_did_not_replace_the_ticket(self):
        """The element boundary is asserted, not the prefix.

        This guard was written as `"<ManualTicket" in search` and observed
        GREEN under a mutation renaming the component to `<ManualTicketXX` --
        a prefix is a substring of every longer identifier, so it could not
        see the mount being taken away. `tests/test_buy_controls.py`'s
        `MOUNTS` check has the same shape and the same blind spot; it is left
        alone here rather than widened in a lane that is not its own.

        It then stayed green a SECOND time, for a different reason worth more
        than the first: this component's own comments name `<ManualTicket`
        while explaining why the link sits beside it, so the guard was reading
        prose about the mount instead of the mount. Comments are stripped
        before the search for exactly that reason -- a pin on what the code
        does must not be satisfiable by a sentence about what it does.
        """
        search = _without_comments(SEARCH.read_text(encoding="utf-8"))
        assert re.search(r"<ManualTicket[\s/>]", search), (
            "the link replaced the hand-bet ticket; #24 resolved that it sits "
            "alongside it"
        )

    def test_the_link_does_not_promise_a_price_it_cannot_guarantee(self):
        """The defect this whole ticket is about, one level up.

        The label read "See the price and what the desk knows" for one draft.
        The destination renders "the recorder never priced this ticker" when
        there is no detail row and refuses the ask outright when it is stale
        -- the two states `quoteVisibility` exists to name. A link is a claim
        about where it goes, and a search result cannot know whether the game
        screen has a price today, so it may not say that it does.

        Mutation observed red: restore "See the price" as the label.
        """
        search = _without_comments(SEARCH.read_text(encoding="utf-8"))
        link = search[search.index("<Link") : search.index("</Link>")]
        for promise in ("the price", "See the price", "the ask"):
            assert promise not in link, (
                f"the search link promises {promise!r}, which the game screen "
                "does not always have -- the same claim ADR 0065's 2026-09-05 "
                "amendment removed from the ticket, before the ticket's mask "
                "was removed outright"
            )

    def test_the_list_itself_still_carries_no_price(self):
        """The list stays price-free. It used to be ADR 0065's mask that made
        this load-bearing; what makes it load-bearing now is that a price here
        would carry no age, no currency judgement and no book beside it. The
        link changes where a reader can go, never what this component shows.
        """
        search = _without_comments(SEARCH.read_text(encoding="utf-8"))
        for field in ("ask_dollars", "ask_display", "ask_tenths"):
            assert field not in search, (
                f"the search list now renders {field} -- an ask with no age "
                "and no currency judgement beside it, which is the one thing "
                "this screen must not show"
            )
