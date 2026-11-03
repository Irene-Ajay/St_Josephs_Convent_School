"""Application entry point.

Start with:  python run.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import config
from app.auth import AccessDenied, LoginRequired
from app.database import create_tables

BASE_DIR = Path(__file__).resolve().parent

import logging
import sys

# Simple logger for startup and general application info
_logger = logging.getLogger("app")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("INFO:     %(message)s"))
    _logger.addHandler(_handler)

class LoggerWrapper:
    def info(self, msg: str, **kwargs) -> None:
        if kwargs:
            details = " ".join(f"{k}={v}" for k, v in kwargs.items())
            _logger.info(f"{msg} ({details})")
        else:
            _logger.info(msg)

log = LoggerWrapper()


templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["school_name"] = config.SCHOOL_NAME
templates.env.globals["today"] = date.today

app = FastAPI(title=config.SCHOOL_NAME, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def on_startup() -> None:
    """Creates the database file and tables if they do not exist, then makes
    sure there is at least one account to log in with. This is what lets the
    school run the system by double-clicking a single file."""
    # Add any columns missing from a database created by an earlier version,
    # BEFORE create_all runs or anything queries those tables.
    # Remove -wal/-shm files from an earlier WAL-mode run. If the folder is
    # synced (OneDrive etc.) these make the database unopenable.
    from app.database import clear_stale_wal_files

    stale = clear_stale_wal_files()
    if stale:
        log.info("removed_stale_wal_files", files=stale)

    from app.schema_upgrade import upgrade_schema

    changed = upgrade_schema()
    if changed:
        log.info("schema_upgraded", columns=changed)

    create_tables()

    from app.setup_data import ensure_first_admin

    ensure_first_admin()

    # There must always be a current academic year, so the office never has to
    # configure one before the system is usable.
    from app.academic import backfill_enrollments, ensure_current_year
    from app.database import SessionLocal

    with SessionLocal() as db:
        year = ensure_current_year(db)
        added = backfill_enrollments(db, year)
        if added:
            log.info("enrollments_backfilled", year=year.name, count=added)

    # Automatic backups: once now, then daily. Removes the human from the
    # loop - nobody has to remember to copy the database file.
    from app.backup import start_scheduler

    start_scheduler()


@app.exception_handler(LoginRequired)
async def _login_required(request: Request, _exc: LoginRequired):
    return RedirectResponse(f"/login?next={request.url.path}", status_code=303)


@app.exception_handler(AccessDenied)
async def _access_denied(request: Request, exc: AccessDenied):
    return templates.TemplateResponse(
        request,
        "message.html",
        { "title": "Not allowed", "message": str(exc)},
        status_code=403,
    )


@app.exception_handler(404)
async def _not_found(request: Request, _exc):
    return templates.TemplateResponse(
        request,
        "message.html",
        {
            "title": "Page not found",
            "message": "That page does not exist.",
        },
        status_code=404,
    )


from app.routers import (  # noqa: E402
    attendance, auth_routes, reports, staff, students, years,
)

app.include_router(auth_routes.router)
app.include_router(students.router)
app.include_router(attendance.router)
app.include_router(reports.router)
app.include_router(staff.router)
app.include_router(years.router)


@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/dashboard", status_code=303)
