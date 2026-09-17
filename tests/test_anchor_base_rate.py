"""The slate says how often a sharp book was behind the prices, before the rows.

Joe's answer, 2026-09-16, option A. Every price surface already marks the
individual row (`test_soft_fallback_is_shown_on_every_price_surface.py`), but
on NCAAF `spreads` and `totals` that marker fires on about seven rows in ten,
and a caveat that fires on most rows stops being read. `AnchorBaseRate.tsx`
reports the base rate per (league, market family) for the rows on screen.

THE THREE PROPERTIES THAT MAKE IT HONEST, AND WHY EACH IS PINNED
----------------------------------------------------------------
1. **Per (league, MARKET FAMILY), never per league alone.** Measured live
   2026-09-16: NCAAF `h2h` anchored ~84% of the time, NCAAF `spreads` ~30%.
   A per-league number pools two populations that disagree and describes
   neither — CLAUDE.md, "a pooled number is not a finding until the parts
   agree". This is why `f.market` was added to the slate payload at all.
2. **Every group is listed, including the fully-anchored ones.** A block that
   rendered only the thin groups would be a warning that fires on bad news and
   stays silent otherwise, which is the exact defect `ParlayCards.tsx` carried
   until the day before this shipped: a check that only speaks up when
   something is wrong reads as a check that passed.
3. **Unknown is counted separately and never folded into either side.**
   `anchored_on_sharp` is `null` when the join missed, which is not the same
   fact as "no sharp book" (CLAUDE.md: unreadable resolves to `None`, never
   `0`). A group with no readable rows prints no fraction at all, because a
   denominator of zero is not a rate.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Source text, not rendering.** Same instrument and same limitation as
  `test_soft_fallback_is_shown_on_every_price_surface.py` and
  `test_good_chance_picks.py`: a green suite says the component contains the
  right branches, not that they render, are legible, or fit on a phone.
- **Nothing about the counts being RIGHT on live.** Whether
  `anchored_on_sharp` is correct is `backend/core/devig.py`; whether the
  market family reaches the payload is the serialiser test below. The
  arithmetic here is counted in the browser from rows the server sent.
- **Nothing about whether it changes a bet.** It pins that the base rate is
  on the screen above the rows, not that Joe reads it.

Mutations, each observed red:
  1. group on league alone (drop `consensus_market` from the bucket key)
  2. render only buckets with at least one unanchored row
  3. count `null` as unanchored instead of unknown
  4. print `0 of 0` when no row in a group is readable
  5. drop `f.market AS consensus_market` from the slate query

THE PICKS HALF -- `PicksAnchorBaseRate.tsx`, JOE'S `54A`, 2026-09-17
--------------------------------------------------------------------
Ticket #54 asked the question the Games answer did not settle: **Picks ranks
one row per game and that row is always the moneyline favourite**, so
`consensus_market` is constant there and the approved (league, market family)
grouping collapses into per league -- the very pooling property 1 above
refuses. Joe answered A: put the block on Picks, group by league, and say
`moneyline` out loud.

So the Picks variant is held to the same three properties and to two more:

4. **The sentence names the market family.** "MLB -- 7 of 11" on a screen the
   reader cannot tell is moneyline-only reads as a statement about MLB, whose
   spreads and totals anchor far less often. The word is what bounds the
   claim to the rows it counted; it is the reason option C was refused.
5. **Constancy is pinned at the producers, not assumed.** No
   `consensus_market` key was added to the picks payload -- it would arrive
   the same on every row of every response. What makes that safe is that the
   only two arms of the runner that write a `recommendations` row are the
   moneyline one and the prop one, and the picks loop excludes props by name;
   `_price_spread_event` and `_price_totals_event` write `fair_prices` and no
   recommendation (ADR 0070). The day that stops being true the word
   "moneyline" on the screen becomes false, and the tests below are what say
   so rather than the screen.

The Games block's closing paragraph does NOT travel: it explains that each
sharp book quotes one main line per game, so a Kalshi spread rung at another
number has no sharp quote to match. There is one moneyline per game and that
mechanism does not operate; writing a replacement would mean asserting what a
low count MEANS on `h2h`, which this repo has not measured.

Picks mutations, each observed red:
  6. drop the word `moneyline` from the rendered count
  7. drop `<Term k="moneyline">` from the heading
  8. count `null` as unanchored in the picks bucketer
  9. print `0 of 0` when no pick in a league is readable
 10. filter the picks buckets down to the thin ones
 11. sort the picks buckets
 12. render the block below `<GoodChancePicks>` instead of above it
 13. copy the Games closing paragraph onto the Picks block
 14. build a `Candidate` in the spread arm of the runner
 15. rank player props in the picks loop
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "frontend" / "src" / "components" / "AnchorBaseRate.tsx"
PICKS_COMPONENT = (
    ROOT / "frontend" / "src" / "components" / "PicksAnchorBaseRate.tsx"
)
SLATE_PAGE = ROOT / "frontend" / "src" / "app" / "slate" / "page.tsx"
PICKS_PAGE = ROOT / "frontend" / "src" / "app" / "picks" / "page.tsx"
ROUTES = ROOT / "backend" / "api" / "routes.py"
RUNNER = ROOT / "backend" / "runner.py"
SERIALISE = ROOT / "backend" / "api" / "serialise.py"
GLOSSARY = ROOT / "frontend" / "src" / "lib" / "glossary.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _code_only(text: str) -> str:
    """`text` with comments stripped.

    A prohibition's own explanation must not satisfy the grep that enforces
    it -- the `test_crew_bubble` lesson, and live here: the Picks component's
    docstring says at length why it carries no `consensus_market` and why the
    Games closing paragraph about Pinnacle and Matchbook must not travel, so
    without this both assertions below would pass on the comment alone.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


