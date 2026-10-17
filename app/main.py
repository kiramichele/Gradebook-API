from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import courses, me


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Gradebook API",
        version="0.1.0",
        description="Weighted category grading, drop-lowest-N, stats, and CSV import/export.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(me.router)
    app.include_router(courses.router)
    return app


app = create_app()
