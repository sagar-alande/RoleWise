import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from rolewise import schemas
from rolewise.auth import current_user
from rolewise.aws import enqueue
from rolewise.db import get_db
from rolewise.models import AgentRun, Job, User
from rolewise.worker.tasks import _source, upsert_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


class GreenhouseIngest(BaseModel):
    board_token: str
    company: str | None = None


class JobUrlIngest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


@router.get("", response_model=list[schemas.JobOut])
def list_jobs(limit: int = 50, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Job).order_by(Job.created_at.desc()).limit(min(limit, 200))).all()


@router.post("/paste", response_model=schemas.TaskAccepted, status_code=202)
def paste_job(body: schemas.JobPaste, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A job description the user pasted. Always permitted, since the user provides it."""
    source = _source(db, "user_paste", "user_paste")
    job = upsert_job(db, source, **body.model_dump())
    if job is None:
        raise HTTPException(409, "This job is already in RoleWise")
    run = AgentRun(user_id=user.id, task="extract_requirements")
    db.add(run)
    db.commit()
    enqueue("extract_requirements", run.id, {"job_id": str(job.id)})
    return schemas.TaskAccepted(run_id=run.id)


@router.post("/sources/greenhouse", response_model=schemas.TaskAccepted, status_code=202)
def ingest_greenhouse(body: GreenhouseIngest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not re.fullmatch(r"[a-z0-9_-]{2,100}", body.board_token):
        raise HTTPException(400, "Invalid board token")
    run = AgentRun(user_id=user.id, task="ingest_greenhouse")
    db.add(run)
    db.commit()
    enqueue("ingest_greenhouse", run.id, body.model_dump())
    return schemas.TaskAccepted(run_id=run.id)


@router.post("/from-url", response_model=schemas.TaskAccepted, status_code=202)
def ingest_from_url(body: JobUrlIngest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Fetch one job by its posting URL instead of pasting the description by hand. Only works for
    Greenhouse/Lever/Ashby postings (fetched via their own public APIs) - any other URL fails with a
    clear message asking the user to paste the description instead."""
    if not re.match(r"^https?://", body.url, re.IGNORECASE):
        raise HTTPException(400, "That doesn't look like a URL")
    run = AgentRun(user_id=user.id, task="ingest_job_url")
    db.add(run)
    db.commit()
    enqueue("ingest_job_url", run.id, {"url": body.url})
    return schemas.TaskAccepted(run_id=run.id)
