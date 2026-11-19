"""14 interviewable colleagues on ONE shared, grounded framework.

An agent never invents work facts. Every answer is assembled from per-person *statements* computed from the
data room (Employee Master, Jira, incidents, hiring, GL, emails, transcripts), filtered by release day.
Persona colour (hobbies etc.) is fictional, labelled as such and logged in ASSUMPTIONS.md. A language model may
only re-phrase the verified answer in the person's voice, and only if guard.check() passes.
"""
from __future__ import annotations

import os
import re

from . import data as D
from . import facts as F
from .config import DEFAULT_AS_OF, available
from .data import fmt_inr, lakh
from .intents import has, norm
from .people import target_agents

S = F.src
JIRA_ASSIGNEE_BY_EMPLOYEE = {v: k for k, v in F.JIRA_ASSIGNEE.items()}  # kept for backwards compatibility (emp_id -> initials)
JIRA_ASSIGNEE_BY_EMPLOYEE = {emp: ini for ini, emp in F.JIRA_ASSIGNEE.items()}


def _st(topic, day, text, *sources):
    return {"topic": topic, "day": day, "text": text, "sources": list(sources)}


def _first(emp_id):
    return F.emp(emp_id)["name"].split()[0]


def statements(emp_id: str) -> list[dict]:
    """All record-backed first-person statements for this person (release-gated later)."""
    e = F.emp(emp_id)
    out = [
        _st("identity", "Day1", f"I'm {e['name']}, {e['title']} in {e['dept']} (employee ID {emp_id}). I joined on {e['join_date']} and I'm based in {e['location']}.",
            S(F.EMP_F, f"row {int(e['_row'])}")),
        _st("manager", "Day1", f"I report to {F.emp_name(e['manager_id'])}." if e["manager_id"] else "I'm the CEO, so I report to no one.", S(F.EMP_F, f"row {int(e['_row'])}")),
    ]
    reports = F.employees()[F.employees()["manager_id"] == emp_id]
    if len(reports):
        out.append(_st("team", "Day1", "My direct reports are " + ", ".join(f"{r['name']} ({r['title']})" for _, r in reports.iterrows()) + ".", S(F.EMP_F, "Manager ID column")))
    j = F.jira_for(emp_id)
    if j:
        epics = F.epic_names()
        out.append(_st("work", "Day3",
                       f"In the Atlas Jira export I have {j['issues']} unresolved issues ({j['points']} story points) and {j['done']} completed, across: " +
                       ", ".join(epics.get(k, k) for k in j["epics"]) + ". Story points are estimates of assigned work, not my productivity or remaining days.",
                       S(F.JIRA_F, f"Issues sheet; assignee {j['initials']}; keys {', '.join(j['keys'])}")))
        out.append(_st("workload", "Day3", f"My open load is {j['issues']} issues / {j['points']} points out of {F.jira_summary()['open']} issues / {F.jira_summary()['open_points']} points unresolved across Atlas.",
                       S(F.JIRA_F, "Issues sheet")))
    cs = F.commit_summary()["by_author"]
    if e["email"] in cs:
        extra = " (a separate GitHub noreply alias also exists; the records don't establish it's mine, so it isn't counted)" if emp_id == "VX007" else ""
        out.append(_st("work", "Day3", f"My work email shows {cs[e['email']]} commits in the repository export{extra}; that is recorded activity, not a measure of how well I'm doing.", S("git_log.csv", "author_email")))
    inc = F.incidents()
    mine = inc[inc["Responder"] == e["name"].split()[0]]
    if emp_id in ("VX012", "VX009") and len(mine):
        sev = mine["Severity"].value_counts().to_dict()
        out.append(_st("incident", "Day3", f"I'm the recorded responder on {len(mine)} incidents (" + ", ".join(f"{n} {k}" for k, n in sorted(sev.items())) + ")." +
                       (" All three August SEV1s on routing-api list me." if sev.get("SEV1") == 3 else ""), F.incident_summary()["source"]))
    o = F.oncall()
    fn = e["name"].split()[0]
    pw, sw = int((o["Primary"] == fn).sum()), int((o["Secondary"] == fn).sum())
    if pw + sw and emp_id in ("VX012", "VX007", "VX009"):
        out.append(_st("incident", "Day3", f"On the on-call rota I'm primary for {pw} weeks and secondary for {sw}.", F.oncall_summary()["source"]))

    # ---- person-specific, record-backed material -------------------------------------------------
    if emp_id == "VX004":
        out += [_st("hiring", "Day2", "I'm hiring manager on the backend requisitions. Meera paused REQ-014 and REQ-015 on 12 Aug until the round closes, and I replied “Understood. We'll absorb it.”",
                    S("06.eml", "12 Aug"), S("07.eml", "12 Aug"), S(F.HIRE_F, "REQ-014, REQ-015")),
                _st("work", "Day3", "My 2 Jun Atlas plan: Priya leads the core engine and re-routing, Rahul the API, Arjun the UI, Sneha hardening; 15 Sep GA was achievable only if the two backend hires landed by July.", S("04.eml", "2 Jun")),
                _st("work", "Day3", f"Jira records the Atlas GA date being moved from {F.jira_version()['original']} to {F.jira_version()['revised']} on {F.jira_version()['changed_on']} by “vikram”.", F.jira_version()["source"])]
    if emp_id == "VX007":
        out += [_st("work", "Day3", "Vikram's plan has me leading the core routing engine and re-routing.", S("04.eml", "2 Jun")),
                _st("work", "Day3", "On 1 Sep I emailed Vikram asking for time that week to talk about Atlas ownership; the records don't say what we discussed.", S("09.eml", "1 Sep"))]
    if emp_id == "VX009":
        out.append(_st("location", "Day2", "On 18 Sep I asked Deepa to make remote working from Pune permanent, offering to come to Bengaluru once a month; no decision is recorded.", S("10.eml", "18 Sep")))
    if emp_id == "VX012":
        out.append(_st("incident", "Day3", "My 24 Aug email to Vikram says it was the third SEV1 that month, that I was pausing the Atlas perf tickets to stabilise routing-api, and that a contractor starts on the rota that week. "
                       "I can't say whether “Snehal” on the rota is that contractor — the records don't link them.", S("08.eml", "24 Aug")))
    if emp_id == "VX018":
        fp = F.feb_proration()
        out.append(_st("payroll", "Day1", f"I joined on 3 Feb and asked Fatima on 6 Mar whether my first payslip looked right for a partial month; her 10 Mar reply was “Will check and get back”. "
                       f"I don't see a resolution in the records. The register shows {fp['recorded_days']} payable days for February against {fp['expected_days']} if prorated from my start date; whether that is wrong depends on payroll policy.",
                       S("02.eml", "6 Mar"), S("03.eml", "10 Mar"), S("Payroll_Register_Jan-Mar_2026.xlsx", "days fields only")))
    if emp_id == "VX003":
        out += [_st("finance", "Day2", "On 12 Aug I told Vikram I was pausing REQ-014 and REQ-015 until the round closes because burn is the priority this quarter.", S("06.eml", "12 Aug")),
                _st("finance", "Day1", f"The latest board figures: ARR ₹{D.board('Jul-Sep 2026')['arr_cr']} Cr, burn ₹{D.board('Jul-Sep 2026')['burn_lakh']:g} lakh a month, runway {D.board('Jul-Sep 2026')['runway_months']} months. Individual salaries never go to the CEO — only totals.",
                    S(F.BOARD_Q3, "Key numbers"), S("T2_CFO_Call.docx", "salary confidentiality"))]
    if emp_id == "VX010":
        out.append(_st("finance", "Day1", "I ran February payroll on 28 Feb because Fatima was out, using the January sheet and adding the new joiner (register “KS”).", S("01.eml", "28 Feb"), S("Payroll_Register_Jan-Mar_2026.xlsx", "Processed By")))
    if emp_id == "VX014":
        g = F.gl()
        n_fs = int((g["Entered By"] == "FS").sum())
        out += [_st("finance", "Day1", f"I'm recorded as entering {n_fs} of the {len(g)} GL postings in the Apr–Sep export, and I processed the January and March payroll runs (“FS”).", S(F.GL_F, "Entered By column")),
                _st("payroll", "Day1", "Rahul asked me about his first payslip on 6 Mar and I replied on 10 Mar “Will check and get back”; no later record shows the outcome.", S("02.eml", "6 Mar"), S("03.eml", "10 Mar"))]
        lv = F.leave_for("F. Sheikh")
        if lv:
            out.append(_st("finance", "Day2", f"I was on leave from {lv[0]['from']} to {lv[0]['to']}, which is why Karthik ran February payroll.", S(F.LEAVE_F, f"row {lv[0]['row']}"), S("01.eml", "28 Feb")))
    if emp_id == "VX005":
        out += [_st("people", "Day2", "On 29 Sep I told Ananya the engineering pulse dropped and that the team is too small for me to share comments, and I suggested Vikram do 1:1s that week.", S("11.eml", "29 Sep")),
                _st("people", "Day2", "Arjun asked me on 18 Sep to make remote working permanent; no decision is recorded in the records I can see.", S("10.eml", "18 Sep"))]
        s = F.pulse_series("Engineering")
        out.append(_st("people", "Day2", f"Engineering engagement went from {s[-2]['score']:g} to {s[-1]['score']:g} (Jul–Sep; {s[-1]['responses']} of {s[-1]['team_size']} responded).", S(F.PULSE_F, "Engineering rows")))
    if emp_id == "VX015":
        rows = F.hiring_rows()
        out.append(_st("hiring", "Day2", "The 31 Oct hiring export shows: " + "; ".join(f"{r['req']} {r['role']} — {r['status']}, {r['pipeline']} in pipeline" for r in rows) + ".", S(F.HIRE_F, "Requisitions sheet")))
    if emp_id == "VX017":
        out.append(_st("people", "Day2", "Deepa describes me as handling exits, so Siddharth's departure (last day 31 Oct) falls in my area.", S("T3_Head_of_People_Call.docx", "summary"), S(F.EMP_F, "VX013 row")))
    if emp_id == "VX006":
        m = F.marketing_ledger()
        out += [_st("marketing", "Day1", f"The GL shows ₹{lakh(m['total'], 4)} lakh across the two marketing cost centres (selected cost centres only). My own “one point eight” has no unit or scope in the call summary, so it hasn't been reconciled.", m["source"], S("T4_Head_of_Marketing_Call.docx", "summary")),
                _st("hiring", "Day2", "I'm hiring manager for REQ-016, the Product Marketing Manager backfill; it was Open with 7 in the pipeline in the 31 Oct export.", S(F.HIRE_F, "REQ-016")),
                _st("marketing", "Day3", "I've heard marketing will report to a new CRO but I have no date; the CEO's note says next month or the month after, still finalising.", S("T4_Head_of_Marketing_Call.docx", "summary"), S("T6b_CEO_Voice_Note.docx", "transcript"))]
    if emp_id == "VX011":
        m = F.marketing_ledger()
        out.append(_st("marketing", "Day1", f"Paid search (MKT-PS) is ₹{lakh(m['paid_search'], 4)} lakh across {len([l for l in m['lines'] if l['cc'] == 'MKT-PS'])} Google Ads postings in the Apr–Sep GL.", m["source"]))
        out.append(_st("marketing", "Day3", "Nikhil says paid search is going great since I took over; I don't have a conversion export in the records to prove it either way.", S("T4_Head_of_Marketing_Call.docx", "summary")))
    if emp_id == "VX013":
        out += [_st("resign", "Day2", "I resigned by a letter dated 15 September 2026: I wanted clearer launch timelines and work that reaches customers. My last working day was 31 October 2026.", S("Resignation_Letter_SM.pdf", "page 1"), S(F.EMP_F, "VX013 row")),
                _st("marketing", "Day3", "I owned the Atlas launch kit v1 (21 Jul): deck Ready, website page Ready but unpublished, three-email sequence Ready, press note Draft; the launch date was TBC with engineering. My 22 Jul email says only a date from engineering was missing.",
                    S("Atlas_Launch_Kit_v1.pdf", "page 1"), S("05.eml", "22 Jul"))]
    return out


