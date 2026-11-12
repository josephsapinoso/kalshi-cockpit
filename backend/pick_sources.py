"""Where a pick came from, in Joe's own word, one tag per market ticker.

Joe asked on 2026-10-02 to track the bets he placed off the desk's
recommendations and learn from them. The record already holds every bet
(`parlay_positions`, `manual_orders`, `venue_settlements`); what it could not
say is **which recommendation a bet came from**. `parlay_lookup_id` is a
guess (the newest lookup for the ticker), leg verdicts are deliberately never
joined to a position (ADR 0186 §3), and a pick from a chat or a friend's link
leaves no trace at all. So the tag is Joe's, set by one tap on /bets, and
nothing here infers it.

Keyed by **ticker**, not by position id, because the three places a bet lives
share only that: an open combination's `parlay_positions.combo_ticker`, a
settled one's `venue_settlements.ticker`, and a single placed anywhere. A
hand-recorded sportsbook slip has no ticker and cannot be tagged; that is a
stated gap, not a bug.

`suggested_sources` offers a pre-selection only where the record PROVES it:
a game-script card stamped with the ticker is `card`, and a position whose
label is a ladder preset's key is `preset`. A suggestion is never stored --
the tag exists only after his tap -- and a ticket whose Check a parlay
lookup carried a name (`parlay_lookups.tailed_from`, #424) is offered
`friend`. Nothing is ever suggested as `own`, `chat` or `verdict`, because
nothing in the record proves those.

What this module does NOT establish
-----------------------------------
That a tag is true. It is Joe's word after the fact, and a bet built from two
sources gets one. It is not a measurement of any source's skill: the per-source
summary in `backend/bets.py` is the same expected-vs-won line the kinds carry,
under the same >= 5-each-side rule, and it says nothing until a source has
enough settled bets for the line to speak (ADR 0193).
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, Optional

from .core.ladder import CARD_SHAPES, PROP_CARD, TOTALS_CARD

#: The tags, in the ONE fixed order every screen and summary uses. Never
#: re-sorted by any result: an ordering is a claim (ADR 0071 §2.5).
PICK_SOURCES: tuple[str, ...] = (
    "card", "verdict", "preset", "chat", "friend", "own",
)

#: The words the screen shows for each tag.
PICK_SOURCE_LABELS: dict[str, str] = {
    "card": "Game-script card",
    "verdict": "Leg verdict",
    "preset": "Parlay preset",
    "chat": "Claude chat",
    "friend": "Tailed pick",
    "own": "My own pick",
}

#: The summary's bucket for a settled bet nobody tagged. Not a tag: it can
#: never be stored, and it is counted, never folded into `own`.
UNTAGGED = "untagged"

#: Every ladder recipe key: a position labelled with one was built from a
#: preset card on /parlays.
PRESET_KEYS: frozenset[str] = frozenset(
    {recipe.key for recipe in CARD_SHAPES} | {PROP_CARD.key, TOTALS_CARD.key}
)

MAX_TICKER_LEN = 120

#: Longest name for who a tailed pick came from (ADR 0193 Amendment 1).
MAX_TAILED_NAME_LEN = 40


class PickSourceRefused(ValueError):
    """A tag or ticker the table cannot hold; the message is the screen's."""


def clean_tailed_name(name: Optional[str]) -> Optional[str]:
    """Trim a name; blank is None; over the limit is refused in words."""
    if name is None:
        return None
    name = name.strip()
    if not name:
        return None
    if len(name) > MAX_TAILED_NAME_LEN:
        raise PickSourceRefused(
            f"A name is at most {MAX_TAILED_NAME_LEN} characters. "
            "Nothing was tagged."
        )
    return name


def set_pick_source(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    source: Optional[str],
    now_ms: int,
    tailed_from: Optional[str] = None,
) -> None:
    """Store Joe's tag for `ticker`, or clear it when `source` is None.

    `tailed_from` names who a tailed pick came from and is allowed only with
    `friend`; a tag changed away from `friend` loses its name (ADR 0193
    Amendment 1).
    """
    ticker = (ticker or "").strip()
    if not ticker or len(ticker) > MAX_TICKER_LEN:
        raise PickSourceRefused("That is not a ticker. Nothing was tagged.")
    name = clean_tailed_name(tailed_from)
    if source is None:
        if name is not None:
            raise PickSourceRefused(
                "A name goes with a tailed pick only. Nothing was tagged."
            )
        conn.execute("DELETE FROM pick_sources WHERE ticker = ?", (ticker,))
        conn.commit()
        return
    if source not in PICK_SOURCES:
        raise PickSourceRefused(
            f"'{source}' is not one of the sources. Nothing was tagged."
        )
    if name is not None and source != "friend":
        raise PickSourceRefused(
            "A name goes with a tailed pick only. Nothing was tagged."
        )
    conn.execute(
        "INSERT INTO pick_sources (ticker, source, tagged_ms, tailed_from) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(ticker) DO UPDATE SET "
        "source = excluded.source, tagged_ms = excluded.tagged_ms, "
        "tailed_from = excluded.tailed_from",
        (ticker, source, now_ms, name),
    )
    conn.commit()


