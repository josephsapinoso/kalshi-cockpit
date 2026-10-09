"""The combo-markup `g` rebuild runs on the inspector's own connection, which
returns plain tuples, and a crash inside it is a counted reason, never the
end of the run.

What this establishes: with an event link and market rows present, the
rebuild reaches the ladder without raising (the first live look on
2026-10-09 died there with `TypeError: tuple indices must be integers or
slices, not str`, printing no statistic); and if the ladder does raise, the
ask carries `ladder_error:<Type>` instead of the whole instrument dying.
What it does not establish: that `g` is right -- `tests/test_inspect_live_db_parlays.py`
owns the arithmetic.
"""
from __future__ import annotations

import sqlite3

from backend.store import db
from scripts.inspect_live_db import QUERIES  # noqa: F401 -- puts scripts/ on sys.path
import inspect_live_db_parlays as par  # noqa: E402 -- on sys.path via the line above

EVENT = "KXMLBGAME-26OCT09TORPHI"
SERIES = "KXMLBGAME"
ASOF_MS = 1_790_000_000_000


def _seed(path) -> None:
    conn = db.init_db(path)
    conn.execute(
        "INSERT INTO kalshi_series (series_ticker, first_seen_ms, last_seen_ms) VALUES (?, 1, 1)",
        (SERIES,),
    )
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, series_ticker, title, first_seen_ms, "
        "last_seen_ms) VALUES (?, ?, 'Toronto at Philadelphia', 1, 1)",
        (EVENT, SERIES),
    )
    for team in ("TOR", "PHI"):
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, title, "
            "yes_side_team, market_type, strike, status, first_seen_ms, last_seen_ms) "
            "VALUES (?, ?, ?, ?, ?, 'moneyline', NULL, 'open', 1, 1)",
            (f"{EVENT}-{team}", EVENT, SERIES, f"{team} wins", team),
        )
    conn.execute(
        "INSERT INTO event_links (id, kalshi_event_ticker, odds_event_id, league, method, "
        "commence_skew_ms, linked_ms) VALUES (1, ?, 'odds-1', 'mlb', 'exact_alias_pair', 0, 1)",
        (EVENT,),
    )
    for name, p in (("Toronto Blue Jays", 0.55), ("Philadelphia Phillies", 0.45)):
        conn.execute(
            "INSERT INTO fair_prices (computed_ms, link_id, market, outcome_name, "
            "p_multiplicative, p_additive, p_power, p_shin, p_conservative, book_count, "
            "books_used, anchored_on_sharp, market_width) "
            "VALUES (?, 1, 'h2h', ?, ?, ?, ?, ?, ?, 3, '[\"a\",\"b\",\"c\"]', 1, 0.02)",
            (ASOF_MS - 60_000, name, p + 0.01, p + 0.005, p + 0.002, p + 0.004, p),
        )
    conn.commit()
    conn.close()


class TestTheRebuildSurvivesThePlainConnection:
    def test_market_rows_reach_the_ladder_by_name_and_nothing_raises(self, tmp_path):
        path = tmp_path / "plain.db"
        _seed(path)
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)  # tuples, as live
        try:
            recon = par._CmReconstructor(conn)
            assert recon.parlays is not None, recon.unavailable
            legs = [
                {"event_ticker": EVENT, "market_ticker": f"{EVENT}-TOR", "side": "yes"},
            ]
            g, why = recon.reconstruct(legs, ASOF_MS, 0.55)
            # The ladder ran on dict rows: whatever it concluded about this
            # thin fixture, it did not die indexing a tuple by name.
            assert why is None or not why.startswith("ladder_error"), why
            assert isinstance(recon._markets[EVENT][0], dict)
            assert recon._markets[EVENT][0]["market_type"] == "moneyline"
        finally:
            conn.close()

    def test_a_crash_in_the_ladder_is_a_counted_reason_not_the_end_of_the_run(self, tmp_path):
        path = tmp_path / "plain2.db"
        _seed(path)
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            recon = par._CmReconstructor(conn)

            class Boom:
                CandidatePool = par._CmReconstructor  # never reached

                @staticmethod
                def ladder_candidates(*_a, **_k):
                    raise TypeError("tuple indices must be integers or slices, not str")

            recon.parlays = Boom()
            legs = [{"event_ticker": EVENT, "market_ticker": f"{EVENT}-TOR", "side": "yes"}]
            g, why = recon.reconstruct(legs, ASOF_MS, 0.55)
            assert g is None and why == "ladder_error:TypeError"
        finally:
            conn.close()
