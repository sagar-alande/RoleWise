"""Deterministic, explainable match scoring.

Invariant: this module is the only place a match score is computed. The LLM explains the breakdown
produced here and never changes the number. Pure functions only, so it is easy to test and audit.

The structure follows career-ops (github.com/santifer/career-ops), with one deliberate difference:
career-ops lets the model make a holistic 1-5 judgment, RoleWise computes it from labels with fixed rules.

Pipeline for one job:
  1. Hard filters (no score): dealbreakers, salary floor, target titles, excluded title words, skipped tiers.
  2. Requirement matching against verified facts, weighted by importance band (critical .. low_signal).
  3. Components: required, preferred, domain, education, experience, preferences, north_star, level.
  4. Signals: work authorization and geo mismatch. "no_sponsorship" is a hard stop that caps the verdict.
  5. Global 1-5 score and a verdict band (apply_now, worth_applying, only_with_reason, not_recommended).
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field

from rolewise.config import Settings, get_settings
from rolewise.services import signals

COMPONENT_BY_KIND = {
    "required_skill": "required",
    "preferred_skill": "preferred",
    "domain": "domain",
    "education": "education",
    "experience": "experience",
}

# Importance bands (career-ops oferta.md Block B). Weights are used only inside a component.
IMPORTANCE_ORDER = ["critical", "high", "meaningful", "preferred", "low_signal"]
IMPORTANCE_WEIGHT = {"critical": 3.0, "high": 2.0, "meaningful": 1.0, "preferred": 0.5, "low_signal": 0.25}
EVIDENCE_TIERS = {"stated", "structural", "inferred"}
DEFAULT_IMPORTANCE = {"required_skill": "high", "experience": "high", "preferred_skill": "preferred",
                      "domain": "meaningful", "education": "meaningful"}

# Archetype fit (career-ops profile.yml target_roles.archetypes).
FIT_WEIGHT = {"primary": 1.0, "secondary": 0.75, "adjacent": 0.5}

# Verdict bands on the 1-5 global score (career-ops _shared.md "Score interpretation").
VERDICTS = [(4.5, "apply_now"), (4.0, "worth_applying"), (3.5, "only_with_reason"), (0.0, "not_recommended")]
HARD_STOP_CAP = 2.5
# The percentage equivalent of HARD_STOP_CAP on the 1-5 scale (global_score = 1 + 4*score/100). Capping
# `score` itself - not just `global_score` - keeps the two numbers in the same linear relationship even
# on a hard-stop job, so the UI's single displayed percentage can never read higher than the verdict implies.
HARD_STOP_SCORE_CAP = (HARD_STOP_CAP - 1) * 25

# Sources trustworthy enough for a skill's own `years` value to satisfy a skill-specific duration
# requirement on its own. Deliberately excludes "resume_parse": editing a resume_parse fact never
# relabels it (see profile.py update_fact), so an explicitly-user-typed years value on a resume-derived
# fact is indistinguishable here from one a future parser change might scrape unsupervised - conservative
# by design, per the never-invent-qualifications rule.
TRUSTWORTHY_SKILL_YEARS_SOURCES = {"user_entry", "user_edit"}


def normalize_importance(kind: str, importance: str | None, evidence_tier: str | None) -> tuple[str, str]:
    """Apply the career-ops gate: an inferred requirement can never be critical or high."""
    imp = importance if importance in IMPORTANCE_WEIGHT else DEFAULT_IMPORTANCE.get(kind, "meaningful")
    tier = evidence_tier if evidence_tier in EVIDENCE_TIERS else "inferred"
    if tier == "inferred" and imp in ("critical", "high"):
        imp = "meaningful"
    return imp, tier


@dataclass
class FactIn:
    id: str
    kind: str
    title: str
    verified: bool
    source: str
    embedding: list[float]
    years: float | None = None  # for role facts
    highlights: list[str] = field(default_factory=list)  # for role facts; never embedded, text-searched only


@dataclass
class RequirementIn:
    id: str
    kind: str
    text: str
    embedding: list[float]
    normalized: str | None = None
    min_years: float | None = None
    importance: str | None = None
    evidence_tier: str | None = None
    jd_signal: str | None = None  # verbatim quote from the posting


@dataclass
class JobIn:
    title: str
    description: str
    company: str
    location: str | None
    remote_mode: str | None
    salary_max: int | None
    requirements: list[RequirementIn]
    title_embedding: list[float] | None = None


@dataclass
class Archetype:
    name: str
    fit: str = "primary"  # primary | secondary | adjacent


@dataclass
class PreferencesIn:
    locations: list[str] = field(default_factory=list)
    remote_modes: list[str] = field(default_factory=list)
    salary_min: int | None = None
    dealbreakers: list[str] = field(default_factory=list)
    target_titles: list[str] = field(default_factory=list)
    excluded_title_keywords: list[str] = field(default_factory=list)
    skip_tiers: list[str] = field(default_factory=list)
    seniority: str | None = None
    authorized_in: list[str] = field(default_factory=list)
    needs_sponsorship: bool | None = None
    archetypes: list[Archetype] = field(default_factory=list)
    # Parallel to target_titles: same-index embedding for each. Lets "only show these roles" catch
    # role-family variants with no shared words (e.g. "Analytics Engineer" for target "Data Engineer").
    target_title_embeddings: list[list[float]] = field(default_factory=list)


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
    importance: str = "meaningful"
    evidence_tier: str = "inferred"
    jd_signal: str | None = None
    years_evidence: str | None = None  # known|unknown|none - set only for min_years experience requirements
    known_years: float | None = None  # the actual computed figure behind years_evidence=="known" - never invented


@dataclass
class Signal:
    code: str  # no_sponsorship | geo_mismatch | level_stretch | level_down | unstated_sponsorship ...
    message: str
    quote: str | None = None


@dataclass
class MatchResult:
    score: float  # 0..100
    filtered_out: str | None  # reason when a hard filter excluded the job
    components: dict[str, float | None]  # 0..1 per component, None when not applicable
    weights_used: dict[str, float]
    preference_checks: dict[str, bool]
    requirements: list[RequirementResult]
    global_score: float = 0.0  # 1.0..5.0
    verdict: str = "not_recommended"
    hard_stops: list[Signal] = field(default_factory=list)
    flags: list[Signal] = field(default_factory=list)
    archetype: dict | None = None  # {"name", "fit", "strength"}
    level: dict | None = None  # {"job_tier", "candidate_tier", "fit"}
    work_auth: dict | None = None  # {"tier", "quote", "country"}

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


def _mentions(role: FactIn, subject: str) -> bool:
    """Whether a role's own bullet points name the requirement's subject - an incidental mention, not
    proof the skill/domain spans the role's whole duration (role titles are never embedded with
    highlights, so this is a separate text search, not a cosine check)."""
    haystack = " ".join(role.highlights).lower()
    return re.search(r"(?<![a-z0-9])" + re.escape(subject.strip().lower()) + r"(?![a-z0-9])", haystack) is not None


def _title_semantically_matches(job: JobIn, prefs: PreferencesIn) -> bool:
    """Fallback for target roles that share no words with the job title (e.g. "Analytics Engineer"
    for target "Data Engineer"). Only used when the literal phrase check has already failed."""
    s = get_settings()
    if not job.title_embedding or not prefs.target_title_embeddings:
        return False
    return any(cosine(job.title_embedding, te) >= s.title_semantic_threshold
              for te in prefs.target_title_embeddings)


def hard_filter(job: JobIn, prefs: PreferencesIn) -> str | None:
    """Reasons a job is not shown at all. Missing data never filters a job out."""
    haystack = f"{job.company}\n{job.title}\n{job.description}"
    for d in prefs.dealbreakers:
        if d.strip() and signals.compile_keyword(d).search(haystack):
            return f"dealbreaker: {d.strip()}"
    if prefs.salary_min and job.salary_max and job.salary_max < prefs.salary_min:
        return "salary below minimum"
    reason = signals.title_filter(job.title, prefs.target_titles, prefs.excluded_title_keywords)
    if reason == "title does not match your target roles" and _title_semantically_matches(job, prefs):
        reason = None
    if reason:
        return reason
    tier = signals.classify_tier(job.title)
    if tier in prefs.skip_tiers:
        return f"seniority tier skipped: {tier}"
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
    return checks


def archetype_fit(job_title: str, archetypes: list[Archetype]) -> dict | None:
    """Best matching target archetype. strength = title overlap x fit weight (North Star, career-ops)."""
    if not archetypes:
        return None
    best, best_key = {"name": None, "fit": None, "strength": 0.0}, (0.0, 0.0)
    for a in archetypes:
        overlap = signals.title_overlap(job_title, a.name)
        weight = FIT_WEIGHT.get(a.fit, 0.5)
        # The closest title wins first. Fit only breaks ties, so a primary archetype that shares one
        # word ("Data Engineer") never beats an exact adjacent one ("Data Analyst").
        if overlap >= 0.5 and (overlap, weight) > best_key:
            best_key = (overlap, weight)
            best = {"name": a.name, "fit": a.fit, "strength": round(overlap * weight, 3)}
    return best


def level_fit(job_title: str, prefs: PreferencesIn, total_years: float, has_roles: bool) -> dict | None:
    """Compare the job's seniority tier with the candidate's. None when the candidate's level is unknown."""
    if not prefs.seniority and not has_roles:
        return None
    job_tier = signals.classify_tier(job_title)
    cand = signals.candidate_tier(prefs.seniority, total_years)
    if job_tier == "intern" or cand == "intern":
        gap = 0 if job_tier == cand else 2
    else:
        gap = signals.TIERS.index(job_tier) - signals.TIERS.index(cand)
    fit = {0: 1.0, 1: 0.5, -1: 0.5}.get(gap, 0.0)
    return {"job_tier": job_tier, "candidate_tier": cand, "gap": gap, "fit": fit}


