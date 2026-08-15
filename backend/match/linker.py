"""Deterministic matching between Kalshi events and sportsbook fixtures.

This module is where the previous project's worst measured failure lived. Its
Kalshi-to-Polymarket text matcher achieved a **0.56% hit rate, and the hits
were wrong** -- pairing "who wins" against "over/under 3.5 goals" on the same
fixture. A wrong match does not produce an error; it produces an *edge*, because
you are comparing two prices for different questions.

So the design rule here is: **ambiguity refuses.** Every join is either
unambiguous or it is reported as unmatched. There is no scoring, no
best-guess, no threshold to tune down when coverage looks thin.

The resolution trick
--------------------
Team-name reconciliation is normally a large maintenance problem: Kalshi says
`"Houston"`, The Odds API says `"Houston Astros"`, and `"New York G"` has to
become `"New York Giants"` without becoming `"New York Jets"`.

Rather than maintain a global table of every team in every league, names are
resolved **within a single candidate fixture** -- against just the two teams
that fixture actually contains. `"New York G"` only has to be distinguishable
from `"Dallas"`, not from all 32 NFL teams. That shrinks the ambiguity space to
almost nothing and makes the alias file a short list of genuine exceptions
rather than a full roster.

The rule is a normalised prefix match that must produce a **bijection**: each
Kalshi side maps to exactly one distinct sportsbook team. Anything else --
no match, two matches, both Kalshi sides claiming the same team -- refuses.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

logger = logging.getLogger(__name__)

ALIAS_DIR = Path(__file__).parent / "aliases"

# How far apart two sources' stated start times may be and still be the same
# fixture.
#
# **Kalshi's `occurrence_datetime` runs exactly 3 hours late.** Measured against
# The Odds API on a live slate (2026-08-07):
#
#     KXMLBGAME  14 of 18 same-day pairs at +180 min
#     KXWNBAGAME  6 of  6 same-day pairs at +180 min
#
# The two-sport agreement is what identifies it. WNBA games run about two hours
# and MLB about three, so if `occurrence_datetime` were the expected *outcome*
# time the offsets would differ by an hour; they are identical, which makes it a
# fixed shift and not a duration. Three hours is the US Eastern-to-Pacific gap,
# and both zones move together across DST, so it does not vary seasonally.
#
# The tolerance was 2 hours, so **every single link failed by an hour** and the
# whole chain produced zero recommendations from a full live slate.
#
# Widened to 4 rather than correcting the offset in `discovery`, because a
# hard-coded `-3h` is a silent lie the day Kalshi fixes it, and because the
# residual skew is *recorded* on every link (`commence_skew_ms`) -- so the
# offset stays visible as data rather than being subtracted away where nobody
# can see it drift.
#
# Widening is safe here specifically because `link_event` **refuses** when more
# than one fixture matches the same team pair inside the window. A wider window
# therefore cannot produce a wrong match; it can only turn an MLB doubleheader
# into a refusal, which is the documented and intended behaviour. Note the
# offset makes this matter more, not less: at a *tight* tolerance, game one's
# shifted Kalshi time lands near game two's true start, which is precisely the
# wrong-match this refusal exists to prevent.
DEFAULT_COMMENCE_TOLERANCE_MS = 4 * 3600 * 1000

# The measured shift above. Not applied anywhere -- it is asserted by
# `TestKalshiOccurrenceDatetimeRunsLate` so that if Kalshi ever corrects it, the
# test fails and this comment stops being true silently.
OBSERVED_KALSHI_COMMENCE_OFFSET_MS = 3 * 3600 * 1000

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")

# The fixture a Kalshi event ticker names, e.g. `26AUG151310CWSDET`.
#
# `KXMLBGAME-26AUG151310CWSDET` and `KXMLBKS-26AUG151310CWSDET` are the
# moneyline and the strikeout ladder for **one game**, and the segment after the
# series is byte-identical between them. That is what lets a prop event inherit
# a link the game event already earned, instead of being matched from scratch
# against team names it does not carry.
#
# Anchored at both ends, and it captures rather than slices. `joint_bound.py`
# records why a fixed character count is the wrong tool here: segment lengths
# vary with the team codes (`CWSDET` is six, `LADAZ` is five), so anything
# counting characters is right until the first three-letter matchup.
_FIXTURE_SEGMENT = re.compile(r"^[A-Z0-9]+-(?P<fixture>[0-9]{2}[A-Z]{3}[0-9]+[A-Z]+)$")

# `event_links.method` for a link inherited this way, so a prop link is never
# mistaken in the record for one that passed the team-pair bijection.
PROP_LINK_METHOD = "prop_fixture_segment"

# `event_links.method` for a link that did pass it. Named rather than repeated
# as a literal, because a prop is only allowed to inherit from this kind and a
# reader comparing two spellings of one string cannot tell that rule is holding.
EXACT_ALIAS_PAIR = "exact_alias_pair"


def fixture_segment(event_ticker: str) -> Optional[str]:
    """`KXMLBKS-26AUG151310CWSDET` -> `26AUG151310CWSDET`, else `None`.

    `None` on anything that does not have exactly the two-part shape. A ticker
    this cannot read must block the link rather than fall back to the whole
    string, which would compare a prop against a game only when both were
    equally unreadable -- a join that succeeds precisely when it is least
    justified.
    """
    matched = _FIXTURE_SEGMENT.match(event_ticker or "")
    return matched.group("fixture") if matched else None

# Dropped when comparing, because one source includes them and the other does
# not. "FC" and "SC" matter for soccer; the rest are US-league noise.
_NOISE_TOKENS = frozenset({"fc", "sc", "afc", "cf", "the"})


def normalise(name: str) -> str:
    """Casefold, strip accents and punctuation, collapse whitespace.

    `"St. Louis"` and `"St Louis"` must compare equal; `"Montréal"` and
    `"Montreal"` must too.
    """
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = _PUNCT.sub(" ", ascii_only.lower())
    tokens = [t for t in _WS.split(lowered) if t and t not in _NOISE_TOKENS]
    return " ".join(tokens)


@dataclass(frozen=True)
class TeamAliases:
    """Explicit overrides for one league, loaded from `aliases/<sport_key>.yaml`.

    Only needed where the prefix rule genuinely cannot resolve a name -- for
    example when a source uses a nickname that shares no prefix with the other
    ("Cardinals" vs "St. Louis"). Keep this file short; a long alias file means
    the deterministic rule has stopped working and is being papered over.
    """

    sport_key: str
    # normalised kalshi name -> normalised sportsbook name
    mapping: dict[str, str] = field(default_factory=dict)

    def resolve(self, kalshi_name: str) -> Optional[str]:
        return self.mapping.get(normalise(kalshi_name))


def load_aliases(sport_key: str, alias_dir: Path = ALIAS_DIR) -> TeamAliases:
    """Load a league's alias overrides. A missing file means no overrides."""
    path = alias_dir / f"{sport_key}.yaml"
    if not path.exists():
        return TeamAliases(sport_key=sport_key)

    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mapping = {
        normalise(k): normalise(v) for k, v in (raw.get("teams") or {}).items()
    }
    return TeamAliases(sport_key=sport_key, mapping=mapping)


