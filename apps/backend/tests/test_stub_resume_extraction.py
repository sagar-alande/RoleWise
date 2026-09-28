"""StubAI's offline resume parsing: heuristic, but must actually extract roles with verbatim
bullets, not just skill keywords - resume_tailor.v1 and cover_letter.v1 have nothing to work with
otherwise (career-facts stay title-only, so every generated resume/letter is generic)."""

from rolewise.services.ai import StubAI

ai = StubAI()


def _facts(resume_text: str) -> list[dict]:
    data, _ = ai.complete_json("resume_extract.v2", resume_text=resume_text)
    return data["facts"]


def test_roles_with_bullets_are_extracted_verbatim():
    resume = (
        "PROFESSIONAL EXPERIENCE\n"
        "Data Engineer, Acme Corp (Jan 2021 - Present)\n"
        "- Built ETL pipelines processing 50M records daily using Python and Airflow\n"
        "- Reduced query latency by 40% by optimizing PostgreSQL indexes\n"
        "Data Analyst, Globex Inc (Jun 2018 - Dec 2020)\n"
        "* Developed dashboards in Tableau for executive reporting\n"
    )
    roles = [f for f in _facts(resume) if f["kind"] == "role"]
    assert [r["title"] for r in roles] == ["Data Engineer, Acme Corp", "Data Analyst, Globex Inc"]
    first = roles[0]["details"]
    assert first["highlights"] == [
        "Built ETL pipelines processing 50M records daily using Python and Airflow",
        "Reduced query latency by 40% by optimizing PostgreSQL indexes",
    ]
    assert first["start"] == "Jan 2021" and first["end"] == "Present"


def test_section_headers_with_bulleted_lists_are_not_mistaken_for_roles():
    resume = "SKILLS\n- Python\n- SQL\nEDUCATION\n- BS Computer Science, State University\n"
    assert [f for f in _facts(resume) if f["kind"] == "role"] == []


def test_bullet_lines_without_a_marker_are_still_recognized_by_their_verb():
    # PDF text extraction often drops bullet glyphs entirely, leaving bare lines.
    resume = "Software Engineer, Acme (2019 - 2021)\nBuilt internal tooling for the support team\n"
    roles = [f for f in _facts(resume) if f["kind"] == "role"]
    assert len(roles) == 1
    assert roles[0]["details"]["highlights"] == ["Built internal tooling for the support team"]


def test_a_bullet_wrapped_across_pdf_text_lines_is_rejoined_not_dropped_or_faked_into_a_role():
    # A long bullet in a real PDF extracts as 2+ text lines. The wrapped tail has no marker and can
    # start with an uppercase abbreviation mid-sentence ("...engineering, QA, production...") - so it
    # must be rejoined to the previous bullet, not dropped, and never mistaken for a new role header.
    resume = (
        "Acme Corp | Engineer I (Jan 2021 - Present)\n"
        "- Directed projects while aligning engineering,\n"
        "QA, production, and vendor activities with operational timelines.\n"
        "- Reduced latency by 40%.\n"
    )
    roles = [f for f in _facts(resume) if f["kind"] == "role"]
    assert len(roles) == 1
    expected_first = (
        "Directed projects while aligning engineering, QA, production, and vendor activities "
        "with operational timelines."
    )
    assert roles[0]["details"]["highlights"] == [expected_first, "Reduced latency by 40%."]


def test_a_header_with_a_right_aligned_date_column_is_not_rejected_for_length():
    # A right-aligned date extracts as one huge run of spaces, which can push an otherwise-short
    # header line past a naive length cap.
    padded_title = "Acme Corp | Engineer" + " " * 90 + "Jan 2021 - Present"
    resume = f"{padded_title}\n- Built things.\n"
    roles = [f for f in _facts(resume) if f["kind"] == "role"]
    assert len(roles) == 1
    assert roles[0]["title"] == "Acme Corp | Engineer"
    assert roles[0]["details"]["start"] == "Jan 2021" and roles[0]["details"]["end"] == "Present"


def test_apostrophe_year_dates_are_parsed_including_mismatched_smart_quote_direction():
    # A resume can use a different "smart quote" direction for each date in the same range
    # ("Sept ‘22 – Aug ’23") depending on how the PDF's autocorrect treated each one.
    resume = "Acme Corp | Engineer Sept ‘22 – Aug ’23\n- Built things.\n"
    roles = [f for f in _facts(resume) if f["kind"] == "role"]
    assert len(roles) == 1
    assert roles[0]["details"]["start"] == "Sept ‘22" and roles[0]["details"]["end"] == "Aug ’23"


def test_experience_section_boundary_stops_the_skills_list_from_being_read_as_a_role():
    # A bulleted "Tools:" line under Skills wraps the same way job bullets do; with no role actively
    # collecting them, its tail must not become a fresh fake role, and it must not get silently
    # absorbed into the PRECEDING real role's last bullet either.
    resume = (
        "Acme Corp | Engineer (Jan 2021 - Present)\n"
        "- Built things.\n"
        "Skills\n"
        "- Tools: Python, SQL, a lot of other\n"
        "things that go on for a while\n"
    )
    roles = [f for f in _facts(resume) if f["kind"] == "role"]
    assert len(roles) == 1
    assert roles[0]["details"]["highlights"] == ["Built things."]


