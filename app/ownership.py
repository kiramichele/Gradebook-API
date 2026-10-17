"""Look up rows the caller owns, or raise 404.

Every lookup filters on the owning teacher even though RLS already does, so
ownership is enforced in the API too (and in tests, which run on SQLite
without RLS). Another teacher's row is a 404, never a 403, so ids don't leak.
"""

import uuid
from collections.abc import Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.models import Assignment, Category, Course, Student, Teacher


def not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def get_or_create_teacher(db: Session, user: CurrentUser) -> Teacher:
    """Fallback for accounts created before the signup trigger existed."""
    teacher = db.get(Teacher, user.id)
    if teacher is None:
        name = (user.claims.get("user_metadata") or {}).get("name", "")
        teacher = Teacher(id=user.id, name=name)
        db.add(teacher)
        db.flush()
    return teacher


def get_owned_course(db: Session, user: CurrentUser, course_id: uuid.UUID) -> Course:
    course = db.scalar(select(Course).where(Course.id == course_id, Course.teacher_id == user.id))
    if course is None:
        raise not_found("Course")
    return course


def get_owned_student(db: Session, user: CurrentUser, student_id: uuid.UUID) -> Student:
    student = db.scalar(
        select(Student).where(Student.id == student_id, Student.teacher_id == user.id)
    )
    if student is None:
        raise not_found("Student")
    return student


def get_owned_students(
    db: Session, user: CurrentUser, student_ids: Iterable[uuid.UUID]
) -> list[Student]:
    """Return the students in request order, or 404 naming the ids that aren't the caller's."""
    ids = list(dict.fromkeys(student_ids))
    found = {
        s.id: s
        for s in db.scalars(
            select(Student).where(Student.id.in_(ids), Student.teacher_id == user.id)
        )
    }
    missing = [str(i) for i in ids if i not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Students not found", "student_ids": missing},
        )
    return [found[i] for i in ids]


def get_owned_category(db: Session, user: CurrentUser, category_id: uuid.UUID) -> Category:
    category = db.scalar(
        select(Category)
        .join(Course, Course.id == Category.course_id)
        .where(Category.id == category_id, Course.teacher_id == user.id)
    )
    if category is None:
        raise not_found("Category")
    return category


def get_owned_assignment(db: Session, user: CurrentUser, assignment_id: uuid.UUID) -> Assignment:
    assignment = db.scalar(
        select(Assignment)
        .join(Course, Course.id == Assignment.course_id)
        .where(Assignment.id == assignment_id, Course.teacher_id == user.id)
    )
    if assignment is None:
        raise not_found("Assignment")
    return assignment


def flush_or_conflict(db: Session, detail: str) -> None:
    """Flush pending changes, turning a unique-constraint violation into a 409."""
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