def _matches(kalshi_name: str, book_name: str, aliases: TeamAliases) -> bool:
    """Whether one Kalshi side refers to one sportsbook team.

    Three deterministic tests, in order. None of them scores or thresholds.
    """
    k = normalise(kalshi_name)
    b = normalise(book_name)
    if not k or not b:
        return False

    # 1. Exact.
    if k == b:
        return True

    # 2. Explicit override.
    override = aliases.resolve(kalshi_name)
    if override and override == b:
        return True

    # 3. Token-prefix. Kalshi abbreviates to the city or a truncation of it:
    #    "Houston" -> "Houston Astros", "New York G" -> "New York Giants".
    #    Compared token-wise so "New York G" cannot match "New York" alone,
    #    and a partial final token must genuinely start the book's token --
    #    which is what keeps "New York G" off "New York Jets".
    k_tokens, b_tokens = k.split(), b.split()
    if len(k_tokens) > len(b_tokens):
        return False
    for i, k_tok in enumerate(k_tokens):
        b_tok = b_tokens[i]
        if i == len(k_tokens) - 1:
            if not b_tok.startswith(k_tok):
                return False
        elif k_tok != b_tok:
            return False
    return True


@dataclass(frozen=True)
class MatchCandidate:
    """One sportsbook fixture that might be the same game."""

    odds_event_id: str
    commence_ms: int
    home_team: str
    away_team: str


@dataclass(frozen=True)
class MatchResult:
    kalshi_event_ticker: str
    odds_event_id: Optional[str]
    commence_skew_ms: Optional[int]
    method: str
    reason: Optional[str] = None

    @property
    def matched(self) -> bool:
        return self.odds_event_id is not None


