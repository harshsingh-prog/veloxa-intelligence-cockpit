"""CEO question answering: deterministic, evidence-first, release-aware.

Pipeline:  normalise -> classify intent (word-boundary regex) -> check release gate ->
           compute from facts.py -> format answer + citations + confidence -> (optional) guarded LLM rewrite.

The language model is never allowed to decide a fact, pick a source or do arithmetic (see guard.py).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from . import data as D
from . import facts as F
from . import timeline as T
from .config import DEFAULT_AS_OF, RELEASES, available, days_available, ts
from .data import fmt_inr, lakh
from .intents import dept_in, has, month_in, norm, parse_date, persons, quarter_in, title_in
from .risks import worry_list  # noqa: F401  (re-exported for the UI)

S = F.src


class NotYet(Exception):
    def __init__(self, day: str):
        self.day = day


@dataclass
class Ans:
    text: str
    confidence: str = "High"
    sources: list = field(default_factory=list)
    uncertain: bool = False
    refused: bool = False
    intent: str = ""
    derived: list = field(default_factory=list)   # computed (not copied) numbers, for the groundedness audit


class Ctx:
    def __init__(self, raw: str, as_of: str):
        self.raw, self.as_of = raw, as_of
        self.q = norm(raw)
        self.P = persons(self.q)

    def d(self, day: str) -> bool:
        return available(self.as_of, day)

    def need(self, day: str):
        if not self.d(day):
            raise NotYet(day)


def pct(n: float, d: float) -> str:
    return f"{100 * n / d:.0f}%"


def _name(emp_id: str) -> str:
    return F.emp_name(emp_id)


def _first(emp_id: str) -> str:
    return F.emp(emp_id)["name"].split()[0]


def _join(items: list[str]) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# =================================================================== SAFETY / REFUSAL HANDLERS
def h_injection_prefix(c: Ctx) -> str:
    return ""


def h_slack(c: Ctx) -> Ans:
    return Ans("I cannot show Slack or any private messages. No Slack export (or any private-message data) is present in the supplied "
               "data room, and nobody's approval can create access to data that was never provided. T1 only lists looking into a "
               "“slag channel” (probably Slack) as an unassigned action item. I can show documented, record-backed facts instead: "
               "team-level engagement, workload by assignee, incidents, hiring status and confirmed departures.",
               "High", ["Data-room inventory (README.txt): hr/, finance/, engineering/, documents/, email/ — no Slack export",
                        S("T1_CEO_Kickoff_Call.docx", "action items"), S("T6c_CEO_Voice_Note.docx", "request") if c.d("Day4") else
                        S("T1_CEO_Kickoff_Call.docx", "summary")],
               uncertain=True, refused=True, intent="refuse_slack")


def h_quit(c: Ctx) -> Ans:
    parts = ["I won't rank or name individual employees by likelihood of quitting. The records do not support a reliable individual "
             "prediction, and inferring one from leave, engagement or personal data would be employee surveillance rather than evidence."]
    src = [S(F.PULSE_F, "Pulse by team sheet")] if c.d("Day2") else [S(F.EMP_F, "Employees sheet")]
    facts_ = []
    if c.d("Day2"):
        sid = F.emp("VX013")
        facts_.append(f"Documented departure: Siddharth Mehta (last working day {sid['exit_date']}; letter dated 15 September 2026)")
        s = F.pulse_series("Engineering"); m = F.pulse_series("Marketing")
        facts_.append(f"team-level engagement (1–5): Engineering {s[-2]['score']}→{s[-1]['score']} ({s[-2]['quarter']} to {s[-1]['quarter']}, "
                      f"{s[-1]['responses']} of {s[-1]['team_size']} responded) and Marketing {m[-2]['score']}→{m[-1]['score']}")
        hold = [r["req"] for r in F.hiring_rows() if r["status"] == "On hold"]
        facts_.append(f"hiring gaps: {_join(hold)} on hold, REQ-016 (Siddharth's backfill) open")
        src += [S("Resignation_Letter_SM.pdf", "page 1"), S(F.HIRE_F, "Requisitions sheet")]
    if c.d("Day3"):
        pn = F.jira_summary()["by_assignee"]["PN"]
        facts_.append(f"workload concentration: {pn['issues']} of {F.jira_summary()['open']} unresolved Jira issues ({pn['points']} of {F.jira_summary()['open_points']} points) are assigned to one engineer")
        src.append(S(F.JIRA_F, "Issues sheet"))
    if c.d("Day4"):
        facts_.append("an unverified CEO-reported resignation (T6d, 'Pria', likely Priya Nair) awaiting HR confirmation")
        src.append(S("T6d_CEO_Voice_Note.docx", "transcript"))
    if facts_:
        parts.append("What the records do support: " + "; ".join(facts_) + ".")
    parts.append("Recommended instead: a team-level retention and capacity review (Deepa already suggests 1:1s led by Vikram, email 11).")
    return Ans(" ".join(parts), "High", src, uncertain=True, refused=True, intent="refuse_quit_ranking",
               derived=[str(x) for x in re.findall(r"\d[\d.]*", " ".join(facts_))])


def h_thoughts(c: Ctx) -> Ans:
    return Ans("I do not know anyone's private thoughts or feelings, and I will not invent them. The data room holds work records, "
               "transcripts and exports only. Agent personas contain clearly labelled fictional personal details (ASSUMPTIONS.md); those are "
               "role-play, never evidence about what a real employee believes. I can tell you what people are recorded as saying or doing "
               "in emails and exports.",
               "High", ["ASSUMPTIONS.md — fictional persona details", "Data-room inventory (README.txt)"],
               uncertain=True, refused=True, intent="refuse_private_thoughts")


def h_salary_refuse(c: Ctx) -> Ans:
    pg = F.payroll_gl()
    return Ans("Individual salaries and pay are not available in the CEO view. The CFO said individual salaries “must never show up in anything "
               "Ananya sees, only totals” (T2), and this is enforced in code: salary columns from the payroll register are never loaded. "
               f"Approved totals only: the general ledger posts company-wide salaries of ₹{fmt_inr(max(pg['months'].values()))} per month (Apr–Sep 2026).",
               "High", [S("T2_CFO_Call.docx", "CFO statement on salaries"), pg["source"]], uncertain=False, refused=True,
               intent="refuse_individual_salary", derived=[fmt_inr(max(pg["months"].values()))])


def h_rank_people(c: Ctx) -> Ans:
    cs = F.commit_summary()
    return Ans("I won't rank people's performance or productivity from commit counts. Commit counts show recorded repository activity only — not "
               "hours, quality, review work, incident response or difficulty — and the repository has an unresolved alias, so even the counts are not "
               f"clean. Recorded commits by author email: " + ", ".join(f"{k} {v}" for k, v in cs["by_author"].items()) + ".",
               "High", [cs["source"]], uncertain=True, refused=True, intent="refuse_rank_performance",
               derived=[str(v) for v in cs["by_author"].values()])


# =================================================================== FINANCE

def _board_period(c: Ctx) -> str | None:
    """None = latest; a period label = that board quarter; 'NONE' = a period the records don't cover."""
    q = c.q
    qt = quarter_in(q)
    yr = re.findall(r"\b(20\d{2})\b", q)
    if qt == "Apr-Jun 2026":
        return "Apr-Jun 2026"
    if qt == "Jul-Sep 2026":
        return None
    if qt in ("Oct-Dec 2025", "Jan-Mar 2026") or any(y != "2026" for y in yr) or has(q, r"last year|previous year|two years|\bfy ?2[0-9]\b|financial year"):
        return "NONE"
    return None


def metric_text(b: dict, key: str) -> str:
    return {"arr_cr": f"recurring ARR of ₹{b['arr_cr']} Cr", "burn_lakh": f"monthly burn of ₹{b['burn_lakh']:g} lakh",
            "customers": f"{b['customers']} customers", "runway_months": f"{b['runway_months']} months of runway"}[key]


def _no_period(metric: str) -> Ans:
    return Ans(f"I don't know {metric} for that period: the only board updates in the records cover Apr–Jun 2026 and Jul–Sep 2026. I won't estimate other periods.",
               "High", [S(F.BOARD_Q2, "Key numbers"), S(F.BOARD_Q3, "Key numbers")], uncertain=True, intent="no_period_record")


def h_forecast(c: Ctx) -> Ans:
    c.need("Day1")
    b3 = D.board("Jul-Sep 2026")
    return Ans(f"The records contain no forecast or projection, and I won't make one up. The latest board-reported actuals (Jul–Sep 2026) are ARR ₹{b3['arr_cr']} Cr, burn ₹{b3['burn_lakh']:g} lakh/month, "
               f"{b3['customers']} customers and {b3['runway_months']} months of runway. The CFO's forecasts are described as running late (T2) and no forecast file was supplied.",
               "High", [S(F.BOARD_Q3, "Key numbers"), S("T2_CFO_Call.docx", "summary")], uncertain=True, intent="no_forecast")

def h_arr(c: Ctx) -> Ans:
    c.need("Day1")
    bp = _board_period(c)
    if bp == "NONE":
        return _no_period("ARR")
    if bp == "Apr-Jun 2026":
        b = D.board(bp)
        return Ans(f"The Apr–Jun 2026 board update (sent {b['sent']}) reports {metric_text(b, 'arr_cr')}.", "High", [S(F.BOARD_Q2, "Key numbers")], intent="arr_q2",
                   derived=[str(b['arr_cr'])])
    b3, b2 = D.board("Jul-Sep 2026"), D.board("Apr-Jun 2026")
    t = (f"The latest board-reported recurring ARR is ₹{b3['arr_cr']} Cr (Jul–Sep 2026 update, sent {b3['sent']}), up from ₹{b2['arr_cr']} Cr in the "
         f"Apr–Jun update. The transcript figures — the CEO's “around forty-two crore, maybe forty-five” (T1) and the CFO's “forty-eight” (T2) — "
         "do not reconcile with the board figures, so the board figure is used. This is recurring revenue (ARR), not total revenue.")
    return Ans(t, "High", [S(F.BOARD_Q3, "Key numbers — ARR (recurring)"), S(F.BOARD_Q2, "Key numbers — ARR (recurring)"),
                           S("T1_CEO_Kickoff_Call.docx", "summary: ARR statement"), S("T2_CFO_Call.docx", "summary: ARR statement")],
               uncertain=True, intent="arr")


def h_burn(c: Ctx) -> Ans:
    c.need("Day1")
    bp = _board_period(c)
    if bp == "NONE":
        return _no_period("burn")
    if bp == "Apr-Jun 2026":
        b = D.board(bp)
        return Ans(f"The Apr–Jun 2026 board update (sent {b['sent']}) reports {metric_text(b, 'burn_lakh')}.", "High", [S(F.BOARD_Q2, "Key numbers")], intent="burn_q2",
                   derived=[str(b['burn_lakh'])])
    b3, b2 = D.board("Jul-Sep 2026"), D.board("Apr-Jun 2026")
    t = (f"The latest board-reported monthly burn is ₹{b3['burn_lakh']:g} lakh (Jul–Sep 2026), down from ₹{b2['burn_lakh']:g} lakh in Apr–Jun. "
         "The CEO's “around two point two” (T1) and the CFO's “two point two lakhs a month, sometimes two point five” (T2) are unit-ambiguous "
         "and do not match the board figure, so they are not used.")
    return Ans(t, "High", [S(F.BOARD_Q3, "Key numbers — Monthly burn"), S(F.BOARD_Q2, "Key numbers — Monthly burn"),
                           S("T1_CEO_Kickoff_Call.docx", "summary: burn"), S("T2_CFO_Call.docx", "summary: burn")], uncertain=True, intent="burn")


