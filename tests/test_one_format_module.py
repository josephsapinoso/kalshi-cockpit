"""One format module, and the lookalikes it kept apart (#261, ADR 0191 follow-up).

`frontend/src/lib/format.ts` owns how the desk writes a time, an age, a duration,
dollars from tenths and a percent. It was a dozen private copies in components,
none testable because node cannot run a `.tsx` file.

**The rule was "move the code, do not unify the behaviour".** `EXPECTED` below
is the output of each function captured from the PRE-move code (a throwaway
driver run against the old definitions, 2026-10-01), hard-coded. If a future
edit changes any boundary, this goes red -- including an edit that "tidies" two
lookalikes into one. They differ at 59_999 ms, 89_999 ms, 90_000 ms, in
rounding vs flooring, in the unit's spelling, and in the unit of the INPUT
(ms, seconds, tenths, a 0-1 fraction, whole dollars), so none could merge.

Establishes: the exported formatters print what they printed before they moved;
none of the old private names is defined in a `.tsx`; `api.ts` defines none of
the moved functions and re-exports the ones it used to own.
Does not establish: that a screen picks the right formatter for its sentence.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests._node_driver import node_driver

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "frontend" / "src"
FORMAT_TS = SRC / "lib" / "format.ts"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not on PATH")

#: name -> [(input, expected output)], captured from the pre-move code.
#: ms boundaries: 0, 59_999, 60_000, 89_999, 90_000, 90 min, 23h59m, 48h, and
#: negatives; null wherever the signature allows it.
EXPECTED: dict[str, list[tuple]] = {
    "formatAge": [
        (0, "just now"),
        (59999, "60s ago"),
        (60000, "1m ago"),
        (89999, "1m ago"),
        (90000, "2m ago"),
        (5400000, "1.5h ago"),
        (86340000, "24.0h ago"),
        (172800000, "48.0h ago"),
        (-1, "just now"),
        (-60000, "just now"),
    ],
    "formatDuration": [
        (0, "under a second"),
        (59999, "60s"),
        (60000, "1m"),
        (89999, "1m"),
        (90000, "2m"),
        (5400000, "1.5h"),
        (86340000, "24.0h"),
        (172800000, "48.0h"),
        (-1, "under a second"),
        (-60000, "under a second"),
    ],
    "formatUntil": [
        (0, "now"),
        (59999, "in 1m"),
        (60000, "in 1m"),
        (89999, "in 1m"),
        (90000, "in 2m"),
        (5400000, "in 1h 30m"),
        (86340000, "in 23h 59m"),
        (172800000, "in 48h 0m"),
        (-1, "now"),
        (-60000, "now"),
    ],
    "formatAgeShort": [
        (0, "0s"),
        (59999, "60s"),
        (60000, "60s"),
        (89999, "90s"),
        (90000, "2m"),
        (5400000, "2h"),
        (86340000, "24h"),
        (172800000, "48h"),
        (-1, "0s"),
        (-60000, "-60s"),
    ],
    "ageWords": [
        (0, "1 s"),
        (59999, "60 s"),
        (60000, "1 min"),
        (89999, "1 min"),
        (90000, "2 min"),
        (5400000, "1.5 h"),
        (86340000, "24.0 h"),
        (172800000, "48.0 h"),
        (-1, "1 s"),
        (-60000, "1 s"),
    ],
    "describeQuoteAgeFloor": [
        (0, "just now"),
        (59999, "59s ago"),
        (60000, "1m ago"),
        (89999, "1m ago"),
        (90000, "1m ago"),
        (5400000, "1h ago"),
        (86340000, "23h ago"),
        (172800000, "48h ago"),
        (-1, None),
        (-60000, None),
        (None, None),
        ("undefined", None),
    ],
    "scoutAge": [
        (0, " Filed just now."),
        (59999, " Filed just now."),
        (60000, " Filed 1m ago."),
        (89999, " Filed 1m ago."),
        (90000, " Filed 1m ago."),
        (5400000, " Filed 1h ago."),
        (86340000, " Filed 23h ago."),
        (172800000, " Filed 48h ago."),
        (-1, " Filed just now."),
        (-60000, " Filed just now."),
        (None, ""),
    ],
    "formatCountdown": [
        (0, "0s"),
        (59, "59s"),
        (60, "1m 00s"),
        (61, "1m 01s"),
        (89, "1m 29s"),
        (90, "1m 30s"),
        (3599, "59m 59s"),
        (3600, "60m 00s"),
        (86399, "1439m 59s"),
        (-1, "-1s"),
    ],
    "dollarsFromTenths": [
        (0, "$0.00"),
        (1, "$0.00"),
        (-1, "-$0.00"),
        (999, "$1.00"),
        (1000, "$1.00"),
        (-1000, "-$1.00"),
        (1234, "$1.23"),
        (-1234, "-$1.23"),
        (12345, "$12.35"),
        (100, "$0.10"),
        (500, "$0.50"),
        (5, "$0.01"),
        (10, "$0.01"),
    ],
    "pctFromTenths": [
        (0, "0%"),
        (5, "0.5%"),
        (10, "1%"),
        (505, "50.5%"),
        (995, "99.5%"),
        (1000, "100%"),
        (-1, "-0.1%"),
        (333, "33.3%"),
        (250, "25%"),
    ],
    "pctFromFraction": [
        (0, "0%"),
        (0.004, "0%"),
        (0.005, "1%"),
        (0.5, "50%"),
        (0.995, "100%"),
        (1, "100%"),
        (-0.1, "-10%"),
        (1.5, "150%"),
        (0.123, "12%"),
    ],
    "formatBankroll": [
        (0, "$0"),
        (999.5, "$1,000"),
        (1000, "$1,000"),
        (2500, "$2,500"),
        (1234567.5, "$1,234,568"),
        (-5, "$-5"),
        (0.4, "$0"),
        (0.5, "$1"),
    ],
    "formatClock": [
        (1767225600000, "4:00 PM"),
        (1783000000000, "6:46 AM"),
        (1719000000000, "1:00 PM"),
        (0, ""),
        (None, ""),
    ],
    "formatKickoff": [
        (1767225600000, "Wed 4:00 PM"),
        (1783000000000, "Thu 6:46 AM"),
        (1719000000000, "Fri 1:00 PM"),
        (0, ""),
        (None, ""),
    ],
    "displayZoneLabel": [
        (1767225600000, "PST"),
        (1783000000000, "PDT"),
        (1719000000000, "PDT"),
    ],
    "freshness": [
        ([0,30000], "fresh"),
        ([15000,30000], "fresh"),
        ([15001,30000], "aging"),
        ([30000,30000], "aging"),
        ([30001,30000], "stale"),
        ([-1,30000], "fresh"),
        ([10,0], "stale"),
    ],
}

_DRIVER = """
import * as F from "./format.ts";
const cases = JSON.parse(process.argv[2]);
const out = {};
for (const [name, rows] of Object.entries(cases)) {
  out[name] = rows.map(([input]) => {
    const arg = input === "undefined" ? undefined : input;
    return Array.isArray(arg) ? F[name](...arg) : F[name](arg);
  });
}
console.log(JSON.stringify(out));
"""


def run_formatters(module_dir: Path) -> dict[str, list]:
    cases = {k: [[i, o] for i, o in v] for k, v in EXPECTED.items()}
    with node_driver(module_dir, _DRIVER) as driver:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(cases)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(module_dir),
        )
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip())


class TestBehaviourIsUnchanged:
    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_formatter_matches_its_pre_move_output(self, name):
        got = run_formatters(FORMAT_TS.parent)[name]
        want = [o for _, o in EXPECTED[name]]
        inputs = [i for i, _ in EXPECTED[name]]
        assert got == want, f"{name}: inputs {inputs}\n got {got}\nwant {want}"

    def test_every_exported_function_is_covered(self):
        text = FORMAT_TS.read_text(encoding="utf-8")
        exported = set(re.findall(r"^export function (\w+)\(", text, re.M))
        assert exported == set(EXPECTED)

    def test_the_lookalikes_really_do_differ(self):
        """The reason they stayed separate, asserted: if two of these ever
        agree on every pinned input the pair is a merge candidate and this
        says so. Compared over the shared ms boundaries."""
        ms = {
            n: dict((i, o) for i, o in EXPECTED[n] if isinstance(i, int))
            for n in ("formatAge", "formatDuration", "formatAgeShort", "ageWords",
                      "describeQuoteAgeFloor", "scoutAge")
        }
        names = sorted(ms)
        for a_i, a in enumerate(names):
            for b in names[a_i + 1:]:
                shared = ms[a].keys() & ms[b].keys()
                assert any(ms[a][k] != ms[b][k] for k in shared), (a, b)


def _strip_comments(ts: str) -> str:
    ts = re.sub(r"/\*.*?\*/", "", ts, flags=re.S)
    return re.sub(r"//[^\n]*", "", ts)


#: file -> the private names that used to be defined there.
OLD_PRIVATE = {
    "app/slate/page.tsx": ["formatAge"],
    "components/GoodChancePicks.tsx": ["ageWords"],
    "components/HedgePositions.tsx": ["describeQuoteAge"],
    "components/ParlayCards.tsx": ["scoutAge"],
    "components/WindowBanner.tsx": ["formatCountdown"],
    "components/RecordChart.tsx": ["dollars"],
    "components/SlateRow.tsx": ["formatBankroll"],
    "components/PriceChart.tsx": ["pct"],
    "lib/gauges.ts": ["pct"],
}

MOVED_FROM_API = [
    "freshness", "formatAge", "formatDuration", "displayZoneLabel",
    "formatClock", "formatUntil", "formatKickoff",
]


class TestSource:
    @pytest.mark.parametrize("rel,names", sorted(OLD_PRIVATE.items()))
    def test_no_private_copy_is_still_defined(self, rel, names):
        code = _strip_comments((SRC / rel).read_text(encoding="utf-8"))
        for name in names:
            assert not re.search(rf"\b(?:function|const|let)\s+{name}\b", code), (rel, name)

    def test_api_defines_none_of_the_moved_functions(self):
        code = _strip_comments((SRC / "lib" / "api.ts").read_text(encoding="utf-8"))
        for name in MOVED_FROM_API + ["DISPLAY_TIME_ZONE"]:
            assert not re.search(rf"\b(?:function|const)\s+{name}\b", code), name

    def test_api_reexports_them_from_format(self):
        code = _strip_comments((SRC / "lib" / "api.ts").read_text(encoding="utf-8"))
        m = re.search(r"export\s*\{([^}]*)\}\s*from\s*\"\./format\"", code)
        assert m, "api.ts must re-export from ./format"
        assert set(re.findall(r"\w+", m.group(1))) == set(MOVED_FROM_API) | {"DISPLAY_TIME_ZONE"}

    def test_format_imports_nothing(self):
        code = _strip_comments(FORMAT_TS.read_text(encoding="utf-8"))
        assert not re.search(r"^\s*import\b|\brequire\(", code, re.M)

    def test_the_components_import_from_format(self):
        for rel in OLD_PRIVATE:
            text = (SRC / rel).read_text(encoding="utf-8")
            assert re.search(r"from \"(?:@/lib/|\./)format\"", text), rel


class TestMutation:
    def test_a_moved_boundary_turns_the_behaviour_check_red(self, tmp_path):
        """Shift formatAge's 60_000 boundary and the expected-output check
        must notice -- otherwise EXPECTED is decoration."""
        source = FORMAT_TS.read_text(encoding="utf-8")
        needle = "if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`;"
        assert needle in source
        (tmp_path / "format.ts").write_text(
            source.replace(needle, needle.replace("60_000", "59_000")), encoding="utf-8"
        )
        got = run_formatters(tmp_path)["formatAge"]
        want = [o for _, o in EXPECTED["formatAge"]]
        assert got != want
