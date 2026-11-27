from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select

from ..db import get_session
from ..enums import BUILTIN_REASONS, SKILL_REASONS
from ..models import Application, ReasonCreate, ReasonOption, ReasonRead
from ..reasons import get_or_create_reason, reason_usage

router = APIRouter(prefix="/api", tags=["rejection reasons"])
SessionDep = Annotated[Session, Depends(get_session)]


def _list(session: Session) -> list[ReasonRead]:
    usage = reason_usage(session)
    rows = [
        ReasonRead(key=k, label=v, builtin=True, skill_kind=SKILL_REASONS.get(k), used=usage.get(k, 0))
        for k, v in BUILTIN_REASONS.items()
    ]
    for r in session.exec(select(ReasonOption).order_by(ReasonOption.id)).all():
        rows.append(ReasonRead(key=r.key, label=r.label, builtin=False, used=usage.get(r.key, 0)))
    return rows


@router.get("/reasons", response_model=list[ReasonRead])
def list_reasons(session: SessionDep):
    return _list(session)


@router.post("/reasons", response_model=ReasonRead, status_code=201)
def add_reason(payload: ReasonCreate, session: SessionDep):
    """Add a custom reason, or return the existing one if the label is already known."""
    key = get_or_create_reason(session, payload.label)
    session.commit()
    return next(r for r in _list(session) if r.key == key)


@router.delete("/reasons/{key}", status_code=204)
def delete_reason(key: str, session: SessionDep):
    if key in BUILTIN_REASONS:
        raise HTTPException(422, "Built-in reasons can't be removed")
    option = session.exec(select(ReasonOption).where(ReasonOption.key == key)).first()
    if option is None:
        raise HTTPException(404, "Reason not found")
    if used := reason_usage(session).get(key):
        raise HTTPException(409, f"Used by {used} application(s); remove it from them first")
    session.delete(option)
    session.commit()
    return Response(status_code=204)


@router.get("/skills")
def known_skills(session: SessionDep):
    """Every missing skill logged so far, most frequent first, for autocomplete."""
    counts: Counter[str] = Counter()
    display: dict[str, Counter[str]] = {}
    rows = session.exec(
        select(Application.missing_required_skills, Application.missing_preferred_skills)
    ).all()
    for required, preferred in rows:
        for skill in [*(required or []), *(preferred or [])]:
            counts[skill.casefold()] += 1
            display.setdefault(skill.casefold(), Counter())[skill] += 1
    return [{"skill": display[k].most_common(1)[0][0], "count": n} for k, n in counts.most_common()]
