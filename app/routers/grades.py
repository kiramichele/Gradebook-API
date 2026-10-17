"""Grades for an assignment: bulk upsert, read, and clear."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Enrollment, Grade
from app.ownership import get_owned_assignment, not_found
from app.schemas import GradeRead, GradesUpsert

router = APIRouter(tags=["grades"])


def _insert_for(db: Session):
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql.insert
    if dialect == "sqlite":
        return sqlite.insert
    raise NotImplementedError(f"Grade upsert is not implemented for {dialect}")


def _grades_for(db: Session, assignment_id: uuid.UUID) -> list[Grade]:
    stmt = (
        select(Grade)
        .where(Grade.assignment_id == assignment_id)
        .order_by(Grade.student_id)
        .execution_options(populate_existing=True)
    )
    return list(db.scalars(stmt))


@router.put("/grades", response_model=list[GradeRead])
def upsert_grades(
    payload: GradesUpsert,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Grade]:
    """Create or replace grades for one assignment, all or nothing.

    Every student must be enrolled in the assignment's course. Returns all of
    the assignment's grades after the update.
    """
    assignment = get_owned_assignment(db, user, payload.assignment_id)
    student_ids = [g.student_id for g in payload.grades]
    enrolled = set(
        db.scalars(
            select(Enrollment.student_id).where(
                Enrollment.course_id == assignment.course_id,
                Enrollment.student_id.in_(student_ids),
            )
        )
    )
    not_enrolled = [str(i) for i in student_ids if i not in enrolled]
    if not_enrolled:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "Students not enrolled in this course", "student_ids": not_enrolled},
        )

    insert = _insert_for(db)
    stmt = insert(Grade).values(
        [
            {
                "assignment_id": assignment.id,
                "student_id": g.student_id,
                "score": g.score,
                "status": g.status,
            }
            for g in payload.grades
        ]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Grade.assignment_id, Grade.student_id],
        set_={
            "score": stmt.excluded.score,
            "status": stmt.excluded.status,
            "updated_at": func.now(),
        },
    )
    db.execute(stmt)
    return _grades_for(db, assignment.id)


@router.get("/assignments/{assignment_id}/grades", response_model=list[GradeRead])
def list_grades(
    assignment_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Grade]:
    get_owned_assignment(db, user, assignment_id)
    return _grades_for(db, assignment_id)


@router.delete(
    "/assignments/{assignment_id}/grades/{student_id}", status_code=status.HTTP_204_NO_CONTENT
)
def clear_grade(
    assignment_id: uuid.UUID,
    student_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Remove a grade so the assignment is ungraded for that student."""
    get_owned_assignment(db, user, assignment_id)
    grade = db.get(Grade, (assignment_id, student_id))
    if grade is None:
        raise not_found("Grade")
    db.delete(grade)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
