"""Normalize selected source exports into queryable SQLite tables.

Individual payroll amounts are intentionally not normalized into a CEO-facing table.
The raw source remains retained for audit, while search/UI surfaces suppress its row-level content.
"""
from pathlib import Path
import pandas as pd
from .config import RAW_ROOT, RELEASE_BY_FOLDER
from .ingestion import connect
from .people import target_agents

TABLES={
 'employees':'CREATE TABLE IF NOT EXISTS employees (emp_id TEXT PRIMARY KEY, full_name TEXT, email TEXT, department TEXT, title TEXT, manager_id TEXT, join_date TEXT, location TEXT, status TEXT, exit_date TEXT, available_from TEXT, source_id TEXT)',
 'financial_transactions':'CREATE TABLE IF NOT EXISTS financial_transactions (voucher TEXT PRIMARY KEY, txn_date TEXT, vendor TEXT, ref TEXT, cost_centre TEXT, amount_rs REAL, narration TEXT, entered_by TEXT, available_from TEXT, source_id TEXT)',
 'jira_issues':'CREATE TABLE IF NOT EXISTS jira_issues (issue_key TEXT PRIMARY KEY, issue_type TEXT, summary TEXT, epic_link TEXT, assignee TEXT, story_points REAL, status TEXT, created TEXT, resolved TEXT, fix_version TEXT, available_from TEXT, source_id TEXT)',
 'jira_versions':'CREATE TABLE IF NOT EXISTS jira_versions (version TEXT PRIMARY KEY, release_date TEXT, original_release_date TEXT, last_changed TEXT, changed_by TEXT, available_from TEXT, source_id TEXT)',
 'incidents':'CREATE TABLE IF NOT EXISTS incidents (incident_id TEXT PRIMARY KEY, severity TEXT, opened TEXT, resolved TEXT, service TEXT, responder TEXT, available_from TEXT, source_id TEXT)',
 'pulse_scores':'CREATE TABLE IF NOT EXISTS pulse_scores (quarter TEXT, team TEXT, team_size INTEGER, responses INTEGER, engagement REAL, comments TEXT, available_from TEXT, source_id TEXT, PRIMARY KEY(quarter,team))',
 'hiring_requisitions':'CREATE TABLE IF NOT EXISTS hiring_requisitions (req_id TEXT PRIMARY KEY, role TEXT, team TEXT, hiring_manager TEXT, opened TEXT, status TEXT, status_date TEXT, pipeline INTEGER, notes TEXT, available_from TEXT, source_id TEXT)',
 'leave_records':'CREATE TABLE IF NOT EXISTS leave_records (leave_id INTEGER PRIMARY KEY AUTOINCREMENT, employee_label TEXT, leave_type TEXT, date_from TEXT, date_to TEXT, days REAL, approved_by TEXT, available_from TEXT, source_id TEXT)',
 'git_commits':'CREATE TABLE IF NOT EXISTS git_commits (sha TEXT PRIMARY KEY, author_email TEXT, committed_at TEXT, repo TEXT, message TEXT, files_changed INTEGER, available_from TEXT, source_id TEXT)',
 'oncall_assignments':'CREATE TABLE IF NOT EXISTS oncall_assignments (week_of TEXT PRIMARY KEY, primary_name TEXT, secondary_name TEXT, available_from TEXT, source_id TEXT)',
 'agent_profiles':'CREATE TABLE IF NOT EXISTS agent_profiles (emp_id TEXT PRIMARY KEY, name TEXT, department TEXT, title TEXT, personal_life_assumption TEXT, assumption_basis TEXT, available_from TEXT, source_id TEXT)',
}

def _clean(v):
    if pd.isna(v): return None
    if hasattr(v,'isoformat'): return v.isoformat()[:19]
    return v

def _frame(name, sheet=0, header=2):
    p=next(RAW_ROOT.rglob(name))
    return p,pd.read_excel(p,sheet_name=sheet,header=header)

