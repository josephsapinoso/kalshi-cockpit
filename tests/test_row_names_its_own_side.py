"""A slate row must name the side it prices, on every route that serves one.

Ticket #6. `_serialise` emitted `team` as `kalshi_markets.yes_side_team` on
both rows of a market and never consulted `side` when doing so, so the Games
row printed the YES-side team under every NO row -- the opponent of the team
that bet pays on. Worse than "half the rows are wrong": in the thirty-minute
window `/slate` and `/board` draw from, 178 of 180 tickers (98.9%) carried both
sides at once, so the screen printed the same name on two adjacent rows with
different asks and nothing to tell them apart.

The fix is a field, not a derivation. `fair_prices.outcome_name` on the row's
own `fair_price_id` is already the team (or Over/Under) that side pays on --
`backend/runner.py` binds it per side, YES to the market's outcome and NO to
the other one, and `tests/test_runner.py` pins that the two sides resolve to
different names. `_serialise` now emits it as `side_outcome`, read off the
join; `/api/board` gains the `fair_prices` join that `/api/slate` and
`/api/market/{ticker}` already had. Renaming sides inside a route by string
manipulation is refused for the reason the picks block gives: a derivation
that goes wrong produces the *other* team's name, which looks fine on screen.

What these tests establish: that on a NO row `side_outcome` differs from `team`
and equals the `fair_prices` outcome for that side, on all three routes; that
`team` still means the YES side on both rows (the picks block, the ticket sheet
and `betDirection.ts` all rely on that); that a row with no fair price resolves
to `None` and never to `team`; and that on a total the field says "Under", not
a team. What they do not establish: how the name renders (that is
`tests/test_row_subject.py`, under node), whether `outcome_name` spells a team
the way `yes_side_team` does (the two have not been compared on the live
record), or anything about `/api/ledger`, which does not join `fair_prices`
and so emits `None` -- an absence, and the ledger page already falls back to
the ticker.
"""

from __future__ import annotations

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db

PIT = "KXMLBGAME-PIT"        # a team market: YES = Pittsburgh Pirates
NOFAIR = "KXMLBGAME-NOFAIR"  # a team market whose NO row has no fair price
TOTAL = "KXMLBTOTAL-O8"      # a total: no yes_side_team, outcomes Over/Under

YES_TEAM = "Pittsburgh Pirates"
NO_TEAM = "New York Mets"


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


def _fair(conn, *, fair_id: int, outcome: str, p: float) -> None:
    conn.execute(
        "INSERT INTO fair_prices (id, computed_ms, link_id, market, "
        "outcome_name, p_multiplicative, p_additive, p_power, p_shin, "
        "p_conservative, market_width, book_count, books_used, "
        "anchored_on_sharp) VALUES (?, 1000, 1, 'h2h', ?, ?, ?, ?, NULL, ?, "
        "0.012, 5, '[\"pinnacle\"]', 1)",
        (fair_id, outcome, p, p, p, p),
    )


def _rec(conn, *, ticker: str, side: str, fair_id: int | None, created_ms: int):
    conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, "
        "ticker, link_id, fair_price_id, side, entry_ask_tenths, "
        "fair_probability, edge_tenths, fee_predicted, ev_net_dollars, "
        "kelly_fraction, suggested_contracts, reference_contracts, "
        "kalshi_quote_age_ms, odds_age_ms, reason_text) "
        "VALUES (?, 1, ?, 1, ?, ?, 500, 0.52, 5.0, 0.1, 0.2, 0.01, 0, 0, "
        "1000, 2000, 'test row')",
        (created_ms, ticker, fair_id, side),
    )


@pytest.fixture
def sides_db(tmp_path):
    path = tmp_path / "sides.db"
    conn = db.init_db(path)
    now = db.now_ms()
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, title, first_seen_ms, "
        "last_seen_ms, commence_ms) VALUES ('KXMLBGAME-EVT', 'Mets at Pirates', "
        "1000, 1000, ?)",
        (now + 3_600_000,),
    )
    conn.execute(
        "INSERT INTO event_links (id, kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES (1, 'KXMLBGAME-EVT', 'odds-pit', 'baseball_mlb', "
        "'exact_alias_pair', 0, 1000)"
    )
    for ticker, yes_side_team in (
        (PIT, YES_TEAM),
        (NOFAIR, YES_TEAM),
        (TOTAL, None),
    ):
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, event_ticker, title, "
            "yes_side_team, first_seen_ms, last_seen_ms) "
            "VALUES (?, 'KXMLBGAME-EVT', ?, ?, 1000, 1000)",
            (ticker, f"{ticker} market", yes_side_team),
        )
    # One fair price per outcome, exactly as the runner writes them: the YES
    # row binds to the market's own outcome and the NO row to the other one.
    _fair(conn, fair_id=1, outcome=YES_TEAM, p=0.53)
    _fair(conn, fair_id=2, outcome=NO_TEAM, p=0.47)
    _fair(conn, fair_id=3, outcome="Over", p=0.51)
    _fair(conn, fair_id=4, outcome="Under", p=0.49)
    # The NO row is written last so `/api/market/{ticker}`, which serves the
    # newest row of either side, serves the NO side -- the case the header
    # line on the single-game screen had no words for.
    _rec(conn, ticker=PIT, side="yes", fair_id=1, created_ms=now)
    _rec(conn, ticker=PIT, side="no", fair_id=2, created_ms=now + 1)
    _rec(conn, ticker=NOFAIR, side="no", fair_id=None, created_ms=now)
    _rec(conn, ticker=TOTAL, side="yes", fair_id=3, created_ms=now)
    _rec(conn, ticker=TOTAL, side="no", fair_id=4, created_ms=now + 1)
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def sides_app(sides_db):
    return create_app(AppConfig(instance_mode="demo", db_path=sides_db))


