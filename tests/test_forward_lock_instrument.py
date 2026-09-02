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

#: The fixture's `T0`, derived from the deploy constant rather than picked.
#:
#: It must sit **after** `ADR_0091_DEPLOY_MS`, because that is the real
#: ordering: section 2.2's discarded interval runs from the deploy to the first
#: mirror marker, ~26 h on live. The first version of this file used a bare
#: literal that landed *before* the deploy, which silently made the "pre-fix"
#: window (ms < deploy) swallow the whole post-`T0` exposure -- so C4 and C5
#: compared a window against itself and could not fail. Three tests caught it.
DISCARDED_INTERVAL_MS = 26 * 3_600_000
T0_MS = inspector.ADR_0091_DEPLOY_MS + DISCARDED_INTERVAL_MS


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


def _write_rss(tmp_path, samples):
    """`samples` is [(ms, restart, wal_kb)].

    `restart` is True (first sample of a process), False (an ordinary sample),
    or None meaning **the `produced_by` key is absent entirely** -- a line
    written before the field existed on 2026-08-29. The three are different
    states and `_read_rss_samples` must not conflate the last two.
    """
    lines = []
    for ms, restart, wal_kb in samples:
        entry = {"ms": ms, "kind": "quote", "rss_kb": 1}
        if restart is not None:
            entry["produced_by"] = None if restart else "quote"
        if wal_kb is not None:
            entry["wal_kb"] = wal_kb
        lines.append(json.dumps(entry))
    (tmp_path / "loop_rss.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


class TestAbsentAndNullProducedByAreDifferentStates:
    """The defect that would have made C3 easier to pass.

    `produced_by: null` is a process's **first sample** -- the restart marker
    the append-only file otherwise lacks. An **absent** `produced_by` is a line
    written before the field existed (2026-08-29) and says nothing about
    restarts.

    `entry.get("produced_by") is None` cannot tell them apart. On the live file
    it counts **752** restarts where there are **44** -- seventeen-fold, and in
    the flattering direction: phantom restarts shorten every process age, which
    lowers `A_pre` and lets more cycles qualify as aged, so C3 gets *easier*.
    """

    def test_a_missing_key_is_not_read_as_a_restart(self, tmp_path):
        _write_rss(tmp_path, [
            (T0_MS + i * 60_000, None, 100) for i in range(10)
        ])
        samples, err = inspector._read_rss_samples(str(tmp_path / "cockpit.db"))
        assert err is None
        assert len(samples) == 10
        assert all(s["restart"] is None for s in samples), (
            "a line with no `produced_by` key must be tri-state None, not False "
            "and certainly not True"
        )
        assert inspector._process_start_index(samples) == [], (
            "no true restart marker means nothing can be aged; ageing against "
            "the file's first line would invent an age"
        )

    def test_an_explicit_null_is_a_restart(self, tmp_path):
        _write_rss(tmp_path, [
            (T0_MS, True, 100),
            (T0_MS + 60_000, False, 100),
            (T0_MS + 120_000, False, 100),
        ])
        samples, _ = inspector._read_rss_samples(str(tmp_path / "cockpit.db"))
        assert [s["restart"] for s in samples] == [True, False, False]
        aged = inspector._process_start_index(samples)
        assert len(aged) == 3
        assert all(start == T0_MS for _, start in aged)

    def test_wal_kb_absent_is_none_and_never_zero(self, tmp_path):
        """`wal_kb: null` is 'not measured'; `wal_kb: 0` is 'the WAL is
        empty'. C4 takes percentiles over these and a zero would drag them."""
        _write_rss(tmp_path, [
            (T0_MS, True, None),
            (T0_MS + 60_000, False, 0),
            (T0_MS + 120_000, False, 500),
        ])
        samples, _ = inspector._read_rss_samples(str(tmp_path / "cockpit.db"))
        assert samples[0]["wal_kb"] is None
        assert samples[1]["wal_kb"] == 0
        assert samples[2]["wal_kb"] == 500


class TestC3RestartCoverage:
    """§7's C3: 30 fast cycles at process age >= `A_pre`."""

    def _cycles(self, n=200):
        return [(T0_MS, True)] + [
            (T0_MS + i * CYCLE_MS, False) for i in range(1, n)
        ]

    def test_a_process_that_never_ages_fails_c3(self, tmp_path):
        """The shape this session created: deploy every twenty minutes and no
        process life reaches `A_pre`, so `E` climbs while aged exposure does
        not."""
        # A restart every 10 minutes across the whole exposure.
        rss = []
        for i in range(0, 200):
            ms = T0_MS + i * 60_000
            rss.append((ms, i % 10 == 0, 100))
        _write_rss(tmp_path, rss)
        path, conn = _seed(tmp_path, cycles=self._cycles(), journal=[])
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "PRECONDITIONS")
        assert rows["C3 restart coverage"][1] == "FAIL", rows["C3 restart coverage"]
        assert "A_pre" in str(rows["C3 restart coverage"][2])

    def test_one_long_process_life_passes_c3(self, tmp_path):
        """One boot, then samples for many hours: aged cycles accumulate."""
        rss = [(T0_MS, True, 100)]
        rss += [(T0_MS + i * 60_000, False, 100) for i in range(1, 900)]
        _write_rss(tmp_path, rss)
        path, conn = _seed(tmp_path, cycles=self._cycles(), journal=[])
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "PRECONDITIONS")
        assert rows["C3 restart coverage"][1] == "PASS", rows["C3 restart coverage"]

    def test_a_pre_falls_back_when_no_pre_fix_burst_can_be_aged(self, tmp_path):
        """§7 fixes the fallback at 2.0 h and says why: the largest round value
        below the longest observed post-fix life, so C3 is reachable rather
        than automatically failing."""
        rss = [(T0_MS, True, 100)]
        rss += [(T0_MS + i * 60_000, False, 100) for i in range(1, 900)]
        _write_rss(tmp_path, rss)
        path, conn = _seed(tmp_path, cycles=self._cycles(), journal=[])
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "PRECONDITIONS")
        note = str(rows["C3 restart coverage"][2])
        assert "FALLBACK 2.0 h" in note, note


