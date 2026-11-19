from __future__ import annotations
import sys, json
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from veloxa.ingestion import ingest_all, connect, search_evidence
from veloxa.people import target_agents, employee_master, DEPT_ORDER
from veloxa.answer_engine import answer_question, worry_list
from veloxa.agents import all_agents
from veloxa import data as D

st.set_page_config(page_title='Veloxa Intelligence',page_icon='🧭',layout='wide')

@st.cache_resource
def bootstrap():
    ingest_all()
    conn=connect()
    source_count=conn.execute('SELECT COUNT(*) FROM sources').fetchone()[0]
    evidence_count=conn.execute('SELECT COUNT(*) FROM evidence').fetchone()[0]
    conn.close()
    return {'files_ingested':source_count,'evidence_units_added':evidence_count}

stats=bootstrap()

def load_sources():
    c=connect(); rows=c.execute('SELECT file_name,relative_path,release_at,file_type FROM sources ORDER BY release_at,relative_path').fetchall(); c.close()
    return pd.DataFrame([dict(r) for r in rows])

st.markdown('''<style>
.block-container{padding-top:1.3rem;padding-bottom:2rem;max-width:1500px}
[data-testid="stMetric"]{background:rgba(100,116,139,.10);padding:14px;border-radius:12px;border:1px solid rgba(148,163,184,.18)}
.small-muted{color:#94a3b8;font-size:.86rem}
</style>''',unsafe_allow_html=True)

with st.sidebar:
    st.title('🧭 VELOXA')
    st.caption('Evidence-grounded executive intelligence')
    page=st.radio('Navigation',['Executive overview','Ask Intelligence','What should I worry about?','14 AI agents','Departments & people','Project Atlas','Historical knowledge','Evidence explorer','Assumptions & conflicts','Accuracy & audit'],label_visibility='collapsed')
    st.divider()
    st.caption('Data release mode')
    release=st.selectbox('Knowledge available through',['Day 1 · 16 Nov 10:00','Day 2 · 17 Nov 10:00','Day 3 · 18 Nov 10:00','Day 4 · 19 Nov 10:00'],index=3)
    as_of={'Day 1 · 16 Nov 10:00':'2026-11-16T10:00:00+05:30','Day 2 · 17 Nov 10:00':'2026-11-17T10:00:00+05:30','Day 3 · 18 Nov 10:00':'2026-11-18T10:00:00+05:30','Day 4 · 19 Nov 10:00':'2026-11-19T10:00:00+05:30'}[release]
    st.caption(f"Loaded {stats['files_ingested']} source files · {stats['evidence_units_added']} evidence units")

agents=target_agents()
emp=employee_master()

if page=='Executive overview':
    st.title('Good morning, Ananya.')
    st.write('Here is the company picture supported by the latest released records. Select an earlier release in the sidebar to replay what the cockpit could know then.')
    cols=st.columns(4)
    for col,label,value,helptext in [
      (cols[0],'Latest reported ARR',f"₹{D.board('Jul-Sep 2026')['arr_cr']} Cr",'Board update · Jul–Sep 2026 (computed from the PDF)'),
      (cols[1],'Monthly burn',f"₹{D.board('Jul-Sep 2026')['burn_lakh']:g} L",'Board update · Jul–Sep 2026 (computed from the PDF)'),
      (cols[2],'Runway',f"{D.board('Jul-Sep 2026')['runway_months']} months",'Board-reported, not recalculated'),
      (cols[3],'Target AI agents',str(len(agents)),'14 people across four departments')]:
        col.metric(label,value,help=helptext)
    st.subheader('What should I worry about?')
    for i,r in enumerate(worry_list(as_of)[:3],1):
        with st.container(border=True):
            a,b=st.columns([4,1]); a.markdown(f"**{i}. {r['title']}**"); b.markdown(f"**{r['severity']}**")
            st.write(r['why']); st.caption('Evidence: '+', '.join(r['sources'])+' · Confidence: '+r['confidence'])
    st.subheader('Company record coverage')
    c1,c2=st.columns(2)
    c1.metric('Employee master records',len(emp),'Includes Sales and Support outside the 14-agent scope')
    c2.metric('Departments in agent scope',4)
    st.info('Important: ARR, burn and runway are board-reported figures. They are not derived from the selected GL export.')

