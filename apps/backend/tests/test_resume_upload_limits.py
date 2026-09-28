"""Resume upload limits: a page-count cap before full PDF parsing, and a file-size cap checked via
S3 HEAD before the body is ever downloaded - both existed with no bound at all before this, an easy
resource-exhaustion path on the worker. Both must reject with a friendly, specific message and never
touch a normal-sized resume."""

import io
import uuid
from unittest.mock import MagicMock

import pytest

from rolewise.services.resume_parser import MAX_PDF_PAGES, MAX_RESUME_BYTES, extract_text


def _pdf_with_pages(n: int) -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(n):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_pdf_over_the_page_limit_is_rejected_with_a_friendly_message():
    with pytest.raises(ValueError, match=f"under {MAX_PDF_PAGES}"):
        extract_text(_pdf_with_pages(MAX_PDF_PAGES + 1), "resume.pdf")


def test_pdf_at_exactly_the_page_limit_is_accepted():
    # A ceiling, not an off-by-one trap - exactly the limit must still work.
    extract_text(_pdf_with_pages(MAX_PDF_PAGES), "resume.pdf")  # must not raise


def test_a_normal_short_resume_is_unaffected():
    extract_text(_pdf_with_pages(2), "resume.pdf")  # must not raise


def test_parse_resume_rejects_an_oversized_file_without_downloading_it(monkeypatch):
    from rolewise.worker import tasks

    fake_s3 = MagicMock()
    fake_s3.head_object.return_value = {"ContentLength": MAX_RESUME_BYTES + 1}
    monkeypatch.setattr(tasks, "s3", lambda: fake_s3)
    monkeypatch.setattr(tasks, "get_settings", lambda: MagicMock(s3_bucket="test-bucket"))

    with pytest.raises(ValueError, match="MB"):
        tasks.parse_resume(MagicMock(), uuid.uuid4(), "resumes/u/f.pdf", "f.pdf")
    fake_s3.get_object.assert_not_called()  # rejected from the HEAD alone - the body was never fetched


def test_parse_resume_proceeds_past_the_size_check_for_a_normal_file(monkeypatch):
    from rolewise.worker import tasks

    fake_s3 = MagicMock()
    fake_s3.head_object.return_value = {"ContentLength": 1024}  # well under the limit
    fake_s3.get_object.return_value = {"Body": io.BytesIO(b"not actually valid content, just checking the size gate passes")}
    monkeypatch.setattr(tasks, "s3", lambda: fake_s3)
    monkeypatch.setattr(tasks, "get_settings", lambda: MagicMock(s3_bucket="test-bucket"))

    # extract_text() will raise on the unsupported/garbage filename before anything else happens -
    # this only proves the size gate itself let a normal-sized file through to that point.
    with pytest.raises(ValueError, match="Unsupported file type"):
        tasks.parse_resume(MagicMock(), uuid.uuid4(), "resumes/u/f.xyz", "f.xyz")
    fake_s3.get_object.assert_called_once()
