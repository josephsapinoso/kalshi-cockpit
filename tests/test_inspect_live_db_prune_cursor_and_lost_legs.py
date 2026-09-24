"""`odds-prune-cursor` and `lost-leg-closures` -- durable reads for two armed
features whose only other evidence is a 10-minute stdout log (#144).

`odds-prune-cursor` decodes the `meta` row `odds_snapshot_prune_cursor`
(`backend/store/odds_snapshot_prune.py:97`, `_read_cursor` :177) the same way
that function does. `lost-leg-closures` lists `parlay_positions` rows the
desk closed itself because a held leg lost (v55, ADR 0184, #143).

What these tests establish
---------------------------
- A seeded cursor decodes per sport, with the meta row's own clock beside it.
- An absent cursor prints the "never written" line rather than zero rows.
- A `lost_leg` row is listed and a tap-closed row (`closed_reason` NULL) is
  not.
- `-n` bounds `lost-leg-closures`.
- Both QueryDefs carry `cost=CHEAP`.

What these tests do NOT establish
----------------------------------
- **Nothing about live.** Every row here is seeded in this file, against a
  real schema-initialised SQLite database (`backend/store/schema.sql` run
  verbatim by `db.init_db`), not a hand-written stand-in schema.
- **Nothing about the prune's progress or the closure population's size.**
  Both queries are dumps; no aggregate, no rate.
"""

from __future__ import annotations

import json

from scripts.inspect_live_db import CHEAP, QUERIES
from backend.store import db


def _args(**kw):
    class A:
        limit = 100
        tail = 5

    a = A()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _seeded_db(tmp_path, name="prune.db"):
    path = tmp_path / name
    conn = db.init_db(path)
    conn.commit()
    conn.close()
    return path


def _run(path, name, **kw):
    conn = db.connect(path)
    try:
        return QUERIES[name].run(conn, _args(**kw))
    finally:
        conn.close()


def _section(sections, title_contains):
    for s in sections:
        if title_contains in s.title:
            return s
    raise AssertionError(
        f"no section titled like {title_contains!r} among "
        f"{[s.title for s in sections]}"
    )


def _col(section, name):
    """Rows are tuples -- index by declared column name so a reordered
    SELECT cannot silently move an assertion onto another column."""
    i = section.columns.index(name)
    return [r[i] for r in section.rows]


class TestBothQueriesAreCheap:
    def test_odds_prune_cursor_is_cheap(self):
        """Mutation: flip the entry to `cost=WALKS_THE_FILE` -- red."""
        assert QUERIES["odds-prune-cursor"].cost == CHEAP

    def test_lost_leg_closures_is_cheap(self):
        """Mutation: flip the entry to `cost=WALKS_THE_FILE` -- red."""
        assert QUERIES["lost-leg-closures"].cost == CHEAP


