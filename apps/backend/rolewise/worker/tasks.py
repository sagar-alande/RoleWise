"""Worker tasks. Each task records its progress in agent_runs and logs ids only (no personal data)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from rolewise.aws import s3
from rolewise.config import get_settings
from rolewise.db import get_sessionmaker
from rolewise.models import (
    AgentRun,
    AuditLog,
    CareerFact,
    Document,
    GapAnalysis,
    Job,
    JobRequirement,
    JobSource,
    Match,
    Preference,
)
from rolewise.services import matching
from rolewise.services.ai import get_ai
from rolewise.services.explain import explain_match
from rolewise.services.gaps import analyze_gaps
from rolewise.services.resume_parser import extract_text, structure_resume
from rolewise.worker.connectors import CURATED_BOARDS, FETCHERS, content_hash

log = logging.getLogger(__name__)

RECALL_LIMIT = 200  # jobs pulled by vector similarity before full scoring
EXPLAIN_TOP_N = 20  # only the best matches get an LLM explanation, to control cost


# --------------------------------------------------------------------------- resume


def parse_resume(db: Session, user_id: uuid.UUID, s3_key: str, filename: str) -> dict:
    obj = s3().get_object(Bucket=get_settings().s3_bucket, Key=s3_key)
    text = extract_text(obj["Body"].read(), filename)
    facts, model_id = structure_resume(text)
    embeddings = get_ai().embed([f"{f['kind']}: {f['title']}" for f in facts]) if facts else []
    for f, emb in zip(facts, embeddings):
        db.add(CareerFact(user_id=user_id, embedding=emb, **f))

    # One row tracks the user's current uploaded resume, so it survives a page refresh.
    doc = db.scalar(select(Document).where(Document.user_id == user_id, Document.kind == "uploaded_resume"))
    if not doc:
        doc = Document(user_id=user_id, kind="uploaded_resume")
        db.add(doc)
    doc.s3_key = s3_key
    doc.content = {"filename": filename, "uploaded_at": datetime.now(UTC).isoformat()}
    doc.status = "stored"

    db.add(AuditLog(user_id=user_id, actor="agent", action="resume_parsed",
                    details={"facts": len(facts), "model": model_id}))
    db.commit()
    return {"facts_created": len(facts)}


# --------------------------------------------------------------------------- jobs


# Source kinds that are permitted by design: user-pasted jobs and public ATS job-board APIs.
# Anything else (aggregators) must be inserted by a human with terms_ok reviewed.
AUTO_ALLOWED_KINDS = {"user_paste", "ats_board"}


def _source(db: Session, name: str, kind: str) -> JobSource:
    src = db.scalar(select(JobSource).where(JobSource.name == name))
    if not src:
        if kind not in AUTO_ALLOWED_KINDS:
            raise PermissionError(f"Job source {name} must be registered and reviewed first")
        src = JobSource(name=name, kind=kind, terms_ok=True)
        db.add(src)
        db.flush()
    if not src.terms_ok:
        raise PermissionError(f"Job source {name} is not allow-listed")
    return src


def upsert_job(db: Session, source: JobSource, **fields) -> Job | None:
    """Returns the new Job, or None when an identical posting already exists."""
    h = content_hash(fields["company"], fields["title"], fields["description"])
    if db.scalar(select(Job.id).where(Job.content_hash == h)):
        return None
    job = Job(source_id=source.id, content_hash=h, **fields)
    db.add(job)
    db.flush()
    return job


def extract_requirements(db: Session, job_id: uuid.UUID) -> dict:
    job = db.get(Job, job_id)
    data, _ = get_ai().complete_json(
        "job_requirements.v1", fast=True, job_title=job.title, job_description=job.description[:20000]
    )
    reqs = [r for r in data.get("requirements", []) if r.get("kind") in matching.COMPONENT_BY_KIND]
    texts = [r.get("normalized") or r["text"] for r in reqs]
    vectors = get_ai().embed(texts + [f"{job.title}\n{job.description[:4000]}"])
    for r, vec in zip(reqs, vectors):
        db.add(JobRequirement(job_id=job.id, kind=r["kind"], text=r["text"], normalized=r.get("normalized"),
                              min_years=r.get("min_years"), embedding=vec))
    job.embedding = vectors[-1]
    job.requirements_extracted = True
    db.commit()
    return {"requirements": len(reqs)}


def _ingest_platform_board(db: Session, platform: str, board_token: str, company: str | None = None) -> dict:
    source = _source(db, f"{platform}:{board_token}", "ats_board")
    created = 0
    for raw in FETCHERS[platform](board_token, company):
        remote = "remote" if raw.location and "remote" in raw.location.lower() else None
        job = upsert_job(db, source, external_id=raw.external_id, company=raw.company, title=raw.title,
                         location=raw.location, remote_mode=remote, description=raw.description, url=raw.url)
        if job:
            db.commit()
            extract_requirements(db, job.id)
            created += 1
    db.commit()
    return {"jobs_created": created}


def ingest_greenhouse(db: Session, board_token: str, company: str | None = None) -> dict:
    return _ingest_platform_board(db, "greenhouse", board_token, company)


def ingest_lever(db: Session, board_token: str, company: str | None = None) -> dict:
    return _ingest_platform_board(db, "lever", board_token, company)


def ingest_ashby(db: Session, board_token: str, company: str | None = None) -> dict:
    return _ingest_platform_board(db, "ashby", board_token, company)


def discover_jobs(db: Session) -> dict:
    """Ingest every curated, allow-listed board. Shared across users: boards aren't per-user."""
    created = 0
    for platform, token, company in CURATED_BOARDS:
        try:
            created += _ingest_platform_board(db, platform, token, company)["jobs_created"]
        except Exception:
            log.exception("discover_jobs: failed to ingest %s:%s", platform, token)
    return {"jobs_created": created}


