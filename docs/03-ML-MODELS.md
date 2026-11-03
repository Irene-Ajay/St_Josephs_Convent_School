# Machine Learning & AI Design

This is the chapter your project will be judged on hardest. The guiding principle below is worth stating in the report's opening paragraph:

> **Match the algorithm to the problem structure.** Prediction problems get learned models. Constraint problems get solvers. Selection problems get optimisers. Using a neural network where a constraint solver is correct is not sophistication — it is a modelling error.

| Module | Problem | Correct technique | Not this |
|---|---|---|---|
| Attendance risk | Binary classification | Gradient boosting + SHAP | Deep learning on 3k rows |
| Attendance volume | Time series | SARIMA / Prophet | LSTM on 200 points |
| Performance risk | Multi-class classification | XGBoost + SHAP | — |
| Student segments | Clustering | K-Means / GMM + silhouette | Arbitrary rule buckets |
| Timetable | Constraint satisfaction | OR-Tools CP-SAT | Genetic algorithm |
| Question paper | Constrained selection | ILP / weighted sampling | "Random with filters" |
| Duplicate questions | Semantic similarity | Sentence embeddings | Keyword matching |
| Question tagging | Text classification | Fine-tuned transformer / LLM | Manual only |

---

## 1. Model A — Attendance Risk Classifier

**Question.** Will this student's attendance fall below the 75% threshold by term end?

**Target.** Binary. Computed retrospectively from historical terms: `1` if end-of-term % < 75.

**Features (engineered at a chosen cut-off point, e.g. week 8 of the term):**

| Feature | Rationale |
|---|---|
| `current_attendance_pct` | Baseline signal |
| `rolling_7d_rate`, `rolling_14d_rate`, `rolling_30d_rate` | Recency — a recent decline matters more than the average |
| `attendance_trend_slope` | Linear fit over weekly rates; direction of travel |
| `max_consecutive_absences` | Distinguishes one illness episode from chronic irregularity |
| `current_absence_streak` | Live signal |
| `monday_absence_rate`, `friday_absence_rate` | Long-weekend pattern |
| `post_holiday_absence_rate` | Extended-vacation pattern |
| `subject_attendance_variance` | High variance = selective skipping, a different problem from illness |
| `late_arrival_rate` | Often a leading indicator of absence |
| `prev_term_attendance_pct` | Strongest single predictor in most schools |
| `distance_from_school_km`, `transport_required` | Logistical friction |
| `sibling_absence_correlation` | Family-level causes (illness, travel, financial) |
| `fee_overdue_flag` | Correlates with disengagement — **use with care, see §7** |
| `avg_marks_pct` | Academic disengagement |
| `assignment_submission_rate` | Engagement proxy |

**Algorithm.** XGBoost / LightGBM. Compared in the report against Logistic Regression (interpretable baseline) and Random Forest. Report the comparison table — showing you tested alternatives is worth more than a single unexplained model.

**Class imbalance.** Roughly 5–12% positive. Handle with `scale_pos_weight`, stratified k-fold, and threshold tuning on the validation PR curve rather than the default 0.5.

**Metrics — report all of these, never accuracy alone:**
`Precision`, `Recall`, `F1`, `PR-AUC` (primary), `ROC-AUC`, confusion matrix, and a calibration curve. Recall is weighted higher than precision here: missing a genuinely at-risk child costs more than a false alarm that produces one extra phone call.

**Validation.** Temporal split — train on terms 1–2, test on term 3. A random split leaks future information through the rolling features and will produce a flatteringly wrong number. State this explicitly; interviewers and examiners look for it.

**Explainability.** SHAP `TreeExplainer`. The API returns the top-3 contributing features per prediction. A flag reading *"predicted at-risk: 4-day current streak, Monday absence rate 42%, downward trend since week 3"* is actionable; a bare `0.83` is not.

**Retraining.** Weekly Celery job. New version written to `ml_models`; promoted to active only if PR-AUC on a held-out set is at least as good as the incumbent. Automatic promotion without a guard is how production models silently degrade.

---

## 2. Model B — Attendance Volume Forecast

**Question.** What is next week's expected daily attendance rate for a class or the school?

**Data.** Daily attendance rate series per class-section.

