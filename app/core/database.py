"""Database engine and session management (SQLAlchemy)."""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}


def _ensure_sqlite_directory_exists(database_url: str) -> None:
    """Create the parent directory for a SQLite file if it is missing.

    Git does not track empty directories, so a fresh clone or a container
    rebuild can arrive without ``data/``. Without this, SQLAlchemy fails
    with 'unable to open database file' before the app can start.
    """
    if not database_url.startswith("sqlite"):
        return

    path_part = database_url.split("sqlite:///", 1)[-1]
    if not path_part or path_part == ":memory:":
        return

    parent_directory = Path(path_part).expanduser().resolve().parent
    parent_directory.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_directory_exists(settings.database_url)

engine = create_engine(settings.database_url, connect_args=_connect_args, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