class TestTheMarketFamilyTravels:
    """Without it the block can only pool, which is the thing it must not do."""

    def test_the_slate_query_selects_the_consensus_market(self):
        assert "f.market AS consensus_market" in _read(ROUTES)

    def test_the_serialiser_emits_it(self):
        source = _read(SERIALISE)
        assert '"consensus_market"' in source

    def test_an_absent_column_serialises_as_None_not_a_placeholder(self):
        """A row whose family is unknown must be countable as unknown.

        Filing it under some default family would put rows into a bucket whose
        rate then describes a population it does not belong to.
        """
        source = _read(SERIALISE)
        block = source[source.index('"consensus_market"') :][:400]
        assert "else None" in block


class TestTheGroupingIsPerLeagueAndMarket:
    def test_the_bucket_key_uses_both(self):
        source = _read(COMPONENT)
        match = re.search(r"const key = `\$\{league[^`]*`", source)
        assert match is not None, "bucket key not found"
        assert "market" in match.group(0), match.group(0)

    def test_the_component_reads_the_market_family_off_the_row(self):
        assert "row.consensus_market" in _read(COMPONENT)


class TestEveryGroupIsListed:
    """Property 2. The defect this forecloses has already shipped once."""

    def test_no_bucket_is_filtered_out_before_rendering(self):
        """`buckets.map` renders the whole list, with no `.filter` between.

        A `.filter` here is how "show only the bad ones" would arrive, and it
        would look like a tidy-up in review.
        """
        source = _read(COMPONENT)
        render = source[source.index("buckets.map") - 200 :][:300]
        assert ".filter" not in render, render

    def test_bucketRows_returns_every_group_it_built(self):
        source = _read(COMPONENT)
        body = source[source.index("export function bucketRows") :]
        body = body[: body.index("\n}")]
        assert "return [...buckets.values()]" in body
        assert ".filter" not in body


class TestUnknownIsItsOwnCount:
    """Property 3. `null` is not `false`."""

    def test_the_three_states_are_branched_separately(self):
        source = _read(COMPONENT)
        assert "=== true" in source
        assert "=== false" in source
        # The `else` arm is the unknown one; a two-way branch would fold null
        # into whichever side the truthiness test happened to take.
        assert "bucket.unknown += 1" in source

    def test_a_group_with_no_readable_row_prints_no_fraction(self):
        """`0 of 0` is not a rate, and printing one invents a quantity."""
        source = _read(COMPONENT)
        assert "known === 0" in source
        guard = source[source.index("known === 0") :][:400]
        assert "unreadable" in guard

    def test_unreadable_rows_are_reported_beside_a_readable_fraction(self):
        source = _read(COMPONENT)
        assert "unreadable" in source
        assert "bucket.unknown > 0" in source


class TestItSitsAboveTheRows:
    """Its whole job is to set the expectation BEFORE the per-row warnings."""

    def test_the_slate_renders_it(self):
        assert "<AnchorBaseRate rows={rows} />" in _read(SLATE_PAGE)

    def test_it_is_rendered_before_the_row_list(self):
        source = _read(SLATE_PAGE)
        assert source.index("<AnchorBaseRate") < source.index("rows.map((row)")


class TestItTeachesTheTerm:
    """Joe asked to be educated; every betting term gets defined at first use."""

    def test_the_glossary_defines_a_sharp_book(self):
        source = _read(GLOSSARY)
        assert "sharp_book:" in source
        entry = source[source.index("sharp_book:") :][:600]
        assert "Pinnacle" in entry and "Matchbook" in entry

    def test_the_heading_uses_the_glossary_term(self):
        assert 'Term k="sharp_book"' in _read(COMPONENT)


