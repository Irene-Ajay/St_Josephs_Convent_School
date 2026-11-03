"""Reports, exports, parent messaging, and settings."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import attendance_utils, backup, config, notify
from app.auth import log_activity, require_admin, require_login
from app.database import get_db
from app.importer import export_attendance_workbook
from app.models import MessageLog, Section, User

router = APIRouter()


def _templates():
    from app.main import templates
    return templates


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(
    request: Request,
    section_id: int | None = None,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    sections = list(db.scalars(select(Section).order_by(Section.order_index)))
    if not user.is_admin:
        sections = [s for s in sections if s.class_teacher_id == user.id]

    low = attendance_utils.defaulters(db, section_id)

    return _templates().TemplateResponse(
        request,
        "reports.html",
        { "user": user, "sections": sections,
            "section_id": section_id, "defaulters": low,
            "threshold": config.ATTENDANCE_THRESHOLD,
        },
    )


@router.get("/reports/export")
async def export_attendance(
    section_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    end_date = date.fromisoformat(end) if end else date.today()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=30)

    content = export_attendance_workbook(db, section_id, start_date, end_date)
    filename = f"attendance_{start_date}_{end_date}.xlsx"
    return Response(
        content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/messages", response_class=HTMLResponse)
async def messages_page(
    request: Request,
    day: str | None = None,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """Prepared parent messages, ready to send.

    The copy-to-WhatsApp list is intentionally the primary path: it works on
    the school's existing phone, on day one, at no cost. Email is automatic
    once configured. Automated SMS needs DLT registration by the school.
    """
    target_day = date.fromisoformat(day) if day else date.today()
    pending = notify.prepare_absence_messages(db, target_day)

    sent_today = list(
        db.scalars(
            select(MessageLog)
            .where(MessageLog.date == target_day)
            .order_by(MessageLog.sent_at.desc())
        )
    )

    return _templates().TemplateResponse(
        request,
        "messages.html",
        { "user": user, "day": target_day,
            "pending": pending, "sent": sent_today,
            "email_ready": notify.email_configured(),
        },
    )


@router.post("/messages/send-email")
async def send_absence_emails(
    day: str = Form(...),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    target_day = date.fromisoformat(day)
    result = notify.send_absence_emails(db, target_day)
    log_activity(db, user, "Sent absence emails", str(result))
    return RedirectResponse(
        f"/messages?day={target_day}&sent={result['sent']}&failed={result['failed']}",
        status_code=303,
    )


@router.post("/messages/mark-contacted")
async def mark_contacted(
    day: str = Form(...),
    student_id: int = Form(...),
    message: str = Form(""),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """Records that a staff member sent the WhatsApp message manually, so the
    parent is not contacted twice and the school has a record."""
    target_day = date.fromisoformat(day)
    notify.record_sent(
        db, student_id, target_day, "WHATSAPP_COPIED", None, message
    )
    return RedirectResponse(f"/messages?day={target_day}", status_code=303)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user: User = Depends(require_admin),
):
    return _templates().TemplateResponse(
        request,
        "settings.html",
        {
            "user": user,
            "config": config,
            "backup_info": backup.last_backup_info(),
            "saved": request.query_params.get("saved"),
            "backed_up": request.query_params.get("backed_up"),
        },
    )


@router.post("/settings")
async def settings_save(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    for key in ("name", "short_name", "phone", "email", "address"):
        if key in form:
            config.update("school", key, str(form[key]))

    if "threshold_percent" in form:
        config.update("attendance", "threshold_percent", str(form["threshold_percent"]))

    for key in ("enabled", "smtp_host", "smtp_port", "username", "from_name"):
        if key in form:
            value = "true" if key == "enabled" and form.get(key) else str(form.get(key, ""))
            config.update("email", key, value)
    if form.get("password"):
        config.update("email", "password", str(form["password"]))

    if "second_location" in form:
        config.update("backup", "second_location", str(form["second_location"]))

    log_activity(db, user, "Updated settings")
    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/settings/backup-now")
async def backup_now(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Manual backup, for just before a holiday or a software change."""
    path = backup.run_backup("manual")
    log_activity(db, user, "Ran backup", path.name if path else "no database")
    return RedirectResponse("/settings?backed_up=1", status_code=303)
