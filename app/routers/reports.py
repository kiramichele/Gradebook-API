"""Read-only computed views: gradebook, student reports, CSV export, assignment stats."""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.csv_io import gradebook_csv
from app.db import get_db
from app.enums import GradeStatus
from app.gradebook import build_gradebook, build_student_report, points_earned
from app.grading import CategoryResult
from app.grading.stats import score_stats
from app.models import Enrollment, Grade
from app.ownership import get_owned_assignment, get_owned_course, get_owned_student
from app.schemas import (
    AssignmentRead,
    AssignmentStatsRead,
    BinRead,
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

SCORED = (GradeStatus.GRADED, GradeStatus.LATE)
VALID_BIN_WIDTHS = frozenset(w for w in range(1, 101) if 100 % w == 0)


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


@router.get("/courses/{course_id}/gradebook/export", response_class=Response)
def export_gradebook(
    course_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """The gradebook as a CSV file, one row per student."""
    course = get_owned_course(db, user, course_id)
    content = gradebook_csv(build_gradebook(db, course))
    slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{course.name} {course.term}").strip("-").lower()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{slug or "gradebook"}.csv"'},
    )


@router.get("/assignments/{assignment_id}/stats", response_model=AssignmentStatsRead)
def read_assignment_stats(
    assignment_id: uuid.UUID,
    include_missing: bool = Query(False, description="Count missing work as 0 in the stats"),
    bin_width: int = Query(10, description="Histogram bin width in percent; must divide 100"),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssignmentStatsRead:
    """Mean, median, standard deviation and score distribution for enrolled students.

    Excused and ungraded students are always left out. Missing work is left
    out by default, since a 0 for work never turned in describes effort
    more than how well the class understood the material.
    """
    if bin_width not in VALID_BIN_WIDTHS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"bin_width must be one of {sorted(VALID_BIN_WIDTHS)}",
        )
    assignment = get_owned_assignment(db, user, assignment_id)
    enrolled = db.scalar(select(func.count()).where(Enrollment.course_id == assignment.course_id))
    grades = list(
        db.scalars(
            select(Grade)
            .join(
                Enrollment,
                (Enrollment.student_id == Grade.student_id)
                & (Enrollment.course_id == assignment.course_id),
            )
            .where(Grade.assignment_id == assignment.id)
        )
    )
    scored = [g.score for g in grades if g.status in SCORED and g.score is not None]
    missing = sum(g.status == GradeStatus.MISSING for g in grades)
    excused = sum(g.status == GradeStatus.EXCUSED for g in grades)
    values = scored + [0] * missing if include_missing else scored
    stats = score_stats(values, assignment.points_possible, bin_width)

    return AssignmentStatsRead(
        assignment_id=assignment.id,
        points_possible=assignment.points_possible,
        include_missing=include_missing,
        enrolled=enrolled,
        graded=len(scored),
        missing=missing,
        excused=excused,
        ungraded=enrolled - len(scored) - missing - excused,
        count=stats.count,
        mean=stats.mean,
        median=stats.median,
        std_dev=stats.std_dev,
        min=stats.min,
        max=stats.max,
        mean_percent=stats.mean_percent,
        median_percent=stats.median_percent,
        histogram=[BinRead(lower=b.lower, upper=b.upper, count=b.count) for b in stats.histogram],
        letters=stats.letters,
    )
