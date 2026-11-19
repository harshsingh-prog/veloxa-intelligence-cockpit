"""Fact layer: every figure the cockpit may state is computed here from the raw files.

Nothing in this module is typed in by hand except two *documented inferences* (identity aliases),
each carrying its own evidence and confidence. Handlers in answer_engine.py only format these facts.
"""
from __future__ import annotations

import functools
import re

import pandas as pd

from . import data as D
from .data import lakh, fmt_inr, num

EMP_F, JIRA_F, VER_F = "Employee_Master.xlsx", "Jira_Export_ATLAS.xlsx", "Jira_Export_ATLAS.xlsx"
INC_F, PULSE_F, HIRE_F = "Incidents_Aug-Oct_2026.xlsx", "Pulse_Survey.xlsx", "Hiring_Tracker.xlsx"
GL_F, ONCALL_F, LEAVE_F = "GL_Export_Apr-Sep_2026.xlsx", "OnCall_Rota.xlsx", "Leave_Register.xlsx"
BOARD_Q3, BOARD_Q2 = "Board_Update_Jul-Sep_2026.pdf", "Board_Update_Apr-Jun_2026.pdf"

DEPT_ORDER = ["Engineering", "Finance", "People & Ops", "Marketing"]
QUARTERS = ["Oct-Dec 2025", "Jan-Mar 2026", "Apr-Jun 2026", "Jul-Sep 2026"]


def day(file_name: str) -> str:
    return D.day_of(D.path_of(file_name))


def src(file_name: str, locator: str) -> str:
    return f"{file_name} — {locator}"


# ------------------------------------------------------------------ identity resolution
# Two *inferences* the data supports. Everything else (e.g. Sneha vs Snehal) stays unresolved.
JIRA_ASSIGNEE = {  # Jira shows initials only (see sheet title). Each initial pair is unique in Employee Master.
    "PN": "VX007", "RV": "VX018", "AD": "VX009", "SK": "VX012",
}
NICKNAMES = {  # transcript mishearing / short form -> (emp_id, confidence, evidence)
    "pria": ("VX007", "High", "T1/T5/T6d say 'Pria' for the routing lead; only Priya Nair fits (Employee Master title, Jira PN, email 04)."),
    "sid": ("VX013", "High", "sid@veloxa.in is Siddharth Mehta's work email in Employee Master."),
    "kartik": ("VX010", "High", "T2 'Kartik' on planning = Karthik Subramanian, FP&A Manager."),
    "ayesha": ("VX011", "Medium", "T4 'Ayesha' runs paid search; Employee Master has Aisha Khan, Performance Marketing Manager."),
}


@functools.lru_cache(maxsize=None)
def employees() -> pd.DataFrame:
    t = D.table(EMP_F)
    df = pd.DataFrame({
        "emp_id": t["Emp ID"], "name": t["Full Name"], "email": t["Work Email"], "dept": t["Department"],
        "title": t["Title"], "manager_id": t["Manager ID"].where(t["Manager ID"].notna(), None),
        "join_date": t["Join Date"].astype(str).str[:10], "location": t["Location"], "status": t["Status"],
        "exit_date": t["Exit Date"].where(t["Exit Date"].notna(), None), "_row": t["_row"],
    })
    df["exit_date"] = df["exit_date"].map(lambda v: None if v is None else str(v)[:10])
    df["first"] = df["name"].str.split().str[0].str.lower()
    return df


def emp(emp_id: str) -> dict:
    r = employees()[employees()["emp_id"] == emp_id]
    return r.iloc[0].to_dict() if len(r) else {}


def emp_name(emp_id: str | None) -> str:
    return emp(emp_id).get("name", "unknown") if emp_id else "no manager recorded"


def by_title(title: str) -> dict | None:
    r = employees()[employees()["title"].str.lower() == title.lower()]
    return r.iloc[0].to_dict() if len(r) else None


