"""Academic years, batch archive, and end-of-year promotion."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import academic
from app.auth import AccessDenied, log_activity, require_admin, require_login
from app.database import get_db
from app.models import AcademicYear, Enrollment, Section, Student, User

router = APIRouter()


def _templates():
    from app.main import templates
    return templates


@router.get("/years", response_class=HTMLResponse)
async def years_page(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    years = list(db.scalars(select(AcademicYear).order_by(AcademicYear.start_date.desc())))
    summaries = {y.id: academic.year_summary(db, y.id) for y in years}
    return _templates().TemplateResponse(
        request, "years.html",
        {"user": user, "years": years, "summaries": summaries,
         "saved": request.query_params.get("saved")},
    )


@router.post("/years/new")
async def year_create(
    name: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not db.scalar(select(AcademicYear).where(AcademicYear.name == name.strip())):
        db.add(AcademicYear(
            name=name.strip(),
            start_date=date.fromisoformat(start_date),
            end_date=date.fromisoformat(end_date),
        ))
        db.commit()
        log_activity(db, user, "Created academic year", name)
    return RedirectResponse("/years?saved=1", status_code=303)


@router.post("/years/{year_id}/set-current")
async def year_set_current(
    year_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    academic.set_current_year(db, year_id)
    year = db.get(AcademicYear, year_id)
    log_activity(db, user, "Changed current year", year.name if year else str(year_id))
    return RedirectResponse("/years?saved=1", status_code=303)


@router.get("/archive", response_class=HTMLResponse)
async def archive(
    request: Request,
    year_id: int | None = None,
    section_id: int | None = None,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """The documentation view: browse any past year's classes and students.

    This is what 'the database exists forever' actually means in practice —
    being able to open the Class 10 batch of 2026-27 in 2031.
    """
    years = list(db.scalars(select(AcademicYear).order_by(AcademicYear.start_date.desc())))
    if not years:
        return _templates().TemplateResponse(
            request, "message.html",
            {"title": "No years yet", "message": "No academic year has been set up."},
        )

    selected_year = db.get(AcademicYear, year_id) if year_id else academic.current_year(db)
    if selected_year is None:
        selected_year = years[0]

    section_ids = [
        row for row in db.scalars(
            select(Enrollment.section_id)
            .where(Enrollment.academic_year_id == selected_year.id)
            .distinct()
        )
    ]
    sections = [db.get(Section, sid) for sid in section_ids]
    sections = sorted([s for s in sections if s], key=lambda s: (s.order_index, s.division))

    students = (
        academic.students_in(db, section_id, selected_year.id) if section_id else []
    )
    rolls = {}
    if section_id:
        for e in db.scalars(select(Enrollment).where(
            Enrollment.academic_year_id == selected_year.id,
            Enrollment.section_id == section_id,
        )):
            rolls[e.student_id] = e.roll_number

    return _templates().TemplateResponse(
        request, "archive.html",
        {
            "user": user, "years": years, "selected_year": selected_year,
            "sections": sections, "section_id": section_id,
            "students": students, "rolls": rolls,
            "selected_section": db.get(Section, section_id) if section_id else None,
        },
    )


@router.get("/promotion", response_class=HTMLResponse)
async def promotion_page(
    request: Request,
    section_id: int | None = None,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    years = list(db.scalars(select(AcademicYear).order_by(AcademicYear.start_date.desc())))
    from_year = academic.current_year(db)
    if from_year is None:
        raise AccessDenied("No current academic year is set.")

    # Next year = the year starting after this one
    to_year = db.scalar(
        select(AcademicYear)
        .where(AcademicYear.start_date > from_year.start_date)
        .order_by(AcademicYear.start_date)
        .limit(1)
    )

    sections = list(db.scalars(select(Section).order_by(Section.order_index, Section.division)))
    all_sections = sections

    students, suggested = [], None
    if section_id:
        students = academic.students_in(db, section_id, from_year.id)
        section = db.get(Section, section_id)
        suggested = academic.suggest_next_section(db, section) if section else None

    return _templates().TemplateResponse(
        request, "promotion.html",
        {
            "user": user, "from_year": from_year, "to_year": to_year,
            "years": years, "sections": sections, "all_sections": all_sections,
            "section_id": section_id,
            "selected_section": db.get(Section, section_id) if section_id else None,
            "students": students, "suggested": suggested,
            "done": request.query_params.get("done"),
        },
    )


@router.post("/promotion/run")
async def promotion_run(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    from_year_id = int(str(form["from_year_id"]))
    to_year_id = int(str(form["to_year_id"]))

    moves: dict[int, int | None] = {}
    for key, value in form.items():
        if not key.startswith("dest_"):
            continue
        student_id = int(key.removeprefix("dest_"))
        text = str(value)
        if text in ("", "GRADUATE"):
            moves[student_id] = None      # graduated / left
        elif text == "SKIP":
            continue                       # repeat the year, leave untouched
        else:
            moves[student_id] = int(text)

    result = academic.promote(
        db, from_year_id=from_year_id, to_year_id=to_year_id, moves=moves
    )
    log_activity(db, user, "Promoted students", str(result))
    return RedirectResponse(
        f"/promotion?done={result['promoted']}+promoted,+{result['graduated']}+graduated",
        status_code=303,
    )
