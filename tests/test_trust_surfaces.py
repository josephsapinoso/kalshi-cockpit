"""The sweet spot reaches three screens, and all three say the same thing.

ADR 0090 built the evidence score and shipped it on the parlay card. Joe chose
**all three** surfaces -- the card, the slate row and the market screen -- and
this is the other two, plus the property that only exists once there is more
than one: **one tap must not change the number.**

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **That a high-trust row wins.** Nothing here is scored against an outcome.
  The score counts checks the desk already refuses on; it contains no edge
  term, and that exclusion is arithmetic rather than taste (`beta = -0.141`,
  every interval below the registered 0.40 threshold, so a composite carrying
  the gap would rank the least trustworthy rows highest).
- **That the checks are equally important.** They are counted equally because
  that is the only weighting that invents nothing.
- **Anything about how the score looks at 390px.** These are wire values and
  source assertions. The 2026-08-31 typography defect -- `EVIDENCE 7/7 CHECKS`
  with the caveat outside the styled span -- passed every wording test there
  was, and was caught by opening the page. A source test can prove a string is
  present and can never prove it is legible.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import httpx
import pytest

from backend.api import routes as api_routes
from backend.api.routes import create_app
from backend.config import AppConfig, StalenessConfig
from backend.core.suppression import SuppressionConfig
from backend.core.trust import TrustThresholds, method_spread_points
from backend.store import db

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src"
TRUST_NOTE = FRONTEND / "components" / "TrustNote.tsx"
SLATE_PAGE = FRONTEND / "app" / "slate" / "page.tsx"
MARKET_PAGE = FRONTEND / "app" / "market" / "[ticker]" / "page.tsx"

EVENT = "KXTRUST-EVENT"
TICKER = "KXTRUST-YES"


async def get(app, path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path)


def _seed(path, *, with_fair: bool = True):
    """One linked game with one recommendation, optionally devigged.

    `with_fair=False` is the row whose `fair_prices` join finds nothing --
    `fair_price_id` is nullable in the schema, and that row must not be scored
    on four checks it has no inputs for.
    """
    conn = db.init_db(path)
    now = db.now_ms()
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, title, first_seen_ms, "
        "last_seen_ms, commence_ms) VALUES (?, 'Away at Home', 1000, 1000, ?)",
        (EVENT, now + 3_600_000),
    )
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, title, "
        "yes_side_team, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, 'moneyline', 'Home', 1000, 1000)",
        (TICKER, EVENT),
    )
    conn.execute(
        "INSERT INTO event_links (id, kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES (1, ?, 'odds-1', 'baseball_mlb', 'exact_alias_pair', 0, 1000)",
        (EVENT,),
    )
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal) VALUES (1000, 'baseball_mlb', 'odds-1', ?, 'Home', "
        "'Away', 'pinnacle', 'h2h', 'Home', 1.9)",
        (now + 3_600_000,),
    )
    fair_id = None
    if with_fair:
        conn.execute(
            "INSERT INTO fair_prices (id, computed_ms, link_id, market, "
            "outcome_name, p_multiplicative, p_additive, p_power, p_shin, "
            "p_conservative, market_width, book_count, books_used, "
            "anchored_on_sharp) VALUES (1, 1000, 1, 'h2h', 'Home', 0.53, "
            "0.535, 0.532, NULL, 0.53, 0.012, 5, ?, 1)",
            ('["pinnacle"]',),
        )
        fair_id = 1
    conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, "
        "ticker, link_id, fair_price_id, side, entry_ask_tenths, "
        "fair_probability, edge_tenths, fee_predicted, ev_net_dollars, "
        "kelly_fraction, suggested_contracts, reference_contracts, "
        "kalshi_quote_age_ms, odds_age_ms, depth_at_ask, reason_text) "
        "VALUES (?, 1, ?, 1, ?, 'yes', 500, 0.53, 5.0, 0.1, 0.2, 0.01, 0, 0, "
        "1000, 2000, 40.0, 'test row')",
        (now, TICKER, fair_id),
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def app(tmp_path):
    return create_app(
        AppConfig(instance_mode="demo", db_path=_seed(tmp_path / "trust.db"))
    )


class TestOneTapDoesNotChangeTheNumber:
    """The property that only exists once the score is on two screens.

    The slate row and the market screen are one tap apart. Two scorers -- or
    one scorer fed differently -- would let a row read `6/8` on the list and
    `7/8` on its own page, which is the two-screens-disagree failure this repo
    has recorded on kickoff time (ticket #26) and on the refusal string.
    """

    async def test_the_slate_and_the_market_screen_agree_exactly(self, app):
        rows = (await get(app, "/api/slate")).json()["rows"]
        assert rows, "the slate returned nothing, so this asserts nothing"
        compared = 0
        for row in rows:
            detail = (await get(app, f"/api/market/{row['ticker']}")).json()
            assert row["trust"] is not None, f"{row['ticker']} carries no score"
            assert row["trust"] == detail["trust"], (
                f"{row['ticker']}: the list and the detail screen disagree "
                f"about the evidence behind the same row"
            )
            compared += 1
        assert compared == 1

    async def test_both_score_against_the_configs_own_limits(self, app):
        """Not a second set of numbers written down in the route.

        `from_configs` is the only constructor, so a limit that moves in
        `StalenessConfig` or `SuppressionConfig` moves here. Asserted by
        reading the check details back against the config the app was built
        with, rather than against a literal typed into this test.
        """
        expect = TrustThresholds.from_configs(
            StalenessConfig.load(), SuppressionConfig()
        )
        detail = (await get(app, f"/api/market/{TICKER}")).json()
        books = next(
            c for c in detail["trust"]["checks"] if c["name"] == "books"
        )
        assert f"need {expect.min_book_count}" in books["detail"]


class TestTheScoreIsWiredIntoBothRoutes:
    """The built-but-never-called failure, which this repo has hit four times.

    A module can be complete, tested and imported by nothing. These assert the
    route actually passes its thresholds -- not that the function works.
    """

    async def test_the_slate_serves_a_score(self, app):
        """Mutation observed red: drop `trust_thresholds=` from the
        `_serialise` call in `/api/slate`."""
        row = (await get(app, "/api/slate")).json()["rows"][0]
        assert row["trust"]["total"] == 8
        assert row["trust"]["passed"] >= 1

    async def test_the_market_screen_serves_a_score(self, app):
        """Mutation observed red: drop `trust_thresholds=` from the
        `_serialise` call in `/api/market/{ticker}`."""
        detail = (await get(app, f"/api/market/{TICKER}")).json()
        assert detail["trust"]["total"] == 8

    async def test_the_ledger_serves_none(self, app):
        """A historical row is scored against ages that must not move.

        `/api/ledger` calls `_serialise` with neither `now_ms` nor a threshold
        set, so the key is absent rather than null: a score computed from
        write-time ages would say "the consensus was 2 seconds old" about a
        row from last month.
        """
        rows = (await get(app, "/api/ledger")).json()["rows"]
        assert rows, "the ledger returned nothing, so this asserts nothing"
        for row in rows:
            assert "trust" not in row


class TestAScoreIsRefusedRatherThanHalfComputed:
    async def test_a_row_with_no_fair_price_carries_no_score(self, tmp_path):
        """Four of the eight checks read off the `fair_prices` row.

        Scoring anyway publishes "fewer than two devig methods solved" -- a
        claim about the DEVIG, when the truth is that there was no fair price
        to read. Four unknowns from one missing join is also not the same
        quantity as four separately unmeasured checks, and the payload has no
        way to say which it is holding.

        Mutation observed red: drop the `row["book_count"] is not None` guard.
        """
        app = create_app(
            AppConfig(
                instance_mode="demo",
                db_path=_seed(tmp_path / "nofair.db", with_fair=False),
            )
        )
        row = (await get(app, "/api/slate")).json()["rows"][0]
        # Present and null, not absent: the route asked for a score and the
        # server declined to compute one. An absent key would mean the route
        # never asked, which is the different defect the wiring tests own.
        assert "trust" in row
        assert row["trust"] is None, (
            "an unjoined row was scored on inputs it does not have"
        )

    def test_thresholds_without_a_clock_are_refused(self):
        """The ages are the half a caller is most likely to forget.

        Without `now_ms` and `staleness` there is no live age at all, so both
        clock checks read `unknown` and the row looks examined when nothing
        was measured. Refuse, per `clamping-is-for-values-you-trust`.
        """
        with pytest.raises(ValueError, match="now_ms and staleness"):
            api_routes._serialise(
                {"entry_ask_tenths": 500},
                trust_thresholds=TrustThresholds.from_configs(
                    StalenessConfig.load(), SuppressionConfig()
                ),
            )


class TestOneDefinitionOfMethodDisagreement:
    """Three surfaces score `methods_agree`; one function computes it."""

    def test_fewer_than_two_readings_is_none_not_zero(self):
        """One reading is not perfect agreement, it is one reading.

        `0.0` would score the least-evidenced row as the most agreed-upon --
        the `market_width = 0.0` failure `suppression.py` records.
        """
        assert method_spread_points([0.5]) is None
        assert method_spread_points([0.5, None, None, None]) is None
        assert method_spread_points([None, None]) is None

    def test_two_readings_give_their_span_in_points(self):
        assert method_spread_points([0.50, 0.52, None]) == pytest.approx(2.0)

    def test_the_parlay_helper_delegates_rather_than_repeating_it(self):
        """A second copy would be a second definition of "the methods
        disagree", with no error the day one of them changed."""
        from backend import parlays

        source = inspect.getsource(parlays._method_spread_points)
        assert "method_spread_points(" in source
        assert "max(" not in source, "the arithmetic is repeated here"


class TestTheStripAndTheScoreReportOneDisagreement:
    """Both render "how far the devig readings sit apart" on the same row.

    Found the day the score reached the slate: one row printed `readings
    disagree by 0.6 pts` beside `four methods within 0.5 pts`, and another
    `8.4` against `7.0`. The strip's headline was
    `(domain.hi - domain.lo) * 100` -- the **padded axis**, a tenth of the
    span added at each end so an extreme mark is not half-clipped, so exactly
    1.2x the truth on every row ever rendered. Worse where books are joined:
    `dispersion.ts` pushes the book span into `values`, so the headline was
    not about the readings at all, while the sentence one line below it --
    computed off `methodLo`/`methodHi` -- was right the whole time.

    **A number cannot be checked against itself.** This survived because
    nothing else on the screen claimed the same quantity. Putting a second
    rendering beside it is what found it, and this test is what keeps the two
    from drifting apart again.
    """

    STRIP = FRONTEND / "components" / "DispersionStrip.tsx"

    def test_the_headline_is_the_readings_span_not_the_axis(self):
        """Mutation observed red: restore
        `const spreadPoints = (d.domain.hi - d.domain.lo) * 100;`."""
        source = self.STRIP.read_text(encoding="utf-8")
        assert "const spreadPoints = (methodHi - methodLo) * 100;" in source
        assert "(d.domain.hi - d.domain.lo) * 100" not in source, (
            "the summary prints the padded axis, which overstates the "
            "readings' disagreement by a fifth"
        )

    def test_the_headline_and_the_sentence_below_it_share_their_inputs(self):
        """The sentence was already correct; the headline was not.

        Both must read off `methodLo`/`methodHi`, so a row cannot print one
        span in its summary and a different one when the reader taps it open.
        """
        source = self.STRIP.read_text(encoding="utf-8")
        i = source.index("const spreadPoints")
        j = source.index("readings disagree by", i)
        assert "d.domain" not in source[i:j], (
            "the axis is back in the headline's derivation"
        )


class TestTheSweetSpotIsNeverRenderedBare:
    """The single most likely way this feature goes wrong.

    A lone "6/8" beside a bet reads to a beginner as "this is a 6-out-of-8
    bet" -- the edge claim the whole design avoids, and the measured signal
    points the other way (`beta = -0.141`). These are source assertions
    because the property is about what the component may do.

    Moved here from `test_parlay_leg_facts.py` when the component was
    extracted: it now serves three surfaces, and a guard filed under one of
    them reads as a rule about that screen rather than about the component.
    """

    def _block(self) -> str:
        return TRUST_NOTE.read_text(encoding="utf-8")

    def test_the_number_carries_its_subject(self):
        """`evidence`, not `value`, `score`, `rating` or `quality of bet`."""
        block = self._block()
        assert "evidence" in block
        for banned in ("good bet", "rating", "grade"):
            assert banned not in block, banned

    def test_the_unknown_count_shares_the_scores_own_styled_span(self):
        """Words are not enough; the TYPOGRAPHY has to carry them too.

        Shipped 2026-08-31 with the count outside the styled span, rendering
        `EVIDENCE 7/7 CHECKS - 1 not checked` -- a loud perfect score with a
        lowercase footnote. Every wording test passed. A reader stops at 7/7.

        Mutation observed red: move `{unknown > 0 && ...}` back outside the
        closing `</span>`.
        """
        block = self._block()
        i = block.index("evidence {trust.passed}/{trust.known} checks")
        j = block.index("</span>", i)
        assert "unknown > 0" in block[i:j], (
            "the unknown count is rendered outside the score's own span; it "
            "reads as a footnote to a perfect score"
        )

    def test_the_size_prop_changes_the_scale_and_nothing_else(self):
        """A second size is where the nesting quietly gets a second spelling.

        The scale is one interpolated class on the one span; there is no
        second copy of the score line to keep in step, which is what makes the
        test above true of both values rather than of `compact` alone.
        """
        block = self._block()
        assert block.count("evidence {trust.passed}/{trust.known} checks") == 1
        assert block.count("unknown > 0") == 1
        assert 'size === "panel"' in block

    def test_the_unknown_count_is_shown_not_folded_in(self):
        """`total - known` is how many checks nobody ran.

        Hiding it makes the least-examined row look like the best one -- the
        same failure `suppression.py` records for a 0.0 market width.
        Mutation observed red: render `passed`/`total` and drop the unknowns.
        """
        block = self._block()
        assert "trust.total - trust.known" in block
        assert "not checked" in block

    def test_the_denominator_is_known_not_total(self):
        """Scoring against `total` silently counts an unknown as a miss, which
        is the opposite error and equally wrong: it punishes a row for a check
        nobody ran."""
        block = self._block()
        assert "{trust.passed}/{trust.known}" in block

    def test_every_failure_is_spelled_out(self):
        """Naming one hides the one that mattered more, and choosing which to
        name would be the importance weight the module refuses to invent."""
        block = self._block()
        assert 'state === "fail"' in block
        assert ".join(" in block

    def test_a_full_score_still_disclaims_the_bet(self):
        block = self._block()
        assert "not about whether the bet wins" in block

    def test_the_clean_sentence_names_no_single_surface(self):
        """It renders on a parlay leg, a slate row and a market screen.

        "on this leg" was true of the only caller it had; on the other two it
        is a lie, and one this repo's own rule about copy would not otherwise
        catch.
        """
        block = self._block()
        assert "on this leg passed" not in block

    def test_the_prose_can_break_an_unbreakable_token(self):
        """The failure list embeds `suppressed_reason` verbatim.

        That is often several codes joined by commas with no spaces
        (`stale_odds,too_few_books,no_market_width,...`), which reaches a
        line-breaker as ONE token. Measured on live at 390px: this span ran to
        `scrollWidth` 404 inside a 327px column and pushed the document to 428
        against a 390 viewport -- the slate scrolled sideways on a phone.

        Data-dependent, so an identical read an hour earlier measured a clean
        375 and saw nothing. That is why this is pinned in source rather than
        trusted to a browser check.

        Mutation observed red: drop `break-words` from the outer span.
        """
        block = self._block()
        i = block.index("<span className={`block")
        j = block.index("}>", i)
        assert "break-words" in block[i:j], (
            "the prose cannot break, so a multi-code suppression reason "
            "scrolls the page sideways at 390px"
        )

    def test_no_colour_and_no_sort(self):
        """Red means lose (ADR 0081); a failing evidence check is not a loss.
        And ADR 0071 s2.5 bars ranking by a per-row fact."""
        block = self._block()
        for token in ("text-red", "bg-red", "text-green", "bg-green",
                      "text-positive", "text-negative", ".sort("):
            assert token not in block, token


class TestEverySurfaceReusesTheComponent:
    """No screen draws its own.

    The properties above are guarantees about one implementation, and a copy
    would carry none of them while passing every test written about the screen
    it lives on.
    """

    @pytest.mark.parametrize("page", [SLATE_PAGE, MARKET_PAGE])
    def test_the_page_imports_it(self, page):
        source = page.read_text(encoding="utf-8")
        assert 'from "@/components/TrustNote"' in source
        assert "<TrustNote" in source

    @pytest.mark.parametrize("page", [SLATE_PAGE, MARKET_PAGE])
    def test_the_page_declares_no_score_line_of_its_own(self, page):
        """Mutation observed red: paste `evidence {row.trust.passed}/...` into
        either page."""
        source = page.read_text(encoding="utf-8")
        assert "function TrustNote" not in source
        assert "evidence {" not in source
