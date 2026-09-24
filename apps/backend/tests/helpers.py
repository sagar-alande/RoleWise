from rolewise.services.ai import StubAI
from rolewise.services.matching import FactIn, JobIn, RequirementIn

ai = StubAI()


def fact(title: str, kind: str = "skill", verified: bool = True, source: str = "resume_parse",
         years: float | None = None) -> FactIn:
    return FactIn(id=f"f-{title}", kind=kind, title=title, verified=verified, source=source,
                  embedding=ai.embed([f"{kind}: {title}"])[0], years=years)


def req(text: str, kind: str = "required_skill", min_years: float | None = None) -> RequirementIn:
    return RequirementIn(id=f"r-{text}", kind=kind, text=text, embedding=ai.embed([text])[0],
                         normalized=text, min_years=min_years)


def job(requirements, description: str = "A backend role.", remote_mode: str | None = "remote",
        location: str | None = "Remote, US", salary_max: int | None = None, title: str = "Backend Engineer") -> JobIn:
    return JobIn(title=title, description=description, company="Acme", location=location,
                 remote_mode=remote_mode, salary_max=salary_max, requirements=requirements)
