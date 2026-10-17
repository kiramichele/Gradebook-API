"""Fill a teacher's account with realistic demo data, through the real API.

    # Create (or reuse) a confirmed demo user, sign in, and seed:
    SUPABASE_URL=... SUPABASE_ANON_KEY=... SUPABASE_SERVICE_ROLE_KEY=... \\
    python scripts/seed_demo.py --api-url https://your-api.up.railway.app \\
        --email demo@example.edu --password '...' --create-user

    # Seed an account you already have (just signs in):
    python scripts/seed_demo.py --api-url ... --email you@school.edu --password '...'

Everything goes through the public API with the teacher's own token, so the
demo data passes the same validation and RLS as real use, and seeding doubles
as a smoke test of a fresh deployment. The data is generated from a fixed
random seed, so every run produces the same gradebook.

The service role key is only used to create the demo user. It never reaches
the API.
"""

from __future__ import annotations

import argparse
import io
import os
import random
import sys
from dataclasses import dataclass
from datetime import date

import httpx

FIRST = [
    "Amara", "Bao", "Camila", "Dev", "Elif", "Farah", "Gabriel", "Hana", "Ibrahim", "Jonah",
    "Kavya", "Liam", "Mei", "Nia", "Omar", "Priya", "Quinn", "Rafael", "Sofia", "Tariq",
    "Uma", "Victor", "Wren", "Ximena", "Yusuf", "Zoe",
]  # fmt: skip
LAST = [
    "Abara", "Bianchi", "Castillo", "Dubois", "Eriksen", "Fujita", "Gomez", "Haddad", "Ivanova",
    "Jansen", "Kowalski", "Lindqvist", "Moreau", "Nakamura", "Okafor", "Petrov", "Quispe",
    "Rahman", "Silva", "Tanaka", "Ueda", "Vargas", "Wójcik", "Xu", "Yilmaz", "Zielinski",
]  # fmt: skip


@dataclass(frozen=True)
class CourseSpec:
    name: str
    term: str
    # (name, weight, drop_lowest)
    categories: tuple[tuple[str, int, int], ...]
    # (title, category, points, due)
    assignments: tuple[tuple[str, str, int, str], ...]
    students: slice


COURSES = (
    CourseSpec(
        name="AP Chemistry",
        term="Fall 2026",
        categories=(
            ("Tests", 45, 0),
            ("Labs", 30, 1),
            ("Homework", 15, 2),
            ("Participation", 10, 0),
        ),
        assignments=(
            ("Lab 1: Density", "Labs", 20, "2026-09-04"),
            ("HW 1: Measurement", "Homework", 10, "2026-09-08"),
            ("HW 2: Atomic structure", "Homework", 10, "2026-09-15"),
            ("Lab 2: Flame tests", "Labs", 20, "2026-09-18"),
            ("Participation: September", "Participation", 10, "2026-09-30"),
            ("Unit 1 Test", "Tests", 100, "2026-10-01"),
            ("HW 3: Periodic trends", "Homework", 10, "2026-10-06"),
            ("Lab 3: Stoichiometry", "Labs", 20, "2026-10-09"),
            ("HW 4: Bonding", "Homework", 10, "2026-10-13"),
            ("Unit 2 Test", "Tests", 100, "2026-10-29"),
            ("Lab 4: Titration", "Labs", 20, "2026-11-06"),
            ("Midterm", "Tests", 150, "2026-12-11"),
        ),
        students=slice(0, 22),
    ),
    CourseSpec(
        name="Algebra II",
        term="Fall 2026",
        categories=(("Tests", 50, 0), ("Quizzes", 30, 1), ("Homework", 20, 1)),
        assignments=(
            ("Quiz 1: Functions", "Quizzes", 20, "2026-09-05"),
            ("HW 1", "Homework", 15, "2026-09-09"),
            ("Quiz 2: Linear systems", "Quizzes", 20, "2026-09-19"),
            ("HW 2", "Homework", 15, "2026-09-23"),
            ("Test 1: Linear algebra", "Tests", 100, "2026-09-30"),
            ("Quiz 3: Quadratics", "Quizzes", 20, "2026-10-10"),
            ("HW 3", "Homework", 15, "2026-10-14"),
            ("Test 2: Polynomials", "Tests", 100, "2026-11-04"),
        ),
        students=slice(10, 26),
    ),
)


def roster_csv() -> str:
    """26 fictional students. Emails use example.edu, which is reserved for examples."""
    lines = ["first_name,last_name,email"]
    for first, last in zip(FIRST, LAST, strict=True):
        email = f"{first}.{last}@students.example.edu".lower().replace("ó", "o")
        lines.append(f"{first},{last},{email}")
    return "\n".join(lines) + "\n"


def _check(response: httpx.Response) -> httpx.Response:
    if response.is_error:
        raise SystemExit(
            f"{response.request.method} {response.request.url} -> "
            f"{response.status_code}: {response.text}"
        )
    return response


