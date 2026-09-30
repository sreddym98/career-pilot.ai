# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""H-1B sponsor records (public USCIS Employer Data Hub) and name matching.

The record says an employer FILED and was APPROVED for H-1B petitions in a
fiscal year. It is history, not a promise about this job, so the UI words it
that way. Matching a job's company to a sponsor row is by a normalised "brand
key" (legal suffixes and generic words removed), exact match only — a loose
prefix match would tie "First Solar" to every "First ..." filer.
"""
import re

_LEGAL = {"inc", "incorporated", "llc", "llp", "lp", "ltd", "limited", "corp", "corporation",
          "co", "company", "plc", "gmbh", "pllc", "pc", "na", "the"}
_GENERIC = {"services", "service", "technologies", "technology", "tech", "solutions", "systems",
            "group", "holdings", "holding", "america", "americas", "usa", "us", "com",
            "international", "global", "enterprises", "consulting", "software", "labs"}


def _tokens(name):
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return [t for t in s.split() if t]


def clean_name(name):
    """Name with legal suffixes removed: 'AMAZON.COM SERVICES LLC' -> 'amazon com services'."""
    return " ".join(t for t in _tokens(name) if t not in _LEGAL)


def brand_key(name):
    """Stable match key. Falls back to the cleaned name if everything is generic."""
    toks = [t for t in _tokens(name) if t not in _LEGAL]
    core = [t for t in toks if t not in _GENERIC]
    return " ".join(core or toks)


def sponsors_for(db, companies):
    """{company: {"approvals": n, "fy": year}} for companies with a sponsor row."""
    from api.models import H1BSponsor
    keys = {}
    for c in {c for c in companies if c}:
        k = brand_key(c)
        if k:
            keys.setdefault(k, []).append(c)
    if not keys:
        return {}
    out = {}
    rows = db.query(H1BSponsor).filter(H1BSponsor.brand_key.in_(list(keys))).all()
    for r in rows:
        for c in keys.get(r.brand_key, []):
            out[c] = {"approvals": r.approvals, "fy": r.fy}
    return out
