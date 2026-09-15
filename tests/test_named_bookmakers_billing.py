"""Named books replace regions, and the bill follows them — ADR 0155.

The Odds API charges `markets x regions`, and lets a caller name individual
bookmakers instead: "Every group of 10 bookmakers is the equivalent of 1
region", and "if both `bookmakers` and `regions` are both specified,
`bookmakers` takes priority". Measured against their own counter 2026-09-15
before any of this was built: ten books x three markets returned
`x-requests-last: 3` and moved `x-requests-used` 5048 -> 5051.

Why it matters here rather than as a tidy saving: every sharp book this feed
carries (`pinnacle`, `matchbook`, `betfair_ex_eu`) is EU-region, and
`consensus_devig` selects on `SHARP_BOOKS` when any is present. Dropping `eu`
to halve the bill would have taken `anchored_on_sharp` from 57% of
`fair_prices` to zero. Naming the books buys the same halving with the anchor
intact.

What these establish: the ceiling arithmetic including the group-of-ten cliff;
that a request sends exactly one of the two keys; that `bookmakers` wins when
both are configured; and that an unset `ODDS_BOOKMAKERS` leaves every
deployment on the old region behaviour.

What they do not establish: that any particular book key is spelled correctly
or covers a given sport. A misspelled key is silently absent from the vendor's
response and still costs a slot toward the next group of ten — that is a live
fact, checked by reading the response, not by this file.
"""

from __future__ import annotations

import pytest

from backend.odds.budget import BOOKMAKERS_PER_REGION, sweep_cost
from backend.odds.client import _region_params

THREE = ("h2h", "spreads", "totals")
TEN = tuple(f"book{i}" for i in range(10))


class TestTheBillFollowsTheNamedBooks:
    def test_ten_books_cost_one_region(self):
        """The measured case: 3 markets x 1 region-equivalent = 3 credits.

        Mutation observed red: `sweep_cost` ignoring `bookmakers` and billing
        `len(regions)` — returns 6, which is the number this change exists to
        stop paying.
        """
        assert sweep_cost(THREE, ("us", "eu"), TEN) == 3

    def test_the_eleventh_book_doubles_the_bill(self):
        """Ten is a cliff, not a budget. `ceil`, never a proportion."""
        assert sweep_cost(THREE, ("us",), TEN) == 3
        assert sweep_cost(THREE, ("us",), TEN + ("book10",)) == 6

    def test_one_book_still_costs_a_whole_region(self):
        assert sweep_cost(THREE, ("us", "eu"), ("pinnacle",)) == 3

    def test_twenty_books_are_two_regions(self):
        twenty = tuple(f"book{i}" for i in range(20))
        assert sweep_cost(THREE, ("us",), twenty) == 6
        assert len(twenty) == 2 * BOOKMAKERS_PER_REGION

    def test_no_books_bills_on_regions_exactly_as_before(self):
        """The default path. Every deployment that sets no books is unchanged."""
        assert sweep_cost(THREE, ("us", "eu")) == 6
        assert sweep_cost(THREE, ("us", "eu"), ()) == 6
        assert sweep_cost(("h2h",), ("us",)) == 1

    def test_the_floor_of_one_credit_survives(self):
        assert sweep_cost((), (), ("pinnacle",)) == 1


class TestExactlyOneKeyIsSent:
    """Sending both would leave the request and the bill disagreeing.

    The vendor tolerates both and lets `bookmakers` win, so a request carrying
    `regions` too would still cost the book price — until someone edited one
    of the two and the other silently kept applying.
    """

    def test_books_configured_sends_bookmakers_and_no_regions(self):
        params = _region_params(["us", "eu"], ["pinnacle", "matchbook"])
        assert params == {"bookmakers": "pinnacle,matchbook"}
        assert "regions" not in params

    def test_no_books_sends_regions_and_no_bookmakers(self):
        params = _region_params(["us", "eu"], [])
        assert params == {"regions": "us,eu"}
        assert "bookmakers" not in params

    def test_the_two_are_never_both_present(self):
        """Mutation observed red: `_region_params` merging both dicts."""
        for books in ([], ["pinnacle"], ["a", "b", "c"]):
            params = _region_params(["us"], books)
            assert len(set(params) & {"regions", "bookmakers"}) == 1


class TestTheConfigCarriesItEndToEnd:
    def test_credits_per_sweep_reads_the_books(self, monkeypatch):
        """Mutation observed red: the property multiplying markets x regions
        directly, as it did until ADR 0155 — reports 6 while the vendor
        charges 3."""
        from backend.config import OddsConfig

        cfg = OddsConfig(
            api_key="k",
            base_url="https://example.invalid",
            daily_credit_budget=700,
            regions=["us", "eu"],
            markets=list(THREE),
            bookmakers=list(TEN),
        )
        assert cfg.credits_per_sweep_per_sport == 3

    def test_unset_books_leave_the_old_number(self):
        from backend.config import OddsConfig

        cfg = OddsConfig(
            api_key="k",
            base_url="https://example.invalid",
            daily_credit_budget=700,
            regions=["us", "eu"],
            markets=list(THREE),
        )
        assert cfg.bookmakers == []
        assert cfg.credits_per_sweep_per_sport == 6

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("", []),
            ("pinnacle", ["pinnacle"]),
            ("pinnacle,matchbook", ["pinnacle", "matchbook"]),
            # Whitespace around a name is a spelling, not a second book.
            (" pinnacle , matchbook ", ["pinnacle", "matchbook"]),
            # A trailing comma must not produce an empty name that costs a slot.
            ("pinnacle,", ["pinnacle"]),
        ],
    )
    def test_the_env_list_is_parsed_without_phantom_books(
        self, monkeypatch, raw, expected
    ):
        from backend.config import OddsConfig

        monkeypatch.setenv("ODDS_API_KEY", "k")
        monkeypatch.setenv("ODDS_BOOKMAKERS", raw)
        assert OddsConfig.load().bookmakers == expected


