from rolewise.services.matching import HARD_STOP_CAP, HARD_STOP_SCORE_CAP, PreferencesIn, score_match
from tests.helpers import fact, job, req


def test_full_match_scores_100():
    j = job([req("python"), req("postgresql")])
    result = score_match(j, [fact("python"), fact("postgresql")], PreferencesIn(remote_modes=["remote"]))
    assert result.score == 100.0
    assert all(r.status == "matched" for r in result.requirements)


def test_missing_required_skill_lowers_score_and_is_reported():
    j = job([req("python"), req("kubernetes")])
    result = score_match(j, [fact("python")], PreferencesIn())
    statuses = {r.text: r.status for r in result.requirements}
    assert statuses == {"python": "matched", "kubernetes": "missing"}
    assert result.score == 50.0  # only the required component applies, half matched


def test_score_is_deterministic():
    j = job([req("python"), req("aws"), req("docker", "preferred_skill")])
    facts = [fact("python"), fact("docker")]
    assert score_match(j, facts, PreferencesIn()).score == score_match(j, facts, PreferencesIn()).score


def test_unused_components_are_renormalized():
    j = job([req("python")])
    result = score_match(j, [fact("python")], PreferencesIn())
    assert result.weights_used == {"required": 1.0}


def test_experience_years_from_verified_roles():
    j = job([req("5 years", "experience", min_years=5)])
    facts = [fact("Engineer at A", "role", years=2), fact("Engineer at B", "role", years=1.5)]
    result = score_match(j, facts, PreferencesIn())
    assert result.requirements[0].status == "partial"
    assert result.components["experience"] == 0.7


def test_role_highlight_mention_never_becomes_full_role_duration():
    # A Data Engineer role mentioning Python in a bullet point is real evidence Python was used - but
    # not proof it spans the role's whole 6 years. Must stay partial, never claim 6 years of Python.
    j = job([req("python experience", "experience", min_years=5, normalized="python")])
    facts = [fact("Data Engineer", "role", years=6, highlights=["Built ETL pipelines using Python."])]
    result = score_match(j, facts, PreferencesIn())
    r = result.requirements[0]
    assert r.status == "partial"
    assert r.credit == 0.5
    assert r.years_evidence == "unknown"


def test_verified_skill_relevant_role_unknown_duration_is_partial():
    # Having Python also separately verified (with no years) must not flip this to "matched" via some
    # other path - the role's incidental mention still only earns partial credit.
    j = job([req("python experience", "experience", min_years=5, normalized="python")])
    facts = [
        fact("Data Engineer", "role", years=6, highlights=["Built ETL pipelines using Python."]),
        fact("Python", "skill"),
    ]
    result = score_match(j, facts, PreferencesIn())
    assert result.requirements[0].status == "partial"


def test_generic_requirement_uses_full_relevant_role_duration():
    j = job([req("5 years professional experience", "experience", min_years=5)])
    facts = [fact("Data Engineer", "role", years=6)]
    result = score_match(j, facts, PreferencesIn())
    r = result.requirements[0]
    assert r.status == "matched"
    assert r.years_evidence == "known"


def test_domain_title_match_can_reach_matched():
    j = job([req("financial services experience", "experience", min_years=5, normalized="financial services")])
    facts = [fact("Financial Services Analyst", "role", years=5)]
    result = score_match(j, facts, PreferencesIn())
    assert result.requirements[0].status == "matched"


def test_unrelated_role_never_satisfies_specific_requirement():
    j = job([req("python experience", "experience", min_years=5, normalized="python")])
    facts = [fact("Marketing Coordinator", "role", years=10)]
    result = score_match(j, facts, PreferencesIn())
    r = result.requirements[0]
    assert r.status == "missing"
    assert r.credit == 0.0
    assert r.years_evidence == "none"


def test_explicit_skill_years_claim_can_satisfy_requirement():
    # The candidate directly entered and verified "Python: 6 years" themselves - not inferred from any
    # role. user_entry/user_edit are the only sources trustworthy enough for this on their own.
    j = job([req("python experience", "experience", min_years=5, normalized="python")])
    facts = [fact("Python", "skill", years=6, source="user_entry")]
    result = score_match(j, facts, PreferencesIn())
    r = result.requirements[0]
    assert r.status == "matched"
    assert r.years_evidence == "known"


