"""Staff accounts and class assignment.

Without these pages the school cannot add a single teacher without a
programmer, which would make the whole system undeliverable. The office must
be able to run this alone after the project team leaves.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import AccessDenied, hash_password, log_activity, require_admin
from app.database import get_db
from app.models import Section, Student, User

router = APIRouter()


def _templates():
    from app.main import templates
    return templates


def _readable_password() -> str:
    """A password a teacher can be told over the phone and type correctly.

    Random hex is secure but gets written on a sticky note wrong. This is
    still 40+ bits of entropy and is changed on first login anyway.
    """
    words = ["lotus", "cedar", "river", "amber", "maple", "coral",
             "olive", "pearl", "swift", "quill", "ember", "linen"]
    return f"{secrets.choice(words)}-{secrets.choice(words)}-{secrets.randbelow(90) + 10}"


# ── Staff accounts ───────────────────────────────────────────────


@router.get("/staff", response_class=HTMLResponse)
async def staff_list(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    staff = list(db.scalars(select(User).order_by(User.role, User.full_name)))
    sections_by_teacher: dict[int, list[str]] = {}
    for section in db.scalars(select(Section).where(Section.class_teacher_id.is_not(None))):
        sections_by_teacher.setdefault(section.class_teacher_id, []).append(section.label)

    return _templates().TemplateResponse(
        request, "staff_list.html",
        {
            "user": user, "staff": staff,
            "sections_by_teacher": sections_by_teacher,
            "new_password": request.query_params.get("password"),
            "new_username": request.query_params.get("username"),
        },
    )


@router.get("/staff/new", response_class=HTMLResponse)
async def staff_new_form(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    sections = list(db.scalars(select(Section).order_by(Section.order_index)))
    return _templates().TemplateResponse(
        request, "staff_form.html",
        {"user": user, "staff_member": None, "sections": sections, "error": None},
    )


@router.post("/staff/new")
async def staff_create(
    request: Request,
    full_name: str = Form(...),
    username: str = Form(...),
    role: str = Form("TEACHER"),
    email: str = Form(""),
    phone: str = Form(""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    username = username.strip().lower().replace(" ", "")
    error = None

    if len(username) < 3:
        error = "Username must be at least 3 characters."
    elif db.scalar(select(User.id).where(User.username == username)):
        error = f"The username '{username}' is already taken."
    elif not full_name.strip():
        error = "Full name is required."

    if error:
        sections = list(db.scalars(select(Section).order_by(Section.order_index)))
        return _templates().TemplateResponse(
            request, "staff_form.html",
            {"user": user, "staff_member": None, "sections": sections, "error": error},
            status_code=400,
        )

    password = _readable_password()
    new_user = User(
        username=username,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        role=role if role in ("ADMIN", "PRINCIPAL", "TEACHER") else "TEACHER",
        email=email.strip() or None,
        phone=phone.strip() or None,
        must_change_password=True,   # they choose their own at first login
    )
    db.add(new_user)
    db.commit()
    log_activity(db, user, "Created staff account", f"{username} ({role})")

    # The password is shown once, on the next page. It is never recoverable
    # afterwards — only resettable — because we store a hash, not the password.
    return RedirectResponse(
        f"/staff?username={username}&password={password}", status_code=303
    )


@router.post("/staff/{staff_id}/reset-password")
async def staff_reset_password(
    staff_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, staff_id)
    if target is None:
        raise AccessDenied("That staff member does not exist.")

    password = _readable_password()
    target.password_hash = hash_password(password)
    target.must_change_password = True
    db.commit()
    log_activity(db, user, "Reset password", target.username)

    return RedirectResponse(
        f"/staff?username={target.username}&password={password}", status_code=303
    )


@router.post("/staff/{staff_id}/toggle-active")
async def staff_toggle_active(
    staff_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, staff_id)
    if target is None:
        raise AccessDenied("That staff member does not exist.")
    if target.id == user.id:
        raise AccessDenied("You cannot deactivate your own account.")

    # Staff who leave are deactivated, never deleted: their name must remain
    # attached to the attendance they marked.
    target.is_active = not target.is_active
    db.commit()
    log_activity(
        db, user,
        "Activated staff" if target.is_active else "Deactivated staff",
        target.username,
    )
    return RedirectResponse("/staff", status_code=303)


# ── Classes ──────────────────────────────────────────────────────


@router.get("/classes", response_class=HTMLResponse)
async def classes_list(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    sections = list(db.scalars(select(Section).order_by(Section.order_index,
                                                       Section.division)))
    teachers = list(
        db.scalars(
            select(User)
            .where(User.is_active.is_(True), User.role.in_(["TEACHER", "ADMIN", "PRINCIPAL"]))
            .order_by(User.full_name)
        )
    )
    counts = {
        section.id: db.scalar(
            select(Student.id).where(Student.section_id == section.id).limit(1)
        )
        for section in sections
    }
    strengths = {
        section.id: len(
            list(db.scalars(select(Student.id).where(
                Student.section_id == section.id, Student.is_active.is_(True)
            )))
        )
        for section in sections
    }

    return _templates().TemplateResponse(
        request, "classes.html",
        {"user": user, "sections": sections, "teachers": teachers,
         "counts": counts, "strengths": strengths,
         "saved": request.query_params.get("saved")},
    )


@router.post("/classes/new")
async def class_create(
    name: str = Form(...),
    division: str = Form("A"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    name = name.strip()
    division = division.strip().upper() or "A"

    existing = db.scalar(
        select(Section).where(Section.name == name, Section.division == division)
    )
    if existing is None and name:
        highest = db.scalar(select(Section.order_index).order_by(
            Section.order_index.desc()).limit(1)) or 0
        db.add(Section(name=name, division=division, order_index=highest + 1))
        db.commit()
        log_activity(db, user, "Created class", f"{name} - {division}")

    return RedirectResponse("/classes?saved=1", status_code=303)


@router.post("/classes/{section_id}/assign-teacher")
async def class_assign_teacher(
    section_id: int,
    teacher_id: str = Form(""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Assigning the class teacher is what grants a teacher access to that
    class's attendance and students. This is the access-control decision, made
    in plain language by the office rather than through a permissions screen."""
    section = db.get(Section, section_id)
    if section is None:
        raise AccessDenied("That class does not exist.")

    section.class_teacher_id = int(teacher_id) if teacher_id else None
    db.commit()
    log_activity(
        db, user, "Assigned class teacher",
        f"{section.label} -> {teacher_id or 'none'}",
    )
    return RedirectResponse("/classes?saved=1", status_code=303)