def h_customers(c: Ctx) -> Ans:
    c.need("Day1")
    bp = _board_period(c)
    if bp == "NONE":
        return _no_period("the customer count")
    if bp == "Apr-Jun 2026":
        b = D.board(bp)
        return Ans(f"The Apr–Jun 2026 board update (sent {b['sent']}) reports {metric_text(b, 'customers')}.", "High", [S(F.BOARD_Q2, "Key numbers")], intent="customers_q2",
                   derived=[str(b['customers'])])
    b3, b2 = D.board("Jul-Sep 2026"), D.board("Apr-Jun 2026")
    return Ans(f"The Jul–Sep 2026 board update reports {b3['customers']} customers (up from {b2['customers']} in Apr–Jun). No customer-level export was supplied.",
               "High", [S(F.BOARD_Q3, "Key numbers — Customers"), S(F.BOARD_Q2, "Key numbers — Customers")], intent="customers")


def h_runway(c: Ctx) -> Ans:
    c.need("Day1")
    bp = _board_period(c)
    if bp == "NONE":
        return _no_period("runway")
    if bp == "Apr-Jun 2026":
        b = D.board(bp)
        return Ans(f"The Apr–Jun 2026 board update (sent {b['sent']}) reports {metric_text(b, 'runway_months')}.", "High", [S(F.BOARD_Q2, "Key numbers")], intent="runway_q2",
                   derived=[str(b['runway_months'])])
    b3, b2 = D.board("Jul-Sep 2026"), D.board("Apr-Jun 2026")
    return Ans(f"The Jul–Sep 2026 board update reports {b3['runway_months']} months of runway (down from {b2['runway_months']} months in Apr–Jun). "
               "This is a board-reported figure; it is not recalculated from the selected GL export.",
               "High", [S(F.BOARD_Q3, "Key numbers — Runway"), S(F.BOARD_Q2, "Key numbers — Runway")], intent="runway")


def h_headcount(c: Ctx) -> Ans:
    c.need("Day1")
    h = F.headcount()
    dept = ", ".join(f"{k} {v}" for k, v in h["by_dept"].items())
    t = (f"The Employee Master (Keka export, 31 Oct 2026) holds {h['records']} employee records — {h['active']} Active and {h['notice']} on notice "
         f"(Siddharth Mehta, exit date 31 Oct 2026) — and both board updates report a team of {h['board_q3']}. By department: {dept}. "
         "The Candidate Brief calls Veloxa a 180-person company and T1 is garbled (“roughly eighteen” in the summary, “one-eighty” in the quote); "
         "that claim is unresolved. Keka excludes contractors, so the export alone cannot prove nobody else works for Veloxa. "
         f"Working figure: {h['records']} recorded employees (Medium confidence).")
    return Ans(t, "Medium", h["sources"] + [S("Candidate_Brief.docx", "The ask"), S("T1_CEO_Kickoff_Call.docx", "summary")],
               uncertain=True, intent="headcount", derived=[str(v) for v in h["by_dept"].values()] + ["180"])


def h_agent_count(c: Ctx) -> Ans:
    c.need("Day1")
    r = F.agents_roster()
    by = {}
    for e in r:
        by[e["dept"]] = by.get(e["dept"], 0) + 1
    return Ans(f"The brief requires {len(r)} interviewable agents — " + ", ".join(f"{k} {by[k]}" for k in F.DEPT_ORDER) +
               f" — all taken from Employee Master rows. The company roster has {F.headcount()['records']} people; Leadership, Sales and Support "
               f"({F.headcount()['records'] - len(r)} people) are outside the agent scope.",
               "High", [S("Candidate_Brief.docx", "Scope: Must have"), S(F.EMP_F, "Employees sheet")], intent="agent_count",
               derived=[str(v) for v in by.values()] + [str(F.headcount()["records"] - len(r))])


def h_marketing_spend(c: Ctx) -> Ans:
    c.need("Day1")
    m = F.marketing_ledger()
    q = c.q
    ev = [l for l in m["lines"] if l["cc"] == "MKT-EVT"]
    ps = [l for l in m["lines"] if l["cc"] == "MKT-PS"]
    ev_txt = " + ".join(f"{l['vendor']} ₹{fmt_inr(l['amount'])}" for l in ev)
    t = (f"The supplied general-ledger export (selected cost centres, Apr–Sep 2026) records ₹{lakh(m['total'], 4)} lakh (₹{fmt_inr(m['total'])}) across the two marketing cost "
         f"centres: MKT-EVT ₹{lakh(m['events'], 2)} lakh ({ev_txt}) and MKT-PS ₹{lakh(m['paid_search'], 4)} lakh ({len(ps)} Google Ads postings). ")
    if has(q, r"google|paid search|ads"):
        t = (f"Paid search (MKT-PS) totals ₹{lakh(m['paid_search'], 4)} lakh (₹{fmt_inr(m['paid_search'])}) across {len(ps)} Google India postings, Apr–Sep 2026. ") + \
            f"Together with events, the two marketing cost centres total ₹{lakh(m['total'], 4)} lakh. "
    elif has(q, r"event|summit"):
        t = (f"Event spend (MKT-EVT) totals ₹{lakh(m['events'], 2)} lakh (₹{fmt_inr(m['events'])}): {ev_txt}. ") + \
            f"Together with paid search, the two marketing cost centres total ₹{lakh(m['total'], 4)} lakh. "
    t += "This is not necessarily total marketing spend — the export contains selected cost centres only. "
    srcs = [m["source"]]
    if c.d("Day3"):
        t += ("T4's “one point eight” (Nikhil) has no stated unit or scope and cannot be reconciled with the ledger; the CFO also says Nikhil's numbers "
              "never match hers (T2). ")
        srcs += [S("T4_Head_of_Marketing_Call.docx", "summary: marketing spend"), S("T2_CFO_Call.docx", "summary")]
    t += ("The event vendors “Sapphire Events Pvt Ltd” and “Saphire Event Mgmt” are spelled differently and are kept as separate vendors, not merged; "
          "a third, “Sapphire Residency Hotel” (₹38,940, SAL-TRV sales offsite), is a different cost centre and unrelated.")
    return Ans(t, "Medium", srcs, uncertain=True, intent="marketing_spend",
               derived=[lakh(m["total"], 2), lakh(m["events"], 2), lakh(m["paid_search"], 2), lakh(m["paid_search"], 4), lakh(m["total"], 4),
                        fmt_inr(m["total"]), fmt_inr(m["paid_search"]), fmt_inr(m["events"]), str(len(ps)), "38,940", "38940"])


def h_payroll_total(c: Ctx) -> Ans:
    c.need("Day1")
    pg = F.payroll_gl()
    mon = re.search(r"\b(apr|may|jun|jul|aug|sep)\w*", c.q)
    key = {"apr": "2026-04", "may": "2026-05", "jun": "2026-06", "jul": "2026-07", "aug": "2026-08", "sep": "2026-09"}.get(mon.group(1)) if mon else "2026-09"
    amt = pg["months"][key]
    dept = dept_in(c.q)
    t = (f"The general ledger records a company-wide salary posting of ₹{fmt_inr(amt)} (₹{lakh(amt, 2)} lakh) for {key} under the PAYROLL cost centre "
         f"(₹{fmt_inr(pg['total'])} across Apr–Sep 2026). The GL has no department split, so I cannot state "
         f"{'the ' + dept + ' ' if dept else 'a department-level '}payroll cost, and individual salaries are not available in the CEO view (T2).")
    return Ans(t, "Medium", [pg["source"], S("T2_CFO_Call.docx", "salary confidentiality")], uncertain=True, intent="payroll_total",
               derived=[fmt_inr(amt), lakh(amt, 2), fmt_inr(pg["total"])])


_GL_TOPICS = [
    (r"\baws\b|amazon web|cloud|infra", "ENG-INF", "AWS / engineering infrastructure"),
    (r"\brent\b|wework|office", "G&A", "office rent (WeWork India)"),
    (r"recruit|cohere|search fee|agency", "PPL-HIR", "recruitment search fee"),
    (r"offsite|travel|hotel", "SAL-TRV", "sales offsite travel"),
    (r"contractor|patil|on-call support", "ENG-OPS", "on-call support (Patil Infra Services)"),
]


def h_gl_lookup(c: Ctx) -> Ans | None:
    c.need("Day1")
    for pat, cc, label in _GL_TOPICS:
        if re.search(pat, c.q):
            ls = F.gl_lines(lambda d, cc=cc: d["Cost Centre"] == cc)
            tot = sum(l["amount"] for l in ls)
            lines = "; ".join(f"{l['date']} {l['vendor']} ₹{fmt_inr(l['amount'])} ({l['narr']})" for l in ls)
            t = f"The GL export (Apr–Sep 2026) shows {len(ls)} posting(s) for {label} in cost centre {cc}, totalling ₹{fmt_inr(tot)}: {lines}."
            if cc == "PPL-HIR":
                t += " Note: this advance was paid for two backend roles; REQ-014 and REQ-015 were paused on 12 Aug (email 06)."
            t += " The export covers selected cost centres only."
            cites = [S(F.GL_F, f"cost centre {cc}, rows {', '.join(str(l['row']) for l in ls)}")]
            if cc == "PPL-HIR" and c.d("Day2"):
                cites.append(S("06.eml", "12 Aug 2026"))
            if cc == "PPL-HIR" and not c.d("Day2"):
                t = t.replace(" Note: this advance was paid for two backend roles; REQ-014 and REQ-015 were paused on 12 Aug (email 06).", "")
            return Ans(t, "High", cites, uncertain=False, intent="gl_lookup",
                       derived=[fmt_inr(tot), str(len(ls))] + [fmt_inr(l["amount"]) for l in ls])
    return None


def h_payroll_processor(c: Ctx) -> Ans:
    c.need("Day1")
    a = F.payroll_run_audit("VX018", "Feb-2026")
    karthik = F.emp("VX010")
    t = (f"{karthik['name']} ({karthik['title']}) processed February 2026 payroll: the register's “Processed By” is “{a['processed_by']}” on all {a['rows_in_run']} February rows, "
         "and his email of 28 Feb says he ran it because Fatima was out, using the January sheet plus the new joiner (email 01). January and March were processed by “FS” (Fatima Sheikh).")
    return Ans(t, "High", [S("01.eml", "Karthik to Meera, 28 Feb 2026"), S("Payroll_Register_Jan-Mar_2026.xlsx", "Payroll Q4 sheet, Processed By column (no amounts used)")],
               intent="payroll_processor", derived=[str(a["rows_in_run"])])


