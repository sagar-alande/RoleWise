"""Tailored resume and cover letter: the fact check is the product invariant, so it gets the most tests."""

import io

from docx import Document as Docx

from rolewise.services import documents as docs

ROLE = docs.Fact("r1", "role", "Data Engineer", {"company": "Initech", "years": 3, "start": "2022-01",
                                                "end": "present",
                                                "highlights": ["Cut pipeline runtime by 40% with Airflow"]})
ROLE2 = docs.Fact("r2", "role", "Data Analyst", {"company": "Globex", "years": 2})
PY = docs.Fact("s1", "skill", "python", {})
K8S = docs.Fact("s2", "skill", "k8s", {})
EDU = docs.Fact("e1", "education", "BSc Computer Science", {"institution": "State University", "end": "2020"})
FACTS = [ROLE, ROLE2, PY, K8S, EDU]


def checker(job_terms=("python", "spark")):
    return docs.FactChecker(FACTS, list(job_terms), "Must have Python. Spark is a plus. Team of 12.")


def test_line_without_facts_is_removed():
    fc = checker()
    assert not fc.verify("summary", "Expert in data platforms.", [])
    assert fc.check.removed[0]["reason"] == "not backed by a verified fact"


def test_unknown_or_unverified_fact_ids_are_removed():
    fc = checker()
    assert not fc.verify("summary", "Python developer.", ["not-a-real-fact"])


def test_invented_numbers_are_removed():
    fc = checker()
    assert fc.verify("experience", "Cut pipeline runtime by 40% using Airflow.", ["r1"])
    assert not fc.verify("experience", "Cut pipeline runtime by 60% using Airflow.", ["r1"])
    assert "60" in fc.check.removed[0]["reason"]


def test_total_years_across_cited_roles_is_allowed():
    fc = checker()
    assert fc.verify("summary", "Data professional with 5 years of experience.", ["r1", "r2"])
    assert not fc.verify("summary", "Data professional with 5 years of experience.", ["r1"])


def test_skills_not_in_cited_facts_are_removed():
    fc = checker()
    assert fc.verify("skills", "Python", ["s1"])
    assert not fc.verify("skills", "Python and Spark", ["s1"])
    assert "spark" in fc.check.removed[0]["reason"]


def test_aliases_count_as_the_same_skill():
    fc = checker(job_terms=("kubernetes",))
    assert fc.verify("skills", "Kubernetes", ["s2"])


def test_em_dashes_are_replaced():
    fc = checker()
    fc.verify("summary", "Python engineer — pipelines", ["s1"])
    assert "—" not in fc.check.kept[0]["text"]


def test_unsupported_leadership_verb_is_flagged_not_hidden():
    fc = checker()
    assert fc.verify("experience", "Led Python pipeline work.", ["s1"])
    assert fc.check.warnings and "led" in fc.check.warnings[0].lower()


def test_job_title_skill_echo_survives_without_a_possession_claim():
    # "Data Engineering" is a KNOWN_SKILLS phrase that also happens to be part of the job title - naming
    # the role you're applying for must not be treated as a claim of having that skill.
    fc = docs.FactChecker(FACTS, [], "", names="Data Engineering Platform Engineer at Acme")
    assert fc.verify("opening", "I am interested in the Data Engineering Platform Engineer role at Acme.", ["r1"])


def test_job_title_skill_echo_still_rejected_when_paired_with_a_possession_claim():
    # Same job title, but this sentence claims the candidate HAS the experience - that's a claim, not an
    # echo, and still needs a cited fact regardless of what the job title happens to contain.
    fc = docs.FactChecker(FACTS, [], "", names="Data Engineering Platform Engineer at Acme")
    assert not fc.verify("opening", "I have Data Engineering experience.", ["r1"])
    assert "data engineering" in fc.check.removed[0]["reason"]


def test_resume_headers_come_from_facts_not_the_model():
    raw = {"experience": [{"fact_id": "r1", "title": "Head of Data", "bullets": [
        {"text": "Cut pipeline runtime by 40% with Airflow", "fact_ids": ["r1"]}]}],
        "education": [], "skills": [{"text": "python", "fact_ids": ["s1"]}]}
    content, _check = docs.assemble_resume(raw, FACTS, {"full_name": "Sam Lee"}, ["python"], "Python", "Data Engineer")
    role = content["experience"][0]
    assert role["title"] == "Data Engineer" and role["company"] == "Initech"
    assert role["bullets"][0]["text"] == "Cut pipeline runtime by 40% with Airflow"
    # Education is always listed even if the model left it out.
    assert content["education"][0]["text"] == "BSc Computer Science, State University, 2020"


