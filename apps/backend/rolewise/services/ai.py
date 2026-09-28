"""AI access layer. BedrockAI calls Amazon Bedrock. StubAI is deterministic and offline for local dev and tests.

Everything else in the codebase calls get_ai() and never talks to Bedrock directly.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from typing import Protocol

from rolewise.config import get_settings
from rolewise.services.prompts import render_prompt


class AI(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def complete_json(self, prompt_name: str, fast: bool = False, **variables: str) -> tuple[dict, str]:
        """Returns (parsed JSON, model id)."""
        ...


def _parse_json(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])


class BedrockAI:
    def __init__(self) -> None:
        import boto3

        s = get_settings()
        self.settings = s
        self.client = boto3.client("bedrock-runtime", region_name=s.aws_region)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            body = json.dumps({"inputText": text[:8000], "dimensions": self.settings.embedding_dims, "normalize": True})
            resp = self.client.invoke_model(modelId=self.settings.bedrock_embed_model_id, body=body)
            vectors.append(json.loads(resp["body"].read())["embedding"])
        return vectors

    def complete_json(self, prompt_name: str, fast: bool = False, **variables: str) -> tuple[dict, str]:
        model_id = self.settings.bedrock_fast_model_id if fast else self.settings.bedrock_text_model_id
        prompt = render_prompt(prompt_name, **variables)
        resp = self.client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 4096, "temperature": 0},
        )
        text = resp["output"]["message"]["content"][0]["text"]
        return _parse_json(text), model_id


# --------------------------------------------------------------------------- offline stub

# Vocabulary so the stub can "extract" skills from text via keyword matching. It's necessarily
# shallow next to real extraction (Bedrock reads the whole description); this list exists to make
# local/offline dev and demos closer to real results, not to replace the LLM path.
# 'go', 'r', 'excel' and 'spring' deliberately excluded here - see _CASE_SENSITIVE_SKILLS below.
KNOWN_SKILLS = [
    # languages
    "python", "java", "javascript", "typescript", "golang", "rust", "c++", "c#", "ruby",
    "scala", "kotlin", "swift", "php",
    # web / app frameworks
    "react", "next.js", "vue", "angular", "node.js", "fastapi", "django", "flask",
    "ruby on rails", "graphql", "rest api", "grpc",
    # data / ml
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "snowflake", "bigquery",
    "machine learning", "deep learning", "pytorch", "tensorflow", "scikit-learn", "nlp", "llm",
    "data analysis", "data engineering", "pandas", "numpy", "spark", "airflow", "dbt", "etl",
    "tableau", "power bi", "looker", "a/b testing", "statistics",
    # cloud / infra
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ci/cd", "linux", "microservices",
    "distributed systems", "system design",
    # product / design
    "figma", "sketch", "product management", "roadmapping", "user research", "prototyping",
    "wireframing", "a/b tests", "ux research", "design systems",
    # business / ops / legal
    "salesforce", "hubspot", "sql reporting", "financial modeling", "forecasting", "contract negotiation",
    "compliance", "gdpr", "sox", "vendor management", "budget management", "recruiting",
    # general / soft skills
    "git", "agile", "scrum", "kanban", "project management", "stakeholder management",
    "communication", "leadership", "mentoring", "cross-functional collaboration",
]

# Real skills that collide with ordinary English words ("go the extra mile", "excel in",
# "a spring in your step"). A lowercase, whole-text match would fire on the word, not the skill - so
# these match only their conventional capitalized form, against the ORIGINAL (un-lowercased) text.
# Same fix career-ops applies to 'Go' and 'SAFe' in skill-extract.mjs. The R language isn't included
# here at all: a bare single letter is unfixably ambiguous (initials like "R. Dighe", list markers,
# roman numerals) even case-sensitively, so it's left out rather than risk-managed.
_CASE_SENSITIVE_SKILLS = {
    "Go": re.compile(r"(?<![A-Za-z])Go(?![A-Za-z-])"),  # trailing '-' excludes "Go-to-market", "Go-live"
    "Excel": re.compile(r"(?<![A-Za-z])Excel(?![A-Za-z])"),
    "Spring": re.compile(r"(?<![A-Za-z])Spring(?![A-Za-z])"),
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#./]+", text.lower())


def _stub_vector(text: str, dims: int) -> list[float]:
    """Bag-of-tokens hashed into a unit vector. Shared words give positive cosine similarity."""
    vec = [0.0] * dims
    for tok in _tokens(text):
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        vec[h % dims] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _find_skills(text: str) -> list[str]:
    low = text.lower()
    found = [s for s in KNOWN_SKILLS if re.search(r"(?<![a-z])" + re.escape(s) + r"(?![a-z])", low)]
    found += [s.lower() for s, pattern in _CASE_SENSITIVE_SKILLS.items() if pattern.search(text)]
    return found


# --------------------------------------------------------------------------- offline resume parsing
# Heuristic, not an LLM: it can't understand an arbitrary resume layout the way Bedrock does. It exists
# so local/offline runs exercise the real pipeline (roles with verbatim bullets feed resume_tailor.v1 and
# cover_letter.v1) instead of silently producing skills-only facts with nothing for those to draw from.

#  and  are Wingdings/Symbol-font bullet glyphs (solid round, solid square) that Word's PDF
# export commonly embeds via a custom font encoding - they survive text extraction as private-use-area
# codepoints rather than as a real Unicode bullet character, so without these a Word-exported resume's
# bullets are invisible to _is_bullet() even though they render as normal bullets when viewed.
_BULLET_MARKER = re.compile(r"^[\s]*[•\-*◦‣●○➤►·�]\s*|^\s*\d+[.)]\s+")
_ACTION_VERBS = (
    "led", "built", "developed", "designed", "implemented", "created", "managed", "improved",
    "reduced", "increased", "launched", "drove", "delivered", "architected", "optimized", "automated",
    "migrated", "scaled", "owned", "mentored", "collaborated", "partnered", "wrote", "shipped",
    "spearheaded", "coordinated", "analyzed", "established", "directed", "oversaw", "prepared",
    "redesigned", "facilitated", "investigated", "presented", "evaluated", "administered",
    "orchestrated", "reviewed", "monitored", "organized", "maintained", "resolved", "supervised",
    "conducted", "streamlined", "eliminated", "strengthened", "supported", "identified", "executed",
    "planned", "trained", "negotiated", "authored", "researched", "assisted", "generated", "tracked",
)
_SECTION_HEADERS = {
    "experience", "work experience", "professional experience", "employment history",
    "skills", "technical skills", "core competencies", "education", "certifications",
    "projects", "summary", "professional summary", "objective", "achievements", "awards",
    "publications", "languages", "interests", "references", "volunteer experience",
}
# Month name, then either a 4-digit year or an apostrophe + 2-digit year ("Aug 2023" or "Aug '23").
# PDFs commonly typeset a truncated year's leading apostrophe as a "smart quote", and not always the
# same direction - a resume can use ’ for one date and ‘ for the very next, so both are here
# alongside the plain ASCII apostrophe.
_APOS = "’‘'"
_MONTH_YEAR = rf"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(?:\d{{4}}|[{_APOS}]\d{{2}})"
_BARE_YEAR = rf"\d{{4}}|[{_APOS}]\d{{2}}"
_DATE_RANGE = re.compile(
    rf"({_MONTH_YEAR}|{_BARE_YEAR})"
    r"\s*(?:-|–|—|to)\s*"
    rf"({_MONTH_YEAR}|{_BARE_YEAR}|present|current)",
    re.IGNORECASE,
)

_MONTH_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
# Manually-entered role facts store dates as ISO "YYYY-MM" (from an HTML month input); resume-parsed
# ones store "Mon YYYY" or a bare year (from _DATE_RANGE, matching how a PDF actually prints a date) -
# both are real, both must sort correctly against each other.
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{1,2})\b")
_SINGLE_DATE_RE = re.compile(
    rf"^(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*)?(\d{{4}}|[{_APOS}]\d{{2}})",
    re.IGNORECASE,
)


def parse_role_date(value: str | None) -> tuple[int, int]:
    """A (year, month) key for chronological sorting of a role's start/end date string - comparing
    these strings directly ("Mar 2026" vs "Sept 2024") sorts alphabetically, not by calendar order,
    which is wrong often enough to matter (that exact pair puts March 2026 BEFORE September 2024).
    An explicitly open-ended date ("Present"/"Current") sorts as the far future. Blank or unparseable
    text sorts as the far past (0, 0) - it must NOT be treated as "the future" here, since that would
    be correct for a missing END date (still ongoing) but wrong for a missing START date (just
    unknown); callers that want "no end date recorded" to mean "ongoing" apply that themselves via
    parse_role_end_date below, rather than this function guessing which field it was given. A bare
    year with no month defaults to December, since "ended sometime in 2021" is closer to year-end than
    year-start for sorting purposes, and no more specific information is available."""
    text = str(value or "").strip().lower()
    if text in ("present", "current", "currently"):
        return (9999, 12)
    if not text or text == "none":
        return (0, 0)
    iso = _ISO_DATE_RE.match(text)
    if iso:
        return (int(iso.group(1)), int(iso.group(2)))
    m = _SINGLE_DATE_RE.match(text)
    if not m:
        return (0, 0)
    month_key, year_raw = m.group(1), m.group(2).lstrip(_APOS)
    year = int(year_raw)
    if year < 100:  # apostrophe-year shorthand, e.g. "'22" -> 2022
        year += 2000
    month = _MONTH_NUM.get(month_key[:3], 12) if month_key else 12
    return (year, month)


def parse_role_end_date(value: str | None) -> tuple[int, int]:
    """A role's END date specifically - unlike parse_role_date, a blank value here means "no end
    recorded yet" (still ongoing), so it sorts as the far future just like an explicit "Present"."""
    if not value or not str(value).strip():
        return (9999, 12)
    return parse_role_date(value)


