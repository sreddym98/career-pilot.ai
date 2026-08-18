# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""JD text → visa eligibility flags.

'y' accepted | 'n' explicitly excluded | 'u' not stated.

Default is ALWAYS 'u'. Most postings say nothing about sponsorship, and
treating silence as rejection would delete ~70% of the board and make the
product useless. Only mark 'n' on an explicit statement.
"""
import re

NEGATIVE = [
    (r"\bno\s+(h-?1\s?b|visa)\s+sponsor", {"h1b": "n"}),
    (r"\b(are\s+)?(un(able|willing)|not\s+able)\s+to\s+sponsor", {"h1b": "n", "opt": "n"}),
    (r"\b(we\s+)?(do\s+not|don'?t|cannot|can'?t|won'?t)\s+(currently\s+)?(offer\s+|provide\s+)?sponsor", {"h1b": "n", "opt": "n"}),
    (r"\bsponsorship\s+(is\s+)?(not\s+|un)available", {"h1b": "n", "opt": "n"}),
    (r"\b(us|u\.s\.)\s+citizen(ship)?\s+(only|required|is\s+required)", {"usc": "y", "h1b": "n", "opt": "n", "gc": "n"}),
    (r"\bcitizens?\s+or\s+green\s+card", {"usc": "y", "gc": "y", "h1b": "n", "opt": "n"}),
    (r"\bmust\s+be\s+(a\s+)?(us|u\.s\.)\s+citizen", {"usc": "y", "h1b": "n", "opt": "n", "gc": "n"}),
    (r"\b(able|authorized)\s+to\s+work\s+.{0,30}without\s+sponsorship", {"h1b": "n", "opt": "n"}),
    (r"\bsecurity\s+clearance\b", {"h1b": "n", "opt": "n", "gc": "n"}),
    (r"\busc\s*/?\s*gc\s+only", {"usc": "y", "gc": "y", "h1b": "n", "opt": "n"}),
    (r"\bno\s+(opt|cpt|ead)\b", {"opt": "n"}),
]

POSITIVE = [
    (r"\bh-?1\s?b\s+(transfer|sponsor)", {"h1b": "y"}),
    (r"\bwill(ing\s+to)?\s+sponsor", {"h1b": "y"}),
    (r"\bsponsorship\s+(is\s+)?available", {"h1b": "y"}),
    (r"\bopt\b|\bcpt\b|\bead\b|\bstem\s+opt\b", {"opt": "y"}),
    (r"\bany\s+visa\b|\ball\s+visa", {"usc": "y", "gc": "y", "h1b": "y", "opt": "y"}),
]

# "only H1B" — agencies do this; it excludes citizens, which is unusual
# but real, and getting it wrong wastes the user's application.
ONLY_H1B = re.compile(r"\bonly\s+h-?1\s?b?\b|\bh-?1\s?b?\s+only\b", re.I)


# "Visa: USC, GC, H1B, H4 EAD" — agencies list accepted statuses explicitly.
VISA_LIST = re.compile(r"\bvisa\s*(status)?\s*[:\-]\s*([^\n.;]{3,90})", re.I)
TOKENS = {
    "usc": [r"\busc\b", r"\bus\s+citizen", r"\bcitizen"],
    "gc":  [r"\bgc\b", r"\bgreen\s*card", r"\bpermanent\s+resident", r"\blpr\b"],
    "h1b": [r"\bh-?1\s?b\b", r"\bh1\b"],
    "opt": [r"\bopt\b", r"\bcpt\b", r"\bead\b", r"\bh-?4\b", r"\bl-?2\b", r"\btn\b", r"\be-?3\b"],
}


def parse_visa(text: str) -> dict:
    t = (text or "").lower()
    out = {"usc": "u", "gc": "u", "h1b": "u", "opt": "u"}

    if ONLY_H1B.search(t):
        return {"usc": "n", "gc": "n", "h1b": "y", "opt": "n"}

    # explicit accepted-status list wins over generic phrasing
    m = VISA_LIST.search(t)
    if m:
        listed = m.group(2)
        for k, pats in TOKENS.items():
            if any(re.search(p, listed, re.I) for p in pats):
                out[k] = "y"

    for pat, flags in POSITIVE:
        if re.search(pat, t, re.I):
            out.update(flags)
    # negatives win — an explicit exclusion beats a generic positive
    for pat, flags in NEGATIVE:
        if re.search(pat, t, re.I):
            out.update(flags)
    return out


if __name__ == "__main__":
    cases = [
        ("Visa: USC, GC, H1B", {"usc": "y", "gc": "y", "h1b": "y"}),
        ("Visa Status: H1B, H4 EAD, L2, E3, TN", {"h1b": "y", "opt": "y"}),
        ("We are unable to sponsor at this time.", {"h1b": "n"}),
        ("Sponsorship is not available for this role.", {"h1b": "n"}),
        ("Citizens or green card holders only.", {"usc": "y", "gc": "y", "h1b": "n"}),
        ("USC/GC only, no C2C", {"usc": "y", "h1b": "n"}),
        ("Rate is $53/hr on C2C, no corp to corp", {"h1b": "u"}),
        ("H1B only", {"h1b": "y", "usc": "n"}),
        ("We are unable to sponsor H1B visas at this time.", {"h1b": "n"}),
        ("Visa: USC, H1B, H4 EAD, L2, E3, TN", {"opt": "y"}),
        ("NOTE: ONLY H1", {"h1b": "y", "usc": "n"}),
        ("Must be a US citizen. Security clearance required.", {"h1b": "n", "gc": "n"}),
        ("Great team, competitive pay, remote friendly.", {"h1b": "u", "usc": "u"}),
        ("H1B transfer welcome, we sponsor.", {"h1b": "y"}),
        ("Candidates must be authorized to work in the US without sponsorship.", {"h1b": "n"}),
    ]
    ok = 0
    for txt, want in cases:
        got = parse_visa(txt)
        hit = all(got[k] == v for k, v in want.items())
        ok += hit
        print(("PASS " if hit else "FAIL ") + txt[:52].ljust(54), got)
    print(f"\n{ok}/{len(cases)} passed")