def test_resume_rejects_a_block_that_is_not_a_role():
    raw = {"experience": [{"fact_id": "s1", "bullets": []}]}
    content, check = docs.assemble_resume(raw, FACTS, {}, [], "", "x")
    # The invalid block is still rejected and logged - but real verified roles (r1, r2) are backfilled
    # regardless, since a career history isn't erased just because the model proposed one bad block.
    assert [e["fact_id"] for e in content["experience"]] == ["r1", "r2"]
    assert check.removed[0]["reason"] == "not a verified role"


# --------------------------------------------------------------------------- Phase 8B: full career history
# Regresses the exact bug observed in production: a candidate with several employers ended up with a
# generated resume showing only 1-2 roles because the model (or stub) simply didn't propose the rest, and
# nothing recovered them. FIVE roles, spanning a full career, with the model deliberately proposing bullets
# for only 2 of them (the current role and one from the middle) - simulating under-selection at any position,
# not just "drops the oldest one".
ROLE_CURRENT = docs.Fact("rc", "role", "Senior Data Engineer", {"company": "Wayne Enterprises", "start": "2023-01",
                                                                "end": "present", "highlights": [
    "Cut pipeline runtime by 40% with Airflow", "Migrated warehouse to Snowflake",
    "Led on-call rotation for data platform", "Mentored two junior engineers",
    "Built real-time fraud detection pipeline", "Reduced cloud spend by 20%",
    "Introduced dbt for transformation layer", "Automated data quality checks"]})
ROLE_RECENT = docs.Fact("rr", "role", "Data Engineer", {"company": "Stark Industries", "start": "2020-01",
                                                        "end": "2022-12", "highlights": [
    "Built ETL pipelines processing 10M records daily", "Optimized PostgreSQL indexes",
    "Migrated on-prem jobs to AWS", "Wrote internal data pipeline docs",
    "Onboarded new hires to the data stack", "Fixed recurring pipeline failures"]})
ROLE_MID = docs.Fact("rm", "role", "Data Analyst", {"company": "Oscorp", "start": "2017-06", "end": "2019-12",
                                                    "highlights": [
    "Built weekly reporting dashboards in Tableau", "Automated a manual reconciliation process",
    "Presented findings to leadership", "Trained analysts on SQL", "Cleaned legacy customer data"]})
ROLE_EARLY = docs.Fact("re", "role", "Junior Analyst", {"company": "Initrode", "start": "2015-01",
                                                        "end": "2017-05", "highlights": [
    "Maintained spreadsheet-based reports", "Assisted with month-end close", "Learned SQL on the job",
    "Supported the analytics team with ad hoc requests"]})
ROLE_INTERN = docs.Fact("ri", "role", "Data Intern", {"company": "Acme Co", "start": "2014-06", "end": "2014-12",
                                                      "highlights": ["Cleaned datasets for a research project",
                                                                    "Shadowed senior analysts",
                                                                    "Wrote basic SQL queries"]})
CAREER_FACTS = [ROLE_CURRENT, ROLE_RECENT, ROLE_MID, ROLE_EARLY, ROLE_INTERN, PY, K8S, EDU]


def test_all_five_verified_roles_survive_even_when_model_proposes_only_two():
    # The model (or a real Bedrock response under token pressure) only bothered proposing the current role
    # and one from the middle of the career - exactly the failure mode reported.
    raw = {"experience": [
        {"fact_id": "rc", "bullets": [{"text": h, "fact_ids": ["rc"]} for h in ROLE_CURRENT.details["highlights"]]},
        {"fact_id": "rm", "bullets": [{"text": h, "fact_ids": ["rm"]} for h in ROLE_MID.details["highlights"]]},
    ]}
    content, check = docs.assemble_resume(raw, CAREER_FACTS, {"full_name": "Sam Lee"}, [], "", "Data Engineer")
    ids = [r["fact_id"] for r in content["experience"]]
    # All 5 roles present, in reverse-chronological order - not just the 2 the model bothered to propose.
    assert ids == ["rc", "rr", "rm", "re", "ri"]
    by_id = {r["fact_id"]: r for r in content["experience"]}
    # Bullet ceilings by recency rank: current (rank 0) up to 5, next (rank 1) up to 4, older (rank 2+) up to 2.
    assert len(by_id["rc"]["bullets"]) == 5  # 8 candidates offered, capped at 5
    assert len(by_id["rr"]["bullets"]) == 0  # never proposed by the model - never fabricated
    assert len(by_id["rm"]["bullets"]) == 2  # rank 2 (third most recent) -> capped at 2, 5 candidates offered
    assert len(by_id["re"]["bullets"]) == 0
    assert len(by_id["ri"]["bullets"]) == 0
    # The backfilled roles are still real headers (title/company from the fact, never invented).
    assert by_id["rr"]["company"] == "Stark Industries" and by_id["ri"]["title"] == "Data Intern"