def _is_bullet(line: str) -> bool:
    if _BULLET_MARKER.match(line):
        return True
    first_word = line.strip().split(" ", 1)[0].lower().rstrip(":,.")
    return first_word in _ACTION_VERBS


def _looks_like_a_header(line: str) -> bool:
    """A genuine title/section line is a noun phrase, never a sentence - so it never ends the way a
    wrapped bullet continuation does. A resume PDF almost always extracts one visual line per physical
    line, so a long bullet wraps into 2+ text lines; the tail end ("...and cross-functional
    coordination.") is short, unmarked and would otherwise look exactly like a new role header."""
    return not line.rstrip().endswith((".", ",", ";", ":"))


def _clean_bullet(line: str) -> str:
    return _BULLET_MARKER.sub("", line).strip()


_EXPERIENCE_HEADERS = {"experience", "work experience", "professional experience", "employment history"}


def _extract_roles(text: str) -> list[dict]:
    """A role header is a short, non-bullet line immediately followed by one or more bullet lines -
    the near-universal "Title, Company (dates)" + bullets shape most resumes use for experience."""
    # A right-aligned date column ("Title | Company        Jan 2021 - Present") extracts as one huge
    # run of spaces, which can push an otherwise-short header line well past any sane length cap.
    lines = [re.sub(r" {2,}", " ", ln.rstrip()) for ln in text.splitlines()]
    roles: list[dict] = []
    # Most resumes put Summary/Skills BEFORE Experience, not after - so hitting a non-experience
    # section header must not stop the scan until Experience has actually been entered (or a role
    # has already been captured, for resumes with no explicit "Experience" header at all). Only a
    # later section - Education, etc. coming AFTER Experience - should end the scan.
    seen_experience = False
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        header_key = line.strip(":").lower()
        if header_key in _EXPERIENCE_HEADERS:
            seen_experience = True
        elif header_key in _SECTION_HEADERS:
            # Skills/Education/etc. bullets (e.g. "Tools: Power BI, SAP...") wrap the same way job
            # bullets do, and with no role actively collecting them their tails would otherwise be
            # picked up as fresh header candidates - so once we're clearly past the experience
            # section, stop looking for roles entirely rather than mis-read that section's bullets.
            if seen_experience or roles:
                break
            i += 1
            continue
        if (line and not _is_bullet(line) and len(line) <= 120 and _looks_like_a_header(line)
                and header_key not in _SECTION_HEADERS):
            # A long bullet in the PDF almost always wraps into 2-3 text lines. The wrapped tail has
            # no marker and doesn't look like a header either, but it completes a sentence the
            # previous bullet left unfinished - so it belongs appended to that bullet, not dropped.
            # Whether it "looks like a header" (ends cleanly, starts uppercase) is NOT a safe signal
            # here: a wrapped tail can start with an abbreviation ("QA, production...") just as easily
            # as a genuine next role can lack one. What a real header reliably HAS that a continuation
            # never does is a date range or a "Title | Company" pipe separator - so that's the check.
            bullets, j = [], i + 1
            while j < len(lines):
                ln = lines[j].strip()
                if not ln:
                    j += 1
                elif _is_bullet(ln):
                    bullets.append(_clean_bullet(ln))
                    j += 1
                elif (bullets and ln.strip(":").lower() not in _SECTION_HEADERS
                      and not (_DATE_RANGE.search(ln) or "|" in ln)):
                    bullets[-1] = f"{bullets[-1]} {ln}".strip()
                    j += 1
                else:
                    break
            if bullets:
                dates = _DATE_RANGE.search(line)
                details: dict = {"highlights": bullets[:8]}
                if dates:
                    details["start"], details["end"] = dates.group(1), dates.group(2)
                title = line[: dates.start()].strip(" -,|(") if dates else line
                roles.append({"kind": "role", "title": title[:500] or line[:500], "details": details})
                i = j
                continue
        i += 1
    return roles[:6]


