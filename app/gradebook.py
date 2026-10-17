"""Load courses from the database and grade them with app.grading.

Each function issues a fixed number of queries regardless of how many
students or assignments are involved.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import GradeStatus
from app.grading import AssignmentSpec, CategorySpec, GradeEntry, GradeResult, compute_grade
from app.models import Assignment, Category, Course, Enrollment, Grade, Student


def category_order():
    return (Category.name, Category.id)


def assignment_order():
    """Due date first, undated last, then creation order."""
    return (
        Assignment.due_date.is_(None),
        Assignment.due_date,
        Assignment.created_at,
        Assignment.id,
    )


@dataclass
class CourseData:
    course: Course
    categories: list[Category] = field(default_factory=list)
    assignments: list[Assignment] = field(default_factory=list)

    def grade(self, grades: Iterable[Grade]) -> GradeResult:
        return compute_grade(
            [CategorySpec(c.id, c.name, c.weight, c.drop_lowest) for c in self.categories],
            [AssignmentSpec(a.id, a.category_id, a.points_possible) for a in self.assignments],
            [GradeEntry(g.assignment_id, g.status, g.score) for g in grades],
        )


def load_courses(db: Session, courses: list[Course]) -> dict[uuid.UUID, CourseData]:
    """Categories and assignments for several courses in two queries."""
    data = {c.id: CourseData(c) for c in courses}
    if not data:
        return data
    for category in db.scalars(
        select(Category).where(Category.course_id.in_(data)).order_by(*category_order())
    ):
        data[category.course_id].categories.append(category)
    for assignment in db.scalars(
        select(Assignment).where(Assignment.course_id.in_(data)).order_by(*assignment_order())
    ):
        data[assignment.course_id].assignments.append(assignment)
    return data


@dataclass
class GradebookRow:
    student: Student
    grades: dict[uuid.UUID, Grade]
    result: GradeResult


@dataclass
class Gradebook:
    data: CourseData
    rows: list[GradebookRow]


def build_gradebook(db: Session, course: Course) -> Gradebook:
    """The full grid: every enrolled student against every assignment."""
    data = load_courses(db, [course])[course.id]
    students = list(
        db.scalars(
            select(Student)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(Enrollment.course_id == course.id)
            .order_by(Student.name, Student.id)
        )
    )
    by_student: dict[uuid.UUID, dict[uuid.UUID, Grade]] = defaultdict(dict)
    if students and data.assignments:
        for grade in db.scalars(
            select(Grade)
            .join(Assignment, Assignment.id == Grade.assignment_id)
            .join(
                Enrollment,
                (Enrollment.student_id == Grade.student_id)
                & (Enrollment.course_id == Assignment.course_id),
            )
            .where(Assignment.course_id == course.id)
        ):
            by_student[grade.student_id][grade.assignment_id] = grade

    rows = [
        GradebookRow(s, by_student[s.id], data.grade(by_student[s.id].values())) for s in students
    ]
    return Gradebook(data, rows)


@dataclass
class CourseReport:
    data: CourseData
    grades: dict[uuid.UUID, Grade]
    result: GradeResult


def build_student_report(
    db: Session, student: Student, course_id: uuid.UUID | None = None
) -> list[CourseReport]:
    """One student's grade in each course they're enrolled in (or just `course_id`)."""
    stmt = (
        select(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(Enrollment.student_id == student.id)
        .order_by(Course.name, Course.id)
    )
    if course_id is not None:
        stmt = stmt.where(Course.id == course_id)
    data = load_courses(db, list(db.scalars(stmt)))

    grades: dict[uuid.UUID, dict[uuid.UUID, Grade]] = {cid: {} for cid in data}
    if data:
        for grade, cid in db.execute(
            select(Grade, Assignment.course_id)
            .join(Assignment, Assignment.id == Grade.assignment_id)
            .where(Grade.student_id == student.id, Assignment.course_id.in_(data))
        ):
            grades[cid][grade.assignment_id] = grade

    return [CourseReport(d, grades[cid], d.grade(grades[cid].values())) for cid, d in data.items()]


def points_earned(grade: Grade | None) -> float | None:
    """The points that count toward the grade: 0 for missing, none for excused or ungraded."""
    if grade is None or grade.status == GradeStatus.EXCUSED:
        return None
    if grade.status == GradeStatus.MISSING:
        return 0.0
    return float(grade.score) if grade.score is not None else None
