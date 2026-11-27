"""Generate a fictional demo dataset (for screenshots / trying the app).

    python -m app.seed            # writes data/demo.db
    make demo                     # seed + run the app against demo.db

Company names are random word pairs; none of this is real data. The simulation
plants a few patterns (referrals help, the newer resume works better, technical
rounds are the bottleneck, good-feeling interviews often fail) so the analytics
page has something to find.
"""

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

from sqlmodel import Session, SQLModel

from .config import DATA_DIR
from .db import make_engine
from .enums import Level, Outcome, Source, Stage, WorkMode
from .models import Application, ReasonOption, StageEvent

PREFIXES = """Bluefin Cobaltine Driftwood Emberly Foxglove Granitepeak Halcyon Ironbark Kestrel
Lumenfield Marigold Nettlebay Orchardly Pebblestone Quillworks Rookery Saffronet Tidewater
Umberline Vantly Willowmere Yarrowdale Zephyrine Aldermoor Brackenridge""".split()
SUFFIXES = ["Labs", "Systems", "Analytics", "Health", "Robotics", "Software", "Data", "Cloud"]
ROLES = [
    "Software Engineer",
    "Backend Engineer",
    "Frontend Engineer",
    "Full Stack Engineer",
    "Data Analyst",
    "Data Scientist",
    "ML Engineer",
]
CITIES = ["New York, NY", "Seattle, WA", "Austin, TX", "Remote", "San Francisco, CA", "Boston, MA"]

PASS_PROB = {Stage.screen: 0.72, Stage.assessment: 0.6, Stage.technical: 0.4, Stage.onsite: 0.6}
GHOST_PROB = {Stage.applied: 0.65, Stage.screen: 0.3}
CUSTOM_REASON = ("custom_visa_sponsorship", "Visa sponsorship")  # shows off a user-added reason
REASONS = {
    Stage.applied: [
        ("missing_required_skill", 4),
        ("missing_preferred_skill", 3),
        ("job_closed", 2),
        ("open_question", 2),
        (CUSTOM_REASON[0], 1),
    ],
    Stage.screen: [
        ("missing_preferred_skill", 2),
        ("open_question", 2),
        (CUSTOM_REASON[0], 2),
        ("job_closed", 1),
    ],
    Stage.assessment: [("oa_fail", 1)],
    Stage.technical: [("interview_performance", 5), ("missing_required_skill", 4)],
    Stage.onsite: [("interview_performance", 4), ("missing_preferred_skill", 2)],
}
REQUIRED_SKILLS = [("Kubernetes", 6), ("Go", 4), ("AWS", 4), ("System design", 3), ("Spark", 2), ("Kafka", 2)]
PREFERRED_SKILLS = [("Terraform", 4), ("GraphQL", 3), ("Kubernetes", 2), ("Rust", 2), ("Airflow", 2)]
REFLECTIONS = {
    Stage.technical: [
        "Froze on the graph question, need more BFS/DFS reps.",
        "Solved it but too slowly; didn't talk through my approach.",
        "Didn't know their stack (Kafka) well enough.",
    ],
    Stage.onsite: [
        "Behavioral answers were vague, need concrete STAR stories.",
        "System design round: didn't discuss trade-offs.",
    ],
    Stage.applied: ["Probably filtered by ATS keywords."],
}


def _pick(rng: random.Random, weighted: list[tuple[str, int]]) -> str:
    values, weights = zip(*weighted, strict=False)
    return rng.choices(values, weights=weights)[0]


def _skills(rng: random.Random, pool: list[tuple[str, int]]) -> list[str]:
    return sorted({_pick(rng, pool) for _ in range(rng.choice([1, 1, 2]))})