class TestC4AndC5Comparability:
    """§7's C4 (WAL) and C5 (victim tempo). Both compare the post-`T0`
    exposure against the **pre-fix** window, which ends at ADR 0091's deploy --
    not at `T0`, because §2.2's discarded interval sits between them."""

    def _cycles(self):
        return [(T0_MS, True)] + [
            (T0_MS + i * CYCLE_MS, False) for i in range(1, 200)
        ]

    def _rss_with(self, pre_wal, post_wal, *, pre_step=60_000, post_step=60_000):
        pre_start = inspector.ADR_0091_DEPLOY_MS - 300 * pre_step
        rss = [(pre_start, True, pre_wal)]
        rss += [
            (pre_start + i * pre_step, False, pre_wal) for i in range(1, 300)
        ]
        rss += [(T0_MS, True, post_wal)]
        rss += [
            (T0_MS + i * post_step, False, post_wal) for i in range(1, 900)
        ]
        return rss

    def test_a_shrunken_wal_fails_c4(self, tmp_path):
        """Lock duration plausibly grows with WAL size and restarts shrink it,
        so a post-`T0` WAL well below the pre-fix floor means the arms are not
        comparable -- the fix would look good for the wrong reason."""
        _write_rss(tmp_path, self._rss_with(pre_wal=5000, post_wal=10))
        path, conn = _seed(tmp_path, cycles=self._cycles(), journal=[])
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "PRECONDITIONS")
        assert rows["C4 WAL comparability"][1] == "FAIL"

    def test_a_comparable_wal_passes_c4(self, tmp_path):
        _write_rss(tmp_path, self._rss_with(pre_wal=1000, post_wal=1200))
        path, conn = _seed(tmp_path, cycles=self._cycles(), journal=[])
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "PRECONDITIONS")
        assert rows["C4 WAL comparability"][1] == "PASS"

    def test_samples_without_wal_kb_are_excluded_from_c4_not_read_as_zero(
        self, tmp_path
    ):
        """The live file carries both shapes: 708 of 5,532 lines predate
        `wal_kb`. Reading an absent field as 0 would drag the post-`T0` median
        toward zero and fail C4 as WAL-CONFOUNDED for a reason that is an
        artifact of the file's history rather than the database's state.
        """
        pre_start = inspector.ADR_0091_DEPLOY_MS - 300 * 60_000
        rss = [(pre_start, True, 1000)]
        rss += [(pre_start + i * 60_000, False, 1000) for i in range(1, 300)]
        rss += [(T0_MS, True, 1200)]
        # Half the post-T0 samples carry no `wal_kb` at all. If they were read
        # as 0 the median would collapse to 0 and C4 would FAIL.
        rss += [
            (T0_MS + i * 60_000, False, None if i % 2 else 1200)
            for i in range(1, 900)
        ]
        _write_rss(tmp_path, rss)
        path, conn = _seed(tmp_path, cycles=self._cycles(), journal=[])
        row = _rows(inspector._q_forward_lock(conn, _Args(path)),
                    "PRECONDITIONS")["C4 WAL comparability"]
        assert row[1] == "PASS", row
        assert "median wal_kb post-T0 = 1200" in str(row[2]), row[2]

    def test_a_halved_pass_tempo_fails_c5(self, tmp_path):
        """Fewer passes means fewer collisions regardless of the fix."""
        _write_rss(tmp_path, self._rss_with(
            pre_wal=1000, post_wal=1000, pre_step=60_000, post_step=180_000,
        ))
        path, conn = _seed(tmp_path, cycles=self._cycles(), journal=[])
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "PRECONDITIONS")
        assert rows["C5 victim tempo"][1] == "FAIL"
        assert "/h" in str(rows["C5 victim tempo"][2])

    def test_a_doubled_pass_tempo_also_fails_c5(self, tmp_path):
        """The tolerance is two-sided as registered (section 7: "within plus or
        minus 25%"), and the live 2026-09-02 reading failed it in THIS
        direction -- post-T0 79.64/h against a pre-fix 56.81/h, +40%.

        Mutation observed red: make `c5_ok` one-sided,
        `(pre_tempo - post_tempo) / pre_tempo <= C5_TEMPO_TOLERANCE`, so only a
        SLOWER victim fails. The halved-tempo test above stays green under that
        mutation; this one is what pins the registered shape.
        """
        _write_rss(tmp_path, self._rss_with(
            pre_wal=1000, post_wal=1000, pre_step=60_000, post_step=30_000,
        ))
        path, conn = _seed(tmp_path, cycles=self._cycles(), journal=[])
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "PRECONDITIONS")
        assert rows["C5 victim tempo"][1] == "FAIL", rows["C5 victim tempo"]
        assert "tolerance +/-25%" in str(rows["C5 victim tempo"][2])

    def test_a_matched_tempo_passes_c5(self, tmp_path):
        _write_rss(tmp_path, self._rss_with(pre_wal=1000, post_wal=1000))
        path, conn = _seed(tmp_path, cycles=self._cycles(), journal=[])
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "PRECONDITIONS")
        assert rows["C5 victim tempo"][1] == "PASS"


