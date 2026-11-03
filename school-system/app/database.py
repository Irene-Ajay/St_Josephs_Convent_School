"""Database connection.

SQLite, synchronous. No connection pool to tune, no server to start, no
password to rotate. For a school of a few thousand students with tens of
concurrent users this is comfortably fast, and it means the entire backup
procedure is "copy data/school.db to a pen drive".
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL, DB_PATH

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):
    """Connection tuning.

    JOURNAL MODE: we deliberately use DELETE (SQLite's default), not WAL.

    WAL is faster for concurrent reads, but it creates `-wal` and `-shm`
    side-files and requires memory-mapping the `-shm` file. On OneDrive,
    Google Drive, Dropbox or any network share, that mapping breaks and
    SQLite raises "disk I/O error" -- leaving the database UNREADABLE.

    We hit exactly this during development: the file was intact, but every
    query failed because the folder was inside OneDrive. Schools will put
    this folder wherever is convenient, so correctness has to win over the
    marginal speed gain. Writes here are a few milliseconds and
    busy_timeout handles the contention.

    Set journal_mode = WAL in settings.ini only if the data folder is on a
    genuinely local disk and you need the concurrency.
    """
    cursor = dbapi_connection.cursor()
    try:
        from app import config

        mode = config.get("database", "journal_mode", "DELETE").upper()
    except Exception:  # noqa: BLE001 - config not ready during early import
        mode = "DELETE"

    if mode not in {"DELETE", "WAL", "TRUNCATE", "PERSIST"}:
        mode = "DELETE"

    try:
        cursor.execute(f"PRAGMA journal_mode={mode}")
    except Exception:  # noqa: BLE001
        cursor.execute("PRAGMA journal_mode=DELETE")

    cursor.execute("PRAGMA foreign_keys=ON")   # SQLite has these OFF by default
    cursor.execute("PRAGMA busy_timeout=5000")  # wait, don't fail, on contention
    cursor.execute("PRAGMA synchronous=FULL")   # survive a power cut mid-write
    cursor.close()


def clear_stale_wal_files() -> list[str]:
    """Remove orphaned -wal and -shm files left by an earlier WAL-mode run.

    If these exist and the folder is synced, the database cannot be opened at
    all. Removing them is safe ONLY when no process is using the database,
    which is why this runs at startup before anything connects.
    """
    removed = []
    for suffix in ("-wal", "-shm"):
        stale = Path(str(DB_PATH) + suffix)
        if stale.exists():
            try:
                stale.unlink()
                removed.append(stale.name)
            except OSError:
                pass
    return removed


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Called on startup. Creates any table that does not yet exist.

    No migration tool: for a system this size, additive schema changes and a
    file backup are safer than asking a future maintainer to learn Alembic.
    """
    from app import models  # noqa: F401  (registers the tables)

    Base.metadata.create_all(engine)
