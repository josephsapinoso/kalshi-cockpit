"""Reading the whole evidence record, soundly, while it is being written to.

`/api/ledger` capped at the newest 1,000 rows of 1,535, so every rate computed
off it described a slice -- and `engine.persist_if_changed` writes a row only
when the ask or the fair *moved*, so rows-per-game tracks price volatility and
that slice is weighted toward volatile, wide-disagreement games. That is the
direction that inflates an apparent edge, which is why paging is a prerequisite
for a decisive measurement rather than a convenience.

**But `offset` alone makes it worse, not better**, and that is what most of this
file is about. The route sorts newest-first, so a row written *during* a
multi-page pull lands on page 0 and shifts every later page along. Measured on
the live record 2026-08-10: one `created_ms` carries **84 rows**, because a
sweep writes its whole slate at one instant. A pull that walks four pages
through one such sweep comes back with a quarter of its rows duplicated and 84
rows of the table simply absent -- while `returned`, `limit` and `total` all
still add up, so nothing in the payload contradicts it.

**What these tests do not establish.** They assert that a whole-table pull is
*complete and duplicate-free*, and that the four devig readings reach a caller.
They say nothing about whether the record is any good, nothing about what the
devig methods imply, and nothing about the ordering being stable across SQLite
versions -- only that it is a total order, which is the property that makes the
question moot.
"""

from __future__ import annotations

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db

# Three sweeps, every row inside a sweep sharing one `created_ms`, because that
# is what the live table looks like: 1,000 rows across 169 distinct timestamps.
# A fixture with unique timestamps would make every test here pass vacuously.
_SWEEPS = 3
_ROWS_PER_SWEEP = 12
_TOTAL = _SWEEPS * _ROWS_PER_SWEEP


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


def _insert_sweep(conn, created_ms: int, n: int, *, with_fair: bool = True) -> None:
    for k in range(n):
        ticker = f"KXTEST-{created_ms}-{k:02d}"
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_markets (ticker, first_seen_ms, "
            "last_seen_ms) VALUES (?, ?, ?)",
            (ticker, 1000, 1000),
        )
        fair_price_id = None
        if with_fair:
            cur = conn.execute(
                "INSERT INTO fair_prices (computed_ms, link_id, market, "
                "outcome_name, p_multiplicative, p_additive, p_power, p_shin, "
                "p_conservative, book_count, books_used) "
                "VALUES (?, 1, 'h2h', 'Team', ?, ?, ?, ?, ?, 3, '[]')",
                (created_ms, 0.55, 0.54, 0.53, 0.56, 0.52),
            )
            fair_price_id = cur.lastrowid
        conn.execute(
            "INSERT INTO recommendations (created_ms, strategy_config_version, "
            "ticker, fair_price_id, side, entry_ask_tenths, fair_probability, "
            "edge_tenths, fee_predicted, ev_net_dollars, kelly_fraction, "
            "suggested_contracts, reference_contracts, kalshi_quote_age_ms, "
            "odds_age_ms, reason_text) "
            "VALUES (?, 1, ?, ?, 'yes', 500, 0.52, 5.0, 0.1, 0.2, 0.01, 0, 0, "
            "1000, 2000, 'test row')",
            (created_ms, ticker, fair_price_id),
        )


@pytest.fixture
def paged_db(tmp_path):
    path = tmp_path / "paged.db"
    conn = db.init_db(path)
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    # `fair_prices.link_id` FKs to `event_links`, which FKs to `kalshi_events`.
    # Built rather than stubbed with a bare integer, so the join under test is
    # the same one production makes.
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, first_seen_ms, last_seen_ms) "
        "VALUES ('KXTEST-EVENT', 1000, 1000)"
    )
    conn.execute(
        "INSERT INTO event_links (id, kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES (1, 'KXTEST-EVENT', 'odds-1', 'baseball_mlb', "
        "'exact_alias_pair', 0, 1000)"
    )
    for s in range(_SWEEPS):
        _insert_sweep(conn, 1000 + s, _ROWS_PER_SWEEP)
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def paged_app(paged_db):
    return create_app(AppConfig(instance_mode="demo", db_path=paged_db))


async def _walk(app, *, page: int, pin: bool):
    """Page the ledger to exhaustion the way a whole-table pull would."""
    first = (await get(app, f"/api/ledger?limit={page}&offset=0")).json()
    max_id = first["newest_id"] if pin else None
    suffix = f"&max_id={max_id}" if pin else ""
    ids, offset = [], 0
    while True:
        body = (await get(app, f"/api/ledger?limit={page}&offset={offset}{suffix}")).json()
        ids += [r["id"] for r in body["rows"]]
        offset += page
        if offset >= body["total"]:
            return ids, body


