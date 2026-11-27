"""Pure-Python analytics over job applications.

Nothing in here touches the database: the API converts rows into ``AppRecord``s
and hands them over, which keeps every metric easy to unit-test.

Definitions used throughout
---------------------------
* **max stage** - the furthest stage an application has a logged event for
  (an accepted/declined outcome implies the offer stage).
* **stale** - still ``active`` but no activity for ``ghost_days``; treated as
  *likely ghosted* so silent applications don't inflate your success rates.
* **eligible** - applications old enough to judge: they progressed, were
  rejected/ghosted, or went stale. Fresh applications still waiting for a
  reply are left out of rates.
* **stage pass rate** - of the applications that actually went *through* a
  stage (have an event for it) and have a decision, the share that moved on.
* **active / pending** - an open application is *active* while its current stage
  has moved within ``pending_days`` (default 7), and *pending* after that.
  Time in stage is measured from the last movement at the current stage: the date
  you took the step (e.g. the OA) if you have, otherwise the date you received it.
  A step scheduled in the future (interview, webinar) keeps the application active.
* **neutral outcomes** - withdrew, unfinished (you didn't complete a step) and job
  cancelled (the employer pulled the role) close an application without counting as
  a company's rejection, so they're left out of pass rates and shown separately.
* **rejection reasons** - multi-select, so one rejection can count towards
  several reasons; shares are "% of rejections that cite this reason".
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

from .enums import BUILTIN_REASONS, LABELS, STAGE_ORDER, Outcome, Stage, stage_index

OFFER_IDX = stage_index(Stage.offer)
TECHNICAL_IDX = stage_index(Stage.technical)
FAILED_OUTCOMES = {Outcome.rejected, Outcome.ghosted}
NOT_SET = "(not set)"

PENDING_DAYS = 7
MIN_GROUP_N = 5  # smallest group we draw comparisons from
MIN_STAGE_N = 3  # smallest number of decisions before ranking a stage

DIMENSIONS: dict[str, str] = {
    "source": "Source",
    "referral": "Referral",
    "resume_version": "Resume version",
    "cover_letter": "Cover letter",
    "level": "Level",
    "work_mode": "Work mode",
    "applied_month": "Month applied",
}

STAGE_ADVICE: dict[Stage, str] = {
    Stage.applied: (
        "This is a targeting/resume problem, not an interview problem. Tailor the resume to "
        "each posting's keywords, quantify impact, apply within the first days of a posting, "
        "and push for referrals."
    ),
    Stage.webinar: (
        "Applications end after the webinar / info session. Attend live, ask a specific "
        "question, and follow up with the recruiter afterwards to stand out."
    ),
    Stage.screen: (
        "Recruiter screens filter on pitch, motivation and logistics. Rehearse a 60-second "
        "story, research the company, and have clear answers on salary, location and visa."
    ),
    Stage.assessment: (
        "Online assessments are a practice problem: do timed sets on the same platforms and "
        "difficulty, and review the question types you missed."
    ),
    Stage.technical: (
        "Technical rounds are the bottleneck. Review the notes you logged for these "
        "interviews, practice thinking out loud, and drill the weak topics they reveal."
    ),
    Stage.onsite: (
        "You get to the final round but don't close. Prepare STAR stories for behavioral "
        "questions, practise system design, and ask for feedback after each loop."
    ),
}


# ----------------------------------------------------------------------- records


@dataclass
class EventRecord:
    stage: Stage
    event_date: date | None = None
    self_rating: int | None = None
    order: int = 0  # tie-breaker, usually the database id
    taken_date: date | None = None  # when you took it / it took place; future = scheduled


@dataclass
class AppRecord:
    id: int
    applied_date: date
    outcome: Outcome = Outcome.active
    rejection_reasons: list[str] = field(default_factory=list)
    events: list[EventRecord] = field(default_factory=list)
    dims: dict[str, str] = field(default_factory=dict)
    missing_required: list[str] = field(default_factory=list)
    missing_preferred: list[str] = field(default_factory=list)
    outcome_date: date | None = None
    name: str = ""  # "Company · Role", for chart tooltips

    @property
    def max_idx(self) -> int:
        idx = max((stage_index(e.stage) for e in self.events), default=0)
        if self.outcome in (Outcome.accepted, Outcome.declined):
            idx = max(idx, OFFER_IDX)
        return idx

    @property
    def current_stage(self) -> Stage:
        return STAGE_ORDER[self.max_idx]

    @property
    def stages_seen(self) -> set[int]:
        return {0} | {stage_index(e.stage) for e in self.events}

    @property
    def last_activity(self) -> date:
        dates = [e.event_date for e in self.events if e.event_date]
        if self.outcome_date:
            dates.append(self.outcome_date)
        return max([self.applied_date, *dates])

    def _current_events(self) -> list[EventRecord]:
        return [e for e in self.events if stage_index(e.stage) == self.max_idx]

    def stage_since(self, today: date | None = None) -> date:
        """Last movement in the current stage: when you took it if you have, else when received.

        Taken dates in the future (scheduled) don't count yet.
        """
        moves = []
        for e in self._current_events():
            if e.taken_date and (today is None or e.taken_date <= today):
                moves.append(e.taken_date)
            elif e.event_date:
                moves.append(e.event_date)
        if moves:
            return max(moves)
        dated = [e.event_date for e in self.events if e.event_date]
        return max([self.applied_date, *dated])

    def upcoming(self, today: date) -> date | None:
        """The next scheduled step (future taken date) in the current stage, if any."""
        future = [e.taken_date for e in self._current_events() if e.taken_date and e.taken_date > today]
        return min(future) if future else None

    def days_in_stage(self, today: date) -> int:
        return max(0, (today - self.stage_since(today)).days)

    def is_pending(self, today: date, pending_days: int) -> bool:
        return (
            self.outcome == Outcome.active
            and self.upcoming(today) is None
            and self.days_in_stage(today) >= pending_days
        )

    def days_since_activity(self, today: date) -> int:
        return (today - self.last_activity).days

    def is_stale(self, today: date, ghost_days: int) -> bool:
        return (
            self.outcome == Outcome.active
            and self.max_idx < OFFER_IDX
            and self.upcoming(today) is None
            and (today - self.stage_since(today)).days >= ghost_days
        )

    def ended_failed(self, today: date, ghost_days: int) -> bool:
        return self.outcome in FAILED_OUTCOMES or self.is_stale(today, ghost_days)

    def is_eligible(self, today: date, ghost_days: int) -> bool:
        return self.max_idx > 0 or self.ended_failed(today, ghost_days)

    def status(self, today: date, pending_days: int = PENDING_DAYS) -> str:
        """Where this application stands right now: active / pending, or how it ended."""
        if self.outcome == Outcome.accepted:
            return "accepted"
        if self.outcome in (Outcome.withdrawn, Outcome.declined):
            return "withdrawn"
        if self.outcome in (Outcome.unfinished, Outcome.cancelled):
            return self.outcome.value
        if self.outcome in (Outcome.rejected, Outcome.ghosted):
            return self.outcome.value
        return "pending" if self.is_pending(today, pending_days) else "active"

    def first_response_date(self) -> date | None:
        dates = [e.event_date for e in self.events if stage_index(e.stage) > 0 and e.event_date]
        return min(dates) if dates else None

    def sorted_events(self) -> list[EventRecord]:
        return sorted(
            self.events,
            key=lambda e: (stage_index(e.stage), e.event_date or date.min, e.order),
        )


# ----------------------------------------------------------------------- helpers


def rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval: honest error bars for small samples."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def stage_label(stage: Stage | str) -> str:
    return LABELS[Stage][Stage(stage).value]


# ----------------------------------------------------------------------- metrics


def summary(apps: list[AppRecord], today: date, ghost_days: int, pending_days: int = PENDING_DAYS) -> dict:
    eligible = [a for a in apps if a.is_eligible(today, ghost_days)]
    n = len(eligible)
    responses = sum(1 for a in eligible if a.max_idx > 0)
    interviews = sum(1 for a in eligible if a.max_idx >= TECHNICAL_IDX)
    offers = sum(1 for a in apps if a.max_idx >= OFFER_IDX)
    ghosted = sum(1 for a in eligible if a.outcome == Outcome.ghosted or a.is_stale(today, ghost_days))
    response_days = [(d - a.applied_date).days for a in apps if (d := a.first_response_date()) is not None]
    return {
        "total": len(apps),
        "open": sum(1 for a in apps if a.outcome == Outcome.active),
        "active": sum(1 for a in apps if a.status(today, pending_days) == "active"),
        "pending": sum(1 for a in apps if a.status(today, pending_days) == "pending"),
        "stale": sum(1 for a in apps if a.is_stale(today, ghost_days)),
        "eligible": n,
        "responses": responses,
        "response_rate": rate(responses, n),
        "interview_rate": rate(interviews, n),
        "offer_rate": rate(sum(1 for a in eligible if a.max_idx >= OFFER_IDX), n),
        "offers": offers,
        "ghost_rate": rate(ghosted, n),
        "median_days_to_response": median(response_days) if response_days else None,
    }


def funnel(apps: list[AppRecord]) -> list[dict]:
    """How many applications actually went through each stage.

    Stages are often skipped (many companies send an OA straight after you apply, with
    no recruiter screen), so "reached" counts only applications with an event at that
    stage. Those that went past it without one are reported as ``skipped``.
    """
    total = len(apps)
    rows = []
    for i, stage in enumerate(STAGE_ORDER):
        # An accepted/declined offer implies the offer stage even without an event.
        went = {a.id for a in apps if i in a.stages_seen or (i == OFFER_IDX and a.max_idx >= OFFER_IDX)}
        later = {a.id for a in apps if a.max_idx > i}
        rows.append(
            {
                "stage": stage.value,
                "label": stage_label(stage),
                "reached": len(went),
                "reached_rate": rate(len(went), total),
                "skipped": len(later - went),
                "reached_or_later": len(went | later),
            }
        )
    return rows


def stage_stats(
    apps: list[AppRecord], today: date, ghost_days: int, labels: dict[str, str] | None = None
) -> list[dict]:
    """Per-stage pass/fail: the core 'where do I fail?' table."""
    labels = labels or BUILTIN_REASONS
    rows = []
    for i, stage in enumerate(STAGE_ORDER[:OFFER_IDX]):
        through = [a for a in apps if i in a.stages_seen]
        passed = [a for a in through if a.max_idx > i]
        ended_here = [a for a in through if a.max_idx == i]

        rejected = [a for a in ended_here if a.outcome == Outcome.rejected]
        ghosted = sum(1 for a in ended_here if a.outcome == Outcome.ghosted)
        likely_ghosted = sum(1 for a in ended_here if a.is_stale(today, ghost_days))
        withdrawn = sum(1 for a in ended_here if a.outcome == Outcome.withdrawn)
        unfinished = sum(1 for a in ended_here if a.outcome == Outcome.unfinished)
        cancelled = sum(1 for a in ended_here if a.outcome == Outcome.cancelled)
        pending = sum(
            1 for a in ended_here if a.outcome == Outcome.active and not a.is_stale(today, ghost_days)
        )
        failed = len(rejected) + ghosted + likely_ghosted

        reasons = Counter(r for a in rejected for r in a.rejection_reasons)
        rows.append(
            {
                "stage": stage.value,
                "label": stage_label(stage),
                "through": len(through),
                "passed": len(passed),
                "failed": failed,
                "rejected": len(rejected),
                "ghosted": ghosted,
                "likely_ghosted": likely_ghosted,
                "withdrawn": withdrawn,
                "unfinished": unfinished,
                "cancelled": cancelled,
                "pending": pending,
                "pass_rate": rate(len(passed), len(passed) + failed),
                "pass_ci": wilson_interval(len(passed), len(passed) + failed),
                "reasons": [
                    {"reason": r, "label": labels.get(r, r), "count": c} for r, c in reasons.most_common()
                ],
                "unlogged": sum(1 for a in rejected if not a.rejection_reasons),
            }
        )
    return rows


PIPELINE_STATUSES: list[tuple[str, str]] = [
    ("active", "Active"),
    ("pending", "Pending"),
    ("rejected", "Rejected"),
    ("ghosted", "Ghosted"),
    ("withdrawn", "Withdrew / declined"),
    ("accepted", "Offer accepted"),
    ("unfinished", "Unfinished"),
    ("cancelled", "Job cancelled"),
]


def pipeline(apps: list[AppRecord], today: date, pending_days: int = PENDING_DAYS) -> list[dict]:
    """How many applications sit at each stage right now, split by status."""
    rows = [
        {"stage": s.value, "label": stage_label(s), "total": 0, **{k: 0 for k, _ in PIPELINE_STATUSES}}
        for s in STAGE_ORDER
    ]
    for a in apps:
        row = rows[a.max_idx]
        row["total"] += 1
        row[a.status(today, pending_days)] += 1
    return rows


def waiting(apps: list[AppRecord], today: date, pending_days: int = PENDING_DAYS) -> dict:
    """Open applications: how long each has sat in its current stage."""
    open_apps = [a for a in apps if a.outcome == Outcome.active]
    points = [
        {
            "id": a.id,
            "name": a.name,
            "stage": a.current_stage.value,
            "stage_index": a.max_idx,
            "label": stage_label(a.current_stage),
            "since": a.stage_since(today),
            "upcoming": a.upcoming(today),
            "days": a.days_in_stage(today),
            "status": a.status(today, pending_days),
        }
        for a in open_apps
    ]
    by_stage = []
    for i, stage in enumerate(STAGE_ORDER):
        here = [p for p in points if p["stage_index"] == i]
        days = [p["days"] for p in here]
        by_stage.append(
            {
                "stage": stage.value,
                "label": stage_label(stage),
                "active": sum(1 for p in here if p["status"] == "active"),
                "pending": sum(1 for p in here if p["status"] == "pending"),
                "median_days": median(days) if days else None,
                "max_days": max(days) if days else None,
            }
        )
    return {"pending_days": pending_days, "points": points, "by_stage": by_stage}


def rejection_reasons(apps: list[AppRecord], labels: dict[str, str] | None = None) -> dict:
    """Reason counts, each split by the stage the rejection happened at."""
    labels = labels or BUILTIN_REASONS
    rejected = [a for a in apps if a.outcome == Outcome.rejected]
    by_reason: dict[str, Counter[str]] = defaultdict(Counter)
    for a in rejected:
        for r in a.rejection_reasons:
            by_reason[r][a.current_stage.value] += 1
    rows = [
        {
            "reason": r,
            "label": labels.get(r, r),
            "count": sum(stages.values()),
            "share": rate(sum(stages.values()), len(rejected)),
            "by_stage": {s.value: stages.get(s.value, 0) for s in STAGE_ORDER[:OFFER_IDX]},
        }
        for r, stages in by_reason.items()
    ]
    rows.sort(key=lambda row: (-row["count"], row["label"]))
    return {
        "rejected": len(rejected),
        "unlogged": sum(1 for a in rejected if not a.rejection_reasons),
        "rows": rows,
    }


def missing_skills(apps: list[AppRecord]) -> dict:
    """Which skills keep coming up in rejections, as required vs preferred."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"required": 0, "preferred": 0})
    spelling: dict[str, Counter[str]] = defaultdict(Counter)
    with_gap = 0
    rejected = [a for a in apps if a.outcome == Outcome.rejected]
    for a in rejected:
        if a.missing_required or a.missing_preferred:
            with_gap += 1
        for kind, skills in (("required", a.missing_required), ("preferred", a.missing_preferred)):
            for skill in skills:
                key = skill.casefold()
                counts[key][kind] += 1
                spelling[key][skill] += 1
    rows = [
        {
            "skill": spelling[k].most_common(1)[0][0],
            "required": c["required"],
            "preferred": c["preferred"],
            "total": c["required"] + c["preferred"],
        }
        for k, c in counts.items()
    ]
    rows.sort(key=lambda r: (-r["total"], -r["required"], r["skill"].casefold()))
    return {"rejections_with_skill_gap": with_gap, "rejected": len(rejected), "rows": rows}


