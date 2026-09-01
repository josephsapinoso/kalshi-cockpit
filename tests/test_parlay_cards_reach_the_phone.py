"""Parlay cards push to Discord, once per card, in the desk's own words.

The desk's whole product is three cards, and until now they reached Joe only if
he opened a browser. ADR 0071 settles the tool as a personal betting desk whose
job at the moment of a bet is price transparency -- so putting the cards in the
channel he already watches is the product arriving, not a new feature.

Two properties carry the whole thing:

- **The dedupe key IS the change detection.** `notifications.UNIQUE (kind, key)`
  drops a card whose legs have not moved. There is no timestamp comparison and
  no threshold to tune, and it survives the restart an in-memory policy would
  not.
- **Every number is a string the server already rendered.** The embed does no
  arithmetic, so it cannot drift from the screen.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **That Discord accepts the embed.** `_post` is faked here. Only posting to
  the real webhook proves the wire shape, and that is a human action -- the
  same argument `heartbeat.yml`'s `force_alarm` input makes.
- **That a card is worth buying.** No edge is claimed anywhere in this path,
  and none was measured (ADR 0038). `backend/core/ladder.py`'s own docstring is
  the authority.
- **That the ladder builds good cards.** `tests/test_ladder.py` owns that;
  these tests take a built payload as given.
- **Anything about ordering.** Cards go out in ladder order, which is a shape
  (2-3 legs, 4, 6), not a ranking. ADR 0071 SS2.5 forbids ranking by the gap.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.notify.alerts import (
    MAX_PARLAY_PUSHES_PER_DAY,
    PARLAY_DEBOUNCE_BUILDS,
    Alerter,
    parlay_card_due_ms,
    parlay_key,
)
from backend.notify.discord import (
    COLOUR_OPPORTUNITY, COLOUR_PARLAY, DiscordConfig, DiscordNotifier,
)
from backend.parlays import NOTES
from backend.store import db

NOW = 1_787_680_800_000
DAY_START = NOW - 3_600_000


def _leg(ticker: str, team: str = "Yankees") -> dict:
    return {
        "ticker": ticker,
        "event_ticker": f"EV-{ticker}",
        "event_title": "Yankees at Red Sox",
        "team": team,
        "label": f"{team} win",
        "league": "baseball_mlb",
        "commence_ms": NOW + 3_600_000,
        "market": "h2h",
        "point": None,
        "fair_percent_display": "64.2%",
    }


def _card(key: str = "safe", tickers=("A", "B", "C")) -> dict:
    return {
        "key": key,
        "title": key.title(),
        "legs": [_leg(t) for t in tickers],
        "not_built_reason": None,
        "joint": {
            "conservative_percent_display": "26.5%",
            "method_range_display": "24.1%–29.8%",
            "fair_cost_display": "26.5c",
            "correlation_note": "Same-night games move together a little.",
        },
        "at_stakes": [
            {
                "stake_cents": 500, "stake_display": "$5.00",
                "contracts_display": "~18.9", "payout_display": "$18.87",
                "is_default": True,
            },
        ],
    }


def _unbuilt(key: str = "lottery") -> dict:
    return {
        "key": key, "title": key.title(), "legs": [],
        "not_built_reason": "needs 6 fresh games and the slate has 2",
        "joint": None, "at_stakes": [],
    }


def _ladder(*cards) -> dict:
    return {"generated_ms": NOW, "cards": list(cards), "excluded": {},
            "notes": dict(NOTES)}


def _ms(year: int, month: int, day: int, hour: int, minute: int = 0) -> int:
    return int(
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        .timestamp() * 1000
    )


def _at(hour: int, minute: int = 0) -> int:
    """A wall-clock instant on the same UTC date as `NOW` (2026-08-25)."""
    return _ms(2026, 8, 25, hour, minute)


#: The card hour these tests run under **unless one names its own**.
#:
#: `NOW` is 18:00Z and `DAY_START` is 17:00Z, so an hour of 9 puts the
#: scheduled card at 09:00Z *tomorrow* -- fifteen hours out, past the widest
#: span any test below advances through. Every test in this file that is about
#: the change channel therefore runs with the scheduled channel provably
#: dormant, rather than with a hour chosen to be merely unlikely.
CARD_HOUR = 9


async def _push(alerter, ladder, *, now_ms: int = NOW,
                day_start_ms: int = DAY_START, hour: int = CARD_HOUR):
    """One ladder build."""
    return await alerter.parlay_cards(
        ladder, now_ms=now_ms, day_start_ms=day_start_ms, card_hour_utc=hour,
    )


async def _settle(alerter, ladder, *, now_ms: int = NOW,
                  day_start_ms: int = DAY_START, hour: int = CARD_HOUR):
    """Present one ladder for `PARLAY_DEBOUNCE_BUILDS` consecutive builds.

    Returns the LAST result, which is the one a send lands in. Written against
    the constant rather than hard-coded to two calls, so raising the debounce
    does not silently turn every caller below into a test of a held card.
    """
    for i in range(PARLAY_DEBOUNCE_BUILDS):
        result = await _push(
            alerter, ladder, now_ms=now_ms + i, day_start_ms=day_start_ms,
            hour=hour,
        )
    return result


@pytest.fixture()
def conn(tmp_path):
    c = db.init_db(tmp_path / "parlay_alerts.db")
    yield c
    c.close()


class FakeNotifier:
    """Records embeds instead of posting them."""

    enabled = True

    def __init__(self, *, deliver: bool = True):
        self.posted: list[dict] = []
        self._deliver = deliver

    async def parlay_card(self, card, *, notes):
        self.posted.append({"card": card, "notes": notes})
        return self._deliver


class TestTheKeyIsTheCardsIdentity:
    """This is the claim the whole feature rests on."""

    def test_the_same_legs_in_a_different_order_are_the_same_card(self):
        """Mutation observed red: drop `sorted(...)` in `parlay_key`.

        `build_ladder` orders legs by `(-p_conservative, ...)`, so two
        probabilities crossing between passes reorders the same set -- and an
        order-sensitive key would push the same parlay again.
        """
        assert parlay_key(_card(tickers=("A", "B", "C"))) == parlay_key(
            _card(tickers=("C", "A", "B"))
        )

    def test_a_changed_leg_is_a_different_card(self):
        assert parlay_key(_card(tickers=("A", "B", "C"))) != parlay_key(
            _card(tickers=("A", "B", "D"))
        )

    def test_the_same_legs_at_a_different_rung_are_different_cards(self):
        """Mutation observed red: drop `card.get('key')` from the key.

        The same legs as a Safe and as a Middle are different suggestions.
        """
        assert parlay_key(_card("safe", ("A", "B"))) != parlay_key(
            _card("middle", ("A", "B"))
        )

    def test_a_card_with_no_legs_has_no_identity(self):
        """`"safe:"` would make every empty card the same card forever."""
        assert parlay_key({"key": "safe", "legs": []}) is None

    def test_a_leg_missing_its_ticker_does_not_become_an_empty_slot(self):
        key = parlay_key({"key": "safe", "legs": [_leg("A"), {"ticker": None}]})
        assert key == "safe:A"


class TestOneCardIsAnnouncedOnce:
    async def test_a_built_card_that_holds_still_is_sent(self, conn):
        notifier = FakeNotifier()
        result = await _settle(Alerter(conn, notifier), _ladder(_card()))
        assert result.sent == ("safe",)
        assert len(notifier.posted) == 1

    async def test_the_same_card_on_the_next_pass_is_not_resent(self, conn):
        """Mutation observed red: give `parlay_cards` a key of `str(now_ms)`.

        This is what makes it safe to ask on every pass. Without it a card
        would be pushed every fifteen seconds for as long as its legs held --
        and note the debounce does NOT provide this, because a composition that
        holds still keeps clearing the debounce on every later build. The
        `notifications` claim is still the thing that stops a re-push.
        """
        alerter = Alerter(conn, FakeNotifier())
        await _settle(alerter, _ladder(_card()))
        again = await _push(alerter, _ladder(_card()), now_ms=NOW + 15_000)
        assert again.sent == ()
        assert again.skipped == ("safe",)

    async def test_a_price_move_alone_does_not_resend(self, conn):
        """The legs are the card. A re-quote of the same six legs is the same
        suggestion, and a phone that buzzes for a tenth of a cent gets muted."""
        alerter = Alerter(conn, FakeNotifier())
        await _settle(alerter, _ladder(_card()))
        moved = _card()
        moved["joint"]["conservative_percent_display"] = "27.9%"
        moved["legs"][0]["fair_percent_display"] = "66.0%"
        assert (await _push(
            alerter, _ladder(moved), now_ms=NOW + 15_000
        )).sent == ()

    async def test_a_changed_leg_is_announced_once_it_has_held(self, conn):
        """The material-change trigger. It needs no separate key machinery --
        only the debounce, which is what stops it firing on a composition that
        exists because one sport happened to be swept last."""
        alerter = Alerter(conn, FakeNotifier())
        await _settle(alerter, _ladder(_card()))
        fresh = await _settle(
            alerter, _ladder(_card(tickers=("A", "B", "D"))),
            now_ms=NOW + 900_000,
        )
        assert fresh.sent == ("safe",)

    async def test_an_unbuilt_card_says_nothing(self, conn):
        """A push saying "nothing tonight" is a notification with no action."""
        notifier = FakeNotifier()
        result = await _settle(Alerter(conn, notifier), _ladder(_unbuilt()))
        assert result.sent == ()
        assert result.held == ()
        assert notifier.posted == []

    async def test_a_screen_only_cut_never_reaches_the_phone(self, conn):
        """Longshot / Next 3 hours / Agreed shipped 2026-08-26 as SCREEN
        cards. Six cards against the day's ceiling would make one ladder the
        whole day's pushes, and the day they shipped the existing three already
        burned the ceiling in four minutes.

        Neither sent nor skipped nor held: it was never a candidate, and
        counting it under any of the three would report a decision that was
        never taken about it."""
        notifier = FakeNotifier()
        result = await _settle(
            Alerter(conn, notifier),
            _ladder(
                _card("safe", ("A", "B")),
                _card("longshot", ("C", "D")),
                _card("soon", ("E", "F")),
                _card("agreed", ("G", "H")),
            ),
        )
        assert result.sent == ("safe",)
        assert result.skipped == ()
        assert result.held == ()
        assert [p["card"]["key"] for p in notifier.posted] == ["safe"]

    async def test_a_screen_only_cut_is_not_even_tracked(self, conn):
        """Mutation observed red: move `_observe_candidate` above the
        `PUSHED_CARD_KEYS` filter.

        A slot that cannot be pushed has no run worth counting, and a key
        promoted into `PUSHED_CARD_KEYS` later must start from zero rather than
        inherit a run it never earned.
        """
        await _settle(
            Alerter(conn, FakeNotifier()),
            _ladder(_card("safe", ("A", "B")), _card("longshot", ("C", "D"))),
        )
        tracked = {
            r["card_key"] for r in conn.execute(
                "SELECT card_key FROM parlay_card_candidates"
            )
        }
        assert tracked == {"safe"}

    async def test_the_pushed_set_is_a_subset_of_the_registered_cards(self):
        """A key that leaves `CARD_SHAPES` must not linger here as a
        permission to push a card that no longer exists."""
        from backend.core.ladder import CARD_SHAPES
        from backend.notify.alerts import PUSHED_CARD_KEYS

        assert PUSHED_CARD_KEYS <= {r.key for r in CARD_SHAPES}
        assert PUSHED_CARD_KEYS != {r.key for r in CARD_SHAPES}

    async def test_every_rung_gets_its_own_notification(self, conn):
        notifier = FakeNotifier()
        result = await _settle(
            Alerter(conn, notifier),
            _ladder(
                _card("safe", ("A", "B")),
                _card("middle", ("A", "B", "C", "D")),
            ),
        )
        assert result.sent == ("safe", "middle")

    async def test_a_failed_delivery_is_recorded_as_failed(self, conn):
        result = await _settle(
            Alerter(conn, FakeNotifier(deliver=False)), _ladder(_card())
        )
        assert result.failed == ("safe",)
        row = conn.execute(
            "SELECT delivered FROM notifications WHERE kind = 'parlay_card'"
        ).fetchone()
        assert row["delivered"] == 0, (
            "'we decided to alert' and 'the alert arrived' are different facts"
        )

    async def test_no_notifier_sends_nothing_and_does_not_raise(self, conn):
        """Alerting is optional infrastructure; the recorder is not."""
        result = await _settle(Alerter(conn, None), _ladder(_card()))
        assert result.sent == ()

    async def test_a_disabled_notifier_writes_no_candidate_row(self, conn):
        """Mutation observed red: move the `self.enabled` guard below the loop.

        With no notifier there is no channel, so there is no run to count. A
        debounce advanced while the alerter is disabled would let the first
        build after a webhook is configured push immediately -- which is the
        state this whole mechanism exists to refuse.
        """
        await _settle(Alerter(conn, None), _ladder(_card()))
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM parlay_card_candidates"
        ).fetchone()["n"] == 0


class TestTheDebounceHoldsACompositionThatIsStillChurning:
    """The reason this exists, measured on live 2026-08-26.

        22:41:43Z  safe: LADATL-LAD | BOSMIA-BOS | MILNYM-MIL   (all MLB)
        22:45:10Z  safe: CHICONN-CHI | PDXDAL-DAL | GSCONN-GS   (all WNBA)

    The card swapped sport entirely and all three rungs re-pushed, four minutes
    apart, spending the day's whole ceiling. Both pushes were *correct* under
    the dedupe rule: sports are swept on independent clocks, `build_ladder`
    drops legs past `MAX_ODDS_AGE_S`, and ranking is by probability -- so
    whichever sport is currently fresh owns the top of every card.
    """

    async def test_a_first_sighting_is_held_rather_than_pushed(self, conn):
        notifier = FakeNotifier()
        result = await _push(Alerter(conn, notifier), _ladder(_card()))
        assert result.held == ("safe",)
        assert result.sent == ()
        assert notifier.posted == []

    async def test_held_is_not_deduped(self, conn):
        """A held card was a genuine candidate that was NOT deduped -- nothing
        about it had been sent. Filing it under `alerts_deduped` would say the
        dedupe was working when what was working is the debounce, and the two
        have opposite remedies: a stuck `skipped` means the ladder is rebuilding
        identically, a stuck `held` means it is churning."""
        result = await _push(Alerter(conn, FakeNotifier()), _ladder(_card()))
        assert result.skipped == ()
        assert "alerts_held" in result.as_dict()
        assert result.as_dict()["alerts_deduped"] == []

    async def test_two_alternating_compositions_never_push(self, conn):
        """Mutation observed red: accumulate `builds` instead of replacing the
        row on a different key.

        This is the live failure, run twelve times. Under a counter that only
        went up, each composition would reach two on its second sighting and
        both would announce -- which is precisely the pattern being suppressed.
        """
        alerter = Alerter(conn, FakeNotifier())
        mlb = _ladder(_card(tickers=("LAD", "BOS", "MIL")))
        wnba = _ladder(_card(tickers=("CHI", "PDX", "GS")))
        sent = 0
        for n in range(12):
            result = await _push(
                alerter, mlb if n % 2 == 0 else wnba,
                now_ms=NOW + n * 900_000,
            )
            sent += len(result.sent)
        assert sent == 0, "an alternating composition announced itself"

    async def test_a_composition_that_settles_does_push(self, conn):
        """The other half, so the test above cannot be satisfied by a debounce
        that never releases anything."""
        alerter = Alerter(conn, FakeNotifier())
        mlb = _ladder(_card(tickers=("LAD", "BOS", "MIL")))
        wnba = _ladder(_card(tickers=("CHI", "PDX", "GS")))
        await _push(alerter, mlb, now_ms=NOW)
        await _push(alerter, wnba, now_ms=NOW + 900_000)
        first = await _push(alerter, mlb, now_ms=NOW + 1_800_000)
        second = await _push(alerter, mlb, now_ms=NOW + 2_700_000)
        assert first.sent == () and first.held == ("safe",)
        assert second.sent == ("safe",)

    async def test_a_composition_that_vanishes_starts_over(self, conn):
        """Mutation observed red: return early on `key is None` without
        deleting the row.

        Appear, vanish, reappear is not two consecutive builds. Leaving the row
        would let a composition that the ladder could not build in between
        claim a run it does not have -- and an unbuildable slate is exactly
        when the pool is churning hardest.
        """
        alerter = Alerter(conn, FakeNotifier())
        card = _ladder(_card(tickers=("LAD", "BOS", "MIL")))
        await _push(alerter, card, now_ms=NOW)
        await _push(alerter, _ladder(_unbuilt("safe")), now_ms=NOW + 900_000)
        again = await _push(alerter, card, now_ms=NOW + 1_800_000)
        assert again.sent == ()
        assert again.held == ("safe",)

    async def test_the_run_survives_a_restart(self, conn):
        """A dict on the Alerter would forget on every deploy, and a deploy is
        exactly when the pool churns -- which is how the live failure was found
        in the first place. `notifications`' own argument, applied again."""
        card = _ladder(_card())
        await _push(Alerter(conn, FakeNotifier()), card)
        reborn = Alerter(conn, FakeNotifier())
        assert (await _push(reborn, card, now_ms=NOW + 900_000)).sent == (
            "safe",
        )

    async def test_the_run_is_keyed_on_the_whole_composition(self, conn):
        """Mutation observed red: store `legs[0]["ticker"]` instead of
        `parlay_key(card)`.

        Two cuts routinely agree on the leading leg and diverge below it -- the
        exact hole found once already on `_joint_key`. A run keyed on the first
        ticker would let a card whose tail changed every build announce itself
        as though it had held still.
        """
        alerter = Alerter(conn, FakeNotifier())
        for n in range(6):
            result = await _push(
                alerter,
                _ladder(_card(tickers=("LEAD", "B", f"TAIL{n}"))),
                now_ms=NOW + n * 900_000,
            )
            assert result.sent == (), (
                "a card whose tail changed on every build was announced"
            )

    async def test_the_debounce_is_two_and_the_constant_is_what_decides(self):
        """Vacuity guard. Every test above is written against the value 2; if
        the constant moves, they are measuring something else and must be
        rewritten rather than left passing."""
        assert PARLAY_DEBOUNCE_BUILDS == 2


