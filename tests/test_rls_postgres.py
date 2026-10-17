"""Row Level Security tests against real Postgres.

These apply supabase/migrations to a throwaway database and check that the
policies, not just the API's WHERE clauses, keep teachers apart. Queries here
are deliberately unfiltered raw SQL.

Skipped unless TEST_POSTGRES_URL points at a server where the user can create
databases, e.g. postgresql+psycopg://postgres:postgres@localhost:5432/postgres
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.auth import CurrentUser
from app.db import _apply_rls_context
from app.main import create_app
from tests.conftest import Api

ROOT = Path(__file__).resolve().parent.parent
ADMIN_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="TEST_POSTGRES_URL not set")


@pytest.fixture(scope="module")
def database() -> Iterator[tuple[Engine, Engine]]:
    """Yield (admin engine, api engine) for a freshly migrated database."""
    name = f"gradebook_test_{uuid.uuid4().hex[:8]}"
    server = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        conn.execute(text(f'create database "{name}"'))

    admin_url = make_url(ADMIN_URL).set(database=name)
    admin = create_engine(admin_url)
    with admin.begin() as conn:
        for path in [
            ROOT / "tests/sql/supabase_stub.sql",
            *sorted((ROOT / "supabase/migrations").glob("*.sql")),
        ]:
            conn.exec_driver_sql(path.read_text())

    api_url = admin_url.set(username="gradebook_api", password="gradebook_api")
    api = create_engine(api_url, connect_args={"prepare_threshold": None})
    try:
        yield admin, api
    finally:
        api.dispose()
        admin.dispose()
        with server.connect() as conn:
            conn.execute(text(f'drop database "{name}" with (force)'))
        server.dispose()


def signup(admin: Engine, name: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    with admin.begin() as conn:
        conn.execute(
            text(
                "insert into auth.users values (:id, jsonb_build_object('name', cast(:n as text)))"
            ),
            {"id": user_id, "n": name},
        )
    return user_id


def session_as(api: Engine, user_id: uuid.UUID) -> Session:
    session = sessionmaker(bind=api)()
    _apply_rls_context(session, CurrentUser(user_id, None, {"sub": str(user_id)}))
    return session


def count(session: Session, table: str) -> int:
    return session.execute(text(f"select count(*) from {table}")).scalar_one()


def test_signup_trigger_creates_teacher(database):
    admin, _ = database
    user_id = signup(admin, "Ms. Frizzle")
    with admin.connect() as conn:
        name = conn.execute(text("select name from teachers where id = :id"), {"id": user_id})
        assert name.scalar_one() == "Ms. Frizzle"


def test_session_runs_as_authenticated_even_after_rollback(database):
    admin, api = database
    with session_as(api, signup(admin, "T")) as s:
        assert s.execute(text("select current_user")).scalar_one() == "authenticated"
        s.rollback()
        assert s.execute(text("select current_user")).scalar_one() == "authenticated"


def test_teachers_are_isolated(database):
    admin, api = database
    alice, bob = signup(admin, "Alice"), signup(admin, "Bob")

    with session_as(api, alice) as s:
        course_id = s.execute(
            text("insert into courses (name) values ('Physics') returning id")
        ).scalar_one()
        category_id = s.execute(
            text(
                "insert into categories (course_id, name, weight) "
                "values (:c, 'HW', 50) returning id"
            ),
            {"c": course_id},
        ).scalar_one()
        assignment_id = s.execute(
            text(
                "insert into assignments (course_id, category_id, title, points_possible) "
                "values (:c, :k, 'HW1', 10) returning id"
            ),
            {"c": course_id, "k": category_id},
        ).scalar_one()
        student_id = s.execute(
            text("insert into students (name) values ('Sam') returning id")
        ).scalar_one()
        s.execute(
            text("insert into enrollments values (:c, :s)"), {"c": course_id, "s": student_id}
        )
        s.execute(
            text("insert into grades (assignment_id, student_id, score) values (:a, :s, 9)"),
            {"a": assignment_id, "s": student_id},
        )
        s.commit()

    with session_as(api, bob) as s:
        for table in ["courses", "students", "enrollments", "categories", "assignments", "grades"]:
            assert count(s, table) == 0, table
        assert count(s, "teachers") == 1

        updated = s.execute(
            text("update courses set name = 'pwned' where id = :c"), {"c": course_id}
        )
        assert updated.rowcount == 0
        assert s.execute(text("delete from grades")).rowcount == 0

        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(
                text("insert into courses (teacher_id, name) values (:t, 'hijack')"), {"t": alice}
            )
        s.rollback()

        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(
                text("insert into categories (course_id, name, weight) values (:c, 'x', 1)"),
                {"c": course_id},
            )
        s.rollback()

    with session_as(api, alice) as s:
        assert count(s, "courses") == 1
        assert s.execute(text("select name from courses")).scalar_one() == "Physics"


def test_cannot_enroll_another_teachers_student(database):
    admin, api = database
    alice, bob = signup(admin, "Alice"), signup(admin, "Bob")
    with session_as(api, bob) as s:
        bobs_student = s.execute(
            text("insert into students (name) values ('Bo') returning id")
        ).scalar_one()
        s.commit()
    with session_as(api, alice) as s:
        course_id = s.execute(
            text("insert into courses (name) values ('Bio') returning id")
        ).scalar_one()
        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(
                text("insert into enrollments values (:c, :s)"), {"c": course_id, "s": bobs_student}
            )


def test_grades_require_enrollment(database):
    admin, api = database
    with session_as(api, signup(admin, "T")) as s:
        course_id = s.execute(
            text("insert into courses (name) values ('Art') returning id")
        ).scalar_one()
        category_id = s.execute(
            text(
                "insert into categories (course_id, name, weight) values (:c, 'HW', 1) returning id"
            ),
            {"c": course_id},
        ).scalar_one()
        assignment_id = s.execute(
            text(
                "insert into assignments (course_id, category_id, title, points_possible) "
                "values (:c, :k, 'A', 10) returning id"
            ),
            {"c": course_id, "k": category_id},
        ).scalar_one()
        student_id = s.execute(
            text("insert into students (name) values ('Sam') returning id")
        ).scalar_one()
        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(
                text("insert into grades (assignment_id, student_id, score) values (:a, :s, 9)"),
                {"a": assignment_id, "s": student_id},
            )


def test_assignment_cannot_use_another_courses_category(database):
    admin, api = database
    with session_as(api, signup(admin, "T")) as s:
        c1, c2 = (
            s.execute(
                text("insert into courses (name) values (:n) returning id"), {"n": n}
            ).scalar_one()
            for n in ("One", "Two")
        )
        category_id = s.execute(
            text(
                "insert into categories (course_id, name, weight) values (:c, 'HW', 1) returning id"
            ),
            {"c": c1},
        ).scalar_one()
        with pytest.raises(DBAPIError, match="foreign key"):
            s.execute(
                text(
                    "insert into assignments (course_id, category_id, title, points_possible) "
                    "values (:c, :k, 'A', 10)"
                ),
                {"c": c2, "k": category_id},
            )


@pytest.fixture
def pg_client(database, settings):
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.db import get_session_factory

    _, api = database
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session_factory] = lambda: sessionmaker(
        bind=api, expire_on_commit=False
    )
    with TestClient(app) as client:
        yield client


def test_api_end_to_end_on_postgres(database, pg_client, auth_headers):
    """The whole API under RLS, including the Postgres ON CONFLICT upsert and native enum."""
    admin, _ = database
    alice = Api(pg_client, auth_headers(signup(admin, "Alice")))
    bob = Api(pg_client, auth_headers(signup(admin, "Bob")))

    assert alice.get("/me").json()["name"] == "Alice"
    course = alice.course("Physics")
    category = alice.category(course["id"], "Labs", weight="40.5", drop_lowest=1)
    assert category["weight"] == 40.5
    assignment = alice.assignment(course["id"], category["id"], points="12.5")
    ana, ben = alice.student("Ana", "ana@example.edu"), alice.student("Ben")
    alice.enroll(course["id"], ana["id"], ben["id"])

    def put(*grades):
        response = alice.put(
            "/grades", json={"assignment_id": assignment["id"], "grades": list(grades)}
        )
        assert response.status_code == 200, response.text
        return {g["student_id"]: (g["score"], g["status"]) for g in response.json()}

    assert put(
        {"student_id": ana["id"], "score": "11.25"}, {"student_id": ben["id"], "status": "missing"}
    ) == {
        ana["id"]: (11.25, "graded"),
        ben["id"]: (None, "missing"),
    }
    assert put({"student_id": ben["id"], "score": 12, "status": "late"}) == {
        ana["id"]: (11.25, "graded"),
        ben["id"]: (12.0, "late"),
    }

    assert (
        alice.post("/students", json={"name": "Dup", "email": "ana@example.edu"}).status_code == 409
    )
    assert alice.delete(f"/categories/{category['id']}").status_code == 409

    # Labs drop 1 of 1 -> nothing dropped (never the last); 11.25/12.5 and 12/12.5.
    book = alice.get(f"/courses/{course['id']}/gradebook").json()
    assert [(r["student"]["name"], r["percent"]) for r in book["students"]] == [
        ("Ana", 90.0),
        ("Ben", 96.0),
    ]
    (report,) = alice.get(f"/students/{ben['id']}/report").json()["courses"]
    assert report["letter"] == "A"
    assert bob.get(f"/courses/{course['id']}/gradebook").status_code == 404
    assert bob.get(f"/students/{ana['id']}/report").status_code == 404

    assert bob.get(f"/courses/{course['id']}").status_code == 404
    assert bob.get(f"/assignments/{assignment['id']}/grades").status_code == 404
    response = bob.put(
        "/grades",
        json={"assignment_id": assignment["id"], "grades": [{"student_id": ana["id"], "score": 0}]},
    )
    assert response.status_code == 404
    assert bob.get("/students").json() == []

    assert alice.delete(f"/courses/{course['id']}").status_code == 204
    assert [s["name"] for s in alice.get("/students").json()] == ["Ana", "Ben"]
