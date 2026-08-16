"""The Slate's desk crew: who speaks, from what, and what they may not become.

This repo has no JavaScript test runner (`frontend/package.json` has `dev`,
`build`, `start` and `lint`), so these assertions are over **source text**, the
same instrument `tests/test_board_screen.py` uses and with the same limitation
stated up front.

WHY THE CREW NEEDS GUARDING AT ALL
----------------------------------
The bubble is the one place on the Slate where the product speaks in sentences
rather than columns, and a sentence is the easiest thing in this codebase to
turn into a model by accident. Two failure modes, both cheap to reach:

1. **A persona that weighs one factor against another is a rating.** "Books
   like it and it has drifted your way" is a composite with no ADR, and
   `test_slate.py` / `test_api.py` cannot see it because it never touches the
   payload. The defence is structural rather than lexical: **one voice, one
   data source**, so no line has two factors available to weigh. That is what
   the per-function tests below pin.

2. **A persona that is a real person is a fabricated quote.** Joe asked for
   Billy Walters; `.claude/agents/sharp-bettor.md` forbids putting invented
   words in a living person's mouth. **Willy Balters is a fiction with a
   fiction's name**, which is Joe's own fix and the reason the character can
   exist. The inventory test is what stops a later edit from "correcting" the
   spelling.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about rendering.** Source text is not a DOM. A green suite says the
  functions read the fields they are allowed to read; it does not say the
  bubble appears, is reachable, or is legible on a phone.
- **Nothing about whether the lines are true.** They restate fields the server
  computed. If `books_below` means something other than what `willyLine`
  says it means, every test here still passes.
- **Nothing about the avatars looking like anything.** They assert the drawings
  are inline and self-contained, not that they are recognisable.
- **Nothing about the backend agents.** `backend/agents/skeptic.py` and
  `scout.py` share these names and are a different thing: LLM callers, metered,
  quarantined where ADR 0022 says so, and guarded by `tests/test_has_callers.py`
  and `tests/test_agent_budget.py`. Nothing here reaches them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
BUBBLE = FRONTEND / "components" / "CrewBubble.tsx"
AVATAR = FRONTEND / "components" / "CrewAvatar.tsx"


def source(path: Path) -> str:
    assert path.exists(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """`text` with every comment removed.

    **Written after three of these tests failed on their own explanations.**
    A component that documents *why* it does not use `next/image`, or why a
    persona must not become a rating, contains those words -- and a grep over
    raw source cannot tell a prohibition from a violation of it. Forbidding the
    explanation along with the thing explained is worse than not checking:
    it makes the honest comment the thing that has to go.

    Deliberately naive: `/* */` and `//` only, no string-literal awareness. It
    is enough here because neither file contains a `//` inside a string, and a
    smarter stripper would be a parser nobody reviews.
    """
    without_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.MULTILINE)


def fields_read(body: str, receiver: str) -> set[str]:
    """Which `<receiver>.x` fields a function body actually reads.

    Field access rather than word search, because `skepticLine` legitimately
    contains the word "edge" in a sentence it prints. A test that could not
    tell `row.edge_cents` from the English word would force the user-facing
    prose to be written around the checker, which is the tail wagging the dog.

    Destructuring counts: `const { books_below: below } = books` reads
    `books_below` just as surely as `books.books_below` does.
    """
    direct = set(re.findall(rf"\b{re.escape(receiver)}\.(\w+)", body))
    destructured: set[str] = set()
    for block in re.findall(rf"{{([^}}]*)}}\s*=\s*{re.escape(receiver)}\b", body):
        for part in block.split(","):
            name = part.split(":")[0].strip()
            if name:
                destructured.add(name)
    return direct | destructured


def body_of(text: str, name: str) -> str:
    """The body of a top-level `function name(...) { ... }`.

    Anchored on a closing brace in column 0, which is what Prettier gives every
    top-level function in this codebase. Deliberately strict: if the extraction
    ever fails it raises here rather than returning `""`, because an empty
    string would satisfy every "must not mention" assertion below and turn this
    whole file green by accident. That is the exact shape of the `unreadable`
    counter that read 0 of 81,420 while a third of the data went out under it.
    """
    match = re.search(
        rf"^function {re.escape(name)}\((.*?)\)[^{{]*{{\n(.*?)^}}",
        text,
        re.DOTALL | re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"could not find a top-level `function {name}(` ")
    return match.group(2)


def params_of(text: str, name: str) -> str:
    match = re.search(rf"^function {re.escape(name)}\((.*?)\)", text, re.MULTILINE)
    if match is None:
        raise AssertionError(f"could not find a top-level `function {name}(` ")
    return match.group(1).strip()


# The complete cast. An inventory rather than a snapshot: a fourth persona has
# to be added here, which is the moment somebody re-reads the one-voice rule.
EXPECTED_CREW = {"The Skeptic", "Willy Balters", "The Scout"}


class TestTheCastIsAnInventory:
    """Who is on screen is a decision, not an accident of a component edit."""

    def test_the_declared_crew_is_exactly_the_expected_three(self):
        names = set(re.findall(r'^\s*name: "(.+?)",', source(BUBBLE), re.MULTILINE))
        assert names == EXPECTED_CREW

    def test_all_three_are_actually_rendered(self):
        """Declared and rendered are different things.

        A `CrewMember` constant that no longer appears in the bubble's list is
        a persona that exists in the source and not on the screen -- the same
        "built but never called" shape this project has shipped four times.
        """
        text = source(BUBBLE)
        rendered = re.search(r"\{\[\n(.*?)\]\.map", text, re.DOTALL)
        assert rendered is not None, "could not find the rendered crew list"
        for const in ("SKEPTIC", "WILLY", "SCOUT"):
            assert f"who: {const}" in rendered.group(1), const

    def test_no_persona_is_named_after_a_living_person(self):
        """The name is the fiction, and it is load-bearing.

        Mutation: change `name: "Willy Balters"` to `name: "Billy Walters"`.

        Checked on the `name:` fields only, because the component's docstring
        legitimately names the real person to explain why he is not on screen.
        Grepping the whole file would forbid the explanation along with the
        thing it explains.
        """
        names = set(re.findall(r'^\s*name: "(.+?)",', source(BUBBLE), re.MULTILINE))
        assert "Billy Walters" not in names
        assert "Willy Balters" in names


class TestOneVoiceReadsOneSource:
    """The structural reason no line can become a composite.

    Every mutation below is a persona reaching for a second factor, which is
    exactly how a sentence becomes a rating without anybody deciding to build
    one.
    """

    # The complete set of row fields the Skeptic is allowed to see. An
    # allowlist, not a denylist: a new factor added to `SlateRowData` is
    # forbidden to him by default, which is the direction that stays safe as
    # the row grows.
    SKEPTIC_MAY_READ = {"suppressed_reason", "suggested_contracts"}

    def test_the_skeptic_reads_only_suppression(self):
        body = code_only(body_of(source(BUBBLE), "skepticLine"))
        read = fields_read(body, "row")
        assert read, "skepticLine reads no row field, so this test is vacuous"
        assert read <= self.SKEPTIC_MAY_READ, read - self.SKEPTIC_MAY_READ

    def test_willy_never_touches_the_row_at_all(self):
        """He is handed the distribution, so `row.` cannot appear.

        Stronger than an allowlist and simpler: there is no field of the row he
        is entitled to, so any `row.` at all is the violation.
        """
        body = code_only(body_of(source(BUBBLE), "willyLine"))
        assert fields_read(body, "row") == set()

    def test_willy_does_read_the_distribution(self):
        """Without this the test above passes on an empty function."""
        body = code_only(body_of(source(BUBBLE), "willyLine"))
        assert fields_read(body, "books"), "willyLine reads no book field"

    def test_willy_is_handed_the_distribution_and_not_the_row(self):
        """The narrowest possible parameter is the guard.

        Mutation: `willyLine(row: SlateRowData)`. Passing the whole row would
        make every other factor reachable, and the one-voice rule would then
        rest on nobody using them.
        """
        params = params_of(source(BUBBLE), "willyLine")
        assert "SlateRowData" not in params
        assert "BookDistribution" in params

    def test_the_scout_is_handed_nothing_at_all(self):
        """Mutation: give `scoutLine` a `row` parameter.

        A scout that can see a price is a scout that can invent context from
        one, and its line is an admission that it has not looked.
        """
        assert params_of(source(BUBBLE), "scoutLine") == ""

    def test_the_scout_says_it_has_not_looked(self):
        """Silence and a disconnected wire are different states. ADR 0022."""
        body = body_of(source(BUBBLE), "scoutLine")
        assert "not looked" in body


class TestNoPersonaMayBecomeAComposite:
    """The same prohibition `test_slate.py` puts on the payload, on the screen.

    Mutation: add `const score = ...` to the component.
    """

    FORBIDDEN = ("score", "rating", "confidence", "ranked", "overall")

    def test_the_component_computes_no_composite(self):
        text = code_only(source(BUBBLE)).lower()
        for word in self.FORBIDDEN:
            assert word not in text, (
                f"{word!r} appeared in CrewBubble.tsx; combining unscored "
                f"factors into one number is a model and needs ADR 0021 §9"
            )

    def test_no_line_claims_a_forecast(self):
        """The footer is the disclaimer and it must survive an edit."""
        assert "no forecast" in source(BUBBLE).lower()


class TestTheAvatarsAreSelfContained:
    """Inline SVG, no asset pipeline, no network, no likeness.

    A remote avatar would be a third-party request from a page that shows what
    somebody is about to bet, and it would fail exactly when a phone's
    connection is worst -- which is when the screen is most likely to be open.
    """

    def test_no_avatar_is_fetched_from_anywhere(self):
        text = code_only(source(AVATAR))
        for forbidden in ("<img", "src=", "http://", "https://", "next/image"):
            assert forbidden not in text, forbidden

    def test_every_declared_face_is_drawn(self):
        """Mutation: delete one `kind === "..."` branch.

        A `CrewFace` value with no branch renders an empty circle-less `<svg>`,
        which is a blank space where a character should be -- absence wearing
        the shape of a present thing.
        """
        text = source(AVATAR)
        declared = set(
            re.findall(r'export type CrewFace =\s*(.+?);', text, re.DOTALL)[0]
            .replace('"', "")
            .replace("|", " ")
            .split()
        )
        assert declared, "CrewFace declares no faces"
        for face in declared:
            assert f'kind === "{face}"' in text, face

    def test_the_faces_the_bubble_asks_for_all_exist(self):
        """The two files must agree, and neither imports the other's list."""
        used = set(re.findall(r'^\s*face: "(.+?)",', source(BUBBLE), re.MULTILINE))
        assert used, "the bubble asks for no faces"
        for face in used:
            assert f'kind === "{face}"' in source(AVATAR), face

    def test_the_drawing_is_not_announced_to_a_screen_reader(self):
        """The name and role are already text beside it. ARIA would read twice.

        `code_only` and not `source`, and the mutation run is why: written
        against the raw file, this test stayed green with the attribute deleted
        because the component's own docstring says the words "aria-hidden".
        Ten of eleven crew mutations went red and this was the one that did
        not, which is the entire argument for running them.
        """
        assert "aria-hidden" in code_only(source(AVATAR))


class TestTheBubbleIsNotTheOnlyRouteToAnything:
    """Hover is desktop-only by nature, and Joe operates this from a phone."""

    @pytest.mark.parametrize("handler", ["onMouseEnter", "onFocus"])
    def test_the_bubble_opens_on_focus_as_well_as_hover(self, handler):
        assert handler in source(BUBBLE)