def test_resume_derived_skill_years_cannot_satisfy_requirement():
    # A resume-parsed skill fact's years are never treated as authoritative on their own - editing a
    # resume_parse fact never relabels its source (see profile.py), so this source can never prove the
    # years value itself was explicitly asserted rather than silently produced by a parser.
    j = job([req("python experience", "experience", min_years=5, normalized="python")])
    facts = [fact("Python", "skill", years=6, source="resume_parse")]
    result = score_match(j, facts, PreferencesIn())
    r = result.requirements[0]
    assert r.status != "matched"
    assert r.status == "missing"  # no role evidence either, in this fixture


def test_unrelated_role_duration_does_not_leak_into_skill_years():
    # A verified-but-yearless Python skill plus a long but unrelated role must not combine into a
    # satisfied "5+ years Python" - the unrelated role's 10 years must never leak in.
    j = job([req("python experience", "experience", min_years=5, normalized="python")])
    facts = [fact("Python", "skill", source="user_entry"), fact("Marketing Coordinator", "role", years=10)]
    result = score_match(j, facts, PreferencesIn())
    r = result.requirements[0]
    assert r.status == "missing"


def test_parser_regression_resume_parse_years_not_authoritative():
    # Defensive regression guard: resume_extract does not produce `years` on skill facts today (neither
    # StubAI nor the Bedrock prompt schema), but nothing validates or strips it if a future prompt/model
    # change ever did. This asserts that even if it happened, it would still not become authoritative.
    j = job([req("python experience", "experience", min_years=5, normalized="python")])
    facts = [fact("Python", "skill", years=8, source="resume_parse")]
    result = score_match(j, facts, PreferencesIn())
    assert result.requirements[0].status != "matched"


def test_experience_no_relevant_role_is_missing():
    j = job([req("python experience", "experience", min_years=5, normalized="python")])
    result = score_match(j, [], PreferencesIn())
    r = result.requirements[0]
    assert r.status == "missing"
    assert r.years_evidence == "none"


def test_experience_no_min_years_ignores_duration():
    # No explicit year figure - falls through to ordinary text-similarity matching, untouched by any
    # of the duration logic above.
    j = job([req("data engineering experience", "experience")])
    facts = [fact("Data Engineer", "role")]
    result = score_match(j, facts, PreferencesIn())
    assert result.requirements[0].years_evidence is None


def test_dealbreaker_filters_job():
    j = job([req("python")], description="Work on defense contractor systems.")
    result = score_match(j, [fact("python")], PreferencesIn(dealbreakers=["defense"]))
    assert result.filtered_out == "dealbreaker: defense"
    assert result.score == 0.0


def test_salary_below_floor_filters_job():
    j = job([req("python")], salary_max=90000)
    result = score_match(j, [fact("python")], PreferencesIn(salary_min=120000))
    assert result.filtered_out == "salary below minimum"


def test_preference_mismatch_lowers_score():
    j = job([req("python")], remote_mode="onsite", location="Austin, TX")
    result = score_match(j, [fact("python")], PreferencesIn(remote_modes=["remote"], locations=["Boston"]))
    assert result.preference_checks == {"remote_mode": False, "location": False}
    assert result.score < 100


def test_score_and_global_score_stay_linearly_consistent():
    # The UI shows only `score` (a percentage) now, but `global_score`/`verdict` still drive backend
    # filtering - they must never be derivable to a different conclusion than the displayed percentage.
    j = job([req("python"), req("kubernetes")])
    result = score_match(j, [fact("python")], PreferencesIn())
    assert result.global_score == round(1 + 4 * result.score / 100, 1)


def test_hard_stop_caps_score_and_global_score_in_lockstep():
    j = job([req("python")], title="Backend Engineer", location="London, UK", remote_mode="onsite",
            description="We do not sponsor visas for this role.")
    result = score_match(j, [fact("python")], PreferencesIn(authorized_in=["Canada"]))
    assert result.hard_stops  # sanity: the hard-stop path actually triggered
    assert result.verdict == "hard_stop"
    assert result.score <= HARD_STOP_SCORE_CAP
    assert result.global_score <= HARD_STOP_CAP
    assert result.global_score == round(1 + 4 * result.score / 100, 1)


def test_target_titles_are_a_hard_filter():
    # career-ops title_filter.positive: a job whose title is not a target role is not shown at all.
    j = job([req("python")], title="Full Stack Engineer")
    result = score_match(j, [fact("python")], PreferencesIn(target_titles=["Data Engineer"]))
    assert result.filtered_out == "title does not match your target roles"

    j2 = job([req("python")], title="Senior Data Engineer II")
    result2 = score_match(j2, [fact("python")], PreferencesIn(target_titles=["Data Engineer"]))
    assert result2.filtered_out is None
    assert result2.score == 100.0
