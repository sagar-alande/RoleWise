"""Resume text extraction and structuring. Output facts are always unverified until the user confirms them."""

from __future__ import annotations

import io

from rolewise.services.ai import get_ai

ALLOWED_KINDS = {"skill", "role", "project", "education", "certification", "achievement"}


def extract_text(data: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    if name.endswith(".docx"):
        from docx import Document

        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore")
    raise ValueError("Unsupported file type. Upload a PDF, DOCX or TXT file.")


def structure_resume(text: str) -> tuple[list[dict], str]:
    """Returns (candidate facts, model id). Facts are validated but NOT verified."""
    data, model_id = get_ai().complete_json("resume_extract.v1", fast=True, resume_text=text[:30000])
    facts = []
    for f in data.get("facts", []):
        if f.get("kind") in ALLOWED_KINDS and str(f.get("title", "")).strip():
            facts.append(
                {
                    "kind": f["kind"],
                    "title": str(f["title"]).strip()[:500],
                    "details": f.get("details") or {},
                    "source": "resume_parse",
                    "verified": False,
                }
            )
    return facts, model_id
