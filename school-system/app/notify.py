"""Parent notification.

Two channels, deliberately ordered by how quickly the school can actually
use them:

  1. WhatsApp / SMS copy-list  — works on day one, costs nothing. The system
     prepares the message and the number; a staff member sends it from the
     school phone.
  2. Email                     — automatic, free, needs only a Gmail App
     Password in settings.

Automated SMS is NOT included. In India it requires DLT registration by the
school (entity + 6-character sender ID + every template pre-approved), which
costs money and takes days, and cannot be done on the school's behalf. The
system is built so SMS can be added later without changing anything else.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import attendance_utils, config
from app.models import MessageLog, Student


@dataclass
class ParentMessage:
    student: Student
    phone: str | None
    email: str | None
    text: str
    consecutive_absences: int


def build_absence_message(student: Student, day: date, consecutive: int) -> str:
    school = config.get("school", "short_name") or config.SCHOOL_NAME
    date_text = day.strftime("%d %B %Y")

    if consecutive >= 3:
        return (
            f"Dear Parent, {student.full_name} has been absent from {school} "
            f"for {consecutive} consecutive days, including {date_text}. "
            f"Kindly contact the class teacher. - {school}"
        )
    return (
        f"Dear Parent, this is to inform you that {student.full_name} "
        f"was absent from {school} on {date_text}. "
        f"If this is unexpected, please contact the school office. - {school}"
    )


def prepare_absence_messages(
    db: Session, day: date, section_id: int | None = None
) -> list[ParentMessage]:
    """Build the list of messages for a day, skipping anyone already
    contacted. Sending a parent the same alert twice erodes trust in the
    whole system quickly."""
    already_sent = {
        row.student_id
        for row in db.scalars(select(MessageLog).where(MessageLog.date == day))
    }

    messages: list[ParentMessage] = []
    for student, _record in attendance_utils.absent_students_on(db, day, section_id):
        if student.id in already_sent:
            continue
        consecutive = attendance_utils.consecutive_absences(db, student.id, day)
        messages.append(
            ParentMessage(
                student=student,
                phone=student.contact_number,
                email=student.guardian_email,
                text=build_absence_message(student, day, consecutive),
                consecutive_absences=consecutive,
            )
        )
    return messages


def record_sent(
    db: Session,
    student_id: int,
    day: date,
    channel: str,
    recipient: str | None,
    message: str,
    status: str = "SENT",
    error: str | None = None,
) -> None:
    db.add(
        MessageLog(
            student_id=student_id, date=day, channel=channel,
            recipient=recipient, message=message, status=status, error=error,
        )
    )
    db.commit()


# ── Email ────────────────────────────────────────────────────────


def email_configured() -> bool:
    return (
        config.get_bool("email", "enabled")
        and bool(config.get("email", "username"))
        and bool(config.get("email", "password"))
    )


def send_email(to_address: str, subject: str, body: str) -> tuple[bool, str | None]:
    if not email_configured():
        return False, "Email is not configured in Settings."

    message = EmailMessage()
    message["From"] = (
        f"{config.get('email', 'from_name')} <{config.get('email', 'username')}>"
    )
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(
            config.get("email", "smtp_host"),
            config.get_int("email", "smtp_port", 587),
            timeout=20,
        ) as server:
            server.starttls()
            server.login(
                config.get("email", "username"), config.get("email", "password")
            )
            server.send_message(message)
        return True, None
    except Exception as exc:  # noqa: BLE001
        # Never let a mail failure break attendance marking. The absence is
        # already recorded; the message can be re-sent from the Absent page.
        return False, str(exc)


def send_absence_emails(db: Session, day: date, section_id: int | None = None) -> dict:
    messages = prepare_absence_messages(db, day, section_id)
    sent = failed = skipped = 0

    for item in messages:
        if not item.email:
            skipped += 1
            continue
        ok, error = send_email(
            item.email,
            f"Absence notification - {item.student.full_name}",
            item.text,
        )
        record_sent(
            db, item.student.id, day, "EMAIL", item.email, item.text,
            status="SENT" if ok else "FAILED", error=error,
        )
        sent += ok
        failed += not ok

    return {
        "total": len(messages), "sent": sent, "failed": failed,
        "no_email": skipped,
    }
