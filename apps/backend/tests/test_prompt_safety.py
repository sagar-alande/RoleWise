"""Prompts that embed user-controlled free text (a resume, a job posting) must tell the model to
treat that content as untrusted and ignore embedded instructions - otherwise the text itself could
try to manipulate what gets extracted or written. Regression for resume_extract.v2.md, which had no
such instruction while every other prompt embedding attacker-influenced text already did."""

from rolewise.services.prompts import load_prompt

# Every live prompt that interpolates raw free text the user doesn't control the meaning of
# (an uploaded resume, a pasted/fetched job posting) - not prompts that only see structured,
# already-computed data (e.g. match_explanation.v2, which only sees a JSON score breakdown).
PROMPTS_EMBEDDING_UNTRUSTED_TEXT = [
    "resume_extract.v2",
    "job_requirements.v2",
    "resume_tailor.v1",
    "cover_letter.v1",
]


def test_prompts_embedding_untrusted_free_text_flag_it_as_untrusted():
    for name in PROMPTS_EMBEDDING_UNTRUSTED_TEXT:
        text = load_prompt(name).lower()
        assert "untrusted" in text, f"{name}.md embeds user-controlled text but has no untrusted-data instruction"
