"""Importer tests on synthetic rows (no real data)."""

from datetime import date
from pathlib import Path

import openpyxl
from sqlmodel import Session, select

from app.db import make_engine
from app.enums import Level, Outcome, Stage, WorkMode
from app.import_xlsx import import_rows, parse_row, read_workbook
from app.models import Application

HEADER = [
    "date_applied", "category", "company", "role", "location", "apply_url",
    "resume_pdf_used", "application_status", "follow_up_date", "notes",
]  # fmt: skip


def row(**kw):
    base = dict.fromkeys(HEADER)
    base.update(date_applied="2026-11-01", category="SDE", company="Acme", role="Software Engineer, New Grad")
    base["application_status"] = "Applied - user reported 2026-11-01"
    base.update(kw)
    return base


def test_applied_row():
    r = parse_row(2, row(location="Remote in USA", apply_url="https://jobs.lever.co/acme/1"))
    d = r.data
    assert (d["outcome"], d["outcome_date"], d["applied_date"]) == (Outcome.active, None, date(2026, 11, 1))
    assert (d["level"], d["work_mode"], d["source"], d["tags"]) == (
        Level.entry,
        WorkMode.remote,
        "company_site",
        "SDE",
    )
    assert r.events == [] and "Original status: Applied" in d["notes"]


def test_rejected_after_oa_from_notes():
    notes = (
        'Outcome 2026-11-03: online assessment reported (shorthand "x oa"). | '
        "Outcome 2026-11-10: OA done. Outcome: REJECTED after OA, user reported 2026-11-12"
    )
    r = parse_row(2, row(application_status="Rejected - user reported 2026-11-12", notes=notes))
    assert r.data["outcome"] == Outcome.rejected and r.data["outcome_date"] == date(2026, 11, 12)
    assert r.events == [(Stage.assessment, date(2026, 11, 3))]
    assert r.taken == {Stage.assessment: date(2026, 11, 10)}


def test_interviews_video_and_cancelled():
    two_stages = parse_row(
        2,
        row(
            application_status="Interview - first round finished 2026-11-17 (user reported 2026-11-18)",
            notes="Outcome 2026-11-03: online assessment finished. Outcome 2026-11-18: first round "
            "interview finished yesterday 2026-11-17 (shorthand)",
        ),
    )
    assert two_stages.events == [(Stage.assessment, date(2026, 11, 3)), (Stage.technical, date(2026, 11, 17))]
    assert two_stages.data["outcome"] == Outcome.active

    video = parse_row(
        2,
        row(
            application_status="Interview - video not done, user reported 2026-11-25",
            notes="Outcome 2026-11-03: interview stage reported; format per user: 2 video recordings",
        ),
    )
    assert video.events == [(Stage.assessment, date(2026, 11, 3))]
    assert (video.data["outcome"], video.data["outcome_date"]) == (Outcome.unfinished, date(2026, 11, 25))

    hr = parse_row(
        2,
        row(
            application_status="Interview - user reported 2026-11-03",
            notes="Outcome 2026-11-03: HR interview scheduled",
        ),
    )
    assert hr.events == [(Stage.screen, date(2026, 11, 3))]

    plain = parse_row(2, row(application_status="Interview - user reported 2026-11-11"))
    assert plain.events == [(Stage.technical, date(2026, 11, 11))]

    cancelled = parse_row(2, row(application_status="Job cancelled - user reported 2026-11-18"))
    assert cancelled.data["outcome"] == Outcome.cancelled
    assert cancelled.data["rejection_reasons"] == []

    oa = parse_row(2, row(application_status="OA not finished - user reported 2026-11-18"))
    assert oa.data["outcome"] == Outcome.unfinished and oa.events == [(Stage.assessment, date(2026, 11, 18))]


def test_unknown_applied_date_and_undated_rejection():
    r = parse_row(2, row(date_applied="unknown", application_status="Rejected - user reported 2026-11-04"))
    assert r.data["applied_date"] == date(2026, 11, 4)
    assert "applied-date-unknown" in r.data["tags"] and r.warnings

    r = parse_row(2, row(application_status="Rejected", notes="Rejected, reported 2026-11-23, no OA stage"))
    assert r.data["outcome_date"] == date(2026, 11, 23) and r.events == []


def test_workbook_import_is_rerunnable(tmp_path: Path):
    wb = openpyxl.Workbook()
    wb.active.title = "Summary"
    ws = wb.create_sheet("Applied")
    ws.append(HEADER)
    for i, status in enumerate(["Applied - user reported 2026-11-01", "OA - user reported 2026-11-05"]):
        r = row(company=f"Co{i}", apply_url=f"https://x.io/{i}", application_status=status)
        ws.append([r[h] for h in HEADER])
    path = tmp_path / "tracker.xlsx"
    wb.save(path)

    engine = make_engine("sqlite://")
    rows = read_workbook(path)
    with Session(engine) as s:
        added, skipped = import_rows(s, rows)
        s.commit()
        assert (len(added), len(skipped)) == (2, 0)
        added, skipped = import_rows(s, read_workbook(path))
        assert (len(added), len(skipped)) == (0, 2)
        oa = s.exec(select(Application).where(Application.company == "Co1")).one()
        assert sorted(e.stage for e in oa.events) == [Stage.applied, Stage.assessment]


def test_webinar_and_unfinished_oa_has_no_taken_date():
    r = parse_row(2, row(notes="Outcome 2026-11-20: moved to webinar stage"))
    assert r.events == [(Stage.webinar, date(2026, 11, 20))]
    r = parse_row(
        2,
        row(
            application_status="OA not finished - user reported 2026-11-18",
            notes="Outcome 2026-11-18: online assessment reported. Outcome 2026-11-25: OA did NOT finish",
        ),
    )
    assert r.taken == {}