def _bijection(
    kalshi_teams: Sequence[str],
    candidate: MatchCandidate,
    aliases: TeamAliases,
) -> bool:
    """Whether the two Kalshi sides map one-to-one onto this fixture's teams.

    Requires a genuine bijection. Both Kalshi sides matching the same
    sportsbook team is a failure, not a half-success -- it means the names are
    too coarse to tell the teams apart, which is exactly when a wrong join
    would look like a right one.
    """
    if len(kalshi_teams) != 2:
        return False

    book_teams = [candidate.home_team, candidate.away_team]
    used: set[int] = set()

    for kalshi_name in kalshi_teams:
        hits = [
            i
            for i, book_name in enumerate(book_teams)
            if i not in used and _matches(kalshi_name, book_name, aliases)
        ]
        if len(hits) != 1:
            return False
        used.add(hits[0])

    return len(used) == 2


def link_event(
    *,
    kalshi_event_ticker: str,
    kalshi_teams: Sequence[str],
    kalshi_commence_ms: int,
    candidates: Iterable[MatchCandidate],
    aliases: TeamAliases,
    tolerance_ms: int = DEFAULT_COMMENCE_TOLERANCE_MS,
) -> MatchResult:
    """Resolve one Kalshi event to at most one sportsbook fixture.

    Returns an unmatched result with a stated reason rather than raising --
    "we could not match this" is normal operating output that belongs in the
    work queue, not an exception.
    """
    if len(kalshi_teams) != 2:
        return MatchResult(
            kalshi_event_ticker, None, None, "none",
            reason=f"expected 2 sides, got {len(kalshi_teams)}: {list(kalshi_teams)}",
        )

    in_window = [
        c
        for c in candidates
        if abs(c.commence_ms - kalshi_commence_ms) <= tolerance_ms
    ]
    if not in_window:
        return MatchResult(
            kalshi_event_ticker, None, None, "none",
            reason="no sportsbook fixture within the commence-time window",
        )

    viable = [c for c in in_window if _bijection(kalshi_teams, c, aliases)]

    if not viable:
        near = ", ".join(f"{c.away_team} @ {c.home_team}" for c in in_window[:3])
        return MatchResult(
            kalshi_event_ticker, None, None, "none",
            reason=(
                f"no team-pair bijection. Kalshi sides {list(kalshi_teams)} did "
                f"not resolve against any of: {near}. Add an alias if these are "
                f"the same fixture."
            ),
        )

    if len(viable) > 1:
        # Two fixtures with the same teams inside the window -- a doubleheader
        # with a loose tolerance, or duplicate feed entries. Guessing here is
        # how you price one game off another game's line.
        return MatchResult(
            kalshi_event_ticker, None, None, "none",
            reason=(
                f"ambiguous: {len(viable)} fixtures match the same team pair "
                f"within +/-{tolerance_ms // 60000}min. Refusing rather than "
                f"guessing which game this is."
            ),
        )

    winner = viable[0]
    return MatchResult(
        kalshi_event_ticker=kalshi_event_ticker,
        odds_event_id=winner.odds_event_id,
        commence_skew_ms=winner.commence_ms - kalshi_commence_ms,
        method=EXACT_ALIAS_PAIR,
    )


@dataclass(frozen=True)
class LinkedFixture:
    """A link some other Kalshi event already earned, offered to a prop.

    `odds_commence_ms` is the **sportsbook's** start time, not Kalshi's. It is
    carried so a prop's own skew can be measured against the same reference the
    game's was, rather than the prop inheriting a number computed for a
    different event.
    """

    fixture: str
    odds_event_id: str
    odds_commence_ms: int


