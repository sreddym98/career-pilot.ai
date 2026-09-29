# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Posting-quality gates. Pure functions, no network, no database.

A job reaches the board only if it has a real employer-facing https link, a real
title and company, and is not an obviously stale or boilerplate listing. These
checks are STATIC — they say "this can't be a legitimate posting", never "this
link works" (that is ingest/verify.py, which actually makes requests).
"""
import datetime as dt
import ipaddress
import re
from urllib.parse import urlparse, urlunparse

# Sources that list a company's own ATS board. Such a feed is authoritative:
# a posting still listed there is still open, however old its posted_at.
ATS_SOURCES = frozenset({"greenhouse", "lever", "ashby", "workable", "smartrecruiters",
                         "recruitee", "teamtailor", "jazzhr", "breezy"})

STALE_DAYS = 60
MAX_URL = 2000

_BAD_TLDS = {"test", "example", "invalid", "localhost", "local", "internal", "lan", "home",
             "corp", "intranet", "onion"}
_PLACEHOLDER_DOMAINS = {"example.com", "example.org", "example.net", "test.com", "foo.com",
                        "bar.com", "domain.com", "yourdomain.com", "yoursite.com",
                        "yourcompany.com", "company.com", "website.com", "site.com",
                        "sample.com", "placeholder.com", "abc.com", "xyz.com", "mysite.com",
                        "url.com", "link.com", "acme.com"}
_PLACEHOLDER_WORD = re.compile(r"placeholder|example|lorem|your-?(company|site|domain)|changeme", re.I)


def normalize_apply_url(url):
    """Return a cleaned https URL, or None if it can't be a real apply link."""
    if not isinstance(url, str):
        return None
    u = url.strip()
    if not u or len(u) > MAX_URL or re.search(r"\s", u):
        return None
    if u[:7].lower() == "http://":          # every real ATS serves https; upgrade, verify later
        u = "https://" + u[7:]
    try:
        p = urlparse(u)
        host = (p.hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    if p.scheme.lower() != "https" or not host or p.username or p.password:
        return None
    try:
        p.port
    except ValueError:
        return None
    if host == "localhost" or "." not in host:
        return None
    try:
        ipaddress.ip_address(host)
        return None                          # raw IPs are never a careers page
    except ValueError:
        pass
    labels = host.split(".")
    tld = labels[-1]
    if (not re.fullmatch(r"[a-z]{2,24}|xn--[a-z0-9-]+", tld) or tld in _BAD_TLDS
            or any(not l or len(l) > 63 or l.startswith("-") or l.endswith("-") for l in labels)):
        return None
    base = ".".join(labels[-2:])
    if base in _PLACEHOLDER_DOMAINS or host in _PLACEHOLDER_DOMAINS or _PLACEHOLDER_WORD.search(host):
        return None
    return urlunparse((p.scheme.lower(), p.netloc, p.path, p.params, p.query, ""))


_BAD_TITLE = re.compile(
    r"^\W*(test|tests|test job|test job title|test req|test posting|job title|position title|"
    r"job|position|opening|untitled|title|tbd|n/?a|na|none|null|undefined|sample|sample job|"
    r"example|example job|placeholder|lorem ipsum.*|new job|new position|job posting|"
    r"quality checker|qa tester entry level)\W*$", re.I)
_BAD_COMPANY = re.compile(r"^\W*(unknown|n/?a|na|none|null|undefined|tbd|test|sample|example|"
                          r"placeholder|company|company name|your company|confidential|"
                          r"not specified|not provided|-+)\W*$", re.I)


def bad_title(title) -> bool:
    t = (title or "").strip()
    return (len(t) < 3 or len(t) > 200 or not re.search(r"[A-Za-z]{2}", t)
            or bool(_BAD_TITLE.match(t)) or "lorem ipsum" in t.lower())


def bad_company(company) -> bool:
    c = (company or "").strip()
    return len(c) < 2 or not re.search(r"[A-Za-z0-9]", c) or bool(_BAD_COMPANY.match(c))


def is_stale(posted_at, source, now, days=STALE_DAYS) -> bool:
    """Older than `days`, unless the source is a company ATS board (which only
    lists postings that are still open). Unknown posted_at is NOT stale — many
    feeds omit it, and freshness then rests on last_seen and link checks."""
    if posted_at is None or source in ATS_SOURCES:
        return False
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=dt.timezone.utc)
    return (now - posted_at) > dt.timedelta(days=days)


def reject_reason(rec, posted_at, now):
    """Why this record must not be ingested, or None if it may be.
    `posted_at` is the record's already-parsed datetime (or None)."""
    if bad_title(rec.get("title")):
        return "bad_title"
    if bad_company(rec.get("company")):
        return "bad_company"
    if normalize_apply_url(rec.get("url")) is None:
        return "bad_url"
    if is_stale(posted_at, rec.get("source", ""), now):
        return "stale"
    return None
