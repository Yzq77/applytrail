from datetime import date

import pytest

from app.quickadd import parse_date, parse_line, parse_text

TODAY = date(2026, 11, 26)


def test_documented_order():
    p = parse_line("https://jobs.lever.co/acme/123, Backend Engineer, Acme, 2026-11-20", TODAY)
    assert p.error is None
    assert (p.job_url, p.role, p.company, p.applied_date) == (
        "https://jobs.lever.co/acme/123",
        "Backend Engineer",
        "Acme",
        date(2026, 11, 20),
    )
    assert p.source == "company_site"
    assert not p.date_defaulted


def test_link_and_date_are_optional():
    p = parse_line("Data Analyst, Globex", TODAY)
    assert (p.role, p.company, p.job_url) == ("Data Analyst", "Globex", None)
    assert p.applied_date == TODAY and p.date_defaulted
    assert p.source is None


def test_title_with_commas_and_company_suffix():
    p = parse_line("linkedin.com/jobs/view/42, Engineer, Backend, Platform, Acme, Inc., 11/3", TODAY)
    assert p.role == "Engineer, Backend, Platform"
    assert p.company == "Acme, Inc."
    assert p.job_url == "https://linkedin.com/jobs/view/42"
    assert p.source == "linkedin"
    assert p.applied_date == date(2026, 11, 3)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2026-11-20", date(2026, 11, 20)),
        ("11/20/2026", date(2026, 11, 20)),
        ("11/20", date(2026, 11, 20)),
        ("Nov 20 2026", date(2026, 11, 20)),
        ("Nov 20, 2026", date(2026, 11, 20)),
        ("20 November 2026", date(2026, 11, 20)),
        ("today", TODAY),
        ("yesterday", date(2026, 11, 25)),
        ("3 days ago", date(2026, 11, 23)),
        ("2026年11月20日", date(2026, 11, 20)),
        ("Dec 30", date(2025, 12, 30)),  # no year, would be in the future -> last year
        ("Software Engineer", None),
    ],
)
def test_dates(text, expected):
    assert parse_date(text, TODAY) == expected


def test_date_with_comma_inside_line():
    p = parse_line("https://x.io/j/1, SWE, Initech, Nov 20, 2026", TODAY)
    assert (p.role, p.company, p.applied_date) == ("SWE", "Initech", date(2026, 11, 20))


def test_errors_and_multiline():
    items = parse_text("SWE, Acme\n\nhttps://only-a-link.com/x, 2026-01-01\n", TODAY)
    assert len(items) == 2
    assert items[0].error is None
    assert items[1].error and items[1].line == 3
