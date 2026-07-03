"""Test harness guard: force the SQLite backend for the whole test session.

The production pipeline runs on PostgreSQL via DATABASE_URL in .env
(load_dotenv in pipeline.config). Without this guard, importing any pipeline
module inside tests would pick that up and the suite would read/write the
PRODUCTION database. Tests always run hermetically against temp SQLite files
(each test module sets its own DATABASE_PATH).

Must run before any `pipeline.*` import — pytest imports conftest first.
"""
import os

os.environ["DATABASE_URL"] = ""
os.environ.setdefault("DATABASE_PATH", "/tmp/catandary_test_fallback.db")
