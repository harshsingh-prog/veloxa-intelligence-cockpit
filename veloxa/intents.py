"""Question understanding: normalisation, entity extraction and date parsing.

All matching is word-boundary regex on a normalised string. (The previous version used substring
tests such as `'cro' in q`, which fires on "across"/"microphone" and `'arr' in q`, which fires on "warranty".)
"""
from __future__ import annotations

import re

from . import facts as F

# machine-transcription / spelling variants -> canonical token (documented in TRANSCRIPT_NOTES.md)
_ALIASES = [
    (r"\bpria\b", "priya"), (r"\bpriyaa\b", "priya"), (r"\bpnair\b", "priya"),
    (r"\bjeera\b|\bjeera board\b", "jira"), (r"\bslag\b", "slack"), (r"\bkartik\b", "karthik"),
    (r"\bayesha\b", "aisha"), (r"\bsidharth\b|\bsiddarth\b", "siddharth"), (r"\bsid\b", "siddharth"),
    (r"\bshaikh\b", "sheikh"), (r"\bkekka\b|\bkayka\b", "keka"), (r"\bcult amp\b", "culture amp"),
    (r"\bhub sport\b|\bhub spot\b", "hubspot"), (r"\bjoho books\b", "zoho books"),
    (r"\bversion (three|3)\b|\bv ?3\b|\brouting engine\b", "atlas"),
]
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def norm(q: str) -> str:
    s = q.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"'s\b", "", s)  # possessives: "rahul's" -> "rahul"
    for pat, rep in _ALIASES:
        s = re.sub(pat, rep, s)
    return re.sub(r"\s+", " ", s).strip()


def has(q: str, *pats: str) -> bool:
    return any(re.search(p, q) for p in pats)


# --------------------------------------------------------------------------- people
def persons(q: str) -> list[str]:
    """Employee IDs (plus 'SNEHAL' for the unresolved contractor-like name) in order of appearance."""
    found: list[tuple[int, str]] = []
    for _, e in F.employees().iterrows():
        for token in {e["first"], e["name"].lower()}:
            m = re.search(rf"\b{re.escape(token)}\b", q)
            if m:
                found.append((m.start(), e["emp_id"]))
                break
    m = re.search(r"\bsnehal\b", q)
    if m:
        found = [f for f in found if f[1] != "VX012"] if not re.search(r"\bsneha\b", q) else found
        found.append((m.start(), "SNEHAL"))
    found.sort()
    out: list[str] = []
    for _, i in found:
        if i not in out:
            out.append(i)
    return out


TITLE_ALIASES = {
    r"\bcfo\b|chief financial officer|finance head|head of finance|(leads?|runs?|heads?|in charge of) (the )?finance( team)?": "CFO",
    r"\bceo\b|chief executive": "CEO",
    r"vp (of )?engineering|head of engineering|engineering head|\bvpe\b|(leads?|runs?|heads?|in charge of|manages) (the )?engineering( team)?": "VP Engineering",
    r"head of people|hr head|head of hr|head of people (&|and) ops|(leads?|runs?|heads?|in charge of) (the )?(hr|people)( team)?": "Head of People & Ops",
    r"head of marketing|marketing head|\bcmo\b|(leads?|runs?|heads?|in charge of) (the )?marketing( team)?": "Head of Marketing",
    r"fp&a|fpa manager|planning manager": "FP&A Manager",
    r"sales lead|head of sales": "Sales Lead",
    r"support lead|head of support": "Customer Support Lead",
    r"talent partner|recruiter": "Talent Partner",
    r"\bsre\b|site reliability": "Site Reliability Engineer",
    r"staff engineer": "Staff Engineer",
    r"frontend engineer|front-end engineer": "Senior Frontend Engineer",
    r"product marketing manager": "Product Marketing Manager",
    r"performance marketing": "Performance Marketing Manager",
    r"accounts (&|and) payroll|payroll executive": "Accounts & Payroll Executive",
    r"hr (&|and) office|office executive": "HR & Office Executive",
    r"account executive": "Account Executive",
    r"support associate": "Support Associate",
}


def title_in(q: str) -> str | None:
    for pat, title in TITLE_ALIASES.items():
        if re.search(pat, q):
            return title
    return None


DEPT_ALIASES = {
    r"\bengineering\b|\beng\b|\bengineers\b|\btech team\b": "Engineering",
    r"\bfinance\b|\baccounts\b": "Finance",
    r"\bpeople\b|\bhr\b|\bpeople (&|and) ops\b|\bhuman resources\b": "People & Ops",
    r"\bmarketing\b": "Marketing", r"\bsales\b": "Sales", r"\bsupport\b": "Support",
}


def dept_in(q: str) -> str | None:
    for pat, dept in DEPT_ALIASES.items():
        if re.search(pat, q):
            return dept
    return None


# ----------------------------------------------------------------------------- dates
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"


def parse_date(q: str, default_year: int = 2026) -> str | None:
    """Return ISO date for the first date-like expression in `q` (dd/mm/yyyy is Indian order)."""
    m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", q)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", q)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MON}\b,?\s*(20\d{{2}})?", q)
    if m:
        return f"{int(m.group(3) or default_year):04d}-{MONTHS[m.group(2)[:3]]:02d}-{int(m.group(1)):02d}"
    m = re.search(rf"\b{_MON}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b,?\s*(20\d{{2}})?", q)
    if m:
        return f"{int(m.group(3) or default_year):04d}-{MONTHS[m.group(1)[:3]]:02d}-{int(m.group(2)):02d}"
    return None


def month_in(q: str) -> int | None:
    """A bare month reference such as 'in august' (used for incident questions)."""
    m = re.search(rf"\b(?:in|during|for|of)\s+{_MON}\b", q)
    return MONTHS[m.group(1)[:3]] if m else None


def quarter_in(q: str) -> str | None:
    for pat, label in ((r"oct\w*\s*[-–to ]+\s*dec", "Oct-Dec 2025"), (r"jan\w*\s*[-–to ]+\s*mar", "Jan-Mar 2026"),
                       (r"apr\w*\s*[-–to ]+\s*jun", "Apr-Jun 2026"), (r"jul\w*\s*[-–to ]+\s*sep", "Jul-Sep 2026")):
        if re.search(pat, q):
            return label
    return None
