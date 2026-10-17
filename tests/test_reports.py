"""The gradebook grid and student reports, end to end through the API.

The grading math itself is covered in test_grading.py; these check that the
database rows reach the engine correctly and come back in the right shape.
"""

import pytest


@pytest.fixture
def course(teacher):
    """Tests 40% (one test), Homework 35% (two, drop lowest 1), Quizzes 25% (none graded)."""
    course = teacher.course("Chemistry")
    tests = teacher.category(course["id"], "Tests", weight=40)
    hw = teacher.category(course["id"], "Homework", weight=35, drop_lowest=1)
    quizzes = teacher.category(course["id"], "Quizzes", weight=25)
    t1 = teacher.assignment(course["id"], tests["id"], "Test 1", points=100, due_date="2026-10-01")
    h1 = teacher.assignment(course["id"], hw["id"], "HW 1", points=10, due_date="2026-09-01")
    h2 = teacher.assignment(course["id"], hw["id"], "HW 2", points=10, due_date="2026-09-08")
    q1 = teacher.assignment(course["id"], quizzes["id"], "Quiz 1", points=20)
    ana, ben = teacher.student("Ana"), teacher.student("Ben")
    teacher.enroll(course["id"], ana["id"], ben["id"])

    def put(assignment, *grades):
        response = teacher.put(
            "/grades", json={"assignment_id": assignment["id"], "grades": list(grades)}
        )
        assert response.status_code == 200, response.text

    put(t1, {"student_id": ana["id"], "score": 80}, {"student_id": ben["id"], "status": "excused"})
    put(h1, {"student_id": ana["id"], "score": 10}, {"student_id": ben["id"], "score": 6})
    put(h2, {"student_id": ana["id"], "status": "missing"})
    return {
        "course": course,
        "categories": {"tests": tests, "hw": hw, "quizzes": quizzes},
        "assignments": {"t1": t1, "h1": h1, "h2": h2, "q1": q1},
        "students": {"ana": ana, "ben": ben},
    }


def ids(rows):
    return [row["id"] for row in rows]


# --- gradebook ---------------------------------------------------------------


def test_gradebook_shape(teacher, course):
    book = teacher.get(f"/courses/{course['course']['id']}/gradebook").json()
    a, c = course["assignments"], course["categories"]

    assert book["course"]["id"] == course["course"]["id"]
    assert ids(book["categories"]) == [c["hw"]["id"], c["quizzes"]["id"], c["tests"]["id"]]
    assert ids(book["assignments"]) == [a["h1"]["id"], a["h2"]["id"], a["t1"]["id"], a["q1"]["id"]]
    assert [row["student"]["name"] for row in book["students"]] == ["Ana", "Ben"]


def test_gradebook_grades_and_math(teacher, course):
    book = teacher.get(f"/courses/{course['course']['id']}/gradebook").json()
    a, c = course["assignments"], course["categories"]
    ana, ben = book["students"]

    assert ana["grades"] == {
        a["t1"]["id"]: {"score": 80.0, "status": "graded"},
        a["h1"]["id"]: {"score": 10.0, "status": "graded"},
        a["h2"]["id"]: {"score": None, "status": "missing"},
    }
    # Homework drops the missing HW 2 -> 100%. Quizzes are empty, so Tests and
    # Homework split the course 40:35. (40*80 + 35*100) / 75
    assert ana["percent"] == pytest.approx(6700 / 75)
    assert ana["letter"] == "B+"
    by_category = {cat["category_id"]: cat for cat in ana["categories"]}
    assert by_category[c["hw"]["id"]]["dropped"] == [a["h2"]["id"]]
    assert by_category[c["hw"]["id"]]["percent"] == 100
    assert by_category[c["tests"]["id"]]["effective_weight"] == pytest.approx(40 / 75)
    assert by_category[c["quizzes"]["id"]]["percent"] is None
    assert by_category[c["quizzes"]["id"]]["effective_weight"] is None

    # Ben: test excused, one homework at 60%. Only Homework counts.
    assert ben["percent"] == pytest.approx(60)
    assert ben["letter"] == "D-"
    assert a["h2"]["id"] not in ben["grades"]


def test_gradebook_reflects_category_changes(teacher, course):
    hw = course["categories"]["hw"]
    teacher.patch(f"/categories/{hw['id']}", json={"drop_lowest": 0})
    book = teacher.get(f"/courses/{course['course']['id']}/gradebook").json()
    # Ana's homework is now 10/20 = 50%: (40*80 + 35*50) / 75
    assert book["students"][0]["percent"] == pytest.approx(4950 / 75)


def test_gradebook_excludes_unenrolled_students(teacher, course):
    ben = course["students"]["ben"]
    teacher.delete(f"/courses/{course['course']['id']}/students/{ben['id']}")
    book = teacher.get(f"/courses/{course['course']['id']}/gradebook").json()
    assert [row["student"]["name"] for row in book["students"]] == ["Ana"]


def test_gradebook_ignores_grades_from_other_courses(teacher, course):
    other = teacher.course("Other")
    category = teacher.category(other["id"])
    assignment = teacher.assignment(other["id"], category["id"])
    ana = course["students"]["ana"]
    teacher.enroll(other["id"], ana["id"])
    teacher.put(
        "/grades",
        json={"assignment_id": assignment["id"], "grades": [{"student_id": ana["id"], "score": 0}]},
    )
    book = teacher.get(f"/courses/{course['course']['id']}/gradebook").json()
    assert assignment["id"] not in book["students"][0]["grades"]
    assert book["students"][0]["percent"] == pytest.approx(6700 / 75)


def test_empty_gradebook(teacher):
    course = teacher.course()
    book = teacher.get(f"/courses/{course['id']}/gradebook").json()
    assert book["categories"] == book["assignments"] == book["students"] == []


