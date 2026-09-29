# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Apply-link verification: a bounded background pass after ingest.

For jobs whose link has never been checked (or was last checked long ago) we
request apply_url and record what actually happened:

    ok           final response 2xx/3xx            -> verified_at = now, shown as "Verified link"
    dead         404 or 410                        -> the ONLY case that deactivates the job
    blocked      401/403/429/451/999 (bot walls)   -> unverified, job stays live
    unreachable  timeout / DNS / TLS / connection  -> unverified, job stays live
    error        5xx or anything else              -> unverified, job stays live

We never claim a link is verified unless the request succeeded, and never
retire a job on ambiguity: many career sites block bots, rate-limit, or flake.

Bounds: per-request timeout, minimum gap per host, worker cap, wall-clock
budget, max rows per pass. Redirects are followed by hand, at most 5 hops, and
every hop must be a public https host (no SSRF into private networks).
Network happens in worker threads; the database is written from the caller's
thread only.
"""
import datetime as dt
import ipaddress
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests

from ingest.quality import normalize_apply_url

UA = {"User-Agent": "careerpilot-linkcheck/1.0 (+https://careerpilot.ai)",
      "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
TIMEOUT = (4, 8)
MAX_HOPS = 5
BLOCKED = {401, 403, 407, 429, 451, 999}
DEAD = {404, 410}
RECHECK_DAYS = 14

_sleep = time.sleep          # patched in tests
_clock = time.monotonic


def _public_host(host):
    """True if every address the host resolves to is publicly routable."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return None                          # unresolvable -> "unreachable", not "dead"
    addrs = {i[4][0].split("%")[0] for i in infos}
    return bool(addrs) and all(ipaddress.ip_address(a).is_global for a in addrs)


class HostLimiter:
    """Minimum gap between requests to one host, across threads."""

    def __init__(self, interval=1.0):
        self.interval, self._next, self._lock = interval, {}, threading.Lock()

    def slot(self, host):
        """Reserve the next slot for `host`; returns seconds to wait."""
        with self._lock:
            now = _clock()
            at = max(now, self._next.get(host, 0.0))
            self._next[host] = at + self.interval
            return at - now


def check_url(url, resolver=_public_host, limiter=None, deadline=None):
    """One link check. Returns (status, http_code). Never raises."""
    cur = normalize_apply_url(url)
    if cur is None:
        return "error", None
    code = None
    try:
        for _ in range(MAX_HOPS + 1):
            host = urlparse(cur).hostname or ""
            pub = resolver(host)
            if pub is None:
                return "unreachable", None
            if not pub:
                return "error", None
            if limiter:
                wait = limiter.slot(host)
                if deadline is not None and _clock() + wait >= deadline:
                    return "skipped", None
                if wait > 0:
                    _sleep(wait)
            r = None
            try:
                r = requests.head(cur, headers=UA, timeout=TIMEOUT, allow_redirects=False)
                if r.status_code in (400, 403, 405, 406, 429, 501) or r.status_code >= 500:
                    r = requests.get(cur, headers=UA, timeout=TIMEOUT, allow_redirects=False,
                                     stream=True)      # many hosts reject HEAD only
            except (requests.ConnectionError, requests.Timeout, requests.exceptions.SSLError):
                return "unreachable", None
            code = r.status_code
            loc = r.headers.get("Location") if hasattr(r, "headers") else None
            close = getattr(r, "close", None)
            if close:
                close()
            if code in (301, 302, 303, 307, 308) and loc:
                nxt = normalize_apply_url(urljoin(cur, loc))
                if nxt is None:
                    return "error", code
                cur = nxt
                continue
            if code in DEAD:
                return "dead", code
            if code in BLOCKED:
                return "blocked", code
            if 200 <= code < 400:
                return "ok", code
            return "error", code
        return "error", code                 # redirect loop
    except Exception:
        return "error", code


def verify_links(db, budget_s=60, workers=6, host_interval=1.0, limit=150, now=None,
                 recheck_days=RECHECK_DAYS, resolver=_public_host):
    """Check a bounded batch of live jobs. Returns a stats dict."""
    from api.models import Job
    from sqlalchemy import or_
    now = now or dt.datetime.now(dt.timezone.utc)
    st = {"checked": 0, "ok": 0, "dead": 0, "blocked": 0, "unreachable": 0, "error": 0,
          "skipped": 0, "deactivated": 0}
    if budget_s <= 0:
        return st
    rows = (db.query(Job.fingerprint, Job.apply_url)
            .filter(Job.active.is_(True), Job.apply_url.isnot(None), Job.apply_url != "",
                    or_(Job.link_checked_at.is_(None),
                        Job.link_checked_at < now - dt.timedelta(days=recheck_days)))
            .order_by(Job.link_checked_at.is_(None).desc(), Job.first_seen.desc())
            .limit(limit).all())
    if not rows:
        return st

    deadline = _clock() + budget_s
    limiter = HostLimiter(host_interval)

    def work(fp, url):
        if _clock() >= deadline:
            return fp, "skipped", None
        s, c = check_url(url, resolver, limiter, deadline)
        return fp, s, c

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(work, fp, url) for fp, url in rows]
        for f in as_completed(futs):
            try:
                fp, status, code = f.result()
            except Exception:
                st["error"] += 1
                continue
            if status == "skipped":
                st["skipped"] += 1
                continue
            job = db.get(Job, fp)
            if job is None:
                continue
            job.link_checked_at, job.link_status, job.link_http = now, status, code
            if status == "ok":
                job.verified_at = now
            elif status == "dead":
                job.active = False           # definite 404/410 only
                st["deactivated"] += 1
            st["checked"] += 1
            st[status] += 1
    db.commit()
    return st
