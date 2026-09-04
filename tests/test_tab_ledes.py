"""The one line that says what each tab is for (ticket #9), and three comments
the record had refuted.

Ticket #9 wrote seven strings and Joe ratified them on 2026-08-27. Two shipped
with #8 and #29 (`tests/test_picks_screen.py` pins them); the other five --
Games, Parlays, Your bets, Playbook and Gate -- did not ship until 2026-09-03.
This file pins those five on the RENDERED prose, so a later edit to any of them
is a decision written into a test rather than a drift.

Source-text assertions, the same instrument as `tests/test_scope_sentences.py`
and with the same limitation: a green suite says the files say and omit the
right words, not that the page renders or that a novice understands it.

What these pin, and why each earns a test:

- **Each ratified lede is on its page, verbatim after whitespace and markup
  normalisation.** The Games lede departs from #9 in one clause, on a newer
  ruling: Joe's 29A ratification (2026-09-03) of the Refusals footer blurb
  found two rows in three in the live window refused by the fee bar with no
  rule named, so "the named rule behind each one the desk refused" became
  "the reason behind each one ... -- a named check, or the fee bar". The
  constant below carries the shipped wording, and its docstring the reason.
- **The Gate lede's predecessor is gone.** "The tool has to demonstrate an edge
  before it is allowed to act on one" was pre-ADR-0038 framing: the edge was
  measured and it was negative (`beta = -0.141`), the hunt is closed, and the
  gate is the interlock that is never lowered (ADR 0038 §3). A screen that
  says the tool is waiting to earn its permission tells a novice the
  opposite of what the record says.
- **The Gate screen says the count is a reading, not a plan.** ADR 0100 §3
  made "the footer link is called Gate and `/gate` keeps its games-against-300
  count" a hard condition so that nobody re-derives "the gate will open" as a
  step. The page itself now says so, in the sentence that names the count.
- **No comment asserts `--accent` is `--negative`.** Four did, in the present
  tense, after ADR 0081 (commit `7bdcb11`, 2026-08-28) made them different
  hues. A false reason attached to a live refusal is how a future session
  deletes the refusal (ticket #33's own words). The historical form ("used to
  be", "was") is allowed; the present tense is not.
- **The market page's `priceAlreadyVisible` comment records #24's decision
  rather than arguing against it.** The prop is passed unconditionally and is
  false in two states the ticket measured; Joe ruled (2026-09-02) that it
  becomes conditional before any search link ships. The comment used to say
  it was "true here and always has been".

Mutation observed red, per test, in the docstring of each.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "app"
COMPONENTS = ROOT / "frontend" / "src" / "components"

GATE = APP / "gate" / "page.tsx"
GAMES = APP / "slate" / "page.tsx"
PARLAYS = APP / "parlays" / "page.tsx"
BETS = APP / "bets" / "page.tsx"
PLAYBOOK = APP / "playbook" / "page.tsx"
BOARD = APP / "board" / "page.tsx"
MARKET = APP / "market" / "[ticker]" / "page.tsx"
FAIR_VALUE_STEPS = COMPONENTS / "FairValueSteps.tsx"
PARLAY_DIFFICULTY = COMPONENTS / "ParlayDifficulty.tsx"

#: #9's Games lede, with the 29A refusal clause. #9 wrote "and the named rule
#: behind each one the desk refused"; only the `rejected` bucket carries a
#: named rule, and on live 2026-09-02 82 of 122 rows in the window were
#: refused by the fee bar with none. Joe ratified the two-kinds phrasing for
#: the footer blurb (29A, 2026-09-03) and this lede takes the same shape
#: rather than the universal reading he refused there.
GAMES_LEDE = (
    "The long list, one line per side of a market the desk priced in its "
    "last half-hour of recording: what Kalshi charges for it, how likely "
    "the sportsbooks think it is, and the reason behind each one the desk "
    "refused — a named check, or the fee bar — with your balance and the "
    "caps it sets at the top."
)

#: #9's Parlays lede, verbatim. `<Term>` markup is stripped before comparison.
PARLAYS_LEDE = (
    "Parlay cards cut from tonight’s games, one pick per game, shown at the "
    "fair value the sportsbooks’ chances imply rather than at what Kalshi "
    "charges — a card pays only if every pick on it wins, and once you own "
    "one nobody is bidding to buy it back."
)

#: #9's "Your bets" lede, verbatim. CLV is described, never named, so the
#: glossary-coverage rule is not triggered by it.
BETS_LEDE = (
    "Your own record, read back from your Kalshi account: every bet the desk "
    "has seen settle since it started watching — however you placed it — "
    "what each one won or lost after the venue’s fees, what they add up to, "
    "and, on the ones where it can be checked, whether you paid better than "
    "Kalshi’s own last price before the game started."
)

#: #9's Playbook lede, verbatim. It names what the guide is about, not what
#: to do tonight, so it stays true whether or not the five steps are rewritten.
PLAYBOOK_LEDE = (
    "A guide to thinking a bet through before you place it, and under it a "
    "dated record of every time this tool’s own settings changed — so a "
    "change of settings is never mistaken for a change in results."
)

#: #9's Gate lede, verbatim. No count and no status figure, on purpose: the
#: live number renders in the Conditions list and a figure in prose would go
#: stale on the runner's next pass.
GATE_LEDE = (
    "The lock on this tool ever placing a bet by itself — which it has never "
    "done, and the code that would send an order is switched off behind the "
    "lock as well. The bets you place by hand go through a different door "
    "with its own limits, and this lock never touches them."
)

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)


def prose(path: Path) -> str:
    """The rendered prose of a page: comments stripped (a comment quoting a
    retired sentence must not satisfy an assertion that it is gone), `<Term>`
    tags and `{" "}` spacers removed, `&rsquo;` decoded, whitespace collapsed
    so a sentence JSX wraps across lines can be asserted as one string."""
    text = path.read_text(encoding="utf-8")
    text = _BLOCK_COMMENT.sub(" ", text)
    text = _LINE_COMMENT.sub(" ", text)
    text = re.sub(r"</?Term\b[^>]*>", "", text)
    text = text.replace('{" "}', " ")
    text = text.replace("&rsquo;", "’").replace("&mdash;", "—")
    return re.sub(r"\s+", " ", text)


def comments(path: Path) -> str:
    """Only the comments of a file, whitespace collapsed -- the half `prose`
    throws away, for the assertions that are about what the code SAYS about
    itself rather than what it renders."""
    text = path.read_text(encoding="utf-8")
    found = _BLOCK_COMMENT.findall(text) + _LINE_COMMENT.findall(text)
    return re.sub(r"\s+", " ", " ".join(found))


class TestEveryRatifiedLedeIsOnItsPage:
    """Five of #9's seven strings. Each is compared after normalisation
    against the constant above, so a one-word edit to the screen fails here
    and has to be written into the constant as a decision."""

    def test_games(self):
        """Mutation observed red: "last half-hour" -> "last hour" on the page."""
        assert GAMES_LEDE in prose(GAMES)

    def test_parlays(self):
        """Mutation observed red: drop "nobody is bidding to buy it back"."""
        assert PARLAYS_LEDE in prose(PARLAYS)

    def test_your_bets(self):
        """Mutation observed red: "however you placed it" -> "placed here"."""
        assert BETS_LEDE in prose(BETS)

    def test_playbook(self):
        """Mutation observed red: restore "The rules that were in force"."""
        assert PLAYBOOK_LEDE in prose(PLAYBOOK)

    def test_gate(self):
        """Mutation observed red: "which it has never done" -> "which it has
        not done yet" -- the trajectory reading the string is written to
        deny."""
        assert GATE_LEDE in prose(GATE)

    def test_the_games_lede_still_hands_off_to_the_server_note(self):
        """#9: the lede keeps `{data.note}` appended -- the chance-is-not-edge
        sentence comes from the payload so the server and the screen cannot
        disagree about what the page claims. Mutation observed red: delete
        `{data.note}` from the header."""
        header = prose(GAMES).split("</header>", 1)[0]
        assert "{data.note}" in header


class TestTheGateNoLongerSaysItIsWaitingToEarnAnEdge:
    """The sentence the lede replaced credited a hunt that is closed."""

    def test_the_pre_0038_sentence_is_gone(self):
        """Mutation observed red: paste "the tool has to demonstrate an edge
        before it is allowed to act on one" back into the header."""
        text = prose(GATE)
        for phrase in (
            "demonstrate an edge",
            "until the paper record earns it",
            "allowed to act on one",
        ):
            assert phrase not in text, (
                f"/gate says {phrase!r} again: that is the pre-ADR-0038 "
                f"framing in which the tool is waiting to earn permission. The "
                f"edge was measured (beta = -0.141) and the gate is an interlock "
                f"that is never lowered, not a bar the record is climbing."
            )

    def test_the_count_is_called_a_reading_and_not_a_plan(self):
        """ADR 0100 §3 pins the 300 on the page; this pins what the page says
        the 300 IS. Mutation observed red: delete the sentence "That count is
        a reading, not a plan ..." from the scope paragraph."""
        text = prose(GATE)
        assert "a reading, not a plan" in text
        assert "never lowered or bypassed" in text
        assert "nothing on this desk waits for it to open" in text

    def test_the_lede_bakes_in_no_count(self):
        """#9: "No count or status figure is baked in, so the string cannot go
        stale when the runner writes another actionable row." The live number
        is the Conditions list's job. Mutation observed red: append "The
        record has 2 in its life." to the lede."""
        text = prose(GATE)
        lede_end = text.index(GATE_LEDE) + len(GATE_LEDE)
        after = text[lede_end:].lstrip()
        assert after.startswith("</p>"), (
            "the Gate lede grew a sentence after #9's ratified string: "
            f"{after[:80]!r}"
        )
        assert not re.search(r"\b\d+ in its (?:whole )?life\b", text)


