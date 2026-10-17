def test_category_crud(teacher):
    course = teacher.course()
    category = teacher.category(course["id"], "Tests", weight=40, drop_lowest=1)
    assert category["weight"] == 40.0  # a JSON number, not "40.000"
    assert category["drop_lowest"] == 1
    assert category["course_id"] == course["id"]

    listed = teacher.get(f"/courses/{course['id']}/categories").json()
    assert [c["id"] for c in listed] == [category["id"]]

    updated = teacher.patch(f"/categories/{category['id']}", json={"weight": "37.5"})
    assert updated.status_code == 200
    assert updated.json()["weight"] == 37.5
    assert updated.json()["name"] == "Tests"

    assert teacher.delete(f"/categories/{category['id']}").status_code == 204
    assert teacher.get(f"/categories/{category['id']}").status_code == 404


def test_category_names_unique_within_course(teacher):
    c1, c2 = teacher.course("One"), teacher.course("Two")
    teacher.category(c1["id"], "Quizzes")
    duplicate = teacher.post(
        f"/courses/{c1['id']}/categories", json={"name": "Quizzes", "weight": 1}
    )
    assert duplicate.status_code == 409
    teacher.category(c2["id"], "Quizzes")

    other = teacher.category(c1["id"], "Tests")
    assert teacher.patch(f"/categories/{other['id']}", json={"name": "Quizzes"}).status_code == 409


def test_cannot_delete_category_with_assignments(teacher):
    course = teacher.course()
    category = teacher.category(course["id"])
    assignment = teacher.assignment(course["id"], category["id"])

    response = teacher.delete(f"/categories/{category['id']}")
    assert response.status_code == 409
    assert teacher.get(f"/assignments/{assignment['id']}").status_code == 200

    teacher.delete(f"/assignments/{assignment['id']}")
    assert teacher.delete(f"/categories/{category['id']}").status_code == 204


def test_category_validation(teacher):
    course = teacher.course()
    path = f"/courses/{course['id']}/categories"
    for body in [
        {"name": "x", "weight": -1},
        {"name": "x", "weight": 1000},
        {"name": "x", "weight": "1.2345"},
        {"name": "x", "weight": 1, "drop_lowest": -1},
        {"name": "", "weight": 1},
        {"weight": 1},
    ]:
        assert teacher.post(path, json=body).status_code == 422, body

    category = teacher.category(course["id"])
    assert teacher.patch(f"/categories/{category['id']}", json={"weight": None}).status_code == 422


def test_categories_for_unknown_course_404(teacher):
    missing = "00000000-0000-0000-0000-000000000000"
    assert teacher.get(f"/courses/{missing}/categories").status_code == 404
    response = teacher.post(f"/courses/{missing}/categories", json={"name": "x", "weight": 1})
    assert response.status_code == 404
