"""Backup / restore (JSON) and spreadsheet interchange (CSV)."""

import csv
import io
import json
from datetime import date
from enum import Enum
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ValidationError
from sqlalchemy.orm import selectinload
from sqlmodel import Session, delete, select

from ..db import get_session
from ..enums import LABELS, STAGE_ORDER, Level, Outcome, Source, Stage, WorkMode
from ..models import (
    LIST_FIELDS,
    Application,
    ApplicationBase,
    BackupPayload,
    ExportedApplication,
    StageEvent,
    StageEventBase,
)
from ..reasons import clean_list, get_or_create_reason, reason_labels, split_skills
from ..services import sorted_events, to_record

router = APIRouter(prefix="/api", tags=["import/export"])
SessionDep = Annotated[Session, Depends(get_session)]
Mode = Literal["append", "replace"]

BASE_FIELDS = list(ApplicationBase.model_fields)
ENUM_FIELDS: dict[str, type[Enum]] = {
    "level": Level,
    "work_mode": WorkMode,
    "source": Source,
    "outcome": Outcome,
}
BOOL_FIELDS = {"referral", "cover_letter"}
STAGE_DATE_COLS = {f"{s.value}_date": s for s in STAGE_ORDER}


def _all_apps(session: Session) -> list[Application]:
    stmt = select(Application).options(selectinload(Application.events)).order_by(Application.id)
    return list(session.exec(stmt).all())


def _download(content: str, filename: str, media_type: str) -> Response:
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _store(session: Session, items: list[ExportedApplication], mode: Mode) -> int:
    if mode == "replace":
        session.exec(delete(StageEvent))
        session.exec(delete(Application))
    for item in items:
        data = item.model_dump(exclude={"events"})
        # Reasons may arrive as keys or labels; unknown ones become custom reasons.
        data["rejection_reasons"] = [
            get_or_create_reason(session, r) for r in clean_list(data["rejection_reasons"])
        ]
        data["missing_required_skills"] = clean_list(data["missing_required_skills"])
        data["missing_preferred_skills"] = clean_list(data["missing_preferred_skills"])
        app = Application.model_validate(data)
        session.add(app)
        session.flush()
        events = list(item.events)
        if not any(e.stage == Stage.applied for e in events):
            events.insert(0, StageEventBase(stage=Stage.applied, event_date=app.applied_date))
        for e in events:
            session.add(StageEvent.model_validate(e, update={"application_id": app.id}))
    session.commit()
    return len(items)


# --------------------------------------------------------------------------- JSON


@router.get("/export/json")
def export_json(session: SessionDep):
    labels = reason_labels(session)
    payload = {
        "version": 2,
        "exported_on": date.today().isoformat(),
        "custom_reasons": [{"key": k, "label": v} for k, v in labels.items() if k.startswith("custom_")],
        "applications": [
            {
                **a.model_dump(mode="json", exclude={"id", "created_at", "updated_at"}),
                "events": [
                    e.model_dump(mode="json", exclude={"id", "application_id"}) for e in sorted_events(a)
                ],
            }
            for a in _all_apps(session)
        ],
    }
    return _download(
        json.dumps(payload, indent=2, ensure_ascii=False),
        f"applytrail-backup-{date.today()}.json",
        "application/json",
    )


@router.post("/import/json")
def import_json(payload: BackupPayload, session: SessionDep, mode: Mode = "append"):
    # Recreate custom reasons first so their keys resolve; a label that already
    # exists under another key is remapped to that key.
    remap: dict[str, str] = {}
    for r in payload.custom_reasons:
        if r.get("key") and r.get("label"):
            remap[r["key"]] = get_or_create_reason(session, r["label"])
    for item in payload.applications:
        item.rejection_reasons = [remap.get(k, k) for k in item.rejection_reasons]
    return {"imported": _store(session, payload.applications, mode), "errors": []}


# ---------------------------------------------------------------------------- CSV


@router.get("/export/csv")
def export_csv(session: SessionDep):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([*BASE_FIELDS, "current_stage", *STAGE_DATE_COLS])
    labels = reason_labels(session)
    for a in _all_apps(session):
        firsts: dict[Stage, date | None] = {}
        for e in sorted_events(a):
            if Stage(e.stage) not in firsts or firsts[Stage(e.stage)] is None:
                firsts[Stage(e.stage)] = e.event_date
        row = []
        for f in BASE_FIELDS:
            v = getattr(a, f)
            if f == "rejection_reasons":
                v = "; ".join(labels.get(k, k) for k in v or [])
            elif f in LIST_FIELDS:
                v = "; ".join(v or [])
            row.append("" if v is None else getattr(v, "value", v))
        row.append(to_record(a).current_stage.value)
        for stage in STAGE_DATE_COLS.values():
            d = firsts.get(stage)
            row.append(d.isoformat() if d else "")
        writer.writerow(row)
    return _download(buf.getvalue(), f"applytrail-{date.today()}.csv", "text/csv")


def _coerce_enum(enum_cls: type[Enum], raw: str) -> str:
    """Accept either the value ('linkedin') or the label ('LinkedIn'), any case."""
    key = raw.strip().lower()
    for member in enum_cls:
        if key in (member.value.lower(), LABELS[enum_cls][member.value].lower()):
            return member.value
    raise ValueError(f"'{raw}' is not one of {[m.value for m in enum_cls]}")


def _parse_row(row: dict[str, str]) -> ExportedApplication:
    clean = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
    data: dict = {}
    for f in BASE_FIELDS:
        raw = clean.get(f, "")
        if raw == "":
            continue
        if f in ENUM_FIELDS:
            data[f] = _coerce_enum(ENUM_FIELDS[f], raw)
        elif f in BOOL_FIELDS:
            data[f] = raw.lower() in {"1", "true", "yes", "y", "x"}
        elif f == "rejection_reasons":
            data[f] = clean_list(raw.split(";"))  # labels may contain commas, so ';' only
        elif f in LIST_FIELDS:
            data[f] = split_skills(raw)
        else:
            data[f] = raw
    base = ApplicationBase.model_validate(data)

    events = [
        StageEventBase(stage=stage, event_date=date.fromisoformat(clean[col]))
        for col, stage in STAGE_DATE_COLS.items()
        if clean.get(col)
    ]
    current = clean.get("current_stage")
    if current:
        stage = Stage(_coerce_enum(Stage, current))
        if stage != Stage.applied and not any(e.stage == stage for e in events):
            events.append(StageEventBase(stage=stage))
    return ExportedApplication(**base.model_dump(), events=events)


@router.post("/import/csv")
async def import_csv(request: Request, session: SessionDep, mode: Mode = "append"):
    text = (await request.body()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    missing = {"company", "role", "applied_date"} - set(reader.fieldnames or [])
    if missing:
        raise HTTPException(422, f"CSV is missing required column(s): {', '.join(sorted(missing))}")

    items, errors = [], []
    for line_no, row in enumerate(reader, start=2):
        try:
            items.append(_parse_row(row))
        except (ValidationError, ValueError) as exc:
            errors.append({"row": line_no, "error": str(exc).splitlines()[0]})
    if errors:
        # All-or-nothing: never half-import a spreadsheet.
        raise HTTPException(422, {"message": "Nothing was imported", "errors": errors})
    return {"imported": _store(session, items, mode), "errors": []}
