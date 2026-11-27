from datetime import date

import sqlalchemy as sa

from app.analytics import AppRecord, EventRecord, missing_skills, pipeline, rejection_reasons
from app.db import make_engine
from app.enums import Outcome, Stage

from .helpers import new_app

TODAY = date(2026, 6, 1)


def reject(client, app_id, reasons, required=None, preferred=None):
    body = {"outcome": "rejected", "rejection_reasons": reasons}
    if required is not None:
        body["missing_required_skills"] = required
    if preferred is not None:
        body["missing_preferred_skills"] = preferred
    return client.patch(f"/api/applications/{app_id}", json=body)


def test_builtin_reasons_listed(client):
    reasons = client.get("/api/reasons").json()
    assert [r["label"] for r in reasons] == [
        "Missing preferred skill",
        "Missing required skill",
        "OA fail",
        "Interview performance",
        "Job closed when rejected",
        "Has open question in application",
    ]
    assert {r["key"]: r["skill_kind"] for r in reasons if r["skill_kind"]} == {
        "missing_preferred_skill": "preferred",
        "missing_required_skill": "required",
    }


def test_custom_reason_is_added_once_and_reusable(client):
    r = client.post("/api/reasons", json={"label": "  Visa   sponsorship "})
    assert r.status_code == 201
    key = r.json()["key"]
    assert r.json()["label"] == "Visa sponsorship" and not r.json()["builtin"]
    # same label in another case -> same reason, no duplicate
    assert client.post("/api/reasons", json={"label": "visa sponsorship"}).json()["key"] == key
    # typing a built-in label maps to the built-in
    assert client.post("/api/reasons", json={"label": "oa FAIL"}).json()["key"] == "oa_fail"
    assert len(client.get("/api/reasons").json()) == 7

    a = new_app(client)
    assert reject(client, a["id"], ["oa_fail", key]).status_code == 200
    used = {r["key"]: r["used"] for r in client.get("/api/reasons").json()}
    assert used[key] == 1 and used["oa_fail"] == 1

    # in-use custom reasons can't be deleted; unused ones can
    assert client.delete(f"/api/reasons/{key}").status_code == 409
    reject(client, a["id"], ["oa_fail"])
    assert client.delete(f"/api/reasons/{key}").status_code == 204
    assert client.delete("/api/reasons/oa_fail").status_code == 422


def test_unknown_reason_rejected(client):
    a = new_app(client)
    r = reject(client, a["id"], ["made_up"])
    assert r.status_code == 422 and "made_up" in r.json()["detail"]


def test_skills_are_cleaned_and_counted(client):
    a = new_app(client, company="A")
    b = new_app(client, company="B")
    r = reject(client, a["id"], ["missing_required_skill"], required=[" Kubernetes", "go", "kubernetes", ""])
    assert r.json()["missing_required_skills"] == ["Kubernetes", "go"]
    reject(
        client, b["id"], ["missing_preferred_skill", "missing_required_skill"], ["Kubernetes"], ["Terraform"]
    )

    stats = client.get("/api/analytics").json()
    skills = {row["skill"]: row for row in stats["missing_skills"]["rows"]}
    assert skills["Kubernetes"]["required"] == 2 and skills["Kubernetes"]["total"] == 2
    assert skills["Terraform"]["preferred"] == 1
    assert stats["missing_skills"]["rows"][0]["skill"] == "Kubernetes"
    assert client.get("/api/skills").json()[0] == {"skill": "Kubernetes", "count": 2}

    reasons = {row["reason"]: row for row in stats["rejection_reasons"]["rows"]}
    assert reasons["missing_required_skill"]["count"] == 2
    assert reasons["missing_required_skill"]["share"] == 1.0
    assert reasons["missing_required_skill"]["by_stage"]["applied"] == 2


def test_reasons_and_skills_survive_backup_roundtrip(client):
    key = client.post("/api/reasons", json={"label": "Visa sponsorship"}).json()["key"]
    a = new_app(client)
    reject(client, a["id"], [key, "missing_required_skill"], required=["Go"])

    backup = client.get("/api/export/json").json()
    assert backup["custom_reasons"] == [{"key": key, "label": "Visa sponsorship"}]
    client.post("/api/import/json", params={"mode": "replace"}, json=backup)
    restored = client.get("/api/applications").json()[0]
    assert set(restored["rejection_reasons"]) == {key, "missing_required_skill"}
    assert restored["missing_required_skills"] == ["Go"]

    csv_text = client.get("/api/export/csv").text
    assert (
        "Visa sponsorship; Missing required skill" in csv_text or "Missing required skill; Visa" in csv_text
    )
    r = client.post("/api/import/csv", params={"mode": "replace"}, content=csv_text.encode())
    assert r.status_code == 200, r.text
    assert set(client.get("/api/applications").json()[0]["rejection_reasons"]) == {
        key,
        "missing_required_skill",
    }


