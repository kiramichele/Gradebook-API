import time
import uuid
from collections.abc import Callable, Iterator

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
