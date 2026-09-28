"""Tailored resume and cover letter assembly, with a deterministic fact check.

Modeled on career-ops (github.com/santifer/career-ops) modes/pdf.md, modes/cover.md and verify-cv-facts.mjs:
reword real experience into the job's vocabulary, never fabricate, fact-check every line before export.

Invariant 1 (CLAUDE.md): generated content may only make claims backed by verified career facts.
The LLM proposes lines with fact ids. This module keeps a line only when:
  - it cites at least one fact id, and every cited id is a verified fact of this user,
  - every number in it appears in the cited facts (or is the sum of cited role years),
  - every skill or requirement term it names appears in the cited facts.
Headers for roles, education and certifications are rendered from the facts themselves, never from LLM text,
so titles, employers and dates cannot be inflated.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from rolewise.services.ai import KNOWN_SKILLS, parse_role_date, parse_role_end_date
from rolewise.services.signals import compile_keyword

ALIASES = {
    "k8s": "kubernetes", "postgres": "postgresql", "js": "javascript", "ts": "typescript",
    "golang": "go", "gcp": "google cloud", "ml": "machine learning", "tf": "terraform",
}
INFLATION_VERBS = re.compile(r"\b(led|lead|managed|founded|built|created|architected|owned|launched|authored)\b",
                             re.IGNORECASE)
BANNED_PHRASES = [
    "i am writing to", "i am pleased to", "i am excited to", "passionate", "synergy", "holistic", "championed",
    "orchestrated", "excited", "data-driven", "actionable insights", "move the needle", "north star",
    "unique opportunity", "perfect fit", "strong track record", "results-driven", "go-getter",
]
_NUM_RE = re.compile(r"(?<![a-z])\$?\d[\d,]*(?:\.\d+)?%?[kKmMbB+]?")

# A candidate's first-person claim of possessing something ("I have Spark experience") must be backed by
# a cited fact just like any other claim - but this only fires on possession language, so a paragraph can
# still legitimately NAME a company's need ("Your team needs Spark") without being flagged.
_POSSESSION_RE = re.compile(
    r"\b(?:i have|i bring|i possess|i know|i'm|i am (?:skilled|proficient|experienced|well-versed) in|"
    r"my experience (?:with|in))\b", re.IGNORECASE)

# Bullet ceilings by role recency rank (index 0 = most recent role after reverse-chronological sort).
# These are ceilings, never floors - a role with fewer verified highlights than its cap simply shows fewer.
ROLE_BULLET_CAPS = [5, 4]  # index 0 -> 5, index 1 -> 4, index 2+ -> ROLE_BULLET_CAP_OLDER
ROLE_BULLET_CAP_OLDER = 2

# A resume with only 1-2 skills looks sparse even when the model correctly favored relevance over volume -
# this is a floor on the FINAL skills section, only topped up with facts the model didn't already list, and
# only ever with job-relevant ones. It is not a "list every verified skill" backfill.
MIN_RESUME_SKILLS = 5


def _role_bullet_cap(rank: int) -> int:
    return ROLE_BULLET_CAPS[rank] if rank < len(ROLE_BULLET_CAPS) else ROLE_BULLET_CAP_OLDER


@dataclass
class Fact:
    id: str
    kind: str
    title: str
    details: dict

    @property
    def text(self) -> str:
        return f"{self.title}\n{json.dumps(self.details, ensure_ascii=False)}".lower()


@dataclass
class Check:
    kept: list[dict] = field(default_factory=list)  # {"section", "text", "fact_ids"}
    removed: list[dict] = field(default_factory=list)  # {"section", "text", "reason"}
    warnings: list[str] = field(default_factory=list)


def _canon(term: str) -> str:
    t = term.strip().lower()
    return ALIASES.get(t, t)


def _numbers(text: str) -> set[str]:
    out = set()
    for n in _NUM_RE.findall(text):
        n = n.strip("$+").rstrip("kKmMbB").rstrip("%").replace(",", "")
        if n:
            out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out


def fact_catalog(facts: list[Fact]) -> str:
    """What the LLM sees: ids, kinds, titles, details. Nothing else about the candidate."""
    return json.dumps([{"id": f.id, "kind": f.kind, "title": f.title, "details": f.details} for f in facts],
                      ensure_ascii=False, indent=1)


class FactChecker:
    def __init__(self, facts: list[Fact], job_terms: list[str], job_text: str, names: str = ""):
        self.facts = {f.id: f for f in facts}
        # Terms the checker watches for: the skill vocabulary plus this job's own requirement terms.
        # Ambiguous words ("go") and anything with digits ("3 years") are not skill names.
        self.terms = sorted({_canon(t) for t in [*KNOWN_SKILLS, *job_terms]
                             if len(t.strip()) > 1 and not re.search(r"\d", t) and t.strip().lower() not in {"go"}},
                            key=len, reverse=True)
        self.job_numbers = _numbers(job_text)
        self.name_numbers = _numbers(names)  # digits in the job title or company name are never claims
        # A skill-like word that happens to appear IN the job title or company name ("Data Engineering
        # Platform") is not a candidate claim just because it's echoed back ("interested in the Data
        # Engineering Platform role") - same reasoning as name_numbers above, but for terms.
        self.name_terms = {t for t in self.terms if compile_keyword(t).search(names.lower())}
        self.check = Check()

    def verify(self, section: str, text: str, fact_ids: list[str], *, require_facts: bool = True,
               check_terms: bool = True, allow_job_numbers: bool = False, guard_possession: bool = False) -> bool:
        text = (text or "").replace(" — ", ", ").replace("—", ", ").strip()
        if not text:
            return False
        ids = [str(i) for i in (fact_ids or [])]
        unknown = [i for i in ids if i not in self.facts]
        if unknown or (require_facts and not ids):
            return self._reject(section, text, "not backed by a verified fact")
        cited = [self.facts[i] for i in ids]
        cited_text = "\n".join(f.text for f in cited)

        allowed = _numbers(cited_text) | self.name_numbers
        role_years = [f.details.get("years") for f in cited if f.kind == "role" and f.details.get("years")]
        if role_years:
            total = sum(float(y) for y in role_years)
            allowed.add(str(int(total)) if total.is_integer() else str(total))
        if allow_job_numbers:
            allowed |= self.job_numbers
        bad_numbers = _numbers(text) - allowed
        if bad_numbers:
            return self._reject(section, text, f"number {min(bad_numbers)} is not in your verified facts")

        # A paragraph exempted from check_terms (so it can legitimately NAME a company's need) must still
        # never let the candidate claim to POSSESS something not in their cited facts - possession language
        # aimed at an unbacked term is exactly the false claim check_terms would catch elsewhere.
        if guard_possession:
            low_text = text.lower()
            for m in _POSSESSION_RE.finditer(low_text):
                window = low_text[m.end(): m.end() + 60]
                for term in self.terms:
                    if compile_keyword(term).search(window):
                        aliases = [a for a, c in ALIASES.items() if c == term]
                        if not any(compile_keyword(t).search(cited_text) for t in [term, *aliases]):
                            return self._reject(section, text, f"claims to have '{term}', which the cited facts don't show")

        if check_terms:
            low = text.lower()
            for term in self.terms:
                m = compile_keyword(term).search(low)
                if m:
                    aliases = [a for a, c in ALIASES.items() if c == term]
                    backed = any(compile_keyword(t).search(cited_text) for t in [term, *aliases])
                    # Echoing the job title/company ("...the Data Engineering Platform role...") is not a
                    # claim - but if possession language leads into this same mention ("I have Data
                    # Engineering experience"), it IS a claim and still needs a cited fact, title or not.
                    if not backed and term in self.name_terms and not _POSSESSION_RE.search(low[:m.start()]):
                        backed = True
                    if not backed:
                        return self._reject(section, text, f"mentions '{term}', which the cited facts don't show")
                    low = compile_keyword(term).sub(" ", low)  # don't re-match parts of a longer term

        verb = INFLATION_VERBS.search(text)
        if verb and verb.group(1).lower() not in cited_text:
            self.check.warnings.append(f"Check the word '{verb.group(1)}' in: \"{text[:90]}\". "
                                       "Your facts don't use it.")
        self.check.kept.append({"section": section, "text": text, "fact_ids": ids})
        return True

    def _reject(self, section: str, text: str, reason: str) -> bool:
        self.check.removed.append({"section": section, "text": text, "reason": reason})
        return False


# --------------------------------------------------------------------------- resume


def _role_header(f: Fact) -> dict:
    d = f.details
    dates = " - ".join(x for x in [str(d.get("start", "")), str(d.get("end", ""))] if x and x != "None")
    if not dates and d.get("years"):
        dates = f"{d['years']} years"
    return {"fact_id": f.id, "title": f.title, "company": d.get("company"), "location": d.get("location"),
            "dates": dates}


def _role_sort_key(f: Fact) -> tuple[int, int, int, int]:
    """Reverse-chronological by actual calendar date (see ai.parse_role_date) - comparing date
    strings directly would sort "Mar 2026" before "Sept 2024" alphabetically, which is wrong.
    Tie-broken by start date; an open-ended role ("present"/no end date) sorts as the most recent."""
    d = f.details
    return (*parse_role_end_date(d.get("end")), *parse_role_date(d.get("start")))


def _is_job_relevant(term: str, job_terms_canon: set[str], job_text_low: str) -> bool:
    canon = _canon(term)
    return canon in job_terms_canon or bool(compile_keyword(canon).search(job_text_low))


def _edu_line(f: Fact) -> str:
    d = f.details
    parts = [f.title, d.get("degree"), d.get("field"), d.get("institution"), d.get("end")]
    seen, out = set(), []
    for p in parts:
        if p and str(p) not in seen:
            seen.add(str(p))
            out.append(str(p))
    return ", ".join(out)


def assemble_resume(raw: dict, facts: list[Fact], contact: dict, job_terms: list[str], job_text: str,
                    headline: str, company: str = "") -> tuple[dict, Check]:
    fc = FactChecker(facts, job_terms, job_text, names=f"{headline} {company}")
    by_id = fc.facts

    def lines(section: str, items) -> list[dict]:
        out = []
        for it in items or []:
            if isinstance(it, dict) and fc.verify(section, it.get("text", ""), it.get("fact_ids", [])):
                out.append({"text": fc.check.kept[-1]["text"], "fact_ids": fc.check.kept[-1]["fact_ids"]})
        return out

    def blocks(section: str, items, kind: str) -> list[dict]:
        out = []
        for it in items or []:
            f = by_id.get(str(it.get("fact_id")))
            if not f or f.kind != kind:
                fc._reject(section, str(it.get("fact_id")), f"not a verified {kind}")
                continue
            bullets = []
            for b in it.get("bullets", []) or []:
                ids = list({str(f.id), *[str(x) for x in b.get("fact_ids", [])]})
                if fc.verify(section, b.get("text", ""), ids):
                    bullets.append({"text": fc.check.kept[-1]["text"], "fact_ids": ids})
            out.append({**_role_header(f), "bullets": bullets})
        return out

    def picked(ids, kind) -> list[dict]:
        return [{"fact_id": by_id[str(i)].id, "text": _edu_line(by_id[str(i)])}
                for i in ids or [] if str(i) in by_id and by_id[str(i)].kind == kind]

    def experience_blocks() -> list[dict]:
        """Every verified role fact appears, in reverse-chronological order, regardless of what the model
        proposed - a role the model left out is still real career history, unlike a line it never cited."""
        proposed: dict[str, list[dict]] = {}
        for it in raw.get("experience") or []:
            f = by_id.get(str(it.get("fact_id")))
            if not f or f.kind != "role":
                fc._reject("experience", str(it.get("fact_id")), "not a verified role")
                continue
            bullets = []
            for b in it.get("bullets", []) or []:
                ids = list({str(f.id), *[str(x) for x in b.get("fact_ids", [])]})
                if fc.verify("experience", b.get("text", ""), ids):
                    bullets.append({"text": fc.check.kept[-1]["text"], "fact_ids": ids})
            proposed[f.id] = bullets
        roles = sorted((f for f in facts if f.kind == "role"), key=_role_sort_key, reverse=True)
        return [{**_role_header(f), "bullets": proposed.get(f.id, [])[:_role_bullet_cap(rank)]}
                for rank, f in enumerate(roles)]

    def skills_with_fallback() -> list[dict]:
        """The model's own selection first (it should already favor job relevance). Only tops up with more
        verified, job-relevant skills - never the full inventory - if the model under-selected."""
        proposed = lines("skills", raw.get("skills"))
        if len(proposed) >= MIN_RESUME_SKILLS:
            return proposed
        listed_ids = {i for s in proposed for i in s["fact_ids"]}
        job_terms_canon = {_canon(t) for t in job_terms}
        job_text_low = (job_text or "").lower()
        for f in facts:
            if len(proposed) >= MIN_RESUME_SKILLS:
                break
            if f.kind == "skill" and f.id not in listed_ids and _is_job_relevant(f.title, job_terms_canon, job_text_low):
                proposed.append({"text": f.title, "fact_ids": [f.id]})
                listed_ids.add(f.id)
        return proposed

    content = {
        "header": {"full_name": contact.get("full_name") or "", "headline": headline,
                   "contact": [x for x in [contact.get("location"), contact.get("email"), contact.get("phone"),
                                           *(contact.get("links") or [])] if x]},
        "summary": lines("summary", raw.get("summary")),
        "competencies": lines("competencies", raw.get("competencies"))[:8],
        "experience": experience_blocks(),
        "projects": blocks("projects", raw.get("projects"), "project")[:3],
        "achievements": lines("achievements", raw.get("achievements"))[:3],
        "education": picked(raw.get("education"), "education"),
        "certifications": picked(raw.get("certifications"), "certification"),
        "skills": skills_with_fallback(),
    }
    # Anything verified but left out by the model is still true. Education and certifications are always kept.
    listed = {e["fact_id"] for e in content["education"] + content["certifications"]}
    for f in facts:
        if f.kind in ("education", "certification") and f.id not in listed:
            content["education" if f.kind == "education" else "certifications"].append(
                {"fact_id": f.id, "text": _edu_line(f)})
    return content, fc.check


# --------------------------------------------------------------------------- cover letter


def assemble_cover_letter(raw: dict, facts: list[Fact], contact: dict, job_terms: list[str], job_text: str,
                          job_title: str, company: str) -> tuple[dict, Check]:
    fc = FactChecker(facts, job_terms, job_text, names=f"{job_title} {company}")

    def para(section: str, item: dict | None, **kw) -> dict | None:
        if item and fc.verify(section, item.get("text", ""), item.get("fact_ids", []), **kw):
            return {"text": fc.check.kept[-1]["text"], "fact_ids": fc.check.kept[-1]["fact_ids"]}
        return None

    # Narrative: 1-2 flowing paragraphs, not a bullet dump. Each sentence is fact-checked independently
    # (like the old bullets were) so a single unsupported sentence drops without breaking the paragraph;
    # sentences are then joined into prose by their "para" tag instead of rendered as a list.
    narrative_paras: dict[int, list[str]] = {1: [], 2: []}
    for item in raw.get("narrative", []) or []:
        para_num = item.get("para")
        para_num = 1 if para_num not in (1, 2) else para_num
        text = str(item.get("text", "")).replace("—", ",")
        if fc.verify("narrative", text, item.get("fact_ids", [])):
            narrative_paras[para_num].append(fc.check.kept[-1]["text"])
    narrative = [" ".join(narrative_paras[n]) for n in (1, 2) if narrative_paras[n]]

    problems = raw.get("problems") or {}
    quotes = [q for q in problems.get("jd_quotes", []) or [] if q and q.strip() in job_text]
    content = {
        "header": {"full_name": contact.get("full_name") or "",
                   "contact": [x for x in [contact.get("location"), contact.get("email"), contact.get("phone"),
                                           *(contact.get("links") or [])] if x]},
        "title": f"Cover Letter: {job_title}",
        "company": company,
        "date": datetime.now(UTC).date().isoformat(),
        "salutation": f"Dear {company} hiring team,",
        "opening": para("opening", raw.get("opening")),
        "profile": para("profile", raw.get("profile")),
        "narrative": narrative,
        # The problems paragraph talks about the company's needs, so job terms and numbers are allowed there -
        # but guard_possession still blocks it from claiming the candidate HAS something not in their facts.
        "problems": para("problems", problems, require_facts=False, check_terms=False, allow_job_numbers=True,
                         guard_possession=True),
        "closing": para("closing", raw.get("closing"), require_facts=False),
        "jd_quotes": quotes,
    }
    body = " ".join(filter(None, [
        (content["opening"] or {}).get("text"), (content["profile"] or {}).get("text"),
        *content["narrative"],
        (content["problems"] or {}).get("text"), (content["closing"] or {}).get("text"),
    ]))
    words = len(body.split())
    content["word_count"] = words
    if not 300 <= words <= 450:
        fc.check.warnings.append(f"The letter is {words} words. Aim for 350-420.")
    low = body.lower()
    for phrase in BANNED_PHRASES:
        if phrase in low:
            fc.check.warnings.append(f"Consider rewording '{phrase}'. It reads as filler.")
    return content, fc.check


# --------------------------------------------------------------------------- coverage


def keyword_coverage(requirements: list[dict], text: str) -> list[dict]:
    """Which high-importance requirements the finished document actually shows, and why the rest don't."""
    out = []
    low = text.lower()
    for r in requirements:
        if r.get("importance") not in ("critical", "high", "meaningful") or r.get("kind") == "experience":
            continue
        term = r.get("text", "")
        shown = bool(compile_keyword(term).search(low)) if term else False
        if shown:
            state = "shown"
        elif r.get("status") == "missing":
            state = "not_in_profile"  # honest gap, deliberately not added
        else:
            state = "could_add"
        out.append({"text": term, "importance": r.get("importance"), "status": r.get("status"), "state": state})
    return out