_TOPIC_PATTERNS = [
    ("salary", r"salary|salaries|\bpay\b|\bpaid\b|gross|\bctc\b|compensation|wage|earn|bonus|take[- ]home"),
    ("slack", r"\bslack\b|private (messages?|chats?)|\bdms?\b|direct messages?"),
    ("thoughts", r"private thoughts?|really think|real feelings?|how do you feel|are you (happy|unhappy|stressed|burnt|burned)|do you like your (job|boss|manager)|secretly|what do you think (of|about)|opinion (of|on|about)|\bfeelings?\b|morale"),
    ("quit", r"(going|planning|thinking|about|likely|intend)\w* ?(to )?(quit|resign|leave)|will you (quit|resign|leave)|are you leaving|are you resigning|did you (quit|resign)|have you resigned|your resignation|\bresign|notice period|last (working )?day|why did you leave"),
    ("personal", r"hobb(y|ies)|free time|weekend|outside (of )?work|personal life|family|fun|for fun|interests?|relax|off the clock|do you enjoy|after work|passion"),
    ("identity", r"who are you|introduce|about yourself|tell me about you|your role|what do you do|your job|your title|designation|your position|what('s| is) your name"),
    ("manager", r"manager|boss|report(s|ing)? to|who do you report|reporting line"),
    ("team", r"your team|direct reports|who works (for|with|under) you|colleagues|teammates"),
    ("incident", r"incident|sev ?[123]|on[- ]?call|pager|outage|reliab|routing-api|postmortem"),
    ("hiring", r"hiring|requisition|req-?\d|recruit|vacanc|pipeline|backfill|headcount|open role"),
    ("payroll", r"payroll|payslip|february|\bfeb\b|over-?paid|under-?paid|prorat"),
    ("finance", r"burn|runway|\barr\b|budget|\bgl\b|ledger|spend|cost|forecast|board"),
    ("marketing", r"marketing|summit|campaign|launch kit|google ads|paid search|leads?|\bcro\b|brand"),
    ("people", r"engagement|pulse|survey|attrition|remote|exit|culture"),
    ("location", r"where|location|based|remote|city|office"),
    ("join", r"when did you join|joining|tenure|how long have you|since when|start date"),
    ("workload", r"workload|overload|busy|capacity|bandwidth|how much (work|do you have)|story points?|backlog|tickets?|issues?\b|late nights?"),
    ("work", r"work(ing)? on|project|atlas|\bjira\b|responsib|assigned|priorit|current(ly)?|deliver|status|progress|commits?|routing|engine|launch"),
]