class TestOddsPruneCursorDecodesPerSport:
    def test_a_seeded_cursor_decodes_per_sport(self, tmp_path):
        """Mutation: in `_q_odds_prune_cursor`, use `decoded.values()` without
        `.items()` (drop the sport key) -- red, `sport` column empty/wrong."""
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        cursor = {
            "baseball_mlb": [1_700_000_000_000, "evt-mlb-1"],
            "americanfootball_nfl": [1_700_100_000_000, "evt-nfl-9"],
        }
        conn.execute(
            "INSERT INTO meta (key, value, updated_ms) VALUES (?, ?, ?)",
            ("odds_snapshot_prune_cursor", json.dumps(cursor), 1_700_200_000_000),
        )
        conn.commit()
        conn.close()

        sections = _run(path, "odds-prune-cursor")
        per_sport = _section(sections, "one row per sport")
        assert sorted(_col(per_sport, "sport")) == [
            "americanfootball_nfl",
            "baseball_mlb",
        ]
        by_sport_commence = dict(
            zip(_col(per_sport, "sport"), _col(per_sport, "commence_ms"))
        )
        by_sport_event = dict(
            zip(_col(per_sport, "sport"), _col(per_sport, "event_id"))
        )
        assert by_sport_commence["baseball_mlb"] == 1_700_000_000_000
        assert by_sport_commence["americanfootball_nfl"] == 1_700_100_000_000
        assert by_sport_event["baseball_mlb"] == "evt-mlb-1"
        assert by_sport_event["americanfootball_nfl"] == "evt-nfl-9"

    def test_the_cursor_commence_ms_is_rendered_as_iso_utc(self, tmp_path):
        """Mutation: delete the `_derive_iso(per_sport, "commence_ms", ...)`
        call -- red, no `commence_iso` column."""
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        conn.execute(
            "INSERT INTO meta (key, value, updated_ms) VALUES (?, ?, ?)",
            (
                "odds_snapshot_prune_cursor",
                json.dumps({"baseball_mlb": [1_700_000_000_000, "evt-1"]}),
                1_700_200_000_000,
            ),
        )
        conn.commit()
        conn.close()

        sections = _run(path, "odds-prune-cursor")
        per_sport = _section(sections, "one row per sport")
        assert "commence_iso" in per_sport.columns
        assert _col(per_sport, "commence_iso") == ["2023-11-14T22:13:20Z"]

    def test_the_meta_rows_own_clock_is_reported(self, tmp_path):
        """Mutation: hardcode `updated_ms` to `None` in the meta section --
        red."""
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        conn.execute(
            "INSERT INTO meta (key, value, updated_ms) VALUES (?, ?, ?)",
            (
                "odds_snapshot_prune_cursor",
                json.dumps({"baseball_mlb": [1_700_000_000_000, "evt-1"]}),
                1_700_200_000_000,
            ),
        )
        conn.commit()
        conn.close()

        sections = _run(path, "odds-prune-cursor")
        meta_section = _section(sections, "meta row's own clock")
        assert _col(meta_section, "updated_ms") == [1_700_200_000_000]
        assert _col(meta_section, "sports_decoded") == [1]


class TestAnAbsentCursorSaysSoRatherThanReturningZeroRowsSilently:
    def test_an_absent_cursor_prints_the_never_written_line(self, tmp_path):
        """Mutation: replace the `if row is None:` branch with `return []`
        -- red, no section, no message at all."""
        path = _seeded_db(tmp_path)
        sections = _run(path, "odds-prune-cursor")
        assert len(sections) == 1
        note_section = sections[0]
        assert note_section.columns == ("note",)
        assert note_section.row_count == 1
        assert "never written" in note_section.rows[0][0]

    def test_the_never_written_line_is_not_the_same_shape_as_zero_rows(
        self, tmp_path
    ):
        """An absent cursor must not be indistinguishable from an empty
        per-sport section: the row count is 1 (the note), not 0."""
        path = _seeded_db(tmp_path)
        sections = _run(path, "odds-prune-cursor")
        assert sections[0].row_count == 1


