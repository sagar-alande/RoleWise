"""Worker tasks. Each task records its progress in agent_runs and logs ids only (no personal data)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rolewise.aws import s3
from rolewise.config import get_settings
from rolewise.db import get_sessionmaker
from rolewise.models import (
    AgentRun,
    AuditLog,
    CareerFact,
    Claim,
    Document,
    GapAnalysis,
    Job,
    JobRequirement,
    JobSource,
    Match,
    Preference,
    User,
)
from rolewise.services import documents as docs
from rolewise.services import matching
from rolewise.services.ai import get_ai
from rolewise.services.explain import explain_match
from rolewise.services.gaps import analyze_gaps
from rolewise.services.resume_parser import MAX_RESUME_BYTES, extract_text, structure_resume
from rolewise.worker import connectors
from rolewise.worker.connectors import CURATED_BOARDS, FETCHERS, content_hash

log = logging.getLogger(__name__)

RECALL_LIMIT = 200  # jobs pulled by vector similarity before full scoring
EXPLAIN_TOP_N = 20  # only the best matches get an LLM explanation, to control cost


# --------------------------------------------------------------------------- resume


def parse_resume(db: Session, user_id: uuid.UUID, s3_key: str, filename: str, replace_existing: bool = False) -> dict:
    s3_client = s3()
    bucket = get_settings().s3_bucket
    # Checked via HEAD before downloading the body, so an oversized file is rejected without ever
    # pulling it into memory.
    size = s3_client.head_object(Bucket=bucket, Key=s3_key)["ContentLength"]
    if size > MAX_RESUME_BYTES:
        raise ValueError(
            f"That file is {size // (1024 * 1024)}MB - resumes must be under "
            f"{MAX_RESUME_BYTES // (1024 * 1024)}MB. Please upload a smaller file."
        )
    obj = s3_client.get_object(Bucket=bucket, Key=s3_key)
    text = extract_text(obj["Body"].read(), filename)
    facts, model_id = structure_resume(text)

    if replace_existing:
        # Remove only facts the old resume produced and the user never touched. A fact the user has
        # since edited is source="user_edit" (see profile.py's update_fact), so it survives here - the
        # provenance fix makes this scoped delete naturally preserve real user corrections without any
        # special-casing by kind or field.
        old = db.scalars(select(CareerFact).where(CareerFact.user_id == user_id, CareerFact.source == "resume_parse")).all()
        for f in old:
            db.delete(f)
        db.flush()

    # Whatever remains - every existing fact on merge, or the user_entry/user_edit facts a replace just
    # preserved - must never be silently duplicated by the newly parsed facts. Exact match first (as
    # before), then a strict same-kind semantic check for near-duplicates an extraction might phrase
    # slightly differently ("AWS" vs "Amazon Web Services") - this only ever prevents inserting a new
    # fact, it never touches or deletes an existing one.
    existing_facts = db.scalars(select(CareerFact).where(CareerFact.user_id == user_id)).all()
    existing_keys = {(f.kind, f.title.strip().lower()) for f in existing_facts}
    facts = [f for f in facts if (f["kind"], f["title"].strip().lower()) not in existing_keys]

    if facts:
        missing = [f for f in existing_facts if f.embedding is None]
        if missing:
            for f, vec in zip(missing, get_ai().embed([f"{f.kind}: {f.title}" for f in missing])):
                f.embedding = vec
            db.flush()

        threshold = get_settings().match_threshold
        by_kind: dict[str, list[list[float]]] = {}
        for f in existing_facts:
            if f.embedding is not None:
                by_kind.setdefault(f.kind, []).append(list(f.embedding))

        new_embeddings = get_ai().embed([f"{f['kind']}: {f['title']}" for f in facts])
        kept_facts: list[dict] = []
        kept_embeddings: list[list[float]] = []
        for f, emb in zip(facts, new_embeddings):
            candidates = by_kind.get(f["kind"], []) + [
                e for kf, e in zip(kept_facts, kept_embeddings) if kf["kind"] == f["kind"]
            ]
            if any(matching.cosine(emb, e) >= threshold for e in candidates):
                continue  # a clear near-duplicate of an existing or already-kept fact
            kept_facts.append(f)
            kept_embeddings.append(emb)
        facts, embeddings = kept_facts, kept_embeddings
    else:
        embeddings = []

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


def _upsert_or_reconcile(db: Session, source: JobSource, *, external_id: str | None, company: str, title: str,
                         location: str | None, remote_mode: str | None, description: str, url: str | None,
                         now: datetime) -> tuple[Job, bool]:
    """Like upsert_job, but for ats_board sources: resolves identity in priority order (1) same
    source + external_id, (2) same content_hash - so a posting reposted under a new external_id is
    recognized as the same job rather than degraded toward closed while a duplicate accumulates - and
    only then (3) creates a new row. Only external_id/url/listing_status/last_checked_at are ever
    reconciled onto an existing row; title/description/content_hash/embedding are left exactly as
    originally scored, since this function only tracks identity and liveness, never content.
    Returns (job, created)."""
    h = content_hash(company, title, description)

    existing = None
    if external_id:
        existing = db.scalar(select(Job).where(Job.source_id == source.id, Job.external_id == external_id))
    if existing is None:
        existing = db.scalar(select(Job).where(Job.content_hash == h))

    if existing is not None:
        if existing.source_id == source.id:
            # Same board: either the same external_id, or identical text reposted under a new one -
            # either way it's still live.
            if external_id and existing.external_id != external_id:
                existing.external_id = external_id
            if url and existing.url != url:
                existing.url = url
            existing.listing_status = "active"
            existing.last_checked_at = now
        # else: identical text already represented under a different source entirely - not this
        # board's job to claim identity or liveness over.
        return existing, False

    job = Job(source_id=source.id, external_id=external_id, company=company, title=title, location=location,
             remote_mode=remote_mode, description=description, url=url, content_hash=h,
             listing_status="active", last_checked_at=now)
    db.add(job)
    db.flush()
    return job, True


def _degrade_missing_jobs(db: Session, source_id: uuid.UUID, confirmed_ids: set[uuid.UUID]) -> None:
    """Two-strike closure, run only after a successful, non-suspicious board refresh: a job absent
    from that refresh degrades one step (unknown/active -> possibly_stale, possibly_stale -> closed).
    Never runs after a failed or suspicious refresh (see _ingest_platform_board), so a transient
    provider problem can never cost a job its status. Age alone never reaches this function either -
    that's a display-time computation from last_checked_at, not a stored-status mutation."""
    q = select(Job).where(Job.source_id == source_id, Job.listing_status.in_(("unknown", "active", "possibly_stale")))
    if confirmed_ids:
        q = q.where(Job.id.not_in(confirmed_ids))
    for job in db.scalars(q).all():
        job.listing_status = "closed" if job.listing_status == "possibly_stale" else "possibly_stale"


