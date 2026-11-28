"""Parse quick-add lines: ``link, company, job title, date``.

The order is the documented one, but parsing is forgiving:

* the link is recognised wherever it appears, and is optional; tracking bits
  (``/confirmation``, ``?gh_src=…``, ``utm_*``…) are removed so duplicates match;
* the date is recognised in many formats ("2026-11-26", "11/26", "Nov 26, 2026",
  "today", "3 days ago", "2026年11月26日") and defaults to today;
* of the remaining parts, the first is the company and the rest is the job title,
  so titles containing commas still work ("Software Engineer, Robotics");
* a trailing "Inc." / "LLC" / "Ltd" stays attached to the company name, and if the
  link names the company (``greenhouse.io/acmeinc/…``) that part wins wherever it is;
* brackets or quotes around the line or a part are ignored.
"""

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
TRACKING_PARAM_RE = re.compile(
    r"^(utm_\w+|gh_src|ref|source|src|trk|refid|trackingid|lever-\w+|embed|_ga)$", re.IGNORECASE
)
# Pages you land on while applying, which aren't the posting itself.
APPLY_SUFFIX_RE = re.compile(r"/(confirmation|thank[-_]?you|application|apply)/?$", re.IGNORECASE)
# Hiring platforms whose URL contains the company: host pattern -> where the slug is.
ATS_SLUG_RES = [
    re.compile(r"^(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/([^/?#]+)", re.I),
    re.compile(r"^jobs\.(?:eu\.)?lever\.co/([^/?#]+)", re.I),
    re.compile(r"^jobs\.ashbyhq\.com/([^/?#]+)", re.I),
    re.compile(r"^apply\.workable\.com/([^/?#]+)", re.I),
    re.compile(r"^jobs\.smartrecruiters\.com/([^/?#]+)", re.I),
    re.compile(r"^ats\.rippling\.com/([^/?#]+)", re.I),
    re.compile(r"^([^./]+)\.wd\d+\.myworkdayjobs\.com", re.I),
]


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


BRACKETS = {"(": ")", "[": "]", "{": "}", "<": ">"}
QUOTES = {'"': '"', "'": "'", "“": "”", "‘": "’", "`": "`"}


def _balanced(text: str) -> bool:
    depth = 0
    for ch in text:
        if ch in BRACKETS:
            depth += 1
        elif ch in BRACKETS.values():
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _unwrap(text: str) -> str:
    """Remove brackets/quotes around the text, or unpaired ones at its ends.

    "(a, b)" -> "a, b" and "(https://x" -> "https://x", but a closing bracket that belongs
    to the text stays: "Engineer (New Grad)" is left alone.
    """
    t = text.strip()
    while len(t) >= 1:
        first, last = t[0], t[-1]
        pairs = {**BRACKETS, **QUOTES}
        if len(t) >= 2 and first in pairs and last == pairs[first] and _balanced(t[1:-1]):
            t = t[1:-1].strip()
        elif first in BRACKETS and t.count(first) > t.count(BRACKETS[first]):
            t = t[1:].strip()
        elif last in BRACKETS.values():
            opener = next(k for k, v in BRACKETS.items() if v == last)
            if t.count(last) > t.count(opener):
                t = t[:-1].strip()
            else:
                break
        elif first in QUOTES and t.count(first) == 1:
            t = t[1:].strip()
        elif last in QUOTES.values() and t.count(last) == 1:
            t = t[:-1].strip()
        else:
            break
    return t


def clean_url(url: str) -> str:
    """Drop tracking parameters and apply/confirmation pages so the same posting matches."""
    if not url.lower().startswith("http"):
        url = f"https://{url}"
    parts = urlsplit(url)
    path = APPLY_SUFFIX_RE.sub("", parts.path)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAM_RE.match(k)])
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def company_slug(url: str | None) -> str | None:
    """'job-boards.greenhouse.io/acmeroboticsinc/jobs/1' -> 'acmeroboticsinc'"""
    if not url:
        return None
    rest = re.sub(r"^https?://", "", url, flags=re.I)
    for pattern in ATS_SLUG_RES:
        if m := pattern.match(rest):
            return _norm(m.group(1)) or None
    return None


def _matches_slug(token: str, slug: str) -> bool:
    t = _norm(token)
    return len(t) >= 3 and (t == slug or slug.startswith(t) or t.startswith(slug))


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
    for part in (_unwrap(p) for p in _unwrap(line).split(",")):
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
            result.job_url = clean_url(tokens.pop(i))
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
        result.error = "Need at least a company and a job title: link, company, job title, date"
        return result

    # The company is the first part, unless the link or an "Inc."-style suffix says otherwise.
    idx = 0
    slug = company_slug(result.job_url)
    by_slug = [i for i, t in enumerate(tokens) if slug and _matches_slug(t, slug)]
    by_suffix = [
        i
        for i, t in enumerate(tokens)
        if re.search(r",\s*\S+$", t) and COMPANY_SUFFIX_RE.match(t.rsplit(",", 1)[1].strip())
    ]
    if len(by_slug) == 1:
        idx = by_slug[0]
    elif len(by_suffix) == 1:
        idx = by_suffix[0]
    result.company = tokens[idx]
    result.role = ", ".join(t for i, t in enumerate(tokens) if i != idx)

    # Never save a line that was misread: a leftover link or date means something's off.
    for part in (result.company, result.role):
        if re.search(r"https?:|://|www\.", part, re.I) or parse_date(part, today):
            result.error = f"Couldn't read “{part}”. Check the link and date are separated by commas"
            return result
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
