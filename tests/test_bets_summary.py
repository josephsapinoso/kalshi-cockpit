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


# ---------------------------------------------------------------------------
# #323 / ADR 0194: the legs of the combinations Joe holds, by league and kind.
# ---------------------------------------------------------------------------

MLB_ML = "KXMLBGAME-26SEP01AAABBB"
MLB_SPREAD = "KXMLBSPREAD-26SEP01AAABBB"
MLB_TOTAL = "KXMLBTOTAL-26SEP01AAABBB"
MLB_PROP = "KXMLBKS-26SEP01AAABBB"
NFL_ML = "KXNFLGAME-26SEP07AAABBB"


def _leg(conn, *, event, league="Pro Baseball", side="yes", outcome="won",
         ask=400, close=None, n=0):
    """One settled held leg. `ask`/`close` None stay NULL (never 0).

    `close` is `(bid, ask)` tenths of the YES side.
    """
    from backend import hedge

    leg = {"ticker": f"{event}-T{n}", "event_ticker": event, "side": side,
           "label": "synthetic", "league": league}
    if ask is not None:
        leg["kalshi_ask_tenths"] = ask
    position_id = hedge.record_position(
        conn, now_ms=1_000 + n, source="kalshi_combo", label="synthetic",
        stake_tenths=1000, return_tenths=5000, legs=[leg],
    )
    conn.execute(
        "UPDATE parlay_position_legs SET outcome = ?, resolved_ms = 2, "
        "resolved_source = 'venue' WHERE position_id = ?",
        (outcome, position_id),
    )
    if close is not None:
        conn.execute(
            "UPDATE parlay_position_legs SET close_yes_bid_tenths = ?, "
            "close_yes_ask_tenths = ?, close_observed_ms = 3 "
            "WHERE position_id = ?", (close[0], close[1], position_id),
        )
    conn.commit()


def _legs_db(tmp_path):
    return db.init_db(tmp_path / "legs.db")


def _blocks(summary, league="Pro Baseball"):
    [row] = [x for x in summary["leagues"] if x["league"] == league]
    return {b["kind"]: b for b in row["kinds"]}


