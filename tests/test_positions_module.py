"""One writer of held combos, and the provenance it stores (ADR 0192, #264).

Establishes:
  * For an RFQ fill, the stake, basis and reason `backend/positions.py`
    stores at write are what ADR 0160/0178's read-time join computes for the
    same row. The fills covered are: a usable venue fill (whole and
    fractional), a venue that answered with nothing, a fill read that
    failed, and a quote the venue was never asked about.
  * A slip typed on `/hedge` and a holding adopted off the venue store the
    basis the read would give them. A typed Kalshi combination that DOES
    carry the order's key stores none, so the join still resolves it.
  * A row with no stored basis, the shape of every pre-v60 row and of every
    row the hand-bet order path writes until S2 (#265), is served by the
    join exactly as before.
  * By source text: in production, only `backend/positions.py` calls
    `hedge.record_position`. The allowlist holds the order path until #265
    and two operator scripts. Only `backend/hedge.py` inserts into the two
    tables.
  * The RFQ writer never raises.

  * The hand-bet order path (S2, #265) stores, per its order row read by
    id, the stake the join computes: whole and 2.5-contract venue fills,
    no venue price, no count, a NO order, and no order row. A count finer
    than a tenth writes nothing.

Does not establish: anything about live rows (none are rewritten, ADR 0192
§2.6), or what Kalshi charged after fees.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

import backend.hedge as hedge
import backend.positions as positions
from backend import combo_rfq
from backend.store import combo_rfqs as store
from backend.store import db
from tests.test_combo_fill_is_watched_for_a_hedge import (
    COMBO_TICKER as ORDER_COMBO,
)
from tests.test_combo_fill_is_watched_for_a_hedge import _seed_lookup
from tests.test_stake_basis_is_the_venue_fill import (
    SENT_TENTHS,
    VENUE_TENTHS,
    an_order,
)
from tests.test_combo_rfq_accept import (
    QUOTE,
    RFQ,
    SCHEMA,
    FakeApi,
    _as_pre_v60,
    _fill_at,
    _positions,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def conn():
    """`test_combo_rfq_accept`'s fixture, restated: one RFQ on `KXMVE-X` and
    one maker quote at 59.3c for 9 contracts."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA.read_text())
    store.record_rfq(
        c, rfq_id=RFQ, requested_ms=1_000, ticker="KXMVE-X",
        collection_ticker="KXMVECROSSCATEGORY-R",
        legs=[{"market_ticker": "M1", "side": "yes"}], exchange_index=1,
    )
    c.execute(
        "INSERT INTO combo_rfq_quotes (rfq_id, quote_id, captured_ms, maker_id, "
        "yes_ask_tenths, no_bid_tenths, contracts, status, created_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (RFQ, QUOTE, 1_000, "maker", 593, 407, 9.0, "open", "ts"),
    )
    c.commit()
    yield c
    c.close()

#: Production callers of `hedge.record_position`: the one writer, and two
#: operator scripts. `routes.py` left this set with #265 (S2), when the
#: hand-bet order path moved onto `positions.record_order_fill`.
RECORD_POSITION_ALLOWED = {
    "backend/positions.py",
    "scripts/backfill_orphan_combo_position.py",
    "scripts/drive_hedge.py",
}


async def _accept(conn, api):
    return await combo_rfq.accept_quote_for_joe(
        conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000, api=api, dry_run=False,
    )


def _stored_then_joined(conn):
    """The basis `/hedge` serves from the stored columns, then the one the
    read-time join computes for the same row with those columns cleared."""
    rows = _positions(conn)
    assert len(rows) == 1
    pid = int(rows[0]["id"])
    stored = hedge.stake_bases(conn, rows)[pid]
    _as_pre_v60(conn)
    joined = hedge.stake_bases(conn, _positions(conn))[pid]
    return stored, joined


class TestAnRfqFillStoresWhatTheJoinWouldHaveRead:
    @pytest.mark.parametrize(
        "api_kwargs, basis, reason",
        [
            ({"fills": [_fill_at("9.00")]}, hedge.STAKE_BASIS_VENUE_FILL, None),
            ({"fills": [_fill_at("4.50")]}, hedge.STAKE_BASIS_VENUE_FILL, None),
            ({"fills": []}, hedge.STAKE_BASIS_AS_RECORDED, "rfq_fill_unmatched"),
            ({"fills_raise": True}, hedge.STAKE_BASIS_AS_RECORDED, "rfq_fill_unmatched"),
        ],
        ids=["whole-fill", "fractional-fill", "venue-said-nothing", "read-failed"],
    )
    async def test_stored_equals_joined(self, conn, api_kwargs, basis, reason):
        await _accept(conn, FakeApi(statuses=["executed"], **api_kwargs))
        row = _positions(conn)[0]
        assert row["fill_source"] == positions.FILL_RFQ_QUOTE
        quote_id = conn.execute("SELECT id FROM combo_rfq_quotes").fetchone()[0]
        assert row["fill_ref"] == quote_id
        stored, joined = _stored_then_joined(conn)
        assert stored == joined
        assert (stored.basis, stored.reason) == (basis, reason)

    def test_a_venue_never_asked_is_rfq_accept(self, conn):
        """An executed acceptance whose fill was never read (every accept
        before schema v50 had this shape)."""
        conn.execute(
            "UPDATE combo_rfq_quotes SET outcome_status = 'executed', "
            "accepted_ms = 2000, accept_dry_run = 0"
        )
        conn.commit()
        quote = conn.execute("SELECT * FROM combo_rfq_quotes").fetchone()
        pid = positions.record_rfq_accept(
            conn, rfq_id=RFQ, quote=quote, now_ms=2_000, venue=None
        )
        assert pid is not None
        stored, joined = _stored_then_joined(conn)
        assert stored == joined
        assert stored.reason == "rfq_accept"


