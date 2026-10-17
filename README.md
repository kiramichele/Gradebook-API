# Gradebook API

A teacher gradebook API built with FastAPI, SQLAlchemy, and Supabase (Postgres,
Auth, Row Level Security). It does weighted category grading, excused work,
optimal drop-lowest-N, assignment statistics, and CSV import/export.

## Status

- [x] Project setup, Supabase schema with RLS, JWT auth
- [x] CRUD for courses, students, categories, assignments; enrollment; bulk grade upsert
- [x] Grade calculation engine with tests
- [x] `GET /courses/{id}/gradebook`, `GET /students/{id}/report`
- [ ] `GET /assignments/{id}/stats`, CSV import/export
- [ ] Next.js dashboard with an editable grade grid
- [ ] Deploy, seed demo data, case study

## Endpoints

Every endpoint requires a Supabase access token (`Authorization: Bearer ...`).
Interactive docs are at `/docs`.

| Method | Path | Notes |
|---|---|---|
| GET | `/me` | The signed-in teacher |
| GET, POST | `/courses` | |
| GET, PATCH, DELETE | `/courses/{id}` | Delete cascades to categories, assignments, enrollments, grades |
| GET | `/courses/{id}/students` | Roster, by name |
| POST | `/courses/{id}/enroll` | `{"student_ids": [...]}`; idempotent, reports `enrolled` and `already_enrolled` |
| DELETE | `/courses/{id}/students/{student_id}` | Unenroll; grades are kept and return on re-enrollment |
| GET, POST | `/students` | Email optional, unique per teacher (409 otherwise), stored lowercase |
| GET, PATCH, DELETE | `/students/{id}` | Delete removes the student's enrollments and grades everywhere |
| GET, POST | `/courses/{id}/categories` | `weight`, `drop_lowest` |
| GET, PATCH, DELETE | `/categories/{id}` | Delete is refused (409) while assignments use the category |
| GET, POST | `/courses/{id}/assignments` | By due date, undated last; `?category_id=` filter |
| GET, PATCH, DELETE | `/assignments/{id}` | The category must be in the same course (422) |
| PUT | `/grades` | Bulk upsert for one assignment, all or nothing; see below |
| GET | `/assignments/{id}/grades` | |
| DELETE | `/assignments/{id}/grades/{student_id}` | Clears a grade back to ungraded |
| GET | `/courses/{id}/gradebook` | The full grid with each student's computed grade; see below |
| GET | `/students/{id}/report` | Per-course breakdown for one student; `?course_id=` for one course |

```json
PUT /grades
{
  "assignment_id": "…",
  "grades": [
    {"student_id": "…", "score": 9.5},
    {"student_id": "…", "score": 7, "status": "late"},
    {"student_id": "…", "status": "missing"},
    {"student_id": "…", "status": "excused"}
  ]
}
```

`status` defaults to `graded`. `graded` and `late` need a score, and scores
above `points_possible` are allowed (extra credit). If any student isn't
enrolled in the course, the request fails with 422 listing them, and nothing
is written. The response is every grade for the assignment after the update.

### Gradebook and report

