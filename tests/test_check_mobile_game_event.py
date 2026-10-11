"""check_mobile.py --game-event adds /game/<event> to the visited routes (#364)."""

from __future__ import annotations

import re
from pathlib import Path

from scripts import check_mobile

SOURCE = Path(check_mobile.__file__).read_text(encoding="utf-8")


class TestGameEventRoute:
    def test_game_event_adds_the_game_route(self):
        routes = check_mobile.routes_for(game_event="KXNBAGAME-26OCT11LALDEN")
        assert "/game/KXNBAGAME-26OCT11LALDEN" in routes
        assert routes[: len(check_mobile.PAGES)] == check_mobile.PAGES

    def test_omitting_it_changes_nothing(self):
        assert check_mobile.routes_for() == check_mobile.PAGES
        assert not any(r.startswith("/game/") for r in check_mobile.routes_for())

    def test_market_ticker_still_works_alongside(self):
        routes = check_mobile.routes_for("KXFOO-1", "EVT-1")
        assert routes[-2:] == ["/market/KXFOO-1", "/game/EVT-1"]

    def test_pages_is_not_mutated(self):
        before = list(check_mobile.PAGES)
        check_mobile.routes_for("KXFOO-1", "EVT-1")
        assert check_mobile.PAGES == before

    def test_the_cli_option_is_declared_and_wired(self):
        assert '"--game-event"' in SOURCE
        assert re.search(r"routes_for\(args\.market_ticker, args\.game_event\)", SOURCE)