# A record inside EDUCATION/CERTIFICATIONS "looks complete" once it has a year or a status word -
# until then, the next line is treated as a wrapped continuation of the same record rather than a
# new one (PDF extraction commonly wraps a long line, e.g. "...| Currently" / "Enrolled").
_RECORD_COMPLETE_RE = re.compile(r"\d{4}|enrolled|in\s*progress|present|expected|anticipated", re.IGNORECASE)


def _extract_section_records(text: str, header_names: set[str], kind: str, *, split_institution: bool) -> list[dict]:
    """One fact per (possibly line-wrapped) record inside a named section, e.g. EDUCATION or
    CERTIFICATIONS. Never invents a field: a record that doesn't match the expected
    "<institution/name> - <program> | <dates/status>" shape is kept as-is, title-only."""
    lines = [ln.strip() for ln in text.splitlines()]
    in_section = False
    buffer = ""
    raw_entries: list[str] = []
    for line in lines:
        header_key = line.strip(":").lower()
        if header_key in header_names:
            in_section = True
            continue
        if not in_section:
            continue
        if header_key in _SECTION_HEADERS and header_key not in header_names:
            if buffer:
                raw_entries.append(buffer)
                buffer = ""
            break
        if not line:
            continue
        if buffer and _RECORD_COMPLETE_RE.search(buffer):
            raw_entries.append(buffer)
            buffer = line
        elif buffer:
            buffer = f"{buffer} {line}"
        else:
            buffer = line
    if buffer:
        raw_entries.append(buffer)

    out = []
    for raw in raw_entries[:8]:
        rest, status = raw, None
        if "|" in rest:
            rest, status = (p.strip() for p in rest.rsplit("|", 1))
        details: dict = {}
        if status:
            details["end"] = status
        title = rest
        if split_institution and " - " in rest:
            institution, program = (p.strip() for p in rest.split(" - ", 1))
            details["institution"] = institution
            title = program
        out.append({"kind": kind, "title": title[:500] or raw[:500], "details": details})
    return out


