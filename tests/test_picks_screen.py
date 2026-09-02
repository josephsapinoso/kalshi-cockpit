"""The "Picks" nav slot opens the ranked list, and the ranked list has no door
to real money on it (decision-map #8, ratified by Joe 2026-08-27; #29 for the
name of the screen it displaced).

Source-text assertions, the same instrument as `tests/test_good_chance_picks.py`
and `tests/test_every_screen_is_reachable.py`, with the same limitation: a green
suite says the files contain and omit the right text, not that the page renders,
is legible, or that the payload is honest (that half is `tests/test_slate_picks.py`,
which walks every key of the block for anything readable as profit).

What these pin, and why each is worth a test rather than a docstring:

- **The nav word "Picks" opens `/picks`, not `/board`.** For two weeks the word
  opened a screen on which nothing has been a pick in the life of the record,
  and every row of it mounted a live hand-bet button.
- **`/picks` renders the same block Games renders, through the same
  component, handed the server's block whole.** A second ranking on the page
  could disagree with the first.
- **No order route on `/picks`.** #8 counted the taps from the Picks tab to a
  real-money confirm: zero under the old mapping, two under this one, and
  that count is the reason the promotion is safe. It stays true only while
  this file fails on the first ticket import.
- **No credit-spending refresh control and no ranked-count headline** -- the
  two prohibitions that only become possible once the block is a screen.
- **The deposit-arithmetic sentence does not travel.** Honest apparatus beside
  the refusal machinery on Games, a funnel beside a favourites list at 11pm.
- **`/board` is served, linked from the footer as "Refusals", with the blurb
  that says what it is; its h1 agrees.** One screen, one name (#29).

Mutation observed red, per test, in the docstring of each.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.test_buy_controls import MOUNTS

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
PICKS_PAGE = FRONTEND / "app" / "picks" / "page.tsx"
PICKS_LOADING = FRONTEND / "app" / "picks" / "loading.tsx"
BOARD_PAGE = FRONTEND / "app" / "board" / "page.tsx"
NAV = FRONTEND / "components" / "Nav.tsx"
FOOTER = FRONTEND / "components" / "Footer.tsx"

#: The sentence #9 wrote for the Picks slot, ratified with its disarming
#: clause 2026-08-27. Whitespace-normalised before comparison because JSX
#: wraps prose across lines.
PICKS_LEDE = (
    "One line for each game the desk could price: the side the sportsbooks "
    "make more likely, the chance they give it, and what Kalshi charges — "
    "ordered by that chance, which is not a claim that any of them is worth "
    "buying."
)

#: #9's seventh string, as the footer blurb for `/board`, with the exactness
#: fix #9 itself sanctioned ("the reason that stopped it") extended to name
#: both kinds of refusal -- measured on live 2026-09-02, two rows in three in
#: the window were refused by the fee bar with no rule named.
REFUSALS_BLURB = (
    "The candidates the engine priced in its last half-hour of recording, "
    "each with the reason that stopped it — a named check, or the fee bar. "
    "Nearly all are refused — the ordinary night."
)


def source(path: Path) -> str:
    assert path.exists(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """`text` with comments removed, so a prohibition's own explanation
    cannot fail the grep that enforces it (the `test_crew_bubble` lesson)."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def prose(text: str) -> str:
    """JSX prose flattened: entities decoded and whitespace collapsed."""
    text = text.replace("&mdash;", "—").replace("&rsquo;", "’").replace("&ldquo;", "“")
    text = text.replace("&rdquo;", "”")
    return re.sub(r"\s+", " ", text)


def nav_links() -> list[tuple[str, str]]:
    """`(href, label)` pairs from `LINKS`, in order, from the code only."""
    text = code_only(source(NAV))
    block = text[text.index("const LINKS = ["):]
    block = block[: block.index("];")]
    return re.findall(r'href:\s*"([^"]+)",\s*label:\s*"([^"]+)"', block)


