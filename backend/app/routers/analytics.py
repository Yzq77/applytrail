from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from ..analytics import compute_all
from ..config import DEMO_MODE, GHOST_DAYS_DEFAULT, PENDING_DAYS_DEFAULT, db_path
from ..db import get_session, get_today
from ..enums import Level, Outcome, Source, Stage, WorkMode, options
from ..models import Application
from ..reasons import reason_labels
from ..services import to_record

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics")
def get_analytics(
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(get_today)],
    ghost_days: Annotated[int, Query(ge=1, le=365)] = GHOST_DAYS_DEFAULT,
    pending_days: Annotated[int, Query(ge=1, le=365)] = PENDING_DAYS_DEFAULT,
):
    apps = session.exec(select(Application).options(selectinload(Application.events))).all()
    records = [to_record(a) for a in apps]
    return compute_all(records, today, ghost_days, reason_labels(session), pending_days=pending_days)


@router.get("/meta")
def get_meta():
    return {
        "stages": options(Stage),
        "outcomes": options(Outcome),
        "sources": options(Source),
        "levels": options(Level),
        "work_modes": options(WorkMode),
        "demo": DEMO_MODE,
        "db_file": db_path().name,
        "ghost_days_default": GHOST_DAYS_DEFAULT,
        "pending_days_default": PENDING_DAYS_DEFAULT,
    }