class TestTheOtherWritersStoreTheReadsAnswer:
    LEGS = [{"ticker": "M1", "side": "yes", "label": "Leg one"}]

    def _hand(self, conn, **kw):
        defaults = dict(
            now_ms=1_000, source="kalshi_combo", label="Typed slip",
            stake_tenths=5_000, return_tenths=20_000, legs=self.LEGS,
        )
        defaults.update(kw)
        return positions.record_hand_entry(conn, **defaults)

    @pytest.mark.parametrize(
        "kw, reason",
        [
            ({"source": "sportsbook", "book": "DK"}, "not_a_kalshi_combo"),
            ({}, "hand_recorded_position"),
        ],
        ids=["sportsbook", "kalshi-no-key"],
    )
    def test_a_typed_slip(self, conn, kw, reason):
        self._hand(conn, **kw)
        row = _positions(conn)[0]
        assert row["fill_source"] == positions.FILL_HAND
        assert row["fill_ref"] is None
        stored, joined = _stored_then_joined(conn)
        assert stored == joined
        assert stored.reason == reason

    def test_a_typed_combo_with_the_orders_key_leaves_the_join_to_decide(self, conn):
        self._hand(conn, combo_ticker="KXMVE-X", placed_ms=1_500)
        row = _positions(conn)[0]
        assert row["fill_source"] == positions.FILL_HAND
        assert row["stake_basis"] is None
        basis = hedge.stake_bases(conn, [row])[int(row["id"])]
        assert basis.reason == "no_order_row"

    def test_an_adopted_holding(self, conn):
        positions.record_adopted(
            conn, now_ms=1_000, label="Adopted", stake_tenths=4_000,
            return_tenths=10_000, legs=self.LEGS, combo_ticker="KXMVE-Y",
            note=hedge.ADOPTED_NOTE_MARKER + " from the venue",
        )
        row = _positions(conn)[0]
        assert row["fill_source"] == positions.FILL_ADOPTED
        stored, joined = _stored_then_joined(conn)
        assert stored == joined
        assert stored.basis == hedge.STAKE_BASIS_VENUE_EXPOSURE


@pytest.fixture()
def order_conn(tmp_path):
    """A database holding the priced lookup the order path recovers legs from."""
    path = tmp_path / "orders.db"
    connection = db.init_db(path)
    _seed_lookup(path)
    yield connection
    connection.close()


def _order_fill(conn, *, filled=4.0, write_order=True, **order_kw):
    order_id = (
        an_order(conn, ticker=ORDER_COMBO, submitted_ms=1_500, **order_kw)
        if write_order
        else 999
    )
    result = positions.record_order_fill(
        conn, manual_order_id=order_id, ticker=ORDER_COMBO, filled=filled,
        sent_price_tenths=SENT_TENTHS, now_ms=2_000, placed_ms=1_500,
    )
    return order_id, result.position_id