REQUIREMENTS_PROMPT = "job_requirements.v2"


def extract_requirements(db: Session, job_id: uuid.UUID) -> dict:
    """Pass 1 of the two-pass rule: importance is judged from the posting alone, before any candidate
    data is involved. Matching (pass 2) never changes it."""
    job = db.get(Job, job_id)
    data, _ = get_ai().complete_json(
        REQUIREMENTS_PROMPT, fast=True, job_title=job.title, job_description=job.description[:20000]
    )
    reqs = [r for r in data.get("requirements", []) if r.get("kind") in matching.COMPONENT_BY_KIND]
    texts = [r.get("normalized") or r["text"] for r in reqs]
    # Title-only embedding last: backs semantic "target roles" matching, kept separate from the
    # combined title+description embedding so it isn't diluted by the rest of the posting.
    vectors = get_ai().embed(texts + [f"{job.title}\n{job.description[:4000]}", job.title])
    db.query(JobRequirement).filter(JobRequirement.job_id == job.id).delete()
    for r, vec in zip(reqs, vectors):
        importance, tier = matching.normalize_importance(r["kind"], r.get("importance"), r.get("evidence_tier"))
        quote = r.get("jd_signal")
        db.add(JobRequirement(job_id=job.id, kind=r["kind"], text=r["text"], normalized=r.get("normalized"),
                              min_years=r.get("min_years"), importance=importance, evidence_tier=tier,
                              jd_signal=str(quote)[:500] if quote else None, embedding=vec))
    job.embedding = vectors[-2]
    job.title_embedding = vectors[-1]
    job.requirements_extracted = True
    db.commit()
    return {"requirements": len(reqs)}


def upgrade_legacy_requirements(db: Session, limit: int = 200) -> int:
    """Re-extract jobs whose requirements predate importance bands (job_requirements.v1)."""
    legacy = db.scalars(
        select(JobRequirement.job_id).where(JobRequirement.importance.is_(None)).distinct().limit(limit)
    ).all()
    for job_id in legacy:
        extract_requirements(db, job_id)
    return len(legacy)


