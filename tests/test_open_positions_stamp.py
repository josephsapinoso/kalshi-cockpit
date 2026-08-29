"""The "as of" on the open-positions line names the read that produced the
figure beside it — not the container's boot.

The defect, 2026-08-29. The slate rendered:

    Open now: 1 position · $0.00 at risk · as of 7:47 AM

and 7:47 AM was `count_as_of_ms`, the newest successful `poll_log` row for
endpoint 'positions'. Positions are polled **only** inside the full mirror
(`backend/portfolio_poll.py::poll_portfolio`), which `poll_portfolio_forever`
runs on its first cycle and then every `MIRROR_INTERVAL_S` = 12 hours. No
container on this instance lives twelve hours
(`docs/measurements/2026-08-28-recorder-silence-is-chronic.md` observes uptimes
of 43.6 and 2,618 seconds), so that stamp was the process start time and it did
not move again until the next restart. It sat immediately after the
dollars-at-risk figure, which rides the five-minute balance cadence and carries
its own `value_as_of_ms` — already in the payload, and discarded by the
renderer at `frontend/src/components/OpenPositions.tsx:66`.

Under ADR 0071 the desk's job at the moment of a bet is price transparency. A
boot-time stamp on a money figure gets more false the longer the container
lives, which is the one direction a freshness claim must never drift.

What this establishes: that the value figure's stamp is the balance read and
the count figure's stamp is the positions poll; that a figure with no
observation carries **no** stamp rather than borrowing the other one; that the
age served is the server's own subtraction against the same `now_ms` the
staleness bounds use; and that the renderer no longer touches `count_as_of_ms`
anywhere near the value.

**The cadence half of that defect was fixed separately, later the same day.**
`portfolio_poll.poll_positions` left the twelve-hour mirror for the five-minute
cadence, so the count is no longer a boot-time read and `bets.open_positions`
now bounds it with the same `TONIGHT_STALE_AFTER_MS` the value uses. That does
**not** retire this file: a shared cadence is not a shared read. A positions
poll that fails while the balance poll succeeds leaves the two stamps hours
apart, which is exactly the divergence one borrowed clock would hide, so the
scenarios below now run a fresh-but-distinct positions read and keep the
six-hour one as the case where the count refuses.

What it does **not** establish: that the poller is running (a stale count is
served as a refusal, not as a promise), that the venue's `portfolio_value`
means what it appears to mean (its unit is pinned only at zero), or that the
line is legible.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from backend import bets
from backend.store import db

REPO = Path(__file__).resolve().parents[1]
STAMPS_TS = REPO / "frontend" / "src" / "lib" / "openPositionsStamps.ts"
COMPONENT_TSX = REPO / "frontend" / "src" / "components" / "OpenPositions.tsx"

NODE = shutil.which("node")

NOW_MS = 1_755_000_000_000
BOOT_MS = NOW_MS - 6 * 3600 * 1000          # the container came up 6h ago
BALANCE_MS = NOW_MS - 90_000                # the balance was read 90s ago
# One five-minute tick behind the balance read: both polls are on the same
# cadence and are still two separate reads, which is the whole point.
POSITIONS_MS = NOW_MS - 4 * 60 * 1000

_DRIVER = """
import { countStamp, describeAge, valueStamp } from "./openPositionsStamps.ts";
const block = JSON.parse(process.argv[2]);
const shape = (s) =>
  s === null ? null : { asOfMs: s.asOfMs, ageMs: s.ageMs, age: describeAge(s.ageMs) };