def test_role_bullet_ceilings_are_never_exceeded_regardless_of_rank():
    # Same 5 roles, but this time the model proposes generous bullet counts for every role - the cap must
    # still hold at 5 / 4 / 2 / 2 / 2 by recency rank, never fabricating and never exceeding the ceiling.
    raw = {"experience": [
        {"fact_id": f.id, "bullets": [{"text": h, "fact_ids": [f.id]} for h in f.details["highlights"]]}
        for f in [ROLE_CURRENT, ROLE_RECENT, ROLE_MID, ROLE_EARLY, ROLE_INTERN]
    ]}
    content, _ = docs.assemble_resume(raw, CAREER_FACTS, {}, [], "", "x")
    caps = {"rc": 5, "rr": 4, "rm": 2, "re": 2, "ri": 2}
    for role in content["experience"]:
        available = len(next(f for f in CAREER_FACTS if f.id == role["fact_id"]).details["highlights"])
        assert len(role["bullets"]) == min(caps[role["fact_id"]], available)


# --------------------------------------------------------------------------- role date ordering
# Regression for a real bug: role dates were sorted by comparing the extracted strings directly
# ("Mar 2026" vs "Sept 2024"), which sorts alphabetically, not chronologically - that exact pair put
# State Street (ending March 2026) THIRD instead of first, so it got a 2-bullet cap instead of 5. This
# is the exact date sequence from the resume that surfaced it.
STATE_STREET = docs.Fact("ss", "role", "Risk Data Management Analyst", {"company": "State Street",
                                                                        "start": "Sept 2024", "end": "Mar 2026",
                                                                        "highlights": [f"State Street bullet {i}"
                                                                                      for i in range(1, 6)]})
VANDOO = docs.Fact("vd", "role", "Trainee Analyst", {"company": "Vandoo LLC", "start": "Oct 2023", "end": "Sept 2024",
                                                     "highlights": [f"Vandoo bullet {i}" for i in range(1, 5)]})
VOLUNTEER = docs.Fact("vl", "role", "Data Analyst and Automation Engineer", {"company": "Volunteer",
                                                                             "start": "Apr 2023", "end": "Oct 2023",
                                                                             "highlights": [f"Volunteer bullet {i}"
                                                                                           for i in range(1, 4)]})
ACCENTURE = docs.Fact("ac", "role", "Senior Data Analyst (SSE)", {"company": "Accenture", "start": "Oct 2015",
                                                                  "end": "Dec 2020",
                                                                  "highlights": [f"Accenture bullet {i}"
                                                                                for i in range(1, 6)]})
MONTH_NAME_DATE_FACTS = [STATE_STREET, VANDOO, VOLUNTEER, ACCENTURE]


def test_month_name_dates_sort_chronologically_not_alphabetically():
    raw = {"experience": [
        {"fact_id": f.id, "bullets": [{"text": h, "fact_ids": [f.id]} for h in f.details["highlights"]]}
        for f in MONTH_NAME_DATE_FACTS
    ]}
    content, _ = docs.assemble_resume(raw, MONTH_NAME_DATE_FACTS, {}, [], "", "x")
    assert [r["title"] for r in content["experience"]] == [
        "Risk Data Management Analyst", "Trainee Analyst",
        "Data Analyst and Automation Engineer", "Senior Data Analyst (SSE)",
    ]
    by_title = {r["title"]: r for r in content["experience"]}
    # 5 bullets to the most recent role, 4 to the next, 2 / 2 to the older two.
    assert len(by_title["Risk Data Management Analyst"]["bullets"]) == 5
    assert len(by_title["Trainee Analyst"]["bullets"]) == 4
    assert len(by_title["Data Analyst and Automation Engineer"]["bullets"]) == 2
    assert len(by_title["Senior Data Analyst (SSE)"]["bullets"]) == 2


