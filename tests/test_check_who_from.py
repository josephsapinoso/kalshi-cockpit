"""Check a parlay: who is this from, that sharp's record line, the price as
odds (#424, ADR 0193 Amendment 1, ADR 0196 s2.1).

Every name is invented ("sharp_a"); no operator data.

What this establishes
---------------------
- A name given on the check is cleaned, refused in words past 40 characters
  (before any venue call), and stored on the `parlay_lookups` row the check
  writes; a check with no name stores nothing.
- The per-name record line has its three fixed states and matches names
  case-folded; with no name the whole tailed line is served.
- `price_as_odds` is arithmetic on the one price and is None without one.
- A bought ticket whose check carried a name is SUGGESTED that name, and the
  suggestion is never stored.
- The check carries no price-band record and no band word.

What it does NOT establish
--------------------------
That any name's record means anything: it is the same expected-vs-won line,
under the same floor, and the check shows it as a fact with no verdict.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend import parlay_check, pick_sources
from backend.parlays import LookupRefused
from backend.store import db as store
from backend.store.db import now_ms
from tests.test_parlay_check import (
    EMPTY_BOOK,
    MAX_ODDS_AGE_MS,
    PRICED_BOOK,
    FakeApi,
    _mk_ticker,
    _total_and_game_combo,
)

REPO = Path(__file__).resolve().parents[1]
COMPONENT = REPO / "frontend" / "src" / "components" / "CheckAParlay.tsx"
BAND_WORDS = re.compile(r"band|longshot|long shot", re.IGNORECASE)


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "who.db")
    yield c
    c.close()


async def _check(conn, payload, ticker, *, name=None, book=PRICED_BOOK):
    api = FakeApi(market_payload=payload, book_payload=book)
    result = await parlay_check.check_parlay_text(
        conn, text=ticker, now_ms=now_ms(), api=api,
        max_odds_age_ms=MAX_ODDS_AGE_MS, tailed_from=name,
    )
    return result, api


def _lookup_names(conn):
    return [
        r[0] for r in conn.execute(
            "SELECT tailed_from FROM parlay_lookups ORDER BY id"
        )
    ]


class TestTheNameOnTheCheck:
    async def test_the_name_is_trimmed_and_stored_on_the_lookup_row(self, conn):
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        result, _ = await _check(
            conn, payload, _mk_ticker("AB10"), name="  sharp_a ")
        assert result["tailed_from"] == "sharp_a"
        assert _lookup_names(conn) == ["sharp_a"]

    async def test_no_name_stores_nothing(self, conn):
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        await _check(conn, payload, _mk_ticker("AB11"))
        await _check(conn, payload, _mk_ticker("AB11"), name="   ")
        assert _lookup_names(conn) == [None, None]

    async def test_a_name_over_forty_characters_is_refused_before_any_read(
        self, conn
    ):
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        api = FakeApi(market_payload=payload, book_payload=PRICED_BOOK)
        with pytest.raises(LookupRefused) as err:
            await parlay_check.check_parlay_text(
                conn, text=_mk_ticker("AB12"), now_ms=now_ms(), api=api,
                max_odds_age_ms=MAX_ODDS_AGE_MS, tailed_from="x" * 41,
            )
        assert err.value.status_code == 422
        assert "at most 40 characters" in str(err.value.detail)
        assert api.calls == []
        assert _lookup_names(conn) == []

    async def test_the_known_names_are_served_for_tap_targets(self, conn):
        pick_sources.set_pick_source(
            conn, ticker="T1", source="friend", now_ms=1, tailed_from="sharp_a")
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        result, _ = await _check(conn, payload, _mk_ticker("AB13"))
        assert result["tailed_names"] == ["sharp_a"]


def _patch_record(monkeypatch, by_name):
    block = {
        "source": "friend", "wins": 3, "losses": 17,
        "expected": {"too_few": False, "expected": 4.2, "n": 20},
        "by_name": by_name,
    }
    monkeypatch.setattr(
        parlay_check, "bets_record",
        lambda c, limit=1: {"by_source": {"combo": [block]}},
    )


class TestThePerNameLine:
    def test_a_name_with_no_settled_card_says_zero_cards(self, conn, monkeypatch):
        _patch_record(monkeypatch, [])
        assert parlay_check.friend_source_line(conn, "sharp_a") == (
            "sharp_a's picks so far: too few to tell yet (0 cards)"
        )

    def test_below_the_floor_says_too_few_with_the_count(self, conn, monkeypatch):
        _patch_record(monkeypatch, [{
            "name": "sharp_a", "wins": 1, "losses": 6,
            "expected": {"too_few": True, "expected": 1.0, "n": 7},
        }])
        assert parlay_check.friend_source_line(conn, "sharp_a") == (
            "sharp_a's picks so far: too few to tell yet (7 cards)"
        )

    def test_above_the_floor_states_expected_and_won_for_that_name_only(
        self, conn, monkeypatch
    ):
        _patch_record(monkeypatch, [
            {"name": "sharp_b", "wins": 9, "losses": 1,
             "expected": {"too_few": False, "expected": 2.5, "n": 10}},
            {"name": "Sharp_A", "wins": 3, "losses": 17,
             "expected": {"too_few": False, "expected": 4.2, "n": 20}},
        ])
        assert parlay_check.friend_source_line(conn, "sharp_a") == (
            "sharp_a's picks so far: about 4.2 expected to win, 3 did"
        )

    def test_no_name_keeps_the_whole_tailed_line(self, conn, monkeypatch):
        _patch_record(monkeypatch, [])
        assert parlay_check.friend_source_line(conn) == (
            "Tailed picks so far: about 4.2 expected to win, 3 did"
        )

    async def test_the_check_serves_the_named_line(self, conn):
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        result, _ = await _check(
            conn, payload, _mk_ticker("AB14"), name="sharp_a")
        assert result["source_line"] == (
            "sharp_a's picks so far: too few to tell yet (0 cards)"
        )


class TestPriceAsOdds:
    def test_thirty_tenths_is_about_one_in_thirty_three(self):
        assert parlay_check.price_as_odds(30) == (
            "At 3c this pays if about 1 in 33 of these come in"
        )

    def test_below_ten_to_one_shows_one_decimal(self):
        assert parlay_check.price_as_odds(300) == (
            "At 30c this pays if about 1 in 3.3 of these come in"
        )
        assert parlay_check.price_as_odds(125) == (
            "At 12.5c this pays if about 1 in 8.0 of these come in"
        )

    @pytest.mark.parametrize("bad", [None, 0, -5, 1000, 1500, 30.5, True])
    def test_no_price_or_a_price_out_of_range_is_none(self, bad):
        assert parlay_check.price_as_odds(bad) is None

    async def test_the_check_serves_it_for_the_book_ask(self, conn):
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        result, _ = await _check(conn, payload, _mk_ticker("AB15"))
        # PRICED_BOOK: derived YES ask 30.0c = 300 tenths.
        assert result["price_as_odds"] == (
            "At 30c this pays if about 1 in 3.3 of these come in"
        )

    async def test_an_empty_book_serves_none(self, conn):
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        result, _ = await _check(
            conn, payload, _mk_ticker("AB16"), book=EMPTY_BOOK)
        assert result["price_as_odds"] is None


class TestTheSuggestion:
    async def test_a_named_check_suggests_that_sharp_on_the_bought_ticket(
        self, conn
    ):
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        ticker = _mk_ticker("AB17")
        await _check(conn, payload, ticker, name="sharp_a")
        out = pick_sources.pick_source_payload(conn, [ticker])
        assert out["suggested"] == {ticker: "friend"}
        assert out["suggested_tailed_from"] == {ticker: "sharp_a"}
        # A suggestion is never stored: the tag still needs his tap.
        assert out["tagged"] == {}
        assert conn.execute("SELECT COUNT(*) FROM pick_sources").fetchone()[0] == 0

    async def test_the_newest_named_check_wins(self, conn):
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        ticker = _mk_ticker("AB18")
        await _check(conn, payload, ticker, name="sharp_a")
        await _check(conn, payload, ticker, name="sharp_b")
        assert pick_sources.suggested_tailed_from(conn, [ticker]) == {
            ticker: "sharp_b"
        }

    async def test_an_unnamed_check_suggests_nothing(self, conn):
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        ticker = _mk_ticker("AB19")
        await _check(conn, payload, ticker)
        out = pick_sources.pick_source_payload(conn, [ticker])
        assert out["suggested"] == {} and out["suggested_tailed_from"] == {}

    async def test_a_proven_preset_outranks_the_name(self, conn):
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        ticker = _mk_ticker("AB1A")
        await _check(conn, payload, ticker, name="sharp_a")
        conn.execute(
            "INSERT INTO parlay_positions (source, label, stake_tenths, "
            "return_tenths, created_ms, combo_ticker, status) "
            "VALUES ('kalshi_combo', 'safe', 100, 1000, 1, ?, 'open')",
            (ticker,),
        )
        conn.commit()
        out = pick_sources.pick_source_payload(conn, [ticker])
        assert out["suggested"] == {ticker: "preset"}
        assert out["suggested_tailed_from"] == {}


class TestNoBandRecordAtTheBuyMoment:
    async def test_the_check_shows_no_price_band_record(self, conn):
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        result, _ = await _check(
            conn, payload, _mk_ticker("AB1B"), name="sharp_a")

        def keys(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    yield k
                    yield from keys(v)
            elif isinstance(node, list):
                for v in node:
                    yield from keys(v)

        assert not {"price_bands", "by_shape"} & set(keys(result))
        for sentence in (
            result["source_line"], result["price_as_odds"],
            result["friend_source_line"],
        ):
            assert sentence and not BAND_WORDS.search(sentence)
        # The component is scanned whole, comments and JSX text alike.
        assert not BAND_WORDS.search(COMPONENT.read_text(encoding="utf-8"))