ASSESSMENT_IDX = stage_index(Stage.assessment)


def assessments(apps: list[AppRecord], today: date) -> dict:
    """Online assessments: when they arrive, how fast you take them, how fast you hear back.

    * received = date of the first assessment event; days measured from the application
    * taken = when you took it (``taken_date``); "not taken" if empty
    * result = moving to a later stage ("passed", dated by that next event) or the outcome
      (rejected / ghosted / unfinished…, dated by ``outcome_date``); otherwise still waiting
    """
    rows = []
    for a in apps:
        oa = [e for e in a.events if e.stage == Stage.assessment and e.event_date]
        if not oa:
            continue
        received = min(e.event_date for e in oa)
        taken_dates = [e.taken_date for e in oa if e.taken_date and e.taken_date <= today]
        taken = min(taken_dates) if taken_dates else None
        later = [e.event_date for e in a.events if stage_index(e.stage) > ASSESSMENT_IDX and e.event_date]
        if a.max_idx > ASSESSMENT_IDX:
            result, result_date = "passed", min(later) if later else None
        elif a.outcome != Outcome.active:
            result, result_date = a.outcome.value, a.outcome_date
        else:
            result, result_date = ("waiting" if taken else "not taken"), None
        start = taken or received
        rows.append(
            {
                "id": a.id,
                "name": a.name,
                "applied": a.applied_date,
                "received": received,
                "taken": taken,
                "result": result,
                "result_date": result_date,
                "days_to_receive": max(0, (received - a.applied_date).days),
                "days_to_take": max(0, (taken - received).days) if taken else None,
                "days_to_result": max(0, (result_date - start).days) if result_date else None,
                # open-ended segments for the timeline chart (still running today)
                "days_open": max(0, (today - start).days) if result_date is None else None,
            }
        )
    rows.sort(key=lambda r: (r["received"], r["name"]))

    def med(key: str) -> dict:
        vals = [r[key] for r in rows if r[key] is not None]
        return {"median": median(vals) if vals else None, "n": len(vals)}

    decided = [r for r in rows if r["result"] in ("passed", "rejected", "ghosted")]
    passed = sum(1 for r in decided if r["result"] == "passed")
    return {
        "count": len(rows),
        "taken": sum(1 for r in rows if r["taken"]),
        "not_taken": sum(1 for r in rows if r["result"] == "not taken"),
        "days_to_receive": med("days_to_receive"),
        "days_to_take": med("days_to_take"),
        "days_to_result": med("days_to_result"),
        "pass_rate": rate(passed, len(decided)),
        "passed": passed,
        "decided": len(decided),
        "rows": rows,
    }


