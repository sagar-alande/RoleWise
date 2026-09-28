"""Resume gap analysis, derived from a MatchResult. No LLM needed for the classification itself."""

from __future__ import annotations

from dataclasses import dataclass, field

from rolewise.config import get_settings
from rolewise.services.matching import FactIn, MatchResult, cosine

# Facts that came from the uploaded resume. Anything else (user_entry, user_edit) is verified
# experience that the current resume may not show.
RESUME_SOURCES = {"resume_parse"}


@dataclass
class GapResult:
    matched: list[dict] = field(default_factory=list)
    partial: list[dict] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)
    underrepresented: list[dict] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)


def _resume_backed(fact_id: str | None, facts_by_id: dict[str, FactIn], resume_embeddings: list[list[float]],
                    threshold: float) -> bool:
    """True when the fact that won a requirement match is itself resume-derived, OR when a
    resume-derived fact is close enough in meaning to it (e.g. resume has "Amazon Web Services",
    the candidate separately added "AWS cloud services" and that one happened to win the match -
    the concept is still represented on the resume, just under a different fact record)."""
    fact = facts_by_id.get(fact_id) if fact_id else None
    if not fact:
        return False
    if fact.source in RESUME_SOURCES:
        return True
    return any(cosine(fact.embedding, emb) >= threshold for emb in resume_embeddings)


def analyze_gaps(result: MatchResult, facts: list[FactIn], has_resume: bool = True) -> GapResult:
    """has_resume: whether the user uploaded a resume. Without one, nothing can be "missing from the resume"."""
    gaps = GapResult()
    verified = [f for f in facts if f.verified]  # same invariant as matching.py: unverified facts never count
    facts_by_id = {f.id: f for f in verified}
    resume_embeddings = [f.embedding for f in verified if f.source in RESUME_SOURCES]
    settings = get_settings()

    for r in result.requirements:
        item = {"requirement_id": r.requirement_id, "kind": r.kind, "text": r.text, "fact_id": r.fact_id,
                "fact_title": r.fact_title, "importance": r.importance}
        if r.status == "matched":
            gaps.matched.append(item)
        elif r.status == "partial":
            gaps.partial.append(item)
        else:
            gaps.missing.append(item)

        if (has_resume and r.fact_id
                and not _resume_backed(r.fact_id, facts_by_id, resume_embeddings, settings.partial_threshold)):
            gaps.underrepresented.append(item)

    # career-ops rule: every missing or partial requirement at critical or high importance gets an
    # interview-risk note and a mitigation. Mitigations never suggest claiming unverified experience.
    for r in result.requirements:
        if r.status == "matched" or r.importance not in ("critical", "high"):
            continue
        quote = f' The posting says: "{r.jd_signal}".' if r.jd_signal and r.evidence_tier == "stated" else ""
        risk = f"Interviewers will likely probe '{r.text}' ({r.importance}).{quote}"
        if r.status == "partial" and r.fact_title:
            mitigation = (f"Lead with your adjacent, verified experience in '{r.fact_title}' and be clear "
                          "about where it differs.")
        elif r.kind == "experience":
            mitigation = ("Point to the scope and results of your verified roles rather than the year count, "
                          "and don't overstate your years.")
        else:
            mitigation = (f"If you have '{r.text}' experience, add it to your profile so it can be verified. "
                          "If not, say so honestly and describe how you would ramp up.")
        gaps.recommendations.append({
            "type": "interview_risk", "requirement": r.text, "importance": r.importance,
            "risk": risk, "mitigation": mitigation, "text": f"{risk} {mitigation}",
            "supporting_fact_ids": [r.fact_id] if r.fact_id else [],
        })
    for m in gaps.missing:
        if m["kind"] in ("required_skill", "preferred_skill") and m.get("importance") not in ("critical", "high"):
            gaps.recommendations.append({
                "type": "true_gap",
                "text": f"'{m['text']}' is not in your verified profile. If you have this experience, add it "
                "to your profile. Otherwise consider it a learning goal.",
                "supporting_fact_ids": [],
            })
    return gaps
