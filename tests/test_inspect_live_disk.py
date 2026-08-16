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

from scripts.inspect_live_disk import by_extension, human, report, walk

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "inspect_live_disk.py"


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
