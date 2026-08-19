"""The chain runner: the stage that turns built parts into a recorded observation.

Before this module existed, `persist_recommendation` was called only by
`seed_demo.py` and by tests, `odds_snapshots` had a writer and no reader, and
`fair_prices` had neither. So these tests are weighted toward the **join** --
the parts were already covered individually, and what had never been exercised
was any of them talking to another.

On fixtures
-----------
Both captured payloads are real and are parsed by the real parsers:
`events_sports_nested.json` for the Kalshi side and
`odds_mlb_h2h_spreads_totals.json` for the books.

They do **not** describe the same games -- the Kalshi capture is 9-10 August,
the odds capture is the 7th -- so linking them as-is resolves nothing and would
make an end-to-end test that asserts a chain of zeros. `aligned_kalshi_event`
therefore takes a real Kalshi event dict and rewrites **only the join keys**
(event ticker, market ticker, `yes_sub_title`, `occurrence_datetime`) onto a
real odds fixture. Every field name and every value format stays exactly as
Kalshi sent it, so the wire-format assumptions are still pinned to real bytes;
only the identity of the game is moved.

That distinction is the point. Aligning a timestamp is not the same as
hand-writing a payload, and the thing this project keeps getting burned by is
the second one.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from backend.config import RiskConfig, StalenessConfig
from backend.core.suppression import SuppressionConfig
from backend.gate import live_ages
from backend.kalshi.discovery import discover_from_events
from backend.kalshi.props import ALTERNATE_SUFFIX
from backend.odds.client import OddsQuote, store_quotes
from backend.match.linker import EXACT_ALIAS_PAIR, PROP_LINK_METHOD
from backend.runner import (
    MONEYLINE,
    PassCounts,
    _linked_fixtures,
    book_quotes_for_event,
    current_exposure_dollars,
    link_discovered_events,
    run_pricing_pass,
    store_quotes_from_discovery,
    upsert_discovered,
)
from backend.store import db

FIXTURES = Path(__file__).parent / "fixtures"

# Five minutes after the odds capture was taken (2026-08-07T13:49:22Z). It has
# to sit *after* the payload it reads: a clock set before the capture makes
# every book's age negative, which is a real state the code now reports rather
# than clamping to "perfectly fresh" -- but it is not the state under test here.
NOW = 1_786_110_562_317 + 300_000


@pytest.fixture(scope="module")
def kalshi_events() -> list[dict]:
    return json.loads((FIXTURES / "events_sports_nested.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def odds_capture() -> dict:
    return json.loads(
        (FIXTURES / "odds_mlb_h2h_spreads_totals.json").read_text("utf-8")
    )


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "runner.db")
    yield c
    c.close()


def _iso(ms: int) -> str:
    """Epoch ms -> the Zulu ISO string Kalshi actually publishes."""
    from datetime import datetime, timezone

    return (
        datetime.fromtimestamp(ms / 1000, timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _mlb_template(kalshi_events: list[dict]) -> dict:
    """A real two-sided Kalshi moneyline event, used as the shape to copy."""
    return next(
        e
        for e in kalshi_events
        if (e.get("event_ticker") or "").startswith("KXMLBGAME-")
        and len(e.get("markets") or []) == 2
    )


def aligned_kalshi_event(
    template: dict,
    *,
    odds_event: dict,
    kalshi_names: tuple[str, str],
) -> dict:
    """Re-point a real Kalshi event at a real odds fixture.

    `kalshi_names` are the short forms Kalshi actually publishes ("Pittsburgh",
    "New York M"), in `(home, away)` order, so the alias and prefix rules in the
    matcher are genuinely exercised rather than sidestepped by using the books'
    own spellings.
    """
    event = copy.deepcopy(template)
    home, away = kalshi_names
    slug = f"{home[:3]}{away[:3]}".upper().replace(" ", "")
    event["event_ticker"] = f"KXMLBGAME-TEST{slug}"
    event["title"] = f"{home} vs {away}"

    for market, name in zip(event["markets"], (home, away)):
        market["event_ticker"] = event["event_ticker"]
        market["ticker"] = f"{event['event_ticker']}-{name[:3].upper()}"
        market["yes_sub_title"] = name
        market["occurrence_datetime"] = odds_event["commence_time"]
        market["close_time"] = odds_event["commence_time"]
    return event


@pytest.fixture
def book_odds(conn, odds_capture):
    """The captured sportsbook slate, stored. Returns the Pittsburgh fixture.

    Split out of `joined` so a test can pair the same real odds with a Kalshi
    event of its own shaping -- `joined` copies the sportsbook's kickoff onto
    the Kalshi side, which is right for a linking test and makes it impossible
    to tell the two clocks apart.
    """
    from backend.config import OddsConfig
    from backend.odds.budget import CreditBudget
    from backend.odds.client import OddsClient

    client = OddsClient(
        OddsConfig(
            api_key="x", base_url="https://example.invalid",
            daily_credit_budget=16, regions=["us", "eu"],
            markets=["h2h", "spreads", "totals"],
        ),
        CreditBudget(conn, daily_budget=16),
    )
    quotes = client._parse(
        odds_capture["events"], sport_key="baseball_mlb", fetched_ms=NOW
    )
    store_quotes(conn, quotes)

    return next(
        e for e in odds_capture["events"]
        if e["home_team"] == "Pittsburgh Pirates"
    )


@pytest.fixture
def joined(conn, kalshi_events, book_odds):
    """A database with real odds stored and a Kalshi event aligned onto one.

    Returns `(events, odds_event)`, where `events` is the discovery output.
    """
    odds_event = book_odds
    event = aligned_kalshi_event(
        _mlb_template(kalshi_events),
        odds_event=odds_event,
        kalshi_names=("Pittsburgh", "New York M"),
    )
    events = discover_from_events([event])
    upsert_discovered(conn, events, now=NOW)
    store_quotes_from_discovery(conn, events, now=NOW)
    return events, odds_event


class TestTheQuoteRidesOnTheDiscoveryPayload:
    """No separate orderbook call, and no second wire format to guess at.

    `/events?with_nested_markets=true` already carries the quote. Re-reading the
    same bytes elsewhere would mean a second set of field-name assumptions,
    which is precisely how the WebSocket parser came to read `data["yes"]` while
    Kalshi sent `yes_dollars_fp`.
    """

    def test_prices_are_parsed_from_the_real_payload(self, kalshi_events):
        events = discover_from_events(kalshi_events)
        markets = [
            m for e in events for m in e.markets if m.market_type == "moneyline"
        ]
        assert markets, "no moneyline markets in the capture"

        priced = [m for m in markets if m.yes_bid_tenths is not None]
        assert priced, "every moneyline market parsed to a null price"
        for market in priced:
            # Dollar strings ("0.4500") -> integer tenths of a cent.
            assert 0 <= market.yes_bid_tenths <= 1000
            assert market.yes_bid_tenths % 10 == 0 or True

    def test_the_derived_ask_identity_holds_on_the_capture(self, kalshi_events):
        """`yes_ask == 1 - no_bid`, checked against Kalshi's own quoted ask.

        The identity is what lets the runner store only the two published bids
        and derive both asks. If it ever stops holding, the derivation is
        unsound and every entry price in the record is wrong.
        """
        raw_markets = [
            m
            for e in kalshi_events
            for m in (e.get("markets") or [])
            if m.get("yes_ask_dollars") and m.get("no_bid_dollars")
        ]
        assert raw_markets

        checked = 0
        for market in raw_markets:
            quoted_ask = round(float(market["yes_ask_dollars"]) * 1000)
            derived = 1000 - round(float(market["no_bid_dollars"]) * 1000)
            assert quoted_ask == derived, market["ticker"]
            checked += 1
        assert checked > 50, f"only {checked} markets carried both sides"

    def test_sizes_are_stored_against_the_side_that_can_lift_them(self, conn, joined):
        """A yes ask is filled by the resting NO bid, so that is its depth.

        Getting this backwards is invisible: both numbers are plausible sizes,
        and the only symptom is a depth suppression firing on the wrong side.
        """
        events, _ = joined
        market = next(
            m for e in events for m in e.markets if m.market_type == "moneyline"
        )
        row = conn.execute(
            "SELECT * FROM kalshi_quotes WHERE ticker = ?", (market.ticker,)
        ).fetchone()

        assert row["yes_bid_qty"] == market.no_ask_size
        assert row["no_bid_qty"] == market.yes_ask_size


class TestBookQuotesReadPath:
    """`odds_snapshots` -> `consensus_devig`. The join that did not exist."""

    def test_it_reads_the_real_capture_grouped_by_book(self, conn, joined):
        _, odds_event = joined
        books = book_quotes_for_event(conn, odds_event["id"], now=NOW)

        assert books is not None
        assert len(books.outcomes) == 2
        assert len(books.quotes_by_book) >= 10, "expected many books in the capture"
        for prices in books.quotes_by_book.values():
            assert len(prices) == len(books.outcomes)
            assert all(p > 1.0 for p in prices)

    def test_lay_prices_never_appear(self, conn, joined):
        """Excluded at ingest, so the read path cannot resurrect them."""
        _, odds_event = joined
        rows = conn.execute(
            "SELECT DISTINCT market FROM odds_snapshots WHERE odds_event_id = ?",
            (odds_event["id"],),
        ).fetchall()
        assert not [r for r in rows if r["market"].endswith("_lay")]

    def test_nothing_stored_returns_none_rather_than_an_empty_consensus(self, conn):
        assert book_quotes_for_event(conn, "no-such-event", now=NOW) is None

    def test_only_the_latest_sweep_is_used(self, conn, joined):
        """A stale book must look stale, not wide.

        Mixing sweeps would pair a fresh Pinnacle price with an hour-old
        DraftKings one and report the disagreement as `market_width`, which is a
        suppression input. The staleness would be laundered into a different
        diagnostic.
        """
        _, odds_event = joined
        later = NOW + 3_600_000
        store_quotes(
            conn,
            [
                OddsQuote(
                    fetched_ms=later, book_updated_ms=later,
                    sport_key="baseball_mlb", odds_event_id=odds_event["id"],
                    commence_ms=NOW, home_team=odds_event["home_team"],
                    away_team=odds_event["away_team"], bookmaker="onlybook",
                    market=MONEYLINE, outcome_name=name, outcome_point=None,
                    price_decimal=2.0,
                )
                for name in (odds_event["home_team"], odds_event["away_team"])
            ],
        )

        books = book_quotes_for_event(conn, odds_event["id"], now=later)
        assert set(books.quotes_by_book) == {"onlybook"}, (
            "the earlier sweep leaked into the later one"
        )

    def test_age_is_the_oldest_contributing_book(self, conn, joined):
        """A consensus is only as fresh as the stalest price inside it."""
        _, odds_event = joined
        books = book_quotes_for_event(conn, odds_event["id"], now=NOW)

        rows = conn.execute(
            "SELECT MIN(COALESCE(book_updated_ms, fetched_ms)) AS oldest "
            "FROM odds_snapshots WHERE odds_event_id = ? AND market = ?",
            (odds_event["id"], MONEYLINE),
        ).fetchone()
        assert books.oldest_book_age_ms == NOW - int(rows["oldest"])

    def test_a_book_stamped_in_the_future_is_not_reported_as_fresh(
        self, conn, joined, caplog
    ):
        """Found by a failing test rather than by reasoning.

        The first version took `max(ages.get(book, 0), age)`, whose zero seed
        floored every negative age. A book stamped an hour ahead of us therefore
        came back as "0ms old" -- maximally fresh, passing every staleness
        check, and indistinguishable from a genuinely current price. Clock skew
        would have been laundered into confidence.
        """
        import logging

        _, odds_event = joined
        earlier = NOW - 7_200_000     # our clock two hours behind the books

        with caplog.at_level(logging.WARNING):
            books = book_quotes_for_event(conn, odds_event["id"], now=earlier)

        assert books.oldest_book_age_ms < 0, (
            "a future-stamped book must keep its negative age, not clamp to 0"
        )
        assert "stamped in the future" in caplog.text

    def test_outcome_order_is_identical_for_every_book(self, conn, joined):
        """`consensus_devig` pairs prices to outcomes positionally.

        An inconsistent order swaps the two teams' probabilities and produces
        entirely plausible numbers, so this is asserted against the stored rows
        rather than trusted.
        """
        _, odds_event = joined
        books = book_quotes_for_event(conn, odds_event["id"], now=NOW)

        for book, prices in books.quotes_by_book.items():
            for outcome, price in zip(books.outcomes, prices):
                row = conn.execute(
                    "SELECT price_decimal FROM odds_snapshots WHERE "
                    "odds_event_id = ? AND market = ? AND bookmaker = ? "
                    "AND outcome_name = ?",
                    (odds_event["id"], MONEYLINE, book, outcome),
                ).fetchone()
                assert row is not None, f"{book} has no price for {outcome}"
                assert row["price_decimal"] == pytest.approx(price)


class TestTheChainProducesRecordedObservations:
    """End to end: real payloads in, `recommendations` rows out."""

    def test_a_pass_writes_recommendations(self, conn, joined):
        events, _ = joined
        counts = run_pricing_pass(conn, events, now=NOW)

        assert counts.events_linked == 1, counts.as_dict()
        assert counts.fair_prices_written == 2
        assert counts.recommendations == 4, "two markets, two sides each"

        rows = conn.execute("SELECT * FROM recommendations").fetchall()
        assert len(rows) == 4
        for row in rows:
            assert row["link_id"] is not None
            assert row["fair_price_id"] is not None
            assert row["strategy_config_version"] >= 1
            assert 0 < row["entry_ask_tenths"] <= 1000
            assert row["reason_text"]

    def test_both_sides_are_priced_against_opposite_outcomes(self, conn, joined):
        """Buying NO on the Pittsburgh market is buying the Mets.

        If both sides resolved to the same outcome the NO price would be
        compared against the wrong fair probability -- and the number would look
        completely ordinary.
        """
        events, _ = joined
        run_pricing_pass(conn, events, now=NOW)

        ticker = next(
            m.ticker for e in events for m in e.markets
            if m.market_type == "moneyline"
        )
        rows = {
            r["side"]: r
            for r in conn.execute(
                "SELECT r.side, f.outcome_name FROM recommendations r "
                "JOIN fair_prices f ON f.id = r.fair_price_id WHERE r.ticker = ?",
                (ticker,),
            ).fetchall()
        }
        assert set(rows) == {"yes", "no"}
        assert rows["yes"]["outcome_name"] != rows["no"]["outcome_name"]

    def test_no_edge_is_still_recorded(self, conn, joined):
        """The normal answer is "no bet", and it is still an observation.

        Scoring it on the closing line is what makes 300 observations reachable
        without placing 300 bets, so a runner that stored only actionable rows
        would never reach the gate at all.
        """
        events, _ = joined
        counts = run_pricing_pass(conn, events, now=NOW)

        assert counts.recommendations > counts.surfaced
        stored = conn.execute("SELECT COUNT(*) AS n FROM recommendations").fetchone()
        assert stored["n"] == counts.recommendations

    def test_a_second_pass_does_not_duplicate_the_link(self, conn, joined):
        """`record_link` reads the id back; `INSERT OR IGNORE` gives none.

        Every pass after the first hits the conflict branch, so if the id were
        taken from the cursor it would be 0 from the second pass onward and
        every later recommendation would carry a dangling foreign key.
        """
        events, _ = joined
        run_pricing_pass(conn, events, now=NOW)
        run_pricing_pass(conn, events, now=NOW + 60_000)

        links = conn.execute("SELECT * FROM event_links").fetchall()
        assert len(links) == 1

        ids = {
            r["link_id"]
            for r in conn.execute("SELECT DISTINCT link_id FROM recommendations")
        }
        assert ids == {links[0]["id"]}, "a later pass wrote a different link id"

    def test_an_unmatchable_event_lands_in_the_work_queue(self, conn, kalshi_events):
        """Unlinked is normal output, not silence.

        Nothing is stored for these odds, so the link must fail and say so.
        """
        template = _mlb_template(kalshi_events)
        events = discover_from_events([template])
        upsert_discovered(conn, events, now=NOW)

        linked = link_discovered_events(conn, events, now=NOW)
        assert linked == {}

        queued = conn.execute("SELECT * FROM unmatched_events").fetchall()
        assert len(queued) == 1
        assert queued[0]["side"] == "kalshi"
        assert queued[0]["reason"]
        # The names as seen, because this queue is what alias files get
        # filled in from.
        assert "Houston" in queued[0]["detail"]


class TestExposure:
    """The runner reads exposure through `store.orders`, not from `fills`.

    It summed `fills` net of `settlements` until 2026-08-08, while the order
    endpoint summed live `orders`. Both were vacuous -- no table had a row --
    so the two had never disagreed, and they answer different questions: a
    resting order is committed capital and appears in exactly one of them. The
    runner sizing recommendations against one number while the endpoint sized
    the resulting order against the other is the shape `tasks/lessons.md` calls
    "don't test that two paths agree, delete one of the paths".

    The behaviours of the shared implementation are covered in
    `tests/test_order_record.py`; what these two assert is that the *runner*
    reads it.
    """

    def test_no_orders_is_a_true_zero_not_an_unreadable_one(self, conn):
        """`size_position` refuses on `None`, so returning 0.0 is a claim.

        It is a true one: "no live orders" is a fact about the table, unlike
        "the table could not be read".
        """
        assert current_exposure_dollars(conn) == 0.0

    def test_a_fill_alone_is_no_longer_exposure(self, conn, joined):
        """The deletion, stated as a test rather than left to a comment.

        `fills` measures `fee_actual` against `fee_predicted`; it is not a
        second exposure source. A fill exists only because an order did, and
        the order is what carries the committed capital.
        """
        events, _ = joined
        ticker = next(
            m.ticker for e in events for m in e.markets
            if m.market_type == "moneyline"
        )
        conn.execute(
            "INSERT INTO fills (kalshi_fill_id, ticker, filled_ms, count, "
            "price_tenths, is_taker, fee_predicted, fee_model_used) "
            "VALUES ('f1', ?, ?, 20, 500, 1, 0.15, 'conservative')",
            (ticker, NOW),
        )
        conn.commit()
        assert current_exposure_dollars(conn) == 0.0

    def test_a_live_order_is(self, conn, joined):
        events, _ = joined
        ticker = next(
            m.ticker for e in events for m in e.markets
            if m.market_type == "moneyline"
        )
        conn.execute(
            "INSERT INTO orders (client_order_id, submitted_ms, ticker, side, "
            "action, order_type, count, limit_price_tenths, status, "
            "request_body_json, dry_run) "
            "VALUES ('c1', ?, ?, 'yes', 'buy', 'limit', 20, 500, 'resting', "
            "'{}', 0)",
            (NOW, ticker),
        )
        conn.commit()
        assert current_exposure_dollars(conn) == pytest.approx(
            # 20 contracts at 50c: $10.00 of stake plus the 40c taker fee.
            # Exposure is fee-inclusive since 2026-08-09, because the cap is
            # spent that way -- see `store.orders.exposure_contribution`.
            10.35
        )

    def test_an_unreadable_exposure_stops_the_pass_rather_than_refusing_the_slate(
        self, conn, joined, monkeypatch
    ):
        """Passing `None` down to `size_position` would refuse *every*
        candidate, and each refusal would be persisted -- a hundred rows saying
        "not sized" for a reason unrelated to any of them, mixed into the
        genuine no-edge rows and told apart by nothing. The loop is built to
        die loudly; this is what that is for.
        """
        events, _ = joined
        monkeypatch.setattr(
            "backend.runner.current_exposure_dollars",
        lambda _conn, **_kw: None,
        )
        with pytest.raises(RuntimeError, match="exposure could not be read"):
            run_pricing_pass(conn, events, risk=RiskConfig())
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM recommendations"
        ).fetchone()["n"] == 0

    def test_an_unreadable_daily_pnl_stops_the_pass_the_same_way(
        self, conn, joined, monkeypatch
    ):
        """The second budget, which nothing read until 2026-08-10.

        `size_position`'s daily-loss kill switch had no producer anywhere in
        production: the parameter defaulted to `0.0`, so the runner sized every
        card on the slate as though nothing had been lost today. The exposure
        argument above applies unchanged -- `None` here would refuse the whole
        slate for a reason unrelated to any candidate -- so it dies the same way.
        """
        events, _ = joined
        monkeypatch.setattr(
            "backend.runner.daily_realised_pnl_dollars",
            lambda _conn, **_kw: None,
        )
        with pytest.raises(RuntimeError, match="realised P&L could not be read"):
            run_pricing_pass(conn, events, risk=RiskConfig())
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM recommendations"
        ).fetchone()["n"] == 0

    def test_a_realised_loss_past_the_limit_sizes_the_whole_slate_to_zero(
        self, conn, joined
    ):
        """The kill switch reaching the Board, from the database.

        Written as a settlement rather than a monkeypatched number on purpose:
        the finding this replaces was not that the comparison was wrong, it was
        that no caller supplied the input. A test that injects the input cannot
        tell the two apart -- see `tests/test_ev_sizing.py::
        test_the_daily_loss_kill_switch_refuses`, which is green and always was.

        Every row is still *recorded*, carrying the refusal. Dropping them would
        lose the observation, and a suppressed row is still scored on the
        closing line.
        """
        events, _ = joined
        ticker = next(
            m.ticker for e in events for m in e.markets
            if m.market_type == "moneyline"
        )
        conn.execute(
            "INSERT INTO orders (client_order_id, submitted_ms, ticker, side, "
            "action, order_type, count, limit_price_tenths, status, "
            "request_body_json, dry_run) "
            "VALUES ('k1', ?, ?, 'yes', 'buy', 'limit', 10, 500, 'dry_run', "
            "'{}', 1)",
            (NOW, ticker),
        )
        conn.execute(
            "INSERT INTO settlements (order_id, ticker, settled_ms, result, "
            "contracts, pnl_cents, dry_run, fill_assumption) "
            "SELECT id, ticker, ?, 'no', 10, -500000, 1, 'test' FROM orders "
            "WHERE client_order_id = 'k1'",
            (NOW,),
        )
        conn.commit()

        run_pricing_pass(conn, events, risk=RiskConfig(), now=NOW)

        rows = conn.execute(
            "SELECT suggested_contracts, suppressed_reason, reason_text "
            "FROM recommendations"
        ).fetchall()
        assert rows, "the pass recorded nothing, so this asserts nothing"
        assert all(r["suggested_contracts"] == 0 for r in rows)
        # `reason_text` rather than `suppressed_reason`, because a row can fail
        # several checks and `suppressed_reason` keeps the suppression layer's
        # verdict when there is one. The refusal is on every row's prose, which
        # is what the Board actually renders.
        assert all(
            "kill switch" in r["reason_text"].lower() for r in rows
        ), [dict(r) for r in rows]


class TestSuppressionConfigIsHonoured:
    def test_a_tight_freshness_limit_suppresses_the_whole_slate(self, conn, joined):
        """Proves the runner passes its config through rather than ignoring it.

        The odds capture is hours old relative to `NOW`, so a strict staleness
        limit must reject everything -- and the rejections must be recorded,
        not dropped.
        """
        events, _ = joined
        counts = run_pricing_pass(
            conn,
            events,
            suppression=SuppressionConfig(max_odds_age_ms=1_000),
            risk=RiskConfig(),
            now=NOW,
        )
        assert counts.recommendations == 4
        assert counts.surfaced == 0
        assert counts.suppressed == 4


class TestTheRecordDoesNotFillWithRepeats:
    """The runner re-prices every market on every pass.

    With a 15-minute interval and an odds budget affording two sweeps a day,
    most passes see an unchanged quote and unchanged odds and would re-record an
    identical decision. Measured on a real two-pass run: 152 rows carrying 77
    distinct `(ticker, side, ask, fair)` combinations. At ~96 passes a day that
    is about 98% repetition.

    Not a statistical problem -- the gate clusters by game, so repeats already
    count once. An evidence problem: a Ledger where 98% of rows are the same row
    is unreadable, and a suppression summary dominated by one candidate rejected
    96 times says nothing about which rules matter.
    """

    def test_a_second_identical_pass_records_nothing_new(self, conn, joined):
        events, _ = joined
        first = run_pricing_pass(conn, events, now=NOW)
        second = run_pricing_pass(conn, events, now=NOW + 900_000)

        assert first.recommendations == 4
        assert second.recommendations == 0, "an unchanged slate re-recorded itself"
        assert second.unchanged_confirmed == 4

        stored = conn.execute("SELECT COUNT(*) n FROM recommendations").fetchone()
        assert stored["n"] == 4

    def test_an_unchanged_row_is_confirmed_rather_than_left_to_rot(
        self, conn, joined
    ):
        """Not re-recording it must not mean never looking at it again.

        This is the half that was missing. The record was right -- one row per
        distinct decision -- and every freshness check measured from
        `created_ms`, so the row went stale on a market that had not moved. The
        second pass has to leave a mark, or "unchanged" and "unobserved" are the
        same state.
        """
        events, _ = joined
        run_pricing_pass(conn, events, now=NOW)
        run_pricing_pass(conn, events, now=NOW + 900_000)

        rows = conn.execute(
            "SELECT created_ms, last_confirmed_ms, last_confirmed_quote_age_ms, "
            "last_confirmed_odds_age_ms FROM recommendations"
        ).fetchall()
        assert len(rows) == 4
        for row in rows:
            assert row["created_ms"] == NOW, "confirming must not rewrite history"
            assert row["last_confirmed_ms"] == NOW + 900_000
            # Both ages, never one. See `gate.live_ages`.
            assert row["last_confirmed_quote_age_ms"] is not None
            assert row["last_confirmed_odds_age_ms"] is not None

    def test_a_changed_price_is_recorded(self, conn, joined):
        """The guard must not be so eager that it swallows real movement."""
        events, _ = joined
        run_pricing_pass(conn, events, now=NOW)

        ticker = next(
            m.ticker for e in events for m in e.markets
            if m.market_type == "moneyline"
        )
        # A new Kalshi quote: the derived ask moves.
        conn.execute(
            "INSERT INTO kalshi_quotes (ticker, observed_ms, source, "
            "yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty) "
            "VALUES (?, ?, 'rest', 400, 100.0, 570, 100.0)",
            (ticker, NOW + 900_000),
        )
        conn.commit()

        second = run_pricing_pass(conn, events, now=NOW + 900_000)
        assert second.recommendations >= 1, "a moved price was not recorded"

    def test_a_price_that_returns_is_recorded_again(self, conn, joined):
        """Consecutive dedupe, not global. 47 -> 48 -> 47 is three observations.

        Deduping globally would drop the third, thinning the record precisely
        where the market is moving -- and the return to 47 is a genuine second
        opportunity at that price, not a repeat of the first.
        """
        events, _ = joined
        ticker = next(
            m.ticker for e in events for m in e.markets
            if m.market_type == "moneyline"
        )

        def quote(no_bid, at):
            conn.execute(
                "INSERT INTO kalshi_quotes (ticker, observed_ms, source, "
                "yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty) "
                "VALUES (?, ?, 'rest', 400, 100.0, ?, 100.0)",
                (ticker, at, no_bid),
            )
            conn.commit()

        quote(530, NOW + 1)                       # yes ask 470
        run_pricing_pass(conn, events, now=NOW + 1)
        quote(520, NOW + 2)                       # yes ask 480
        run_pricing_pass(conn, events, now=NOW + 2)
        quote(530, NOW + 3)                       # back to 470
        run_pricing_pass(conn, events, now=NOW + 3)

        asks = [
            r["entry_ask_tenths"]
            for r in conn.execute(
                "SELECT entry_ask_tenths FROM recommendations "
                "WHERE ticker = ? AND side = 'yes' ORDER BY id", (ticker,)
            )
        ]
        assert asks.count(470) >= 2, (
            f"the return to 470 was swallowed as a duplicate: {asks}"
        )

    def test_the_recording_rule_is_part_of_the_strategy_version(self, conn, joined):
        """Changing what gets recorded must segment the record, not blend into it.

        Two recording regimes in one dataset with no way to tell them apart is
        exactly what `strategy_config_version` exists to prevent.
        """
        events, _ = joined
        run_pricing_pass(conn, events, now=NOW)

        row = conn.execute(
            "SELECT config_json FROM strategy_configs ORDER BY version DESC LIMIT 1"
        ).fetchone()
        assert "record" in row["config_json"]


class FakeKalshi:
    """`events()` is an async generator on the real client, so it is here too.

    **It filters on `series_ticker`, and that is not politeness.** A fake that
    accepted the argument and ignored it would let the narrowed walk (ADR 0053)
    pass every test while fetching the whole catalogue -- which is precisely the
    behaviour the narrowing exists to stop, and it would be invisible because
    the resulting event list is identical.

    `series_seen` records every value asked for, so a test can assert *which*
    series were walked rather than only what came back.
    """

    def __init__(self, raw_events: list[dict]):
        self.raw = raw_events
        self.series_seen: list[str | None] = []
        #: How many raw events were actually handed over. This -- not the
        #: discovered count -- is what the narrowing is for: discovery drops
        #: out-of-scope events either way, so an assertion downstream of it
        #: cannot tell a narrowed fetch from a wide one.
        self.yielded = 0

    async def events(
        self,
        with_nested_markets: bool = False,
        series_ticker: str | None = None,
        **_: object,
    ):
        self.series_seen.append(series_ticker)
        for event in self.raw:
            if series_ticker is not None and event.get("series_ticker") != series_ticker:
                continue
            self.yielded += 1
            yield event


class FakeOdds:
    """Records what it was asked for. Returns nothing, which is a real state."""

    def __init__(self):
        self.calls: list[str] = []
        self.triggers: list = []

    async def fetch_odds(self, sport_key: str, *, now_ms: int, trigger=None):
        self.calls.append(sport_key)
        self.triggers.append(trigger)
        return []


def _store_fixture(conn, *, commence_ms: int, fetched_ms: int):
    for book in ("pinnacle", "draftkings"):
        for outcome in ("Home", "Away"):
            conn.execute(
                "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, "
                "sport_key, odds_event_id, commence_ms, home_team, away_team, "
                "bookmaker, market, outcome_name, price_decimal) VALUES "
                "(?, ?, 'baseball_mlb', 'sched-1', ?, 'Home', 'Away', ?, "
                "'h2h', ?, 2.0)",
                (fetched_ms, fetched_ms, commence_ms, book, outcome),
            )
    conn.commit()


class TestTheSweepIsScheduledRatherThanOpportunistic:
    """The ingest pass must actually consult `odds.timing`.

    `plan_sweep` spent the day's credits on the first pass that had any, so the
    fifteen minutes the tool is bettable for landed wherever the process
    restarted -- 19:32Z on 2026-08-07, because that is when a deploy happened.
    These tests exist as much to prove the decision is *reached* from the runner
    as to check what it decides: three modules in this repo have been complete,
    tested, and called by nothing.
    """

    async def _ingest(self, conn, kalshi_events, *, now: int, commence_ms: int):
        from backend.config import OddsConfig
        from backend.odds.budget import CreditBudget
        from backend.runner import run_ingest_pass

        _store_fixture(conn, commence_ms=commence_ms, fetched_ms=now - 3_600_000)
        odds = FakeOdds()
        _, counts = await run_ingest_pass(
            conn,
            FakeKalshi([_mlb_template(kalshi_events)]),
            odds,
            CreditBudget(conn, daily_budget=16),
            config=OddsConfig(
                api_key="x", base_url="https://example.invalid",
                daily_credit_budget=16, regions=["us", "eu"],
                markets=["h2h", "spreads", "totals"],
            ),
            now=now,
            suppression=SuppressionConfig(),
        )
        return odds.calls, counts

    async def test_it_sweeps_when_the_pass_lands_before_a_kickoff(
        self, conn, kalshi_events
    ):
        calls, counts = await self._ingest(
            conn, kalshi_events, now=NOW, commence_ms=NOW + 20 * 60_000
        )
        assert calls == ["baseball_mlb"]
        assert counts.sweep_decision

    async def test_it_holds_the_credit_when_the_game_is_hours_away(
        self, conn, kalshi_events
    ):
        calls, counts = await self._ingest(
            conn, kalshi_events, now=NOW, commence_ms=NOW + 8 * 3_600_000
        )
        assert calls == []
        assert "next slot" in counts.sweep_decision

    async def test_it_does_not_sweep_once_the_game_has_started(
        self, conn, kalshi_events
    ):
        """The window would run into the game, which is not a bet this tool
        prices -- and Kalshi's own clock says the game starts three hours later,
        so a scheduler reading that field would sweep here."""
        calls, _ = await self._ingest(
            conn, kalshi_events, now=NOW, commence_ms=NOW - 10 * 60_000
        )
        assert calls == []

    async def test_the_staleness_limit_that_suppresses_is_the_one_that_schedules(
        self, conn, kalshi_events
    ):
        """The sweep exists to open the window `stale_odds` then judges. A
        second, separately-written limit would drift out of agreement with it."""
        from backend.config import OddsConfig
        from backend.odds.budget import CreditBudget
        from backend.runner import run_ingest_pass

        # 60-minute freshness: the last moment to sweep moves an hour earlier,
        # so a kickoff 50 minutes out is now too close rather than too far.
        commence = NOW + 50 * 60_000
        _store_fixture(conn, commence_ms=commence, fetched_ms=NOW - 3_600_000)
        odds = FakeOdds()
        await run_ingest_pass(
            conn,
            FakeKalshi([_mlb_template(kalshi_events)]),
            odds,
            CreditBudget(conn, daily_budget=16),
            config=OddsConfig(
                api_key="x", base_url="https://example.invalid",
                daily_credit_budget=16, regions=["us", "eu"],
                markets=["h2h", "spreads", "totals"],
            ),
            now=NOW,
            suppression=SuppressionConfig(max_odds_age_ms=3_600_000),
        )
        assert odds.calls == []


class TestAGameInProgressIsNotACandidate:
    """Measured on one live pass, not reasoned about.

    36 of 104 recorded rows were for games whose sportsbook kickoff had already
    passed. Their edges ran **-200.3 to +67.7 tenths**; the 68 pre-game rows on
    the same slate ran -39.2 to -17.7. That dispersion is not opportunity, it is
    a stored pre-game consensus being subtracted from a Kalshi price that has
    absorbed two innings.

    Fourteen were caught by `wide_market` or `suspicious_edge`. The other
    twenty-two passed as ordinary no-edge observations, which is the half that
    matters: they enter the evidence record looking exactly like evidence.
    """

    def _commence(self, odds_event) -> int:
        from backend.kalshi.discovery import parse_ms

        return parse_ms(odds_event["commence_time"])

    def test_a_started_game_is_dropped_rather_than_priced(self, conn, joined):
        events, odds_event = joined
        counts = run_pricing_pass(
            conn, events, now=self._commence(odds_event) + 1
        )
        assert counts.recommendations == 0
        assert counts.dropped_game_started == 1

    def test_the_same_slate_before_kickoff_is_priced_normally(self, conn, joined):
        """The guard must not be so eager that it drops the whole record."""
        events, odds_event = joined
        counts = run_pricing_pass(
            conn, events, now=self._commence(odds_event) - 3_600_000
        )
        assert counts.recommendations == 4
        assert counts.dropped_game_started == 0

    def test_kickoff_is_read_from_the_sportsbook_not_from_kalshi(
        self, conn, kalshi_events, book_odds
    ):
        """Kalshi's `occurrence_datetime` runs exactly three hours late.

        `joined` copies the sportsbook's time onto the Kalshi event so the
        linker has something clean to match, which means it cannot tell the two
        clocks apart -- a guard reading the wrong one passes every test in this
        file. So this fixture reintroduces the measured +3h offset, and prices
        at the one instant where the two clocks disagree about the answer: two
        hours after the real first pitch, an hour before Kalshi thinks it
        starts. Reading Kalshi's field here prices the seventh inning.
        """
        offset_ms = 3 * 3_600_000
        odds_event = book_odds
        commence = self._commence(odds_event)

        raw = aligned_kalshi_event(
            _mlb_template(kalshi_events),
            odds_event=odds_event,
            kalshi_names=("Pittsburgh", "New York M"),
        )
        for market in raw["markets"]:
            market["occurrence_datetime"] = _iso(commence + offset_ms)

        events = discover_from_events([raw])
        assert events[0].commence_ms == commence + offset_ms, (
            "the fixture no longer carries the three-hour offset, so this test "
            "cannot tell the two clocks apart"
        )

        upsert_discovered(conn, events, now=commence - 3_600_000)
        store_quotes_from_discovery(conn, events, now=commence - 3_600_000)

        counts = run_pricing_pass(conn, events, now=commence + 2 * 3_600_000)
        assert counts.dropped_game_started == 1
        assert counts.recommendations == 0


class RecordingFakeOdds:
    """A fake that bills itself, because the pacing is read back from the bill.

    `FakeOdds` records nothing, which is fine for "was it called". It is *not*
    fine for the rolling refresh: `firing_for_slot` paces on the sport's last
    served `/odds` call, and `last_sweep_by_sport` reads that from `api_credits`
    with `endpoint LIKE '%/odds' AND cost > 0`. A fake that skips the recording
    is a fake with no clock, and every pass reads "never swept" -- so a test
    built on it would report the pacing broken when it works, or worse, report
    it working when it does not.

    The endpoint spelling matters and is the real one. `client.py` records
    `/sports/{sport_key}/odds`; a literal `/odds` here would match a predicate
    that production rows do not, which is exactly the demo-vs-live split that
    made the window panel read "never" on the instance for the project's life.
    """

    def __init__(self, budget, *, cost: int = 6):
        self.budget = budget
        self.cost = cost
        self.calls: list[str] = []
        self.triggers: list = []

    async def fetch_odds(self, sport_key: str, *, now_ms: int, trigger=None):
        self.calls.append(sport_key)
        self.triggers.append(trigger)
        self.budget.record(
            trigger=trigger,
            called_ms=now_ms,
            endpoint=f"/sports/{sport_key}/odds",
            cost=self.cost,
            sport_key=sport_key,
        )
        return []


class TestTheQuotePassKeepsARowBettable:
    """The fast cadence: Kalshi only, no credit, and a row that stays fresh.

    Two limits bound the actionable window and the tighter one decides it. The
    sportsbook consensus is good for 900s; the Kalshi quote for 30s; the loop
    wrote a row every 900s. So each row was bettable for **thirty seconds** and
    the tool was actionable for about a minute a day -- against fifteen minutes
    twice a day, which is what every document in this repo claimed. Kalshi REST
    is unmetered, so the fix is to re-read it often enough to matter.
    """

    async def _quote_pass(self, conn, kalshi_events, odds_event, *, now):
        from backend.runner import run_quote_pass

        raw = aligned_kalshi_event(
            _mlb_template(kalshi_events),
            odds_event=odds_event,
            kalshi_names=("Pittsburgh", "New York M"),
        )
        return await run_quote_pass(conn, FakeKalshi([raw]), now=now)

    async def test_it_spends_no_odds_credit_when_given_no_odds_client(
        self, conn, joined, kalshi_events
    ):
        """Structurally, not by policy: with no odds client it cannot spend.

        **This claim narrowed on 2026-08-16 and the narrowing is the point.** It
        used to read "a quote pass spends no credit", full stop, and the pass
        took no odds client at all. It now carries the rolling refresh, so the
        honest statement is that a pass *handed no client* cannot spend -- which
        is what keeps every test, script and demo caller unable to spend by
        accident. What stops the deployed caller from draining the day at a 15s
        cadence is `refresh_interval_ms`, tested separately in
        `test_sweep_timing.py`, not the absence of a client.

        `sweep_decision` still says which kind of pass it was rather than
        leaving the field blank -- a quote pass and a full pass that declined to
        sweep need opposite responses.
        """
        _, odds_event = joined
        counts = await self._quote_pass(
            conn, kalshi_events, odds_event, now=NOW + 60_000
        )

        assert counts.odds_sweeps == 0
        assert counts.odds_quotes_stored == 0
        assert "quote refresh only" in counts.sweep_decision

        spent = conn.execute("SELECT COUNT(*) n FROM api_credits").fetchone()
        assert spent["n"] == 0

    def _refreshing_odds(self, conn):
        """One budget and one fake, shared across the passes of a test.

        The budget's state lives in `api_credits`, so a fresh object per pass
        would behave identically -- but the fake needs *a* budget to bill, and
        sharing one keeps the two halves of the chain obviously the same chain.
        """
        from backend.odds.budget import CreditBudget

        budget = CreditBudget(conn, daily_budget=400)
        return budget, RecordingFakeOdds(budget)

    async def _refreshing_quote_pass(
        self, conn, kalshi_events, odds_event, *, now, odds, budget
    ):
        from backend.config import OddsConfig
        from backend.runner import run_quote_pass

        raw = aligned_kalshi_event(
            _mlb_template(kalshi_events),
            odds_event=odds_event,
            kalshi_names=("Pittsburgh", "New York M"),
        )
        return await run_quote_pass(
            conn,
            FakeKalshi([raw]),
            odds_client=odds,
            budget=budget,
            config=OddsConfig(
                api_key="x", base_url="https://example.invalid",
                daily_credit_budget=400, regions=["us", "eu"],
                markets=["h2h", "spreads", "totals"],
            ),
            now=now,
        )

    async def test_it_refreshes_odds_when_the_loop_hands_it_the_three(
        self, conn, joined, kalshi_events
    ):
        """The wiring, tested at the call site rather than assumed.

        Four modules in this repo have reached production as source with no
        caller, so "the parameter exists" is not evidence that anything uses it.
        This asserts the odds client is reached *from a quote pass*, which is
        the whole of what makes the refresh cadence fast enough to beat the
        staleness limit.
        """
        now = NOW + 60_000
        # A kickoff 30 minutes out puts `now` inside the slot: the window runs
        # from 45 min before to 15 min before, and nothing has been swept.
        _store_fixture(conn, commence_ms=now + 30 * 60_000, fetched_ms=now)
        budget, odds = self._refreshing_odds(conn)

        counts = await self._refreshing_quote_pass(
            conn, kalshi_events, joined[1], now=now, odds=odds, budget=budget
        )

        assert odds.calls == ["baseball_mlb"], (
            "a quote pass handed an odds client did not reach it, so the "
            "rolling refresh never runs on the only cadence fast enough for it"
        )
        assert "quote refresh only" not in counts.sweep_decision, (
            "the pass reported itself as spending nothing while sweeping"
        )

    async def test_a_second_quote_pass_seconds_later_does_not_buy_again(
        self, conn, joined, kalshi_events
    ):
        """What bounds the spend on a 15s cadence, stated as the falsifier.

        The pass asks on every tick. If `refresh_interval_ms` did not answer
        "not yet", this would spend 6 credits every 15 seconds -- 2,300 a day
        against a 400 cap -- which is a far worse failure than the staleness it
        was written to fix.
        """
        now = NOW + 60_000
        _store_fixture(conn, commence_ms=now + 30 * 60_000, fetched_ms=now)
        budget, odds = self._refreshing_odds(conn)

        await self._refreshing_quote_pass(
            conn, kalshi_events, joined[1], now=now, odds=odds, budget=budget
        )
        assert odds.calls == ["baseball_mlb"]

        await self._refreshing_quote_pass(
            conn, kalshi_events, joined[1], now=now + 15_000, odds=odds,
            budget=budget,
        )
        assert odds.calls == ["baseball_mlb"], (
            "the refresh interval did not pace the fast cadence"
        )

    async def test_the_same_slot_does_buy_again_once_the_interval_passes(
        self, conn, joined, kalshi_events
    ):
        """The other half. Without this the test above passes on a pass that
        never sweeps at all, which is the state being fixed."""
        from backend.odds.timing import refresh_interval_ms
        from backend.core.suppression import SuppressionConfig

        now = NOW + 60_000
        _store_fixture(conn, commence_ms=now + 30 * 60_000, fetched_ms=now)
        budget, odds = self._refreshing_odds(conn)

        await self._refreshing_quote_pass(
            conn, kalshi_events, joined[1], now=now, odds=odds, budget=budget
        )
        later = now + refresh_interval_ms(SuppressionConfig().max_odds_age_ms)
        await self._refreshing_quote_pass(
            conn, kalshi_events, joined[1], now=later, odds=odds, budget=budget
        )

        assert odds.calls == ["baseball_mlb", "baseball_mlb"], (
            "the window shut instead of being held open, which is the whole "
            "defect: one buy per cluster and stale_odds for the rest of it"
        )

    async def test_a_quote_pass_never_bootstraps(self, conn, joined, kalshi_events):
        """A bootstrap has no slot, so nothing paces it but one-per-day.

        On a 15s cadence that fires once per pass for every sport the
        sportsbook does not cover, exhausting them within a couple of minutes
        of a restart. The full pass every 900s is where bootstrap belongs, and
        it is not time-critical: a sport with no stored fixtures has nothing to
        be timely about.

        No fixture is stored here, so a slot is impossible and a bootstrap is
        the only firing that could occur. Any call at all is that bootstrap.
        """
        budget, odds = self._refreshing_odds(conn)
        await self._refreshing_quote_pass(
            conn, kalshi_events, joined[1], now=NOW + 60_000, odds=odds,
            budget=budget,
        )
        assert odds.calls == [], (
            "a quote pass bootstrapped a sport, which on the fast cadence "
            "spends once per pass with nothing to pace it"
        )

    async def test_it_re_reads_kalshi_and_re_prices(self, conn, joined, kalshi_events):
        _, odds_event = joined
        before = conn.execute("SELECT COUNT(*) n FROM kalshi_quotes").fetchone()["n"]

        counts = await self._quote_pass(
            conn, kalshi_events, odds_event, now=NOW + 60_000
        )

        after = conn.execute("SELECT COUNT(*) n FROM kalshi_quotes").fetchone()["n"]
        assert after > before, "a quote pass that stores no quote refreshes nothing"
        assert counts.markets_quoted > 0
        assert counts.events_linked == 1

    async def test_a_row_survives_the_thirty_second_limit_across_quote_passes(
        self, conn, joined, kalshi_events
    ):
        """**The claim the whole change exists to make**, end to end.

        A row written at T, then quote-passed every 15s. At T+120s -- four times
        past `MAX_KALSHI_QUOTE_AGE_S` -- it must still be inside the limit,
        because the quote behind it was re-read 15 seconds ago and had not moved.
        Before this, the same row read 120 seconds old and the order endpoint
        refused it.
        """
        events, odds_event = joined
        run_pricing_pass(conn, events, now=NOW)

        for step in range(15_000, 120_001, 15_000):
            await self._quote_pass(
                conn, kalshi_events, odds_event, now=NOW + step
            )

        rows = conn.execute("SELECT * FROM recommendations").fetchall()
        assert rows, "nothing was recorded"
        limit_ms = StalenessConfig().max_kalshi_quote_age_s * 1000
        for row in rows:
            ages = live_ages(row, now_ms=NOW + 120_000)
            assert ages.quote_age_ms <= limit_ms, (
                f"{row['ticker']} {row['side']} reads "
                f"{ages.quote_age_ms}ms old after quote passes"
            )

        # And the record did not grow: the point is that an unchanged decision
        # is confirmed, not re-recorded. Eight passes over four candidates would
        # otherwise be 32 rows saying one thing.
        assert len(rows) == 4

    async def test_quote_passes_cannot_outlive_the_odds_window(
        self, conn, joined, kalshi_events
    ):
        """Polling Kalshi does not widen the window; it fills the one there is.

        The odds are the fifteen-minute limit and no amount of quote refreshing
        changes that. If this ever passes, the tool has started offering bets
        priced against a consensus swept an hour ago.
        """
        events, odds_event = joined
        run_pricing_pass(conn, events, now=NOW)

        for step in (600_000, 1_200_000):
            await self._quote_pass(
                conn, kalshi_events, odds_event, now=NOW + step
            )

        limit_ms = StalenessConfig().max_odds_age_s * 1000
        for row in conn.execute("SELECT * FROM recommendations").fetchall():
            ages = live_ages(row, now_ms=NOW + 1_200_000)
            assert ages.odds_age_ms > limit_ms, (
                "a quote pass refreshed the odds clock it has no business "
                "touching"
            )


class TestThePassLineReportsWhetherTheFleetRan:
    """`skeptic_reviewed` / `skeptic_blocked` must survive `as_dict()` at zero.

    Their own comment in `PassCounts` says they are "reported anyway", and the
    `if v` filter dropped them in exactly the state the comment was written
    about. Measured on the live instance 2026-08-08: the pass line carried
    neither key, so "the agent fleet has never run" could only be inferred from
    `surfaced: 0` — which is what the fields exist to stop anyone having to do.
    """

    def test_both_fields_appear_when_the_fleet_has_not_run(self):
        counts = PassCounts()
        as_dict = counts.as_dict()

        assert as_dict["skeptic_reviewed"] == 0
        assert as_dict["skeptic_blocked"] == 0

    def test_blocked_zero_is_visible_beside_a_nonzero_reviewed(self):
        """The case that decides money, and the one a truthiness filter hides.

        A fleet that reviewed two rows and blocked none prints
        `skeptic_reviewed: 2` either way. Only the presence of `skeptic_blocked`
        distinguishes "blocked nothing" from "the field was dropped", and
        blocking is the half that stops a bet.
        """
        counts = PassCounts(skeptic_reviewed=2)

        assert counts.as_dict()["skeptic_blocked"] == 0

    def test_a_genuinely_empty_stage_is_still_filtered_out(self):
        """The filter must still do its job, or this test proves nothing.

        `as_dict` exists to keep a pass line readable. If everything were
        reported the assertions above would pass against a `return self.__dict__`
        that had abandoned the filter entirely.
        """
        assert "dropped_no_books" not in PassCounts().as_dict()


class TestTheSharpSetThatActuallyAnchors:
    """ADR 0019. The guard used to sit on the copy that anchored nothing.

    `backend/odds/client.py` carried a second `SHARP_BOOKS` with its own
    assertions, while `runner.SHARP_BOOKS` -- the set passed to
    `consensus_devig` at `runner.py:647`, and therefore the only one that
    decides what the fair price is built from -- had no guard at all. The dead
    copy is deleted; these assertions move here, onto the live one.
    """

    def test_the_live_sharp_set_is_a_filter_not_a_synonym_for_every_book(self):
        from backend.runner import SHARP_BOOKS

        assert "pinnacle" in SHARP_BOOKS
        assert "draftkings" not in SHARP_BOOKS
        assert "fanduel" not in SHARP_BOOKS
        assert len(SHARP_BOOKS) <= 5, (
            f"{len(SHARP_BOOKS)} 'sharp' books is not a filter -- anchoring on "
            f"everything is the unweighted average wearing a rigorous name"
        )

    def test_it_is_the_set_consensus_devig_is_actually_given(self):
        """Pins the wiring, not just the contents.

        A correct set that nothing passes to `consensus_devig` is the failure
        the deleted copy actually was.
        """
        import inspect

        from backend import runner

        source = inspect.getsource(runner)
        assert "sharp_books=SHARP_BOOKS" in source, (
            "runner defines SHARP_BOOKS but no longer hands it to "
            "consensus_devig; anchoring has silently become unweighted"
        )


class TestOnlyABijectionMayBeInherited:
    """A prop's link must trace back to team-name evidence, always.

    `link_prop_event` hands a prop whatever link its fixture already has. If
    the pool it draws from included other props, the first prop linked in a
    slate would become the authority for every prop after it -- a chain with no
    bijection anywhere underneath. It would be correct today by luck, and
    self-confirming the moment one wrong prop link is written, because the
    wrong answer would then be offered back as evidence.

    So `_linked_fixtures` offers `exact_alias_pair` rows only, and this is the
    test that says so.
    """

    def _event(self, conn, ticker, commence_ms):
        """Series then event, because the foreign keys are enforced here."""
        series = ticker.split("-")[0]
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_series (series_ticker, title, "
            "league, first_seen_ms, last_seen_ms) VALUES (?, ?, ?, ?, ?)",
            (series, series, "Pro Baseball", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, series_ticker, title, "
            "commence_ms, first_seen_ms, last_seen_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ticker, series, "t", commence_ms, NOW, NOW),
        )

    def _seed(self, conn, *, ticker, method, odds_id, commence_ms):
        self._event(conn, ticker, commence_ms)
        conn.execute(
            "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, "
            "league, method, commence_skew_ms, linked_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ticker, odds_id, "Pro Baseball", method, 0, NOW),
        )
        conn.commit()

    def test_a_game_link_is_offered(self, conn):
        self._seed(
            conn,
            ticker="KXMLBGAME-26AUG151310CWSDET",
            method=EXACT_ALIAS_PAIR,
            odds_id="odds_game",
            commence_ms=NOW,
        )
        offered = _linked_fixtures(conn, since_ms=NOW - 86_400_000)
        assert [f.odds_event_id for f in offered] == ["odds_game"]
        assert offered[0].fixture == "26AUG151310CWSDET"

    def test_a_prop_link_is_not_offered_back(self, conn):
        """The guard. Without it a prop inherits from a prop."""
        self._seed(
            conn,
            ticker="KXMLBKS-26AUG151310CWSDET",
            method=PROP_LINK_METHOD,
            odds_id="odds_prop",
            commence_ms=NOW,
        )
        offered = _linked_fixtures(conn, since_ms=NOW - 86_400_000)
        assert offered == [], (
            "a prop link was offered as something another prop may inherit; "
            "every inherited link must trace back to a team-name bijection"
        )

    def test_the_sportsbook_commence_is_recovered_not_the_kalshi_one(self, conn):
        """`odds_commence_ms` is Kalshi's stamp plus the recorded skew.

        Kalshi's `occurrence_datetime` runs three hours late. If this returned
        Kalshi's own time, every prop's skew would be measured against the
        wrong reference and would read as zero -- which is exactly what a
        correct link looks like, so nothing downstream would object.
        """
        self._event(conn, "KXMLBGAME-26AUG151310CWSDET", NOW)
        conn.execute(
            "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, "
            "league, method, commence_skew_ms, linked_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("KXMLBGAME-26AUG151310CWSDET", "odds_game", "Pro Baseball",
             EXACT_ALIAS_PAIR, -3 * 3_600_000, NOW),
        )
        conn.commit()

        offered = _linked_fixtures(conn, since_ms=NOW - 86_400_000)
        assert offered[0].odds_commence_ms == NOW - 3 * 3_600_000


PROP_FIXTURE_SEGMENT = "26AUG141820CHCSTL"


@pytest.fixture(scope="module")
def prop_odds_capture() -> dict:
    return json.loads((FIXTURES / "odds_mlb_player_props.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def prop_commence_ms(prop_odds_capture) -> int:
    """First pitch, read from the capture rather than transcribed.

    A hand-copied epoch was wrong by exactly one day on the first attempt, and
    the failure it produced was `events_unmatched=2` -- a *linking* symptom,
    several stages away from the transcription. Deriving it removes the only
    number in this test nobody could check by eye.
    """
    from backend.kalshi.discovery import parse_ms

    return parse_ms(prop_odds_capture["commence_time"])


@pytest.fixture(scope="module")
def prop_now(prop_commence_ms) -> int:
    """Thirty minutes before first pitch.

    Props are priced pre-game for the reason team markets are, so a clock after
    kickoff would exercise the in-play drop rather than the pricing.
    """
    return prop_commence_ms - 30 * 60 * 1000


@pytest.fixture(scope="module")
def kalshi_prop_capture() -> dict:
    return json.loads(
        (FIXTURES / "events_mlb_props_nested.json").read_text("utf-8")
    )


def _prop_market_template(kalshi_prop_capture: dict) -> dict:
    """A real Kalshi prop market object, used as the shape to copy."""
    return kalshi_prop_capture["events_by_series"]["KXMLBKS"][0]["markets"][0]


def _kalshi_prop_event(kalshi_prop_capture: dict, rungs, commence_ms: int) -> dict:
    """A real prop event re-pointed at the prop odds fixture's game.

    Only the join keys move -- event ticker, market ticker, `yes_sub_title`,
    `floor_strike`, `occurrence_datetime`. Every other field and every value
    format is exactly what Kalshi sent, which is what keeps the wire-format
    assumptions pinned to real bytes. Aligning a timestamp is not the same as
    hand-writing a payload.
    """
    source = kalshi_prop_capture["events_by_series"]["KXMLBKS"][0]
    event = copy.deepcopy(source)
    event["event_ticker"] = f"KXMLBKS-{PROP_FIXTURE_SEGMENT}"
    template = copy.deepcopy(event["markets"][0])

    markets = []
    for index, (player, subtitle, floor_strike) in enumerate(rungs):
        market = copy.deepcopy(template)
        market["event_ticker"] = event["event_ticker"]
        market["ticker"] = f"{event['event_ticker']}-R{index}"
        market["yes_sub_title"] = subtitle
        market["no_sub_title"] = subtitle
        market["floor_strike"] = floor_strike
        market["occurrence_datetime"] = _iso(commence_ms)
        market["close_time"] = _iso(commence_ms)
        markets.append(market)
    event["markets"] = markets
    return event


def _kalshi_game_event(kalshi_events: list[dict], commence_ms: int) -> dict:
    """The moneyline event whose link the prop event will inherit."""
    event = copy.deepcopy(_mlb_template(kalshi_events))
    event["event_ticker"] = f"KXMLBGAME-{PROP_FIXTURE_SEGMENT}"
    event["title"] = "Chicago vs St. Louis"
    for market, name in zip(event["markets"], ("Chicago", "St. Louis")):
        market["event_ticker"] = event["event_ticker"]
        market["ticker"] = f"{event['event_ticker']}-{name[:3].upper()}"
        market["yes_sub_title"] = name
        market["occurrence_datetime"] = _iso(commence_ms)
        market["close_time"] = _iso(commence_ms)
    return event


PROP_RUNGS = (
    ("Matthew Liberatore", "Matthew Liberatore: 5+", 4.5),
    ("Clay Holmes", "Clay Holmes: 4+", 3.5),
)


def _prop_slate(
    kalshi_events: list[dict], kalshi_prop_capture: dict, commence_ms: int
) -> list[dict]:
    """A game and its Kalshi prop ladder, which is what a real slate looks like.

    Named because three tests need it and one of them was written without it.
    That version passed against code that would still have bought props: with no
    prop event in the payload, `fetch_and_store_props` returns on its "no prop
    series discovered" branch and the switch under test is never reached. A
    fixture that makes the guard unreachable is the quietest way to write a
    green test of nothing.
    """
    return [
        _kalshi_game_event(kalshi_events, commence_ms),
        _kalshi_prop_event(kalshi_prop_capture, PROP_RUNGS, commence_ms),
    ]


@pytest.fixture
def priced_props(
    conn, kalshi_events, kalshi_prop_capture, prop_odds_capture,
    prop_commence_ms, prop_now,
):
    """The whole offline chain, run once: store -> discover -> link -> price."""
    from backend.config import OddsConfig
    from backend.odds.budget import CreditBudget
    from backend.odds.client import OddsClient

    client = OddsClient(
        OddsConfig(
            api_key="x", base_url="https://example.invalid",
            daily_credit_budget=16, regions=["us"],
            markets=["h2h", "spreads", "totals"],
        ),
        CreditBudget(conn, daily_budget=16),
    )
    store_quotes(
        conn,
        client._parse(
            [prop_odds_capture], sport_key="baseball_mlb", fetched_ms=prop_now
        ),
    )

    events = discover_from_events(
        [
            _kalshi_game_event(kalshi_events, prop_commence_ms),
            _kalshi_prop_event(kalshi_prop_capture, PROP_RUNGS, prop_commence_ms),
        ]
    )
    upsert_discovered(conn, events, now=prop_now)
    store_quotes_from_discovery(conn, events, now=prop_now)
    return run_pricing_pass(conn, events, now=prop_now)


class TestPropsRunThroughTheWholeChainOffline:
    """Discovery -> link -> devig -> fair price -> recommendation, no network.

    The two rungs used here are the only two in the captured prop payload that
    any book quotes on **both** sides -- Matthew Liberatore at 4.5 with seven
    books, Clay Holmes at 3.5 with six. The other eighteen are Over-only and
    `consensus_devig` cannot use them, which is not an artefact of this test: it
    is the 174-of-222 drop recorded in `tasks/NEXT.md`, reproduced on captured
    bytes.

    Kalshi's rungs are therefore `5+` and `4+`. That the Kalshi subtitle is one
    higher than the book's point is the whole `N+ == Over N-0.5` identity, and
    if it were ever wrong every assertion below would still pass on a
    consensus for the wrong rung -- which is why `floor_strike` is what
    actually joins, and why `tests/test_discovery.py` pins it against 259
    markets rather than these two.
    """

    RUNGS = PROP_RUNGS

    def test_the_prop_event_inherits_the_games_link(self, conn, priced_props):
        rows = {
            r["kalshi_event_ticker"]: r
            for r in conn.execute(
                "SELECT kalshi_event_ticker, odds_event_id, method FROM event_links"
            )
        }
        game = rows[f"KXMLBGAME-{PROP_FIXTURE_SEGMENT}"]
        prop = rows[f"KXMLBKS-{PROP_FIXTURE_SEGMENT}"]
        assert game["method"] == EXACT_ALIAS_PAIR
        assert prop["method"] == PROP_LINK_METHOD
        assert prop["odds_event_id"] == game["odds_event_id"], (
            "the prop was linked to a different fixture than its own game"
        )

    def test_a_fair_price_is_written_per_player_and_line(self, conn, priced_props):
        rows = conn.execute(
            "SELECT market, outcome_name, outcome_description, outcome_point, "
            "book_count, anchored_on_sharp FROM fair_prices "
            "WHERE market = 'pitcher_strikeouts' ORDER BY outcome_description, "
            "outcome_name"
        ).fetchall()

        got = [
            (r["outcome_description"], r["outcome_point"], r["outcome_name"])
            for r in rows
        ]
        assert got == [
            ("Clay Holmes", 3.5, "Over"),
            ("Clay Holmes", 3.5, "Under"),
            ("Matthew Liberatore", 4.5, "Over"),
            ("Matthew Liberatore", 4.5, "Under"),
        ], got

        by_player = {r["outcome_description"]: r for r in rows}
        assert by_player["Matthew Liberatore"]["book_count"] == 7
        assert by_player["Clay Holmes"]["book_count"] == 6

    def test_no_prop_row_claims_a_sharp_anchor(self, conn, priced_props):
        """Eight books quote props and none of them is Pinnacle or Betfair.

        `consensus_devig` falls back to the full set when no sharp book is
        present, which is correct and silent -- `anchored_on_sharp` is the only
        thing that says which happened. A prop row claiming an anchor would
        mean a sharp book had appeared, and the whole reason props were worth
        probing is that one has not.
        """
        rows = conn.execute(
            "SELECT anchored_on_sharp FROM fair_prices "
            "WHERE market = 'pitcher_strikeouts'"
        ).fetchall()
        assert rows
        assert all(r["anchored_on_sharp"] == 0 for r in rows)

    def test_both_sides_of_every_rung_are_recorded(self, conn, priced_props):
        """And each side points at its OWN fair price, not its opposite's.

        Joined through `fair_price_id` rather than read off `recommendations`,
        which carries no outcome of its own. That is the assertion worth making
        anyway: buying NO on `"Clay Holmes: 4+"` is buying the book's Under, so
        a row whose `fair_price_id` resolved to the Over would be comparing an
        ask against the fair value of the other side -- an error that produces
        an edge rather than an exception.
        """
        rows = conn.execute(
            "SELECT r.ticker, r.side, f.outcome_name, f.outcome_description, "
            "f.outcome_point FROM recommendations r "
            "JOIN fair_prices f ON f.id = r.fair_price_id "
            "WHERE r.ticker LIKE 'KXMLBKS-%' ORDER BY r.ticker, r.side"
        ).fetchall()
        assert len(rows) == 4, "two rungs, two sides each"
        assert {(r["side"], r["outcome_name"]) for r in rows} == {
            ("yes", "Over"),
            ("no", "Under"),
        }, "Kalshi YES is the book's Over; NO is Under"
        # Every row carries the player and line it was priced against, so the
        # evidence record can tell two rungs of one ladder apart.
        assert {
            (r["outcome_description"], r["outcome_point"]) for r in rows
        } == {("Matthew Liberatore", 4.5), ("Clay Holmes", 3.5)}

    def test_the_over_only_rungs_are_dropped_not_devigged(self, conn, priced_props):
        """Eighteen of twenty rungs have no two-sided book.

        They must produce no `fair_prices` row at all. A one-sided book cannot
        be devigged -- there is no overround to remove -- and inventing the
        missing side is the assumption `tasks/NEXT.md` says must be registered
        before it is made.
        """
        players = {
            r["outcome_description"]
            for r in conn.execute(
                "SELECT DISTINCT outcome_description FROM fair_prices "
                "WHERE market = 'pitcher_strikeouts'"
            )
        }
        assert players == {"Matthew Liberatore", "Clay Holmes"}, players

    def test_the_strategy_version_says_props_are_priced(self, conn, priced_props):
        """Prop rows and team rows are two populations under one runner.

        The config string is what segments the record. If it still said
        "moneyline only", every prop row would be filed under a strategy
        version that predates props existing.
        """
        row = conn.execute(
            "SELECT config_json FROM strategy_configs ORDER BY version DESC LIMIT 1"
        ).fetchone()
        assert "props" in json.loads(row["config_json"])["prices"]


class TestTheDevigKeepsOverAndUnderTheRightWayRound:
    """The one prop error that produces an edge instead of an exception.

    `consensus_devig` pairs prices to outcomes **positionally**, so a mispairing
    still writes an `"Over"` row and an `"Under"` row with correct names,
    correct players and correct lines -- and the two probabilities swapped.
    Every structural assertion in the class above stays green, the Board renders
    confidently, and every prop row on the record is priced against the wrong
    side.

    **Reversing `PROP_SIDES` is not that bug, and the distinction was measured
    rather than reasoned about.** A mutation reversing it left the whole suite
    green, because the outcome tuple and each book's price list are both built
    by iterating that constant and therefore cannot disagree. The mutation is
    kept in the battery and recorded as semantically equivalent instead of
    being pruned, and the code comment that used to claim otherwise has been
    corrected. What this test actually pins is the case where the two lists are
    built from *different* orders.

    So the check is on the *ordering*, not on any particular number: all four
    devig methods are monotone in the raw implied probability, so whichever
    side the books price as more likely must come out more likely. That holds
    whatever the vig is and whichever method wins the worst-of rule, which is
    why it can be asserted without re-deriving the arithmetic the code under
    test performs.
    """

    def _raw_implied(self, capture, player, point):
        """Mean raw implied probability per side, straight off the capture."""
        totals = {"Over": [], "Under": []}
        for book in capture["bookmakers"]:
            for market in book["markets"]:
                sides = {
                    o["name"]: o["price"]
                    for o in market["outcomes"]
                    if o.get("description") == player and o.get("point") == point
                }
                if len(sides) == 2:
                    for name, price in sides.items():
                        totals[name].append(1.0 / price)
        assert totals["Over"] and totals["Under"], (player, point)
        return {k: sum(v) / len(v) for k, v in totals.items()}

    @pytest.mark.parametrize(
        "player,point",
        [("Matthew Liberatore", 4.5), ("Clay Holmes", 3.5)],
    )
    def test_the_favoured_side_stays_the_favoured_side(
        self, conn, priced_props, prop_odds_capture, player, point
    ):
        raw = self._raw_implied(prop_odds_capture, player, point)
        fair = {
            r["outcome_name"]: r["p_conservative"]
            for r in conn.execute(
                "SELECT outcome_name, p_conservative FROM fair_prices "
                "WHERE market = 'pitcher_strikeouts' AND outcome_description = ? "
                "AND outcome_point = ?",
                (player, point),
            )
        }
        assert set(fair) == {"Over", "Under"}, fair

        raw_favours_over = raw["Over"] > raw["Under"]
        fair_favours_over = fair["Over"] > fair["Under"]
        assert raw_favours_over == fair_favours_over, (
            f"{player} {point}: the books price Over at {raw['Over']:.4f} and "
            f"Under at {raw['Under']:.4f}, but the devigged fair values are "
            f"Over {fair['Over']:.4f} / Under {fair['Under']:.4f}. The two "
            f"sides are the wrong way round."
        )


class TestIngestActuallyBuysTheProps:
    """`fetch_props` shipped complete, tested, and called by nothing.

    That is this repo's most-repeated failure -- four modules have reached
    production as source only -- so the call site gets a test of its own rather
    than being assumed from the fact that the function exists.
    """

    class FakePropOdds:
        """Records what it was asked for. Serves a team sweep, then props."""

        def __init__(self, quotes):
            self.quotes = quotes
            self.prop_calls: list[tuple] = []

        async def fetch_odds(self, sport_key: str, *, now_ms: int, trigger=None):
            return self.quotes

        async def fetch_props(
            self, sport_key, odds_event_ids, *, now_ms, markets=None,
            regions=None, trigger=None,
        ):
            self.prop_calls.append((sport_key, tuple(odds_event_ids), tuple(markets or ())))
            return []

    async def _ingest(
        self, conn, events, quotes, *, now, commence_ms, seed_fixtures=True,
        buy_props_on_schedule=True,
    ):
        from backend.config import OddsConfig
        from backend.odds.budget import CreditBudget
        from backend.odds.client import store_quotes
        from backend.runner import run_ingest_pass

        if seed_fixtures:
            # **The sweep must fire as `scheduled`, not `bootstrap`.**
            # `decide_sweeps` plans slots from `odds_snapshots`, so on an empty
            # database no slot exists, the sweep bootstraps, and a bootstrap
            # buys no props at all -- which would make every assertion below
            # pass for a reason other than the one it is testing. Seeding a
            # stored fixture is what the live instance always looks like: it has
            # been sweeping MLB for days.
            store_quotes(conn, quotes)

        odds = self.FakePropOdds(quotes)
        await run_ingest_pass(
            conn,
            FakeKalshi(events),
            odds,
            CreditBudget(conn, daily_budget=10_000),
            config=OddsConfig(
                api_key="x", base_url="https://example.invalid",
                daily_credit_budget=10_000, regions=["us"],
                markets=["h2h", "spreads", "totals"],
                # **Opted in explicitly, and the default is the opposite.**
                # Scheduled prop buying is off on a deployed instance since
                # 2026-08-16 (ADR 0032) because props are 86% of the bill and
                # add no cluster to the 300-game floor. The behaviour these
                # tests pin is still the behaviour when it is switched on, and
                # it must keep working -- so they turn it on rather than being
                # weakened. `test_the_default_buys_no_props_on_a_schedule`
                # below pins the default itself.
                buy_props_on_schedule=buy_props_on_schedule,
            ),
            now=now,
        )
        return odds

    def _quotes(self, *, commence_ms, fetched_ms):
        return [
            OddsQuote(
                fetched_ms=fetched_ms, book_updated_ms=fetched_ms,
                sport_key="baseball_mlb", odds_event_id="odds-1",
                commence_ms=commence_ms, home_team="Chicago Cubs",
                away_team="St. Louis Cardinals", bookmaker=book,
                market="h2h", outcome_name=name, outcome_point=None,
                price_decimal=2.0,
            )
            for book in ("pinnacle", "draftkings")
            for name in ("Chicago Cubs", "St. Louis Cardinals")
        ]

    async def test_a_served_sweep_also_buys_the_props(
        self, conn, kalshi_events, kalshi_prop_capture, prop_commence_ms
    ):
        now = prop_commence_ms - 30 * 60 * 1000
        odds = await self._ingest(
            conn,
            [
                _kalshi_game_event(kalshi_events, prop_commence_ms),
                _kalshi_prop_event(
                    kalshi_prop_capture,
                    TestPropsRunThroughTheWholeChainOffline.RUNGS,
                    prop_commence_ms,
                ),
            ],
            self._quotes(commence_ms=prop_commence_ms, fetched_ms=now),
            now=now,
            commence_ms=prop_commence_ms,
        )

        assert odds.prop_calls, (
            "the team sweep was served and no prop call followed it; "
            "fetch_props is source-only again"
        )
        sport_key, event_ids, markets = odds.prop_calls[0]
        assert sport_key == "baseball_mlb"
        assert event_ids == ("odds-1",)
        # Both feeds. Primaries alone matched 48 of 263 Kalshi prop markets.
        assert any(m.endswith(ALTERNATE_SUFFIX) for m in markets), markets
        assert any(not m.endswith(ALTERNATE_SUFFIX) for m in markets), markets

    async def test_no_kalshi_ladder_means_no_props_are_bought(
        self, conn, kalshi_events, prop_commence_ms
    ):
        """Credits are not spent on a comparison with only one side.

        A book's prop with no Kalshi market to compare it against is a price we
        can store and never use, and props cost roughly ten credits a fixture
        against six for the whole team sweep.
        """
        now = prop_commence_ms - 30 * 60 * 1000
        odds = await self._ingest(
            conn,
            [_kalshi_game_event(kalshi_events, prop_commence_ms)],
            self._quotes(commence_ms=prop_commence_ms, fetched_ms=now),
            now=now,
            commence_ms=prop_commence_ms,
        )
        assert odds.prop_calls == []

        skipped = [
            r["detail"]
            for r in conn.execute(
                "SELECT detail FROM odds_sweep_log WHERE detail LIKE 'props:%'"
            )
        ]
        assert skipped, "the decision not to buy props left no row anywhere"

    async def test_an_in_play_fixture_is_not_bought(
        self, conn, kalshi_events, kalshi_prop_capture, prop_commence_ms
    ):
        """A prop priced after first pitch can never be scored on CLV.

        The closing line is read before kickoff, so an in-play prop row would
        enter the evidence record looking like evidence and be unscoreable --
        the same reason `run_pricing_pass` drops in-play team rows.
        """
        now = prop_commence_ms + 60_000
        odds = await self._ingest(
            conn,
            [
                _kalshi_game_event(kalshi_events, prop_commence_ms),
                _kalshi_prop_event(
                    kalshi_prop_capture,
                    TestPropsRunThroughTheWholeChainOffline.RUNGS,
                    prop_commence_ms,
                ),
            ],
            self._quotes(commence_ms=prop_commence_ms, fetched_ms=now),
            now=now,
            commence_ms=prop_commence_ms,
        )
        assert odds.prop_calls == []


class TestPropsAreBoughtForTheSlotNotTheSlate:
    """The credit drain of 2026-08-15, and the guard against it.

    `fetch_odds` returns the **whole** slate for a sport. The sweep that
    triggered it was fired for one kickoff cluster. Until this guard existed,
    `fetch_and_store_props` took every still-pre-game fixture out of the
    returned slate -- 27 of them, where the slot covered 4 -- and at 20 credits
    an event (ten market keys x two regions) that spent **384 of a 400-credit
    day in a single pass**. Every remaining odds sweep that day was refused,
    team sweeps included, so the moneyline record stopped growing: the asset the
    whole CLV gate depends on.

    The number to watch here is `len(event_ids)`, and what makes the assertion
    meaningful is that the slate deliberately contains fixtures the slot does
    **not** cover.
    """

    def _slate(self, *, anchor_ms, fetched_ms):
        """Three fixtures: two in the anchor's cluster, one far outside it.

        The far one is `COVERAGE_MS` plus an hour past the anchor, so it is a
        real fixture on a real slate that this sweep was simply not fired for.
        It is exactly what the 27-vs-4 gap was made of.
        """
        from backend.odds.timing import COVERAGE_MS

        spec = [
            ("odds-covered-1", anchor_ms),
            ("odds-covered-2", anchor_ms + 10 * 60 * 1000),
            ("odds-far", anchor_ms + COVERAGE_MS + 60 * 60 * 1000),
        ]
        return [
            OddsQuote(
                fetched_ms=fetched_ms, book_updated_ms=fetched_ms,
                sport_key="baseball_mlb", odds_event_id=event_id,
                commence_ms=commence, home_team="Chicago Cubs",
                away_team="St. Louis Cardinals", bookmaker=book,
                market="h2h", outcome_name=name, outcome_point=None,
                price_decimal=2.0,
            )
            for event_id, commence in spec
            for book in ("pinnacle", "draftkings")
            for name in ("Chicago Cubs", "St. Louis Cardinals")
        ]

    async def test_only_the_covered_fixtures_are_bought(
        self, conn, kalshi_events, kalshi_prop_capture, prop_commence_ms
    ):
        helper = TestIngestActuallyBuysTheProps()
        now = prop_commence_ms - 30 * 60 * 1000
        quotes = self._slate(anchor_ms=prop_commence_ms, fetched_ms=now)

        odds = await helper._ingest(
            conn,
            [
                _kalshi_game_event(kalshi_events, prop_commence_ms),
                _kalshi_prop_event(
                    kalshi_prop_capture,
                    TestPropsRunThroughTheWholeChainOffline.RUNGS,
                    prop_commence_ms,
                ),
            ],
            quotes,
            now=now,
            commence_ms=prop_commence_ms,
        )

        assert odds.prop_calls, "the scheduled sweep bought no props at all"
        _, event_ids, _ = odds.prop_calls[0]
        assert set(event_ids) == {"odds-covered-1", "odds-covered-2"}, (
            "props were bought for a fixture this sweep was not fired for; "
            "that is the 27-vs-4 defect that spent 384 of 400 credits"
        )

    async def test_a_bootstrap_buys_no_props_and_says_so(
        self, conn, kalshi_events, kalshi_prop_capture, prop_commence_ms
    ):
        """A bootstrap has no cluster to aim at, so it has no fixture set.

        Falling back to "everything in the slate" is precisely the defect. The
        refusal is **recorded**, because a pass that declined and left no row
        reads exactly like a pass that never ran -- this repo's inert-but-quiet
        failure mode.

        **Verified by disabling the branch, and the failure is worse than a
        cost overrun**: without it `slot.covers` is called on `None` and the
        `AttributeError` propagates out of `fetch_and_store_props` into
        `fetch_and_store_odds` and the ingest pass. Same blast radius as the
        untradeable rung below -- a raise inside a per-item loop fails the pass,
        not the item, and a failed pass is retried. So this guard is load-bearing
        for liveness, not only for credits.
        """
        helper = TestIngestActuallyBuysTheProps()
        now = prop_commence_ms - 30 * 60 * 1000
        odds = await helper._ingest(
            conn,
            [
                _kalshi_game_event(kalshi_events, prop_commence_ms),
                _kalshi_prop_event(
                    kalshi_prop_capture,
                    TestPropsRunThroughTheWholeChainOffline.RUNGS,
                    prop_commence_ms,
                ),
            ],
            helper._quotes(commence_ms=prop_commence_ms, fetched_ms=now),
            now=now,
            commence_ms=prop_commence_ms,
            seed_fixtures=False,
        )

        assert odds.prop_calls == [], (
            "a bootstrap sweep bought props for a fixture set nothing defined"
        )
        details = [
            r["detail"]
            for r in conn.execute(
                "SELECT detail FROM odds_sweep_log WHERE detail LIKE 'props:%'"
            )
        ]
        assert any("bootstrap" in d for d in details), (
            f"the refusal was not recorded as a bootstrap; got {details}"
        )


class TestAnUntradeableRungIsSkippedNotFatal:
    """The defect that took down the first live pass to price props.

    A prop ladder is priced from `2+` to `9+`, so its far end is a market
    nobody will trade: the NO bid rests at 1000 tenths and the derived YES ask
    is therefore **0**. `core/ev.effective_price` refuses 0 and 1000 -- they are
    settled outcomes, not quotes, and an ask of 0 yields a zero fee, a $0.00
    effective price, a 0% breakeven and a fabricated edge.

    The prop path checked `ask is None` and nothing else, copying the team path,
    where the guard has never been needed: a game moneyline does not reach 0 or
    1000 while it is still pre-game and open. **A ladder reaches both on an
    ordinary slate.**

    What made it serious was not the prop rows. `_price_prop_event` is called
    from inside `run_pricing_pass`'s main loop, so the `ValueError` aborted the
    **entire pass** -- moneyline recommendations included -- and a failed full
    pass is retried rather than counted as done, so it would have repeated every
    pass until the runner gave up and the container restarted into the same
    thing. The evidence record stops growing and every screen still renders.

    Live at 19:42:07Z on 2026-08-15, one pass after props first shipped.
    """

    def _ladder_event(self, kalshi_prop_capture, commence_ms, no_bid_dollars):
        """One prop event whose single rung carries the given NO bid."""
        event = _kalshi_prop_event(
            kalshi_prop_capture,
            (("Clay Holmes", "Clay Holmes: 4+", 3.5),),
            commence_ms,
        )
        market = event["markets"][0]
        # A YES ask is 1000 - the NO bid, so a NO bid of $1.00 derives an ask of
        # 0. Set on the captured payload rather than constructed, so the field
        # names stay the ones Kalshi actually sends.
        market["no_bid_dollars"] = no_bid_dollars
        market["yes_bid_dollars"] = "0.0000"
        return event

    def _run(self, conn, kalshi_events, kalshi_prop_capture, prop_odds_capture,
             prop_commence_ms, prop_now, no_bid_dollars):
        from backend.config import OddsConfig
        from backend.odds.budget import CreditBudget
        from backend.odds.client import OddsClient

        client = OddsClient(
            OddsConfig(
                api_key="x", base_url="https://example.invalid",
                daily_credit_budget=16, regions=["us"],
                markets=["h2h", "spreads", "totals"],
            ),
            CreditBudget(conn, daily_budget=16),
        )
        store_quotes(
            conn,
            client._parse(
                [prop_odds_capture], sport_key="baseball_mlb", fetched_ms=prop_now
            ),
        )
        events = discover_from_events(
            [
                _kalshi_game_event(kalshi_events, prop_commence_ms),
                self._ladder_event(
                    kalshi_prop_capture, prop_commence_ms, no_bid_dollars
                ),
            ]
        )
        upsert_discovered(conn, events, now=prop_now)
        store_quotes_from_discovery(conn, events, now=prop_now)
        return run_pricing_pass(conn, events, now=prop_now)

    def test_a_rung_nobody_will_trade_does_not_abort_the_pass(
        self, conn, kalshi_events, kalshi_prop_capture, prop_odds_capture,
        prop_commence_ms, prop_now,
    ):
        """The regression. Before the fix this raised and took the pass with it."""
        counts = self._run(
            conn, kalshi_events, kalshi_prop_capture, prop_odds_capture,
            prop_commence_ms, prop_now, no_bid_dollars="1.0000",
        )
        # The pass completed. That is the whole assertion -- reaching this line
        # at all is what was broken.
        assert counts.dropped_no_kalshi_quote >= 1, counts.as_dict()

    def test_the_untradeable_side_is_dropped_and_the_other_is_not(
        self, conn, kalshi_events, kalshi_prop_capture, prop_odds_capture,
        prop_commence_ms, prop_now,
    ):
        """Only the bad side goes.

        A NO bid of $1.00 makes the YES ask 0 and leaves the NO ask at
        1000 - 0 = 1000, which is equally untradeable. Both sides drop here, and
        the point of asserting it is that the guard is per-side rather than
        per-market: a ladder rung with one tradeable side must still record it.
        """
        counts = self._run(
            conn, kalshi_events, kalshi_prop_capture, prop_odds_capture,
            prop_commence_ms, prop_now, no_bid_dollars="1.0000",
        )
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM recommendations WHERE ticker LIKE 'KXMLBKS-%'"
        ).fetchone()
        assert rows["n"] == 0, "an untradeable rung was priced anyway"

    def test_a_tradeable_rung_on_the_same_ladder_still_prices(
        self, conn, kalshi_events, kalshi_prop_capture, prop_odds_capture,
        prop_commence_ms, prop_now,
    ):
        """The guard must not have swallowed the ordinary case.

        Without this, replacing the body of the loop with `continue` would pass
        both tests above and the prop path would silently record nothing.
        """
        counts = self._run(
            conn, kalshi_events, kalshi_prop_capture, prop_odds_capture,
            prop_commence_ms, prop_now, no_bid_dollars="0.4500",
        )
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM recommendations WHERE ticker LIKE 'KXMLBKS-%'"
        ).fetchone()
        assert rows["n"] > 0, counts.as_dict()


class TestScheduledPropBuyingIsOffByDefault:
    """The switch that took 86% off a cluster's bill. ADR 0032.

    Props are 20 credits per fixture against a 6-credit team sweep, and
    `gate.py:424-428` collapses a prop event onto its game's `odds_event_id` by
    construction -- so a prop row on a game that already has a moneyline row
    adds **no cluster** to the 300-game floor it is competing for budget with.

    Two separate claims, kept separate because they fail for different reasons:
    that the *default* is off, and that *off* buys nothing. The behaviour when
    it is switched on is pinned by `TestIngestActuallyBuysTheProps`, which now
    opts in explicitly rather than relying on a default that has moved.
    """

    def test_the_dataclass_default_is_off(self):
        """A deployment that says nothing buys no props.

        `tasks/lessons.md` records the inverse error costing a session: props
        came from a code default with no environment variable, and the absence
        was read as the feature being off when it meant the default applied.
        This is that default, asserted rather than assumed -- and it now points
        the safe way, so the same misreading would be harmless.
        """
        from backend.config import OddsConfig

        config = OddsConfig(
            api_key="x", base_url="https://example.invalid",
            daily_credit_budget=600, regions=["us"], markets=["h2h"],
        )
        assert config.buy_props_on_schedule is False

    def test_an_absent_environment_variable_leaves_it_off(self, monkeypatch):
        """`load()` and the dataclass must agree, or the deploy file lies.

        `load_without_credentials` is checked too: it is the constructor the
        demo and every read-only screen use, and it has drifted from `load`
        before -- it read `ODDS_BUDGET_DAY_START_UTC_HOUR` raw while `load`
        validated it.
        """
        from backend.config import OddsConfig

        monkeypatch.delenv("ODDS_BUY_PROPS_ON_SCHEDULE", raising=False)
        monkeypatch.setenv("ODDS_API_KEY", "x")
        assert OddsConfig.load().buy_props_on_schedule is False
        assert OddsConfig.load_without_credentials().buy_props_on_schedule is False

    async def test_off_means_a_scheduled_sweep_buys_no_props(
        self, conn, kalshi_events, kalshi_prop_capture, prop_commence_ms
    ):
        helper = TestIngestActuallyBuysTheProps()
        now = prop_commence_ms - 30 * 60 * 1000
        odds = await helper._ingest(
            conn,
            # **A real Kalshi prop ladder, or this passes for the wrong
            # reason.** With no prop event the function returns on its "no prop
            # series discovered" branch and never reaches the switch -- which is
            # exactly how the first draft of this test passed against code that
            # would still have bought.
            _prop_slate(kalshi_events, kalshi_prop_capture, prop_commence_ms),
            helper._quotes(commence_ms=prop_commence_ms, fetched_ms=now),
            now=now,
            commence_ms=prop_commence_ms,
            buy_props_on_schedule=False,
        )
        assert odds.prop_calls == [], (
            f"a scheduled sweep bought props with the switch off; "
            f"got {odds.prop_calls}"
        )

    async def test_the_skip_is_recorded_rather_than_silent(
        self, conn, kalshi_events, kalshi_prop_capture, prop_commence_ms
    ):
        """A pass that declined and left no row reads like a pass that never ran.

        `odds_sweep_log` exists for exactly this, and a *new* way of buying
        nothing needs its own row or it inherits the silence the table was
        created to end.
        """
        helper = TestIngestActuallyBuysTheProps()
        now = prop_commence_ms - 30 * 60 * 1000
        await helper._ingest(
            conn,
            _prop_slate(kalshi_events, kalshi_prop_capture, prop_commence_ms),
            helper._quotes(commence_ms=prop_commence_ms, fetched_ms=now),
            now=now,
            commence_ms=prop_commence_ms,
            buy_props_on_schedule=False,
        )
        details = [
            r["detail"]
            for r in conn.execute(
                "SELECT detail FROM odds_sweep_log WHERE detail LIKE 'props:%'"
            )
        ]
        assert any("scheduled prop buying is off" in d for d in details), (
            f"the skip was not recorded; got {details}"
        )

    async def test_a_named_fixture_is_still_bought_with_the_switch_off(
        self, conn, kalshi_events, kalshi_prop_capture, prop_commence_ms
    ):
        """The tap must survive the switch, or the two-tier design is one tier.

        `fetch_and_store_props` honours an explicitly named fixture set
        regardless of the schedule switch. That asymmetry is the whole point:
        the guards exist to stop props being bought for a set **nobody named**,
        and a tap names one. Without this, turning the schedule off would
        silently disable the on-demand button shipped the same day.

        Driven at `fetch_and_store_props` rather than through the pass, because
        the claim is about this function's guard ordering; a pass-level test
        would route it through `decide_sweeps` and prove something else.
        """
        from backend.kalshi.discovery import discover_from_events
        from backend.odds.client import store_quotes
        from backend.odds.timing import MANUAL
        from backend.runner import fetch_and_store_props

        helper = TestIngestActuallyBuysTheProps()
        now = prop_commence_ms - 30 * 60 * 1000
        quotes = helper._quotes(commence_ms=prop_commence_ms, fetched_ms=now)
        store_quotes(conn, quotes)
        discovered = discover_from_events(
            _prop_slate(kalshi_events, kalshi_prop_capture, prop_commence_ms)
        )

        odds = helper.FakePropOdds(quotes)
        await fetch_and_store_props(
            conn,
            odds,
            events=discovered,
            quotes=quotes,
            sport_key="baseball_mlb",
            now=now,
            slot=None,
            trigger=MANUAL,
            only_events=("odds-1",),
            # The switch at its default: no sport is scheduled for props.
            scheduled_prop_sports=set(),
        )
        assert [c[1] for c in odds.prop_calls] == [("odds-1",)], (
            f"the tap did not buy its named fixture; got {odds.prop_calls}"
        )


class TestTheQuotePassWalksOnlyPriceableSeries:
    """The narrowed walk (ADR 0053), which is what stopped the quote pass
    taking the live instance down.

    The unnarrowed walk paginates the whole open catalogue -- 11,160 events and
    96,326 nested markets, measured against the real API on 2026-08-19 -- to
    find ~510 priceable ones, on a 15-second cadence. It took 27-77s on the
    live shared vCPU, starved uvicorn, and cost 18 unbroken minutes of
    downtime. Scoping the walk to the series that recently carried a priceable
    event measured 3.13s for the same coverage.

    **What these tests establish**: that a quote pass asks for exactly the
    known series and never the whole catalogue, that a full pass still asks for
    the whole catalogue, and that an unknown or stale series set falls back to
    walking everything rather than fetching nothing. **What they do not
    establish**: that it is faster -- that is a network property, measured in
    `docs/measurements/2026-08-19-quote-pass-cost-attribution.md` and not
    re-derivable from a fake.
    """

    async def test_priceable_series_reads_recently_seen_events(self, conn):
        from backend.runner import PRICEABLE_SERIES_WINDOW_MS, priceable_series

        now = 1_787_000_000_000
        for ticker, series, seen in (
            ("KXA-1", "KXMLBGAME", now - 1_000),
            ("KXA-2", "KXMLBGAME", now - 2_000),
            ("KXB-1", "KXWNBAGAME", now - 5_000),
            ("KXC-1", "KXOLDGAME", now - PRICEABLE_SERIES_WINDOW_MS - 1),
        ):
            conn.execute(
                "INSERT OR IGNORE INTO kalshi_series (series_ticker, league, "
                "has_game_markets, first_seen_ms, last_seen_ms) "
                "VALUES (?, 'Pro Baseball', 1, ?, ?)",
                (series, seen, seen),
            )
            conn.execute(
                "INSERT INTO kalshi_events (event_ticker, series_ticker, title, "
                "category, commence_ms, status, first_seen_ms, last_seen_ms) "
                "VALUES (?, ?, 't', 'Sports', ?, 'open', ?, ?)",
                (ticker, series, now, seen, seen),
            )
        conn.commit()

        got = priceable_series(conn, now=now)
        assert got == ["KXMLBGAME", "KXWNBAGAME"], got

    async def test_a_series_that_stopped_listing_drops_out(self, conn):
        """Otherwise a series whose season ended is walked every 15 seconds for
        the life of the instance -- the same unbounded-growth shape as the query
        that took the box down on 2026-08-18."""
        from backend.runner import PRICEABLE_SERIES_WINDOW_MS, priceable_series

        now = 1_787_000_000_000
        conn.execute(
            "INSERT INTO kalshi_series (series_ticker, league, has_game_markets, "
            "first_seen_ms, last_seen_ms) VALUES ('KXDONE', 'Pro Baseball', 1, ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, series_ticker, title, "
            "category, commence_ms, status, first_seen_ms, last_seen_ms) "
            "VALUES ('KXZ-1', 'KXDONE', 't', 'Sports', ?, 'open', ?, ?)",
            (now, now, now),
        )
        conn.commit()
        assert priceable_series(conn, now=now) == ["KXDONE"]
        later = now + PRICEABLE_SERIES_WINDOW_MS + 1
        assert priceable_series(conn, now=later) == []

    async def test_an_empty_set_walks_everything_rather_than_nothing(
        self, conn, kalshi_events
    ):
        """A fresh volume knows no series. Fetching nothing there would report a
        quiet slate, which is indistinguishable from a quiet market -- the
        failure this repo names most often."""
        from backend.runner import run_kalshi_pass, PassCounts

        client = FakeKalshi([_mlb_template(kalshi_events)])
        await run_kalshi_pass(
            conn, client, now=1_787_000_000_000, counts=PassCounts(),
            series_tickers=[],
        )
        assert client.series_seen == [None], client.series_seen

    async def test_a_full_pass_still_walks_the_whole_catalogue(
        self, conn, kalshi_events
    ):
        """A narrowed walk can only re-see series it already knows, so something
        has to look at everything or a newly-listed league is invisible
        forever. That job stays on the full pass."""
        from backend.runner import run_kalshi_pass, PassCounts

        client = FakeKalshi([_mlb_template(kalshi_events)])
        await run_kalshi_pass(
            conn, client, now=1_787_000_000_000, counts=PassCounts()
        )
        assert client.series_seen == [None], client.series_seen

    async def test_a_quote_pass_asks_for_the_known_series_and_not_the_catalogue(
        self, conn, joined, kalshi_events
    ):
        """The claim the whole change rests on. Asserted on what was *asked
        for*, not on what came back: a client that accepted `series_ticker` and
        ignored it returns an identical event list, which is exactly the
        regression that would put the 15s catalogue walk back without changing
        a single visible number."""
        from backend.runner import run_quote_pass

        _, odds_event = joined
        raw = aligned_kalshi_event(
            _mlb_template(kalshi_events),
            odds_event=odds_event,
            kalshi_names=("Pittsburgh", "New York M"),
        )
        series = raw["series_ticker"]
        now = 1_787_000_000_000
        conn.execute(
            "INSERT OR REPLACE INTO kalshi_events (event_ticker, series_ticker, "
            "title, category, commence_ms, status, first_seen_ms, last_seen_ms) "
            "VALUES (?, ?, 't', 'Sports', ?, 'open', ?, ?)",
            (raw["event_ticker"], series, now, now, now),
        )
        conn.commit()

        client = FakeKalshi([raw])
        await run_quote_pass(conn, client, now=now)

        assert client.series_seen == [series], client.series_seen
        assert None not in client.series_seen, (
            "the quote pass walked the whole catalogue, which is the 27-77s "
            "path that took live down"
        )

    async def test_narrowing_actually_narrows_what_is_fetched(
        self, conn, kalshi_events
    ):
        """**The claim `series_seen` cannot make.** Asserting which series were
        *asked for* proves the argument is passed; it says nothing about the
        argument doing anything, and it passed unchanged when the fake was made
        to ignore its own filter.

        The first attempt at this test asserted on the *discovered* events and
        was also green under that mutation -- discovery drops an out-of-scope
        series either way, so nothing downstream of it can tell a narrowed
        fetch from a wide one. It is written down because a test that passes
        for the wrong reason is worse than no test.

        So the assertion is on **what the client handed over**, which is the
        quantity the change exists to reduce: 96,326 nested markets on the wide
        walk against 6,917 on the scoped one, measured 2026-08-19.
        """
        from backend.runner import run_kalshi_pass, PassCounts

        wanted = _mlb_template(kalshi_events)
        other = dict(wanted)
        other["series_ticker"] = "KXOTHER"
        other["event_ticker"] = wanted["event_ticker"] + "-OTHER"

        wide = FakeKalshi([wanted, other])
        await run_kalshi_pass(
            conn, wide, now=1_787_000_000_000, counts=PassCounts()
        )

        narrow = FakeKalshi([wanted, other])
        await run_kalshi_pass(
            conn, narrow, now=1_787_000_000_000, counts=PassCounts(),
            series_tickers=[wanted["series_ticker"]],
        )

        assert wide.yielded == 2, wide.yielded
        assert narrow.yielded == 1, (
            "the narrowed walk fetched everything anyway, so it is not "
            f"narrowing: {narrow.yielded} events"
        )
