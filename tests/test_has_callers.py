"""Every module on the critical path must be reachable from something that runs.

This project has now shipped the same defect three times: a module written to
completion, tested thoroughly, recorded as done in `tasks/todo.md`, and called
by nothing.

    analysis/clv.py        ~40 tests. Nothing ever called `score_recommendations`,
                           so no row could be scored and the gate's counter was
                           structurally pinned at zero for the project's life.
    notify/discord.py      ~20 tests. Not imported anywhere. The only match for
                           "discord" in the codebase was the word "discordant"
                           in `backtest.py`.
    backend/agents/*       ~40 tests implying a safety layer. Still orphaned;
                           named below so this file fails when it is wired up
                           and the exception can be deleted.

The failure has no line number. Every file is individually excellent, coverage
goes up, and the missing thing is the *absence of a call* -- which no reviewer
reads and no coverage tool reports, because the untested code does not exist.

The cheap detector was already written down in `tasks/lessons.md`:

    grep -rn "score_recommendations" --include=*.py .
    # if every hit is tests/ or a seeder, the feature does not exist yet

This is that grep, run by CI instead of by memory.

What this does not establish
----------------------------
That the caller is reached at *runtime*. A function imported by a module nobody
runs still passes here. It is a floor, not a proof -- the behavioural tests
beside it are what establish the path actually executes.
"""

from __future__ import annotations

import ast
import fnmatch
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Directories that do not count as a caller. A feature called only by its own
# tests and its own demo seeder is a feature that has not shipped.
NOT_A_CALLER = ("tests", "warehouse", ".venv", "node_modules", "__pycache__")

# The seeder is not a caller either, for the same reason tests are not: it is
# what `persist_recommendation` had for eleven build steps while the chain that
# was supposed to call it did not exist.
NOT_A_CALLER_FILES = ("backend/seed_demo.py",)

# (symbol, why it matters if it goes uncalled again)
MUST_HAVE_CALLERS = [
    (
        "score_recommendations",
        "nothing can be scored, and the gate's 300-game counter stays at zero "
        "however long the system runs",
    ),
    (
        "persist_if_changed",
        "the evidence record stops growing while every screen keeps rendering",
    ),
    (
        "decide_sweeps",
        "the odds budget goes on whichever pass runs first, and the actionable "
        "window lands wherever the process happened to restart",
    ),
    (
        "window_status",
        "the Board cannot say whether anything on it can be acted on",
    ),
    (
        "DiscordNotifier",
        "no alert reaches a phone, and the window is open for fifteen minutes "
        "twice a day",
    ),
    (
        "Alerter",
        "the notifier exists and nothing decides when to use it -- exactly the "
        "state this file exists to detect",
    ),
    (
        "run_settlement_pass",
        "no paper position ever closes, so paper exposure only ratchets up "
        "until the order endpoint refuses everything -- a cap that can only "
        "close is an off switch, which is exactly why ADR 0008 declined to "
        "count paper exposure at all",
    ),
    (
        "run_scoring_pass",
        "closing lines are never fetched, so `score_recommendations` has "
        "nothing to score even once it is called",
    ),
    (
        "run_market_result_pass",
        "`kalshi_markets.result` goes back to being NULL for every row, as it "
        "was for the project's life, and calibration can only ever be measured "
        "against `settlements` -- which reads `orders`, where the only writers "
        "are the auth-gated endpoint and the demo seeder",
    ),
    (
        "run_quote_pass",
        "the loop runs on the odds cadence alone, so every row is bettable for "
        "thirty seconds after the pass that wrote it and the tool is actionable "
        "for about a minute a day",
    ),
    (
        "live_ages",
        "the Board and the order endpoint go back to computing freshness by two "
        "separate paths, which is how a screen comes to offer a row the server "
        "refuses",
    ),
    (
        "Tempo",
        "nothing chooses between the two cadences, so either Kalshi is polled "
        "4,300 times a day or it is polled twice",
    ),
    (
        "quote_refresh_survives_interval",
        "the composed window goes unchecked again -- three defensible limits "
        "whose product is a tool nobody can use, with no module holding more "
        "than one of them",
    ),
    (
        "apply_verdict",
        "`backend/agents/*` goes back to being ~40 green tests implying a "
        "safety layer that can block nothing -- the fourth module in this "
        "project to be complete, tested, and called by nothing",
    ),
    (
        "review_surfaced",
        "`apply_verdict` has a definition and no path to it from a pass, so "
        "the Skeptic is wired up on paper only",
    ),
]

