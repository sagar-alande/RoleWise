from rolewise.services.matching import PreferencesIn, score_match
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


def test_target_titles_are_checked_against_the_job_title():
    j = job([req("python")], title="Full Stack Engineer")
    result = score_match(j, [fact("python")], PreferencesIn(target_titles=["Data Engineer"]))
    assert result.preference_checks == {"target_title": False}

    j2 = job([req("python")], title="Senior Data Engineer II")
    result2 = score_match(j2, [fact("python")], PreferencesIn(target_titles=["Data Engineer"]))
    assert result2.preference_checks == {"target_title": True}
    assert result2.score > result.score
