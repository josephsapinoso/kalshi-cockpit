"""#161: the desk's chance for a combo at the moment Joe priced it.

Every synthetic row here (the operator-data ruling: no account data enters
the repo, even sanitized). This pins `bets.bets_record`'s
`chance_when_priced`/`chance_priced_before_fill_ms`/`chance_refusal_reason`
on combo rows, `sections["combo"]["chance_carried"]` as a whole-table COUNT
(never a sum or an average), and that neither the backend module nor the
frontend page ever aggregates the chance values themselves.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from backend import bets
from backend.store import db

COMBO_TICKER = "KXMVECROSSCATEGORY-SHARD1-S20266AE347C36E7-E497F938E16"
COMBO_TICKER_2 = "KXMVECROSSCATEGORY-SHARD2-S20266AE347C36E7-E497F938E17"
GAME_TICKER = "KXMLBGAME-26AUG221805STLPHI-PHI"

FILL_MS = 1_700_000_000_000  # the anchor: the position's first fill


def _settlement(conn, *, ticker=COMBO_TICKER, settled_ms=1_000, **overrides):
    row = {
        "ticker": ticker,
        "event_ticker": "KXMVECROSSCATEGORY",
        "market_result": "yes",
        "settled_ms": settled_ms,
        "side": "yes",
        "contracts": 2.0,
        "entry_price_tenths": 400,
        "fee_cost_tenths": 20,
        "position_first_seen_ms": None,
    }
    row.update(overrides)
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
        "position_first_seen_ms) "
        "VALUES (:ticker, :event_ticker, :market_result, :settled_ms, :side, "
        ":contracts, :entry_price_tenths, :fee_cost_tenths, "
        ":position_first_seen_ms)",
        row,
    )
    conn.commit()


def _fill(conn, *, ticker=COMBO_TICKER, filled_ms=FILL_MS, count=2.0,
          price_tenths=400):
    conn.execute(
        "INSERT INTO fills (ticker, filled_ms, count, price_tenths, is_taker, "
        "fee_predicted, fee_model_used, source) VALUES (?, ?, ?, ?, 1, 0.0, "
        "'model_a_deci', 'venue_hand')",
        (ticker, filled_ms, count, price_tenths),
    )
    conn.commit()


def _lookup(conn, *, ticker=COMBO_TICKER, requested_ms, status="priced",
            fair_joint_conservative=0.34, card_key="safe"):
    conn.execute(
        "INSERT INTO parlay_lookups (requested_ms, card_key, stake_cents, "
        "selected_legs, status, minted_market_ticker, "
        "fair_joint_conservative, collection_unverified) "
        "VALUES (?, ?, 500, '[]', ?, ?, ?, 0)",
        (requested_ms, card_key, status, ticker, fair_joint_conservative),
    )
    conn.commit()


def _rfq(conn, *, ticker=COMBO_TICKER, requested_ms, fair_joint=0.34,
          rfq_id=None, status="quoted", purpose="buy"):
    if rfq_id is None:
        rfq_id = f"rfq-{ticker}-{requested_ms}"
    conn.execute(
        "INSERT INTO combo_rfqs (rfq_id, requested_ms, ticker, "
        "collection_ticker, selected_legs, exchange_index, fair_joint, "
        "status, purpose) "
        "VALUES (?, ?, ?, 'KXMVECROSSCATEGORY', '[]', 1, ?, ?, ?)",
        (rfq_id, requested_ms, ticker, fair_joint, status, purpose),
    )
    conn.commit()


def _combo_row(record: dict, ticker=COMBO_TICKER) -> dict:
    matches = [b for b in record["bets"] if b["ticker"] == ticker]
    assert len(matches) == 1, f"expected exactly one row for {ticker}"
    return matches[0]


class TestTheLatestPricedLookupBeforeTheFillWins:
    def test_several_priced_lookups_before_the_fill_take_the_latest(
        self, tmp_path
    ):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _lookup(conn, requested_ms=FILL_MS - 10_000, fair_joint_conservative=0.20)
        _lookup(conn, requested_ms=FILL_MS - 5_000, fair_joint_conservative=0.31)
        _lookup(conn, requested_ms=FILL_MS - 1_000, fair_joint_conservative=0.34)
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] == 0.34
        assert bet["chance_priced_before_fill_ms"] == 1_000
        assert bet["chance_refusal_reason"] is None

    def test_a_lookup_after_the_fill_is_ignored_if_it_is_the_only_one(
        self, tmp_path
    ):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _lookup(conn, requested_ms=FILL_MS + 5_000, fair_joint_conservative=0.55)
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] is None
        assert bet["chance_priced_before_fill_ms"] is None
        assert bet["chance_refusal_reason"] == "not_priced_on_desk"

    def test_a_later_lookup_is_ignored_even_when_an_earlier_one_qualifies(
        self, tmp_path
    ):
        """The after-fill lookup must not win the latest-wins tiebreak just
        because it has a bigger `requested_ms`."""
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _lookup(conn, requested_ms=FILL_MS - 2_000, fair_joint_conservative=0.28)
        _lookup(conn, requested_ms=FILL_MS + 3_000, fair_joint_conservative=0.99)
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] == 0.28
        assert bet["chance_refusal_reason"] is None


class TestNoFillRow:
    def test_a_combo_with_no_fill_row_refuses(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _lookup(conn, requested_ms=1, fair_joint_conservative=0.5)
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] is None
        assert bet["chance_priced_before_fill_ms"] is None
        assert bet["chance_refusal_reason"] == "no_fill_row"


class TestRefusedAndErrorLookupsAreIgnored:
    """Renamed from `TestOnlyPricedStatusCounts` (#163): `status = 'priced'`
    is no longer the only status that carries a chance -- `book_empty` does
    too, per `test_a_book_empty_lookup_carries_the_chance` below. What this
    class still pins is that `refused` (no market was minted) and `error`
    (the read failed) never carry one."""

    def test_a_non_priced_lookup_is_ignored(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _lookup(
            conn, requested_ms=FILL_MS - 1_000, status="refused",
            fair_joint_conservative=0.77,
        )
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] is None
        assert bet["chance_refusal_reason"] == "not_priced_on_desk"

    def test_an_error_lookup_is_ignored(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _lookup(
            conn, requested_ms=FILL_MS - 1_000, status="error",
            fair_joint_conservative=0.77,
        )
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] is None
        assert bet["chance_refusal_reason"] == "not_priced_on_desk"

    def test_a_book_empty_lookup_beats_an_earlier_priced_one(self, tmp_path):
        """SPEC CORRECTION (#163), not a weakened assertion: this test used
        to be named `test_a_priced_lookup_beats_a_later_non_priced_one` and
        asserted the OPPOSITE -- that a `priced` reading wins over a later
        `book_empty` one. That was wrong: a KXMVE book is empty by design
        between RFQs (ADR 0164), so `book_empty` is a real desk reading, not
        a lesser one, and the newest qualifying reading must win regardless
        of which of the two statuses it carries."""
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _lookup(conn, requested_ms=FILL_MS - 3_000, fair_joint_conservative=0.40)
        _lookup(
            conn, requested_ms=FILL_MS - 500, status="book_empty",
            fair_joint_conservative=0.90,
        )
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] == 0.90
        assert bet["chance_refusal_reason"] is None


class TestABookEmptyLookupCarriesTheChance:
    def test_a_book_empty_lookup_carries_the_chance(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _lookup(
            conn, requested_ms=FILL_MS - 1_000, status="book_empty",
            fair_joint_conservative=0.41,
        )
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] == 0.41
        assert bet["chance_refusal_reason"] is None
        assert record["sections"]["combo"]["chance_carried"] == 1


class TestAnRfqAskCarriesTheChance:
    def test_an_rfq_ask_carries_the_chance(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _rfq(conn, requested_ms=FILL_MS - 1_000, fair_joint=0.578)
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] == 0.578
        assert bet["chance_refusal_reason"] is None
        assert record["sections"]["combo"]["chance_carried"] == 1


class TestTheLatestReadingWinsAcrossBothTables:
    def test_the_latest_reading_wins_across_both_tables(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _lookup(
            conn, requested_ms=FILL_MS - 5_000, status="book_empty",
            fair_joint_conservative=0.20,
        )
        _rfq(conn, requested_ms=FILL_MS - 2_000, fair_joint=0.578)
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] == 0.578
        assert bet["chance_priced_before_fill_ms"] == 2_000

    def test_an_older_rfq_loses_to_a_newer_lookup(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _rfq(conn, requested_ms=FILL_MS - 5_000, fair_joint=0.578)
        _lookup(
            conn, requested_ms=FILL_MS - 2_000, status="book_empty",
            fair_joint_conservative=0.20,
        )
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] == 0.20

    def test_a_tie_at_the_same_millisecond_is_broken_toward_the_lookup(
        self, tmp_path
    ):
        """The ticket requires a deterministic tiebreak and asks that it be
        stated. This repo's rule (see `_chance_when_priced_by_ticker`'s
        docstring): at an identical `requested_ms`, the `parlay_lookups`
        reading wins over the `combo_rfqs` one."""
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        tied_ms = FILL_MS - 1_000
        _lookup(conn, requested_ms=tied_ms, status="book_empty",
                fair_joint_conservative=0.20)
        _rfq(conn, requested_ms=tied_ms, fair_joint=0.578)
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] == 0.20


class TestAnRfqAfterTheFillIsIgnored:
    def test_an_rfq_after_the_fill_is_ignored(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _rfq(conn, requested_ms=FILL_MS + 5_000, fair_joint=0.14,
             purpose="exit")
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] is None
        assert bet["chance_refusal_reason"] == "not_priced_on_desk"

    def test_an_rfq_at_or_before_the_fill_still_qualifies_even_as_exit(
        self, tmp_path
    ):
        """The ticket does not ask for a `purpose` filter -- the
        at-or-before-the-fill bound alone excludes a post-fill sell-side
        ask, since a sell-side ask cannot exist before the position does in
        the tool's own flow. This pins that no extra `purpose` guard was
        smuggled in that would also exclude a legitimate before-the-fill
        row."""
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _rfq(conn, requested_ms=FILL_MS - 1_000, fair_joint=0.578,
             purpose="exit")
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] == 0.578


class TestSinglesCarryNone:
    def test_a_single_game_row_carries_none_for_all_three_keys(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn, ticker=GAME_TICKER)
        record = bets.bets_record(conn)
        bet = _combo_row(record, ticker=GAME_TICKER)
        assert bet["kind"] == "single"
        assert bet["chance_when_priced"] is None
        assert bet["chance_priced_before_fill_ms"] is None
        assert bet["chance_refusal_reason"] is None


class TestChanceCarriedIsAWholeTableCount:
    def test_chance_carried_counts_the_whole_table_not_the_limit_window(
        self, tmp_path
    ):
        conn = db.init_db(tmp_path / "b.db")
        for i in range(3):
            ticker = f"{COMBO_TICKER}-{i}"
            _settlement(conn, ticker=ticker, settled_ms=1_000 + i)
            _fill(conn, ticker=ticker, filled_ms=FILL_MS + i)
            _lookup(
                conn, ticker=ticker, requested_ms=FILL_MS + i - 500,
                fair_joint_conservative=0.3 + i / 100,
            )
        # One combo with no qualifying lookup -- does not carry the chance.
        _settlement(conn, ticker=COMBO_TICKER_2, settled_ms=2_000)
        _fill(conn, ticker=COMBO_TICKER_2, filled_ms=FILL_MS)

        record = bets.bets_record(conn, limit=1)
        assert record["returned"] == 1
        assert record["total"] == 4
        assert record["sections"]["combo"]["chance_carried"] == 3

    def test_chance_carried_never_counts_a_single(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn, ticker=GAME_TICKER)
        record = bets.bets_record(conn)
        assert record["sections"]["single"]["chance_carried"] == 0


class TestOneBatchedQueryNotOnePerRow:
    def test_bets_record_does_not_query_parlay_lookups_inside_the_row_loop(
        self, tmp_path
    ):
        """A grep-shaped guard: `bets.py`'s row loop (the `for row in rows`
        body) must not itself execute a SQL statement against
        `parlay_lookups` -- the batched helper is called once, before the
        loop, and the loop only reads its pre-built dict."""
        source = inspect.getsource(bets.bets_record)
        tree = ast.parse(source)
        func = tree.body[0]
        loop = next(
            node for node in ast.walk(func) if isinstance(node, ast.For)
        )
        loop_source = ast.unparse(loop)
        assert "conn.execute" not in loop_source


class TestCheckedWithoutChance:
    """#168: a `parlay_lookups` row written by the outside-parlay check
    (#166, `card_key = 'outside'`) with a NULL `fair_joint_conservative` --
    the desk looked at the parlay and could not produce one number for the
    whole thing. Such a row must not render identically to "not priced on
    the desk" at all; `checked_without_chance` says the desk DID look."""

    def test_an_outside_row_with_null_joint_before_the_fill_sets_the_flag(
        self, tmp_path
    ):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _lookup(
            conn, requested_ms=FILL_MS - 1_000, card_key="outside",
            status="priced", fair_joint_conservative=None,
        )
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] is None
        assert bet["chance_refusal_reason"] == "not_priced_on_desk"
        assert bet["checked_without_chance"] is True

    def test_the_same_row_after_the_fill_does_not_set_the_flag(
        self, tmp_path
    ):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _lookup(
            conn, requested_ms=FILL_MS + 1_000, card_key="outside",
            status="priced", fair_joint_conservative=None,
        )
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] is None
        assert bet["checked_without_chance"] is False

    def test_an_earlier_chance_plus_a_later_null_joint_row_shows_the_chance(
        self, tmp_path
    ):
        """A reading with a chance always wins: the earlier priced lookup
        carries a real joint and must still be shown, and the later
        null-joint row (itself before the fill) must not flip the flag on
        top of a chance that is already showing."""
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _lookup(
            conn, requested_ms=FILL_MS - 5_000, card_key="safe",
            status="priced", fair_joint_conservative=0.42,
        )
        _lookup(
            conn, requested_ms=FILL_MS - 1_000, card_key="outside",
            status="priced", fair_joint_conservative=None,
        )
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] == 0.42
        assert bet["chance_refusal_reason"] is None
        assert bet["checked_without_chance"] is False

    def test_a_refused_or_error_row_with_null_joint_does_not_set_the_flag(
        self, tmp_path
    ):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _lookup(
            conn, requested_ms=FILL_MS - 1_000, card_key="outside",
            status="refused", fair_joint_conservative=None,
        )
        _lookup(
            conn, requested_ms=FILL_MS - 500, card_key="outside",
            status="error", fair_joint_conservative=None,
        )
        record = bets.bets_record(conn)
        bet = _combo_row(record)
        assert bet["chance_when_priced"] is None
        assert bet["checked_without_chance"] is False

    def test_the_flag_never_counts_toward_chance_carried(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn)
        _fill(conn)
        _lookup(
            conn, requested_ms=FILL_MS - 1_000, card_key="outside",
            status="priced", fair_joint_conservative=None,
        )
        record = bets.bets_record(conn)
        assert record["sections"]["combo"]["chance_carried"] == 0

    def test_a_single_carries_false_never_none(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settlement(conn, ticker=GAME_TICKER)
        record = bets.bets_record(conn)
        bet = _combo_row(record, ticker=GAME_TICKER)
        assert bet["checked_without_chance"] is False


class TestNoAggregationOfChanceValues:
    """The ticket's out-of-scope guard, enforced by source scan, on both the
    backend module and the frontend page."""

    BETS_PY = Path(__file__).resolve().parents[1] / "backend" / "bets.py"
    PAGE_TSX = (
        Path(__file__).resolve().parents[1]
        / "frontend" / "src" / "app" / "bets" / "page.tsx"
    )

    def test_bets_py_never_sums_or_averages_chance_when_priced(self):
        source = self.BETS_PY.read_text(encoding="utf-8")
        # Every mention of `chance_when_priced` must not sit inside a
        # sum(...)/mean(...) call or a += accumulation.
        assert "sum(" not in source or "chance_when_priced" not in source
        for line in source.splitlines():
            if "chance_when_priced" in line:
                assert "sum(" not in line
                assert "mean" not in line
                assert "+=" not in line

    def test_page_tsx_never_reduces_or_sums_chance_when_priced(self):
        source = self.PAGE_TSX.read_text(encoding="utf-8")
        assert "reduce" not in source
        for line in source.splitlines():
            if "chance_when_priced" in line:
                assert "sum" not in line.lower()
                assert "mean" not in line.lower()

    def test_page_tsx_never_defaults_chance_when_priced_to_zero(self):
        source = self.PAGE_TSX.read_text(encoding="utf-8")
        for line in source.splitlines():
            if "chance_when_priced" in line:
                assert "?? 0" not in line
                assert "|| 0" not in line

    def test_page_tsx_carries_the_not_priced_copy(self):
        source = self.PAGE_TSX.read_text(encoding="utf-8")
        assert "not priced on the desk" in source

    def test_a_small_chance_never_renders_as_zero_percent(self):
        """The first live render printed "Desk's chance when you priced it:
        0%" for a combination bought at a tenth of a cent. A reading of 0.08%
        is not "no chance"; rounding it to whole points said that it was."""
        source = self.PAGE_TSX.read_text(encoding="utf-8")
        assert "Math.round(bet.chance_when_priced" not in source
        assert "chancePercent(bet.chance_when_priced)" in source
        helper = source[source.index("function chancePercent") :]
        helper = helper[: helper.index("\n}\n")]
        assert '"under 0.01%"' in helper
        assert "toFixed(2)" in helper