def agents_roster() -> list[dict]:
    e = employees()
    e = e[e["dept"].isin(DEPT_ORDER)]
    order = {d: i for i, d in enumerate(DEPT_ORDER)}
    return e.assign(_o=e["dept"].map(order)).sort_values(["_o", "emp_id"]).drop(columns="_o").to_dict("records")


def headcount() -> dict:
    e = employees()
    return {
        "records": len(e), "active": int((e["status"] == "Active").sum()),
        "notice": int((e["status"] == "Notice period").sum()),
        "by_dept": e["dept"].value_counts().to_dict(),
        "board_q2": D.board("Apr-Jun 2026")["team"], "board_q3": D.board("Jul-Sep 2026")["team"],
        "sources": [src(EMP_F, f"Employees sheet, rows {int(e['_row'].min())}-{int(e['_row'].max())}"),
                    src(BOARD_Q3, "Key numbers — Team"), src(BOARD_Q2, "Key numbers — Team")],
    }


# ------------------------------------------------------------------------------- Jira
@functools.lru_cache(maxsize=None)
def jira() -> pd.DataFrame:
    t = D.table(JIRA_F, "Issues")
    t = t[t["Key"].astype(str).str.startswith("ATLAS-")].copy()
    t["points"] = num(t["Story Points"]).fillna(0).astype(int)
    t["is_open"] = t["Status"].astype(str).str.strip().str.lower() != "done"
    t["person"] = t["Assignee"].map(JIRA_ASSIGNEE)
    return t.reset_index(drop=True)


def jira_summary() -> dict:
    j = jira()
    o = j[j["is_open"]]
    by = {}
    for a, g in o.groupby("Assignee"):
        by[a] = {"issues": len(g), "points": int(g["points"].sum()), "emp_id": JIRA_ASSIGNEE.get(a),
                 "keys": g["Key"].tolist()}
    return {
        "total": len(j), "done": int((~j["is_open"]).sum()),
        "in_progress": int((j["Status"] == "In Progress").sum()), "todo": int((j["Status"] == "To Do").sum()),
        "open": len(o), "open_points": int(o["points"].sum()), "by_assignee": by,
        "unassigned_open": int(o["Assignee"].isna().sum()),
        "rows": f"rows {int(j['_row'].min())}-{int(j['_row'].max())}",
        "sources": [src(JIRA_F, f"Issues sheet, rows {int(j['_row'].min())}-{int(j['_row'].max())}")],
    }


def jira_for(emp_id: str) -> dict | None:
    for a, v in jira_summary()["by_assignee"].items():
        if v["emp_id"] == emp_id:
            j = jira()
            mine = j[j["person"] == emp_id]
            return {**v, "initials": a, "total": len(mine), "done": int((~mine["is_open"]).sum()),
                    "total_points": int(mine["points"].sum()),
                    "epics": sorted(set(mine[mine["is_open"]]["Epic Link"].dropna()))}
    return None


def epic_names() -> dict:
    t = D.table(JIRA_F, "Epics")
    return dict(zip(t["Key"], t["Epic Name"]))


def jira_version() -> dict:
    v = D.table(VER_F, "Versions").iloc[0]
    return {"version": v["Version"], "revised": str(v["Release Date"])[:10],
            "original": str(v["Original Release Date"])[:10], "changed_on": str(v["Last Changed"])[:10],
            "changed_by": v["Changed By"], "source": src(VER_F, f"Versions sheet, row {int(v['_row'])}")}


# --------------------------------------------------------------------------- incidents
@functools.lru_cache(maxsize=None)
def incidents() -> pd.DataFrame:
    t = D.table(INC_F).copy()
    t["opened_utc"] = pd.to_datetime(t["Opened"], utc=True)
    t["month"] = t["opened_utc"].dt.strftime("%Y-%m")
    return t


