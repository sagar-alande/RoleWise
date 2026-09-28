"""Resume text extraction and structuring. Output facts are always unverified until the user confirms them."""

from __future__ import annotations

import io

from rolewise.services.ai import get_ai

ALLOWED_KINDS = {"skill", "role", "project", "education", "certification", "achievement"}

# Generous bounds for an actual resume (a handful of pages, a few MB at most) that still cap the
# worst case: a pathological or oversized file forcing expensive parsing with no limit at all.
MAX_RESUME_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_PDF_PAGES = 20


def extract_text(data: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError(
                f"That PDF has {len(reader.pages)} pages - resumes should be under {MAX_PDF_PAGES}. "
                "Please upload a shorter file."
            )
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith(".docx"):
        from docx import Document

        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore")
    raise ValueError("Unsupported file type. Upload a PDF, DOCX or TXT file.")


def structure_resume(text: str) -> tuple[list[dict], str]:
    """Returns (candidate facts, model id). Facts are validated but NOT verified."""
    data, model_id = get_ai().complete_json("resume_extract.v2", fast=True, resume_text=text[:30000])
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
