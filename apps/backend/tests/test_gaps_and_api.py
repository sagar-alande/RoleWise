from fastapi.testclient import TestClient

from rolewise.api.main import app
from rolewise.services.gaps import analyze_gaps
from rolewise.services.matching import PreferencesIn, score_match
from rolewise.worker.connectors import content_hash, strip_html
from tests.helpers import fact, job, req


def test_gap_analysis_flags_underrepresented_experience():
    j = job([req("python"), req("docker"), req("kubernetes")])
    facts = [fact("python"), fact("docker", source="user_entry")]
    gaps = analyze_gaps(score_match(j, facts, PreferencesIn()), facts)
    assert [g["text"] for g in gaps.matched] == ["python", "docker"]
    assert [g["text"] for g in gaps.missing] == ["kubernetes"]
    assert [g["text"] for g in gaps.underrepresented] == ["docker"]
    assert {r["type"] for r in gaps.recommendations} == {"interview_risk"}


def test_underrepresented_ignores_semantically_equivalent_resume_fact():
    # Resume already has "aws", the candidate separately added a near-duplicate "aws cloud" that
    # happens to win the match - the concept is still represented on the resume, so this must NOT
    # be flagged as a resume-visibility gap even though the winning fact's source is user_entry.
    j = job([req("aws cloud")])
    facts = [fact("aws"), fact("aws cloud", source="user_entry")]
    gaps = analyze_gaps(score_match(j, facts, PreferencesIn()), facts)
    assert gaps.underrepresented == []


def test_underrepresented_still_flags_truly_absent_concepts():
    # No resume-derived fact shares any meaning with "docker" - this is a genuine visibility gap.
    j = job([req("docker")])
    facts = [fact("python"), fact("docker", source="user_entry")]
    gaps = analyze_gaps(score_match(j, facts, PreferencesIn()), facts)
    assert [g["text"] for g in gaps.underrepresented] == ["docker"]


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_protected_routes_need_auth():
    assert TestClient(app).get("/profile/facts").status_code == 401


def test_content_hash_ignores_whitespace_and_case():
    assert content_hash("Acme", "Engineer", "Build  APIs") == content_hash("acme", "engineer", "build apis")


def test_strip_html():
    assert strip_html("&lt;p&gt;Hello &amp; welcome&lt;/p&gt;") == "Hello & welcome"


def test_no_resume_means_nothing_is_underrepresented():
    j = job([req("python")])
    facts = [fact("python", source="user_entry")]
    gaps = analyze_gaps(score_match(j, facts, PreferencesIn()), facts, has_resume=False)
    assert gaps.underrepresented == []
    assert gaps.recommendations == []


def test_stub_marks_nice_to_have_as_preferred():
    from rolewise.services.ai import StubAI

    data, _ = StubAI().complete_json("job_requirements.v1", job_title="x",
                                     job_description="Required: Python and AWS. Nice to have Spark.")
    kinds = {r["text"]: r["kind"] for r in data["requirements"]}
    assert kinds == {"python": "required_skill", "aws": "required_skill", "spark": "preferred_skill"}


def test_stub_years_requirement_captures_skill_subject():
    from rolewise.services.ai import StubAI

    data, _ = StubAI().complete_json("job_requirements.v1", job_title="x",
                                     job_description="You must have 5+ years of Python experience.")
    exp = next(r for r in data["requirements"] if r["kind"] == "experience")
    assert exp["min_years"] == 5.0
    assert exp["normalized"] == "python"


def test_stub_years_requirement_generic_has_no_subject():
    from rolewise.services.ai import StubAI

    data, _ = StubAI().complete_json("job_requirements.v1", job_title="x",
                                     job_description="You need 5+ years of professional experience.")
    exp = next(r for r in data["requirements"] if r["kind"] == "experience")
    assert exp["normalized"] is None


def test_stub_years_requirement_captures_domain_phrase():
    from rolewise.services.ai import StubAI

    data, _ = StubAI().complete_json("job_requirements.v1", job_title="x",
                                     job_description="We need 5+ years in financial services.")
    exp = next(r for r in data["requirements"] if r["kind"] == "experience")
    assert exp["normalized"] == "financial services"


def test_generic_experience_ignores_a_skill_mentioned_later_in_the_sentence():
    # Regression: "3 years of professional experience" is what's being measured - "REST API services"
    # is just what the work involves, not what the years figure is about. Must not become "rest api".
    from rolewise.services.ai import StubAI

    data, _ = StubAI().complete_json(
        "job_requirements.v1", job_title="x",
        job_description="You need 3 years of professional experience building REST API services.",
    )
    exp = next(r for r in data["requirements"] if r["kind"] == "experience")
    assert exp["min_years"] == 3.0
    assert exp["normalized"] is None


def test_skill_specific_years_immediately_after_of_is_still_captured():
    from rolewise.services.ai import StubAI

    data, _ = StubAI().complete_json(
        "job_requirements.v1", job_title="x",
        job_description="You need 3 years of REST API development experience.",
    )
    exp = next(r for r in data["requirements"] if r["kind"] == "experience")
    assert exp["normalized"] == "rest api"


def test_generic_years_with_software_engineering_qualifier_has_no_subject():
    from rolewise.services.ai import StubAI

    data, _ = StubAI().complete_json(
        "job_requirements.v1", job_title="x",
        job_description="You need 5+ years of professional software engineering experience.",
    )
    exp = next(r for r in data["requirements"] if r["kind"] == "experience")
    assert exp["normalized"] is None


def test_skill_specific_years_with_working_with_is_captured():
    from rolewise.services.ai import StubAI

    data, _ = StubAI().complete_json(
        "job_requirements.v1", job_title="x",
        job_description="You need 4+ years working with AWS.",
    )
    exp = next(r for r in data["requirements"] if r["kind"] == "experience")
    assert exp["normalized"] == "aws"
