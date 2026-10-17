"""The deploy check's settings logic and the demo seeder, run against the in-process API."""

from datetime import date

import pytest

from app.config import Settings
from tests.conftest import load_script

check_deploy = load_script("check_deploy")
seed_demo = load_script("seed_demo")


# --- check_deploy --------------------------------------------------------------


def failures(settings):
    return {r.name for r in check_deploy.check_settings(settings) if not r.ok}


def test_good_settings_pass():
    settings = Settings(
        database_url="postgresql+psycopg://u:p@db.example.com:5432/postgres",
        supabase_url="https://abc.supabase.co",
        cors_origins=["https://gradebook.vercel.app"],
    )
    assert failures(settings) == set()


def test_bad_settings_fail():
    assert failures(Settings(database_url="sqlite://", cors_origins=["http://localhost:3000"])) == {
        "DATABASE_URL is Postgres",
        "SUPABASE_URL is set",
        "CORS_ORIGINS includes the deployed dashboard",
    }


def test_main_exits_nonzero_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(check_deploy, "get_settings", lambda: Settings(database_url="sqlite://"))
    monkeypatch.setattr(
        check_deploy, "check_jwks", lambda s: check_deploy.Result("JWKS reachable", True)
    )
    assert check_deploy.main() == 1
    assert "[FAIL] DATABASE_URL is Postgres" in capsys.readouterr().out


def test_hs256_secret_skips_jwks():
    result = check_deploy.check_jwks(Settings(supabase_jwt_secret="x" * 32))
    assert result.ok


# --- seed_demo -----------------------------------------------------------------


AS_OF = date(2026, 10, 17)


def test_roster_is_fictional_and_valid():
    lines = seed_demo.roster_csv().strip().splitlines()
    assert lines[0] == "first_name,last_name,email"
    assert len(lines) == 27
    assert all(line.endswith("@students.example.edu") for line in lines[1:])


def test_seed_builds_a_believable_gradebook(teacher):
    summary = seed_demo.seed(teacher.client_with_auth(), as_of=AS_OF)
    assert len(summary["courses"]) == 2
    assert summary["students"] == 26  # 22 + 16 enrolled, 12 shared between courses

    courses = {c["name"]: c for c in teacher.get("/courses").json()}
    chem = teacher.get(f"/courses/{courses['AP Chemistry']['id']}/gradebook").json()
    assert len(chem["students"]) == 22
    assert len(chem["assignments"]) == 12
    rows = chem["students"]
    assert all(row["percent"] is not None for row in rows)
    assert 70 < sum(r["percent"] for r in rows) / len(rows) < 92
    assert len({row["letter"] for row in rows}) >= 4  # a spread of grades

    # Future assignments (due after AS_OF) are ungraded; past ones are filled in.
    future = {a["id"] for a in chem["assignments"] if a["due_date"] > AS_OF.isoformat()}
    assert len(future) == 3
    assert all(not (row["grades"].keys() & future) for row in rows)
    cells = [cell for row in rows for cell in row["grades"].values()]
    statuses = {cell["status"] for cell in cells}
    assert statuses == {"graded", "late", "missing", "excused"}
    assert any(cat["dropped"] for row in rows for cat in row["categories"])


def test_seed_is_deterministic(teacher, other_teacher):
    def scores(api):
        seed_demo.seed(api.client_with_auth(), as_of=AS_OF)
        course = next(c for c in api.get("/courses").json() if c["name"] == "Algebra II")
        book = api.get(f"/courses/{course['id']}/gradebook").json()
        return [(row["student"]["name"], row["percent"]) for row in book["students"]]

    assert scores(teacher) == scores(other_teacher)


def test_seed_refuses_to_duplicate_and_can_reset(teacher):
    client = teacher.client_with_auth()
    seed_demo.seed(client, as_of=AS_OF)
    with pytest.raises(SystemExit, match="already exists"):
        seed_demo.seed(client, as_of=AS_OF)

    seed_demo.seed(client, as_of=AS_OF, reset=True)
    assert len(teacher.get("/courses").json()) == 2
    assert len(teacher.get("/students").json()) == 26  # matched by email, not duplicated


def test_admin_headers_for_both_key_formats():
    assert seed_demo._admin_headers("sb_secret_abc") == {"apikey": "sb_secret_abc"}
    assert seed_demo._admin_headers("eyJhbGciOi.legacy.jwt") == {
        "apikey": "eyJhbGciOi.legacy.jwt",
        "Authorization": "Bearer eyJhbGciOi.legacy.jwt",
    }
