"""Attendance marking — the screen teachers use every single morning."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import attendance_utils
from app.auth import AccessDenied, can_access_section, log_activity, require_login
from app.database import get_db
from app.models import Attendance, Section, Student, User

router = APIRouter(prefix="/attendance")


def _templates():
    from app.main import templates
    return templates


@router.get("/mark/{section_id}", response_class=HTMLResponse)
async def mark_page(
    section_id: int,
    request: Request,
    day: str | None = None,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    if not can_access_section(user, section_id, db):
        raise AccessDenied("You are not the class teacher for this section.")

    section = db.get(Section, section_id)
    if section is None:
        raise AccessDenied("That class does not exist.")

    target_day = date.fromisoformat(day) if day else date.today()

    students = list(
        db.scalars(
            select(Student)
            .where(Student.section_id == section_id, Student.is_active.is_(True))
            .order_by(Student.roll_number, Student.full_name)
        )
    )

    # Anything already saved for this day, so reopening the screen shows what
    # was marked rather than resetting everyone to present.
    existing = {
        row.student_id: row
        for row in db.scalars(
            select(Attendance).where(
                Attendance.section_id == section_id, Attendance.date == target_day
            )
        )
    }

    # Overall percentage per student, shown next to their name. A teacher
    # deciding whether to chase a parent needs to know if this is the first
    # absence or the twentieth.
    percentages = attendance_utils.section_percentages(db, section_id)

    rows = [
        {
            "student": student,
            # Default PRESENT: marking 3 exceptions is far faster than
            # marking 42 presents, and teachers do this every day.
            "status": existing[student.id].status if student.id in existing else "PRESENT",
            "remarks": existing[student.id].remarks if student.id in existing else "",
            "percentage": percentages.get(student.id).percentage
            if percentages.get(student.id)
            else None,
        }
        for student in students
    ]

    return _templates().TemplateResponse(
        request,
        "attendance_mark.html",
        {
            "user": user,
            "section": section,
            "rows": rows,
            "day": target_day,
            "already_marked": bool(existing),
            "is_holiday": attendance_utils.is_holiday(db, target_day),
            "statuses": attendance_utils.STATUS_LABELS,
        },
    )


@router.post("/mark/{section_id}")
async def mark_submit(
    section_id: int,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    if not can_access_section(user, section_id, db):
        raise AccessDenied("You are not the class teacher for this section.")

    form = await request.form()
    target_day = date.fromisoformat(str(form.get("day", date.today().isoformat())))

    existing = {
        row.student_id: row
        for row in db.scalars(
            select(Attendance).where(
                Attendance.section_id == section_id, Attendance.date == target_day
            )
        )
    }

    # Tag every record with the academic year it belongs to, so a year's
    # attendance stays queryable forever even if classes are later renamed.
    from app import academic

    year = academic.year_for_date(db, target_day) or academic.current_year(db)
    year_id = year.id if year else None

    saved = 0
    for key, value in form.items():
        if not key.startswith("status_"):
            continue
        student_id = int(key.removeprefix("status_"))
        status = str(value)
        remarks = str(form.get(f"remarks_{student_id}", "")).strip() or None

        row = existing.get(student_id)
        if row is None:
            db.add(
                Attendance(
                    student_id=student_id,
                    section_id=section_id,
                    date=target_day,
                    academic_year_id=year_id,
                    status=status,
                    remarks=remarks,
                    marked_by_id=user.id,
                )
            )
        else:
            row.status = status
            row.remarks = remarks
            row.marked_by_id = user.id
            row.academic_year_id = row.academic_year_id or year_id
            row.marked_at = datetime.now()
        saved += 1

    db.commit()
    log_activity(
        db, user, "Marked attendance",
        f"section={section_id} date={target_day} students={saved}",
    )

    return RedirectResponse(
        f"/attendance/mark/{section_id}?day={target_day}&saved={saved}",
        status_code=303,
    )


@router.get("/absent-today", response_class=HTMLResponse)
async def absent_today(
    request: Request,
    day: str | None = None,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """Today's absentees with guardian phone numbers, ready to contact.

    This page is the practical heart of the system: it turns 'who is missing'
    into 'here is the number to call', which is what the office actually
    needs at 9:30 in the morning.
    """
    target_day = date.fromisoformat(day) if day else date.today()
    section_filter = None if user.is_admin else None

    results = attendance_utils.absent_students_on(db, target_day, section_filter)

    if not user.is_admin:
        allowed = {
            s.id
            for s in db.scalars(
                select(Section).where(Section.class_teacher_id == user.id)
            )
        }
        results = [(st, at) for st, at in results if at.section_id in allowed]

    entries = []
    for student, record in results:
        entries.append(
            {
                "student": student,
                "record": record,
                "consecutive": attendance_utils.consecutive_absences(
                    db, student.id, target_day
                ),
            }
        )

    return _templates().TemplateResponse(
        request,
        "absent_today.html",
        {
            "user": user,
            "entries": entries,
            "day": target_day,
        },
    )
