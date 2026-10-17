"""CSV parsing for roster import and formatting for gradebook export."""

import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal

from pydantic import TypeAdapter, ValidationError

from app.enums import GradeStatus
from app.gradebook import Gradebook
from app.schemas import Email

MAX_ROWS = 5000
MAX_NAME_LENGTH = 200

HEADER_ALIASES = {
    "name": {"name", "student", "student_name", "full_name"},
    "first_name": {"first_name", "first", "given_name"},
    "last_name": {"last_name", "last", "surname", "family_name"},
    "email": {"email", "email_address", "e_mail", "student_email"},
}

_email = TypeAdapter(Email)


@dataclass(frozen=True)
class RosterRow:
    line: int
    name: str
    email: str | None


class CSVError(ValueError):
    def __init__(self, errors: list[dict[str, object]]):
        super().__init__(f"{len(errors)} problem(s) in CSV")
        self.errors = errors


def decode(data: bytes) -> str:
    """UTF-8 (with or without BOM), falling back to Windows-1252, Excel's default."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _normalize_header(header: str) -> str:
    return re.sub(r"[\s\-]+", "_", header.strip().lower())


def parse_roster(data: bytes) -> list[RosterRow]:
    """Parse a roster with a `name` column (or `first_name` and `last_name`) and optional `email`.

    All-or-nothing: raises CSVError listing every problem by line number.
    """
    reader = csv.reader(io.StringIO(decode(data)))
    try:
        headers = next(reader)
    except StopIteration:
        raise CSVError([{"line": 1, "error": "File is empty"}]) from None
    except csv.Error as exc:
        raise CSVError([{"line": 1, "error": f"Malformed CSV: {exc}"}]) from None

    columns: dict[str, int] = {}
    for index, header in enumerate(headers):
        normalized = _normalize_header(header)
        for field, aliases in HEADER_ALIASES.items():
            if normalized in aliases and field not in columns:
                columns[field] = index
    if "name" not in columns and not {"first_name", "last_name"} <= columns.keys():
        raise CSVError(
            [{"line": 1, "error": "Need a 'name' column, or 'first_name' and 'last_name' columns"}]
        )

    def cell(row: list[str], field: str) -> str:
        index = columns.get(field)
        return row[index].strip() if index is not None and index < len(row) else ""

    rows: list[RosterRow] = []
    errors: list[dict[str, object]] = []
    first_line_by_email: dict[str, int] = {}
    try:
        for row in reader:
            line = reader.line_num
            if not any(value.strip() for value in row):
                continue
            if len(rows) + len(errors) >= MAX_ROWS:
                errors.append({"line": line, "error": f"More than {MAX_ROWS} rows"})
                break

            name = cell(row, "name") or " ".join(
                part for part in (cell(row, "first_name"), cell(row, "last_name")) if part
            )
            if not name:
                errors.append({"line": line, "error": "Name is required"})
                continue
            if len(name) > MAX_NAME_LENGTH:
                errors.append({"line": line, "error": f"Name is over {MAX_NAME_LENGTH} characters"})
                continue

            email = cell(row, "email") or None
            if email is not None:
                try:
                    email = _email.validate_python(email)
                except ValidationError:
                    errors.append({"line": line, "error": f"Invalid email: {email}"})
                    continue
                if email in first_line_by_email:
                    errors.append(
                        {
                            "line": line,
                            "error": f"Duplicate email {email} "
                            f"(first seen on line {first_line_by_email[email]})",
                        }
                    )
                    continue
                first_line_by_email[email] = line
            rows.append(RosterRow(line, name, email))
    except csv.Error as exc:
        errors.append({"line": reader.line_num, "error": f"Malformed CSV: {exc}"})

    if errors:
        raise CSVError(errors)
    if not rows:
        raise CSVError([{"line": 2, "error": "No students found"}])
    return rows


# --- export ------------------------------------------------------------------

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_text(value: str) -> str:
    """Stop spreadsheets from running a cell as a formula (CSV injection)."""
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def format_number(value: Decimal | float) -> str:
    """10.00 -> "10", 12.50 -> "12.5"."""
    return format(Decimal(str(value)).normalize(), "f")


def format_percent(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def gradebook_csv(gradebook: Gradebook) -> str:
    """One row per student: assignment scores, category percents, course percent, letter.

    Starts with a UTF-8 BOM so Excel detects the encoding. Missing and
    excused grades are written as words; ungraded cells are empty.
    """
    data = gradebook.data
    out = io.StringIO()
    out.write("\ufeff")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(
        [
            "Student",
            "Email",
            *(
                safe_text(f"{a.title} ({format_number(a.points_possible)} pts)")
                for a in data.assignments
            ),
            *(safe_text(f"{c.name} %") for c in data.categories),
            "Course %",
            "Letter",
        ]
    )
    for row in gradebook.rows:
        cells = []
        for assignment in data.assignments:
            grade = row.grades.get(assignment.id)
            if grade is None:
                cells.append("")
            elif grade.status in (GradeStatus.MISSING, GradeStatus.EXCUSED):
                cells.append(grade.status.value)
            else:
                cells.append(format_number(grade.score))
        category_results = {r.category_id: r for r in row.result.categories}
        writer.writerow(
            [
                safe_text(row.student.name),
                safe_text(row.student.email or ""),
                *cells,
                *(format_percent(category_results[c.id].percent) for c in data.categories),
                format_percent(row.result.percent),
                row.result.letter or "",
            ]
        )
    return out.getvalue()
