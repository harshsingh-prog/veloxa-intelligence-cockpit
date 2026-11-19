"""People helpers. Employee data comes from facts.py (single parsing path); only the *fictional* persona lines live here."""
import pandas as pd
from . import facts as F

DEPT_ORDER = F.DEPT_ORDER
# FICTIONAL persona details - every one is logged in ASSUMPTIONS.md and is never evidence about the real employee.
PERSONA_ASSUMPTIONS = {
 'VX004': ('Keeps a small paper notebook for architecture decisions.', 'Fictional persona detail; not an employee-record fact.'),
 'VX007': ('Prefers written design notes before high-risk code changes.', 'Fictional persona detail; not an employee-record fact.'),
 'VX009': ('Enjoys sketching interface flows away from the screen.', 'Fictional persona detail; not an employee-record fact.'),
 'VX012': ('Likes quiet early-morning focus time.', 'Fictional persona detail; not an employee-record fact.'),
 'VX018': ('Enjoys solving logic puzzles outside work.', 'Fictional persona detail; not an employee-record fact.'),
 'VX003': ('Prefers concise, reconciled numbers over narrative-only updates.', 'Fictional persona detail; not an employee-record fact.'),
 'VX010': ('Keeps a personal checklist for month-end close.', 'Fictional persona detail; not an employee-record fact.'),
 'VX014': ('Enjoys cooking new recipes on weekends.', 'Fictional persona detail; not an employee-record fact.'),
 'VX005': ('Values clear, documented people processes.', 'Fictional persona detail; not an employee-record fact.'),
 'VX015': ('Likes keeping a tidy recruitment pipeline.', 'Fictional persona detail; not an employee-record fact.'),
 'VX017': ('Enjoys gardening as a screen-free hobby.', 'Fictional persona detail; not an employee-record fact.'),
 'VX006': ('Collects examples of strong product-launch messaging.', 'Fictional persona detail; not an employee-record fact.'),
 'VX011': ('Enjoys experimenting with campaign measurement dashboards.', 'Fictional persona detail; not an employee-record fact.'),
 'VX013': ('Likes turning complex product details into simple customer stories.', 'Fictional persona detail; not an employee-record fact.'),
}

def employee_master() -> pd.DataFrame:
    """Original Employee Master column names, for the UI."""
    e = F.employees()
    return pd.DataFrame({'Emp ID': e['emp_id'], 'Full Name': e['name'], 'Work Email': e['email'], 'Department': e['dept'], 'Title': e['title'],
                         'Manager ID': e['manager_id'], 'Join Date': e['join_date'], 'Location': e['location'], 'Status': e['status'], 'Exit Date': e['exit_date']})

def target_agents() -> list[dict]:
    out = []
    for r in F.agents_roster():
        detail, basis = PERSONA_ASSUMPTIONS[r['emp_id']]
        out.append({'emp_id': r['emp_id'], 'name': r['name'], 'email': r['email'], 'department': r['dept'], 'title': r['title'],
                    'manager_id': r['manager_id'], 'join_date': r['join_date'], 'location': r['location'], 'status': r['status'],
                    'exit_date': r['exit_date'], 'personal_life_assumption': detail, 'assumption_basis': basis})
    return out
