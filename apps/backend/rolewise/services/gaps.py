"""Resume gap analysis, derived from a MatchResult. No LLM needed for the classification itself."""

from __future__ import annotations

from dataclasses import dataclass, field

from rolewise.services.matching import MatchResult

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


def analyze_gaps(result: MatchResult, has_resume: bool = True) -> GapResult:
    """has_resume: whether the user uploaded a resume. Without one, nothing can be "missing from the resume"."""
    gaps = GapResult()
    for r in result.requirements:
        item = {"requirement_id": r.requirement_id, "kind": r.kind, "text": r.text, "fact_id": r.fact_id}
        if r.status == "matched":
            gaps.matched.append(item)
        elif r.status == "partial":
            gaps.partial.append(item)
        else:
            gaps.missing.append(item)

        if has_resume and r.fact_id and r.fact_source and r.fact_source not in RESUME_SOURCES:
            gaps.underrepresented.append(item)
            gaps.recommendations.append(
                {
                    "type": "surface_existing",
                    "text": f"Add your verified '{r.fact_title}' experience to the resume for this role.",
                    "supporting_fact_ids": [r.fact_id],
                }
            )

    for m in gaps.missing:
        if m["kind"] == "required_skill":
            gaps.recommendations.append(
                {
                    "type": "true_gap",
                    "text": f"'{m['text']}' is required and not in your verified profile. If you have this "
                    "experience, add it to your profile. Otherwise consider it a learning goal.",
                    "supporting_fact_ids": [],
                }
            )
    return gaps
