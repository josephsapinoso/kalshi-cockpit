"""The window-gate reader's two traps, each caught by a test that fails without it.

Both were live mistakes made while writing the script on 2026-08-20, not
hypotheticals, and both fail in the *flattering-looking* direction of reporting
a FAIL on correct behaviour -- which in a measurement is the direction that gets
a working fix reverted.

    trap 1  an earlier window that was legitimately open runs at the 15s
            cadence. Counted as "early wakes with no window coming", it makes
            observation 4 fail on a loop doing exactly what it was told.
    trap 2  `odds_sweep_log` outlives the deploy. Passes written before the
            build under test are the OLD code's cadence, and 17 of them at
            ~17s apart sat in the first real pull.

What this does not establish
----------------------------
Nothing about the fix. These test the reader, on synthetic rows. The
registration is `docs/measurements/2026-08-20-window-gate-plan.md`.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from scripts.read_window_gate_observations import main, pass_grid

OPEN_MS = int(dt.datetime(2026, 8, 20, 15, 26, tzinfo=dt.UTC).timestamp() * 1000)
DEPLOY_MS = int(dt.datetime(2026, 8, 20, 3, 54, tzinfo=dt.UTC).timestamp() * 1000)

# The three `detail` shapes `decide_sweeps` actually writes, copied from a live
# pull rather than invented -- the reader matches on this text, so a paraphrase
# here would test a string this repo never emits.
CLOSED = (
    "no sweep: next slot is baseball_mlb at 15:26Z-16:26Z for 6 game(s) "
    "from 16:41Z, sweeping 75-15 min before first kickoff"
)
OPEN = (
    "no sweep: basketball_wnba's window is open and its odds are 1.5min old; "
    "next refresh at 01:46Z"
)
SERVED = (
    "1 game(s) from 02:10Z, sweeping 75-15 min before first kickoff; "
    "holding the window open"
)


def _pull(rows: list[tuple[int, str]], *, truncated: bool = False) -> dict:
    return {
        "query": "sweep-log",
        "db": "/data/cockpit.db",
        "sections": [
            {
                "title": "odds_sweep_log: count and pass_ms range by outcome",
                "columns": ["outcome", "n"],
                "rows": [],
                "row_count": 0,
                "empty": True,
                "truncated": False,
                "row_cap": 300,
            },
            {
                "title": "odds_sweep_log: last 400 rows, newest first",
                "columns": ["id", "pass_ms", "sport_key", "outcome", "detail"],
                "rows": [
                    [i, ms, None, "skipped", detail]
                    for i, (ms, detail) in enumerate(rows)
                ],
                "row_count": len(rows),
                "empty": not rows,
                "truncated": truncated,
                "row_cap": 300,
            },
        ],
    }


def _write(tmp_path, rows, **kwargs):
    path = tmp_path / "pull.json"
    path.write_text(json.dumps(_pull(rows, **kwargs)), encoding="utf-8")
    return str(path)


def _run(capsys, path, since="2026-08-20T03:54:00Z") -> str:
    main(
        [
            path,
            "--open",
            "2026-08-20T15:26:00Z",
            "--close",
            "2026-08-20T16:26:00Z",
            "--since",
            since,
        ]
    )
    return capsys.readouterr().out


class TestWindowStateComesFromTheDetailText:
    """`detail` is the durable record of `window_open`, so observation 3 is read
    rather than inferred from how fast the passes came."""

    def test_the_closed_wording_reads_closed(self):
        _, state = pass_grid(_pull([(OPEN_MS, CLOSED)]))
        assert state[OPEN_MS] == "closed"

    def test_the_open_wording_reads_open(self):
        _, state = pass_grid(_pull([(OPEN_MS, OPEN)]))
        assert state[OPEN_MS] == "open"

    def test_the_sweep_that_opens_the_window_reads_open(self):
        _, state = pass_grid(_pull([(OPEN_MS, SERVED)]))
        assert state[OPEN_MS] == "open"

    def test_one_open_row_beats_several_closed_ones_on_the_same_pass(self):
        """A pass writes one row per sport. The sport whose window is open is
        the decision that matters; the others are about a different game."""
        _, state = pass_grid(
            _pull([(OPEN_MS, CLOSED), (OPEN_MS, OPEN), (OPEN_MS, CLOSED)])
        )
        assert state[OPEN_MS] == "open"

    def test_one_pass_writing_three_rows_is_one_pass(self):
        grid, _ = pass_grid(
            _pull([(OPEN_MS, CLOSED), (OPEN_MS, OPEN), (OPEN_MS, CLOSED)])
        )
        assert grid == [OPEN_MS]


class TestTrapOneAnEarlierOpenWindowIsNotAnEarlyWake:
    def test_fast_passes_inside_an_earlier_open_window_do_not_fail_observation_4(
        self, tmp_path, capsys
    ):
        # 04:00Z-04:05Z at 17s with the window open, then the slow cadence.
        rows = [(DEPLOY_MS + 6 * 60_000 + i * 17_000, OPEN) for i in range(18)]
        rows += [(DEPLOY_MS + 30 * 60_000 + i * 900_000, CLOSED) for i in range(9)]
        out = _run(capsys, _write(tmp_path, rows))
        assert "0 below the 765s slow-cadence floor" in out
        assert "18 excluded as window-open" in out

    def test_the_guard_is_real_because_removing_the_exclusion_fails(
        self, tmp_path, capsys
    ):
        """Same rows, but the open ones relabelled closed -- which is what the
        first draft effectively did. It must now fail."""
        rows = [(DEPLOY_MS + 6 * 60_000 + i * 17_000, CLOSED) for i in range(18)]
        rows += [(DEPLOY_MS + 30 * 60_000 + i * 900_000, CLOSED) for i in range(9)]
        out = _run(capsys, _write(tmp_path, rows))
        assert "0 below the 765s slow-cadence floor" not in out


class TestTrapTwoThePreDeployPassesAreADifferentBuild:
    def test_passes_before_since_are_excluded(self, tmp_path, capsys):
        # 17 pre-deploy passes at 17s -- the old code's cadence, really present
        # in the 2026-08-20 pull -- then a clean slow run on the new build.
        rows = [(DEPLOY_MS - 2 * 3600_000 + i * 17_000, CLOSED) for i in range(17)]
        rows += [(DEPLOY_MS + 30 * 60_000 + i * 900_000, CLOSED) for i in range(9)]
        out = _run(capsys, _write(tmp_path, rows))
        assert "17 earlier passes ran the old code and are excluded" in out
        assert "0 below the 765s slow-cadence floor" in out

    def test_the_guard_is_real_because_widening_since_fails(self, tmp_path, capsys):
        """Same rows with `--since` moved back before the old build. The 17
        pre-deploy gaps come back and the run reports them."""
        rows = [(DEPLOY_MS - 2 * 3600_000 + i * 17_000, CLOSED) for i in range(17)]
        rows += [(DEPLOY_MS + 30 * 60_000 + i * 900_000, CLOSED) for i in range(9)]
        out = _run(capsys, _write(tmp_path, rows), since="2026-08-19T00:00:00Z")
        assert "0 below the 765s slow-cadence floor" not in out
        assert "16 below the 765s slow-cadence floor" in out


class TestItRefusesToPresentAnIncompleteWindowAsTheMeasurement:
    def test_a_pull_ending_before_the_close_says_so_first(self, tmp_path, capsys):
        rows = [(DEPLOY_MS + i * 900_000, CLOSED) for i in range(9)]
        out = _run(capsys, _write(tmp_path, rows))
        assert "THE PULL ENDS BEFORE THE WINDOW CLOSES" in out

    def test_a_truncated_tail_warns(self, tmp_path, capsys):
        rows = [(DEPLOY_MS + i * 900_000, CLOSED) for i in range(9)]
        path = _write(tmp_path, rows, truncated=True)
        main(
            [
                path,
                "--open",
                "2026-08-20T15:26:00Z",
                "--close",
                "2026-08-20T16:26:00Z",
                "--since",
                "2026-08-20T03:54:00Z",
            ]
        )
        # Read once: `_run` drains the capture, so asking it for stderr
        # afterwards returns an empty string and the assertion passes on nothing.
        assert "TRUNCATED" in capsys.readouterr().err

    def test_an_empty_pull_returns_nonzero_rather_than_a_verdict(self, tmp_path):
        assert (
            main(
                [
                    _write(tmp_path, []),
                    "--open",
                    "2026-08-20T15:26:00Z",
                    "--close",
                    "2026-08-20T16:26:00Z",
                    "--since",
                    "2026-08-20T03:54:00Z",
                ]
            )
            == 2
        )

    def test_since_is_required(self, tmp_path):
        with pytest.raises(SystemExit):
            main(
                [
                    _write(tmp_path, []),
                    "--open",
                    "2026-08-20T15:26:00Z",
                    "--close",
                    "2026-08-20T16:26:00Z",
                ]
            )


class TestObservationOneIsNotComputedHere:
    def test_it_says_the_absence_of_a_prune_line_confirms_nothing(
        self, tmp_path, capsys
    ):
        """The registration's weakest arm must announce its own weakness in the
        output, not only in the docstring nobody reads at 16:30Z."""
        rows = [(DEPLOY_MS + i * 900_000, CLOSED) for i in range(9)]
        out = _run(capsys, _write(tmp_path, rows))
        assert "Absence does NOT confirm it" in out
