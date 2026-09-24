"""LLM explanation of a match. Input is the deterministic breakdown, so the explanation cannot change the score."""

from __future__ import annotations

import json

from rolewise.services.ai import get_ai
from rolewise.services.matching import MatchResult

PROMPT = "match_explanation.v1"


def explain_match(job_title: str, company: str, result: MatchResult) -> tuple[dict, str, str]:
    """Returns (explanation, model id, prompt version)."""
    breakdown = result.to_dict()
    # Only ids, titles and statuses go to the model. No resume text.
    data, model_id = get_ai().complete_json(
        PROMPT,
        job_title=job_title,
        company=company,
        breakdown_json=json.dumps(breakdown),
    )
    explanation = {
        "summary": str(data.get("summary", "")),
        "strengths": [str(x) for x in data.get("strengths", [])][:8],
        "gaps": [str(x) for x in data.get("gaps", [])][:8],
        "resume_tips": [str(x) for x in data.get("resume_tips", [])][:8],
    }
    return explanation, model_id, PROMPT
