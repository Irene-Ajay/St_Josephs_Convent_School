"""Safe schema upgrades for databases created by an earlier version.

`create_all()` creates missing TABLES but never adds missing COLUMNS to a
table that already exists. Anyone who ran an earlier build has a school.db
without the new columns, and the app would crash on first query.

A full migration tool (Alembic) is deliberately avoided here: it is one more
thing a future maintainer would have to learn. SQLite's ALTER TABLE ADD COLUMN
is enough for the additive changes this system needs, and this runs
automatically at startup.
"""

from __future__ import annotations

import sqlite3

from app.config import DB_PATH

# table -> column -> SQL type
REQUIRED_COLUMNS: dict[str, dict[str, str]] = {
    "students": {
        "status": "VARCHAR(20) DEFAULT 'ACTIVE'",
    },
    "attendance": {
        "academic_year_id": "INTEGER",
    },
}


def upgrade_schema() -> list[str]:
    """Add any missing columns. Returns a list of what changed."""
    if not DB_PATH.exists():
        return []

    applied: list[str] = []
    conn = sqlite3.connect(str(DB_PATH))
    try:
        existing_tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        for table, columns in REQUIRED_COLUMNS.items():
            if table not in existing_tables:
                continue  # create_all will build it fresh
            present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, definition in columns.items():
                if column not in present:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                    applied.append(f"{table}.{column}")
        conn.commit()
    finally:
        conn.close()

    return applied