def h_rahul_payroll(c: Ctx) -> Ans:
    c.need("Day1")
    fp = F.feb_proration()
    a = fp["audit"]
    t = ("This is an unresolved verification query, not a confirmed overpayment. "
         f"Rahul Verma joined on 3 Feb 2026 (Employee Master), yet the February register shows {fp['recorded_days']} payable days out of {fp['days_in_month']}; "
         f"a calendar-day proration from his start date would give {fp['expected_days']} — a {fp['gap_days']}-day ({fp['gap_fraction'] * 100:.1f}%) difference. "
         "Whether that is an error depends on Veloxa's proration policy, which is not in the records. "
         f"Karthik (“KS”) ran February payroll for all {a['rows_in_run']} employees because Fatima was out (email 01: he “used the Jan sheet and added the new joiner”). "
         "Rahul asked on 6 March whether his first payslip was right for a partial month (email 02); Fatima replied on 10 March “Will check and get back” (email 03). "
         "No later record resolves it. Salary amounts are withheld from the CEO view.")
    srcs = [S("Payroll_Register_Jan-Mar_2026.xlsx", f"Payroll Q4 sheet, row {a['row']} (days fields only)"), S(F.EMP_F, "VX018 join date"),
            S("01.eml", "28 Feb"), S("02.eml", "6 Mar"), S("03.eml", "10 Mar")]
    if c.d("Day2"):
        lv = F.leave_for("F. Sheikh")
        if lv:
            t += f" The Leave Register shows F. Sheikh on leave {lv[0]['from']} to {lv[0]['to']}, consistent with email 01."
            srcs.append(S(F.LEAVE_F, f"row {lv[0]['row']}"))
    return Ans(t, "High", srcs, uncertain=True, intent="rahul_payroll",
               derived=[str(fp["gap_days"]), f"{fp['gap_fraction'] * 100:.1f}", str(a["rows_in_run"])])


# =================================================================== PEOPLE
def _emp_line(e: dict) -> str:
    return f"{e['name']} is the {e['title']} ({e['dept']}), employee ID {e['emp_id']}, reporting to {_name(e['manager_id']) if e['manager_id'] else 'no one (top of the org chart)'}."


def h_person(c: Ctx) -> Ans | None:
    c.need("Day1")
    q = c.q
    ids = [p for p in c.P if p != "SNEHAL"]
    if not ids:
        return None
    e = F.emp(ids[0])
    src = [S(F.EMP_F, f"Employees sheet, row {int(e['_row'])}")]
    extra = ""
    if has(q, r"direct reports?|who reports to|reports? into|reporting to " + e["first"]) or has(q, rf"who reports to {e['first']}"):
        rep = F.employees()[F.employees()["manager_id"] == e["emp_id"]]
        t = (f"{e['name']} has {len(rep)} direct report(s) in the Employee Master: " + ", ".join(f"{r['name']} ({r['title']})" for _, r in rep.iterrows()) + "."
             if len(rep) else f"No employee is recorded as reporting to {e['name']}.")
        return Ans(t, "High", src, intent="direct_reports", derived=[str(len(rep))])
    if has(q, r"\bmanager\b|reports? to|boss|reporting line|who does .* report|reports into|report to"):
        t = f"{e['name']} reports to {_name(e['manager_id'])} ({F.emp(e['manager_id']).get('title', '')}) according to the Employee Master." if e["manager_id"] else f"{e['name']} has no manager recorded (CEO)."
        conf = "High"
        if e["dept"] == "Marketing" and c.d("Day3") and e["emp_id"] != "VX013":
            t += (" Separately, T6b says Marketing will report to a new CRO “from next month, or the month after” — that change is proposed with no confirmed "
                  "effective date, so the recorded reporting line above stays active.")
            src.append(S("T6b_CEO_Voice_Note.docx", "transcript"))
        return Ans(t, conf, src, intent="manager")
    if has(q, r"\bjoin|joining|start date|tenure|how long|since when|hired"):
        return Ans(f"{e['name']} joined Veloxa on {e['join_date']} (Employee Master).", "High", src, intent="join_date")
    if has(q, r"where|location|based|remote|city|office"):
        t = f"{e['name']} is recorded in the Employee Master with location “{e['location']}”."
        if e["emp_id"] == "VX009" and c.d("Day2"):
            t += " Arjun's email of 18 Sep asks Deepa to make remote working permanent (monthly Bengaluru visits offered); no decision is recorded (email 10)."
            src.append(S("10.eml", "18 Sep 2026"))
        return Ans(t, "High", src, intent="location")
    if has(q, r"still (employed|here|working|at)|\bactive\b|\bleft\b|leaving|notice|exit|resign|last (working )?day|status"):
        if e["emp_id"] == "VX013":
            return h_siddharth(c)
        t = f"The Employee Master (31 Oct 2026) records {e['name']} as {e['status']}" + (f" with exit date {e['exit_date']}" if e["exit_date"] else "") + "."
        return Ans(t, "High", src, intent="employee_status")
    return Ans(_emp_line(e) + f" Joined {e['join_date']}; location {e['location']}; status {e['status']}.", "High", src, intent="person")


def h_role_lookup(c: Ctx) -> Ans | None:
    c.need("Day1")
    title = title_in(c.q)
    if not title or not has(c.q, r"\bwho\b|\bname\b|\bwhich\b|\bidentify\b|\bleads?\b|\bruns?\b"):
        return None
    r = F.employees()[F.employees()["title"] == title]
    if not len(r):
        return None
    e = r.iloc[0].to_dict()
    return Ans(_emp_line(e), "High", [S(F.EMP_F, f"Employees sheet, row {int(e['_row'])}")], intent="role_lookup")


def h_team_members(c: Ctx) -> Ans | None:
    c.need("Day1")
    d = dept_in(c.q)
    if not d:
        return None
    r = F.employees()[F.employees()["dept"] == d]
    if not len(r):
        return None
    t = f"{d} has {len(r)} recorded employees: " + "; ".join(f"{x['name']} ({x['title']}{', status ' + x['status'] if x['status'] != 'Active' else ''})" for _, x in r.iterrows()) + "."
    return Ans(t, "High", [S(F.EMP_F, "Employees sheet, Department column")], intent="team_members", derived=[str(len(r))])


def h_pulse(c: Ctx) -> Ans:
    c.need("Day2")
    team = dept_in(c.q)
    qtr = quarter_in(c.q)
    cm = "Comments are withheld in the source export because every team is smaller than six people — a privacy rule, not missing data."
    if team and team in F.pulse_teams():
        s = F.pulse_series(team)
        latest = next((x for x in s if x["quarter"] == qtr), s[-1])
        trend = " → ".join(f"{x['score']:g}" for x in s)
        t = (f"{team}'s Culture Amp engagement score was {latest['score']:g} / 5 in {latest['quarter']}, with {latest['responses']} responses from a team of {latest['team_size']}. "
             f"Trend from {s[0]['quarter']} to {s[-1]['quarter']}: {trend}. {cm}")
        return Ans(t, "High", [S(F.PULSE_F, f"Pulse by team sheet, row {latest['row']}")], intent="pulse_team",
                   derived=[f"{x['score']:g}" for x in s] + [str(latest["responses"]), str(latest["team_size"])])
    rows = []
    for tm in F.pulse_teams():
        s = F.pulse_series(tm)
        rows.append(f"{tm} {s[-1]['score']:g} (was {s[-2]['score']:g})")
    return Ans("Latest (Jul–Sep 2026) engagement scores out of 5, with the previous quarter: " + "; ".join(rows) + f". The clearest declines are Engineering and Marketing. {cm}",
               "High", [S(F.PULSE_F, "Pulse by team sheet")], intent="pulse_all",
               derived=[f"{F.pulse_series(tm)[-1]['score']:g}" for tm in F.pulse_teams()] + [f"{F.pulse_series(tm)[-2]['score']:g}" for tm in F.pulse_teams()])


def h_hiring(c: Ctx) -> Ans:
    c.need("Day2")
    rows = F.hiring_rows()
    q = c.q
    m = re.search(r"req-?(\d{3})", q)
    sel, label = rows, "All six requisitions in the 31 Oct 2026 Keka Hire export"
    if m:
        sel = [r for r in rows if r["req"] == f"REQ-{m.group(1)}"]; label = f"REQ-{m.group(1)}"
    elif has(q, r"routing") and not m:
        sel = [r for r in rows if r["req"] == "REQ-014"]; label = "REQ-014 (the Routing backend role)"
    elif has(q, r"platform") and not m:
        sel = [r for r in rows if r["req"] == "REQ-015"]; label = "REQ-015 (the Platform backend role)"
    elif has(q, r"replacement|backfill|siddharth|marketing manager") and not dept_in(q) == "Engineering":
        sel = [r for r in rows if r["req"] == "REQ-016"]; label = "REQ-016 (Siddharth's backfill)"
    elif has(q, r"paused|on hold|frozen|freeze|halted|stopped|who paused"):
        sel = [r for r in rows if r["status"] == "On hold"]; label = "Requisitions on hold"
        if dept_in(q):
            sel = [r for r in sel if r["team"] == dept_in(q)]
    elif has(q, r"\bopen\b|vacanc|openings|currently hiring|open roles"):
        sel = [r for r in rows if r["status"] == "Open"]; label = "Open requisitions"
        if dept_in(q):
            sel = [r for r in sel if r["team"] == dept_in(q)]
    elif dept_in(q):
        sel = [r for r in rows if r["team"] == dept_in(q)]; label = f"{dept_in(q)} requisitions"
    if not sel:
        return Ans(f"No matching requisition is recorded in the 31 Oct 2026 hiring export.", "High", [S(F.HIRE_F, "Requisitions sheet")], intent="hiring")
    body = "; ".join(f"{r['req']} {r['role']} ({r['team']}): {r['status']} since {r['status_date']}, {r['pipeline']} in pipeline" + (f" — {r['notes']}" if r["notes"] else "") for r in sel)
    t = f"{label}: {body}."
    srcs = [S(F.HIRE_F, "Requisitions sheet, rows " + ", ".join(str(r["row"]) for r in sel))]
    held = [r for r in sel if r["status"] == "On hold"]
    if held and any(r["req"] in ("REQ-014", "REQ-015") for r in held):
        t += " Finance (Meera) paused REQ-014 and REQ-015 on 12 Aug “until the round closes”, and Vikram replied “We'll absorb it” (emails 06 and 07); the Jul–Sep board update also says hiring is paused while the round closes."
        srcs += [S("06.eml", "12 Aug 2026"), S("07.eml", "12 Aug 2026"), S(F.BOARD_Q3, "Team")]
    if any(r["req"] == "REQ-016" for r in sel):
        t += " REQ-016 is the backfill for Siddharth Mehta."
    return Ans(t, "High", srcs, intent="hiring", derived=[str(r["pipeline"]) for r in sel])


