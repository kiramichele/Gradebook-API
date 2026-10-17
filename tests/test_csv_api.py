import csv
import io

import pytest

from app.routers import students as students_router


def upload(api, text: str | bytes, **params):
    data = text.encode() if isinstance(text, str) else text
    return api.post(
        "/students/import", files={"file": ("roster.csv", data, "text/csv")}, params=params
    )


ROSTER = "Name,Email\nAda Lovelace,ada@example.edu\nAlan Turing,alan@example.edu\nNo Email,\n"


# --- import --------------------------------------------------------------------


def test_import_creates_students(teacher):
    response = upload(teacher, ROSTER)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["dry_run"] is False
    assert [s["name"] for s in result["created"]] == ["Ada Lovelace", "Alan Turing", "No Email"]
    assert result["existing"] == result["enrolled"] == result["already_enrolled"] == []
    assert len(teacher.get("/students").json()) == 3


def test_import_and_enroll(teacher):
    course = teacher.course()
    result = upload(teacher, ROSTER, course_id=course["id"]).json()
    assert len(result["enrolled"]) == 3
    roster = teacher.get(f"/courses/{course['id']}/students").json()
    assert {s["name"] for s in roster} == {"Ada Lovelace", "Alan Turing", "No Email"}


def test_reimport_matches_by_email(teacher):
    course = teacher.course()
    first = upload(teacher, ROSTER, course_id=course["id"]).json()
    second = upload(teacher, ROSTER.replace("ada@", "ADA@"), course_id=course["id"]).json()

    # Emailed students are matched; the email-less row can't be, so it's new.
    assert {s["name"] for s in second["existing"]} == {"Ada Lovelace", "Alan Turing"}
    assert [s["name"] for s in second["created"]] == ["No Email"]
    assert len(second["already_enrolled"]) == 2
    ada_id = next(s["id"] for s in first["created"] if s["name"] == "Ada Lovelace")
    assert ada_id in {s["id"] for s in second["existing"]}


def test_import_matches_students_added_by_hand(teacher):
    existing = teacher.student("Ada K.", "ada@example.edu")
    result = upload(teacher, ROSTER).json()
    assert result["existing"] == [{**existing, "created_at": result["existing"][0]["created_at"]}]
    assert result["existing"][0]["name"] == "Ada K."  # not overwritten


def test_dry_run_saves_nothing(teacher):
    course = teacher.course()
    result = upload(teacher, ROSTER, course_id=course["id"], dry_run="true").json()
    assert result["dry_run"] is True
    assert len(result["created"]) == 3
    assert len(result["enrolled"]) == 3
    assert teacher.get("/students").json() == []
    assert teacher.get(f"/courses/{course['id']}/students").json() == []


def test_bad_rows_reject_whole_file(teacher):
    response = upload(teacher, "name,email\nOk,ok@example.edu\n,missing@example.edu\nX,bad\n")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["message"] == "Roster has errors; nothing was imported"
    assert [e["line"] for e in detail["errors"]] == [3, 4]
    assert teacher.get("/students").json() == []


def test_import_into_other_teachers_course_is_404(teacher, other_teacher):
    theirs = other_teacher.course()
    assert upload(teacher, ROSTER, course_id=theirs["id"]).status_code == 404
    assert teacher.get("/students").json() == []
    assert other_teacher.get(f"/courses/{theirs['id']}/students").json() == []


def test_import_requires_a_file(teacher):
    assert teacher.post("/students/import").status_code == 422


def test_import_too_large(teacher, monkeypatch):
    monkeypatch.setattr(students_router, "MAX_UPLOAD_BYTES", 50)
    assert upload(teacher, ROSTER + "x" * 100).status_code == 413


def test_import_requires_auth(client):
    files = {"file": ("r.csv", ROSTER.encode(), "text/csv")}
    assert client.post("/students/import", files=files).status_code == 401


# --- export --------------------------------------------------------------------


@pytest.fixture
def course(teacher):
    course = teacher.course("Bio 101", "Fall 2026")
    labs = teacher.category(course["id"], "Labs", weight=60)
    tests = teacher.category(course["id"], "Tests", weight=40)
    lab1 = teacher.assignment(
        course["id"], labs["id"], "Lab 1", points="12.5", due_date="2026-09-01"
    )
    lab2 = teacher.assignment(course["id"], labs["id"], "Lab 2", points=10, due_date="2026-09-08")
    test1 = teacher.assignment(
        course["id"], tests["id"], "=Test 1", points=100, due_date="2026-10-01"
    )
    ada = teacher.student("Ada", "ada@example.edu")
    evil = teacher.student("=cmd|' /C calc'!A0", "evil@example.edu")
    teacher.enroll(course["id"], ada["id"], evil["id"])

    def put(assignment, *grades):
        teacher.put("/grades", json={"assignment_id": assignment["id"], "grades": list(grades)})

    put(
        lab1,
        {"student_id": ada["id"], "score": "12.5"},
        {"student_id": evil["id"], "status": "missing"},
    )
    put(lab2, {"student_id": ada["id"], "status": "excused"})
    put(test1, {"student_id": ada["id"], "score": 81, "status": "late"})
    return course


def export(teacher, course):
    response = teacher.get(f"/courses/{course['id']}/gradebook/export")
    assert response.status_code == 200, response.text
    return response


def test_export_headers(teacher, course):
    response = export(teacher, course)
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="bio-101-fall-2026.csv"'
    assert response.content.startswith(b"\xef\xbb\xbf")


def test_export_content(teacher, course):
    rows = list(csv.reader(io.StringIO(export(teacher, course).content.decode("utf-8-sig"))))
    assert rows[0] == [
        "Student",
        "Email",
        "Lab 1 (12.5 pts)",
        "Lab 2 (10 pts)",
        "'=Test 1 (100 pts)",
        "Labs %",
        "Tests %",
        "Course %",
        "Letter",
    ]
    by_name = {row[0]: row for row in rows[1:]}
    # Ada: Labs 12.5/12.5 (Lab 2 excused) = 100%, Tests 81%. 0.6*100 + 0.4*81 = 92.4
    assert by_name["Ada"] == [
        "Ada", "ada@example.edu", "12.5", "excused", "81", "100.00", "81.00", "92.40", "A-",
    ]  # fmt: skip
    # Formula-looking names are escaped; ungraded cells are empty.
    evil = by_name["'=cmd|' /C calc'!A0"]
    assert evil[2:5] == ["missing", "", ""]
    assert evil[5:] == ["0.00", "", "0.00", "F"]


def test_export_empty_course(teacher):
    course = teacher.course("Empty")
    text = export(teacher, course).content.decode("utf-8-sig")
    assert text == "Student,Email,Course %,Letter\r\n"


def test_exported_gradebook_reimports_as_roster(teacher, course):
    """The export's Student and Email columns are a valid roster for another course."""
    exported = export(teacher, course).content
    spring = teacher.course("Bio 102")
    result = upload(teacher, exported, course_id=spring["id"]).json()
    assert result["created"] == []
    # Matched by email, so the stored name comes back without the export's escaping.
    assert {s["name"] for s in result["existing"]} == {"Ada", "=cmd|' /C calc'!A0"}
    assert len(result["enrolled"]) == 2
