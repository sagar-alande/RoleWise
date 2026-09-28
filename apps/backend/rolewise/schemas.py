import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FactKind = Literal["skill", "role", "project", "education", "certification", "achievement"]
MatchStatus = Literal["new", "saved", "dismissed", "pursuing", "applied", "interview", "offer", "rejected"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FactCreate(BaseModel):
    kind: FactKind
    title: str = Field(min_length=1, max_length=500)
    details: dict = Field(default_factory=dict)


class FactUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    details: dict | None = None


class FactOut(ORM):
    id: uuid.UUID
    kind: str
    title: str
    details: dict
    source: str
    verified: bool
    verified_at: datetime | None


Tier = Literal["intern", "entry", "mid", "senior"]


class ArchetypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    fit: Literal["primary", "secondary", "adjacent"] = "primary"


class PreferencesIn(BaseModel):
    target_titles: list[str] = []
    locations: list[str] = []
    remote_modes: list[Literal["onsite", "hybrid", "remote"]] = []
    salary_min: int | None = None
    currency: str = "USD"
    seniority: Tier | None = None
    employment_types: list[str] = []
    industries: list[str] = []
    dealbreakers: list[str] = []
    excluded_title_keywords: list[str] = []
    skip_tiers: list[Tier] = []
    authorized_in: list[str] = []
    needs_sponsorship: bool | None = None
    archetypes: list[ArchetypeIn] = []


class PreferencesOut(PreferencesIn, ORM):
    seniority: str | None = None  # lenient on read: rows saved before tiers were enforced
    skip_tiers: list[str] = []


class UploadUrlRequest(BaseModel):
    filename: str
    content_type: str


class UploadUrlResponse(BaseModel):
    upload_url: str
    s3_key: str


class ParseRequest(BaseModel):
    s3_key: str
    filename: str
    replace_existing: bool = False


class ResumeOut(BaseModel):
    filename: str
    uploaded_at: datetime
    download_url: str


class TaskAccepted(BaseModel):
    run_id: uuid.UUID
    status: str = "queued"


class JobPaste(BaseModel):
    company: str
    title: str
    description: str = Field(min_length=50)
    location: str | None = None
    remote_mode: Literal["onsite", "hybrid", "remote"] | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    url: str | None = None


class JobOut(ORM):
    id: uuid.UUID
    company: str
    title: str
    location: str | None
    remote_mode: str | None
    salary_min: int | None
    salary_max: int | None
    url: str | None
    created_at: datetime
    listing_status: str
    last_checked_at: datetime | None


class GapOut(ORM):
    matched: list
    partial: list
    missing: list
    underrepresented: list
    recommendations: list


class MatchOut(ORM):
    id: uuid.UUID
    job: JobOut
    score: float
    global_score: float | None = None
    verdict: str | None = None
    has_documents: bool = False
    status: str
    breakdown: dict
    explanation: dict | None
    created_at: datetime


class MatchDetail(MatchOut):
    gaps: GapOut | None = None


class MatchStatusUpdate(BaseModel):
    status: MatchStatus


class RunOut(ORM):
    id: uuid.UUID
    task: str
    status: str
    error: str | None
    started_at: datetime
    ended_at: datetime | None


class ContactIn(BaseModel):
    """Resume header details. Entered by the user, never generated."""
    full_name: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=50)
    location: str = Field(default="", max_length=200)
    links: list[str] = Field(default_factory=list, max_length=5)


class GenerateDocumentsIn(BaseModel):
    tone: Literal["mirror", "formal", "direct", "conversational"] = "mirror"
    angle: str | None = Field(default=None, max_length=500)  # the candidate's own "why this role"


class DocumentOut(ORM):
    id: uuid.UUID
    match_id: uuid.UUID | None
    kind: str
    version: int
    content: dict
    status: str
    created_at: datetime


class DocumentVersion(ORM):
    id: uuid.UUID
    kind: str
    version: int
    created_at: datetime


class MatchDocumentsOut(BaseModel):
    resume: DocumentOut | None = None
    cover_letter: DocumentOut | None = None
    history: list[DocumentVersion] = []
