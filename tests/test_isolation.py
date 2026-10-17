"""Every endpoint that takes an id treats another teacher's row as nonexistent."""

import pytest


@pytest.fixture
def alices(teacher):
    course = teacher.course("Alice's course")
    category = teacher.category(course["id"])
    assignment = teacher.assignment(course["id"], category["id"])
    student = teacher.student("Alice's student", "kid@example.edu")
    teacher.enroll(course["id"], student["id"])
    teacher.put(
        "/grades",
        json={
            "assignment_id": assignment["id"],
            "grades": [{"student_id": student["id"], "score": 9}],
        },
    )
    return {"course": course, "category": category, "assignment": assignment, "student": student}


ROUTES = [
    ("GET", "/courses/{course}", None),
    ("PATCH", "/courses/{course}", {"name": "x"}),
    ("DELETE", "/courses/{course}", None),
    ("GET", "/courses/{course}/students", None),
    ("POST", "/courses/{course}/enroll", {"student_ids": ["{student}"]}),
    ("DELETE", "/courses/{course}/students/{student}", None),
    ("GET", "/students/{student}", None),
    ("PATCH", "/students/{student}", {"name": "x"}),
    ("DELETE", "/students/{student}", None),
    ("GET", "/courses/{course}/categories", None),
    ("POST", "/courses/{course}/categories", {"name": "x", "weight": 1}),
    ("GET", "/categories/{category}", None),
    ("PATCH", "/categories/{category}", {"name": "x"}),
    ("DELETE", "/categories/{category}", None),
    ("GET", "/courses/{course}/assignments", None),
    (
        "POST",
        "/courses/{course}/assignments",
        {"category_id": "{category}", "title": "x", "points_possible": 1},
    ),
    ("GET", "/assignments/{assignment}", None),
    ("PATCH", "/assignments/{assignment}", {"title": "x"}),
    ("DELETE", "/assignments/{assignment}", None),
    ("GET", "/assignments/{assignment}/grades", None),
    ("DELETE", "/assignments/{assignment}/grades/{student}", None),
    (
        "PUT",
        "/grades",
        {"assignment_id": "{assignment}", "grades": [{"student_id": "{student}", "score": 0}]},
    ),
]


def fill(template, ids):
    if isinstance(template, str):
        return template.format(**ids)
    if isinstance(template, list):
        return [fill(item, ids) for item in template]
    if isinstance(template, dict):
        return {key: fill(value, ids) for key, value in template.items()}
    return template


@pytest.mark.parametrize(("method", "path", "body"), ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
def test_other_teacher_gets_404(teacher, other_teacher, alices, method, path, body):
    ids = {name: row["id"] for name, row in alices.items()}
    response = other_teacher.request(method, fill(path, ids), json=fill(body, ids))
    assert response.status_code == 404, response.text

    # And nothing changed for Alice.
    assert teacher.get(f"/courses/{ids['course']}").json()["name"] == "Alice's course"
    assert teacher.get(f"/students/{ids['student']}").json()["name"] == "Alice's student"
    assert len(teacher.get(f"/assignments/{ids['assignment']}/grades").json()) == 1
    assert len(teacher.get(f"/courses/{ids['course']}/students").json()) == 1


def test_other_teacher_lists_are_empty(other_teacher, alices):
    assert other_teacher.get("/courses").json() == []
    assert other_teacher.get("/students").json() == []


def test_other_teacher_can_reuse_email(other_teacher, alices):
    other_teacher.student("Different kid", alices["student"]["email"])


def test_every_id_route_is_covered():
    """Fails when a new route is added without an isolation case above."""
    from app.main import app

    covered = {(method, path) for method, path, _ in ROUTES}
    for path, item in app.openapi()["paths"].items():
        for method in item:
            if "{" in path or (method, path) == ("put", "/grades"):
                template = path
                for name in ("course", "student", "category", "assignment"):
                    template = template.replace(f"{{{name}_id}}", f"{{{name}}}")
                assert (method.upper(), template) in covered, f"{method.upper()} {path}"
