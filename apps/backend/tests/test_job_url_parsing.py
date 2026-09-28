"""URL parsing for the "paste a job URL" flow. Must resolve real posting URLs to (platform, token,
job_id) without ever needing to render or scrape the page - see connectors.py's module docstring."""

from rolewise.worker.connectors import parse_ats_url, parse_greenhouse_gh_jid


def test_standard_greenhouse_board_url():
    url = "https://job-boards.greenhouse.io/anthropic/jobs/5310731008"
    assert parse_ats_url(url) == ("greenhouse", "anthropic", "5310731008")


def test_legacy_greenhouse_board_url():
    url = "https://boards.greenhouse.io/cloudflare/jobs/8179461?gh_jid=8179461"
    assert parse_ats_url(url) == ("greenhouse", "cloudflare", "8179461")


def test_lever_url():
    url = "https://jobs.lever.co/palantir/1bb19522-3936-4adc-9ced-c3df8b5900b9"
    assert parse_ats_url(url) == ("lever", "palantir", "1bb19522-3936-4adc-9ced-c3df8b5900b9")


def test_ashby_url():
    url = "https://jobs.ashbyhq.com/Ramp/8fa367de-71ba-409e-befd-175a163acb1b"
    assert parse_ats_url(url) == ("ashby", "Ramp", "8fa367de-71ba-409e-befd-175a163acb1b")


def test_unrecognized_url_is_a_graceful_miss_not_an_error():
    assert parse_ats_url("https://www.linkedin.com/jobs/view/12345") is None
    assert parse_ats_url("not a url at all") is None


def test_employer_custom_domain_gh_jid_is_extracted_separately():
    # The board token can't be recovered from these URLs directly - parse_ats_url correctly misses,
    # and the caller falls back to parse_greenhouse_gh_jid to try known boards.
    url = "https://careers.airbnb.com/positions/8214444?gh_jid=8214444"
    assert parse_ats_url(url) is None
    assert parse_greenhouse_gh_jid(url) == "8214444"


def test_url_with_no_gh_jid_yields_no_fallback():
    assert parse_greenhouse_gh_jid("https://example.com/careers/some-job") is None
