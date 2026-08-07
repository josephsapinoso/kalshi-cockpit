"""Synthetic margin data for demos and tests. **This is not data.**

Nothing produced here is evidence about football. It exists so the teaser and
spread machinery can be exercised, demonstrated and tested before a historical
results feed lands, and every consumer is expected to label its output as
illustrative.

The reason this module exists at all is a mistake worth recording. The first
version of the Builder demo generated margins by drawing magnitudes from a
key-number-heavy pool and choosing signs to steer the mean onto the spread. The
mean came out right and the key-number spikes were there, so it looked correct
-- but steering the mean to +8 from a pool averaging 8.6 requires the favourite
to win about 96% of the time. The variance was nonsense, and the demo duly
printed a Wong teaser at **+28.4% EV**, which is a fabricated edge roughly five
times the size of anything real.

That is exactly the failure this project is built to refuse, arriving through
the back door of test scaffolding. So the generator here fixes both moments:

- **Mean** from the closing spread, since that is what a spread *is*.
- **Spread of outcomes** from the league's real standard deviation (~13.5 points
  in the NFL), which is what makes the favourite win a realistic ~76% rather
  than 96%.
- **Key numbers** by snapping nearby margins onto 3, 7, 10 and 14, which
  reproduces the lumpiness without disturbing either of the above.
"""

from __future__ import annotations

import random
from typing import Sequence

# Published NFL margin standard deviation. Close enough to the standard
# deviation of (margin - closing spread) that one number serves for both.
NFL_MARGIN_SD = 13.5

DEFAULT_KEY_NUMBERS = (3, 7, 10, 14)


def synthetic_margins(
    spread: float,
    n: int,
    *,
    seed: int,
    sd: float = NFL_MARGIN_SD,
    key_numbers: Sequence[int] = DEFAULT_KEY_NUMBERS,
    snap_probability: float = 0.6,
) -> list[int]:
    """Plausible final margins for `n` games at a given closing spread.

    `spread` is in betting notation, so −8 is an eight-point favourite and the
    generated margins centre on **+8** from that side's perspective.

    Margins are drawn normally, then a margin within a point of a key number is
    snapped onto it with probability `snap_probability`. Snapping is symmetric
    about the key number, so it adds the spikes without moving the mean.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if sd <= 0:
        raise ValueError("sd must be positive")

    rng = random.Random(seed)
    expected = -float(spread)
    margins: list[int] = []

    for _ in range(n):
        draw = round(rng.gauss(expected, sd))
        # Ties are rare enough in football (~0.1% of games) that spread and
        # teaser markets treat them as a separate case, so a zero draw is
        # pushed to a one-point game rather than left level.
        if draw == 0:
            draw = rng.choice((1, -1))

        magnitude = abs(draw)
        nearest = min(key_numbers, key=lambda k: abs(k - magnitude))
        if abs(nearest - magnitude) <= 1 and rng.random() < snap_probability:
            magnitude = nearest

        margins.append(magnitude if draw > 0 else -magnitude)

    return margins


def synthetic_bucket_observations(
    spreads: Sequence[float],
    *,
    n_per_bucket: int = 1200,
    seed: int = 20260807,
    sd: float = NFL_MARGIN_SD,
) -> list[tuple[float, int]]:
    """`(spread, margin)` pairs across several spreads, for `fit_by_spread`.

    `n_per_bucket` defaults well above `MIN_GAMES_FOR_EMPIRICAL` so every bucket
    is usable; a thinner one would be refused, which is correct behaviour but
    makes for a poor demonstration.
    """
    observations: list[tuple[float, int]] = []
    for offset, spread in enumerate(spreads):
        observations.extend(
            (spread, margin)
            for margin in synthetic_margins(
                spread, n_per_bucket, seed=seed + offset, sd=sd
            )
        )
    return observations
