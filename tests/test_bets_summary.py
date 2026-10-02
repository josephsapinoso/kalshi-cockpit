"""#287: the Your bets summary never pools the kinds, and its one
"expected at the prices you paid" line says only what the prices say.

Every fixture here is synthetic (round invented prices and results on
made-up tickers); nothing is, or may be, copied from the operator's record.

What this establishes
---------------------
- Wins and losses are served per kind and no key in `summary` spans both.
- Expected wins is the sum of the entry prices, recomputed from the rows
  (changing a price changes it; there is no stored constant).
- A cell expecting fewer than 5 wins or fewer than 5 losses is `too_few` and
  carries no range; overall and per bucket.
- Singles below the 30-bet floor get counts only (`expected` is None).
- The page renders the server's per-kind figures, carries no return/ROI
  figure and neither "unlucky" nor "due", and the range has a glossary entry
  rendered through `<Term>`.

What it does NOT establish
--------------------------
That the page draws (`next build` and a browser say that), or that a range
of two standard deviations is the right width -- it is a plain-words choice,
about 19 in 20, and is not a test of anything.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend import bets
from backend.store import db

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "frontend" / "src" / "app" / "bets" / "page.tsx"
GLOSSARY = REPO / "frontend" / "src" / "lib" / "glossary.ts"

COMBO = "KXMVESYNTHETIC-SHARD1-S0000000000000000-AAAAAAAAAAA"
SINGLE = "KXSYNTHGAME-26JAN010000AAABBB-AAA"


def _insert(conn, *, ticker, price, won, n=0, side="yes"):
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
        "position_first_seen_ms) VALUES (?, 'KXSYNTH', ?, ?, ?, 1.0, ?, 0, NULL)",
        (f"{ticker}-{n}", "yes" if won else "no", 1_000 + n, side, price),
    )


def _seed(conn, kind_ticker, cells):
    for i, (price, won) in enumerate(cells):
        _insert(conn, ticker=kind_ticker, price=price, won=won, n=i)
    conn.commit()


def _summary(tmp_path, *, combos=(), singles=()):
    conn = db.init_db(tmp_path / "s.db")
    _seed(conn, COMBO, combos)
    _seed(conn, SINGLE, singles)
    return bets.bets_record(conn)["summary"]


def test_bets_summary_never_pools_kinds(tmp_path):
    combos = [(250, True)] * 3 + [(250, False)] * 5
    singles = [(500, True)] * 2 + [(500, False)] * 4
    s = _summary(tmp_path, combos=combos, singles=singles)
    assert set(s) == {"single", "combo"}
    assert (s["combo"]["wins"], s["combo"]["losses"]) == (3, 5)
    assert (s["single"]["wins"], s["single"]["losses"]) == (2, 4)
    # No key anywhere in the summary spans both kinds.
    for block in s.values():
        assert not {"total_wins", "total_losses", "pooled"} & set(block)


class TestExpectedIsTheSumOfThePricesPaid:
    def test_expected_and_range_from_prices(self, tmp_path):
        # 40 combos at 25c, 10 won: expected 10.0; sd = sqrt(40*.25*.75).
        combos = [(250, True)] * 10 + [(250, False)] * 30
        e = _summary(tmp_path, combos=combos)["combo"]["expected"]
        assert e["expected"] == 10.0 and e["won"] == 10 and e["n"] == 40
        assert (e["range_low"], e["range_high"]) == (4, 16)
        assert e["too_few"] is False

    def test_a_different_price_gives_a_different_expected(self, tmp_path):
        combos = [(500, True)] * 10 + [(500, False)] * 30
        e = _summary(tmp_path, combos=combos)["combo"]["expected"]
        assert e["expected"] == 20.0

    def test_buckets_split_by_the_price_paid(self, tmp_path):
        combos = [(50, False)] * 3 + [(200, True)] * 2 + [(700, True)]
        buckets = {
            b["label"]: b
            for b in _summary(tmp_path, combos=combos)["combo"]["expected"][
                "buckets"
            ]
        }
        assert buckets["under 10c"]["n"] == 3
        assert buckets["10c to 25c"]["n"] == 2
        assert buckets["50c and up"]["n"] == 1
        assert buckets["25c to 50c"]["n"] == 0

    def test_a_row_with_no_readable_price_is_excluded_not_zeroed(self, tmp_path):
        conn = db.init_db(tmp_path / "s.db")
        _seed(conn, COMBO, [(250, True)])
        _insert(conn, ticker=COMBO, price=1000, won=True, n=99)  # out of range
        conn.commit()
        c = bets.bets_record(conn)["summary"]["combo"]
        assert c["excluded_from_expected"] == 1
        assert c["expected"]["n"] == 1


class TestTooFewCellsGetNoRange:
    def test_overall_too_few_when_expected_wins_under_five(self, tmp_path):
        combos = [(100, False)] * 20  # expects 2.0 wins
        e = _summary(tmp_path, combos=combos)["combo"]["expected"]
        assert e["too_few"] is True
        assert e["range_low"] is None and e["range_high"] is None

    def test_too_few_when_expected_losses_under_five(self, tmp_path):
        combos = [(900, True)] * 20  # expects 18 wins, only 2 losses
        e = _summary(tmp_path, combos=combos)["combo"]["expected"]
        assert e["too_few"] is True
        assert e["range_low"] is None

    def test_a_thin_bucket_is_too_few_while_the_overall_speaks(self, tmp_path):
        combos = [(250, True)] * 10 + [(250, False)] * 30 + [(50, False)] * 2
        e = _summary(tmp_path, combos=combos)["combo"]["expected"]
        assert e["too_few"] is False
        small = next(b for b in e["buckets"] if b["label"] == "under 10c")
        assert small["too_few"] is True and small["range_low"] is None


class TestSinglesBelowTheFloorGetCountsOnly:
    def test_below_floor(self, tmp_path):
        singles = [(500, True)] * 10 + [(500, False)] * 19  # 29 settled
        s = _summary(tmp_path, singles=singles)["single"]
        assert s["counts_only"] is True and s["expected"] is None
        assert s["wins"] == 10 and s["losses"] == 19

    def test_at_floor_the_line_appears(self, tmp_path):
        singles = [(500, True)] * 15 + [(500, False)] * 15  # 30 settled
        s = _summary(tmp_path, singles=singles)["single"]
        assert s["counts_only"] is False
        assert s["expected"]["expected"] == 15.0


def _code(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


class TestTheScreen:
    def test_the_page_renders_the_servers_summary_per_kind(self):
        text = _code(PAGE)
        assert "record.summary?.[section.kind]" in text
        assert "<KindSummary" in text

    def test_the_pooled_win_loss_count_is_not_rendered(self):
        text = _code(PAGE)
        assert "totals.wins" not in text and "totals.losses" not in text

    @pytest.mark.parametrize("word", ["unlucky", "due", "roi", "return on"])
    def test_words_the_page_may_never_carry(self, word):
        text = _code(PAGE).lower()
        assert not re.search(rf"\b{re.escape(word)}\b", text), word

    def test_no_return_figure_in_the_summary_payload(self, tmp_path):
        s = _summary(tmp_path, combos=[(250, True)] * 10 + [(250, False)] * 30)
        keys = " ".join(
            list(s["combo"]) + list(s["combo"]["expected"])
        ).lower()
        assert "net" not in keys and "roi" not in keys and "return" not in keys

    def test_the_range_has_a_glossary_entry_rendered_through_term(self):
        assert "plausible_range:" in GLOSSARY.read_text(encoding="utf-8")
        assert 'k="plausible_range"' in _code(PAGE)
        assert 'k="expected_wins"' in _code(PAGE)

    def test_the_too_few_label_is_on_the_page(self):
        text = _code(PAGE)
        assert "too few to judge" in text and "Too few" in text
