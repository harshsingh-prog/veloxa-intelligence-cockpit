"""Single parsing path for every source file.

All answers, agents, the DB normaliser and the evaluation oracle's *cross-checks* start from the
raw files via these loaders, so there is exactly one place where a spreadsheet quirk can be handled.
Every table carries `_row` (the real Excel row number) so citations can point at a row.
"""
from __future__ import annotations

import functools
import re
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pandas as pd
from docx import Document
from pypdf import PdfReader

from .config import DAY_BY_FOLDER, RAW_ROOT
from .permissions import PAYROLL_ALLOWED_COLUMNS


@functools.lru_cache(maxsize=None)
def path_of(name: str) -> Path:
    try:
        return next(RAW_ROOT.rglob(name))
    except StopIteration as exc:
        raise FileNotFoundError(f"{name} not found under {RAW_ROOT}") from exc


def day_of(path: Path) -> str:
    return DAY_BY_FOLDER[path.relative_to(RAW_ROOT).parts[0]]


def _header_row(raw: pd.DataFrame) -> int:
    """First row whose populated cells are all text and that has >=2 cells (title rows have 1)."""
    for i in range(min(8, len(raw))):
        vals = [v for v in raw.iloc[i].tolist() if pd.notna(v) and str(v).strip()]
        if len(vals) >= 2 and all(isinstance(v, str) for v in vals):
            return i
    return 0


@functools.lru_cache(maxsize=None)
def table(name: str, sheet: str | int = 0) -> pd.DataFrame:
    p = path_of(name)
    raw = pd.read_excel(p, sheet_name=sheet, header=None, dtype=object)
    h = _header_row(raw)
    cols = [str(c).strip() for c in raw.iloc[h].tolist()]
    df = raw.iloc[h + 1:].copy()
    df.columns = cols
    df["_row"] = df.index + 1  # Excel rows are 1-based
    df = df.dropna(how="all", subset=cols).reset_index(drop=True)
    return df


def num(series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


@functools.lru_cache(maxsize=None)
def payroll_meta() -> pd.DataFrame:
    """Payroll register restricted to the permitted non-monetary columns (see permissions.py)."""
    df = table("Payroll_Register_Jan-Mar_2026.xlsx")
    return df[PAYROLL_ALLOWED_COLUMNS + ["_row"]].copy()


@functools.lru_cache(maxsize=None)
def pdf_text(name: str) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(path_of(name))).pages)


@functools.lru_cache(maxsize=None)
def docx_text(name: str) -> str:
    d = Document(path_of(name))
    return "\n".join(p.text for p in d.paragraphs if p.text.strip())


@functools.lru_cache(maxsize=None)
def email_msg(name: str) -> dict:
    m = BytesParser(policy=policy.default).parsebytes(path_of(name).read_bytes())
    body = m.get_body(preferencelist=("plain",))
    return {
        "from": str(m["From"]), "to": str(m["To"]), "subject": str(m["Subject"]),
        "date": pd.Timestamp(str(m["Date"])), "body": (body.get_content() if body else "").strip(),
    }


@functools.lru_cache(maxsize=None)
def git_log() -> pd.DataFrame:
    df = pd.read_csv(path_of("git_log.csv"))
    df["committed_at"] = pd.to_datetime(df["committed_at"], utc=True)
    return df


# ---------------------------------------------------------------- board updates
_PERIODS = {"Board_Update_Apr-Jun_2026.pdf": "Apr-Jun 2026", "Board_Update_Jul-Sep_2026.pdf": "Jul-Sep 2026"}


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


@functools.lru_cache(maxsize=None)
def board(period: str) -> dict:
    fname = next(k for k, v in _PERIODS.items() if v == period)
    t = pdf_text(fname)
    g = lambda pat: re.search(pat, t, re.S)  # noqa: E731
    out = {
        "file": fname, "period": period,
        "arr_cr": float(g(r"ARR \(recurring\)\s*Rs\.\s*([\d.]+)\s*Cr").group(1)),
        "customers": int(g(r"Customers\s*(\d+)").group(1)),
        "team": int(g(r"\nTeam\s*(\d+)\s*Monthly").group(1)),
        "burn_lakh": float(g(r"Monthly burn\s*Rs\.\s*([\d.]+)\s*L").group(1)),
        "runway_months": int(g(r"Runway\s*(\d+)\s*months").group(1)),
        "sent": g(r"Sent (\d+ \w+ \d{4})").group(1),
    }
    prod = g(r"\nProduct\s*(.*?)\nTeam\s*\n")
    out["product"] = _flat(prod.group(1)) if prod else ""
    team = g(r"\nTeam\s*\n(?!\d)(.*?)(?:\nMarketing\s*\n|\nAsks\s*\n|$)")
    out["team_text"] = _flat(team.group(1)) if team else ""
    mk = g(r"\nMarketing\s*\n(.*)$")
    out["marketing_text"] = _flat(mk.group(1)) if mk else ""
    m = re.search(r"(\d+) registrations", out["marketing_text"])
    out["summit_registrations"] = int(m.group(1)) if m else None
    return out


# ------------------------------------------------------------------- misc helpers
def fmt_inr(x: float) -> str:
    """Indian digit grouping: 1426620 -> 14,26,620."""
    s = f"{int(round(x)):d}"
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:]); head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def lakh(x: float, nd: int = 2) -> str:
    return f"{x / 100000:.{nd}f}"