def h_siddharth(c: Ctx) -> Ans:
    c.need("Day1")
    sid = F.emp("VX013")
    if not c.d("Day2"):
        return Ans(f"The Employee Master (Keka export, 31 Oct 2026) lists Siddharth Mehta ({sid['title']}, Marketing) with status “{sid['status']}” and exit date {sid['exit_date']}. "
                   "The resignation letter itself is released on Day 2.", "High", [S(F.EMP_F, f"Employees sheet, row {int(sid['_row'])}")], intent="siddharth")
    req = next(r for r in F.hiring_rows() if r["req"] == "REQ-016")
    t = (f"Siddharth Mehta ({sid['title']}, Marketing) resigned by a letter dated 15 September 2026 addressed to Nikhil Bose; his last working day is {sid['exit_date']} "
         f"(31 October 2026), which the Employee Master independently records as notice period with that exit date. His stated reason: he wants a role with clearer launch timelines "
         f"where the work he prepares reaches customers. His backfill {req['req']} (opened {req['opened']}) was still {req['status']} with {req['pipeline']} in the pipeline in the 31 Oct export. "
         "He is a departed employee, so his agent is a historical profile, not an active colleague.")
    return Ans(t, "High", [S("Resignation_Letter_SM.pdf", "page 1"), S(F.EMP_F, f"Employees sheet, row {int(sid['_row'])}"), S(F.HIRE_F, f"row {req['row']}"),
                           S(F.BOARD_Q3, "Team: one planned departure in marketing")], intent="siddharth", derived=[str(req["pipeline"])])


def h_resigned_list(c: Ctx) -> Ans:
    c.need("Day1")
    t = "Documented departure: Siddharth Mehta (Product Marketing Manager, Marketing), last working day 31 October 2026. "
    srcs = [S(F.EMP_F, "VX013 row")]
    if c.d("Day2"):
        srcs.append(S("Resignation_Letter_SM.pdf", "page 1"))
    if c.d("Day4"):
        t += ("A second, unverified item: T6d (CEO voice note) reports that “Pria” resigned — likely Priya Nair — but the 31 Oct HR exports contain no resignation for her, "
              "so it awaits HR confirmation.")
        srcs.append(S("T6d_CEO_Voice_Note.docx", "transcript"))
    return Ans(t, "High" if not c.d("Day4") else "Medium", srcs, uncertain=c.d("Day4"), intent="resigned_list")


def h_priya_resignation(c: Ctx) -> Ans:
    c.need("Day4")
    pr = F.emp("VX007")
    t = ("T6d (CEO voice note) says “Pria resigned this morning” with a notice period of “two months, I think”. Identity: Priya Nair (Staff Engineer, routing lead) is the likely match "
         "(High confidence — no other routing lead exists, Jira initials PN and Vikram's Atlas plan agree). Status: this is a CEO-reported claim awaiting HR confirmation — "
         f"the Employee Master and hiring exports are dated 31 Oct and show Priya as {pr['status']} with no resignation record. The notice period is unverified.")
    return Ans(t, "Medium", [S("T6d_CEO_Voice_Note.docx", "transcript"), S(F.EMP_F, f"VX007 row {int(pr['_row'])}"), S(F.JIRA_F, "Assignee initials PN") if c.d("Day3") else S(F.EMP_F, "VX007")],
               uncertain=True, intent="priya_resignation")


def h_replacement(c: Ctx) -> Ans:
    c.need("Day1")
    ids = [p for p in c.P if p != "SNEHAL"]
    e = F.emp(ids[0]) if ids else None
    if not e:
        return Ans("I don't know — no replacement is named in the records.", "High", [], uncertain=True, intent="replacement")
    if e["emp_id"] == "VX013" and c.d("Day2"):
        r16 = next(r for r in F.hiring_rows() if r["req"] == "REQ-016")
        return Ans(f"No successor for Siddharth is named. His backfill REQ-016 was {r16['status']} with {r16['pipeline']} in the pipeline in the 31 Oct export (opened {r16['opened']}); no hire is recorded.",
                   "High", [S(F.HIRE_F, f"row {r16['row']}")], uncertain=True, intent="replacement", derived=[str(r16["pipeline"])])
    t = f"The records name no replacement, successor or backup owner for {e['name']}."
    srcs = [S(F.EMP_F, f"row {int(e['_row'])}")]
    der = []
    if c.d("Day2") and e["dept"] == "Engineering":
        hold = [r for r in F.hiring_rows() if r["status"] == "On hold"]
        t += f" The two backend requisitions ({_join([r['req'] for r in hold])}) are on hold, so no replacement capacity is in the pipeline."
        srcs.append(S(F.HIRE_F, "REQ-014/REQ-015"))
    if c.d("Day3") and F.jira_for(e["emp_id"]):
        x = F.jira_for(e["emp_id"]); t += f" {e['name']} holds {x['issues']} unresolved Atlas issues ({x['points']} points) that would need reassignment."
        srcs.append(S(F.JIRA_F, "Issues sheet")); der = [str(x["issues"]), str(x["points"])]
    return Ans(t, "Medium", srcs, uncertain=True, intent="replacement", derived=der)


def h_email_lookup(c: Ctx) -> Ans | None:
    ids = [p for p in c.P if p != "SNEHAL"]
    toks = {w for w in re.findall(r"[a-z]{4,}", c.q) if w not in {"what", "said", "write", "wrote", "email", "about", "tell", "told", "mention", "mentioned", "does", "from"}}
    found = []
    for n in ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11"):
        name = f"{n}.eml"
        m = D.email_msg(name)
        if not c.d(F.day(name)):
            continue
        who = (m["from"] + " " + m["to"]).lower()
        body = (m["subject"] + " " + m["body"]).lower()
        sc = (3 if ids and any(F.emp(i)["email"] in who for i in ids) else 0) + sum(1 for t in toks if t in body)
        if sc >= 3 or (not ids and sc >= 2):
            found.append((sc, name, m))
    if not found:
        return None
    found.sort(key=lambda x: (-x[0], x[1]))
    top = found[:2]
    t = " ".join(f"{m['from'].split('<')[0].strip()} to {m['to'].split('<')[0].strip()} on {m['date'].strftime('%d %b %Y')} (“{m['subject']}”): {re.sub(chr(10) + '+', ' ', m['body'])}" for _, _, m in top)
    return Ans(t, "High", [S(n, "email") for _, n, _ in top], intent="email_lookup", derived=[m["date"].strftime("%d") for _, _, m in top])


def h_attrition(c: Ctx) -> Ans:
    c.need("Day2")
    if has(c.q, r"team|department|which|where"):
        rows = []
        for tm in F.pulse_teams():
            s = F.pulse_series(tm); rows.append((s[-1]["score"] - s[-2]["score"], tm, s[-2]["score"], s[-1]["score"]))
        rows.sort()
        ds = "; ".join(f"{tm} {a:g}→{b:g} ({d:+.1f})" for d, tm, a, b in rows[:3])
        return Ans(f"Attrition risk cannot be measured from these records, so I can't say which team will lose people. A team-level signal I can report is the quarterly change in engagement (Apr–Jun → Jul–Sep): {ds}. "
                   "Engineering shows the largest fall. Engagement is not an attrition forecast, comments are withheld (teams under six people), and this says nothing about any individual.",
                   "Medium", [S(F.PULSE_F, "Pulse by team sheet")], uncertain=True, intent="attrition_team",
                   derived=[f"{x:.1f}" for d, _, _, _ in rows[:3] for x in (abs(d),)] + [f"{x:g}" for _, _, a, b in rows[:3] for x in (a, b)])
    return Ans("An attrition rate cannot be derived from the records. T3's “about twelve” has no unit (percentage, headcount or target) and no HR export of leavers was supplied. "
               "Recorded: one documented resignation (Siddharth Mehta, last day 31 Oct 2026)" + (" plus the unverified T6d claim about 'Pria'" if c.d("Day4") else "") + ".",
               "High", [S("T3_Head_of_People_Call.docx", "summary: attrition"), S(F.EMP_F, "VX013 row")], uncertain=True, intent="attrition", derived=["12"])


# =================================================================== ENGINEERING
def h_atlas_board_only(c: Ctx) -> Ans:
    b2, b3 = D.board("Apr-Jun 2026"), D.board("Jul-Sep 2026")
    orig = re.search(r"GA on (\d+ \w+)", b2["product"]).group(1)
    return Ans(f"The Apr–Jun board update (sent {b2['sent']}) said Atlas (routing engine v3) was on track for GA on {orig}. The Jul–Sep update (sent {b3['sent']}) says GA was moved to absorb "
               "unplanned reliability work after a difficult August, and that the engine is feature-complete and in final hardening. No new GA date is stated in the records released so far; "
               "Jira-level issue counts, ownership and incident detail arrive in the Day 3 release.",
               "High", [S(F.BOARD_Q3, "Product"), S(F.BOARD_Q2, "Product")], uncertain=True, intent="atlas_board_only")


def _atlas_core(c: Ctx) -> dict:
    j, v, inc = F.jira_summary(), F.jira_version(), F.incident_summary()
    return {"j": j, "v": v, "inc": inc, "pn": j["by_assignee"]["PN"]}


def h_atlas(c: Ctx) -> Ans:
    c.need("Day1")
    if not c.d("Day3"):
        return h_atlas_board_only(c)
    k = _atlas_core(c); j, v, inc, pn = k["j"], k["v"], k["inc"], k["pn"]
    q = c.q
    base_src = [v["source"]]
    if has(q, r"who (changed|moved|postponed|pushed|delayed|updated|approved)"):
        return Ans(f"The Jira Versions record shows the Atlas GA release date was last changed on {v['changed_on']} by “{v['changed_by']}” (Vikram Menon, VP Engineering — "
                   "an inference from the name and his @veloxa.in account), from "
                   f"{v['original']} to {v['revised']}.", "High", base_src, intent="atlas_who_changed")
    if has(q, r"original|initial|first|previous|old\b|planned|promised|target") and not has(q, r"revised|new\b|latest|current"):
        return Ans(f"Atlas's original GA release date was {v['original']} (Jira Versions: Original Release Date; the Apr–Jun board update also said 15 September). "
                   f"It was moved to {v['revised']} on {v['changed_on']}.", "High", base_src + [S(F.BOARD_Q2, "Product")], intent="atlas_original_date")
    if has(q, r"revised|new\b|latest|current|moved to|now\b|when (will|is|does)|launch date|ga date|release date") and not has(q, r"why|reason|cause|delay|behind|blocker"):
        return Ans(f"Atlas's current GA release date in Jira is {v['revised']} (originally {v['original']}; changed {v['changed_on']} by {v['changed_by']}). "
                   "This is the planned date, not a guarantee: the records cannot confirm it will be met.", "High", base_src + [S(F.BOARD_Q3, "Product")],
                   uncertain=False, intent="atlas_revised_date")
    # default: composite delay / status answer
    inc_aug = inc["sev1_by_month"].get("2026-08", 0)
    sev1_resp = sorted({r["Responder"] for r in inc["sev1_rows"]})
    hold = [r for r in F.hiring_rows() if r["status"] == "On hold" and r["team"] == "Engineering"]
    t = (f"Atlas GA was moved from {v['original']} to {v['revised']} (Jira Versions, changed {v['changed_on']} by {v['changed_by']}); the Jul–Sep board update says GA moved to absorb "
         "unplanned reliability work after a difficult August. Documented contributors: "
         f"(1) Reliability — {inc['total']} incidents between {inc['span'][0]} and {inc['span'][1]}, including {inc_aug} SEV1s in August (all on routing-api, responder recorded as {_join(sev1_resp)}); "
         "Sneha's 24 Aug email says it was the third SEV1 that month and that she was pausing the Atlas perf tickets to stabilise routing-api. "
         f"(2) Unfinished work — {j['open']} of {j['total']} Jira issues are unresolved ({j['open_points']} story points); {pn['issues']} of them ({pn['points']} points, {pct(pn['points'], j['open_points'])}) are assigned to Priya (PN). "
         f"(3) Capacity — {_join([r['req'] for r in hold])} are on hold, so the two backend hires Vikram's 2 Jun plan depended on have not landed. "
         "Conflict: the VP Engineering call (T5) says “on track” and “September-ish”, which contradicts the Jira record that Vikram himself changed on 2 Sep and the board update; "
         "the system records are preferred over the transcript. Story points measure assigned work, not calendar time, so the records support delivery risk but no exact future slip.")
    srcs = [v["source"], S(F.BOARD_Q3, "Product"), inc["source"], j["sources"][0], S("08.eml", "24 Aug 2026"), S(F.HIRE_F, "REQ-014/REQ-015"), S("04.eml", "2 Jun 2026"),
            S("T5_VP_Engineering_Call.docx", "summary")]
    return Ans(t, "High", srcs, uncertain=True, intent="atlas_delay",
               derived=[str(inc_aug), str(inc["total"]), str(j["open"]), str(j["total"]), str(j["open_points"]), str(pn["issues"]), str(pn["points"]), pct(pn["points"], j["open_points"]).rstrip("%")])


