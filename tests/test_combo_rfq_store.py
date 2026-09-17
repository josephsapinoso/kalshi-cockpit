"""The RFQ record: the only copy of a price nobody else can see.

What these tests do not establish
---------------------------------
- Nothing about whether the venue behaves as recorded. These exercise our
  writes against our schema; the venue's half is pinned by
  `tests/test_combo_rfq.py` against a captured payload.
- Nothing about acceptance, which has never been attempted.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.kalshi.rfq import RfqQuote
from backend.store import combo_rfqs as store

SCHEMA = Path(__file__).parent.parent / "backend" / "store" / "schema.sql"

LEGS = [
    {"event_ticker": "E1", "market_ticker": "M1", "side": "yes"},
    {"event_ticker": "E2", "market_ticker": "M2", "side": "yes"},
]


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA.read_text())
    yield c
    c.close()


def _quote(quote_id: str, no_bid: int, **kw) -> RfqQuote:
    return RfqQuote(
        quote_id=quote_id,
        rfq_id=kw.get("rfq_id", "rfq-1"),
        maker_id=kw.get("maker_id", "maker"),
        market_ticker="KXMVE-X",
        yes_ask_tenths=1000 - no_bid,
        no_bid_tenths=no_bid,
        contracts=kw.get("contracts", 8.19),
        status="open",
        created_ts="2026-09-17T15:50:47.631646Z",
    )


def _ask(conn, **kw):
    store.record_rfq(
        conn, rfq_id=kw.pop("rfq_id", "rfq-1"), requested_ms=1_000,
        ticker="KXMVE-X", collection_ticker="KXMVECROSSCATEGORY-R",
        legs=LEGS, exchange_index=1, **kw,
    )


class TestTheAskIsRecordedBeforeAnyAnswer:
    def test_an_rfq_with_no_quotes_is_still_a_row(self, conn):
        """The RFQ is live at the venue before a quote can arrive.

        If the quote read then fails, the row must still say we asked.
        """
        _ask(conn)
        row = conn.execute("SELECT * FROM combo_rfqs").fetchone()
        assert row["status"] == store.STATUS_ASKED
        assert row["quote_count"] == 0
        assert row["ticker"] == "KXMVE-X"

    def test_the_legs_round_trip_as_json(self, conn):
        import json
        _ask(conn)
        row = conn.execute("SELECT selected_legs FROM combo_rfqs").fetchone()
        assert json.loads(row["selected_legs"]) == LEGS

    def test_an_empty_book_is_recorded_as_null_not_zero(self, conn):
        """NULL means "the book had no ask", which is the NORMAL state.

        Zero would be a price, and a price of zero on the money path is the
        exact confusion `unreadable resolves to None` exists to prevent.
        """
        _ask(conn, book_yes_ask_tenths=None)
        row = conn.execute("SELECT book_yes_ask_tenths FROM combo_rfqs").fetchone()
        assert row["book_yes_ask_tenths"] is None

    def test_asking_twice_with_one_rfq_id_records_one_row(self, conn):
        _ask(conn)
        _ask(conn)
        assert conn.execute("SELECT COUNT(*) FROM combo_rfqs").fetchone()[0] == 1

    def test_an_unknown_status_is_refused_by_the_schema(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            _ask(conn, rfq_id="rfq-bad", status="probably_fine")


class TestTheQuotesAreTheOnlyCopy:
    def test_quotes_are_written_and_counted(self, conn):
        _ask(conn)
        written = store.record_quotes(
            conn, rfq_id="rfq-1",
            quotes=[_quote("q1", 407), _quote("q2", 369)], captured_ms=2_000,
        )
        assert written == 2
        row = conn.execute("SELECT * FROM combo_rfqs").fetchone()
        assert row["quote_count"] == 2
        assert row["status"] == store.STATUS_QUOTED

    def test_the_same_quote_seen_twice_is_one_quote(self, conn):
        """A caller that polls sees each quote on every pass."""
        _ask(conn)
        store.record_quotes(conn, rfq_id="rfq-1", quotes=[_quote("q1", 407)], captured_ms=2_000)
        store.record_quotes(conn, rfq_id="rfq-1", quotes=[_quote("q1", 407)], captured_ms=2_500)
        assert conn.execute("SELECT COUNT(*) FROM combo_rfq_quotes").fetchone()[0] == 1
        assert conn.execute("SELECT quote_count FROM combo_rfqs").fetchone()[0] == 1

    def test_nobody_answering_is_its_own_status(self, conn):
        """`no_quotes` is a fact about the market. It is not an error.

        Collapsing it into `asked` would make "we asked and nobody answered"
        indistinguishable from "we asked and never read the answer".
        """
        _ask(conn)
        store.record_quotes(conn, rfq_id="rfq-1", quotes=[], captured_ms=2_000)
        row = conn.execute("SELECT * FROM combo_rfqs").fetchone()
        assert row["status"] == store.STATUS_NO_QUOTES
        assert row["quote_count"] == 0

    def test_quote_count_comes_from_the_table_not_the_argument(self, conn):
        """A count derived from `len(quotes)` would report writes that failed.

        Two quotes are offered, one of which duplicates a row already stored,
        so the honest stored count is 2 and a naive count would say 3.
        """
        _ask(conn)
        store.record_quotes(conn, rfq_id="rfq-1", quotes=[_quote("q1", 407)], captured_ms=2_000)
        store.record_quotes(
            conn, rfq_id="rfq-1",
            quotes=[_quote("q1", 407), _quote("q2", 369)], captured_ms=2_500,
        )
        assert conn.execute("SELECT quote_count FROM combo_rfqs").fetchone()[0] == 2

    def test_quotes_read_back_cheapest_first(self, conn):
        _ask(conn)
        store.record_quotes(
            conn, rfq_id="rfq-1",
            quotes=[_quote("q1", 369), _quote("q2", 407)], captured_ms=2_000,
        )
        asks = [r["yes_ask_tenths"] for r in store.quotes_for(conn, "rfq-1")]
        assert asks == [593, 631]

    def test_another_rfqs_quotes_are_not_returned(self, conn):
        _ask(conn)
        _ask(conn, rfq_id="rfq-2")
        store.record_quotes(conn, rfq_id="rfq-1", quotes=[_quote("q1", 407)], captured_ms=2_000)
        store.record_quotes(conn, rfq_id="rfq-2", quotes=[_quote("q9", 500)], captured_ms=2_000)
        assert [r["quote_id"] for r in store.quotes_for(conn, "rfq-1")] == ["q1"]


class TestTheWindowIsBounded:
    def test_deleting_stamps_when_the_quotes_became_unreachable(self, conn):
        """After this instant the venue's copy is gone (measured 2026-09-17)."""
        _ask(conn)
        store.mark_deleted(conn, rfq_id="rfq-1", deleted_ms=9_999)
        assert conn.execute("SELECT deleted_ms FROM combo_rfqs").fetchone()[0] == 9_999

    def test_an_error_is_recorded_with_its_words(self, conn):
        _ask(conn)
        store.mark_error(conn, rfq_id="rfq-1", error_text="HTTP 500 from venue")
        row = conn.execute("SELECT * FROM combo_rfqs").fetchone()
        assert row["status"] == store.STATUS_ERROR
        assert "HTTP 500" in row["error_text"]