class TestTheScheduledCardLandsAtItsHour:
    """Joe's trigger #1, taken literally. Immune to churn by construction
    rather than by policy: whatever the ladder says at the stated hour is the
    day's card."""

    async def test_it_is_not_pushed_before_its_hour(self, conn):
        result = await _push(
            Alerter(conn, FakeNotifier()), _ladder(_card()),
            now_ms=_at(19, 59), hour=20,
        )
        assert result.sent == ()
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM notifications WHERE kind = 'parlay_daily'"
        ).fetchone()["n"] == 0

    async def test_it_is_pushed_on_the_first_build_at_its_hour(self, conn):
        notifier = FakeNotifier()
        result = await _push(
            Alerter(conn, notifier), _ladder(_card()),
            now_ms=_at(20, 0), hour=20,
        )
        assert result.sent == ("safe",)
        assert len(notifier.posted) == 1

    async def test_it_is_not_debounced(self, conn):
        """Mutation observed red: move the `builds < PARLAY_DEBOUNCE_BUILDS`
        check above the scheduled block.

        A debounce could delay or skip the one push that is supposed to be
        guaranteed, and Joe picked the hour on the basis that the card would be
        there. This is the FIRST sighting of this composition and it still
        goes.
        """
        result = await _push(
            Alerter(conn, FakeNotifier()), _ladder(_card()),
            now_ms=_at(20, 1), hour=20,
        )
        assert result.sent == ("safe",)
        assert result.held == ()

    async def test_it_goes_once_a_day_however_many_builds_follow(self, conn):
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        for minute in range(0, 60, 10):
            await _push(
                alerter, _ladder(_card()), now_ms=_at(20, minute), hour=20
            )
        assert len(notifier.posted) == 1

    async def test_it_returns_the_next_budget_day(self, conn):
        alerter = Alerter(conn, FakeNotifier())
        first = await _push(
            alerter, _ladder(_card()), now_ms=_at(20, 0), hour=20
        )
        second = await _push(
            alerter, _ladder(_card()),
            now_ms=_at(20, 0) + 86_400_000,
            day_start_ms=DAY_START + 86_400_000, hour=20,
        )
        assert first.sent == ("safe",) and second.sent == ("safe",)

    async def test_it_does_not_spend_the_change_ceiling(self, conn):
        """It cannot run away -- its own key bounds it at one per rung per day
        -- so it is counted under its own `kind` and not against the ceiling
        that exists to bound churn.

        This asserts the LEDGER only. On its own it is not the guard: the test
        below is, and this one was observed GREEN under the mutation that test
        catches. Kept because the two facts are different and both are true.
        """
        alerter = Alerter(conn, FakeNotifier())
        await _push(alerter, _ladder(_card()), now_ms=_at(20, 0), hour=20)
        assert alerter._parlay_pushes_today(day_start_ms=DAY_START) == 0

    async def test_the_guaranteed_card_does_not_silence_the_days_alerts(
        self, conn
    ):
        """Mutation observed red: increment `pushed_today` after a scheduled
        send.

        Joe chose "keep 6 at the worst" on the understanding that the two
        channels are counted separately. A scheduled push that spent the change
        budget would make the guaranteed card a mute button for the rest of the
        ladder in the same build.

        **The fixture is intricate because the interaction is narrow**, and
        that is worth stating rather than hiding: the two channels only meet
        inside a single call in which one rung takes the scheduled branch while
        another has already had its scheduled push and falls through with a
        settled, changed composition. `safe` is the late arrival here for a
        reason -- cards are processed in ladder order, so the scheduled send
        has to come BEFORE the fall-throughs for its counter to reach them.
        """
        alerter = Alerter(conn, FakeNotifier())

        # Two change alerts earlier in the day: room for exactly one more.
        for n in range(MAX_PARLAY_PUSHES_PER_DAY - 1):
            await _settle(
                alerter, _ladder(_card("middle", (f"E{n}", "X", "Y", "Z"))),
                now_ms=_at(18, n), hour=20,
            )
        assert alerter._parlay_pushes_today(day_start_ms=DAY_START) == (
            MAX_PARLAY_PUSHES_PER_DAY - 1
        )

        # `middle` and `lottery` take their scheduled cards at the hour; their
        # compositions then change and settle. `safe` is not built until later.
        await _push(
            alerter,
            _ladder(
                _card("middle", ("C", "D", "E", "F")),
                _card("lottery", ("G", "H", "I", "J", "K", "L")),
            ),
            now_ms=_at(20, 0), hour=20,
        )
        moved = (
            _card("middle", ("M", "N", "O", "P")),
            _card("lottery", ("Q", "R", "S", "T", "U", "V")),
        )
        await _push(alerter, _ladder(*moved), now_ms=_at(20, 1), hour=20)

        # One call: `safe` sends its scheduled card, then two settled
        # compositions ask the change channel with one slot left.
        result = await _push(
            alerter, _ladder(_card("safe", ("A", "B")), *moved),
            now_ms=_at(20, 2), hour=20,
        )
        assert result.sent == ("safe", "middle"), (
            "the scheduled card spent the change budget and silenced a "
            "settled composition"
        )
        assert result.skipped == ("lottery",)

    async def test_the_scheduled_push_burns_the_change_key_too(self, conn):
        """Mutation observed red: drop the `_claim(PARLAY_CHANGE_KIND, ...)`
        after a scheduled send.

        The two channels have different `kind`s, so `UNIQUE (kind, key)` does
        not see across them. Without this the card sent at 20:00Z is announced
        again by the change channel as soon as it has held two builds, having
        changed nothing at all -- the split would double every card it was
        built to de-duplicate.
        """
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        await _push(alerter, _ladder(_card()), now_ms=_at(20, 0), hour=20)
        for minute in (10, 20, 30):
            await _push(
                alerter, _ladder(_card()), now_ms=_at(20, minute), hour=20
            )
        assert len(notifier.posted) == 1

    async def test_a_composition_that_changes_after_the_card_still_alerts(
        self, conn
    ):
        """The other half. The scheduled card must not become a mute button for
        the rest of the day -- a genuinely different, settled composition is
        still worth saying."""
        alerter = Alerter(conn, FakeNotifier())
        await _push(alerter, _ladder(_card()), now_ms=_at(20, 0), hour=20)
        moved = _ladder(_card(tickers=("X", "Y", "Z")))
        await _push(alerter, moved, now_ms=_at(20, 10), hour=20)
        later = await _push(alerter, moved, now_ms=_at(20, 20), hour=20)
        assert later.sent == ("safe",)

    async def test_an_hour_earlier_than_the_day_start_is_tomorrows(self):
        """`day_start.replace(hour=...)` is only right while the card hour is
        later in the clock than the budget day's start. The budget day begins at
        10:00Z, so a card configured for 05:00Z belongs to the NEXT calendar
        date -- a plain `replace` would put it seventeen hours in the past and
        fire it instantly at the day roll.

        Mutation observed red: drop the `if due < start` branch.
        """
        day_start = _ms(2026, 8, 26, 10)
        assert parlay_card_due_ms(day_start, 5) == _ms(2026, 8, 27, 5)
        assert parlay_card_due_ms(day_start, 20) == _ms(2026, 8, 26, 20)
        assert parlay_card_due_ms(day_start, 10) == day_start