class TestLostLegClosuresListsOnlyDeskInitiatedCloses:
    def _seed_positions(self, conn):
        base = {
            "created_ms": 1_700_000_000_000,
            "source": "kalshi_combo",
            "label": "a hand-recorded slip",
            "stake_tenths": 1000,
            "return_tenths": 2000,
            "status": "closed",
        }
        conn.execute(
            "INSERT INTO parlay_positions (created_ms, source, label, "
            "stake_tenths, return_tenths, status, placed_ms, closed_ms, "
            "closed_source, closed_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                base["created_ms"], base["source"], base["label"],
                base["stake_tenths"], base["return_tenths"], base["status"],
                1_700_000_100_000, 1_700_001_000_000, "venue", "lost_leg",
            ),
        )
        # A tap-closed row: closed_reason stays NULL.
        conn.execute(
            "INSERT INTO parlay_positions (created_ms, source, label, "
            "stake_tenths, return_tenths, status, placed_ms, closed_ms, "
            "closed_source, closed_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                base["created_ms"], base["source"], "a tap-closed slip",
                base["stake_tenths"], base["return_tenths"], base["status"],
                1_700_000_200_000, 1_700_002_000_000, "manual", None,
            ),
        )

    def test_a_lost_leg_row_is_listed(self, tmp_path):
        """Mutation: change the SQL's WHERE to `closed_reason = 'lost_leg' OR
        TRUE` (drop the filter) -- red, tap-closed row leaks in too."""
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        self._seed_positions(conn)
        conn.commit()
        conn.close()

        sections = _run(path, "lost-leg-closures")
        section = sections[0]
        assert section.row_count == 1
        assert _col(section, "closed_reason") == ["lost_leg"]
        assert _col(section, "closed_source") == ["venue"]

    def test_a_tap_closed_row_is_not_listed(self, tmp_path):
        """Mutation: change the SQL's WHERE to `closed_reason IS NOT NULL OR
        closed_source IS NOT NULL` -- red, the tap-closed row (closed_source
        'manual', closed_reason NULL) appears."""
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        self._seed_positions(conn)
        conn.commit()
        conn.close()

        sections = _run(path, "lost-leg-closures")
        section = sections[0]
        assert "a tap-closed slip" not in [
            r for row in section.rows for r in row if isinstance(r, str)
        ]
        assert section.row_count == 1

    def test_closed_and_placed_are_rendered_as_iso(self, tmp_path):
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        self._seed_positions(conn)
        conn.commit()
        conn.close()

        sections = _run(path, "lost-leg-closures")
        section = sections[0]
        assert "closed_iso" in section.columns
        assert "placed_iso" in section.columns
        assert _col(section, "closed_iso") == ["2023-11-14T22:30:00Z"]

    def test_newest_first(self, tmp_path):
        """Mutation: drop `DESC` from `ORDER BY closed_ms` -- red, ordering
        inverts."""
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        conn.execute(
            "INSERT INTO parlay_positions (created_ms, source, label, "
            "stake_tenths, return_tenths, status, placed_ms, closed_ms, "
            "closed_source, closed_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1_700_000_000_000, "kalshi_combo", "older lost leg",
                1000, 2000, "closed", 1_700_000_050_000, 1_700_000_500_000,
                "venue", "lost_leg",
            ),
        )
        conn.execute(
            "INSERT INTO parlay_positions (created_ms, source, label, "
            "stake_tenths, return_tenths, status, placed_ms, closed_ms, "
            "closed_source, closed_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1_700_000_000_000, "kalshi_combo", "newer lost leg",
                1000, 2000, "closed", 1_700_000_060_000, 1_700_009_000_000,
                "manual", "lost_leg",
            ),
        )
        conn.commit()
        conn.close()

        sections = _run(path, "lost-leg-closures")
        section = sections[0]
        assert _col(section, "id") == sorted(_col(section, "id"), reverse=True)
        # The first row is the one with the LATER closed_ms.
        closed = _col(section, "closed_ms")
        assert closed[0] > closed[1]


class TestNBoundsTheOutput:
    def test_n_bounds_lost_leg_closures(self, tmp_path):
        """Mutation: pass `requested=None` instead of `requested=args.tail`
        to `_fetch` -- red, all rows returned regardless of -n."""
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        for i in range(5):
            conn.execute(
                "INSERT INTO parlay_positions (created_ms, source, label, "
                "stake_tenths, return_tenths, status, placed_ms, closed_ms, "
                "closed_source, closed_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    1_700_000_000_000, "kalshi_combo", f"slip {i}",
                    1000, 2000, "closed",
                    1_700_000_000_000 + i,
                    1_700_000_100_000 + i,
                    "venue", "lost_leg",
                ),
            )
        conn.commit()
        conn.close()

        sections = _run(path, "lost-leg-closures", tail=2)
        section = sections[0]
        assert section.row_count == 2

    def test_a_larger_n_than_rows_returns_everything(self, tmp_path):
        path = _seeded_db(tmp_path)
        conn = db.connect(path)
        conn.execute(
            "INSERT INTO parlay_positions (created_ms, source, label, "
            "stake_tenths, return_tenths, status, placed_ms, closed_ms, "
            "closed_source, closed_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1_700_000_000_000, "kalshi_combo", "the only slip",
                1000, 2000, "closed", 1_700_000_000_000, 1_700_000_100_000,
                "venue", "lost_leg",
            ),
        )
        conn.commit()
        conn.close()

        sections = _run(path, "lost-leg-closures", tail=100)
        assert sections[0].row_count == 1
