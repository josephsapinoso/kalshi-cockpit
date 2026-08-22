"""The glossary's coverage is pinned, so it cannot silently regress.

Joe's standing instruction (2026-08-18, recorded in `lib/glossary.ts`): every
betting or statistics term the site uses must teach itself. Until 2026-08-22
nothing enforced it — 14 terms existed, 7 files used them, three definitions
had no caller at all, and the money screen (`TicketSheet`) rendered zero.
Precedent for the shape: `tests/test_suppression_gloss.py` (coverage both
directions, an anti-vacuity anchor, exemptions that carry written reasons).

Four claims, tested separately because they fail for different reasons:

1. **Vocabulary coverage** — a file whose prose uses a vocabulary word must
   gloss it at least once (`<Term k="...">`), matching the define-at-first-use
   instruction, or carry a written exemption.
2. **The scan finds what it should** — the anchor; an over-eager regex change
   must not let the scan find nothing and pass perfectly.
3. **No orphaned terms** — every glossary key is rendered by some file. A
   definition nobody can reach is a plan, not a feature (`drift`,
   `candlestick` and `basis_points` were exactly this).
4. **House style** — definitions stay popover-sized, and the `stake` entry
   may never again carry a money figure: the only prescriptive sentence in
   the old glossary instructed "$2, every time" against a real derived cap
   of 26 cents.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- That any definition is *correct* — a wrong sentence passes here.
- That the popover renders, or is legible (Term.tsx's own concern).
- Full-app coverage of every conceivable term; only the vocabulary below.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "frontend" / "src"
GLOSSARY_TS = SRC / "lib" / "glossary.ts"

#: Prose surface → glossary key. Case-sensitive, word-bounded; chosen to be
#: prose-shaped so identifiers do not false-positive (underscores are word
#: characters, so `resulting_exposure_dollars` does not match `\bexposure\b`).
VOCABULARY: dict[str, str] = {
    #: `contract` is deliberately absent: as a bare word it is
    #: indistinguishable from the identifier (`bet.contracts`,
    #: `const contracts`) in comment-stripped source, so scanning for it
    #: reports code as prose. The orphan test still guarantees the term is
    #: rendered somewhere; TicketSheet, OpportunityCard and the market page
    #: carry it.
    r"[Cc]onsensus fair": "consensus",
    r"\bdevigged\b": "devig",
    r"\bQuarter-Kelly\b": "kelly",
    r"\bCLV\b": "clv",
    r"\bexposure\b": "exposure",
    r"\bbankroll\b": "bankroll",
}

#: (file, key) pairs excused from the vocabulary rule, each with the reason.
#: An exemption without a reason is a hole wearing a label. `lib/glossary.ts`
#: is skipped wholesale in the scan — it IS the glossary.
EXEMPT: dict[tuple[str, str], str] = {
    ("components/HowToRead.tsx", "consensus"): (
        "teaching prose that defines its own words in full sentences"
    ),
    ("components/FiveStepTest.tsx", "bankroll"): (
        "the word sits inside a step's concatenated teaching string; the "
        "component's own prose defines it in the same sentence"
    ),
    ("lib/suppressionGloss.ts", "bankroll"): (
        "gloss sentences define in place; a Term inside a gloss would nest "
        "popovers"
    ),
    ("app/layout.tsx", "devig"): (
        "the word is in the <meta> description string — no DOM to tap"
    ),
    ("app/dashboards/page.tsx", "clv"): (
        "developer screen (503 on live, off the nav since 2026-08-22); its "
        "subtitle sentence carries the caveat in place"
    ),
}


def strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


def scanned_files() -> dict[str, str]:
    """Every frontend source file, comment-stripped, keyed by posix path."""
    return {
        path.relative_to(SRC).as_posix(): strip_comments(
            path.read_text(encoding="utf-8")
        )
        for path in sorted(SRC.rglob("*.ts*"))
    }


def glossary_keys() -> set[str]:
    source = GLOSSARY_TS.read_text(encoding="utf-8")
    block = source.split("export const GLOSSARY", 1)[1]
    return set(re.findall(r"^  ([a-z_]+): \{", block, flags=re.MULTILINE))


def glossary_definitions() -> dict[str, str]:
    """Each entry's definition text, concatenated string literals joined."""
    source = GLOSSARY_TS.read_text(encoding="utf-8")
    block = source.split("export const GLOSSARY", 1)[1]
    entries: dict[str, str] = {}
    for match in re.finditer(
        r"^  ([a-z_]+): \{(.*?)^  \},", block, flags=re.MULTILINE | re.DOTALL
    ):
        key, body = match.group(1), match.group(2)
        definition = body.split("definition:", 1)[1]
        parts = re.findall(r'"((?:[^"\\]|\\.)*)"', definition)
        entries[key] = "".join(parts)
    return entries


