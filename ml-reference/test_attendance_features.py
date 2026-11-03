"""The ML test almost every student project omits.

Training/serving skew is invisible: the model validates well, then quietly
degrades in production because inference builds features slightly differently
from training. These tests make that impossible.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from attendance_features import (
    FEATURE_COLUMNS,
    build_attendance_features,
    build_target,
)


@pytest.fixture
def sample_records() -> pd.DataFrame:
    start = date(2026, 1, 5)
    rows = []
    for student in ("s1", "s2", "s3"):
        for offset in range(90):
            day = start + timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            # s3 deteriorates over time; s1 is reliable; s2 skips Mondays.
            if student == "s1":
                status = "PRESENT"
            elif student == "s2":
                status = "ABSENT" if day.weekday() == 0 else "PRESENT"
            else:
                status = "ABSENT" if offset > 55 and offset % 2 == 0 else "PRESENT"
            rows.append(
                {
                    "student_id": student,
                    "session_date": day,
                    "status": status,
                    "subject_id": None,
                }
            )
    return pd.DataFrame(rows)


def test_feature_columns_are_stable(sample_records):
    features = build_attendance_features(sample_records, as_of=date(2026, 3, 1))
    assert list(features.columns) == ["student_id", *FEATURE_COLUMNS]


def test_training_and_inference_produce_identical_columns(sample_records):
    """Guards against train/serve skew — the invisible ML bug."""
    train = build_attendance_features(sample_records, as_of=date(2026, 2, 15))
    infer = build_attendance_features(sample_records, as_of=date(2026, 4, 1))
    assert list(train.columns) == list(infer.columns)


def test_as_of_cutoff_excludes_future_data(sample_records):
    """A random train/test split leaks the future through rolling windows and
    produces a flatteringly wrong score. The cut-off must be respected."""
    early = build_attendance_features(sample_records, as_of=date(2026, 1, 20))
    late = build_attendance_features(sample_records, as_of=date(2026, 4, 1))
    s3_early = early.loc[early.student_id == "s3", "current_attendance_pct"].iloc[0]
    s3_late = late.loc[late.student_id == "s3", "current_attendance_pct"].iloc[0]
    # s3 only deteriorates after day 55, so the early cut-off must not see it.
    assert s3_early > s3_late


def test_monday_absence_pattern_is_detected(sample_records):
    features = build_attendance_features(sample_records, as_of=date(2026, 4, 1))
    s2 = features.loc[features.student_id == "s2"].iloc[0]
    s1 = features.loc[features.student_id == "s1"].iloc[0]
    assert s2["monday_absence_rate"] > 0.9
    assert s1["monday_absence_rate"] == 0.0


def test_target_is_binary_and_uses_full_term(sample_records):
    target = build_target(sample_records, term_end=date(2026, 4, 30), threshold=75.0)
    assert set(target.unique()).issubset({0, 1})
    assert target.loc["s1"] == 0  # perfect attendance is never at risk


def test_empty_input_returns_empty_frame_not_error():
    empty = pd.DataFrame(columns=["student_id", "session_date", "status"])
    result = build_attendance_features(empty, as_of=date.today())
    assert result.empty
    assert "student_id" in result.columns