def _by_side(rows: list[dict], ticker: str) -> dict[str, dict]:
    out = {r["side"]: r for r in rows if r["ticker"] == ticker}
    assert out, f"no rows for {ticker}; the seed did not reach the route"
    return out


async def _slate(app) -> list[dict]:
    return (await get(app, "/api/slate")).json()["rows"]


async def _board(app) -> list[dict]:
    body = (await get(app, "/api/board?include_suppressed=true")).json()
    return body["surfaced"] + body["expired"] + body["suppressed"] + body["no_edge"]


class TestARowNamesTheSideItPrices:
    async def test_the_no_row_names_the_team_no_buys_not_the_yes_side(
        self, sides_app
    ):
        """The defect, stated as a claim: NO on the Pirates is a bet on the Mets."""
        pit = _by_side(await _slate(sides_app), PIT)
        assert pit["no"]["side_outcome"] == NO_TEAM
        assert pit["no"]["side_outcome"] != pit["no"]["team"]
        assert pit["yes"]["side_outcome"] == YES_TEAM

    async def test_team_still_names_the_yes_side_on_both_rows(self, sides_app):
        """`team` keeps its meaning. The picks block, `betDirection.ts` and the
        ticket sheet all read it as the YES-side team, and a field that changed
        meaning under them would break each one silently."""
        pit = _by_side(await _slate(sides_app), PIT)
        assert pit["yes"]["team"] == YES_TEAM
        assert pit["no"]["team"] == YES_TEAM

    async def test_the_two_sides_of_one_market_carry_different_names(
        self, sides_app
    ):
        """The legibility half of the ticket: two adjacent rows, two names."""
        pit = _by_side(await _slate(sides_app), PIT)
        assert pit["yes"]["side_outcome"] != pit["no"]["side_outcome"]

    async def test_the_name_is_the_fair_prices_outcome_for_that_side(
        self, sides_app, sides_db
    ):
        """Read, not derived. Whatever the route says must be what the record
        says for that row's own `fair_price_id` -- checked per row against
        the join `tests/test_runner.py` uses, so a route that renamed sides by
        string manipulation and happened to agree on one row is still caught
        on the other."""
        conn = db.connect(sides_db)
        try:
            recorded = {
                (r["ticker"], r["side"]): r["outcome_name"]
                for r in conn.execute(
                    "SELECT r.ticker, r.side, f.outcome_name "
                    "FROM recommendations r "
                    "JOIN fair_prices f ON f.id = r.fair_price_id"
                ).fetchall()
            }
        finally:
            conn.close()
        assert len(recorded) == 4, "the seed binds four rows to a fair price"
        rows = await _slate(sides_app)
        compared = 0
        for row in rows:
            key = (row["ticker"], row["side"])
            if key in recorded:
                assert row["side_outcome"] == recorded[key], key
                compared += 1
        assert compared == 4


class TestEveryRouteThatServesARowAgrees:
    async def test_the_board_carries_the_same_name_as_the_slate(self, sides_app):
        """`/api/board` was the one slate surface without the `fair_prices`
        join. Both screens render `SlateRow`, so a name that differed between
        them would be the same row telling two stories one tap apart."""
        slate = {(r["ticker"], r["side"]): r["side_outcome"] for r in await _slate(sides_app)}
        board = {(r["ticker"], r["side"]): r["side_outcome"] for r in await _board(sides_app)}
        assert (PIT, "no") in board, "the seed's NO row did not reach the board"
        assert board[(PIT, "no")] == NO_TEAM
        for key, name in board.items():
            assert name == slate[key], key

    async def test_the_detail_screen_says_which_side_it_serves(self, sides_app):
        """`/api/market/{ticker}` serves the newest row of either side. Its
        header line read "YES = {team} ... pays $1 if the {team} win" whatever
        side that row priced; the payload now carries what the line needs."""
        detail = (await get(sides_app, f"/api/market/{PIT}")).json()
        assert detail["side"] == "no"
        assert detail["team"] == YES_TEAM
        assert detail["side_outcome"] == NO_TEAM


class TestItRefusesRatherThanSubstitutes:
    async def test_a_no_row_with_no_fair_price_resolves_to_none_never_the_yes_side(
        self, sides_app
    ):
        """Unreadable resolves to `None`. The available substitute is `team`,
        which on a NO row is the exact wrong answer this field exists to end."""
        nofair = _by_side(await _slate(sides_app), NOFAIR)
        assert nofair["no"]["side_outcome"] is None
        assert nofair["no"]["team"] == YES_TEAM

    async def test_a_total_names_over_or_under_not_a_team(self, sides_app):
        """The row IS about a side of a total, so "Under" is the honest name --
        and it is why this is a second field rather than an overwrite of
        `team`, which stays `None` on a market with no YES-side team."""
        total = _by_side(await _slate(sides_app), TOTAL)
        assert total["yes"]["side_outcome"] == "Over"
        assert total["no"]["side_outcome"] == "Under"
        assert total["yes"]["team"] is None
        assert total["no"]["team"] is None