def offers(apps: list[AppRecord]) -> dict:
    got = [a for a in apps if a.max_idx >= OFFER_IDX]
    return {
        "total": len(got),
        "accepted": sum(1 for a in got if a.outcome == Outcome.accepted),
        "declined": sum(1 for a in got if a.outcome == Outcome.declined),
        "pending": sum(1 for a in got if a.outcome == Outcome.active),
    }


def breakdowns(apps: list[AppRecord], today: date, ghost_days: int) -> dict:
    eligible = [a for a in apps if a.is_eligible(today, ghost_days)]
    result = {}
    for dim, dim_label in DIMENSIONS.items():
        groups: dict[str, list[AppRecord]] = defaultdict(list)
        for a in eligible:
            groups[a.dims.get(dim) or NOT_SET].append(a)
        rows = []
        for value, items in groups.items():
            n = len(items)
            responses = sum(1 for a in items if a.max_idx > 0)
            interviews = sum(1 for a in items if a.max_idx >= TECHNICAL_IDX)
            got_offers = sum(1 for a in items if a.max_idx >= OFFER_IDX)
            rows.append(
                {
                    "value": value,
                    "n": n,
                    "responses": responses,
                    "interviews": interviews,
                    "offers": got_offers,
                    "response_rate": rate(responses, n),
                    "interview_rate": rate(interviews, n),
                    "offer_rate": rate(got_offers, n),
                    "response_ci": wilson_interval(responses, n),
                    "low_sample": n < MIN_GROUP_N,
                }
            )
        key = (lambda r: r["value"]) if dim == "applied_month" else (lambda r: (-r["n"], r["value"]))
        rows.sort(key=key)
        result[dim] = {"label": dim_label, "rows": rows}
    return result


