# Data-room audit

This audit is derived from the exact files in `data/Veloxa_Hackathon_Release_Packs.zip` and the extracted folders under `data/raw/`.

## Inventory and ingestion

- ZIP archive entries: 65 (including directories).
- Supported source files ingested: 41.
- Evidence units generated: 366.
- Evidence-index rows exported for the CEO-facing index: 309.
- Individual payroll-register row evidence is deliberately excluded from the CEO-facing evidence index and retrieval surface because T2 says individual salaries must never appear in anything Ananya sees.
- Source release boundaries are recorded in `veloxa/config.py`.

## Employee scope

Employee Master has 19 employee rows. The hackathon's 14-agent requirement names Engineering, Finance, HR/People and Marketing. The 14 agents are derived from those departments:

| Department | Count | Employee IDs |
|---|---:|---|
| Engineering | 5 | VX004, VX007, VX009, VX012, VX018 |
| Finance | 3 | VX003, VX010, VX014 |
| People & Ops | 3 | VX005, VX015, VX017 |
| Marketing | 3 | VX006, VX011, VX013 |

The five remaining master records are Leadership (Ananya Rao), Sales (Manoj Kumar, Divya Reddy) and Support (Imran Siddiqui, Kavya Narayan). They remain in the company model but are outside the 14-agent scope.

## Key source-derived facts

| Topic | Source-supported fact | Caveat |
|---|---|---|
| Headcount | Employee Master has 19 rows; both board updates report team 19. | Candidate Brief says 180; Keka export excludes contractors. Do not claim the employee export proves all workers. |
| Latest ARR | ₹6.1 Cr, Jul–Sep 2026 board update. | T1/T2 transcript numbers are ambiguous or inconsistent. |
| Latest burn | ₹44 lakh/month, Jul–Sep 2026 board update. | T1/T2 transcript wording conflicts materially. |
| Runway | 13 months, Jul–Sep board update. | Board-reported, not recalculated from selected GL. |
| Customers | 66, Jul–Sep board update. | No customer-level export supplied. |
| Marketing GL | ₹14,26,620 across MKT-EVT and MKT-PS in the selected Apr–Sep GL. | Selected cost centres only; not necessarily total marketing spend. T4's “one point eight” is underspecified. |
| Atlas dates | Original GA 15 Sep 2026; revised GA 15 Dec 2026; last changed 2 Sep by vikram. | Jira export is released Day 3; board updates already describe the move in Day 1. |
| Jira status | 62 issues: 35 Done, 8 In Progress, 19 To Do; 27 unresolved. | Story points are not calendar duration. |
| Priya Jira work | Assignee PN has 14 unresolved issues and 62 story points. | “Pria” identity is likely Priya Nair, but alias mapping remains documented. |
| Incidents | 11 incidents; 3 SEV1, all opened in August. | Responder labels include Sneha and Snehal. |
| Pulse | Jul–Sep Engineering 3.1/5; Finance 3.9; People & Ops 4.1; Marketing 3.4. | Small-team comments are withheld by the source export. |
| Hiring | REQ-014 and REQ-015 On hold; REQ-016 and REQ-017 Open. | Export is as of 31 Oct. |
| Siddharth | Resignation letter dated 15 Sep; last working day 31 Oct; Employee Master has notice-period status and exit date. | Treat as historical employee in agent interface. |
| Priya resignation | T6d reports “Pria resigned”; two-month notice is qualified by “I think”. | No matching HR resignation record in 31 Oct Employee Master. Pending confirmation. |

## Data not supplied

No Slack export, HubSpot export, LinkedIn campaign export, Confluence postmortem export, formal CRO org-change approval, or formal Priya resignation letter is included. The system must not pretend these records exist.