class TestTheBurnIsNotAFailedDelivery:
    """The scheduled card's channel-burn must not read as an undelivered push.

    ADR 0076 claims `PARLAY_CHANGE_KIND` for the composition the scheduled card
    just sent, with no send behind it, so one card cannot buzz twice. That row
    is `delivered = 0` forever -- which is also exactly what a process that
    died between claiming and sending leaves behind, and that second case is
    the one ADR 0049 built `undelivered_last_24h` to catch.

    Measured on live 2026-08-27: `/api/health` read `undelivered_last_24h: 5`
    with **no failed delivery anywhere in the window**. Three burns a day is a
    permanent alarm, and `test_an_old_failure_falls_out_of_the_24h_count` in
    `test_alerts.py` says why that matters -- one bad night must not read as a
    permanently broken alerter.
    """

    async def test_a_burn_is_not_counted_as_undelivered(self, conn):
        """Mutation observed red: drop `suppressed=True` at the burn site."""
        alerter = Alerter(conn, FakeNotifier())
        await _push(alerter, _ladder(_card()), now_ms=_at(20, 0), hour=20)

        burns = conn.execute(
            "SELECT COUNT(*) AS n FROM notifications "
            "WHERE kind = 'parlay_card' AND suppressed = 1"
        ).fetchone()["n"]
        assert burns == 1, "the burn must exist, or this asserts nothing"

        health = alerter.delivery_health(now_ms=_at(20, 1))
        assert health["undelivered_last_24h"] == 0
        assert health["suppressed_last_24h"] == 1

    async def test_a_real_failure_is_still_counted_beside_a_burn(self, conn):
        """The discriminating case, and one call produces both rows.

        A scheduled card whose delivery FAILS still burns the change key --
        deliberately, so a change alert cannot re-send what the card could not
        deliver. So this single push writes one genuine failure (`parlay_daily`,
        attempted and refused) and one deliberate claim (`parlay_card`, never
        attempted). They must be counted apart.

        Mutation observed red: drop `suppressed=True` and `undelivered` reads 2.
        """
        alerter = Alerter(conn, FakeNotifier(deliver=False))
        result = await _push(
            alerter, _ladder(_card()), now_ms=_at(20, 0), hour=20
        )
        assert result.failed == ("safe",)

        health = alerter.delivery_health(now_ms=_at(20, 1))
        assert health["undelivered_last_24h"] == 1, "the daily card really failed"
        assert health["suppressed_last_24h"] == 1, "the burn really was deliberate"
        assert health["last_delivered_ms"] is None

    async def test_a_burn_still_blocks_the_change_channel(self, conn):
        """The behaviour the row exists for, asserted rather than its record.

        Marking the row `suppressed` must not weaken what it does. After the
        scheduled card goes, the change channel may not re-announce the same
        composition however many builds follow -- which is the property, where
        the count above is only its trace.
        """
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        await _push(alerter, _ladder(_card()), now_ms=_at(20, 0), hour=20)
        assert len(notifier.posted) == 1

        for i in range(PARLAY_DEBOUNCE_BUILDS + 2):
            await _push(
                alerter, _ladder(_card()), now_ms=_at(20, 10 + i), hour=20
            )
        assert len(notifier.posted) == 1, "the same composition buzzed twice"


