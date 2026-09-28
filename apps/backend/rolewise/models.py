"""Database models. career_facts is the single source of truth for everything the AI may claim."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from rolewise.db import Base

EMBED_DIMS = 1024


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _id()
    auth_subject: Mapped[str] = mapped_column(String(255), unique=True)  # Cognito sub
    email: Mapped[str] = mapped_column(String(320))
    # Resume header: {"full_name", "email", "phone", "location", "links": [...], "headline"}. User-entered only.
    contact: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _created()


class CareerFact(Base):
    """One verifiable fact: a skill, role, project, education entry, certification or achievement."""

    __tablename__ = "career_facts"
    __table_args__ = (
        Index("ix_career_facts_embedding", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = _user_fk()
    kind: Mapped[str] = mapped_column(String(32))  # skill|role|project|education|certification|achievement
    title: Mapped[str] = mapped_column(String(500))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)  # e.g. company, dates, years, metrics
    source: Mapped[str] = mapped_column(String(32))  # resume_parse|user_entry|user_edit|ai_suggestion
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIMS), nullable=True)
    created_at: Mapped[datetime] = _created()


class Preference(Base):
    __tablename__ = "preferences"
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    target_titles: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    locations: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    remote_modes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)  # onsite|hybrid|remote
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    seniority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    employment_types: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    industries: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    dealbreakers: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    # Matching filters and signals modeled on career-ops (see services/matching.py).
    excluded_title_keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default=text("'{}'")
    )
    skip_tiers: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    authorized_in: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    needs_sponsorship: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # [{"name": "Data Engineer", "fit": "primary|secondary|adjacent"}]
    archetypes: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))


class JobSource(Base):
    __tablename__ = "job_sources"
    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(String(100), unique=True)
    kind: Mapped[str] = mapped_column(String(32))  # ats_board|aggregator|user_paste
    terms_ok: Mapped[bool] = mapped_column(Boolean, default=False)  # invariant: only true sources are used
    config: Mapped[dict] = mapped_column(JSONB, default=dict)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("content_hash"),
        Index("ix_jobs_embedding", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
    id: Mapped[uuid.UUID] = _id()
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job_sources.id"))
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500))
    # Some employers list many regions in one string (e.g. Datadog remote postings) - well past a
    # typical "City, State" length, so this needs real headroom, not just a little.
    location: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    remote_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    requirements_extracted: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIMS), nullable=True)
    # Title only (not title+description like `embedding`). Backs semantic "target roles" matching,
    # which needs the title's own meaning, not diluted by the rest of the posting.
    title_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIMS), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()
    # Source evidence only - never mutated by age alone. unknown|active|possibly_stale|closed. See
    # worker/tasks.py's liveness pass: possibly_stale means "absent from one trusted refresh", closed
    # means "absent from two consecutive trusted refreshes". A failed or suspicious refresh never
    # changes this. Time-based staleness ("not checked in N days") is computed for display from
    # last_checked_at, never persisted here, so "not recently checked" and "checked and missing" stay
    # distinguishable.
    listing_status: Mapped[str] = mapped_column(String(16), default="unknown", server_default="unknown")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobRequirement(Base):
    __tablename__ = "job_requirements"
    id: Mapped[uuid.UUID] = _id()
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # required_skill|preferred_skill|experience|education|domain
    text: Mapped[str] = mapped_column(Text)
    normalized: Mapped[str | None] = mapped_column(String(255), nullable=True)
    min_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    # critical|high|meaningful|preferred|low_signal, judged from the posting alone (never from the CV)
    importance: Mapped[str | None] = mapped_column(String(16), nullable=True)
    evidence_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)  # stated|structural|inferred
    jd_signal: Mapped[str | None] = mapped_column(Text, nullable=True)  # verbatim quote from the posting
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIMS), nullable=True)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = _user_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float)  # 0..100, from services/matching.py only
    global_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 1..5
    # apply_now|worth_applying|only_with_reason|not_recommended|hard_stop
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    breakdown: Mapped[dict] = mapped_column(JSONB)
    explanation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="new")
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = _created()


class GapAnalysis(Base):
    __tablename__ = "gap_analyses"
    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    matched: Mapped[list] = mapped_column(JSONB, default=list)
    partial: Mapped[list] = mapped_column(JSONB, default=list)
    missing: Mapped[list] = mapped_column(JSONB, default=list)
    underrepresented: Mapped[list] = mapped_column(JSONB, default=list)
    recommendations: Mapped[list] = mapped_column(JSONB, default=list)


class Document(Base):
    """V2: generated resume or cover letter."""

    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_match_kind", "match_id", "kind"),)
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = _user_fk()
    match_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matches.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # resume|cover_letter|uploaded_resume
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[dict] = mapped_column(JSONB, default=dict)
    s3_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = _created()


class Claim(Base):
    """V2: every sentence in a generated document, linked to the verified facts that support it."""

    __tablename__ = "claims"
    id: Mapped[uuid.UUID] = _id()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    supporting_fact_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    validator_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|ok|rejected
    validator_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # why a claim was rejected


class Approval(Base):
    """V2: the exact package the user approved. submit_application requires a matching payload_hash."""

    __tablename__ = "approvals"
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = _user_fk()
    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(64))
    payload_hash: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[datetime] = _created()


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = _user_fk()
    task: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="queued")  # queued|running|waiting_user|done|failed
    state: Mapped[dict] = mapped_column(JSONB, default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = _created()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(16))  # user|agent|system
    action: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)  # ids only, never personal data
    at: Mapped[datetime] = _created()
