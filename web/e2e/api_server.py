"""Start the real API on a fresh SQLite database for the end-to-end tests.

Run by Playwright (see playwright.config.ts); not for production use.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent / ".data"

DATA.mkdir(exist_ok=True)
database = DATA / "e2e.db"
database.unlink(missing_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{database}"
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from app.db import get_engine  # noqa: E402
from app.models import Base  # noqa: E402

Base.metadata.create_all(get_engine())
uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8100")))
