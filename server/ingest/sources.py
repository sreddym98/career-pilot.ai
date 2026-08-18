# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Every job source, in one place.

Grouped by what they cost you and what they're good for:

  FREE + UNLIMITED   ATS boards (Greenhouse, Lever, Ashby, Workable,
                     SmartRecruiters, Recruitee, Teamtailor, JazzHR, Breezy).
                     Direct employers. Clean data. This is your base.

  FREE + PUBLIC      USAJobs, Arbeitnow, Remotive, RemoteOK, Findwork,
                     Adzuna free tier. Real APIs, no scraping, no ToS problem.

  PAID / METERED     JSearch, Adzuna paid, Coresignal. This is the ONLY leg
                     that reliably surfaces staffing-agency contract roles,
                     because agencies post to Dice and job boards, not ATS.

Nothing here scrapes. Every endpoint is a published API or a public feed.
"""
import os, re, time, datetime as dt
from typing import Iterable

try:
    import requests
except ImportError:
    raise SystemExit("pip install requests")

UA = {"User-Agent": "careerpilot/1.0 (+contact@yourdomain.com)"}
TIMEOUT = 20


def _get(url, **kw):
    kw.setdefault("headers", UA)
    kw.setdefault("timeout", TIMEOUT)
    return requests.get(url, **kw)


def _iso(v):
    if not v:
        return None
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(v / 1000 if v > 1e11 else v, dt.timezone.utc).isoformat()
    return str(v)


def _clean(html):
    if not html:
        return ""
    t = re.sub(r"<br\s*/?>", "\n", html)
    t = re.sub(r"</(p|li|div|h\d)>", "\n", t)
    t = re.sub(r"<li[^>]*>", "• ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"'))
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _rec(**k):
    """Normalised shape every connector returns."""
    k.setdefault("employment", None)
    k.setdefault("remote", None)
    k.setdefault("company_type", None)
    return k


# ══════════════════════════════════════════════════════════════
#  ATS BOARDS — free, unlimited, direct employers
# ══════════════════════════════════════════════════════════════

def greenhouse(slug, label=None):
    r = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    r.raise_for_status()
    for j in r.json().get("jobs", []):
        yield _rec(source="greenhouse", source_id=str(j.get("id")),
                   company=label or slug, title=j.get("title", ""),
                   location=(j.get("location") or {}).get("name", ""),
                   description=_clean(j.get("content", "")),
                   url=j.get("absolute_url", ""), posted_at=_iso(j.get("updated_at")))


def lever(slug, label=None):
    r = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    r.raise_for_status()
    for j in r.json():
        c = j.get("categories") or {}
        yield _rec(source="lever", source_id=j.get("id"),
                   company=label or slug, title=j.get("text", ""),
                   location=c.get("location", ""), employment=c.get("commitment"),
                   description=j.get("descriptionPlain") or _clean(j.get("description", "")),
                   url=j.get("hostedUrl", ""), posted_at=_iso(j.get("createdAt")))


def ashby(slug, label=None):
    r = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
    r.raise_for_status()
    for j in r.json().get("jobs", []):
        yield _rec(source="ashby", source_id=j.get("id"),
                   company=label or slug, title=j.get("title", ""),
                   location=j.get("location", ""), employment=j.get("employmentType"),
                   remote=j.get("isRemote"),
                   description=j.get("descriptionPlain", ""),
                   url=j.get("jobUrl", ""), posted_at=_iso(j.get("publishedAt")))


def workable(slug, label=None):
    r = _get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
    r.raise_for_status()
    d = r.json()
    for j in d.get("jobs", []):
        yield _rec(source="workable", source_id=j.get("shortcode"),
                   company=label or d.get("name") or slug, title=j.get("title", ""),
                   location=", ".join(filter(None, [j.get("city"), j.get("state"), j.get("country")])),
                   employment=j.get("employment_type"), remote=j.get("telecommuting"),
                   description=_clean(j.get("description", "")),
                   url=j.get("url") or j.get("application_url", ""),
                   posted_at=_iso(j.get("published_on")))


def smartrecruiters(slug, label=None):
    r = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100")
    r.raise_for_status()
    for j in r.json().get("content", []):
        loc = j.get("location") or {}
        yield _rec(source="smartrecruiters", source_id=j.get("id"),
                   company=label or slug, title=j.get("name", ""),
                   location=", ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country")])),
                   employment=(j.get("typeOfEmployment") or {}).get("label"),
                   remote=loc.get("remote"),
                   description="",  # detail call needed; skipped to stay fast
                   url=(j.get("ref") or "").replace("api.smartrecruiters.com/v1/companies",
                                                    "jobs.smartrecruiters.com"),
                   posted_at=_iso(j.get("releasedDate")))


def recruitee(slug, label=None):
    r = _get(f"https://{slug}.recruitee.com/api/offers/")
    r.raise_for_status()
    for j in r.json().get("offers", []):
        yield _rec(source="recruitee", source_id=str(j.get("id")),
                   company=label or slug, title=j.get("title", ""),
                   location=j.get("location", ""), employment=j.get("employment_type_code"),
                   remote=j.get("remote"),
                   description=_clean(j.get("description", "")),
                   url=j.get("careers_url") or j.get("careers_apply_url", ""),
                   posted_at=_iso(j.get("published_at")))


def teamtailor(slug, label=None):
    r = _get(f"https://{slug}.teamtailor.com/jobs.json")
    r.raise_for_status()
    for j in (r.json() if isinstance(r.json(), list) else r.json().get("jobs", [])):
        yield _rec(source="teamtailor", source_id=str(j.get("id")),
                   company=label or slug, title=j.get("title", ""),
                   location=j.get("location", ""),
                   description=_clean(j.get("body", "")),
                   url=j.get("careersite_job_url", ""), posted_at=_iso(j.get("created_at")))


def jazzhr(slug, label=None):
    r = _get(f"https://{slug}.applytojob.com/apply/jobs.json")
    r.raise_for_status()
    for j in r.json():
        yield _rec(source="jazzhr", source_id=str(j.get("id")),
                   company=label or slug, title=j.get("title", ""),
                   location=", ".join(filter(None, [j.get("city"), j.get("state")])),
                   employment=j.get("type"),
                   description=_clean(j.get("description", "")),
                   url=j.get("board_code") and f"https://{slug}.applytojob.com/apply/{j['board_code']}" or "",
                   posted_at=_iso(j.get("create_date")))


def breezy(slug, label=None):
    r = _get(f"https://{slug}.breezy.hr/json")
    r.raise_for_status()
    for j in r.json():
        loc = j.get("location") or {}
        yield _rec(source="breezy", source_id=j.get("id"),
                   company=label or slug, title=j.get("name", ""),
                   location=", ".join(filter(None, [(loc.get("city") or ""), (loc.get("country") or {}).get("name", "")])),
                   employment=(j.get("type") or {}).get("name"),
                   remote=loc.get("is_remote"),
                   description=_clean(j.get("description", "")),
                   url=j.get("url", ""), posted_at=_iso(j.get("published_date")))


ATS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "workable": workable,
       "smartrecruiters": smartrecruiters, "recruitee": recruitee, "teamtailor": teamtailor,
       "jazzhr": jazzhr, "breezy": breezy}


# ══════════════════════════════════════════════════════════════
#  FREE PUBLIC APIS — no key, no cost, real volume
# ══════════════════════════════════════════════════════════════

def usajobs(keyword, email=None, key=None, pages=3):
    """Federal jobs. Free, official, and genuinely large — thousands of IT
    and QA postings at any time. Needs a free key from developer.usajobs.gov."""
    email = email or os.environ.get("USAJOBS_EMAIL")
    key = key or os.environ.get("USAJOBS_KEY")
    if not (email and key):
        return
    h = {**UA, "Host": "data.usajobs.gov", "User-Agent": email, "Authorization-Key": key}
    for p in range(1, pages + 1):
        r = _get("https://data.usajobs.gov/api/search", headers=h,
                 params={"Keyword": keyword, "ResultsPerPage": 500, "Page": p})
        if r.status_code != 200:
            return
        items = r.json().get("SearchResult", {}).get("SearchResultItems", [])
        if not items:
            return
        for it in items:
            d = it.get("MatchedObjectDescriptor", {})
            locs = d.get("PositionLocation") or [{}]
            yield _rec(source="usajobs", source_id=d.get("PositionID"),
                       company=(d.get("OrganizationName") or "US Government"),
                       company_type="employer",
                       title=d.get("PositionTitle", ""),
                       location=locs[0].get("LocationName", ""),
                       employment=(d.get("PositionSchedule") or [{}])[0].get("Name"),
                       description=_clean((d.get("UserArea", {}).get("Details", {}) or {}).get("JobSummary", "")),
                       url=d.get("PositionURI", ""), posted_at=d.get("PublicationStartDate"))
        time.sleep(0.3)


def remotive(search=""):
    """Remote-only board with a free public API."""
    r = _get("https://remotive.com/api/remote-jobs", params={"search": search, "limit": 200})
    if r.status_code != 200:
        return
    for j in r.json().get("jobs", []):
        yield _rec(source="remotive", source_id=str(j.get("id")),
                   company=j.get("company_name", ""), title=j.get("title", ""),
                   location=j.get("candidate_required_location", "Remote"), remote=True,
                   employment=j.get("job_type"),
                   description=_clean(j.get("description", "")),
                   url=j.get("url", ""), posted_at=j.get("publication_date"))


def arbeitnow():
    """Free, no key, paginated. Mostly EU but carries US remote roles."""
    for page in range(1, 6):
        r = _get("https://www.arbeitnow.com/api/job-board-api", params={"page": page})
        if r.status_code != 200:
            return
        data = r.json().get("data", [])
        if not data:
            return
        for j in data:
            yield _rec(source="arbeitnow", source_id=j.get("slug"),
                       company=j.get("company_name", ""), title=j.get("title", ""),
                       location=j.get("location", ""), remote=j.get("remote"),
                       employment=(j.get("job_types") or [None])[0],
                       description=_clean(j.get("description", "")),
                       url=j.get("url", ""), posted_at=_iso(j.get("created_at")))
        time.sleep(0.3)


def remoteok():
    r = _get("https://remoteok.com/api")
    if r.status_code != 200:
        return
    for j in r.json()[1:]:
        yield _rec(source="remoteok", source_id=str(j.get("id")),
                   company=j.get("company", ""), title=j.get("position", ""),
                   location=j.get("location") or "Remote", remote=True,
                   description=_clean(j.get("description", "")),
                   url=j.get("url", ""), posted_at=j.get("date"))


def adzuna(what, where="us", pages=3, app_id=None, app_key=None):
    """1,000 calls/month free. Aggregates a lot of US boards including
    agency postings."""
    app_id = app_id or os.environ.get("ADZUNA_APP_ID")
    app_key = app_key or os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return
    for p in range(1, pages + 1):
        r = _get(f"https://api.adzuna.com/v1/api/jobs/{where}/search/{p}",
                 params={"app_id": app_id, "app_key": app_key, "what": what,
                         "results_per_page": 50, "max_days_old": 7,
                         "content-type": "application/json"})
        if r.status_code != 200:
            return
        res = r.json().get("results", [])
        if not res:
            return
        for j in res:
            yield _rec(source="adzuna", source_id=str(j.get("id")),
                       company=(j.get("company") or {}).get("display_name", ""),
                       title=j.get("title", ""),
                       location=(j.get("location") or {}).get("display_name", ""),
                       employment=j.get("contract_time"),
                       description=_clean(j.get("description", "")),
                       url=j.get("redirect_url", ""), posted_at=j.get("created"))
        time.sleep(0.4)


# ══════════════════════════════════════════════════════════════
#  METERED — the only reliable route to staffing-agency contracts
# ══════════════════════════════════════════════════════════════

def jsearch(query, pages=2, date_posted="today", key=None):
    """Reads Google for Jobs, which indexes Dice, Indeed, LinkedIn and the
    staffing boards. This is where contract/C2C roles actually live."""
    key = key or os.environ.get("RAPIDAPI_KEY")
    if not key:
        return
    for p in range(1, pages + 1):
        r = _get("https://jsearch.p.rapidapi.com/search",
                 headers={"X-RapidAPI-Key": key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
                 params={"query": query, "page": p, "num_pages": 1,
                         "date_posted": date_posted, "country": "us"})
        if r.status_code != 200:
            return
        for j in r.json().get("data", []):
            yield _rec(source="jsearch", source_id=j.get("job_id"),
                       company=j.get("employer_name", ""), title=j.get("job_title", ""),
                       location=", ".join(filter(None, [j.get("job_city"), j.get("job_state")])),
                       remote=j.get("job_is_remote"),
                       employment=j.get("job_employment_type"),
                       description=j.get("job_description", ""),
                       url=j.get("job_apply_link", ""),
                       posted_at=j.get("job_posted_at_datetime_utc"))
        time.sleep(1)


AGGREGATORS = {"usajobs": usajobs, "remotive": remotive, "arbeitnow": arbeitnow,
               "remoteok": remoteok, "adzuna": adzuna, "jsearch": jsearch}