def test_csv_import_creates_new_reason_labels(client):
    sheet = (
        "company,role,applied_date,outcome,rejection_reasons,missing_required_skills\n"
        'Acme,Dev,2026-04-01,rejected,OA fail; Relocation required,"Go, Rust"\n'
    )
    assert client.post("/api/import/csv", content=sheet.encode()).status_code == 200
    labels = {r["label"]: r["key"] for r in client.get("/api/reasons").json()}
    app = client.get("/api/applications").json()[0]
    assert set(app["rejection_reasons"]) == {"oa_fail", labels["Relocation required"]}
    assert app["missing_required_skills"] == ["Go", "Rust"]


def test_quick_add_preview_then_create(client):
    text = "https://www.linkedin.com/jobs/view/1, Data Analyst, Globex, 2026-05-20\nSWE, Initech"
    preview = client.post("/api/applications/quick", json={"text": text, "dry_run": True}).json()
    assert [i["company"] for i in preview["items"]] == ["Globex", "Initech"]
    assert preview["items"][0]["source"] == "linkedin"
    assert preview["items"][1]["date_defaulted"] is True
    assert preview["created"] == [] and client.get("/api/applications").json() == []

    r = client.post("/api/applications/quick", json={"text": text, "resume_version": "v3"})
    assert len(r.json()["created"]) == 2
    apps = {a["company"]: a for a in client.get("/api/applications").json()}
    assert apps["Globex"]["applied_date"] == "2026-05-20"
    assert apps["Initech"]["applied_date"] == "2026-06-01"  # frozen "today"
    assert apps["Globex"]["resume_version"] == "v3"
    assert [e["stage"] for e in apps["Globex"]["events"]] == ["applied"]

    again = client.post("/api/applications/quick", json={"text": text, "dry_run": True}).json()
    assert all(i["warning"].startswith("Already tracked") for i in again["items"])


def test_quick_add_is_all_or_nothing(client):
    r = client.post("/api/applications/quick", json={"text": "SWE, Acme\njust-one-field"})
    assert r.status_code == 422
    assert r.json()["detail"]["errors"][0]["row"] == 2
    assert client.get("/api/applications").json() == []


def test_pipeline_counts_current_stage_by_status():
    def rec(i, stages, outcome=Outcome.active, days_ago=5):
        applied = date(2026, 6, 1).toordinal() - days_ago
        d = date.fromordinal(applied)
        return AppRecord(
            i, d, outcome, [], [EventRecord(Stage.applied, d), *[EventRecord(s, d) for s in stages]]
        )

    apps = [
        rec(1, []),
        rec(2, [], days_ago=40),
        rec(3, [Stage.screen], Outcome.rejected),
        rec(4, [Stage.screen, Stage.technical]),
        rec(5, [Stage.screen, Stage.technical, Stage.onsite, Stage.offer], Outcome.accepted),
    ]
    rows = {r["stage"]: r for r in pipeline(apps, TODAY, 7)}
    assert rows["applied"]["total"] == 2
    assert rows["applied"]["active"] == 1 and rows["applied"]["pending"] == 1
    assert rows["screen"]["rejected"] == 1
    assert rows["technical"]["active"] == 1
    assert rows["offer"]["accepted"] == 1
    assert sum(r["total"] for r in rows.values()) == len(apps)


def test_reason_and_skill_stats_ignore_non_rejected():
    d = date(2026, 5, 1)
    apps = [
        AppRecord(1, d, Outcome.rejected, ["oa_fail"], [EventRecord(Stage.assessment, d)]),
        AppRecord(2, d, Outcome.rejected, [], []),
        AppRecord(3, d, Outcome.active, ["oa_fail"], [], missing_required=["Go"]),
    ]
    reasons = rejection_reasons(apps)
    assert reasons["rejected"] == 2 and reasons["unlogged"] == 1
    assert reasons["rows"][0]["by_stage"]["assessment"] == 1
    assert missing_skills(apps)["rows"] == []


def test_old_database_gets_new_columns(tmp_path):
    path = tmp_path / "old.db"
    raw = sa.create_engine(f"sqlite:///{path}")
    with raw.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE application (id INTEGER PRIMARY KEY, company VARCHAR NOT NULL, "
                "role VARCHAR NOT NULL, applied_date DATE NOT NULL, referral BOOLEAN NOT NULL DEFAULT 0, "
                "cover_letter BOOLEAN NOT NULL DEFAULT 0, outcome VARCHAR NOT NULL DEFAULT 'active', "
                "created_at DATETIME, updated_at DATETIME)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO application (company, role, applied_date) VALUES ('Old', 'Dev', '2026-01-01')"
            )
        )
    engine = make_engine(f"sqlite:///{path}")
    cols = {c["name"] for c in sa.inspect(engine).get_columns("application")}
    assert {"rejection_reasons", "missing_required_skills", "job_url"} <= cols
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT rejection_reasons FROM application")).scalar() == "[]"
