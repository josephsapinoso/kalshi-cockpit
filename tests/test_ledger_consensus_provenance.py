"""How much consensus produced a fair value, and whose, on `/api/ledger`.

ADR 0021's closing section records that `market_width`, `book_count` and
`books_used` **were never observed** over the whole 1,564-row record, so two of
the predicates its measurement brief registered went unanswered. The cause was
not a missing join -- the `fair_prices` join has been there since the four devig
readings were added. All three columns live on `fair_prices` rather than on
`recommendations`, so `SELECT r.*` never reached them, and `_serialise` is a
hand-built dict that named none of them. **Two barriers, in two languages, and
either one alone leaves the payload unchanged.**

That is what the first test here is for: it fails if the SQL is narrowed *or* if
the dict is, which is the only shape that can catch a two-barrier defect.

Why the columns matter enough to widen a payload for. ADR 0021 §7.2 is the
strongest argument that the whole refutation is a tautology -- Kalshi tested only
against references plausibly as sharp as Kalshi -- and the magnitude it quotes
("a median of 26 of 29 usable books discarded") is measured on
`tests/fixtures/odds_mlb_h2h_spreads_totals.json`, captured
**2026-08-07T13:49:22Z**, against a record whose earliest odds observation is
**2026-08-07T19:28:12Z**. Zero of 1,564 rows overlap it; the minimum gap is
5.65 hours. These three columns are what let that number be re-measured on the
record instead of borrowed from a fixture.

**What these tests do not establish.** Nothing about whether the anchoring is
*correct*, nothing about what any observed `book_count` implies, and nothing
about the live database -- the deployed record was written before this change
and these columns say nothing retroactively about rows already stored. They
assert only that the two barriers are down and that three states which look
alike stay distinguishable: the join missed, the width was unmeasurable, and the
width was measured as zero.
"""

from __future__ import annotations

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db

_BOOKS = ["betfair_ex_eu", "matchbook", "pinnacle"]


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


