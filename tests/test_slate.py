"""The Slate factors, and the claims each one is not allowed to make.

`backend/slate.py` computes things that have never been scored against an
outcome. That makes the *prohibitions* as much the subject of these tests as the
arithmetic: a factor that quietly starts behaving like an edge would pass any
test written only about its value.
"""

from __future__ import annotations

import pytest

from backend.core.devig import devig
from backend.slate import (
    DRIFT_WINDOW_MS,
    BookDistribution,
    book_distribution,
    kalshi_drift,
)
from backend.store import db


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "slate.db")
    yield c
    c.close()


def _market(conn, ticker):
    """`kalshi_quotes.ticker` is a real foreign key, so the market must exist."""
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_series (series_ticker, league, "
        "has_game_markets, first_seen_ms, last_seen_ms) "
        "VALUES ('KXMLBGAME', 'Pro Baseball', 1, 0, 0)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, series_ticker, "
        "title, category, commence_ms, close_ms, status, first_seen_ms, "
        "last_seen_ms) VALUES ('EV', 'KXMLBGAME', 't', 'Sports', 0, 0, "
        "'open', 0, 0)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, "
        "series_ticker, title, market_type, price_structure, close_ms, "
        "status, first_seen_ms, last_seen_ms) "
        "VALUES (?, 'EV', 'KXMLBGAME', 't', 'moneyline', 'linear_cent', "
        "0, 'open', 0, 0)",
        (ticker,),
    )
    conn.commit()


def _quote(conn, ticker, observed_ms, *, yes_bid, no_bid):
    _market(conn, ticker)
    conn.execute(
        "INSERT INTO kalshi_quotes (ticker, observed_ms, source, "
        "yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty) "
        "VALUES (?, ?, 'rest', ?, 10.0, ?, 10.0)",
        (ticker, observed_ms, yes_bid, no_bid),
    )
    conn.commit()


class TestTheBookDistributionIsLikeForLike:
    """Every book is devigged before anything is compared.

    Comparing Kalshi's ask against *raw* book prices would rank books by how
    much vig they charge rather than by what they think, and every book would
    look expensive next to Kalshi by construction -- an artefact pointing in
    the flattering direction, which is what `CLAUDE.md` rule 1 exists for.
    """

    OUTCOMES = ("Cubs", "Cardinals")

    def _books(self, *specs):
        return {f"book{i}": list(odds) for i, odds in enumerate(specs)}

    def test_a_book_is_devigged_before_it_is_compared(self):
        # 1.90/1.90 is a 5.3% overround. Raw implied is 0.526 a side; devigged
        # it is 0.500. Kalshi at 51.0c sits ABOVE the devigged fair and BELOW
        # the raw one, so the two readings disagree about the sign -- which is
        # the whole reason the devig is not optional.
        dist = book_distribution(
            outcomes=self.OUTCOMES,
            quotes_by_book=self._books((1.90, 1.90)),
            outcome_name="Cubs",
            kalshi_ask_tenths=510,
        )
        assert dist is not None
        assert dist.book_count == 1
        assert dist.book_probabilities[0] == pytest.approx(0.5, abs=1e-9)
        assert dist.books_below == 1, (
            "the raw 0.526 was compared instead of the devigged 0.500; every "
            "book would look expensive beside Kalshi by construction"
        )

    def test_the_worst_of_four_methods_is_taken_per_book(self):
        """Matching `CLAUDE.md` rule 2 and the money path's `p_conservative`.

        Using the mean of the four here while `edge_tenths` uses the minimum
        would put two different fair values on one screen under one word.
        """
        odds = (1.40, 3.20)
        dist = book_distribution(
            outcomes=self.OUTCOMES,
            quotes_by_book=self._books(odds),
            outcome_name="Cubs",
            kalshi_ask_tenths=500,
        )
        expected = min(
            m[0] for m in devig(self.OUTCOMES, list(odds)).all_methods().values()
        )
        assert dist.book_probabilities[0] == pytest.approx(expected, abs=1e-12)

    def test_it_reads_the_requested_outcome_and_not_the_first_one(self):
        """Positional indexing is how the two teams silently swap."""
        odds = (1.40, 3.20)
        cubs = book_distribution(
            outcomes=self.OUTCOMES, quotes_by_book=self._books(odds),
            outcome_name="Cubs", kalshi_ask_tenths=500,
        )
        cards = book_distribution(
            outcomes=self.OUTCOMES, quotes_by_book=self._books(odds),
            outcome_name="Cardinals", kalshi_ask_tenths=500,
        )
        assert cubs.book_probabilities[0] > cards.book_probabilities[0], (
            "the favourite and the underdog came back with the same "
            "probability, so the outcome index is being ignored"
        )

    def test_an_unknown_outcome_returns_none_rather_than_the_other_team(self):
        assert (
            book_distribution(
                outcomes=self.OUTCOMES,
                quotes_by_book=self._books((1.90, 1.90)),
                outcome_name="Mets",
                kalshi_ask_tenths=500,
            )
            is None
        )

    def test_no_sharp_anchoring_is_applied(self):
        """The anchoring is the thing this distribution exists to look past.

        `consensus_devig` keeps only `SHARP_BOOKS` when any are present. ADR
        0021 §7.2 argues that is why the whole result may be a tautology, so
        the distribution here must span every usable book -- including the
        soft ones the anchored consensus threw away.
        """
        dist = book_distribution(
            outcomes=self.OUTCOMES,
            quotes_by_book={
                "pinnacle": [1.90, 1.90],
                "draftkings": [1.80, 2.05],
                "fanduel": [1.83, 2.00],
            },
            outcome_name="Cubs",
            kalshi_ask_tenths=500,
        )
        assert dist.book_count == 3, (
            "only the sharp book survived, so this is the anchored consensus "
            "again rather than the distribution around it"
        )