class TestNoCommentSaysTheAccentIsTheLossColour:
    """`--accent` and `--negative` were one hex until commit `7bdcb11` (ADR
    0081, 2026-08-28). Four comments kept saying so in the present tense for a
    week. The historical form is allowed -- the history is why the refusals
    exist -- and the present tense is not.

    **What this does not establish:** that the palette is right, or that any
    refusal is still justified. `tests/test_palette_contrast.py` owns the
    tokens; `tests/test_fair_value_steps.py` and
    `tests/test_parlay_difficulty_chart.py` own the refusals.
    """

    #: Present-tense identity, either spelling the four comments used.
    PRESENT_TENSE = re.compile(
        r"`?--accent`?\s+is\s+(?:byte-identical|the same (?:red|hex|colour|color))"
    )

    def test_the_four_repaired_comments(self):
        """Mutation observed red: change "was byte-identical" back to "is
        byte-identical" in `board/page.tsx`'s Stat comment."""
        for path in (FAIR_VALUE_STEPS, PARLAY_DIFFICULTY, BOARD, GAMES):
            text = comments(path)
            hit = self.PRESENT_TENSE.search(text)
            assert hit is None, (
                f"{path.name} says {hit.group(0)!r}: false since ADR 0081. "
                f"Say what is true today, or say 'was'."
            )

    def test_each_names_the_reason_that_survives(self):
        """Repairing a false reason by deleting it leaves a refusal with no
        reason, which is the next thing a session deletes. Each comment must
        still say WHY the element stays uncoloured. Mutation observed red:
        cut "a mark on a chart is a claim" from `FairValueSteps.tsx`."""
        assert "a mark on a chart is a claim" in comments(FAIR_VALUE_STEPS)
        assert "a mark on a chart is a claim" in comments(PARLAY_DIFFICULTY)
        for path in (BOARD, GAMES):
            stat = path.read_text(encoding="utf-8").split("function Stat(", 1)[1]
            assert "count is a fact, not a verdict" in re.sub(r"\s+", " ", stat).lower(), (
                f"{path.name}'s Stat comment lost its reason"
            )


class TestTheMarketPageRecordsTicket24:
    """The `priceAlreadyVisible` comment on `/market/[ticker]`."""

    def test_it_no_longer_claims_the_prop_is_always_true(self):
        """Mutation observed red: restore "`priceAlreadyVisible` is true here
        and always has been" as the comment's opening."""
        text = comments(MARKET)
        assert "is true here and always has been" not in text, (
            "the market page argues again that the flag is unconditionally "
            "true; #24 measured two states in which it is false"
        )

    def test_it_records_the_decision_and_its_precondition(self):
        """Mutation observed red: delete "#24" from the comment."""
        text = comments(MARKET)
        assert "#24" in text
        assert "conditional" in text
        assert "ADR 0065" in text
        assert "`detail` is null" in text

    def test_the_prop_is_still_passed(self):
        """The decision is that the flag CHANGES before a link ships, not that
        it goes. `tests/test_buy_controls.py` pins the mount; this pins that
        the comment did not become the edit. Mutation observed red: drop the
        prop from the `<ManualTicket` mount."""
        code = _BLOCK_COMMENT.sub("", MARKET.read_text(encoding="utf-8"))
        assert re.search(r"<ManualTicket\s+ticker=\{ticker\}\s+priceAlreadyVisible\s*/>", code)