elif page=='Ask Intelligence':
    st.title('Ask Veloxa Intelligence')
    st.caption('Answers are constrained by the selected release date. Unsupported claims are marked unknown or disputed.')
    examples=['Why is Atlas v3 delayed?','What is the latest ARR and burn?','What happened with Rahul’s February payslip?','Are Sneha and Snehal the same person?','What did we know on 2026-11-17?','Show me everyone’s Slack messages.']
    prompt=st.chat_input('Ask a company question…')
    if 'chat_history' not in st.session_state: st.session_state.chat_history=[]
    for item in st.session_state.chat_history:
        with st.chat_message(item['role']): st.markdown(item['content'])
    if prompt:
        st.session_state.chat_history.append({'role':'user','content':prompt})
        result=answer_question(prompt,as_of=as_of)
        body=result['answer']+f"\n\n**Confidence:** {result['confidence']}"+(' · **Uncertainty/refusal:** Yes' if result['uncertain'] else '')+f" · *route: {result['intent']}"+(' · wording by local model, guard-verified' if result['llm']['used_llm'] else ' · deterministic, evidence-computed')+'*'
        if result['sources']: body+='\n\n**Evidence**\n'+ '\n'.join(f'- {s}' for s in result['sources'])
        else: body+='\n\n**Evidence:** No supporting record found.'
        st.session_state.chat_history.append({'role':'assistant','content':body})
        st.rerun()
    st.markdown('**Try a question**')
    buttons=st.columns(3)
    for i,q in enumerate(examples):
        if buttons[i%3].button(q,key=f'ex{i}',use_container_width=True):
            result=answer_question(q,as_of=as_of)
            st.session_state.chat_history.append({'role':'user','content':q})
            body=result['answer']+f"\n\n**Confidence:** {result['confidence']}\n\n**Evidence**\n"+'\n'.join(f'- {s}' for s in result['sources'])
            st.session_state.chat_history.append({'role':'assistant','content':body}); st.rerun()

elif page=='What should I worry about?':
    st.title('What should I worry about?')
    st.caption('Ranked operational concerns. Scores are qualitative prioritization, not statistical probabilities.')
    for i,r in enumerate(worry_list(as_of),1):
        with st.container(border=True):
            st.markdown(f"### {i}. {r['title']} · {r['severity']}")
            st.write(r['why'])
            st.caption(f"Confidence: {r['confidence']} · Sources: {', '.join(r['sources'])}")
    st.warning('Do not interpret engagement, leave or commit activity as a prediction that a named employee will resign.')

elif page=='14 AI agents':
    st.title('Your 14 AI colleagues')
    st.caption('These agents share one evidence base. Fictional personal details are labeled as assumptions and never used as factual evidence.')
    dept=st.selectbox('Department',['All']+DEPT_ORDER)
    subset=[a for a in agents if dept=='All' or a['department']==dept]
    names=[f"{a['name']} · {a['title']}" for a in subset]
    chosen=st.selectbox('Select an agent',names)
    profile=subset[names.index(chosen)]
    left,right=st.columns([1,2])
    with left:
        st.subheader(profile['name']); st.write(profile['title']); st.caption(profile['department'])
        st.write('**Employee ID:** '+profile['emp_id']); st.write('**Location:** '+profile['location'])
        st.write('**Status:** '+profile['status'])
        st.write('**Manager ID:** '+str(profile['manager_id'] or 'Not recorded'))
        st.info('Fictional persona detail (assumption): '+profile['personal_life_assumption'])
    with right:
        q=st.text_input('Interview this agent',placeholder='What are you currently working on?')
        if q:
            from veloxa.agents import EmployeeAgent
            res=EmployeeAgent(profile).answer(q,as_of=as_of)
            st.write(res['response'])
            st.caption(f"route: {res['intent']} · "+('wording by local model (guard-verified)' if res['model_used'] else 'verified deterministic answer')+(f" · model output rejected: {'; '.join(res['llm']['reasons'])}" if not res['llm']['guard_ok'] else ''))
            if res['evidence']:
                st.markdown('**Retrieved evidence**')
                for e in res['evidence']:
                    with st.expander(f"{e['file_name']} · {e['locator']} · {e['evidence_id']}"):
                        st.write(e['text'][:5000])
    st.divider()
    df=pd.DataFrame([{k:a[k] for k in ['name','emp_id','department','title','status','exit_date']} for a in agents])
    st.dataframe(df,use_container_width=True,hide_index=True)