class TestFixConfirmedIsReachableAndGuarded:
    """§6.3 conditions FIX CONFIRMED on E, K, E_n **and every** precondition."""

    def _cycles(self):
        return [(T0_MS, True)] + [
            (T0_MS + i * CYCLE_MS, False) for i in range(1, 200)
        ]

    def _healthy_rss(self):
        pre_start = inspector.ADR_0091_DEPLOY_MS - 300 * 60_000
        rss = [(pre_start, True, 1000)]
        rss += [(pre_start + i * 60_000, False, 1000) for i in range(1, 300)]
        rss += [(T0_MS, True, 1100)]
        rss += [(T0_MS + i * 60_000, False, 1100) for i in range(1, 900)]
        return rss

    def test_all_conditions_met_reaches_fix_confirmed(self, tmp_path):
        _write_rss(tmp_path, self._healthy_rss())
        path, conn = _seed(tmp_path, cycles=self._cycles(), journal=[])
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "THE REGISTERED TEST")
        assert str(rows["VERDICT"][1]) == "FIX CONFIRMED ON LIVE EVIDENCE"

    def test_one_failed_precondition_blocks_it_and_is_named(self, tmp_path):
        """§6.3: a failed precondition is reported by name and *never*
        shortened to UNRESOLVED alone."""
        rss = self._healthy_rss()
        # Break C4 alone: post-T0 WAL far below the pre-fix floor.
        rss = [
            (ms, restart, 5 if ms >= T0_MS else wal)
            for ms, restart, wal in rss
        ]
        _write_rss(tmp_path, rss)
        path, conn = _seed(tmp_path, cycles=self._cycles(), journal=[])
        rows = _rows(inspector._q_forward_lock(conn, _Args(path)),
                     "THE REGISTERED TEST")
        verdict = str(rows["VERDICT"][1])
        assert verdict == "UNRESOLVED - C4", verdict
        assert verdict != "UNRESOLVED"

    def test_no_rss_file_makes_all_three_uncomputable_not_passed(self, tmp_path):
        """An absent instrument is not a passing precondition. This is the
        state the instrument shipped in before C3/C4/C5 were built, and it must
        never render as FIX CONFIRMED."""
        path, conn = _seed(tmp_path, cycles=self._cycles(), journal=[])
        sections = inspector._q_forward_lock(conn, _Args(path))
        pre = _rows(sections, "PRECONDITIONS")
        for name in ("C3 restart coverage", "C4 WAL comparability",
                     "C5 victim tempo"):
            assert pre[name][1] == "NOT COMPUTED", name
        verdict = str(_rows(sections, "THE REGISTERED TEST")["VERDICT"][1])
        assert verdict == "UNRESOLVED - C3/C4/C5", verdict


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