class TestAnOrderFillStoresWhatTheJoinWouldHaveRead:
    """S2 (#265, ADR 0192 §2.3–§2.5): the armed path's position, decided by
    the read's own function on this order's row, read by id."""

    @pytest.mark.parametrize(
        "kw, basis, reason, stake",
        [
            ({}, hedge.STAKE_BASIS_VENUE_FILL, None, 4 * VENUE_TENTHS),
            (
                {"filled": 2.5, "venue_count": 2.5},
                hedge.STAKE_BASIS_VENUE_FILL, None, round(2.5 * VENUE_TENTHS),
            ),
            (
                {"venue_price": None},
                hedge.STAKE_BASIS_AS_RECORDED, "no_venue_price", 4 * SENT_TENTHS,
            ),
            (
                {"venue_count": None},
                hedge.STAKE_BASIS_AS_RECORDED, "no_venue_fill_count", 4 * SENT_TENTHS,
            ),
            (
                {"side": "no"},
                hedge.STAKE_BASIS_AS_RECORDED, "side_convention_unresolved",
                4 * SENT_TENTHS,
            ),
            (
                {"write_order": False},
                hedge.STAKE_BASIS_AS_RECORDED, "no_order_row", 4 * SENT_TENTHS,
            ),
        ],
        ids=["venue-fill", "fraction-2.5", "no-price", "no-count", "no-side", "no-row"],
    )
    def test_stored_equals_joined(self, order_conn, kw, basis, reason, stake):
        order_id, position_id = _order_fill(order_conn, **kw)
        assert position_id is not None
        row = _positions(order_conn)[0]
        assert row["fill_source"] == positions.FILL_MANUAL_ORDER
        assert row["fill_ref"] == order_id
        stored, joined = _stored_then_joined(order_conn)
        assert stored == joined
        assert (stored.basis, stored.reason, stored.stake_tenths) == (
            basis, reason, stake,
        )

    def test_a_tiny_fraction_is_refused_for_its_size_not_its_legs(
        self, order_conn
    ):
        """0.01 of a contract at 95.0c: the stake rounds to the return, the
        ticket check refuses it, and the reason travels back so the screen
        does not blame the legs."""
        an_order(
            order_conn, ticker=ORDER_COMBO, submitted_ms=1_500,
            venue_count=0.01, venue_price=950,
        )
        result = positions.record_order_fill(
            order_conn, manual_order_id=1, ticker=ORDER_COMBO, filled=0.01,
            sent_price_tenths=950, now_ms=2_000, placed_ms=1_500,
        )
        assert result.position_id is None
        assert result.refused
        assert _positions(order_conn) == []

    def test_a_count_finer_than_the_table_writes_nothing(self, order_conn):
        _, position_id = _order_fill(order_conn, filled=2.5005, venue_count=2.5005)
        assert position_id is None
        assert _positions(order_conn) == []

    @pytest.mark.parametrize("count", [2.5, 4.0, 60.97, 8.22])
    def test_a_holdable_count_is_whole_tenths(self, count):
        assert positions.holdable_count(count)

    @pytest.mark.parametrize("count", [2.5005, 0, -1, None, float("nan")])
    def test_an_unholdable_count_is_refused(self, count):
        assert not positions.holdable_count(count)


class TestAStoredBasisIsWhatTheScreenReads:
    async def test_a_later_change_to_the_quote_row_does_not_move_it(self, conn):
        """The id link makes the stored basis the answer. The join would now
        call this row a gap (`no_order_row`, a dry-run quote never explains a
        stake); the stored basis, decided when the fill happened, does not
        change with it."""
        await _accept(conn, FakeApi(statuses=["executed"], fills=[_fill_at("9.00")]))
        conn.execute("UPDATE combo_rfq_quotes SET accept_dry_run = 1")
        conn.commit()
        row = _positions(conn)[0]
        basis = hedge.stake_bases(conn, [row])[int(row["id"])]
        assert basis.basis == hedge.STAKE_BASIS_VENUE_FILL
        _as_pre_v60(conn)
        joined = hedge.stake_bases(conn, _positions(conn))[int(row["id"])]
        assert joined.reason == "no_order_row"


class TestARowWithNoStoredBasisIsServedByTheJoin:
    def test_the_order_paths_shape_is_unchanged(self, conn):
        """What `routes._record_combo_position` writes until #265: a formed
        key, no provenance. The join answers, exactly as before v60."""
        hedge.record_position(
            conn, now_ms=1_000, source="kalshi_combo", label="Bought",
            stake_tenths=5_000, return_tenths=10_000,
            legs=[{"ticker": "M1", "side": "yes", "label": "Leg"}],
            placed_ms=1_234, combo_ticker="KXMVE-Z",
        )
        row = _positions(conn)[0]
        assert row["fill_source"] is None and row["stake_basis"] is None
        assert hedge.stake_bases(conn, [row])[int(row["id"])] == hedge.stake_basis_for(
            row, None
        )


class TestTheRfqWriterNeverRaises:
    def test_a_broken_connection_returns_none(self, conn):
        quote = conn.execute("SELECT * FROM combo_rfq_quotes").fetchone()
        broken = sqlite3.connect(":memory:")
        broken.row_factory = sqlite3.Row
        assert (
            positions.record_rfq_accept(
                broken, rfq_id=RFQ, quote=quote, now_ms=2_000, venue=None
            )
            is None
        )


def _production_files():
    for base in ("backend", "scripts"):
        for path in (ROOT / base).rglob("*.py"):
            yield path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8")


def _code(text: str) -> str:
    """Python source without comments or triple-quoted strings, so a sentence
    that NAMES the function is not counted as a call to it."""
    text = re.sub(r'"""[\s\S]*?"""', "", text)
    return "\n".join(
        line.split("#")[0] for line in text.splitlines()
    )


class TestOneWriter:
    def test_only_the_positions_module_calls_record_position(self):
        callers = {
            rel
            for rel, text in _production_files()
            if re.search(r"(?<!def )\brecord_position\(", _code(text))
        }
        assert callers - RECORD_POSITION_ALLOWED == set()
        assert "backend/positions.py" in callers

    def test_only_hedge_inserts_into_the_position_tables(self):
        inserters = {
            rel
            for rel, text in _production_files()
            if re.search(r"INSERT\s+INTO\s+parlay_position(s|_legs)\b", text)
        }
        assert inserters <= {"backend/hedge.py", "backend/store/db.py"}