def timing(apps: list[AppRecord]) -> dict:
    first = [(d - a.applied_date).days for a in apps if (d := a.first_response_date()) is not None]
    durations: dict[int, list[int]] = defaultdict(list)
    for a in apps:
        firsts: dict[int, date] = {0: a.applied_date}
        for e in a.sorted_events():
            if e.event_date:
                firsts.setdefault(stage_index(e.stage), e.event_date)
        idxs = sorted(firsts)
        for x, y in zip(idxs, idxs[1:], strict=False):
            days = (firsts[y] - firsts[x]).days
            if days >= 0:
                durations[x].append(days)
    # Rejection timing, from the outcome date you log.
    to_reject: list[int] = []
    in_stage_to_reject: dict[int, list[int]] = defaultdict(list)
    for a in apps:
        if a.outcome != Outcome.rejected or not a.outcome_date:
            continue
        to_reject.append((a.outcome_date - a.applied_date).days)
        days = (a.outcome_date - a.stage_since(a.outcome_date)).days
        if days >= 0:
            in_stage_to_reject[a.max_idx].append(days)
    return {
        "days_to_first_response": {
            "median": median(first) if first else None,
            "n": len(first),
        },
        "days_to_rejection": {
            "median": median(to_reject) if to_reject else None,
            "n": len(to_reject),
        },
        "stage_durations": [
            {
                "stage": STAGE_ORDER[i].value,
                "label": stage_label(STAGE_ORDER[i]),
                "median_days": median(durations[i]) if durations[i] else None,
                "n": len(durations[i]),
                "median_days_to_rejection": (
                    median(in_stage_to_reject[i]) if in_stage_to_reject[i] else None
                ),
                "rejected_n": len(in_stage_to_reject[i]),
            }
            for i in range(OFFER_IDX)
        ],
    }