class TestTheDayHasACeiling:
    """The dedupe key alone is not a ceiling, and this is why.

    `ladder_candidates` takes pre-game fixtures only, so **every kickoff drops
    a game out of the pool**. If that game was in a card, the leg set changes,
    the key changes, and the card is legitimately new by the dedupe rule. On a
    14-fixture MLB night that is up to fourteen correct pushes per rung and a
    phone nobody leaves un-muted.

    The debounce does not replace this. A game commencing is a *real* change
    that a composition then holds through, so every one of these clears the
    debounce on its second build.
    """

    async def test_a_night_of_kickoffs_cannot_push_forever(self, conn):
        """Mutation observed red: remove the `MAX_PARLAY_PUSHES_PER_DAY` check.

        Each iteration is a genuinely different leg set, exactly as a game
        starting produces, and each is presented twice so the debounce is not
        what is doing the work. Without a ceiling every one of them sends.
        """
        alerter = Alerter(conn, FakeNotifier())
        sent = 0
        for n in range(14):
            result = await _settle(
                alerter,
                _ladder(_card(tickers=(f"G{n}", f"G{n + 1}", f"G{n + 2}"))),
                now_ms=NOW + n * 60_000,
            )
            sent += len(result.sent)
        assert sent == MAX_PARLAY_PUSHES_PER_DAY

    async def test_the_ceiling_resets_on_the_next_budget_day(self, conn):
        alerter = Alerter(conn, FakeNotifier())
        for n in range(MAX_PARLAY_PUSHES_PER_DAY):
            await _settle(
                alerter, _ladder(_card(tickers=(f"G{n}", "X", "Y"))),
                now_ms=NOW + n * 1000,
            )
        tomorrow = NOW + 86_400_000
        result = await _settle(
            alerter, _ladder(_card(tickers=("P", "Q", "R"))),
            now_ms=tomorrow, day_start_ms=DAY_START + 86_400_000,
        )
        assert result.sent == ("safe",)

    async def test_an_undelivered_push_does_not_burn_the_ceiling(self, conn):
        """Mutation observed red: drop `delivered = 1` from the count.

        A push Discord rejected did not reach the phone. Charging it against a
        ceiling that exists to protect the phone would let one outage silence
        the rest of the day.
        """
        alerter = Alerter(conn, FakeNotifier(deliver=False))
        for n in range(MAX_PARLAY_PUSHES_PER_DAY + 2):
            await _settle(
                alerter, _ladder(_card(tickers=(f"G{n}", "X", "Y"))),
                now_ms=NOW + n * 1000,
            )
        assert alerter._parlay_pushes_today(day_start_ms=DAY_START) == 0

    async def test_one_ladder_cannot_all_pass_a_ceiling_with_room_for_one(
        self, conn
    ):
        """Three rungs in one ladder share ONE day's budget.

        **Mutation observed red: remove the ceiling check.** The mutation this
        docstring used to name -- re-query the count per card instead of
        incrementing locally -- was run and observed **GREEN**, because `_send`
        commits before returning, so a re-query sees exactly what the increment
        counted. The claim was wrong and the note is kept rather than quietly
        deleted: the local increment is an optimisation, and what makes the
        budget shared is that the count is committed.
        """
        alerter = Alerter(conn, FakeNotifier())
        for n in range(MAX_PARLAY_PUSHES_PER_DAY - 1):
            await _settle(
                alerter, _ladder(_card(tickers=(f"G{n}", "X", "Y"))),
                now_ms=NOW + n * 1000,
            )
        ladder = _ladder(
            _card("safe", ("P", "Q")),
            _card("middle", ("P", "Q", "R", "S")),
            _card("lottery", ("P", "Q", "R", "S", "T", "U")),
        )
        result = await _settle(alerter, ladder, now_ms=NOW + 999_000)
        assert len(result.sent) == 1, (
            "the ladder spent more of the day's budget than was left"
        )
        assert result.skipped == ("middle", "lottery")

    async def test_the_two_channels_sum_to_the_total_joe_chose(self):
        """Joe was asked how many pushes a day at the worst and said keep 6.

        The scheduled card is bounded by construction at one per pushed rung;
        the change channel is bounded by the constant. This asserts the sum,
        because that is the number he answered -- a change to either half that
        leaves the total alone is fine, and one that moves it is his decision
        and not a refactor.
        """
        from backend.notify.alerts import PUSHED_CARD_KEYS

        assert len(PUSHED_CARD_KEYS) + MAX_PARLAY_PUSHES_PER_DAY == 6


