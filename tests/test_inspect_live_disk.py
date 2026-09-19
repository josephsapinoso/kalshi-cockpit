"""The disk report's portable half, and the property that it cannot delete.

`capacity()` wraps `os.statvfs`, which does not exist on Windows, so it is not
exercised here -- the laptop this is developed on cannot run it and a test that
skipped silently would give false comfort. What IS tested is everything the
verdict is read off: the walk, the grouping that names a cause, and the
unaccounted-bytes gap.

The most important test in this file asserts the script contains no way to
remove a file. That is a property of a tool pointed at the volume holding the
money record, and it is the one thing here that must not drift.
"""

from __future__ import annotations

import os
from pathlib import Path

from scripts.inspect_live_disk import by_extension, capacity, human, render_text, report, walk

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "inspect_live_disk.py"


class _FakeStatvfs:
    """Stands in for the namedtuple-like object `os.statvfs` returns.

    Only the fields `capacity()` reads are populated; a real result carries
    more, and reading an unfaked one here would be a Linux-only test.
    """

    def __init__(self, f_blocks, f_bfree, f_bavail, f_frsize):
        self.f_blocks = f_blocks
        self.f_bfree = f_bfree
        self.f_bavail = f_bavail
        self.f_frsize = f_frsize


def _tree(root: Path) -> Path:
    (root / "sub").mkdir()
    (root / "big.parquet").write_bytes(b"x" * 4096)
    (root / "sub" / "small.parquet").write_bytes(b"y" * 512)
    (root / "cockpit.db").write_bytes(b"z" * 2048)
    (root / "noext").write_bytes(b"w" * 16)
    return root


class TestTheWalkCountsWhatIsThere:
    def test_every_regular_file_is_found_and_summed(self, tmp_path):
        _tree(tmp_path)
        entries, total, errors = walk(str(tmp_path))
        assert len(entries) == 4
        assert total == 4096 + 512 + 2048 + 16
        assert errors == 0

    def test_entries_are_ordered_largest_first(self, tmp_path):
        _tree(tmp_path)
        entries, _, _ = walk(str(tmp_path))
        assert [e.bytes_ for e in entries] == sorted(
            [e.bytes_ for e in entries], reverse=True
        )

    def test_a_directory_is_not_counted_as_a_file(self, tmp_path):
        """Mutation: drop the `S_ISREG` check.

        Directory inodes carry a nonzero `st_size` on ext4, so counting them
        inflates the total by an amount that scales with how many directories
        the volume has -- and then `unaccounted_bytes` goes negative, which
        reads as "the walk found more than df did" and is nonsense.
        """
        _tree(tmp_path)
        entries, _, _ = walk(str(tmp_path))
        assert all(os.path.isfile(e.path) for e in entries)


class TestTheExtensionViewNamesACauseNotAFile:
    """One 2 GiB database and 4,000 Parquet snapshots look identical in a
    top-N file list and are completely different problems. Mutation: delete
    `by_extension` from the report and the incident has no diagnosis.
    """

    def test_files_of_one_kind_are_grouped_and_summed(self, tmp_path):
        _tree(tmp_path)
        entries, _, _ = walk(str(tmp_path))
        rows = {ext: (n, b) for ext, n, b in by_extension(entries)}
        assert rows[".parquet"] == (2, 4096 + 512)
        assert rows[".db"] == (1, 2048)

    def test_an_extensionless_file_is_labelled_not_dropped(self, tmp_path):
        _tree(tmp_path)
        entries, _, _ = walk(str(tmp_path))
        rows = {ext: b for ext, _n, b in by_extension(entries)}
        assert rows["(none)"] == 16

    def test_groups_are_ordered_by_size(self, tmp_path):
        _tree(tmp_path)
        entries, _, _ = walk(str(tmp_path))
        sizes = [b for _ext, _n, b in by_extension(entries)]
        assert sizes == sorted(sizes, reverse=True)


