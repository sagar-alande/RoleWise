"""Job source connectors. Only sources whose terms permit automated access belong here.

Greenhouse, Lever and Ashby publish public job-board APIs for employers' career pages.
Do not add scrapers for LinkedIn, Indeed or other sites that forbid automated access.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass

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


# Small starter list of real, verified-working public boards to auto-search when a user submits
# preferences. Allow-listed by construction: only Greenhouse/Lever/Ashby, the same ToS-compliant
# platforms as the manual connectors above. Extend this list as more boards are verified.
CURATED_BOARDS: list[tuple[str, str, str]] = [
    ("greenhouse", "airbnb", "Airbnb"),
    ("greenhouse", "stripe", "Stripe"),
    ("greenhouse", "figma", "Figma"),
    ("greenhouse", "coinbase", "Coinbase"),
    ("greenhouse", "pinterest", "Pinterest"),
    ("lever", "palantir", "Palantir"),
    ("ashby", "Ramp", "Ramp"),
    ("ashby", "Notion", "Notion"),
    ("ashby", "Linear", "Linear"),
    ("ashby", "Replit", "Replit"),
]

FETCHERS = {
    "greenhouse": fetch_greenhouse_board,
    "lever": fetch_lever_board,
    "ashby": fetch_ashby_board,
}
