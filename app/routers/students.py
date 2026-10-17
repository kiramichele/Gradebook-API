"""Students. Each teacher has their own roster; enroll them in courses via /courses."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.csv_io import CSVError, parse_roster
from app.db import get_db
from app.models import Student
from app.ownership import (
    flush_or_conflict,
    get_or_create_teacher,
    get_owned_course,
    get_owned_student,
)
from app.roster import enroll, import_students
from app.schemas import RosterImportResult, StudentCreate, StudentRead, StudentUpdate

router = APIRouter(prefix="/students", tags=["students"])

DUPLICATE_EMAIL = "A student with this email already exists"
MAX_UPLOAD_BYTES = 2_000_000


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


@router.post("/import", response_model=RosterImportResult)
def import_roster(
    file: UploadFile = File(
        description="CSV with a name column (or first/last) and optional email"
    ),
    course_id: uuid.UUID | None = Query(None, description="Also enroll everyone in this course"),
    dry_run: bool = Query(False, description="Validate and preview without saving"),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RosterImportResult:
    """Import students from a CSV roster, optionally enrolling them in a course.

    All or nothing: any bad row rejects the file with a 422 listing every
    problem by line. Rows whose email matches an existing student reuse that
    student, so importing the same roster twice creates no duplicates.
    """
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File is over {MAX_UPLOAD_BYTES // 1_000_000} MB",
        )
    try:
        rows = parse_roster(data)
    except CSVError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "Roster has errors; nothing was imported", "errors": exc.errors},
        ) from exc

    if course_id is not None:
        get_owned_course(db, user, course_id)
    get_or_create_teacher(db, user)
    created, existing = import_students(db, user, rows)
    enrolled: list[uuid.UUID] = []
    already_enrolled: list[uuid.UUID] = []
    if course_id is not None:
        enrolled, already_enrolled = enroll(db, course_id, [s.id for s in created + existing])

    result = RosterImportResult(
        dry_run=dry_run,
        created=[StudentRead.model_validate(s) for s in created],
        existing=[StudentRead.model_validate(s) for s in existing],
        enrolled=enrolled,
        already_enrolled=already_enrolled,
    )
    if dry_run:
        db.rollback()
    return result


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
