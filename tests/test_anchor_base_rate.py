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
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "frontend" / "src" / "components" / "AnchorBaseRate.tsx"
SLATE_PAGE = ROOT / "frontend" / "src" / "app" / "slate" / "page.tsx"
ROUTES = ROOT / "backend" / "api" / "routes.py"
SERIALISE = ROOT / "backend" / "api" / "serialise.py"
GLOSSARY = ROOT / "frontend" / "src" / "lib" / "glossary.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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