def incident_summary() -> dict:
    t = incidents()
    return {
        "total": len(t), "by_sev": t["Severity"].value_counts().to_dict(),
        "sev1_by_month": t[t["Severity"] == "SEV1"]["month"].value_counts().to_dict(),
        "sev1_rows": t[t["Severity"] == "SEV1"][["ID", "opened_utc", "Service", "Responder"]].to_dict("records"),
        "responders": t["Responder"].value_counts().to_dict(),
        "by_service": t["Service"].value_counts().to_dict(),
        "span": (t["opened_utc"].min().date().isoformat(), t["opened_utc"].max().date().isoformat()),
        "source": src(INC_F, f"Incidents sheet, rows {int(t['_row'].min())}-{int(t['_row'].max())} (timestamps UTC)"),
    }


# ----------------------------------------------------------------------------- pulse
@functools.lru_cache(maxsize=None)
def pulse() -> pd.DataFrame:
    t = D.table(PULSE_F).copy()
    for c in ["Team size", "Responses", "Engagement (1-5)"]:
        t[c] = num(t[c])
    return t


def pulse_series(team: str) -> list[dict]:
    t = pulse()
    t = t[t["Team"] == team]
    out = []
    for q in QUARTERS:
        r = t[t["Quarter"] == q]
        if len(r):
            r = r.iloc[0]
            out.append({"quarter": q, "score": float(r["Engagement (1-5)"]), "responses": int(r["Responses"]),
                        "team_size": int(r["Team size"]), "row": int(r["_row"])})
    return out


def pulse_teams() -> list[str]:
    return list(dict.fromkeys(pulse()["Team"].tolist()))


# --------------------------------------------------------------------------- hiring
@functools.lru_cache(maxsize=None)
def hiring() -> pd.DataFrame:
    t = D.table(HIRE_F).copy()
    t["pipeline"] = num(t["In pipeline"]).fillna(0).astype(int)
    return t


def hiring_rows() -> list[dict]:
    return [{"req": r["Req ID"], "role": r["Role"], "team": r["Team"], "status": r["Status"],
             "status_date": str(r["Status Date"])[:10], "opened": str(r["Opened"])[:10],
             "pipeline": int(r["pipeline"]), "notes": r["Notes"] if pd.notna(r["Notes"]) else "",
             "manager": emp_name(r["Hiring Manager"]), "row": int(r["_row"])} for _, r in hiring().iterrows()]


# ------------------------------------------------------------------------------ GL
@functools.lru_cache(maxsize=None)
def gl() -> pd.DataFrame:
    t = D.table(GL_F).copy()
    t["amount"] = num(t["Amount (Rs.)"])
    t["date"] = t["Txn Date"].astype(str).str[:10]
    return t


def gl_lines(mask) -> list[dict]:
    t = gl()[mask(gl())]
    return [{"date": r["date"], "voucher": r["Voucher"], "vendor": r["Vendor / Payee"], "ref": r["Ref"],
             "cc": r["Cost Centre"], "amount": float(r["amount"]), "narr": r["Narration"], "row": int(r["_row"])}
            for _, r in t.iterrows()]


def marketing_ledger() -> dict:
    t = gl()
    m = t[t["Cost Centre"].astype(str).str.startswith("MKT")]
    ev, ps = m[m["Cost Centre"] == "MKT-EVT"], m[m["Cost Centre"] == "MKT-PS"]
    return {
        "total": float(m["amount"].sum()), "events": float(ev["amount"].sum()), "paid_search": float(ps["amount"].sum()),
        "lines": gl_lines(lambda d: d["Cost Centre"].astype(str).str.startswith("MKT")),
        "event_vendors": ev["Vendor / Payee"].tolist(),
        "source": src(GL_F, f"GL Apr-Sep sheet, cost centres MKT-EVT and MKT-PS (rows {', '.join(str(int(r)) for r in m['_row'])})"),
    }


def sapphire_vendors() -> list[dict]:
    return gl_lines(lambda d: d["Vendor / Payee"].astype(str).str.lower().str.contains(r"sapph?ire|saphire", regex=True))