class TestTheEmbedRepeatsTheDeskRatherThanRecomputingIt:
    @staticmethod
    def _notifier():
        posted: list[dict] = []
        n = DiscordNotifier(
            DiscordConfig(
                cockpit_base_url="https://kalshi-cockpit.fly.dev",
                webhook_url="https://discord.com/api/webhooks/x/y",
            )
        )
        n._post = lambda embed: _record(posted, embed)  # type: ignore[method-assign]
        return n, posted

    async def test_the_four_caveats_travel_verbatim(self):
        """Mutation observed red: drop `notes.get("unquoted")` from the footer.

        Two of these are the difference between a number and money: the cost is
        FAIR value and not a quote, and the market is *unquoted* -- ADR 0085's
        upgrade of ADR 0012 §5's "enter-only", because the 2026-08-30 census
        found the entry side missing too.

        This assertion was already sourced from `NOTES` rather than retyped,
        so the rename reached it by construction. That is the shape the other
        two caveat tests have now been converted to.
        """
        notifier, posted = self._notifier()
        await notifier.parlay_card(_card(), notes=dict(NOTES))
        embed = posted[0]
        assert NOTES["fair_value"] in embed["footer"]["text"]
        assert NOTES["unquoted"] in embed["footer"]["text"]
        assert NOTES["fee"] in embed["footer"]["text"]
        assert NOTES["chance"] in embed["description"]

    async def test_every_number_on_it_is_a_string_the_payload_carried(self):
        """The no-arithmetic rule. Mutation observed red: render the joint as
        `f"{joint * 100:.1f}%"` from a float instead of reading the display
        string -- the embed and the screen then disagree by a rounding step."""
        notifier, posted = self._notifier()
        card = _card()
        await notifier.parlay_card(card, notes=dict(NOTES))
        rendered = str(posted[0])
        for shown in (
            card["joint"]["conservative_percent_display"],
            card["joint"]["method_range_display"],
            card["joint"]["fair_cost_display"],
            card["at_stakes"][0]["payout_display"],
            card["legs"][0]["fair_percent_display"],
        ):
            assert shown in rendered, f"{shown!r} was recomputed, not repeated"

    async def test_it_carries_no_edge_and_no_recommendation(self):
        """ADR 0038 closed the hunt; ADR 0071 makes the job transparency.

        Asserted over the field NAMES and the title, not over the whole embed:
        `NOTES["chance"]` contains the words "not an edge", which is the
        disclaimer and must survive. A blanket substring ban would delete the
        sentence that does the work -- it caught exactly that when first
        written.
        """
        notifier, posted = self._notifier()
        await notifier.parlay_card(_card(), notes=dict(NOTES))
        embed = posted[0]
        claims = " ".join(
            [embed["title"]] + [f["name"] for f in embed["fields"]]
        ).lower()
        for forbidden in ("edge", "ev", "expected", "recommend", "value bet"):
            assert forbidden not in claims.split(), (
                f"a field is labelled {forbidden!r}; this embed states fair "
                f"value and claims nothing"
            )

    async def test_the_disclaimer_that_it_is_not_an_edge_survives(self):
        """The other half, so the test above cannot be satisfied by deleting
        the sentence rather than by not claiming an edge."""
        notifier, posted = self._notifier()
        await notifier.parlay_card(_card(), notes=dict(NOTES))
        assert "not an edge" in posted[0]["description"]

    async def test_it_is_not_coloured_as_an_opportunity(self):
        """Green is this palette's "we found something", which this is not."""
        notifier, posted = self._notifier()
        await notifier.parlay_card(_card(), notes=dict(NOTES))
        assert posted[0]["color"] == COLOUR_PARLAY
        assert COLOUR_PARLAY != COLOUR_OPPORTUNITY

    async def test_every_leg_is_identifiable(self):
        """A leg you cannot identify is one you cannot check: the side taken
        AND the fixture, because "Yankees" does not say against whom."""
        notifier, posted = self._notifier()
        await notifier.parlay_card(_card(), notes=dict(NOTES))
        rendered = str(posted[0])
        assert "Yankees win" in rendered
        assert "Yankees at Red Sox" in rendered

    async def test_it_links_to_the_cockpit_and_carries_no_button(self):
        """Same ruling as `opportunity`: no tap-to-buy in a chat client."""
        notifier, posted = self._notifier()
        await notifier.parlay_card(_card(), notes=dict(NOTES))
        assert posted[0]["url"] == "https://kalshi-cockpit.fly.dev/parlays"
        assert "components" not in posted[0]

    async def test_an_unbuilt_card_is_refused_at_the_transport_too(self):
        """Belt and braces: `Alerter` filters these, and so does this. Neither
        alone is a guarantee that a "nothing tonight" push cannot happen."""
        notifier, posted = self._notifier()
        sent = await notifier.parlay_card(
            {"key": "lottery", "title": "Lottery", "legs": [],
             "not_built_reason": "needs 6 fresh games", "joint": None,
             "at_stakes": []},
            notes=dict(NOTES),
        )
        assert sent is False
        assert posted == []

    async def test_an_unconfigured_notifier_refuses_rather_than_raising(self):
        assert await DiscordNotifier(None).parlay_card(
            _card(), notes=dict(NOTES)
        ) is False