# --------------------------------------------------------------------------- rendering


def resume_plain_text(c: dict) -> str:
    parts = [c["header"]["full_name"], c["header"]["headline"], " | ".join(c["header"]["contact"])]
    parts += [x["text"] for x in c["summary"] + c["competencies"] + c["achievements"] + c["skills"]]
    for block in c["experience"] + c["projects"]:
        parts += [block["title"], block.get("company") or ""] + [b["text"] for b in block["bullets"]]
    parts += [e["text"] for e in c["education"] + c["certifications"]]
    return "\n".join(p for p in parts if p)


def cover_plain_text(c: dict) -> str:
    parts = [(c.get("opening") or {}).get("text"), (c.get("profile") or {}).get("text")]
    parts += list(c.get("narrative", []))
    parts += [(c.get("problems") or {}).get("text"), (c.get("closing") or {}).get("text")]
    return "\n\n".join(p for p in parts if p)


def to_markdown(kind: str, c: dict) -> str:
    h = c["header"]
    md = [f"# {h['full_name'] or 'Your Name'}"]
    if kind == "resume":
        if h.get("headline"):
            md.append(f"**{h['headline']}**")
        md.append(" | ".join(h["contact"]))
        if c["summary"]:
            md += ["", "## Professional Summary", " ".join(x["text"] for x in c["summary"])]
        if c["competencies"]:
            md += ["", "## Core Competencies", " · ".join(x["text"] for x in c["competencies"])]
        if c["experience"]:
            md += ["", "## Work Experience"]
            for r in c["experience"]:
                sub = " | ".join(x for x in [r.get("company"), r.get("location"), r.get("dates")] if x)
                md += ["", f"### {r['title']}" + (f"  \n{sub}" if sub else "")]
                md += [f"- {b['text']}" for b in r["bullets"]]
        if c["projects"]:
            md += ["", "## Projects"]
            for p in c["projects"]:
                md += ["", f"### {p['title']}"] + [f"- {b['text']}" for b in p["bullets"]]
        if c["achievements"]:
            md += ["", "## Achievements"] + [f"- {a['text']}" for a in c["achievements"]]
        if c["education"]:
            md += ["", "## Education"] + [f"- {e['text']}" for e in c["education"]]
        if c["certifications"]:
            md += ["", "## Certifications"] + [f"- {e['text']}" for e in c["certifications"]]
        if c["skills"]:
            md += ["", "## Skills", ", ".join(s["text"] for s in c["skills"])]
    else:
        md += [" | ".join(h["contact"]), "", f"**{c['title']}**  \n{c['company']} · {c['date']}", "",
               c.get("salutation") or "", ""]
        for key in ("opening", "profile"):
            if c.get(key):
                md += [c[key]["text"], ""]
        for p in c.get("narrative", []):
            md += [p, ""]
        for key in ("problems", "closing"):
            if c.get(key):
                md += ["", c[key]["text"]]
        md += ["", h["full_name"] or ""]
    return "\n".join(md).strip() + "\n"


def to_docx(kind: str, c: dict) -> bytes:
    """ATS-friendly single column DOCX: standard headings, no tables, no text boxes."""
    from docx import Document as Docx
    from docx.shared import Pt

    doc = Docx()
    style = doc.styles["Normal"]
    style.font.name, style.font.size = "Calibri", Pt(10.5)
    for line in to_markdown(kind, c).splitlines():
        text = line.rstrip()
        if not text:
            continue
        if text.startswith("# "):
            doc.add_heading(text[2:], level=0)
        elif text.startswith("## "):
            doc.add_heading(text[3:], level=1)
        elif text.startswith("### "):
            doc.add_heading(text[4:].replace("  ", ""), level=2)
        elif text.startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            _runs(p, text[2:])
        else:
            _runs(doc.add_paragraph(), text.rstrip(" "))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _runs(paragraph, text: str) -> None:
    for i, part in enumerate(re.split(r"\*\*", text)):
        if part:
            paragraph.add_run(part).bold = i % 2 == 1
