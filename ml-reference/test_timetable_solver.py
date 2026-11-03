"""Timetable solver tests, including the infeasibility diagnostics."""

from __future__ import annotations

from timetable_solver import (
    Requirement,
    SolverInput,
    SolverStatus,
    TimetableSolver,
)


def _basic_input() -> SolverInput:
    return SolverInput(
        requirements=[
            Requirement("10A", "MATH", "T1", periods_per_week=5, is_core=True),
            Requirement("10A", "ENG", "T2", periods_per_week=4),
            Requirement("10B", "MATH", "T1", periods_per_week=5, is_core=True),
            Requirement("10B", "ENG", "T2", periods_per_week=4),
        ],
        days=[0, 1, 2, 3, 4],
        periods=[1, 2, 3, 4, 5, 6],
        rooms={"R1": "CLASSROOM", "R2": "CLASSROOM"},
        section_home_room={"10A": "R1", "10B": "R2"},
        teacher_max_per_day={"T1": 4, "T2": 4},
        teacher_max_per_week={"T1": 20, "T2": 20},
        late_periods={6},
    )


def test_solver_finds_feasible_schedule():
    result = TimetableSolver(_basic_input(), max_seconds=30).solve()
    assert result.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    assert len(result.entries) == 18  # 5+4+5+4


def test_no_teacher_double_booking():
    result = TimetableSolver(_basic_input(), max_seconds=30).solve()
    seen = set()
    for entry in result.entries:
        key = (entry["teacher_id"], entry["day_of_week"], entry["period_number"])
        assert key not in seen, "Teacher double-booked"
        seen.add(key)


def test_no_section_double_booking():
    result = TimetableSolver(_basic_input(), max_seconds=30).solve()
    seen = set()
    for entry in result.entries:
        key = (
            entry["class_section_id"],
            entry["day_of_week"],
            entry["period_number"],
        )
        assert key not in seen, "Section double-booked"
        seen.add(key)


def test_infeasible_input_returns_actionable_diagnostics():
    """The differentiating feature: 'no solution' with no explanation is
    useless to the person who has to fix the inputs."""
    data = _basic_input()
    # One teacher, far more periods than the week can hold.
    data.requirements = [
        Requirement("10A", "MATH", "T1", periods_per_week=20),
        Requirement("10B", "MATH", "T1", periods_per_week=20),
    ]
    data.teacher_max_per_week = {"T1": 20}

    result = TimetableSolver(data, max_seconds=20).solve()
    assert result.status == SolverStatus.INFEASIBLE
    assert result.conflicts
    conflict = result.conflicts[0]
    assert conflict.type == "INSUFFICIENT_TEACHER_CAPACITY"
    assert conflict.suggestion  # every conflict must suggest a fix


def test_diagnostics_detect_oversubscribed_section():
    data = _basic_input()
    data.requirements = [
        Requirement("10A", "MATH", "T1", periods_per_week=20),
        Requirement("10A", "ENG", "T2", periods_per_week=20),
    ]
    conflicts = TimetableSolver(data).diagnose()
    assert any(c.type == "SECTION_OVERSUBSCRIBED" for c in conflicts)