async def _record(bucket: list, embed: dict) -> bool:
    bucket.append(embed)
    return True


class TestTheLoopAsksOnEveryPass:
    """Source-pinned: `run_loop.main()` has no caller but `__main__`."""

    @staticmethod
    def _source() -> str:
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        return (root / "scripts" / "run_loop.py").read_text(encoding="utf-8")

    def test_the_loop_pushes_parlay_cards(self):
        assert "alerter.parlay_cards(" in self._source()

    @classmethod
    def _gate_line(cls) -> str:
        """The `if` that decides whether the ladder is built this pass."""
        source = cls._source()
        call = source.index("alerter.parlay_cards(")
        gate = source.rindex("if alerter.enabled", 0, call)
        return source[gate:source.index("\n", gate)].strip()

    def test_the_gate_is_where_this_test_expects_it(self):
        """Vacuity guard. Both assertions below read one line; if the wiring
        moves, they must fail loudly rather than pass over the wrong text."""
        assert self._gate_line().endswith(":")

    def test_it_is_not_gated_behind_a_full_pass_alone(self):
        """Mutation observed red: change the gate to `kind == "full"` only.

        A full pass is every 900s. A sweep is what changes a fair value, and it
        can land on a quote pass -- waiting for the next full pass would sit on
        a newly-buildable card for up to a quarter of an hour.
        """
        assert "counts.odds_sweeps > 0" in self._gate_line()

    def test_it_does_not_rebuild_the_ladder_on_every_pass(self):
        """Mutation observed red: gate on `alerter.enabled` alone.

        `build_ladder` runs a 200,000-sample copula five times per card
        (~400ms for three cards on a laptop; this VM is shared-cpu-1x), against
        a quote pass budgeted 8s that already runs ~4.2s on live. Between
        sweeps the ladder rebuilds byte-identically, so the cost would buy a
        notification the dedupe then discards.
        """
        assert self._gate_line() != "if alerter.enabled:", (
            "the ladder is rebuilt on every pass, including the 15s quote "
            "cadence, for a result that cannot have changed since the last "
            "sweep"
        )

    def test_it_reads_the_same_staleness_limit_the_screen_does(self):
        """A push built on a looser limit than `/api/parlays` would announce a
        card the screen refuses to show.

        **Repointed 2026-08-28, not loosened.** This read the 600 characters
        *after* `alerter.parlay_cards(`, which held the whole
        `build_ladder_payload(...)` call while it was written inline as that
        call's first argument. Binding the payload to a name -- so the pass
        line can report its `excluded` tally -- moved the limit above the call
        and the probe stopped seeing it. The region now runs from the gate to
        the push, which is the span the claim was always about: one pass, one
        limit, feeding one notification.
        """
        source = self._source()
        call = source.index("alerter.parlay_cards(")
        gate = source.rindex("if alerter.enabled", 0, call)
        region = source[gate:call + 300]

        # Vacuity guards. Each of the three anchors must be inside the region,
        # or the assertion below is reading text that has nothing to do with
        # the push.
        assert "build_ladder_payload(" in region, (
            "the ladder is no longer built inside the block that pushes it; "
            "this probe is reading the wrong span"
        )
        assert "alerter.parlay_cards(" in region

        assert "max_odds_age_ms=staleness.max_odds_age_s * 1000" in region


