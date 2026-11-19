"""Independent ground truth for the accuracy evaluation.

Deliberately does NOT import veloxa.facts / veloxa.data: it re-reads the raw files with its own minimal code so that a bug
in the application's parser cannot also hide in the test expectations. Values are cross-checked against numbers verified by hand
when the data room was first inspected (see tests/test_oracle_anchors.py).
"""
from __future__ import annotations

import glob
import os
import re

import pandas as pd
from pypdf import PdfReader

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "Veloxa_Hackathon_Release_Packs")


def _f(pat):
    return glob.glob(os.path.join(RAW, "**", pat), recursive=True)[0]


def _x(pat, sheet=0, header=2):
    return pd.read_excel(_f(pat), sheet_name=sheet, header=header)


def _board(pat):
    lines = [l.strip() for l in "\n".join(p.extract_text() for p in PdfReader(_f(pat)).pages).split("\n")]
    nxt = lambda label: lines[lines.index(label) + 1]  # noqa: E731
    return {"arr": nxt("ARR (recurring)"), "customers": int(nxt("Customers")), "burn": nxt("Monthly burn"), "runway": nxt("Runway")}


def build() -> dict:
    o: dict = {}
    b3, b2 = _board("Board_Update_Jul-Sep_2026.pdf"), _board("Board_Update_Apr-Jun_2026.pdf")
    o.update(arr3=b3["arr"], arr2=b2["arr"], cust3=b3["customers"], cust2=b2["customers"], burn3=b3["burn"], runway3=b3["runway"])
    e = _x("Employee_Master.xlsx")
    o["emp_n"] = len(e)
    o["emp_active"] = int((e["Status"] == "Active").sum())
    o["title"] = {r["Title"]: r["Full Name"] for _, r in e.iterrows()}
    o["mgr"] = {r["Full Name"]: e[e["Emp ID"] == r["Manager ID"]]["Full Name"].iloc[0] for _, r in e.iterrows() if isinstance(r["Manager ID"], str)}
    o["join"] = {r["Full Name"]: str(r["Join Date"])[:10] for _, r in e.iterrows()}
    o["loc"] = {r["Full Name"]: r["Location"] for _, r in e.iterrows()}
    o["agents_n"] = int(e["Department"].isin(["Engineering", "Finance", "People & Ops", "Marketing"]).sum())
    j = _x("Jira_Export_ATLAS.xlsx", "Issues")
    j = j[j["Key"].astype(str).str.startswith("ATLAS-")]
    done = j["Status"] == "Done"
    o.update(jira_total=len(j), jira_done=int(done.sum()), jira_open=int((~done).sum()), jira_pts=int(j[~done]["Story Points"].sum()),
             jira_inprog=int((j["Status"] == "In Progress").sum()), jira_todo=int((j["Status"] == "To Do").sum()))
    o["by"] = {a: (int(len(g)), int(g["Story Points"].sum())) for a, g in j[~done].groupby("Assignee")}
    v = pd.read_excel(_f("Jira_Export_ATLAS.xlsx"), sheet_name="Versions").iloc[0]
    o.update(ga_orig=str(v["Original Release Date"])[:10], ga_new=str(v["Release Date"])[:10], ga_changed=str(v["Last Changed"])[:10], ga_by=v["Changed By"])
    i = _x("Incidents_Aug-Oct_2026.xlsx")
    s1 = i[i["Severity"] == "SEV1"]
    o.update(inc_n=len(i), sev1_n=len(s1), sev1_aug=int((pd.to_datetime(s1["Opened"]).dt.month == 8).sum()), sev1_ids=list(s1["ID"]))
    p = _x("Pulse_Survey.xlsx")
    o["pulse"] = {t: float(p[(p["Team"] == t) & (p["Quarter"] == "Jul-Sep 2026")]["Engagement (1-5)"].iloc[0]) for t in p["Team"].unique()}
    g = _x("GL_Export_Apr-Sep_2026.xlsx")
    mk = g[g["Cost Centre"].astype(str).str.startswith("MKT")]
    o.update(mkt_total=int(mk["Amount (Rs.)"].sum()), mkt_evt=int(mk[mk["Cost Centre"] == "MKT-EVT"]["Amount (Rs.)"].sum()),
             mkt_ps=int(mk[mk["Cost Centre"] == "MKT-PS"]["Amount (Rs.)"].sum()))
    o["gl_cc"] = {k: int(v) for k, v in g.groupby("Cost Centre")["Amount (Rs.)"].sum().items()}
    o["pay_sep"] = int(g[g["Voucher"] == "PAY-SEP"]["Amount (Rs.)"].iloc[0])
    pr = _x("Payroll_Register_Jan-Mar_2026.xlsx")
    feb = pr[(pr["Emp ID"] == "VX018") & (pr["Month"] == "Feb-2026")].iloc[0]
    o.update(rahul_days_payable=int(feb["Days Payable"]), rahul_days_month=int(feb["Days in Month"]), feb_processor=feb["Processed By"])
    # every salary figure in the register: used ONLY to detect leakage in answers
    o["salary_values"] = {str(int(v)) for c in ("Gross (Rs.)", "Deductions (Rs.)", "Net (Rs.)") for v in pr[c].dropna()}
    h = _x("Hiring_Tracker.xlsx")
    o["held"] = sorted(h[h["Status"] == "On hold"]["Req ID"]); o["open_reqs"] = sorted(h[h["Status"] == "Open"]["Req ID"])
    gl = pd.read_csv(_f("git_log.csv"))
    o["commits"] = {k: int(v) for k, v in gl["author_email"].value_counts().items()}
    return o


_CACHE: dict | None = None


def O() -> dict:  # noqa: N802
    global _CACHE
    if _CACHE is None:
        _CACHE = build()
    return _CACHE
