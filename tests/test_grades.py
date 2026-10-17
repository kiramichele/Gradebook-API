import pytest


@pytest.fixture
def setup(teacher):
    course = teacher.course()
    category = teacher.category(course["id"])
    assignment = teacher.assignment(course["id"], category["id"], points=10)
    students = [teacher.student(name) for name in ("Ana", "Ben", "Cy")]
    teacher.enroll(course["id"], *(s["id"] for s in students))
    return course, assignment, [s["id"] for s in students]


def put(api, assignment_id, *grades):
    return api.put("/grades", json={"assignment_id": assignment_id, "grades": list(grades)})


def by_student(response):
    return {g["student_id"]: (g["score"], g["status"]) for g in response.json()}


def test_bulk_insert(teacher, setup):
    _, assignment, (ana, ben, cy) = setup
    response = put(
        teacher,
        assignment["id"],
        {"student_id": ana, "score": 9.5},
        {"student_id": ben, "status": "missing"},
        {"student_id": cy, "status": "excused"},
    )
    assert response.status_code == 200, response.text
    assert by_student(response) == {
        ana: (9.5, "graded"),
        ben: (None, "missing"),
        cy: (None, "excused"),
    }


def test_upsert_updates_existing_and_keeps_others(teacher, setup):
    _, assignment, (ana, ben, cy) = setup
    put(teacher, assignment["id"], {"student_id": ana, "score": 5}, {"student_id": ben, "score": 6})

    response = put(
        teacher,
        assignment["id"],
        {"student_id": ana, "score": 8, "status": "late"},
        {"student_id": cy, "score": 10},
    )
    assert by_student(response) == {ana: (8.0, "late"), ben: (6.0, "graded"), cy: (10.0, "graded")}
    assert by_student(teacher.get(f"/assignments/{assignment['id']}/grades")) == by_student(
        response
    )


def test_score_above_points_possible_allowed(teacher, setup):
    _, assignment, (ana, *_) = setup
    response = put(teacher, assignment["id"], {"student_id": ana, "score": 11})
    assert by_student(response)[ana] == (11.0, "graded")


@pytest.mark.parametrize(
    "grade",
    [
        {"score": -1},
        {"score": "1.234"},
        {"status": "graded"},
        {"status": "late"},
        {"score": 5, "status": "bogus"},
        {"score": 5, "comment": "nice"},
    ],
)
def test_invalid_grades_are_422(teacher, setup, grade):
    _, assignment, (ana, *_) = setup
    assert put(teacher, assignment["id"], {"student_id": ana, **grade}).status_code == 422


def test_duplicate_students_in_one_request_are_422(teacher, setup):
    _, assignment, (ana, *_) = setup
    response = put(
        teacher, assignment["id"], {"student_id": ana, "score": 1}, {"student_id": ana, "score": 2}
    )
    assert response.status_code == 422


def test_empty_request_is_422(teacher, setup):
    _, assignment, _ = setup
    assert put(teacher, assignment["id"]).status_code == 422


def test_unenrolled_student_rejects_whole_batch(teacher, setup):
    _, assignment, (ana, *_) = setup
    outsider = teacher.student("Outsider")
    response = put(
        teacher,
        assignment["id"],
        {"student_id": ana, "score": 9},
        {"student_id": outsider["id"], "score": 9},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["student_ids"] == [outsider["id"]]
    assert teacher.get(f"/assignments/{assignment['id']}/grades").json() == []


def test_student_enrolled_in_a_different_course_rejected(teacher, setup):
    _, assignment, _ = setup
    other_course = teacher.course("Other")
    elsewhere = teacher.student("Elsewhere")
    teacher.enroll(other_course["id"], elsewhere["id"])
    response = put(teacher, assignment["id"], {"student_id": elsewhere["id"], "score": 1})
    assert response.status_code == 422


def test_unknown_assignment_is_404(teacher):
    student = teacher.student()
    response = put(
        teacher, "00000000-0000-0000-0000-000000000000", {"student_id": student["id"], "score": 1}
    )
    assert response.status_code == 404


def test_clear_grade(teacher, setup):
    _, assignment, (ana, ben, _) = setup
    put(teacher, assignment["id"], {"student_id": ana, "score": 5}, {"student_id": ben, "score": 6})

    path = f"/assignments/{assignment['id']}/grades/{ana}"
    assert teacher.delete(path).status_code == 204
    assert teacher.delete(path).status_code == 404
    assert list(by_student(teacher.get(f"/assignments/{assignment['id']}/grades"))) == [ben]


def test_deleting_assignment_removes_grades(teacher, setup):
    course, assignment, (ana, *_) = setup
    put(teacher, assignment["id"], {"student_id": ana, "score": 5})
    teacher.delete(f"/assignments/{assignment['id']}")
    assert teacher.get(f"/assignments/{assignment['id']}/grades").status_code == 404
