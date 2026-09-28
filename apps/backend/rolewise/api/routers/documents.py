import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from rolewise import schemas
from rolewise.auth import current_user
from rolewise.db import get_db
from rolewise.models import Document, User
from rolewise.services import documents as docs

router = APIRouter(prefix="/documents", tags=["documents"])


def _own_doc(db: Session, user: User, doc_id: uuid.UUID) -> Document:
    d = db.get(Document, doc_id)
    if not d or d.user_id != user.id or d.kind not in ("resume", "cover_letter"):
        raise HTTPException(404, "Document not found")
    return d


@router.get("/{doc_id}", response_model=schemas.DocumentOut)
def get_document(doc_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _own_doc(db, user, doc_id)


@router.get("/{doc_id}/download")
def download(doc_id: uuid.UUID, format: str = Query("docx", pattern="^(docx|md)$"),
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _own_doc(db, user, doc_id)
    meta = d.content.get("meta", {})
    name = "-".join(filter(None, [
        d.content.get("header", {}).get("full_name") or "resume",
        meta.get("company"), "cover-letter" if d.kind == "cover_letter" else "resume", f"v{d.version}",
    ]))
    filename = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") + f".{format}"
    if format == "md":
        body, media = docs.to_markdown(d.kind, d.content).encode(), "text/markdown; charset=utf-8"
    else:
        body = docs.to_docx(d.kind, d.content)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
