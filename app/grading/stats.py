"""Descriptive statistics for one assignment's scores.

Pure functions, like the grade engine. Scores are converted to exact
fractions, so the mean and median are exact; only the standard deviation
involves a square root, done by `statistics.pstdev` with correct rounding.

The standard deviation is the *population* SD: the class is the whole group
being described, not a sample of a larger one.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from app.grading.engine import DEFAULT_LETTER_SCALE, Number, letter_for, to_fraction


@dataclass(frozen=True)
class Bin:
    """Scores with lower <= percent < upper (the top bin also includes upper)."""

    lower: float
    upper: float | None  # None for the open-ended bin above 100%
    count: int


@dataclass(frozen=True)
class ScoreStats:
    count: int
    mean: float | None
    median: float | None
    std_dev: float | None
    min: float | None
    max: float | None
    mean_percent: float | None
    median_percent: float | None
    histogram: tuple[Bin, ...]
    letters: dict[str, int]


def histogram(percents: Sequence[Fraction], bin_width: int = 10) -> tuple[Bin, ...]:
    """Bin percents into [0, w), [w, 2w), ..., [100 - w, 100], plus (100, ...) if needed.

    100% lands in the top bin rather than a bin of its own. Scores over 100%
    (extra credit) get an extra open-ended bin, present only when used.
    """
    if not 0 < bin_width <= 100 or 100 % bin_width:
        raise ValueError("bin_width must divide 100")
    n_bins = 100 // bin_width
    counts = [0] * n_bins
    over = 0
    for p in percents:
        if p < 0:
            raise ValueError("percent must be non-negative")
        if p > 100:
            over += 1
        else:
            counts[min(math.floor(p / bin_width), n_bins - 1)] += 1
    bins = [Bin(i * bin_width, (i + 1) * bin_width, c) for i, c in enumerate(counts)]
    if over:
        bins.append(Bin(100, None, over))
    return tuple(bins)


def score_stats(
    scores: Sequence[Number],
    points_possible: Number,
    bin_width: int = 10,
    letter_scale: Sequence[tuple[float, str]] = DEFAULT_LETTER_SCALE,
) -> ScoreStats:
    possible = to_fraction(points_possible)
    if possible <= 0:
        raise ValueError("points_possible must be positive")
    exact = sorted(to_fraction(s) for s in scores)
    percents = [100 * s / possible for s in exact]
    letters = {letter: 0 for _, letter in letter_scale}
    for p in percents:
        letters[letter_for(float(p), letter_scale)] += 1

    if not exact:
        return ScoreStats(
            count=0,
            mean=None,
            median=None,
            std_dev=None,
            min=None,
            max=None,
            mean_percent=None,
            median_percent=None,
            histogram=histogram([], bin_width),
            letters=letters,
        )

    mean = sum(exact, Fraction(0)) / len(exact)
    median = statistics.median(exact)
    return ScoreStats(
        count=len(exact),
        mean=float(mean),
        median=float(median),
        std_dev=float(statistics.pstdev(exact)),
        min=float(exact[0]),
        max=float(exact[-1]),
        mean_percent=float(100 * mean / possible),
        median_percent=float(100 * median / possible),
        histogram=histogram(percents, bin_width),
        letters=letters,
    )