_STATED = re.compile(r"must|required|requirement|essential|mandatory|you have|you need|need to have", re.IGNORECASE)
_REQ_HEADER = re.compile(r"requirements|qualifications|what you.ll need|what we.re looking for|you have", re.IGNORECASE)
_PREF_SPLIT = re.compile(r"nice to have|preferred|bonus|a plus", re.IGNORECASE)

# What a "N years ..." phrase is about, so scoring never treats a skill- or domain-specific years figure
# as if it were total career duration (matching.py does the actual duration/relevance gating - this just
# tags each years requirement with its subject, or None for a genuinely generic figure).
_GENERIC_YEARS_TERMS = ("total", "overall", "hands-on", "hands on", "relevant", "industry",
                        "professional", "work", "software engineering", "software development")
_GENERIC_YEARS_PHRASE = re.compile(
    r"^\s*(?:of\s+)?(?:(?:" + "|".join(re.escape(t) for t in _GENERIC_YEARS_TERMS) + r")\s+)*experience\b",
    re.IGNORECASE,
)
_YEARS_SUBJECT_PHRASE = re.compile(
    r"^\s*(?:of\s+|in\s+|with\s+|working\s+in\s+)?([a-z][a-z0-9\s/&+.#-]{1,40}?)(?:\s+experience\b)?[.,;\n]",
    re.IGNORECASE,
)


