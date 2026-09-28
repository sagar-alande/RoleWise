"""Matching rules modeled on career-ops (github.com/santifer/career-ops): filters, importance bands,
evidence tiers, work authorization, geo mismatch, archetypes, level and verdict bands."""

from rolewise.services.gaps import analyze_gaps
from rolewise.services.matching import (
    Archetype,
    PreferencesIn,
    normalize_importance,
    score_match,
    verdict_for,
)
from rolewise.services.signals import classify_tier
from tests.helpers import fact, job, req

# ---------------------------------------------------------------- filters


def test_dealbreakers_match_whole_words_only():
    # A bare "java" must not reject a posting that only mentions JavaScript (career-ops #3274).
    j = job([req("python")], description="Our frontend uses JavaScript.")
    assert score_match(j, [fact("python")], PreferencesIn(dealbreakers=["java"])).filtered_out is None
    j2 = job([req("python")], description="Our backend is Java.")
    assert score_match(j2, [fact("python")], PreferencesIn(dealbreakers=["java"])).filtered_out == "dealbreaker: java"


def test_excluded_title_keywords_filter():
    j = job([req("python")], title="Sales Engineer")
    result = score_match(j, [fact("python")], PreferencesIn(excluded_title_keywords=["sales"]))
    assert result.filtered_out == "title contains excluded keyword 'sales'"


def test_skip_tiers_filter():
    j = job([req("python")], title="Software Engineering Intern")
    assert score_match(j, [fact("python")], PreferencesIn(skip_tiers=["intern"])).filtered_out == \
        "seniority tier skipped: intern"


def test_skip_tiers_is_independent_of_the_candidates_own_seniority():
    # skip_tiers rejects JOB postings at that tier - it has nothing to do with the candidate's own
    # stated level (seniority), which only ever affects the level-fit score, never filtering. A
    # candidate who calls themselves senior must still have senior-tier postings filtered if skipped.
    j = job([req("python")], title="Senior Backend Engineer")
    result = score_match(j, [fact("python")], PreferencesIn(skip_tiers=["senior"], seniority="senior"))
    assert result.filtered_out == "seniority tier skipped: senior"


def test_missing_job_salary_is_never_rejected():
    # Phase 5 finding: 0% of auto-discovered jobs carry salary_max. salary_min must stay a no-op
    # whenever the job simply doesn't state a salary, never treated as "below the floor".
    j = job([req("python")], salary_max=None)
    result = score_match(j, [fact("python")], PreferencesIn(salary_min=120000))
    assert result.filtered_out is None
    assert "salary" not in result.preference_checks


def test_target_titles_require_an_adjacent_phrase_not_scattered_words():
    # "Data Engineer" must not match a title that only happens to contain both words separately.
    j = job([req("python")], title="Software Engineer II, Data Analytics & Engineering")
    result = score_match(j, [fact("python")], PreferencesIn(target_titles=["Data Engineer"]))
    assert result.filtered_out == "title does not match your target roles"

    for title in ["Senior Data Engineer II", "Data Engineering Lead", "Staff Data Engineer, Market Data"]:
        j2 = job([req("python")], title=title)
        assert score_match(j2, [fact("python")], PreferencesIn(target_titles=["Data Engineer"])).filtered_out is None


def test_semantic_fallback_admits_a_real_variant_but_not_a_same_scoring_lookalike():
    from tests.helpers import ai

    def prefs_for(target: str) -> PreferencesIn:
        return PreferencesIn(target_titles=[target], target_title_embeddings=ai.embed([target]))

    def scored(title: str, target: str):
        j = job([req("python")], title=title)
        j.title_embedding = ai.embed([title])[0]
        return score_match(j, [fact("python")], prefs_for(target))

    # "Data Platform Engineer" shares no adjacent phrase with "Data Engineer" but is a real variant -
    # the offline stub's embeddings can tell it apart from a same-scoring generic lookalike.
    assert scored("Data Platform Engineer", "Data Engineer").filtered_out is None

    # "Software Engineer" scores identically to "Analytics Engineer" against "Data Engineer" under the
    # offline stub (both share only the word "Engineer") - the threshold must stay above that noise
    # floor so a same-scoring irrelevant title isn't let in as a side effect.
    assert scored("Software Engineer", "Data Engineer").filtered_out == "title does not match your target roles"