def calibration(apps: list[AppRecord], today: date, ghost_days: int) -> list[dict]:
    """Does 'I think that went well' predict passing? Grouped by self-rating 1-5."""
    buckets = {r: {"passed": 0, "failed": 0} for r in range(1, 6)}
    for a in apps:
        events = a.sorted_events()
        for j, e in enumerate(events):
            if e.self_rating is None or stage_index(e.stage) >= OFFER_IDX:
                continue
            if j < len(events) - 1 or a.max_idx > stage_index(e.stage):
                buckets[e.self_rating]["passed"] += 1
            elif a.ended_failed(today, ghost_days):
                buckets[e.self_rating]["failed"] += 1
    return [
        {
            "rating": r,
            "passed": b["passed"],
            "failed": b["failed"],
            "n": b["passed"] + b["failed"],
            "pass_rate": rate(b["passed"], b["passed"] + b["failed"]),
        }
        for r, b in buckets.items()
    ]


def activity(apps: list[AppRecord], today: date) -> list[dict]:
    applied = Counter(week_start(a.applied_date) for a in apps)
    responses = Counter(week_start(d) for a in apps if (d := a.first_response_date()) is not None)
    weeks = set(applied) | set(responses)
    if not weeks:
        return []
    start, end = min(weeks), max(max(weeks), week_start(today))
    rows = []
    w = start
    while w <= end:
        rows.append({"week": w, "applied": applied.get(w, 0), "responses": responses.get(w, 0)})
        w += timedelta(days=7)
    return rows


