"""Deterministic job signals, modeled on career-ops (github.com/santifer/career-ops).

Pure functions, no LLM. They read the job's own text and structured fields and return labels plus the
verbatim evidence behind each label, so every filter and flag can be audited.

- Keyword matching with word boundaries (career-ops title-keywords.mjs): "java" never matches "JavaScript".
- Seniority tiers (career-ops classify-tier.mjs): intern, entry, mid, senior. Plain titles default to mid.
- Work authorization (career-ops oferta.md Block A): sponsors, not_needed, unstated, no_sponsorship.
  Only no_sponsorship is a hard stop. Silence is neutral.
- Geo mismatch (career-ops oferta.md Block A): the job is listed as remote but the text requires office
  attendance. Always quoted verbatim, never paraphrased.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------- keyword matching

_WORD_RE = re.compile(r"[a-z0-9+#.]+")


def compile_keyword(keyword: str) -> re.Pattern[str]:
    """Case-insensitive match on word boundaries. Works for 'c++', '.net', 'power bi' too."""
    kw = re.escape(keyword.strip().lower())
    return re.compile(rf"(?<![a-z0-9]){kw}(?![a-z0-9])", re.IGNORECASE)


def find_keyword(keyword: str, text: str) -> str | None:
    """Return the sentence containing the keyword (verbatim), or None."""
    if not keyword.strip():
        return None
    m = compile_keyword(keyword).search(text)
    return _sentence_at(text, m.start()) if m else None


def _sentence_at(text: str, pos: int) -> str:
    start = max(text.rfind(".", 0, pos), text.rfind("\n", 0, pos)) + 1
    ends = [i for i in (text.find(".", pos), text.find("\n", pos)) if i != -1]
    end = min(ends) + 1 if ends else len(text)
    return text[start:end].strip()[:300]


# --------------------------------------------------------------------------- titles and seniority

TIERS = ["intern", "entry", "mid", "senior"]

# (pattern, tier, weight). Higher weight wins when a title has several signals ("Senior Intern" -> intern).
_TIER_RULES: list[tuple[str, str, int]] = [
    (r"intern(ship)?|co-?op|trainee|apprentice", "intern", 5),
    (r"junior|jr\.?|entry[- ]level|graduate|new grad|associate", "entry", 4),
    (r"senior|sr\.?|staff|principal|lead|head of|director|vp|vice president|chief", "senior", 3),
    (r"ii|level 2|mid[- ]level", "mid", 2),
    (r"iii|iv|level [34]", "senior", 2),
    (r"i|level 1", "entry", 1),
]


def classify_tier(title: str) -> str:
    low = title.lower()
    best, best_w = "mid", 0
    for pattern, tier, weight in _TIER_RULES:
        if re.search(rf"(?<![a-z]){pattern}(?![a-z])", low) and weight > best_w:
            best, best_w = tier, weight
    return best


def candidate_tier(stated: str | None, total_years: float) -> str:
    """The user's own stated level wins. Otherwise infer from verified years of experience."""
    if stated and stated.lower() in TIERS:
        return stated.lower()
    if total_years < 1:
        return "entry"
    if total_years < 5:
        return "mid"
    return "senior"


_TITLE_STOPWORDS = {"senior", "staff", "principal", "lead", "junior", "jr", "sr", "i", "ii", "iii", "iv", "of", "and"}
# Common role-noun variants so "Engineering" and "Engineer" count as the same word.
_TITLE_SYNONYMS = {
    "engineering": "engineer", "engineers": "engineer",
    "analytics": "analyst", "analysis": "analyst", "analysts": "analyst",
    "science": "scientist", "scientists": "scientist",
    "development": "developer", "developers": "developer",
}


def title_words(title: str) -> set[str]:
    return set(re.findall(r"[a-z]+", title.lower())) - _TITLE_STOPWORDS


def _title_words_ordered(title: str) -> list[str]:
    words = [w for w in re.findall(r"[a-z]+", title.lower()) if w not in _TITLE_STOPWORDS]
    return [_TITLE_SYNONYMS.get(w, w) for w in words]


def title_overlap(job_title: str, target: str) -> float:
    """1.0 when every distinctive word of the target is in the job title, else the share that is.
    Lenient by design: used only for the soft archetype-fit score bonus, never to hide a job."""
    t = title_words(target)
    if not t:
        return 0.0
    return len(t & title_words(job_title)) / len(t)


def title_phrase_match(job_title: str, target: str) -> bool:
    """True when the target's words appear in the job title as a contiguous, ordered phrase (seniority
    words like "Senior" or "II" may appear elsewhere but not inside the phrase). Stricter than
    title_overlap on purpose: this backs the hard "only show these roles" filter, where scattered-word
    matches like "Data Engineer" -> "Data Analytics & Engineering" would silently defeat the filter."""
    t = _title_words_ordered(target)
    if not t:
        return False
    j = _title_words_ordered(job_title)
    n = len(t)
    return any(j[i:i + n] == t for i in range(len(j) - n + 1))


