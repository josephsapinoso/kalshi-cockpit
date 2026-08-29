"""The Games list and the game-detail screen must name one kickoff time.

Until 2026-08-29 `/api/slate` selected `kalshi_events.commence_ms`, which
stores Kalshi's `occurrence_datetime` raw -- about three hours late on game
series (ADR 0006). `/api/market/{ticker}`, one tap away, took the linked
sportsbook fixture's start instead. So a 19:05 first pitch printed as 22:05 on
the list and 19:05 on the detail screen, and the product disagreed with itself
by three hours on the one field that answers "do I still have time to act".
Ticket #26.

The fix is the join, not the constant. `OBSERVED_KALSHI_COMMENCE_OFFSET_MS`
records the shift as *measured* -- 14 of 18 MLB pairs and 6 of 6 WNBA pairs at
exactly +180 minutes -- and the four MLB pairs that did not carry it are the
reason it may not be applied: a hardcoded shift would have moved those four to
a wrong minute with the same confidence it moved the other fourteen to a right
one. `MIN(odds_snapshots.commence_ms)` per linked fixture is what the detail
screen, `/api/ledger` and `backend/scoring.py:markets_awaiting_scoring` already
read, so this makes the list agree with all three rather than inventing a
fourth definition.

**What these tests do not establish.** Nothing about rows already stored on the
live instance: `link_id` is nullable and rows written before the linker ran
still resolve to `None`, which is the intended refusal, not a regression.
Nothing about whether the linker matched the right fixture -- `commence_skew_ms`
on the link is the evidence for that. Nothing about `/api/board`, which still
selects the raw Kalshi field and feeds `OpportunityCard`/`TicketSheet`. And
nothing about rendering: these are wire values in UTC milliseconds, not clocks.
"""

from __future__ import annotations

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.match.linker import OBSERVED_KALSHI_COMMENCE_OFFSET_MS
from backend.store import db

# Two games on one slate. The first carries the ADR 0006 offset on its Kalshi
# event; the second does not, standing in for the 4 of 18 MLB pairs that did
# not. Their *true* order is EARLY then LATE; their raw Kalshi order is the
# reverse, which is what makes the sort assertion below a real claim rather
# than a restatement of the display one.
_EARLY_TRUE_MS = 1_755_800_000_000                 # the offset game, 19:05-ish
_LATE_TRUE_MS = _EARLY_TRUE_MS + 2 * 3_600_000     # two hours later, no offset

# The rows are written as of the wall clock the route reads, not a fixed
# constant: `/api/slate`'s picks block drops any game whose consensus is older
# than `max_odds_age_s`, and a row stamped at epoch 2 seconds is stale by half a
# century. The kickoff values above stay fixed -- they are the fact under test,
# and nothing on this route compares them to now.
def _basis_ms() -> int:
    return db.now_ms()


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


