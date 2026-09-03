"""The #15 list cuts: `league` and `within_hours` on `/api/slate` and
`/api/parlays`, and the sticky bar that drives them.

What these tests establish: the two parameters cut both lists on one
vocabulary (the odds feed's sport key), an unknown value is a 422 rather than
a silently whole list, an unfiltered read carries no new key, the cut is
applied before the slate's `LIMIT` so a filter can reach a row the full list
could not fit, the kickoff window is judged on the same clock the row prints
(`MIN(odds_snapshots.commence_ms)` per fixture) and refuses an unknown one,
neither cut reorders anything, and the frontend's chip keys are a subset of
what the server accepts.

What they do not establish: anything about what the cut lists LOOK like at
390px -- `scripts/check_mobile.py` measures overflow, and a test here only
reads the source. Nor that the live database's `event_links.league` strings
match `IN_SCOPE_LEAGUES`; the slate filter deliberately does not read that
column (see `backend/list_filters.py`).
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from backend.api.routes import _slate_filter_sql, create_app
from backend.config import AppConfig
from backend.kalshi.discovery import IN_SCOPE_LEAGUES
from backend.list_filters import (
    LEAGUE_FILTER_KEYS,
    MAX_WITHIN_HOURS,
    FilterRefused,
    ListFilter,
    parse_list_filter,
)
from backend.parlays import build_ladder_payload
from backend.store import db

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
FILTER_BAR = FRONTEND / "components" / "FilterBar.tsx"
LIST_PAGES = {
    "slate": FRONTEND / "app" / "slate" / "page.tsx",
    "picks": FRONTEND / "app" / "picks" / "page.tsx",
    "parlays": FRONTEND / "app" / "parlays" / "page.tsx",
}

HOUR_MS = 3_600_000

#: Key stems a list cut may never read or serve. `edge_tenths = 1000 *
#: (fair - breakeven)`, and ADR 0071 section 2.5 forbids ranking OR cutting on
#: that gap: `beta = -0.141` means a cut on it keeps the least trustworthy
#: rows.
FORBIDDEN_STEMS = ("edge", "fair", "breakeven", "kelly", "ev_", "suggested")


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


# --- slate seeding ----------------------------------------------------------


def _slate_game(
    conn,
    *,
    key: str,
    sport_key: str | None,
    kickoff_ms: int | None,
    basis_ms: int,
) -> str:
    """One recommendation on the slate, linked (or not) to an odds fixture.

    `sport_key=None` seeds an unlinked row: no `event_links` row and no
    snapshot, so both the league and the kickoff resolve to nothing. Returns
    the ticker.
    """
    event_ticker = f"KXTEST{key}-EVENT"
    ticker = f"KXTEST{key}-YES"
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, title, first_seen_ms, "
        "last_seen_ms, commence_ms) VALUES (?, ?, 1000, 1000, ?)",
        (event_ticker, f"Game {key}", kickoff_ms),
    )
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, title, "
        "yes_side_team, first_seen_ms, last_seen_ms) VALUES (?, ?, ?, ?, 1000, 1000)",
        (ticker, event_ticker, f"Game {key} moneyline", f"Team {key}"),
    )
    link_id = None
    if sport_key is not None:
        odds_event_id = f"odds-{key}"
        cursor = conn.execute(
            "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, "
            "league, method, commence_skew_ms, linked_ms) "
            # Kalshi's competition string, as production writes it -- and
            # deliberately NOT the sport key, so a filter that read this
            # column instead of the fixture's would match nothing here.
            "VALUES (?, ?, 'Pro Something', 'exact_alias_pair', 0, 1000)",
            (event_ticker, odds_event_id),
        )
        link_id = int(cursor.lastrowid)
        if kickoff_ms is not None:
            # Two snapshots ten minutes apart: `MIN` must decide, as it does
            # for the printed kickoff and the scorer.
            for offset in (600_000, 0):
                conn.execute(
                    "INSERT INTO odds_snapshots (fetched_ms, sport_key, "
                    "odds_event_id, commence_ms, home_team, away_team, "
                    "bookmaker, market, outcome_name, price_decimal) "
                    "VALUES (1000, ?, ?, ?, 'Home', 'Away', 'pinnacle', "
                    "'h2h', 'Home', 1.9)",
                    (sport_key, odds_event_id, kickoff_ms + offset),
                )
    conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, "
        "ticker, link_id, side, entry_ask_tenths, fair_probability, "
        "edge_tenths, fee_predicted, ev_net_dollars, kelly_fraction, "
        "suggested_contracts, reference_contracts, kalshi_quote_age_ms, "
        "odds_age_ms, reason_text) "
        "VALUES (?, 1, ?, ?, 'yes', 500, 0.52, 5.0, 0.1, 0.2, 0.01, 0, 0, "
        "1000, 2000, 'test row')",
        (basis_ms, ticker, link_id),
    )
    return ticker


@pytest.fixture
def slate_app(tmp_path):
    """Four rows on one slate, as of the wall clock the route reads.

    MLB-2H  baseball_mlb     kicks off in two hours
    WNBA-5H basketball_wnba  kicks off in five hours
    MLB-AGO baseball_mlb     kicked off an hour ago
    NOLINK  unlinked         no league and no kickoff
    """
    path = tmp_path / "slate_filters.db"
    conn = db.init_db(path)
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    now = db.now_ms()
    _slate_game(conn, key="MLB2H", sport_key="baseball_mlb",
                kickoff_ms=now + 2 * HOUR_MS, basis_ms=now)
    _slate_game(conn, key="WNBA5H", sport_key="basketball_wnba",
                kickoff_ms=now + 5 * HOUR_MS, basis_ms=now)
    _slate_game(conn, key="MLBAGO", sport_key="baseball_mlb",
                kickoff_ms=now - HOUR_MS, basis_ms=now)
    _slate_game(conn, key="NOLINK", sport_key=None, kickoff_ms=None,
                basis_ms=now)
    conn.commit()
    conn.close()
    return create_app(AppConfig(instance_mode="demo", db_path=path))


def _tickers(payload: dict) -> list[str]:
    return [row["ticker"] for row in payload["rows"]]


# --- parsing ----------------------------------------------------------------


class TestTheParametersAreParsedOnce:
    def test_neither_set_is_no_filter_at_all(self):
        assert parse_list_filter(None, None, now_ms=0) is None

    def test_the_allowed_leagues_are_the_priceable_ones(self):
        """The vocabulary is the odds feed's sport keys, exactly the set the
        discovery walk can devig against -- not Kalshi's competition
        strings, which `event_links.league` holds."""
        assert set(LEAGUE_FILTER_KEYS) == set(IN_SCOPE_LEAGUES.values())
        assert "baseball_mlb" in LEAGUE_FILTER_KEYS
        assert "Pro Baseball" not in LEAGUE_FILTER_KEYS

    @pytest.mark.parametrize("league", ["", "mlb", "Pro Baseball", "BASEBALL_MLB"])
    def test_an_unknown_league_is_refused_not_ignored(self, league):
        with pytest.raises(FilterRefused) as err:
            parse_list_filter(league, None, now_ms=0)
        # The refusal names what would have been accepted.
        assert "baseball_mlb" in str(err.value)

    @pytest.mark.parametrize("hours", [0, -1, MAX_WITHIN_HOURS + 1])
    def test_a_window_outside_the_range_is_refused(self, hours):
        with pytest.raises(FilterRefused):
            parse_list_filter(None, hours, now_ms=0)

    def test_the_window_resolves_to_bounds_on_the_servers_clock(self):
        flt = parse_list_filter(None, 3, now_ms=1_000)
        assert flt == ListFilter(
            league=None, within_hours=3,
            kickoff_from_ms=1_000, kickoff_until_ms=1_000 + 3 * HOUR_MS,
        )

    def test_an_unknown_kickoff_never_passes_a_window(self):
        """A row that cannot say when it starts cannot say it starts within
        three hours. Refused, not substituted (the `None`-never-`0` rule)."""
        flt = parse_list_filter(None, 3, now_ms=1_000)
        assert flt.keeps_kickoff(None) is False
        assert flt.keeps_kickoff(1_000 + HOUR_MS) is True
        assert flt.keeps_kickoff(999) is False, "already started is not 'next'"
        assert flt.keeps_kickoff(1_000 + 4 * HOUR_MS) is False

    def test_a_league_only_filter_keeps_every_kickoff(self):
        flt = parse_list_filter("baseball_mlb", None, now_ms=1_000)
        assert flt.keeps_kickoff(None) is True

    def test_the_echo_carries_no_profit_readable_key(self):
        """The cut is league and clock, and its echo may say nothing else."""
        flt = parse_list_filter("baseball_mlb", 3, now_ms=1_000)
        for key in flt.as_dict(hidden=0):
            assert not any(stem in key for stem in FORBIDDEN_STEMS), key


class TestTheSlateSqlCutsAndNeverOrders:
    def test_no_filter_is_no_sql(self):
        assert _slate_filter_sql(None) == ("", [])

    def test_the_predicates_read_the_fixture_not_the_link_label(self):
        sql, params = _slate_filter_sql(
            parse_list_filter("baseball_mlb", 3, now_ms=1_000)
        )
        assert "o.sport_key = ?" in sql
        assert "l.league" not in sql, (
            "`event_links.league` is Kalshi's 'Pro Baseball', not the key"
        )
        assert "MIN(o.commence_ms)" in sql
        assert params == ["baseball_mlb", 1_000, 1_000 + 3 * HOUR_MS]

    def test_the_sql_orders_nothing_and_reads_no_edge(self):
        sql, _ = _slate_filter_sql(parse_list_filter("baseball_mlb", 3, now_ms=0))
        assert "ORDER BY" not in sql.upper()
        assert "LIMIT" not in sql.upper()
        for stem in FORBIDDEN_STEMS:
            assert stem not in sql.lower(), stem


# --- /api/slate -------------------------------------------------------------


class TestTheSlateIsCutNotReordered:
    async def test_unfiltered_carries_no_filter_key_and_every_row(self, slate_app):
        """The pre-#15 payload, byte for byte: no `filter` key, and the
        top-level shape exactly as it was. A new key that rode the
        unfiltered read would be a contract change nobody asked for."""
        payload = (await get(slate_app, "/api/slate")).json()
        assert "filter" not in payload
        assert set(payload) == {
            "rows", "picks", "money", "tonight", "open_positions", "counts",
            "staleness", "slate", "drift_window_ms", "note",
        }
        assert len(payload["rows"]) == 4
        assert payload["slate"]["in_window"] == 4

    async def test_league_keeps_only_that_leagues_rows(self, slate_app):
        payload = (
            await get(slate_app, "/api/slate", params={"league": "baseball_mlb"})
        ).json()
        assert _tickers(payload) == ["KXTESTMLBAGO-YES", "KXTESTMLB2H-YES"], (
            "both MLB rows, still in kickoff order -- the started one first"
        )
        assert payload["filter"] == {
            "league": "baseball_mlb",
            "within_hours": None,
            "kickoff_from_ms": None,
            "kickoff_until_ms": None,
            "hidden": 2,
        }
        # The window counts describe the cut list, so `truncated` compares
        # like with like; the history count is still against the whole window.
        assert payload["slate"]["in_window"] == 2
        assert payload["slate"]["returned"] == 2
        assert payload["slate"]["truncated"] is False
        assert payload["slate"]["older_than_window"] == 0

    async def test_the_league_is_the_fixtures_not_the_links_label(self, slate_app):
        """Every seeded link says 'Pro Something'; the fixtures say
        `basketball_wnba` on exactly one. A filter reading the link column
        would return nothing here and pass a weaker test."""
        payload = (
            await get(slate_app, "/api/slate", params={"league": "basketball_wnba"})
        ).json()
        assert _tickers(payload) == ["KXTESTWNBA5H-YES"]

    async def test_within_hours_keeps_the_next_games_only(self, slate_app):
        """Three hours out keeps the 2h game; drops the 5h game, the one that
        already started, and the one with no kickoff to judge."""
        payload = (
            await get(slate_app, "/api/slate", params={"within_hours": 3})
        ).json()
        assert _tickers(payload) == ["KXTESTMLB2H-YES"]
        assert payload["filter"]["hidden"] == 3
        assert payload["filter"]["within_hours"] == 3
        assert payload["filter"]["kickoff_until_ms"] - payload["filter"][
            "kickoff_from_ms"
        ] == 3 * HOUR_MS

    async def test_a_wider_window_reaches_the_later_game(self, slate_app):
        payload = (
            await get(slate_app, "/api/slate", params={"within_hours": 6})
        ).json()
        assert _tickers(payload) == ["KXTESTMLB2H-YES", "KXTESTWNBA5H-YES"]

    async def test_both_cuts_compose(self, slate_app):
        payload = (
            await get(
                slate_app, "/api/slate",
                params={"league": "baseball_mlb", "within_hours": 6},
            )
        ).json()
        assert _tickers(payload) == ["KXTESTMLB2H-YES"]
        assert payload["filter"]["hidden"] == 3

    async def test_the_cut_reaches_a_row_the_limit_would_drop(self, slate_app):
        """The point of a cut: at `limit=1` the full list shows one row, and
        a league filter still finds the WNBA game the limit left out. A cut
        applied after `LIMIT` would return nothing here."""
        whole = (await get(slate_app, "/api/slate", params={"limit": 1})).json()
        assert len(whole["rows"]) == 1
        assert whole["slate"]["truncated"] is True
        cut = (
            await get(
                slate_app, "/api/slate",
                params={"limit": 1, "league": "basketball_wnba"},
            )
        ).json()
        assert _tickers(cut) == ["KXTESTWNBA5H-YES"]

    async def test_the_picks_block_is_cut_with_the_rows(self, slate_app):
        """One list, one cut: the ranked block is built from the same rows,
        so a league filter cannot rank a game the rows do not show."""
        payload = (
            await get(slate_app, "/api/slate", params={"league": "basketball_wnba"})
        ).json()
        picks = payload.get("picks")
        if picks is None:
            pytest.skip("this backend serves no picks block")
        for entry in picks["ranked"]:
            assert entry["ticker"] == "KXTESTWNBA5H-YES"


class TestTheSlateRefusesWhatItCannotCutOn:
    @pytest.mark.parametrize(
        "params",
        [
            {"league": "mlb"},
            {"league": "Pro Baseball"},
            {"league": ""},
            {"within_hours": 0},
            {"within_hours": MAX_WITHIN_HOURS + 1},
            {"within_hours": "three"},
            {"within_hours": "1.5"},
        ],
    )
    async def test_an_unknown_value_is_a_422_not_the_whole_list(
        self, slate_app, params
    ):
        response = await get(slate_app, "/api/slate", params=params)
        assert response.status_code == 422, response.text

    async def test_the_refusal_names_the_allowed_leagues(self, slate_app):
        response = await get(slate_app, "/api/slate", params={"league": "mlb"})
        assert "baseball_mlb" in response.text


# --- /api/parlays -----------------------------------------------------------


def _ladder_game(
    conn, *, game: str, team: str, other: str, sport_key: str,
    commence_ms: int, computed_ms: int, p: float = 0.62,
) -> None:
    """One linked game with a YES-side h2h fair row, in the league asked
    for. Modelled on `tests/test_parlays_api.py::seed_game`, which is
    MLB-only."""
    event_ticker = f"KXGAME-{game}"
    ticker = f"{event_ticker}-{team[:6].upper().replace(' ', '')}"
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, title, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, 0, 0)",
        (event_ticker, f"{other} at {team}"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, "
        "yes_side_team, market_type, status, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, ?, 'moneyline', 'active', 0, 0)",
        (ticker, event_ticker, team),
    )
    cursor = conn.execute(
        "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES (?, ?, 'Pro Something', 'exact_alias_pair', 0, 0)",
        (event_ticker, game),
    )
    link_id = int(cursor.lastrowid)
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal) VALUES (?, ?, ?, ?, ?, ?, 'pinnacle', 'h2h', ?, 1.6)",
        (computed_ms, sport_key, game, commence_ms, team, other, team),
    )
    for outcome, prob in ((team, p), (other, 1 - p - 0.02)):
        conn.execute(
            "INSERT INTO fair_prices (computed_ms, link_id, market, "
            "outcome_name, p_multiplicative, p_additive, p_power, p_shin, "
            "p_conservative, book_count, books_used, anchored_on_sharp, "
            "oldest_book_age_ms) "
            "VALUES (?, ?, 'h2h', ?, ?, ?, ?, ?, ?, 3, '[]', 1, 5000)",
            (
                computed_ms, link_id, outcome,
                prob + 0.02, prob + 0.01, prob + 0.015, prob + 0.005, prob,
            ),
        )


#: Friday 2026-08-28, 15:00 Pacific -- the clock `tests/test_parlays_api.py`
#: injects for the desk-day cases. The evening slate is ahead and the 4am
#: rollover is thirteen hours out, so nothing below rides on a boundary.
FRIDAY_3PM_PT = 1787954400000


def _ladder_conn(tmp_path, now: int):
    """Three games relative to `now`: MLB in 30 minutes and in 3 hours,
    WNBA in 1 hour. All before the desk-day rollover."""
    conn = db.init_db(tmp_path / "ladder_filters.db")
    _ladder_game(conn, game="mlb-soon", team="Boston", other="New York",
                 sport_key="baseball_mlb", commence_ms=now + HOUR_MS // 2,
                 computed_ms=now - 30_000, p=0.70)
    _ladder_game(conn, game="mlb-later", team="Houston", other="Seattle",
                 sport_key="baseball_mlb", commence_ms=now + 3 * HOUR_MS,
                 computed_ms=now - 30_000, p=0.66)
    _ladder_game(conn, game="wnba", team="Las Vegas", other="Phoenix",
                 sport_key="basketball_wnba", commence_ms=now + HOUR_MS,
                 computed_ms=now - 30_000, p=0.62)
    conn.commit()
    return conn


def _ladder_leagues(payload: dict) -> set[str]:
    return {leg["league"] for card in payload["cards"] for leg in card["legs"]}


def _ladder_games(payload: dict) -> set[str]:
    return {leg["event_title"] for card in payload["cards"] for leg in card["legs"]}


class TestTheLadderPoolIsCutBeforeTheCardsAreBuilt:
    def _payload(self, conn, now, **params):
        return build_ladder_payload(
            conn,
            now_ms=now,
            max_odds_age_ms=900_000,
            list_filter=parse_list_filter(
                params.get("league"), params.get("within_hours"), now_ms=now
            ),
        )

    def test_unfiltered_carries_no_filter_key(self, tmp_path):
        conn = _ladder_conn(tmp_path, FRIDAY_3PM_PT)
        payload = self._payload(conn, FRIDAY_3PM_PT)
        assert "filter" not in payload
        assert set(payload) == {"generated_ms", "cards", "excluded", "notes"}
        assert _ladder_leagues(payload) == {"baseball_mlb", "basketball_wnba"}

    def test_league_removes_the_other_leagues_legs_and_says_so(self, tmp_path):
        conn = _ladder_conn(tmp_path, FRIDAY_3PM_PT)
        payload = self._payload(conn, FRIDAY_3PM_PT, league="baseball_mlb")
        assert _ladder_leagues(payload) == {"baseball_mlb"}
        assert payload["filter"]["league"] == "baseball_mlb"
        # One WNBA YES side was in the pool and the cut removed it; the
        # payload says so rather than reading as a two-game night.
        assert payload["filter"]["hidden"] == 1

    def test_a_one_game_cut_builds_no_card_and_still_says_why(self, tmp_path):
        """A parlay needs two legs, so cutting the pool to one game builds
        nothing -- and the payload must say the cut did it, or an empty
        desk under a WNBA chip reads as a night with no WNBA."""
        conn = _ladder_conn(tmp_path, FRIDAY_3PM_PT)
        payload = self._payload(conn, FRIDAY_3PM_PT, league="basketball_wnba")
        assert _ladder_leagues(payload) <= {"basketball_wnba"}
        assert payload["filter"]["hidden"] == 2
        assert payload["cards"], "the ladder still names its cards"
        assert all(card.get("not_built_reason") for card in payload["cards"])

    def test_within_hours_removes_the_later_kickoff(self, tmp_path):
        conn = _ladder_conn(tmp_path, FRIDAY_3PM_PT)
        payload = self._payload(conn, FRIDAY_3PM_PT, within_hours=1)
        assert _ladder_games(payload) == {"New York at Boston", "Phoenix at Las Vegas"}
        assert payload["filter"]["hidden"] == 1
        assert payload["filter"]["kickoff_until_ms"] == FRIDAY_3PM_PT + HOUR_MS

    def test_the_cut_leaves_the_excluded_reasons_alone(self, tmp_path):
        """A filtered-out leg is not a refused one. The engine's own reason
        counts are unchanged by a cut, and the cut's count lives on the
        `filter` echo, not among them."""
        conn = _ladder_conn(tmp_path, FRIDAY_3PM_PT)
        whole = self._payload(conn, FRIDAY_3PM_PT)
        cut = self._payload(conn, FRIDAY_3PM_PT, league="baseball_mlb")
        assert cut["excluded"] == whole["excluded"]


class TestTheParlaysRouteRefusesTheSameValues:
    @pytest.fixture
    def app(self, tmp_path):
        conn = _ladder_conn(tmp_path, db.now_ms())
        conn.close()
        return create_app(
            AppConfig(instance_mode="demo", db_path=tmp_path / "ladder_filters.db")
        )

    @pytest.mark.parametrize(
        "params",
        [{"league": "wnba"}, {"league": ""}, {"within_hours": 0},
         {"within_hours": MAX_WITHIN_HOURS + 1}, {"within_hours": "x"}],
    )
    async def test_an_unknown_value_is_a_422(self, app, params):
        response = await get(app, "/api/parlays", params=params)
        assert response.status_code == 422, response.text

    async def test_unfiltered_still_answers_without_a_filter_key(self, app):
        payload = (await get(app, "/api/parlays")).json()
        assert "filter" not in payload

    async def test_a_known_league_is_accepted_and_echoed(self, app):
        payload = (
            await get(app, "/api/parlays", params={"league": "basketball_wnba"})
        ).json()
        assert payload["filter"]["league"] == "basketball_wnba"
        assert _ladder_leagues(payload) <= {"basketball_wnba"}


# --- the bar ----------------------------------------------------------------


class TestTheBarOffersOnlyWhatTheServerAccepts:
    def test_the_chip_keys_are_a_subset_of_the_servers_leagues(self):
        """A chip for a league the server refuses would be a 422 one tap
        away. The frontend list is pinned against the backend's, not the
        other way round: the backend's is the set of leagues the desk can
        price at all."""
        source = FILTER_BAR.read_text(encoding="utf-8")
        chips = set(re.findall(r'^\s*"([a-z]+_[a-z]+)",\s*$', source, re.M))
        assert chips, "no league chips found in FilterBar.tsx"
        assert chips <= set(LEAGUE_FILTER_KEYS), chips - set(LEAGUE_FILTER_KEYS)

    def test_the_window_chips_are_inside_the_servers_range(self):
        source = FILTER_BAR.read_text(encoding="utf-8")
        # `const WINDOW_HOURS: readonly number[] = [3, 6, 12, 24];` -- the
        # annotation carries its own brackets, so read past the `=`.
        match = re.search(r"WINDOW_HOURS[^=]*=\s*\[([^\]]*)\]", source)
        assert match, "no WINDOW_HOURS list in FilterBar.tsx"
        hours = [int(h) for h in re.findall(r"\d+", match.group(1))]
        assert hours, "the bar offers no kickoff windows"
        assert all(1 <= h <= MAX_WITHIN_HOURS for h in hours), hours

    def test_the_bar_sends_the_parameters_the_routes_read(self):
        """One query builder on both ends: the chips' hrefs and the fetch
        go through `listFilterQuery`, which names the two parameters the
        routes declare and no third."""
        api = (FRONTEND / "lib" / "api.ts").read_text(encoding="utf-8")
        builder = re.search(
            r"function listFilterQuery\(.*?\n}\n", api, re.S
        )
        assert builder, "no listFilterQuery in api.ts"
        keys = re.findall(r'qs\.set\("([a-z_]+)"', builder.group(0))
        assert keys == ["league", "within_hours"], keys
        bar = FILTER_BAR.read_text(encoding="utf-8")
        assert "listFilterQuery(" in bar
        assert bar.count("prefetch={false}") >= 2, (
            "every chip is a Link to a force-dynamic page; prefetching them "
            "is a dozen /api/slate reads per scroll"
        )

    def test_the_bar_offers_no_cut_on_the_gap(self):
        """ADR 0071 section 2.5, on the control itself: no chip, sort, or
        parameter names the consensus-vs-Kalshi gap or any profit figure."""
        source = FILTER_BAR.read_text(encoding="utf-8").lower()
        for stem in FORBIDDEN_STEMS:
            assert stem not in source, stem
        assert "sort" not in source

    @pytest.mark.parametrize("page", sorted(LIST_PAGES))
    def test_every_list_screen_mounts_the_bar(self, page):
        source = LIST_PAGES[page].read_text(encoding="utf-8")
        assert "<FilterBar" in source, f"/{page} has no filter bar"

    @pytest.mark.parametrize("page", sorted(LIST_PAGES))
    def test_every_list_screen_passes_the_cut_to_the_fetch(self, page):
        """A bar that changed the URL and not the request would render the
        whole list under chips saying it was cut."""
        source = LIST_PAGES[page].read_text(encoding="utf-8")
        assert "searchParams" in source
        assert re.search(r"fetch(Slate|Parlays)\(\s*\w*[Ff]ilter", source), (
            f"/{page} fetches without the parsed filter"
        )

    def test_the_bar_sits_below_the_nav(self):
        """`Nav.tsx` is `sticky top-0 z-50`. The bar sticks under it at a
        lower z-index and an offset it owns, so the nav's own internals can
        change without the bar sliding beneath it."""
        source = FILTER_BAR.read_text(encoding="utf-8")
        # The className that carries `sticky`, not the docstring that quotes
        # the nav's own `z-50`.
        sticky = re.search(r'className="([^"]*\bsticky\b[^"]*)"', source)
        assert sticky, "no sticky element in FilterBar.tsx"
        z = re.search(r"\bz-(\d+)\b", sticky.group(1))
        assert z and int(z.group(1)) < 50, "the bar must not outrank the nav"
        assert "--nav-height" in source
