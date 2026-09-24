"""`combo-rfqs` and `leg-scout-state` -- durable reads for two records no
instrument could previously see (#149).

`combo-rfqs` lists `combo_rfqs` rows newest-`requested_ms`-first, the read
that audits an RFQ ask (or exit ask) seen only from Joe's own screen --
including the sell-quote tap he made on 2026-09-24. `leg-scout-state` counts
`parlay_position_legs.scout_state` per budget day, joined to `parlay_positions`
for the position's own timestamp, bounded to positions created on or after
2026-09-21T10:00Z (when unattended scouting, #116/#118, went live).

What these tests establish
---------------------------
- `combo-rfqs` lists newest `requested_ms` first, and `-n` bounds it.
- `combo-rfqs` never prints `selected_legs`.
- `leg-scout-state` groups by budget day across the 10:00Z boundary: a leg
  whose position was created at 09:59Z and one created at 10:01Z the same
  UTC calendar day land in different budget-day buckets.
- `leg-scout-state` prints a NULL `scout_state` as its own labelled bucket
  ('NULL'), never folded into another bucket and never dropped.
- `leg-scout-state` excludes a position created before the 2026-09-21T10:00Z
  bound.
- Both QueryDefs carry `cost=CHEAP`.

What these tests do NOT establish
----------------------------------
- **Nothing about live.** Every row here is seeded in this file against a
  real schema-initialised SQLite database (`backend/store/schema.sql` run
  verbatim by `db.init_db`), not a hand-written stand-in schema.
- **Nothing about whether scouting reaches Joe before he bets.**
  `scout_state` records what the lookup found at record time; these tests
  only establish that the column's states are counted and bucketed
  correctly, never that a "briefed" bucket means anything was read.
- **No aggregate, no rate, for either query.** Only counts and dumps.
"""

from __future__ import annotations

from scripts.inspect_live_db import CHEAP, QUERIES
from backend.store import db


def _args(**kw):
    class A:
        limit = 100
        tail = 5
        day_start_hour = 10

    a = A()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _seeded_db(tmp_path, name="combo_rfqs_and_scout.db"):
    path = tmp_path / name
    conn = db.init_db(path)
    conn.commit()
    conn.close()
    return path


def _run(path, name, **kw):
    conn = db.connect(path)
    try:
        return QUERIES[name].run(conn, _args(**kw))
    finally:
        conn.close()


def _section(sections, title_contains):
    for s in sections:
        if title_contains in s.title:
            return s
    raise AssertionError(
        f"no section titled like {title_contains!r} among "
        f"{[s.title for s in sections]}"
    )


def _col(section, name):
    """Rows are tuples -- index by declared column name so a reordered
    SELECT cannot silently move an assertion onto another column."""
    i = section.columns.index(name)
    return [r[i] for r in section.rows]


def _insert_rfq(conn, *, rfq_id, requested_ms, ticker="KXMVE-TEST-1", status="quoted",
                 exchange_index=1, target_cost_dollars="1.00", contracts_requested=None,
                 fair_joint=0.5, book_yes_ask_tenths=None, quote_count=1,
                 refused_too_fine=None, selected_legs='[{"a": 1}]'):
    conn.execute(
        "INSERT INTO combo_rfqs (rfq_id, requested_ms, ticker, "
        "collection_ticker, selected_legs, exchange_index, "
        "target_cost_dollars, contracts_requested, fair_joint, "
        "book_yes_ask_tenths, quote_count, refused_too_fine, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rfq_id, requested_ms, ticker, "KXMVE-COLLECTION", selected_legs,
            exchange_index, target_cost_dollars, contracts_requested,
            fair_joint, book_yes_ask_tenths, quote_count, refused_too_fine,
            status,
        ),
    )


class TestBothQueriesAreCheap:
    def test_combo_rfqs_is_cheap(self):
        """Mutation: flip the entry to `cost=WALKS_THE_FILE` -- red."""
        assert QUERIES["combo-rfqs"].cost == CHEAP

    def test_leg_scout_state_is_cheap(self):
        """Mutation: flip the entry to `cost=WALKS_THE_FILE` -- red."""
        assert QUERIES["leg-scout-state"].cost == CHEAP


