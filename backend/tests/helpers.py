def new_app(client, **overrides):
    body = {"company": "Example Co", "role": "Engineer", "applied_date": "2026-05-01", **overrides}
    r = client.post("/api/applications", json=body)
    assert r.status_code == 201, r.text
    return r.json()