def simulate(rng: random.Random, today: date) -> tuple[Application, list[StageEvent]]:
    days_ago = rng.randint(0, 150)
    applied = today - timedelta(days=days_ago)
    referral = rng.random() < 0.18
    source = Source(
        _pick(
            rng,
            [("linkedin", 6), ("company_site", 5), ("job_board", 3), ("recruiter", 2), ("networking", 1)],
        )
    )
    resume = "v1-generic" if days_ago > 100 else rng.choice(["v2-tailored", "v3-quantified"])

    p_response = 0.10 + {"v1-generic": 0.0, "v2-tailored": 0.06, "v3-quantified": 0.16}[resume]
    p_response += 0.30 if referral else 0.0
    p_response += {Source.recruiter: 0.40, Source.networking: 0.20, Source.company_site: 0.04}.get(source, 0)
    p_response = min(p_response, 0.9)

    app = Application(
        company=f"{rng.choice(PREFIXES)} {rng.choice(SUFFIXES)}",
        role=rng.choice(ROLES),
        applied_date=applied,
        level=rng.choice([Level.entry, Level.entry, Level.mid, Level.mid, Level.senior]),
        location=rng.choice(CITIES),
        work_mode=rng.choice(list(WorkMode)),
        source=source,
        referral=referral,
        resume_version=resume,
        cover_letter=rng.random() < 0.3,
        salary_min=rng.choice([None, 90000, 110000, 130000]),
        tags=rng.choice([None, "dream", "backup", "fintech", "startup"]),
    )
    if app.salary_min:
        app.salary_max = app.salary_min + 30000

    path = [Stage.screen]
    if rng.random() < 0.5:
        path.append(Stage.assessment)
    path += [Stage.technical, Stage.onsite, Stage.offer]

    events = [StageEvent(stage=Stage.applied, event_date=applied)]
    current, cur_date = Stage.applied, applied
    for nxt in path:
        gap = rng.randint(5, 25) if current == Stage.applied else rng.randint(3, 12)
        if cur_date + timedelta(days=gap) > today:
            break  # still waiting to hear back
        prob = p_response if current == Stage.applied else PASS_PROB[current]
        if rng.random() < prob:
            cur_date += timedelta(days=gap)
            events.append(StageEvent(stage=nxt, event_date=cur_date))
            current = nxt
            if nxt == Stage.offer:
                app.outcome = rng.choice([Outcome.accepted, Outcome.declined, Outcome.active])
                if app.outcome != Outcome.active:
                    app.outcome_date = min(today, cur_date + timedelta(days=rng.randint(2, 7)))
            continue
        if current == Stage.applied and rng.random() < 0.25:
            break  # silent, left active: becomes "likely ghosted" once stale
        app.outcome_date = cur_date + timedelta(days=gap)  # the day the decision came
        if rng.random() < GHOST_PROB.get(current, 0.12):
            app.outcome = Outcome.ghosted
        else:
            app.outcome = Outcome.rejected
            if rng.random() < 0.85:  # some rejections never get a reason logged
                reasons = {_pick(rng, REASONS[current])}
                if rng.random() < 0.3:
                    reasons.add(_pick(rng, REASONS[current]))
                app.rejection_reasons = sorted(reasons)
                if "missing_required_skill" in reasons:
                    app.missing_required_skills = _skills(rng, REQUIRED_SKILLS)
                if "missing_preferred_skill" in reasons:
                    app.missing_preferred_skills = _skills(rng, PREFERRED_SKILLS)
            if current in REFLECTIONS and rng.random() < 0.6:
                app.reflection = rng.choice(REFLECTIONS[current])
        break

    if app.outcome == Outcome.active and current != Stage.offer and rng.random() < 0.04:
        app.outcome = Outcome.withdrawn
        app.outcome_date = min(today, cur_date + timedelta(days=rng.randint(3, 10)))

    # When the OA was taken: a few days after it arrived, before anything that followed.
    for j, e in enumerate(events):
        if e.stage == Stage.assessment and (
            j < len(events) - 1 or app.outcome != Outcome.active or rng.random() < 0.5
        ):
            limit = events[j + 1].event_date if j < len(events) - 1 else (app.outcome_date or today)
            e.taken_date = min(e.event_date + timedelta(days=rng.randint(0, 6)), limit, today)

    failed = app.outcome in (Outcome.rejected, Outcome.ghosted)
    for j, e in enumerate(events):
        if e.stage in (Stage.applied, Stage.offer) or rng.random() > 0.75:
            continue
        passed = j < len(events) - 1
        if passed:
            weights = [1, 2, 4, 6, 4]
        elif failed and e.stage == Stage.technical:
            weights = [1, 2, 4, 5, 2]  # the planted blind spot
        elif failed:
            weights = [3, 5, 4, 2, 1]
        else:
            continue
        e.self_rating = rng.choices([1, 2, 3, 4, 5], weights=weights)[0]
    return app, events


def seed(path: Path, n: int, seed_value: int, today: date | None = None) -> int:
    today = today or date.today()
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    rng = random.Random(seed_value)
    with Session(engine) as session:
        session.add(ReasonOption(key=CUSTOM_REASON[0], label=CUSTOM_REASON[1]))
        for _ in range(n):
            app, events = simulate(rng, today)
            session.add(app)
            session.flush()
            for e in events:
                e.application_id = app.id
                session.add(e)
        session.commit()
    return n


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=DATA_DIR / "demo.db")
    parser.add_argument("-n", type=int, default=120, help="number of applications")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    if args.out.name == "applytrail.db":
        parser.error("refusing to overwrite your real database; pick another --out")
    count = seed(args.out, args.n, args.seed)
    print(f"Wrote {count} fictional applications to {args.out}")


if __name__ == "__main__":
    main()
