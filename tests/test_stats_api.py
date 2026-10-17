import pytest


@pytest.fixture
def quiz(teacher):
    """A 20-point quiz for six enrolled students plus one who has since unenrolled."""
    course = teacher.course()
    category = teacher.category(course["id"])
    assignment = teacher.assignment(course["id"], category["id"], "Quiz", points=20)
    names = ["A", "B", "C", "D", "E", "F", "Gone"]
    students = {n: teacher.student(n)["id"] for n in names}
    teacher.enroll(course["id"], *students.values())
    grades = [
        {"student_id": students["A"], "score": 20},
        {"student_id": students["B"], "score": 16},
        {"student_id": students["C"], "score": 12, "status": "late"},
        {"student_id": students["D"], "status": "missing"},
        {"student_id": students["E"], "status": "excused"},
        {"student_id": students["Gone"], "score": 0},
        # F is ungraded
    ]
    response = teacher.put("/grades", json={"assignment_id": assignment["id"], "grades": grades})
    assert response.status_code == 200
    teacher.delete(f"/courses/{course['id']}/students/{students['Gone']}")
    return assignment


def get_stats(teacher, assignment, **params):
    response = teacher.get(f"/assignments/{assignment['id']}/stats", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_stats_default_excludes_missing(teacher, quiz):
    stats = get_stats(teacher, quiz)
    assert stats["points_possible"] == 20
    assert stats["include_missing"] is False
    assert (stats["enrolled"], stats["graded"], stats["missing"]) == (6, 3, 1)
    assert (stats["excused"], stats["ungraded"]) == (1, 1)
    # 20, 16, 12 (late still counts). The unenrolled student's 0 is ignored.
    assert stats["count"] == 3
    assert stats["mean"] == 16
    assert stats["median"] == 16
    assert stats["std_dev"] == pytest.approx((32 / 3) ** 0.5)
    assert (stats["min"], stats["max"]) == (12, 20)
    assert stats["mean_percent"] == 80
    nonzero = {(b["lower"], b["upper"]): b["count"] for b in stats["histogram"] if b["count"]}
    assert nonzero == {(60, 70): 1, (80, 90): 1, (90, 100): 1}
    assert stats["letters"]["A"] == 1
    assert stats["letters"]["B-"] == 1
    assert stats["letters"]["D-"] == 1


def test_stats_including_missing_as_zero(teacher, quiz):
    stats = get_stats(teacher, quiz, include_missing="true")
    assert stats["count"] == 4
    assert stats["mean"] == 12
    assert stats["median"] == 14
    assert stats["min"] == 0
    assert stats["letters"]["F"] == 1


def test_stats_bin_width(teacher, quiz):
    stats = get_stats(teacher, quiz, bin_width=50)
    assert [(b["lower"], b["upper"], b["count"]) for b in stats["histogram"]] == [
        (0, 50, 0),
        (50, 100, 3),
    ]


@pytest.mark.parametrize("width", [0, 3, 200])
def test_invalid_bin_width_is_422(teacher, quiz, width):
    response = teacher.get(f"/assignments/{quiz['id']}/stats", params={"bin_width": width})
    assert response.status_code == 422


def test_stats_with_no_grades(teacher):
    course = teacher.course()
    category = teacher.category(course["id"])
    assignment = teacher.assignment(course["id"], category["id"])
    stats = get_stats(teacher, assignment)
    assert stats["enrolled"] == stats["count"] == 0
    assert stats["mean"] is stats["std_dev"] is None


def test_extra_credit_in_overflow_bin(teacher):
    course = teacher.course()
    category = teacher.category(course["id"])
    assignment = teacher.assignment(course["id"], category["id"], points=10)
    student = teacher.student()
    teacher.enroll(course["id"], student["id"])
    teacher.put(
        "/grades",
        json={
            "assignment_id": assignment["id"],
            "grades": [{"student_id": student["id"], "score": 12}],
        },
    )
    stats = get_stats(teacher, assignment)
    assert stats["histogram"][-1] == {"lower": 100, "upper": None, "count": 1}
    assert stats["max"] == 12
