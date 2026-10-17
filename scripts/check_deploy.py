"""Check that a deployment is configured safely before it takes traffic.

Railway runs this as the pre-deploy command (see railway.json), so a
misconfiguration fails the deploy instead of shipping. It never writes data.

    python scripts/check_deploy.py

The checks that matter most are about Row Level Security. A database can be
set up so the API works perfectly while RLS protects nothing (tables created
without RLS, a policy granted to anon, a role that bypasses RLS). Those
mistakes are invisible from the outside, so this script looks for them.
"""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jwt  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Connection, Engine  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402

TABLES = ("teachers", "courses", "students", "enrollments", "categories", "assignments", "grades")


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


def check_settings(settings: Settings) -> list[Result]:
    results = [
        Result(
            "DATABASE_URL is Postgres",
            settings.database_url.startswith("postgresql"),
            "RLS needs Postgres; SQLite is for local development only",
        ),
        Result(
            "SUPABASE_URL is set",
            bool(settings.supabase_url),
            "needed to verify tokens (JWKS) and their issuer",
        ),
    ]
    local = [o for o in settings.cors_origins if "localhost" in o or "127.0.0.1" in o]
    results.append(
        Result(
            "CORS_ORIGINS includes the deployed dashboard",
            bool(settings.cors_origins) and len(local) < len(settings.cors_origins),
            f"currently {settings.cors_origins}; add the Vercel URL",
        )
    )
    return results


def check_jwks(settings: Settings) -> Result:
    if settings.supabase_jwt_secret:
        return Result("Token verification", True, "using the legacy HS256 secret")
    try:
        keys = jwt.PyJWKClient(settings.jwks_url).get_signing_keys()
    except Exception as exc:  # noqa: BLE001 - report any failure to reach or parse JWKS
        return Result("JWKS reachable", False, f"{settings.jwks_url}: {exc}")
    return Result("JWKS reachable", bool(keys), f"{len(keys)} signing key(s)")


def check_database(engine: Engine) -> list[Result]:
    results: list[Result] = []
    with engine.connect() as conn:
        results.append(Result("Database reachable", True))

        missing = [
            t for t in TABLES if not _scalar(conn, "select to_regclass(:t)", t=f"public.{t}")
        ]
        results.append(
            Result(
                "Migration applied",
                not missing,
                f"missing tables: {', '.join(missing)}; run supabase/migrations" if missing else "",
            )
        )
        if missing:
            return results

        no_rls = list(
            conn.execute(
                text(
                    "select c.relname from pg_class c "
                    "join pg_namespace n on n.oid = c.relnamespace "
                    "where n.nspname = 'public' and c.relname = any(:tables) "
                    "and not c.relrowsecurity"
                ),
                {"tables": list(TABLES)},
            ).scalars()
        )
        results.append(
            Result(
                "RLS enabled on every table",
                not no_rls,
                f"RLS is off for: {', '.join(no_rls)}" if no_rls else "",
            )
        )

        loose = list(
            conn.execute(
                text(
                    "select tablename || ' (' || policyname || ')' from pg_policies "
                    "where schemaname = 'public' and tablename = any(:tables) "
                    "and roles <> '{authenticated}'"
                ),
                {"tables": list(TABLES)},
            ).scalars()
        )
        results.append(
            Result(
                "Policies apply only to signed-in users",
                not loose,
                f"policies open to other roles: {', '.join(loose)}" if loose else "",
            )
        )

        bypass = _scalar(conn, "select rolbypassrls from pg_roles where rolname = 'authenticated'")
        results.append(
            Result(
                "authenticated role does not bypass RLS",
                bypass is False,
                "the authenticated role has BYPASSRLS" if bypass else "",
            )
        )

        can_switch = _scalar(conn, "select pg_has_role(current_user, 'authenticated', 'member')")
        results.append(
            Result(
                "API user can act as authenticated",
                bool(can_switch),
                f"{_scalar(conn, 'select current_user')} cannot SET ROLE authenticated; "
                "connect as the postgres user"
                if not can_switch
                else "",
            )
        )
        if not can_switch:
            return results

    # The real test: as an unknown teacher, through the same mechanism the API
    # uses, every table must look empty.
    with engine.connect() as conn, conn.begin():
        conn.exec_driver_sql("SET LOCAL ROLE authenticated")
        conn.execute(
            text("select set_config('request.jwt.claims', :c, true)"),
            {"c": json.dumps({"sub": str(uuid.uuid4()), "role": "authenticated"})},
        )
        visible = {
            t: n
            for t in TABLES
            if (n := _scalar(conn, f"select count(*) from {t}"))  # noqa: S608
        }
        conn.rollback()
    results.append(
        Result(
            "A stranger sees no rows",
            not visible,
            f"visible to an unknown user: {visible}" if visible else "",
        )
    )
    return results


def _scalar(conn: Connection, sql: str, **params: object):
    return conn.execute(text(sql), params).scalar()


def run(
    settings: Settings,
    engine_factory: Callable[[str], Engine] | None = None,
    jwks: Callable[[Settings], Result] = check_jwks,
) -> list[Result]:
    results = check_settings(settings)
    results.append(jwks(settings))
    if settings.database_url.startswith("postgresql"):
        factory = engine_factory or (
            lambda url: create_engine(url, connect_args={"prepare_threshold": None})
        )
        engine = factory(settings.database_url)
        try:
            results.extend(check_database(engine))
        except Exception as exc:  # noqa: BLE001 - report, don't crash, so the output is useful
            results.append(Result("Database reachable", False, str(exc).splitlines()[0]))
        finally:
            engine.dispose()
    return results


def main() -> int:
    results = run(get_settings())
    for r in results:
        mark = "ok  " if r.ok else "FAIL"
        print(f"[{mark}] {r.name}" + (f": {r.detail}" if r.detail and not r.ok else ""))
    failed = [r for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
