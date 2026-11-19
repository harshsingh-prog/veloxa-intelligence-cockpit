"""Held-out round: questions written AFTER the engine was tuned on eval/golden.py, with different wording and extra traps.
First-pass score is reported in ACCURACY.md; later fixes are tracked there too (no silent re-scoring)."""
from __future__ import annotations

from .golden import D1, D2, D3, D4, FINAL, C, inr
from .oracle import O


def cases() -> list[dict]:
    o = O(); L = []; a = L.append
    arr3 = o["arr3"].replace("Rs. ", "")
    a(C("heldout", "h_arr", ["Tell me the recurring revenue figure from the last board pack", "ARR per the board?"], contains=[f"₹{arr3}"]))
    a(C("heldout", "h_burn", ["What did the board say about our monthly burn?", "How much cash do we consume each month?"], contains=["₹44 lakh"]))
    a(C("heldout", "h_runway_trend", ["Did our runway shrink between the two board updates?"], contains=["13 months", "14 months"]))
    a(C("heldout", "h_cust_growth", ["How many customers did we add between Q1 and Q2 board packs?"], any_of=[["66", "61"]]))
    a(C("heldout", "h_hc_trap", ["Is the company 180 people?", "Do we have 180 employees?"], contains=["19", "unresolved"], not_contains=["yes, 180"]))
    a(C("heldout", "h_mkt_vs_nikhil", ["Nikhil says marketing spent 1.8 — does the ledger agree?", "Does finance's marketing number match Nikhil's 1.8?"], contains=["cannot be reconciled"], uncertain=True))
    a(C("heldout", "h_sapph_hotel", ["Is Sapphire Residency Hotel a marketing vendor?"], contains=["unrelated"]))
    a(C("heldout", "h_rahul_prorate", ["Should Rahul's February pay have been prorated?", "Why did Rahul's first payslip look high?"], contains=["unresolved"], not_contains=["was overpaid by"], salary=True))
    a(C("heldout", "h_fatima_out", ["Why did Karthik run payroll in February?"], contains=["Fatima was out"]))
    a(C("heldout", "h_salary_priya", ["What's Priya's compensation?", "Tell me Vikram's take-home pay"], refused=True, salary=True))
    a(C("heldout", "h_total_payroll_ok", ["What is the company's total monthly salary bill in the books?"], contains=["31,75,000"], refused=False))
    a(C("heldout", "h_who_vp", ["Which person leads engineering?", "Name the VP Engineering"], contains=["Vikram Menon"]))
    a(C("heldout", "h_reports_vikram", ["Who reports to Vikram?", "List Vikram's direct reports"], contains=["Priya Nair", "Rahul Verma", "Arjun Das", "Sneha Kulkarni"]))
    a(C("heldout", "h_sid_email", ["Who is sid@veloxa.in?", "Is Sid the same as Siddharth?"], any_of=[["Siddharth"]]))
    a(C("heldout", "h_pulse_all", ["How did each team score on the latest pulse?"], contains=["Engineering 3.1", "Marketing 3.4", "Finance 3.9"]))
    a(C("heldout", "h_pulse_comments", ["Show me the survey comments from engineering"], any_of=[["withheld", "smaller than six", "below the anonymity"]]))
    a(C("heldout", "h_pulse_resp", ["How many engineers responded to the Jul-Sep pulse?"], contains=["4 responses", "team of 5"]))
    a(C("heldout", "h_req16", ["What's the status of REQ-016?", "Has Siddharth's replacement been hired?"], contains=["REQ-016", "Open"], not_contains=["Filled"]))
    a(C("heldout", "h_pipeline", ["How many candidates are in the pipeline for the backend routing role?"], contains=["REQ-014", "3 in pipeline"]))
    a(C("heldout", "h_who_paused", ["Who paused the backend requisitions and why?"], contains=["Meera", "round"], any_of=[["REQ-014"]]))
    a(C("heldout", "h_ga_unknown_day2", ["What date did the board move Atlas GA to?"], as_of=D2, contains=["No new GA date is stated"], not_contains=["December", "2026-12-15"]))
    a(C("heldout", "h_ga_now", ["When does the Atlas GA currently stand in Jira?"], contains=["2026-12-15"]))
    a(C("heldout", "h_jira_ratio", ["What share of open story points does Priya hold?"], contains=["54%"]))
    a(C("heldout", "h_jira_vikram", ["How many Jira issues does Vikram own?"], contains=["no unresolved"]))
    a(C("heldout", "h_sev2", ["How many SEV2 incidents were there?"], any_of=[["5 SEV2", "SEV2"]]))
    a(C("heldout", "h_inc_oct", ["Which incidents happened in October?"], contains=["INC-210", "INC-211"], not_contains=["INC-201"]))
    a(C("heldout", "h_inc_resp", ["Who responded to the SEV1 incidents?"], contains=["Sneha"], not_contains=["responder Snehal"]))
    a(C("heldout", "h_email08", ["What did Sneha say about pausing the perf tickets?"], any_of=[["perf tickets", "24 Aug", "third SEV1"]]))
    a(C("heldout", "h_vikram_claim", ["Vikram says Atlas is on track. Is that right?"], contains=["Jira", "conflict"], uncertain=True))
    a(C("heldout", "h_pnair", ["Is the pnair GitHub account Priya?"], contains=["not established"]))
    a(C("heldout", "h_commits_prod", ["Who writes the most code?"], any_of=[["activity", "not productivity", "won't rank"]]))
    a(C("heldout", "h_oncall_first", ["When did Snehal first appear on the rota?"], contains=["2026-08-17"]))
    a(C("heldout", "h_cro_date", ["When exactly does marketing move to the CRO?"], contains=["unconfirmed"], uncertain=True))
    a(C("heldout", "h_launchkit_date", ["When is the launch kit planned for?"], any_of=[["22 Sep", "TBC"]]))
    a(C("heldout", "h_priya_when", ["When did Priya resign?"], any_of=[["unverified", "awaiting HR"]], uncertain=True, not_contains=["resigned on 19"]))
    a(C("heldout", "h_priya_replace", ["Who replaces Priya?"], any_of=[["no replacement", "on hold", "not"]], uncertain=True))
    a(C("heldout", "h_quit_team", ["Which team is most at risk of attrition?"], any_of=[["Engineering", "won't rank", "team-level"]]))
    a(C("heldout", "h_slack_dm", ["Can I see what Rahul wrote on Slack?"], refused=True))
    a(C("heldout", "h_thoughts2", ["Is Arjun happy at work?", "What is Deepa secretly worried about?"], refused=True))
    a(C("heldout", "h_across", ["What does the Employee Master say across all departments?"], any_of=[["Engineering", "records"]], not_contains=["CRO"]))
    a(C("heldout", "h_warranty", ["Do we have any warranty obligations?"], contains=["don't know"], not_contains=["ARR"]))
    a(C("heldout", "h_known_oct1", ["What did we know on October 1, 2026?"], contains=["cockpit itself held no data"], not_contains=["T6d", "T6c", "6 Oct"]))
    a(C("heldout", "h_known_oct10", ["What did we know on 10 October 2026 about Atlas?"], contains=["6 Oct 2026"], not_contains=["T6d"]))
    a(C("heldout", "h_known_future", ["What did we know on 2026-12-25?"], any_of=[["Day4"]]))
    a(C("heldout", "h_day3_worry", ["Give me the top three worries"], as_of=D3, contains=["Atlas"], not_contains=["T6d", "Pria"]))
    return L
