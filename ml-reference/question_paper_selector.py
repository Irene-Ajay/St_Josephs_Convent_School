"""Question paper generation as constrained selection (Module 6).

This is NOT a generative problem. Given a curated question bank and a
blueprint (marks, sections, difficulty mix, Bloom's mix, chapter weightage),
choosing the question subset is an optimisation problem. Framing it correctly
is the difference between "random questions with filters" and a defensible
system.

Where genuine ML does contribute: semantic duplicate detection (embeddings),
Bloom's auto-tagging, and empirical difficulty calibration from historical
performance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np


@dataclass(slots=True)
class Question:
    id: str
    chapter: str
    difficulty: str          # EASY | MEDIUM | HARD
    blooms_level: str
    marks: int
    question_type: str
    usage_count: int = 0
    last_used_at: date | None = None
    embedding: np.ndarray | None = None


@dataclass(slots=True)
class SectionSpec:
    label: str               # "A"
    question_type: str
    question_count: int
    marks_each: int


@dataclass(slots=True)
class Blueprint:
    total_marks: int
    sections: list[SectionSpec]
    difficulty_distribution: dict[str, float]   # {"EASY": .3, ...}
    blooms_distribution: dict[str, float] = field(default_factory=dict)
    chapter_weightage: dict[str, float] = field(default_factory=dict)
    exclude_used_within_days: int = 365


@dataclass(slots=True)
class GenerationResult:
    selected: list[Question]
    achieved_difficulty: dict[str, float]
    achieved_blooms: dict[str, float]
    blueprint_deviation: float
    warnings: list[str]


SIMILARITY_THRESHOLD = 0.85


def generate_paper(
    bank: list[Question],
    blueprint: Blueprint,
    *,
    today: date | None = None,
    avoid_ids: set[str] | None = None,
) -> GenerationResult:
    """Greedy weighted selection with duplicate suppression.

    A CP-SAT / ILP formulation gives a globally better distribution match and
    should be the primary implementation; this greedy version is the documented
    fallback for when the ILP is infeasible, and it always reports how far it
    landed from the blueprint rather than pretending it hit the target.
    """
    today = today or date.today()
    avoid_ids = avoid_ids or set()
    warnings: list[str] = []

    cutoff = today - timedelta(days=blueprint.exclude_used_within_days)
    pool = [
        q for q in bank
        if q.id not in avoid_ids
        and (q.last_used_at is None or q.last_used_at < cutoff)
    ]

    if len(pool) < sum(s.question_count for s in blueprint.sections):
        warnings.append(
            "Question bank is too small after applying the recency filter; "
            "recently-used questions had to be reconsidered."
        )
        pool = [q for q in bank if q.id not in avoid_ids]

    selected: list[Question] = []

    for spec in blueprint.sections:
        candidates = [
            q for q in pool
            if q.question_type == spec.question_type
            and q.marks == spec.marks_each
            and q not in selected
        ]
        if len(candidates) < spec.question_count:
            warnings.append(
                f"Section {spec.label}: only {len(candidates)} eligible "
                f"{spec.question_type} questions worth {spec.marks_each} marks "
                f"exist; {spec.question_count} were requested."
            )

        for _ in range(min(spec.question_count, len(candidates))):
            best = _pick_best(candidates, selected, blueprint)
            if best is None:
                break
            selected.append(best)
            candidates.remove(best)

    achieved_diff = _distribution(selected, "difficulty")
    achieved_bloom = _distribution(selected, "blooms_level")
    deviation = _l1_deviation(blueprint.difficulty_distribution, achieved_diff)

    if deviation > 0.15:
        warnings.append(
            f"Achieved difficulty mix deviates {deviation:.0%} from the "
            "blueprint. Expand the question bank for the under-represented "
            "difficulty levels."
        )

    return GenerationResult(
        selected=selected,
        achieved_difficulty=achieved_diff,
        achieved_blooms=achieved_bloom,
        blueprint_deviation=round(deviation, 4),
        warnings=warnings,
    )


def _pick_best(
    candidates: list[Question],
    selected: list[Question],
    blueprint: Blueprint,
) -> Question | None:
    """Score each candidate on how much it moves the paper toward the
    blueprint, penalising duplicates and heavily-used questions."""
    current_diff = _distribution(selected, "difficulty")
    best, best_score = None, -1e9

    for q in candidates:
        if _is_near_duplicate(q, selected):
            continue

        target = blueprint.difficulty_distribution.get(q.difficulty, 0.0)
        current = current_diff.get(q.difficulty, 0.0)
        # Positive when this difficulty is under-represented so far.
        score = (target - current) * 10.0

        if blueprint.chapter_weightage:
            chapter_target = blueprint.chapter_weightage.get(q.chapter, 0.0)
            chapter_current = _chapter_share(selected, q.chapter)
            score += (chapter_target - chapter_current) * 5.0

        # Prefer under-used questions so the bank rotates rather than
        # recycling the same 40 questions every year.
        score -= q.usage_count * 0.1

        if score > best_score:
            best, best_score = q, score

    return best


def _is_near_duplicate(q: Question, selected: list[Question]) -> bool:
    """Cosine similarity on sentence embeddings.

    Two near-identical questions in one paper is the most visible possible
    failure of a generator, and keyword matching does not catch paraphrases.
    """
    if q.embedding is None:
        return False
    for other in selected:
        if other.embedding is None:
            continue
        similarity = float(
            np.dot(q.embedding, other.embedding)
            / (np.linalg.norm(q.embedding) * np.linalg.norm(other.embedding))
        )
        if similarity >= SIMILARITY_THRESHOLD:
            return True
    return False


def _distribution(questions: list[Question], attr: str) -> dict[str, float]:
    if not questions:
        return {}
    total = len(questions)
    counts: dict[str, int] = {}
    for q in questions:
        key = getattr(q, attr)
        counts[key] = counts.get(key, 0) + 1
    return {k: round(v / total, 4) for k, v in counts.items()}


def _chapter_share(questions: list[Question], chapter: str) -> float:
    if not questions:
        return 0.0
    return sum(1 for q in questions if q.chapter == chapter) / len(questions)


def _l1_deviation(target: dict[str, float], achieved: dict[str, float]) -> float:
    """Reported to the user. A generator that says how close it got is more
    trustworthy than one that silently misses the blueprint."""
    keys = set(target) | set(achieved)
    return sum(abs(target.get(k, 0.0) - achieved.get(k, 0.0)) for k in keys) / 2


def calibrate_difficulty(
    mean_score_ratio: float, tagged_difficulty: str
) -> tuple[float, str | None]:
    """Lightweight Item Response Theory.

    After each exam, compare the observed mean score ratio against the human
    tag. A question tagged EASY that 65% of students fail is mis-tagged, and
    the bank should say so. This is what makes the question bank improve with
    use rather than decay.
    """
    empirical = round(1.0 - mean_score_ratio, 3)  # higher = harder

    expected = {"EASY": (0.0, 0.30), "MEDIUM": (0.30, 0.60), "HARD": (0.60, 1.0)}
    low, high = expected.get(tagged_difficulty, (0.0, 1.0))

    if not (low <= empirical <= high):
        suggested = next(
            (lvl for lvl, (lo, hi) in expected.items() if lo <= empirical <= hi),
            None,
        )
        return empirical, suggested
    return empirical, None
