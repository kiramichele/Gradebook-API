from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.ownership import get_or_create_teacher
from app.schemas import TeacherRead

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=TeacherRead)
def read_me(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> TeacherRead:
    teacher = get_or_create_teacher(db, user)
    return TeacherRead(id=teacher.id, name=teacher.name, email=user.email)