class TestTheLiveDeployNamesTenBooksAndKeepsTheSharps:
    """`fly.live.toml` is the deployed value; the repo default is not.

    The sharp anchor is the reason this change exists, so the deploy file
    naming fewer than all the sharps the feed carries — or naming an eleventh
    book and doubling the bill — is a regression this pins.
    """

    def _live_books(self) -> list[str]:
        import re
        from pathlib import Path

        toml = Path(__file__).resolve().parents[1] / "fly.live.toml"
        text = toml.read_text(encoding="utf-8")
        m = re.search(r'^\s*ODDS_BOOKMAKERS\s*=\s*"([^"]*)"', text, re.M)
        assert m, "fly.live.toml does not set ODDS_BOOKMAKERS"
        return [b.strip() for b in m.group(1).split(",") if b.strip()]

    def test_the_live_list_is_exactly_ten(self):
        books = self._live_books()
        assert len(books) == BOOKMAKERS_PER_REGION, books
        assert len(set(books)) == len(books), "a duplicate costs a slot"

    def test_every_sharp_book_the_feed_carries_is_named(self):
        """`betfair_ex_uk` is deliberately absent — it returns nothing for
        these sports, and an absent book still costs a slot."""
        from backend.runner import SHARP_BOOKS

        books = set(self._live_books())
        carried = {"pinnacle", "matchbook", "betfair_ex_eu"}
        assert carried <= SHARP_BOOKS
        assert carried <= books, sorted(carried - books)

    def test_the_live_sweep_is_three_credits_not_six(self):
        assert sweep_cost(THREE, ("us", "eu"), self._live_books()) == 3


class TestTheSpendRowSaysWhatItBought:
    """`api_credits.bookmakers`, schema v44 — ADR 0156.

    ADR 0155 started sending named books INSTEAD of regions, and the row kept
    recording only `regions` — the configured value, not the sent one. The
    first named-book sweep landed on live as `regions = "us,eu"` with
    `cost = 3`, and this table's own rule (`cost` is "what we predicted:
    markets x regions") turns that into 3 x 2 = 6. A ledger row describing a
    purchase that did not happen.

    `cost` was right throughout, so the reconciliation against
    `x-requests-used` never drifted. What was wrong is the only column that
    says WHY the cost is what it is — the first thing anyone debugging a
    drift would read.

    Mutations observed red, one per test: `record` dropping the `bookmakers`
    argument from the INSERT; the client not passing it.
    """

    def _conn(self, tmp_path):
        from backend.store import db as store

        return store.init_db(tmp_path / "credits.db")

    def test_a_named_book_call_records_the_books(self, tmp_path):
        from backend.odds.budget import CreditBudget

        conn = self._conn(tmp_path)
        CreditBudget(conn, daily_budget=700).record(
            called_ms=1, endpoint="/sports/x/odds", cost=3,
            markets=list(THREE), regions=["us", "eu"], bookmakers=list(TEN),
        )
        row = conn.execute("SELECT * FROM api_credits").fetchone()
        assert row["bookmakers"] == ",".join(TEN)
        assert row["cost"] == 3
        # The row is now self-consistent: cost == markets x ceil(books/10).
        books = row["bookmakers"].split(",")
        assert row["cost"] == sweep_cost(row["markets"].split(","), [], books)
        conn.close()

    def test_a_region_call_leaves_the_column_null(self, tmp_path):
        """NULL means 'this call bought regions' — every row before v44 — and
        is not the same as 'bought no books'."""
        from backend.odds.budget import CreditBudget

        conn = self._conn(tmp_path)
        CreditBudget(conn, daily_budget=700).record(
            called_ms=1, endpoint="/sports/x/odds", cost=6,
            markets=list(THREE), regions=["us", "eu"],
        )
        row = conn.execute("SELECT * FROM api_credits").fetchone()
        assert row["bookmakers"] is None
        assert row["regions"] == "us,eu"
        assert row["cost"] == sweep_cost(
            row["markets"].split(","), row["regions"].split(",")
        )
        conn.close()

    def test_the_schema_is_v44(self):
        from backend.store.db import SCHEMA_VERSION, _MIGRATIONS

        assert SCHEMA_VERSION == 44
        assert ("api_credits", "bookmakers", "TEXT") in _MIGRATIONS[44].columns

    def test_the_migration_reaches_an_existing_database(self, tmp_path):
        """v44 must add the column to a database that predates it, not only
        appear in a freshly created one."""
        import sqlite3

        from backend.store import db as store

        conn = self._conn(tmp_path)
        conn.execute("ALTER TABLE api_credits DROP COLUMN bookmakers")
        store._set_meta(conn, "schema_version", "43")
        conn.commit()
        assert "bookmakers" not in store._columns(conn, "api_credits")
        ran = store.migrate(conn)
        assert 44 in ran
        assert "bookmakers" in store._columns(conn, "api_credits")
        conn.close()

    def test_the_inspector_reads_the_new_column(self):
        """An instrument blind to the column cannot show the row it explains."""
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        import inspect_live_db_feed as feed

        assert "bookmakers" in feed._CREDIT_COLUMNS