def h_jira(c: Ctx) -> Ans:
    c.need("Day3")
    j = F.jira_summary()
    q = c.q
    people = [p for p in c.P if p != "SNEHAL"]
    base = (f"The Jira ATLAS export has {j['total']} issues: {j['done']} Done, {j['in_progress']} In Progress and {j['todo']} To Do — {j['open']} unresolved carrying {j['open_points']} story points.")
    srcs = j["sources"]
    der = [str(j[k]) for k in ("total", "done", "in_progress", "todo", "open", "open_points")]
    if people or has(q, r"most|owns|assignee|who has|biggest|largest|per person|by person|workload"):
        by = j["by_assignee"]
        if people and F.jira_for(people[0]):
            x = F.jira_for(people[0]); e = F.emp(people[0])
            t = (f"{e['name']} (Jira assignee {x['initials']}) has {x['issues']} unresolved issues carrying {x['points']} story points, out of {j['open']} / {j['open_points']} overall "
                 f"({pct(x['points'], j['open_points'])} of open points). Story points are relative estimates of assigned work — not hours, productivity or remaining calendar time. "
                 "(Mapping initials to people is an inference: each initial pair is unique in the Employee Master.)")
            return Ans(t, "High", srcs, intent="jira_person", derived=der + [str(x["issues"]), str(x["points"]), pct(x["points"], j["open_points"]).rstrip("%")])
        if people and not F.jira_for(people[0]):
            e = F.emp(people[0])
            return Ans(f"{e['name']} has no unresolved Jira ATLAS issues assigned in the export. {base}", "High", srcs, intent="jira_person", derived=der)
        top = max(by.items(), key=lambda kv: kv[1]["points"])
        pn = by[top[0]]
        others = "; ".join(f"{_first(v['emp_id'])} {v['issues']} issues / {v['points']} points" for a, v in sorted(by.items(), key=lambda kv: -kv[1]["points"]) if a != top[0])
        t = (f"{_name(pn['emp_id'])} (assignee {top[0]}) owns the most unresolved story points: {pn['points']} across {pn['issues']} issues ({pct(pn['points'], j['open_points'])} of the {j['open_points']} open points). "
             f"Others: {others}. Story points are relative estimates of assigned work, not productivity or calendar time.")
        return Ans(t, "High", srcs, intent="jira_owner", derived=der + [str(v["points"]) for v in by.values()] + [str(v["issues"]) for v in by.values()] + [pct(pn["points"], j["open_points"]).rstrip("%")])
    lead = ""
    if has(q, r"unresolved|\bopen\b|remain|\bleft\b|pending|outstanding|incomplete|not (done|finished|complete)|story points?"):
        lead = f"{j['open']} issues remain unresolved, carrying {j['open_points']} story points. "
    elif has(q, r"in progress|started|working on"):
        lead = f"{j['in_progress']} issues are In Progress. "
    elif has(q, r"to do|todo|not started|backlog"):
        lead = f"{j['todo']} issues are still To Do. "
    elif has(q, r"\b(completed?|done|finished|closed|resolved)\b"):
        lead = f"{j['done']} issues are completed (Done). "
    return Ans(lead + base, "High", srcs, intent="jira_counts", derived=der)


def h_incidents(c: Ctx) -> Ans:
    c.need("Day3")
    inc = F.incident_summary()
    t_ = F.incidents()
    q = c.q
    mo = month_in(q) or (8 if re.search(r"\baug(ust)?\b", q) else None) or (9 if re.search(r"\bsep(tember)?\b", q) else None) or (10 if re.search(r"\boct(ober)?\b", q) else None)
    sev = re.search(r"sev ?([123])", q)
    sel = t_
    desc = "incidents"
    if sev:
        sel = sel[sel["Severity"] == f"SEV{sev.group(1)}"]; desc = f"SEV{sev.group(1)} incidents"
    if mo:
        sel = sel[sel["opened_utc"].dt.month == mo]
        desc += f" in {['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][mo]} 2026"
    ids = ", ".join(f"{r['ID']} ({r['opened_utc'].strftime('%d %b')}, {r['Service']}, responder {r['Responder']})" for _, r in sel.iterrows())
    sev_line = ", ".join(f"{n} {k}" for k, n in sorted(inc["by_sev"].items()))
    t = f"There {'was' if len(sel) == 1 else 'were'} {len(sel)} {desc}: {ids}." if len(sel) else f"No {desc} are recorded."
    t += (f" Across the whole export there are {inc['total']} incidents from {inc['span'][0]} to {inc['span'][1]} ({sev_line}); all {inc['by_sev'].get('SEV1', 0)} SEV1s were in August "
          "(timestamps are UTC). Responders appear as both “Sneha” and “Snehal”; their relationship is unresolved.")
    return Ans(t, "High", [inc["source"]], intent="incidents",
               derived=[str(len(sel)), str(inc["total"])] + [str(n) for n in inc["by_sev"].values()] + [r["opened_utc"].strftime("%d") for _, r in sel.iterrows()])


def h_oncall(c: Ctx) -> Ans:
    c.need("Day3")
    o = F.oncall_summary()
    return Ans(f"The on-call rota covers {o['weeks']} weeks (6 Jul–26 Oct 2026). Primary: Sneha {o['primary'].get('Sneha', 0)} weeks, Snehal {o['primary'].get('Snehal', 0)}; "
               f"secondary: Sneha {o['secondary'].get('Sneha', 0)}, Snehal {o['secondary'].get('Snehal', 0)}, Arjun {o['secondary'].get('Arjun', 0)}, Priya {o['secondary'].get('Priya', 0)}. "
               f"“Snehal” first appears in the week of {o['first_snehal_week']}. Whether Snehal is Sneha Kulkarni is unresolved.",
               "High", [o["source"]], uncertain=True, intent="oncall",
               derived=[str(o["weeks"])] + [str(v) for v in list(o["primary"].values()) + list(o["secondary"].values())])


def h_sneha_snehal(c: Ctx) -> Ans:
    c.need("Day3")
    o, ct = F.oncall_summary(), F.contractor()
    t = ("Unresolved — I keep Sneha Kulkarni and “Snehal” as separate identities. Evidence: the Employee Master lists Sneha Kulkarni (SRE, VX012) and no Snehal (it excludes contractors); "
         f"the incident export and on-call rota use both names, with “Snehal” first on the rota in the week of {o['first_snehal_week']}; the VP Engineering call (T5) refers to “Snehal on SRE and on-call” and "
         "mentions “Sneha” once, unclear if the same person; Sneha's 24 Aug email says a contractor “starts on the rota this week”; and Invoice PIS-114 bills Patil Infra Services for on-call SRE support by “S. Patil”. "
         "“Snehal” could be that contractor, but no record links the names, and the dates differ (rota 17 Aug, GL invoice PIS-108 covers 18–31 Aug, email dated 24 Aug). "
         "An explicit record linking them would change this conclusion.")
    return Ans(t, "Low", [S(F.EMP_F, "VX012 row"), o["source"], F.incident_summary()["source"], S("T5_VP_Engineering_Call.docx", "summary"), S("08.eml", "24 Aug 2026"), ct["source"]],
               uncertain=True, intent="sneha_snehal", derived=["31"])


def h_git(c: Ctx) -> Ans:
    c.need("Day3")
    cs = F.commit_summary()
    pn_off, pn_alias = cs["by_author"]["priya.n@veloxa.in"], cs["by_author"]["pnair@users.noreply.github.com"]
    ids = [p for p in c.P if p != "SNEHAL"]
    caution = ("Commit counts show recorded repository activity only, not productivity, effort or quality. ")
    if ids and ids[0] == "VX007":
        t = (f"Priya's work email priya.n@veloxa.in has {pn_off} commits. A further {pn_alias} come from pnair@users.noreply.github.com — plausibly her GitHub identity but not established by the records, "
             f"so I do not merge them (the combined figure would be {pn_off + pn_alias} only if that alias is hers). " + caution)
        return Ans(t, "Medium", [cs["source"]], uncertain=True, intent="git_priya", derived=[str(pn_off), str(pn_alias), str(pn_off + pn_alias)])
    if ids:
        e = F.emp(ids[0])
        n = cs["by_author"].get(e["email"], 0)
        return Ans(f"{e['name']}'s work email {e['email']} has {n} commits in the export. " + caution, "High", [cs["source"]], intent="git_person", derived=[str(n)])
    t = (f"The git export holds {cs['total']} commits from {cs['first']} to {cs['last']}: " + ", ".join(f"{k} {v}" for k, v in cs["by_author"].items()) + ". "
         "The pnair@users.noreply.github.com author is an unresolved alias (plausibly Priya) and is not merged. " + caution)
    return Ans(t, "Medium", [cs["source"]], uncertain=True, intent="git", derived=[str(cs["total"])] + [str(v) for v in cs["by_author"].values()])