def normalize_all():
    conn=connect(); cur=conn.cursor()
    for ddl in TABLES.values(): cur.execute(ddl)
    for table in TABLES: cur.execute(f'DELETE FROM {table}')
    src={r['relative_path']:r['source_id'] for r in conn.execute('SELECT source_id,relative_path FROM sources').fetchall()}
    def meta(p):
        rel=p.relative_to(RAW_ROOT).as_posix(); folder=rel.split('/')[0]
        return RELEASE_BY_FOLDER.get(folder,RELEASE_BY_FOLDER['Day1_Mon_16Nov']),src.get(rel)
    # Employee Master
    p,df=_frame('Employee_Master.xlsx')
    release,sid=meta(p)
    for _,r in df.iterrows():
        cur.execute('INSERT INTO employees VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',tuple(_clean(r.get(k)) for k in ['Emp ID','Full Name','Work Email','Department','Title','Manager ID','Join Date','Location','Status','Exit Date'])+(release,sid))
    # GL selected cost centres only
    p,df=_frame('GL_Export_Apr-Sep_2026.xlsx'); release,sid=meta(p)
    for _,r in df.iterrows():
        cur.execute('INSERT OR REPLACE INTO financial_transactions VALUES (?,?,?,?,?,?,?,?,?,?)',tuple(_clean(r.get(k)) for k in ['Voucher','Txn Date','Vendor / Payee','Ref','Cost Centre','Amount (Rs.)','Narration','Entered By'])+(release,sid))
    # Jira issues and release version
    p,df=_frame('Jira_Export_ATLAS.xlsx','Issues'); release,sid=meta(p)
    for _,r in df.iterrows():
        cur.execute('INSERT OR REPLACE INTO jira_issues VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',tuple(_clean(r.get(k)) for k in ['Key','Type','Summary','Epic Link','Assignee','Story Points','Status','Created','Resolved','Fix Version'])+(release,sid))
    _,dfv=_frame('Jira_Export_ATLAS.xlsx','Versions',header=0)
    for _,r in dfv.iterrows():
        cur.execute('INSERT OR REPLACE INTO jira_versions VALUES (?,?,?,?,?,?,?)',tuple(_clean(r.get(k)) for k in ['Version','Release Date','Original Release Date','Last Changed','Changed By'])+(release,sid))
    # Incidents
    p,df=_frame('Incidents_Aug-Oct_2026.xlsx'); release,sid=meta(p)
    for _,r in df.iterrows():
        cur.execute('INSERT OR REPLACE INTO incidents VALUES (?,?,?,?,?,?,?,?)',tuple(_clean(r.get(k)) for k in ['ID','Severity','Opened','Resolved','Service','Responder'])+(release,sid))
    # Pulse
    p,df=_frame('Pulse_Survey.xlsx'); release,sid=meta(p)
    for _,r in df.iterrows():
        cur.execute('INSERT OR REPLACE INTO pulse_scores VALUES (?,?,?,?,?,?,?,?)',tuple(_clean(r.get(k)) for k in ['Quarter','Team','Team size','Responses','Engagement (1-5)','Comments'])+(release,sid))
    # Hiring
    p,df=_frame('Hiring_Tracker.xlsx'); release,sid=meta(p)
    for _,r in df.iterrows():
        cur.execute('INSERT OR REPLACE INTO hiring_requisitions VALUES (?,?,?,?,?,?,?,?,?,?,?)',tuple(_clean(r.get(k)) for k in ['Req ID','Role','Team','Hiring Manager','Opened','Status','Status Date','In pipeline','Notes'])+(release,sid))
    # Leave records; initials retained as supplied, not forcibly resolved.
    p,df=_frame('Leave_Register.xlsx'); release,sid=meta(p)
    for _,r in df.iterrows():
        cur.execute('INSERT INTO leave_records (employee_label,leave_type,date_from,date_to,days,approved_by,available_from,source_id) VALUES (?,?,?,?,?,?,?,?)',tuple(_clean(r.get(k)) for k in ['Employee','Leave Type','From','To','Days','Approved By'])+(release,sid))
    # Git history
    p=next(RAW_ROOT.rglob('git_log.csv')); df=pd.read_csv(p); release,sid=meta(p)
    for _,r in df.iterrows():
        cur.execute('INSERT OR REPLACE INTO git_commits VALUES (?,?,?,?,?,?,?,?)',tuple(_clean(r.get(k)) for k in ['sha','author_email','committed_at','repo','message','files_changed'])+(release,sid))
    # On-call rota
    p,df=_frame('OnCall_Rota.xlsx'); release,sid=meta(p)
    for _,r in df.iterrows():
        cur.execute('INSERT OR REPLACE INTO oncall_assignments VALUES (?,?,?,?,?)',tuple(_clean(r.get(k)) for k in ['Week of','Primary','Secondary'])+(release,sid))
    # Agent profiles are exactly the selected employee master records.
    for a in target_agents():
        cur.execute('INSERT OR REPLACE INTO agent_profiles VALUES (?,?,?,?,?,?,?,?)',(a['emp_id'],a['name'],a['department'],a['title'],a['personal_life_assumption'],a['assumption_basis'],RELEASE_BY_FOLDER['Day1_Mon_16Nov'],src.get(next(RAW_ROOT.rglob('Employee_Master.xlsx')).relative_to(RAW_ROOT).as_posix())))
    conn.commit(); conn.close()