console.log(JSON.stringify({
  count: shape(countStamp(block)),
  value: shape(valueStamp(block)),
}));
"""


def stamps(block: dict) -> dict:
    """Run the shipped stamp module under node over a real payload."""
    driver = STAMPS_TS.parent / "_open_positions_stamp_driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    try:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(block)],
            capture_output=True,
            text=True,
            # Node writes UTF-8; without this, Windows decodes with the ANSI
            # code page and an em dash comes back as U+FFFD.
            encoding="utf-8",
            timeout=60,
            cwd=str(STAMPS_TS.parent),
        )
    finally:
        driver.unlink(missing_ok=True)
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip())


def _served(tmp_path, *, positions_ms=POSITIONS_MS, balance_ms=BALANCE_MS,
            row_count=1, value_tenths=0) -> dict:
    """The real payload `/api/slate` serves, off a real database."""
    conn = db.init_db(tmp_path / "p.db")
    if positions_ms is not None:
        conn.execute(
            "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count) "
            "VALUES (?, 'positions', 1, ?)",
            (positions_ms, row_count),
        )
    if balance_ms is not None:
        conn.execute(
            "INSERT INTO venue_balance_snapshots "
            "(observed_ms, balance_tenths, portfolio_value_tenths) "
            "VALUES (?, 2560, ?)",
            (balance_ms, value_tenths),
        )
    conn.commit()
    return bets.open_positions(conn, now_ms=NOW_MS)


nodeless = pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: the guard is real "
        "where node exists (CI and both dev machines)."
    ),
)


class TestTheStampNamesTheReadNotTheBoot:
    @nodeless
    def test_the_value_stamp_is_the_balance_read_not_the_positions_poll(
        self, tmp_path
    ):
        """The claim in the title, over two reads on the same cadence: a
        4-minute-old positions poll beside a 90-second-old balance read. Same
        clock, different reads — the dollars-at-risk figure must wear 90
        seconds, and it must wear them because that is when IT was read."""
        block = _served(tmp_path)
        assert block["value_display"] == "$0.00"
        assert block["count"] == 1

        out = stamps(block)
        assert out["value"]["asOfMs"] == BALANCE_MS
        assert out["value"]["asOfMs"] != block["count_as_of_ms"]
        assert out["value"]["ageMs"] == 90_000
        assert out["value"]["age"] == "1m ago"

        # And the count keeps its own.
        assert out["count"]["asOfMs"] == POSITIONS_MS
        assert out["count"]["age"] == "4m ago"

    @nodeless
    def test_a_dead_positions_poll_refuses_the_count_and_never_the_value(
        self, tmp_path
    ):
        """The divergence that survives the shared cadence, and the reason
        this file was not deleted with it. The positions poll has not
        succeeded for six hours — the pre-2026-08-29 boot-read shape, and now
        the shape of a poller that is failing — while the balance was read 90
        seconds ago. The count refuses and keeps its own stale clock; the
        money figure is served and wears 90 seconds. One borrowed stamp here
        would put six hours on a fresh figure or 90 seconds on a dead one."""
        block = _served(tmp_path, positions_ms=BOOT_MS)
        assert block["count"] is None, "6h is past the 30-minute bound"
        assert block["count_as_of_ms"] == BOOT_MS
        assert block["value_display"] == "$0.00"

        out = stamps(block)
        assert out["count"]["age"] == "6h ago"
        assert out["value"]["age"] == "1m ago"

    @nodeless
    def test_a_never_observed_value_carries_no_stamp_not_the_counts(
        self, tmp_path
    ):
        """Unreadable resolves to absent. With no balance snapshot ever the
        value refuses in words, and the line must show no clock at all rather
        than reaching for the count's."""
        block = _served(tmp_path, balance_ms=None)
        assert block["value_as_of_ms"] is None
        assert block["value_age_ms"] is None
        assert block["value_refusal"] == "never observed"

        out = stamps(block)
        assert out["value"] is None
        assert out["count"]["asOfMs"] == POSITIONS_MS

    @nodeless
    def test_an_absent_age_leaves_the_clock_and_invents_nothing(self):
        """A backend one version behind omits `*_age_ms`. The stamp keeps the
        clock it does have and the age is null — never 0, which would read as
        'just now' on a figure hours old."""
        out = stamps(
            {
                "count": 1,
                "count_as_of_ms": BOOT_MS,
                "value_tenths": 0,
                "value_display": "$0.00",
                "value_as_of_ms": BALANCE_MS,
                "value_refusal": None,
            }
        )
        assert out["value"] == {"asOfMs": BALANCE_MS, "ageMs": None, "age": None}
        assert out["count"] == {"asOfMs": BOOT_MS, "ageMs": None, "age": None}

    def test_the_server_computes_each_age_on_its_own_read(self, tmp_path):
        """Both ages come off the same `now_ms` the staleness bounds use, so
        nothing subtracts a browser millisecond from a server one."""
        block = _served(tmp_path)
        assert block["count_age_ms"] == 4 * 60 * 1000
        assert block["value_age_ms"] == 90_000

    def test_an_unread_figure_has_no_age_rather_than_a_zero(self, tmp_path):
        block = _served(tmp_path, positions_ms=None, balance_ms=None)
        assert block["count_as_of_ms"] is None
        assert block["count_age_ms"] is None
        assert block["value_as_of_ms"] is None
        assert block["value_age_ms"] is None

    def test_the_renderer_never_reaches_for_the_counts_clock(self):
        """The source guard behind the executed ones: the component asks the
        stamp module for each figure's clock and never reads either `*_as_of_ms`
        field itself, so no future edit can quietly re-pair the value with the
        boot-time stamp."""
        source = COMPONENT_TSX.read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines()
            if not line.lstrip().startswith("*")
        )
        assert "count_as_of_ms" not in code
        assert "value_as_of_ms" not in code
        assert "countStamp(block)" in code
        assert "valueStamp(block)" in code