`GET /courses/{id}/gradebook` returns the course's `categories` and
`assignments` (the grid's columns, by due date) and one row per enrolled
student:

```json
{
  "student": {"id": "…", "name": "Ana", "email": null},
  "percent": 89.33,
  "letter": "B+",
  "grades": {"<assignment_id>": {"score": 80.0, "status": "graded"}},
  "categories": [
    {"category_id": "…", "percent": 100.0, "earned": 10.0, "possible": 10.0,
     "effective_weight": 0.467, "dropped": ["<assignment_id>"]}
  ]
}
```

An assignment missing from `grades` hasn't been graded. `effective_weight` is
the category's real share of the course grade: with Quizzes (25%) still
empty, Tests (40%) and Homework (35%) count for 40/75 and 35/75.

`GET /students/{id}/report` gives the same numbers nested by course, then
category, then assignment. Each assignment has an `outcome` (`counted`,
`dropped`, `excused` or `ungraded`) and the `earned` points that counted, so
a student or parent can see exactly how the grade was reached.

Both endpoints use a fixed number of queries however large the class is; a
test checks this.

Conventions:
- Another teacher's resource is always a **404**, never a 403, so ids don't leak.
- PATCH changes only the fields you send. Sending `null` for a required field is a 422.
- Unknown fields are rejected (422), which catches typos like `"pionts_possible"`.
- Numbers come back as JSON numbers. Send decimals as strings (`"12.5"`) for exact input.

## How grades are calculated

All of this lives in [`app/grading/engine.py`](app/grading/engine.py), a set of
pure functions with no database dependency.

| Status    | Effect                                                      |
|-----------|-------------------------------------------------------------|
| `graded`  | Counts its score                                            |
| `late`    | Counts its score (no penalty yet)                           |
| `missing` | Counts as 0                                                 |
| `excused` | Removed from numerator **and** denominator                  |
| no grade  | Ungraded; ignored until scored                              |

- **Within a category**, grades are points-based: `sum(earned) / sum(possible)`.
- **Across categories**, the course grade is the weighted mean of category
  percents. Weights are relative (40/35/25 and 0.4/0.35/0.25 are the same).
- **Empty categories** (nothing counted yet, or everything excused) drop out, and
  their weight is redistributed proportionally across the remaining categories.
- **Drop lowest N** removes the N results whose removal *maximizes* the category
  percent, never the last counted one. This is not always the N lowest
  percentages. With 9/10, 50/100 and 9/20, dropping the 45% quiz gives 53.6%,
  but dropping the 50% test gives 60%. The engine solves it exactly with
  Dinkelbach's method for fractional programming, and a randomized test checks
  it against brute force over every subset.
- Arithmetic uses `fractions.Fraction`, so there is no float drift and ties
  always resolve the same way (the earlier assignment is kept).

## Security model

Supabase Auth issues the JWT. The API verifies it (asymmetric keys through the
project's JWKS, or the legacy HS256 secret) and then, for every database
transaction, runs:

```sql
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims', '<verified claims>', true);
```

so `auth.uid()` is the caller and the RLS policies in
[`supabase/migrations`](supabase/migrations) apply to API queries the same way
they apply to supabase-js. Route handlers also filter by `teacher_id`, so
ownership is enforced at two layers. `tests/test_rls_postgres.py` checks the
policies on real Postgres using unfiltered SQL.

The plan's data model, with two additions:

- `students.teacher_id`: students belong to a teacher, so a roster can exist
  before anyone is enrolled and RLS has an owner to check.
- `categories.drop_lowest`, plus a composite foreign key so an assignment can't
  point at another course's category.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env               # fill in your Supabase values
supabase db push                   # or paste the migration into the SQL editor
uvicorn app.main:app --reload      # http://localhost:8000/docs
```

## Tests

```bash
pytest                              # unit + API tests on SQLite
TEST_POSTGRES_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres pytest
                                    # also runs the RLS tests against real Postgres
ruff check . && ruff format --check .
```

CI runs all of it, including the Postgres RLS tests, on every push and pull request.

## Layout

```
app/
  main.py            app factory, CORS, routers
  config.py          settings from env / .env
  auth.py            Supabase JWT verification -> CurrentUser
  db.py              engine + per-request session that applies RLS context
  models.py          SQLAlchemy models (mirror the SQL migration)
  schemas.py         Pydantic request/response models
  ownership.py       "get it if the caller owns it, else 404" lookups
  gradebook.py       loads courses and grades and runs the grade engine
  routers/           me, courses (+ roster), students, categories, assignments, grades, reports
  grading/engine.py  grade calculation
supabase/migrations/ schema, signup trigger, RLS policies
tests/
  test_isolation.py  every id-taking route, called by the wrong teacher, must 404
```