def _years_subject(text: str, end: int) -> str | None:
    """What a "N years ..." phrase is about: a known skill, a short domain phrase, or None (generic).
    Checked in order: clearly generic boilerplate immediately after "N years" ("of professional
    experience") is recognized FIRST and wins outright - a skill mentioned later in the same sentence
    ("...experience building REST API services") is what the work would involve, not what the years
    figure measures, and must never override an already-generic reading. Only once the phrase isn't
    generic does an actual KNOWN_SKILLS token nearby win (most specific, most confident); otherwise
    fall back to whatever short phrase follows, e.g. "financial services" from "in financial services."
    A years figure this can't confidently parse defaults to generic rather than specific, since wrongly
    treating a specific figure as generic (over-crediting) is the failure mode this whole mechanism
    exists to prevent."""
    window = text[end:end + 60]
    if _GENERIC_YEARS_PHRASE.match(window):
        return None
    for skill in KNOWN_SKILLS:
        if re.search(r"(?<![a-z])" + re.escape(skill) + r"(?![a-z])", window, re.IGNORECASE):
            return skill
    m = _YEARS_SUBJECT_PHRASE.match(window)
    return m.group(1).strip().lower() if m else None


def _sentence(text: str, needle: str) -> str | None:
    m = re.search(r"(?<![a-z])" + re.escape(needle) + r"(?![a-z])", text, re.IGNORECASE)
    if not m:
        return None
    start = max(text.rfind(".", 0, m.start()), text.rfind("\n", 0, m.start())) + 1
    ends = [i for i in (text.find(".", m.end()), text.find("\n", m.end())) if i != -1]
    return text[start:(min(ends) + 1 if ends else len(text))].strip()[:300]


