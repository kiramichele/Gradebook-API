def test_student_crud(teacher):
    student = teacher.student("Ada Lovelace", "Ada@Example.edu ")
    assert student["email"] == "ada@example.edu"

    assert [s["id"] for s in teacher.get("/students").json()] == [student["id"]]
    assert teacher.get(f"/students/{student['id']}").json()["name"] == "Ada Lovelace"

    updated = teacher.patch(f"/students/{student['id']}", json={"name": "  Ada King  "})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Ada King"
    assert updated.json()["email"] == "ada@example.edu"

    cleared = teacher.patch(f"/students/{student['id']}", json={"email": None})
    assert cleared.json()["email"] is None

    assert teacher.delete(f"/students/{student['id']}").status_code == 204
    assert teacher.get(f"/students/{student['id']}").status_code == 404


def test_students_listed_by_name(teacher):
    for name in ["Zed", "amy", "Bo"]:
        teacher.student(name)
    names = [s["name"] for s in teacher.get("/students").json()]
    assert sorted(names) == sorted(["Zed", "amy", "Bo"])
    assert names.index("Bo") < names.index("Zed")


def test_duplicate_email_is_409(teacher):
    teacher.student("A", "a@example.edu")
    response = teacher.post("/students", json={"name": "B", "email": "A@example.edu"})
    assert response.status_code == 409

    other = teacher.student("C", "c@example.edu")
    response = teacher.patch(f"/students/{other['id']}", json={"email": "a@example.edu"})
    assert response.status_code == 409


def test_email_unique_per_teacher_only(teacher, other_teacher):
    teacher.student("A", "shared@example.edu")
    response = other_teacher.post("/students", json={"name": "A", "email": "shared@example.edu"})
    assert response.status_code == 201


def test_students_without_email_do_not_conflict(teacher):
    teacher.student("A")
    teacher.student("B")
    assert len(teacher.get("/students").json()) == 2


def test_student_validation(teacher):
    assert teacher.post("/students", json={"name": "  "}).status_code == 422
    assert teacher.post("/students", json={"name": "A", "email": "nope"}).status_code == 422
    assert teacher.post("/students", json={"name": "A", "extra": 1}).status_code == 422
    student = teacher.student()
    assert teacher.patch(f"/students/{student['id']}", json={"name": None}).status_code == 422


def test_deleting_student_removes_enrollments_and_grades(teacher):
    course = teacher.course()
    category = teacher.category(course["id"])
    assignment = teacher.assignment(course["id"], category["id"])
    student = teacher.student()
    teacher.enroll(course["id"], student["id"])
    teacher.put(
        "/grades",
        json={
            "assignment_id": assignment["id"],
            "grades": [{"student_id": student["id"], "score": 9}],
        },
    )

    assert teacher.delete(f"/students/{student['id']}").status_code == 204
    assert teacher.get(f"/courses/{course['id']}/students").json() == []
    assert teacher.get(f"/assignments/{assignment['id']}/grades").json() == []
