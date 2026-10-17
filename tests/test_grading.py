import itertools
import random
from decimal import Decimal
from fractions import Fraction

import pytest

from app.enums import GradeStatus
from app.grading import AssignmentSpec, CategorySpec, GradeEntry, compute_grade, letter_for
from app.grading.engine import _Item, _ratio, best_kept_subset

G, M, E, L = GradeStatus.GRADED, GradeStatus.MISSING, GradeStatus.EXCUSED, GradeStatus.LATE


def graded(assignment_id, score, status=G):
    return GradeEntry(assignment_id, status, score)


# --- single category --------------------------------------------------------


def test_points_based_within_a_category():
    cats = [CategorySpec("hw", "Homework", 100)]
    assignments = [AssignmentSpec("a1", "hw", 10), AssignmentSpec("a2", "hw", 30)]
    result = compute_grade(cats, assignments, [graded("a1", 10), graded("a2", 15)])
    # 25 / 40, not the mean of 100% and 50%
    assert result.percent == pytest.approx(62.5)
    assert result.categories[0].earned == 25
    assert result.categories[0].possible == 40


def test_missing_counts_as_zero():
    cats = [CategorySpec("hw", "Homework", 1)]
    assignments = [AssignmentSpec("a1", "hw", 10), AssignmentSpec("a2", "hw", 10)]
    result = compute_grade(cats, assignments, [graded("a1", 10), GradeEntry("a2", M)])
    assert result.percent == pytest.approx(50)


def test_excused_dropped_from_denominator():
    cats = [CategorySpec("hw", "Homework", 1)]
    assignments = [AssignmentSpec("a1", "hw", 10), AssignmentSpec("a2", "hw", 10)]
    result = compute_grade(cats, assignments, [graded("a1", 8), GradeEntry("a2", E)])
    assert result.percent == pytest.approx(80)
    assert result.categories[0].excused == ("a2",)
    assert result.categories[0].possible == 10


def test_excused_score_is_ignored():
    cats = [CategorySpec("hw", "Homework", 1)]
    assignments = [AssignmentSpec("a1", "hw", 10), AssignmentSpec("a2", "hw", 10)]
    result = compute_grade(cats, assignments, [graded("a1", 8), GradeEntry("a2", E, 0)])
    assert result.percent == pytest.approx(80)


def test_ungraded_work_is_ignored():
    cats = [CategorySpec("hw", "Homework", 1)]
    assignments = [AssignmentSpec(f"a{i}", "hw", 10) for i in range(3)]
    result = compute_grade(cats, assignments, [graded("a0", 9), GradeEntry("a1", G, None)])
    assert result.percent == pytest.approx(90)
    assert result.categories[0].ungraded == ("a1", "a2")


def test_late_counts_its_score():
    cats = [CategorySpec("hw", "Homework", 1)]
    result = compute_grade(cats, [AssignmentSpec("a1", "hw", 10)], [graded("a1", 7, L)])
    assert result.percent == pytest.approx(70)


def test_extra_points_above_possible_allowed():
    cats = [CategorySpec("hw", "Homework", 1)]
    result = compute_grade(cats, [AssignmentSpec("a1", "hw", 10)], [graded("a1", 11)])
    assert result.percent == pytest.approx(110)


def test_nothing_graded_has_no_grade():
    cats = [CategorySpec("hw", "Homework", 1)]
    result = compute_grade(cats, [AssignmentSpec("a1", "hw", 10)], [])
    assert result.percent is None
    assert result.letter is None
    assert result.categories[0].percent is None


def test_all_excused_has_no_grade():
    cats = [CategorySpec("hw", "Homework", 1)]
    result = compute_grade(cats, [AssignmentSpec("a1", "hw", 10)], [GradeEntry("a1", E)])
    assert result.percent is None


# --- weighting --------------------------------------------------------------


@pytest.fixture
def weighted_course():
    cats = [
        CategorySpec("tests", "Tests", 40),
        CategorySpec("hw", "Homework", 35),
        CategorySpec("quiz", "Quizzes", 25),
    ]
    assignments = [
        AssignmentSpec("t1", "tests", 100),
        AssignmentSpec("h1", "hw", 10),
        AssignmentSpec("h2", "hw", 10),
        AssignmentSpec("q1", "quiz", 20),
    ]
    return cats, assignments


def test_weighted_categories(weighted_course):
    cats, assignments = weighted_course
    entries = [graded("t1", 80), graded("h1", 10), graded("h2", 8), graded("q1", 14)]
    result = compute_grade(cats, assignments, entries)
    # 0.40*80 + 0.35*90 + 0.25*70
    assert result.percent == pytest.approx(81.0)
    assert result.letter == "B-"