**Approach.** SARIMA with weekly seasonality (`m=5` or `6` school days), plus exogenous regressors: day-before-holiday, day-after-holiday, exam-week flag, monsoon-month flag. Prophet is an acceptable alternative and is easier to explain in a viva; run both and compare MAE.

**Baseline to beat.** Seasonal naive (same weekday last week). If your model does not beat it, say so honestly — that is a legitimate finding, and reporting it demonstrates integrity that examiners notice.

**Metrics.** MAE, RMSE, MAPE, plus coverage of the 80% prediction interval.

**Caveat to state in the report.** Two to three years of daily data is thin for seasonal modelling. Present intervals, not point estimates, and be explicit about the limitation.

---

## 3. Model C — Academic Risk Classifier

**Question.** Which band will this student land in on the next exam: `SAFE`, `WATCH`, or `AT_RISK`?

**Target.** Three classes by next-exam percentage: ≥60 SAFE, 40–60 WATCH, <40 AT_RISK. Thresholds configurable in settings, not hard-coded.

**Features.**

| Group | Features |
|---|---|
| Academic history | Last-3-exam average, per-subject averages, trend slope, σ across subjects, best/worst subject gap |
| Relative standing | Percentile in section, rank change since last exam |
| Engagement | Attendance %, assignment submission rate, on-time submission rate, homework average |
| Subject context | Subject difficulty index, teacher-section historical mean |
| Trajectory | Improvement/decline flag, consecutive-decline count |
| Background | Guardian education band, sibling academic performance, distance, prior-school flag |

**Algorithm.** XGBoost multi-class with `class_weight='balanced'`. Ordinal regression is arguably a better fit since the classes are ordered — mention this in the report as a considered alternative and, if time permits, implement it and compare.

**Metrics.** Per-class precision/recall/F1, macro-F1 (primary), confusion matrix, Cohen's κ. Weight recall on `AT_RISK` heavily.

**Explainability.** SHAP force plot per student, rendered in the teacher UI as a plain-language sentence: *"Flagged mainly due to a 22-point drop in Mathematics and a 14% fall in attendance since the last exam."*

**Ethical guardrails (implement, then document):**
- Predictions are visible to teachers, principal and admin — **never to the student, and never to parents as a raw label**. A child told an algorithm predicts they will fail is a self-fulfilling prophecy.
- Predictions never affect section allocation, admission or fee decisions.
- Every flag carries "why" and a suggested intervention, not just a score.
- Socio-economic features are included for research analysis but must be **excluded from the deployed classifier** if ablation shows they contribute materially — otherwise the model learns to predict poverty rather than academic risk. Run the ablation and report it. This single experiment will elevate the project.

---

## 4. Model D — Student Clustering

**Question.** What natural cohorts exist, beyond simple marks ranking?

**Features (standardised).** Average marks %, marks σ, attendance %, assignment submission rate, improvement slope, subject-balance index, participation score.

**Algorithm.** K-Means with k selected by silhouette score and the elbow method (report both plots). Gaussian Mixture as a comparison — it permits soft membership, which is more honest for students near a boundary. Optionally reduce with PCA to 2D for the dashboard scatter.

**Deliverable.** Named clusters derived by inspecting centroids, for example:

| Cluster | Profile | Suggested intervention |
|---|---|---|
| Consistent High Achievers | High marks, high attendance, low variance | Enrichment, olympiad track |
| Capable but Disengaged | High marks, low attendance | Attendance counselling — highest-value cohort to catch |
| Steady Improvers | Mid marks, strong positive slope | Recognition and encouragement |
| Uneven Performers | Mid marks, high subject variance | Targeted subject support |
| Needs Support | Low marks, low attendance | Coordinated academic + family intervention |

Shipping "Cluster 0 … Cluster 4" is the difference between a data science project and a data science *product*. Name them.

**Validation.** Silhouette score, Davies-Bouldin index, and cluster stability under bootstrap resampling. Unstable clusters must not be shown to teachers as fact.

---

## 5. Timetable Solver (CP-SAT)

**Formulation.** Boolean variable `x[section, subject, teacher, room, day, period] ∈ {0,1}`.

