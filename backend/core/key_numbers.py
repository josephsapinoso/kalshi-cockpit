"""Football key numbers: a display-only fact about a spread line.

Football margins land on 3 and 7 far more often than on their neighbours,
then 6, 10 and 14 (public record: Walters's memoir and interviews), so a line
that sits on one, or whose half point sits against one, is worth more or less
than the same half point elsewhere. This module says *where a line sits*; it
prices nothing, ranks nothing and changes no side or strike a ticket reads.

`key_number_flag(line)` returns

- `{"kind": "on", "number": N}` when `abs(line)` is exactly a key number
  (a sportsbook line -- Kalshi never lists a spread *on* 3),
- `{"kind": "crosses", "number": N}` when `abs(line)` is a half point beside
  one (Kalshi's 2.5 / 3.5, 6.5, 7.5 ...),
- `None` otherwise, and for `None` in.

Choice, documented: 6.5 sits beside both 6 and 7; the flag names only 7, the
stronger number. 5.5 -> 6, 9.5 / 10.5 -> 10, 13.5 / 14.5 -> 14.
Football only: the caller must not ask about a basketball or baseball line.

WHAT THIS DOES NOT ESTABLISH: how often a game lands on the number (the
glossary sentence is the public record, not a measurement of ours), or that
a key-number line is mispriced.
"""

from __future__ import annotations

from typing import Optional

#: Strongest first; a half point beside two numbers resolves to the earlier.
KEY_NUMBERS: tuple[int, ...] = (3, 7, 6, 10, 14)

#: Kalshi series prefixes and Odds API sport-key prefix that mean football.
FOOTBALL_KALSHI_PREFIXES: tuple[str, ...] = ("KXNFL", "KXNCAAF")
FOOTBALL_SPORT_KEY_PREFIX = "americanfootball_"


def key_number_flag(line: Optional[float]) -> Optional[dict]:
    if line is None:
        return None
    try:
        mag = abs(float(line))
    except (TypeError, ValueError):
        return None
    for n in KEY_NUMBERS:
        if mag == n:
            return {"kind": "on", "number": n}
    for n in KEY_NUMBERS:
        if abs(mag - n) == 0.5:
            return {"kind": "crosses", "number": n}
    return None
