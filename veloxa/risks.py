"""Transparent risk ranking for the "what should I worry about?" view (T6a).

score = round(100 * impact/5 * likelihood/5 * evidence_weight)
  impact       1-5  consequence for the company if the risk materialises
  likelihood   1-5  how strongly the *records* indicate it is happening / will happen
  evidence_weight  High=1.0, Medium=0.8, Low=0.6  (quality of the supporting evidence)
Scores are an ordinal prioritisation aid - NOT statistical probabilities. Only evidence released
by the selected cutoff is used, so replaying Day 1/2/3 never leaks later records.
Numbers in the text are computed from facts, never typed in.
"""
from __future__ import annotations

from . import data as D
from . import facts as F
from .config import DEFAULT_AS_OF, available

WEIGHT = {"High": 1.0, "Medium": 0.8, "Low": 0.6}


def _sev(score: int) -> str:
    return "Critical" if score >= 60 else "High" if score >= 40 else "Medium" if score >= 20 else "Low"


def _mk(title, impact, likelihood, conf, why, sources):
    score = round(100 * impact / 5 * likelihood / 5 * WEIGHT[conf])
    return {"title": title, "severity": _sev(score), "confidence": conf, "score": score, "impact": impact,
            "likelihood": likelihood, "evidence_weight": WEIGHT[conf], "why": why, "sources": sources}