elif page=='Departments & people':
    st.title('Departments & people')
    counts=pd.DataFrame([{'Department':d,'People':sum(1 for a in agents if a['department']==d)} for d in DEPT_ORDER])
    st.plotly_chart(px.bar(counts,x='Department',y='People',title='14-person agent scope'),use_container_width=True)
    st.dataframe(pd.DataFrame(agents)[['emp_id','name','department','title','manager_id','location','status','exit_date']],use_container_width=True,hide_index=True)
    st.caption('Sales, Support and Leadership remain in the wider Employee Master but are outside the 14-person agent scope.')

elif page=='Project Atlas':
    st.title('Atlas v3 delivery intelligence')
    if pd.Timestamp(as_of) < pd.Timestamp('2026-11-18T10:00:00+05:30'):
        st.info('The Jira export, incident records and on-call rota are not released to the cockpit yet. The Day 1 board update can still be queried in Ask Intelligence.')
    else:
        jira=next(ROOT.glob('data/raw/**/Jira_Export_ATLAS.xlsx'))
        issues=pd.read_excel(jira,sheet_name='Issues',header=2)
        issues=issues[issues['Key'].astype(str).str.startswith('ATLAS-')].copy()
        issues['Story Points']=pd.to_numeric(issues['Story Points'],errors='coerce')
        vc=pd.read_excel(jira,sheet_name='Versions',header=0)
        v=vc.iloc[0]
        a,b,c=st.columns(3); a.metric('Original GA',str(pd.to_datetime(v['Original Release Date']).date())); b.metric('Revised GA',str(pd.to_datetime(v['Release Date']).date())); c.metric('Unresolved issues',int((issues['Status']!='Done').sum()))
        st.plotly_chart(px.histogram(issues,x='Status',title='Jira issue status'),use_container_width=True)
        open_issues=issues[issues['Status']!='Done']
        ass=open_issues.groupby('Assignee',dropna=False)['Story Points'].sum().reset_index().sort_values('Story Points',ascending=False)
        st.plotly_chart(px.bar(ass,x='Assignee',y='Story Points',title='Unresolved story points by Jira assignee (initials)'),use_container_width=True)
        st.dataframe(open_issues[['Key','Summary','Assignee','Story Points','Status','Created','Fix Version']],use_container_width=True,hide_index=True)
        st.warning('Story points are relative estimates, not calendar days or a direct measure of individual productivity.')
elif page=='Historical knowledge':
    st.title('Historical knowledge replay')
    dt=st.date_input('What date do you want to ask about?',value=pd.Timestamp('2026-09-15').date(),min_value=pd.Timestamp('2026-01-01').date(),max_value=pd.Timestamp('2026-11-19').date())
    q=st.text_input('Question','What did we know on this date?')
    if st.button('Reconstruct knowledge'):
        query=f"What did we know on {dt.isoformat()}? {q}"
        result=answer_question(query,as_of=as_of)
        st.write(result['answer']); st.caption('Confidence: '+result['confidence'])
        for src in result['sources']: st.write('• '+src)
    st.info('Release boundaries are enforced independently of the dates written inside source documents. A later export does not become earlier knowledge merely because it describes an earlier event.')

elif page=='Evidence explorer':
    st.title('Evidence explorer')
    q=st.text_input('Search source records',placeholder='e.g. Atlas routing reliability')
    if q:
        hits=search_evidence(q,as_of=as_of,limit=20)
        st.write(f'{len(hits)} matching evidence units')
        for h in hits:
            with st.expander(f"{h['file_name']} · {h['locator']} · {h['evidence_id']} · score {h['score']}"):
                st.caption(f"Release available: {h['release_at']} · {h['relative_path']}")
                st.text(h['text'][:8000])
    src=load_sources()
    st.subheader('Loaded source inventory')
    st.dataframe(src,use_container_width=True,hide_index=True)

