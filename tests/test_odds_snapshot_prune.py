"""The `odds_snapshots` closing-line prune (#58).

What these tests establish
--------------------------
That for a game past the window the prune keeps exactly each book's last
pre-kickoff sweep per market plus the lowest-kickoff row, deletes every
other reading, leaves games inside the window untouched, preserves the
`MIN(commence_ms)` / `sport_key` answers five readers depend on, refuses
unless both flags allow it, resumes from its cursor, and walks the table by
index seeks rather than scans.

What they do NOT establish
--------------------------
- **Nothing about live.** Every row is seeded on a schema-built tmp database.
- **Nothing about speed or bytes.** The delete rate and freed pages on the
  live volume are read from the dry run's and the armed pass's logs.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.store import db, odds_snapshot_prune as prune

DAY = 86_400_000
HOUR = 3_600_000
NOW = 1_800_000_000_000


@dataclass
class Cfg:
    enabled: bool = True
    dry_run: bool = False
    retention_days: int = 14
    budget_s: float = 30.0

    @property
    def deletes(self) -> bool:
        return self.enabled and not self.dry_run


def _conn(tmp_path):
    return db.init_db(tmp_path / "odds.db")


def _row(conn, *, event, commence, fetched, book="pinnacle", market="h2h",
         outcome="Home", point=None, sport="baseball_mlb"):
    return conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "outcome_point, price_decimal) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (fetched, sport, event, commence, "Home", "Away", book, market,
         outcome, point, 1.9),
    ).lastrowid


def _sweep(conn, *, event, commence, fetched, book="pinnacle", market="h2h",
           sport="baseball_mlb"):
    return [
        _row(conn, event=event, commence=commence, fetched=fetched, book=book,
             market=market, outcome=o, sport=sport)
        for o in ("Home", "Away")
    ]


def _ids(conn, event):
    return {r[0] for r in conn.execute(
        "SELECT id FROM odds_snapshots WHERE odds_event_id = ?", (event,))}


class TestAnOldGameKeepsOnlyItsClosingLines:
    def test_the_last_pre_kickoff_sweep_per_book_and_market_survives(self, tmp_path):
        conn = _conn(tmp_path)
        k = NOW - 20 * DAY
        _sweep(conn, event="g", commence=k, fetched=k - 5 * HOUR)
        close_pin = _sweep(conn, event="g", commence=k, fetched=k - HOUR)
        _sweep(conn, event="g", commence=k, fetched=k + HOUR)  # in-play
        _sweep(conn, event="g", commence=k, fetched=k - 3 * HOUR, book="dk")
        close_dk = _sweep(conn, event="g", commence=k, fetched=k - 2 * HOUR, book="dk")
        close_tot = _sweep(conn, event="g", commence=k, fetched=k - 10 * 60_000,
                           market="totals")
        conn.commit()

        result = prune.run(conn, now=NOW, config=Cfg())

        assert _ids(conn, "g") == set(close_pin + close_dk + close_tot)
        assert result.rows_deleted == 6
        assert result.games == 1

    def test_the_lowest_kickoff_row_is_kept_so_min_commence_does_not_move(
        self, tmp_path
    ):
        """A fixture that moved: its earliest row is an in-between reading, and
        five readers take MIN(commence_ms). It must survive the prune."""
        conn = _conn(tmp_path)
        early, late = NOW - 30 * DAY, NOW - 20 * DAY
        first = _row(conn, event="g", commence=early, fetched=early - 9 * DAY)
        _sweep(conn, event="g", commence=late, fetched=late - 5 * HOUR)
        close = _sweep(conn, event="g", commence=late, fetched=late - HOUR)
        conn.commit()
        before = conn.execute(
            "SELECT MIN(commence_ms), (SELECT sport_key FROM odds_snapshots "
            "WHERE odds_event_id='g' ORDER BY commence_ms LIMIT 1) "
            "FROM odds_snapshots WHERE odds_event_id='g'").fetchone()

        prune.run(conn, now=NOW, config=Cfg())

        assert _ids(conn, "g") == {first, *close}
        after = conn.execute(
            "SELECT MIN(commence_ms), (SELECT sport_key FROM odds_snapshots "
            "WHERE odds_event_id='g' ORDER BY commence_ms LIMIT 1) "
            "FROM odds_snapshots WHERE odds_event_id='g'").fetchone()
        assert tuple(after) == tuple(before)


class TestAGameInsideTheWindowIsUntouched:
    def test_a_recent_game_keeps_every_row(self, tmp_path):
        conn = _conn(tmp_path)
        k = NOW - 13 * DAY
        rows = (_sweep(conn, event="g", commence=k, fetched=k - 5 * HOUR)
                + _sweep(conn, event="g", commence=k, fetched=k - HOUR))
        conn.commit()

        prune.run(conn, now=NOW, config=Cfg())

        assert _ids(conn, "g") == set(rows)

    def test_a_game_whose_kickoff_moved_inside_the_window_is_skipped(self, tmp_path):
        conn = _conn(tmp_path)
        rows = (_sweep(conn, event="g", commence=NOW - 20 * DAY,
                       fetched=NOW - 25 * DAY)
                + _sweep(conn, event="g", commence=NOW - 20 * DAY,
                         fetched=NOW - 22 * DAY)
                + _sweep(conn, event="g", commence=NOW + DAY, fetched=NOW - HOUR))
        conn.commit()

        result = prune.run(conn, now=NOW, config=Cfg())

        assert _ids(conn, "g") == set(rows)
        assert result.skipped_moved == 1


class TestTwoRefusals:
    def _seed(self, conn):
        k = NOW - 20 * DAY
        _sweep(conn, event="g", commence=k, fetched=k - 5 * HOUR)
        _sweep(conn, event="g", commence=k, fetched=k - HOUR)
        conn.commit()

    def test_disabled_deletes_nothing(self, tmp_path):
        conn = _conn(tmp_path)
        self._seed(conn)
        prune.run(conn, now=NOW, config=Cfg(enabled=False))
        assert len(_ids(conn, "g")) == 4

    def test_dry_run_counts_and_deletes_nothing(self, tmp_path):
        conn = _conn(tmp_path)
        self._seed(conn)
        result = prune.run(conn, now=NOW, config=Cfg(dry_run=True))
        assert len(_ids(conn, "g")) == 4
        assert result.rows_would_delete == 2
        assert result.rows_deleted == 0
        assert conn.execute(
            "SELECT 1 FROM meta WHERE key = ?", (prune.CURSOR_KEY,)
        ).fetchone() is None

    def test_the_real_config_refuses_by_default(self, monkeypatch):
        from backend.config import OddsSnapshotPruneConfig

        for k in ("ODDS_SNAPSHOT_PRUNE_ENABLED", "ODDS_SNAPSHOT_PRUNE_DRY_RUN"):
            monkeypatch.delenv(k, raising=False)
        cfg = OddsSnapshotPruneConfig.load()
        assert cfg.deletes is False
        monkeypatch.setenv("ODDS_SNAPSHOT_PRUNE_ENABLED", "true")
        assert OddsSnapshotPruneConfig.load().deletes is False
        monkeypatch.setenv("ODDS_SNAPSHOT_PRUNE_DRY_RUN", "false")
        assert OddsSnapshotPruneConfig.load().deletes is True


class TestTheCursor:
    def test_a_budget_stop_resumes_where_it_left_off(self, tmp_path):
        conn = _conn(tmp_path)
        for i in range(3):
            k = NOW - (30 - i) * DAY
            _sweep(conn, event=f"g{i}", commence=k, fetched=k - 5 * HOUR)
            _sweep(conn, event=f"g{i}", commence=k, fetched=k - HOUR)
        conn.commit()

        first = prune.run(conn, now=NOW, config=Cfg(), budget_s=0.0)
        assert first.games == 0  # zero budget: stops before the first game

        done = prune.run(conn, now=NOW, config=Cfg())
        assert done.games == 3
        again = prune.run(conn, now=NOW, config=Cfg())
        assert again.games == 0  # the cursor is past every old game
        for i in range(3):
            assert len(_ids(conn, f"g{i}")) == 2

    def test_every_sport_is_walked(self, tmp_path):
        conn = _conn(tmp_path)
        k = NOW - 20 * DAY
        for sport in ("baseball_mlb", "americanfootball_nfl", "basketball_wnba"):
            _sweep(conn, event=sport, commence=k, fetched=k - 5 * HOUR, sport=sport)
            _sweep(conn, event=sport, commence=k, fetched=k - HOUR, sport=sport)
        conn.commit()

        result = prune.run(conn, now=NOW, config=Cfg())

        assert result.games == 3
        assert sorted(result.sports_done) == [
            "americanfootball_nfl", "baseball_mlb", "basketball_wnba"]


class TestItSeeksRatherThanScans:
    def test_the_next_game_query_uses_the_sport_commence_index(self, tmp_path):
        conn = _conn(tmp_path)
        plan = " ".join(r[-1] for r in conn.execute(
            "EXPLAIN QUERY PLAN " + prune._NEXT_GAME_SQL,
            {"sport": "x", "c": 0, "e": "", "cutoff": 1}))
        assert "idx_odds_sport_commence" in plan
        assert "SCAN odds_snapshots" not in plan
        assert "TEMP B-TREE" not in plan

    def test_the_keep_query_uses_the_event_index(self, tmp_path):
        conn = _conn(tmp_path)
        plan = " ".join(r[-1] for r in conn.execute(
            "EXPLAIN QUERY PLAN " + prune.KEEP_SQL, {"e": "x"}))
        assert "SCAN odds_snapshots" not in plan


def _prop(conn, *, event, commence, fetched, player, side="Over", book="fanduel"):
    return conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "outcome_description, outcome_point, price_decimal) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (fetched, "baseball_mlb", event, commence, "Home", "Away", book,
         "batter_hits", side, player, 0.5, 1.9),
    ).lastrowid


class TestAPlayerKeepsTheirOwnClose:
    def test_a_player_missing_from_the_last_sweep_keeps_their_last_line(
        self, tmp_path
    ):
        """The review's bug: one prop market covers every player, so keyed on
        (book, market) alone a player dropped from the final sweep lost their
        only close."""
        conn = _conn(tmp_path)
        k = NOW - 20 * DAY
        _prop(conn, event="g", commence=k, fetched=k - 9 * HOUR, player="X")
        x_close = _prop(conn, event="g", commence=k, fetched=k - 5 * HOUR, player="X")
        _prop(conn, event="g", commence=k, fetched=k - 5 * HOUR, player="Y")
        y_close = _prop(conn, event="g", commence=k, fetched=k - HOUR, player="Y")
        conn.commit()

        prune.run(conn, now=NOW, config=Cfg())

        assert _ids(conn, "g") == {x_close, y_close}


class TestTheDryRunIsASample:
    def test_it_stops_at_the_sample_cap(self, tmp_path, monkeypatch):
        monkeypatch.setattr(prune, "DRY_RUN_SAMPLE_GAMES", 2)
        conn = _conn(tmp_path)
        for i in range(5):
            k = NOW - (30 - i) * DAY
            _sweep(conn, event=f"g{i}", commence=k, fetched=k - 5 * HOUR)
            _sweep(conn, event=f"g{i}", commence=k, fetched=k - HOUR)
        conn.commit()

        result = prune.run(conn, now=NOW, config=Cfg(dry_run=True))

        assert result.games == 2
        assert (result.rows_would_delete, result.rows_examined) == (4, 8)


class TestAMalformedCursorRestarts:
    def test_a_bad_entry_is_dropped_not_raised(self, tmp_path):
        conn = _conn(tmp_path)
        k = NOW - 20 * DAY
        _sweep(conn, event="g", commence=k, fetched=k - 5 * HOUR)
        _sweep(conn, event="g", commence=k, fetched=k - HOUR)
        conn.execute(
            "INSERT INTO meta (key, value, updated_ms) VALUES (?, ?, 0)",
            (prune.CURSOR_KEY, '{"baseball_mlb": [5]}'),
        )
        conn.commit()

        result = prune.run(conn, now=NOW, config=Cfg())

        assert result.games == 1
        assert len(_ids(conn, "g")) == 2