def seed(client: httpx.Client, *, as_of: date, seed: int = 2026, reset: bool = False) -> dict:
    """Create the demo courses. `client` must send the teacher's bearer token."""
    existing = {(c["name"], c["term"]): c for c in _check(client.get("/courses")).json()}
    for spec in COURSES:
        found = existing.get((spec.name, spec.term))
        if found and not reset:
            raise SystemExit(
                f"{spec.name} ({spec.term}) already exists; pass --reset to replace it"
            )
        if found:
            _check(client.delete(f"/courses/{found['id']}"))

    rng = random.Random(seed)
    summary = {"courses": [], "students": 0, "grades": 0}
    for spec in COURSES:
        course = _check(client.post("/courses", json={"name": spec.name, "term": spec.term})).json()

        # The roster goes in through CSV import, matched by email, so re-seeding
        # reuses the same students.
        names = roster_csv().splitlines()
        csv = "\n".join([names[0], *names[1:][spec.students]]) + "\n"
        imported = _check(
            client.post(
                "/students/import",
                params={"course_id": course["id"]},
                files={"file": ("roster.csv", io.BytesIO(csv.encode()), "text/csv")},
            )
        ).json()
        students = imported["created"] + imported["existing"]
        summary["students"] += len(imported["created"])

        category_ids = {}
        for name, weight, drop in spec.categories:
            category = _check(
                client.post(
                    f"/courses/{course['id']}/categories",
                    json={"name": name, "weight": weight, "drop_lowest": drop},
                )
            ).json()
            category_ids[name] = category["id"]

        # Each student has an ability and each assignment a difficulty, so the
        # gradebook has believable structure rather than uniform noise.
        ability = {s["id"]: min(0.99, max(0.45, rng.gauss(0.82, 0.1))) for s in students}
        struggling = students[3]["id"]  # one student with a run of missing work
        ability[struggling] = 0.68

        for title, category, points, due in spec.assignments:
            assignment = _check(
                client.post(
                    f"/courses/{course['id']}/assignments",
                    json={
                        "category_id": category_ids[category],
                        "title": title,
                        "points_possible": points,
                        "due_date": due,
                    },
                )
            ).json()
            if date.fromisoformat(due) > as_of:
                continue  # not due yet, so not graded

            difficulty = rng.uniform(-0.08, 0.04)
            grades = []
            for student in students:
                roll = rng.random()
                missing_rate = 0.25 if student["id"] == struggling else 0.035
                if roll < missing_rate:
                    grades.append({"student_id": student["id"], "status": "missing"})
                    continue
                if roll < missing_rate + 0.03:
                    grades.append({"student_id": student["id"], "status": "excused"})
                    continue
                fraction = ability[student["id"]] + difficulty + rng.gauss(0, 0.06)
                score = round(min(1.03, max(0.3, fraction)) * points * 2) / 2
                late = rng.random() < 0.05
                grades.append(
                    {
                        "student_id": student["id"],
                        "score": score,
                        "status": "late" if late else "graded",
                    }
                )
            _check(
                client.put("/grades", json={"assignment_id": assignment["id"], "grades": grades})
            )
            summary["grades"] += len(grades)
        summary["courses"].append(course["id"])
    return summary


def sign_in(supabase_url: str, anon_key: str, email: str, password: str) -> str:
    response = httpx.post(
        f"{supabase_url.rstrip('/')}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": anon_key},
        json={"email": email, "password": password},
        timeout=30,
    )
    _check(response)
    return response.json()["access_token"]


def _admin_headers(key: str) -> dict[str, str]:
    # New secret keys (sb_secret_...) aren't JWTs and go only in apikey; the
    # legacy service_role key is a JWT and also needs to be the bearer token.
    if key.startswith("sb_"):
        return {"apikey": key}
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def create_user(supabase_url: str, service_key: str, email: str, password: str) -> None:
    """Create a confirmed user with the admin API; fine if it already exists."""
    response = httpx.post(
        f"{supabase_url.rstrip('/')}/auth/v1/admin/users",
        headers=_admin_headers(service_key),
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"name": "Demo Teacher"},
        },
        timeout=30,
    )
    if response.status_code == 422 and "already" in response.text.lower():
        print(f"{email} already exists; signing in")
        return
    _check(response)
    print(f"Created {email}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument(
        "--create-user", action="store_true", help="needs SUPABASE_SERVICE_ROLE_KEY"
    )
    parser.add_argument("--reset", action="store_true", help="replace existing demo courses")
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=date.today(),
        help="grade assignments due on or before this date (default: today)",
    )
    args = parser.parse_args()

    supabase_url = os.environ.get("SUPABASE_URL") or sys.exit("Set SUPABASE_URL")
    anon_key = os.environ.get("SUPABASE_ANON_KEY") or sys.exit("Set SUPABASE_ANON_KEY")
    if args.create_user:
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or sys.exit(
            "Set SUPABASE_SERVICE_ROLE_KEY to create the user"
        )
        create_user(supabase_url, service_key, args.email, args.password)

    token = sign_in(supabase_url, anon_key, args.email, args.password)
    with httpx.Client(
        base_url=args.api_url.rstrip("/"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    ) as client:
        summary = seed(client, as_of=args.as_of, reset=args.reset)
    print(
        f"Seeded {len(summary['courses'])} courses, {summary['students']} new students, "
        f"{summary['grades']} grades"
    )


if __name__ == "__main__":
    main()
