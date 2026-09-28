"""Tests for the product invariants in CLAUDE.md. Never delete or weaken these to make a change pass."""

import copy

import pytest

from rolewise.services.explain import explain_match
from rolewise.services.gaps import analyze_gaps
from rolewise.services.matching import PreferencesIn, score_match
from rolewise.worker.connectors import CURATED_BOARDS, FETCHERS
from rolewise.worker.tasks import _source
from tests.helpers import fact, job, req


def test_unverified_facts_never_count():
    j = job([req("python")])
    result = score_match(j, [fact("python", verified=False)], PreferencesIn())
    assert result.requirements[0].status == "missing"
    assert result.requirements[0].fact_id is None


def test_explanation_does_not_change_score():
    j = job([req("python"), req("aws")])
    result = score_match(j, [fact("python")], PreferencesIn())
    before = copy.deepcopy(result.to_dict())
    explanation, _, prompt_version = explain_match("Backend Engineer", "Acme", result)
    assert result.to_dict() == before
    assert prompt_version == "match_explanation.v2"
    assert set(explanation) == {"summary", "strengths", "gaps", "resume_tips"}


def test_recommendations_cite_only_verified_facts():
    j = job([req("python"), req("docker")])
    facts = [fact("python"), fact("docker", source="user_entry"), fact("kubernetes", verified=False)]
    gaps = analyze_gaps(score_match(j, facts, PreferencesIn()), facts)
    verified_ids = {f.id for f in facts if f.verified}
    for rec in gaps.recommendations:
        assert set(rec["supporting_fact_ids"]) <= verified_ids


def test_unreviewed_source_kinds_are_rejected():
    class FakeDB:
        def scalar(self, _):
            return None

    with pytest.raises(PermissionError):
        _source(FakeDB(), "some-aggregator", "aggregator")


def test_curated_boards_are_all_ats_platforms_with_a_fetcher():
    """The automatic 'find my matches' discovery only ever touches ToS-compliant ATS board
    APIs. Adding a scraper for a site that forbids automated access must not slip in here."""
    allowed_platforms = {"greenhouse", "lever", "ashby"}
    assert allowed_platforms == set(FETCHERS)
    for platform, token, _company in CURATED_BOARDS:
        assert platform in allowed_platforms
        assert token


def test_generated_resume_never_names_a_skill_the_candidate_has_not_verified():
    import json

    from rolewise.services import documents as docs
    from rolewise.services.ai import StubAI

    facts = [docs.Fact("r1", "role", "Data Engineer", {"years": 3, "highlights": ["Built ETL jobs in Python"]}),
             docs.Fact("s1", "skill", "python", {})]
    reqs = [{"text": "python", "status": "matched", "importance": "high"},
            {"text": "spark", "status": "missing", "importance": "critical"}]
    raw, _ = StubAI().complete_json("resume_tailor.v1", job_title="Data Engineer", company="Acme",
                                    job_description="Must have Python and Spark.",
                                    requirements_json=json.dumps(reqs), facts_json=docs.fact_catalog(facts))
    # Simulate a model that tries to sneak in an unverified skill.
    raw["skills"].append({"text": "spark", "fact_ids": ["s1"]})
    raw["summary"].append({"text": "Spark expert.", "fact_ids": []})
    content, check = docs.assemble_resume(raw, facts, {}, ["python", "spark"], "Must have Python and Spark.", "x")
    assert "spark" not in docs.resume_plain_text(content).lower()
    assert len(check.removed) == 2
