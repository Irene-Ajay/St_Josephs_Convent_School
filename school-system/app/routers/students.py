"""Student records: list, add, edit, and bulk import from Excel."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import attendance_utils
from app.auth import AccessDenied, log_activity, require_admin, require_login
from app.database import get_db
from app.importer import build_template_workbook, import_students
from app.models import Section, Student, User

router = APIRouter(prefix="/students")


def _templates():
    from app.main import templates
    return templates


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@router.get("", response_class=HTMLResponse)
async def student_list(
    request: Request,
    q: str = "",
    section_id: int | None = None,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    query = select(Student).where(Student.is_active.is_(True))

    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Student.full_name.ilike(pattern),
                Student.admission_number.ilike(pattern),
                Student.guardian_phone.ilike(pattern),
            )
        )
    if section_id:
        query = query.where(Student.section_id == section_id)

    # A class teacher sees their own class by default rather than all 1,200
    # students, which is almost never what they want.
    if not user.is_admin and not section_id and not q:
        own = [
            s.id
            for s in db.scalars(select(Section).where(Section.class_teacher_id == user.id))
        ]
        if own:
            query = query.where(Student.section_id.in_(own))

    students = list(
        db.scalars(query.order_by(Student.section_id, Student.roll_number).limit(500))
    )
    sections = list(db.scalars(select(Section).order_by(Section.order_index)))

    return _templates().TemplateResponse(
        request,
        "students_list.html",
        {
            "user": user,
            "students": students,
            "sections": sections,
            "q": q,
            "section_id": section_id,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_student_form(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    sections = list(db.scalars(select(Section).order_by(Section.order_index)))
    return _templates().TemplateResponse(
        request,
        "student_form.html",
        { "user": user, "student": None, "sections": sections,
         "error": None},
    )


@router.post("/new")
async def create_student(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    admission_number = str(form.get("admission_number", "")).strip()

    if not admission_number or not str(form.get("full_name", "")).strip():
        sections = list(db.scalars(select(Section).order_by(Section.order_index)))
        return _templates().TemplateResponse(
            request,
            "student_form.html",
            { "user": user, "student": None,
                "sections": sections,
                "error": "Admission number and full name are required.",
            },
            status_code=400,
        )

    if db.scalar(select(Student.id).where(Student.admission_number == admission_number)):
        sections = list(db.scalars(select(Section).order_by(Section.order_index)))
        return _templates().TemplateResponse(
            request,
            "student_form.html",
            { "user": user, "student": None,
                "sections": sections,
                "error": f"Admission number {admission_number} already exists.",
            },
            status_code=400,
        )

    student = Student(
        admission_number=admission_number,
        full_name=str(form.get("full_name", "")).strip(),
        roll_number=int(form["roll_number"]) if form.get("roll_number") else None,
        section_id=int(form["section_id"]) if form.get("section_id") else None,
        date_of_birth=_parse_date(str(form.get("date_of_birth") or "")),
        gender=str(form.get("gender") or "") or None,
        blood_group=str(form.get("blood_group") or "") or None,
        father_name=str(form.get("father_name") or "") or None,
        mother_name=str(form.get("mother_name") or "") or None,
        guardian_phone=str(form.get("guardian_phone") or "") or None,
        guardian_phone_alt=str(form.get("guardian_phone_alt") or "") or None,
        guardian_email=str(form.get("guardian_email") or "") or None,
        address=str(form.get("address") or "") or None,
        allergies_or_medical=str(form.get("allergies_or_medical") or "") or None,
        emergency_contact=str(form.get("emergency_contact") or "") or None,
        admission_date=_parse_date(str(form.get("admission_date") or "")),
    )
    db.add(student)
    db.commit()
    log_activity(db, user, "Added student", f"{admission_number} {student.full_name}")
    return RedirectResponse(f"/students/{student.id}", status_code=303)


@router.get("/import", response_class=HTMLResponse)
async def import_page(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _templates().TemplateResponse(
        request,
        "students_import.html",
        { "user": user, "result": None},
    )


@router.get("/import/template")
async def download_template(user: User = Depends(require_admin)):
    """A blank Excel file with the right column headers.

    The school already keeps student lists in Excel. Giving them a template
    to paste into is far more realistic than asking the office to type
    1,200 students into a web form.
    """
    from fastapi.responses import Response

    content = build_template_workbook()
    return Response(
        content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": 'attachment; filename="student_import_template.xlsx"'
        },
    )


@router.post("/import", response_class=HTMLResponse)
async def import_submit(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    contents = await file.read()
    result = import_students(db, contents)
    log_activity(
        db, user, "Imported students",
        f"added={result.added} updated={result.updated} errors={len(result.errors)}",
    )
    return _templates().TemplateResponse(
        request,
        "students_import.html",
        { "user": user, "result": result},
    )


@router.get("/{student_id}", response_class=HTMLResponse)
async def student_detail(
    student_id: int,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if student is None:
        raise AccessDenied("That student record does not exist.")

    # A teacher may only open students in their own class.
    if not user.is_admin:
        if not student.section_id or not any(
            s.id == student.section_id
            for s in db.scalars(select(Section).where(Section.class_teacher_id == user.id))
        ):
            raise AccessDenied("You can only view students in your own class.")

    stats = attendance_utils.student_stats(db, student_id)
    from app.models import Attendance

    recent = list(
        db.scalars(
            select(Attendance)
            .where(Attendance.student_id == student_id)
            .order_by(Attendance.date.desc())
            .limit(30)
        )
    )

    from app import academic

    history = academic.student_history(db, student_id)

    return _templates().TemplateResponse(
        request,
        "student_detail.html",
        {
            "user": user,
            "student": student,
            "stats": stats,
            "recent": recent,
            "history": history,
            "labels": attendance_utils.STATUS_LABELS,
        },
    )
