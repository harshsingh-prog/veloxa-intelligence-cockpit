"""Event timeline for "what did we know on date X?".

Two different questions are kept apart (this is the bitemporal idea from ARCHITECTURE.md):
  * company layer  - what the company's own records already said on date X (event_date <= X)
  * cockpit layer  - what had been *released to the cockpit* by date X (release timestamps)
A later export can reveal an earlier event; that does not mean anyone knew it then.
"""
from __future__ import annotations

import functools
import re

import pandas as pd

from . import data as D
from . import facts as F
from .config import RELEASES, available, ts
from .data import fmt_inr


def _flat(s: str, n: int = 220) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _ev(date, title, detail, source, file_name, importance, tags):
    return {"date": str(date)[:10], "title": title, "detail": detail, "source": source,
            "day": F.day(file_name), "importance": importance, "tags": set(tags)}


@functools.lru_cache(maxsize=None)
def events() -> list[dict]:
    ev: list[dict] = []
    # board updates -------------------------------------------------------------
    for period, f in (("Apr-Jun 2026", F.BOARD_Q2), ("Jul-Sep 2026", F.BOARD_Q3)):
        b = D.board(period)
        d = pd.to_datetime(b["sent"], format="%d %b %Y").date()
        ev.append(_ev(d, f"Board update ({period}) sent",
                      f"ARR ₹{b['arr_cr']} Cr, burn ₹{b['burn_lakh']:g} L/month, {b['customers']} customers, runway {b['runway_months']} months. {b['product']}",
                      F.src(f, "Key numbers and Product section"), f, 5, ["board", "finance", "atlas"]))
    # emails --------------------------------------------------------------------
    meta = {
        "01.eml": (3, ["payroll"]), "02.eml": (3, ["payroll"]), "03.eml": (4, ["payroll"]),
        "04.eml": (4, ["atlas", "engineering"]), "05.eml": (3, ["marketing", "atlas"]),
        "06.eml": (5, ["hiring", "engineering", "finance"]), "07.eml": (3, ["hiring", "engineering"]),
        "08.eml": (5, ["atlas", "engineering", "incidents"]), "09.eml": (4, ["atlas", "engineering", "priya"]),
        "10.eml": (2, ["people"]), "11.eml": (4, ["people", "engineering", "pulse"]),
    }
    for name, (imp, tags) in meta.items():
        m = D.email_msg(name)
        ev.append(_ev(m["date"].date(), f"Email {name[:2]}: {m['subject']}",
                      f"{m['from'].split('<')[0].strip()} to {m['to'].split('<')[0].strip()}: {_flat(m['body'])}",
                      F.src(name, "email"), name, imp, tags))
    # resignation letter ----------------------------------------------------------
    ev.append(_ev("2026-09-15", "Siddharth Mehta resigns (letter dated 15 Sep)",
                  "Product Marketing Manager; last working day stated as 31 October 2026.",
                  F.src("Resignation_Letter_SM.pdf", "page 1"), "Resignation_Letter_SM.pdf", 5, ["marketing", "people", "resignation"]))
    # Jira + incidents -----------------------------------------------------------------
    v = F.jira_version()
    ev.append(_ev(v["changed_on"], f"Atlas GA date changed {v['original']} → {v['revised']} in Jira",
                  f"Changed by {v['changed_by']}.", v["source"], F.VER_F, 5, ["atlas", "engineering"]))
    for _, r in F.incidents().iterrows():
        sev1 = r["Severity"] == "SEV1"
        ev.append(_ev(r["opened_utc"].date(), f"{r['ID']} {r['Severity']} on {r['Service']}",
                      f"Responder recorded as {r['Responder']}.", F.src(F.INC_F, f"row {int(r['_row'])}"), F.INC_F,
                      5 if sev1 else 2, ["incidents", "engineering", "atlas"] + (["sev1"] if sev1 else [])))
    # hiring -------------------------------------------------------------------------
    for r in F.hiring_rows():
        imp = 4 if r["status"] == "On hold" else 3
        ev.append(_ev(r["status_date"], f"{r['req']} {r['role']}: {r['status']}",
                      f"Team {r['team']}; {r['pipeline']} in pipeline. {r['notes']}".strip(),
                      F.src(F.HIRE_F, f"row {r['row']}"), F.HIRE_F, imp, ["hiring", r["team"].lower()]))
    # people ------------------------------------------------------------------------
    rahul = F.emp("VX018")
    ev.append(_ev(rahul["join_date"], "Rahul Verma joins as Backend Engineer", "Per Employee Master join date.",
                  F.src(F.EMP_F, f"row {int(rahul['_row'])}"), F.EMP_F, 2, ["people", "engineering", "payroll"]))
    sid = F.emp("VX013")
    ev.append(_ev(sid["exit_date"], "Siddharth Mehta's recorded exit date", "Employee Master: notice period, exit date.",
                  F.src(F.EMP_F, f"row {int(sid['_row'])}"), F.EMP_F, 4, ["marketing", "people", "resignation"]))
    # finance -----------------------------------------------------------------------
    for l in F.gl_lines(lambda d: d["Cost Centre"].isin(["MKT-EVT", "PPL-HIR", "ENG-OPS", "SAL-TRV"])):
        imp = 3 if l["cc"] in ("MKT-EVT", "PPL-HIR", "ENG-OPS") else 1
        ev.append(_ev(l["date"], f"GL: {l['vendor']} ₹{fmt_inr(l['amount'])} ({l['cc']})", l["narr"],
                      F.src(F.GL_F, f"row {l['row']}"), F.GL_F, imp, ["finance", l["cc"].lower()]))
    for l in F.leave_for("F. Sheikh"):
        ev.append(_ev(l["from"], f"F. Sheikh on leave {l['from']} to {l['to']} ({l['days']} days)", "Leave Register entry.",
                      F.src(F.LEAVE_F, f"row {l['row']}"), F.LEAVE_F, 2, ["payroll", "finance"]))
    o = F.oncall_summary()
    ev.append(_ev(o["first_snehal_week"], "'Snehal' first appears on the on-call rota (week of this date)",
                  "Identity relationship to Sneha Kulkarni is not established.", o["source"], F.ONCALL_F, 3, ["engineering", "incidents"]))
    c = F.contractor()
    ev.append(_ev(c["invoice_date"], "Patil Infra Services invoice PIS-114 (S. Patil, on-call SRE support, Sept)",
                  f"₹{fmt_inr(c['base'])} + IGST ₹{fmt_inr(c['igst'])} = ₹{fmt_inr(c['total'])}.", c["source"], "Invoice_PIS-114.pdf", 2, ["engineering", "finance"]))
    # CEO voice notes: undated transcripts, dated at the moment they were released ------------
    for name, text, tags in (
        ("T6a_CEO_Voice_Note.docx", "CEO asks for the top three worries without typing.", ["ceo"]),
        ("T6b_CEO_Voice_Note.docx", "CEO: marketing to report to the new CRO from next month or the month after.", ["marketing", "cro"]),
        ("T6c_CEO_Voice_Note.docx", "CEO asks for a quit-likelihood ranking and Slack messages.", ["ceo", "people"]),
        ("T6d_CEO_Voice_Note.docx", "CEO reports that 'Pria' resigned; notice period 'two months, I think'.", ["priya", "resignation", "atlas"])):
        day = F.day(name)
        ev.append(_ev(RELEASES[day][:10], f"{name[:3]} CEO voice note (undated; dated at release)", text,
                      F.src(name, "transcript"), name, 4, tags))
    return sorted(ev, key=lambda e: (e["date"], -e["importance"]))


def board_as_of(date: str) -> dict | None:
    best = None
    for period in ("Apr-Jun 2026", "Jul-Sep 2026"):
        b = D.board(period)
        sent = pd.to_datetime(b["sent"], format="%d %b %Y")
        if sent <= pd.Timestamp(date):
            best = b
    return best


def known_on(date: str, as_of: str, tags: set[str] | None = None, limit: int = 8) -> list[dict]:
    """Events dated <= `date` whose source had been released by `as_of`, most important/recent first."""
    pool = [e for e in events() if e["date"] <= date and available(as_of, e["day"])]
    if tags:
        pool = [e for e in pool if e["tags"] & tags] or pool
    picked = sorted(pool, key=lambda e: (-e["importance"], e["date"]), reverse=False)
    picked = sorted(picked[:limit], key=lambda e: e["date"])
    return picked


def cockpit_knowledge_on(date: str) -> list[str]:
    """Release days whose timestamp is on/before the *end* of `date` (IST)."""
    end = ts(date) + pd.Timedelta(hours=23, minutes=59)
    return [d for d, t in RELEASES.items() if ts(t) <= end]
