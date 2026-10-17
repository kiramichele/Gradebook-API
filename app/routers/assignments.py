"""Assignments, created within a course and filed under one of its categories."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.gradebook import assignment_order
from app.models import Assignment, Category
from app.ownership import get_owned_assignment, get_owned_course
from app.schemas import AssignmentCreate, AssignmentRead, AssignmentUpdate

router = APIRouter(tags=["assignments"])


def require_course_category(db: Session, course_id: uuid.UUID, category_id: uuid.UUID) -> None:
    category = db.get(Category, category_id)
    if category is None or category.course_id != course_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="category_id must be a category in this course",
        )


@router.get("/courses/{course_id}/assignments", response_model=list[AssignmentRead])
def list_assignments(
    course_id: uuid.UUID,
    category_id: uuid.UUID | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Assignment]:
    """List a course's assignments by due date (undated last), optionally for one category."""
    get_owned_course(db, user, course_id)
    stmt = select(Assignment).where(Assignment.course_id == course_id)
    if category_id is not None:
        stmt = stmt.where(Assignment.category_id == category_id)
    stmt = stmt.order_by(*assignment_order())
    return list(db.scalars(stmt))


@router.post(
    "/courses/{course_id}/assignments",
    response_model=AssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_assignment(
    course_id: uuid.UUID,
    payload: AssignmentCreate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Assignment:
    get_owned_course(db, user, course_id)
    require_course_category(db, course_id, payload.category_id)
    assignment = Assignment(course_id=course_id, **payload.model_dump())
    db.add(assignment)
    db.flush()
    db.refresh(assignment)
    return assignment


@router.get("/assignments/{assignment_id}", response_model=AssignmentRead)
def read_assignment(
    assignment_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Assignment:
    return get_owned_assignment(db, user, assignment_id)


@router.patch("/assignments/{assignment_id}", response_model=AssignmentRead)
def update_assignment(
    assignment_id: uuid.UUID,
    payload: AssignmentUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Assignment:
    assignment = get_owned_assignment(db, user, assignment_id)
    changes = payload.changes()
    if "category_id" in changes:
        require_course_category(db, assignment.course_id, changes["category_id"])
    for key, value in changes.items():
        setattr(assignment, key, value)
    db.flush()
    return assignment


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Delete an assignment and all of its grades."""
    db.delete(get_owned_assignment(db, user, assignment_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