def _stub_requirements(title: str, text: str) -> list[dict]:
    """Offline stand-in for job_requirements.v2. Reads only the posting (pass 1 of the two-pass rule)."""
    parts = _PREF_SPLIT.split(text, maxsplit=1)
    required_text = parts[0]
    header = _REQ_HEADER.search(required_text)
    section_start = header.start() if header else None
    reqs: list[dict] = []
    for skill in _find_skills(title):
        reqs.append({"kind": "required_skill", "text": skill, "normalized": skill, "importance": "critical",
                     "evidence_tier": "stated", "jd_signal": title})
    seen = {r["text"] for r in reqs}
    for skill in _find_skills(required_text):
        if skill in seen:
            continue
        quote = _sentence(required_text, skill)
        pos = required_text.lower().find(skill)
        if quote and _STATED.search(quote):
            imp, tier = "high", "stated"
        elif section_start is not None and pos > section_start:
            imp, tier = "high", "structural"
        else:
            imp, tier, quote = "meaningful", "inferred", None
        reqs.append({"kind": "required_skill", "text": skill, "normalized": skill,
                     "importance": imp, "evidence_tier": tier, "jd_signal": quote})
        seen.add(skill)
    if len(parts) > 1:
        for skill in _find_skills(parts[1]):
            if skill not in seen:
                reqs.append({"kind": "preferred_skill", "text": skill, "normalized": skill,
                             "importance": "preferred", "evidence_tier": "structural",
                             "jd_signal": _sentence(text[len(required_text):], skill)})
                seen.add(skill)
    years = re.search(r"(\d+)\+?\s+years", text)
    if years:
        reqs.append({"kind": "experience", "text": years.group(0), "normalized": _years_subject(text, years.end()),
                     "min_years": float(years.group(1)),
                     "importance": "high", "evidence_tier": "stated", "jd_signal": _sentence(text, years.group(0))})
    return reqs


class StubAI:
    model_id = "stub-v1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        dims = get_settings().embedding_dims
        return [_stub_vector(t, dims) for t in texts]

    def complete_json(self, prompt_name: str, fast: bool = False, **variables: str) -> tuple[dict, str]:
        base = prompt_name.split(".")[0]
        if base == "resume_extract":
            text = variables.get("resume_text", "")
            skills = [{"kind": "skill", "title": s, "details": {}} for s in _find_skills(text)]
            education = _extract_section_records(text, {"education"}, "education", split_institution=True)
            certifications = _extract_section_records(text, {"certifications"}, "certification",
                                                       split_institution=False)
            return {"facts": skills + _extract_roles(text) + education + certifications}, self.model_id
        if base == "job_requirements":
            return {"requirements": _stub_requirements(variables.get("job_title", ""),
                                                       variables.get("job_description", ""))}, self.model_id
        if base == "match_explanation":
            b = json.loads(variables.get("breakdown_json", "{}"))
            reqs = b.get("requirements", [])
            matched = [r for r in reqs if r["status"] == "matched" and r.get("fact_title")]
            gaps = [r for r in reqs if r["status"] != "matched"]
            # Neutral language only, keyed off the same percentage the UI shows - RoleWise supports the
            # user's decision rather than labeling a job "worth applying" or "not recommended" for them.
            score = b.get("score", 0)
            alignment = "Strong alignment" if score >= 75 else "Moderate alignment" if score >= 50 else "Limited alignment"
            summary = f"{alignment} ({score:.0f}%). You match {len(matched)} of {len(reqs)} requirements."
            for stop in b.get("hard_stops", []):
                summary = f"{stop['message']} The posting says: \"{stop['quote']}\". " + summary
            return {
                "summary": summary,
                "strengths": [f"{r['text']} ({r['importance']}): verified as {r['fact_title']}" for r in matched[:5]],
                "gaps": [f"{r['text']} ({r['importance']}) is {r['status']}" for r in gaps[:5]],
                "resume_tips": [],
            }, self.model_id
        if base == "resume_tailor":
            return _stub_resume(variables), self.model_id
        if base == "cover_letter":
            return _stub_cover(variables), self.model_id
        raise ValueError(f"StubAI has no handler for prompt {prompt_name}")


@lru_cache
def get_ai() -> AI:
    return BedrockAI() if get_settings().bedrock_enabled else StubAI()


# --------------------------------------------------------------------------- stub documents
# Offline stand-ins for resume_tailor.v1 and cover_letter.v1. They only select and reorder verified facts,
# so local demos show the real flow. Bedrock does the actual rewording into the job's vocabulary.


def _stub_inputs(v: dict) -> tuple[list[dict], list[dict], str]:
    facts = json.loads(v.get("facts_json") or "[]")
    reqs = json.loads(v.get("requirements_json") or "[]")
    return facts, reqs, v.get("job_description", "").lower()


