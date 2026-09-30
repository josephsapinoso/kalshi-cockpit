"""A settled combination leads with its legs, not "Combination bet" (#254).

WHAT THIS ESTABLISHES
----------------------
(i)   A combination whose legs the desk wrote down -- on the lookup that
      minted its ticker, or on a recorded position -- is served with `legs`
      in leg order, and the page's `betLead` joins their labels with " + ".
      The combo ticker and its two legs come from the captured
      `tests/fixtures/combo_lookup_response.json` (a real venue payload);
      the desk's own labels are derived from that payload's `no_sub_title`.
(ii)  A combination whose legs cannot be read -- no lookup, a lookup blob
      with a blank label (ticker stood in), or an unparseable blob -- is
      served `legs = None` and `betLead` still says "Combination bet".
      Never a partial list: one unreadable leg drops the whole row's legs.
(iii) A single never carries `legs`; it carries Kalshi's market title when
      discovery holds one.
(iv)  The legs read is bounded by the returned window.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- Rendering, and how a hand-typed slip's labels read (they are the
  operator's words, used as typed).
- That the desk's labels are side-complete for every market type; a leg's
  `side` is served but the lead shows the label alone.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend import bets, hedge
from backend.store import db

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads(
    (ROOT / "tests" / "fixtures" / "combo_lookup_response.json").read_text(
        encoding="utf-8"
    )
)
MARKET = FIXTURE["market"]
COMBO = MARKET["ticker"]
LEGS = MARKET["mve_selected_legs"]
# "yes TEN Titans,yes BUF Bills" -> "TEN Titans to win", "BUF Bills to win"
LABELS = [
    part.split(" ", 1)[1] + " to win"
    for part in MARKET["no_sub_title"].split(",")
]
PAGE = (ROOT / "frontend" / "src" / "app" / "bets" / "page.tsx").read_text(
    encoding="utf-8"
).replace("\r\n", "\n")


def _settle(conn, ticker):
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
        "position_first_seen_ms) VALUES (?, 'E', 'yes', 1000, 'yes', 2.0, "
        "400, 20, NULL)",
        (ticker,),
    )
    conn.commit()


def _lookup(conn, *, blob, ticker=COMBO, status="priced"):
    conn.execute(
        "INSERT INTO parlay_lookups (requested_ms, card_key, stake_cents, "
        "selected_legs, status, minted_market_ticker) "
        "VALUES (1, 'safe', 100, ?, ?, ?)",
        (blob if isinstance(blob, str) else json.dumps(blob), status, ticker),
    )
    conn.commit()


def _blob(labels):
    return [
        {
            "event_ticker": leg["event_ticker"],
            "market_ticker": leg["market_ticker"],
            "side": leg["side"],
            **({"label": label} if label is not None else {}),
        }
        for leg, label in zip(LEGS, labels)
    ]


def _bet(conn, ticker=COMBO):
    return next(
        b for b in bets.bets_record(conn)["bets"] if b["ticker"] == ticker
    )


def _lead(bet) -> str:
    """betLead, as the page computes it, for the two branches under test."""
    if bet["kind"] == "combo" and bet["legs"]:
        return " + ".join(leg["label"] for leg in bet["legs"])
    return "Combination bet"


class TestLegsLeadTheRow:
    def test_a_lookup_minted_combo_lists_its_legs_from_the_real_fixture(
        self, tmp_path
    ):
        assert len(LEGS) == 2 and all(LABELS)
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn, COMBO)
        _lookup(conn, blob=_blob(LABELS))
        bet = _bet(conn)
        assert [leg["label"] for leg in bet["legs"]] == LABELS
        assert _lead(bet) == " + ".join(LABELS)
        assert _lead(bet).startswith(LABELS[0])

    def test_a_recorded_position_wins_and_keeps_leg_order(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn, COMBO)
        _lookup(conn, blob=_blob(["stale one", "stale two"]))
        hedge.record_position(
            conn, now_ms=5, source="kalshi_combo", label="mine",
            stake_tenths=1000, return_tenths=4000, combo_ticker=COMBO,
            legs=[
                {"ticker": leg["market_ticker"], "side": leg["side"],
                 "label": label, "event_ticker": leg["event_ticker"]}
                for leg, label in zip(LEGS, LABELS)
            ],
        )
        assert [leg["label"] for leg in _bet(conn)["legs"]] == LABELS


    def test_two_positions_on_one_ticker_do_not_merge_their_legs(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn, COMBO)
        for stamp, labels in ((5, ["old a", "old b"]), (6, LABELS)):
            hedge.record_position(
                conn, now_ms=stamp, source="kalshi_combo", label="mine",
                stake_tenths=1000, return_tenths=4000, combo_ticker=COMBO,
                legs=[
                    {"ticker": leg["market_ticker"], "side": leg["side"],
                     "label": label, "event_ticker": leg["event_ticker"]}
                    for leg, label in zip(LEGS, labels)
                ],
            )
        assert [leg["label"] for leg in _bet(conn)["legs"]] == LABELS


class TestUnreadableLegsNeverGuess:
    def test_no_lookup_and_no_position_says_combination_bet(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn, COMBO)
        bet = _bet(conn)
        assert bet["legs"] is None
        assert _lead(bet) == "Combination bet"

    def test_a_blob_with_a_missing_label_is_not_shown_as_tickers(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn, COMBO)
        _lookup(conn, blob=_blob([LABELS[0], None]))
        bet = _bet(conn)
        assert bet["legs"] is None
        assert _lead(bet) == "Combination bet"

    def test_a_blank_label_drops_the_whole_row_not_one_leg(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn, COMBO)
        _lookup(conn, blob=_blob([LABELS[0], "  "]))
        assert _bet(conn)["legs"] is None

    def test_a_position_leg_labelled_with_its_ticker_is_not_words(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn, COMBO)
        hedge.record_position(
            conn, now_ms=5, source="kalshi_combo", label="mine",
            stake_tenths=1000, return_tenths=4000, combo_ticker=COMBO,
            legs=[
                {"ticker": LEGS[0]["market_ticker"], "side": "yes",
                 "label": LABELS[0]},
                {"ticker": LEGS[1]["market_ticker"], "side": "yes",
                 "label": LEGS[1]["market_ticker"]},
            ],
        )
        bet = _bet(conn)
        assert bet["legs"] is None
        assert _lead(bet) == "Combination bet"

    def test_an_unparseable_blob_says_combination_bet(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn, COMBO)
        _lookup(conn, blob="{not json")
        assert _lead(_bet(conn)) == "Combination bet"

    def test_a_refused_lookup_does_not_supply_legs(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn, COMBO)
        _lookup(conn, blob=_blob(LABELS), status="refused")
        assert _bet(conn)["legs"] is None


class TestSingles:
    def test_a_single_carries_its_title_and_no_legs(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        ticker = "KXNFLGAME-26AUG23SEATEN-TEN"
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, title, first_seen_ms, "
            "last_seen_ms) VALUES (?, 'Seattle at Tennessee Winner?', 0, 0)",
            (ticker,),
        )
        conn.commit()
        _settle(conn, ticker)
        bet = _bet(conn, ticker)
        assert bet["legs"] is None
        assert bet["market_title"] == "Seattle at Tennessee Winner?"

    def test_a_combo_never_carries_a_single_title(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn, COMBO)
        assert _bet(conn)["market_title"] is None


class TestWindowBound:
    def test_legs_are_read_for_the_returned_window_only(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn, COMBO)
        _lookup(conn, blob=_blob(LABELS))
        seen: list[list[str]] = []
        real = bets._legs_by_ticker

        def spy(c, tickers):
            seen.append(list(tickers))
            return real(c, tickers)

        bets._legs_by_ticker = spy
        try:
            bets.bets_record(conn, limit=0)
        finally:
            bets._legs_by_ticker = real
        assert seen == [[]]


class TestPageLeadsWithLegs:
    def test_bet_lead_joins_leg_labels_and_keeps_the_fallback(self):
        fn = PAGE[PAGE.index("function betLead") :][:1800]
        assert re.search(r'bet\.legs\.map\(\(leg\) => leg\.label\)\.join\(" \+ "\)', fn)
        assert 'kind === "combo") return "Combination bet"' in fn
        assert fn.index("bet.legs.map") < fn.index('return "Combination bet"')
