"""Login, logout, password change, dashboard."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import attendance_utils
from app.auth import (
    clear_session,
    hash_password,
    log_activity,
    require_login,
    set_session,
    touch_login,
    verify_password,
)
from app.database import get_db
from app.models import Section, Student, User

router = APIRouter()


def _templates():
    from app.main import templates
    return templates


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/dashboard"):
    return _templates().TemplateResponse(request, "login.html", { "next": next, "error": None}
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/dashboard"),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.username == username.strip().lower()))

    # Identical message whether the user does not exist or the password is
    # wrong, so this page cannot be used to discover valid usernames.
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return _templates().TemplateResponse(
            request,
            "login.html",
            {
                "next": next,
                "error": "Incorrect username or password.",
            },
            status_code=401,
        )

    touch_login(db, user)
    log_activity(db, user, "Logged in")

    destination = "/change-password" if user.must_change_password else next
    response = RedirectResponse(destination, status_code=303)
    set_session(response, user)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    clear_session(response)
    return response


@router.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request, user: User = Depends(require_login)):
    return _templates().TemplateResponse(request, "change_password.html", { "user": user, "error": None}
    )


@router.post("/change-password")
async def change_password_submit(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    error = None
    if not verify_password(current_password, user.password_hash):
        error = "Your current password is not correct."
    elif len(new_password) < 8:
        error = "The new password must be at least 8 characters."
    elif new_password != confirm_password:
        error = "The two new passwords do not match."

    if error:
        return _templates().TemplateResponse(
            request,
            "change_password.html",
            { "user": user, "error": error},
            status_code=400,
        )

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.commit()
    log_activity(db, user, "Changed password")
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    today = date.today()
    summary = attendance_utils.school_summary(db, today)

    if user.is_admin:
        sections = list(db.scalars(select(Section).order_by(Section.order_index)))
    else:
        sections = list(
            db.scalars(
                select(Section)
                .where(Section.class_teacher_id == user.id)
                .order_by(Section.order_index)
            )
        )

    # Which of my sections still need attendance marked today? This is the
    # single most useful thing to show a teacher at 9 a.m.
    from app.models import Attendance

    pending = []
    for section in sections:
        marked = db.scalar(
            select(Attendance.id)
            .where(Attendance.section_id == section.id, Attendance.date == today)
            .limit(1)
        )
        count = db.scalar(
            select(Student.id).where(Student.section_id == section.id).limit(1)
        )
        if marked is None and count is not None:
            pending.append(section)

    low_attendance = attendance_utils.defaulters(db)[:10] if user.is_admin else []

    return _templates().TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "summary": summary,
            "sections": sections,
            "pending": pending,
            "low_attendance": low_attendance,
            "today": today,
        },
    )