class TestTheTableCanBeReadWhole:
    async def test_paging_returns_every_row_exactly_once(self, paged_app):
        ids, body = await _walk(paged_app, page=5, pin=False)
        assert body["total"] == _TOTAL
        assert sorted(ids) == list(range(1, _TOTAL + 1))

    async def test_offset_past_the_end_is_empty_rather_than_an_error(self, paged_app):
        body = (await get(paged_app, f"/api/ledger?offset={_TOTAL + 50}")).json()
        assert body["rows"] == []
        assert body["returned"] == 0
        assert body["total"] == _TOTAL

    async def test_the_payload_says_which_page_it_is(self, paged_app):
        """`total`, `returned` and `limit` cannot tell page 0 from page 0 twice."""
        body = (await get(paged_app, "/api/ledger?limit=5&offset=10")).json()
        assert body["offset"] == 10
        assert body["limit"] == 5


class TestTheOrderingIsATotalOrder:
    """Ties are the normal case, so the order within one must be defined.

    [MEASURED, live, 2026-08-10] the newest 1,000 rows carry 169 distinct
    `created_ms` values and 960 of them tie with at least one other row.

    No corruption is claimed on a static table -- measured directly, the
    untied query pages consistently today because the planner happens to scan
    `idx_recs_created`. The point is that it *happens to*: adding the
    `fair_prices` join already changed the plan, and a paging contract that
    holds only while a plan holds is one optimiser change from being wrong.
    """

    async def test_the_whole_pull_strictly_decreases_on_created_ms_then_id(
        self, paged_app
    ):
        ids, _ = await _walk(paged_app, page=5, pin=False)
        rows = (await get(paged_app, f"/api/ledger?limit={_TOTAL}")).json()["rows"]
        keys = [(r["created_ms"], r["id"]) for r in rows]
        assert len(keys) == _TOTAL
        assert all(a > b for a, b in zip(keys, keys[1:])), (
            "the ordering has a tie in it, so which row lands on which page is "
            "whatever the query planner chose today"
        )

    async def test_newest_first_holds_inside_a_sweep_too(self, paged_app):
        """Under `created_ms DESC` alone a sweep came back oldest-id-first."""
        rows = (await get(paged_app, f"/api/ledger?limit={_TOTAL}")).json()["rows"]
        newest_sweep = [r for r in rows if r["created_ms"] == 1000 + _SWEEPS - 1]
        assert len(newest_sweep) == _ROWS_PER_SWEEP
        assert [r["id"] for r in newest_sweep] == sorted(
            (r["id"] for r in newest_sweep), reverse=True
        )