def _relevance(text: str, job: str) -> int:
    return sum(1 for s in _find_skills(text) if s in job) + sum(1 for w in set(_tokens(text)) if len(w) > 4 and w in job)


def _ordered_skills(facts: list[dict], reqs: list[dict]) -> list[dict]:
    skills = [f for f in facts if f["kind"] == "skill"]
    wanted = [r["text"].lower() for r in reqs]
    return sorted(skills, key=lambda f: wanted.index(f["title"].lower()) if f["title"].lower() in wanted else 99)


def _roles(facts: list[dict]) -> list[dict]:
    roles = [f for f in facts if f["kind"] == "role"]
    return sorted(roles, key=lambda f: parse_role_end_date(f["details"].get("end")), reverse=True)


def _display_role_title(title: str) -> str:
    """A role fact's title can be the full extracted header line ("State Street, Boston, MA | Risk
    Data Management Analyst"), not just the job title - _extract_roles() stores it that way because
    there's no separate structured company field. That's fine as a resume section heading, but
    dropped verbatim into a sentence built for a title alone ("I currently work as ...") it reads as
    broken grammar. When the title has that " | " separator, only the part after the LAST one (the
    job title, per how _extract_roles builds it) belongs in a sentence; a title with no separator is
    already just a title and is returned unchanged. Still the same verified fact's own text - nothing
    invented, just not narrating the parts that were never meant to be read as one clause."""
    return title.rsplit(" | ", 1)[-1].strip() if " | " in title else title


# Bullet ceilings by role recency rank - mirrors documents.ROLE_BULLET_CAPS, kept as a separate constant
# here since ai.py (the stub) and documents.py (the assembler/backstop) intentionally don't import from
# each other, so both sides of the offline path agree on the same tiers without a circular import.
_STUB_ROLE_BULLET_CAPS = [5, 4]
_STUB_ROLE_BULLET_CAP_OLDER = 2
# A resume with only 1-2 skills looks sparse even when relevance filtering correctly favored quality over
# volume - this is a floor on the stub's OWN proposed list, topped up with more verified skills only when
# too few relevant ones exist. It is not "list every verified skill."
_STUB_MIN_SKILLS = 5


def _stub_resume(v: dict) -> dict:
    facts, reqs, job = _stub_inputs(v)
    skills, roles = _ordered_skills(facts, reqs), _roles(facts)
    matched = [s for s in skills if s["title"].lower() in {r["text"].lower() for r in reqs}]
    summary = []
    if roles:
        years = sum(float(r["details"].get("years") or 0) for r in roles)
        yrs = f" with {int(years) if years.is_integer() else years} years of experience" if years else ""
        summary.append({"text": f"{_display_role_title(roles[0]['title'])}{yrs}.", "fact_ids": [r["id"] for r in roles]})
    if matched:
        names = [s["title"] for s in matched[:3]]
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        summary.append({"text": f"Hands-on experience with {joined}, the core skills this role asks for.",
                        "fact_ids": [s["id"] for s in matched[:3]]})
    exp = []
    for rank, r in enumerate(roles):
        cap = _STUB_ROLE_BULLET_CAPS[rank] if rank < len(_STUB_ROLE_BULLET_CAPS) else _STUB_ROLE_BULLET_CAP_OLDER
        hl = sorted(r["details"].get("highlights") or [], key=lambda h: _relevance(h, job), reverse=True)
        exp.append({"fact_id": r["id"], "bullets": [{"text": h, "fact_ids": [r["id"]]} for h in hl[:cap]]})
    projects = sorted([f for f in facts if f["kind"] == "project"],
                      key=lambda f: _relevance(f["title"] + " " + " ".join(f["details"].get("highlights") or []), job),
                      reverse=True)
    # Job-relevant skills first (matched requirements, then anything else the job text mentions); only top
    # up with the rest of the candidate's verified skills if that leaves the list too sparse to look complete.
    relevant = [s for s in skills if s in matched or _relevance(s["title"], job) > 0]
    seen_skill_ids = {s["id"] for s in relevant}
    skills_out = list(relevant)
    for s in skills:
        if len(skills_out) >= _STUB_MIN_SKILLS:
            break
        if s["id"] not in seen_skill_ids:
            skills_out.append(s)
            seen_skill_ids.add(s["id"])
    return {
        "summary": summary,
        "competencies": [{"text": s["title"], "fact_ids": [s["id"]]} for s in matched[:8]],
        "experience": exp,
        "projects": [{"fact_id": p["id"], "bullets": [{"text": h, "fact_ids": [p["id"]]}
                                                      for h in (p["details"].get("highlights") or [])[:3]]}
                     for p in projects[:3]],
        "achievements": [{"text": a["title"], "fact_ids": [a["id"]]} for a in facts if a["kind"] == "achievement"][:3],
        "education": [f["id"] for f in facts if f["kind"] == "education"],
        "certifications": [f["id"] for f in facts if f["kind"] == "certification"],
        "skills": [{"text": s["title"], "fact_ids": [s["id"]]} for s in skills_out],
    }


