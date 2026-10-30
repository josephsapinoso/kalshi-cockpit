"""Men's college basketball fixtures resolve under `link_event` (#360).

Captured 2026-10-30 by `scripts/capture_team_names.py --league ncaab`: 155 Kalshi
`KXNCAAMBGAME` events against 7 Odds API `basketball_ncaab` fixtures, reduced to
names and kickoffs. Zero odds credits (`x-requests-last: 0`).

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That the alias file is complete, or that most teams link.** The books had
  posted 7 fixtures against Kalshi's 155 (the 11-02/03 slate was not up), so this
  rests on n = 7. 6 linked with NO aliases, 1 (Miami (FL)) needed one. It must
  be re-captured on the full slate; main owns that ticket.
- **Anything about the other 148 events.** They have no book counterpart in the
  capture; they say nothing about names.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.match.linker import (
    ALIAS_DIR,
    MatchCandidate,
    TeamAliases,
    link_event,
    load_aliases,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPORT_KEY = "basketball_ncaab"

#: ticker -> (away, home) of the book fixture it must link to. Read off the
#: capture, each pair checked by eye. A link to ANY other fixture is wrong.
EXPECTED_NO_ALIASES = {
    "KXNCAAMBGAME-26NOV01NDVILL": ("Villanova Wildcats", "Notre Dame Fighting Irish"),
    "KXNCAAMBGAME-26NOV02LIBHP": ("High Point Panthers", "Liberty Flames"),
    "KXNCAAMBGAME-26NOV02MEMISU": ("Memphis Tigers", "Iowa State Cyclones"),
    "KXNCAAMBGAME-26NOV02PURGONZ": ("Purdue Boilermakers", "Gonzaga Bulldogs"),
    "KXNCAAMBGAME-26NOV02OSUBYU": ("Ohio State Buckeyes", "BYU Cougars"),
    "KXNCAAMBGAME-26NOV02ARIZUCLA": ("UCLA Bruins", "Arizona Wildcats"),
}
MIAMI = "KXNCAAMBGAME-26NOV02FLAMIA"
MIAMI_BOOK = ("Florida Gators", "Miami Hurricanes")
#: Same "Ohio" token, a different game (Ohio State @ BYU). Must stay refused.
NOT_A_MATCH = "KXNCAAMBGAME-26NOV02OHIOUSA"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _results(aliases):
    books = _load("ncaab_names_books.json")["fixtures"]
    assert len(books) >= 7, f"only {len(books)} book fixtures captured"
    names = {f["id"]: (f["away_team"], f["home_team"]) for f in books}
    cands = [
        MatchCandidate(
            odds_event_id=f["id"],
            commence_ms=f["commence_ms"],
            home_team=f["home_team"],
            away_team=f["away_team"],
        )
        for f in books
    ]
    out = {}
    for e in _load("ncaab_names_kalshi.json")["events"]:
        r = link_event(
            kalshi_event_ticker=e["event_ticker"],
            kalshi_teams=e["teams"],
            kalshi_commence_ms=e["commence_ms"],
            candidates=cands,
            aliases=aliases,
        )
        out[e["event_ticker"]] = names[r.odds_event_id] if r.matched else None
    return out


class TestCollegeBasketballNamesResolve:
    def test_six_of_seven_available_fixtures_link_with_empty_aliases_and_correctly(self):
        got = _results(TeamAliases(sport_key=SPORT_KEY))
        for ticker, book in EXPECTED_NO_ALIASES.items():
            assert got[ticker] == book, (ticker, got[ticker])
        linked = {t for t, b in got.items() if b is not None}
        assert linked == set(EXPECTED_NO_ALIASES), linked ^ set(EXPECTED_NO_ALIASES)

    def test_miami_fl_needs_its_alias_and_links_correctly_with_it(self):
        assert _results(TeamAliases(sport_key=SPORT_KEY))[MIAMI] is None
        assert _results(load_aliases(SPORT_KEY))[MIAMI] == MIAMI_BOOK

    def test_the_alias_file_exists_and_every_entry_earns_its_place(self):
        path = ALIAS_DIR / f"{SPORT_KEY}.yaml"
        assert path.exists()
        with_file = _results(load_aliases(SPORT_KEY))
        without = _results(TeamAliases(sport_key=SPORT_KEY))
        assert sum(b is not None for b in with_file.values()) == (
            sum(b is not None for b in without.values()) + 1
        )

    def test_a_shared_token_with_a_different_game_stays_refused(self):
        assert _results(load_aliases(SPORT_KEY))[NOT_A_MATCH] is None