def test_weights_need_not_sum_to_100(weighted_course):
    cats, assignments = weighted_course
    scaled = [CategorySpec(c.id, c.name, Fraction(c.weight, 100)) for c in cats]
    entries = [graded("t1", 80), graded("h1", 10), graded("h2", 8), graded("q1", 14)]
    assert compute_grade(scaled, assignments, entries).percent == pytest.approx(81.0)


def test_empty_category_weight_is_redistributed(weighted_course):
    cats, assignments = weighted_course
    # No quiz graded yet: tests and homework share 40:35
    entries = [graded("t1", 80), graded("h1", 10), graded("h2", 8)]
    result = compute_grade(cats, assignments, entries)
    assert result.percent == pytest.approx((40 * 80 + 35 * 90) / 75)


def test_effective_weights_show_redistribution(weighted_course):
    cats, assignments = weighted_course
    entries = [graded("t1", 80), graded("h1", 10), graded("h2", 8)]
    tests, hw, quiz = compute_grade(cats, assignments, entries).categories
    assert tests.effective_weight == pytest.approx(40 / 75)
    assert hw.effective_weight == pytest.approx(35 / 75)
    assert quiz.effective_weight is None


def test_effective_weights_sum_to_one(weighted_course):
    cats, assignments = weighted_course
    entries = [graded("t1", 80), graded("h1", 10), graded("q1", 14)]
    result = compute_grade(cats, assignments, entries)
    assert sum(c.effective_weight for c in result.categories) == pytest.approx(1)
    assert [c.effective_weight for c in result.categories] == pytest.approx([0.40, 0.35, 0.25])


def test_zero_weight_category_has_no_effective_weight():
    cats = [CategorySpec("tests", "Tests", 1), CategorySpec("practice", "Practice", 0)]
    assignments = [AssignmentSpec("t1", "tests", 10), AssignmentSpec("p1", "practice", 10)]
    result = compute_grade(cats, assignments, [graded("t1", 9), graded("p1", 5)])
    assert [c.effective_weight for c in result.categories] == [1.0, None]


def test_fully_excused_category_weight_is_redistributed(weighted_course):
    cats, assignments = weighted_course
    entries = [graded("t1", 80), GradeEntry("h1", E), GradeEntry("h2", E), graded("q1", 14)]
    result = compute_grade(cats, assignments, entries)
    assert result.percent == pytest.approx((40 * 80 + 25 * 70) / 65)


def test_zero_weight_category_does_not_count():
    cats = [CategorySpec("tests", "Tests", 1), CategorySpec("practice", "Practice", 0)]
    assignments = [AssignmentSpec("t1", "tests", 10), AssignmentSpec("p1", "practice", 10)]
    result = compute_grade(cats, assignments, [graded("t1", 9), graded("p1", 0)])
    assert result.percent == pytest.approx(90)
    assert result.categories[1].percent == 0


def test_decimal_inputs_from_the_database():
    cats = [CategorySpec("hw", "Homework", Decimal("40.000"))]
    assignments = [AssignmentSpec("a1", "hw", Decimal("3.00"))]
    result = compute_grade(cats, assignments, [graded("a1", Decimal("2.00"))])
    assert result.percent == pytest.approx(200 / 3)


def test_float_inputs_are_exact():
    cats = [CategorySpec("a", "A", 0.1), CategorySpec("b", "B", 0.2)]
    assignments = [AssignmentSpec("a1", "a", 0.3), AssignmentSpec("b1", "b", 0.3)]
    result = compute_grade(cats, assignments, [graded("a1", 0.1), graded("b1", 0.2)])
    assert Fraction(result.percent).limit_denominator(1000) == Fraction(500, 9)


# --- drop lowest ------------------------------------------------------------


def test_drop_lowest_one():
    cats = [CategorySpec("quiz", "Quizzes", 1, drop_lowest=1)]
    assignments = [AssignmentSpec(f"q{i}", "quiz", 10) for i in range(4)]
    entries = [graded("q0", 9), graded("q1", 4), graded("q2", 8), graded("q3", 10)]
    result = compute_grade(cats, assignments, entries)
    assert result.percent == pytest.approx(90)
    assert result.categories[0].dropped == ("q1",)
    assert result.categories[0].counted == ("q0", "q2", "q3")


def test_drop_lowest_drops_missing_work_first():
    cats = [CategorySpec("quiz", "Quizzes", 1, drop_lowest=1)]
    assignments = [AssignmentSpec(f"q{i}", "quiz", 10) for i in range(3)]
    entries = [graded("q0", 6), GradeEntry("q1", M), graded("q2", 8)]
    result = compute_grade(cats, assignments, entries)
    assert result.categories[0].dropped == ("q1",)
    assert result.percent == pytest.approx(70)