def _stub_cover(v: dict) -> dict:
    facts, reqs, job = _stub_inputs(v)
    skills, roles = _ordered_skills(facts, reqs), _roles(facts)
    matched = [s for s in skills if s["title"].lower() in {r["text"].lower() for r in reqs}][:3]
    names = [s["title"] for s in matched]
    joined = (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]) if names else ""
    title, company = v.get("job_title", "this"), v.get("company", "your team")
    role = roles[0] if roles else None
    opening_ids = ([role["id"]] if role else []) + [s["id"] for s in matched]
    opening = f"I am applying for the {title} role at {company}."
    if role:
        opening += f" I currently work as {_display_role_title(role['title'])}" + (f", using {joined} every day." if joined else ".")
    years = sum(float(r["details"].get("years") or 0) for r in roles)
    profile = None
    if roles and years:
        y = int(years) if years.is_integer() else years
        profile = {"text": f"I bring {y} years of experience, most recently as {_display_role_title(role['title'])}.",
                   "fact_ids": [r["id"] for r in roles]}
    candidates = [(h, r["id"]) for r in roles for h in (r["details"].get("highlights") or [])]
    candidates += [(a["title"], a["id"]) for a in facts if a["kind"] == "achievement"]
    candidates.sort(key=lambda c: (bool(re.search(r"\d", c[0])), _relevance(c[0], job)), reverse=True)

    # Narrative, not a bullet list: the strongest achievements become connected sentences grouped into up
    # to 2 paragraphs, each still traceable to exactly the fact(s) it came from.
    _LEAD_INS = ["", "I also ", "More recently, ", "Beyond that, "]
    narrative = []
    for i, (h, fid) in enumerate(candidates[:4]):
        prefix = _LEAD_INS[i] if i < len(_LEAD_INS) else ""
        sentence = h[0].lower() + h[1:] if prefix and h else h
        sentence = f"{prefix}{sentence}".strip()
        if sentence and not sentence.endswith((".", "!", "?")):
            sentence += "."
        narrative.append({"text": sentence, "fact_ids": [fid], "para": 1 if i < 2 else 2})

    # Quote a stated requirement the candidate actually meets, so the letter talks about real strengths.
    stated = next((r for r in reqs if r.get("evidence_tier") == "stated" and r.get("jd_signal")
                   and r.get("status") == "matched"), None)
    problems = {"text": f"Your posting says: \"{stated['jd_signal']}\" That is the work I want to take on first."
                if stated else f"I would focus first on the problems this role owns at {company}.",
                "fact_ids": [], "jd_quotes": [stated["jd_signal"]] if stated else []}
    return {
        "opening": {"text": opening, "fact_ids": opening_ids},
        "profile": profile,
        "narrative": narrative,
        "problems": problems,
        "closing": {"text": f"I would welcome a conversation about how I can help {company}.", "fact_ids": []},
    }