def test_summary_and_skills_before_experience_still_extracts_all_roles():
    # Most real resumes put Summary/Skills BEFORE Experience - hitting one of those section headers
    # first must not end the scan before Experience is even reached. Regression for a production bug
    # where a real resume's 4 roles all vanished because of this exact ordering.
    resume = (
        "SUMMARY\n"
        "Experienced engineer with a track record of delivery.\n"
        "TECHNICAL SKILLS\n"
        "Python, SQL, AWS\n"
        "PROFESSIONAL EXPERIENCE\n"
        "Acme Corp | Engineer I (Jan 2022 - Present)\n"
        "- Built things.\n"
        "Globex Inc | Engineer II (Jan 2019 - Dec 2021)\n"
        "- Built other things.\n"
    )
    roles = [f for f in _facts(resume) if f["kind"] == "role"]
    assert [r["title"] for r in roles] == ["Acme Corp | Engineer I", "Globex Inc | Engineer II"]


def test_experience_stops_correctly_at_the_next_section_after_being_entered():
    # Preserve the original purpose of the section-boundary check: once Experience HAS been entered,
    # a later section (Education here) must still end the scan, not be absorbed as more roles/bullets.
    resume = (
        "PROFESSIONAL EXPERIENCE\n"
        "Acme Corp | Engineer (Jan 2021 - Present)\n"
        "- Built things.\n"
        "EDUCATION\n"
        "State University - BS Computer Science | 2018\n"
    )
    roles = [f for f in _facts(resume) if f["kind"] == "role"]
    assert len(roles) == 1
    assert roles[0]["details"]["highlights"] == ["Built things."]


def test_education_section_extracts_institution_degree_and_dates():
    # The exact 3-entry shape from the real resume that surfaced this bug, including the PDF line-wrap
    # ("...| Currently\nEnrolled") that must be rejoined into one record, not split into two.
    resume = (
        "EDUCATION\n"
        "Indiana Wesleyan University, Merrillville, IN - Master of Science in Artificial Intelligence, "
        "Concentration: Data Analytics | Currently \n"
        "Enrolled\n"
        "New Jersey Institute of Technology, Newark, NJ - Master of Science in Information Systems, "
        "Concentration: Data Science & \n"
        "Analytics | Dec 2022\n"
        "University of Mumbai, Mumbai, India - Bachelor of Engineering in Electronics Engineering | May 2015\n"
    )
    edu = [f for f in _facts(resume) if f["kind"] == "education"]
    assert len(edu) == 3
    assert edu[0]["title"] == "Master of Science in Artificial Intelligence, Concentration: Data Analytics"
    assert edu[0]["details"]["institution"] == "Indiana Wesleyan University, Merrillville, IN"
    assert edu[0]["details"]["end"] == "Currently Enrolled"
    assert edu[1]["details"]["institution"] == "New Jersey Institute of Technology, Newark, NJ"
    assert edu[1]["details"]["end"] == "Dec 2022"
    assert edu[2]["title"] == "Bachelor of Engineering in Electronics Engineering"
    assert edu[2]["details"]["end"] == "May 2015"


def test_certifications_section_extracts_when_present():
    resume = (
        "CERTIFICATIONS\n"
        "AWS Certified Solutions Architect - Associate | 2023\n"
        "Certified Scrum Master | 2021\n"
    )
    certs = [f for f in _facts(resume) if f["kind"] == "certification"]
    assert len(certs) == 2
    # Certifications don't get an institution/degree split - their own name can legitimately contain
    # " - ", so the raw title (minus only the trailing date) is kept whole rather than guessing a split.
    assert certs[0]["title"] == "AWS Certified Solutions Architect - Associate"
    assert certs[0]["details"]["end"] == "2023"
    assert certs[1]["title"] == "Certified Scrum Master" and certs[1]["details"]["end"] == "2021"


def test_no_education_or_certification_sections_extracts_nothing_for_those_kinds():
    resume = "PROFESSIONAL EXPERIENCE\nAcme Corp | Engineer (Jan 2021 - Present)\n- Built things.\n"
    facts = _facts(resume)
    assert [f for f in facts if f["kind"] == "education"] == []
    assert [f for f in facts if f["kind"] == "certification"] == []


def test_bullet_markers_wingdings_private_use_glyphs_are_recognized():
    # Word's PDF export commonly embeds bullets via a Wingdings/Symbol font, which survive text
    # extraction as private-use-area codepoints rather than a real bullet character - regression for a
    # production bug where an entire resume's bullets (and therefore all 4 roles) were invisible to the
    # parser because of this exact encoding.
    for bullet in ("•", "", ""):
        resume = f"Acme Corp | Engineer (Jan 2021 - Present)\n{bullet} Built things.\n"
        roles = [f for f in _facts(resume) if f["kind"] == "role"]
        assert len(roles) == 1, f"bullet {bullet!r} was not recognized"
        assert roles[0]["details"]["highlights"] == ["Built things."]


def test_ambiguous_skill_words_only_match_their_conventional_capitalization():
    # "go", "excel" and "r" are ordinary English words far more often than they are a skill name.
    resume = "Summary: I go the extra mile and always try to excel in a fast-paced role."
    assert [f["title"] for f in _facts(resume) if f["kind"] == "skill"] == []

    resume2 = "Skills: Go, Excel, Spring Framework"
    titles = {f["title"] for f in _facts(resume2) if f["kind"] == "skill"}
    assert {"go", "excel", "spring"} <= titles
