"""P1's three clauses must be able to FAIL on the machine the capture runs on.

These exist because they did not. `scripts/capture_odds_repeat_poll.py:278-301`
guarded clause 2 (`remaining_this_month`) and clause 3
(`x-requests-remaining`) with `is not None`. On a laptop both **are** `None` --
local `api_credits` holds no rows, so `BudgetState.remaining_reported` is
`None`, and `.env` sets no `ODDS_MONTHLY_CREDIT_BUDGET`, so
`BudgetState.remaining_this_month` is `None` (`backend/odds/budget.py:85-94`).
Neither clause could append to `failures`. The script printed **`P1 pass`** with
two of its three registered preconditions structurally unable to object.

**The general form of the defect, which is what these tests target, is: a
precondition whose input is `None` silently becomes a pass.** Three specific
regression tests would have been worth less -- the next clause added would have
been written in the same shape. So the central test here is a sweep over *every
nullable input* of `evaluate_p1`, asserting that no combination of `None` ever
produces an overall pass unless the account's own live count was actually read.

Nothing here reaches the network. The `/sports` probe is driven through
`httpx.MockTransport`, and `OddsConfig.load` is replaced so the real
`ODDS_API_KEY` from `.env` never enters the process under test.

What these tests do NOT establish
---------------------------------
That the capture would succeed, that the slate rule (P4) is satisfiable, or
that 24 credits are actually available on the account today -- they assert what
the code does with an answer, not what the answer is. They do not test the
analysis script, and they establish nothing about `last_update`, which is the
registration's actual question. They also do not prove the Odds API leaves
`/sports` unmetered; that is a property of the provider, evidenced by
`scripts/setup_odds_key.sh` having called it on every key install, and no test
in this repo can settle it without spending the credit it claims not to cost.
"""

from __future__ import annotations

import itertools
import sqlite3

import httpx
import pytest

from backend.config import OddsConfig
from scripts.capture_odds_repeat_poll import (
    CLAUSE_DAILY,
    CLAUSE_FAIL,
    CLAUSE_MONTHLY,
    CLAUSE_NOT_APPLICABLE,
    CLAUSE_PASS,
    CLAUSE_SERVER,
    REQUIRED_CREDITS,
    SPORTS_PROBE_PATH,
    evaluate_p1,
    p1_passes,
    probe_server_credits,
    run_capture,
)
import scripts.capture_odds_repeat_poll as capture


FAKE_KEY = "not-a-real-odds-api-key-0000"


def _config(**overrides) -> OddsConfig:
    base = dict(
        api_key=FAKE_KEY,
        base_url="https://odds.invalid/v4",
        daily_credit_budget=REQUIRED_CREDITS,
        regions=["us", "eu"],
        markets=["h2h", "spreads", "totals"],
        monthly_credit_budget=None,
        budget_day_start_utc_hour=10,
    )
    base.update(overrides)
    return OddsConfig(**base)


def _healthy(**overrides) -> dict:
    """Inputs on which every clause is satisfiable, so a mutation is visible."""
    kwargs = dict(
        remaining_today=REQUIRED_CREDITS,
        monthly_budget=1000,
        remaining_this_month=1000,
        live_remaining=19_000,
    )
    kwargs.update(overrides)
    return kwargs


def _state(results, name: str) -> str:
    return next(r.state for r in results if r.name == name)


