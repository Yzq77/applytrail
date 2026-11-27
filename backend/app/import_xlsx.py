"""Import the "Applied" sheet of an application-tracker workbook into the database.

    python -m app.import_xlsx path/to/tracker.xlsx --dry-run   # preview, writes nothing
    python -m app.import_xlsx path/to/tracker.xlsx             # import into your database

Expected columns: date_applied, category, company, role, location, apply_url,
resume_pdf_used, application_status, follow_up_date, notes.

How rows are mapped
-------------------
* ``application_status`` decides the outcome: "Applied …" stays active, "Rejected …"
  becomes rejected, "Job cancelled …" becomes *Job cancelled*, "OA not finished …" or
  "… not done" becomes *Unfinished*, and other "OA …" / "Interview …" stay active. The first date in the
  status is the outcome date.
* "OA done / finished / completed" entries in the notes set the date you took the OA.
* Stage dates come from the dated ``Outcome YYYY-MM-DD: …`` entries in ``notes``: an
  online assessment or a recorded video interview counts as *Assessment / OA*, an HR,
  recruiter or phone-screen interview as *Recruiter screen*, and any other interview as
  *Technical interview*. The status date is the fallback.
* ``category`` becomes a tag; the seniority level is inferred from the role title.
* An unknown ``date_applied`` falls back to the earliest date known for the row, and the
  row is tagged ``applied-date-unknown``.
* Rows whose link, or company + role, already exist in the database are skipped, so the
  command can be re-run on newer exports. The full original notes and status are kept.
"""

import argparse
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from sqlmodel import Session, select

from .config import db_path
from .db import make_engine
from .enums import Level, Outcome, Stage, WorkMode
from .models import Application, StageEvent
from .quickadd import guess_source

SHEET = "Applied"
REQUIRED_COLUMNS = {"date_applied", "company", "role", "application_status"}
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Each "Outcome YYYY-MM-DD: …" entry, up to (not including) the next one.
OUTCOME_NOTE_RE = re.compile(r"Outcome (\d{4}-\d{2}-\d{2}):\s*((?:(?!Outcome\b).){0,220})", re.IGNORECASE)


@dataclass
class Row:
    line: int
    data: dict
    events: list[tuple[Stage, date]] = field(default_factory=list)
    taken: dict[Stage, date] = field(default_factory=dict)  # when you took/finished a step
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _date(text: str | None) -> date | None:
    m = DATE_RE.search(text or "")
    return date.fromisoformat(m.group()) if m else None


def _stage_for(text: str) -> Stage | None:
    t = text.lower()
    if "reject" in t or "cancel" in t:
        return None
    if "webinar" in t or "info session" in t:
        return Stage.webinar
    if "video" in t or "hirevue" in t or "hireview" in t:
        return Stage.assessment
    if "interview" in t:
        if re.search(r"\bhr\b|recruiter|phone screen|screening call", t):
            return Stage.screen
        return Stage.technical
    if "online assessment" in t or re.search(r"\boa\b", t):
        return Stage.assessment
    return None


def _level(role: str, category: str) -> Level | None:
    r = role.lower()
    if "intern" in r or category.lower() == "internship":
        return Level.intern
    if re.search(r"new grad|early career|graduate|junior|entry|university|campus|20\d\d start", r):
        return Level.entry
    if re.search(r"\bsenior\b|\bsr\.?\b", r):
        return Level.senior
    return None


def _work_mode(location: str) -> WorkMode | None:
    low = location.lower()
    if "remote" in low:
        return WorkMode.remote
    if "hybrid" in low:
        return WorkMode.hybrid
    return None


