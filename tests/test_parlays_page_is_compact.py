"""`/parlays` on a phone: one section at a time, compact cards, filters, times (#221).

Joe said the page made him scroll a lot and that props carried no time. What
this pins, as source assertions (this repo has no JS test runner, the pattern
of `tests/test_game_script_card_screen.py`):

- **A three-way switch, default Game scripts, URL-driven**, with the cut
  (`league`, `within_hours`, `horizon`) carried across it, and the page draws
  only the selected section.
- **The card's story sits behind one `<details>`**; the heading, the legs and
  Ask the market do not.
- **Day and league chips filter the list and never order it** (ADR 0071): no
  sort, reverse or rebuild, and the number of games hidden is said.
- **A time on every leg row in all three components.**

What this does not establish: that the page fits at 390px (main checks that on
live), or that Intl formats the day the way the chips assume in every browser.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"
PAGE = SRC / "app" / "parlays" / "page.tsx"
VIEW_LIB = SRC / "lib" / "parlaysView.ts"
SWITCH = SRC / "components" / "ParlaysViewSwitch.tsx"
SCRIPTS = SRC / "components" / "GameScriptCard.tsx"
CARDS = SRC / "components" / "ParlayCards.tsx"
CHECK = SRC / "components" / "CheckAParlay.tsx"


def _code(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


class TestTheSwitchShowsOneSectionAtATime:
    def test_there_are_three_views_in_the_ticket_order(self):
        src = _code(VIEW_LIB)
        keys = re.findall(r'\{ key: "(\w+)", label: "([^"]+)" \}', src)
        assert keys == [
            ("scripts", "Game scripts"),
            ("cards", "Parlay cards"),
            ("check", "Check a parlay"),
        ]

    def test_the_default_is_game_scripts_and_an_unknown_view_falls_back(self):
        src = _code(VIEW_LIB)
        assert 'DEFAULT_PARLAYS_VIEW: ParlaysView = "scripts"' in src
        assert ": DEFAULT_PARLAYS_VIEW" in src

    def test_the_view_is_in_the_url_and_the_cut_survives_the_switch(self):
        src = _code(VIEW_LIB)
        assert 'qs.set("view", view)' in src
        for param in ("league", "within_hours", "horizon"):
            assert f'"{param}"' in src
        assert "KEPT_PARAMS" in src

    def test_the_switch_is_plain_links_built_by_that_helper(self):
        src = _code(SWITCH)
        assert "<Link" in src and "parlaysViewHref(choice.key, params)" in src
        assert "PARLAYS_VIEWS.map(" in src
        assert "aria-current" in src

    def test_the_page_reads_the_view_and_draws_only_the_selected_section(self):
        src = _code(PAGE)
        assert "readParlaysView(params.view)" in src
        assert '{view === "scripts" && <GameScriptParlays />}' in src
        assert '{view === "check" && <CheckAParlay />}' in src
        assert 'view === "cards" && ladder !== null' in src
        assert "<ParlaysViewSwitch" in src

    def test_the_switch_sits_between_the_header_and_the_sections(self):
        src = PAGE.read_text(encoding="utf-8")
        assert (
            src.index("</header>")
            < src.index("<ParlaysViewSwitch")
            < src.index("<CheckAParlay")
            < src.index("<ParlayCards")
        )

    def test_the_cards_views_pickers_stay_in_the_cards_view(self):
        src = _code(PAGE)
        for element in ("<FilterBar", "<WindowPicker", "<RefreshOddsPanel"):
            lines = [ln for ln in src.splitlines() if element in ln]
            assert lines, element
        # Every chip link the cards view draws carries `view=cards`.
        assert src.count('keep="view=cards"') >= 4
        for path in (
            SRC / "components" / "FilterBar.tsx",
            SRC / "components" / "WindowPicker.tsx",
            SRC / "components" / "RefreshOddsPanel.tsx",
        ):
            assert "withKept(" in _code(path), path.name

    def test_a_failed_ladder_read_does_not_take_the_other_views_down(self):
        src = _code(PAGE)
        assert "let ladder: ParlayLadder | null = null;" in src
        # The refusal and the outage are words inside the cards view only.
        assert src.index('view === "cards" && ladder === null') < src.index(
            "Backend unreachable."
        )


class TestTheCardIsCompact:
    def test_the_story_and_reasoning_sit_behind_one_details(self):
        src = _code(SCRIPTS)
        card = src[src.index("export default function GameScriptCard"):]
        card = card[: card.index("function GameHeading")]
        details = re.search(r"<details.*?</details>", card, flags=re.DOTALL)
        assert details, "no <details> in the card"
        assert "Why this card" in details.group(0)
        for needle in (
            "{card.story}",
            "{DROPPED_WIN_LINE}",
            "{card.drop_if}",
            'k="inactives"',
        ):
            assert needle in details.group(0), needle

    def test_the_face_of_the_card_stays_outside_the_details(self):
        src = _code(SCRIPTS)
        card = src[src.index("export default function GameScriptCard"):]
        card = card[: card.index("function GameHeading")]
        details = re.search(r"<details.*?</details>", card, flags=re.DOTALL)
        assert details
        outside = card.replace(details.group(0), "")
        for needle in (
            "<GameHeading",
            "<LegRow",
            "{NO_COMBINED_CHANCE_LINE}",
            "Ask the market",
        ):
            assert needle in outside, needle
        assert "{card.story}" not in outside

    def test_the_heading_carries_day_time_zone_and_the_sport_tag(self):
        src = _code(SCRIPTS)
        heading = src[src.index("function GameHeading"): src.index("function LegRow")]
        assert "kickoffText(card.kickoff_ms)" in heading
        assert "leagueLabel(card.sport_key)" in heading

    def test_the_list_is_two_columns_from_md_up(self):
        assert "md:grid-cols-2" in _code(SCRIPTS)


class TestTheFiltersCutTheListAndNeverOrderIt:
    def test_the_day_chips_are_today_tomorrow_all(self):
        src = _code(SCRIPTS)
        assert 'type DayChoice = "today" | "tomorrow" | "all";' in src
        for label in ("Today", "Tomorrow", "All"):
            assert f'label: "{label}"' in src

    def test_days_are_calendar_days_in_the_display_zone(self):
        src = _code(SCRIPTS)
        key = src[src.index("function dayKey"): src.index("function nextDayKey")]
        assert "timeZone: DISPLAY_TIME_ZONE" in key
        # Tomorrow is date arithmetic, not "now plus 24 hours".
        assert "Date.UTC(y, m - 1, d + 1)" in src

    def test_league_chips_are_the_leagues_present_and_go_through_the_label(self):
        src = _code(SCRIPTS)
        assert "leaguesPresent" in src and "card.sport_key" in src
        assert "leagueLabel(key)" in src

    def test_the_component_never_sorts_reverses_or_rebuilds_the_order(self):
        src = _code(SCRIPTS)
        for banned in (".sort(", ".toSorted(", ".reverse(", ".toReversed("):
            assert banned not in src, banned

    def test_the_filter_is_a_test_inside_the_map_so_the_server_order_holds(self):
        src = _code(SCRIPTS)
        assert "data.cards.map((card) =>" in src
        assert "matches(card) ?" in src

    def test_the_number_of_hidden_games_is_said(self):
        src = _code(SCRIPTS)
        assert "hidden by this filter" in src
        assert "hiddenCount = cards.length - shownCount" in src


class TestEveryPickCarriesATime:
    def test_a_game_script_leg_row_shows_the_cards_kickoff(self):
        src = _code(SCRIPTS)
        leg = src[src.index("function LegRow"): src.index("function NoCard")]
        assert "kickoffText(kickoffMs)" in leg
        assert "kickoffMs={card.kickoff_ms}" in src

    def test_the_parlay_card_leg_time_is_weekday_time_and_zone_not_bare_hh_mm(self):
        src = _code(CARDS)
        fn = src[src.index("function kickoff("): src.index("function overUnder")]
        assert "formatKickoff(ms)" in fn and "displayZoneLabel(ms)" in fn
        assert "hour12: false" not in fn and '"--:--"' not in fn
        assert "{kickoff(leg.commence_ms)}" in src

    def test_an_unknown_parlay_card_time_says_so(self):
        src = _code(CARDS)
        fn = src[src.index("function kickoff("): src.index("function overUnder")]
        assert 'ms === null) return "time unknown"' in fn

    def test_a_checked_leg_shows_its_time_or_says_it_is_unknown(self):
        src = _code(CHECK)
        result = src[src.index("function CheckedResult"):]
        assert "leg.commence_ms === null" in result
        assert '"time unknown"' in result
        assert "formatKickoff(leg.commence_ms)" in result
        assert "displayZoneLabel(leg.commence_ms)" in result


class TestNothingNewClaimsACombinedChance:
    def test_the_new_files_carry_no_combined_or_ranking_words(self):
        forbidden = re.compile(
            r"joint|combined chance|as if independent|conservative|fair_cost"
            r"|\.sort\(|\.toSorted\(",
            re.IGNORECASE,
        )
        for path in (VIEW_LIB, SWITCH):
            hits = forbidden.findall(_code(path))
            assert not hits, f"{path.name}: {hits}"