class TestNoClauseIsSkippableBecauseItsInputIsNone:
    """The general defect: a `None` input turning a precondition into a pass."""

    NULLABLE = ("remaining_today", "monthly_budget",
                "remaining_this_month", "live_remaining")

    @pytest.mark.parametrize("n_none", range(1, len(NULLABLE) + 1))
    def test_no_combination_of_none_inputs_passes_without_a_live_count(self, n_none):
        """Sweep every subset of the nullable inputs, at every size.

        The rule asserted is exact rather than "something fails somewhere":
        **P1 passes if and only if the account's own live count was read.**
        Any other `None` may legitimately be `NOT-APPLICABLE`, but it may never
        carry the verdict on its own.
        """
        for subset in itertools.combinations(self.NULLABLE, n_none):
            kwargs = _healthy(**{field: None for field in subset})
            results = evaluate_p1(**kwargs)
            passed = p1_passes(results)

            if "live_remaining" in subset:
                assert passed is False, (
                    f"P1 passed with {subset} set to None. The account's own "
                    "credit count was never read and nothing refused."
                )
            if "remaining_today" in subset:
                assert passed is False, (
                    f"P1 passed with {subset} set to None -- an unreadable "
                    "daily ceiling was treated as headroom."
                )
            if passed:
                # The only permitted pass: nothing unreadable was asked for.
                assert set(subset) <= {"monthly_budget", "remaining_this_month"}
                assert _state(results, CLAUSE_SERVER) == CLAUSE_PASS

    def test_every_clause_reports_one_of_three_explicit_states(self):
        """A clause may not resolve to silence. Silence is what the bug was."""
        for subset_size in range(len(self.NULLABLE) + 1):
            for subset in itertools.combinations(self.NULLABLE, subset_size):
                results = evaluate_p1(
                    **_healthy(**{field: None for field in subset})
                )
                names = [r.name for r in results]
                assert names == [CLAUSE_DAILY, CLAUSE_MONTHLY, CLAUSE_SERVER]
                for result in results:
                    assert result.state in {
                        CLAUSE_PASS, CLAUSE_FAIL, CLAUSE_NOT_APPLICABLE
                    }
                    assert result.detail.strip(), (
                        f"{result.name} resolved to {result.state} with no "
                        "stated reason."
                    )

    def test_the_laptop_state_that_printed_p1_pass_now_fails(self):
        """The exact defect, reproduced: empty `api_credits`, no monthly cap.

        `remaining_reported is None` and `monthly_budget is None` was the live
        laptop state, and the old code printed `P1 pass` on it.
        """
        results = evaluate_p1(
            remaining_today=REQUIRED_CREDITS,
            monthly_budget=None,
            remaining_this_month=None,
            live_remaining=None,
        )
        assert p1_passes(results) is False
        assert _state(results, CLAUSE_SERVER) == CLAUSE_FAIL


class TestEachClauseCanIndividuallyRefuse:
    """A clause that cannot bind on its own is decoration."""

    def test_daily_clause_refuses_one_credit_short(self):
        results = evaluate_p1(**_healthy(remaining_today=REQUIRED_CREDITS - 1))
        assert _state(results, CLAUSE_DAILY) == CLAUSE_FAIL
        assert p1_passes(results) is False

    def test_monthly_clause_refuses_one_credit_short(self):
        results = evaluate_p1(**_healthy(
            monthly_budget=100, remaining_this_month=REQUIRED_CREDITS - 1
        ))
        assert _state(results, CLAUSE_MONTHLY) == CLAUSE_FAIL
        assert p1_passes(results) is False

    def test_server_clause_refuses_one_credit_short(self):
        results = evaluate_p1(**_healthy(live_remaining=REQUIRED_CREDITS - 1))
        assert _state(results, CLAUSE_SERVER) == CLAUSE_FAIL
        assert p1_passes(results) is False

    def test_exactly_the_required_credits_is_enough_on_every_clause(self):
        """`>=`, not `>`. The registration says `>= 24` in all three places."""
        results = evaluate_p1(
            remaining_today=REQUIRED_CREDITS,
            monthly_budget=REQUIRED_CREDITS,
            remaining_this_month=REQUIRED_CREDITS,
            live_remaining=REQUIRED_CREDITS,
        )
        assert p1_passes(results) is True


class TestTheMonthlyClauseSaysWhichItIs:
    """`NOT-APPLICABLE` is a decision, printed. It is not a skip."""

    def test_unset_ceiling_is_not_applicable_not_a_silent_pass(self):
        results = evaluate_p1(**_healthy(
            monthly_budget=None, remaining_this_month=None
        ))
        assert _state(results, CLAUSE_MONTHLY) == CLAUSE_NOT_APPLICABLE
        detail = next(r.detail for r in results if r.name == CLAUSE_MONTHLY)
        assert "ODDS_MONTHLY_CREDIT_BUDGET" in detail

    def test_a_ceiling_that_was_asked_for_and_cannot_be_read_refuses(self):
        """Configured but unreadable is an unreadable input, and it refuses."""
        results = evaluate_p1(**_healthy(
            monthly_budget=1000, remaining_this_month=None
        ))
        assert _state(results, CLAUSE_MONTHLY) == CLAUSE_FAIL
        assert p1_passes(results) is False

    def test_the_server_clause_may_never_be_not_applicable(self):
        """The structural coupling that makes `NOT-APPLICABLE` safe at all.

        Hand `p1_passes` a result set in which clause 3 has been marked
        `NOT-APPLICABLE` -- the shape a future edit would reintroduce -- and it
        must still refuse.
        """
        from scripts.capture_odds_repeat_poll import ClauseResult

        forged = [
            ClauseResult(CLAUSE_DAILY, CLAUSE_PASS, "fine"),
            ClauseResult(CLAUSE_MONTHLY, CLAUSE_NOT_APPLICABLE, "unset"),
            ClauseResult(CLAUSE_SERVER, CLAUSE_NOT_APPLICABLE,
                         "no count available"),
        ]
        assert p1_passes(forged) is False

    def test_a_result_set_missing_the_server_clause_refuses(self):
        from scripts.capture_odds_repeat_poll import ClauseResult

        assert p1_passes([ClauseResult(CLAUSE_DAILY, CLAUSE_PASS, "fine")]) is False


