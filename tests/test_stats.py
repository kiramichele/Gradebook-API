import random
import statistics
from decimal import Decimal

import pytest

from app.grading.stats import Bin, histogram, score_stats


def test_textbook_example():
    # The classic example with mean 5 and population SD exactly 2.
    stats = score_stats([2, 4, 4, 4, 5, 5, 7, 9], points_possible=10)
    assert stats.count == 8
    assert stats.mean == 5
    assert stats.median == 4.5
    assert stats.std_dev == 2
    assert (stats.min, stats.max) == (2, 9)
    assert stats.mean_percent == 50
    assert stats.median_percent == 45


def test_odd_count_median():
    assert score_stats([9, 1, 5], 10).median == 5


def test_single_score_has_zero_spread():
    stats = score_stats([7], 10)
    assert (stats.mean, stats.median, stats.std_dev) == (7, 7, 0)


def test_empty():
    stats = score_stats([], 10)
    assert stats.count == 0
    assert stats.mean is stats.median is stats.std_dev is stats.min is stats.max is None
    assert stats.mean_percent is stats.median_percent is None
    assert [b.count for b in stats.histogram] == [0] * 10
    assert set(stats.letters.values()) == {0}


def test_exact_with_awkward_decimals():
    # Floating point would give 0.30000000000000004 for this mean.
    stats = score_stats([Decimal("0.1"), Decimal("0.2"), Decimal("0.6")], Decimal("1"))
    assert stats.mean == 0.3
    assert stats.mean_percent == 30


@pytest.mark.parametrize("seed", range(50))
def test_matches_statistics_module(seed):
    rng = random.Random(seed)
    scores = [rng.randint(0, 100) for _ in range(rng.randint(1, 40))]
    stats = score_stats(scores, 100)
    assert stats.mean == pytest.approx(statistics.fmean(scores))
    assert stats.median == pytest.approx(statistics.median(scores))
    assert stats.std_dev == pytest.approx(statistics.pstdev(scores))
    assert sum(b.count for b in stats.histogram) == len(scores)
    assert sum(stats.letters.values()) == len(scores)


def test_letters():
    stats = score_stats([95, 91, 85, 50, 50], 100)
    assert stats.letters["A"] == 1
    assert stats.letters["A-"] == 1
    assert stats.letters["B"] == 1
    assert stats.letters["F"] == 2
    assert list(stats.letters)[0] == "A"


# --- histogram ----------------------------------------------------------------


def counts(bins):
    return {(b.lower, b.upper): b.count for b in bins if b.count}


def test_bin_edges():
    bins = histogram([0, 9.99, 10, 89.99, 90, 100])
    assert counts(bins) == {(0, 10): 2, (10, 20): 1, (80, 90): 1, (90, 100): 2}
    assert len(bins) == 10


def test_extra_credit_gets_overflow_bin():
    bins = histogram([50, 100, 105, 120])
    assert bins[-1] == Bin(100, None, 2)
    assert counts(bins)[(90, 100)] == 1


def test_no_overflow_bin_when_unused():
    assert all(b.upper is not None for b in histogram([100]))


def test_bin_width():
    bins = histogram([10, 30, 60, 99], bin_width=25)
    assert [(b.lower, b.upper, b.count) for b in bins] == [
        (0, 25, 1),
        (25, 50, 1),
        (50, 75, 1),
        (75, 100, 1),
    ]


def test_histogram_uses_percent_of_points_possible():
    stats = score_stats([15, 20], points_possible=20)
    assert counts(stats.histogram) == {(70, 80): 1, (90, 100): 1}


@pytest.mark.parametrize("width", [0, 3, 101, -10])
def test_invalid_bin_width(width):
    with pytest.raises(ValueError):
        histogram([], bin_width=width)


def test_invalid_points_possible():
    with pytest.raises(ValueError):
        score_stats([1], 0)
