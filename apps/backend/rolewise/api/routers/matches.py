import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from rolewise import schemas
from rolewise.auth import current_user
from rolewise.aws import enqueue
from rolewise.db import get_db
from rolewise.models import AgentRun, GapAnalysis, Job, Match, User

router = APIRouter(prefix="/matches", tags=["matches"])


def _out(m: Match, job: Job, gaps: GapAnalysis | None = None) -> schemas.MatchDetail:
    return schemas.MatchDetail(
        id=m.id, job=schemas.JobOut.model_validate(job), score=m.score, status=m.status,
        breakdown=m.breakdown, explanation=m.explanation, created_at=m.created_at,
        gaps=schemas.GapOut.model_validate(gaps) if gaps else None,
    )


@router.get("", response_model=list[schemas.MatchOut])
def list_matches(status: str | None = None, min_score: float = 0, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    q = (
        select(Match, Job)
        .join(Job, Job.id == Match.job_id)
        .where(Match.user_id == user.id, Match.score >= min_score)
        .order_by(Match.score.desc())
    )
    q = q.where(Match.status == status) if status else q.where(Match.status != "dismissed")
    return [_out(m, j) for m, j in db.execute(q.limit(100)).all()]


@router.get("/{match_id}", response_model=schemas.MatchDetail)
def get_match(match_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m or m.user_id != user.id:
        raise HTTPException(404, "Match not found")
    return _out(m, db.get(Job, m.job_id), db.get(GapAnalysis, m.id))


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
