"""Deterministic, explainable match scoring.

Invariant: this module is the only place a match score is computed. The LLM explains the breakdown
produced here and never changes the number. Pure functions only, so it is easy to test and audit.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field

from rolewise.config import Settings, get_settings

_WORD_RE = re.compile(r"[a-z]+")
# Seniority/level modifiers don't distinguish one role from another, so they're ignored on both
# sides before comparing. Role words (engineer, analyst, manager, ...) are kept and must match.
_TITLE_STOPWORDS = {"senior", "staff", "principal", "lead", "junior", "jr", "sr", "i", "ii", "iii", "iv"}


def _title_words(title: str) -> set[str]:
    return set(_WORD_RE.findall(title.lower())) - _TITLE_STOPWORDS


def _title_relevant(job_title: str, target_titles: list[str]) -> bool:
    """True when every distinctive word of a target title also appears in the job title
    (e.g. "Data Engineer" matches "Senior Data Engineer II" but not "Full Stack Engineer")."""
    job_words = _title_words(job_title)
    for t in target_titles:
        t_words = _title_words(t)
        if t_words and t_words <= job_words:
            return True
    return False

SKILL_KINDS = {"required_skill", "preferred_skill", "domain", "education"}
COMPONENT_BY_KIND = {
    "required_skill": "required",
    "preferred_skill": "preferred",
    "domain": "domain",
    "education": "education",
    "experience": "experience",
}


@dataclass
class FactIn:
    id: str
    kind: str
    title: str
    verified: bool
    source: str
    embedding: list[float]
    years: float | None = None  # for role facts


@dataclass
class RequirementIn:
    id: str
    kind: str
    text: str
    embedding: list[float]
    normalized: str | None = None
    min_years: float | None = None


@dataclass
class JobIn:
    title: str
    description: str
    company: str
    location: str | None
    remote_mode: str | None
    salary_max: int | None
    requirements: list[RequirementIn]


@dataclass
class PreferencesIn:
    locations: list[str] = field(default_factory=list)
    remote_modes: list[str] = field(default_factory=list)
    salary_min: int | None = None
    dealbreakers: list[str] = field(default_factory=list)
    target_titles: list[str] = field(default_factory=list)


@dataclass
class RequirementResult:
    requirement_id: str
    kind: str
    text: str
    status: str  # matched|partial|missing
    credit: float  # 1.0, 0.5 or 0.0 (experience can be fractional)
    similarity: float
    fact_id: str | None
    fact_title: str | None
    fact_source: str | None


@dataclass
class MatchResult:
    score: float  # 0..100
    filtered_out: str | None  # reason when a hard filter excluded the job
    components: dict[str, float | None]  # 0..1 per component, None when not applicable
    weights_used: dict[str, float]
    preference_checks: dict[str, bool]
    requirements: list[RequirementResult]

    def to_dict(self) -> dict:
        return asdict(self)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _best_fact(req: RequirementIn, facts: list[FactIn]) -> tuple[FactIn | None, float]:
    best, best_sim = None, 0.0
    target = (req.normalized or req.text).strip().lower()
    for f in facts:
        sim = 1.0 if f.title.strip().lower() == target else cosine(req.embedding, f.embedding)
        if sim > best_sim:
            best, best_sim = f, sim
    return best, best_sim


def _classify(sim: float, s: Settings) -> tuple[str, float]:
    if sim >= s.match_threshold:
        return "matched", 1.0
    if sim >= s.partial_threshold:
        return "partial", 0.5
    return "missing", 0.0


def hard_filter(job: JobIn, prefs: PreferencesIn) -> str | None:
    haystack = f"{job.company} {job.title} {job.description}".lower()
    for d in prefs.dealbreakers:
        if d.strip() and d.strip().lower() in haystack:
            return f"dealbreaker: {d}"
    if prefs.salary_min and job.salary_max and job.salary_max < prefs.salary_min:
        return "salary below minimum"
    return None


def preference_checks(job: JobIn, prefs: PreferencesIn) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    if prefs.remote_modes and job.remote_mode:
        checks["remote_mode"] = job.remote_mode in prefs.remote_modes
    if prefs.locations and job.location:
        loc = job.location.lower()
        checks["location"] = job.remote_mode == "remote" or any(p.lower() in loc for p in prefs.locations)
    if prefs.salary_min and job.salary_max:
        checks["salary"] = job.salary_max >= prefs.salary_min
    if prefs.target_titles:
        checks["target_title"] = _title_relevant(job.title, prefs.target_titles)
    return checks


def score_match(
    job: JobIn, facts: list[FactIn], prefs: PreferencesIn, settings: Settings | None = None
) -> MatchResult:
    s = settings or get_settings()
    verified = [f for f in facts if f.verified]  # invariant: unverified facts never count

    reason = hard_filter(job, prefs)
    if reason:
        return MatchResult(0.0, reason, {}, {}, {}, [])

    total_years = sum(f.years or 0.0 for f in verified if f.kind == "role")
    results: list[RequirementResult] = []
    for req in job.requirements:
        if req.kind == "experience" and req.min_years:
            credit = min(1.0, total_years / req.min_years)
            status = "matched" if credit >= 1.0 else "partial" if credit >= 0.5 else "missing"
            results.append(
                RequirementResult(req.id, req.kind, req.text, status, round(credit, 3), credit, None, None, None)
            )
            continue
        fact, sim = _best_fact(req, verified)
        status, credit = _classify(sim, s)
        results.append(
            RequirementResult(
                req.id, req.kind, req.text, status, credit, round(sim, 4),
                fact.id if fact and status != "missing" else None,
                fact.title if fact and status != "missing" else None,
                fact.source if fact and status != "missing" else None,
            )
        )

    components: dict[str, float | None] = {k: None for k in COMPONENT_BY_KIND.values()}
    for comp in components:
        credits = [r.credit for r in results if COMPONENT_BY_KIND.get(r.kind) == comp]
        if credits:
            components[comp] = sum(credits) / len(credits)

    checks = preference_checks(job, prefs)
    components["preferences"] = (sum(checks.values()) / len(checks)) if checks else None

    weights = {
        "required": s.weight_required,
        "experience": s.weight_experience,
        "preferred": s.weight_preferred,
        "domain": s.weight_domain,
        "education": s.weight_education,
        "preferences": s.weight_preferences,
    }
    # Components with nothing to measure are dropped and the remaining weights renormalized.
    active = {k: w for k, w in weights.items() if components.get(k) is not None}
    total_w = sum(active.values())
    score = 0.0 if not total_w else 100 * sum(components[k] * w for k, w in active.items()) / total_w
    weights_used = {k: round(w / total_w, 4) for k, w in active.items()} if total_w else {}

    return MatchResult(round(score, 1), None, components, weights_used, checks, results)
