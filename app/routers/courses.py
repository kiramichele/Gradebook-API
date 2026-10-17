"""Courses and their rosters."""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Course, Enrollment, Student
from app.ownership import (
    get_or_create_teacher,
    get_owned_course,
    get_owned_students,
    not_found,
)
from app.roster import enroll, roster
from app.schemas import (
    CourseCreate,
    CourseRead,
    CourseUpdate,
    EnrollRequest,
    EnrollResult,
    StudentRead,
)

router = APIRouter(prefix="/courses", tags=["courses"])


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
    for key, value in payload.changes().items():
        setattr(course, key, value)
    db.flush()
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a course with its categories, assignments, enrollments and grades."""
    db.delete(get_owned_course(db, user, course_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- roster -----------------------------------------------------------------


@router.get("/{course_id}/students", response_model=list[StudentRead])
def list_roster(
    course_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Student]:
    get_owned_course(db, user, course_id)
    return roster(db, course_id)


@router.post("/{course_id}/enroll", response_model=EnrollResult)
def enroll_students(
    course_id: uuid.UUID,
    payload: EnrollRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnrollResult:
    """Enroll students. Idempotent: already-enrolled students are reported, not an error."""
    get_owned_course(db, user, course_id)
    students = get_owned_students(db, user, payload.student_ids)
    enrolled, already_enrolled = enroll(db, course_id, [s.id for s in students])
    return EnrollResult(
        enrolled=enrolled,
        already_enrolled=already_enrolled,
        roster=[StudentRead.model_validate(s) for s in roster(db, course_id)],
    )


@router.delete("/{course_id}/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def unenroll_student(
    course_id: uuid.UUID,
    student_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Remove a student from the roster. Their grades are kept and return if they re-enroll."""
    get_owned_course(db, user, course_id)
    enrollment = db.get(Enrollment, (course_id, student_id))
    if enrollment is None:
        raise not_found("Enrollment")
    db.delete(enrollment)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
