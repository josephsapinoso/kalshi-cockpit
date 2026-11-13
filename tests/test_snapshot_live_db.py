"""`scripts/snapshot_live_db.py` copies consistently and refuses to fill the volume.

What this does not establish: behaviour on the live box's filesystem or under
a concurrent writer at the live file's size. The free-space check is tested
with a patched `free_bytes`, not a full disk.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts import snapshot_live_db as snap


def _source(tmp_path: Path) -> Path:
    db = tmp_path / "cockpit.db"
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    con.executemany("INSERT INTO t (v) VALUES (?)", [("x" * 200,)] * 5000)
    con.commit()
    con.close()
    return db


class TestTheCopyIsComplete:
    def test_every_row_arrives(self, tmp_path):
        src = _source(tmp_path)
        out = tmp_path / "rehearsal-copy.db"
        snap.snapshot(src, out, pages=64, sleep_s=0)
        n = sqlite3.connect(out).execute("SELECT count(*) FROM t").fetchone()[0]
        assert n == 5000


class TestItRefusesRatherThanFillTheVolume:
    def test_too_little_free_space_writes_nothing(self, tmp_path, monkeypatch):
        src = _source(tmp_path)
        out = tmp_path / "rehearsal-copy.db"
        monkeypatch.setattr(snap, "free_bytes", lambda _p: src.stat().st_size)
        assert snap.main(["--db", str(src), "--out", str(out)]) == 2
        assert not out.exists()

    def test_enough_free_space_proceeds(self, tmp_path, monkeypatch):
        src = _source(tmp_path)
        out = tmp_path / "rehearsal-copy.db"
        monkeypatch.setattr(snap, "free_bytes", lambda _p: 100 * snap.GIB)
        monkeypatch.setattr(snap, "SLEEP_BETWEEN_STEPS_S", 0)
        assert snap.main(["--db", str(src), "--out", str(out)]) == 0
        assert out.exists()

    def test_it_never_overwrites_the_source(self, tmp_path, monkeypatch):
        src = _source(tmp_path)
        alias = tmp_path / "sub" / ".." / "cockpit.db"
        (tmp_path / "sub").mkdir()
        monkeypatch.setattr(snap, "free_bytes", lambda _p: 100 * snap.GIB)
        with pytest.raises(snap.Refused, match="is the source database"):
            snap.check_paths(src, alias)

    def test_an_existing_output_is_not_overwritten(self, tmp_path, monkeypatch):
        src = _source(tmp_path)
        out = tmp_path / "rehearsal-copy.db"
        out.write_text("keep me")
        monkeypatch.setattr(snap, "free_bytes", lambda _p: 100 * snap.GIB)
        assert snap.main(["--db", str(src), "--out", str(out)]) == 2
        assert out.read_text() == "keep me"


class TestDeleteRemovesOnlyTheRehearsalCopy:
    def test_the_live_database_cannot_be_deleted(self, tmp_path):
        src = _source(tmp_path)
        assert snap.main(["--delete", str(src)]) == 2
        assert src.exists()

    def test_the_rehearsal_copy_is_deleted(self, tmp_path):
        copy = tmp_path / "rehearsal-copy.db"
        copy.write_text("x")
        assert snap.main(["--delete", str(copy)]) == 0
        assert not copy.exists()
