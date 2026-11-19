"""Hallucination guard: nothing a language model writes is shown unless it passes these checks.

The deterministic engine produces a verified answer plus the evidence it rests on. A model may only
*re-phrase* it. A rewrite is accepted when ALL hold:
  1. every number/date token also occurs in the verified text or evidence;
  2. every identifier (REQ-014, ATLAS-16, INC-201, VX007 …) occurs there too;
  3. no person is named who is not named in the verified text or evidence;
  4. it keeps at least one uncertainty marker when the verified answer had one;
  5. it contains no forbidden claim pattern (salary amounts, resignation predictions, Slack content …).
Otherwise the verified deterministic text is used. The model can therefore lower style quality,
never factual quality.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

NAMES = ["ananya", "manoj", "meera", "vikram", "deepa", "nikhil", "priya", "divya", "arjun", "karthik", "aisha",
         "sneha", "snehal", "siddharth", "fatima", "rohan", "imran", "lakshmi", "rahul", "kavya", "pria", "sid"]
UNCERTAIN = ["not established", "unresolved", "unverified", "unknown", "do not know", "don't know", "cannot", "can't",
             "no record", "pending", "proposed", "not confirmed", "disputed", "not available", "does not", "do not",
             "unclear", "not supported", "not an", "no exact"]
FORBIDDEN = [
    r"will (definitely |certainly )?(resign|quit|leave)", r"\b(is|are) (definitely|certainly) (going to )?(resign|quit|leave)",
    r"(probability|likelihood|chance) of (quitting|resigning|leaving)", r"slack (message|channel)s? (show|say|reveal)",
    r"overpaid by", r"salary (is|was) (rs|₹|inr)", r"(rs\.?|₹|inr)\s?[\d,]+\s*(per month|a month|ctc|salary)",
    r"ignore (the )?(previous|above)", r"as an ai language model",
]
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_ID = re.compile(r"\b(?:REQ|ATLAS|INC|VX|EV|JIRA|PIS|JV|SEV)-?\d+\b", re.I)


def numbers(text: str) -> set[str]:
    out = set()
    for m in _NUM.findall(text):
        t = m.replace(",", "").rstrip(".")
        if "." in t:
            t = t.rstrip("0").rstrip(".")
        out.add(t.lstrip("0") or "0")
        if "." not in t and len(t) > 3:  # Indian vs western grouping of the same amount compares equal after comma removal
            pass
    return out


_WORDS = r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|dozen|couple|several|roughly|approximately|about|around|nearly|almost)\b"


def number_words(text: str) -> set[str]:
    return set(re.findall(_WORDS, text.lower()))


def ids(text: str) -> set[str]:
    return {m.upper().replace("-", "") for m in _ID.findall(text)}


def names(text: str) -> set[str]:
    low = text.lower()
    return {n for n in NAMES if re.search(rf"\b{n}\b", low)}


@dataclass
class GuardResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def check(candidate: str, verified: str, evidence: str = "", *, require_uncertainty: bool = False) -> GuardResult:
    allowed = verified + "\n" + evidence
    why: list[str] = []
    if not candidate or not candidate.strip():
        return GuardResult(False, ["empty"])
    extra_nums = numbers(candidate) - numbers(allowed)
    if extra_nums:
        why.append(f"new numbers: {sorted(extra_nums)[:5]}")
    extra_words = number_words(candidate) - number_words(allowed)
    if extra_words:
        why.append(f"new number words / approximations: {sorted(extra_words)[:5]}")
    extra_ids = ids(candidate) - ids(allowed)
    if extra_ids:
        why.append(f"new identifiers: {sorted(extra_ids)[:5]}")
    extra_names = names(candidate) - names(allowed)
    if extra_names:
        why.append(f"new people: {sorted(extra_names)[:5]}")
    low = candidate.lower()
    for pat in FORBIDDEN:
        if re.search(pat, low):
            why.append(f"forbidden pattern: {pat}")
    if require_uncertainty and not any(u in low for u in UNCERTAIN):
        why.append("dropped uncertainty wording")
    if len(candidate) > 2 * len(verified) + 300:
        why.append("much longer than verified answer")
    return GuardResult(not why, why)


def has_uncertainty(text: str) -> bool:
    low = text.lower()
    return any(u in low for u in UNCERTAIN)
