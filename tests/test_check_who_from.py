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

from backend import bets, parlay_check, pick_sources
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
#: The check response's top-level keys, pinned: a new key fails this test
#: until someone adds it here deliberately (ADR 0196 s2.1).
CHECK_KEYS = {
    "status", "minted_market_ticker", "rfq_available",
    "rfq_unavailable_reason", "legs", "alt_buys", "fair", "quoted",
    "hold_display", "friend_source_line", "tailed_from", "source_line",
    "tailed_names", "price_as_odds", "fee_coefficient", "words", "notes",
}
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


SPEAKS = {
    "too_few": False, "expected": 4.2, "n": 18, "won": 2,
    "range_low": 1, "range_high": 8,
}


def _patch_record(monkeypatch, by_name):
    block = {
        "source": "friend", "wins": 3, "losses": 17,
        "expected": dict(SPEAKS),
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
            "Your tails of sharp_a so far: too few to tell yet (0 cards)"
        )

    def test_below_the_floor_says_too_few_with_the_count(self, conn, monkeypatch):
        _patch_record(monkeypatch, [{
            "name": "sharp_a", "wins": 1, "losses": 6,
            "expected": {"too_few": True, "expected": 1.0, "n": 7},
        }])
        assert parlay_check.friend_source_line(conn, "sharp_a") == (
            "Your tails of sharp_a so far: too few to tell yet (7 cards)"
        )

    def test_above_the_floor_states_expected_and_won_for_that_name_only(
        self, conn, monkeypatch
    ):
        _patch_record(monkeypatch, [
            {"name": "sharp_b", "wins": 9, "losses": 1,
             "expected": {"too_few": False, "expected": 2.5, "n": 10}},
            {"name": "Sharp_A", "wins": 3, "losses": 17,
             "expected": dict(SPEAKS)},
        ])
        assert parlay_check.friend_source_line(conn, "sharp_a") == (
            "Your tails of sharp_a so far (18 cards): their prices said "
            "about 4.2 would win, 2 did; anything from 1 to 8 is normal if "
            "those prices were fair"
        )

    def test_no_name_keeps_the_whole_tailed_line(self, conn, monkeypatch):
        _patch_record(monkeypatch, [])
        assert parlay_check.friend_source_line(conn) == (
            "Your tailed picks so far (18 cards): their prices said about "
            "4.2 would win, 2 did; anything from 1 to 8 is normal if those "
            "prices were fair"
        )

    async def test_the_check_serves_the_named_line(self, conn):
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        result, _ = await _check(
            conn, payload, _mk_ticker("AB14"), name="sharp_a")
        assert result["source_line"] == (
            "Your tails of sharp_a so far: too few to tell yet (0 cards)"
        )


class TestPriceAsOdds:
    @pytest.mark.parametrize("tenths, text", [
        (10, "1c a contract on the book now, 1.1c with Kalshi's fee, "
             "a ticket like this has to win about 1 time in 93 to break even."),
        (30, "3c a contract on the book now, 3.2c with Kalshi's fee, "
             "a ticket like this has to win about 1 time in 31 to break even."),
        (50, "5c a contract on the book now, 5.3c with Kalshi's fee, "
             "a ticket like this has to win about 1 time in 19 to break even."),
        (100, "10c a contract on the book now, 10.6c with Kalshi's fee, "
              "a ticket like this has to win about 1 time in 9.4 to break even."),
        (200, "20c a contract on the book now, 21.1c with Kalshi's fee, "
              "a ticket like this has to win about 1 time in 4.7 to break even."),
    ])
    def test_the_break_even_rate_is_after_the_combo_taker_fee(self, tenths, text):
        assert parlay_check.price_as_odds(tenths) == "At " + text

    def test_the_sentence_says_break_even_and_not_pays_or_of_these(self):
        sentence = parlay_check.price_as_odds(30)
        assert "break even" in sentence
        assert "pays" not in sentence and "of these" not in sentence

    def test_an_uncomputable_fee_is_none(self, monkeypatch):
        monkeypatch.setattr(parlay_check, "combo_taker_fee", lambda p, c: None)
        assert parlay_check.price_as_odds(30) is None

    @pytest.mark.parametrize("bad", [None, 0, -5, 1000, 1500, 30.5, True])
    def test_no_price_or_a_price_out_of_range_is_none(self, bad):
        assert parlay_check.price_as_odds(bad) is None

    async def test_the_check_serves_it_for_the_book_ask(self, conn):
        payload, _, _ = _total_and_game_combo(conn, one_book_total=False)
        result, _ = await _check(conn, payload, _mk_ticker("AB15"))
        # PRICED_BOOK: derived YES ask 30.0c = 300 tenths.
        assert result["price_as_odds"] == parlay_check.price_as_odds(300)
        assert "1 time in 3.2 to break even" in result["price_as_odds"]

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

        assert set(result) == CHECK_KEYS

        def strings(node):
            if isinstance(node, str):
                yield node
            elif isinstance(node, dict):
                for k, v in node.items():
                    yield from strings(k)
                    yield from strings(v)
            elif isinstance(node, (list, tuple)):
                for v in node:
                    yield from strings(v)

        def keys(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    yield k
                    yield from keys(v)
            elif isinstance(node, list):
                for v in node:
                    yield from keys(v)

        assert not {"price_bands", "by_shape", "by_price"} & set(keys(result))
        labels = [label for _, _, label in bets.EXPECTED_BUCKETS]
        for text in strings(result):
            assert not BAND_WORDS.search(text), text
            for label in labels:
                assert label not in text, (label, text)
        # The component is scanned whole, comments and JSX text alike.
        assert not BAND_WORDS.search(COMPONENT.read_text(encoding="utf-8"))


class TestTheChipCarriesTheNameGivenAtTheCheck:
    """Main's follow-up to #424: the suggestion reaches the tap, and only the
    tap stores it (ADR 0193 s2)."""

    CHIPS = (
        Path(__file__).resolve().parents[1]
        / "frontend" / "src" / "components" / "PickSourceChips.tsx"
    ).read_text(encoding="utf-8").replace("\r\n", "\n")

    def test_the_suggested_name_is_read_only_for_a_suggested_tailed_tag(self):
        assert (
            'suggested === "friend" ? (block.suggested_tailed_from?.[ticker] ?? null) : null'
            in self.CHIPS
        )

    def test_confirming_the_dashed_tag_sends_the_name_with_the_tap(self):
        assert 'const carried = next === "friend" ? suggestedName : null;' in self.CHIPS
        assert "await setPickSource(ticker, next, carried)" in self.CHIPS
        # Nothing stores a name outside a tap handler: the only two writes
        # are in `tap` and `saveName`.
        assert self.CHIPS.count("await setPickSource(") == 2
