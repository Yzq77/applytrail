"""Enumerations shared by the models, the analytics engine and the API."""

from enum import Enum, StrEnum


class Stage(StrEnum):
    applied = "applied"
    screen = "screen"
    webinar = "webinar"
    assessment = "assessment"
    technical = "technical"
    onsite = "onsite"
    offer = "offer"


class Outcome(StrEnum):
    active = "active"
    rejected = "rejected"
    ghosted = "ghosted"
    withdrawn = "withdrawn"
    unfinished = "unfinished"  # you didn't complete a step (OA, recorded video…)
    cancelled = "cancelled"  # the employer cancelled the position
    accepted = "accepted"
    declined = "declined"


class Source(StrEnum):
    company_site = "company_site"
    linkedin = "linkedin"
    job_board = "job_board"
    recruiter = "recruiter"
    networking = "networking"
    career_fair = "career_fair"
    other = "other"


class Level(StrEnum):
    intern = "intern"
    entry = "entry"
    mid = "mid"
    senior = "senior"
    staff = "staff"
    manager = "manager"
    other = "other"


class WorkMode(StrEnum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"


STAGE_ORDER: list[Stage] = list(Stage)


def stage_index(stage: "Stage | str") -> int:
    return STAGE_ORDER.index(Stage(stage))


LABELS: dict[type[Enum], dict[str, str]] = {
    Stage: {
        "applied": "Applied",
        "screen": "Recruiter screen",
        "webinar": "Webinar / info session",
        "assessment": "Assessment / OA",
        "technical": "Technical interview",
        "onsite": "Onsite / final round",
        "offer": "Offer",
    },
    Outcome: {
        "active": "Active",
        "rejected": "Rejected",
        "ghosted": "Ghosted",
        "withdrawn": "Withdrew",
        "unfinished": "Unfinished",
        "cancelled": "Job cancelled",
        "accepted": "Offer accepted",
        "declined": "Offer declined",
    },
    Source: {
        "company_site": "Company website",
        "linkedin": "LinkedIn",
        "job_board": "Job board",
        "recruiter": "Recruiter reached out",
        "networking": "Networking",
        "career_fair": "Career fair",
        "other": "Other",
    },
    Level: {
        "intern": "Intern",
        "entry": "Entry / new grad",
        "mid": "Mid",
        "senior": "Senior",
        "staff": "Staff+",
        "manager": "Manager",
        "other": "Other",
    },
    WorkMode: {"onsite": "On-site", "hybrid": "Hybrid", "remote": "Remote"},
}


def label(enum_cls: type[Enum], value: "Enum | str | None") -> str | None:
    if value is None:
        return None
    raw = value.value if isinstance(value, Enum) else value
    return LABELS[enum_cls].get(raw, raw)


def options(enum_cls: type[Enum]) -> list[dict[str, str]]:
    return [{"value": m.value, "label": LABELS[enum_cls][m.value]} for m in enum_cls]


# Rejection reasons are a user-extensible list: these built-ins plus any custom
# reasons typed in the UI (stored in the ``reason_option`` table). An application
# can carry several reasons at once.
BUILTIN_REASONS: dict[str, str] = {
    "missing_preferred_skill": "Missing preferred skill",
    "missing_required_skill": "Missing required skill",
    "oa_fail": "OA fail",
    "interview_performance": "Interview performance",
    "job_closed": "Job closed when rejected",
    "open_question": "Has open question in application",
}

# Reasons that come with a list of skills, and which list they fill.
SKILL_REASONS: dict[str, str] = {
    "missing_required_skill": "required",
    "missing_preferred_skill": "preferred",
}
