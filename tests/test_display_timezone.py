"""Every human-facing clock on the site renders in one pinned timezone.

**Why this is a test and not a convention.** The site rendered times three
different ways at once: `formatClock` and `formatKickoff` passed `undefined` as
the locale, which means *the device's* zone; `slate/page.tsx` printed
`getUTCHours()`; `playbook/page.tsx` printed `toISOString()`. So the same
instant read 16:51 on the phone, 23:51 on the page beside it, and 23:51Z on a
third -- and none of them said which.

The failure that causes is not cosmetic. The one thing this product asks a human
to do is *be at the phone at a particular time*, and a schedule whose times
depend on which screen is reading it cannot be quoted, compared against
yesterday, or acted on. It is also the exact shape of the defect this repo has
already paid for once: Kalshi's `occurrence_datetime` runs three hours late, and
what made that expensive was two clocks that looked alike.

What this does **not** establish
--------------------------------
That the *stored* record is UTC. It still is, everywhere, and nothing here
checks that -- `test_sweep_timing.py` and the schema own it. This is about the
last inch before a pixel.

It also cannot check what renders at runtime; it reads the source. A component
that formats a time by some path this pattern does not recognise would pass. It
catches the three spellings that were actually there, and any new use of the
device zone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src"
API_TS = FRONTEND / "lib" / "api.ts"

# The single source of truth the components must import.
PINNED_ZONE = "America/Los_Angeles"


def _sources() -> list[Path]:
    return sorted(p for p in FRONTEND.rglob("*.ts*") if p.is_file())


# Comments in this codebase are prose, and the prose discusses the very strings
# these checks ban -- the `WindowSchedule` header comment explains why "PDT" is
# not repeated per row, and matched its own explanation. Blanked rather than
# deleted so line numbers in a failure message still point at the right line.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")


def _code_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    text = _BLOCK_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    text = _LINE_COMMENT.sub("", text)
    return text.splitlines()


class TestOneZoneForEveryClock:
    def test_the_zone_is_declared_once(self):
        source = API_TS.read_text(encoding="utf-8")
        assert f'DISPLAY_TIME_ZONE = "{PINNED_ZONE}"' in source, (
            f"`DISPLAY_TIME_ZONE` is not pinned to {PINNED_ZONE} in {API_TS}"
        )

    def test_it_is_a_named_zone_not_a_fixed_offset(self):
        """A `-08:00` would be wrong for the eight months of daylight saving,
        and wrong silently -- every time on the page an hour out, with nothing
        on screen to suggest it."""
        assert "/" in PINNED_ZONE, "a named IANA zone handles DST; an offset does not"

    @pytest.mark.parametrize("banned", ["getUTCHours", "getUTCMinutes"])
    def test_no_component_hand_rolls_a_utc_clock(self, banned):
        """`slate/page.tsx` did exactly this, printing a 22:41 first pitch to a
        reader seven hours behind it."""
        offenders = [
            f"{p}:{i}"
            for p in _sources()
            for i, line in enumerate(_code_lines(p), 1)
            if banned in line
        ]
        assert offenders == [], (
            f"{banned} renders a UTC clock to a human: {offenders}. Format "
            f"through `formatClock`/`formatKickoff`, or pass "
            f"`timeZone: DISPLAY_TIME_ZONE`."
        )

    def test_no_time_formatter_falls_back_to_the_device_zone(self):
        """`toLocale*(undefined, ...)` is the device's zone, which is the bug.

        Matched on the literal `undefined` first argument rather than on a
        missing one, because that is the spelling that was there and the one a
        future edit would reach for by copying a neighbour.
        """
        pattern = re.compile(r"toLocale(?:Time|Date)?String\(\s*undefined")
        offenders = [
            f"{p}:{i}"
            for p in _sources()
            for i, line in enumerate(_code_lines(p), 1)
            if pattern.search(line)
        ]
        assert offenders == [], (
            f"these format a time in whichever zone the reading device is in, "
            f"so the same slot prints differently on a phone and a laptop: "
            f"{offenders}"
        )

    def test_every_date_formatter_names_the_zone(self):
        """The falsifier for the two above: banning the wrong spellings proves
        nothing if the right one is never used. Every surviving call that
        formats a `Date` must pass `timeZone`.

        Number formatting -- `value.toLocaleString()` on a count -- is excluded
        by requiring a `Date` on the left, which is what distinguishes them.
        """
        pattern = re.compile(r"new Date\([^)]*\)\.toLocale\w*\(")
        missing: list[str] = []
        for p in _sources():
            text = p.read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                # The options object ends at the closing brace of the call.
                tail = text[match.end() : match.end() + 400]
                if "timeZone" not in tail.split("})")[0]:
                    line = text[: match.start()].count("\n") + 1
                    missing.append(f"{p}:{line}")
        assert missing == [], (
            f"these format a Date without naming a timeZone, so they render in "
            f"the device's zone: {missing}"
        )

    def test_the_zone_label_is_derived_rather_than_written(self):
        """Writing "PST" would be wrong from March to November. The label comes
        out of the same formatter that produces the time, so it says PDT when
        the time is PDT."""
        source = API_TS.read_text(encoding="utf-8")
        assert "timeZoneName" in source, (
            "`displayZoneLabel` must read the zone name from the platform"
        )
        offenders = [
            f"{p}:{i}"
            for p in _sources()
            for i, line in enumerate(_code_lines(p), 1)
            if re.search(r'"\s*P[SD]T\s*"', line)
        ]
        assert offenders == [], (
            f"a hardcoded PST/PDT label is wrong for half the year: {offenders}"
        )