class TestByLegKind:
    def test_kinds_are_never_pooled(self, tmp_path):
        conn = _legs_db(tmp_path)
        for i in range(12):
            _leg(conn, event=MLB_ML, ask=500, outcome="won" if i < 6 else "lost", n=i)
        for i in range(3):
            _leg(conn, event=MLB_SPREAD, ask=250, outcome="lost", n=100 + i)
        s = bets.by_leg_kind_summary(conn)
        blocks = _blocks(s)
        assert blocks["moneyline"]["expected"]["n"] == 12
        assert blocks["moneyline"]["expected"]["won"] == 6
        assert blocks["spread"]["expected"]["n"] == 3
        assert blocks["spread"]["expected"]["won"] == 0
        # nothing spans kinds: no pooled block, no pooled key
        [league] = s["leagues"]
        assert [b["kind"] for b in league["kinds"]] == ["moneyline", "spread"]
        assert set(s) == {"kind_order", "leagues"}

    def test_leagues_are_never_pooled(self, tmp_path):
        conn = _legs_db(tmp_path)
        _leg(conn, event=MLB_ML, league="Pro Baseball", n=1)
        _leg(conn, event=NFL_ML, league="Pro Football", n=2)
        s = bets.by_leg_kind_summary(conn)
        assert [x["league"] for x in s["leagues"]] == ["Pro Baseball", "Pro Football"]
        assert _blocks(s, "Pro Baseball")["moneyline"]["expected"]["n"] == 1
        assert _blocks(s, "Pro Football")["moneyline"]["expected"]["n"] == 1

    @pytest.mark.parametrize("flip", [False, True])
    def test_the_order_is_fixed_and_never_sorted_by_result(self, tmp_path, flip):
        """Inserted in the opposite of the fixed order, with results that
        would order the kinds differently from it -- and flipped. The served
        order is the same in all four arrangements."""
        conn = _legs_db(tmp_path)
        wins = {"prop": 12, "total": 8, "spread": 4, "moneyline": 0}
        events = {"prop": MLB_PROP, "total": MLB_TOTAL,
                  "spread": MLB_SPREAD, "moneyline": MLB_ML}
        k = 0
        for kind in ("prop", "total", "spread", "moneyline"):
            for i in range(12):
                won = (i < wins[kind]) != flip
                _leg(conn, event=events[kind], outcome="won" if won else "lost",
                     ask=500, n=k)
                k += 1
        _leg(conn, event=MLB_ML, league=None, ask=500, n=k)
        _leg(conn, event=MLB_ML, league="Pro Basketball", ask=500, n=k + 1)
        s = bets.by_leg_kind_summary(conn)
        assert [x["league"] for x in s["leagues"]] == [
            "Pro Baseball", "Pro Basketball", "Unknown",
        ]
        assert [b["kind"] for b in s["leagues"][0]["kinds"]] == [
            "moneyline", "spread", "total", "prop",
        ]

    def test_a_null_ask_is_counted_not_priced_at_zero(self, tmp_path):
        conn = _legs_db(tmp_path)
        for i in range(10):
            _leg(conn, event=MLB_ML, ask=500, outcome="won" if i < 5 else "lost", n=i)
        for i in range(4):
            _leg(conn, event=MLB_ML, ask=None, outcome="lost", n=50 + i)
        block = _blocks(bets.by_leg_kind_summary(conn))["moneyline"]
        assert block["settled"] == 14
        assert block["ask_not_recorded"] == 4
        # the four unknown legs are in no cell: n and expected are the ten
        assert block["expected"]["n"] == 10
        assert block["expected"]["expected"] == 5.0
        assert block["expected"]["won"] == 5

    def test_a_null_close_is_counted_and_an_empty_clv_is_none_not_zero(
        self, tmp_path
    ):
        conn = _legs_db(tmp_path)
        _leg(conn, event=MLB_ML, ask=400, close=None, n=1)
        _leg(conn, event=MLB_ML, ask=400, close=(480, None), n=2)  # one-sided
        block = _blocks(bets.by_leg_kind_summary(conn))["moneyline"]
        assert block["clv"] == {
            "n": 0, "sum_cents": None, "median_cents": None,
            "close_not_recorded": 2,
        }

    def test_the_close_is_signed_by_the_side_held(self, tmp_path):
        conn = _legs_db(tmp_path)
        # YES at 40.0c, closes mid 50.0c: +10.0c. NO at 30.0c, closes at a
        # YES mid of 50.0c, worth 50.0c: +20.0c.
        _leg(conn, event=MLB_ML, side="yes", ask=400, close=(480, 520), n=1)
        _leg(conn, event=MLB_ML, side="no", ask=300, close=(480, 520), n=2)
        clv = _blocks(bets.by_leg_kind_summary(conn))["moneyline"]["clv"]
        assert clv["n"] == 2
        assert clv["sum_cents"] == 30.0
        assert clv["median_cents"] == 15.0
        assert clv["close_not_recorded"] == 0

    def test_too_few_below_five_expected_each_side(self, tmp_path):
        conn = _legs_db(tmp_path)
        for i in range(8):
            _leg(conn, event=MLB_ML, ask=500, n=i)
        block = _blocks(bets.by_leg_kind_summary(conn))["moneyline"]["expected"]
        assert block["too_few"] is True
        assert block["range_low"] is None and block["range_high"] is None
        for i in range(8, 14):
            _leg(conn, event=MLB_ML, ask=500, n=i)
        block = _blocks(bets.by_leg_kind_summary(conn))["moneyline"]["expected"]
        assert block["too_few"] is False and block["range_low"] is not None

    def test_pending_and_void_legs_are_not_in_the_block(self, tmp_path):
        conn = _legs_db(tmp_path)
        _leg(conn, event=MLB_ML, ask=500, n=1)
        conn.execute(
            "UPDATE parlay_position_legs SET outcome = 'void' WHERE ticker LIKE ?",
            (f"{MLB_ML}-T1",),
        )
        conn.commit()
        assert bets.by_leg_kind_summary(conn)["leagues"] == []

    def test_bets_record_serves_it_beside_the_sections(self, tmp_path):
        conn = _legs_db(tmp_path)
        _leg(conn, event=MLB_ML, ask=500, n=1)
        record = bets.bets_record(conn)
        assert _blocks(record["by_leg_kind"])["moneyline"]["settled"] == 1

    # -- the two rules of ADR 0194 s2.6 ----------------------------------

    def test_the_block_never_reads_leg_verdicts(self, tmp_path):
        """Rows exist in `leg_verdicts`; the authorizer sees every table the
        statement touches at compile time, so a join to it is caught even if
        it changed no number."""
        import sqlite3

        conn = _legs_db(tmp_path)
        _leg(conn, event=MLB_ML, ask=500, n=1)
        touched: set[str] = set()

        def authorizer(action, arg1, arg2, dbname, source):
            if action == sqlite3.SQLITE_READ and arg1:
                touched.add(arg1)
            return sqlite3.SQLITE_OK

        conn.set_authorizer(authorizer)
        bets.by_leg_kind_summary(conn)
        conn.set_authorizer(None)
        assert "parlay_position_legs" in touched
        assert "leg_verdicts" not in touched

    def test_the_block_never_names_leg_verdicts_or_the_gap(self):
        """No string literal in the function (its docstring aside) names
        either; so a hand-written split cannot hide in a SQL string."""
        import ast
        import inspect
        import textwrap

        source = textwrap.dedent(inspect.getsource(bets.by_leg_kind_summary))
        tree = ast.parse(source)
        fn = tree.body[0]
        doc = ast.get_docstring(fn, clean=False)
        for node in ast.walk(fn):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value == doc:
                    continue
                for banned in ("leg_verdicts", "desk_chance", "fair_joint"):
                    assert banned not in node.value, (banned, node.value)
            if isinstance(node, ast.Name):
                assert node.id not in ("desk_chance", "gap"), node.id

    def test_nothing_is_split_by_the_books_chance_minus_the_ask(self, tmp_path):
        """The served shape is exactly kind/settled/ask_not_recorded/expected/
        clv: a gap split would have to add a key, and none is allowed."""
        conn = _legs_db(tmp_path)
        _leg(conn, event=MLB_ML, ask=400, close=(480, 520), n=1)
        s = bets.by_leg_kind_summary(conn)
        [block] = s["leagues"][0]["kinds"]
        assert set(block) == {
            "kind", "settled", "ask_not_recorded", "expected", "clv",
        }
        assert set(block["clv"]) == {
            "n", "sum_cents", "median_cents", "close_not_recorded",
        }
        assert set(s["leagues"][0]) == {"league", "kinds"}
        # the table the block reads has no chance column to split on
        cols = {r[1] for r in conn.execute("PRAGMA table_info(parlay_position_legs)")}
        assert "desk_chance" not in cols

    def test_no_hit_rate_or_average_key_anywhere(self, tmp_path):
        conn = _legs_db(tmp_path)
        _leg(conn, event=MLB_ML, ask=400, close=(480, 520), n=1)
        text = repr(bets.by_leg_kind_summary(conn)).lower()
        for word in ("rate", "mean", "average", "roi", "trend", "streak"):
            assert word not in text, word

    # -- one classifier, in two places ------------------------------------

    def test_the_kind_agrees_with_the_census_scripts_classifier(self):
        from scripts.count_combo_leg_sides import classify_leg_kind

        from backend.kalshi.props import PROP_SERIES

        series = [
            "KXMLBGAME", "KXNFLGAME", "KXNBAGAME", "KXWNBAGAME", "KXMLBSPREAD",
            "KXNFLSPREAD", "KXMLBTOTAL", "KXNFLTOTAL", "KXMLBTEAMTOTAL",
            "KXNOTASERIES", "KXMVECROSSCATEGORY", *PROP_SERIES,
        ]
        assert len(PROP_SERIES) >= 5
        for s in series:
            event = f"{s}-26SEP01AAABBB"
            script_kind = classify_leg_kind(
                {"event_ticker": event, "market_ticker": f"{event}-AAA", "side": "yes"}
            ).kind.split(":")[0]
            assert bets.leg_kind(event, f"{event}-AAA") == script_kind, s

    def test_a_leg_with_no_event_ticker_is_classified_by_its_market_ticker(self):
        assert bets.leg_kind(None, "KXNFLSPREAD-26SEP07AAABBB-AAA3") == "spread"
        assert bets.leg_kind(None, None) == "other"


class TestByLegKindOnThePage:
    def _component(self):
        text = _code(PAGE)
        start = text.index("type LegKindClv")
        end = text.index("function MirrorNotAccount")
        return text[start:end]

    def test_the_page_renders_the_servers_block_for_combos(self):
        text = _code(PAGE)
        assert "<ByLegKindBlock" in text
        assert 'section.kind === "combo"' in text

    def test_fixed_order_no_colour_no_arithmetic(self):
        comp = self._component()
        for token in (".sort(", "toSorted", ".reverse(", "text-positive",
                      "text-negative", "text-green", "text-red", ".reduce("):
            assert token not in comp, token

    def test_the_too_few_and_not_recorded_words_are_on_the_page(self):
        comp = self._component()
        assert "too few to judge" in comp
        assert "not recorded" in comp

    def test_the_page_never_names_the_books_chance(self):
        comp = self._component().lower()
        for token in ("desk_chance", "leg_verdict", "verdict"):
            assert token not in comp, token