def _probe_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestTheSportsProbeRefusesRatherThanSubstitutes:
    """Every failure path returns `None`, and `None` fails clause 3."""

    async def test_reads_the_live_header_from_the_sports_path(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["key"] = request.url.params.get("apiKey")
            return httpx.Response(
                200, json=[], headers={"x-requests-remaining": "19412"}
            )

        async with _probe_client(handler) as client:
            remaining, detail = await probe_server_credits(
                _config(), http=client
            )

        assert remaining == 19412
        assert detail
        assert seen["path"].endswith(SPORTS_PROBE_PATH)
        # The probe must hit the UNMETERED endpoint, never an /odds path.
        assert "/odds" not in seen["path"]
        assert seen["key"] == FAKE_KEY

    @pytest.mark.parametrize(
        "response_factory, why",
        [
            (lambda: httpx.Response(200, json=[]), "no header at all"),
            (lambda: httpx.Response(
                200, json=[], headers={"x-requests-remaining": ""}
            ), "empty header"),
            (lambda: httpx.Response(
                200, json=[], headers={"x-requests-remaining": "unlimited"}
            ), "non-numeric header"),
            (lambda: httpx.Response(
                200, json=[], headers={"x-requests-remaining": "19412.5"}
            ), "non-integer header"),
            (lambda: httpx.Response(
                401, json={"message": "bad key"},
                headers={"x-requests-remaining": "19412"},
            ), "non-200 even with a header present"),
            (lambda: httpx.Response(
                500, text="upstream", headers={"x-requests-remaining": "19412"}
            ), "server error with a header present"),
        ],
    )
    async def test_unreadable_resolves_to_none_and_fails_p1(
        self, response_factory, why
    ):
        async with _probe_client(lambda request: response_factory()) as client:
            remaining, detail = await probe_server_credits(
                _config(), http=client
            )

        assert remaining is None, f"{why} produced a number instead of None"
        assert detail, f"{why} produced no stated reason"

        results = evaluate_p1(**_healthy(live_remaining=remaining))
        assert p1_passes(results) is False, (
            f"{why} did not refuse -- P1 passed without an account count"
        )

    async def test_a_transport_failure_resolves_to_none(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        async with _probe_client(handler) as client:
            remaining, detail = await probe_server_credits(
                _config(), http=client
            )

        assert remaining is None
        assert "ConnectError" in detail

    async def test_the_probe_never_leaks_the_key_or_a_url(self):
        """P2. The credential rides in the query string; httpx logs URLs.

        Every string this function can return is checked against the key and
        against the `apiKey` token that would mean a URL had been serialised.
        """
        cases = [
            lambda request: httpx.Response(200, json=[]),
            lambda request: httpx.Response(403, text="forbidden"),
            lambda request: httpx.Response(
                200, json=[], headers={"x-requests-remaining": "nope"}
            ),
            lambda request: httpx.Response(
                200, json=[], headers={"x-requests-remaining": "19412"}
            ),
        ]
        for handler in cases:
            async with _probe_client(handler) as client:
                remaining, detail = await probe_server_credits(
                    _config(), http=client
                )
            assert FAKE_KEY not in detail
            assert "apiKey" not in detail
            assert "https://" not in detail
            assert str(remaining) != FAKE_KEY

        def raiser(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(
                f"failed connecting to {request.url}", request=request
            )

        async with _probe_client(raiser) as client:
            _, detail = await probe_server_credits(_config(), http=client)
        assert FAKE_KEY not in detail
        assert "apiKey" not in detail
        assert "https://" not in detail


class TestTheCaptureRefusesToSpendWhenP1Fails:
    """End to end through `run_capture`, with no network and no credit."""

    @pytest.fixture
    def no_slate_check(self, monkeypatch):
        monkeypatch.setattr(
            capture, "check_slate",
            lambda sport_key, t0_ms: (True, "P4 pass (stubbed)", []),
        )

    @pytest.fixture
    def fake_config(self, monkeypatch):
        """The real `ODDS_API_KEY` never enters this process."""
        cfg = _config(daily_credit_budget=16)
        monkeypatch.setattr(
            capture.OddsConfig, "load", classmethod(lambda cls: cfg)
        )
        return cfg

    async def _run(self, tmp_path, handler) -> int:
        db_path = str(tmp_path / "p1.db")
        async with _probe_client(handler) as client:
            return await run_capture(
                sport_key="baseball_mlb",
                out_dir=tmp_path / "out",
                db_path=db_path,
                dry_run=True,
                probe_client=client,
            )

    async def test_dry_run_returns_p1_fail_when_the_probe_is_unreadable(
        self, tmp_path, monkeypatch, capsys, no_slate_check, fake_config
    ):
        code = await self._run(
            tmp_path, lambda request: httpx.Response(200, json=[]),
        )
        out = capsys.readouterr().out
        assert code == 4, "the capture did not refuse on an unreadable probe"
        assert "P1 FAIL" in out
        assert "P1 pass" not in out

    async def test_dry_run_returns_p1_fail_when_the_account_is_short(
        self, tmp_path, monkeypatch, capsys, no_slate_check, fake_config
    ):
        code = await self._run(
            tmp_path,
            lambda request: httpx.Response(
                200, json=[],
                headers={"x-requests-remaining": str(REQUIRED_CREDITS - 1)},
            ),
        )
        out = capsys.readouterr().out
        assert code == 4
        assert "P1 FAIL" in out

    async def test_dry_run_passes_only_with_a_live_count_and_spends_nothing(
        self, tmp_path, monkeypatch, capsys, no_slate_check, fake_config
    ):
        db_path = str(tmp_path / "p1.db")
        async with _probe_client(
            lambda request: httpx.Response(
                200, json=[], headers={"x-requests-remaining": "19412"}
            )
        ) as client:
            code = await run_capture(
                sport_key="baseball_mlb",
                out_dir=tmp_path / "out",
                db_path=db_path,
                dry_run=True,
                probe_client=client,
            )
        out = capsys.readouterr().out
        assert code == 0
        assert "P1 pass" in out
        assert "NOTHING SPENT" in out

        # P1 is free: the probe writes no credit row, so nothing was metered.
        conn = sqlite3.connect(db_path)
        try:
            spent = conn.execute("SELECT COUNT(*) FROM api_credits").fetchone()[0]
        finally:
            conn.close()
        assert spent == 0, "the precondition check recorded a credit spend"

    async def test_the_printed_output_names_every_clause(
        self, tmp_path, monkeypatch, capsys, no_slate_check, fake_config
    ):
        """The registration requires all three printed before poll 1."""
        await self._run(
            tmp_path,
            lambda request: httpx.Response(
                200, json=[], headers={"x-requests-remaining": "19412"}
            ),
        )
        out = capsys.readouterr().out
        for clause in (CLAUSE_DAILY, CLAUSE_MONTHLY, CLAUSE_SERVER):
            assert clause in out, f"{clause} was not printed before poll 1"


class TestTheInFlightHeaderParserDoesNotSubstitute:
    def test_unreadable_header_values_resolve_to_none(self):
        from scripts.capture_odds_repeat_poll import _as_int

        for raw in (None, "", "  ", "unlimited", "19412.5", "1e4", object()):
            assert _as_int(raw) is None, f"{raw!r} was coerced to a number"

    def test_readable_header_values_parse(self):
        from scripts.capture_odds_repeat_poll import _as_int

        assert _as_int("19412") == 19412
        assert _as_int(" 24 ") == 24
        assert _as_int(0) == 0
        assert _as_int("-1") == -1


def test_required_credits_is_the_registered_authorisation() -> None:
    """24, one shot. Not a tunable, and the fix did not touch it."""
    assert REQUIRED_CREDITS == 24
