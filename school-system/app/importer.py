"""Excel import and export.

The school already maintains student lists in Excel. Meeting them where they
are — rather than asking the office to retype everything — is the difference
between a system that gets adopted and one that gets abandoned in week two.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Section, Student

# Column heading -> model field. Headings are matched case-insensitively and
# ignoring spaces, so "Admission No" and "admission_no" both work. Office
# spreadsheets are never formatted the way you expect.
COLUMN_MAP = {
    "admissionnumber": "admission_number",
    "admissionno": "admission_number",
    "admno": "admission_number",
    "rollnumber": "roll_number",
    "rollno": "roll_number",
    "roll": "roll_number",
    "name": "full_name",
    "studentname": "full_name",
    "fullname": "full_name",
    "class": "_class",
    "standard": "_class",
    "division": "_division",
    "section": "_division",
    "dateofbirth": "date_of_birth",
    "dob": "date_of_birth",
    "gender": "gender",
    "bloodgroup": "blood_group",
    "fathername": "father_name",
    "father": "father_name",
    "mothername": "mother_name",
    "mother": "mother_name",
    "phone": "guardian_phone",
    "phonenumber": "guardian_phone",
    "contactnumber": "guardian_phone",
    "guardianphone": "guardian_phone",
    "mobile": "guardian_phone",
    "alternatephone": "guardian_phone_alt",
    "email": "guardian_email",
    "guardianemail": "guardian_email",
    "address": "address",
    "admissiondate": "admission_date",
    "medical": "allergies_or_medical",
    "allergies": "allergies_or_medical",
    "emergencycontact": "emergency_contact",
}

TEMPLATE_HEADERS = [
    "Admission Number", "Roll Number", "Name", "Class", "Division",
    "Date of Birth", "Gender", "Blood Group", "Father Name", "Mother Name",
    "Phone", "Alternate Phone", "Email", "Address", "Admission Date",
    "Allergies / Medical", "Emergency Contact",
]


@dataclass
class ImportResult:
    added: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    sections_created: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.added + self.updated


def _normalise(heading: object) -> str:
    return str(heading or "").strip().lower().replace(" ", "").replace("_", "").replace(".", "")


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _to_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def _clean_phone(value: object) -> str | None:
    """Excel loves turning phone numbers into 9.87654321e+09."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = str(value).strip()
    text = text.replace(" ", "").replace("-", "")
    return text or None


def build_template_workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Students"

    header_fill = PatternFill("solid", fgColor="243B53")
    header_font = Font(color="FFFFFF", bold=True)

    for index, heading in enumerate(TEMPLATE_HEADERS, start=1):
        cell = sheet.cell(row=1, column=index, value=heading)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        sheet.column_dimensions[get_column_letter(index)].width = max(len(heading) + 4, 14)

    sheet.cell(row=2, column=1, value="2026001")
    sheet.cell(row=2, column=2, value=1)
    sheet.cell(row=2, column=3, value="Ananya Maria Jose")
    sheet.cell(row=2, column=4, value="Class 8")
    sheet.cell(row=2, column=5, value="A")
    sheet.cell(row=2, column=6, value="2012-04-15")
    sheet.cell(row=2, column=7, value="Female")
    sheet.cell(row=2, column=11, value="9876543210")

    notes = workbook.create_sheet("How to use")
    for row, line in enumerate(
        [
            "HOW TO IMPORT STUDENTS",
            "",
            "1. Fill in the 'Students' sheet. Row 2 is an example — replace or delete it.",
            "2. 'Admission Number' and 'Name' are required. Everything else is optional.",
            "3. 'Class' and 'Division' create the class automatically if it does not exist.",
            "4. Dates can be written as 2012-04-15 or 15-04-2012.",
            "5. Save the file, then upload it on the Import page.",
            "",
            "Importing the same file twice is safe: existing students are updated,",
            "not duplicated. Admission Number is what identifies a student.",
        ],
        start=1,
    ):
        notes.cell(row=row, column=1, value=line)
    notes.column_dimensions["A"].width = 80

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def import_students(db: Session, file_bytes: bytes) -> ImportResult:
    result = ImportResult()

    try:
        workbook = load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Could not read the file. Is it a .xlsx file? ({exc})")
        return result

    sheet = workbook["Students"] if "Students" in workbook.sheetnames else workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if len(rows) < 2:
        result.errors.append("The sheet has no data rows.")
        return result

    headers = [_normalise(h) for h in rows[0]]
    fields = [COLUMN_MAP.get(h) for h in headers]

    if "admission_number" not in fields:
        result.errors.append(
            "No 'Admission Number' column found. Download the template and use its headings."
        )
        return result
    if "full_name" not in fields:
        result.errors.append("No 'Name' column found.")
        return result

    sections = {
        (s.name.strip().lower(), s.division.strip().upper()): s
        for s in db.scalars(select(Section))
    }
    imported: list[tuple[int, int | None, int | None]] = []

    for row_number, row in enumerate(rows[1:], start=2):
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        data: dict[str, object] = {}
        for field_name, value in zip(fields, row, strict=False):
            if field_name:
                data[field_name] = value

        admission_number = _clean(data.get("admission_number"))
        full_name = _clean(data.get("full_name"))

        if not admission_number or not full_name:
            result.skipped += 1
            result.errors.append(
                f"Row {row_number}: skipped — admission number or name is blank."
            )
            continue

        # Resolve or create the class-section.
        section_id = None
        class_name = _clean(data.get("_class"))
        division = (_clean(data.get("_division")) or "A").upper()
        if class_name:
            key = (class_name.strip().lower(), division)
            section = sections.get(key)
            if section is None:
                section = Section(name=class_name.strip(), division=division,
                                  order_index=len(sections) + 1)
                db.add(section)
                db.flush()
                sections[key] = section
                result.sections_created.append(section.label)
            section_id = section.id

        values = {
            "full_name": full_name,
            "roll_number": _to_int(data.get("roll_number")),
            "date_of_birth": _to_date(data.get("date_of_birth")),
            "gender": _clean(data.get("gender")),
            "blood_group": _clean(data.get("blood_group")),
            "father_name": _clean(data.get("father_name")),
            "mother_name": _clean(data.get("mother_name")),
            "guardian_phone": _clean_phone(data.get("guardian_phone")),
            "guardian_phone_alt": _clean_phone(data.get("guardian_phone_alt")),
            "guardian_email": _clean(data.get("guardian_email")),
            "address": _clean(data.get("address")),
            "admission_date": _to_date(data.get("admission_date")),
            "allergies_or_medical": _clean(data.get("allergies_or_medical")),
            "emergency_contact": _clean(data.get("emergency_contact")),
        }
        if section_id:
            values["section_id"] = section_id

        existing = db.scalar(
            select(Student).where(Student.admission_number == admission_number)
        )

        if existing:
            # Re-importing is safe and is how the office will fix typos:
            # correct the spreadsheet, upload again.
            for key_name, value in values.items():
                if value is not None:
                    setattr(existing, key_name, value)
            student = existing
            result.updated += 1
        else:
            student = Student(admission_number=admission_number, **values)
            db.add(student)
            result.added += 1

        db.flush()  # need student.id for the enrolment row
        imported.append((student.id, section_id, values.get("roll_number")))

    db.commit()

    # Record which class each student is in FOR THIS YEAR. This is what makes
    # the batch recoverable years later, after they have moved up several
    # classes or left the school.
    from app.academic import ensure_current_year, enrol

    year = ensure_current_year(db)
    for student_id, section_id, roll in imported:
        if section_id:
            enrol(db, student_id, section_id, year.id, roll)

    return result