**Hard constraints:**
```
1. ∀ teacher, day, period:  Σ x[·,·,teacher,·,day,period] ≤ 1
2. ∀ section, day, period:  Σ x[section,·,·,·,day,period] ≤ 1
3. ∀ room, day, period:     Σ x[·,·,·,room,day,period] ≤ 1
4. ∀ section, subject:      Σ x[section,subject,·,·,·,·] = periods_per_week
5. ∀ teacher, day:          Σ x[·,·,teacher,·,day,·] ≤ max_periods_per_day
6. ∀ teacher, week:         Σ x[·,·,teacher,·,·,·] ≤ max_periods_per_week
7. teacher availability:    x = 0 where teacher_availability = false
8. lab subjects:            occupy contiguous period pairs in lab-type rooms
9. only assigned teachers:  x = 0 unless (teacher,section,subject) ∈ teacher_assignments
```

**Soft objective (minimise weighted sum):**
```
w1 · subject_clustering_penalty      # same subject twice in a day
w2 · teacher_gap_count               # free period between two teaching periods
w3 · late_period_core_subject_count  # Maths/Science in the last periods
w4 · daily_load_imbalance            # σ of periods per day per section
w5 · teacher_preference_violations   # negative preference_score slots used
```
Weights are configurable per generation request so the principal can trade off priorities.

**Multiple candidates.** Run the solver with different random seeds and slightly perturbed weights to produce 3 distinct feasible solutions, each with its quality metrics. The principal chooses. A system that offers options is more usable than one that dictates.

**Infeasibility diagnostics — the differentiating feature.** When CP-SAT returns INFEASIBLE:
1. Re-solve with hard constraints converted to soft, with large penalties.
2. Inspect which penalties are non-zero in the relaxed solution.
3. Translate each into a human-readable conflict with a concrete suggestion.

This converts a dead end into a diagnostic tool. Most timetable projects only work on hand-cleaned data because they have no answer for infeasibility.

**Performance.** For ~30 sections × ~10 subjects × 40 slots, CP-SAT typically finds a good solution in 10–120 seconds. Run in Celery with a time limit and progress reporting. Always warm-start from the previously approved timetable when regenerating mid-year — it produces a more stable schedule and converges faster.

**Report comparison.** Benchmark against a Genetic Algorithm baseline: solve time, hard-constraint violations, soft penalty. CP-SAT should win decisively on all three. That table is one of the strongest slides in the presentation.

---

## 6. Question Paper Generation

### 6.1 Selection as constrained optimisation