class TestTheDistributionRefusesToFabricateAZero:
    """A count of zero and an absence of measurement must not render alike.

    This repo's recurring failure: *the zero that means "no measurement" passes
    every threshold*. `percentile` of 0.0 reads as "Kalshi is the cheapest venue
    here", which is the flattering misreading of a measurement that never ran.
    """

    def test_an_empty_distribution_has_a_null_percentile_not_zero(self):
        dist = book_distribution(
            outcomes=("Cubs", "Cardinals"),
            quotes_by_book={"book0": [1.90]},   # short price list, unusable
            outcome_name="Cubs",
            kalshi_ask_tenths=500,
        )
        assert dist.book_count == 0
        assert dist.percentile is None
        assert dist.median_book_probability is None
        assert dist.books_unusable == 1

    def test_books_dropped_before_the_call_are_still_counted(self):
        """`book_quotes_for_event` drops books that miss a leg, silently.

        Two filters on one quantity and the earlier one says nothing, so
        without this the payload reports a clean distribution over every book
        the fixture had.
        """
        dist = book_distribution(
            outcomes=("Cubs", "Cardinals"),
            quotes_by_book={"book0": [1.90, 1.90]},
            outcome_name="Cubs",
            kalshi_ask_tenths=500,
            already_dropped=17,
        )
        assert dist.books_unusable == 17

    def test_a_real_zero_is_still_reported_as_zero(self):
        """The falsifier for the two above: `None` must mean unmeasured only."""
        dist = book_distribution(
            outcomes=("Cubs", "Cardinals"),
            quotes_by_book={"book0": [1.90, 1.90]},
            outcome_name="Cubs",
            kalshi_ask_tenths=10,   # Kalshi far cheaper than every book
        )
        assert dist.books_below == 0
        assert dist.percentile == 0.0


class TestTheComparisonIsBiasedAgainstKalshiOnPurpose:
    def test_the_ask_is_used_and_not_a_mid(self):
        """`CLAUDE.md`: bucket by the price you would actually pay.

        A previous project produced a +25.4 point 'edge' that lost money by
        bucketing on the mid and transacting at the ask.
        """
        dist = book_distribution(
            outcomes=("Cubs", "Cardinals"),
            quotes_by_book={"book0": [1.90, 1.90]},
            outcome_name="Cubs",
            kalshi_ask_tenths=530,
        )
        assert dist.kalshi_probability == pytest.approx(0.530)