# ---------------------------------------------------------------------- insights


def _insight(severity: str, title: str, detail: str) -> dict:
    return {"severity": severity, "title": title, "detail": detail}


def insights(
    apps: list[AppRecord],
    today: date,
    ghost_days: int,
    summ: dict,
    stages: list[dict],
    groups: dict,
    calib: list[dict],
    reasons: dict | None = None,
    skills: dict | None = None,
    pending_days: int = PENDING_DAYS,
) -> list[dict]:
    if not apps:
        return [
            _insight(
                "info",
                "No data yet",
                "Add your applications and log each stage as it happens. Insights show up "
                "once a few outcomes are in.",
            )
        ]

    out: list[dict] = []

    # 1. Bottleneck stage
    decided = [s for s in stages if s["passed"] + s["failed"] >= MIN_STAGE_N]
    if decided:
        weakest = min(decided, key=lambda s: s["pass_rate"])
        detail = (
            f"You move past this stage {pct(weakest['pass_rate'])} of the time "
            f"({weakest['passed']} of {weakest['passed'] + weakest['failed']} decided). "
        )
        if weakest["reasons"]:
            top = weakest["reasons"][0]
            detail += f"Most common logged reason: {top['label'].lower()} ({top['count']}x). "
        detail += STAGE_ADVICE[Stage(weakest["stage"])]
        out.append(_insight("warning", f"Biggest drop-off: {weakest['label']}", detail))

        strongest = max(decided, key=lambda s: s["pass_rate"])
        if strongest is not weakest and (strongest["pass_rate"] or 0) >= 0.5:
            out.append(
                _insight(
                    "good",
                    f"Strongest stage: {strongest['label']}",
                    f"You pass {pct(strongest['pass_rate'])} of the time here, so keep doing "
                    "what you're doing at this step.",
                )
            )
    else:
        out.append(
            _insight(
                "info",
                "Not enough outcomes to find a bottleneck yet",
                f"Each stage needs at least {MIN_STAGE_N} decided applications (passed, "
                "rejected or ghosted) before it can be ranked.",
            )
        )

    # 2. Why rejections happen, and which skills are missing
    if reasons and reasons["rejected"] >= MIN_STAGE_N and reasons["rows"]:
        top = reasons["rows"][0]
        stage_counts = {k: v for k, v in top["by_stage"].items() if v}
        where = max(stage_counts, key=stage_counts.get) if stage_counts else None
        out.append(
            _insight(
                "warning" if (top["share"] or 0) >= 0.3 else "info",
                f"Top rejection reason: {top['label']}",
                f"Cited in {top['count']} of {reasons['rejected']} rejections ({pct(top['share'])})"
                + (f", mostly at the {stage_label(where).lower()} stage." if where else "."),
            )
        )
    if skills and skills["rows"]:
        top_skill = skills["rows"][0]
        if top_skill["total"] >= 2:
            others = ", ".join(r["skill"] for r in skills["rows"][1:4])
            out.append(
                _insight(
                    "warning",
                    f"Most-cited missing skill: {top_skill['skill']}",
                    f"Missing in {top_skill['total']} rejections ({top_skill['required']} as a "
                    f"required skill, {top_skill['preferred']} as preferred)."
                    + (f" Next most common: {others}." if others else "")
                    + " This is the skill most worth learning or adding evidence of to your resume.",
                )
            )

    # 3. Which levers move the response rate?
    for dim in ("referral", "source", "resume_version", "cover_letter"):
        rows = [r for r in groups[dim]["rows"] if not r["low_sample"] and r["value"] != NOT_SET]
        if len(rows) < 2:
            continue
        best = max(rows, key=lambda r: r["response_rate"])
        worst = min(rows, key=lambda r: r["response_rate"])
        gap = best["response_rate"] - worst["response_rate"]
        if gap < 0.15:
            continue
        clear = best["response_ci"][0] > worst["response_ci"][1]
        confidence = (
            "The gap is statistically clear."
            if clear
            else "The confidence intervals overlap, so this could still be noise. Keep collecting."
        )
        out.append(
            _insight(
                "good" if clear else "info",
                f"{groups[dim]['label']}: “{best['value']}” works better",
                f"“{best['value']}” gets a response {pct(best['response_rate'])} of the time "
                f"(n={best['n']}) vs {pct(worst['response_rate'])} for “{worst['value']}” "
                f"(n={worst['n']}). {confidence}",
            )
        )

    # 4. Ghosting
    if summ["eligible"] >= MIN_GROUP_N and (summ["ghost_rate"] or 0) >= 0.4:
        out.append(
            _insight(
                "warning",
                f"{pct(summ['ghost_rate'])} of applications go silent",
                "A high ghost rate usually means applications aren't reaching a human. Try "
                "referrals, messaging the hiring manager directly, or applying earlier.",
            )
        )

    # 5. Follow-ups
    if summ["pending"]:
        stale = (
            f" {summ['stale']} of them have been silent {ghost_days}+ days and already count as "
            "no-reply in your rates; mark them ghosted if you've given up."
            if summ["stale"]
            else ""
        )
        out.append(
            _insight(
                "info",
                f"{summ['pending']} application(s) pending for {pending_days}+ days",
                f"These haven't moved in their current stage for at least {pending_days} days. "
                f"A short follow-up to the recruiter often gets things moving again.{stale}",
            )
        )

    # 6. Steps you didn't finish
    unfinished = [s for s in stages if s["unfinished"]]
    if unfinished:
        n = sum(s["unfinished"] for s in unfinished)
        where = ", ".join(f"{s['label'].lower()} ({s['unfinished']})" for s in unfinished)
        out.append(
            _insight(
                "info",
                f"{n} step(s) left unfinished",
                f"At: {where}. These aren't counted as rejections, but each one is an opportunity "
                "you closed yourself. If time was the problem, block time as soon as the invite arrives.",
            )
        )

    # 7. Self-assessment calibration
    high = [c for c in calib if c["rating"] >= 4]
    low = [c for c in calib if c["rating"] <= 2]
    high_n = sum(c["n"] for c in high)
    low_n = sum(c["n"] for c in low)
    high_rate = rate(sum(c["passed"] for c in high), high_n)
    low_rate = rate(sum(c["passed"] for c in low), low_n)
    if high_n >= MIN_STAGE_N and high_rate is not None and high_rate < 0.5:
        out.append(
            _insight(
                "warning",
                "Interviews that felt good often don't pass",
                f"You passed only {pct(high_rate)} of the {high_n} interviews you rated 4-5. "
                "That points to a blind spot. Ask interviewers for feedback and compare your "
                "notes with what the role needs.",
            )
        )
    elif (
        high_n >= MIN_STAGE_N
        and low_n >= MIN_STAGE_N
        and high_rate is not None
        and low_rate is not None
        and high_rate - low_rate >= 0.3
    ):
        out.append(
            _insight(
                "good",
                "Your gut feeling is well calibrated",
                f"Interviews you rate 4-5 pass {pct(high_rate)} of the time vs {pct(low_rate)} "
                "for 1-2, so your self-rating is a reliable early signal.",
            )
        )

    # 8. Data quality
    rejected = [a for a in apps if a.outcome == Outcome.rejected]
    missing = [a for a in rejected if not a.rejection_reasons]
    if len(rejected) >= MIN_GROUP_N and len(missing) / len(rejected) > 0.5:
        out.append(
            _insight(
                "info",
                "Most rejections have no reason logged",
                f"{len(missing)} of {len(rejected)} rejections have no reason. Even a best guess "
                "(missing skill, OA fail...) makes the drop-off analysis much sharper.",
            )
        )
    if summ["eligible"] < 10:
        out.append(
            _insight(
                "info",
                "Small sample",
                f"Only {summ['eligible']} applications have a result so far, so read these "
                "patterns as hints, not conclusions.",
            )
        )
    return out