class TestTheCardHourIsSpelledTheSameEverywhere:
    """Three files name this hour. A comment nobody reads cannot be wrong, so
    it was wrong for the life of the project -- `FAILURE_KINDS` above carries
    the same lesson, and `assert_risk_day_start_agrees` is the same guard for
    the budget day.

    Live sets the variable explicitly, so on live the code default is inert:
    drift would mean `.env.example` documenting an hour the deployed card does
    not use, which is the failure mode, not a cosmetic one.
    """

    @staticmethod
    def _root():
        from pathlib import Path
        return Path(__file__).resolve().parents[1]

    def test_the_code_default_the_contract_and_live_agree(self, monkeypatch):
        import re

        from backend.config import configured_parlay_card_utc_hour

        monkeypatch.delenv("PARLAY_CARD_UTC_HOUR", raising=False)
        default = configured_parlay_card_utc_hour()

        env = (self._root() / ".env.example").read_text(encoding="utf-8")
        contract = re.search(r"^PARLAY_CARD_UTC_HOUR=(\d+)$", env, re.M)
        assert contract, ".env.example is the contract; it must name this"

        toml = (self._root() / "fly.live.toml").read_text(encoding="utf-8")
        live = re.search(r'^\s*PARLAY_CARD_UTC_HOUR = "(\d+)"$', toml, re.M)
        assert live, "live must set the hour Joe chose, not inherit a default"

        assert default == int(contract.group(1)) == int(live.group(1))

    def test_an_out_of_range_hour_refuses_rather_than_clamping(
        self, monkeypatch
    ):
        """`clamping-is-for-values-you-trust`. An hour arriving from the
        environment is being validated, and 25 silently becoming 23 would move
        the card by hours with nothing saying so."""
        from backend.config import ConfigError, configured_parlay_card_utc_hour

        monkeypatch.setenv("PARLAY_CARD_UTC_HOUR", "25")
        with pytest.raises(ConfigError):
            configured_parlay_card_utc_hour()

    def test_the_loop_reads_it_once_at_startup_not_per_pass(self):
        """Mutation observed red: inline `configured_parlay_card_utc_hour()`
        into the `parlay_cards` call.

        A per-pass read is a per-pass chance to raise on a bad value, 96 times
        a day, in the middle of the recording loop -- the failure
        `MarketResultConfig` was moved out of the pass for.
        """
        source = (self._root() / "scripts" / "run_loop.py").read_text(
            encoding="utf-8"
        )
        call = source.index("alerter.parlay_cards(")
        block = source[call:call + 400]
        assert "card_hour_utc=parlay_card_hour" in block
        assert "configured_parlay_card_utc_hour()" not in block


