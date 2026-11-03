# ML Reference Code

Machine learning and optimisation code preserved from the full-scale design
study. **Not part of the running system** in `school-system/` — this is the
starting point for the project's AI component.

All files are standalone: no imports from the old `app.*` package, and
compatible with Python 3.8+.

| File | Lines | What it does |
|---|---|---|
| `timetable_solver.py` | 401 | Conflict-free timetable generation using Google OR-Tools CP-SAT. Includes infeasibility diagnostics that explain *why* no schedule exists rather than returning a bare failure. |
| `attendance_features.py` | 213 | Feature engineering for attendance-risk prediction: rolling rates, trend slope, absence streaks, day-of-week patterns. Enforces an `as_of` cut-off so temporal validation is honest. |
| `question_paper_selector.py` | 239 | Blueprint-driven question selection with embedding-based duplicate suppression and empirical difficulty calibration. |
| `model_registry.py` | 102 | Model versioning with a promotion guard and train/serve feature-parity check. |
| `test_timetable_solver.py` | 85 | Solver correctness + infeasibility diagnostics. |
| `test_attendance_features.py` | 90 | Feature stability and cut-off enforcement. |

## Verified working

```bash
pip install ortools pandas numpy pytest
pytest -q
# 11 passed
```

## How this connects to the working system

`school-system/` collects daily attendance into `data/school.db`. Once enough
history accumulates, `attendance_features.py` can build a feature table from
that data and train a risk model.

**The obstacle is data, not code.** A newly deployed system starts empty.
Either the pilot must run long enough to accumulate history, or the school's
existing paper registers must be digitised to provide it. Report this
limitation plainly rather than training on synthetic data and reporting a
flattering accuracy figure.

`timetable_solver.py` and `question_paper_selector.py` are complete and
runnable, but need input data the current system does not yet collect
(teacher assignments and periods; a question bank).
