"""Database engine and the per-request session.

On Postgres every transaction a request opens first runs

    SET LOCAL ROLE authenticated;
    SELECT set_config('request.jwt.claims', '<the caller's JWT claims>', true);

which is what Supabase's PostgREST does for supabase-js. `auth.uid()` then
resolves to the caller and the RLS policies in supabase/migrations apply.
Both settings are transaction-local, so a pooled connection never carries one
teacher's identity into another request.
"""

import json
from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, SessionTransaction, sessionmaker

from app.auth import CurrentUser, get_current_user
from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if url.startswith("postgresql"):
        # Supabase's transaction pooler doesn't support prepared statements.
        return create_engine(url, pool_pre_ping=True, connect_args={"prepare_threshold": None})
    return create_engine(url, connect_args={"check_same_thread": False})


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def _apply_rls_context(session: Session, user: CurrentUser) -> None:
    claims = json.dumps(user.claims, default=str)

    @event.listens_for(session, "after_begin")
    def set_claims(_session: Session, _txn: SessionTransaction, conn: Connection) -> None:
        if conn.dialect.name != "postgresql":
            return
        conn.exec_driver_sql("SET LOCAL ROLE authenticated")
        conn.execute(
            text("SELECT set_config('request.jwt.claims', :claims, true)"), {"claims": claims}
        )


def get_db(
    user: CurrentUser = Depends(get_current_user),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> Iterator[Session]:
    """A session scoped to the caller. Commits if the request succeeds."""
    with session_factory() as session:
        _apply_rls_context(session, user)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
