def test_enroll_and_roster(teacher):
    course = teacher.course()
    zoe, adam = teacher.student("Zoe"), teacher.student("Adam")

    result = teacher.enroll(course["id"], zoe["id"], adam["id"])
    assert result["enrolled"] == [zoe["id"], adam["id"]]
    assert result["already_enrolled"] == []
    assert [s["name"] for s in result["roster"]] == ["Adam", "Zoe"]

    roster = teacher.get(f"/courses/{course['id']}/students").json()
    assert [s["name"] for s in roster] == ["Adam", "Zoe"]


def test_enroll_is_idempotent(teacher):
    course = teacher.course()
    a, b = teacher.student("A"), teacher.student("B")
    teacher.enroll(course["id"], a["id"])

    result = teacher.enroll(course["id"], a["id"], b["id"], b["id"])
    assert result["enrolled"] == [b["id"]]
    assert result["already_enrolled"] == [a["id"]]
    assert len(result["roster"]) == 2


def test_enroll_unknown_student_is_404_and_enrolls_nobody(teacher):
    course = teacher.course()
    real = teacher.student()
    fake = "00000000-0000-0000-0000-000000000000"

    response = teacher.post(
        f"/courses/{course['id']}/enroll", json={"student_ids": [real["id"], fake]}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["student_ids"] == [fake]
    assert teacher.get(f"/courses/{course['id']}/students").json() == []


def test_cannot_enroll_another_teachers_student(teacher, other_teacher):
    course = teacher.course()
    theirs = other_teacher.student()
    response = teacher.post(f"/courses/{course['id']}/enroll", json={"student_ids": [theirs["id"]]})
    assert response.status_code == 404


def test_enroll_requires_students(teacher):
    course = teacher.course()
    assert (
        teacher.post(f"/courses/{course['id']}/enroll", json={"student_ids": []}).status_code == 422
    )


def test_unenroll_keeps_grades_for_reenrollment(teacher):
    course = teacher.course()
    category = teacher.category(course["id"])
    assignment = teacher.assignment(course["id"], category["id"])
    student = teacher.student()
    teacher.enroll(course["id"], student["id"])
    teacher.put(
        "/grades",
        json={
            "assignment_id": assignment["id"],
            "grades": [{"student_id": student["id"], "score": 7}],
        },
    )

    path = f"/courses/{course['id']}/students/{student['id']}"
    assert teacher.delete(path).status_code == 204
    assert teacher.delete(path).status_code == 404
    assert teacher.get(f"/courses/{course['id']}/students").json() == []

    teacher.enroll(course["id"], student["id"])
    grades = teacher.get(f"/assignments/{assignment['id']}/grades").json()
    assert [(g["student_id"], g["score"]) for g in grades] == [(student["id"], 7.0)]
