"""Job source connectors. Only sources whose terms permit automated access belong here.

Greenhouse, Lever and Ashby publish public job-board APIs for employers' career pages.
Do not add scrapers for LinkedIn, Indeed or other sites that forbid automated access.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx


@dataclass
class RawJob:
    external_id: str
    company: str
    title: str
    location: str | None
    description: str
    url: str | None


def content_hash(company: str, title: str, description: str) -> str:
    norm = re.sub(r"\s+", " ", f"{company}|{title}|{description}".lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest()


def strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<(br|/p|/li|/h\d)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def fetch_greenhouse_board(board_token: str, company: str | None = None) -> list[RawJob]:
    """Public Greenhouse Job Board API: https://developers.greenhouse.io/job-board.html"""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    resp = httpx.get(url, params={"content": "true"}, timeout=30)
    resp.raise_for_status()
    jobs = []
    for j in resp.json().get("jobs", []):
        jobs.append(
            RawJob(
                external_id=str(j["id"]),
                company=company or board_token,
                title=j.get("title", ""),
                location=(j.get("location") or {}).get("name"),
                description=strip_html(j.get("content", "")),
                url=j.get("absolute_url"),
            )
        )
    return jobs


def fetch_lever_board(board_token: str, company: str | None = None) -> list[RawJob]:
    """Public Lever postings API: https://github.com/lever/postings-api"""
    url = f"https://api.lever.co/v0/postings/{board_token}"
    resp = httpx.get(url, params={"mode": "json"}, timeout=30)
    resp.raise_for_status()
    jobs = []
    for j in resp.json():
        jobs.append(
            RawJob(
                external_id=str(j["id"]),
                company=company or board_token,
                title=j.get("text", ""),
                location=(j.get("categories") or {}).get("location"),
                description=j.get("descriptionPlain", ""),
                url=j.get("hostedUrl"),
            )
        )
    return jobs


def fetch_ashby_board(board_token: str, company: str | None = None) -> list[RawJob]:
    """Public Ashby job board API: https://developers.ashbyhq.com/reference/jobpostingsync"""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    jobs = []
    for j in resp.json().get("jobs", []):
        jobs.append(
            RawJob(
                external_id=str(j["id"]),
                company=company or board_token,
                title=j.get("title", ""),
                location=j.get("location"),
                description=strip_html(j.get("descriptionHtml", "")),
                url=j.get("jobUrl"),
            )
        )
    return jobs


# --------------------------------------------------------------------------- single job, by URL
# Lets a user paste one job's URL instead of copy-pasting the description by hand. Modeled on
# career-ops's fetch-jd.mjs: fetch via the ATS's own public API, the same one the board connectors
# above use - never by rendering or scraping the page itself. A URL from an unrecognized source is a
# graceful miss (None), not an error - the caller falls back to asking for a pasted description.


def fetch_greenhouse_job(board_token: str, job_id: str) -> RawJob | None:
    resp = httpx.get(f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}", timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    j = resp.json()
    return RawJob(external_id=str(j["id"]), company=j.get("company_name") or board_token,
                 title=j.get("title", ""), location=(j.get("location") or {}).get("name"),
                 description=strip_html(j.get("content", "")), url=j.get("absolute_url"))


