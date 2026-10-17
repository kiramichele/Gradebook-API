from enum import StrEnum


class GradeStatus(StrEnum):
    GRADED = "graded"
    MISSING = "missing"
    EXCUSED = "excused"
    LATE = "late"