def tailed_names(conn: sqlite3.Connection) -> list[str]:
    """Distinct names in FIRST-USED order: the earliest `tagged_ms` per
    case-folded name, the spelling first used wins. Never sorted by any
    result -- an ordering is a claim (ADR 0071 s2.5)."""
    seen: dict[str, str] = {}
    for name, in conn.execute(
        "SELECT tailed_from FROM pick_sources WHERE tailed_from IS NOT NULL "
        "ORDER BY tagged_ms, ticker"
    ):
        seen.setdefault(name.casefold(), name)
    return list(seen.values())


def tailed_from_for(
    conn: sqlite3.Connection, tickers: Iterable[str]
) -> dict[str, str]:
    """`ticker -> name` for tickers that carry one."""
    wanted = sorted({t for t in tickers if t})
    out: dict[str, str] = {}
    for start in range(0, len(wanted), 500):
        chunk = wanted[start:start + 500]
        for row in conn.execute(
            "SELECT ticker, tailed_from FROM pick_sources "
            f"WHERE tailed_from IS NOT NULL AND ticker IN ({_placeholders(len(chunk))})",
            chunk,
        ):
            out[row[0]] = row[1]
    return out


def _placeholders(n: int) -> str:
    return ",".join("?" * n)


def pick_sources_for(
    conn: sqlite3.Connection, tickers: Iterable[str]
) -> dict[str, str]:
    """`ticker -> source` for the tagged ones; an untagged ticker is absent."""
    wanted = sorted({t for t in tickers if t})
    if not wanted:
        return {}
    out: dict[str, str] = {}
    # Chunked under SQLite's default host-parameter ceiling.
    for start in range(0, len(wanted), 500):
        chunk = wanted[start:start + 500]
        for row in conn.execute(
            "SELECT ticker, source FROM pick_sources "
            f"WHERE ticker IN ({_placeholders(len(chunk))})",
            chunk,
        ):
            out[row[0]] = row[1]
    return out


def suggested_sources(
    conn: sqlite3.Connection, tickers: Iterable[str]
) -> dict[str, str]:
    """`ticker -> source` only where the record proves it (see the module
    docstring). A card stamp outranks a preset label: the card is the more
    specific fact."""
    wanted = sorted({t for t in tickers if t})
    if not wanted:
        return {}
    out: dict[str, str] = {}
    for start in range(0, len(wanted), 500):
        chunk = wanted[start:start + 500]
        marks = _placeholders(len(chunk))
        for row in conn.execute(
            "SELECT combo_ticker, label FROM parlay_positions "
            f"WHERE combo_ticker IN ({marks})",
            chunk,
        ):
            if row[1] in PRESET_KEYS:
                out[row[0]] = "preset"
        for row in conn.execute(
            "SELECT DISTINCT combo_ticker FROM game_script_cards "
            f"WHERE combo_ticker IN ({marks})",
            chunk,
        ):
            out[row[0]] = "card"
    # A ticket whose CHECK carried a name (#424) is offered `friend`, only
    # where no card or preset is proven. Never stored: the tag needs his tap.
    for ticker in suggested_tailed_from(conn, wanted):
        out.setdefault(ticker, "friend")
    return out


def suggested_tailed_from(
    conn: sqlite3.Connection, tickers: Iterable[str]
) -> dict[str, str]:
    """`ticker -> name` from the NEWEST `parlay_lookups` row for the ticker
    that carries a `tailed_from` (the name given on Check a parlay). A
    suggestion only: nothing here writes `pick_sources`."""
    wanted = sorted({t for t in tickers if t})
    out: dict[str, str] = {}
    for start in range(0, len(wanted), 500):
        chunk = wanted[start:start + 500]
        for row in conn.execute(
            "SELECT minted_market_ticker, tailed_from FROM parlay_lookups "
            f"WHERE tailed_from IS NOT NULL AND minted_market_ticker IN "
            f"({_placeholders(len(chunk))}) ORDER BY requested_ms, id",
            chunk,
        ):
            out[row[0]] = row[1]
    return out


def open_combo_tickers(conn: sqlite3.Connection) -> list[str]:
    """Tickers of every open recorded combination: the ones /bets lists
    under Open, so their chips can be served in the same payload."""
    return [
        row[0]
        for row in conn.execute(
            "SELECT combo_ticker FROM parlay_positions "
            "WHERE status = 'open' AND combo_ticker IS NOT NULL"
        )
    ]


def pick_source_payload(
    conn: sqlite3.Connection, tickers: Iterable[str]
) -> dict:
    """What /bets needs to draw the chips: the fixed tag list with its words,
    each ticker's stored tag, and the proven suggestions for untagged ones."""
    wanted = sorted({t for t in tickers if t})
    tagged = pick_sources_for(conn, wanted)
    suggested = suggested_sources(
        conn, [t for t in wanted if t not in tagged]
    )
    untagged = [t for t in wanted if t not in tagged]
    names = suggested_tailed_from(conn, untagged)
    return {
        "options": [
            {"key": key, "label": PICK_SOURCE_LABELS[key]}
            for key in PICK_SOURCES
        ],
        "tagged": tagged,
        "suggested": suggested,
        "suggested_tailed_from": {
            t: n for t, n in names.items() if suggested.get(t) == "friend"
        },
        "tailed_from": tailed_from_for(conn, wanted),
        "tailed_names": tailed_names(conn),
    }
