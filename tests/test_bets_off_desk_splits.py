"""#423 / #355: Your bets splits the settled combinations by leg count and by
same-game versus cross-game, and offers the same views for only the
combinations bought off the desk.

Every fixture is synthetic (round invented prices on made-up tickers and
real-shaped but invented fixtures); nothing is, or may be, copied from the
operator's record.

What this establishes
---------------------
- The two splits serve with their n, won, expected, staked and net; a cell
  under five expected wins or losses is `too_few` with no range.
- The order is fixed: leg count ascending, same_game before cross_game,
  whatever the results (flipping every result moves no row).
- A combination with any leg whose game cannot be read is `unclassified`,
  never guessed into either cell; one with no leg list stays `no_leg_list`.
- "Off the desk" is exactly the combinations with no `parlay_positions` row;
  it changes the population, never the order or the rule.
- The page renders both splits through the leg-count row component and carries
  the two-state toggle.

What it does NOT establish
--------------------------
That the page draws (`next build` and a browser say that), or that any shape
means anything: these are counts and expected-at-the-price, not a finding.
"""

from __future__ import annotations

from pathlib import Path

from backend import bets, hedge
from backend.store import db

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "frontend" / "src" / "app" / "bets" / "page.tsx"
STRIP = REPO / "frontend" / "src" / "components" / "ShapeStrip.tsx"

_N = [0]

# Real-shaped event tickers for two distinct games in two leagues.
NFL_A = "KXNFLGAME-26SEP13ATLPIT"
NFL_A_SPREAD = "KXNFLSPREAD-26SEP13ATLPIT"
NFL_B = "KXNFLGAME-26SEP13DENKC"
MLB_A = "KXMLBGAME-26SEP131840BOSMIA"


def _settle(conn, *, price, won, contracts=2.0):
    _N[0] += 1
    n = _N[0]
    ticker = f"KXMVESYNTHETIC-SHARD1-S{n:016d}-AAAAAAAAAAA"
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
        "position_first_seen_ms) VALUES (?, 'KXSYNTH', ?, ?, 'yes', ?, ?, 0, NULL)",
        (ticker, "yes" if won else "no", 1_000 + n, contracts, price),
    )
    return n, ticker


def _on_desk(conn, *, price, won, events, league="Pro Football"):
    n, ticker = _settle(conn, price=price, won=won)
    hedge.record_position(
        conn, now_ms=1_000 + n, source="kalshi_combo", label="synthetic",
        stake_tenths=1000, return_tenths=5000, combo_ticker=ticker,
        legs=[
            {"ticker": f"{ev}-LEG{n}{i}", "event_ticker": ev, "side": "yes",
             "label": f"leg {i}", "league": league}
            for i, ev in enumerate(events)
        ],
    )
    conn.commit()
    return ticker


def _off_desk(conn, *, price, won, events, league="Pro Football"):
    """A combination bought off the desk: a settlement, legs from the venue's
    own read, and NO `parlay_positions` row."""
    n, ticker = _settle(conn, price=price, won=won)
    for i, ev in enumerate(events):
        conn.execute(
            "INSERT INTO venue_combo_legs (combo_ticker, leg_index, ticker, "
            "event_ticker, side, label, league, read_ms, venue_result, "
            "ask_at_purchase_tenths) VALUES (?, ?, ?, ?, 'yes', ?, ?, 1, 'yes', 500)",
            (ticker, i, f"{ev}-LEG{n}{i}", ev, f"venue leg {i}", league),
        )
    conn.commit()
    return ticker


def _build(tmp_path, *, flip=False):
    """12 same-game 2-leg combos at 50c (enough expected each side for a
    range), 2 cross-game 3-leg combos (too few), one 2-leg combo whose games
    cannot be read, one with no leg list. Half on the desk, half off."""
    conn = db.init_db(tmp_path / ("flip.db" if flip else "plain.db"))
    _settled_desk_legs = lambda: conn.execute(  # noqa: E731
        "UPDATE parlay_position_legs SET outcome = 'won', resolved_ms = 5, resolved_source = 'venue', "
        "ask_at_purchase_tenths = 500"
    )
    results = [bool(i % 2) != flip for i in range(12)]
    for i, w in enumerate(results):
        make = _on_desk if i % 2 == 0 else _off_desk
        make(conn, price=500, won=w, events=[NFL_A, NFL_A_SPREAD])
    # Inserted before the 2-leg rows' siblings on purpose: order must come
    # from the rule, not from insertion order.
    _off_desk(conn, price=100, won=flip, events=[NFL_A, NFL_B, MLB_A])
    _on_desk(conn, price=100, won=flip, events=[NFL_A, NFL_B, MLB_A])
    _off_desk(conn, price=300, won=not flip, events=["KXSYNTHEV1", NFL_A])
    _settle(conn, price=400, won=True)  # no legs recorded anywhere
    # The desk's own legs settled too, so the by-leg-kind "all" block holds
    # them and the off-desk block must not.
    _settled_desk_legs()
    conn.commit()
    return conn


