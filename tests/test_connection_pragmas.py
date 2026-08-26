"""Every connection gets a page cache sized against a measured box.

A connection is opened PER REQUEST (`routes.get_conn`) and SQLite's default
page cache is ~2 MB. Measured on live 2026-08-26 with a session cookie, first
hit against warm:

    /api/slate     5.94s -> 0.38s
    /api/parlays   9.96s -> 2.32s

A fifteenfold gap on identical statements is the page cache, not the plan.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That live got faster.** These assert the pragmas are set, which is a
  precondition. The effect has to be re-measured on the box, split by whether
  a full pass was running, the way the original reading was.
- **That these sizes are right.** They are chosen against ~76-130 MB of
  measured headroom on a box that has OOM-killed itself once. Raising them is
  a decision to take against a fresh `MemAvailable` reading.
- **Anything about `mmap_size`,** which is deliberately not set: it competes
  with the page cache rather than adding to it.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from backend.store import db


@pytest.fixture
def path():
    return os.path.join(tempfile.mkdtemp(), "pragmas.db")


def _pragma(conn, name: str):
    return conn.execute(f"PRAGMA {name}").fetchone()[0]


class TestEveryConnectionIsSizedDeliberately:
    def test_a_read_connection_gets_the_larger_cache(self, path):
        """Readers are what a person waits on."""
        db.init_db(path).close()
        conn = db.open_db(path, read_only=True, cross_thread=True)
        try:
            # Negative means KiB rather than pages -- the only form that means
            # the same thing across page sizes.
            assert _pragma(conn, "cache_size") == -db.READ_CACHE_KIB
        finally:
            conn.close()

    def test_a_write_connection_gets_the_smaller_one(self, path):
        conn = db.init_db(path)
        try:
            assert _pragma(conn, "cache_size") == -db.WRITE_CACHE_KIB
        finally:
            conn.close()

    def test_the_reader_is_given_more_than_the_writer(self):
        """The asymmetry is the decision, so it is asserted rather than implied."""
        assert db.READ_CACHE_KIB > db.WRITE_CACHE_KIB

    def test_scratch_space_stays_off_the_volume(self, path):
        """`temp_store = MEMORY` is 2. Sorts and GROUP BY spills are the
        slowest thing in a request on a network volume."""
        db.init_db(path).close()
        for read_only in (True, False):
            conn = db.open_db(path, read_only=read_only, cross_thread=True)
            try:
                assert _pragma(conn, "temp_store") == 2
            finally:
                conn.close()

    def test_the_existing_pragmas_still_hold(self, path):
        """The new lines must not have displaced the old ones."""
        conn = db.init_db(path)
        try:
            assert _pragma(conn, "journal_mode") == "wal"
            assert _pragma(conn, "synchronous") == 1  # NORMAL
            assert _pragma(conn, "foreign_keys") == 1
        finally:
            conn.close()

    def test_the_sizes_stay_within_the_measured_headroom(self):
        """A ceiling, stated, because the failure mode here is an OOM.

        Live measured ~130 MB of page cache steady and ~76 MB during a full
        pass. A per-request read connection at 16 MiB plus a writer at 4 MiB
        sits well inside that; a future edit that multiplies these by ten
        should fail here rather than on the box.
        """
        assert db.READ_CACHE_KIB <= 32 * 1024
        assert db.WRITE_CACHE_KIB <= 16 * 1024

    def test_mmap_is_not_enabled(self, path):
        """Deliberately absent: it competes with the page cache above."""
        db.init_db(path).close()
        conn = db.open_db(path, read_only=True, cross_thread=True)
        try:
            assert _pragma(conn, "mmap_size") == 0
        finally:
            conn.close()