class TestAPullSurvivesTheRecorderWritingUnderIt:
    """The failure `offset` introduces, and the pin that removes it.

    This is the test the feature exists for. Without `max_id` a whole-table
    pull taken during an active slate is a *different multiset* from the table,
    and every consistency check the payload supports still passes.
    """

    @staticmethod
    def _sweep_in(paged_db, created_ms: int, n: int) -> None:
        conn = db.connect(paged_db)
        _insert_sweep(conn, created_ms, n)
        conn.commit()
        conn.close()

    async def test_an_unpinned_pull_duplicates_and_drops_rows(
        self, paged_app, paged_db
    ):
        page = 5
        ids = []
        offset = 0
        while True:
            body = (
                await get(paged_app, f"/api/ledger?limit={page}&offset={offset}")
            ).json()
            ids += [r["id"] for r in body["rows"]]
            if offset == 0:
                # A sweep lands mid-pull. On live this is one poll of the slate.
                self._sweep_in(paged_db, 9999, _ROWS_PER_SWEEP)
            offset += page
            if offset >= _TOTAL:
                break

        assert len(ids) > len(set(ids)), (
            "the unpinned pull must duplicate rows -- if it does not, this test "
            "is not exercising the hazard the pin exists for"
        )
        assert set(range(1, _TOTAL + 1)) - set(ids), (
            "and it must also lose rows that were in the table the whole time"
        )

    async def test_a_pinned_pull_is_complete_and_duplicate_free(
        self, paged_app, paged_db
    ):
        page = 5
        first = (await get(paged_app, "/api/ledger?limit=1")).json()
        pin = first["newest_id"]
        assert pin == _TOTAL

        ids = []
        offset = 0
        while True:
            body = (
                await get(
                    paged_app, f"/api/ledger?limit={page}&offset={offset}&max_id={pin}"
                )
            ).json()
            ids += [r["id"] for r in body["rows"]]
            if offset == 0:
                self._sweep_in(paged_db, 9999, _ROWS_PER_SWEEP)
            offset += page
            if offset >= body["total"]:
                break

        assert sorted(ids) == list(range(1, _TOTAL + 1))

    async def test_the_total_is_counted_under_the_pin(self, paged_app, paged_db):
        """Otherwise paging to `total` walks a target that keeps moving."""
        pin = _TOTAL
        self._sweep_in(paged_db, 9999, _ROWS_PER_SWEEP)
        body = (await get(paged_app, f"/api/ledger?limit=1&max_id={pin}")).json()
        assert body["total"] == _TOTAL
        unpinned = (await get(paged_app, "/api/ledger?limit=1")).json()
        assert unpinned["total"] == _TOTAL + _ROWS_PER_SWEEP

    async def test_newest_id_reports_the_table_not_the_snapshot(
        self, paged_app, paged_db
    ):
        """`newest_id > max_id` is how a caller sees the pin did something."""
        self._sweep_in(paged_db, 9999, _ROWS_PER_SWEEP)
        body = (await get(paged_app, f"/api/ledger?limit=1&max_id={_TOTAL}")).json()
        assert body["max_id"] == _TOTAL
        assert body["newest_id"] == _TOTAL + _ROWS_PER_SWEEP
        assert body["newest_id"] > body["max_id"]

    async def test_an_unpinned_response_says_it_is_unpinned(self, paged_app):
        body = (await get(paged_app, "/api/ledger?limit=1")).json()
        assert body["max_id"] is None


class TestAllFourDevigReadingsReachTheCaller:
    """`fair_probability` is the *lowest* method, and that is a policy choice.

    `devig.conservative_probability` takes the min across methods for the side
    being bought. A downward bias on fair value mechanically produces
    `edge <= 0`, so with only that column on the payload no consumer can
    separate "Kalshi is sharp" from "we chose a low fair" -- which is the whole
    question behind `actionable = 0`.
    """

    async def test_the_four_methods_are_on_the_row(self, paged_app):
        row = (await get(paged_app, "/api/ledger?limit=1")).json()["rows"][0]
        assert row["p_multiplicative"] == 0.55
        assert row["p_additive"] == 0.54
        assert row["p_power"] == 0.53
        assert row["p_shin"] == 0.56

    async def test_the_conservative_reading_travels_so_the_join_can_be_checked(
        self, paged_app
    ):
        """`p_conservative` should equal `fair_probability` on every row.

        Sent so a consumer can *check* the `fair_price_id` join landed on the
        right row rather than assume it. A join to the wrong `fair_prices` row
        would still return four plausible probabilities.
        """
        rows = (await get(paged_app, f"/api/ledger?limit={_TOTAL}")).json()["rows"]
        assert rows
        assert all(r["p_conservative"] == r["fair_probability"] for r in rows)

    async def test_a_row_with_no_fair_price_gets_none_never_zero(
        self, paged_db, paged_app
    ):
        """Zero is a legitimate fair probability, so it cannot mean "missing"."""
        conn = db.connect(paged_db)
        _insert_sweep(conn, 5000, 1, with_fair=False)
        conn.commit()
        conn.close()

        row = (await get(paged_app, "/api/ledger?limit=1")).json()["rows"][0]
        assert row["created_ms"] == 5000, "the unjoined row must be the newest"
        for key in (
            "p_multiplicative",
            "p_additive",
            "p_power",
            "p_shin",
            "p_conservative",
        ):
            assert row[key] is None

    async def test_routes_that_did_not_join_omit_the_keys_entirely(self, paged_app):
        """Not five nulls, which would read as "joined, and empty".

        The Board selects from `recommendations` alone. Emitting the keys as
        `None` there would be indistinguishable from a join that ran and found
        nothing -- the same collapse of two states into one representation this
        repo has been caught by before.
        """
        board = (await get(paged_app, "/api/board?include_suppressed=true")).json()
        every = (
            board["surfaced"] + board["expired"] + board["suppressed"] + board["no_edge"]
        )
        assert every, "the fixture must produce board rows or this proves nothing"
        assert all("p_shin" not in r for r in every)
        assert all("p_conservative" not in r for r in every)
