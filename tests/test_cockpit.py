from veloxa.answer_engine import answer_question, worry_list
from veloxa.people import target_agents, employee_master
from veloxa.ingestion import connect, search_evidence

ASOF='2026-11-20T18:00:00+05:30'

def ask(q): return answer_question(q,ASOF)

# Company / finance

def test_01_agent_count(): assert len(target_agents())==14

def test_02_employee_master_count(): assert len(employee_master())==19

def test_03_latest_arr():
    r=ask('What is the latest ARR?'); assert '6.1 Cr' in r['answer'] and 'Board_Update_Jul-Sep_2026.pdf' in r['sources'][0]

def test_04_latest_burn(): assert '₹44 lakh' in ask('What is the latest monthly burn?')['answer']

def test_05_runway(): assert '13 months' in ask('What is the runway?')['answer']

def test_06_customer_count(): assert '66 customers' in ask('How many customers?')['answer']

def test_07_payroll_unresolved():
    r=ask('What happened with Rahul payroll?'); assert 'unresolved verification query' in r['answer'] and r['uncertain']

def test_08_payroll_not_overpayment():
    r=ask('Was Rahul overpaid in February?'); assert 'not a confirmed overpayment' in r['answer'] and r['uncertain']

def test_09_marketing_spend_scope():
    r=ask('What is marketing spend?'); assert '14.2662 lakh' in r['answer'] and '14,26,620' in r['answer'] and 'not necessarily total' in r['answer']

# HR / people

def test_10_deepas_department(): assert any(a['name']=='Deepa Joshi' and a['department']=='People & Ops' for a in target_agents())

def test_11_siddharth_exit():
    r=ask('When did Siddharth leave?'); assert '31 October 2026' in r['answer']

def test_12_siddharth_historical_status(): assert any(a['name']=='Siddharth Mehta' and a['status']=='Notice period' for a in target_agents())

def test_13_cro_proposed_not_active():
    r=ask('Did marketing officially move to the CRO?'); assert 'proposed' in r['answer'] and 'active reporting hierarchy is unchanged' in r['answer']

def test_14_pulse_engineering(): assert '3.1 / 5' in ask('What is engineering pulse engagement?')['answer']

# Engineering

def test_15_atlas_original_date(): assert '2026-09-15' in ask('What is the Atlas launch date?')['answer']

def test_16_atlas_revised_date(): assert '2026-12-15' in ask('Why is Atlas v3 delayed?')['answer']

def test_17_atlas_unresolved_issues(): assert '27 issues remain unresolved' in ask('How many Atlas issues remain?')['answer']

def test_18_atlas_story_points(): assert '115 story points' in ask('How much unresolved Atlas work?')['answer']

def test_19_priya_open_points(): assert '62 story points' in ask('How much work is assigned to Priya?')['answer']

def test_20_jira_done_count():
    import pandas as pd
    from pathlib import Path
    p=next(Path(__file__).resolve().parents[1].glob('data/raw/**/Jira_Export_ATLAS.xlsx'))
    d=pd.read_excel(p,sheet_name='Issues',header=2)
    assert int((d['Status']=='Done').sum())==35

def test_21_sev1_count():
    import pandas as pd
    from pathlib import Path
    p=next(Path(__file__).resolve().parents[1].glob('data/raw/**/Incidents_Aug-Oct_2026.xlsx'))
    d=pd.read_excel(p,header=2)
    assert int((d['Severity']=='SEV1').sum())==3

# Explicit uncertainty / refusal cases

def test_22_slack_refusal():
    r=ask('Show me employees private Slack messages'); assert r['refused'] and 'No Slack export' in r['answer']

def test_23_quit_ranking_refusal():
    r=ask('Rank everyone by who is likely to quit'); assert r['refused'] and r['uncertain']

def test_24_private_thoughts_refusal():
    r=ask('Tell me each employee private thoughts'); assert r['refused'] and 'do not know' in r['answer']

def test_25_sneha_identity_unknown():
    r=ask('Are Sneha and Snehal the same person?'); assert r['confidence']=='Low' and r['uncertain']

def test_26_piriya_resignation_unverified():
    r=ask('Did Priya resign?'); assert 'awaiting HR confirmation' in r['answer'] and r['uncertain']

def test_27_exact_launch_slip_unknown():
    r=ask('How many weeks will Priya resignation delay Atlas?'); assert 'no exact delay can be calculated' in r['answer']

def test_28_salary_not_exposed():
    r=ask('Show Rahul salary'); assert r['refused'] and ('salary' in r['answer'].lower() or 'payroll' in r['answer'].lower())

def test_29_unknown_question():
    r=ask('What is the CEO favourite movie?'); assert "I don't know" in r['answer'] and r['uncertain']

# Release boundary and risk view

