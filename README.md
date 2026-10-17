# Gradebook API

A teacher gradebook API built with FastAPI, SQLAlchemy, and Supabase (Postgres,
Auth, Row Level Security). It does weighted category grading, excused work,
optimal drop-lowest-N, assignment statistics, and CSV import/export.

## Status

- [x] Project setup, Supabase schema with RLS, JWT auth
- [x] Course CRUD (the pattern for the remaining resources)
- [x] Grade calculation engine with tests
- [ ] CRUD for students, categories, assignments; `POST /courses/{id}/enroll`; `PUT /grades`
- [ ] `GET /courses/{id}/gradebook`, `GET /students/{id}/report`
- [ ] `GET /assignments/{id}/stats`, CSV import/export
- [ ] Next.js dashboard with an editable grade grid
- [ ] Deploy, seed demo data, case study

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
  routers/           /me, /courses
  grading/engine.py  grade calculation
supabase/migrations/ schema, signup trigger, RLS policies
tests/
```