def parse_row(line: int, raw: dict) -> Row:
    def s(key: str) -> str:
        v = raw.get(key)
        if isinstance(v, datetime):
            return v.date().isoformat()
        return "" if v is None else str(v).strip()

    status, notes, category = s("application_status"), s("notes"), s("category")
    row = Row(line=line, data={})
    kind = status.split(" - ")[0].split(",")[0].strip().lower()
    status_date = _date(status)

    # Stage events from the dated outcome notes; the first date per stage wins.
    found: dict[Stage, date] = {}
    for d, text in OUTCOME_NOTE_RE.findall(notes):
        text = re.split(r"\bOutcome\b", text)[0]  # stop at the next outcome entry
        stage = _stage_for(text)
        if stage:
            inner = _date(text.split(";")[0])  # "…finished yesterday 2026-11-17"
            when = inner if inner and inner <= date.fromisoformat(d) else date.fromisoformat(d)
            found.setdefault(stage, when)

    # "OA done / finished / completed" dates when you took it, even inside an entry that
    # is mainly about the next stage ("OA finished, moved to interview").
    for d, text in OUTCOME_NOTE_RE.findall(notes):
        took = re.search(r"\b(oa|online assessment)\b[^.;|]*\b(done|finished|completed)\b", text, re.I)
        if took and not re.search(r"not (done|finished|completed)|did not finish", text, re.I):
            row.taken.setdefault(Stage.assessment, date.fromisoformat(d))
            found.setdefault(Stage.assessment, date.fromisoformat(d))
    if not found and status_date and (kind.startswith("oa") or kind.startswith("interview")):
        stage = Stage.assessment if kind.startswith("oa") or "video" in status.lower() else Stage.technical
        found[stage] = status_date
    interviewed = Stage.screen in found or Stage.technical in found
    if kind.startswith("interview") and not interviewed and "video" not in status.lower():
        if status_date:
            found[Stage.technical] = status_date
    row.events = sorted(found.items(), key=lambda kv: kv[1])

    # Outcome
    outcome, outcome_date = Outcome.active, None
    if kind.startswith("rejected"):
        outcome = Outcome.rejected
        outcome_date = status_date or _date(
            (re.search(r"Rejected, reported (\d{4}-\d{2}-\d{2})", notes) or [None, None])[1]
        )
        if not outcome_date:
            row.warnings.append("rejection date unknown")
    elif kind.startswith("job cancelled"):
        outcome, outcome_date = Outcome.cancelled, status_date
    elif re.search(r"not finished|not done|did not finish|didn't finish", status, re.I):
        outcome, outcome_date = Outcome.unfinished, status_date
    elif not (kind.startswith("applied") or kind.startswith("oa") or kind.startswith("interview")):
        row.warnings.append(f"unrecognised status '{status}', imported as active")

    # Applied date (fall back to the earliest date we know, and say so).
    tags = [category] if category else []
    applied = _date(s("date_applied"))
    if applied is None:
        known = [d for d in [outcome_date, *found.values()] if d]
        if not known:
            raise ValueError("no usable date_applied and no other date in the row")
        applied = min(known)
        tags.append("applied-date-unknown")
        row.warnings.append(f"date_applied unknown, used {applied}")
    if outcome_date and outcome_date < applied:
        row.warnings.append(f"outcome date {outcome_date} before applied date, moved to {applied}")
        outcome_date = applied

    url = s("apply_url") or None
    role = s("role")
    row.data = {
        "company": s("company"),
        "role": role,
        "applied_date": applied,
        "location": s("location") or None,
        "work_mode": _work_mode(s("location")),
        "level": _level(role, category),
        "job_url": url,
        "source": guess_source(url),
        "resume_version": s("resume_pdf_used") or None,
        "outcome": outcome,
        "outcome_date": outcome_date,
        "rejection_reasons": row.reasons,
        "tags": ", ".join(tags) or None,
        "notes": "\n\n".join(p for p in [notes, f"Original status: {status}"] if p),
    }
    if not row.data["company"] or not row.data["role"]:
        raise ValueError("company and role are required")
    return row


def read_workbook(path: Path) -> list[Row]:
    import openpyxl  # imported lazily: only this command needs it

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if SHEET not in wb.sheetnames:
        raise SystemExit(f"No '{SHEET}' sheet in {path.name} (found: {', '.join(wb.sheetnames)})")
    rows = wb[SHEET].iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]
    missing = REQUIRED_COLUMNS - set(header)
    if missing:
        raise SystemExit(f"'{SHEET}' sheet is missing column(s): {', '.join(sorted(missing))}")
    parsed, errors = [], []
    for line, values in enumerate(rows, start=2):
        raw = dict(zip(header, values, strict=False))
        if not any(v not in (None, "") for v in raw.values()):
            continue
        try:
            parsed.append(parse_row(line, raw))
        except ValueError as exc:
            errors.append(f"row {line}: {exc}")
    if errors:
        raise SystemExit("Nothing imported:\n  " + "\n  ".join(errors))
    return parsed


def import_rows(session: Session, rows: list[Row]) -> tuple[list[Row], list[Row]]:
    existing = session.exec(select(Application)).all()
    urls = {a.job_url.rstrip("/").lower() for a in existing if a.job_url}
    names = {(a.company.casefold(), a.role.casefold()) for a in existing}
    added, skipped = [], []
    for row in rows:
        d = row.data
        if (d["job_url"] and d["job_url"].rstrip("/").lower() in urls) or (
            d["company"].casefold(),
            d["role"].casefold(),
        ) in names:
            skipped.append(row)
            continue
        app = Application.model_validate(d)
        session.add(app)
        session.flush()
        session.add(StageEvent(application_id=app.id, stage=Stage.applied, event_date=app.applied_date))
        for stage, when in row.events:
            received = max(when, app.applied_date)
            taken = row.taken.get(stage)
            session.add(
                StageEvent(
                    application_id=app.id,
                    stage=stage,
                    event_date=received,
                    taken_date=max(taken, received) if taken else None,
                )
            )
        added.append(row)
    return added, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("xlsx", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="parse and report, write nothing")
    args = parser.parse_args()

    rows = read_workbook(args.xlsx)
    target = db_path()
    if not args.dry_run and target.exists():
        backup = target.with_name(f"{target.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(target, backup)
        print(f"Backed up existing database to {backup.name}")

    # A dry run against a database that doesn't exist yet must not create it.
    url = "sqlite://" if args.dry_run and not target.exists() else f"sqlite:///{target}"
    engine = make_engine(url)
    with Session(engine) as session:
        added, skipped = import_rows(session, rows)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()

    outcomes: dict[str, int] = {}
    for r in added:
        outcomes[r.data["outcome"].value] = outcomes.get(r.data["outcome"].value, 0) + 1
    verb = "Would import" if args.dry_run else "Imported"
    print(f"{verb} {len(added)} application(s) into {target.name}: {outcomes}")
    if skipped:
        lines = ", ".join(str(r.line) for r in skipped[:10]) + (" …" if len(skipped) > 10 else "")
        print(f"Skipped {len(skipped)} already in the database (rows {lines})")
    staged = [r for r in added if r.events]
    if staged:
        print("Stage events:")
        for r in staged:
            steps = ", ".join(f"{s.value} {d}" for s, d in r.events)
            print(f"  row {r.line}: {r.data['company']}: {steps} [{r.data['outcome'].value}]")
    for r in added:
        for w in r.warnings:
            print(f"  note, row {r.line} ({r.data['company']}): {w}")


if __name__ == "__main__":
    sys.exit(main())
