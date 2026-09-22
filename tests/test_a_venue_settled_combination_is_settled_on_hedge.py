"""A combination the venue has already settled counts as settled on
`/hedge`, even while the desk's own legs still read `pending` (#132).

Why this file exists
---------------------
`kalshi_markets.result` lags the venue by up to one runner pass
(`backend/hedge.py:1001-1010`, `resolve_from_venue`), and `combo_settlements`
already carries the observation that a `KXMVE` combination can settle at the
venue before its leg markets do (`backend/hedge.py:1201`). Before #132,
`build_payload`'s `nothing_pending` guard at `:1958` looked only at
`assessment.pending_legs`, so in that lag window the screen kept a dead
ticket in the live group and spent a venue read on a finalized market's
book -- measured live 2026-09-22 (03:55Z `pending_legs = 2`, both
combinations finalized by the venue at 04:23Z/04:33Z).

What this establishes
----------------------
(i)   `build_payload` treats a venue-settled combination as
      `nothing_pending` -- same reason string as an all-legs-resolved
      combination, no fourth reason -- and never calls the combo-book
      reader for it, regardless of what `pending_legs` says.
(ii)  Without a settlement row, the reader IS called: the guard is the
      settlement, not something else the fixture happens to also change.
(iii) Source-level: `HedgePositions.tsx`'s live predicate (`isLive`) names
      BOTH `pending_legs` and `venue_settlement`.
(iv)  Source-level: the settled group is computed as the NEGATION of that
      same predicate -- one predicate, two filters, one of them negated --
      so no position can match neither group.

What this does not establish
-----------------------------
- Anything about `state` (`derisk`/`lock`/...) -- unchanged by this ticket,
  see `backend/hedge.py:1212`; whether a settled-but-pending-legs row
  auto-closes is #131, not this one.
- That anything renders correctly in a browser -- (iii)/(iv) are source
  text assertions only, same instrument as
  `tests/test_hedge_screen_puts_live_positions_first.py`, which this file
  extends rather than duplicates for the rest of the partition's behaviour.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend import hedge
from backend.store import db

ROOT = Path(__file__).resolve().parent.parent
CARD = ROOT / "frontend" / "src" / "components" / "HedgePositions.tsx"

NOW_MS = 1_700_000_000_000
MAX_AGE_MS = 30_000

CIN = "KXMLBGAME-26AUG26CINSF-CIN"
LAD = "KXMLBGAME-26AUG26LADSD-LAD"
COMBO = "KXMVECROSSCATEGORY-SETTLEDTEST-EE"


@pytest.fixture()
def conn(tmp_path):
    connection = db.init_db(tmp_path / "cockpit.db")
    yield connection
    connection.close()


def seed_combo_position(conn, *, combo_ticker=COMBO) -> int:
    return hedge.record_position(
        conn,
        now_ms=NOW_MS,
        source="kalshi_combo",
        label="two legs",
        stake_tenths=1_020,
        return_tenths=10_000,
        legs=[
            {"ticker": CIN, "side": "yes", "label": "Cincinnati"},
            {"ticker": LAD, "side": "yes", "label": "Los Angeles"},
        ],
        combo_ticker=combo_ticker,
        placed_ms=NOW_MS,
    )


def settle_at_venue(conn, ticker, *, market_result="no", settled_ms=NOW_MS):
    conn.execute(
        "INSERT INTO venue_settlements (ticker, market_result, settled_ms, "
        "side, contracts) VALUES (?, ?, ?, 'yes', 17.74)",
        (ticker, market_result, settled_ms),
    )
    conn.commit()


async def never_called(ticker):
    raise AssertionError(
        "the combo-book reader must not be called for a venue-settled "
        "combination"
    )


def recording_reader(payload=None):
    asked: list[str] = []

    async def _read(ticker: str):
        asked.append(ticker)
        return payload

    return _read, asked


async def raising_fetch(ticker, *, observed_ms):
    raise RuntimeError("no venue leg quote needed for this assertion")


class TestAVenueSettledCombinationIsNothingPending:
    async def test_a_settlement_row_with_every_leg_still_pending_skips_the_read(
        self, conn
    ):
        """(i): legs all `pending`, but `venue_settlements` carries a row for
        this ticket -> `nothing_pending`, and the reader is never called.
        MUTATION (m1): drop the `settlements.get(...)` clause and this goes
        red -- the reader gets called and the reason flips to whatever the
        (never-provided) reader payload renders as."""
        position_id = seed_combo_position(conn)
        settle_at_venue(conn, COMBO, market_result="no", settled_ms=NOW_MS)

        payload = await hedge.build_payload(
            conn,
            now_ms=NOW_MS,
            max_quote_age_ms=MAX_AGE_MS,
            spendable_tenths=None,
            fetch_quote=raising_fetch,
            read_combo_book=never_called,
        )

        (position,) = [
            p for p in payload["positions"] if p["id"] == position_id
        ]
        assert all(leg["outcome"] == "pending" for leg in position["legs"])
        assert position["pending_legs"] == 2
        assert position["combo_book"] is None
        assert (
            position["combo_book_reason"]
            == hedge.COMBO_BOOK_REASON_NOTHING_PENDING
        )

    async def test_without_a_settlement_row_the_reader_is_called(self, conn):
        """(ii): same legs-pending position, no `venue_settlements` row ->
        the reader IS called. Proves the guard added by #132 is the
        settlement, not `pending_legs` alone or some other fixture
        difference."""
        seed_combo_position(conn)
        reader, asked = recording_reader(
            payload={"yes_dollars": [], "no_dollars": []}
        )

        payload = await hedge.build_payload(
            conn,
            now_ms=NOW_MS,
            max_quote_age_ms=MAX_AGE_MS,
            spendable_tenths=None,
            fetch_quote=raising_fetch,
            read_combo_book=reader,
        )

        assert asked == [COMBO]
        (position,) = payload["positions"]
        assert position["combo_book_reason"] is None
        assert position["combo_book"]["state"] == hedge.COMBO_BOOK_EMPTY


def position_groups_body() -> str:
    """`PositionGroups`'s own source, whitespace-collapsed -- narrower than
    the whole file so a mutation elsewhere in the component cannot
    accidentally satisfy these assertions. Matches the helper
    `tests/test_hedge_screen_puts_live_positions_first.py` already uses."""
    source = CARD.read_text(encoding="utf-8")
    start = source.index("function PositionGroups(")
    return re.sub(r"\s+", " ", source[start:])


class TestTheLivePredicateNamesBothFields:
    def test_isLive_checks_pending_legs_and_venue_settlement(self):
        """(iii). MUTATION (m2): drop `venue_settlement === null` from the
        predicate and this goes red."""
        body = position_groups_body()
        match = re.search(
            r"const isLive = \([^)]*\) =>"
            r"\s*position\.pending_legs > 0"
            r"\s*&&\s*position\.venue_settlement === null",
            body,
        )
        assert match, (
            "isLive does not check both pending_legs and venue_settlement: "
            + body[:400]
        )


class TestTheSettledGroupIsTheNegation:
    def test_settled_is_the_complement_of_isLive_not_a_second_condition(self):
        """(iv). One predicate (`isLive`), two filters, one of them negated
        (`!isLive(...)`) -- never a second hand-written condition like a
        literal `pending_legs === 0`, which would leave a venue-settled,
        legs-pending position matching neither group.
        MUTATION (m3): replace the complement filter with a literal
        `pending_legs === 0` and this goes red."""
        body = position_groups_body()
        assert "positions.filter(isLive)" in body
        match = re.search(
            r"settled = positions\.filter\(\s*\([^)]*\)\s*=>\s*!isLive\(",
            body,
        )
        assert match, (
            "the settled group is not computed as !isLive(...): "
            + body[:400]
        )
        assert "pending_legs === 0" not in body
