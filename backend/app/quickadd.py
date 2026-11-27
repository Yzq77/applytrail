"""Parse quick-add lines: ``link, job title, company, date``.

The order is the documented one, but parsing is forgiving:

* the link is recognised wherever it appears, and is optional;
* the date is recognised in many formats ("2026-11-26", "11/26", "Nov 26, 2026",
  "today", "3 days ago", "2026年11月26日") and defaults to today;
* of the remaining parts, the last is the company and everything before it is the
  job title, so titles containing commas still work ("Engineer, Backend");
* a trailing "Inc." / "LLC" / "Ltd" stays attached to the company name.
"""

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta

URL_RE = re.compile(
    r"^(https?://\S+|www\.\S+|[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}/\S*)$",
    re.IGNORECASE,
)
COMPANY_SUFFIX_RE = re.compile(
    r"^(inc|inc\.|llc|l\.l\.c\.|ltd|ltd\.|co|co\.|corp|corp\.|gmbh|plc|ag|s\.a\.|pte\.? ltd\.?)$",
    re.IGNORECASE,
)
DATE_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y",
    "%b %d %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y", "%Y年%m月%d日",
]  # fmt: skip
NO_YEAR_FORMATS = ["%m/%d", "%b %d", "%B %d", "%d %b", "%d %B", "%m月%d日"]

# Where a posting lives says something about the channel you applied through.
SOURCE_HINTS = [
    ("linkedin.", "linkedin"),
    ("indeed.", "job_board"),
    ("glassdoor.", "job_board"),
    ("ziprecruiter.", "job_board"),
    ("joinhandshake.", "job_board"),
    ("wellfound.", "job_board"),
    ("builtin", "job_board"),
    ("dice.com", "job_board"),
    ("simplify.jobs", "job_board"),
]
MAX_LEN = 200


@dataclass
class ParsedLine:
    line: int
    raw: str
    company: str | None = None
    role: str | None = None
    job_url: str | None = None
    applied_date: date | None = None
    date_defaulted: bool = False
    source: str | None = None
    error: str | None = None
    warning: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def parse_date(token: str, today: date) -> date | None:
    t = re.sub(r"\s+", " ", token.replace(",", " ")).strip()
    low = t.lower()
    if low in ("today", "now", "今天"):
        return today
    if low in ("yesterday", "昨天"):
        return today - timedelta(days=1)
    if m := re.fullmatch(r"(\d{1,3}) ?d(ays?)? ago", low):
        return today - timedelta(days=int(m.group(1)))
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    for fmt in NO_YEAR_FORMATS:
        try:
            d = datetime.strptime(f"{today.year} {t}", f"%Y {fmt}").date()
        except ValueError:
            continue
        # "Dec 30" typed in January means last year.
        return d.replace(year=d.year - 1) if d > today + timedelta(days=1) else d
    return None


def guess_source(url: str | None) -> str | None:
    if not url:
        return None
    low = url.lower()
    for hint, source in SOURCE_HINTS:
        if hint in low:
            return source
    return "company_site"


def _tokens(line: str, today: date) -> list[str]:
    tokens: list[str] = []
    for part in (p.strip() for p in line.split(",")):
        if not part:
            continue
        # Re-join dates that contain a comma: "Nov 26, 2026"
        if (
            tokens
            and re.fullmatch(r"\d{4}", part)
            and not re.search(r"\d{4}", tokens[-1])
            and parse_date(tokens[-1], today)
        ):
            tokens[-1] = f"{tokens[-1]} {part}"
            continue
        # Re-join company suffixes: "Acme, Inc."
        if tokens and COMPANY_SUFFIX_RE.match(part):
            tokens[-1] = f"{tokens[-1]}, {part}"
            continue
        tokens.append(part)
    return tokens


def parse_line(line: str, today: date, line_no: int = 1) -> ParsedLine:
    result = ParsedLine(line=line_no, raw=line)
    tokens = _tokens(line, today)

    for i, tok in enumerate(tokens):
        if URL_RE.match(tok):
            url = tokens.pop(i)
            result.job_url = url if url.lower().startswith("http") else f"https://{url}"
            break

    for i in range(len(tokens) - 1, -1, -1):
        if (d := parse_date(tokens[i], today)) is not None:
            result.applied_date = d
            tokens.pop(i)
            break
    if result.applied_date is None:
        result.applied_date, result.date_defaulted = today, True
    elif result.applied_date > today:
        result.warning = "Date is in the future"

    if len(tokens) < 2:
        result.error = "Need at least a job title and a company: link, job title, company, date"
        return result
    result.company = tokens[-1]
    result.role = ", ".join(tokens[:-1])
    if len(result.company) > MAX_LEN or len(result.role) > MAX_LEN:
        result.error = f"Job title and company must be under {MAX_LEN} characters"
    result.source = guess_source(result.job_url)
    return result


def parse_text(text: str, today: date) -> list[ParsedLine]:
    return [
        parse_line(line.strip(), today, n)
        for n, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]