def _labels(shape):
    return (
        [r["legs"] for r in shape["leg_counts"]],
        [c["split"] for c in shape["same_game_split"]["cells"]],
    )


def test_the_leg_count_and_same_game_splits_serve_with_their_n_in_fixed_order(
    tmp_path,
):
    shape = bets.bets_record(_build(tmp_path))["by_shape"]

    # Leg count ascending, same_game before cross_game.
    assert _labels(shape) == ([2, 3], ["same_game", "cross_game"])
    legs2, legs3 = shape["leg_counts"]
    assert (legs2["n"], legs2["won"]) == (13, 7)
    assert (legs3["n"], legs3["won"]) == (2, 0)

    same, cross = shape["same_game_split"]["cells"]
    # 12 combos at 50c, 6 won: n, won, expected at the price paid.
    assert (same["n"], same["won"], same["expected"]) == (12, 6, 6.0)
    assert same["too_few"] is False
    assert same["range_low"] is not None and same["range_high"] is not None
    assert same["staked_tenths"] == 12 * 2 * 500
    # Two combos at 10c expect 0.2 wins: counts, no range.
    assert (cross["n"], cross["won"], cross["expected"]) == (2, 0, 0.2)
    assert cross["too_few"] is True
    assert cross["range_low"] is None and cross["range_high"] is None
    # A leg whose game cannot be read is counted aside, never guessed.
    assert shape["same_game_split"]["unclassified"]["n"] == 1
    # No leg list stays its own count.
    assert shape["no_leg_list"]["n"] == 1

    # The cells reconcile: classified + unclassified == the combos with legs.
    assert (
        same["n"] + cross["n"] + shape["same_game_split"]["unclassified"]["n"]
        == legs2["n"] + legs3["n"]
    )

    # Whatever the results: every result flipped moves no row.
    flipped = bets.bets_record(_build(tmp_path, flip=True))["by_shape"]
    assert _labels(flipped) == _labels(shape)
    assert [c["n"] for c in flipped["same_game_split"]["cells"]] == [12, 2]


def test_the_off_desk_filter_changes_the_population_not_the_order(tmp_path):
    record = bets.bets_record(_build(tmp_path))
    shape = record["by_shape"]
    off = shape["off_desk"]

    # Same shape, same fixed order, as the unfiltered views.
    assert set(off) == {"leg_counts", "same_game_split", "no_leg_list"}
    assert _labels(off) == _labels(shape)

    # The population: off-desk only. 6 of the 12 same-game combos were bought
    # off the desk, one of the two 3-leg ones, and the unreadable one.
    assert [r["n"] for r in off["leg_counts"]] == [7, 1]
    assert [c["n"] for c in off["same_game_split"]["cells"]] == [6, 1]
    assert off["same_game_split"]["unclassified"]["n"] == 1
    # The combination with no leg list has no position either: off the desk.
    assert off["no_leg_list"]["n"] == 1
    # A 6-combo cell at 50c expects 3 wins: too few, so no range.
    assert off["same_game_split"]["cells"][0]["too_few"] is True
    assert off["same_game_split"]["cells"][0]["range_low"] is None

    # The unfiltered keys keep meaning "all" (more combos than the subset).
    assert shape["leg_counts"][0]["n"] > off["leg_counts"][0]["n"]

    # Flipping every result moves no row of the filtered views either.
    flipped = bets.bets_record(_build(tmp_path, flip=True))["by_shape"]["off_desk"]
    assert _labels(flipped) == _labels(off)

    # by_leg_kind: the same block over the off-desk legs only, same order.
    kinds = record["by_leg_kind"]
    assert set(kinds["off_desk"]) == {"kind_order", "leagues"}
    assert kinds["off_desk"]["kind_order"] == kinds["kind_order"]
    off_settled = 0
    for league in kinds["off_desk"]["leagues"]:
        for block in league["kinds"]:
            off_settled += block["settled"]
    all_settled = 0
    for league in kinds["leagues"]:
        for block in league["kinds"]:
            all_settled += block["settled"]
    # Off the desk: 6 two-leg + 1 three-leg + 1 two-leg combos = 17 legs. On
    # the desk: 6 two-leg + 1 three-leg = 15 settled legs. "All" holds both.
    assert off_settled == 17
    assert all_settled == 32