def test_classify_tier():
    assert classify_tier("Software Engineer") == "mid"
    assert classify_tier("Senior Data Engineer II") == "senior"
    assert classify_tier("Junior Analyst") == "entry"
    assert classify_tier("Data Engineering Intern") == "intern"
    assert classify_tier("UI/UX Designer") == "mid"


# ---------------------------------------------------------------- importance bands


def test_inferred_requirements_can_never_be_critical_or_high():
    assert normalize_importance("required_skill", "critical", "inferred") == ("meaningful", "inferred")
    assert normalize_importance("required_skill", "high", None) == ("meaningful", "inferred")
    assert normalize_importance("required_skill", "critical", "stated") == ("critical", "stated")


def test_importance_weights_the_score():
    # Missing a critical requirement costs more than missing a meaningful one.
    critical_gap = job([req("python", importance="critical", evidence_tier="stated"),
                        req("docker", importance="meaningful")])
    minor_gap = job([req("python", importance="meaningful"),
                     req("docker", importance="critical", evidence_tier="stated")])
    facts = [fact("docker")]
    assert score_match(critical_gap, facts, PreferencesIn()).score < \
        score_match(minor_gap, facts, PreferencesIn()).score


def test_requirements_sorted_by_importance_then_unmet_first():
    j = job([
        req("docker", importance="meaningful"),
        req("python", importance="high"),
        req("aws", importance="high"),
        req("kubernetes", importance="critical", evidence_tier="stated"),
    ])
    result = score_match(j, [fact("python"), fact("kubernetes")], PreferencesIn())
    assert [r.text for r in result.requirements] == ["kubernetes", "aws", "python", "docker"]


def test_missing_critical_requirement_is_flagged_with_quote():
    j = job([req("aws", importance="critical", evidence_tier="stated", jd_signal="You must know AWS.")])
    result = score_match(j, [fact("python")], PreferencesIn())
    assert [(f.code, f.quote) for f in result.flags] == [("critical_gap", "You must know AWS.")]


def test_critical_and_high_gaps_get_risk_and_mitigation():
    j = job([req("aws", importance="high", evidence_tier="stated", jd_signal="AWS is required."),
             req("docker", importance="preferred")])
    facts = [fact("python")]
    gaps = analyze_gaps(score_match(j, facts, PreferencesIn()), facts, has_resume=True)
    risks = [r for r in gaps.recommendations if r["type"] == "interview_risk"]
    assert len(risks) == 1 and risks[0]["requirement"] == "aws"
    assert '"AWS is required."' in risks[0]["risk"] and risks[0]["mitigation"]


# ---------------------------------------------------------------- work authorization and geo


def test_no_sponsorship_outside_authorized_country_is_a_hard_stop():
    j = job([req("python")], location="London, UK", remote_mode="onsite",
            description="We are unable to sponsor visas for this role.")
    prefs = PreferencesIn(authorized_in=["United States"], needs_sponsorship=True)
    result = score_match(j, [fact("python")], prefs)
    assert result.verdict == "hard_stop"
    assert result.global_score <= 2.5
    assert result.hard_stops[0].quote == "We are unable to sponsor visas for this role."


def test_no_sponsorship_inside_authorized_country_is_neutral():
    j = job([req("python")], location="Austin, TX", remote_mode="onsite",
            description="We are unable to sponsor visas for this role.")
    prefs = PreferencesIn(authorized_in=["United States"], needs_sponsorship=True)
    result = score_match(j, [fact("python")], prefs)
    assert result.hard_stops == [] and result.work_auth["tier"] == "not_needed"


def test_silence_about_sponsorship_is_neutral():
    j = job([req("python")], location="Berlin, Germany", remote_mode="onsite", description="Great team.")
    prefs = PreferencesIn(authorized_in=["United States"], needs_sponsorship=True)
    result = score_match(j, [fact("python")], prefs)
    assert result.work_auth["tier"] == "unstated" and result.hard_stops == []


