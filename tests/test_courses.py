import uuid


def test_course_crud(client, auth_headers):
    headers = auth_headers(uuid.uuid4())

    created = client.post(
        "/courses", json={"name": "Algebra II", "term": "Fall 2026"}, headers=headers
    )
    assert created.status_code == 201
    course = created.json()
    assert course["name"] == "Algebra II"

    assert [c["id"] for c in client.get("/courses", headers=headers).json()] == [course["id"]]

    updated = client.patch(
        f"/courses/{course['id']}", json={"term": "Spring 2027"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["term"] == "Spring 2027"
    assert updated.json()["name"] == "Algebra II"

    assert client.delete(f"/courses/{course['id']}", headers=headers).status_code == 204
    assert client.get(f"/courses/{course['id']}", headers=headers).status_code == 404


def test_teachers_cannot_see_each_others_courses(client, auth_headers):
    alice, bob = auth_headers(uuid.uuid4()), auth_headers(uuid.uuid4())
    course_id = client.post("/courses", json={"name": "Chemistry"}, headers=alice).json()["id"]

    assert client.get("/courses", headers=bob).json() == []
    assert client.get(f"/courses/{course_id}", headers=bob).status_code == 404
    assert client.patch(f"/courses/{course_id}", json={"name": "x"}, headers=bob).status_code == 404
    assert client.delete(f"/courses/{course_id}", headers=bob).status_code == 404
    assert client.get(f"/courses/{course_id}", headers=alice).json()["name"] == "Chemistry"


def test_course_validation(client, auth_headers):
    headers = auth_headers()
    assert client.post("/courses", json={"name": ""}, headers=headers).status_code == 422
    assert client.post("/courses", json={}, headers=headers).status_code == 422


def test_courses_require_auth(client):
    assert client.get("/courses").status_code == 401
    assert client.post("/courses", json={"name": "x"}).status_code == 401


def test_default_sqlite_engine_enforces_foreign_keys(tmp_path, monkeypatch):
    import uuid as _uuid

    import pytest
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    from app import db as db_module
    from app.config import Settings
    from app.models import Base, Course

    monkeypatch.setattr(
        db_module, "get_settings", lambda: Settings(database_url=f"sqlite:///{tmp_path}/x.db")
    )
    db_module.get_engine.cache_clear()
    try:
        engine = db_module.get_engine()
        Base.metadata.create_all(engine)
        with Session(engine) as session, pytest.raises(IntegrityError):
            session.add(Course(teacher_id=_uuid.uuid4(), name="Orphan"))
            session.flush()
    finally:
        db_module.get_engine.cache_clear()
