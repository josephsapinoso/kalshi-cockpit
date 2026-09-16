"""The "likely winners tonight" block's screen half (ADR 0067).

Source-text assertions, the same instrument as `tests/test_crew_bubble.py`
and with the same limitation: a green suite says the component contains and
omits the right text, not that it renders, is reachable, or is legible.

The server half — ranking, staleness, the counted exclusions, the note's
exact sentence, and the no-edge-key walk — is `tests/test_slate_picks.py`.
These tests pin what only the screen can get wrong: rendering the payload's
own sentence rather than writing one, offering no order affordance, and not
wearing money ink.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
PICKS = FRONTEND / "components" / "GoodChancePicks.tsx"
SLATE_PAGE = FRONTEND / "app" / "slate" / "page.tsx"
#: The block as a screen of its own (decision-map #8, 2026-09-02). Every
#: chase-surface prohibition on the block applies to the page that hosts it
#: under the nav word "Picks"; the walk below runs over both.
PICKS_PAGE = FRONTEND / "app" / "picks" / "page.tsx"
CHASE_SURFACES = [
    pytest.param(PICKS, id="GoodChancePicks"),
    pytest.param(PICKS_PAGE, id="picks-page"),
]


def source(path: Path) -> str:
    assert path.exists(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """`text` with comments removed, so a prohibition's own explanation
    cannot fail the grep that enforces it (the `test_crew_bubble` lesson)."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


class TestTheBlockRendersTheServersSentence:
    def test_the_note_renders_verbatim_from_the_payload(self):
        """`{picks.note}` in the JSX — the screen prints the server's
        chance≠edge sentence rather than authoring its own, so the two
        cannot come to disagree about what the block claims."""
        assert "{picks.note}" in source(PICKS)

    def test_the_counted_exclusions_render_in_words(self):
        text = source(PICKS)
        assert "not_ranked.stale_consensus" in text
        assert "not_ranked.favorite_unpriced" in text


class TestTheBlockIsNotAChaseSurface:
    """Walked over the block AND the `/picks` page that hosts it (#8
    amendment 3): a prohibition that held for a block on Games and lapsed the
    day the block got a nav slot would have lapsed exactly where it matters.
    Mutation observed red on the page: import `ManualTicket` into
    `app/picks/page.tsx` -- `test_nothing_here_opens_a_ticket[picks-page]`."""

    @pytest.mark.parametrize("path", CHASE_SURFACES)
    def test_no_money_ink(self, path):
        """`bg-accent` is reserved for money (ADR 0061); a favorites list
        wearing it would read as a buy button per game."""
        assert "bg-accent" not in code_only(source(path))

    @pytest.mark.parametrize("path", CHASE_SURFACES)
    def test_nothing_here_opens_a_ticket(self, path):
        """Entries link to the game's own screen and nowhere else. A ticket
        on a ranked favorites list is the tilt reviewer's chase surface."""
        text = code_only(source(path))
        for banned in ("TicketSheet", "TicketTrigger", "ManualTicket",
                       "/api/orders", "/api/manual-orders"):
            assert banned not in text, f"{banned} appears in {path.name}"

    @pytest.mark.parametrize("path", CHASE_SURFACES)
    def test_no_streak_or_hit_count(self, path):
        """A "picks that hit" tally is the ego-loaded aggregate the CLV
        ruling banned below n >= 30; this block must never grow one."""
        text = code_only(source(path)).lower()
        for banned in ("hit rate", "hitrate", "streak", "record:"):
            assert banned not in text


class TestTheSlatePageCarriesIt:
    def test_the_page_renders_the_block(self):
        assert "<GoodChancePicks" in source(SLATE_PAGE)

    def test_the_page_passes_the_payload_block_through(self):
        """`picks={data.picks}` — the page hands the server's block over
        whole; deriving picks client-side from the rows would be a second
        ranking implementation that could disagree with the first."""
        assert "picks={data.picks}" in source(SLATE_PAGE)


class TestAStaleRowSaysTheAgeAndTheRemedy:
    """Ticket #47, Joe's A (2026-09-16). "ask not current" named a state and
    no way out. The server still withholds the ask (deliberate: an hours-old
    ask beside a live chance reads as a quote) and now sends the quote's
    live age beside it; the row prints that age and what to do about it.

    Mutations, each observed red:
      1. restore the literal "ask not current"
      2. print the age off `Date.now() - something` instead of the served
         `quote_age_now_ms`
      3. drop the remedy sentence
    """

    def test_the_old_wording_is_gone(self):
        assert "ask not current" not in code_only(source(PICKS))

    def test_the_age_is_the_served_quote_age_under_a_number_guard(self):
        """Rendered only when the server sent a number -- an unknown age
        prints no figure, never "0 min"."""
        text = code_only(source(PICKS))
        assert 'typeof pick.quote_age_now_ms === "number"' in text
        assert "ageWords(pick.quote_age_now_ms)" in text

    def test_the_remedy_is_named_on_the_row(self):
        text = code_only(source(PICKS))
        assert "refresh the books" in text
        assert "open the game screen" in text

    def test_no_age_is_computed_on_the_screen(self):
        """Every duration here is one the server measured on its own clock.
        The component subtracts no two timestamps and reads no wall clock."""
        text = code_only(source(PICKS))
        assert "Date.now()" not in text
        assert "- pick.commence_ms" not in text
        assert "pick.commence_ms -" not in text

    def test_a_duration_never_prints_as_zero_minutes(self):
        """`ageWords` takes the seconds branch below a minute, so no served
        age can print as "0 min"; and the literal is nowhere in the file."""
        text = code_only(source(PICKS))
        body = text.split("function ageWords(")[1].split("}")[0]
        assert "ms < 60_000" in body
        assert "0 min" not in text


class TestAStartedRowIsMarkedNotMoved:
    """Ticket #42, the Picks half, Joe's A (2026-09-16). The list is sorted
    by chance, so the kickoff column cannot be scanned for what is already
    in play; a started row says so, in the same muted register, and keeps
    its place.

    Mutations, each observed red:
      1. drop the `started_ago_ms` branch
      2. `ranked.filter(...)` out the started rows before mapping
      3. `[...ranked].sort(...)` by anything before mapping
    """

    def test_the_mark_reads_the_served_field_under_a_number_guard(self):
        text = code_only(source(PICKS))
        assert 'typeof pick.started_ago_ms === "number"' in text
        assert "started {ageWords(pick.started_ago_ms)} ago" in text

    def test_the_mark_is_muted_not_urgent(self):
        """The same register as the kickoff beside it -- not accent ink,
        which on this product is money or a warning (ADR 0061)."""
        text = code_only(source(PICKS))
        span = text.split("started {ageWords(pick.started_ago_ms)} ago")[0]
        opener = span[span.rindex("<span"):]
        assert "text-muted" in opener
        assert "accent" not in opener

    def test_nothing_reorders_filters_or_gates_the_ranking(self):
        """ADR 0067: the server's order is `fair_probability` alone and the
        screen renders it whole. `ranked.map(` is the only traversal."""
        text = code_only(source(PICKS))
        for banned in (
            "ranked.sort(", "ranked].sort(", ".toSorted(", "ranked.filter(",
            "ranked].filter(", "started_ago_ms ?", "started_ago_ms &&",
        ):
            assert banned not in text, f"{banned!r} touches the ranking"
        assert "ranked.map(" in text
