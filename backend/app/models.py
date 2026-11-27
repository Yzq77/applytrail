"""Database tables and API schemas."""

from datetime import UTC, date, datetime
from typing import Optional

from sqlalchemy import JSON
from sqlmodel import Field, Relationship, SQLModel

from .enums import Level, Outcome, Source, Stage, WorkMode


def utcnow() -> datetime:
    return datetime.now(UTC)


def json_list():
    """A list[str] stored as a JSON column (SQLite has no array type)."""
    return Field(default_factory=list, sa_type=JSON, sa_column_kwargs={"server_default": "[]"})


# --------------------------------------------------------------------------- events


class StageEventBase(SQLModel):
    stage: Stage
    event_date: Optional[date] = None  # when you got the invite / entered the stage
    # When you took it (OA) or it takes place (interview, webinar); a future date = scheduled.
    taken_date: Optional[date] = None
    self_rating: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = None


class StageEvent(StageEventBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    application: Optional["Application"] = Relationship(back_populates="events")


class StageEventCreate(StageEventBase):
    pass


class StageEventUpdate(SQLModel):
    stage: Optional[Stage] = None
    event_date: Optional[date] = None
    taken_date: Optional[date] = None
    self_rating: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = None


class StageEventRead(StageEventBase):
    id: int
    application_id: int


# --------------------------------------------------------------------- applications


class ApplicationBase(SQLModel):
    company: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    applied_date: date
    level: Optional[Level] = None
    location: Optional[str] = None
    work_mode: Optional[WorkMode] = None
    source: Optional[Source] = None
    referral: bool = False
    job_url: Optional[str] = None
    salary_min: Optional[int] = Field(default=None, ge=0)
    salary_max: Optional[int] = Field(default=None, ge=0)
    resume_version: Optional[str] = None
    cover_letter: bool = False
    outcome: Outcome = Outcome.active
    # When the outcome happened (rejection / ghosting / withdrawal / offer decision).
    outcome_date: Optional[date] = None
    # Keys of built-in or custom reasons; several can apply to one rejection.
    rejection_reasons: list[str] = json_list()
    missing_required_skills: list[str] = json_list()
    missing_preferred_skills: list[str] = json_list()
    reflection: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None


class Application(ApplicationBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    events: list[StageEvent] = Relationship(
        back_populates="application",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationUpdate(SQLModel):
    company: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role: Optional[str] = Field(default=None, min_length=1, max_length=200)
    applied_date: Optional[date] = None
    level: Optional[Level] = None
    location: Optional[str] = None
    work_mode: Optional[WorkMode] = None
    source: Optional[Source] = None
    referral: Optional[bool] = None
    job_url: Optional[str] = None
    salary_min: Optional[int] = Field(default=None, ge=0)
    salary_max: Optional[int] = Field(default=None, ge=0)
    resume_version: Optional[str] = None
    cover_letter: Optional[bool] = None
    outcome: Optional[Outcome] = None
    outcome_date: Optional[date] = None
    rejection_reasons: Optional[list[str]] = None
    missing_required_skills: Optional[list[str]] = None
    missing_preferred_skills: Optional[list[str]] = None
    reflection: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None


# Fields that may not be cleared to null through PATCH.
NON_NULLABLE_FIELDS = {"company", "role", "applied_date", "referral", "cover_letter", "outcome"}
LIST_FIELDS = {"rejection_reasons", "missing_required_skills", "missing_preferred_skills"}


class ApplicationRead(ApplicationBase):
    id: int
    created_at: datetime
    updated_at: datetime
    current_stage: Stage
    last_activity: date
    days_since_activity: int
    is_stale: bool
    stage_since: date  # last movement in the current stage
    days_in_stage: int
    upcoming_date: Optional[date] = None  # a scheduled step in the current stage
    status: str  # active | pending (open apps) or the outcome
    events: list[StageEventRead] = []


# ------------------------------------------------------------------ rejection reasons


class ReasonOption(SQLModel, table=True):
    """A custom rejection reason the user typed into "Other"."""

    __tablename__ = "reason_option"
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    label: str
    created_at: datetime = Field(default_factory=utcnow)


class ReasonCreate(SQLModel):
    label: str = Field(min_length=1, max_length=80)


class ReasonRead(SQLModel):
    key: str
    label: str
    builtin: bool
    skill_kind: Optional[str] = None  # "required" | "preferred" for the missing-skill reasons
    used: int = 0


# ------------------------------------------------------------------------ quick add


class QuickAddRequest(SQLModel):
    text: str = Field(max_length=20000)
    dry_run: bool = False
    resume_version: Optional[str] = None


# --------------------------------------------------------------------- import/export


class ExportedApplication(ApplicationBase):
    events: list[StageEventBase] = []


class BackupPayload(SQLModel):
    version: int = 2
    custom_reasons: list[dict[str, str]] = []
    applications: list[ExportedApplication]