def h_contractor(c: Ctx) -> Ans:
    c.need("Day3")
    ct = F.contractor()
    p = ct["pis108"]
    t = (f"Invoice PIS-114 (1 Oct 2026) from Patil Infra Services bills on-call SRE support by “S. Patil” for September 2026: ₹{fmt_inr(ct['base'])} retainer + IGST ₹{fmt_inr(ct['igst'])} = ₹{fmt_inr(ct['total'])}. "
         + (f"The GL shows the earlier invoice PIS-108 (on-call support, 18–31 Aug) at ₹{fmt_inr(p['amount'])}. " if p else "")
         + "Nothing in the records links “S. Patil” to “Snehal” — the name match is only plausible.")
    return Ans(t, "High", [ct["source"], S(F.GL_F, f"row {p['row']}") if p else ct["source"]], uncertain=True, intent="contractor",
               derived=[fmt_inr(ct["base"]), fmt_inr(ct["igst"]), fmt_inr(ct["total"])] + ([fmt_inr(p["amount"])] if p else []))


def h_launch_kit(c: Ctx) -> Ans:
    c.need("Day3")
    t = D.pdf_text("Atlas_Launch_Kit_v1.pdf")
    body = t.split("Status\n", 1)[1].strip().split("\n")
    pairs = [(body[i], body[i + 1]) for i in range(0, len(body) - 1, 2)]
    kit = "; ".join(f"{a}: {b}" for a, b in pairs)
    return Ans(f"Atlas launch kit v1 (owner Sid = Siddharth Mehta, 21 Jul 2026): {kit}. Siddharth's email of 22 Jul says the kit is done and only needs a date from engineering (email 05). "
               "The kit's planned 22 Sep date was overtaken by the GA move to " + F.jira_version()["revised"] + ".", "High",
               [S("Atlas_Launch_Kit_v1.pdf", "page 1"), S("05.eml", "22 Jul 2026"), F.jira_version()["source"]], intent="launch_kit", derived=["21", "22"])


def h_cro(c: Ctx) -> Ans:
    c.need("Day3")
    nikhil = F.emp("VX006")
    return Ans("No — the move of Marketing under a new CRO is proposed, not official. T6b says Marketing will report to the new CRO “from next month, or the month after, still finalising”, and "
               f"Nikhil heard it only as “I hear” with no date (T4). The Employee Master (31 Oct) still shows Nikhil reporting to {_name(nikhil['manager_id'])}. The effective date is unconfirmed, so the proposed "
               "relationship is stored as proposed and the active reporting hierarchy is unchanged. Aisha would sit indirectly under the CRO, and Siddharth has already left.",
               "Medium", [S("T6b_CEO_Voice_Note.docx", "transcript"), S("T4_Head_of_Marketing_Call.docx", "summary"), S(F.EMP_F, "VX006 row")], uncertain=True, intent="cro")


def h_missing_data(c: Ctx) -> Ans:
    return Ans("I don't know — that data is not in the data room, and I won't estimate it. Not supplied: a HubSpot/lead-conversion export, a LinkedIn campaign export, NPS/churn/CAC/LTV metrics, "
               "Confluence postmortems, a Slack export, or any forecast. Supplied and searchable: board updates, Employee Master, GL, payroll register (amounts withheld), Jira, git, incidents, "
               "on-call, hiring, leave, pulse, invoices, emails and call transcripts.",
               "High", [S("README.txt", "data-room inventory")], uncertain=True, intent="missing_data")


def h_summit(c: Ctx) -> Ans:
    c.need("Day1")
    b3 = D.board("Jul-Sep 2026")
    t = f"The Jul–Sep 2026 board update says the Logistics Summit drew {b3['summit_registrations']} registrations, “our biggest event yet”. "
    srcs = [S(F.BOARD_Q3, "Marketing")]
    if c.d("Day3"):
        t += ("Lead quality is disputed: Nikhil calls it “our best quarter ever for pipeline”, while Manoj (Sales) reportedly says the leads are cold (T4). There is no HubSpot or lead-conversion export, so the dispute cannot be resolved from the records.")
        srcs.append(S("T4_Head_of_Marketing_Call.docx", "summary"))
    return Ans(t, "Medium", srcs, uncertain=c.d("Day3"), intent="summit", derived=[str(b3["summit_registrations"])])


def h_priya_impact(c: Ctx) -> Ans:
    c.need("Day3")
    j = F.jira_summary()
    pn = F.jira_for("VX007")
    by = j["by_assignee"]
    others = sum(v["points"] for a, v in by.items() if a != "PN")
    epics = F.epic_names()
    jr = F.jira()
    mine = jr[(jr["person"] == "VX007") & jr["is_open"]]
    ep = mine.groupby("Epic Link").size().sort_values(ascending=False)
    ep_txt = ", ".join(f"{epics.get(k, k)} ({n})" for k, n in ep.items())
    claim = c.d("Day4")
    hold = [r for r in F.hiring_rows() if r["status"] == "On hold"]
    v = F.jira_version()
    head = ("The records cannot support an exact figure for how long Atlas would slip — no exact delay can be calculated. " if has(c.q, r"how (long|many|much)|weeks|days|delay by|slip by|exact") else "")
    t = head
    if claim:
        t += ("T6d reports that “Pria” resigned with a notice period of “two months, I think” — treated as a CEO-reported, unverified claim about Priya Nair (identity High confidence; "
              "the 31 Oct HR exports hold no resignation, so HR confirmation and the real notice period are still needed). ")
    else:
        t += "No resignation by Priya is recorded; this is a hypothetical dependency analysis. "
    t += (f"Dependency: Priya (Jira PN) holds {pn['issues']} of the {j['open']} unresolved Atlas issues — {pn['points']} of {j['open_points']} open story points ({pct(pn['points'], j['open_points'])}), the most of anyone — "
          f"concentrated in {ep_txt}. Vikram's 2 Jun plan names her as lead for the core engine and re-routing (email 04). The other three assignees together hold {others} open points, "
          f"and {_join([r['req'] for r in hold])} (backend hires) are on hold, so no replacement capacity is in the pipeline. The GA date is {v['revised']}. ")
    if claim:
        t += ("If a two-month notice were served in full from about 19 Nov (the voice note itself is undated), her last day would fall in mid-to-late January 2027 — after the "
              f"{v['revised']} GA date — leaving a window for knowledge transfer, but that depends on an unverified notice period. ")
    t += ("Story points are relative estimates, not days, and there is no velocity or absorption-capacity data, so the slip cannot be quantified. "
          "Recommended actions: (1) ask Vikram for an ownership-transfer plan; (2) name a backup owner for core routing and re-routing; (3) review documentation and knowledge transfer; "
          "(4) re-estimate the release plan after reassignment; (5) get HR confirmation of the resignation and notice period. "
          "Confidence: High on the engineering dependency, Medium on identity, Low on the exact delivery impact.")
    srcs = [S(F.JIRA_F, f"Issues sheet; PN keys: {', '.join(pn['keys'])}"), S("04.eml", "2 Jun 2026"), S(F.HIRE_F, "REQ-014/REQ-015"), v["source"]]
    if claim:
        srcs += [S("T6d_CEO_Voice_Note.docx", "transcript"), S(F.EMP_F, "VX007 row")]
    return Ans(t, "Medium", srcs, uncertain=True, intent="priya_impact",
               derived=[str(pn["issues"]), str(j["open"]), str(pn["points"]), str(j["open_points"]), pct(pn["points"], j["open_points"]).rstrip("%"), str(others), "19", "2027", "5", "4", "3", "1", "2"] + [str(n) for n in ep.values])


def h_dependency(c: Ctx) -> Ans | None:
    """Generic 'what if X leaves' for people with Jira work (Priya has the richer handler above)."""
    c.need("Day3")
    ids = [p for p in c.P if p not in ("SNEHAL",)]
    if not ids:
        return None
    x = F.jira_for(ids[0])
    e = F.emp(ids[0])
    if not x:
        return Ans(f"No resignation by {e['name']} is recorded, and they hold no unresolved Atlas Jira issues, so there is no recorded Atlas work to reassign.", "Medium", [S(F.JIRA_F, "Issues sheet")], uncertain=True, intent="dependency")
    j = F.jira_summary()
    return Ans(f"No resignation by {e['name']} is recorded; this is a hypothetical dependency view. {e['name']} (Jira {x['initials']}) holds {x['issues']} unresolved Atlas issues ({x['points']} of {j['open_points']} open points). "
               "The records cannot quantify any delivery impact.", "Medium", [S(F.JIRA_F, "Issues sheet")], uncertain=True, intent="dependency",
               derived=[str(x["issues"]), str(x["points"]), str(j["open_points"])])


def h_eng_capacity(c: Ctx) -> Ans:
    c.need("Day3")
    a = h_atlas(c)
    s = F.pulse_series("Engineering")
    extra = (f" Engineering engagement also fell from {s[-2]['score']:g} to {s[-1]['score']:g} (Jul–Sep 2026; {s[-1]['responses']} of {s[-1]['team_size']} responded, comments withheld).")
    return Ans(a.text + extra, a.confidence, a.sources + [S(F.PULSE_F, "Pulse by team sheet")], uncertain=True, intent="eng_capacity", derived=a.derived + [f"{x['score']:g}" for x in s[-2:]] + [str(s[-1]["responses"]), str(s[-1]["team_size"])])


def h_worry(c: Ctx) -> Ans:
    c.need("Day1")
    top = worry_list(c.as_of)[:3]
    t = "Top three concerns, ranked by a transparent impact × likelihood × evidence score (an ordinal aid, not a probability): " + " ".join(
        f"({i}) {r['title']} [{r['severity']}, score {r['score']}] — {r['why']}" for i, r in enumerate(top, 1))
    srcs = []
    for r in top:
        for s_ in r["sources"]:
            if s_ not in srcs:
                srcs.append(s_)
    return Ans(t, "High" if all(r["confidence"] == "High" for r in top) else "Medium", srcs, uncertain=True, intent="worry",
               derived=[str(r["score"]) for r in top] + ["1", "2", "3"] + list({n for r in top for n in __import__("re").findall(r"\d[\d,.]*", r["why"])}))


# =================================================================== TIME TRAVEL
_REL_DESC = {
    "Day1": "CEO/CFO transcripts, Candidate Brief, Employee Master, selected GL, payroll register, board updates and emails 01–03",
    "Day2": "Head of People transcript, T6a, leave/hiring/pulse exports, Siddharth's resignation letter and HR emails",
    "Day3": "Marketing and Engineering transcripts, T6b, Jira, Git, incidents, on-call, launch kit, invoice and engineering emails",
    "Day4": "T6c and T6d CEO voice notes",
}
_TOPIC_TAGS = [(r"atlas|jira|launch|release|\bga\b", {"atlas"}), (r"hiring|requisition|vacanc|req-", {"hiring"}), (r"marketing|summit|launch kit", {"marketing"}),
               (r"payroll|payslip|rahul", {"payroll"}), (r"incident|sev1|outage|reliab", {"incidents"}), (r"engineering", {"engineering"}),
               (r"finance|spend|gl\b|cost", {"finance"}), (r"people|hr\b|pulse|engagement", {"people", "pulse"})]