def _ingest_platform_board(db: Session, platform: str, board_token: str, company: str | None = None) -> dict:
    source = _source(db, f"{platform}:{board_token}", "ats_board")
    prior_count = db.scalar(select(func.count()).select_from(Job).where(Job.source_id == source.id)) or 0

    # The fetch is deliberately NOT inside the per-job try/except below: a failed fetch (timeout, 500,
    # rate limit, malformed response) must propagate to the caller so this board is skipped this run -
    # not treated as "zero jobs found", which would otherwise look like every known job just vanished.
    raw_jobs = FETCHERS[platform](board_token, company)

    s = get_settings()
    suspicious = (prior_count >= s.suspicious_refresh_min_prior_count
                 and len(raw_jobs) < prior_count * s.suspicious_refresh_drop_ratio)

    now = datetime.now(UTC)
    created = 0
    confirmed_ids: set[uuid.UUID] = set()
    for raw in raw_jobs:
        remote = "remote" if raw.location and "remote" in raw.location.lower() else None
        try:
            job, is_new = _upsert_or_reconcile(
                db, source, external_id=raw.external_id, company=raw.company[:255], title=raw.title[:500],
                location=(raw.location or "")[:1000] or None, remote_mode=remote,
                description=raw.description, url=raw.url, now=now,
            )
            db.commit()
            if job.source_id == source.id:
                confirmed_ids.add(job.id)
            if is_new:
                extract_requirements(db, job.id)
                created += 1
        except Exception:
            # One malformed posting must not sacrifice the rest of this board's jobs, or the boards
            # after it - a poisoned session raises PendingRollbackError on every later query otherwise.
            db.rollback()
            log.exception("skipped a %s:%s posting (external_id=%s)", platform, board_token, raw.external_id)

    if suspicious:
        log.warning("skipped liveness degrade for %s:%s - suspicious refresh (prior=%d, now=%d)",
                   platform, board_token, prior_count, len(raw_jobs))
    else:
        _degrade_missing_jobs(db, source.id, confirmed_ids)
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
            db.rollback()
            log.exception("discover_jobs: failed to ingest %s:%s", platform, token)
    return {"jobs_created": created}


def ingest_job_from_url(db: Session, url: str) -> dict:
    """Fetch and ingest a single job from its posting URL. Greenhouse/Lever/Ashby only, via their
    own public per-job APIs - never by rendering or scraping the page (see connectors.py)."""
    parsed = connectors.parse_ats_url(url)
    if not parsed:
        gh_jid = connectors.parse_greenhouse_gh_jid(url)
        if gh_jid:
            # Employer's own domain (careers.company.com?gh_jid=...): the board token isn't in the
            # URL, so try every Greenhouse board this app already knows about.
            known = db.scalars(select(JobSource.name).where(JobSource.name.like("greenhouse:%"))).all()
            for name in known:
                token = name.split(":", 1)[1]
                raw = connectors.fetch_greenhouse_job(token, gh_jid)
                if raw:
                    parsed = ("greenhouse", token, gh_jid)
                    break
        if not parsed:
            raise ValueError(
                "Couldn't identify this job's source automatically. Paste the description instead."
            )
    platform, token, job_id = parsed
    raw = connectors.FETCH_JOB[platform](token, job_id)
    if not raw:
        raise ValueError("That posting couldn't be found - it may have been taken down.")

    source = _source(db, f"{platform}:{token}", "ats_board")
    remote = "remote" if raw.location and "remote" in raw.location.lower() else None
    job, is_new = _upsert_or_reconcile(
        db, source, external_id=raw.external_id, company=raw.company[:255], title=raw.title[:500],
        location=(raw.location or "")[:1000] or None, remote_mode=remote,
        description=raw.description, url=raw.url, now=datetime.now(UTC),
    )
    db.commit()
    if is_new:
        extract_requirements(db, job.id)
    return {"job_id": str(job.id), "already_existed": not is_new}


# --------------------------------------------------------------------------- matching


