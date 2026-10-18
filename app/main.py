from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.routers import assignments, categories, courses, grades, me, reports, students

DESCRIPTION = """
Weighted category grading, excused work, optimal drop-lowest-N, assignment
statistics, and CSV import/export, for teachers. Every request is scoped to
the signed-in teacher, by the API and again by Postgres Row Level Security.

## Trying it here

1. Sign in to the dashboard (the demo account works) and click **API token**
   in the header to copy your access token.
2. Click **Authorize** below, paste the token, and click **Authorize**.
3. Open any endpoint and click **Try it out**. `GET /courses` is a good start;
   then `GET /courses/{course_id}/gradebook` shows the grading engine's output.

Another teacher's ids return **404**, never 403, so ids don't leak.

## How grades are calculated

* **graded** and **late** count their score, **missing** counts as 0,
  **excused** leaves both the numerator and the denominator, and no grade
  means not graded yet.
* Within a category, grades are points-based. Across categories, the course
  grade is the weighted mean, and an empty category's weight is shared out
  among the rest.
* **Drop lowest N** drops whichever N assignments raise the category percent
  most. That isn't always the N lowest percentages.
"""

TAGS = [
    {"name": "me", "description": "The signed-in teacher."},
    {"name": "courses", "description": "Courses, rosters and enrollment."},
    {
        "name": "students",
        "description": "Students belong to a teacher and can be enrolled in any of their "
        "courses. Roster CSV import is all or nothing, and matches existing students by email.",
    },
    {
        "name": "categories",
        "description": "Weighted grading categories, each with an optional drop-lowest-N.",
    },
    {"name": "assignments", "description": "Assignments, each in exactly one category."},
    {
        "name": "grades",
        "description": "Bulk upsert of scores and statuses (graded, late, missing, excused).",
    },
    {
        "name": "reports",
        "description": "Computed results: the course gradebook, one student's report with "
        "every assignment's treatment explained, assignment stats, and CSV export.",
    },
    {"name": "meta", "description": "Health check."},
]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Gradebook API",
        version="0.1.0",
        summary="Weighted category grading, drop-lowest-N, stats, and CSV import/export.",
        description=DESCRIPTION,
        openapi_tags=TAGS,
        swagger_ui_parameters={
            "persistAuthorization": True,  # keep the pasted token across reloads
            "docExpansion": "none",
            "defaultModelsExpandDepth": 0,
            "displayRequestDuration": True,
            "tryItOutEnabled": True,
        },
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(me.router)
    for module in (courses, students, categories, assignments, grades, reports):
        app.include_router(module.router)
    return app


app = create_app()
