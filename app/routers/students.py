"""Students. Each teacher has their own roster; enroll them in courses via /courses."""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Student
from app.ownership import flush_or_conflict, get_or_create_teacher, get_owned_student
from app.schemas import StudentCreate, StudentRead, StudentUpdate

router = APIRouter(prefix="/students", tags=["students"])

DUPLICATE_EMAIL = "A student with this email already exists"


@router.get("", response_model=list[StudentRead])
def list_students(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Student]:
    stmt = select(Student).where(Student.teacher_id == user.id).order_by(Student.name, Student.id)
    return list(db.scalars(stmt))


@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Student:
    get_or_create_teacher(db, user)
    student = Student(teacher_id=user.id, **payload.model_dump())
    db.add(student)
    flush_or_conflict(db, DUPLICATE_EMAIL)
    db.refresh(student)
    return student


@router.get("/{student_id}", response_model=StudentRead)
def read_student(
    student_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Student:
    return get_owned_student(db, user, student_id)


@router.patch("/{student_id}", response_model=StudentRead)
def update_student(
    student_id: uuid.UUID,
    payload: StudentUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Student:
    student = get_owned_student(db, user, student_id)
    for key, value in payload.changes().items():
        setattr(student, key, value)
    flush_or_conflict(db, DUPLICATE_EMAIL)
    return student


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_student(
    student_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a student along with their enrollments and grades in every course."""
    db.delete(get_owned_student(db, user, student_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