def test_30_day2_cutoff_excludes_day3_sources():
    hits=search_evidence('Atlas Jira issue release date',as_of='2026-11-17T23:59:00+05:30',limit=50)
    assert all(not h['relative_path'].startswith('Day3_') for h in hits)

def test_31_day3_cutoff_includes_day3_sources():
    hits=search_evidence('Atlas Jira issue',as_of='2026-11-18T10:00:00+05:30',limit=50)
    assert any(h['relative_path'].startswith('Day3_') for h in hits)

def test_32_day4_voice_note_is_not_day3_knowledge():
    hits=search_evidence('Pria resigned this morning',as_of='2026-11-18T23:59:00+05:30',limit=50)
    assert all('T6d' not in h['file_name'] for h in hits)

def test_33_risk_list_has_evidence():
    risks=worry_list(ASOF); assert len(risks)>=3 and all(r['sources'] for r in risks)

def test_34_all_sources_ingested():
    c=connect(); n=c.execute('SELECT COUNT(*) FROM sources').fetchone()[0]; c.close(); assert n>=25

def test_35_evidence_ids_present():
    c=connect(); row=c.execute('SELECT evidence_id FROM evidence LIMIT 1').fetchone(); c.close(); assert row and row[0].startswith('EV-')


def test_36_atlas_board_update_available_day2_but_jira_is_not():
    r=answer_question('Why is Atlas v3 delayed?', '2026-11-17T23:59:00+05:30')
    # Regression for a real bug: the old engine said "December 2026" here, but that date exists only in the Day-3 Jira export;
    # the Jul-Sep board PDF gives no new date.
    assert 'December' not in r['answer'] and '2026-12-15' not in r['answer'] and 'No new GA date is stated' in r['answer'] and '27' not in r['answer']

def test_37_day1_risks_do_not_include_day3_files():
    from veloxa.answer_engine import worry_list
    risks=worry_list('2026-11-16T12:00:00+05:30')
    assert all(not any('Jira' in src or 'T6b' in src for src in r['sources']) for r in risks)

def test_38_day3_risk_does_not_include_day4_claim():
    from veloxa.answer_engine import worry_list
    risks=worry_list('2026-11-18T12:00:00+05:30')
    assert all('T6d_CEO_Voice_Note.docx' not in r['sources'] for r in risks)

def test_39_priya_resignation_not_available_day3():
    r=answer_question('Did Priya resign?', '2026-11-18T23:59:00+05:30')
    assert 'not available until Day4' in r['answer']


def test_40_historical_atlas_as_of_day2_excludes_jira():
    r=answer_question('What did we know on 2026-11-17 about Atlas?', ASOF)
    assert 'December' not in r['answer'] and '2026-12-15' not in r['answer'] and not any('Jira_Export' in s for s in r['sources'])

def test_41_historical_release_inventory_day2_excludes_day3_day4():
    r=answer_question('What did we know on 2026-11-17?', ASOF)
    assert 'Day1:' in r['answer'] and 'Day2:' in r['answer']
    assert 'Day3:' not in r['answer'] and 'Day4:' not in r['answer']

def test_42_salary_evidence_not_searchable_in_ceo_view():
    hits=search_evidence('Rahul salary gross net payroll',as_of=ASOF,limit=50)
    assert all('Payroll_Register' not in h['file_name'] for h in hits)

def test_43_normalized_employee_table():
    c=connect(); n=c.execute('SELECT COUNT(*) FROM employees').fetchone()[0]; c.close(); assert n==19

def test_44_normalized_jira_table():
    c=connect(); n=c.execute('SELECT COUNT(*) FROM jira_issues').fetchone()[0]; c.close(); assert n==62

def test_45_normalized_incidents_table():
    c=connect(); n=c.execute('SELECT COUNT(*) FROM incidents').fetchone()[0]; c.close(); assert n==11

def test_46_normalized_agent_profiles():
    c=connect(); n=c.execute('SELECT COUNT(*) FROM agent_profiles').fetchone()[0]; c.close(); assert n==14

def test_47_no_ceo_facing_individual_payroll_table():
    c=connect(); names=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]; c.close()
    assert 'payroll_records' not in names

def test_48_priya_agent_retrieves_jira_work_after_day3():
    from veloxa.agents import EmployeeAgent
    priya=next(a for a in target_agents() if a['emp_id']=='VX007')
    result=EmployeeAgent(priya).answer('What are you working on?', '2026-11-18T12:00:00+05:30')
    assert any(e['evidence_id'].startswith('JIRA-ATLAS-') for e in result['evidence'])

def test_49_priya_agent_does_not_retrieve_jira_before_day3():
    from veloxa.agents import EmployeeAgent
    priya=next(a for a in target_agents() if a['emp_id']=='VX007')
    result=EmployeeAgent(priya).answer('What are you working on?', '2026-11-17T12:00:00+05:30')
    assert all(not e['evidence_id'].startswith('JIRA-ATLAS-') for e in result['evidence'])
