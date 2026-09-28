"""RUN_DB_TESTS=1 integration-test isolation.

All DB-gated tests (test_e2e_db.py) run against a dedicated `rolewise_test` database - never the real
development database. This file:
  1. creates/verifies `rolewise_test` exists (with an explicit CREATEDB-privilege check first, so a
     permissions problem fails with a clear message instead of a confusing downstream error),
  2. points this process's DATABASE_URL at it and resets every cache that could otherwise still be
     bound to the real dev database (Settings, the SQLAlchemy engine/sessionmaker singleton),
  3. asserts - as a hard safety guard, re-checked before every single test, not just once - that the
     active database is actually `rolewise_test` before any destructive statement ever runs,
  4. migrates it to head,
  5. truncates every application table before each test, for full isolation between tests.

No production file is touched by any of this. RECALL_LIMIT, production DATABASE_URL, matching logic
and liveness logic are all completely unaffected - the DB tests pass because they run against a small,
isolated dataset, never because any production behavior was loosened.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("BEDROCK_ENABLED", "false")
os.environ.setdefault("SQS_QUEUE_URL", "")

TEST_DB_NAME = "rolewise_test"
BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _run_db_tests_enabled() -> bool:
    return os.environ.get("RUN_DB_TESTS") == "1"


def _base_database_url() -> str:
    """The admin connection used only to create/inspect rolewise_test itself - whatever DATABASE_URL
    is already set (the real dev database), since that's where the credentials to create a sibling
    database come from. Never used to run or truncate anything."""
    return os.environ.get("DATABASE_URL", "postgresql+psycopg://rolewise:rolewise@localhost:5432/rolewise")


def _with_database_name(url: str, name: str) -> str:
    root, _, _ = url.rpartition("/")
    return f"{root}/{name}"


def _active_database_name(engine: sa.engine.Engine) -> str:
    with engine.connect() as conn:
        return conn.execute(sa.text("SELECT current_database()")).scalar()


def _assert_on_test_database(engine: sa.engine.Engine, context: str) -> None:
    """The single check that stands between this suite and ever truncating the real dev database.
    Re-run before every test, not just once at session start."""
    active = _active_database_name(engine)
    if active != TEST_DB_NAME:
        pytest.exit(
            f"Refusing to {context}: active database is {active!r}, expected {TEST_DB_NAME!r}. "
            "Aborting the test session before any destructive statement runs.",
            returncode=1,
        )


@pytest.fixture(scope="session", autouse=True)
def _db_test_isolation():
    if not _run_db_tests_enabled():
        yield
        return

    base_url = _base_database_url()
    test_url = _with_database_name(base_url, TEST_DB_NAME)

    # 1. Ensure rolewise_test exists, with an explicit privilege check first.
    admin_engine = sa.create_engine(base_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                sa.text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
            ).first()
            if not exists:
                can_create = conn.execute(
                    sa.text("SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = current_user")
                ).scalar()
                if not can_create:
                    pytest.exit(
                        f"{TEST_DB_NAME} does not exist and the configured database user cannot "
                        f"create it (missing CREATEDB privilege). Create it manually first: "
                        f"CREATE DATABASE {TEST_DB_NAME};",
                        returncode=1,
                    )
                conn.execute(sa.text(f"CREATE DATABASE {TEST_DB_NAME}"))
    finally:
        admin_engine.dispose()

    # 2. Point this process at the test database. A scoped MonkeyPatch (not the function-scoped
    # `monkeypatch` fixture, which is the wrong scope for a session fixture) so it's explicitly
    # undone at session end regardless of how the session finishes.
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", test_url)

    from rolewise.config import get_settings

    get_settings.cache_clear()

    import rolewise.db as db_module

    if db_module._engine is not None:
        db_module._engine.dispose()
    db_module._engine = None
    db_module._SessionLocal = None
    # Force a fresh engine bound to the (now test) DATABASE_URL, so both get_db() (FastAPI requests)
    # and get_sessionmaker() (inline worker dispatch) resolve to rolewise_test from here on - they
    # share this exact same cached singleton, so resetting it once here covers both paths.
    db_module.get_sessionmaker()

    # 3. Hard safety guard before anything else touches this database.
    _assert_on_test_database(db_module._engine, "initialize the DB test session")

    # 4. Migrate to head. Run as a subprocess (not in-process) so alembic's own env.py resolves
    # DATABASE_URL fresh from this explicit environment, independent of anything already imported or
    # cached in the current process.
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(BACKEND_ROOT / "alembic.ini"), "upgrade", "head"],
        cwd=str(BACKEND_ROOT),
        env={**os.environ, "DATABASE_URL": test_url},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        mp.undo()
        pytest.exit(
            f"Failed to migrate {TEST_DB_NAME} to head:\n--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}",
            returncode=1,
        )

    yield

    if db_module._engine is not None:
        db_module._engine.dispose()
    db_module._engine = None
    db_module._SessionLocal = None
    mp.undo()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _truncate_before_each_db_test(_db_test_isolation):
    """Runs before every test in the suite, but only does anything when RUN_DB_TESTS=1. TRUNCATE, not
    transaction rollback: the app opens independent sessions through both the FastAPI request path and
    inline worker dispatch, so a single wrapping transaction would not actually contain every write a
    test makes - TRUNCATE-before-test is simpler and is what's actually guaranteed to isolate tests."""
    if not _run_db_tests_enabled():
        yield
        return

    import rolewise.db as db_module

    _assert_on_test_database(db_module._engine, "truncate before a test")

    with db_module._engine.connect() as conn:
        tables = conn.execute(
            sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename != 'alembic_version'")
        ).scalars().all()
        if tables:
            conn.execute(sa.text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
        conn.commit()

    yield