def title_filter(job_title: str, positive: list[str], negative: list[str]) -> str | None:
    """Return a rejection reason, or None when the title passes. Missing positives means 'allow all'."""
    for kw in negative:
        if kw.strip() and compile_keyword(kw).search(job_title):
            return f"title contains excluded keyword '{kw.strip()}'"
    if positive and not any(title_phrase_match(job_title, t) for t in positive if t.strip()):
        return "title does not match your target roles"
    return None


# --------------------------------------------------------------------------- work authorization

_COUNTRIES: dict[str, list[str]] = {
    "United States": ["united states", "usa", "u.s.", "us", "remote, us", "remote - us"],
    "Canada": ["canada", "toronto", "vancouver", "montreal"],
    "United Kingdom": ["united kingdom", "uk", "england", "london"],
    "India": ["india", "bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi", "chennai"],
    "Germany": ["germany", "berlin", "munich"],
    "Ireland": ["ireland", "dublin"],
    "Netherlands": ["netherlands", "amsterdam"],
    "France": ["france", "paris"],
    "Spain": ["spain", "madrid", "barcelona"],
    "Australia": ["australia", "sydney", "melbourne"],
    "Singapore": ["singapore"],
    "Japan": ["japan", "tokyo"],
    "Brazil": ["brazil", "sao paulo", "são paulo"],
    "Mexico": ["mexico"],
}
_US_STATES = ["al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc"]
_US_CITIES = ["new york", "san francisco", "seattle", "austin", "boston", "chicago", "los angeles", "denver",
              "atlanta", "washington", "miami", "dallas", "san jose", "portland", "philadelphia"]


def job_country(location: str | None) -> str | None:
    if not location:
        return None
    low = location.lower()
    for country, words in _COUNTRIES.items():
        if any(compile_keyword(w).search(low) for w in words):
            return country
    if any(c in low for c in _US_CITIES) or re.search(r",\s*(" + "|".join(_US_STATES) + r")\b", low):
        return "United States"
    return None


_NO_SPONSOR = re.compile(
    r"(no|not|unable to|cannot|can't|will not|won't|do not|does not)\s+(provide\s+|offer\s+)?"
    r"(visa\s+)?sponsor(ship)?"
    r"|without\s+(the\s+need\s+for\s+)?(visa\s+)?sponsorship"
    r"|sponsorship\s+(is\s+)?not\s+(available|offered|provided)",
    re.IGNORECASE,
)
_SPONSORS = re.compile(
    r"(visa|relocation)\s+(sponsorship|support|assistance)\s+(is\s+)?(available|provided|offered)"
    r"|we\s+(will\s+|can\s+|do\s+)?sponsor"
    r"|sponsorship\s+(is\s+)?available",
    re.IGNORECASE,
)


@dataclass
class WorkAuth:
    tier: str  # sponsors | not_needed | unstated | no_sponsorship
    quote: str | None
    country: str | None


def work_authorization(
    location: str | None, remote_mode: str | None, description: str,
    authorized_in: list[str], needs_sponsorship: bool | None,
) -> WorkAuth:
    country = job_country(location)
    no = _NO_SPONSOR.search(description)
    yes = _SPONSORS.search(description)
    quote = _sentence_at(description, (no or yes).start()) if (no or yes) else None
    authorized = {a.strip().lower() for a in authorized_in}

    if needs_sponsorship is False:
        return WorkAuth("not_needed", quote, country)
    if country and country.lower() in authorized:
        return WorkAuth("not_needed", quote, country)
    if country is None and remote_mode == "remote":
        # Location-agnostic remote: the candidate can work from a country they're authorized in.
        return WorkAuth("not_needed" if authorized else "unstated", quote, None)
    if no and not yes:
        # Only a hard stop when we know the role is outside the candidate's authorized countries.
        if country and authorized:
            return WorkAuth("no_sponsorship", quote, country)
        return WorkAuth("unstated", quote, country)
    if yes:
        return WorkAuth("sponsors", quote, country)
    return WorkAuth("unstated", None, country)


# --------------------------------------------------------------------------- geo mismatch

_ATTENDANCE = re.compile(
    r"\bhybrid\b|\b\d\s*(\+\s*)?days?\s+(a|per)\s+(week|month)\s+(in|at)\s+(the\s+|our\s+)?office"
    r"|\b(in|at)\s+(the\s+|our\s+)?office\s+\d\s*(\+\s*)?days?"
    r"|\bin[- ]office\b|\bon[- ]?site\b|\brelocat(e|ion)\s+(to|is required)|must\s+be\s+located\s+(in|near)",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(no|not|without|optional|occasional|quarterly|annual|offsites?)\b", re.IGNORECASE
)


def geo_mismatch(remote_mode: str | None, description: str) -> str | None:
    """If the structured field says remote but the text requires attendance, return the verbatim line."""
    if remote_mode != "remote":
        return None
    for m in _ATTENDANCE.finditer(description):
        sentence = _sentence_at(description, m.start())
        if not _NEGATION.search(sentence):
            return sentence
    return None
