import uuid
from datetime import UTC, datetime
from pathlib import PurePath

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from rolewise import schemas
from rolewise.auth import current_user
from rolewise.aws import enqueue, s3_presigner
from rolewise.config import get_settings
from rolewise.db import get_db
from rolewise.models import AgentRun, AuditLog, CareerFact, Document, Preference, User

router = APIRouter(prefix="/profile", tags=["profile"])

ALLOWED_UPLOADS = {".pdf", ".docx", ".txt"}


def _own_fact(db: Session, user: User, fact_id: uuid.UUID) -> CareerFact:
    fact = db.get(CareerFact, fact_id)
    if not fact or fact.user_id != user.id:
        raise HTTPException(404, "Fact not found")
    return fact


@router.get("/facts", response_model=list[schemas.FactOut])
def list_facts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(CareerFact).where(CareerFact.user_id == user.id).order_by(CareerFact.kind, CareerFact.created_at)
    ).all()


@router.post("/facts", response_model=schemas.FactOut, status_code=201)
def create_fact(body: schemas.FactCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Facts the user types in are verified by the user's own action.
    fact = CareerFact(user_id=user.id, kind=body.kind, title=body.title, details=body.details,
                      source="user_entry", verified=True, verified_at=datetime.now(UTC))
    db.add(fact)
    db.commit()
    return fact


@router.patch("/facts/{fact_id}", response_model=schemas.FactOut)
def update_fact(fact_id: uuid.UUID, body: schemas.FactUpdate, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    fact = _own_fact(db, user, fact_id)
    if body.title is not None:
        fact.title = body.title
        fact.embedding = None  # re-embedded on next scoring run
    if body.details is not None:
        fact.details = body.details
    if fact.source != "resume_parse":
        fact.source = "user_edit"
    db.commit()
    return fact


@router.post("/facts/{fact_id}/verify", response_model=schemas.FactOut)
def verify_fact(fact_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    fact = _own_fact(db, user, fact_id)
    fact.verified, fact.verified_at = True, datetime.now(UTC)
    db.add(AuditLog(user_id=user.id, actor="user", action="fact_verified", details={"fact_id": str(fact.id)}))
    db.commit()
    return fact


@router.delete("/facts/{fact_id}", status_code=204)
def delete_fact(fact_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own_fact(db, user, fact_id))
    db.commit()


@router.get("/preferences", response_model=schemas.PreferencesOut)
def get_preferences(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.get(Preference, user.id) or schemas.PreferencesOut()


@router.put("/preferences", response_model=schemas.PreferencesOut)
def put_preferences(body: schemas.PreferencesIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    pref = db.get(Preference, user.id) or Preference(user_id=user.id)
    for key, value in body.model_dump().items():
        setattr(pref, key, value)
    db.add(pref)
    db.commit()
    return pref


@router.post("/resume/upload-url", response_model=schemas.UploadUrlResponse)
def resume_upload_url(body: schemas.UploadUrlRequest, user: User = Depends(current_user)):
    ext = PurePath(body.filename).suffix.lower()
    if ext not in ALLOWED_UPLOADS:
        raise HTTPException(400, "Upload a PDF, DOCX or TXT file")
    key = f"resumes/{user.id}/{uuid.uuid4()}{ext}"
    url = s3_presigner().generate_presigned_url(
        "put_object",
        Params={"Bucket": get_settings().s3_bucket, "Key": key, "ContentType": body.content_type},
        ExpiresIn=600,
    )
    return schemas.UploadUrlResponse(upload_url=url, s3_key=key)


@router.post("/resume/parse", response_model=schemas.TaskAccepted, status_code=202)
def parse_resume(body: schemas.ParseRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not body.s3_key.startswith(f"resumes/{user.id}/"):
        raise HTTPException(403, "Not your file")
    run = AgentRun(user_id=user.id, task="parse_resume")
    db.add(run)
    db.commit()
    enqueue("parse_resume", run.id, {"user_id": str(user.id), "s3_key": body.s3_key, "filename": body.filename})
    return schemas.TaskAccepted(run_id=run.id)


@router.get("/resume", response_model=schemas.ResumeOut | None)
def get_resume(user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.scalar(select(Document).where(Document.user_id == user.id, Document.kind == "uploaded_resume"))
    if not doc or not doc.s3_key:
        return None
    url = s3_presigner().generate_presigned_url(
        "get_object", Params={"Bucket": get_settings().s3_bucket, "Key": doc.s3_key}, ExpiresIn=600,
    )
    return schemas.ResumeOut(
        filename=doc.content.get("filename", "resume"),
        uploaded_at=doc.content.get("uploaded_at") or doc.created_at,
        download_url=url,
    )


@router.get("/runs/{run_id}", response_model=schemas.RunOut)
def get_run(run_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(404, "Run not found")
    return run