class TestTheVocabularyIsCovered:
    def test_every_file_using_a_vocabulary_word_glosses_it_once(self):
        """Define-at-first-use, per file. Mutation observed red: remove the
        gate page's <Term k="kelly"> — the file reappears here by name."""
        offenders = []
        for rel, source in scanned_files().items():
            if rel == "lib/glossary.ts":
                continue
            for pattern, key in VOCABULARY.items():
                if (rel, key) in EXEMPT:
                    continue
                if re.search(pattern, source) and f'k="{key}"' not in source:
                    offenders.append((rel, key))
        assert not offenders, (
            f"These files use a vocabulary word with no <Term> gloss anywhere "
            f"in the file: {offenders}. Wrap the first use in "
            f'<Term k="...">, or add (file, key) to EXEMPT with the reason.'
        )

    def test_every_exemption_still_matches_a_real_file_and_word(self):
        """A stale exemption is a hole that outlived its reason."""
        files = scanned_files()
        for (rel, key), reason in EXEMPT.items():
            assert reason, f"exemption {(rel, key)} carries no reason"
            assert rel in files, f"exempted file {rel} no longer exists"
            pattern = next(p for p, k in VOCABULARY.items() if k == key)
            assert re.search(pattern, files[rel]), (
                f"exempted file {rel} no longer uses the word for {key}; "
                f"remove the stale exemption"
            )


class TestTheScanFindsWhatItShould:
    def test_the_screens_that_matter_are_in_the_scan(self):
        """The anchor. Without it an over-eager regex change makes the scan
        find nothing and pass perfectly — the shape of every vacuous test in
        this repo's history."""
        files = scanned_files()
        for expected in (
            "components/TicketSheet.tsx",
            "app/slate/page.tsx",
            "app/bets/page.tsx",
            "app/gate/page.tsx",
        ):
            assert expected in files
        hits = {
            rel
            for rel, source in files.items()
            if any(re.search(p, source) for p in VOCABULARY)
        }
        assert "components/TicketSheet.tsx" in hits
        assert "app/gate/page.tsx" in hits
        assert "app/bets/page.tsx" in hits

    def test_the_glossary_parser_reads_real_entries(self):
        defs = glossary_definitions()
        assert len(defs) >= 15
        assert "clv" in defs and "Closing-line value" in defs["clv"]


class TestNoOrphanedTerms:
    def test_every_glossary_key_is_rendered_somewhere(self):
        """This is what caught `drift`, `candlestick` and `basis_points`.
        Mutation observed red: add an entry nothing uses."""
        files = scanned_files()
        used = set()
        for rel, source in files.items():
            if rel in ("lib/glossary.ts", "components/Term.tsx"):
                continue
            used.update(re.findall(r'k="([a-z_]+)"', source))
        orphaned = sorted(glossary_keys() - used)
        assert not orphaned, (
            f"{orphaned} are defined in the glossary and rendered by nothing "
            f"— a definition nobody can reach is a plan, not a feature. Use "
            f"it or delete it."
        )

    def test_no_term_call_names_a_missing_key(self):
        """The other direction; the TypeScript union enforces it at build
        time, but this suite runs where tsc may not have."""
        files = scanned_files()
        keys = glossary_keys()
        for rel, source in files.items():
            if rel in ("lib/glossary.ts",):
                continue
            for used in re.findall(r'<Term k="([a-z_]+)"', source):
                assert used in keys, f"{rel} uses unknown glossary key {used!r}"


class TestTheHouseStyleHolds:
    def test_definitions_stay_popover_sized(self):
        """The module's own ceiling is ~45 words for a ~260px popover; 55 is
        the hard stop so existing good copy is not chopped mid-sentence."""
        for key, definition in glossary_definitions().items():
            words = len(definition.split())
            assert words <= 55, (
                f"glossary entry {key!r} is {words} words — it will not fit "
                f"the popover it renders in"
            )

    def test_the_stake_entry_never_carries_a_money_figure(self):
        """The one prescriptive lie this file has already told: 'Yours is
        $2, every time' shipped while the real derived cap was 26 cents
        (ADR 0045). A glossary that gives a number gives an order; the caps
        screen owns the numbers. Mutation observed red: put a dollar amount
        back into the stake definition."""
        stake = glossary_definitions()["stake"]
        assert not re.search(r"[$¢]\s?\d|\d\s?[¢c]\b", stake), (
            "the stake definition carries a money figure again; the caps "
            "screen owns the numbers, the glossary owns the concept"
        )
