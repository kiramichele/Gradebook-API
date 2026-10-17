from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Teacher
from app.schemas import TeacherRead

router = APIRouter(prefix="/me", tags=["me"])


def get_or_create_teacher(db: Session, user: CurrentUser) -> Teacher:
    """Fallback for accounts created before the signup trigger existed."""
    teacher = db.get(Teacher, user.id)
    if teacher is None:
        name = (user.claims.get("user_metadata") or {}).get("name", "")
        teacher = Teacher(id=user.id, name=name)
        db.add(teacher)
        db.flush()
    return teacher


@router.get("", response_model=TeacherRead)
def read_me(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> TeacherRead:
    teacher = get_or_create_teacher(db, user)
    return TeacherRead(id=teacher.id, name=teacher.name, email=user.email)