class TestItMakesNoClaimBeyondTheCount:
    """CLAUDE.md: a per-row fact is transparency, an ordering is a claim."""

    def test_it_does_not_sort_or_score(self):
        source = _read(COMPONENT)
        body = source[source.index("export function bucketRows") :]
        assert ".sort(" not in body, "buckets must keep the rows' own order"

    def test_it_prints_counts_rather_than_a_percentage(self):
        """`3 of 10` carries its denominator; `30%` does not.

        The whole reason this block exists is that a rate without its
        denominator reads as a measurement of the sport rather than of the
        eleven rows in front of you.
        """
        source = _read(COMPONENT)
        rendered = source[source.index("function BucketLine") :]
        assert "toFixed" not in rendered
        assert "%" not in rendered.replace("100%", "")


# ---------------------------------------------------------------------------
# THE PICKS HALF -- `PicksAnchorBaseRate.tsx`, Joe's `54A`, ticket #54.
# ---------------------------------------------------------------------------


class TestThePicksBlockSaysMoneylineOutLoud:
    """Property 4, and the whole reason option C was refused.

    On Picks every ranked row is a moneyline favourite, so the fraction is a
    statement about that league's moneylines and about nothing else. An
    unqualified "MLB -- 7 of 11" reads as a statement about MLB, whose
    spreads anchored about 30% of the time on the 2026-09-16 live read
    against about 84% for `h2h`. The word is the honest part.
    """

    def test_the_readable_count_names_the_market_family(self):
        """Mutation 6 observed red: drop `moneyline` from the count."""
        source = _read(PICKS_COMPONENT)
        assert "{bucket.anchored} of {known} moneyline" in source, (
            "the picks base rate prints a bare fraction, which reads as a "
            "claim about the league rather than about its moneylines"
        )

    def test_the_unreadable_count_names_it_too(self):
        """The `known === 0` arm prints no fraction but still counts picks,
        and a count of picks is as league-shaped as a fraction of them."""
        source = _read(PICKS_COMPONENT)
        assert "anchor unreadable on {bucket.unknown} moneyline" in source

    def test_the_heading_teaches_the_word(self):
        """Mutation 7 observed red: drop the Term from the heading.

        Joe is a beginner and asked to be educated; `moneyline` is a betting
        term and gets defined at first use like `spread` and `total` before
        it.
        """
        assert '<Term k="moneyline">' in _read(PICKS_COMPONENT)

    def test_the_glossary_defines_it(self):
        source = _read(GLOSSARY)
        assert "moneyline:" in source
        entry = source[source.index("moneyline:") :][:600]
        assert "winner" in entry or "who wins" in entry


class TestThePicksBlockGroupsByLeagueAlone:
    """Property 1, in the form the Picks population actually takes.

    Grouping by (league, market family) here would build one bucket per
    league anyway -- the degenerate case #54 was opened about -- while
    implying a distinction the screen cannot draw.
    """

    def test_the_bucket_key_is_the_league(self):
        source = _read(PICKS_COMPONENT)
        assert 'const key = league ?? "?";' in source

    def test_it_reads_no_market_family_off_a_pick(self):
        """Comment-stripped: the docstring explains this absence at length,
        and the explanation must not satisfy the grep."""
        assert "consensus_market" not in _code_only(_read(PICKS_COMPONENT))


class TestThePicksPayloadIsMoneylineByConstruction:
    """Property 5. What makes the word on the screen true is upstream.

    No `consensus_market` key rides the picks payload: it would be constant
    on every row of every response. The cost of leaving it out is that the
    constancy has to be pinned where it is produced, which is here. If a
    spread rung ever starts writing a `recommendations` row, the Picks screen
    would silently start counting non-moneylines under the word `moneyline`
    -- these tests fire first.
    """

    def test_the_ranked_pick_carries_no_market_family(self):
        source = _read(ROUTES)
        block = source[
            source.index("ranked.append(") : source.index("ranked.sort(")
        ]
        assert "anchored_on_sharp" in block, "wrong block: " + block[:200]
        assert "consensus_market" not in block, (
            "a market-family key was added to the picks payload; if it is "
            "genuinely not constant any more, the screen must group by it"
        )

    def test_the_spread_and_totals_arms_write_no_recommendation(self):
        """Mutation 14 observed red: build a `Candidate` in the spread arm.

        ADR 0070: both arms write `fair_prices` and stay off the
        recommendation, gate and board path. That is what leaves the slate's
        recommendation rows to the moneyline arm and the prop arm.
        """
        source = _read(RUNNER)
        arms = source[
            source.index("def _price_spread_event(") : source.index(
                "def link_discovered_events("
            )
        ]
        assert "def _price_totals_event(" in arms, "the slice missed an arm"
        assert "Candidate(" not in arms, (
            "a spread or totals rung now becomes a recommendation, so a "
            "non-moneyline row can reach the picks ranking and the Picks "
            "base rate would count it under the word 'moneyline'"
        )
        assert "persist_if_changed" not in arms

    def test_the_runner_does_build_candidates_somewhere(self):
        """The anti-vacuity anchor for the assertion above: a rename that
        made `Candidate(` unfindable would make it pass perfectly."""
        assert _read(RUNNER).count("Candidate(") >= 2

    def test_the_picks_loop_excludes_player_props(self):
        """Mutation 15 observed red: rank props too.

        The other half of the constancy. A prop's fair price is built from a
        prop market key, never `h2h`; ticket #23 excludes them server-side
        because a prop inherits its game's fixture id.
        """
        source = _read(ROUTES)
        loop = source[
            source.index("for game_key, item, is_prop in picks_source:") :
        ][:600]
        assert "if is_prop:" in loop
        assert "continue" in loop.split("if is_prop:", 1)[1][:200]


