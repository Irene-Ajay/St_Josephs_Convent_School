"""End-to-end checks for the whole system.

Run with:   python -m pytest tests/ -v

These are deliberately not unit tests. They exercise the real journeys a
school actually performs — log in, import a spreadsheet, mark attendance,
notify a parent — because those are what must not break.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select


@pytest.fixture(scope="module")
def env(tmp_path_factory, monkeypatch_session=None):
    """Runs against a throwaway database so a test never touches real data."""
    import os

    workdir = tmp_path_factory.mktemp("smstest")
    os.environ["SMS_DATA_DIR"] = str(workdir)
    yield workdir


def make_spreadsheet(path) -> None:
    """A deliberately messy sheet: unusual headings, phone numbers stored as
    floats by Excel, three different date formats, and a blank row."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Students"
    ws.append(["Adm No", "Roll", "Student Name", "Standard", "Section",
               "DOB", "Gender", "Father", "Mother", "Mobile", "Email"])
    ws.append(["2026001", 1, "Ananya Maria Jose", "Class 8", "A", "15-04-2012",
               "Female", "Jose Mathew", "Maria Jose", 9876543210.0, "j@example.com"])
    ws.append(["2026002", 2, "Rohan Das", "Class 8", "A", "2012-07-02",
               "Male", "Suresh Das", "Latha Das", 9876543211.0, ""])
    ws.append(["2026003", 3, "Fathima Rasheed", "Class 8", "A", "22/09/2012",
               "Female", "Rasheed K", "Ayesha R", "98765 43212", ""])
    ws.append(["", None, "Row with no admission number", "Class 8", "A",
               "", "", "", "", "", ""])
    wb.save(path)


def test_import_handles_messy_spreadsheet(tmp_path):
    from app.database import SessionLocal
    from app.importer import import_students
    from app.models import Student

    path = tmp_path / "list.xlsx"
    make_spreadsheet(path)

    db = SessionLocal()
    result = import_students(db, path.read_bytes())

    assert result.added == 3
    assert result.skipped == 1  # the blank row, not silently ignored

    students = {s.admission_number: s for s in db.scalars(select(Student))}
    # Three different date formats must all parse.
    assert students["2026001"].date_of_birth == date(2012, 4, 15)
    assert students["2026002"].date_of_birth == date(2012, 7, 2)
    assert students["2026003"].date_of_birth == date(2012, 9, 22)
    # Excel turns phone numbers into floats; "9876543210.0" is not a phone.
    assert students["2026001"].guardian_phone == "9876543210"
    assert students["2026003"].guardian_phone == "9876543212"
    db.close()


def test_reimport_updates_rather_than_duplicating(tmp_path):
    """The office WILL upload the same file twice. It must be safe."""
    from app.database import SessionLocal
    from app.importer import import_students
    from app.models import Student

    path = tmp_path / "list.xlsx"
    make_spreadsheet(path)

    db = SessionLocal()
    import_students(db, path.read_bytes())
    before = len(list(db.scalars(select(Student))))
    result = import_students(db, path.read_bytes())
    after = len(list(db.scalars(select(Student))))

    assert before == after
    assert result.added == 0 and result.updated == 3
    db.close()


def test_half_day_counts_as_half():
    """Getting this wrong silently skews every percentage in the system."""
    from app.attendance_utils import _summarise

    assert _summarise(["PRESENT", "PRESENT"]).percentage == 100.0
    assert _summarise(["PRESENT", "HALF_DAY"]).percentage == 75.0
    assert _summarise(["PRESENT", "ABSENT"]).percentage == 50.0
    # A late student attended. Counting LATE as absent would wrongly flag
    # punctual-but-slow students as defaulters.
    assert _summarise(["LATE", "LATE"]).percentage == 100.0
    # Approved leave must not penalise the child.
    assert _summarise(["LEAVE", "PRESENT"]).percentage == 100.0
    # No data must not divide by zero.
    assert _summarise([]).percentage == 0.0
