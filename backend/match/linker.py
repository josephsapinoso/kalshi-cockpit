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
# fixture. Deliberately tight: MLB doubleheaders are the same two teams on the
# same date a few hours apart, so a generous window would merge them. Kalshi
# encodes HHMM in the ticker precisely because same-day repeats exist.
DEFAULT_COMMENCE_TOLERANCE_MS = 2 * 3600 * 1000

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")

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
        method="exact_alias_pair",
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


def record_link(conn, result: MatchResult, league: str, linked_ms: int) -> None:
    """Persist a successful link, keeping the skew as evidence.

    The commence skew is stored rather than validated and discarded: a link
    with a large skew is a different fixture that happens to share teams, and
    that is only visible after the fact if the number was kept.
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
