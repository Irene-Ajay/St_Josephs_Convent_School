"""Automatic backups.

The weakest part of a local system is that someone must remember to copy the
database file. They will not. This module removes the human from the loop.

Backups use SQLite's online backup API rather than a plain file copy: copying
a database file while it is being written to can produce a corrupt backup that
looks fine until the day you need it.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

from app import config
from app.config import DATA_DIR, DB_PATH

BACKUP_DIR = DATA_DIR / "backups"
KEEP_DAILY = 30      # roughly a month of daily copies
KEEP_MONTHLY = 12    # plus one per month for a year


def _safe_copy(destination: Path) -> None:
    """SQLite's own backup API — safe to run while teachers are using the
    system, unlike shutil.copy on a live database."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(DB_PATH))
    target = sqlite3.connect(str(destination))
    try:
        with target:
            source.backup(target)
    finally:
        target.close()
        source.close()


def run_backup(reason: str = "scheduled") -> Path | None:
    """Create today's backup. Returns the path, or None if nothing to back up."""
    if not DB_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    destination = BACKUP_DIR / f"school-{today.isoformat()}.db"

    _safe_copy(destination)
    _prune()
    _copy_to_second_location(destination)

    (BACKUP_DIR / "last_backup.txt").write_text(
        f"{datetime.now().strftime('%d %B %Y, %I:%M %p')}\n"
        f"file: {destination.name}\n"
        f"reason: {reason}\n",
        encoding="utf-8",
    )
    return destination


def _prune() -> None:
    """Keep the last 30 daily backups, plus the first backup of each month.

    Without pruning, a school running this for five years accumulates ~1,800
    files. With it, storage stays trivial and old months remain recoverable.
    """
    backups = sorted(BACKUP_DIR.glob("school-*.db"), reverse=True)
    if len(backups) <= KEEP_DAILY:
        return

    keep = set(backups[:KEEP_DAILY])

    monthly_seen: set[str] = set()
    for path in sorted(backups):  # oldest first, so we keep each month's first
        stamp = path.stem.removeprefix("school-")
        month = stamp[:7]  # YYYY-MM
        if month not in monthly_seen:
            monthly_seen.add(month)
            keep.add(path)

    # Trim monthly archive to the most recent KEEP_MONTHLY months
    monthly = sorted(
        (p for p in keep if p not in backups[:KEEP_DAILY]), reverse=True
    )
    for path in monthly[KEEP_MONTHLY:]:
        keep.discard(path)

    for path in backups:
        if path not in keep:
            path.unlink(missing_ok=True)


def _copy_to_second_location(source: Path) -> None:
    """Copy to a second folder if the school has configured one.

    A backup sitting on the same hard disk as the original protects against
    mistakes, not against the disk failing. The second location should be a
    pen drive, a network share, or a synced folder such as the school's own
    Google Drive or OneDrive.
    """
    target_dir = config.get("backup", "second_location", "").strip()
    if not target_dir:
        return
    try:
        destination = Path(target_dir)
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination / source.name)
    except Exception:  # noqa: BLE001
        # A missing pen drive must never stop the school system from running.
        pass


def last_backup_info() -> dict:
    """Shown on the Settings page so the office can see it is working."""
    marker = BACKUP_DIR / "last_backup.txt"
    backups = sorted(BACKUP_DIR.glob("school-*.db"), reverse=True) if BACKUP_DIR.exists() else []

    total_bytes = sum(p.stat().st_size for p in backups)
    return {
        "last_run": marker.read_text(encoding="utf-8").splitlines()[0]
        if marker.exists() else None,
        "count": len(backups),
        "newest": backups[0].name if backups else None,
        "oldest": backups[-1].name if backups else None,
        "total_size_kb": round(total_bytes / 1024),
        "folder": str(BACKUP_DIR),
        "second_location": config.get("backup", "second_location", ""),
    }


def start_scheduler() -> None:
    """Back up once at startup, then daily.

    Backing up on startup matters more than it looks: a school PC that is
    switched on each morning gets a backup every school day even if the
    machine is shut down before any scheduled time arrives.
    """
    try:
        run_backup("startup")
    except Exception:  # noqa: BLE001
        pass

    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            run_backup, "cron", hour=15, minute=30, kwargs={"reason": "daily"},
            id="daily_backup", replace_existing=True,
        )
        scheduler.start()
    except Exception:  # noqa: BLE001
        # If the scheduler cannot start, the startup backup still ran.
        pass
