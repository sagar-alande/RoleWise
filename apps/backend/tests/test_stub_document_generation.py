"""StubAI's offline resume/cover-letter generation: a role fact's title can be the full extracted
header line ("Company, Location | Job Title"), not just the job title - dropped verbatim into a
sentence built for a title alone, that reads as broken grammar. Regression for that exact bug."""

import json

from rolewise.services.ai import StubAI, _display_role_title

ai = StubAI()

ROLE = {"id": "r1", "kind": "role", "title": "State Street, Boston, MA | Risk Data Management Analyst",
        "details": {"company": None, "start": "Sept 2024", "end": "present",
                    "highlights": ["Built and supported automated data pipelines."]}}
PLAIN_ROLE = {"id": "r2", "kind": "role", "title": "Data Engineer", "details": {"end": "present", "highlights": []}}


def test_display_role_title_strips_company_and_location_prefix():
    assert _display_role_title("State Street, Boston, MA | Risk Data Management Analyst") == "Risk Data Management Analyst"


def test_display_role_title_leaves_a_plain_title_unchanged():
    assert _display_role_title("Data Engineer") == "Data Engineer"


def test_display_role_title_handles_multiple_pipes_by_taking_the_last_segment():
    # "Title | Company | Dates"-style headers exist too - the job title is still whichever segment
    # comes last, since _extract_roles always strips the trailing date range before storing the title.
    assert _display_role_title("Acme Corp | Engineer II | Remote") == "Remote"


def _generate(role: dict, job_title="Data Engineer", company="Acme"):
    variables = {
        "facts_json": json.dumps([role]),
        "requirements_json": "[]",
        "job_title": job_title,
        "company": company,
        "job_description": "",
    }
    resume, _ = ai.complete_json("resume_tailor.v1", **variables)
    cover, _ = ai.complete_json("cover_letter.v1", **variables)
    return resume, cover


def test_cover_letter_opening_never_contains_the_raw_combined_title():
    _, cover = _generate(ROLE)
    assert "|" not in cover["opening"]["text"]
    assert "I currently work as Risk Data Management Analyst" in cover["opening"]["text"]
    assert "State Street, Boston, MA" not in cover["opening"]["text"]


def test_resume_summary_never_contains_the_raw_combined_title():
    resume, _ = _generate(ROLE)
    summary_text = " ".join(s["text"] for s in resume["summary"])
    assert "|" not in summary_text
    assert "State Street, Boston, MA" not in summary_text


def test_plain_title_roles_are_unaffected():
    _, cover = _generate(PLAIN_ROLE)
    assert "I currently work as Data Engineer" in cover["opening"]["text"]