def test_needs_sponsorship_false_short_circuits_regardless_of_country():
    # "Not required" (needs_sponsorship=False) must resolve to not_needed immediately, ignoring
    # authorized_in and the posting's own no-sponsorship language entirely - even on a job whose
    # country isn't in authorized_in and which explicitly says it won't sponsor.
    j = job([req("python")], location="London, UK", remote_mode="onsite",
            description="We are unable to sponsor visas for this role.")
    prefs = PreferencesIn(authorized_in=["United States"], needs_sponsorship=False)
    result = score_match(j, [fact("python")], prefs)
    assert result.work_auth["tier"] == "not_needed"
    assert result.hard_stops == []


def test_empty_authorized_in_never_creates_a_false_hard_stop():
    # An MVP user who selects "Required" but leaves the countries field blank must never see a hard
    # stop manufactured from that silence - a hard stop requires a KNOWN country outside a non-empty
    # authorized_in list, never from an empty list alone.
    j = job([req("python")], location="London, UK", remote_mode="onsite",
            description="We are unable to sponsor visas for this role.")
    prefs = PreferencesIn(authorized_in=[], needs_sponsorship=True)
    result = score_match(j, [fact("python")], prefs)
    assert result.hard_stops == []
    assert result.work_auth["tier"] == "unstated"


def test_remote_listing_that_requires_office_days_is_flagged_verbatim():
    j = job([req("python")], remote_mode="remote",
            description="We are remote friendly. You will be in the office 3 days a week in NYC.")
    result = score_match(j, [fact("python")], PreferencesIn())
    geo = [f for f in result.flags if f.code == "geo_mismatch"]
    assert geo[0].quote == "You will be in the office 3 days a week in NYC."


def test_optional_offsites_are_not_a_geo_mismatch():
    j = job([req("python")], remote_mode="remote", description="Fully remote. Optional quarterly onsite.")
    assert not [f for f in score_match(j, [fact("python")], PreferencesIn()).flags if f.code == "geo_mismatch"]


# ---------------------------------------------------------------- archetypes, level, verdicts


def test_archetype_absence_renormalizes_without_error():
    # Phase 5 hides archetypes from the primary MVP form - a user who never sets any must still get a
    # correctly computed, fully-weighted score. Empty archetypes -> no "north_star" component -> its
    # weight is dropped and the rest renormalize to still sum to 1.0, the same mechanism already used
    # whenever any other component has nothing to measure.
    result = score_match(job([req("python")]), [fact("python")], PreferencesIn(archetypes=[]))
    assert result.archetype is None
    assert "north_star" not in result.weights_used
    assert round(sum(result.weights_used.values()), 4) == 1.0
    assert result.score == 100.0


def test_archetype_fit_weights_primary_above_adjacent():
    prefs = PreferencesIn(archetypes=[Archetype("Data Engineer", "primary"), Archetype("Data Analyst", "adjacent")])
    eng = score_match(job([req("python")], title="Data Engineer"), [fact("python")], prefs)
    ana = score_match(job([req("python")], title="Data Analyst"), [fact("python")], prefs)
    assert eng.archetype == {"name": "Data Engineer", "fit": "primary", "strength": 1.0}
    assert ana.archetype["fit"] == "adjacent"
    assert eng.score > ana.score


def test_level_stretch_is_flagged_and_scored():
    facts = [fact("python"), fact("Engineer at A", "role", years=2)]
    senior = score_match(job([req("python")], title="Senior Backend Engineer"), facts, PreferencesIn())
    mid = score_match(job([req("python")], title="Backend Engineer"), facts, PreferencesIn())
    assert senior.level == {"job_tier": "senior", "candidate_tier": "mid", "gap": 1, "fit": 0.5}
    assert [f.code for f in senior.flags] == ["level_stretch"]
    assert mid.score > senior.score


def test_verdict_bands():
    assert verdict_for(4.6, []) == "apply_now"
    assert verdict_for(4.2, []) == "worth_applying"
    assert verdict_for(3.7, []) == "only_with_reason"
    assert verdict_for(3.0, []) == "not_recommended"


def test_global_score_maps_0_100_onto_1_5():
    result = score_match(job([req("python")]), [fact("python")], PreferencesIn())
    assert (result.score, result.global_score, result.verdict) == (100.0, 5.0, "apply_now")