class TestComboRfqsListsNewestFirst:
    def test_newest_first(self, tmp_path):
        """Mutation: drop `DESC` from `ORDER BY requested_ms` -- red,
        ordering inverts."""
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        _insert_rfq(conn, rfq_id="rfq-older", requested_ms=1_700_000_000_000)
        _insert_rfq(conn, rfq_id="rfq-newer", requested_ms=1_700_000_500_000)
        conn.commit()
        conn.close()

        sections = _run(path, "combo-rfqs")
        section = sections[0]
        requested = _col(section, "requested_ms")
        assert requested[0] > requested[1]

    def test_n_bounds_combo_rfqs(self, tmp_path):
        """Mutation: pass `requested=None` instead of the computed `n` to
        `_fetch` -- red, all rows returned regardless of -n."""
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        for i in range(5):
            _insert_rfq(
                conn,
                rfq_id=f"rfq-{i}",
                requested_ms=1_700_000_000_000 + i,
            )
        conn.commit()
        conn.close()

        sections = _run(path, "combo-rfqs", tail=2)
        assert sections[0].row_count == 2

    def test_an_explicit_n_of_five_returns_five(self, tmp_path):
        """`-n 5` means five. The lane's first cut read the shared default
        of 5 as "unset" and silently served 20 instead of what was typed."""
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        for i in range(8):
            _insert_rfq(
                conn,
                rfq_id=f"rfq-default-{i}",
                requested_ms=1_700_000_000_000 + i,
            )
        conn.commit()
        conn.close()

        sections = _run(path, "combo-rfqs", tail=5)
        assert sections[0].row_count == 5

    def test_purpose_tells_an_exit_ask_from_a_buy(self, tmp_path):
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        _insert_rfq(conn, rfq_id="rfq-exit", requested_ms=1_700_000_000_002)
        conn.execute("UPDATE combo_rfqs SET purpose = 'exit' WHERE rfq_id = 'rfq-exit'")
        conn.commit()
        conn.close()

        section = _run(path, "combo-rfqs", tail=5)[0]
        assert "purpose" in section.columns
        assert section.rows[0][section.columns.index("purpose")] == "exit"

    def test_a_larger_n_than_rows_returns_everything(self, tmp_path):
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        _insert_rfq(conn, rfq_id="rfq-only", requested_ms=1_700_000_000_000)
        conn.commit()
        conn.close()

        sections = _run(path, "combo-rfqs", tail=100)
        assert sections[0].row_count == 1

    def test_requested_ms_is_rendered_as_iso(self, tmp_path):
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        _insert_rfq(conn, rfq_id="rfq-iso", requested_ms=1_700_000_000_000)
        conn.commit()
        conn.close()

        sections = _run(path, "combo-rfqs")
        section = sections[0]
        assert "requested_iso" in section.columns
        assert _col(section, "requested_iso") == ["2023-11-14T22:13:20Z"]

    def test_the_named_columns_are_present(self, tmp_path):
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        _insert_rfq(
            conn,
            rfq_id="rfq-cols",
            requested_ms=1_700_000_000_000,
            ticker="KXMVE-COLS",
            status="quoted",
            exchange_index=1,
            target_cost_dollars="2.50",
            fair_joint=0.62,
            book_yes_ask_tenths=650,
            quote_count=3,
            refused_too_fine=1,
        )
        conn.commit()
        conn.close()

        sections = _run(path, "combo-rfqs")
        section = sections[0]
        for expected in (
            "id", "requested_ms", "ticker", "exchange_index",
            "target_cost_dollars", "contracts_requested", "fair_joint",
            "book_yes_ask_tenths", "quote_count", "refused_too_fine",
            "status",
        ):
            assert expected in section.columns, expected
        assert _col(section, "ticker") == ["KXMVE-COLS"]
        assert _col(section, "status") == ["quoted"]
        assert _col(section, "quote_count") == [3]
        assert _col(section, "refused_too_fine") == [1]


class TestComboRfqsNeverPrintsSelectedLegs:
    def test_selected_legs_is_not_in_the_output(self, tmp_path):
        """Mutation: add `selected_legs` to the SELECT list in
        `_SQL_COMBO_RFQS` -- red, the forbidden column appears."""
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        _insert_rfq(
            conn,
            rfq_id="rfq-legs",
            requested_ms=1_700_000_000_000,
            selected_legs='[{"event_ticker": "SECRET-EVENT"}]',
        )
        conn.commit()
        conn.close()

        sections = _run(path, "combo-rfqs")
        for section in sections:
            assert "selected_legs" not in section.columns
            for row in section.rows:
                for cell in row:
                    if isinstance(cell, str):
                        assert "SECRET-EVENT" not in cell


