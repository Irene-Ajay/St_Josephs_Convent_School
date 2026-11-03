"""Attendance calculations.

Defined in one place so a percentage shown on the dashboard, in a report and
in an export can never disagree with each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.models import Attendance, Holiday, Student

# A half-day counts as half a day present. Getting this wrong silently skews
# every percentage in the system.
STATUS_WEIGHT: dict[str, float] = {
    "PRESENT": 1.0,
    "LATE": 1.0,
    "LEAVE": 1.0,       # approved leave does not penalise the student
    "HALF_DAY": 0.5,
    "ABSENT": 0.0,
}

STATUS_LABELS = {
    "PRESENT": "Present",
    "ABSENT": "Absent",
    "LATE": "Late",
    "HALF_DAY": "Half day",
    "LEAVE": "On leave",
}


@dataclass
class AttendanceStats:
    total_days: int
    present: int
    absent: int
    late: int
    half_day: int
    leave: int
    percentage: float

    @property
    def is_below_threshold(self) -> bool:
        return self.percentage < config.ATTENDANCE_THRESHOLD


def is_holiday(db: Session, day: date) -> bool:
    if day.weekday() == 6:  # Sunday
        return True
    return db.scalar(select(Holiday.id).where(Holiday.date == day)) is not None


def student_stats(
    db: Session,
    student_id: int,
    start: date | None = None,
    end: date | None = None,
) -> AttendanceStats:
    query = select(Attendance.status).where(Attendance.student_id == student_id)
    if start:
        query = query.where(Attendance.date >= start)
    if end:
        query = query.where(Attendance.date <= end)

    statuses = list(db.scalars(query))
    return _summarise(statuses)


def _summarise(statuses: list[str]) -> AttendanceStats:
    total = len(statuses)
    counts = {key: statuses.count(key) for key in STATUS_WEIGHT}
    weighted = sum(STATUS_WEIGHT.get(s, 0.0) for s in statuses)
    return AttendanceStats(
        total_days=total,
        present=counts["PRESENT"],
        absent=counts["ABSENT"],
        late=counts["LATE"],
        half_day=counts["HALF_DAY"],
        leave=counts["LEAVE"],
        percentage=round(weighted / total * 100, 1) if total else 0.0,
    )


def section_percentages(
    db: Session, section_id: int, start: date | None = None, end: date | None = None
) -> dict[int, AttendanceStats]:
    """One query for the whole section rather than one per student.

    Looping students and querying each is the classic mistake that makes a
    report take 30 seconds instead of 30 milliseconds.
    """
    query = select(Attendance.student_id, Attendance.status).where(
        Attendance.section_id == section_id
    )
    if start:
        query = query.where(Attendance.date >= start)
    if end:
        query = query.where(Attendance.date <= end)

    grouped: dict[int, list[str]] = {}
    for student_id, status in db.execute(query):
        grouped.setdefault(student_id, []).append(status)

    return {sid: _summarise(rows) for sid, rows in grouped.items()}


def defaulters(
    db: Session, section_id: int | None = None, threshold: float | None = None
) -> list[tuple[Student, AttendanceStats]]:
    """Students below the attendance threshold."""
    threshold = threshold if threshold is not None else config.ATTENDANCE_THRESHOLD

    student_query = select(Student).where(Student.is_active.is_(True))
    if section_id:
        student_query = student_query.where(Student.section_id == section_id)
    students = list(db.scalars(student_query))

    attendance_query = select(Attendance.student_id, Attendance.status)
    if section_id:
        attendance_query = attendance_query.where(Attendance.section_id == section_id)

    grouped: dict[int, list[str]] = {}
    for student_id, status in db.execute(attendance_query):
        grouped.setdefault(student_id, []).append(status)

    results = []
    for student in students:
        stats = _summarise(grouped.get(student.id, []))
        if stats.total_days > 0 and stats.percentage < threshold:
            results.append((student, stats))

    return sorted(results, key=lambda pair: pair[1].percentage)


def consecutive_absences(db: Session, student_id: int, as_of: date) -> int:
    """How many school days in a row this student has been absent.

    Used to decide whether a parent alert is warranted: one absence is
    usually nothing, three in a row is worth a phone call.
    """
    count = 0
    day = as_of
    checked = 0
    while checked < 30:  # look back at most 30 calendar days
        if not is_holiday(db, day):
            status = db.scalar(
                select(Attendance.status).where(
                    Attendance.student_id == student_id, Attendance.date == day
                )
            )
            if status == "ABSENT":
                count += 1
            elif status is not None:
                break
        day -= timedelta(days=1)
        checked += 1
    return count


def absent_students_on(db: Session, day: date, section_id: int | None = None):
    """Everyone marked absent on a given day, with their guardian contact."""
    query = (
        select(Student, Attendance)
        .join(Attendance, Attendance.student_id == Student.id)
        .where(Attendance.date == day, Attendance.status.in_(["ABSENT", "HALF_DAY"]))
    )
    if section_id:
        query = query.where(Attendance.section_id == section_id)
    return list(db.execute(query))


def school_summary(db: Session, day: date) -> dict:
    """Headline numbers for the dashboard."""
    total_students = db.scalar(
        select(func.count(Student.id)).where(Student.is_active.is_(True))
    ) or 0

    rows = list(db.scalars(select(Attendance.status).where(Attendance.date == day)))
    marked = len(rows)
    stats = _summarise(rows)

    return {
        "total_students": total_students,
        "marked_today": marked,
        "unmarked_today": max(total_students - marked, 0),
        "present_today": stats.present + stats.late,
        "absent_today": stats.absent,
        "percentage_today": stats.percentage,
    }
