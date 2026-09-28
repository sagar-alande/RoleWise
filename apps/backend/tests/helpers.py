from rolewise.services.ai import StubAI
from rolewise.services.matching import FactIn, JobIn, RequirementIn

ai = StubAI()


def fact(title: str, kind: str = "skill", verified: bool = True, source: str = "resume_parse",
         years: float | None = None, highlights: list[str] | None = None) -> FactIn:
    return FactIn(id=f"f-{title}", kind=kind, title=title, verified=verified, source=source,
                  embedding=ai.embed([f"{kind}: {title}"])[0], years=years, highlights=highlights or [])


def req(text: str, kind: str = "required_skill", min_years: float | None = None,
        importance: str | None = None, evidence_tier: str | None = "structural",
        jd_signal: str | None = None, normalized: str | None = None) -> RequirementIn:
    # Matches production: normalized is genuinely null unless the extractor set one. _best_fact()
    # already falls back to `text` when normalized is None, so this changes nothing for skill/preferred
    # requirement tests - it only matters for experience requirements, where normalized now drives
    # generic-vs-specific duration handling and must reflect what a test actually asks for.
    return RequirementIn(id=f"r-{text}", kind=kind, text=text, embedding=ai.embed([normalized or text])[0],
                         normalized=normalized, min_years=min_years, importance=importance,
                         evidence_tier=evidence_tier, jd_signal=jd_signal)


def job(requirements, description: str = "A backend role.", remote_mode: str | None = "remote",
        location: str | None = "Remote, US", salary_max: int | None = None, title: str = "Backend Engineer") -> JobIn:
    return JobIn(title=title, description=description, company="Acme", location=location,
                 remote_mode=remote_mode, salary_max=salary_max, requirements=requirements)