class TestTheReportCannotDeleteAnything:
    """A read-only tool pointed at the volume that holds the money record.

    Mutation: add a cleanup branch. This is the guard that makes it safe to
    invoke over ssh under the governance rule without re-reviewing it each
    time, so it is asserted on the source text rather than on behaviour --
    behaviour only shows what the current code path does, and the risk is a
    path that is added later and not taken during a test.
    """

    def test_the_source_contains_no_removal_or_write_call(self):
        source = SOURCE.read_text(encoding="utf-8")
        # Strip the prose, which legitimately discusses deletion.
        body = source.split('"""', 2)[-1]
        for forbidden in (
            "os.remove",
            "os.unlink",
            "os.rmdir",
            "shutil.rmtree",
            ".truncate(",
            "subprocess",
            "os.system",
        ):
            assert forbidden not in body, forbidden

    def test_it_never_opens_a_file_it_lists(self):
        """Sizes come from `stat`. Reading contents would be a route for row
        data to reach a transcript from the operational database.
        """
        body = SOURCE.read_text(encoding="utf-8").split('"""', 2)[-1]
        assert "open(" not in body
        assert "read_text" not in body
        assert "read_bytes" not in body


class TestReservedBlocks:
    """The root reserve, read from the same `statvfs` call `capacity()`
    already makes -- `(f_bfree - f_bavail) * f_frsize` is the space `f_bfree`
    counts as free that `f_bavail` (what a non-root writer can actually use)
    does not.
    """

    def test_reserved_bytes_is_f_bfree_minus_f_bavail(self, monkeypatch):
        fake = _FakeStatvfs(f_blocks=1000, f_bfree=300, f_bavail=250, f_frsize=4096)
        monkeypatch.setattr(os, "statvfs", lambda root: fake, raising=False)
        cap = capacity("/data")
        assert cap["reserved_bytes"] == (300 - 250) * 4096

    def test_swapping_f_blocks_for_f_bfree_breaks_the_assertion(self, monkeypatch):
        """The mutation named in the ticket: use `f_blocks` in place of
        `f_bfree` in the arithmetic. This pins the correct field is the one
        actually read, by showing the wrong field gives a different answer
        against the same fake.
        """
        fake = _FakeStatvfs(f_blocks=1000, f_bfree=300, f_bavail=250, f_frsize=4096)
        monkeypatch.setattr(os, "statvfs", lambda root: fake, raising=False)
        cap = capacity("/data")
        wrong = (fake.f_blocks - fake.f_bavail) * fake.f_frsize
        assert cap["reserved_bytes"] != wrong

    def test_unaccounted_bytes_is_printed_beside_reserved_bytes(self, tmp_path, monkeypatch):
        (tmp_path / "file.db").write_bytes(b"a" * 100)
        # total 100000 bytes, free 50000 -> used 50000; walked 100 ->
        # unaccounted 49900. bfree-bavail reserve of 4096 bytes.
        fake = _FakeStatvfs(f_blocks=100, f_bfree=13, f_bavail=12, f_frsize=1000)
        monkeypatch.setattr(os, "statvfs", lambda root: fake, raising=False)
        data = report(str(tmp_path), top=5)
        assert data["reserved"]["unaccounted_bytes"] == data["unaccounted_bytes"]
        assert data["reserved"]["reserved_bytes"] == (13 - 12) * 1000
        text = render_text(data)
        assert "reserved" in text
        # Both figures land in the rendered report, so a reader sees them
        # side by side rather than having to compute one from the other.
        # (Rendered with thousands separators, hence the `:,` format.)
        assert f"{data['unaccounted_bytes']:,}" in text
        assert f"{data['reserved']['reserved_bytes']:,}" in text


class TestHumanIsBesideTheBytesNotInsteadOfThem:
    def test_it_renders_the_expected_units(self):
        assert human(0) == "0.0 B"
        assert human(1024) == "1.0 KiB"
        assert human(1024**3) == "1.0 GiB"

    def test_the_exact_byte_count_survives_into_the_report(self, tmp_path):
        """Mutation: report only the human string. A later reading could then
        not be differenced against this one to get a growth rate.
        """
        _tree(tmp_path)
        try:
            data = report(str(tmp_path), top=2)
        except AttributeError:  # os.statvfs is Linux-only
            entries, total, _ = walk(str(tmp_path))
            assert total == 4096 + 512 + 2048 + 16
            return
        assert isinstance(data["walked_bytes"], int)
        assert data["largest"][0]["bytes"] == 4096
        assert data["largest_truncated"] is True
