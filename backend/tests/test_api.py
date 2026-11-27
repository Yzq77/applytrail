from .helpers import new_app


def test_create_adds_applied_event(client):
    a = new_app(client, source="linkedin", referral=True)
    assert a["current_stage"] == "applied"
    assert [e["stage"] for e in a["events"]] == ["applied"]
    assert a["events"][0]["event_date"] == "2026-05-01"
    assert a["is_stale"] is True  # 31 days, nothing heard


def test_progress_and_reject(client):
    a = new_app(client)
    r = client.post(
        f"/api/applications/{a['id']}/events",
        json={"stage": "screen", "event_date": "2026-05-10", "self_rating": 4},
    )
    assert r.status_code == 201
    r = client.patch(
        f"/api/applications/{a['id']}",
        json={"outcome": "rejected", "rejection_reasons": ["job_closed", "oa_fail"]},
    )
    body = r.json()
    assert body["current_stage"] == "screen" and body["outcome"] == "rejected"

    stats = client.get("/api/analytics").json()
    screen = next(s for s in stats["stages"] if s["stage"] == "screen")
    assert screen["rejected"] == 1
    assert {r["reason"] for r in screen["reasons"]} == {"job_closed", "oa_fail"}


def test_validation(client):
    assert (
        client.post(
            "/api/applications", json={"company": "", "role": "x", "applied_date": "2026-01-01"}
        ).status_code
        == 422
    )
    a = new_app(client)
    assert client.patch(f"/api/applications/{a['id']}", json={"company": None}).status_code == 422
    assert client.post(f"/api/applications/{a['id']}/events", json={"stage": "applied"}).status_code == 422
    applied_id = a["events"][0]["id"]
    assert client.delete(f"/api/events/{applied_id}").status_code == 422


def test_changing_applied_date_moves_applied_event(client):
    a = new_app(client)
    b = client.patch(f"/api/applications/{a['id']}", json={"applied_date": "2026-05-20"}).json()
    assert b["events"][0]["event_date"] == "2026-05-20"


def test_delete_cascades(client):
    a = new_app(client)
    client.post(f"/api/applications/{a['id']}/events", json={"stage": "screen"})
    assert client.delete(f"/api/applications/{a['id']}").status_code == 204
    assert client.get("/api/applications").json() == []


def test_search(client):
    new_app(client, company="Alpha", tags="dream")
    new_app(client, company="Beta")
    assert [a["company"] for a in client.get("/api/applications", params={"q": "dre"}).json()] == ["Alpha"]


def test_json_roundtrip(client):
    a = new_app(client, source="recruiter")
    client.post(
        f"/api/applications/{a['id']}/events",
        json={"stage": "technical", "event_date": "2026-05-12", "notes": "graphs"},
    )
    backup = client.get("/api/export/json").json()
    r = client.post("/api/import/json", params={"mode": "replace"}, json=backup)
    assert r.json()["imported"] == 1
    apps = client.get("/api/applications").json()
    assert len(apps) == 1
    assert [e["stage"] for e in apps[0]["events"]] == ["applied", "technical"]
    assert apps[0]["events"][1]["notes"] == "graphs"


def test_csv_roundtrip_and_labels(client):
    a = new_app(client, source="linkedin")
    client.post(f"/api/applications/{a['id']}/events", json={"stage": "screen", "event_date": "2026-05-09"})
    csv_text = client.get("/api/export/csv").text
    assert "screen_date" in csv_text.splitlines()[0]

    r = client.post("/api/import/csv", params={"mode": "replace"}, content=csv_text.encode())
    assert r.status_code == 200, r.text
    apps = client.get("/api/applications").json()
    assert apps[0]["current_stage"] == "screen"

    # labels and loose spreadsheet values are accepted
    sheet = (
        "company,role,applied_date,source,referral,current_stage\n"
        "Acme,Dev,2026-04-01,LinkedIn,yes,Technical interview\n"
    )
    r = client.post("/api/import/csv", content=sheet.encode())
    assert r.status_code == 200, r.text
    acme = next(x for x in client.get("/api/applications").json() if x["company"] == "Acme")
    assert acme["source"] == "linkedin" and acme["referral"] is True
    assert acme["current_stage"] == "technical"


def test_csv_import_is_all_or_nothing(client):
    sheet = "company,role,applied_date\nGood,Dev,2026-04-01\nBad,Dev,not-a-date\n"
    r = client.post("/api/import/csv", content=sheet.encode())
    assert r.status_code == 422
    assert r.json()["detail"]["errors"][0]["row"] == 3
    assert client.get("/api/applications").json() == []
