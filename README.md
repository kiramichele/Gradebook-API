# Gradebook API

A teacher gradebook API built with FastAPI, SQLAlchemy, and Supabase (Postgres,
Auth, Row Level Security). It does weighted category grading, excused work,
optimal drop-lowest-N, assignment statistics, and CSV import/export.

## Status

- [x] Project setup, Supabase schema with RLS, JWT auth
- [x] CRUD for courses, students, categories, assignments; enrollment; bulk grade upsert
- [x] Grade calculation engine with tests
- [x] `GET /courses/{id}/gradebook`, `GET /students/{id}/report`
- [x] `GET /assignments/{id}/stats`, CSV roster import, CSV gradebook export
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
| GET | `/courses/{id}/gradebook/export` | The gradebook as a CSV download |
| GET | `/assignments/{id}/stats` | Mean, median, SD, histogram, letter counts; `?include_missing=`, `?bin_width=` |
| POST | `/students/import` | CSV roster upload (multipart `file`); `?course_id=` to enroll, `?dry_run=true` to preview |

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

### Assignment stats

`GET /assignments/{id}/stats` describes enrolled students' scores: `mean`,
`median`, `std_dev`, `min`, `max`, the mean and median as a percent of points
possible, a `histogram` by percent, and counts per letter grade. It also
returns how many students are `graded`, `missing`, `excused` and `ungraded`.

- Excused and ungraded work is always left out. Missing work is left out by
  default, since a 0 for work never turned in says more about effort than about
  how the class understood the material; pass `include_missing=true` to count it as 0.
- `std_dev` is the **population** standard deviation: the class is the whole
  group being described, not a sample.
- Histogram bins are `[0, 10)`, `[10, 20)`, …, `[90, 100]` (so a perfect score
  lands in the top bin). Scores over 100% get an extra open-ended bin, and
  `bin_width` can be any divisor of 100.

### CSV

**Roster import:** `POST /students/import` takes a CSV with a `name` column (or
`first_name` and `last_name`) and an optional `email`. Header matching is
forgiving: `Student Name`, `E-mail`, `Last Name` and the like all work, and
extra columns are ignored. Files can be UTF-8 (with or without Excel's BOM) or
Windows-1252, which is what Excel on Windows saves.

- **All or nothing:** any bad row rejects the file, with a 422 listing every
  problem by line number, so a teacher can fix them all in one pass.
- **Safe to re-run:** a row whose email matches one of your students reuses that
  student, unchanged. Rows without an email always create a new student.
- `dry_run=true` returns exactly what would happen and saves nothing, which
  makes a good preview step in the UI.

**Gradebook export:** one row per student with each assignment's score (or
`missing` / `excused`, blank if ungraded), each category's percent, the course
percent and letter grade. The file starts with a BOM so Excel opens accented
names correctly. Cells that a spreadsheet would run as a formula (starting
with `=`, `+`, `-` or `@`) are prefixed with `'`, which blocks CSV
injection through student names. The export's `Student` and `Email` columns
are also a valid roster, so last term's gradebook can seed next term's course.

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
  roster.py          enrollment and roster import
  csv_io.py          roster parsing, gradebook CSV formatting
  routers/           me, courses (+ roster), students, categories, assignments, grades, reports
  grading/engine.py  grade calculation
  grading/stats.py   assignment statistics
supabase/migrations/ schema, signup trigger, RLS policies
tests/
  test_isolation.py  every id-taking route, called by the wrong teacher, must 404
```
