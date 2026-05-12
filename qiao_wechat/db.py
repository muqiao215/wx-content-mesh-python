from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


settings = get_settings()
engine = create_engine(settings.database_url, echo=False, future=True, connect_args=_connect_args(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)
    _repair_invalid_enums()


def _repair_invalid_enums() -> None:
    from .models import ArticleStatus

    valid = {e.value for e in ArticleStatus}
    with engine.connect() as conn:
        rows = conn.execute(
            __import__("sqlalchemy").text("SELECT rowid, status FROM articles")
        ).fetchall()
        for rowid, status in rows:
            if status not in valid:
                conn.execute(
                    __import__("sqlalchemy").text(
                        "UPDATE articles SET status='created' WHERE rowid=:rid"
                    ),
                    {"rid": rowid},
                )
        conn.commit()


@contextmanager
def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