def test_drop_lowest_is_optimal_not_lowest_percent():
    """The docstring example: dropping the 45% item is worse than dropping the 50% item."""
    cats = [CategorySpec("hw", "Homework", 1, drop_lowest=1)]
    assignments = [
        AssignmentSpec("small", "hw", 10),
        AssignmentSpec("big", "hw", 100),
        AssignmentSpec("medium", "hw", 20),
    ]
    entries = [graded("small", 9), graded("big", 50), graded("medium", 9)]
    result = compute_grade(cats, assignments, entries)
    assert result.categories[0].dropped == ("big",)
    assert result.percent == pytest.approx(60)


def test_drop_never_removes_last_counted_item():
    cats = [CategorySpec("quiz", "Quizzes", 1, drop_lowest=5)]
    assignments = [AssignmentSpec("q0", "quiz", 10), AssignmentSpec("q1", "quiz", 10)]
    result = compute_grade(cats, assignments, [graded("q0", 3), graded("q1", 7)])
    assert result.categories[0].counted == ("q1",)
    assert result.percent == pytest.approx(70)


def test_excused_and_ungraded_are_not_drop_candidates():
    cats = [CategorySpec("quiz", "Quizzes", 1, drop_lowest=1)]
    assignments = [AssignmentSpec(f"q{i}", "quiz", 10) for i in range(4)]
    entries = [graded("q0", 5), graded("q1", 9), GradeEntry("q2", E)]
    result = compute_grade(cats, assignments, entries)
    assert result.categories[0].dropped == ("q0",)
    assert result.categories[0].excused == ("q2",)
    assert result.categories[0].ungraded == ("q3",)
    assert result.percent == pytest.approx(90)


def test_drop_ties_resolve_to_earliest_assignment():
    cats = [CategorySpec("quiz", "Quizzes", 1, drop_lowest=1)]
    assignments = [AssignmentSpec(f"q{i}", "quiz", 10) for i in range(3)]
    entries = [graded("q0", 9), graded("q1", 5), graded("q2", 5)]
    assert compute_grade(cats, assignments, entries).categories[0].dropped == ("q2",)


def _brute_force_best(items, keep):
    return max(_ratio(combo) for combo in itertools.combinations(items, keep))


@pytest.mark.parametrize("seed", range(300))
def test_best_kept_subset_matches_brute_force(seed):
    rng = random.Random(seed)
    n = rng.randint(1, 8)
    items = []
    for i in range(n):
        possible = Fraction(rng.choice([1, 5, 10, 20, 25, 50, 100, 150]))
        earned = Fraction(rng.randint(0, int(possible) * 11 // 10))
        items.append(_Item(i, earned, possible))
    keep = rng.randint(1, n)

    chosen = best_kept_subset(items, keep)
    assert len(chosen) == keep
    assert len({i.id for i in chosen}) == keep
    assert _ratio(chosen) == _brute_force_best(items, keep)


def test_best_kept_subset_rejects_bad_keep():
    items = [_Item("a", Fraction(1), Fraction(2))]
    with pytest.raises(ValueError):
        best_kept_subset(items, 0)
    with pytest.raises(ValueError):
        best_kept_subset(items, 2)


# --- validation -------------------------------------------------------------


def test_unknown_category_raises():
    with pytest.raises(ValueError, match="unknown category"):
        compute_grade([], [AssignmentSpec("a1", "nope", 10)], [])


def test_duplicate_entries_raise():
    cats = [CategorySpec("hw", "Homework", 1)]
    with pytest.raises(ValueError, match="Duplicate"):
        compute_grade(cats, [AssignmentSpec("a1", "hw", 10)], [graded("a1", 1), graded("a1", 2)])


@pytest.mark.parametrize(
    ("cats", "assignments", "entries"),
    [
        ([CategorySpec("hw", "HW", -1)], [], []),
        ([CategorySpec("hw", "HW", 1, drop_lowest=-1)], [], []),
        ([CategorySpec("hw", "HW", 1)], [AssignmentSpec("a1", "hw", 0)], []),
        ([CategorySpec("hw", "HW", 1)], [AssignmentSpec("a1", "hw", 10)], [graded("a1", -1)]),
    ],
)
def test_invalid_inputs_raise(cats, assignments, entries):
    with pytest.raises(ValueError):
        compute_grade(cats, assignments, entries)


# --- letters ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("percent", "letter"),
    [(100, "A"), (93, "A"), (92.99, "A-"), (89.5, "B+"), (60, "D-"), (59.99, "F"), (0, "F")],
)
def test_letter_boundaries(percent, letter):
    assert letter_for(percent) == letter


def test_custom_letter_scale():
    scale = [(50, "Pass"), (0, "Fail")]
    assert letter_for(50, scale) == "Pass"
    assert letter_for(49.9, scale) == "Fail"