def _add_game(
    conn,
    *,
    key: str,
    link_id: int | None,
    odds_event_id: str | None,
    kalshi_commence_ms: int | None,
    odds_commence_ms: int | None,
) -> str:
    """One event, one linked fixture, one recommendation. Returns the ticker."""
    event_ticker = f"KXTEST{key}-EVENT"
    ticker = f"KXTEST{key}-YES"
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, title, first_seen_ms, "
        "last_seen_ms, commence_ms) VALUES (?, ?, 1000, 1000, ?)",
        (event_ticker, f"Game {key}", kalshi_commence_ms),
    )
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, title, "
        "yes_side_team, first_seen_ms, last_seen_ms) VALUES (?, ?, ?, ?, 1000, 1000)",
        (ticker, event_ticker, f"Game {key} moneyline", f"Team {key}"),
    )
    if link_id is not None and odds_event_id is not None:
        conn.execute(
            "INSERT INTO event_links (id, kalshi_event_ticker, odds_event_id, "
            "league, method, commence_skew_ms, linked_ms) "
            "VALUES (?, ?, ?, 'baseball_mlb', 'exact_alias_pair', 0, 1000)",
            (link_id, event_ticker, odds_event_id),
        )
    if odds_event_id is not None and odds_commence_ms is not None:
        # Two snapshots of one fixture, ten minutes apart: `MIN` must decide,
        # because that is what the scorer does.
        for offset in (0, 600_000):
            conn.execute(
                "INSERT INTO odds_snapshots (fetched_ms, sport_key, "
                "odds_event_id, commence_ms, home_team, away_team, bookmaker, "
                "market, outcome_name, price_decimal) "
                "VALUES (1000, 'baseball_mlb', ?, ?, 'Home', 'Away', "
                "'pinnacle', 'h2h', 'Home', 1.9)",
                (odds_event_id, odds_commence_ms + offset),
            )
    conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, "
        "ticker, link_id, side, entry_ask_tenths, fair_probability, "
        "edge_tenths, fee_predicted, ev_net_dollars, kelly_fraction, "
        "suggested_contracts, reference_contracts, kalshi_quote_age_ms, "
        "odds_age_ms, reason_text) "
        "VALUES (?, 1, ?, ?, 'yes', 500, 0.52, 5.0, 0.1, 0.2, 0.01, 0, 0, "
        "1000, 2000, 'test row')",
        (_basis_ms(), ticker, link_id),
    )
    return ticker


