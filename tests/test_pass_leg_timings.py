"""A pass says where its wall clock went, leg by leg.

`took_s` alone is not a diagnosis. A quote pass melting the live box was
attributed first to the inserts and then to the parse -- both refuted by
measurement -- before the HTTP walk was found and narrowed (ADR 0053). The
narrowing took the walk from ~15s to 2.3s on the live box and the pass still
took 23.6s, because one total cannot say which of four legs moved. Each wrong
guess cost a session; each was settled in minutes once the leg was timed.

So the four legs are reported by the pass itself:

    leg_walk_ms   the Kalshi HTTP walk
    leg_parse_ms  classifying the payload into priceable events
    leg_store_ms  upsert + the quote rows
    leg_price_ms  devig, review and persist

What this does not establish
----------------------------
That the legs are exhaustive -- they are timed inside `run_kalshi_pass` and
`run_pricing_pass`, so anything a *caller* does between them (the odds sweep
leg, notably) is in `took_s` and in none of these fields. A sum well short of
`took_s` is therefore a real signal and not necessarily a bug: read it as
"time went somewhere none of these four legs covers".

Nor that the numbers are accurate under load. `perf_counter` on a saturated
shared vCPU measures wall clock including the time the process was descheduled,
which is the honest number for "why is the box unresponsive" and the wrong one
for "how much CPU did this leg need".
"""

from __future__ import annotations

from backend.runner import PassCounts

LEGS = ("leg_walk_ms", "leg_parse_ms", "leg_store_ms", "leg_price_ms")


class TestEveryLegIsReportedEvenWhenZero:
    """Absence and zero need opposite responses, so zero must be printed.

    A missing key means the leg was never timed -- go and instrument it. A
    zero means the leg ran and is not the problem -- go and look elsewhere.
    `as_dict` filters falsy values by default, which would collapse those two
    into the same output for precisely the leg that is behaving.
    """

    def test_a_pass_that_did_nothing_still_names_all_four_legs(self):
        reported = PassCounts().as_dict()

        for leg in LEGS:
            assert leg in reported, (
                f"`{leg}` vanishes from a pass line when it is zero, so "
                "'this leg is fast' cannot be told from 'this leg was never "
                "timed'"
            )
            assert reported[leg] == 0

    def test_a_timed_leg_reports_its_own_number(self):
        counts = PassCounts(leg_walk_ms=2290, leg_price_ms=18400)
        reported = counts.as_dict()

        assert reported["leg_walk_ms"] == 2290
        assert reported["leg_price_ms"] == 18400


class TestTheLegsAreActuallySet:
    """The fields existing is not the same as the code filling them in.

    This is the half a dataclass test cannot reach: `run_kalshi_pass` and
    `run_pricing_pass` must assign each field, or the guard above passes
    against four permanently-zero columns that look like fast legs.
    """

    def test_the_kalshi_pass_assigns_walk_parse_and_store(self):
        import inspect

        from backend import runner

        source = inspect.getsource(runner.run_kalshi_pass)
        for leg in ("leg_walk_ms", "leg_parse_ms", "leg_store_ms"):
            assert f"counts.{leg} =" in source, (
                f"`run_kalshi_pass` no longer records `{leg}`; the column will "
                "read 0 forever and be mistaken for a leg that is not the "
                "problem"
            )

    def test_the_pricing_pass_assigns_its_own_leg(self):
        import inspect

        from backend import runner

        source = inspect.getsource(runner.run_pricing_pass)
        assert "leg_price_ms" in source, (
            "`run_pricing_pass` no longer records `leg_price_ms`; on the "
            "2026-08-19 measurement this was the largest leg of the pass"
        )