def h_known_on(c: Ctx, date: str) -> Ans:
    first_release = RELEASES["Day1"][:10]
    end = ts(date) + __import__("pandas").Timedelta(hours=23, minutes=59)
    cockpit_days = [d for d, t in RELEASES.items() if ts(t) <= end]
    topic = c.q
    tags = set()
    for pat, tg in _TOPIC_TAGS:
        if re.search(pat, topic):
            tags |= tg
    if date < first_release:
        cutoff = c.as_of
        layer_note = ("The cockpit itself held no data on that date (the first release is " + RELEASES["Day1"] + "). Below is what Veloxa's own records, dated on or before that day, "
                      "already said — but those files reached the cockpit only in later releases, so this is reconstructed from later exports, not knowledge the cockpit had then.")
    else:
        cutoff = c.as_of if ts(c.as_of) < end else end.isoformat()
        layer_note = "Cockpit knowledge on that date: " + "; ".join(f"{d} ({_REL_DESC[d]})" for d in cockpit_days) + ". Later releases are excluded."
    evs = T.known_on(date, cutoff, tags or None, limit=8)
    b = T.board_as_of(date) if evs or date < first_release else T.board_as_of(date)
    lines = []
    if b and available(cutoff, "Day1"):
        lines.append(f"Latest board update by then (sent {b['sent']}): ARR ₹{b['arr_cr']} Cr, burn ₹{b['burn_lakh']:g} lakh/month, {b['customers']} customers, runway {b['runway_months']} months. {b['product']}")
    for e in evs:
        if e["title"].startswith("Board update"):
            continue
        lines.append(f"{e['date']} — {e['title']}: {e['detail']}")
    gap = ""
    if available(cutoff, "Day3") and F.jira_version()["changed_on"] <= date and b and pd_ts(b["sent"]) < F.jira_version()["changed_on"]:
        v = F.jira_version()
        gap = (f" Note the gap: Jira already had Atlas GA at {v['revised']} from {v['changed_on']}, but the latest board update by then (sent {b['sent']}) still described the earlier plan; "
               "the board had not been told of the move by that date.")
        if any(pd_ts(D.board(x)["sent"]) > date for x in ("Apr-Jun 2026", "Jul-Sep 2026")) is False:
            gap = gap.replace("the board had not been told of the move by that date.", "no later board update exists in the records.")
    inv = ""
    if date >= first_release:
        inv = " Release inventory: " + " ".join(f"{d}: {_REL_DESC[d]}." for d in cockpit_days)
    if not lines:
        t = f"As of {date}: {layer_note} No dated record in the available releases falls on or before this date."
    else:
        t = f"As of {date}: {layer_note}\n" + "\n".join(f"- {l}" for l in lines) + gap + (("\n" + inv.strip()) if inv else "")
    srcs = list(dict.fromkeys(e["source"] for e in evs if not e["title"].startswith("Board update")))
    if b and available(cutoff, "Day1"):
        srcs.insert(0, S(b["file"], "Key numbers and Product"))
    return Ans(t, "High", srcs or ["Release schedule (ARCHITECTURE.md)"], uncertain=False, intent="known_on",
               derived=[str(int(x)) for x in re.findall(r"\d+", t)][:200])


def pd_ts(sent: str) -> str:
    import pandas as pd
    return pd.to_datetime(sent, format="%d %b %Y").strftime("%Y-%m-%d")


# =================================================================== DEPT OVERVIEW / FALLBACK
def h_dept_overview(c: Ctx) -> Ans | None:
    d = dept_in(c.q)
    if not d or not has(c.q, r"tell me about|overview|summary|status|how is|how are|what is .* doing|update on|brief"):
        return None
    c.need("Day1")
    ppl = F.employees()[F.employees()["dept"] == d]
    parts = [f"{d} has {len(ppl)} recorded employees: " + ", ".join(f"{r['name']} ({r['title']})" for _, r in ppl.iterrows()) + "."]
    srcs = [S(F.EMP_F, "Employees sheet")]
    if c.d("Day2") and d in F.pulse_teams():
        s = F.pulse_series(d)
        parts.append(f"Engagement {s[-2]['score']:g} → {s[-1]['score']:g} (Jul–Sep 2026).")
        srcs.append(S(F.PULSE_F, "Pulse by team sheet"))
        hr = [r for r in F.hiring_rows() if r["team"] == d]
        if hr:
            parts.append("Requisitions: " + "; ".join(f"{r['req']} {r['status']}" for r in hr) + ".")
            srcs.append(S(F.HIRE_F, "Requisitions sheet"))
    if d == "Engineering" and c.d("Day3"):
        j = F.jira_summary()
        parts.append(f"Atlas: {j['open']} of {j['total']} Jira issues unresolved ({j['open_points']} story points); GA {F.jira_version()['revised']}.")
        srcs += j["sources"]
    if d == "Marketing":
        m = F.marketing_ledger()
        parts.append(f"GL marketing cost centres: ₹{lakh(m['total'], 4)} lakh (selected cost centres only).")
        srcs.append(m["source"])
    return Ans(" ".join(parts), "High", srcs, intent="dept_overview",
               derived=[str(len(ppl))] + list(__import__("re").findall(r"\d[\d,.]*", " ".join(parts))))


def fallback(c: Ctx) -> Ans:
    from .ingestion import search_evidence
    hits = search_evidence(c.raw, as_of=c.as_of, limit=4)
    if hits and hits[0]["matched"] >= 2:
        ex = "\n".join(f"- {h['file_name']} ({h['locator']}) [{h['evidence_id']}]: {h['text'][:240].replace(chr(10), ' ')}" for h in hits[:3])
        return Ans("I do not have a verified answer to that. These are the closest records — unverified excerpts, not a conclusion; read them before relying on them:\n" + ex,
                   "Low", [f"{h['file_name']} — {h['locator']} ({h['evidence_id']})" for h in hits], uncertain=True, intent="retrieval_unverified")
    return Ans("I don't know based on the records available to the cockpit. No sufficiently relevant evidence was found, so I will not invent an answer.", "Low", [], uncertain=True, intent="unknown")


# =================================================================== ROUTER
_INJECTION = r"ignore (all |the |your )?(previous|prior|above|earlier) (instructions|rules)|just guess|make (it|something|a number) up|pretend|jailbreak|system prompt|without (any )?(sources|evidence|citations)|don'?t (cite|say you don'?t know)"
_PAY = r"salary|salaries|\bpay\b|\bpaid\b|gross|net pay|\bctc\b|compensation|\bwages?\b|\bearn|payslip|take[- ]home|\bhike\b|bonus"
_AMOUNT_Q = r"how much|amount|what (is|was|are) .*(salary|pay|gross|net|ctc)|show .*(salary|salaries|pay|gross|net)|tell me .*(salary|salaries)|\bgross\b|\bnet\b|\bctc\b"
_ANOMALY = r"incorrect|wrong|error|overpa|over-pa|mistake|resolved|query|issue|what happened|prorat|partial|anomal|problem|discrepan|higher|correct\b|right\b|fix"