def test_a_desk_position_is_never_read_as_off_the_desk(tmp_path):
    conn = db.init_db(tmp_path / "desk.db")
    ticker = _on_desk(conn, price=500, won=True, events=[NFL_A, NFL_B])
    # A stray venue read for a ticker the desk holds must not count it twice
    # or move it into the off-desk view.
    conn.execute(
        "INSERT INTO venue_combo_legs (combo_ticker, leg_index, ticker, "
        "event_ticker, side, label, read_ms) VALUES (?, 0, 'X-1', ?, 'yes', 'x', 1)",
        (ticker, NFL_A),
    )
    conn.commit()
    shape = bets.bets_record(conn)["by_shape"]
    assert [r["n"] for r in shape["leg_counts"]] == [1]
    assert shape["leg_counts"][0]["legs"] == 2
    assert shape["off_desk"]["leg_counts"] == []


def test_range_count_counts_the_population_the_page_shows(tmp_path):
    record = bets.bets_record(_build(tmp_path))
    everything = bets.count_ranges(record)
    off_view = bets.count_ranges(record, "off_desk")
    assert record["range_count"] == everything
    assert record["range_count_off_desk"] == off_view
    # The all view has the 12-combo same-game cell's range and the 13-combo
    # 2-leg row's; the off-desk view has neither (6 and 7 combos at 50c).
    assert everything > off_view
    fewer = {**record, "by_shape": {**record["by_shape"], "same_game_split": {
        "cells": [{"split": "same_game", "range_low": None, "range_high": None}],
    }}}
    assert bets.count_ranges(fewer) == everything - 1


class TestPageRendersBothSplitsAndTheToggle:
    def test_the_same_game_split_uses_the_leg_count_row_component(self):
        src = STRIP.read_text(encoding="utf-8")
        assert "same_game_split" in src
        # Both splits go through the one CellText component, so the too-few
        # wording and the no-range rule are the leg-count rows' own.
        assert '{row.legs} legs: <CellText cell={row} noun="combos" />' in src
        assert 'view.same_game_split.cells.map' in src
        assert '<CellText cell={cell} noun="combos" />' in src
        assert 'k="same_game"' in src and 'k="cross_game"' in src
        # The population toggle picks the view; it never re-orders it.
        assert "data.off_desk" in src
        # Never sorted in the browser.
        assert ".sort(" not in src

    def test_the_page_carries_a_two_state_toggle(self):
        src = PAGE.read_text(encoding="utf-8")
        assert "All combinations" in src
        assert "Bought off the desk" in src
        assert "off_desk" in src
        assert "searchParams" in src
        # The toggle's choice reaches the strip, the leg-kind block and the
        # range count together.
        assert "population" in src
        assert "range_count_off_desk" in src


class TestEachRowSaysWhetherTheDeskHoldsIt:
    """#425: the off-desk views were aggregates only, so nothing reading the
    payload could say WHICH tickets they counted."""

    def test_a_row_carries_the_flag_the_off_desk_views_count_by(self, tmp_path):
        conn = _build(tmp_path)
        record = bets.bets_record(conn)
        off = [b for b in record["bets"] if b["on_desk"] is False]
        on = [b for b in record["bets"] if b["on_desk"] is True]
        assert len(on) == 7 and len(off) == 9
        view = record["by_shape"]["off_desk"]
        counted = (
            sum(r["n"] for r in view["leg_counts"])
            + view["no_leg_list"]["n"]
        )
        assert counted == len(off)

    def test_a_desk_position_with_a_stray_venue_read_is_still_on_the_desk(self, tmp_path):
        conn = db.init_db(tmp_path / "stray.db")
        ticker = _on_desk(conn, price=500, won=True, events=[NFL_A, NFL_B])
        conn.execute(
            "INSERT INTO venue_combo_legs (combo_ticker, leg_index, ticker, "
            "event_ticker, side, label, read_ms) VALUES (?, 0, 'X-1', ?, 'yes', 'x', 1)",
            (ticker, NFL_A),
        )
        conn.commit()
        (bet,) = bets.bets_record(conn)["bets"]
        assert bet["on_desk"] is True

    def test_a_single_carries_no_flag(self, tmp_path):
        conn = db.init_db(tmp_path / "single.db")
        conn.execute(
            "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
            "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
            "position_first_seen_ms) VALUES ('KXNFLGAME-26SEP13ATLPIT-ATL', "
            "'KXNFLGAME-26SEP13ATLPIT', 'yes', 1000, 'yes', 1.0, 500, 0, NULL)"
        )
        conn.commit()
        (bet,) = bets.bets_record(conn)["bets"]
        assert bet["on_desk"] is None