def verdict_for(global_score: float, hard_stops: list[Signal]) -> str:
    if hard_stops:
        return "hard_stop"
    return next(v for threshold, v in VERDICTS if global_score >= threshold)


def _sort_key(r: RequirementResult) -> tuple[int, int]:
    # Importance descending, then unmet before met within a band (career-ops Block B sort rule).
    return IMPORTANCE_ORDER.index(r.importance), 0 if r.status != "matched" else 1


def score_match(
    job: JobIn, facts: list[FactIn], prefs: PreferencesIn, settings: Settings | None = None
) -> MatchResult:
    s = settings or get_settings()
    verified = [f for f in facts if f.verified]  # invariant: unverified facts never count

    reason = hard_filter(job, prefs)
    if reason:
        return MatchResult(0.0, reason, {}, {}, {}, [], global_score=0.0, verdict="filtered")

    roles = [f for f in verified if f.kind == "role"]
    total_years = sum(f.years or 0.0 for f in roles)

    results: list[RequirementResult] = []
    for req in job.requirements:
        imp, tier = normalize_importance(req.kind, req.importance, req.evidence_tier)
        if req.kind == "experience" and req.min_years:
            if not req.normalized:
                # Generic figure ("5+ years of professional experience") - every verified role counts,
                # full duration, same as the original total-years behavior.
                known = sum(r.years for r in roles if r.years is not None)
                has_unknown = any(r.years is None for r in roles)
                no_evidence = not roles
            else:
                # An explicit, user-verified skill-level years claim is the strongest defensible
                # evidence - never inferred, always something the candidate directly asserted. But
                # `source` alone can't prove *the years value itself* was ever explicitly asserted:
                # editing a resume_parse fact never relabels it away from resume_parse (profile.py),
                # so a resume-derived fact's years could be silently scraped or hand-typed by the user
                # and look identical here. Conservatively require a source that's never ambiguous about
                # that - resume_parse years are never treated as authoritative, even if present.
                skill_fact, skill_sim = _best_fact(req, [f for f in verified if f.kind == "skill"])
                skill_years = (skill_fact.years if skill_fact and skill_sim >= s.match_threshold
                               and skill_fact.years is not None
                               and skill_fact.source in TRUSTWORTHY_SKILL_YEARS_SOURCES else None)
                title_matches = [r for r in roles if cosine(req.embedding, r.embedding) >= s.partial_threshold]
                highlight_only = [r for r in roles if r not in title_matches and _mentions(r, req.normalized)]

                if skill_years is not None:
                    known, has_unknown, no_evidence = skill_years, False, False
                elif title_matches:
                    # The role itself basically IS this skill/domain - its full duration is defensible.
                    known = sum(r.years for r in title_matches if r.years is not None)
                    has_unknown = any(r.years is None for r in title_matches)
                    no_evidence = False
                elif highlight_only:
                    # Only an incidental bullet-point mention - never claim the surrounding role's
                    # full duration as this specific skill/domain's duration.
                    known, has_unknown, no_evidence = 0.0, True, False
                else:
                    known, has_unknown, no_evidence = 0.0, False, True

            if no_evidence:
                credit, status, years_evidence = 0.0, "missing", "none"
            elif known >= req.min_years:
                credit, status, years_evidence = 1.0, "matched", "known"
            elif has_unknown:
                credit = max(0.5, known / req.min_years)
                status, years_evidence = "partial", "unknown"
            else:
                credit = known / req.min_years
                status = "matched" if credit >= 1.0 else "partial" if credit >= 0.5 else "missing"
                years_evidence = "known"

            results.append(RequirementResult(req.id, req.kind, req.text, status, round(credit, 3), credit,
                                             None, None, None, imp, tier, req.jd_signal,
                                             years_evidence=years_evidence,
                                             known_years=known if years_evidence == "known" else None))
            continue
        fact, sim = _best_fact(req, verified)
        status, credit = _classify(sim, s)
        hit = fact if fact and status != "missing" else None
        results.append(RequirementResult(
            req.id, req.kind, req.text, status, credit, round(sim, 4),
            hit.id if hit else None, hit.title if hit else None, hit.source if hit else None,
            imp, tier, req.jd_signal,
        ))

    components: dict[str, float | None] = {k: None for k in COMPONENT_BY_KIND.values()}
    for comp in list(components):
        rows = [r for r in results if COMPONENT_BY_KIND.get(r.kind) == comp]
        if rows:
            weights = [IMPORTANCE_WEIGHT[r.importance] for r in rows]
            components[comp] = sum(r.credit * w for r, w in zip(rows, weights)) / sum(weights)

    checks = preference_checks(job, prefs)
    components["preferences"] = (sum(checks.values()) / len(checks)) if checks else None

    arch = archetype_fit(job.title, prefs.archetypes)
    components["north_star"] = arch["strength"] if arch else None
    level = level_fit(job.title, prefs, total_years, bool(roles))
    components["level"] = level["fit"] if level else None

    weights = {
        "required": s.weight_required,
        "experience": s.weight_experience,
        "preferred": s.weight_preferred,
        "domain": s.weight_domain,
        "education": s.weight_education,
        "preferences": s.weight_preferences,
        "north_star": s.weight_north_star,
        "level": s.weight_level,
    }
    # Components with nothing to measure are dropped and the remaining weights renormalized.
    active = {k: w for k, w in weights.items() if components.get(k) is not None}
    total_w = sum(active.values())
    score = 0.0 if not total_w else 100 * sum(components[k] * w for k, w in active.items()) / total_w
    weights_used = {k: round(w / total_w, 4) for k, w in active.items()} if total_w else {}

    # ---- signals: hard stops and flags (career-ops Block A checks)
    hard_stops: list[Signal] = []
    flags: list[Signal] = []
    wa = signals.work_authorization(job.location, job.remote_mode, job.description,
                                    prefs.authorized_in, prefs.needs_sponsorship)
    if wa.tier == "no_sponsorship":
        hard_stops.append(Signal("no_sponsorship", f"The posting states it will not sponsor, and {wa.country} "
                                 "is not in your authorized countries.", wa.quote))
    geo = signals.geo_mismatch(job.remote_mode, job.description)
    if geo:
        flags.append(Signal("geo_mismatch", "Listed as remote, but the description requires office attendance.",
                            geo))
    if level and level["gap"] >= 1:
        flags.append(Signal("level_stretch", f"The role is {level['job_tier']} level and your level is "
                            f"{level['candidate_tier']}. Treat it as a stretch."))
    elif level and level["gap"] <= -1:
        flags.append(Signal("level_down", f"The role is {level['job_tier']} level, below your "
                            f"{level['candidate_tier']} level."))
    for r in results:
        if r.status == "missing" and r.importance == "critical":
            flags.append(Signal("critical_gap", f"Missing a critical requirement: {r.text}.", r.jd_signal))

    results.sort(key=_sort_key)
    score = round(score, 1)
    if hard_stops:
        score = min(score, HARD_STOP_SCORE_CAP)
    global_score = round(1 + 4 * score / 100, 1)

    return MatchResult(
        score, None, components, weights_used, checks, results,
        global_score=global_score,
        verdict=verdict_for(global_score, hard_stops),
        hard_stops=hard_stops,
        flags=flags,
        archetype=arch,
        level=level,
        work_auth={"tier": wa.tier, "quote": wa.quote, "country": wa.country},
    )