class TestThePicksBlockKeepsTheOtherThreeProperties:
    """Properties 1-3, re-pinned on the second component.

    The Games file passing them says nothing about this one, and "it is the
    same block" is exactly the assumption under which the second copy of a
    fixed defect survives (ADR 0154's shape, `tasks/lessons.md`).
    """

    def test_unknown_is_its_own_count(self):
        """Mutation 8 observed red: fold `null` into unanchored."""
        source = _read(PICKS_COMPONENT)
        assert "pick.anchored_on_sharp === true" in source
        assert "pick.anchored_on_sharp === false" in source
        assert "bucket.unknown += 1" in source

    def test_a_league_with_no_readable_pick_prints_no_fraction(self):
        """Mutation 9 observed red: print `0 of 0`. A denominator of zero is
        not a rate."""
        source = _read(PICKS_COMPONENT)
        assert "known === 0" in source
        guard = source[source.index("known === 0") :][:400]
        assert "unreadable" in guard

    def test_every_league_is_listed(self):
        """Mutation 10 observed red: filter to the thin leagues only. A check
        that speaks up only on bad news reads as a check that passed."""
        source = _read(PICKS_COMPONENT)
        render = source[source.index("buckets.map") - 200 :][:300]
        assert ".filter" not in render, render
        body = source[source.index("export function bucketPicksByLeague") :]
        body = body[: body.index("\n}")]
        assert "return [...buckets.values()]" in body
        assert ".filter" not in body

    def test_it_does_not_sort_or_score(self):
        """Mutation 11 observed red: sort the buckets. A per-row fact is
        transparency; an ordering is a claim (ADR 0071)."""
        body = _read(PICKS_COMPONENT)
        body = body[body.index("export function bucketPicksByLeague") :]
        assert ".sort(" not in body

    def test_it_prints_counts_rather_than_a_percentage(self):
        source = _read(PICKS_COMPONENT)
        rendered = source[source.index("function LeagueLine") :]
        assert "toFixed" not in rendered
        assert "%" not in rendered.replace("100%", "")


class TestItSitsAboveThePicksList:
    """Its job is to set the expectation BEFORE the per-row markers."""

    def test_the_picks_screen_renders_it(self):
        assert "<PicksAnchorBaseRate ranked={picks.ranked} />" in _read(
            PICKS_PAGE
        )

    def test_it_is_rendered_before_the_ranked_block(self):
        """Mutation 12 observed red: move it below `<GoodChancePicks>`."""
        source = _read(PICKS_PAGE)
        assert source.index("<PicksAnchorBaseRate") < source.index(
            "<GoodChancePicks"
        )

    def test_the_games_block_is_not_the_one_on_picks(self):
        """The two screens hold different populations and group differently;
        rendering the Games component here would pool by a family that is
        constant on this screen."""
        assert "<AnchorBaseRate" not in _code_only(_read(PICKS_PAGE))


class TestTheSpreadsParagraphDoesNotTravel:
    """It is about spreads and totals, and there are none on this screen.

    Each sharp book quotes one main line per game, so a Kalshi spread rung at
    another number often has no sharp quote to match. There is one moneyline
    per game; the mechanism does not operate, and the sentence would explain
    a low count with a reason that is not the reason.
    """

    def test_the_picks_block_does_not_carry_it(self):
        """Mutation 13 observed red: copy the paragraph across."""
        rendered = _code_only(_read(PICKS_COMPONENT))
        assert "Pinnacle" not in rendered
        assert "Spreads and totals" not in rendered

    def test_the_games_block_still_does(self):
        """The anti-vacuity anchor: the grep above must be able to find the
        sentence where it belongs, or it proves nothing where it does not."""
        rendered = _code_only(_read(COMPONENT))
        assert "Pinnacle" in rendered
        assert "Spreads and totals" in rendered
