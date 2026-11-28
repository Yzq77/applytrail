from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, or_, select

from ..config import GHOST_DAYS_DEFAULT, PENDING_DAYS_DEFAULT
from ..db import get_session, get_today
from ..enums import Outcome, Stage
from ..models import (
    LIST_FIELDS,
    NON_NULLABLE_FIELDS,
    Application,
    ApplicationCreate,
    ApplicationRead,
    ApplicationUpdate,
    QuickAddRequest,
    StageEvent,
    StageEventCreate,
    StageEventRead,
    StageEventUpdate,
    utcnow,
)
from ..quickadd import clean_url, parse_text
from ..reasons import clean_list, unknown_reasons
from ..services import to_read

router = APIRouter(prefix="/api", tags=["applications"])

SessionDep = Annotated[Session, Depends(get_session)]
TodayDep = Annotated[date, Depends(get_today)]
GhostDays = Annotated[int, Query(ge=1, le=365)]
PendingDays = Annotated[int, Query(ge=1, le=365)]


def _get_app(session: Session, app_id: int) -> Application:
    app = session.get(Application, app_id)
    if app is None:
        raise HTTPException(404, "Application not found")
    return app


@router.get("/applications", response_model=list[ApplicationRead])
def list_applications(
    session: SessionDep,
    today: TodayDep,
    q: Optional[str] = None,
    outcome: Optional[Outcome] = None,
    ghost_days: GhostDays = GHOST_DAYS_DEFAULT,
    pending_days: PendingDays = PENDING_DAYS_DEFAULT,
):
    stmt = select(Application).options(selectinload(Application.events))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                col(Application.company).ilike(like),
                col(Application.role).ilike(like),
                col(Application.tags).ilike(like),
                col(Application.location).ilike(like),
            )
        )
    if outcome:
        stmt = stmt.where(Application.outcome == outcome)
    stmt = stmt.order_by(col(Application.applied_date).desc(), col(Application.id).desc())
    return [to_read(a, today, ghost_days, pending_days) for a in session.exec(stmt).all()]


def _clean_lists(session: Session, data: dict) -> dict:
    """Normalise reason/skill lists and reject unknown reason keys."""
    for key in LIST_FIELDS & data.keys():
        data[key] = clean_list(data[key])
    if bad := unknown_reasons(session, data.get("rejection_reasons", [])):
        raise HTTPException(422, f"Unknown rejection reason(s): {', '.join(bad)}. Add them first.")
    return data


def _insert(session: Session, data: dict) -> Application:
    app = Application.model_validate(data)
    session.add(app)
    session.flush()
    session.add(StageEvent(application_id=app.id, stage=Stage.applied, event_date=app.applied_date))
    return app


@router.post("/applications", response_model=ApplicationRead, status_code=201)
def create_application(payload: ApplicationCreate, session: SessionDep, today: TodayDep):
    app = _insert(session, _clean_lists(session, payload.model_dump()))
    session.commit()
    session.refresh(app)
    return to_read(app, today, GHOST_DAYS_DEFAULT, PENDING_DAYS_DEFAULT)


@router.post("/applications/quick")
def quick_add(payload: QuickAddRequest, session: SessionDep, today: TodayDep):
    """Create applications from 'link, company, job title, date' lines.

    With ``dry_run`` it only returns the parse, which the UI shows as a live preview.
    """
    items = parse_text(payload.text, today)
    existing = session.exec(select(Application)).all()
    by_url = {clean_url(a.job_url).rstrip("/").lower(): a for a in existing if a.job_url}
    by_name = {(a.company.casefold(), a.role.casefold()): a for a in existing}
    for item in items:
        if item.error:
            continue
        dup = (item.job_url and by_url.get(item.job_url.rstrip("/").lower())) or by_name.get(
            (item.company.casefold(), item.role.casefold())
        )
        if dup:
            item.warning = f"Already tracked (applied {dup.applied_date.isoformat()})"

    if payload.dry_run:
        return {"items": [i.to_dict() for i in items], "created": []}
    errors = [{"row": i.line, "error": i.error} for i in items if i.error]
    if not items:
        raise HTTPException(422, "Nothing to add")
    if errors:
        raise HTTPException(422, {"message": "Nothing was added", "errors": errors})

    created = []
    for item in items:
        data = {
            "company": item.company,
            "role": item.role,
            "job_url": item.job_url,
            "applied_date": item.applied_date,
            "source": item.source,
            "resume_version": (payload.resume_version or "").strip() or None,
        }
        created.append(_insert(session, ApplicationCreate.model_validate(data).model_dump()))
    session.commit()
    return {"items": [i.to_dict() for i in items], "created": [a.id for a in created]}