def footer_entries() -> dict[str, tuple[str, str]]:
    """`href -> (label, blurb)` from `SECONDARY`, from the code only."""
    text = code_only(source(FOOTER))
    block = text[text.index("const SECONDARY = ["):]
    block = block[: block.index("];")]
    return {
        href: (label, blurb)
        for href, label, blurb in re.findall(
            r'href:\s*"([^"]+)",\s*label:\s*"([^"]+)",\s*blurb:\s*"([^"]*)"',
            block,
        )
    }


class TestTheWordPicksOpensTheRankedList:
    def test_the_picks_slot_points_at_picks(self):
        """Mutation observed red: point the entry back at `/board`."""
        assert ("/picks", "Picks") in nav_links(), nav_links()

    def test_nothing_in_the_nav_points_at_board_any_more(self):
        """The demotion is real only if the nav no longer carries it."""
        assert "/board" not in {href for href, _ in nav_links()}

    def test_the_budget_is_still_six_in_the_same_order(self):
        """A swap, not an addition: Gate keeps its visible slot at 390px and
        Playbook stays the link that scrolls."""
        assert [label for _, label in nav_links()] == [
            "Games", "Picks", "Parlays", "Your bets", "Gate", "Playbook",
        ]


class TestThePageRendersTheSameBlockGamesDoes:
    def test_the_page_renders_the_block(self):
        assert "<GoodChancePicks" in code_only(source(PICKS_PAGE))

    def test_the_page_hands_the_servers_block_over_whole(self):
        """`picks={picks}` where `picks` is `data.picks` unchanged -- no
        client-side re-ranking, no filtering, no second implementation."""
        text = code_only(source(PICKS_PAGE))
        assert "const picks = data.picks ?? null;" in text
        assert "picks={picks}" in text

    def test_the_page_carries_the_ratified_lede(self):
        assert PICKS_LEDE in prose(source(PICKS_PAGE))

    def test_the_page_carries_the_truncation_sentence(self):
        """Picks are ranked after the row query's limit; a game lost to it is
        counted in neither exclusion the block prints (#8 amendment 5)."""
        text = code_only(source(PICKS_PAGE))
        assert "slate.truncated" in text
        assert "slate.in_window" in text
        assert "slate.returned" in text


class TestThePageHasNoDoorToMoney:
    """The count that made the promotion safe: from the Picks tab, two
    navigations to a real-money confirm rather than zero."""

    def test_no_ticket_import_or_mount(self):
        """Mutation observed red: add `import ManualTicket from
        "@/components/ManualTicket"` to the page."""
        text = code_only(source(PICKS_PAGE))
        for banned in (
            "TicketSheet",
            "TicketTrigger",
            "ManualTicket",
            "TicketProvider",
            "MarketSearch",
            "LiveBoard",
            "/api/orders",
            "/api/manual-orders",
        ):
            assert banned not in text, f"{banned} appears on the picks screen"

    def test_the_page_is_not_a_buy_surface_in_the_buy_controls_inventory(self):
        """`tests/test_buy_controls.py` asserts every surface in `MOUNTS`
        renders `<ManualTicket`. This page must never be listed there: the
        one screen the word "Picks" opens has no buy button on it, by design
        rather than by omission. Mutation observed red: add
        `"app/picks/page.tsx"` to `MOUNTS`."""
        assert "app/picks/page.tsx" not in MOUNTS, (
            "the picks screen is inventoried as a surface that must mount a "
            "hand-bet ticket; #8 built it as the one screen that must not"
        )

    def test_no_credit_spending_refresh_control(self):
        """`RefreshOddsPanel` stays on Games. On this screen it would be
        "act to make the list non-empty" -- the chase affordance in its
        purest form -- and the empty night is the ordinary one."""
        text = code_only(source(PICKS_PAGE))
        assert "RefreshOddsPanel" not in text
        assert "RefreshOddsButton" not in text
        assert "/api/refresh" not in text

    def test_no_headline_counting_how_many_ranked(self):
        """A number that rises when there is more to bet on. The block's own
        `ranked.length > 0` guards are comparisons, never renders; the page
        may branch on the count and may not print it."""
        text = code_only(source(PICKS_PAGE))
        assert re.search(r"\{[^}]*ranked\.length\s*\}", text) is None, (
            "the picks screen prints how many picks ranked"
        )

    def test_no_money_ink(self):
        """`bg-accent` is reserved for money (ADR 0061)."""
        assert "bg-accent" not in code_only(source(PICKS_PAGE))

    def test_the_deposit_arithmetic_does_not_travel(self):
        """"One contract at 50c needs a $X balance" is a funnel beside a
        favourites list; every cap is a percentage of the observed balance."""
        text = code_only(source(PICKS_PAGE))
        assert "deposit_for_50c_display" not in text
        assert "deposit" not in prose(text).lower()

    def test_no_in_page_link_to_the_refusals_screen(self):
        """#8 struck the link from the foot of Picks (Joe took the footer
        alone, 2026-08-27): every `/board` row carries a live hand-bet
        button. The screen may name Refusals in words; it may not link it."""
        text = code_only(source(PICKS_PAGE))
        assert 'href="/board' not in text
        assert "href={`/board" not in text


