"""Grading categories (e.g. Tests 40%), created within a course."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Assignment, Category
from app.ownership import flush_or_conflict, get_owned_category, get_owned_course
from app.schemas import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(tags=["categories"])

DUPLICATE_NAME = "This course already has a category with that name"


@router.get("/courses/{course_id}/categories", response_model=list[CategoryRead])
def list_categories(
    course_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Category]:
    get_owned_course(db, user, course_id)
    stmt = select(Category).where(Category.course_id == course_id).order_by(Category.name)
    return list(db.scalars(stmt))


@router.post(
    "/courses/{course_id}/categories",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    course_id: uuid.UUID,
    payload: CategoryCreate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Category:
    get_owned_course(db, user, course_id)
    category = Category(course_id=course_id, **payload.model_dump())
    db.add(category)
    flush_or_conflict(db, DUPLICATE_NAME)
    return category


@router.get("/categories/{category_id}", response_model=CategoryRead)
def read_category(
    category_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Category:
    return get_owned_category(db, user, category_id)


@router.patch("/categories/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Category:
    category = get_owned_category(db, user, category_id)
    for key, value in payload.changes().items():
        setattr(category, key, value)
    flush_or_conflict(db, DUPLICATE_NAME)
    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Delete an empty category. Refuses (409) while assignments still use it,
    since the database would otherwise cascade away those assignments' grades."""
    category = get_owned_category(db, user, category_id)
    if db.scalar(select(exists().where(Assignment.category_id == category.id))):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category still has assignments; move or delete them first",
        )
    db.delete(category)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
