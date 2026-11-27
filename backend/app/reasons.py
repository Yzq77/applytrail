"""Rejection reasons (built-in + user-defined) and skill-list normalisation."""

import re

from sqlmodel import Session, select

from .enums import BUILTIN_REASONS
from .models import Application, ReasonOption


def clean_list(values: list[str] | None, max_len: int = 80) -> list[str]:
    """Trim, collapse whitespace and drop empty or case-insensitive duplicate entries."""
    out: list[str] = []
    seen: set[str] = set()
    for v in values or []:
        item = re.sub(r"\s+", " ", str(v)).strip()[:max_len]
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            out.append(item)
    return out


def split_skills(text: str) -> list[str]:
    """'Go, Kubernetes; AWS' -> ['Go', 'Kubernetes', 'AWS']"""
    return clean_list(re.split(r"[,;，、\n]", text or ""))


def reason_labels(session: Session) -> dict[str, str]:
    custom = session.exec(select(ReasonOption).order_by(ReasonOption.id)).all()
    return {**BUILTIN_REASONS, **{r.key: r.label for r in custom}}


def unknown_reasons(session: Session, keys: list[str]) -> list[str]:
    labels = reason_labels(session)
    return [k for k in keys if k not in labels]


def _slug(label: str) -> str:
    return re.sub(r"[^\w]+", "_", label.casefold()).strip("_")[:40] or "reason"


def get_or_create_reason(session: Session, label_or_key: str) -> str:
    """Return the key for a reason, matching by key or label (any case), creating it if new."""
    text = re.sub(r"\s+", " ", label_or_key).strip()
    labels = reason_labels(session)
    if text in labels:
        return text
    for key, label in labels.items():
        if label.casefold() == text.casefold():
            return key
    base = key = f"custom_{_slug(text)}"
    n = 2
    while key in labels:
        key, n = f"{base}_{n}", n + 1
    session.add(ReasonOption(key=key, label=text))
    session.flush()
    return key


def reason_usage(session: Session) -> dict[str, int]:
    usage: dict[str, int] = {}
    for reasons in session.exec(select(Application.rejection_reasons)).all():
        for r in reasons or []:
            usage[r] = usage.get(r, 0) + 1
    return usage
