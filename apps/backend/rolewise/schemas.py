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


class PreferencesIn(BaseModel):
    target_titles: list[str] = []
    locations: list[str] = []
    remote_modes: list[Literal["onsite", "hybrid", "remote"]] = []
    salary_min: int | None = None
    currency: str = "USD"
    seniority: str | None = None
    employment_types: list[str] = []
    industries: list[str] = []
    dealbreakers: list[str] = []


class PreferencesOut(PreferencesIn, ORM):
    pass


class UploadUrlRequest(BaseModel):
    filename: str
    content_type: str


class UploadUrlResponse(BaseModel):
    upload_url: str
    s3_key: str


class ParseRequest(BaseModel):
    s3_key: str
    filename: str


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
