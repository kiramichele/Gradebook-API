import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    PlainSerializer,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.enums import GradeStatus

# Numeric columns arrive from the database as Decimal. Accept Decimal input
# (no float rounding on the way in) but emit JSON numbers rather than strings.
Num = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]

Weight = Annotated[Num, Field(ge=0, le=Decimal("999.999"), decimal_places=3)]
Points = Annotated[Num, Field(gt=0, le=Decimal("999999.99"), decimal_places=2)]
Score = Annotated[Num, Field(ge=0, le=Decimal("999999.99"), decimal_places=2)]
DropLowest = Annotated[int, Field(ge=0, le=100)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Term = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
Email = Annotated[
    EmailStr,
    BeforeValidator(lambda v: v.strip() if isinstance(v, str) else v),
    AfterValidator(str.lower),
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PatchModel(BaseModel):
    """Partial update. Omitted fields are left alone; null is only allowed where listed."""

    model_config = ConfigDict(extra="forbid")
    nullable: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def reject_nulls(self) -> Self:
        nulled = sorted(
            name
            for name in self.model_fields_set
            if getattr(self, name) is None and name not in self.nullable
        )
        if nulled:
            raise ValueError(f"Fields cannot be null: {', '.join(nulled)}")
        return self

    def changes(self) -> dict[str, object]:
        return self.model_dump(exclude_unset=True)


# --- teachers ---------------------------------------------------------------


class TeacherRead(ORMModel):
    id: uuid.UUID
    name: str
    email: str | None = None


# --- courses ----------------------------------------------------------------


class CourseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    term: Term = ""


class CourseUpdate(PatchModel):
    name: Name | None = None
    term: Term | None = None


class CourseRead(ORMModel):
    id: uuid.UUID
    teacher_id: uuid.UUID
    name: str
    term: str
    created_at: datetime | None = None


# --- students ---------------------------------------------------------------


class StudentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    email: Email | None = None


class StudentUpdate(PatchModel):
    nullable: ClassVar[frozenset[str]] = frozenset({"email"})

    name: Name | None = None
    email: Email | None = None


class StudentRead(ORMModel):
    id: uuid.UUID
    name: str
    email: str | None
    created_at: datetime | None = None


# --- enrollment -------------------------------------------------------------


class EnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)


class EnrollResult(BaseModel):
    enrolled: list[uuid.UUID]
    already_enrolled: list[uuid.UUID]
    roster: list[StudentRead]


# --- categories -------------------------------------------------------------


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    weight: Weight
    drop_lowest: DropLowest = 0


class CategoryUpdate(PatchModel):
    name: Name | None = None
    weight: Weight | None = None
    drop_lowest: DropLowest | None = None


class CategoryRead(ORMModel):
    id: uuid.UUID
    course_id: uuid.UUID
    name: str
    weight: Num
    drop_lowest: int


# --- assignments ------------------------------------------------------------


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID
    title: Name
    points_possible: Points
    due_date: date | None = None


class AssignmentUpdate(PatchModel):
    nullable: ClassVar[frozenset[str]] = frozenset({"due_date"})

    category_id: uuid.UUID | None = None
    title: Name | None = None
    points_possible: Points | None = None
    due_date: date | None = None


class AssignmentRead(ORMModel):
    id: uuid.UUID
    course_id: uuid.UUID
    category_id: uuid.UUID
    title: str
    points_possible: Num
    due_date: date | None
    created_at: datetime | None = None


# --- grades -----------------------------------------------------------------


class GradeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: uuid.UUID
    score: Score | None = None
    status: GradeStatus = GradeStatus.GRADED

    @model_validator(mode="after")
    def score_required_when_graded(self) -> Self:
        if self.status in (GradeStatus.GRADED, GradeStatus.LATE) and self.score is None:
            raise ValueError(f"score is required when status is {self.status.value!r}")
        return self


class GradesUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: uuid.UUID
    grades: list[GradeInput] = Field(min_length=1, max_length=1000)

    @field_validator("grades")
    @classmethod
    def unique_students(cls, grades: list[GradeInput]) -> list[GradeInput]:
        seen: set[uuid.UUID] = set()
        dupes: set[uuid.UUID] = set()
        for grade in grades:
            (dupes if grade.student_id in seen else seen).add(grade.student_id)
        if dupes:
            raise ValueError(f"Duplicate student_id: {', '.join(sorted(map(str, dupes)))}")
        return grades


class GradeRead(ORMModel):
    assignment_id: uuid.UUID
    student_id: uuid.UUID
    score: Num | None
    status: GradeStatus
    updated_at: datetime | None = None


# --- gradebook & reports ----------------------------------------------------


class CategoryGradeRead(BaseModel):
    category_id: uuid.UUID
    percent: float | None = Field(description="Category percent after drops; null if empty")
    earned: float
    possible: float
    effective_weight: float | None = Field(
        description="Share of the course grade (0-1) after redistributing empty categories"
    )
    dropped: list[uuid.UUID]


class CellRead(BaseModel):
    score: Num | None
    status: GradeStatus


class GradebookRowRead(BaseModel):
    student: StudentRead
    percent: float | None
    letter: str | None
    categories: list[CategoryGradeRead]
    grades: dict[uuid.UUID, CellRead] = Field(
        description="Keyed by assignment id. A missing key means not yet graded."
    )


class GradebookRead(BaseModel):
    course: CourseRead
    categories: list[CategoryRead]
    assignments: list[AssignmentRead]
    students: list[GradebookRowRead]


Outcome = Literal["counted", "dropped", "excused", "ungraded"]


class ReportAssignmentRead(BaseModel):
    assignment: AssignmentRead
    score: Num | None
    status: GradeStatus | None = Field(description="null if no grade has been entered")
    earned: float | None = Field(description="Points counted: 0 for missing, null if not counted")
    outcome: Outcome


class ReportCategoryRead(BaseModel):
    category: CategoryRead
    percent: float | None
    earned: float
    possible: float
    effective_weight: float | None
    assignments: list[ReportAssignmentRead]


class ReportCourseRead(BaseModel):
    course: CourseRead
    percent: float | None
    letter: str | None
    categories: list[ReportCategoryRead]


class StudentReportRead(BaseModel):
    student: StudentRead
    courses: list[ReportCourseRead]