def _prefs_in(p: Preference | None) -> matching.PreferencesIn:
    if not p:
        return matching.PreferencesIn()
    target_titles = p.target_titles or []
    # One batch call, once per scoring run (not per job) - cheap even against real Bedrock.
    embeddings = get_ai().embed(target_titles) if target_titles else []
    return matching.PreferencesIn(
        locations=p.locations or [],
        remote_modes=p.remote_modes or [],
        salary_min=p.salary_min,
        dealbreakers=p.dealbreakers or [],
        target_titles=target_titles,
        excluded_title_keywords=p.excluded_title_keywords or [],
        skip_tiers=p.skip_tiers or [],
        seniority=p.seniority,
        authorized_in=p.authorized_in or [],
        needs_sponsorship=p.needs_sponsorship,
        archetypes=[matching.Archetype(a["name"], a.get("fit", "primary"))
                    for a in (p.archetypes or []) if a.get("name")],
        target_title_embeddings=embeddings,
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
                        (f.details or {}).get("years"), (f.details or {}).get("highlights") or [])
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
            [matching.RequirementIn(str(r.id), r.kind, r.text, list(r.embedding), r.normalized, r.min_years,
                                    r.importance, r.evidence_tier, r.jd_signal)
             for r in reqs if r.embedding is not None],
            title_embedding=list(job.title_embedding) if job.title_embedding is not None else None,
        )
        result = matching.score_match(job_in, fact_ins, prefs)
        if result.filtered_out is None:
            scored.append((job, result))
        else:
            # A job scored earlier may now be filtered (preferences changed). Hide it, keep the row.
            stale = db.scalar(select(Match).where(Match.user_id == user_id, Match.job_id == job.id))
            if stale:
                stale.verdict, stale.breakdown = "filtered", result.to_dict()

    scored.sort(key=lambda x: (x[1].global_score, x[1].score), reverse=True)
    for rank, (job, result) in enumerate(scored):
        m = db.scalar(select(Match).where(Match.user_id == user_id, Match.job_id == job.id))
        if not m:
            m = Match(user_id=user_id, job_id=job.id, score=result.score, breakdown={})
            db.add(m)
        m.score, m.breakdown = result.score, result.to_dict()
        m.global_score, m.verdict = result.global_score, result.verdict
        if rank < EXPLAIN_TOP_N:
            m.explanation, m.model_version, m.prompt_version = explain_match(job.title, job.company, result)
        db.flush()
        gaps = analyze_gaps(result, fact_ins, has_resume)
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
    upgraded = upgrade_legacy_requirements(db)
    scored = score_matches(db, user_id)
    return {**discovered, **scored, "requirements_upgraded": upgraded}


# --------------------------------------------------------------------------- tailored documents

TONES = {"formal", "direct", "conversational", "mirror"}


def _next_version(db: Session, match_id: uuid.UUID, kind: str) -> int:
    latest = db.scalar(select(Document.version).where(Document.match_id == match_id, Document.kind == kind)
                       .order_by(Document.version.desc()).limit(1))
    return (latest or 0) + 1


def _save_doc(db: Session, user_id, match_id, kind: str, content: dict, check: docs.Check, meta: dict) -> Document:
    doc = Document(user_id=user_id, match_id=match_id, kind=kind, version=_next_version(db, match_id, kind),
                   content={**content, "removed": check.removed, "warnings": check.warnings, "meta": meta},
                   status="draft")
    db.add(doc)
    db.flush()
    for c in check.kept:
        db.add(Claim(document_id=doc.id, text=c["text"], supporting_fact_ids=[uuid.UUID(i) for i in c["fact_ids"]],
                     validator_status="ok"))
    for c in check.removed:
        db.add(Claim(document_id=doc.id, text=c["text"], supporting_fact_ids=[], validator_status="rejected",
                     validator_note=c["reason"]))
    return doc