def test_parse_role_date_handles_month_names_iso_dates_and_open_ended_roles():
    from rolewise.services.ai import parse_role_date, parse_role_end_date

    assert parse_role_date("Mar 2026") == (2026, 3)
    assert parse_role_date("Sept 2024") == (2024, 9)
    assert parse_role_date("Oct 2023") == (2023, 10)
    assert parse_role_date("Dec 2020") == (2020, 12)
    assert parse_role_date("2023-01") == (2023, 1)  # ISO, from a manually-entered fact
    assert parse_role_date("2021") == (2021, 12)  # bare year, no month info available
    assert parse_role_date("Present") == (9999, 12)
    assert parse_role_date("not a date") == (0, 0)  # unparseable sorts as oldest, never raises
    # A blank/missing value is NOT the same as "Present" for a general date - only parse_role_end_date
    # (used specifically for the end field) treats "nothing recorded" as "still ongoing".
    assert parse_role_date(None) == (0, 0)
    assert parse_role_date("") == (0, 0)
    assert parse_role_end_date(None) == (9999, 12)
    assert parse_role_end_date("") == (9999, 12)
    assert parse_role_end_date("Mar 2026") == (2026, 3)


def test_skills_fallback_adds_relevant_verified_skills_when_model_under_selects():
    facts = [ROLE_CURRENT, PY, K8S,
             docs.Fact("s3", "skill", "airflow", {}), docs.Fact("s4", "skill", "snowflake", {}),
             docs.Fact("s5", "skill", "dbt", {}), docs.Fact("s6", "skill", "salesforce", {})]  # irrelevant
    raw = {"skills": [{"text": "python", "fact_ids": ["s1"]}]}  # model only proposed 1
    job_text = "We use Airflow, Snowflake and dbt for our data platform, plus Python."
    content, _ = docs.assemble_resume(raw, facts, {}, [], job_text, "x")
    names = {s["text"] for s in content["skills"]}
    # Topped up with job-relevant skills the model missed (as many as exist and are relevant, up to the floor)...
    assert {"python", "airflow", "snowflake", "dbt"}.issubset(names)
    # ...but never with an irrelevant one just to pad the list.
    assert "salesforce" not in names


def test_skills_are_not_backfilled_with_the_full_inventory_when_model_selection_is_sufficient():
    facts = [ROLE_CURRENT, PY, K8S,
             docs.Fact("s3", "skill", "airflow", {}), docs.Fact("s4", "skill", "snowflake", {}),
             docs.Fact("s5", "skill", "dbt", {}), docs.Fact("s6", "skill", "salesforce", {})]
    raw = {"skills": [{"text": "python", "fact_ids": ["s1"]}, {"text": "airflow", "fact_ids": ["s3"]},
                      {"text": "snowflake", "fact_ids": ["s4"]}, {"text": "dbt", "fact_ids": ["s5"]},
                      {"text": "k8s", "fact_ids": ["s2"]}]}  # already 5 - meets the floor
    content, _ = docs.assemble_resume(raw, facts, {}, [], "", "x")
    # No automatic backfill kicks in once the model's own selection already meets the floor.
    assert {s["text"] for s in content["skills"]} == {"python", "airflow", "snowflake", "dbt", "k8s"}


def test_cover_letter_keeps_only_verbatim_job_quotes():
    raw = {"opening": {"text": "I am applying as a Data Engineer.", "fact_ids": ["r1"]},
           "problems": {"text": "You need Spark at scale for a team of 12.", "fact_ids": [],
                        "jd_quotes": ["Spark is a plus.", "We love Rust."]},
           "closing": {"text": "I would welcome a conversation.", "fact_ids": []}}
    content, check = docs.assemble_cover_letter(raw, FACTS, {}, ["spark"], "Must have Python. Spark is a plus. "
                                                "Team of 12.", "Data Engineer", "Acme")
    assert content["jd_quotes"] == ["Spark is a plus."]
    assert content["problems"]["text"].startswith("You need Spark")  # job needs may name job terms
    assert any("words" in w for w in check.warnings)  # too short for a real letter


