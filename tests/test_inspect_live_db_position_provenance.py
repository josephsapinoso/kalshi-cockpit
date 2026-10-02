"""`position-provenance` -- the read #268 needs: `parlay_positions`' stored
provenance (`fill_source`, `fill_ref`, `stake_basis`) beside the
`manual_orders` row `fill_ref` names (ADR 0192). `/api/hedge` serves
`stake_basis` but neither provenance column.

What these tests establish
---------------------------
- A `manual_order` position is joined to the order its `fill_ref` names, and
  that order's venue fill columns travel beside it.
- The join keys on `fill_ref` only: a hand-recorded position whose
  `combo_ticker` matches an order still shows no order (no ticker fallback).
- Newest first by id, and `-n` bounds it.
- The QueryDef carries `cost=CHEAP`.

What these tests do NOT establish
----------------------------------
- **Nothing about live.** Every row is seeded here, against the real schema
  (`backend/store/schema.sql` run by `db.init_db`).
"""

from __future__ import annotations

from scripts.inspect_live_db import CHEAP, QUERIES
from backend.store import db

TICKER = "KXMVECROSSCATEGORY-S0-TEST"


def _args(**kw):
    class A:
        limit = 100
        tail = 5

    a = A()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _seeded(tmp_path):
    path = tmp_path / "prov.db"
    conn = db.init_db(path)
    conn.execute(
        "INSERT INTO manual_orders (id, client_order_id, submitted_ms, ticker,"
        " side, action, count, limit_price_tenths, max_price_tenths, status,"
        " request_body_json, dry_run, venue_fill_count,"
        " venue_avg_fill_price_tenths)"
        " VALUES (9, 'cid-9', 1000, ?, 'yes', 'buy', 10, 380, 400, 'filled',"
        " '{}', 0, 10.0, 378)",
        (TICKER,),
    )
    rows = [
        # id, combo_ticker, fill_source, fill_ref, stake_basis
        (1, TICKER, None, None, None),
        (2, TICKER, "manual_order", 9, "venue_fill"),
        (3, TICKER, "hand", None, "as_recorded"),
        # an RFQ fill whose ref happens to equal an order id: not an order
        (4, TICKER, "rfq_quote", 9, "venue_fill"),
    ]
    for pid, combo, src, ref, basis in rows:
        conn.execute(
            "INSERT INTO parlay_positions (id, created_ms, placed_ms, source,"
            " label, stake_tenths, return_tenths, status, combo_ticker,"
            " fill_source, fill_ref, stake_basis)"
            " VALUES (?, ?, ?, 'kalshi_combo', 'p', 3780, 19600, 'open', ?,"
            " ?, ?, ?)",
            (pid, 1000 + pid, 1000 + pid, combo, src, ref, basis),
        )
    conn.commit()
    conn.close()
    return path


def _run(path, **kw):
    conn = db.connect(path)
    try:
        (section,) = QUERIES["position-provenance"].run(conn, _args(**kw))
        return section
    finally:
        conn.close()


def _by_id(section):
    cols = section.columns
    return {r[cols.index("id")]: dict(zip(cols, r)) for r in section.rows}


class TestPositionProvenance:
    def test_is_cheap(self):
        assert QUERIES["position-provenance"].cost is CHEAP

    def test_a_manual_order_position_carries_the_order_its_fill_ref_names(
        self, tmp_path
    ):
        row = _by_id(_run(_seeded(tmp_path)))[2]
        assert row["fill_source"] == "manual_order"
        assert row["fill_ref"] == row["order_id"] == 9
        assert row["stake_basis"] == "venue_fill"
        assert row["venue_avg_fill_price_tenths"] == 378
        assert row["order_dry_run"] == 0

    def test_the_join_does_not_fall_back_to_the_ticker(self, tmp_path):
        rows = _by_id(_run(_seeded(tmp_path)))
        assert rows[1]["order_id"] is None
        assert rows[3]["order_id"] is None
        assert rows[4]["order_id"] is None

    def test_newest_first_and_tail_bounds_it(self, tmp_path):
        section = _run(_seeded(tmp_path), tail=2)
        ids = [r[section.columns.index("id")] for r in section.rows]
        assert ids == [4, 3]