def link_prop_event(
    *,
    kalshi_event_ticker: str,
    kalshi_commence_ms: int,
    linked_fixtures: Iterable[LinkedFixture],
) -> MatchResult:
    """Resolve a prop event by inheriting its own game's link.

    **Why props cannot go through `link_event`.** That function matches on a
    two-team bijection built from `yes_sub_title`. A prop event's subtitles are
    `"Anthony Kay: 2+"`, `"Anthony Kay: 3+"`, and so on -- twelve player-rung
    strings, not two team names. Every prop event would fail with
    `"expected 2 sides, got 12"` and land in `unmatched_events`, roughly twelve
    hundred rows a pricing pass, describing a failure that was never a failure.

    So a prop is linked by **identity, not by inference**: its ticker names the
    same fixture segment as the moneyline event for the same game, and that
    event has already been matched against the sportsbook by name. Inheriting
    that answer adds no new way to be wrong -- the prop link is exactly as
    correct as the game link it comes from, and no more.

    Refuses, rather than guesses, in three cases: an unreadable ticker, no
    linked game for the fixture, and two linked games claiming one fixture
    segment. The last is the doubleheader shape `link_event` already refuses on,
    and it must refuse here for the same reason -- attaching a player's ladder
    to the wrong half of a doubleheader produces entirely plausible numbers.
    """
    fixture = fixture_segment(kalshi_event_ticker)
    if fixture is None:
        return MatchResult(
            kalshi_event_ticker, None, None, "none",
            reason=(
                f"ticker {kalshi_event_ticker!r} does not name a fixture "
                f"segment, so there is no game event to inherit a link from"
            ),
        )

    matches = [f for f in linked_fixtures if f.fixture == fixture]
    if not matches:
        return MatchResult(
            kalshi_event_ticker, None, None, "none",
            reason=(
                f"no linked game event for fixture {fixture}. A prop inherits "
                f"its game's link; until the moneyline event is matched there "
                f"is nothing to inherit."
            ),
        )

    distinct = {f.odds_event_id for f in matches}
    if len(distinct) > 1:
        return MatchResult(
            kalshi_event_ticker, None, None, "none",
            reason=(
                f"ambiguous: fixture {fixture} is linked to {len(distinct)} "
                f"different sportsbook events ({sorted(distinct)}). Refusing "
                f"rather than guessing which game this player's ladder is on."
            ),
        )

    winner = matches[0]
    return MatchResult(
        kalshi_event_ticker=kalshi_event_ticker,
        odds_event_id=winner.odds_event_id,
        # Measured against the sportsbook's start time, exactly as
        # `link_event` does -- not copied from the game's row. The prop event
        # carries its own `occurrence_datetime`, and a prop stamped differently
        # from its game is a fact worth recording rather than hiding.
        commence_skew_ms=winner.odds_commence_ms - kalshi_commence_ms,
        method=PROP_LINK_METHOD,
    )


def record_unmatched(
    conn,
    *,
    observed_ms: int,
    side: str,
    identifier: str,
    league: Optional[str],
    detail: str,
    reason: str,
) -> None:
    """Add to the visible work queue.

    A matcher that silently drops what it cannot resolve looks identical to one
    with nothing to do. This is the difference between "coverage is thin" and
    "coverage is broken", and it is the queue that alias files get filled from.
    """
    conn.execute(
        "INSERT INTO unmatched_events (observed_ms, side, identifier, league, "
        "detail, reason, resolved) VALUES (?, ?, ?, ?, ?, ?, 0)",
        (observed_ms, side, identifier, league, detail, reason),
    )
    conn.commit()


def resolve_outcome(
    kalshi_name: str, book_names: Sequence[str], aliases: TeamAliases
) -> Optional[str]:
    """Which sportsbook outcome a Kalshi side refers to, or `None`.

    Kalshi names a side by `yes_sub_title` ("Houston"); the books use full names
    ("Houston Astros"). The consensus is keyed on the book's spelling, so a
    Kalshi market has to be resolved onto it before its fair probability can be
    looked up.

    Ambiguity returns `None`. Matching more than one book outcome means the
    names are too coarse to tell the teams apart, which is exactly the case
    where a wrong answer looks like a right one -- the same rule `_bijection`
    applies to fixtures, applied to a single side.
    """
    hits = [name for name in book_names if _matches(kalshi_name, name, aliases)]
    return hits[0] if len(hits) == 1 else None


def record_link(conn, result: MatchResult, league: str, linked_ms: int) -> int:
    """Persist a successful link and return its id, keeping the skew as evidence.

    The commence skew is stored rather than validated and discarded: a link
    with a large skew is a different fixture that happens to share teams, and
    that is only visible after the fact if the number was kept.

    Returns the `event_links.id`, which every downstream row needs as a foreign
    key. `INSERT OR IGNORE` yields no usable `lastrowid` when the link already
    exists -- which is the normal case on every pass after the first -- so the
    id is read back rather than inferred from the cursor.
    """
    if not result.matched:
        raise ValueError("record_link called with an unmatched result")
    conn.execute(
        "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) VALUES (?, ?, ?, ?, ?, ?)",
        (
            result.kalshi_event_ticker,
            result.odds_event_id,
            league,
            result.method,
            result.commence_skew_ms,
            linked_ms,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM event_links WHERE kalshi_event_ticker = ? "
        "AND odds_event_id = ?",
        (result.kalshi_event_ticker, result.odds_event_id),
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f"link for {result.kalshi_event_ticker} vanished immediately after "
            f"insert -- refusing to continue with an unknown link id"
        )
    return int(row["id"])
