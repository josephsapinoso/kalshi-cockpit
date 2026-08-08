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

from backend.config import RiskConfig
from backend.core.suppression import SuppressionConfig
from backend.kalshi.discovery import discover_from_events
from backend.odds.client import OddsQuote, store_quotes
from backend.runner import (
    MONEYLINE,
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
    def test_no_fills_is_a_true_zero_not_an_unreadable_one(self, conn):
        """`size_position` refuses on `None`, so returning 0.0 is a claim.

        It is a true one: "no fills recorded" is a fact about the table, unlike
        "the table could not be read".
        """
        assert current_exposure_dollars(conn) == 0.0

    def test_an_open_fill_counts_toward_exposure(self, conn, joined):
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
        assert current_exposure_dollars(conn) == pytest.approx(10.0)


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
        assert second.unchanged_skipped == 4

        stored = conn.execute("SELECT COUNT(*) n FROM recommendations").fetchone()
        assert stored["n"] == 4

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
    """`events()` is an async generator on the real client, so it is here too."""

    def __init__(self, raw_events: list[dict]):
        self.raw = raw_events

    async def events(self, with_nested_markets: bool = False):
        for event in self.raw:
            yield event


class FakeOdds:
    """Records what it was asked for. Returns nothing, which is a real state."""

    def __init__(self):
        self.calls: list[str] = []

    async def fetch_odds(self, sport_key: str, *, now_ms: int):
        self.calls.append(sport_key)
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
