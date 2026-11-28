from datetime import date

import pytest

from app.quickadd import parse_date, parse_line, parse_text

TODAY = date(2026, 11, 26)


def test_documented_order():
    p = parse_line("https://jobs.lever.co/acme/123, Acme, Backend Engineer, 2026-11-20", TODAY)
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
    p = parse_line("Globex, Data Analyst", TODAY)
    assert (p.role, p.company, p.job_url) == ("Data Analyst", "Globex", None)
    assert p.applied_date == TODAY and p.date_defaulted
    assert p.source is None


def test_title_with_commas_and_company_suffix():
    p = parse_line("linkedin.com/jobs/view/42, Acme, Inc., Engineer, Backend, Platform, 11/3", TODAY)
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
    p = parse_line("https://x.io/j/1, Initech, SWE, Nov 20, 2026", TODAY)
    assert (p.role, p.company, p.applied_date) == ("SWE", "Initech", date(2026, 11, 20))


def test_errors_and_multiline():
    items = parse_text("Acme, SWE\n\nhttps://only-a-link.com/x, 2026-01-01\n", TODAY)
    assert len(items) == 2
    assert items[0].error is None
    assert items[1].error and items[1].line == 3


def test_wrapped_line_tracking_link_and_company_from_link():
    line = (
        "(https://job-boards.greenhouse.io/acmebiosciencesinc/jobs/1234567890/confirmation"
        "?gh_src=Simplify, Acme Biosciences, Inc., Software Engineer, Robotics, 2026-11-27)"
    )
    p = parse_line(line, TODAY)
    assert p.error is None
    assert (p.company, p.role) == ("Acme Biosciences, Inc.", "Software Engineer, Robotics")
    assert p.job_url == "https://job-boards.greenhouse.io/acmebiosciencesinc/jobs/1234567890"
    assert p.applied_date == date(2026, 11, 27)
    # company recognised from the link even when typed after the title
    p = parse_line("Software Engineer, https://jobs.ashbyhq.com/acme-robotics/9, Acme Robotics", TODAY)
    assert (p.company, p.role) == ("Acme Robotics", "Software Engineer")


def test_clean_url_keeps_meaningful_params():
    from app.quickadd import clean_url

    assert clean_url("jobs.ashbyhq.com/x/abc/application?utm_source=Simplify&ref=Simplify") == (
        "https://jobs.ashbyhq.com/x/abc"
    )
    assert clean_url("https://ctc.com/careers?gh_jid=4716937005&gh_src=Simplify") == (
        "https://ctc.com/careers?gh_jid=4716937005"
    )


def test_misread_line_is_an_error_not_a_save():
    p = parse_line("https://x.io/j/1 Acme, SWE, 2026-11-27", TODAY)  # missing comma after the link
    assert p.error and "Check the link" in p.error


@pytest.mark.parametrize(
    "line,company,role",
    [
        ("Globex, Forward Deployed Engineer (New Grad)", "Globex", "Forward Deployed Engineer (New Grad)"),
        (
            "(Globex, Forward Deployed Engineer (New Grad))",
            "Globex",
            "Forward Deployed Engineer (New Grad)",
        ),
        (
            "Initech, Software Engineer I (Factory Platform), 11/28",
            "Initech",
            "Software Engineer I (Factory Platform)",
        ),
        ('"Acme", "Data Analyst"', "Acme", "Data Analyst"),
    ],
)
def test_brackets_that_belong_to_the_text_are_kept(line, company, role):
    p = parse_line(line, TODAY)
    assert (p.company, p.role, p.error) == (company, role, None)