def export_attendance_workbook(
    db: Session, section_id: int | None, start: date, end: date
) -> bytes:
    """Attendance register as Excel, for the school's paper records."""
    from app import attendance_utils
    from app.models import Attendance

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Attendance"

    query = select(Student).where(Student.is_active.is_(True))
    if section_id:
        query = query.where(Student.section_id == section_id)
    students = list(db.scalars(query.order_by(Student.roll_number, Student.full_name)))

    records: dict[tuple[int, date], str] = {}
    attendance_query = select(Attendance).where(
        Attendance.date >= start, Attendance.date <= end
    )
    if section_id:
        attendance_query = attendance_query.where(Attendance.section_id == section_id)
    for row in db.scalars(attendance_query):
        records[(row.student_id, row.date)] = row.status

    days: list[date] = []
    cursor = start
    while cursor <= end:
        if not attendance_utils.is_holiday(db, cursor):
            days.append(cursor)
        cursor = date.fromordinal(cursor.toordinal() + 1)

    header_fill = PatternFill("solid", fgColor="243B53")
    header_font = Font(color="FFFFFF", bold=True)

    headers = ["Roll", "Admission No", "Name", *[d.strftime("%d/%m") for d in days],
               "Present", "Absent", "%"]
    for index, heading in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=index, value=heading)
        cell.fill = header_fill
        cell.font = header_font

    good = PatternFill("solid", fgColor="DCFCE7")
    bad = PatternFill("solid", fgColor="FEE2E2")

    for row_index, student in enumerate(students, start=2):
        sheet.cell(row=row_index, column=1, value=student.roll_number)
        sheet.cell(row=row_index, column=2, value=student.admission_number)
        sheet.cell(row=row_index, column=3, value=student.full_name)

        statuses = []
        for day_index, day in enumerate(days, start=4):
            status = records.get((student.id, day))
            symbol = {"PRESENT": "P", "ABSENT": "A", "LATE": "L",
                      "HALF_DAY": "H", "LEAVE": "Lv"}.get(status or "", "")
            sheet.cell(row=row_index, column=day_index, value=symbol)
            if status:
                statuses.append(status)

        stats = attendance_utils._summarise(statuses)
        base = 4 + len(days)
        sheet.cell(row=row_index, column=base, value=stats.present)
        sheet.cell(row=row_index, column=base + 1, value=stats.absent)
        cell = sheet.cell(row=row_index, column=base + 2, value=stats.percentage)
        cell.fill = bad if stats.is_below_threshold else good

    sheet.column_dimensions["C"].width = 28
    sheet.freeze_panes = "D2"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
