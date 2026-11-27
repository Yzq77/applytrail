"""Glue between database rows and the analytics engine / API schemas."""

from datetime import date

from .analytics import NOT_SET, AppRecord, EventRecord
from .enums import LABELS, Level, Outcome, Source, Stage, WorkMode, stage_index
from .models import Application, ApplicationRead, StageEvent, StageEventRead


def _val(x) -> str | None:
    return None if x is None else getattr(x, "value", x)


def sorted_events(app: Application) -> list[StageEvent]:
    return sorted(
        app.events,
        key=lambda e: (stage_index(e.stage), e.event_date or date.min, e.id or 0),
    )


def to_record(app: Application) -> AppRecord:
    source, level, mode = _val(app.source), _val(app.level), _val(app.work_mode)
    return AppRecord(
        id=app.id or 0,
        applied_date=app.applied_date,
        outcome=Outcome(app.outcome),
        outcome_date=app.outcome_date,
        name=f"{app.company} · {app.role}",
        rejection_reasons=list(app.rejection_reasons or []),
        missing_required=list(app.missing_required_skills or []),
        missing_preferred=list(app.missing_preferred_skills or []),
        events=[
            EventRecord(
                stage=Stage(e.stage),
                event_date=e.event_date,
                self_rating=e.self_rating,
                order=e.id or 0,
                taken_date=e.taken_date,
            )
            for e in app.events
        ],
        dims={
            "source": LABELS[Source][source] if source else NOT_SET,
            "referral": "Referral" if app.referral else "No referral",
            "resume_version": (app.resume_version or "").strip() or NOT_SET,
            "cover_letter": "With cover letter" if app.cover_letter else "No cover letter",
            "level": LABELS[Level][level] if level else NOT_SET,
            "work_mode": LABELS[WorkMode][mode] if mode else NOT_SET,
            "applied_month": app.applied_date.strftime("%Y-%m"),
        },
    )


def to_read(app: Application, today: date, ghost_days: int, pending_days: int) -> ApplicationRead:
    rec = to_record(app)
    return ApplicationRead(
        **app.model_dump(),
        events=[StageEventRead.model_validate(e) for e in sorted_events(app)],
        current_stage=rec.current_stage,
        last_activity=rec.last_activity,
        days_since_activity=rec.days_since_activity(today),
        is_stale=rec.is_stale(today, ghost_days),
        stage_since=rec.stage_since(today),
        upcoming_date=rec.upcoming(today),
        days_in_stage=rec.days_in_stage(today),
        status=rec.status(today, pending_days),
    )
