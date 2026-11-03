"""All database tables, in one file.

Deliberately one file rather than a package. Someone maintaining this after
we leave can read the entire data model in a single sitting.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """Anyone who logs in: office admin, principal, or teacher."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default="TEACHER")  # ADMIN/PRINCIPAL/TEACHER
    email: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    sections: Mapped[list["Section"]] = relationship(back_populates="class_teacher")

    @property
    def is_admin(self) -> bool:
        return self.role in ("ADMIN", "PRINCIPAL")


class Section(Base):
    """A class-section, e.g. 'Class 8 - A'.

    Kept simple: one row per section, with one class teacher. Subject-wise
    period attendance is intentionally NOT modelled — the school marks
    attendance once a day, and building for periods they don't use would
    make the daily screen slower for no benefit.
    """

    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("name", "division", name="uq_section"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))       # "Class 8"
    division: Mapped[str] = mapped_column(String(5))    # "A"
    order_index: Mapped[int] = mapped_column(Integer, default=0)  # for sorting
    class_teacher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    class_teacher: Mapped[User | None] = relationship(back_populates="sections")
    students: Mapped[list["Student"]] = relationship(back_populates="section")

    @property
    def label(self) -> str:
        return f"{self.name} - {self.division}"


class AcademicYear(Base):
    """One row per school year: 2026-27, 2027-28, and so on.

    This is what makes the records permanent. Without a year dimension, a
    student moving from Class 8 to Class 9 overwrites their previous class
    and last year's batch becomes unrecoverable.
    """

    __tablename__ = "academic_years"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True)   # "2026-27"
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def covers(self, day: date) -> bool:
        return self.start_date <= day <= self.end_date


class Enrollment(Base):
    """Which class a student was in, in a given year.

    This is the historical record. One row per student per year, kept
    forever. 'Show me Class 10 of 2026-27' is a query against this table.
    """

    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "academic_year_id", name="uq_enrollment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    academic_year_id: Mapped[int] = mapped_column(
        ForeignKey("academic_years.id"), index=True
    )
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"), index=True)
    roll_number: Mapped[int | None] = mapped_column(Integer)
    # ENROLLED | PROMOTED | REPEATED | GRADUATED | LEFT
    status: Mapped[str] = mapped_column(String(20), default="ENROLLED")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    student: Mapped["Student"] = relationship(back_populates="enrollments")
    section: Mapped["Section"] = relationship()
    academic_year: Mapped[AcademicYear] = relationship()


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    admission_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    roll_number: Mapped[int | None] = mapped_column(Integer)
    full_name: Mapped[str] = mapped_column(String(150))
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id"), index=True)

    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(20))
    blood_group: Mapped[str | None] = mapped_column(String(5))

    # Guardian details are stored on the student rather than in a separate
    # table. A separate table is "more correct", but this matches the single
    # Excel row per student the school already keeps, which makes import and
    # correction far easier for the office staff.
    father_name: Mapped[str | None] = mapped_column(String(120))
    mother_name: Mapped[str | None] = mapped_column(String(120))
    guardian_phone: Mapped[str | None] = mapped_column(String(20))
    guardian_phone_alt: Mapped[str | None] = mapped_column(String(20))
    guardian_email: Mapped[str | None] = mapped_column(String(160))

    address: Mapped[str | None] = mapped_column(Text)
    admission_date: Mapped[date | None] = mapped_column(Date)

    # Kept short and safety-focused. Detailed medical history is deliberately
    # not collected: we cannot protect it adequately in a system with no
    # dedicated administrator.
    allergies_or_medical: Mapped[str | None] = mapped_column(Text)
    emergency_contact: Mapped[str | None] = mapped_column(String(120))

    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # ACTIVE | GRADUATED | LEFT | TRANSFERRED
    # Students are NEVER deleted. A student who left in 2027 must still appear
    # in the 2026-27 batch records years later.
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    section: Mapped[Section | None] = relationship(back_populates="students")
    enrollments: Mapped[list["Enrollment"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    attendance: Mapped[list["Attendance"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )

    @property
    def contact_number(self) -> str | None:
        return self.guardian_phone or self.guardian_phone_alt


class Attendance(Base):
    """One row per student per day.

    UNIQUE(student_id, date) means marking the same day twice updates rather
    than duplicating — teachers reopen a day surprisingly often.
    """

    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("student_id", "date", name="uq_attendance_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    # Tagged at write time so a year's attendance stays queryable even if
    # class structures are later renamed or reorganised.
    academic_year_id: Mapped[int | None] = mapped_column(
        ForeignKey("academic_years.id"), index=True, default=None
    )
    status: Mapped[str] = mapped_column(String(12), default="PRESENT")
    # PRESENT | ABSENT | LATE | HALF_DAY | LEAVE
    remarks: Mapped[str | None] = mapped_column(String(200))
    marked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    marked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    student: Mapped[Student] = relationship(back_populates="attendance")


class Holiday(Base):
    """Holidays are excluded from attendance percentage calculations.

    Without this, every vacation day counts as a school day and the whole
    school appears to have poor attendance.
    """

    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    description: Mapped[str] = mapped_column(String(120))


class MessageLog(Base):
    """Record of every parent message, so the school can prove what was sent
    and nobody gets messaged twice for the same absence."""

    __tablename__ = "message_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    channel: Mapped[str] = mapped_column(String(20))   # EMAIL | WHATSAPP_COPIED
    recipient: Mapped[str | None] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="SENT")
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    student: Mapped[Student] = relationship()


class ActivityLog(Base):
    """Lightweight audit trail. Answers 'who changed this and when' without
    the complexity of a full audit system."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    username: Mapped[str | None] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(120))
    details: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
