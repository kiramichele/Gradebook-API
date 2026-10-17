import importlib.util
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import get_session_factory
from app.main import create_app
from app.models import Base

JWT_SECRET = "test-secret-at-least-32-bytes-long!!"
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load_script(name: str):
    """Import scripts/<name>.py, which isn't a package."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


SUPABASE_URL = "https://test-project.supabase.co"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        supabase_url=SUPABASE_URL,
        supabase_jwt_secret=JWT_SECRET,
    )


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(settings: Settings, engine: Engine) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session_factory] = lambda: sessionmaker(
        bind=engine, expire_on_commit=False
    )
    with TestClient(app) as test_client:
        yield test_client


TokenFactory = Callable[..., str]


@pytest.fixture
def make_token() -> TokenFactory:
    def factory(
        sub: uuid.UUID | str | None = None,
        *,
        expires_in: int = 3600,
        audience: str = "authenticated",
        issuer: str = f"{SUPABASE_URL}/auth/v1",
        secret: str = JWT_SECRET,
        **extra: object,
    ) -> str:
        now = int(time.time())
        claims = {
            "sub": str(sub or uuid.uuid4()),
            "aud": audience,
            "iss": issuer,
            "role": "authenticated",
            "iat": now,
            "exp": now + expires_in,
            **extra,
        }
        return jwt.encode(claims, secret, algorithm="HS256")

    return factory


@pytest.fixture
def auth_headers(make_token: TokenFactory) -> Callable[..., dict[str, str]]:
    def factory(sub: uuid.UUID | str | None = None, **kwargs: object) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(sub, **kwargs)}"}

    return factory


class Api:
    """A test client acting as one teacher, with shortcuts for building fixtures."""

    def __init__(self, client: TestClient, headers: dict[str, str]):
        self.client = client
        self.headers = headers

    def request(self, method: str, path: str, **kwargs):
        return self.client.request(method, path, headers=self.headers, **kwargs)

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs):
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs):
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs):
        return self.request("DELETE", path, **kwargs)

    def _created(self, path: str, body: dict) -> dict:
        response = self.post(path, json=body)
        assert response.status_code == 201, response.text
        return response.json()

    def course(self, name: str = "Algebra II", term: str = "Fall 2026") -> dict:
        return self._created("/courses", {"name": name, "term": term})

    def student(self, name: str = "Sam", email: str | None = None) -> dict:
        return self._created("/students", {"name": name, "email": email})

    def category(self, course_id: str, name: str = "Homework", weight=100, drop_lowest=0) -> dict:
        body = {"name": name, "weight": weight, "drop_lowest": drop_lowest}
        return self._created(f"/courses/{course_id}/categories", body)

    def assignment(
        self, course_id: str, category_id: str, title: str = "HW 1", points=10, **extra
    ) -> dict:
        body = {"category_id": category_id, "title": title, "points_possible": points, **extra}
        return self._created(f"/courses/{course_id}/assignments", body)

    def client_with_auth(self) -> TestClient:
        """A separate client that sends this teacher's token on every request, for
        code that takes an httpx client (TestClient is one)."""
        return TestClient(self.client.app, headers=self.headers)

    def enroll(self, course_id: str, *student_ids: str) -> dict:
        response = self.post(f"/courses/{course_id}/enroll", json={"student_ids": student_ids})
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def teacher(client: TestClient, auth_headers) -> Api:
    return Api(client, auth_headers(uuid.uuid4()))


@pytest.fixture
def other_teacher(client: TestClient, auth_headers) -> Api:
    return Api(client, auth_headers(uuid.uuid4()))