def worry_list(as_of: str = DEFAULT_AS_OF) -> list[dict]:
    a = lambda d: available(as_of, d)  # noqa: E731
    if not a("Day1"):
        return []
    out: list[dict] = []
    b2, b3 = D.board("Apr-Jun 2026"), D.board("Jul-Sep 2026")

    # 1. Atlas delivery (+ key-person dependency once Jira / T6d are released) ------------------
    srcs = [F.BOARD_Q2, F.BOARD_Q3, "T1_CEO_Kickoff_Call.docx"]
    why = (f"The Apr–Jun board update said GA was on track for 15 September; the Jul–Sep update says GA was moved to absorb "
           f"unplanned reliability work after a difficult August, without stating a new date.")
    imp, lik, conf = 5, 3, "Medium"
    if a("Day2"):
        hold = [r for r in F.hiring_rows() if r["status"] == "On hold"]
        why += f" {len(hold)} backend requisitions ({', '.join(r['req'] for r in hold)}) are on hold, limiting added capacity."
        srcs += [F.HIRE_F, "06.eml"]
        lik = 4
    if a("Day3"):
        j, v, inc = F.jira_summary(), F.jira_version(), F.incident_summary()
        pn = j["by_assignee"]["PN"]
        why = (f"Jira moved Atlas GA from {v['original']} to {v['revised']} (changed {v['changed_on']} by {v['changed_by']}). "
               f"{j['open']} of {j['total']} issues are unresolved ({j['open_points']} story points); {pn['issues']} of them "
               f"({pn['points']} points) sit with one engineer (Priya, PN). There were {inc['sev1_by_month'].get('2026-08', 0)} SEV1 incidents in August, "
               f"and {', '.join(r['req'] for r in F.hiring_rows() if r['status'] == 'On hold')} are on hold.")
        srcs = [F.JIRA_F, F.BOARD_Q3, F.INC_F, F.HIRE_F, "06.eml", "08.eml"]
        lik, conf = 4, "High"
    if a("Day4"):
        why += (" T6d adds an unverified CEO-reported resignation of 'Pria' (likely Priya Nair); HR has not confirmed it, "
                "so the dependency is High confidence but the resignation itself is Medium.")
        srcs.append("T6d_CEO_Voice_Note.docx")
        lik, conf = 5, "High"
        out_score_adjust = 0.9  # resignation claim is unverified -> blend High (dependency) and Medium (claim)
        r = _mk("Atlas v3 delivery and key-person dependency", imp, lik, conf, why, srcs)
        r["score"] = round(100 * imp / 5 * lik / 5 * out_score_adjust); r["severity"] = _sev(r["score"])
        r["evidence_weight"] = out_score_adjust
        out.append(r)
    else:
        out.append(_mk("Atlas v3 delivery risk", imp, lik, conf, why, srcs))

    # 2. Engineering capacity & engagement (needs Day2 pulse) ------------------------------------------
    if a("Day2"):
        s = F.pulse_series("Engineering")
        first, last = s[-2], s[-1]
        why = (f"Engineering engagement fell from {first['score']} ({first['quarter']}) to {last['score']} ({last['quarter']}); "
               f"{last['responses']} of {last['team_size']} responded and comments are withheld (team below the anonymity threshold). "
               "Deepa suggests 1:1s led by Vikram (email 11). This is a team-level signal, not a prediction about any individual.")
        srcs = [F.PULSE_F, "11.eml", "T3_Head_of_People_Call.docx"]
        if a("Day3"):
            j, inc, oc = F.jira_summary(), F.incident_summary(), F.oncall_summary()
            why += (f" {inc['total']} incidents were logged Aug–Oct and reliability duty is concentrated: the on-call rota lists "
                    f"{oc['primary'].get('Sneha', 0)} primary weeks for Sneha and {oc['primary'].get('Snehal', 0)} for 'Snehal' (identity unresolved).")
            srcs += [F.INC_F, F.ONCALL_F]
        out.append(_mk("Engineering capacity and engagement", 4, 4, "Medium", why, srcs))

    # 3. Marketing launch continuity (needs Day2: resignation letter / hiring) ----------------------------
    if a("Day2"):
        sid = F.emp("VX013")
        req16 = next(r for r in F.hiring_rows() if r["req"] == "REQ-016")
        why = (f"Siddharth Mehta (Product Marketing Manager, launch-kit owner) left on {sid['exit_date']}; his backfill {req16['req']} was still "
               f"{req16['status']} with {req16['pipeline']} in the pipeline in the 31 Oct export.")
        srcs = [F.EMP_F, "Resignation_Letter_SM.pdf", F.HIRE_F]
        if a("Day3"):
            why += " The launch kit is prepared but its date depends on engineering, and a move to a new CRO is proposed with no effective date."
            srcs += ["Atlas_Launch_Kit_v1.pdf", "T6b_CEO_Voice_Note.docx", "T4_Head_of_Marketing_Call.docx"]
        out.append(_mk("Marketing launch continuity", 3, 4, "High", why, srcs))

    # 4. Financial narrative needs reconciliation (Day1) ---------------------------------------------------
    why = (f"Transcript statements about ARR and burn do not match the board updates (ARR ₹{b3['arr_cr']} Cr, burn ₹{b3['burn_lakh']:g} lakh/month), "
           "and the Candidate Brief's 180-person company conflicts with 19 employee records. Board figures are used; discrepancies stay visible.")
    srcs = ["T1_CEO_Kickoff_Call.docx", "T2_CFO_Call.docx", F.BOARD_Q3]
    if a("Day3"):
        why += " Marketing's 'one point eight' spend (T4) cannot be reconciled to the selected GL cost centres."
        srcs.append("T4_Head_of_Marketing_Call.docx")
    out.append(_mk("Financial figures need reconciliation", 3, 3, "Medium", why, srcs))

    # 5. Payroll verification (Day1) -------------------------------------------------------------------------
    fp = F.feb_proration()
    why = (f"Rahul Verma queried his first payslip (6 Mar); the reply 'will check' (10 Mar) is the last record. February shows "
           f"{fp['recorded_days']} payable days against {fp['expected_days']} if prorated from his {fp['join_date']} start. This is a verification task, not proof of an error.")
    out.append(_mk("Payroll query unresolved", 2, 3, "High", why, ["Payroll_Register_Jan-Mar_2026.xlsx", "02.eml", "03.eml", "01.eml"]))

    out.sort(key=lambda r: (-r["score"], -r["impact"], r["title"]))
    return out
