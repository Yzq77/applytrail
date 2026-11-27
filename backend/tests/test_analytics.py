from datetime import date, timedelta

from app.analytics import (
    AppRecord,
    EventRecord,
    breakdowns,
    calibration,
    compute_all,
    stage_stats,
    summary,
    wilson_interval,
)
from app.enums import Outcome, Stage

TODAY = date(2026, 6, 1)
GHOST = 21


def mk(
    id_: int,
    stages: list[Stage],
    outcome: Outcome = Outcome.active,
    days_ago: int = 60,
    reasons: list[str] | None = None,
    ratings: dict[int, int] | None = None,
    **dims: str,
) -> AppRecord:
    applied = TODAY - timedelta(days=days_ago)
    events = [EventRecord(Stage.applied, applied, order=0)]
    for j, s in enumerate(stages, start=1):
        events.append(EventRecord(s, applied + timedelta(days=7 * j), (ratings or {}).get(j), order=j))
    return AppRecord(id_, applied, outcome, reasons or [], events, dims)


def by_stage(rows):
    return {r["stage"]: r for r in rows}


def test_fresh_application_is_not_counted_against_you():
    apps = [mk(1, [], days_ago=3)]
    s = summary(apps, TODAY, GHOST)
    assert s["eligible"] == 0
    assert s["response_rate"] is None
    assert s["active"] == 1


def test_silent_application_becomes_likely_ghosted():
    apps = [mk(1, [], days_ago=40)]
    s = summary(apps, TODAY, GHOST)
    assert s["stale"] == 1 and s["eligible"] == 1
    assert s["response_rate"] == 0
    assert s["ghost_rate"] == 1
    st = by_stage(stage_stats(apps, TODAY, GHOST))
    assert st["applied"]["likely_ghosted"] == 1
    assert st["applied"]["pass_rate"] == 0


def test_stage_pass_rates_only_count_apps_that_went_through_the_stage():
    apps = [
        # skipped assessment, failed technical
        mk(1, [Stage.screen, Stage.technical], Outcome.rejected, reasons=["missing_required_skill"]),
        # assessment, passed technical, onsite pending (recent activity)
        mk(2, [Stage.screen, Stage.assessment, Stage.technical, Stage.onsite], days_ago=30),
        # rejected at screen
        mk(3, [Stage.screen], Outcome.rejected, reasons=["job_closed"]),
        # ghosted after applying
        mk(4, [], Outcome.ghosted),
    ]
    st = by_stage(stage_stats(apps, TODAY, GHOST))
    assert st["applied"]["through"] == 4
    assert st["applied"]["passed"] == 3 and st["applied"]["failed"] == 1
    assert st["screen"]["passed"] == 2 and st["screen"]["failed"] == 1
    # only app 2 logged an assessment
    assert st["assessment"]["through"] == 1 and st["assessment"]["pass_rate"] == 1
    assert st["technical"]["passed"] == 1 and st["technical"]["failed"] == 1
    assert st["technical"]["reasons"][0]["reason"] == "missing_required_skill"
    assert st["onsite"]["pending"] == 1 and st["onsite"]["pass_rate"] is None


def test_accepted_offer_implies_offer_stage():
    a = mk(1, [Stage.screen], Outcome.accepted)
    assert a.current_stage == Stage.offer
    assert summary([a], TODAY, GHOST)["offers"] == 1


def test_breakdown_groups_and_low_sample_flag():
    apps = [mk(i, [Stage.screen], Outcome.rejected, referral="Referral") for i in range(5)]
    apps += [mk(10 + i, [], Outcome.ghosted, referral="No referral") for i in range(2)]
    rows = {r["value"]: r for r in breakdowns(apps, TODAY, GHOST)["referral"]["rows"]}
    assert rows["Referral"]["response_rate"] == 1 and not rows["Referral"]["low_sample"]
    assert rows["No referral"]["response_rate"] == 0 and rows["No referral"]["low_sample"]
    assert breakdowns(apps, TODAY, GHOST)["source"]["rows"][0]["value"] == "(not set)"


def test_calibration_handles_repeated_rounds():
    # two technical rounds: first passed (there is a later event), second failed
    a = mk(
        1,
        [Stage.screen, Stage.technical, Stage.technical],
        Outcome.rejected,
        ratings={1: 3, 2: 4, 3: 5},
    )
    calib = {c["rating"]: c for c in calibration([a], TODAY, GHOST)}
    assert calib[3]["passed"] == 1
    assert calib[4]["passed"] == 1
    assert calib[5]["failed"] == 1 and calib[5]["passed"] == 0


def test_wilson_interval_bounds():
    lo, hi = wilson_interval(0, 10)
    assert lo == 0 and 0.2 < hi < 0.35
    assert wilson_interval(0, 0) is None


def test_insights_find_the_bottleneck():
    apps = [
        mk(i, [Stage.screen, Stage.technical], Outcome.rejected, reasons=["interview_performance"])
        for i in range(6)
    ]
    apps += [
        mk(10 + i, [Stage.screen, Stage.technical, Stage.onsite], Outcome.rejected, reasons=["open_question"])
        for i in range(2)
    ]
    result = compute_all(apps, TODAY, GHOST)
    first = result["insights"][0]
    assert first["severity"] == "warning"
    assert "Technical interview" in first["title"]
    assert "interview performance" in first["detail"]


def test_empty_dataset():
    result = compute_all([], TODAY, GHOST)
    assert result["summary"]["total"] == 0
    assert result["activity"] == []
    assert result["insights"][0]["title"] == "No data yet"


def test_funnel_counts_only_stages_actually_gone_through():
    from app.analytics import funnel

    apps = [
        mk(1, [Stage.screen]),  # had a recruiter screen
        mk(2, [Stage.assessment]),  # OA straight after applying, no screen
        mk(3, [Stage.assessment, Stage.technical]),
        mk(4, []),
    ]
    rows = {r["stage"]: r for r in funnel(apps)}
    assert rows["applied"]["reached"] == 4
    assert (rows["screen"]["reached"], rows["screen"]["skipped"], rows["screen"]["reached_or_later"]) == (
        1,
        2,
        3,
    )
    assert (rows["assessment"]["reached"], rows["assessment"]["skipped"]) == (2, 0)
    assert (rows["technical"]["reached"], rows["technical"]["skipped"]) == (1, 0)
    accepted = mk(5, [Stage.screen], Outcome.accepted)  # offer implied by the outcome
    assert {r["stage"]: r for r in funnel([accepted])}["offer"]["reached"] == 1
