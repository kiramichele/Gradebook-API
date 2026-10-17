"""Roster operations shared by the enrollment and CSV import endpoints."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.csv_io import RosterRow
from app.models import Enrollment, Student


def roster(db: Session, course_id: uuid.UUID) -> list[Student]:
    stmt = (
        select(Student)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.course_id == course_id)
        .order_by(Student.name, Student.id)
    )
    return list(db.scalars(stmt))


def enroll(
    db: Session, course_id: uuid.UUID, student_ids: Sequence[uuid.UUID]
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """Enroll students the caller already owns. Returns (newly enrolled, already enrolled)."""
    ids = list(dict.fromkeys(student_ids))
    existing = set(
        db.scalars(
            select(Enrollment.student_id).where(
                Enrollment.course_id == course_id, Enrollment.student_id.in_(ids)
            )
        )
    )
    new_ids = [i for i in ids if i not in existing]
    db.add_all(Enrollment(course_id=course_id, student_id=i) for i in new_ids)
    db.flush()
    return new_ids, [i for i in ids if i in existing]


def import_students(
    db: Session, user: CurrentUser, rows: Sequence[RosterRow]
) -> tuple[list[Student], list[Student]]:
    """Create students from parsed rows. Returns (created, existing).

    A row whose email matches one of the teacher's students reuses that
    student (unchanged), so re-importing a roster doesn't duplicate anyone.
    Rows without an email always create a new student.
    """
    emails = [r.email for r in rows if r.email]
    by_email = {
        s.email: s
        for s in db.scalars(
            select(Student).where(Student.teacher_id == user.id, Student.email.in_(emails))
        )
    }
    created: list[Student] = []
    existing: list[Student] = []
    for row in rows:
        match = by_email.get(row.email) if row.email else None
        if match is not None:
            existing.append(match)
        else:
            student = Student(id=uuid.uuid4(), teacher_id=user.id, name=row.name, email=row.email)
            db.add(student)
            created.append(student)
    db.flush()
    return created, existing
