from datetime import timedelta

from app.analytics import AppRecord, EventRecord, compute_all, summary, timing, waiting
from app.enums import Outcome, Stage

from .conftest import TODAY
from .helpers import new_app


def rec(i, events, outcome=Outcome.active, applied_ago=30, outcome_ago=None):
    applied = TODAY - timedelta(days=applied_ago)
    evs = [EventRecord(Stage.applied, applied)] + [
        EventRecord(stage, TODAY - timedelta(days=ago) if ago is not None else None) for stage, ago in events
    ]
    od = TODAY - timedelta(days=outcome_ago) if outcome_ago is not None else None
    return AppRecord(i, applied, outcome, [], evs, outcome_date=od, name=f"Co{i} · Role")


def test_active_vs_pending_uses_days_in_current_stage():
    fresh_screen = rec(1, [(Stage.screen, 6)])  # 6 days in screen -> active
    week_screen = rec(2, [(Stage.screen, 7)])  # exactly 7 days -> pending
    old_apply = rec(3, [], applied_ago=10)  # 10 days at applied -> pending
    assert fresh_screen.days_in_stage(TODAY) == 6
    assert fresh_screen.status(TODAY, 7) == "active"
    assert week_screen.status(TODAY, 7) == "pending"
    assert old_apply.status(TODAY, 7) == "pending"
    assert old_apply.status(TODAY, 14) == "active"  # threshold is configurable


def test_repeated_rounds_reset_the_clock():
    # two technical rounds: the latest one (2 days ago) is the last movement
    a = rec(1, [(Stage.screen, 20), (Stage.technical, 12), (Stage.technical, 2)])
    assert a.days_in_stage(TODAY) == 2 and a.status(TODAY, 7) == "active"


def test_closed_applications_are_neither_active_nor_pending():
    a = rec(1, [(Stage.screen, 30)], Outcome.rejected, outcome_ago=20)
    assert a.status(TODAY, 7) == "rejected"
    s = summary([a, rec(2, [(Stage.screen, 1)])], TODAY, 21, 7)
    assert (s["open"], s["active"], s["pending"]) == (1, 1, 0)


def test_waiting_points_and_stage_summary():
    apps = [
        rec(1, [(Stage.screen, 2)]),
        rec(2, [(Stage.screen, 9)]),
        rec(3, [(Stage.screen, 15)]),
        rec(4, [], Outcome.ghosted),
    ]
    w = waiting(apps, TODAY, 7)
    assert len(w["points"]) == 3
    screen = next(r for r in w["by_stage"] if r["stage"] == "screen")
    assert (screen["active"], screen["pending"], screen["median_days"], screen["max_days"]) == (1, 2, 9, 15)
    assert w["points"][0]["name"] == "Co1 · Role"


def test_rejection_timing_from_outcome_date():
    apps = [
        # applied 30d ago, screen 20d ago, rejected 14d ago -> 6 days in screen, 16 since applying
        rec(1, [(Stage.screen, 20)], Outcome.rejected, outcome_ago=14),
        rec(2, [(Stage.screen, 20)], Outcome.rejected, outcome_ago=10),
        rec(3, [], Outcome.rejected),  # no date logged -> ignored
    ]
    t = timing(apps)
    assert t["days_to_rejection"] == {"median": 18.0, "n": 2}
    screen = next(r for r in t["stage_durations"] if r["stage"] == "screen")
    assert screen["median_days_to_rejection"] == 8.0 and screen["rejected_n"] == 2


def test_pending_insight():
    result = compute_all([rec(1, [], applied_ago=10)], TODAY, 21, pending_days=7)
    assert any("pending for 7+ days" in i["title"] for i in result["insights"])
    assert result["pending_days"] == 7


# ------------------------------------------------------------------------ API


def test_outcome_date_defaults_to_today_and_clears_on_reopen(client):
    a = new_app(client)
    r = client.patch(f"/api/applications/{a['id']}", json={"outcome": "rejected"}).json()
    assert r["outcome_date"] == TODAY.isoformat() and r["status"] == "rejected"
    r = client.patch(f"/api/applications/{a['id']}", json={"outcome_date": "2026-05-20"}).json()
    assert r["outcome_date"] == "2026-05-20"
    r = client.patch(f"/api/applications/{a['id']}", json={"outcome": "active"}).json()
    assert r["outcome_date"] is None
    bad = client.patch(
        f"/api/applications/{a['id']}", json={"outcome": "ghosted", "outcome_date": "2026-01-01"}
    )
    assert bad.status_code == 422