def _topics(q: str) -> list[str]:
    found = [t for t, p in _TOPIC_PATTERNS if re.search(p, q)]
    return found


class EmployeeAgent:
    def __init__(self, profile: dict, generate=None):
        self.profile, self.generate = profile, generate

    # ---------------------------------------------------------------------------------------------
    def _refusal(self, topic: str, p: dict, as_of: str):
        n = p["name"].split()[0]
        if topic == "salary":
            return ("I can't discuss individual pay. The CFO's rule is that individual salaries never appear in anything the CEO sees, and the salary columns are not even loaded into this system. "
                    "Ask for approved company-wide totals instead.", [S("T2_CFO_Call.docx", "salary confidentiality")], "refuse_salary")
        if topic == "slack":
            return ("There are no Slack or private-message records in the data room, so I have nothing to show — and I wouldn't share private messages even if there were.", [S("README.txt", "data-room inventory")], "refuse_slack")
        if topic == "thoughts":
            return (f"I don't have recorded private thoughts or opinions to report, and I won't invent any. I can tell you what the records say I did, wrote or was assigned.", [S("ASSUMPTIONS.md", "fictional persona rules")], "no_private_thoughts")
        if topic == "quit":
            if p["emp_id"] == "VX013":
                return None  # answered from the resignation statements
            t = f"I won't speculate about whether I or anyone else will leave; the records contain no resignation by me. "
            srcs = [S(F.EMP_F, "Status column")]
            if p["emp_id"] == "VX007" and available(as_of, "Day4"):
                t = ("The CEO's voice note T6d says “Pria” resigned with a notice period of “two months, I think”. The 31 Oct HR exports hold no resignation for me, so in the records this is an unverified claim awaiting HR confirmation; "
                     "I can't add to it from the data.")
                srcs = [S("T6d_CEO_Voice_Note.docx", "transcript"), S(F.EMP_F, "VX007 row")]
            return t, srcs, "quit_no_record"
        return None

    def answer(self, question: str, as_of: str = DEFAULT_AS_OF, use_llm: bool | None = None) -> dict:
        p = self.profile
        q = norm(question)
        topics = _topics(q)
        intent, sources, evidence = "grounded", [], []
        text = None
        departed = p["emp_id"] == "VX013"
        prefix = "(I left Veloxa on 31 October 2026 — this is a historical profile.) " if departed else ""

        correctness_q = "payroll" in topics and re.search(r"over-?paid|under-?paid|incorrect|wrong|error|prorat|payslip|resolved|query|issue", q) and not re.search(r"how much|amount|gross|net\b|ctc|what is your salary", q)
        for t in ("salary", "slack", "thoughts", "quit"):
            if t == "salary" and correctness_q:
                continue
            if t in topics:
                if t == "thoughts" and re.search(r"\bwhat do you think (of|about)\b.*\b(atlas|jira|process)\b", q):
                    continue
                r = self._refusal(t, p, as_of)
                if r:
                    text, sources, intent = r
                    break
        if text is None and re.search(r"\bsnehal\b", q):
            if available(as_of, "Day3"):
                o = F.oncall_summary()
                text = ("The records don't establish who “Snehal” is. The Employee Master has Sneha Kulkarni (SRE) and no Snehal; the incident export and on-call rota use both names "
                        f"(Snehal first appears in the week of {o['first_snehal_week']}); and an invoice bills Patil Infra Services for on-call SRE support by “S. Patil”. "
                        "Snehal could be that contractor, but nothing links the names, so I can't say they are the same person.")
                sources, intent = [S(F.EMP_F, "VX012 row"), o["source"], S("Invoice_PIS-114.pdf", "page 1"), S("08.eml", "24 Aug")], "grounded:identity_unresolved"
            else:
                text, intent = "I don't have records about that in the information released by this cutoff (the relevant material arrives in Day3).", "not_yet_released"
        if text is None and "personal" in topics:
            text = f"Not a record — a fictional persona detail: {p['personal_life_assumption']} (logged in ASSUMPTIONS.md; it is not a fact about the real employee)."
            sources, intent = ["ASSUMPTIONS.md"], "persona_fictional"
        if text is None:
            stm = [s for s in statements(p["emp_id"]) if available(as_of, s["day"])]
            wanted = [t for t in topics if t not in ("salary", "slack", "thoughts", "quit", "personal")]
            if "join" in wanted or "location" in wanted:
                wanted = list(dict.fromkeys(wanted + ["identity"]))
            if departed and ("resign" in q or "quit" in topics or "leave" in q or "left" in q):
                wanted = ["resign"] + wanted
            if re.search(r"\bwhat are you (working on|doing)\b|currently|right now", q):
                wanted = list(dict.fromkeys(wanted + ["work"]))
            chosen = [s for t in wanted for s in stm if s["topic"] == t]
            seen, uniq = set(), []
            for s in chosen:
                if s["text"] not in seen:
                    seen.add(s["text"]); uniq.append(s)
            if uniq:
                uniq = uniq[:4]
                text = " ".join(s["text"] for s in uniq)
                sources = list(dict.fromkeys(src for s in uniq for src in s["sources"]))
                intent = "grounded:" + ",".join(dict.fromkeys(s["topic"] for s in uniq))
            else:
                later = [s for s in statements(p["emp_id"]) if not available(as_of, s["day"]) and s["topic"] in wanted]
                if later:
                    d = min(s["day"] for s in later)
                    text, intent = f"I don't have records about that in the information released by this cutoff (the relevant material arrives in {d}).", "not_yet_released"
                elif wanted or topics or not re.search(r"\b(hi|hello|hey|introduce|who are you)\b", q):
                    from .ingestion import search_evidence
                    text, intent = "I don't have a record that answers that, and I won't guess. ", "no_record"
                    hits = [h for h in search_evidence(f"{p['name']} {question}", as_of=as_of, limit=3) if h["matched"] >= 3 and p["name"].split()[0].lower() in h["text"].lower()]
                    if hits:
                        text += "Closest records mentioning me (unverified excerpts): " + " | ".join(f"{h['file_name']} ({h['locator']}) [{h['evidence_id']}]" for h in hits)
                        sources = [f"{h['file_name']} — {h['locator']}" for h in hits]
                else:
                    ids = [s for s in stm if s["topic"] in ("identity", "manager")]
                    text = (" ".join(s["text"] for s in ids) + " Ask me about my work, workload, team, incidents, hiring or finance records — only what the records support.")
                    sources = list(dict.fromkeys(src for s in ids for src in s["sources"]))
                    intent = "grounded:identity"
        # evidence objects for the UI -----------------------------------------------------------
        if available(as_of, "Day3") and any(t in intent for t in ("work", "workload")):
            jr = F.jira()
            for _, r in jr[(jr["person"] == p["emp_id"]) & jr["is_open"]].iterrows():
                evidence.append({"evidence_id": f"JIRA-{r['Key']}", "file_name": F.JIRA_F, "relative_path": "Day3_Wed_18Nov/data_room/engineering/" + F.JIRA_F,
                                 "locator": f"Issues sheet; {r['Key']}", "release_at": "2026-11-18T10:00:00+05:30", "score": 1,
                                 "text": f"{r['Key']}: {r['Summary']}; epic {r['Epic Link']}; {r['points']} points; status {r['Status']}; created {r['Created']}; fix version {r['Fix Version']}"})
        for s_ in sources:
            evidence.append({"evidence_id": "SRC-" + re.sub(r"\W+", "-", s_)[:40], "file_name": s_.split(" — ")[0], "relative_path": "", "locator": s_.split(" — ")[-1],
                             "release_at": "", "score": 1, "text": s_})
        verified = prefix + text
        llm = {"used_llm": False, "guard_ok": True, "reasons": []}
        enabled = use_llm if use_llm is not None else os.getenv("VELOXA_LLM_POLISH", "auto").lower() not in ("0", "false", "off", "no")
        if enabled and intent not in ("not_yet_released", "no_record") and not intent.startswith("refuse"):
            from .llm import safe_rewrite
            rw = safe_rewrite(verified, "\n".join(sources), require_uncertainty=has(verified.lower(), r"can't|cannot|don't|unverified|no record|not "),
                              persona=f"Write in the first person as {p['name']}, {p['title']}, in a natural but professional voice.", generate=self.generate, limit=160)
            verified_text, llm = rw["text"], {k: rw[k] for k in ("used_llm", "guard_ok", "reasons")}
        else:
            verified_text = verified
        return {"employee": p, "response": verified_text, "verified_response": verified, "evidence": evidence, "sources": sources,
                "intent": intent, "model_used": llm["used_llm"], "llm": llm}


def all_agents(): return [EmployeeAgent(p) for p in target_agents()]