Given a blueprint (total marks, section structure, difficulty mix, Bloom's mix, chapter weightage), select a question subset satisfying:

```
Hard:  Σ marks = target_total
       per-section question count and mark totals exact
       no question used in the last N days
       question type matches section requirement
       pairwise cosine similarity < 0.85 (no near-duplicates)

Soft (maximise):  distribution match to blueprint (minimise L1 deviation)
                  chapter coverage breadth
                  Bloom's alignment
                  preference for lower usage_count
```

Solve with OR-Tools CP-SAT (same solver, different model) or PuLP. Fall back to greedy weighted-random selection if the ILP is infeasible, and report the achieved deviation.

### 6.2 Semantic duplicate detection

`sentence-transformers/all-MiniLM-L6-v2` (384-dim, fast, CPU-friendly). Embed on question creation, store in `question_bank.embedding` (pgvector), index with HNSW.

- On creation: warn if cosine similarity > 0.90 against any existing question.
- During generation: hard-exclude pairs above 0.85 within the same paper.

This is the highest-value AI feature in the module and is straightforward to implement well.

### 6.3 Auto-tagging Bloom's level

Two options, both defensible:
- **Fine-tuned classifier:** DistilBERT on a labelled set of ~500 questions. Report accuracy per level. Cheap at inference, no API dependency.
- **LLM zero/few-shot:** prompt with Bloom's definitions and verb cues. Higher accuracy without training data, but costs per call and adds an external dependency.

Recommendation: LLM for suggestion at creation time, teacher confirms, and the confirmed labels accumulate into a dataset you then use to train the local classifier. Describe this bootstrapping loop in the report — it shows systems thinking, not just model thinking.

### 6.4 Empirical difficulty calibration

After each exam, join `paper_questions` → `marks` to compute per-question mean score ratio. Update `empirical_difficulty`. Flag mismatches: a question tagged EASY where the mean score ratio is 0.35 is mis-tagged.

This is a lightweight Item Response Theory application, and it means the question bank *improves with use* — a genuinely compelling story for the viva.

### 6.5 LLM-assisted question generation (optional)

Generate draft questions from syllabus text. Non-negotiable rules:
- `is_ai_generated = true`, `is_approved = false` on insert.
- Cannot enter a paper until a teacher approves.
- Duplicate-check against the existing bank before saving.

Never auto-publish AI-generated assessment content for children. State this policy in the report.

---

## 7. Fee Payment Delay Model — and Why It Is Constrained

Technically straightforward: gradient boosting on payment-latency history, installment size, sibling count, concession status, prior defaults.

**Deployment constraints, stated in the system and in the report:**
- Output is used **only** to order the reminder queue — who gets a gentle reminder first.
- It never gates access to results, exams, the portal, or any educational service.
- It is not shown to teachers, and never to students.
- Predicted-delay status is excluded from all academic models (see §3 ablation).

Include this as a "Responsible AI" section. Deliberately limiting a model you built is a stronger demonstration of maturity than deploying it everywhere you can.

---

## 8. MLOps

### 8.1 Feature store discipline

Feature engineering lives in `app/ml/features/` and is **imported by both training and inference**. Never reimplement a feature in two places — training/serving skew is the most common and most invisible ML bug.

```python
# app/ml/features/attendance.py
def build_attendance_features(df: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """Single source of truth. Called by both the trainer and the API."""
```

### 8.2 Model registry

Every trained model writes a `ml_models` row: version, algorithm, hyperparameters, metrics, feature names, training row count, artifact key. Load by `is_active`, never by filename.

Add a startup assertion that the loaded model's `feature_names` match what the feature builder currently produces. This catches the "we added a feature and inference broke silently" failure.

### 8.3 Monitoring

- **Prediction logging:** every prediction to `predictions`.
- **Outcome backfill:** nightly job writes `actual_value` once ground truth exists.
- **Live metrics:** rolling 30-day precision/recall computed from backfilled outcomes and surfaced in the admin panel.
- **Drift detection:** Population Stability Index on key features, monthly. PSI > 0.25 triggers a retrain alert.

Showing measured production accuracy alongside validation accuracy — and explaining any gap — is the single most impressive thing you can put in the results chapter.

### 8.4 Retraining schedule

| Model | Cadence | Promotion rule |
|---|---|---|
| Attendance risk | Weekly (Sun 02:00) | PR-AUC ≥ incumbent |
| Academic risk | After each exam publish | Macro-F1 ≥ incumbent |
| Clustering | Monthly | Silhouette ≥ 0.35 and stable |
| Attendance forecast | Weekly | MAE ≤ incumbent |
| Question difficulty | After each exam | Always (deterministic computation) |

---

## 9. Evaluation Plan for the Report

For each model, present:

1. Problem statement and why this algorithm class fits
2. Dataset description with row counts and class balance
3. Feature table with rationale per feature
4. Baseline comparison (at least two alternative algorithms)
5. Hyperparameter search method and final values
6. Validation strategy and *why* (temporal vs random — justify it)
7. Full metric table, never accuracy alone
8. Confusion matrix / residual plot
9. Feature importance and SHAP summary plot
10. Error analysis — inspect 10 wrong predictions and characterise the failure mode
11. Limitations, stated plainly
12. Ethical considerations

Item 10 is skipped in almost every student project. Doing it — "the model consistently misses students whose absence is caused by a single long medical episode, because the streak feature saturates" — demonstrates real understanding and is very hard to fake.

---

## 10. Honest Limitations to Declare

State these plainly. Examiners trust a project more when it names its own weaknesses.

1. **Single-institution data.** Models are tuned to St. Joseph's and will not transfer without retraining.
2. **Limited history.** Two to three years constrains seasonal modelling and rare-event learning.
3. **Synthetic augmentation.** Where synthetic data was used, say so and describe the generator's assumptions.
4. **Correlation, not causation.** The system flags association; it does not identify causes.
5. **Human-in-the-loop is mandatory.** No prediction triggers an automated consequence for a child.
6. **Cold start.** New students have no history; the system falls back to cohort averages and must display lower confidence.

---

*Next: `04-SECURITY.md`*
