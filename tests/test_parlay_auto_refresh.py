"""The cold desk stops telling the reader to reload it.

Opening the desk cold stamps `desk_attention`; since `scheduler.sleep_until`
the loop wakes on that within five seconds and sweeps a few seconds after, so
fresh prices land about ten to fifteen seconds after the page renders. The page
is a server component and knew none of it -- the honest instruction was "wait,
then reload", which is a thing to remember to do while looking at a screen that
says nothing is on.

`RefreshWhenPriced` watches `/api/window` and re-renders when the number that
was blocking the cards goes up.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about the effect running.** This repo has no React test runner, so
  these are source pins plus one cross-language constant check. Whether the
  interval fires, whether `router.refresh()` re-renders, and whether a hidden
  tab really stops polling are browser behaviours; they were exercised by hand
  against a local stack and that is what the session record says, not this file.
- **Nothing about a refresh producing cards.** More fresh fixtures may still be
  fewer than a card's minimum, and re-rendering does not change what the
  consensus says.
- **Nothing about the loop waking.** `test_scheduler.py` and
  `test_desk_follows_attention.py` own that half; this one assumes it.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.odds import attention

REPO = Path(__file__).resolve().parents[1]
WATCHER = REPO / "frontend" / "src" / "components" / "RefreshWhenPriced.tsx"
CARDS = REPO / "frontend" / "src" / "components" / "ParlayCards.tsx"
SLATE = REPO / "frontend" / "src" / "app" / "slate" / "page.tsx"
PICKS = REPO / "frontend" / "src" / "app" / "picks" / "page.tsx"


def _flat(path: Path) -> str:
    """Source with runs of whitespace collapsed.

    JSX wraps prose across lines wherever the formatter decides, so a phrase
    assertion against the raw file is really an assertion about line breaks.
    """
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def _code(path: Path) -> str:
    """Source with every comment stripped.

    The file names the alternatives it rejected -- `location.reload()` among
    them -- so a "this string is absent" assertion against the raw text would
    be satisfied by the comment explaining why it is absent, and would go on
    passing after someone changed the call it describes.
    """
    source = path.read_text(encoding="utf-8")
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"//[^\n]*", "", source)


def _const(name: str) -> int:
    source = WATCHER.read_text(encoding="utf-8")
    match = re.search(rf"^const {name} = ([\d_]+);", source, re.M)
    assert match, f"{name} is no longer a module constant in {WATCHER.name}"
    return int(match.group(1).replace("_", ""))


class TestItRefreshesOnTheThingThatWasBlockingTheCards:
    def test_the_trigger_is_more_fresh_fixtures_than_this_render_saw(self):
        """Not "a sweep happened".

        A sweep that re-priced fixtures which were already fresh changes no
        answer on this page, and re-rendering for it is a flicker with nothing
        behind it. `refreshedFor` starts at `renderedFresh` and moves only when
        the page has been refreshed for a higher count, so the same higher
        count seen twice before the new render lands refreshes once. Mutation
        observed red: compare against `last_sweep_ms` instead, or use `>=` so
        an unchanged count refreshes.
        """
        code = _code(WATCHER)
        assert "let refreshedFor = renderedFresh" in code
        assert "facts.fixtures_fresh > refreshedFor" in code
        assert "last_sweep_ms" not in code

    def test_it_refreshes_in_place_rather_than_reloading(self):
        """`router.refresh()` re-runs the server component without blanking the
        page or losing the scroll position. Mutation observed red: swap in
        `window.location.reload()`."""
        code = _code(WATCHER)
        assert "router.refresh()" in code
        assert "location.reload" not in code

    def test_a_hidden_tab_does_not_poll(self):
        """Not a courtesy -- a correctness argument. `Nav.tsx` gates its
        heartbeat on the same property, so a backgrounded tab is sending none,
        so no sweep is coming for it and a poll could only confirm that."""
        source = WATCHER.read_text(encoding="utf-8")
        assert 'document.visibilityState !== "visible"' in source
        assert '"visibilitychange"' in source


class TestItStopsAndSaysSo:
    def test_the_watch_is_bounded(self):
        """A poller that ran until the tab closed would be a background request
        loop nobody asked for. The timer is a `setTimeout` chain since the
        leading edge (2026-09-03), so the bound is the `GIVE_UP_MS` check at
        the top of every look, and the cleanup clears whatever timer is
        pending. Mutation observed red: delete the `GIVE_UP_MS` branch."""
        code = _code(WATCHER)
        assert "now - startedAt > GIVE_UP_MS" in code
        assert "clearTimeout(timer)" in code

    def test_giving_up_matches_the_attention_ttl(self):
        """**One quantity, one limit, across two languages.**

        The watch is worth taking exactly as long as the heartbeat that started
        it is still buying sweeps. Past `DEFAULT_ATTENTION_TTL_MS` the loop is
        no longer being woken for this page, so waiting is not waiting for
        anything -- and a watcher outliving the trigger it depends on is the
        shape of every "two limits on one quantity" bug this repo has hit.

        Mutation observed red: change either number.
        """
        assert _const("GIVE_UP_MS") == attention.DEFAULT_ATTENTION_TTL_MS

    def test_stopping_is_rendered_not_silent(self):
        """A silent watcher and a broken one look identical."""
        flat = _flat(WATCHER)
        assert "stopped watching for them" in flat
        assert "Check again" in flat

    def test_the_poll_cannot_outrun_the_sweep_it_waits_for(self):
        """A cadence faster than the thing being watched mostly asks before the
        answer could have changed. The sweep lands ~10s after a cold open."""
        assert 5_000 <= _const("POLL_MS") <= 30_000


class TestTheDeskWiresIt:
    def test_the_freshness_block_renders_the_watcher(self):
        """The block already fires exactly when a card failed for age, which is
        the cold-page state -- so it needs no second condition. Mutation
        observed red: drop the render."""
        source = CARDS.read_text(encoding="utf-8")
        assert "<RefreshWhenPriced" in source
        block = source.split("function Freshness", 1)[1].split("\nfunction ", 1)[0]
        assert "<RefreshWhenPriced" in block, "the watcher left the stale branch"

    def test_it_is_not_rendered_without_a_baseline(self):
        """Its whole trigger is a count rising above what this render saw. With
        no timetable there is no baseline, and the first successful poll would
        look like a change and refresh the page for nothing. Mutation observed
        red: render it unconditionally."""
        block = (
            CARDS.read_text(encoding="utf-8")
            .split("function Freshness", 1)[1]
            .split("\nfunction ", 1)[0]
        )
        assert "actionable && (" in block
        assert "renderedFresh={actionable.fixtures_fresh}" in block


class TestTheSlateWiresItToo:
    """The same cold-page problem, and deliberately a different gate.

    The parlay desk's `Freshness` block already fires only when a card failed
    for age, so the watcher needed no extra condition there. The slate always
    renders its rows -- refused ones included, because it is a record -- so it
    is never visually empty, and `refreshIsUrgent` (the predicate that decides
    where the refresh panel sits) is `some`: one stale row on a working slate
    satisfies it. Re-rendering under a reader mid-game on that basis would be
    the screen moving for no reason they can see.
    """

    def _source(self) -> str:
        return SLATE.read_text(encoding="utf-8")

    def test_the_slate_renders_the_watcher(self):
        source = self._source()
        assert 'from "@/components/RefreshWhenPriced"' in source
        assert "<RefreshWhenPriced" in source

    def test_it_is_gated_on_the_whole_screen_being_unpriced(self):
        """Mutation observed red: gate on `refreshIsUrgent` instead -- every
        cold-screen test still passes and the slate refreshes under a reader
        whenever any single row is stale."""
        source = self._source()
        assert "slateIsUnpricedByTheClock(" in source
        gate = source.split("{actionable &&", 1)[1].split("<RefreshWhenPriced", 1)[0]
        assert "slateIsUnpricedByTheClock" in gate
        assert "refreshIsUrgent" not in gate

    def test_the_watcher_is_not_buried_in_the_refusal_disclosure(self):
        """`StaleOddsExit` lives inside a collapsed `<details>`. A page that
        re-renders itself while the only explanation is folded away is a page
        that moves for no stated reason, so the watcher sits above it in the
        main flow. Mutation observed red: move the render inside
        `RefusalSummary`."""
        source = self._source()
        assert source.index("<RefreshWhenPriced") < source.index(
            "function RefusalSummary"
        ), "the watcher moved into the collapsed disclosure"

    def test_the_screens_share_one_watcher(self):
        """One component, three callers -- the same reason `StaleOddsExit` was
        extracted. Two screens wording one behaviour two ways is what this
        repo keeps paying for."""
        for page in (CARDS, SLATE, PICKS):
            assert 'from "@/components/RefreshWhenPriced"' in page.read_text(
                encoding="utf-8"
            ), page.name


class TestPicksWiresItToo:
    """The screen the nav word "Picks" opens shipped without the watcher.

    `/picks` (ADR 0098, 2026-09-02) took the slot from `/slate`, which mounts
    `RefreshWhenPriced`; the page was written fresh and the watcher did not
    come with it. On the visit-freshness read of the same day, 21 of 45 cold
    opens had no upcoming fixture inside the limit and the feed then bought
    within a median 3.3 s -- so on half of Joe's opens the new screen rendered
    "N games not ranked: the consensus is too old to speak" and held it for
    the whole visit, while the answer had been in the database since second
    three. His stated reason for not opening the desk, built into the screen
    the day after he said it.

    The gate is `not_ranked.stale_consensus > 0`: a game is withheld by the
    clock, so a rising `fixtures_fresh` can change what the list says. It is
    `some` on purpose where the Slate's is `every`; the page's docstring
    argues it.
    """

    def _source(self) -> str:
        return PICKS.read_text(encoding="utf-8")

    def test_picks_renders_the_watcher(self):
        """Mutation observed red: remove the mount."""
        source = self._source()
        assert 'from "@/components/RefreshWhenPriced"' in source
        assert "<RefreshWhenPriced" in source

    def test_it_is_gated_on_a_game_being_withheld_by_the_clock(self):
        """Mutation observed red: gate on `picks !== null` alone -- the
        watcher then re-renders a complete list for a sweep that changes
        nothing on it, and polls on the empty night the docstring excludes."""
        source = self._source()
        gate = source.split("{actionable &&", 1)[1].split("<RefreshWhenPriced", 1)[0]
        assert "not_ranked.stale_consensus > 0" in gate

    def test_it_is_not_rendered_without_a_baseline(self):
        """Its trigger is a count rising above what this render saw; with no
        timetable the first successful poll would refresh the page for
        nothing. Mutation observed red: drop `actionable &&`."""
        source = self._source()
        gate = source.split("{actionable &&", 1)[1].split("<RefreshWhenPriced", 1)[0]
        assert "renderedFresh={actionable.fixtures_fresh}" in source
        assert "picks !== null" in gate

    def test_it_does_not_answer_the_watchers_question_for_it(self):
        """Ticket #35's half, moved to where it can be answered truthfully.

        This case used to pin `automaticBuyIsComing={anAutomaticBuyIsComing(
        actionable)}` on the mount -- the page answering "is a buy coming"
        from its render's snapshot. The snapshot predates the page's own
        heartbeat, so on a cold open after a quiet hour it said no (the last
        look was over the old 180s constant; the idle cadence is 900s) and the
        watcher switched itself off 0.6s before the buy landed
        (2026-09-02T13:28Z). The watcher now asks `readWatch` against fresh
        facts on every poll, and the page hands it the baseline count only.
        Mutation observed red: pass the prop again."""
        code = _code(PICKS)
        assert "automaticBuyIsComing" not in code
        assert "anAutomaticBuyIsComing" not in code

    def test_the_timetable_failing_costs_the_watcher_not_the_list(self):
        """`/api/window` failing must not send the page to the unreachable
        branch; the list is the content and the watcher is an aid to it.
        Mutation observed red: `await fetchWindow()` without the catch."""
        source = _code(PICKS)
        assert "fetchWindow().catch(() => null)" in source
