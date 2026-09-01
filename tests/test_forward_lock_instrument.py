"""§11 of the forward-lock registration, built to a spec fixed before any read.

`docs/measurements/2026-09-01-forward-lock-instrument-registration.md` named
three capabilities the instrument did not have and fixed their specification in
advance, so that building them is a build task rather than a choice made while
looking at results. These tests check the arithmetic against §6.3's decision
rule verbatim, on synthetic cycles and a synthetic journal.

**No number here is quotable.** The fixtures are hand-built; the registration
names the live box as the only source of a verdict. What these establish is
that the instrument computes what §6.3 says and **refuses** what §6.3 forbids.

What these do NOT establish
---------------------------
- **Anything about ADR 0091.** They test an instrument, not a hypothesis.
- **That C3, C4 and C5 are implemented.** They are not, deliberately, and the
  tests below pin them as blocking `FIX CONFIRMED` rather than as absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.store import db
from scripts import inspect_live_db as inspector


CYCLE_MS = 300_000
T0_MS = 1_788_000_000_000


class _Args:
    def __init__(self, path: Path, limit: int = 200):
        self.db = str(path)
        self.limit = limit


def _seed(tmp_path, *, cycles, journal):
    """`cycles` is [(polled_ms, is_mirror)]; `journal` is [(ms, kind, error)]."""
    path = tmp_path / "cockpit.db"
    conn = db.init_db(path)
    for polled_ms, mirror in cycles:
        conn.execute(
            "INSERT INTO poll_log (polled_ms, endpoint, ok) VALUES (?, ?, 1)",
            (polled_ms, "mirror" if mirror else "positions"),
        )
        if mirror:
            # A mirror cycle also runs the ordinary endpoints; the marker is an
            # extra row, not a replacement. Seeding both is what makes the
            # MAX(CASE ...) split meaningful rather than trivially true.
            conn.execute(
                "INSERT INTO poll_log (polled_ms, endpoint, ok) "
                "VALUES (?, 'positions', 1)",
                (polled_ms,),
            )
    conn.commit()

    lines = []
    for ms, kind, error in journal:
        lines.append(json.dumps({
            "ms": ms, "kind": kind, "error": error, "consecutive_failures": 1,
        }))
    (tmp_path / "loop_failures.jsonl").write_text(
        "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
    )
    return path, conn


def _rows(sections, title_fragment):
    section = next(s for s in sections if title_fragment in s.title)
    return {str(r[0]): r for r in section.rows}


class TestTheT0Boundary:
    """Capability 1. `lock-attribution` reads the whole journal and would pool
    pre- and post-deploy bursts; this refuses to."""

    def test_no_mirror_row_refuses_rather_than_reporting_no_bursts(self, tmp_path):
        """C2. 'The build is not live' and 'there were no failures' are
        different states and the second is the dangerous one to print."""
        path, _ = _seed(
            tmp_path,
            cycles=[(T0_MS + i * CYCLE_MS, False) for i in range(5)],
            journal=[],
        )
        sections = inspector._q_forward_lock(
            db.open_db(path) if hasattr(db, "open_db") else db.init_db(path),
            _Args(path),
        )
        text = " ".join(s.title for s in sections)
        assert "C2 FAILED" in text
        assert "NOT LIVE" in text
        assert "no bursts" in text.lower()

    def test_a_burst_before_t0_is_excluded(self, tmp_path):
        """§2.2's discarded interval. The fix was live in it, and it still
        may not enter either arm."""
        cycles = [(T0_MS - 3 * CYCLE_MS, False), (T0_MS - 2 * CYCLE_MS, False)]
        cycles += [(T0_MS, True)]
        cycles += [(T0_MS + i * CYCLE_MS, False) for i in range(1, 6)]
        path, conn = _seed(
            tmp_path,
            cycles=cycles,
            journal=[(T0_MS - 2 * CYCLE_MS + 5_500, "failure",
                      "database is locked")],
        )
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "THE POPULATION")
        assert rows["K -- matched cycle >= T0, collapsed"][1] == 0
        assert rows["EXCLUDED -- pre-T0 or unmatchable"][1] == 1

    def test_the_straddler_class_is_provably_empty_and_the_branch_still_exists(
        self, tmp_path
    ):
        """§2.4 hedges with *"at most one burst can be in this class"*. It is
        in fact **zero**, and the reason is in the same sentence: *"`T0` is
        itself a cycle start."*

        A burst is matched to the newest cycle start at or before it. If the
        burst is stamped at or after `T0`, and `T0` is a cycle stamp, then the
        newest preceding start is `T0` or later -- never earlier. So no burst
        can be stamped after `T0` and matched before it.

        The defensive branch is kept anyway and this test pins the count at 0
        rather than deleting the branch, because the emptiness depends on `T0`
        being drawn from `poll_log` itself. If a future change ever derived
        `T0` from anywhere else -- a Fly release timestamp, say, which is the
        class of evidence a refused claim leaned on -- the class becomes
        reachable immediately, and a silently-missing branch would exclude
        nothing while reporting nothing.
        """
        cycles = [(T0_MS - CYCLE_MS, False), (T0_MS, True)]
        cycles += [(T0_MS + i * CYCLE_MS, False) for i in range(1, 8)]
        # Stamped one second after T0: the closest a burst can come to
        # straddling, matched to T0 itself.
        path, conn = _seed(
            tmp_path, cycles=cycles,
            journal=[(T0_MS + 1_000, "failure", "database is locked")],
        )
        sections = inspector._q_forward_lock(conn, _Args(path))
        pop = _rows(sections, "THE POPULATION")

        assert pop["EXCLUDED -- straddlers (section 2.4)"][1] == 0
        assert pop["K -- matched cycle >= T0, collapsed"][1] == 1, (
            "the burst belongs to T0's own cycle and must be IN the population"
        )
        assert not any("STRADDLERS" in s.title for s in sections), (
            "an empty straddler section must not be rendered at all"
        )


class TestTheMirrorFastSplit:
    """Capability 2. The old query was `SELECT DISTINCT polled_ms` with no
    `endpoint` join and could not classify a cycle at all."""

    def test_e_counts_fast_cycles_only(self, tmp_path):
        cycles = [(T0_MS, True)]
        cycles += [(T0_MS + i * CYCLE_MS, i % 3 == 0) for i in range(1, 10)]
        path, conn = _seed(tmp_path, cycles=cycles, journal=[])
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "THE BOUNDARY AND THE SPLIT")
        fast = sum(1 for ms, m in cycles if ms >= T0_MS and not m)
        mirror = sum(1 for ms, m in cycles if ms >= T0_MS and m)
        assert rows["cycles >= T0 (FAST)"][1] == fast
        assert rows["cycles >= T0 (MIRROR)"][1] == mirror
        assert fast and mirror, "fixture must contain both or it proves nothing"

    def test_a_mirror_matched_burst_does_not_enter_h(self, tmp_path):
        """`H` is FAST and in-band. A mirror-matched burst is in `K` and not in
        `H`, because the mirror branch is a different code path."""
        cycles = [(T0_MS, True)] + [
            (T0_MS + i * CYCLE_MS, i == 1) for i in range(1, 8)
        ]
        burst_ms = T0_MS + CYCLE_MS + 6_000  # in band, on a MIRROR cycle
        path, conn = _seed(
            tmp_path, cycles=cycles,
            journal=[(burst_ms, "failure", "database is locked")],
        )
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "THE POPULATION")
        assert rows["K -- matched cycle >= T0, collapsed"][1] == 1
        assert rows["of which FAST-matched"][1] == 0
        assert rows["H -- FAST and in band [5.000, 8.000]s"][1] == 0


class TestTheEValueAndTheRefusal:
    """Capability 3, and the refusal that matters more than the arithmetic."""

    def _many_cycles(self, n=200):
        return [(T0_MS, True)] + [
            (T0_MS + i * CYCLE_MS, False) for i in range(1, n)
        ]

    def test_no_verdict_but_signature_persists_below_e_star(self, tmp_path):
        """§6.3: *'No verdict of any kind may be quoted before E >= 160 except
        SIGNATURE PERSISTS.'* This is the sentence the instrument exists to
        obey, and a clean run at low exposure is exactly when it is tempting to
        break it."""
        path, conn = _seed(
            tmp_path, cycles=self._many_cycles(20), journal=[]
        )
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "THE REGISTERED TEST")
        verdict = str(rows["VERDICT"][1])
        assert verdict.startswith("UNRESOLVED - E =")
        assert "FIX CONFIRMED" not in verdict
        assert rows["exposure reached"][1] == "NO"

    def test_signature_persists_is_declarable_below_e_star(self, tmp_path):
        """The sole always-valid verdict. An e-value is a martingale under the
        null, so `E_n >= 200` controls type-I error at any stopping time --
        including one chosen by looking."""
        # Six in-band FAST bursts on distinct cycles: each multiplies E_n by
        # 0.5/p0 = 0.5/(3/300) = 50, so two suffice to clear 200.
        cycles = self._many_cycles(30)
        journal = [
            (T0_MS + i * CYCLE_MS + 6_000, "failure", "database is locked")
            for i in range(1, 4)
        ]
        path, conn = _seed(tmp_path, cycles=cycles, journal=journal)
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "THE REGISTERED TEST")
        assert "SIGNATURE PERSISTS" in str(rows["VERDICT"][1])
        assert rows["exposure reached"][1] == "NO", (
            "the point of this test is that it declares BELOW E*"
        )

    def test_an_out_of_band_burst_pushes_the_e_value_down(self, tmp_path):
        """The e-value must be able to move both ways, or it is an alarm with
        no null. An out-of-band burst multiplies by 0.5/(1-p0) < 1."""
        cycles = self._many_cycles(30)
        journal = [(T0_MS + CYCLE_MS + 120_000, "failure",
                    "database is locked")]  # 120 s: far outside [5, 8]
        path, conn = _seed(tmp_path, cycles=cycles, journal=journal)
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "THE REGISTERED TEST")
        assert float(rows["E_n"][1]) < 1.0

    def test_bursts_sharing_a_cycle_collapse_to_one(self, tmp_path):
        """§6.3: *'collapsing to one any bursts sharing a matched cycle.'* Two
        failures inside one cycle are one draw about that cycle."""
        cycles = self._many_cycles(30)
        cycle = T0_MS + CYCLE_MS
        journal = [
            (cycle + 5_200, "failure", "database is locked"),
            (cycle + 5_900, "failure", "database is locked"),
        ]
        path, conn = _seed(tmp_path, cycles=cycles, journal=journal)
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "THE POPULATION")
        assert rows["journal bursts (locked, consecutive=1)"][1] == 2
        assert rows["K -- matched cycle >= T0, collapsed"][1] == 1


class TestFixConfirmedCannotBeReachedWhileC3C4C5AreUncomputed:
    """§11's shortfall clause, working as written.

    §6.3 conditions FIX CONFIRMED on **every** precondition C1-C6. C3, C4 and
    C5 need `loop_rss.jsonl` and are not built, so the best reachable verdict
    is `UNRESOLVED - C3/C4/C5 NOT COMPUTED`. **The gap is reported, not routed
    around**, and it cannot produce a false positive.
    """

    def test_a_perfectly_clean_run_past_e_star_still_refuses(self, tmp_path):
        cycles = [(T0_MS, True)] + [
            (T0_MS + i * CYCLE_MS, False) for i in range(1, 200)
        ]
        path, conn = _seed(tmp_path, cycles=cycles, journal=[])
        sections = inspector._q_forward_lock(conn, _Args(path))
        rows = _rows(sections, "THE REGISTERED TEST")

        assert rows["exposure reached"][1] == "YES"
        assert rows["K (bursts)"][1] == 0
        verdict = str(rows["VERDICT"][1])
        assert verdict == "UNRESOLVED - C3/C4/C5 NOT COMPUTED", verdict
        assert "FIX CONFIRMED" not in verdict

    def test_the_uncomputed_preconditions_are_named_not_silently_passed(
        self, tmp_path
    ):
        """A precondition that is absent must not render as one that passed."""
        cycles = [(T0_MS, True)] + [
            (T0_MS + i * CYCLE_MS, False) for i in range(1, 200)
        ]
        path, conn = _seed(tmp_path, cycles=cycles, journal=[])
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "PRECONDITIONS")
        for name in ("C3 restart coverage", "C4 WAL comparability",
                     "C5 victim tempo"):
            assert rows[name][1] == "NOT COMPUTED", name
        assert rows["C2 T0 exists"][1] == "PASS"


class TestC6RaisesEStarAndNeverLowersIt:
    """§7's C6. `E* = 160` delivers p <= 0.005 only if `lambda_0 >= 0.03257`."""

    def test_e_star_is_raised_when_lambda_is_below_the_floor(self, tmp_path):
        # One burst in 300 fast cycles -> lambda_0 = 0.0033, well under floor.
        cycles = [(T0_MS, True)] + [
            (T0_MS + i * CYCLE_MS, False) for i in range(1, 301)
        ]
        journal = [(T0_MS + CYCLE_MS + 120_000, "failure",
                    "database is locked")]
        path, conn = _seed(tmp_path, cycles=cycles, journal=journal)
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "PRECONDITIONS")
        note = str(rows["C6 lambda_0 supports E*"][2])
        assert "RAISED" in note, note

        test_rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                          "THE REGISTERED TEST")
        assert int(test_rows["E (fast cycles >= T0)"][2].split("=")[1]) > 160

    def test_e_star_is_never_lowered(self, tmp_path):
        """A high `lambda_0` would make a smaller `E*` sufficient. The
        registration forbids taking it."""
        cycles = [(T0_MS, True)] + [
            (T0_MS + i * CYCLE_MS, False) for i in range(1, 21)
        ]
        journal = [
            (T0_MS + i * CYCLE_MS + 200_000, "failure", "database is locked")
            for i in range(1, 11)
        ]
        path, conn = _seed(tmp_path, cycles=cycles, journal=journal)
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "THE REGISTERED TEST")
        assert int(rows["E (fast cycles >= T0)"][2].split("=")[1]) == 160