@router.get("/applications/{app_id}", response_model=ApplicationRead)
def get_application(
    app_id: int,
    session: SessionDep,
    today: TodayDep,
    ghost_days: GhostDays = GHOST_DAYS_DEFAULT,
    pending_days: PendingDays = PENDING_DAYS_DEFAULT,
):
    return to_read(_get_app(session, app_id), today, ghost_days, pending_days)


@router.patch("/applications/{app_id}", response_model=ApplicationRead)
def update_application(app_id: int, payload: ApplicationUpdate, session: SessionDep, today: TodayDep):
    app = _get_app(session, app_id)
    data = payload.model_dump(exclude_unset=True)
    for key in NON_NULLABLE_FIELDS:
        if key in data and data[key] is None:
            raise HTTPException(422, f"'{key}' cannot be empty")
    for key in LIST_FIELDS:
        if key in data and data[key] is None:
            data[key] = []
    data = _clean_lists(session, data)

    # Every closed outcome carries a date: default to today when the outcome changes,
    # and clear it when the application is reopened.
    new_outcome = data.get("outcome", app.outcome)
    if new_outcome == Outcome.active:
        data["outcome_date"] = None
    elif "outcome" in data and data["outcome"] != app.outcome and not data.get("outcome_date"):
        data["outcome_date"] = today
    elif "outcome_date" in data and data["outcome_date"] is None:
        data["outcome_date"] = app.outcome_date or today
    applied = data.get("applied_date", app.applied_date)
    if data.get("outcome_date") and data["outcome_date"] < applied:
        raise HTTPException(422, "The outcome date can't be before the application date")

    if "applied_date" in data:
        for e in app.events:
            if e.stage == Stage.applied:
                e.event_date = data["applied_date"]
    app.sqlmodel_update(data)
    app.updated_at = utcnow()
    session.add(app)
    session.commit()
    session.refresh(app)
    return to_read(app, today, GHOST_DAYS_DEFAULT, PENDING_DAYS_DEFAULT)


@router.delete("/applications/{app_id}", status_code=204)
def delete_application(app_id: int, session: SessionDep):
    session.delete(_get_app(session, app_id))
    session.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------------ events


@router.post("/applications/{app_id}/events", response_model=StageEventRead, status_code=201)
def add_event(app_id: int, payload: StageEventCreate, session: SessionDep, today: TodayDep):
    app = _get_app(session, app_id)
    if payload.stage == Stage.applied:
        raise HTTPException(422, "The 'applied' event is created automatically")
    # Every stage gets a date; time-in-stage (active vs pending) is measured from it.
    event = StageEvent.model_validate(
        payload, update={"application_id": app.id, "event_date": payload.event_date or today}
    )
    app.updated_at = utcnow()
    session.add(event)
    session.add(app)
    session.commit()
    session.refresh(event)
    return event


def _get_event(session: Session, event_id: int) -> StageEvent:
    event = session.get(StageEvent, event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    return event


@router.patch("/events/{event_id}", response_model=StageEventRead)
def update_event(event_id: int, payload: StageEventUpdate, session: SessionDep):
    event = _get_event(session, event_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("stage") is None:
        data.pop("stage", None)
    if event.stage == Stage.applied and data.get("stage", Stage.applied) != Stage.applied:
        raise HTTPException(422, "The 'applied' event cannot change stage")
    if event.stage != Stage.applied and data.get("stage") == Stage.applied:
        raise HTTPException(422, "Only one 'applied' event is allowed")
    event.sqlmodel_update(data)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int, session: SessionDep):
    event = _get_event(session, event_id)
    if event.stage == Stage.applied:
        raise HTTPException(422, "The 'applied' event cannot be deleted")
    session.delete(event)
    session.commit()
    return Response(status_code=204)