class TestLegScoutStateGroupsByBudgetDay:
    def _insert_position_with_leg(
        self, conn, *, created_ms, scout_state, label="a leg"
    ):
        cur = conn.execute(
            "INSERT INTO parlay_positions (created_ms, source, label, "
            "stake_tenths, return_tenths, status) VALUES (?, ?, ?, ?, ?, ?)",
            (created_ms, "kalshi_combo", label, 1000, 2000, "open"),
        )
        position_id = cur.lastrowid
        conn.execute(
            "INSERT INTO parlay_position_legs (position_id, leg_index, "
            "side, label, outcome, scout_state) VALUES (?, ?, ?, ?, ?, ?)",
            (position_id, 0, "yes", label, "pending", scout_state),
        )
        return position_id

    def test_a_leg_before_and_after_the_ten_oclock_boundary_land_in_different_days(
        self, tmp_path
    ):
        """Mutation: change the offset sign to `+` (`p.created_ms +
        :offset_ms`) in `_SQL_LEG_SCOUT_STATE` -- red, both land in the
        same budget_day.

        Uses 2026-09-22T09:59:00Z and 2026-09-22T10:01:00Z -- a pair
        straddling a 10:00Z boundary comfortably after the
        2026-09-21T10:00Z floor this query is bounded to.
        """
        before_ms = 1_790_071_140_000  # 2026-09-22T09:59:00Z
        after_ms = 1_790_071_260_000  # 2026-09-22T10:01:00Z
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        self._insert_position_with_leg(
            conn, created_ms=before_ms, scout_state="briefed", label="before"
        )
        self._insert_position_with_leg(
            conn, created_ms=after_ms, scout_state="briefed", label="after"
        )
        conn.commit()
        conn.close()

        sections = _run(path, "leg-scout-state")
        section = sections[0]
        days = _col(section, "budget_day")
        assert len(set(days)) == 2, days

    def test_null_scout_state_is_its_own_labelled_bucket(self, tmp_path):
        """Mutation: change `COALESCE(l.scout_state, 'NULL')` to plain
        `l.scout_state` -- red, the bucket's label becomes Python `None`
        rather than the string `'NULL'` (still technically groupable, but
        the ticket requires the labelled string, and a reader comparing
        against `'NULL'` would silently see nothing)."""
        created_ms = 1_790_100_000_000  # well after the 2026-09-21 floor
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        self._insert_position_with_leg(
            conn, created_ms=created_ms, scout_state=None, label="adopted"
        )
        conn.commit()
        conn.close()

        sections = _run(path, "leg-scout-state")
        section = sections[0]
        assert "NULL" in _col(section, "scout_state")
        assert _col(section, "n")[
            _col(section, "scout_state").index("NULL")
        ] == 1

    def test_null_is_not_folded_into_absent(self, tmp_path):
        """A NULL row and an 'absent' row must be counted as two distinct
        buckets, never merged into one."""
        created_ms = 1_790_100_000_000
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        self._insert_position_with_leg(
            conn, created_ms=created_ms, scout_state=None, label="null-one"
        )
        self._insert_position_with_leg(
            conn, created_ms=created_ms, scout_state="absent", label="absent-one"
        )
        conn.commit()
        conn.close()

        sections = _run(path, "leg-scout-state")
        section = sections[0]
        states = _col(section, "scout_state")
        assert "NULL" in states
        assert "absent" in states
        n_by_state = dict(zip(states, _col(section, "n")))
        assert n_by_state["NULL"] == 1
        assert n_by_state["absent"] == 1

    def test_a_row_before_the_bound_is_excluded(self, tmp_path):
        """Mutation: change `p.created_ms >= :since_ms` to `>` a much
        earlier constant, or drop the WHERE clause entirely -- red, the
        pre-bound row leaks into the count."""
        before_bound_ms = 1_789_984_800_000 - 60_000  # one minute early
        after_bound_ms = 1_789_984_800_000 + 60_000  # one minute late
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        self._insert_position_with_leg(
            conn, created_ms=before_bound_ms, scout_state="briefed",
            label="too-early",
        )
        self._insert_position_with_leg(
            conn, created_ms=after_bound_ms, scout_state="briefed",
            label="just-in",
        )
        conn.commit()
        conn.close()

        sections = _run(path, "leg-scout-state")
        section = sections[0]
        total_n = sum(_col(section, "n"))
        assert total_n == 1

    def test_no_ratio_no_rate_columns(self, tmp_path):
        """The output carries only budget_day, scout_state and a count --
        no derived quantity of any kind."""
        created_ms = 1_790_100_000_000
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        self._insert_position_with_leg(
            conn, created_ms=created_ms, scout_state="briefed"
        )
        conn.commit()
        conn.close()

        sections = _run(path, "leg-scout-state")
        assert len(sections) == 1
        assert sections[0].columns == ("budget_day", "scout_state", "n")
