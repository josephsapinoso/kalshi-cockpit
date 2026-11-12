"""Men's college basketball fixtures resolve under `link_event` (#360, #401).

Re-captured 2026-11-12 by `scripts/capture_team_names.py --league ncaab` on the
first full slate the books had posted: 177 Kalshi `KXNCAAMBGAME` events against
62 Odds API `basketball_ncaab` fixtures, reduced to names and kickoffs. Zero
odds credits (`x-requests-last: 0`). (The 2026-10-30 capture this replaces had
7 book fixtures.)

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That the alias file is complete.** 62 fixtures is one night; a school
  absent from the file and from this capture is unread, not proven fine.
- **That every link is right by name.** The nine alias-earned links are pinned
  pair by pair, read off the capture; the other 52 are held only to "each book
  fixture is used once" and "every link sits at Kalshi's 3-hour offset".
- **Anything about the 115 events with no book fixture at their kickoff or none
  sharing a side.** They say nothing about names.
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

#: ticker -> (away, home) of the book fixture it must link to WITH the alias
#: file, and that it fails to link to without it. Read off the capture.
ALIAS_EARNED = {
    "KXNCAAMBGAME-26NOV12CSBWIU": ("CSU Bakersfield Roadrunners", "Western Illinois Leathernecks"),
    "KXNCAAMBGAME-26NOV12LMDTOWS": ("Loyola (MD) Greyhounds", "Towson Tigers"),
    "KXNCAAMBGAME-26NOV12WMUPFW": ("Western Michigan Broncos", "Fort Wayne Mastodons"),
    "KXNCAAMBGAME-26NOV12SOUMINN": ("Southern Jaguars", "Minnesota Golden Gophers"),
    "KXNCAAMBGAME-26NOV13UNAMIA": ("North Alabama Lions", "Miami Hurricanes"),
    "KXNCAAMBGAME-26NOV13HARVGW": ("Harvard Crimson", "GW Revolutionaries"),
    "KXNCAAMBGAME-26NOV13MSMVT": ("Mt. St. Mary's Mountaineers", "Virginia Tech Hokies"),
    "KXNCAAMBGAME-26NOV13SEMOMTU": ("SE Missouri St Redhawks", "Middle Tennessee Blue Raiders"),
    "KXNCAAMBGAME-26NOV13ULMASU": ("UL Monroe Warhawks", "Arizona St Sun Devils"),
}
#: "Tennessee" is a token prefix of both book names; an alias cannot remove a
#: prefix match, so this pair has no bijection and stays refused.
TENNESSEE = "KXNCAAMBGAME-26NOV13TNSTTENN"
LINKED_WITH_FILE = 61
LINKED_WITHOUT = 52
#: Kalshi's `occurrence_datetime` sits three hours after the book's kickoff on
#: every linked game; the linker's tolerance is four.
BOOK_MINUS_KALSHI_MS = -3 * 3_600_000


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _results(aliases):
    books = _load("ncaab_names_books.json")["fixtures"]
    assert len(books) >= 60, f"only {len(books)} book fixtures captured"
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
        if r.matched:
            SKEWS[e["event_ticker"]] = r.commence_skew_ms
    return out


SKEWS: dict[str, int] = {}


class TestCollegeBasketballNamesResolve:
    def test_the_alias_file_links_exactly_the_nine_it_was_written_for(self):
        with_file = _results(load_aliases(SPORT_KEY))
        without = _results(TeamAliases(sport_key=SPORT_KEY))
        changed = {t for t in with_file if with_file[t] != without[t]}
        assert changed == set(ALIAS_EARNED)
        for ticker, book in ALIAS_EARNED.items():
            assert without[ticker] is None, ticker
            assert with_file[ticker] == book, (ticker, with_file[ticker])

    def test_link_counts_with_and_without_the_file(self):
        assert sum(b is not None for b in _results(load_aliases(SPORT_KEY)).values()) == LINKED_WITH_FILE
        assert sum(b is not None for b in _results(TeamAliases(sport_key=SPORT_KEY)).values()) == LINKED_WITHOUT

    def test_no_book_fixture_is_claimed_twice(self):
        linked = [b for b in _results(load_aliases(SPORT_KEY)).values() if b is not None]
        assert len(linked) == len(set(linked))

    def test_every_link_sits_at_kalshis_three_hour_offset(self):
        """A link at any other skew is a different game sharing a name, or a
        drift toward the 4-hour tolerance edge (#401 item 3)."""
        SKEWS.clear()
        _results(load_aliases(SPORT_KEY))
        assert SKEWS and set(SKEWS.values()) == {BOOK_MINUS_KALSHI_MS}

    def test_tennessee_st_at_tennessee_stays_refused(self):
        assert _results(load_aliases(SPORT_KEY))[TENNESSEE] is None

    def test_the_alias_file_exists(self):
        assert (ALIAS_DIR / f"{SPORT_KEY}.yaml").exists()