def generate_documents(db: Session, match_id: uuid.UUID, tone: str = "mirror", angle: str | None = None) -> dict:
    """Tailored resume + cover letter for one match, both fact-checked against verified facts only.
    Every run creates a new version, so earlier documents stay available."""
    m = db.get(Match, match_id)
    job, user = db.get(Job, m.job_id), db.get(User, m.user_id)
    facts = db.scalars(select(CareerFact).where(CareerFact.user_id == m.user_id, CareerFact.verified.is_(True))
                       .order_by(CareerFact.created_at)).all()
    if not facts:
        raise ValueError("Add and verify some facts on your profile first.")
    fact_list = [docs.Fact(str(f.id), f.kind, f.title, f.details or {}) for f in facts]
    reqs = (m.breakdown or {}).get("requirements", [])
    req_view = [{k: r.get(k) for k in ("text", "kind", "importance", "evidence_tier", "jd_signal", "status",
                                        "fact_title")} for r in reqs]
    skill_terms = [r["text"] for r in reqs if r.get("kind") != "experience"]
    contact = {"email": user.email, **(user.contact or {})}
    common = {"job_title": job.title, "company": job.company, "job_description": job.description[:15000],
              "requirements_json": json.dumps(req_view), "facts_json": docs.fact_catalog(fact_list)}
    ai = get_ai()

    raw_resume, model_id = ai.complete_json("resume_tailor.v1", **common)
    resume, rcheck = docs.assemble_resume(raw_resume, fact_list, contact, skill_terms, job.description,
                                          headline=job.title, company=job.company)
    resume["coverage"] = docs.keyword_coverage(reqs, docs.resume_plain_text(resume))

    tone = tone if tone in TONES else "mirror"
    tone_text = {"mirror": "match the register the posting uses", "formal": "formal, structured, respectful",
                 "direct": "direct, plain sentences, no pleasantries",
                 "conversational": "warm but professional"}[tone]
    angle_text = (f"Use the candidate's own angle for why this role: \"{angle.strip()[:500]}\"" if angle and angle.strip()
                  else "Derive why this role from what the posting emphasizes most.")
    raw_cover, _ = ai.complete_json("cover_letter.v1", tone=tone_text, angle_instruction=angle_text, **common)
    cover, ccheck = docs.assemble_cover_letter(raw_cover, fact_list, contact, skill_terms, job.description,
                                               job.title, job.company)
    cover["coverage"] = docs.keyword_coverage(reqs, docs.cover_plain_text(cover))

    meta = {"model": model_id, "tone": tone, "angle": angle or None, "job_title": job.title,
            "company": job.company, "match_score": m.global_score}
    r_doc = _save_doc(db, m.user_id, m.id, "resume", resume, rcheck,
                      {**meta, "prompt_version": "resume_tailor.v1"})
    c_doc = _save_doc(db, m.user_id, m.id, "cover_letter", cover, ccheck,
                      {**meta, "prompt_version": "cover_letter.v1"})
    if m.status in ("new", "dismissed"):
        m.status = "saved"  # generating documents always keeps the job in the user's list
    db.add(AuditLog(user_id=m.user_id, actor="agent", action="documents_generated",
                    details={"match_id": str(m.id), "resume": str(r_doc.id), "cover_letter": str(c_doc.id),
                             "removed_claims": len(rcheck.removed) + len(ccheck.removed)}))
    db.commit()
    return {"resume_id": str(r_doc.id), "cover_letter_id": str(c_doc.id), "version": r_doc.version,
            "removed_claims": len(rcheck.removed) + len(ccheck.removed)}


# --------------------------------------------------------------------------- dispatch

TASKS = {
    "parse_resume": lambda db, p: parse_resume(
        db, uuid.UUID(p["user_id"]), p["s3_key"], p["filename"], p.get("replace_existing", False)
    ),
    "ingest_greenhouse": lambda db, p: ingest_greenhouse(db, p["board_token"], p.get("company")),
    "ingest_lever": lambda db, p: ingest_lever(db, p["board_token"], p.get("company")),
    "ingest_ashby": lambda db, p: ingest_ashby(db, p["board_token"], p.get("company")),
    "extract_requirements": lambda db, p: extract_requirements(db, uuid.UUID(p["job_id"])),
    "score_matches": lambda db, p: score_matches(db, uuid.UUID(p["user_id"])),
    "discover_and_score": lambda db, p: discover_and_score(db, uuid.UUID(p["user_id"])),
    "ingest_job_url": lambda db, p: ingest_job_from_url(db, p["url"]),
    "generate_documents": lambda db, p: generate_documents(db, uuid.UUID(p["match_id"]), p.get("tone", "mirror"),
                                                           p.get("angle")),
}


def _user_facing_error(exc: Exception) -> str:
    """What AgentRun.error shows the user. A ValueError/PermissionError here is always one we raised
    deliberately with a message already written for the user (see e.g. ingest_job_from_url,
    generate_documents); anything else (a library's own exception - HTTPStatusError, KeyError, etc.)
    can carry an internal URL, stack-like text or a class name with no meaning to them, so it's
    replaced with one generic, friendly message instead. The full exception always goes to the logs
    separately (see dispatch()'s log.exception call), regardless of what this returns."""
    if isinstance(exc, (ValueError, PermissionError)) and str(exc):
        return str(exc)
    return "Something went wrong while processing this. Please try again."


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
            run.status, run.error, run.ended_at = "failed", _user_facing_error(exc)[:300], datetime.now(UTC)
            db.commit()
        raise
    finally:
        db.close()
