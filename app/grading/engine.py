"""Grade calculation engine.

Pure functions with no database or web dependencies, so the math can be
tested exhaustively on its own.

Rules
-----
For each student, each assignment falls into one of four buckets:

* counted:  status graded or late with a score, or status missing (counts as 0)
* excused:  status excused; removed from both numerator and denominator
* ungraded: no grade entry yet (or a graded/late entry with no score);
            ignored, so a grade reflects only work that has been assessed

Category percent = sum(earned) / sum(possible) over its counted assignments,
after dropping that category's lowest `drop_lowest` results. Drops never
remove the last counted assignment.

Course percent = weighted mean of category percents. A category with nothing
counted (all excused, ungraded, or empty) has no percent, and its weight is
redistributed across the remaining categories. Weights are relative and need
not sum to 100.

Arithmetic uses fractions.Fraction throughout so results are exact and ties
resolve the same way every time; floats appear only in the returned results.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from fractions import Fraction

from app.enums import GradeStatus

Number = int | float | Decimal | Fraction

DEFAULT_LETTER_SCALE: tuple[tuple[float, str], ...] = (
    (93, "A"),
    (90, "A-"),
    (87, "B+"),
    (83, "B"),
    (80, "B-"),
    (77, "C+"),
    (73, "C"),
    (70, "C-"),
    (67, "D+"),
    (63, "D"),
    (60, "D-"),
    (0, "F"),
)


@dataclass(frozen=True)
class CategorySpec:
    id: Hashable
    name: str
    weight: Number
    drop_lowest: int = 0


@dataclass(frozen=True)
class AssignmentSpec:
    id: Hashable
    category_id: Hashable
    points_possible: Number


@dataclass(frozen=True)
class GradeEntry:
    assignment_id: Hashable
    status: GradeStatus
    score: Number | None = None


@dataclass(frozen=True)
class CategoryResult:
    category_id: Hashable
    name: str
    weight: float
    earned: float
    possible: float
    percent: float | None
    counted: tuple[Hashable, ...]
    dropped: tuple[Hashable, ...]
    excused: tuple[Hashable, ...]
    ungraded: tuple[Hashable, ...]
    # Share of the course grade (0-1) after redistributing empty categories'
    # weight; None when the category doesn't contribute.
    effective_weight: float | None = None


@dataclass(frozen=True)
class GradeResult:
    percent: float | None
    letter: str | None
    categories: tuple[CategoryResult, ...]


@dataclass(frozen=True)
class _Item:
    id: Hashable
    earned: Fraction
    possible: Fraction


def to_fraction(value: Number) -> Fraction:
    """Convert exactly. Floats go through repr so 0.1 becomes 1/10, not 3602879701896397/2**55."""
    if isinstance(value, float):
        return Fraction(repr(value))
    return Fraction(value)


def _ratio(items: Iterable[_Item]) -> Fraction:
    items = list(items)
    return sum((i.earned for i in items), Fraction(0)) / sum(
        (i.possible for i in items), Fraction(0)
    )


def best_kept_subset(items: Sequence[_Item], keep: int) -> list[_Item]:
    """Return the `keep` items whose combined earned/possible ratio is largest.

    Dropping the lowest *percentages* is not optimal when assignments have
    different point values. For example, with 9/10 and 50/100 and 9/20 and one
    drop, dropping the lowest percent (9/20 = 45%) gives 59/110 = 53.6%, but
    dropping 50/100 gives 18/30 = 60%.

    This is Dinkelbach's method for fractional programming. For a target
    ratio q, define F(q) = max over size-`keep` subsets S of sum(e - q*p).
    F(q) is found greedily by taking the `keep` largest values of e - q*p.
    F(q) >= 0 exactly when some subset reaches ratio q, so starting from any
    subset's ratio we repeatedly jump to the greedy subset's ratio until
    F(q) = 0. Each jump strictly increases q and there are finitely many
    subsets, so it terminates; in practice it takes only a few iterations.
    """
    if not 0 < keep <= len(items):
        raise ValueError(f"keep must be between 1 and {len(items)}, got {keep}")

    order = {item.id: index for index, item in enumerate(items)}
    chosen = sorted(items, key=lambda i: (-(i.earned / i.possible), order[i.id]))[:keep]
    q = _ratio(chosen)
    while True:
        candidate = sorted(items, key=lambda i: (-(i.earned - q * i.possible), order[i.id]))[:keep]
        if sum((i.earned - q * i.possible for i in candidate), Fraction(0)) <= 0:
            return sorted(chosen, key=lambda i: order[i.id])
        chosen = candidate
        q = _ratio(chosen)


def letter_for(percent: float | None, scale: Sequence[tuple[float, str]] = DEFAULT_LETTER_SCALE):
    if percent is None:
        return None
    for minimum, letter in scale:
        if percent >= minimum:
            return letter
    return scale[-1][1]


def _category_result(
    category: CategorySpec,
    assignments: Sequence[AssignmentSpec],
    entries: dict[Hashable, GradeEntry],
) -> tuple[CategoryResult, Fraction | None]:
    counted: list[_Item] = []
    excused: list[Hashable] = []
    ungraded: list[Hashable] = []

    for assignment in assignments:
        possible = to_fraction(assignment.points_possible)
        if possible <= 0:
            raise ValueError(f"Assignment {assignment.id!r} must have positive points_possible")
        entry = entries.get(assignment.id)
        if entry is None:
            ungraded.append(assignment.id)
        elif entry.status == GradeStatus.EXCUSED:
            excused.append(assignment.id)
        elif entry.status == GradeStatus.MISSING:
            counted.append(_Item(assignment.id, Fraction(0), possible))
        elif entry.score is None:
            ungraded.append(assignment.id)
        else:
            score = to_fraction(entry.score)
            if score < 0:
                raise ValueError(f"Score for {assignment.id!r} must be non-negative")
            counted.append(_Item(assignment.id, score, possible))

    if category.drop_lowest < 0:
        raise ValueError(f"Category {category.id!r} has negative drop_lowest")

    kept = counted
    if counted:
        drops = min(category.drop_lowest, len(counted) - 1)
        kept = best_kept_subset(counted, len(counted) - drops)
    kept_ids = {i.id for i in kept}

    earned = sum((i.earned for i in kept), Fraction(0))
    possible = sum((i.possible for i in kept), Fraction(0))
    exact_percent = 100 * earned / possible if kept else None

    result = CategoryResult(
        category_id=category.id,
        name=category.name,
        weight=float(to_fraction(category.weight)),
        earned=float(earned),
        possible=float(possible),
        percent=float(exact_percent) if exact_percent is not None else None,
        counted=tuple(i.id for i in kept),
        dropped=tuple(i.id for i in counted if i.id not in kept_ids),
        excused=tuple(excused),
        ungraded=tuple(ungraded),
    )
    return result, exact_percent


def compute_grade(
    categories: Sequence[CategorySpec],
    assignments: Sequence[AssignmentSpec],
    entries: Iterable[GradeEntry],
    letter_scale: Sequence[tuple[float, str]] = DEFAULT_LETTER_SCALE,
) -> GradeResult:
    """Compute one student's course grade."""
    by_assignment: dict[Hashable, GradeEntry] = {}
    for entry in entries:
        if entry.assignment_id in by_assignment:
            raise ValueError(f"Duplicate grade entry for assignment {entry.assignment_id!r}")
        by_assignment[entry.assignment_id] = entry

    by_category: dict[Hashable, list[AssignmentSpec]] = {c.id: [] for c in categories}
    for assignment in assignments:
        if assignment.category_id not in by_category:
            raise ValueError(
                f"Assignment {assignment.id!r} references unknown category "
                f"{assignment.category_id!r}"
            )
        by_category[assignment.category_id].append(assignment)

    results: list[tuple[CategoryResult, Fraction | None]] = []
    weighted_sum = Fraction(0)
    weight_total = Fraction(0)
    for category in categories:
        weight = to_fraction(category.weight)
        if weight < 0:
            raise ValueError(f"Category {category.id!r} has negative weight")
        result, percent = _category_result(category, by_category[category.id], by_assignment)
        contributes = percent is not None and weight > 0
        results.append((result, weight if contributes else None))
        if contributes:
            weighted_sum += weight * percent
            weight_total += weight

    percent = float(weighted_sum / weight_total) if weight_total else None
    return GradeResult(
        percent=percent,
        letter=letter_for(percent, letter_scale),
        categories=tuple(
            replace(result, effective_weight=float(weight / weight_total))
            if weight is not None
            else result
            for result, weight in results
        ),
    )