elif page=='Assumptions & conflicts':
    st.title('Assumptions & conflicts')
    st.subheader('Explicit conflict register')
    conflicts=[
      ('Headcount','Candidate brief describes 180 people','Employee Master has 19 records; board says 19','Use 19 as recorded roster; scope remains limited to 14 agents','Medium'),
      ('ARR / burn','Transcript figures are ambiguous or inconsistent','Board update reports ARR ₹6.1 Cr and burn ₹44 L','Prefer board-reported metrics for board reporting; preserve transcript conflict','High'),
      ('Sneha / Snehal','Engineering transcript and exports use both names','Employee Master only identifies Sneha Kulkarni','Keep separate identities; no merge without evidence','Low'),
      ('Priya resignation','T6d says “Pria resigned” and notice period “I think”','31 Oct HR export lists Priya active and has no resignation','Likely Priya Nair; new CEO claim pending HR confirmation','Medium'),
      ('CRO reporting','T6b says next month or month after','No formal effective date supplied','Keep as proposed relationship, not active hierarchy','Medium'),
      ('Atlas status','VP Engineering call (T5): “on track”, “September-ish”','Jira Versions: GA moved 15 Sep → 15 Dec on 2 Sep by vikram; board says GA moved','Prefer system records over transcript; keep the contradiction visible','High'),
      ('Contractor start','Email 08 (24 Aug): contractor starts “this week”','Rota shows Snehal from week of 17 Aug; invoice PIS-108 covers 18–31 Aug','Dates differ by about a week; identity link Snehal = S. Patil still unproven','Low'),
      ('Sapphire vendors','“Sapphire Events Pvt Ltd” and “Saphire Event Mgmt” (MKT-EVT)','“Sapphire Residency Hotel” (SAL-TRV) is a third, unrelated name','Never merge vendors on name similarity','Medium'),
      ('Rahul payroll','Rahul queried a payslip','No reply resolving query in email chain','Flag for verification; do not claim overpayment','High'),
    ]
    conflict_df=pd.DataFrame(conflicts,columns=['Topic','Claim A','Claim B','Working conclusion','Confidence'])
    if pd.Timestamp(as_of) < pd.Timestamp('2026-11-18T10:00:00+05:30'):
        conflict_df=conflict_df[~conflict_df['Topic'].isin(['Sneha / Snehal','Priya resignation','CRO reporting','Atlas status','Contractor start'])]
    elif pd.Timestamp(as_of) < pd.Timestamp('2026-11-19T10:00:00+05:30'):
        conflict_df=conflict_df[conflict_df['Topic']!='Priya resignation']
    st.dataframe(conflict_df,use_container_width=True,hide_index=True)
    st.subheader('Fictional persona assumptions')
    st.dataframe(pd.DataFrame([{'Employee':a['name'],'ID':a['emp_id'],'Assumption':a['personal_life_assumption'],'Basis':a['assumption_basis']} for a in agents]),use_container_width=True,hide_index=True)
    st.caption('The same assumptions are documented in ASSUMPTIONS.md. They are not used as factual evidence.')


elif page=='Accuracy & audit':
    import sys as _sys
    _sys.path.insert(0,str(Path(__file__).parent/'scripts'))
    st.title('Accuracy & hallucination audit')
    st.caption('Expected answers come from an independent oracle that re-reads the raw files with separate code. The same run is available as `python scripts/evaluate_accuracy.py`.')
    if st.button('Run evaluation now') or 'acc' in st.session_state:
        if 'acc' not in st.session_state or st.session_state.get('acc_fresh'):
            import os; os.environ['VELOXA_LLM_POLISH']='0'
            import evaluate_accuracy as E
            from eval import golden, heldout, fresh
            corpus=E.source_corpus(); rows=[]
            for name,mod in (('golden (tuned)',golden),('held-out round 2',heldout),('fresh round 3',fresh)):
                for c in mod.cases():
                    for q in c['qs']:
                        r=E.check_case(c,q,corpus); r['set']=name; rows.append(r)
            st.session_state['acc']=rows; st.session_state['guard']=E.llm_attack()
        rows=st.session_state['acc']; df=pd.DataFrame(rows)
        a,b,c_=st.columns(3)
        a.metric('Questions answered correctly',f"{int(df.ok.sum())}/{len(df)}")
        b.metric('Answers with untraceable numbers',int((df.ungrounded.str.len()>0).sum()))
        c_.metric('Hostile model outputs blocked',f"{st.session_state['guard'][0]}/{st.session_state['guard'][1]}")
        st.dataframe(df.groupby(['set','cat']).agg(correct=('ok','sum'),total=('ok','count')).reset_index(),use_container_width=True,hide_index=True)
        bad=df[~df.ok]
        if len(bad): st.error('Failures'); st.dataframe(bad[['id','q','fails','answer']],use_container_width=True)
        with st.expander('All questions and answers'):
            st.dataframe(df[['set','cat','q','ok','intent','answer']],use_container_width=True,hide_index=True)

st.divider()
st.caption('Veloxa Technologies is fictional and created for this hackathon. All data shown is from the supplied fictional release pack. Evidence and interpretations remain distinguishable.')
