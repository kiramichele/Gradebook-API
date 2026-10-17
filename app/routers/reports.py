"""Read-only computed views: the course gradebook and per-student reports."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.gradebook import build_gradebook, build_student_report, points_earned
from app.grading import CategoryResult
from app.models import Enrollment
from app.ownership import get_owned_course, get_owned_student
from app.schemas import (
    AssignmentRead,
    CategoryGradeRead,
    CategoryRead,
    CellRead,
    CourseRead,
    GradebookRead,
    GradebookRowRead,
    Outcome,
    ReportAssignmentRead,
    ReportCategoryRead,
    ReportCourseRead,
    StudentRead,
    StudentReportRead,
)

router = APIRouter(tags=["reports"])


def _category_grade(result: CategoryResult) -> CategoryGradeRead:
    return CategoryGradeRead(
        category_id=result.category_id,
        percent=result.percent,
        earned=result.earned,
        possible=result.possible,
        effective_weight=result.effective_weight,
        dropped=list(result.dropped),
    )


def _outcome(result: CategoryResult, assignment_id: uuid.UUID) -> Outcome:
    if assignment_id in result.dropped:
        return "dropped"
    if assignment_id in result.excused:
        return "excused"
    if assignment_id in result.ungraded:
        return "ungraded"
    return "counted"


@router.get("/courses/{course_id}/gradebook", response_model=GradebookRead)
def read_gradebook(
    course_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GradebookRead:
    """Every enrolled student's grades and computed course grade."""
    gradebook = build_gradebook(db, get_owned_course(db, user, course_id))
    data = gradebook.data
    return GradebookRead(
        course=CourseRead.model_validate(data.course),
        categories=[CategoryRead.model_validate(c) for c in data.categories],
        assignments=[AssignmentRead.model_validate(a) for a in data.assignments],
        students=[
            GradebookRowRead(
                student=StudentRead.model_validate(row.student),
                percent=row.result.percent,
                letter=row.result.letter,
                categories=[_category_grade(c) for c in row.result.categories],
                grades={
                    aid: CellRead(score=g.score, status=g.status) for aid, g in row.grades.items()
                },
            )
            for row in gradebook.rows
        ],
    )


@router.get("/students/{student_id}/report", response_model=StudentReportRead)
def read_student_report(
    student_id: uuid.UUID,
    course_id: uuid.UUID | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StudentReportRead:
    """A student's grade breakdown for each course they're enrolled in.

    Pass `course_id` for a single course. Each assignment's `outcome` says
    how it was treated: counted, dropped (drop-lowest), excused, or ungraded.
    """
    student = get_owned_student(db, user, student_id)
    if course_id is not None:
        get_owned_course(db, user, course_id)
        if db.get(Enrollment, (course_id, student_id)) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student is not enrolled in this course",
            )

    courses = []
    for report in build_student_report(db, student, course_id):
        data = report.data
        results = {r.category_id: r for r in report.result.categories}
        categories = []
        for category in data.categories:
            result = results[category.id]
            assignments = []
            for assignment in data.assignments:
                if assignment.category_id != category.id:
                    continue
                grade = report.grades.get(assignment.id)
                assignments.append(
                    ReportAssignmentRead(
                        assignment=AssignmentRead.model_validate(assignment),
                        score=grade.score if grade else None,
                        status=grade.status if grade else None,
                        earned=None if assignment.id in result.dropped else points_earned(grade),
                        outcome=_outcome(result, assignment.id),
                    )
                )
            categories.append(
                ReportCategoryRead(
                    category=CategoryRead.model_validate(category),
                    percent=result.percent,
                    earned=result.earned,
                    possible=result.possible,
                    effective_weight=result.effective_weight,
                    assignments=assignments,
                )
            )
        courses.append(
            ReportCourseRead(
                course=CourseRead.model_validate(data.course),
                percent=report.result.percent,
                letter=report.result.letter,
                categories=categories,
            )
        )
    return StudentReportRead(student=StudentRead.model_validate(student), courses=courses)