class TestThePassLogCanSeeWhatTheParlayChannelDid:
    """The result of `parlay_cards` was DISCARDED at the call site when the
    two channels were split, so every push and every refusal was invisible in
    the pass line -- including `held`, the state the split added specifically
    so that "the ladder keeps rebuilding the same card" and "the ladder is
    churning" could be told apart. A field nothing logs is a field nobody can
    read; this repo has four modules' worth of that failure on record.
    """

    @staticmethod
    def _root():
        from pathlib import Path
        return Path(__file__).resolve().parents[1]

    @classmethod
    def _run_loop(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_run_loop_for_test", cls._root() / "scripts" / "run_loop.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_parlay_outcome_is_not_discarded(self):
        """Mutation observed red: drop the assignment at the call site."""
        source = (self._root() / "scripts" / "run_loop.py").read_text(
            encoding="utf-8"
        )
        assert "parlay = await alerter.parlay_cards(" in source
        assert "parlay=parlay," in source

    def test_a_held_card_is_visible_in_the_merged_line(self):
        """Driven through the real merger rather than pinned by substring."""
        from backend.notify.alerts import AlertResult

        line = self._run_loop().CombinedPass(
            _FakeCounts(), parlay=AlertResult(held=("safe",)),
        ).as_dict()
        assert line["parlay_held"] == ["safe"]

    def test_the_two_alerters_do_not_overwrite_each_other(self):
        """Mutation observed red: merge the parlay counts without the prefix.

        `after_pass` and `parlay_cards` both emit `alerts_sent`. Merged into
        one dict unprefixed, one silently overwrites the other -- the exact
        collision `clv_`, `settle_` and `outcome_` already exist to prevent.
        """
        from backend.notify.alerts import AlertResult

        line = self._run_loop().CombinedPass(
            _FakeCounts(),
            alerts=AlertResult(sent=("window_open",)),
            parlay=AlertResult(sent=("safe",)),
        ).as_dict()
        assert line["alerts_sent"] == ["window_open"]
        assert line["parlay_sent"] == ["safe"]

    def test_an_empty_outcome_adds_no_noise(self):
        """A quiet pass must not print four empty lists; `if v` already does
        this for the other alerter and the parlay counts follow it."""
        from backend.notify.alerts import AlertResult

        line = self._run_loop().CombinedPass(
            _FakeCounts(), parlay=AlertResult(),
        ).as_dict()
        assert not [k for k in line if k.startswith("parlay_")]


class _FakeCounts:
    def as_dict(self):
        return {"markets": 0}