def fetch_lever_job(board_token: str, job_id: str) -> RawJob | None:
    resp = httpx.get(f"https://api.lever.co/v0/postings/{board_token}/{job_id}", timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    j = resp.json()
    return RawJob(external_id=str(j["id"]), company=board_token, title=j.get("text", ""),
                 location=(j.get("categories") or {}).get("location"),
                 description=j.get("descriptionPlain", ""), url=j.get("hostedUrl"))


def fetch_ashby_job(board_token: str, job_id: str) -> RawJob | None:
    # Ashby's per-posting endpoint requires auth; only the board-list endpoint is public, so fetch
    # the whole board (the same request board discovery already makes) and pick out the one job.
    return next((j for j in fetch_ashby_board(board_token) if j.external_id == job_id), None)


FETCH_JOB = {"greenhouse": fetch_greenhouse_job, "lever": fetch_lever_job, "ashby": fetch_ashby_job}

_UUID = r"[0-9a-fA-F-]{36}"


def parse_ats_url(url: str) -> tuple[str, str, str] | None:
    """(platform, board_token, job_id) for a URL whose host and path directly name both - the
    standalone-domain case (boards.greenhouse.io, jobs.lever.co, jobs.ashbyhq.com)."""
    try:
        p = urlparse(url)
    except ValueError:
        return None
    host, path = p.netloc.lower(), p.path
    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io"):
        m = re.match(r"^/([\w-]+)/jobs/(\d+)", path)
        if m:
            return "greenhouse", m.group(1), m.group(2)
    elif host == "jobs.lever.co":
        m = re.match(rf"^/([\w-]+)/({_UUID})", path)
        if m:
            return "lever", m.group(1), m.group(2)
    elif host == "jobs.ashbyhq.com":
        m = re.match(rf"^/([\w-]+)/({_UUID})", path)
        if m:
            return "ashby", m.group(1), m.group(2)
    return None


def parse_greenhouse_gh_jid(url: str) -> str | None:
    """Many employers host their Greenhouse board on their own domain (careers.company.com) with
    the job id only in a ?gh_jid= query param - the board token isn't recoverable from the URL
    itself, so the caller must resolve it by trying boards it already knows about."""
    try:
        qs = parse_qs(urlparse(url).query)
    except ValueError:
        return None
    return (qs.get("gh_jid") or [None])[0]


# Real, verified-working public boards to auto-search when a user submits preferences. Allow-listed
# by construction: only Greenhouse/Lever/Ashby, the same ToS-compliant platforms as the manual
# connectors above - never a site whose terms forbid automated access (no LinkedIn, Indeed, or
# scraping arbitrary company career pages). Every token here was checked with a live request before
# being added. Extend this list as more boards are verified the same way.
CURATED_BOARDS: list[tuple[str, str, str]] = [
    ("greenhouse", "airbnb", "Airbnb"),
    ("greenhouse", "stripe", "Stripe"),
    ("greenhouse", "figma", "Figma"),
    ("greenhouse", "coinbase", "Coinbase"),
    ("greenhouse", "pinterest", "Pinterest"),
    ("greenhouse", "anthropic", "Anthropic"),
    ("greenhouse", "databricks", "Databricks"),
    ("greenhouse", "instacart", "Instacart"),
    ("greenhouse", "robinhood", "Robinhood"),
    ("greenhouse", "gitlab", "GitLab"),
    ("greenhouse", "mongodb", "MongoDB"),
    ("greenhouse", "elastic", "Elastic"),
    ("greenhouse", "datadog", "Datadog"),
    ("greenhouse", "twilio", "Twilio"),
    ("greenhouse", "cloudflare", "Cloudflare"),
    ("greenhouse", "okta", "Okta"),
    ("greenhouse", "dropbox", "Dropbox"),
    ("greenhouse", "squarespace", "Squarespace"),
    ("greenhouse", "asana", "Asana"),
    ("lever", "palantir", "Palantir"),
    ("ashby", "Ramp", "Ramp"),
    ("ashby", "Notion", "Notion"),
    ("ashby", "Linear", "Linear"),
    ("ashby", "Replit", "Replit"),
    ("ashby", "Perplexity", "Perplexity"),
    ("ashby", "Mercury", "Mercury"),
    ("ashby", "Deel", "Deel"),
    ("ashby", "Vanta", "Vanta"),
    ("ashby", "Airtable", "Airtable"),
    ("ashby", "Loom", "Loom"),
    ("ashby", "Zapier", "Zapier"),
    ("ashby", "Hex", "Hex"),
    ("ashby", "Watershed", "Watershed"),
]

FETCHERS = {
    "greenhouse": fetch_greenhouse_board,
    "lever": fetch_lever_board,
    "ashby": fetch_ashby_board,
}
