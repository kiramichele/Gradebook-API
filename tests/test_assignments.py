def test_assignment_crud(teacher):
    course = teacher.course()
    category = teacher.category(course["id"])
    assignment = teacher.assignment(
        course["id"], category["id"], "Lab 1", points="12.5", due_date="2026-10-20"
    )
    assert assignment["points_possible"] == 12.5
    assert assignment["due_date"] == "2026-10-20"

    assert teacher.get(f"/assignments/{assignment['id']}").json()["title"] == "Lab 1"

    updated = teacher.patch(f"/assignments/{assignment['id']}", json={"due_date": None})
    assert updated.status_code == 200
    assert updated.json()["due_date"] is None
    assert updated.json()["title"] == "Lab 1"

    assert teacher.delete(f"/assignments/{assignment['id']}").status_code == 204
    assert teacher.get(f"/assignments/{assignment['id']}").status_code == 404


def test_assignments_sorted_by_due_date_undated_last(teacher):
    course = teacher.course()
    category = teacher.category(course["id"])
    teacher.assignment(course["id"], category["id"], "Undated")
    teacher.assignment(course["id"], category["id"], "Later", due_date="2026-12-01")
    teacher.assignment(course["id"], category["id"], "Sooner", due_date="2026-11-01")

    titles = [a["title"] for a in teacher.get(f"/courses/{course['id']}/assignments").json()]
    assert titles == ["Sooner", "Later", "Undated"]


def test_filter_assignments_by_category(teacher):
    course = teacher.course()
    hw, tests = teacher.category(course["id"], "HW"), teacher.category(course["id"], "Tests")
    teacher.assignment(course["id"], hw["id"], "HW 1")
    teacher.assignment(course["id"], tests["id"], "Test 1")

    response = teacher.get(
        f"/courses/{course['id']}/assignments", params={"category_id": tests["id"]}
    )
    assert [a["title"] for a in response.json()] == ["Test 1"]


def test_category_must_belong_to_the_course(teacher):
    algebra, biology = teacher.course("Algebra"), teacher.course("Biology")
    bio_category = teacher.category(biology["id"])
    response = teacher.post(
        f"/courses/{algebra['id']}/assignments",
        json={"category_id": bio_category["id"], "title": "x", "points_possible": 10},
    )
    assert response.status_code == 422

    algebra_category = teacher.category(algebra["id"])
    assignment = teacher.assignment(algebra["id"], algebra_category["id"])
    response = teacher.patch(
        f"/assignments/{assignment['id']}", json={"category_id": bio_category["id"]}
    )
    assert response.status_code == 422


def test_move_assignment_to_another_category(teacher):
    course = teacher.course()
    hw, tests = teacher.category(course["id"], "HW"), teacher.category(course["id"], "Tests")
    assignment = teacher.assignment(course["id"], hw["id"])
    response = teacher.patch(f"/assignments/{assignment['id']}", json={"category_id": tests["id"]})
    assert response.json()["category_id"] == tests["id"]


def test_assignment_validation(teacher):
    course = teacher.course()
    category = teacher.category(course["id"])
    path = f"/courses/{course['id']}/assignments"
    for body in [
        {"category_id": category["id"], "title": "x", "points_possible": 0},
        {"category_id": category["id"], "title": "x", "points_possible": -5},
        {"category_id": category["id"], "title": "x", "points_possible": "1.234"},
        {"category_id": category["id"], "title": "", "points_possible": 10},
        {"category_id": category["id"], "title": "x", "points_possible": 10, "due_date": "soon"},
        {"category_id": "not-a-uuid", "title": "x", "points_possible": 10},
    ]:
        assert teacher.post(path, json=body).status_code == 422, body


def test_deleting_course_removes_everything(teacher):
    course = teacher.course()
    category = teacher.category(course["id"])
    assignment = teacher.assignment(course["id"], category["id"])
    student = teacher.student()
    teacher.enroll(course["id"], student["id"])

    assert teacher.delete(f"/courses/{course['id']}").status_code == 204
    assert teacher.get(f"/categories/{category['id']}").status_code == 404
    assert teacher.get(f"/assignments/{assignment['id']}").status_code == 404
    # Students outlive courses; they belong to the teacher.
    assert teacher.get(f"/students/{student['id']}").status_code == 200