@pytest.fixture
def kickoff_db(tmp_path):
    path = tmp_path / "kickoff.db"
    conn = db.init_db(path)
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    # A: the measured case. Kalshi's `occurrence_datetime` is three hours after
    # the sportsbook's start.
    _add_game(
        conn,
        key="A",
        link_id=1,
        odds_event_id="odds-a",
        kalshi_commence_ms=_EARLY_TRUE_MS + OBSERVED_KALSHI_COMMENCE_OFFSET_MS,
        odds_commence_ms=_EARLY_TRUE_MS,
    )
    # B: the 4-of-18 case. Kalshi and the books agree, so a hardcoded +3h
    # correction would push this row three hours into the future.
    _add_game(
        conn,
        key="B",
        link_id=2,
        odds_event_id="odds-b",
        kalshi_commence_ms=_LATE_TRUE_MS,
        odds_commence_ms=_LATE_TRUE_MS,
    )
    # C: no link and no fixture. There is no trustworthy kickoff for this row.
    _add_game(
        conn,
        key="C",
        link_id=None,
        odds_event_id=None,
        kalshi_commence_ms=_EARLY_TRUE_MS + OBSERVED_KALSHI_COMMENCE_OFFSET_MS,
        odds_commence_ms=None,
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def kickoff_app(kickoff_db):
    return create_app(AppConfig(instance_mode="demo", db_path=kickoff_db))


async def _slate_rows(app) -> list[dict]:
    return (await get(app, "/api/slate")).json()["rows"]


class TestTheListKickoffEqualsTheGameDetailKickoff:
    async def test_the_list_kickoff_equals_the_game_detail_kickoff(
        self, kickoff_app
    ):
        """The claim the whole ticket is about, on every row that has both.

        One tap must not change the number. Asserted per ticker rather than
        pooled, because a single row agreeing by accident would hide a second
        row that does not.
        """
        rows = await _slate_rows(kickoff_app)
        assert rows, "the slate returned nothing, so this asserts nothing"
        compared = 0
        for row in rows:
            detail = (
                await get(kickoff_app, f"/api/market/{row['ticker']}")
            ).json()
            assert row["commence_ms"] == detail["commence_ms"], (
                f"{row['ticker']}: the list says {row['commence_ms']} and the "
                f"detail screen says {detail['commence_ms']}"
            )
            compared += 1
        assert compared == 3, "all three seeded rows must have been compared"

    async def test_the_offset_row_prints_the_sportsbooks_start_not_kalshis(
        self, kickoff_app
    ):
        """The trap, planted and refused.

        Game A's Kalshi event is exactly `OBSERVED_KALSHI_COMMENCE_OFFSET_MS`
        after the books' start. A route reading `kalshi_events.commence_ms`
        fails this by exactly three hours -- which is the bug as Joe saw it,
        a 19:05 first pitch printed as 22:05.
        """
        rows = await _slate_rows(kickoff_app)
        game_a = next(r for r in rows if r["ticker"] == "KXTESTA-YES")
        assert game_a["commence_ms"] == _EARLY_TRUE_MS
        assert (
            game_a["commence_ms"]
            != _EARLY_TRUE_MS + OBSERVED_KALSHI_COMMENCE_OFFSET_MS
        )

    async def test_a_row_kalshi_already_times_correctly_is_not_shifted(
        self, kickoff_app
    ):
        """Why the constant is the inferior fix, stated as a test.

        The offset was 14 of 18 MLB pairs. Game B is one of the other four:
        Kalshi and the books already agree. Subtracting a hardcoded three hours
        would move this row three hours EARLIER than its own kickoff -- a
        confident wrong time, which rule 3 of the ticket ranks below a blank.
        The join cannot do that, because it never reads the Kalshi field.
        """
        rows = await _slate_rows(kickoff_app)
        game_b = next(r for r in rows if r["ticker"] == "KXTESTB-YES")
        assert game_b["commence_ms"] == _LATE_TRUE_MS

    async def test_an_unlinked_row_resolves_to_none_never_a_substitute(
        self, kickoff_app
    ):
        """Game C has no linked fixture, so there is no kickoff to print.

        `None` renders as `--:--`. The repo rule is that unreadable resolves to
        `None`, never to a guess -- and here the available guess is the raw
        Kalshi field, which is the very value this change exists to stop
        printing. A confident wrong time is worse than a blank because the
        reader cannot tell it is wrong.
        """
        rows = await _slate_rows(kickoff_app)
        game_c = next(r for r in rows if r["ticker"] == "KXTESTC-YES")
        assert game_c["commence_ms"] is None

    async def test_the_earliest_snapshot_wins_matching_the_scorer(
        self, kickoff_app
    ):
        """Two snapshots of each fixture disagree by ten minutes.

        `MIN` must decide, because `markets_awaiting_scoring` takes
        `MIN(commence_ms)` per fixture and the list must not describe a
        different start than the machinery that scores the row.
        """
        rows = await _slate_rows(kickoff_app)
        game_a = next(r for r in rows if r["ticker"] == "KXTESTA-YES")
        assert game_a["commence_ms"] == _EARLY_TRUE_MS
        assert game_a["commence_ms"] != _EARLY_TRUE_MS + 600_000

    async def test_the_order_follows_the_printed_times_not_the_raw_field(
        self, kickoff_app
    ):
        """A list ordered against its own printed times is a worse bug.

        Game A truly starts two hours before game B, and Kalshi's raw field
        says the opposite (A + 3h lands an hour after B). Sorting on the raw
        field therefore genuinely reorders this slate rather than translating
        it, so display and sort had to be corrected by the same change.
        The unlinked row sorts last: it is the least decidable thing here.
        """
        rows = await _slate_rows(kickoff_app)
        order = [r["ticker"] for r in rows]
        assert order == ["KXTESTA-YES", "KXTESTB-YES", "KXTESTC-YES"]
        kickoffs = [
            r["commence_ms"] for r in rows if r["commence_ms"] is not None
        ]
        assert kickoffs == sorted(kickoffs)

    async def test_the_picks_block_carries_the_same_clock_as_the_rows(
        self, kickoff_app
    ):
        """`GoodChancePicks` renders its own `commence_ms`.

        It is built from the same serialised items, so it can only disagree if
        somebody reintroduces a second source. Pinned so that a future edit to
        the picks block cannot quietly restore the Kalshi field on one screen
        while the table keeps the sportsbook's.
        """
        body = (await get(kickoff_app, "/api/slate")).json()
        by_ticker = {r["ticker"]: r["commence_ms"] for r in body["rows"]}
        ranked = body["picks"]["ranked"]
        assert ranked, "the seed has fresh YES rows, so picks must not be empty"
        for pick in ranked:
            assert pick["commence_ms"] == by_ticker[pick["ticker"]]
