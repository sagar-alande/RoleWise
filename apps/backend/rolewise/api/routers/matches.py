import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from rolewise import schemas
from rolewise.auth import current_user
from rolewise.aws import enqueue
from rolewise.db import get_db
from rolewise.models import AgentRun, Document, GapAnalysis, Job, Match, User

router = APIRouter(prefix="/matches", tags=["matches"])


GENERATED_KINDS = ("resume", "cover_letter")
MY_JOB_STATUSES = ("saved", "pursuing", "applied", "interview", "offer", "rejected")
# A "recommendation" means worth looking at. Jobs the scorer itself flagged as filtered, not
# recommended, or a hard stop (e.g. no visa sponsorship) don't belong on that list - they're kept in
# the database for history (visible via My Jobs if saved) but never shown as a suggestion.
NOT_A_RECOMMENDATION = ("filtered", "not_recommended", "hard_stop")


def _has_docs(match_id):
    return exists().where(Document.match_id == match_id, Document.kind.in_(GENERATED_KINDS))


def _own_match(db: Session, user: User, match_id: uuid.UUID) -> Match:
    m = db.get(Match, match_id)
    if not m or m.user_id != user.id:
        raise HTTPException(404, "Match not found")
    return m


def _out(m: Match, job: Job, gaps: GapAnalysis | None = None, has_documents: bool = False) -> schemas.MatchDetail:
    return schemas.MatchDetail(
        id=m.id, job=schemas.JobOut.model_validate(job), score=m.score, status=m.status,
        global_score=m.global_score, verdict=m.verdict, has_documents=has_documents,
        breakdown=m.breakdown, explanation=m.explanation, created_at=m.created_at,
        gaps=schemas.GapOut.model_validate(gaps) if gaps else None,
    )


@router.get("", response_model=list[schemas.MatchOut])
def list_matches(status: str | None = None, min_score: float = 0, scope: str | None = None,
                 verdict: str | None = None, listing_status: str | None = None,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    """scope=mine returns the user's job list: saved or in-progress jobs, and any job with documents -
    never filtered by listing_status, since a job the user saved or generated documents for must stay
    reachable even if it later closes. verdict/listing_status, e.g. "hard_stop"/"closed", bypass the
    recommendation filter to look up a specific excluded match."""
    has_docs = _has_docs(Match.id)
    q = (
        select(Match, Job, has_docs.label("has_docs"))
        .join(Job, Job.id == Match.job_id)
        .where(Match.user_id == user.id, Match.score >= min_score)
    )
    if scope == "mine":
        q = q.where(Match.status.in_(MY_JOB_STATUSES) | has_docs).order_by(Match.created_at.desc())
    else:
        if verdict:
            q = q.where(Match.verdict == verdict)
        else:
            q = q.where((Match.verdict.is_(None)) | (Match.verdict.not_in(NOT_A_RECOMMENDATION)))
        if listing_status:
            q = q.where(Job.listing_status == listing_status)
        else:
            q = q.where(Job.listing_status != "closed")
        q = q.where(Match.status == status) if status else q.where(Match.status != "dismissed")
        q = q.order_by(Match.global_score.desc().nulls_last(), Match.score.desc())
    return [_out(m, j, has_documents=bool(d)) for m, j, d in db.execute(q.limit(200)).all()]


@router.get("/{match_id}", response_model=schemas.MatchDetail)
def get_match(match_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _own_match(db, user, match_id)
    return _out(m, db.get(Job, m.job_id), db.get(GapAnalysis, m.id), bool(db.scalar(select(_has_docs(m.id)))))


@router.post("/{match_id}/documents", response_model=schemas.TaskAccepted, status_code=202)
def generate_documents(match_id: uuid.UUID, body: schemas.GenerateDocumentsIn | None = None,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Tailor the resume and write a cover letter for this job. The job is saved to the user's list at once."""
    m = _own_match(db, user, match_id)
    if m.status in ("new", "dismissed"):
        m.status = "saved"
    body = body or schemas.GenerateDocumentsIn()
    run = AgentRun(user_id=user.id, task="generate_documents")
    db.add(run)
    db.commit()
    enqueue("generate_documents", run.id, {"match_id": str(m.id), "tone": body.tone, "angle": body.angle})
    return schemas.TaskAccepted(run_id=run.id)


@router.get("/{match_id}/documents", response_model=schemas.MatchDocumentsOut)
def get_documents(match_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _own_match(db, user, match_id)
    all_docs = db.scalars(select(Document).where(Document.match_id == m.id, Document.kind.in_(GENERATED_KINDS))
                          .order_by(Document.version.desc(), Document.created_at.desc())).all()
    latest = {}
    for d in all_docs:
        latest.setdefault(d.kind, d)
    return schemas.MatchDocumentsOut(
        resume=latest.get("resume"), cover_letter=latest.get("cover_letter"),
        history=[schemas.DocumentVersion.model_validate(d) for d in all_docs],
    )


@router.patch("/{match_id}", response_model=schemas.MatchOut)
def update_status(match_id: uuid.UUID, body: schemas.MatchStatusUpdate, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m or m.user_id != user.id:
        raise HTTPException(404, "Match not found")
    m.status = body.status
    db.commit()
    return _out(m, db.get(Job, m.job_id))


@router.post("/refresh", response_model=schemas.TaskAccepted, status_code=202)
def refresh(user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = AgentRun(user_id=user.id, task="score_matches")
    db.add(run)
    db.commit()
    enqueue("score_matches", run.id, {"user_id": str(user.id)})
    return schemas.TaskAccepted(run_id=run.id)


@router.post("/discover", response_model=schemas.TaskAccepted, status_code=202)
def discover(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Pull fresh jobs from every allow-listed board, then score them. This is what runs
    automatically once the user has a verified profile and submits preferences."""
    run = AgentRun(user_id=user.id, task="discover_and_score")
    db.add(run)
    db.commit()
    enqueue("discover_and_score", run.id, {"user_id": str(user.id)})
    return schemas.TaskAccepted(run_id=run.id)
