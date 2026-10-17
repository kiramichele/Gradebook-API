import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TeacherRead(ORMModel):
    id: uuid.UUID
    name: str
    email: str | None = None


class CourseBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    term: str = Field(default="", max_length=100)


class CourseCreate(CourseBase):
    pass


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    term: str | None = Field(default=None, max_length=100)


class CourseRead(ORMModel, CourseBase):
    id: uuid.UUID
    teacher_id: uuid.UUID
    created_at: datetime | None = None