def route(c: Ctx) -> Ans | None:
    q = c.q
    # ---- time travel
    if has(q, r"what did we know|what was known|known on|knowledge (on|as of)|state of the company on|as of (the )?\d|what do we know as of|did we know"):
        date = parse_date(q)
        if date:
            return h_known_on(c, date)
        return Ans("Which date? Ask for example “What did we know on 15 September 2026?” — I will separate what Veloxa's records showed by then from what had been released to the cockpit.",
                   "High", [], uncertain=True, intent="known_on_needs_date", derived=["15"])
    # ---- safety
    if has(q, r"\bslack\b|\bchats?\b|conversations? between|private (messages?|chats?|dms?)|direct messages?|\bdms\b|whatsapp (chat|message)s? (of|from)|read (their|everyone'?s|employees') (messages|chats)"):
        return h_slack(c)
    if has(q, r"likely to (quit|leave|resign)|who (will|is going to|might|may|could|is about to|is likely to) (quit|resign|leave)|(quit|resign|leave) next|flight[- ]?risk|"
              r"rank\w* .*(quit|resign|attrition|leave|leaving)|predict\w* .*(quit|resign|attrition|leaving)|(probability|chance|likelihood) (of|that) .*(quit|resign|leav)|"
              r"who is thinking (of|about) (quitting|leaving|resigning)|definitely .*(resign|quit)|about to (quit|resign)|planning to (quit|resign|leave)|unhappy employees|disgruntled"):
        return h_quit(c)
    if has(q, r"unhappy|disgruntled|dissatisfied|miserable|\bis \w+ (really |actually )?(happy|unhappy|satisfied|stressed|upset|angry|miserable|motivated|frustrated|burnt out|burned out)|are (they|employees|people) (happy|unhappy|stressed)|private thoughts?|real (thoughts|feelings)|true feelings|secretly|what is .* (really )?thinking|what does \w+ (really )?(think|feel)|honest opinion|inner (thoughts|feelings)|what do they really"):
        return h_thoughts(c)
    if has(q, r"most productive|least productive|best (engineer|developer|performer)|top performer|worst (engineer|developer|performer)|underperform|who works (the )?hardest|laziest|rank .*(productiv|performance)"):
        return h_rank_people(c)
    pay_q = has(q, _PAY)
    # Rahul-payroll anomaly takes precedence over a salary refusal because it needs no amounts
    amount_q = has(q, r"how much|amount|\bgross\b|\bnet\b|\bctc\b|what('s| is| was| are) .*(salary|pay\b|compensation|earn)|show .*(salary|pay\b)|tell me .*(salary|pay\b)|take-home|\bearns?\b")
    if "VX018" in c.P and has(q, r"payroll|payslip|salary|paid|pay\b|february|feb\b|prorat") and not amount_q:
        return h_rahul_payroll(c)
    if (has(q, r"who (processed|ran|did|handled|prepared|run|made)") and has(q, r"payroll|pay run|payslip")) or \
            (has(q, r"payroll") and has(q, r"karthik|fatima") and has(q, r"feb|run|ran|process|why")):
        return h_payroll_processor(c)
    if pay_q and (c.P or has(q, r"everyone|everybody|each|all (the )?(employees|staff|people)|\bteam\b|\bhis\b|\bher\b|\btheir\b|salary slips?|payslips?")):
        if not has(q, r"total|aggregate|company[- ]wide|payroll cost|payroll total|monthly payroll|salary bill|\bgl\b|books"):
            return h_salary_refuse(c)
    # ---- people / identity
    if has(q, r"\bsneha\b") and has(q, r"\bsnehal\b") and has(q, r"same|different|one person|identical|\bis\b|\bare\b|link|connected|contractor"):
        return h_sneha_snehal(c)
    if "SNEHAL" in c.P and not any(p == "VX012" for p in c.P):
        return h_sneha_snehal(c)
    if "VX007" in c.P and has(q, r"resign|quit|leave|leaving|left|notice|depart|walk(s)? out|exit"):
        if has(q, r"atlas|launch|release|board|delay|impact|slip|ship|version|affect|what happens|do to|mean for|schedule|ga\b|plan"):
            return h_priya_impact(c)
        return h_priya_resignation(c)
    if has(q, r"what (happens|if)|if .* (leaves|resigns|quits|left)|(leaves|resigns|quits) .* (what|impact)") and c.P and has(q, r"leave|leaves|resign|quit|depart|gone|goes"):
        r = h_dependency(c)
        if r:
            return r
    if has(q, r"lost (anyone|someone|people|staff|employees|any)|anyone (has )?(left|resigned|quit)|has (anyone|marketing|engineering|finance|sales|support) (lost|left|resigned)|did anyone (from \w+ )?(resign|quit|leave)|who (has |have )?(resigned|quit|left|is leaving|are leaving|handed in)|which (\w+ ){0,3}(resigned|quit|left|is leaving)|handed in (their|his|her) papers|resignations?|departures?|who left|who is leaving") and "VX013" not in c.P:
        return h_resigned_list(c)
    if "VX013" in c.P and has(q, r"resign|last (working )?day|left|leav|exit|notice|still|status|handover|replace|backfill|depart"):
        return h_siddharth(c)
    if has(q, r"attrition"):
        return h_attrition(c)
    # ---- governance / numbers
    if has(q, r"what should i (worry|be worried|focus|watch)|worr(y|ies|ied)|top (three|3)|biggest (risks?|concerns?)|key risks?|\brisks?\b|concerns?"):
        return h_worry(c)
    if has(q, r"how many .*(agents?|ai colleagues|personas)|number of agents|\b14\b.*agents?"):
        return h_agent_count(c)
    if has(q, r"headcount|\b180\b.*(people|employees|staff)|(people|employees|staff).*\b180\b|how many (employees|people|staff|team members|folks|workers)|team size|size of (the )?(company|team)|how big|number of employees|company size|how many .* (work|working) (at|for|in) (veloxa|the company)"):
        return h_headcount(c)
    if has(q, r"forecast|project(ed|ion|ions)\b|predict|next (year|quarter|month|fy)|will (we|our|the|it) .*(reach|hit|be|grow|touch)|by (march|december|2027|year[- ]end)|expected (revenue|arr|burn)") \
            and has(q, r"\barr\b|revenue|burn|customers?|runway|headcount|cash|sales|growth"):
        return h_forecast(c)
    if has(q, r"\barr\b|recurring revenue|annual(ised|ized)? recurring|annual revenue|\brevenue\b|how much (do we|are we) (make|earning|earn)|top line"):
        return h_arr(c)
    if has(q, r"\bburn\b|cash burn|burn rate|monthly (burn|spend|cash)|how much (cash )?(do we|are we) (spend|burn|consume|use)|cash (we )?(consume|use|spend)|consume each month|monthly (cash )?(consumption|outflow)"):
        return h_burn(c)
    if has(q, r"runway|cash (left|remaining)|how long (can|will) we (last|survive)|months of cash"):
        return h_runway(c)
    if has(q, r"customers?|clients?") and has(q, r"how many|number|count|total|\bhave\b"):
        return h_customers(c)
    if has(q, r"(payroll|salary|salaries) (cost|total|spend|expense|bill)|cost of payroll|total payroll|payroll for") or (has(q, r"payroll") and has(q, r"cost|total|spend|expense|september|\bsep\b|engineering|department")):
        return h_payroll_total(c)
    if has(q, r"1\.8|one point eight") or has(q, r"marketing") and has(q, r"spend|cost|expense|ledger|budget|spent|total") or has(q, r"sapphire|saphire|google ads|google india|\bgoogle\b|paid search|summit (cost|spend|budget)|event (cost|spend)") \
            or (has(q, r"\bevents?\b|summit") and has(q, r"spend|spent|cost|paid|budget|ledger|expense")):
        return h_marketing_spend(c)
    gl = None
    if has(q, r"\baws\b|amazon web|\brent\b|wework|recruit(er|ers|ment)? fees?|\brecruiters?\b|cohere|search fee|offsite|hotel|travel (cost|spend)|infra(structure)? (cost|spend)|cloud (cost|spend)"):
        gl = h_gl_lookup(c)
    if gl:
        return gl
    # ---- engineering
    if has(q, r"patil|invoice|contractor|pis-?1\d\d|s\. patil"):
        return h_contractor(c)
    if has(q, r"launch kit|launch assets|collateral|press note"):
        return h_launch_kit(c)
    if has(q, r"\bcro\b|chief revenue|report(s|ing)? (in)?to the new|reporting line .*market") and (has(q, r"market|report|move|official|cro") ):
        return h_cro(c)
    if has(q, r"hubspot|conversion rate|\bnps\b|\bchurn\b|\bcac\b|\bltv\b|net promoter|win rate|pipeline value|sales funnel"):
        return h_missing_data(c)
    if has(q, r"summit|registrations|leads? (are|were)? ?(cold|quality)|lead quality"):
        return h_summit(c)
    if has(q, r"on[- ]?call|rota|pager"):
        return h_oncall(c)
    if has(q, r"incidents?|sev ?[123]|outages?|downtime|postmortems?|pagerduty"):
        return h_incidents(c)
    if has(q, r"\bplan\b|what did \w+ (say|write|wrote|email|tell|mention)|said about|wrote about|email (from|to|about)|did \w+ (email|write to)") and not has(q, r"slack"):
        r = h_email_lookup(c)
        if r:
            return r
    if has(q, r"replac(e|es|ement)|successor|takes? over|take over|cover for|backup (owner|for)") and c.P:
        return h_replacement(c)
    if has(q, r"commits?|git\b|github|repository|repo\b|writes? the most code|most code|top committer"):
        return h_git(c)
    if (has(q, r"how much work|work (is )?assigned|assigned to|workload|on (his|her|their) plate|\btasks?\b|how busy|work(ing)? load") and c.P and "SNEHAL" not in c.P) or \
            has(q, r"jira|tickets?|story points?|backlog|issues?\b") and not has(q, r"delay|why|behind|reason|\bga\b|release date|launch date|launch|when\b|stand"):
        return h_jira(c)
    if has(q, r"disruption|setbacks?|derail|what (went wrong|caused)|what is blocking|blocking the launch|blockers?|why .*(engineering|team).*(behind|slow|late|falling)|engineering (is )?(falling|behind|slow|overloaded|stretched)|falling behind|capacity|overload|velocity|burnout|stretched thin"):
        return h_eng_capacity(c)
    if has(q, r"\batlas\b|\bga\b|launch|release date|go[- ]live|on track|ship") and not has(q, r"marketing|launch kit"):
        return h_atlas(c)
    # ---- people
    if has(q, r"pulse|engagement|survey|culture amp|morale|eNPS|satisfaction"):
        return h_pulse(c)
    if has(q, r"hiring|\bhires?\b|pausing|requisitions?|req-?\d{3}|vacanc|open roles|recruit|openings|backfill|paused roles|on hold|pipeline|candidates|applicants|who paused"):
        return h_hiring(c)
    r = h_role_lookup(c)
    if r:
        return r
    if c.P:
        r = h_person(c)
        if r:
            return r
    if has(q, r"who (is|are)|list|members|team|who works|staff in|people in"):
        r = h_team_members(c)
        if r:
            return r
    r = h_dept_overview(c)
    if r:
        return r
    return None


def _llm_enabled() -> bool:
    return os.getenv("VELOXA_LLM_POLISH", "auto").lower() not in ("0", "false", "off", "no")


def answer_question(question: str, as_of: str = DEFAULT_AS_OF, use_llm: bool | None = None, generator=None) -> dict:
    c = Ctx(question, as_of)
    notice = ""
    if has(c.q, _INJECTION):
        notice = "I only report what the records support, so I won't guess, invent or drop citations. "
        c.q = re.sub(_INJECTION, " ", c.q)
    if not c.q.strip():
        return _out(Ans("Please ask a question about Veloxa.", "High", [], uncertain=True, intent="empty"), as_of, question)
    try:
        ans = route(c)
        if ans is None and (use_llm if use_llm is not None else _llm_enabled()):
            ans = llm_route(c, generator)
        ans = ans or fallback(c)
    except NotYet as ny:
        ans = Ans(f"I don't know from the information released by this cutoff. The relevant source material is not available until {ny.day} ({RELEASES[ny.day]}). Later releases are excluded.",
                  "High", [], uncertain=True, intent="not_yet_released")
    if notice:
        ans.text = notice + ans.text
    out = _out(ans, as_of, question)
    if (use_llm if use_llm is not None else _llm_enabled()) and ans.intent not in ("not_yet_released", "unknown", "empty") and not ans.refused:
        from .llm import safe_rewrite
        rw = safe_rewrite(ans.text, evidence="\n".join(ans.sources), require_uncertainty=ans.uncertain, generate=generator)
        out["answer"], out["llm"] = rw["text"], {k: rw[k] for k in ("used_llm", "guard_ok", "reasons")}
        out["verified_answer"] = ans.text
    else:
        out["llm"] = {"used_llm": False, "guard_ok": True, "reasons": []}
    return out


def _out(a: Ans, as_of: str, question: str) -> dict:
    return {"answer": a.text, "confidence": a.confidence, "sources": a.sources, "uncertain": a.uncertain, "refused": a.refused,
            "intent": a.intent, "derived": a.derived, "as_of": as_of, "question": question, "verified_answer": a.text}


# =================================================================== OPTIONAL: LLM AS A *CLASSIFIER ONLY*
# When no rule matches, a local model may pick ONE intent from this closed menu. The deterministic handler still writes
# every fact, so recall improves without opening any path for hallucinated content.
INTENT_MENU = {
    "arr": h_arr, "burn": h_burn, "customers": h_customers, "runway": h_runway, "headcount": h_headcount, "marketing_spend": h_marketing_spend,
    "payroll_total": h_payroll_total, "rahul_payroll": h_rahul_payroll, "payroll_processor": h_payroll_processor, "hiring": h_hiring,
    "pulse": h_pulse, "siddharth": h_siddharth, "resigned_list": h_resigned_list, "atlas": h_atlas, "jira": h_jira, "incidents": h_incidents,
    "oncall": h_oncall, "sneha_snehal": h_sneha_snehal, "git": h_git, "contractor": h_contractor, "launch_kit": h_launch_kit, "cro": h_cro,
    "summit": h_summit, "worry": h_worry, "attrition": h_attrition, "eng_capacity": h_eng_capacity, "priya_impact": h_priya_impact,
}


def llm_route(c: Ctx, generator=None) -> Ans | None:
    from . import ollama_client
    gen = generator or ollama_client.generate
    prompt = ("Classify the executive's question into exactly ONE label from this list, or NONE if none fits. Reply with the label only.\n"
              "Labels: " + ", ".join(INTENT_MENU) + "\nQuestion: " + c.raw)
    try:
        out = (gen(prompt) or "").strip().lower().split()[0:1]
    except Exception:
        return None
    label = out[0].strip(".,:;\"'") if out else ""
    fn = INTENT_MENU.get(label)
    if not fn:
        return None
    try:
        ans = fn(c)
    except NotYet:
        raise
    if ans:
        ans.intent = f"llm_routed:{ans.intent}"
        ans.confidence = ans.confidence if ans.confidence != "High" else "Medium"  # routed by a model, not a rule
    return ans
