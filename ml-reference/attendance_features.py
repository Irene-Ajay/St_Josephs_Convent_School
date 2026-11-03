"""Attendance feature engineering.

SINGLE SOURCE OF TRUTH. This module is imported by BOTH the training pipeline
and the inference path. Never reimplement a feature in two places —
training/serving skew is the most common and most invisible ML bug, and it
produces a model that validates well and fails silently in production.

There is a test that asserts the column list is identical across both paths:
see tests/test_ml_feature_parity.py.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

FEATURE_COLUMNS: list[str] = [
    "current_attendance_pct",
    "rolling_7d_rate",
    "rolling_14d_rate",
    "rolling_30d_rate",
    "attendance_trend_slope",
    "max_consecutive_absences",
    "current_absence_streak",
    "monday_absence_rate",
    "friday_absence_rate",
    "post_holiday_absence_rate",
    "subject_attendance_variance",
    "late_arrival_rate",
    "prev_term_attendance_pct",
    "distance_from_school_km",
    "transport_required",
    "sibling_absence_correlation",
    "avg_marks_pct",
    "assignment_submission_rate",
]

# Deliberately excluded from the deployed model. See docs/03-ML-MODELS.md §3:
# including socio-economic proxies risks training a model that predicts
# poverty rather than academic or attendance risk. Retained here only so the
# ablation experiment described in the report can be reproduced.
ABLATION_ONLY_COLUMNS: list[str] = [
    "fee_overdue_flag",
    "guardian_income_band_ordinal",
]

PRESENT_STATUSES = {"PRESENT", "LATE", "EXCUSED", "ON_LEAVE"}


def build_attendance_features(
    records: pd.DataFrame,
    *,
    as_of: date,
    student_meta: pd.DataFrame | None = None,
    include_ablation: bool = False,
) -> pd.DataFrame:
    """Build one feature row per student.

    Parameters
    ----------
    records
        Long-format attendance: student_id, session_date, status, subject_id.
    as_of
        Cut-off date. Nothing after this date may influence the features —
        this is what makes temporal validation honest. A random train/test
        split leaks the future through the rolling windows and produces a
        flatteringly wrong score.
    student_meta
        Static per-student attributes (distance, transport, sibling group).
    """
    if records.empty:
        return pd.DataFrame(columns=["student_id", *FEATURE_COLUMNS])

    df = records.copy()
    df["session_date"] = pd.to_datetime(df["session_date"])
    df = df[df["session_date"].dt.date <= as_of]
    df["is_present"] = df["status"].isin(PRESENT_STATUSES).astype(int)
    df["is_late"] = (df["status"] == "LATE").astype(int)
    df["weekday"] = df["session_date"].dt.weekday  # 0 = Monday

    as_of_ts = pd.Timestamp(as_of)
    out: list[dict] = []

    for student_id, grp in df.groupby("student_id", sort=False):
        grp = grp.sort_values("session_date")
        row: dict[str, object] = {"student_id": student_id}

        row["current_attendance_pct"] = float(grp["is_present"].mean() * 100)

        for window in (7, 14, 30):
            recent = grp[grp["session_date"] >= as_of_ts - pd.Timedelta(days=window)]
            row[f"rolling_{window}d_rate"] = (
                float(recent["is_present"].mean() * 100)
                if len(recent)
                else row["current_attendance_pct"]
            )

        row["attendance_trend_slope"] = _weekly_trend_slope(grp)

        streaks = _absence_streaks(grp["is_present"].to_numpy())
        row["max_consecutive_absences"] = float(max(streaks, default=0))
        row["current_absence_streak"] = float(_trailing_absence_streak(
            grp["is_present"].to_numpy()
        ))

        # Long-weekend patterns look very different from illness and are one
        # of the more useful signals in practice.
        row["monday_absence_rate"] = _weekday_absence_rate(grp, 0)
        row["friday_absence_rate"] = _weekday_absence_rate(grp, 4)
        row["post_holiday_absence_rate"] = _post_gap_absence_rate(grp)

        # High variance across subjects indicates selective skipping, which is
        # a different problem from illness and needs a different intervention.
        if "subject_id" in grp.columns and grp["subject_id"].notna().any():
            per_subject = grp.groupby("subject_id")["is_present"].mean()
            row["subject_attendance_variance"] = float(per_subject.var(ddof=0) or 0.0)
        else:
            row["subject_attendance_variance"] = 0.0

        row["late_arrival_rate"] = float(grp["is_late"].mean())
        out.append(row)

    features = pd.DataFrame(out)

    if student_meta is not None and not student_meta.empty:
        features = features.merge(student_meta, on="student_id", how="left")

    for col in FEATURE_COLUMNS:
        if col not in features.columns:
            features[col] = np.nan

    columns = ["student_id", *FEATURE_COLUMNS]
    if include_ablation:
        for col in ABLATION_ONLY_COLUMNS:
            if col not in features.columns:
                features[col] = np.nan
        columns += ABLATION_ONLY_COLUMNS

    return features[columns]


def build_target(
    records: pd.DataFrame, *, term_end: date, threshold: float = 75.0
) -> pd.Series:
    """Binary label: did the student finish the term below the threshold?

    Computed from the FULL term, while features are computed only up to the
    cut-off. That gap is the prediction horizon.
    """
    df = records.copy()
    df["session_date"] = pd.to_datetime(df["session_date"])
    df = df[df["session_date"].dt.date <= term_end]
    df["is_present"] = df["status"].isin(PRESENT_STATUSES).astype(int)
    final = df.groupby("student_id")["is_present"].mean() * 100
    return (final < threshold).astype(int).rename("is_at_risk")


# ── helpers ──────────────────────────────────────────────────────


def _weekly_trend_slope(grp: pd.DataFrame) -> float:
    """Least-squares slope of weekly attendance rate. Direction of travel
    matters more than level: 90% and falling is a different situation from
    78% and stable."""
    weekly = (
        grp.set_index("session_date")["is_present"].resample("W").mean().dropna()
    )
    if len(weekly) < 3:
        return 0.0
    x = np.arange(len(weekly), dtype=float)
    return float(np.polyfit(x, weekly.to_numpy(dtype=float), 1)[0])


def _absence_streaks(is_present: np.ndarray) -> list[int]:
    streaks, current = [], 0
    for value in is_present:
        if value == 0:
            current += 1
        elif current:
            streaks.append(current)
            current = 0
    if current:
        streaks.append(current)
    return streaks


def _trailing_absence_streak(is_present: np.ndarray) -> int:
    count = 0
    for value in reversed(is_present):
        if value == 0:
            count += 1
        else:
            break
    return count


def _weekday_absence_rate(grp: pd.DataFrame, weekday: int) -> float:
    subset = grp[grp["weekday"] == weekday]
    return float(1 - subset["is_present"].mean()) if len(subset) else 0.0


def _post_gap_absence_rate(grp: pd.DataFrame, gap_days: int = 3) -> float:
    """Absence rate on the first school day after a gap of >= gap_days,
    which captures the extended-vacation pattern."""
    dates = grp["session_date"].to_numpy()
    present = grp["is_present"].to_numpy()
    if len(dates) < 2:
        return 0.0
    gaps = np.diff(dates).astype("timedelta64[D]").astype(int)
    idx = np.where(gaps >= gap_days)[0] + 1
    return float(1 - present[idx].mean()) if len(idx) else 0.0