class TestTheEmptyNightIsDrawnAsWhatItIs:
    """The version of the app Joe opens most often is the empty one (#20).
    Each state below is a different fact, and a tab that opened to an h1 and
    whitespace on any of them is the indictment #8 levelled at the screen this
    one replaced. Drawn minimally here; #20 owns designing them."""

    def test_the_absent_block_is_named_not_silent(self):
        """The demo backend answers with no `picks` key at all."""
        text = prose(code_only(source(PICKS_PAGE)))
        assert "picks === null" in text
        assert "not available on this instance" in text

    def test_zero_ranked_is_named_and_points_at_refusals_in_words(self):
        text = prose(code_only(source(PICKS_PAGE)))
        assert "Nothing ranked" in text
        assert "on Refusals" in text

    def test_the_unreachable_backend_is_an_error_not_whitespace(self):
        assert "Backend unreachable" in code_only(source(PICKS_PAGE))

    def test_the_stale_slate_is_named(self):
        """Stale and empty look identical unless the page says which."""
        text = code_only(source(PICKS_PAGE))
        assert "slate.is_current" in text
        assert "formatAge(slate.age_ms)" in text

    def test_loading_is_drawn(self):
        """`/api/slate` is ~6s cold and this is the first route in a nav slot
        behind it. The loading state says "not yet answered", and draws no
        row shape -- a skeleton is a promise about what is coming."""
        text = source(PICKS_LOADING)
        assert "export default function" in text
        assert "not yet answered" in text


class TestTheRefusalsScreenHasOneName:
    """#29: the h1, the footer label and the footer's sentence change in the
    same commit, or the screen has two names again."""

    def test_the_footer_carries_board_as_refusals_with_the_blurb(self):
        """Mutation observed red: relabel the entry "Board"."""
        entries = footer_entries()
        assert "/board" in entries, entries
        label, blurb = entries["/board"]
        assert label == "Refusals"
        assert blurb == REFUSALS_BLURB

    def test_the_h1_says_refusals(self):
        """Mutation observed red: put "Board" back in the h1."""
        text = code_only(source(BOARD_PAGE))
        h1 = re.search(r"<h1[^>]*>([^<]*)</h1>", text)
        assert h1 is not None
        assert h1.group(1).strip() == "Refusals"
        assert re.search(r"<h1[^>]*>\s*Board\s*</h1>", text) is None

    def test_the_lede_names_both_kinds_of_refusal(self):
        """82 of 122 rows in the live window on 2026-09-02 were refused by
        the fee bar with no rule named. A lede saying every row sits under a
        named rule would be false on two rows in three."""
        text = prose(code_only(source(BOARD_PAGE)))
        assert "each with the reason that stopped it" in text
        assert "a named check, or the" in text
        assert "fee" in text and "bar it could not clear" in text
        assert "Nearly all are refused" in text

    def test_the_old_lede_is_gone(self):
        """"A bet appears only when the edge survives ..." described the
        screen as a place bets appear. None has, in the life of the record."""
        assert "A bet appears only when" not in source(BOARD_PAGE)
