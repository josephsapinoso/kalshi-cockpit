"""A minted /game leg is named from the venue when no local copy holds it.

2026-10-02: four first-half legs on cards Joe bought (#80-#84) were recorded
under their bare tickers. First-half markets are never ingested by discovery,
so `kalshi_markets` has no title for them, and once the 30-minute listing
memory had expired nothing did. `_venue_titles` asks the venue for those
events' markets.

Synthetic payloads in the venue's `markets_for_event` shape; the titles are
invented in Kalshi's phrasing.

What this does NOT establish: that every series the venue lists has a
`title` (an untitled market still falls back to the ticker), or anything
about legs recorded before this landed -- those keep their stored label.
"""

from __future__ import annotations

import inspect

from backend import game_builder


class Api:
    def __init__(self, fail=()):
        self.reads: list[str] = []
        self.fail = set(fail)

    async def markets_for_event(self, event_ticker):
        self.reads.append(event_ticker)
        if event_ticker in self.fail:
            raise RuntimeError("venue down")
        return [
            {"ticker": f"{event_ticker}-AAA", "title": "Alpha wins the 1st half"},
            {"ticker": f"{event_ticker}-BBB", "title": "Beta wins the 1st half"},
        ]


EV1 = "KXNCAAF1H-26JAN01AAABBB"
EV2 = "KXWNBA1HTOTAL-26JAN01AAABBB"


class TestUntitledLegsAreNamedFromTheVenue:
    async def test_only_the_asked_markets_come_back_and_one_read_per_event(self):
        api = Api()
        titles = await game_builder._venue_titles(
            api, [(EV1, f"{EV1}-AAA"), (EV2, f"{EV2}-BBB"), (EV1, f"{EV1}-BBB")]
        )
        assert titles == {
            f"{EV1}-AAA": "Alpha wins the 1st half",
            f"{EV1}-BBB": "Beta wins the 1st half",
            f"{EV2}-BBB": "Beta wins the 1st half",
        }
        assert sorted(api.reads) == sorted([EV1, EV2])

    async def test_nothing_untitled_means_no_venue_read(self):
        api = Api()
        assert await game_builder._venue_titles(api, []) == {}
        assert api.reads == []

    async def test_an_unreadable_event_leaves_its_legs_untitled_and_does_not_raise(self):
        api = Api(fail={EV1})
        titles = await game_builder._venue_titles(
            api, [(EV1, f"{EV1}-AAA"), (EV2, f"{EV2}-AAA")]
        )
        assert titles == {f"{EV2}-AAA": "Alpha wins the 1st half"}

    def test_the_mint_asks_the_venue_before_it_writes_leg_labels(self):
        source = inspect.getsource(game_builder.mint_game_combo)
        ask = source.index("_venue_titles(")
        label = source.index('"label": _leg_label(')
        assert ask < label
