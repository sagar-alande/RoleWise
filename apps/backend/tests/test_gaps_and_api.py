from fastapi.testclient import TestClient

from rolewise.api.main import app
from rolewise.services.gaps import analyze_gaps
from rolewise.services.matching import PreferencesIn, score_match
from rolewise.worker.connectors import content_hash, strip_html
from tests.helpers import fact, job, req


def test_gap_analysis_flags_underrepresented_experience():
    j = job([req("python"), req("docker"), req("kubernetes")])
    facts = [fact("python"), fact("docker", source="user_entry")]
    gaps = analyze_gaps(score_match(j, facts, PreferencesIn()))
    assert [g["text"] for g in gaps.matched] == ["python", "docker"]
    assert [g["text"] for g in gaps.missing] == ["kubernetes"]
    assert [g["text"] for g in gaps.underrepresented] == ["docker"]
    assert {r["type"] for r in gaps.recommendations} == {"surface_existing", "true_gap"}


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
    gaps = analyze_gaps(score_match(j, [fact("python", source="user_entry")], PreferencesIn()), has_resume=False)
    assert gaps.underrepresented == []
    assert gaps.recommendations == []


def test_stub_marks_nice_to_have_as_preferred():
    from rolewise.services.ai import StubAI

    data, _ = StubAI().complete_json("job_requirements.v1", job_title="x",
                                     job_description="Required: Python and AWS. Nice to have Spark.")
    kinds = {r["text"]: r["kind"] for r in data["requirements"]}
    assert kinds == {"python": "required_skill", "aws": "required_skill", "spark": "preferred_skill"}