class TestKalshiDriftReadsTheHistoryNobodyReadsBack:
    TICKER = "KXMLBGAME-TEST-CHI"

    def test_it_measures_the_whole_window_not_the_last_two_quotes(self, conn):
        """A pass writes several quotes a minute.

        Differencing the two newest rows would measure fifteen seconds of drift
        and print it under an hour's label.
        """
        now = 1_800_000_000_000
        # Derived YES ask is 1000 - no_bid, so a falling no_bid is a rising ask.
        for minutes, no_bid in ((50, 500), (30, 480), (10, 460), (0, 455)):
            _quote(conn, self.TICKER, now - minutes * 60_000,
                   yes_bid=400, no_bid=no_bid)

        drift = kalshi_drift(conn, self.TICKER, "yes", now_ms=now)
        # oldest ask 500, newest 545.
        assert drift == 45

    def test_a_single_observation_is_none_and_never_zero(self, conn):
        """Zero would assert the price held steady over the hour."""
        now = 1_800_000_000_000
        _quote(conn, self.TICKER, now, yes_bid=400, no_bid=500)
        assert kalshi_drift(conn, self.TICKER, "yes", now_ms=now) is None

    def test_quotes_older_than_the_window_are_not_reached(self, conn):
        now = 1_800_000_000_000
        _quote(conn, self.TICKER, now - DRIFT_WINDOW_MS - 60_000,
               yes_bid=400, no_bid=900)
        _quote(conn, self.TICKER, now, yes_bid=400, no_bid=500)
        assert kalshi_drift(conn, self.TICKER, "yes", now_ms=now) is None, (
            "a quote from outside the window was differenced against a current "
            "one and reported as an hour's movement"
        )

    def test_an_unreadable_side_is_none_rather_than_no_movement(self, conn):
        """A market with no bid on one side has no derivable ask."""
        now = 1_800_000_000_000
        _quote(conn, self.TICKER, now - 30 * 60_000, yes_bid=400, no_bid=None)
        _quote(conn, self.TICKER, now, yes_bid=400, no_bid=500)
        assert kalshi_drift(conn, self.TICKER, "yes", now_ms=now) is None

    def test_the_no_side_is_derived_from_the_yes_bid(self, conn):
        now = 1_800_000_000_000
        for minutes, yes_bid in ((30, 400), (0, 430)):
            _quote(conn, self.TICKER, now - minutes * 60_000,
                   yes_bid=yes_bid, no_bid=500)
        # NO ask is 1000 - yes_bid: 600 then 570.
        assert kalshi_drift(conn, self.TICKER, "no", now_ms=now) == -30


class TestNothingHereIsAnEdge:
    """The prohibitions, asserted rather than left to the docstring."""

    def test_the_module_computes_no_composite_score(self):
        """A weighted blend of unscored factors is a model, not a fact.

        It would need its own ADR and a pre-registration (ADR 0021 §9). This
        test is the tripwire: adding a `score`, `rating` or `confidence` to the
        payload turns it red.
        """
        dist = BookDistribution(
            kalshi_probability=0.5,
            book_probabilities=(0.4, 0.6),
            books_below=1,
            books_unusable=0,
        )
        forbidden = {"score", "rating", "confidence", "signal", "recommendation"}
        assert not (forbidden & set(dist.as_dict())), (
            "a composite appeared in the Slate payload; combining unscored "
            "factors into one number is a model and needs an ADR"
        )

    def test_the_money_path_does_not_import_this_module(self):
        """No factor here may reach sizing, suppression or the order path.

        Parsed rather than grepped: the word "slate" appears in ordinary prose
        all over this codebase (`SLATE_WINDOW_MS`, "an unchanged slate"), so a
        substring search would be red on arrival and would be deleted rather
        than believed. Only a real `import` counts.
        """
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "backend"
        for module in (
            "engine.py",
            "core/sizing.py",
            "core/suppression.py",
            "core/ev.py",
            "kalshi/orders.py",
        ):
            tree = ast.parse((root / module).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.rsplit(".", 1)[-1])
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imported.add(alias.name.rsplit(".", 1)[-1])
            assert "slate" not in imported, (
                f"{module} imports the slate module; a factor that has never "
                f"been scored against an outcome must not reach the money path"
            )
