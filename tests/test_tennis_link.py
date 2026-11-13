"""The pure tennis link steps (#444, design in #439) on captured fixtures only.

Every payload here is a capture (`tests/fixtures/kalshi_tennis_*.json`,
`odds_tennis_*.json`); no negative example is invented. Establishes nothing
about live coverage: three main-tour matches is n = 3, not a rate.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from backend import tennis
from backend.tennis import (
    choose_link,
    classify_series,
    normalise_name,
    price_leg,
    read_event,
    read_event_object,
)

FX = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def kalshi_list_event(name: str) -> dict:
    """List-endpoint captures wrap the event as `events[0]`."""
    return load(name)["events"][0]


def odds_events() -> list[dict]:
    """Every captured sportsbook event across the tour keys, free-list shape."""
    out = list(load("odds_tennis_events_list.json")["events"])
    for f in ("odds_tennis_atp_finals_h2h.json", "odds_tennis_wta_finals_h2h.json"):
        out.extend(load(f)["events"])
    return out


def h2h_rows(event: dict) -> list[dict]:
    """Stored-quote rows: the `h2h` market only (`h2h_lay` is a lay price)."""
    rows = []
    for b in event["bookmakers"]:
        for m in b["markets"]:
            if m["key"] != "h2h":
                continue
            for o in m["outcomes"]:
                rows.append({
                    "bookmaker": b["key"],
                    "outcome_name": o["name"],
                    "price_decimal": o["price"],
                })
    return rows


def wta_event(home: str) -> dict:
    return next(e for e in load("odds_tennis_wta_finals_h2h.json")["events"]
                if e["home_team"] == home)


def read_main(name: str, suffix: str):
    ev = kalshi_list_event(name)
    ticker = f"{ev['event_ticker']}-{suffix}"
    return ev, read_event({"event": ev}, ticker)


class TestLinkRate:
    def test_three_of_three_captured_main_tour_matches_link(self):
        cases = [
            ("kalshi_tennis_event_atp_main.json", "ZVE", "Alexander Zverev"),
            ("kalshi_tennis_event_wta_main.json", "AND", "Mirra Andreeva"),
        ]
        linked = 0
        pool = odds_events()
        for name, suffix, player in cases:
            _, read = read_main(name, suffix)
            assert read.reason is None and read.leg_player == player
            choice = choose_link(read.players, read.occurrence_ms, pool)
            linked += choice.event is not None
        single = load("kalshi_tennis_single_event.json")["response"]
        read = read_event(single, "KXWTAMATCH-26NOV13SABSVI-SAB")
        choice = choose_link(read.players, read.occurrence_ms, pool)
        linked += choice.event is not None
        print(f"tennis link rate: {linked} of 3 captured main-tour matches")
        assert linked == 3

    def test_skew_is_recorded_and_is_the_observed_three_hours(self):
        _, read = read_main("kalshi_tennis_event_atp_main.json", "ZVE")
        choice = choose_link(read.players, read.occurrence_ms, odds_events())
        assert choice.commence_skew_ms == -3 * 3_600_000

    def test_zverev_v_jodar_does_not_link_to_shelton_v_fils(self):
        _, read = read_main("kalshi_tennis_event_atp_main.json", "ZVE")
        shelton = [e for e in odds_events() if e["home_team"] == "Ben Shelton"]
        assert shelton, "capture must contain Shelton v Fils"
        choice = choose_link(read.players, read.occurrence_ms, shelton)
        assert choice.event is None
        assert choice.reason == tennis.NO_SPORTSBOOK_MATCH

    def test_two_events_for_one_pair_inside_the_window_are_ambiguous(self):
        _, read = read_main("kalshi_tennis_event_wta_main.json", "AND")
        real = next(e for e in odds_events()
                    if {e["home_team"], e["away_team"]} == {"Mirra Andreeva", "Karolina Muchova"})
        twin = dict(real, id="not-the-same-event")
        choice = choose_link(read.players, read.occurrence_ms, [real, twin])
        assert choice.reason == tennis.AMBIGUOUS_MATCH and choice.event is None

    def test_a_rematch_days_apart_is_outside_the_window(self):
        _, read = read_main("kalshi_tennis_event_wta_main.json", "AND")
        real = next(e for e in odds_events()
                    if {e["home_team"], e["away_team"]} == {"Mirra Andreeva", "Karolina Muchova"})
        later = dict(real, commence_time="2026-11-20T20:00:00Z")
        choice = choose_link(read.players, read.occurrence_ms, [later])
        assert choice.reason == tennis.NO_SPORTSBOOK_MATCH

    def test_a_shortened_first_name_is_refused_not_guessed(self):
        _, read = read_main("kalshi_tennis_event_atp_main.json", "ZVE")
        short = ("Alex Zverev", read.players[1])
        choice = choose_link(short, read.occurrence_ms, odds_events())
        assert choice.reason == tennis.NO_SPORTSBOOK_MATCH


class TestNameMatching:
    def test_normalisation_strips_accents_case_hyphens_and_spaces(self):
        assert normalise_name("  Karolína  MUCHOVÁ ") == normalise_name("Karolina Muchova")
        assert normalise_name("Anna-Lena Friedsam") == normalise_name("Anna Lena  Friedsam")

    def test_link_is_independent_of_home_away_order(self):
        _, read = read_main("kalshi_tennis_event_wta_main.json", "AND")
        real = next(e for e in odds_events()
                    if {e["home_team"], e["away_team"]} == {"Mirra Andreeva", "Karolina Muchova"})
        flipped = dict(real, home_team=real["away_team"], away_team=real["home_team"])
        a = choose_link(read.players, read.occurrence_ms, [real])
        b = choose_link(read.players, read.occurrence_ms, [flipped])
        assert a.event is not None and b.event is not None

    def test_betfair_lists_muchova_first_and_the_price_still_lands_on_andreeva(self):
        ev = wta_event("Mirra Andreeva")
        betfair = [r for r in h2h_rows(ev) if r["bookmaker"] == "betfair_ex_eu"]
        assert betfair[0]["outcome_name"] == "Karolina Muchova"  # the capture's order
        andreeva = price_leg(h2h_rows(ev), ("Mirra Andreeva", "Karolina Muchova"),
                             "yes", "Mirra Andreeva")
        muchova = price_leg(h2h_rows(ev), ("Mirra Andreeva", "Karolina Muchova"),
                            "yes", "Karolina Muchova")
        assert andreeva.chance > 0.5 > muchova.chance
        assert andreeva.chance + muchova.chance <= 1.0 + 1e-9

    def test_name_order_of_the_kalshi_pair_does_not_change_the_chance(self):
        ev = wta_event("Mirra Andreeva")
        a = price_leg(h2h_rows(ev), ("Mirra Andreeva", "Karolina Muchova"), "yes", "Mirra Andreeva")
        b = price_leg(h2h_rows(ev), ("Karolina Muchova", "Mirra Andreeva"), "yes", "Mirra Andreeva")
        assert a.chance == b.chance


class TestSeriesClassification:
    def test_atp_and_wta_match_winner_are_priced(self):
        assert classify_series("KXATPMATCH-26NOV15ZVEJOD-ZVE").tier == "atp"
        assert classify_series("KXWTAMATCH-26NOV13ANDMUC-AND").tier == "wta"

    def test_challenger_markets_from_the_captures_are_refused_as_no_sportsbook(self):
        for f in ("kalshi_tennis_event_atp_challenger.json",
                  "kalshi_tennis_event_wta_challenger.json"):
            for m in kalshi_list_event(f)["markets"]:
                got = classify_series(m["ticker"])
                assert (got.tier, got.reason) == (None, tennis.NO_SPORTSBOOK_TOURNAMENT)

    def test_itf_and_doubles_events_in_the_captured_collection_are_refused(self):
        coll = load("kalshi_tennis_mve_collection.json")["multivariate_contract"]
        tickers = coll["associated_event_tickers"]
        itf = [t for t in tickers if t.startswith("KXITFMATCH-") or t.startswith("KXITFWMATCH-")]
        doubles = [t for t in tickers if t.startswith("KXATPDOUBLES-")]
        assert itf and doubles
        for t in itf + doubles:
            assert classify_series(t).reason == tennis.NO_SPORTSBOOK_TOURNAMENT

    def test_a_series_that_merely_starts_with_a_priced_one_is_not_priced(self):
        assert classify_series("KXATPMATCHES-26NOV15ZVEJOD-ZVE").tier is None
        assert classify_series("KXATPSETWINNER-26NOV15ZVEJOD-1").reason == tennis.NOT_MATCH_WINNER

    def test_a_non_game_scope_is_refused(self):
        ev = copy.deepcopy(kalshi_list_event("kalshi_tennis_event_atp_main.json"))
        ev["product_metadata"]["competition_scope"] = "Set"
        got = read_event_object(ev, ev["markets"][0]["ticker"])
        assert got.reason == tennis.NOT_MATCH_WINNER


class TestEventReader:
    SINGLE = "KXWTAMATCH-26NOV13SABSVI-SAB"

    def test_reads_event_markets_not_the_empty_top_level_markets(self):
        payload = load("kalshi_tennis_single_event.json")["response"]
        assert payload["markets"] == []
        got = read_event(payload, self.SINGLE)
        assert got.reason is None
        assert got.players == ("Aryna Sabalenka", "Elina Svitolina")
        assert got.leg_player == "Aryna Sabalenka"

    def _mutated(self, fn):
        ev = copy.deepcopy(kalshi_list_event("kalshi_tennis_event_atp_main.json"))
        fn(ev)
        return read_event_object(ev, ev["markets"][0]["ticker"])

    def test_refuses_each_unreadable_shape(self):
        cases = {
            "one market": lambda e: e["markets"].pop(),
            "three markets": lambda e: e["markets"].append(
                dict(copy.deepcopy(e["markets"][0]), ticker="KXATPMATCH-26NOV15ZVEJOD-XXX")),
            "not mutually exclusive": lambda e: e.update(mutually_exclusive=False),
            "inactive market": lambda e: e["markets"][1].update(status="closed"),
            "unequal occurrence": lambda e: e["markets"][1].update(
                occurrence_datetime="2026-11-15T17:00:00Z"),
            "same competitor": lambda e: e["markets"][1].update(
                custom_strike=copy.deepcopy(e["markets"][0]["custom_strike"])),
        }
        for label, fn in cases.items():
            got = self._mutated(fn)
            assert got.reason == tennis.UNREADABLE_EVENT, label

    def test_leg_ticker_must_match_exactly(self):
        payload = load("kalshi_tennis_single_event.json")["response"]
        got = read_event(payload, "KXWTAMATCH-26NOV13SABSVI-SA")
        assert got.reason == tennis.UNREADABLE_EVENT
        got = read_event(payload, "KXWTAMATCH-26NOV13SABSVI-SVI")
        assert got.leg_player == "Elina Svitolina"


class TestPricing:
    NAMES = ("Jessica Pegula", "Mirra Andreeva")

    def test_one_sharp_book_does_not_anchor_pegula_v_andreeva(self):
        rows = h2h_rows(wta_event("Jessica Pegula"))
        assert {r["bookmaker"] for r in rows} & tennis_sharp() == {"betfair_ex_eu"}
        got = price_leg(rows, self.NAMES, "yes", "Mirra Andreeva")
        assert got.anchored_on_sharp is False
        assert len(got.books_used) == 5

    def test_two_sharp_books_do_anchor_sabalenka_v_svitolina(self):
        ev = load("odds_tennis_event_h2h.json")["event"]
        got = price_leg(h2h_rows(ev), ("Aryna Sabalenka", "Elina Svitolina"),
                        "yes", "Aryna Sabalenka")
        assert got.anchored_on_sharp is True
        assert set(got.books_used) <= tennis_sharp() and len(got.books_used) >= 2

    def test_no_leg_is_the_other_players_side_and_one_minus_max_yes(self):
        rows = h2h_rows(wta_event("Jessica Pegula"))
        yes = price_leg(rows, self.NAMES, "yes", "Mirra Andreeva")
        no = price_leg(rows, self.NAMES, "no", "Mirra Andreeva")
        pegula_yes = price_leg(rows, self.NAMES, "yes", "Jessica Pegula")
        assert no.chance == pegula_yes.chance
        max_yes = _max_method(rows, "Mirra Andreeva", self.NAMES)
        assert abs(no.chance - (1 - max_yes)) < 1e-12
        # the capture's methods genuinely disagree, so 1 - min(YES) is a different number
        assert no.chance < 1 - yes.chance - 1e-6

    def test_all_four_ATP_finals_events_are_unquoted_and_refuse(self):
        for ev in load("odds_tennis_atp_finals_h2h.json")["events"]:
            got = price_leg(h2h_rows(ev), (ev["home_team"], ev["away_team"]),
                            "yes", ev["home_team"])
            assert got.chance is None and got.reason == tennis.NO_TWO_SIDED_BOOK

    def test_a_one_sided_book_is_dropped_and_counted(self):
        ev = load("odds_tennis_event_h2h.json")["event"]
        rows = [r for r in h2h_rows(ev)
                if not (r["bookmaker"] == "fanduel" and r["outcome_name"] == "Elina Svitolina")]
        got = price_leg(rows, ("Aryna Sabalenka", "Elina Svitolina"), "yes", "Aryna Sabalenka")
        assert got.books_dropped == {"fanduel": "one_sided"}

    def test_unknown_side_and_unknown_player_resolve_to_none(self):
        rows = h2h_rows(wta_event("Jessica Pegula"))
        assert price_leg(rows, self.NAMES, "maybe", "Mirra Andreeva").chance is None
        assert price_leg(rows, self.NAMES, "yes", "Someone Else").chance is None


# -- helpers for the pricing claims ------------------------------------------

def tennis_sharp() -> set[str]:
    from backend.runner import SHARP_BOOKS
    return set(SHARP_BOOKS)


def _max_method(rows, player, names) -> float:
    """Highest of the four methods for `player`, from the same book set price_leg uses."""
    from backend.core.devig import consensus_devig
    by_book: dict[str, dict[str, float]] = {}
    for r in rows:
        by_book.setdefault(r["bookmaker"], {})[r["outcome_name"]] = r["price_decimal"]
    quotes = {b: [q[names[0]], q[names[1]]] for b, q in by_book.items() if len(q) == 2}
    cons, _ = consensus_devig(list(names), quotes, sharp_books=None)
    i = list(names).index(player)
    return max(v[i] for v in cons.all_methods().values())