def compute_all(
    apps: list[AppRecord],
    today: date,
    ghost_days: int,
    labels: dict[str, str] | None = None,
    pending_days: int = PENDING_DAYS,
) -> dict:
    summ = summary(apps, today, ghost_days, pending_days)
    stages = stage_stats(apps, today, ghost_days, labels)
    groups = breakdowns(apps, today, ghost_days)
    calib = calibration(apps, today, ghost_days)
    reasons = rejection_reasons(apps, labels)
    skills = missing_skills(apps)
    return {
        "generated_on": today,
        "ghost_days": ghost_days,
        "pending_days": pending_days,
        "summary": summ,
        "pipeline": pipeline(apps, today, pending_days),
        "waiting": waiting(apps, today, pending_days),
        "pipeline_statuses": [{"key": k, "label": v} for k, v in PIPELINE_STATUSES],
        "funnel": funnel(apps),
        "stages": stages,
        "rejection_reasons": reasons,
        "missing_skills": skills,
        "assessments": assessments(apps, today),
        "offers": offers(apps),
        "breakdowns": groups,
        "timing": timing(apps),
        "calibration": calib,
        "activity": activity(apps, today),
        "insights": insights(
            apps, today, ghost_days, summ, stages, groups, calib, reasons, skills, pending_days
        ),
    }