def test_cover_letter_narrative_replaces_the_bullet_dump():
    raw = {"opening": {"text": "I am applying as a Data Engineer.", "fact_ids": ["r1"]},
           "narrative": [
               {"text": "In my current role, I cut pipeline runtime by 40% with Airflow.", "fact_ids": ["r1"], "para": 1},
               {"text": "I am also comfortable with Python.", "fact_ids": ["s1"], "para": 1},
               {"text": "My background as a Data Analyst gives me a broad view of the data lifecycle.",
                "fact_ids": ["r2"], "para": 2},
           ],
           "closing": {"text": "I would welcome a conversation.", "fact_ids": []}}
    content, check = docs.assemble_cover_letter(raw, FACTS, {}, ["python"], "Must have Python.", "Data Engineer", "Acme")
    assert "bullets" not in content
    assert len(content["narrative"]) == 2  # 2 paragraphs, not a per-achievement bullet list
    assert "Cut pipeline runtime" in content["narrative"][0] or "cut pipeline runtime" in content["narrative"][0]
    assert "Data Analyst" in content["narrative"][1]
    text = docs.cover_plain_text(content)
    assert "- " not in text  # no bullet-list rendering anywhere in the plain-text output
    md = docs.to_markdown("cover_letter", content)
    assert "- **" not in md  # no "- **lead,** text" bullet lines in the markdown either


def test_cover_letter_narrative_drops_one_bad_sentence_without_losing_the_paragraph():
    raw = {"narrative": [
        {"text": "I cut pipeline runtime by 40% with Airflow.", "fact_ids": ["r1"], "para": 1},
        {"text": "I cut pipeline runtime by 90% with Airflow.", "fact_ids": ["r1"], "para": 1},  # invented number
    ]}
    content, check = docs.assemble_cover_letter(raw, FACTS, {}, [], "", "Data Engineer", "Acme")
    assert content["narrative"] == ["I cut pipeline runtime by 40% with Airflow."]
    assert any("90" in r["reason"] for r in check.removed)


def test_cover_letter_problems_cannot_claim_possession_of_an_unverified_skill():
    raw = {"problems": {"text": "I have deep Spark experience and would bring it to this team.",
                        "fact_ids": [], "jd_quotes": []}}
    content, check = docs.assemble_cover_letter(raw, FACTS, {}, ["spark"], "Spark is a plus.",
                                                "Data Engineer", "Acme")
    assert content["problems"] is None
    assert any("spark" in r["reason"] and "claims to have" in r["reason"] for r in check.removed)


def test_cover_letter_problems_can_still_name_a_companys_need_without_claiming_it():
    raw = {"problems": {"text": "This team needs Spark experience at scale.", "fact_ids": [], "jd_quotes": []}}
    content, _check = docs.assemble_cover_letter(raw, FACTS, {}, ["spark"], "Spark is a plus.",
                                                 "Data Engineer", "Acme")
    assert content["problems"] is not None
    assert content["problems"]["text"] == "This team needs Spark experience at scale."


def test_coverage_marks_honest_gaps():
    reqs = [{"text": "python", "importance": "high", "status": "matched"},
            {"text": "spark", "importance": "critical", "status": "missing"},
            {"text": "sql", "importance": "high", "status": "matched"}]
    cov = {c["text"]: c["state"] for c in docs.keyword_coverage(reqs, "Python engineer")}
    assert cov == {"python": "shown", "spark": "not_in_profile", "sql": "could_add"}


def test_docx_and_markdown_render():
    raw = {"summary": [{"text": "Data Engineer with 3 years of experience.", "fact_ids": ["r1"]}],
           "experience": [{"fact_id": "r1", "bullets": [{"text": "Cut pipeline runtime by 40% with Airflow",
                                                        "fact_ids": ["r1"]}]}],
           "skills": [{"text": "python", "fact_ids": ["s1"]}]}
    content, _ = docs.assemble_resume(raw, FACTS, {"full_name": "Sam Lee", "email": "sam@example.com"},
                                      ["python"], "", "Data Engineer")
    md = docs.to_markdown("resume", content)
    assert md.startswith("# Sam Lee") and "## Work Experience" in md and "## Professional Summary" in md
    text = "\n".join(p.text for p in Docx(io.BytesIO(docs.to_docx("resume", content))).paragraphs)
    assert "Cut pipeline runtime by 40% with Airflow" in text and "Sam Lee" in text