# --------------------------------------------------------------------------- matching


def _prefs_in(p: Preference | None) -> matching.PreferencesIn:
    if not p:
        return matching.PreferencesIn()
    return matching.PreferencesIn(
        locations=p.locations or [],
        remote_modes=p.remote_modes or [],
        salary_min=p.salary_min,
        dealbreakers=p.dealbreakers or [],
        target_titles=p.target_titles or [],
    )


def score_matches(db: Session, user_id: uuid.UUID) -> dict:
    facts = db.scalars(
        select(CareerFact).where(CareerFact.user_id == user_id, CareerFact.verified.is_(True))
    ).all()
    if not facts:
        return {"scored": 0, "reason": "no verified facts yet"}

    missing = [f for f in facts if f.embedding is None]
    if missing:
        for f, vec in zip(missing, get_ai().embed([f"{f.kind}: {f.title}" for f in missing])):
            f.embedding = vec
        db.flush()

    fact_ins = [
        matching.FactIn(str(f.id), f.kind, f.title, f.verified, f.source, list(f.embedding),
                        (f.details or {}).get("years"))
        for f in facts
    ]
    dims = len(fact_ins[0].embedding)
    profile_vec = [sum(f.embedding[i] for f in fact_ins) / len(fact_ins) for i in range(dims)]
    prefs = _prefs_in(db.get(Preference, user_id))
    has_resume = any(f.source == "resume_parse" for f in facts)

    jobs = db.scalars(
        select(Job)
        .where(Job.requirements_extracted.is_(True), Job.embedding.is_not(None))
        .order_by(Job.embedding.cosine_distance(profile_vec))
        .limit(RECALL_LIMIT)
    ).all()

    scored: list[tuple[Job, matching.MatchResult]] = []
    for job in jobs:
        reqs = db.scalars(select(JobRequirement).where(JobRequirement.job_id == job.id)).all()
        job_in = matching.JobIn(
            job.title, job.description, job.company, job.location, job.remote_mode, job.salary_max,
            [matching.RequirementIn(str(r.id), r.kind, r.text, list(r.embedding), r.normalized, r.min_years)
             for r in reqs if r.embedding is not None],
        )
        result = matching.score_match(job_in, fact_ins, prefs)
        if result.filtered_out is None:
            scored.append((job, result))

    scored.sort(key=lambda x: x[1].score, reverse=True)
    for rank, (job, result) in enumerate(scored):
        m = db.scalar(select(Match).where(Match.user_id == user_id, Match.job_id == job.id))
        if not m:
            m = Match(user_id=user_id, job_id=job.id, score=result.score, breakdown={})
            db.add(m)
        m.score, m.breakdown = result.score, result.to_dict()
        if rank < EXPLAIN_TOP_N:
            m.explanation, m.model_version, m.prompt_version = explain_match(job.title, job.company, result)
        db.flush()
        gaps = analyze_gaps(result, has_resume)
        ga = db.get(GapAnalysis, m.id) or GapAnalysis(match_id=m.id)
        ga.matched, ga.partial, ga.missing = gaps.matched, gaps.partial, gaps.missing
        ga.underrepresented, ga.recommendations = gaps.underrepresented, gaps.recommendations
        db.add(ga)
    db.commit()
    return {"scored": len(scored)}


def discover_and_score(db: Session, user_id: uuid.UUID) -> dict:
    """The end-to-end flow behind 'find my matches': pull fresh jobs from every allow-listed
    board, then score them against this user's verified profile and current preferences."""
    discovered = discover_jobs(db)
    scored = score_matches(db, user_id)
    return {**discovered, **scored}


# --------------------------------------------------------------------------- dispatch

TASKS = {
    "parse_resume": lambda db, p: parse_resume(db, uuid.UUID(p["user_id"]), p["s3_key"], p["filename"]),
    "ingest_greenhouse": lambda db, p: ingest_greenhouse(db, p["board_token"], p.get("company")),
    "ingest_lever": lambda db, p: ingest_lever(db, p["board_token"], p.get("company")),
    "ingest_ashby": lambda db, p: ingest_ashby(db, p["board_token"], p.get("company")),
    "extract_requirements": lambda db, p: extract_requirements(db, uuid.UUID(p["job_id"])),
    "score_matches": lambda db, p: score_matches(db, uuid.UUID(p["user_id"])),
    "discover_and_score": lambda db, p: discover_and_score(db, uuid.UUID(p["user_id"])),
}


def dispatch(message: dict) -> None:
    db = get_sessionmaker()()
    run = db.get(AgentRun, uuid.UUID(message["run_id"])) if message.get("run_id") else None
    try:
        if run:
            run.status = "running"
            db.commit()
        result = TASKS[message["task"]](db, message["payload"])
        if run:
            run.status, run.state, run.ended_at = "done", result, datetime.now(UTC)
            db.commit()
        log.info("task %s done run=%s", message["task"], message.get("run_id"))
    except Exception as exc:
        db.rollback()
        log.exception("task %s failed run=%s", message["task"], message.get("run_id"))
        if run:
            run = db.get(AgentRun, run.id)
            run.status, run.error, run.ended_at = "failed", type(exc).__name__, datetime.now(UTC)
            db.commit()
        raise
    finally:
        db.close()
