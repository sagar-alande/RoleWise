from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from rolewise.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None


def get_sessionmaker() -> sessionmaker:
    global _engine, _SessionLocal
    if _SessionLocal is None:
        _engine = create_engine(get_settings().sqlalchemy_url, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