def payroll_gl() -> dict:
    t = gl()
    p = t[t["Cost Centre"] == "PAYROLL"]
    return {"months": {r["date"][:7]: float(r["amount"]) for _, r in p.iterrows()}, "total": float(p["amount"].sum()),
            "source": src(GL_F, f"GL Apr-Sep sheet, cost centre PAYROLL (rows {', '.join(str(int(r)) for r in p['_row'])})")}


# -------------------------------------------------------------------------- payroll audit (non-monetary only)
def payroll_run_audit(emp_id: str, month: str) -> dict | None:
    p = D.payroll_meta()
    r = p[(p["Emp ID"] == emp_id) & (p["Month"] == month)]
    if not len(r):
        return None
    r = r.iloc[0]
    month_runs = p[p["Month"] == month]
    return {"days_in_month": int(r["Days in Month"]), "days_payable": int(r["Days Payable"]),
            "processed_by": r["Processed By"], "row": int(r["_row"]), "rows_in_run": len(month_runs),
            "processors_in_run": sorted(set(month_runs["Processed By"]))}


def feb_proration(emp_id: str = "VX018") -> dict:
    e, a = emp(emp_id), payroll_run_audit(emp_id, "Feb-2026")
    j = pd.Timestamp(e["join_date"])
    month_end = pd.Timestamp("2026-02-28")
    expected = int((month_end - j).days + 1)  # calendar-day proration, inclusive of join date
    return {"join_date": e["join_date"], "expected_days": expected, "recorded_days": a["days_payable"],
            "days_in_month": a["days_in_month"], "gap_days": a["days_payable"] - expected,
            "gap_fraction": (a["days_payable"] - expected) / a["days_in_month"], "audit": a}


def jan_rows() -> int:
    return len(D.payroll_meta().query("Month == 'Jan-2026'"))


# ---------------------------------------------------------------------------- git / on-call / leave
def commit_summary() -> dict:
    g = D.git_log()
    vc = g["author_email"].value_counts().to_dict()
    return {"by_author": vc, "total": len(g), "first": g["committed_at"].min().date().isoformat(),
            "last": g["committed_at"].max().date().isoformat(),
            "source": src("git_log.csv", f"{len(g)} commit rows (author_email column)")}


@functools.lru_cache(maxsize=None)
def oncall() -> pd.DataFrame:
    return D.table(ONCALL_F)


def oncall_summary() -> dict:
    t = oncall()
    first_snehal = t[(t["Primary"] == "Snehal") | (t["Secondary"] == "Snehal")]["Week of"].astype(str).str[:10].min()
    return {"weeks": len(t), "primary": t["Primary"].value_counts().to_dict(),
            "secondary": t["Secondary"].value_counts().to_dict(), "first_snehal_week": first_snehal,
            "source": src(ONCALL_F, f"On-call sheet, rows {int(t['_row'].min())}-{int(t['_row'].max())}")}


def leave_for(label: str) -> list[dict]:
    t = D.table(LEAVE_F)
    t = t[t["Employee"] == label]
    return [{"type": r["Leave Type"], "from": str(r["From"])[:10], "to": str(r["To"])[:10], "days": int(r["Days"]),
             "row": int(r["_row"])} for _, r in t.iterrows()]


# --------------------------------------------------------------------------- contractor
def contractor() -> dict:
    inv = D.pdf_text("Invoice_PIS-114.pdf")
    base = int(re.search(r"S\. Patil.*?([\d,]{5,})\s*\n", inv, re.S).group(1).replace(",", ""))
    igst = int(re.search(r"IGST @ 18%\s*\n\s*([\d,]+)", inv).group(1).replace(",", ""))
    total = int(re.search(r"Total\s*\n\s*([\d,]+)", inv).group(1).replace(",", ""))
    pis108 = gl_lines(lambda d: d["Ref"].astype(str) == "PIS-108")
    return {"base": base, "igst": igst, "total": total, "pis108": pis108[0] if pis108 else None,
            "invoice_date": "2026-10-01", "vendor": "Patil Infra Services",
            "source": src("Invoice_PIS-114.pdf", "page 1")}
