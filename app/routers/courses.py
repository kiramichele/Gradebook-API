"""Course CRUD.

Queries filter on teacher_id even though RLS already does, so ownership is
enforced in the API too (and in tests, which run on SQLite without RLS).
Another teacher's course is a 404, never a 403, so ids don't leak.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Course
from app.routers.me import get_or_create_teacher
from app.schemas import CourseCreate, CourseRead, CourseUpdate

router = APIRouter(prefix="/courses", tags=["courses"])


def get_owned_course(db: Session, user: CurrentUser, course_id: uuid.UUID) -> Course:
    course = db.scalar(select(Course).where(Course.id == course_id, Course.teacher_id == user.id))
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


@router.get("", response_model=list[CourseRead])
def list_courses(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Course]:
    stmt = select(Course).where(Course.teacher_id == user.id).order_by(Course.name)
    return list(db.scalars(stmt))


@router.post("", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Course:
    get_or_create_teacher(db, user)
    course = Course(teacher_id=user.id, **payload.model_dump())
    db.add(course)
    db.flush()
    db.refresh(course)
    return course


@router.get("/{course_id}", response_model=CourseRead)
def read_course(
    course_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Course:
    return get_owned_course(db, user, course_id)


@router.patch("/{course_id}", response_model=CourseRead)
def update_course(
    course_id: uuid.UUID,
    payload: CourseUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Course:
    course = get_owned_course(db, user, course_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(course, key, value)
    db.flush()
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    db.delete(get_owned_course(db, user, course_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
