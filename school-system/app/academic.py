"""Academic years, enrolments and promotion.

The rule this module exists to enforce: **nothing is ever overwritten**.
A student's class in 2026-27 stays recorded in 2026-27 forever, whatever
happens to them afterwards.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicYear, Attendance, Enrollment, Section, Student


def indian_school_year(today: date | None = None) -> tuple[str, date, date]:
    """Indian academic years run roughly June to April.

    Returns (name, start, end) for the year containing `today`.
    """
    today = today or date.today()
    start_year = today.year if today.month >= 6 else today.year - 1
    return (
        f"{start_year}-{str(start_year + 1)[-2:]}",   # "2026-27"
        date(start_year, 6, 1),
        date(start_year + 1, 4, 30),
    )


def ensure_current_year(db: Session) -> AcademicYear:
    """Guarantees there is always a current year, creating one if needed.

    Called at startup so the office never has to configure this before the
    system is usable.
    """
    current = db.scalar(select(AcademicYear).where(AcademicYear.is_current.is_(True)))
    if current is not None:
        return current

    name, start, end = indian_school_year()
    existing = db.scalar(select(AcademicYear).where(AcademicYear.name == name))
    if existing is not None:
        existing.is_current = True
        db.commit()
        return existing

    year = AcademicYear(name=name, start_date=start, end_date=end, is_current=True)
    db.add(year)
    db.commit()
    return year


def current_year(db: Session) -> AcademicYear | None:
    return db.scalar(select(AcademicYear).where(AcademicYear.is_current.is_(True)))


def set_current_year(db: Session, year_id: int) -> None:
    for year in db.scalars(select(AcademicYear)):
        year.is_current = year.id == year_id
    db.commit()


def year_for_date(db: Session, day: date) -> AcademicYear | None:
    """Which academic year does this date fall in? Used to tag attendance."""
    return db.scalar(
        select(AcademicYear).where(
            AcademicYear.start_date <= day, AcademicYear.end_date >= day
        )
    )


# ── Enrolment ────────────────────────────────────────────────────


def enrol(
    db: Session,
    student_id: int,
    section_id: int,
    year_id: int,
    roll_number: int | None = None,
) -> Enrollment:
    """Record a student in a class for a year. Idempotent."""
    existing = db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.academic_year_id == year_id,
        )
    )
    if existing is not None:
        existing.section_id = section_id
        if roll_number is not None:
            existing.roll_number = roll_number
        db.commit()
        return existing

    row = Enrollment(
        student_id=student_id, section_id=section_id,
        academic_year_id=year_id, roll_number=roll_number,
    )
    db.add(row)
    db.commit()
    return row


def backfill_enrollments(db: Session, year: AcademicYear) -> int:
    """Create enrolment rows for students imported before year tracking
    existed, so no historical record is lost."""
    count = 0
    for student in db.scalars(
        select(Student).where(Student.section_id.is_not(None))
    ):
        already = db.scalar(
            select(Enrollment.id).where(
                Enrollment.student_id == student.id,
                Enrollment.academic_year_id == year.id,
            )
        )
        if already is None:
            db.add(Enrollment(
                student_id=student.id, section_id=student.section_id,
                academic_year_id=year.id, roll_number=student.roll_number,
            ))
            count += 1
    db.commit()
    return count


def students_in(db: Session, section_id: int, year_id: int) -> list[Student]:
    """Who was in this class, in this year. Works for any past year."""
    return list(
        db.scalars(
            select(Student)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(
                Enrollment.section_id == section_id,
                Enrollment.academic_year_id == year_id,
            )
            .order_by(Enrollment.roll_number, Student.full_name)
        )
    )


def student_history(db: Session, student_id: int) -> list[Enrollment]:
    """Every year this student was enrolled — their full school career."""
    return list(
        db.scalars(
            select(Enrollment)
            .join(AcademicYear)
            .where(Enrollment.student_id == student_id)
            .order_by(AcademicYear.start_date)
        )
    )


# ── Promotion ────────────────────────────────────────────────────


def suggest_next_section(db: Session, section: Section) -> Section | None:
    """Guess the next class: 'Class 8' -> 'Class 9', same division.

    A guess only — the office confirms or changes it on screen. Schools name
    classes in ways no rule can fully predict.
    """
    import re

    match = re.search(r"(\d+)", section.name)
    if not match:
        return None
    nxt = section.name.replace(match.group(1), str(int(match.group(1)) + 1), 1)
    return db.scalar(
        select(Section).where(Section.name == nxt, Section.division == section.division)
    )


def promote(
    db: Session,
    *,
    from_year_id: int,
    to_year_id: int,
    moves: dict[int, int | None],
) -> dict:
    """Move students into next year's classes.

    `moves` maps student_id -> destination section_id, or None to mark the
    student graduated/left.

    Nothing is deleted or overwritten. Last year's enrolment row stays exactly
    as it was; a NEW row is created for the new year. That is what makes the
    batch record permanent.
    """
    promoted = graduated = 0

    for student_id, section_id in moves.items():
        old = db.scalar(
            select(Enrollment).where(
                Enrollment.student_id == student_id,
                Enrollment.academic_year_id == from_year_id,
            )
        )
        student = db.get(Student, student_id)
        if student is None:
            continue

        if section_id is None:
            if old is not None:
                old.status = "GRADUATED"
            student.status = "GRADUATED"
            student.is_active = False
            student.section_id = None
            graduated += 1
        else:
            if old is not None:
                old.status = "PROMOTED"
            enrol(db, student_id, section_id, to_year_id)
            student.section_id = section_id   # convenience "current class"
            promoted += 1

    db.commit()
    return {"promoted": promoted, "graduated": graduated}


def year_summary(db: Session, year_id: int) -> dict:
    """Headline numbers for a past year — the documentation view."""
    enrolments = list(db.scalars(
        select(Enrollment).where(Enrollment.academic_year_id == year_id)
    ))
    attendance = db.scalar(
        select(Attendance.id).where(Attendance.academic_year_id == year_id).limit(1)
    )
    sections = {e.section_id for e in enrolments}
    return {
        "students": len(enrolments),
        "sections": len(sections),
        "has_attendance": attendance is not None,
    }