def _insert_row(
    conn,
    *,
    created_ms: int,
    market_width,
    book_count: int,
    books_used: str,
    anchored_on_sharp: int = 1,
    with_fair: bool = True,
) -> None:
    ticker = f"KXTEST-{created_ms}"
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
            "p_conservative, market_width, book_count, books_used, "
            "anchored_on_sharp) "
            "VALUES (?, 1, 'h2h', 'Team', 0.55, 0.54, 0.53, 0.56, 0.52, "
            "?, ?, ?, ?)",
            (created_ms, market_width, book_count, books_used, anchored_on_sharp),
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
def provenance_db(tmp_path):
    path = tmp_path / "provenance.db"
    conn = db.init_db(path)
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    # `fair_prices.link_id` FKs to `event_links`, which FKs to `kalshi_events`.
    # Built rather than stubbed, so the join under test is production's join.
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
    # Three books that disagree -- the ordinary case.
    _insert_row(
        conn,
        created_ms=1000,
        market_width=0.031,
        book_count=3,
        books_used='["betfair_ex_eu", "matchbook", "pinnacle"]',
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def provenance_app(provenance_db):
    return create_app(AppConfig(instance_mode="demo", db_path=provenance_db))


class TestTheConsensusProvenanceReachesTheCaller:
    """Two barriers, and the test must fail if either goes back up.

    `SELECT r.*` cannot reach these three -- they are on `fair_prices`, not on
    `recommendations` -- so the SQL must name them, and `_serialise` builds its
    dict by hand so it must name them too. Narrowing either one alone returns
    the payload to exactly the state ADR 0021 recorded.
    """

    async def test_width_count_and_books_are_all_on_the_row(self, provenance_app):
        row = (await get(provenance_app, "/api/ledger?limit=1")).json()["rows"][0]
        assert row["market_width"] == 0.031
        assert row["book_count"] == 3
        assert row["books_used"] == _BOOKS

    async def test_whether_the_sharp_anchoring_bound_travels_with_the_row(
        self, provenance_app
    ):
        """`book_count` cannot answer this and the ADR's §7.2 turns on it.

        The anchoring is `selected = sharp or usable`, so a row where no sharp
        book quoted was priced against the **full** book set. Three sharp books
        and three soft ones both read `book_count = 3`, so without this column
        "we tested Kalshi only against references as sharp as Kalshi" is
        unfalsifiable on the record.
        """
        row = (await get(provenance_app, "/api/ledger?limit=1")).json()["rows"][0]
        assert row["anchored_on_sharp"] is True

    async def test_books_used_arrives_decoded_not_as_json_inside_json(
        self, provenance_app
    ):
        """The column is TEXT holding a JSON array. A consumer gets a list.

        Asserted separately from the value above because a string that happens
        to *contain* the right book names passes a substring check and fails
        this one. `"[\\"pinnacle\\"]" == ["pinnacle"]` is False in every
        language that matters, and the type is the claim.
        """
        row = (await get(provenance_app, "/api/ledger?limit=1")).json()["rows"][0]
        assert isinstance(row["books_used"], list)
        assert all(isinstance(b, str) for b in row["books_used"])


class TestTheThreeAbsentStatesStayDistinguishable:
    """`null` width, `0.0` width, and no join at all are three different facts.

    This is `tasks/lessons.md`'s recurring shape -- *the zero that means "no
    measurement" passes every threshold* -- carried onto the wire. The payload
    is where the two states were collapsed once before, and a single-case test
    cannot catch a collapse: it needs the *pair*.
    """

    async def test_an_unmeasurable_width_is_null_and_the_row_still_joined(
        self, provenance_db, provenance_app
    ):
        """One book cannot disagree with itself, so there is no width.

        `book_count` is `NOT NULL` in `fair_prices`, so its presence as an
        integer is what proves the join landed -- which is the only thing that
        lets a reader take `market_width is None` as "unmeasurable" rather than
        as "unjoined".
        """
        conn = db.connect(provenance_db)
        _insert_row(
            conn,
            created_ms=5000,
            market_width=None,
            book_count=1,
            books_used='["pinnacle"]',
        )
        conn.commit()
        conn.close()

        row = (await get(provenance_app, "/api/ledger?limit=1")).json()["rows"][0]
        assert row["created_ms"] == 5000, "the one-book row must be the newest"
        assert row["market_width"] is None
        assert row["book_count"] == 1, "the join landed; only the width is absent"

    async def test_a_measured_zero_width_is_zero_and_not_null(
        self, provenance_db, provenance_app
    ):
        """Two books quoting identically genuinely disagree by nothing.

        The pair with the test above is the whole point. If these two ever agree
        again, the states have been collapsed back together -- and the collapse
        is silent, because `0.0` clears every width threshold trivially.
        """
        conn = db.connect(provenance_db)
        _insert_row(
            conn,
            created_ms=6000,
            market_width=0.0,
            book_count=2,
            books_used='["betfair_ex_eu", "matchbook"]',
        )
        conn.commit()
        conn.close()

        row = (await get(provenance_app, "/api/ledger?limit=1")).json()["rows"][0]
        assert row["created_ms"] == 6000
        assert row["market_width"] == 0.0
        assert row["market_width"] is not None

    async def test_a_fallback_to_the_full_book_set_is_false_and_not_null(
        self, provenance_db, provenance_app
    ):
        """"No sharp book quoted" and "we could not tell" are different facts.

        The pair with the unjoined case below is the guard. `anchored_on_sharp`
        is `NOT NULL DEFAULT 0` in `fair_prices`, so a stored `0` is a real
        measurement — this row was priced against a *wide* consensus — while
        `None` can only mean the join missed. Collapsing them would let the one
        row that refutes §7.2's tautology reading hide as a missing value.
        """
        conn = db.connect(provenance_db)
        _insert_row(
            conn,
            created_ms=6500,
            market_width=0.02,
            book_count=3,
            books_used='["draftkings", "fanduel", "betmgm"]',
            anchored_on_sharp=0,
        )
        conn.commit()
        conn.close()

        row = (await get(provenance_app, "/api/ledger?limit=1")).json()["rows"][0]
        assert row["created_ms"] == 6500
        assert row["anchored_on_sharp"] is False
        assert row["anchored_on_sharp"] is not None
        assert row["book_count"] == 3, "a soft-book consensus counts books too"

    async def test_a_row_with_no_fair_price_gets_none_never_zero_or_empty(
        self, provenance_db, provenance_app
    ):
        """No join: all three `None`. Not `0`, and not `[]`.

        `book_count = 0` would say a consensus was built from no books, and
        `books_used = []` would say the same thing again -- both are claims, and
        both would pass straight through a suppression rule that only asks
        whether a value is present.
        """
        conn = db.connect(provenance_db)
        _insert_row(
            conn,
            created_ms=7000,
            market_width=None,
            book_count=0,
            books_used="[]",
            with_fair=False,
        )
        conn.commit()
        conn.close()

        row = (await get(provenance_app, "/api/ledger?limit=1")).json()["rows"][0]
        assert row["created_ms"] == 7000, "the unjoined row must be the newest"
        assert row["market_width"] is None
        assert row["book_count"] is None
        assert row["books_used"] is None
        assert row["anchored_on_sharp"] is None, "not False -- that is a measurement"

    async def test_an_unreadable_books_used_is_none_rather_than_an_empty_list(self):
        """Corrupt JSON must not resolve to "no books were used".

        Exercised on the decoder directly: the column is `NOT NULL` and every
        writer goes through `json.dumps`, so this state is unreachable from the
        route today. It is asserted anyway because the failure it guards is the
        one this repo keeps rediscovering -- an unreadable value that resolves
        to a legitimate answer is indistinguishable from a measurement.
        """
        from backend.api.routes import _decode_books_used

        assert _decode_books_used("not json at all") is None
        assert _decode_books_used('{"pinnacle": 1}') is None, "an object is not a list"
        assert _decode_books_used("[1, 2, 3]") is None, "books are names, not numbers"
        assert _decode_books_used(None) is None
        # And the legitimate empty answer still survives the round trip, or the
        # guard above would be swallowing a real state to catch a fake one.
        assert _decode_books_used("[]") == []


class TestRoutesThatDidNotJoinOmitTheKeysEntirely:
    """Absent, not `null`. Three nulls would read as "joined, and empty".

    The Board and the market detail select from `recommendations` alone. This is
    the same rule the four devig readings already follow, asserted separately
    because the two blocks are guarded by two different `in row.keys()` checks
    and one can be widened without the other.
    """

    async def test_the_board_omits_all_three(self, provenance_app):
        board = (
            await get(provenance_app, "/api/board?include_suppressed=true")
        ).json()
        every = (
            board["surfaced"]
            + board["expired"]
            + board["suppressed"]
            + board["no_edge"]
        )
        assert every, "the fixture must produce board rows or this proves nothing"
        for key in ("market_width", "book_count", "books_used", "anchored_on_sharp"):
            assert all(key not in r for r in every), key