def test_gradebook_with_students_but_no_assignments(teacher):
    course = teacher.course()
    student = teacher.student()
    teacher.enroll(course["id"], student["id"])
    row = teacher.get(f"/courses/{course['id']}/gradebook").json()["students"][0]
    assert row["percent"] is None
    assert row["letter"] is None
    assert row["grades"] == {}


def test_gradebook_unknown_course_404(teacher):
    response = teacher.get("/courses/00000000-0000-0000-0000-000000000000/gradebook")
    assert response.status_code == 404


# --- student report ----------------------------------------------------------


def test_report_breakdown(teacher, course):
    ana = course["students"]["ana"]
    report = teacher.get(f"/students/{ana['id']}/report").json()
    assert report["student"]["id"] == ana["id"]
    (chem,) = report["courses"]
    assert chem["course"]["name"] == "Chemistry"
    assert chem["percent"] == pytest.approx(6700 / 75)
    assert chem["letter"] == "B+"

    cats = {cat["category"]["name"]: cat for cat in chem["categories"]}
    assert list(cats) == ["Homework", "Quizzes", "Tests"]

    hw = cats["Homework"]
    assert hw["percent"] == 100
    assert (hw["earned"], hw["possible"]) == (10, 10)
    assert hw["effective_weight"] == pytest.approx(35 / 75)
    assert [
        (row["assignment"]["title"], row["status"], row["earned"], row["outcome"])
        for row in hw["assignments"]
    ] == [
        ("HW 1", "graded", 10.0, "counted"),
        ("HW 2", "missing", None, "dropped"),
    ]

    (quiz,) = cats["Quizzes"]["assignments"]
    assert (quiz["status"], quiz["score"], quiz["outcome"]) == (None, None, "ungraded")
    assert cats["Quizzes"]["percent"] is None


def test_report_excused_and_missing_outcomes(teacher, course):
    ben = course["students"]["ben"]
    hw = course["categories"]["hw"]
    teacher.patch(f"/categories/{hw['id']}", json={"drop_lowest": 0})
    teacher.put(
        "/grades",
        json={
            "assignment_id": course["assignments"]["h2"]["id"],
            "grades": [{"student_id": ben["id"], "status": "missing"}],
        },
    )
    (chem,) = teacher.get(f"/students/{ben['id']}/report").json()["courses"]
    rows = {
        row["assignment"]["title"]: row for cat in chem["categories"] for row in cat["assignments"]
    }
    assert (rows["Test 1"]["outcome"], rows["Test 1"]["earned"]) == ("excused", None)
    assert (rows["HW 2"]["outcome"], rows["HW 2"]["earned"]) == ("counted", 0.0)
    assert chem["percent"] == pytest.approx(30)  # 6 / 20 homework, the only category counted


def test_report_across_courses_and_filter(teacher, course):
    ana = course["students"]["ana"]
    art = teacher.course("Art")
    teacher.enroll(art["id"], ana["id"])

    report = teacher.get(f"/students/{ana['id']}/report").json()
    assert [c["course"]["name"] for c in report["courses"]] == ["Art", "Chemistry"]
    assert report["courses"][0]["percent"] is None

    filtered = teacher.get(f"/students/{ana['id']}/report", params={"course_id": art["id"]})
    assert [c["course"]["name"] for c in filtered.json()["courses"]] == ["Art"]


def test_report_for_unenrolled_course_is_404(teacher, course):
    loner = teacher.student("Loner")
    response = teacher.get(
        f"/students/{loner['id']}/report", params={"course_id": course["course"]["id"]}
    )
    assert response.status_code == 404
    assert teacher.get(f"/students/{loner['id']}/report").json()["courses"] == []


def test_report_course_filter_must_be_own_course(teacher, other_teacher, course):
    theirs = other_teacher.course()
    ana = course["students"]["ana"]
    response = teacher.get(f"/students/{ana['id']}/report", params={"course_id": theirs["id"]})
    assert response.status_code == 404


def test_report_matches_gradebook(teacher, course):
    book = teacher.get(f"/courses/{course['course']['id']}/gradebook").json()
    for row in book["students"]:
        report = teacher.get(f"/students/{row['student']['id']}/report").json()
        assert report["courses"][0]["percent"] == row["percent"]
        assert report["courses"][0]["letter"] == row["letter"]


def _count_queries(engine, fn):
    from sqlalchemy import event

    statements = []

    def record(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = fn()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    return len(statements)


def test_query_count_does_not_grow_with_class_size(teacher, engine):
    """No N+1: a bigger class or more assignments must not mean more queries."""

    def build(n_students, n_assignments):
        course = teacher.course()
        cats = [teacher.category(course["id"], f"C{i}", weight=1) for i in range(2)]
        assignments = [
            teacher.assignment(course["id"], cats[i % 2]["id"], f"A{i}")
            for i in range(n_assignments)
        ]
        students = [teacher.student(f"S{i}") for i in range(n_students)]
        teacher.enroll(course["id"], *(s["id"] for s in students))
        for a in assignments:
            teacher.put(
                "/grades",
                json={
                    "assignment_id": a["id"],
                    "grades": [{"student_id": s["id"], "score": 5} for s in students],
                },
            )
        return course, students

    small_course, small_students = build(2, 2)
    big_course, big_students = build(15, 8)

    def gradebook(c):
        return lambda: teacher.get(f"/courses/{c['id']}/gradebook")

    def report(s):
        return lambda: teacher.get(f"/students/{s['id']}/report")

    assert _count_queries(engine, gradebook(small_course)) == _count_queries(
        engine, gradebook(big_course)
    )
    assert _count_queries(engine, report(small_students[0])) == _count_queries(
        engine, report(big_students[0])
    )