# Two symbols are deliberately NOT above, and it is worth saying why rather than
# leaving their absence to be read as an oversight. `confirm_recommendation` and
# `store.db.migrate` are each called only from the module that defines them --
# by `persist_if_changed` and `init_db` respectively, both of which *are* on the
# list. Adding them would fail this file for the wrong reason: they are reached,
# through an entry point already checked here. What guards them is behavioural,
# and each was verified by disabling it: `test_an_unchanged_row_is_confirmed_
# rather_than_left_to_rot` and `TestMigration`.


def production_sources() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.py"):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if any(part in NOT_A_CALLER for part in rel.split("/")):
            continue
        if rel in NOT_A_CALLER_FILES:
            continue
        files.append(path)
    return files


def _defines(tree: ast.AST, symbol: str) -> bool:
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == symbol
        for node in ast.walk(tree)
    )


def _uses(tree: ast.AST, symbol: str) -> bool:
    """Whether the symbol is referenced in *code*.

    Parsed rather than grepped, and that is not fastidiousness. The first
    version of this file matched the source text and reported
    `persist_recommendation` as called from `backend/runner.py` -- where the
    only occurrence is a docstring explaining that nothing calls it. A detector
    for orphaned code that counts prose about orphaned code as evidence of a
    caller is worse than no detector, because it reads as a passing check.

    Imports count as a use on purpose: a module the entrypoint imports is wired
    in even when the call sits behind a branch, and the alternative -- demanding
    a syntactic call -- would fail on every dependency-injected caller in this
    repo.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == symbol:
            return True
        if isinstance(node, ast.Attribute) and node.attr == symbol:
            return True
        if isinstance(node, ast.alias) and symbol in (node.name, node.asname):
            return True
    return False


def callers_of(symbol: str) -> list[str]:
    """Production files that use the symbol, excluding the one that defines it."""
    hits: list[str] = []
    for path in production_sources():
        try:
            tree = ast.parse(path.read_text("utf-8", errors="replace"))
        except SyntaxError:                                   # noqa: PERF203
            continue
        if _defines(tree, symbol):
            continue
        if _uses(tree, symbol):
            hits.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    return hits


@pytest.mark.parametrize(
    "symbol,consequence", MUST_HAVE_CALLERS, ids=[s for s, _ in MUST_HAVE_CALLERS]
)
def test_the_symbol_is_used_outside_its_own_module_and_tests(symbol, consequence):
    hits = callers_of(symbol)
    assert hits, (
        f"`{symbol}` is defined, tested, and called by nothing outside "
        f"tests/. If that stands, {consequence}. See tasks/lessons.md: "
        f"'Code with no caller is not a feature, it is a plan'."
    )


# The agent-fleet exception that used to live here is closed. It asserted the
# *current* state -- that `apply_verdict` had no caller -- so that wiring the
# fleet up would turn this file red and point at the list above. It did, on
# 2026-08-08, and `apply_verdict` and `review_surfaced` are now entries in
# MUST_HAVE_CALLERS rather than a documented exception beside it.


def _dockerignore_patterns() -> list[str]:
    """The file's rules, comments and blanks dropped, order preserved.

    Order is the whole semantic: `.dockerignore` is last-match-wins, so
    `scripts/*` followed by `!scripts/run_loop.py` ships one file and
    `!scripts/run_loop.py` followed by `scripts/*` ships none.
    """
    lines = []
    for raw in (ROOT / ".dockerignore").read_text("utf-8").splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def _matches(path: str, pattern: str) -> bool:
    """One pattern against one path, in Docker's `filepath.Match` semantics.

    Segment-wise rather than a flat `fnmatch`, because `*` does **not** cross a
    separator: `scripts/*` matches `scripts/migrate_db.py` and must not match
    `scripts/sub/deep.py`. A flat fnmatch gets that wrong in the direction that
    reports a file as shipped when it is not.
    """
    pattern_parts = pattern.rstrip("/").split("/")
    path_parts = path.split("/")

    # A pattern for a directory excludes everything beneath it (`tests/` hides
    # `tests/fixtures/x.json`), so a pattern shorter than the path may still
    # match -- but only as a prefix.
    if len(pattern_parts) > len(path_parts):
        return False
    if "**" not in pattern_parts and len(pattern_parts) < len(path_parts):
        path_parts = path_parts[: len(pattern_parts)]
    if len(pattern_parts) != len(path_parts):
        return False

    return all(
        fnmatch.fnmatchcase(actual, expected)
        for actual, expected in zip(path_parts, pattern_parts)
    )


def _is_ignored(path: str, patterns: list[str]) -> bool:
    """Whether `path` is excluded from the build context. Last match wins."""
    ignored = False
    for pattern in patterns:
        negated = pattern.startswith("!")
        if _matches(path, pattern.lstrip("!")):
            ignored = not negated
    return ignored


class TestTheEntrypointRunsWhatItMustRunFirst:
    """The same question asked of a shell script instead of a module.

    `store.db.migrate` is reached from `init_db`, which the chain runner calls.
    That is not enough on the deployed instance: the **API** opens the database
    read-only and `open_db` refuses a schema version it does not recognise, so
    on a boot after a schema change it would 500 on every page until the runner
    happened to start -- while `/api/health`, which touches no database, stayed
    green throughout.

    So the migration has to run *before* uvicorn, and the only thing that can
    assert that is a test that reads the script. Nothing else in the suite runs
    `entrypoint.sh` at all.
    """

    def _commands(self) -> list[str]:
        """The script's executable lines, with comments and blanks dropped.

        Not the raw text. The first version of this test searched for
        `"uvicorn"` and matched the header comment explaining why the naive
        `uvicorn & exec node` pattern is wrong -- so it reported the backend
        starting at byte 111, before everything, and failed. That is exactly the
        defect `_uses` above exists to avoid, reproduced in the one file that
        documents it: **prose about a command is not the command.** This repo's
        comment density makes any text search a search of the comments.
        """
        lines = []
        for raw in (ROOT / "docker" / "entrypoint.sh").read_text("utf-8").splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            lines.append(stripped)
        return lines

    def _first_index(self, commands: list[str], needle: str) -> int:
        return next(
            (i for i, line in enumerate(commands) if needle in line), -1
        )

    def test_the_migration_runs_before_the_backend_starts(self):
        commands = self._commands()
        migrate_at = self._first_index(commands, "scripts/migrate_db.py")
        uvicorn_at = self._first_index(commands, "uvicorn")

        assert migrate_at != -1, (
            "entrypoint.sh does not migrate. A schema change would reach the "
            "live volume only when the chain runner next called init_db, and "
            "the API would refuse every read until then."
        )
        assert uvicorn_at != -1, "entrypoint.sh no longer starts the backend"
        assert migrate_at < uvicorn_at, (
            "the migration runs after uvicorn, so the API opens the old schema "
            "first and refuses it"
        )

    def test_the_detector_reads_commands_rather_than_comments(self):
        """The guard on the guard, because the naive version passed for a
        different reason than the one it claimed."""
        commands = self._commands()
        assert not any(line.startswith("#") for line in commands)
        assert any("uvicorn" in line for line in commands)

    # -- and the script it names has to be in the image ---------------------
    #
    # The ordering test above passed while the deployed container crash-looped
    # on `can't open file '/app/scripts/migrate_db.py'`. Both statements were
    # true at once: the entrypoint did run the migration first, and the file it
    # ran was not there. `.dockerignore` carries `scripts/*` with a hand-kept
    # `!` allowlist, and the allowlist was written when the entrypoint ran one
    # script and never revisited when it gained a second.
    #
    # This is the repo's own two-limits shape: one guard covering half a
    # property reads exactly like a guard covering all of it.

    def _scripts_the_entrypoint_runs(self) -> list[str]:
        """Paths of the form `scripts/<name>.py` in executable lines.

        Derived from the script, not listed here, so a third script added to
        the entrypoint is covered without anyone remembering to update a test.
        """
        found: list[str] = []
        for line in self._commands():
            for token in re.findall(r"scripts/[A-Za-z0-9_./-]+\.py", line):
                if token not in found:
                    found.append(token)
        return found

    def test_every_script_the_entrypoint_runs_survives_dockerignore(self):
        scripts = self._scripts_the_entrypoint_runs()

        # If this ever empties out, the test below silently stops asserting
        # anything -- a vacuous pass reads identically to a real one.
        assert scripts, (
            "no `scripts/*.py` found in entrypoint.sh. Either the entrypoint "
            "stopped running any, or the extractor stopped matching them."
        )

        patterns = _dockerignore_patterns()
        for script in scripts:
            assert (ROOT / script).exists(), (
                f"entrypoint.sh runs {script}, which is not in the repo"
            )
            assert not _is_ignored(script, patterns), (
                f"entrypoint.sh runs {script} and .dockerignore excludes it "
                f"from the build context, so `COPY scripts/` cannot ship it. "
                f"The container starts, fails to open the file and exits -- "
                f"add `!{script}` to the allowlist."
            )

    def test_the_dockerignore_matcher_agrees_with_the_rules_it_models(self):
        """The guard on this guard.

        A matcher that never reports "ignored" would pass the test above on any
        input at all, which is the shape of a check that cannot fail. So assert
        both directions on the real file: a capture script is excluded by
        `scripts/*`, and the allowlisted ones are not.
        """
        patterns = _dockerignore_patterns()

        assert _is_ignored("scripts/capture_fixtures.py", patterns), (
            "the matcher does not honour `scripts/*`, so it would report every "
            "script as shipped"
        )
        assert not _is_ignored("scripts/run_loop.py", patterns)
        assert not _is_ignored("backend/api/routes.py", patterns)
        # Last match wins, and a `!` line only counts if it comes after the
        # pattern it negates.
        assert _is_ignored("scripts/x.py", ["!scripts/x.py", "scripts/*"])
        assert not _is_ignored("scripts/x.py", ["scripts/*", "!scripts/x.py"])

    def test_every_script_the_entrypoint_runs_at_least_loads(self):
        """Import-time breakage in a boot step is a crash loop.

        `--help` exits before `main`, so this proves only that the module and
        its imports load -- which is the cheap half. The expensive half is
        below, and only for the migration, because it is the one boot step that
        can be run with no credentials and no network.
        """
        import subprocess

        for script in self._scripts_the_entrypoint_runs():
            result = subprocess.run(
                [sys.executable, str(ROOT / script), "--help"],
                capture_output=True, text=True, cwd=ROOT, timeout=120,
            )
            assert result.returncode == 0, (
                f"{script} does not load: {result.stderr[-800:]}"
            )

    def test_the_migration_step_actually_runs_on_a_real_old_database(self, tmp_path):
        """Run the boot step, as the boot step, against a database like the one
        on the volume.

        This file already asserted that `scripts/migrate_db.py` runs before
        uvicorn and that it survives `.dockerignore`. Both were true on
        2026-08-08 and the deploy still crash-looped, because the script read
        `db._MIGRATIONS` in a shape it no longer had:

            TypeError: '_Migration' object is not iterable

        Nothing executed it. The container did, once, in production. That is
        the same shape as the `.dockerignore` failure this class was written
        for -- a boot step covered by assertions *about* it rather than by
        running it -- so the fix is to run it.

        A subprocess rather than an import, because `python scripts/migrate_db.py`
        is literally what `entrypoint.sh` invokes, and the module-level
        `sys.path` insert it needs to work only happens that way.
        """
        import subprocess

        from backend.store import db

        path = tmp_path / "volume.db"
        connection = db.init_db(path)
        # Wind it back to the version behind the current one, which is the
        # transition the live volume is about to make.
        previous = sorted(db._MIGRATIONS)[-1]
        for name in db._MIGRATIONS[previous].indexes:
            connection.execute(f"DROP INDEX IF EXISTS {name}")
        # A step that rebuilds a table says how to put the old one back; there
        # is nothing generic to infer. This was `statement.split("EXISTS")[1]`,
        # which read `ALTER TABLE settlements_v4 RENAME TO settlements` as an
        # index name and raised -- the fifth reader of `_MIGRATIONS` to assume
        # every statement creates an index.
        for statement in db._MIGRATIONS[previous].undo_statements:
            connection.execute(statement)
        for table, column, _ in db._MIGRATIONS[previous].columns:
            connection.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        connection.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(previous - 1),),
        )
        connection.commit()
        connection.close()

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "migrate_db.py"),
             "--db", str(path)],
            capture_output=True, text=True, cwd=ROOT, timeout=180,
        )
        assert result.returncode == 0, (
            "the boot step failed, which is a crash loop on the instance: "
            + result.stdout + result.stderr
        )
        assert f"migrated v{previous - 1} -> v{db.SCHEMA_VERSION}" in result.stdout, (
            result.stdout
        )
        # And the API can now open what the boot step left behind.
        db.open_db(path).close()

    def test_the_migration_step_is_idempotent_because_it_runs_every_boot(
        self, tmp_path
    ):
        import subprocess

        from backend.store import db

        path = tmp_path / "already.db"
        db.init_db(path).close()

        for _ in range(2):
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "migrate_db.py"),
                 "--db", str(path)],
                capture_output=True, text=True, cwd=ROOT, timeout=180,
            )
            assert result.returncode == 0, result.stderr
            assert "already at schema" in result.stdout, result.stdout

    def test_the_script_it_names_exists(self):
        """A boot step pointing at a missing file fails the deploy, loudly --
        but only on the deploy, which is the worst place to find out."""
        assert (ROOT / "scripts" / "migrate_db.py").exists()


class TestTheQuoteCadenceStaysQuiet:
    """Per-pass work must be guarded by `kind == "full"`, structurally.

    A quote pass runs every 15s while the window is open. Anything called
    unguarded there runs ~5,700 times a day, and this project has already lost
    its production log stream to exactly that: 962 warnings per pass overran a
    100-line buffer and made the boot lines unreadable for three sessions
    (`tasks/lessons.md`, 2026-08-09).

    The guard is asserted on the *source*, by AST, rather than by running the
    loop. Driving 61 quote passes to count log lines is the test I tried first;
    it needs a full fake exchange and it passes for the wrong reason the moment
    the window is closed, because then no quote pass fires at all.

    `run_scoring_pass` and `run_settlement_pass` are listed alongside the new
    one because they are guarded today for their own reasons -- credits and
    pointless requests -- and an enumeration that only names the newest case is
    a list someone will forget to extend.
    """

    FULL_PASS_ONLY = (
        "log_gate_progress",
        "run_scoring_pass",
        "run_settlement_pass",
        "run_market_result_pass",
        "daily_digest",
    )

    def _guarded_calls(self) -> set[str]:
        """Names called anywhere inside an `if kind == "full":` body."""
        tree = ast.parse((ROOT / "scripts" / "run_loop.py").read_text("utf-8"))
        guarded: set[str] = set()

        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            is_full_gate = (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "kind"
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "full"
                and isinstance(test.ops[0], ast.Eq)
            )
            if not is_full_gate:
                continue
            for inner in node.body:
                for call in ast.walk(inner):
                    if not isinstance(call, ast.Call):
                        continue
                    func = call.func
                    if isinstance(func, ast.Name):
                        guarded.add(func.id)
                    elif isinstance(func, ast.Attribute):
                        guarded.add(func.attr)
        return guarded

    def test_the_expensive_calls_are_all_behind_the_full_pass_guard(self):
        guarded = self._guarded_calls()
        missing = [name for name in self.FULL_PASS_ONLY if name not in guarded]
        assert not missing, (
            f"{missing} run on the 15s quote cadence -- ~5,700 times a day"
        )

    def test_the_guard_this_test_looks_for_actually_exists(self):
        """Anchors the test against its own vacuity.

        If `run_loop` were rewritten to dispatch on something other than
        `kind == "full"`, `_guarded_calls` would return an empty set and every
        assertion above would pass by finding nothing to check.
        """
        assert self._guarded_calls(), "no `if kind == \"full\":` block found"