def test_stage_event_gets_a_date_and_status_follows(client):
    a = new_app(client, applied_date="2026-05-01")  # 31 days before TODAY
    assert client.get(f"/api/applications/{a['id']}").json()["status"] == "pending"
    e = client.post(f"/api/applications/{a['id']}/events", json={"stage": "screen"}).json()
    assert e["event_date"] == TODAY.isoformat()
    got = client.get(f"/api/applications/{a['id']}").json()
    assert (got["status"], got["days_in_stage"], got["current_stage"]) == ("active", 0, "screen")
    # threshold is a query parameter
    assert client.get("/api/applications", params={"pending_days": 1}).json()[0]["status"] == "active"
    stats = client.get("/api/analytics", params={"pending_days": 7}).json()
    assert stats["summary"]["active"] == 1 and stats["waiting"]["points"][0]["days"] == 0


def test_unfinished_and_cancelled_are_neutral():
    apps = [
        rec(1, [(Stage.assessment, 10)], Outcome.unfinished, outcome_ago=3),
        rec(2, [], Outcome.cancelled, outcome_ago=5),
        rec(3, [(Stage.assessment, 10)], Outcome.rejected, outcome_ago=2),
        rec(4, [(Stage.assessment, 10), (Stage.technical, 2)]),
    ]
    stages = {s["stage"]: s for s in compute_all(apps, TODAY, 21)["stages"]}
    oa = stages["assessment"]
    assert (oa["passed"], oa["failed"], oa["unfinished"], oa["pass_rate"]) == (1, 1, 1, 0.5)
    assert stages["applied"]["cancelled"] == 1 and stages["applied"]["failed"] == 0
    assert apps[0].status(TODAY) == "unfinished" and apps[1].status(TODAY) == "cancelled"
    result = compute_all(apps, TODAY, 21)
    assert result["summary"]["eligible"] == 3  # the cancelled one, never answered, is left out
    assert any("left unfinished" in i["title"] for i in result["insights"])


def test_taken_date_drives_pending_and_scheduled_steps_stay_active():
    # OA received 20 days ago, taken 3 days ago -> clock runs from the taken date
    oa = AppRecord(
        1,
        TODAY - timedelta(days=30),
        events=[
            EventRecord(Stage.applied, TODAY - timedelta(days=30)),
            EventRecord(Stage.assessment, TODAY - timedelta(days=20), taken_date=TODAY - timedelta(days=3)),
        ],
    )
    assert oa.days_in_stage(TODAY) == 3 and oa.status(TODAY, 7) == "active"
    # interview invited 20 days ago, scheduled 5 days from now -> active, not pending/stale
    iv = AppRecord(
        2,
        TODAY - timedelta(days=40),
        events=[
            EventRecord(Stage.applied, TODAY - timedelta(days=40)),
            EventRecord(Stage.technical, TODAY - timedelta(days=25), taken_date=TODAY + timedelta(days=5)),
        ],
    )
    assert iv.upcoming(TODAY) == TODAY + timedelta(days=5)
    assert iv.status(TODAY, 7) == "active" and not iv.is_stale(TODAY, 21)
    # once the date has passed, the clock starts from the interview day
    later = TODAY + timedelta(days=15)
    assert iv.upcoming(later) is None and iv.days_in_stage(later) == 10 and iv.status(later, 7) == "pending"


def test_assessment_timeline():
    from app.analytics import assessments

    apps = [
        # applied 30d ago, OA 25d ago, taken 20d ago, passed to technical 10d ago
        rec(1, [(Stage.assessment, 25), (Stage.technical, 10)]),
        # applied 30d ago, OA 28d ago, not taken
        rec(2, [(Stage.assessment, 28)]),
        rec(3, [(Stage.assessment, 20)], Outcome.rejected, outcome_ago=5),
    ]
    apps[0].events[1].taken_date = TODAY - timedelta(days=20)
    apps[2].events[1].taken_date = TODAY - timedelta(days=15)
    a = assessments(apps, TODAY)
    rows = {r["id"]: r for r in a["rows"]}
    assert (rows[1]["days_to_receive"], rows[1]["days_to_take"], rows[1]["days_to_result"]) == (5, 5, 10)
    assert rows[1]["result"] == "passed"
    assert rows[2]["result"] == "not taken" and rows[2]["days_open"] == 28
    assert (rows[3]["result"], rows[3]["days_to_result"]) == ("rejected", 10)
    assert a["days_to_receive"] == {"median": 5, "n": 3}
    assert (a["passed"], a["decided"], a["pass_rate"], a["not_taken"]) == (1, 2, 0.5, 1)


def test_event_api_accepts_taken_date(client):
    a = new_app(client, applied_date="2026-05-01")
    e = client.post(
        f"/api/applications/{a['id']}/events",
        json={"stage": "webinar", "event_date": "2026-05-25", "taken_date": "2026-06-05"},
    ).json()
    assert e["taken_date"] == "2026-06-05"
    got = client.get(f"/api/applications/{a['id']}").json()
    assert (got["current_stage"], got["upcoming_date"], got["status"]) == ("webinar", "2026-06-05", "active")
