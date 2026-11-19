from __future__ import annotations
import csv, hashlib, json, re
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Iterable
import pandas as pd
from docx import Document
from pypdf import PdfReader
from .config import RAW_ROOT, DB_PATH, RELEASE_BY_FOLDER, SCHEMA_VERSION, ts
from . import permissions as P
import math, sqlite3

SUPPORTED = {'.xlsx', '.csv', '.docx', '.pdf', '.eml', '.txt'}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS sources (
 source_id TEXT PRIMARY KEY, file_name TEXT NOT NULL, relative_path TEXT NOT NULL,
 release_at TEXT NOT NULL, file_type TEXT NOT NULL, sha256 TEXT NOT NULL,
 extracted_text TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'record'
);
CREATE TABLE IF NOT EXISTS evidence (
 evidence_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, locator TEXT NOT NULL,
 text TEXT NOT NULL, release_at TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'record',
 FOREIGN KEY(source_id) REFERENCES sources(source_id)
);
CREATE TABLE IF NOT EXISTS assumptions (
 assumption_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, subject TEXT NOT NULL,
 assumption TEXT NOT NULL, source_basis TEXT NOT NULL, confidence TEXT NOT NULL,
 what_changes_mind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS conflicts (
 conflict_id TEXT PRIMARY KEY, topic TEXT NOT NULL, claim_a TEXT NOT NULL,
 claim_b TEXT NOT NULL, working_conclusion TEXT NOT NULL, rationale TEXT NOT NULL,
 confidence TEXT NOT NULL, source_refs TEXT NOT NULL
);
'''

def _docx_text(path: Path) -> str:
    doc = Document(path)
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for ti, table in enumerate(doc.tables, 1):
        parts.append(f"TABLE {ti}")
        for row in table.rows:
            parts.append(" | ".join(c.text.replace('\n', ' / ') for c in row.cells))
    return '\n'.join(parts)

def _pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return '\n'.join(f"PAGE {i+1}\n{page.extract_text() or ''}" for i, page in enumerate(reader.pages))

def _eml_text(path: Path) -> str:
    msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    body = msg.get_body(preferencelist=('plain',))
    return '\n'.join(f"{k}: {msg.get(k, '')}" for k in ('From','To','Date','Subject')) + '\n' + (body.get_content() if body else '')

def _xlsx_text(path: Path) -> str:
    parts = []
    book = pd.ExcelFile(path)
    for sheet in book.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet, header=None, dtype=object)
        parts.append(f"SHEET {sheet}")
        parts.append(df.fillna('').to_string(index=False, header=False))
    return '\n'.join(parts)

def _payroll_redacted_rows(path: Path) -> list[tuple[str, str]]:
    """Row-level payroll evidence with ONLY the allow-listed non-monetary columns (permissions.py)."""
    from . import data as D
    df = D.payroll_meta()
    out = []
    for _, r in df.iterrows():
        row = P.redact_payroll_row({k: r[k] for k in P.PAYROLL_ALLOWED_COLUMNS})
        out.append((f"sheet:Payroll Q4:row:{int(r['_row'])}", f"{path.name} | sheet Payroll Q4 | Excel row {int(r['_row'])} (amounts withheld)\n" +
                    '; '.join(f"{k}={v}" for k, v in row.items())))
    return out

def _git_summary(path: Path) -> str:
    from . import facts as F
    cs = F.commit_summary()
    return (f"git_log.csv summary: {cs['total']} commits from {cs['first']} to {cs['last']}. Commits by author email: " +
            '; '.join(f"{k}={v}" for k, v in cs['by_author'].items()) +
            ". Commit counts are activity, not productivity. pnair@users.noreply.github.com is an unresolved alias.")

def classify(path: Path) -> str:
    """record | template (blank worksheets, never evidence) | restricted (payroll: row-level only, never searchable)."""
    if 'templates' in path.parts: return 'template'
    if P.is_payroll_register(path.name): return 'restricted'
    return 'record'

def extract(path: Path) -> str:
    ext = path.suffix.lower()
    if P.is_payroll_register(path.name):
        return '\n'.join(t for _, t in _payroll_redacted_rows(path))
    if path.name == 'git_log.csv':
        return _git_summary(path)
    if ext == '.docx': return _docx_text(path)
    if ext == '.pdf': return _pdf_text(path)
    if ext == '.eml': return _eml_text(path)
    if ext == '.xlsx': return _xlsx_text(path)
    if ext == '.csv': return path.read_text(encoding='utf-8-sig', errors='replace')
    if ext == '.txt': return path.read_text(encoding='utf-8', errors='replace')
    return ''

def _chunks(path: Path, text: str) -> list[tuple[str,str]]:
    ext = path.suffix.lower()
    if P.is_payroll_register(path.name):
        return _payroll_redacted_rows(path)
    if path.name == 'git_log.csv':
        return [('summary', text)]
    if ext == '.xlsx':
        out=[]
        for sheet in pd.ExcelFile(path).sheet_names:
            df=pd.read_excel(path,sheet_name=sheet,header=None,dtype=object).fillna('')
            # Most release workbooks have title/blank rows before the table header.
            # Detect the header as the densest of the first eight rows.
            candidates=[]
            for ri in range(min(8,len(df))):
                vals=[str(v).strip() for v in df.iloc[ri].tolist() if str(v).strip() and str(v).lower()!='nan']
                candidates.append((len(vals),ri))
            if not candidates:
                continue
            _, header_i=max(candidates,key=lambda x:(x[0],-x[1]))
            headers=[]
            for ci,v in enumerate(df.iloc[header_i].tolist()):
                name=str(v).strip() if str(v).strip() and str(v).lower()!='nan' else f'Column{ci+1}'
                headers.append(name)
            out.append((f"sheet:{sheet}:header",f"Workbook {path.name}; sheet {sheet}; header row {header_i+1}: "+' | '.join(headers)))
            for ri in range(header_i+1,len(df)):
                vals=df.iloc[ri].tolist()
                if not any(str(v).strip() and str(v).lower()!='nan' for v in vals):
                    continue
                pairs=[]
                for ci,v in enumerate(vals):
                    if ci<len(headers) and str(v).strip() and str(v).lower()!='nan':
                        pairs.append(f"{headers[ci]}={v}")
                if pairs:
                    out.append((f"sheet:{sheet}:row:{ri+1}",f"{path.name} | sheet {sheet} | Excel row {ri+1}\n"+'; '.join(pairs)))
        return out
    if ext == '.pdf':
        try:
            r=PdfReader(str(path)); return [(f"page:{i+1}", f"{path.name}, page {i+1}\n{p.extract_text() or ''}") for i,p in enumerate(r.pages)]
        except Exception: pass
    # Keep a document as one evidence unit; long docs are split by paragraph to keep retrieval useful.
    paras=[x.strip() for x in re.split(r'\n{2,}',text) if x.strip()]
    if len(paras)>1:
        return [(f"section:{i+1}", f"{path.name}, section {i+1}\n{p}") for i,p in enumerate(paras)]
    return [("document", f"{path.name}\n{text}")]

def connect():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(DB_PATH)
    conn.row_factory=sqlite3.Row
    if conn.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
        # Generated DB from an older schema (may hold unredacted rows): drop everything and rebuild.
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
            conn.execute(f'DROP TABLE IF EXISTS "{name}"')
        conn.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
    conn.executescript(SCHEMA)
    return conn

def ingest_all(force: bool=False) -> dict:
    conn=connect(); cur=conn.cursor()
    if force:
        cur.execute('DELETE FROM evidence'); cur.execute('DELETE FROM sources')
    count=0; ev_count=0
    for path in sorted(RAW_ROOT.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED: continue
        rel=path.relative_to(RAW_ROOT).as_posix()
        folder=rel.split('/')[0]
        release=RELEASE_BY_FOLDER.get(folder, RELEASE_BY_FOLDER['Day1_Mon_16Nov'])
        raw=path.read_bytes(); sha=hashlib.sha256(raw).hexdigest()
        sid='SRC-'+sha[:12].upper()
        if cur.execute('SELECT 1 FROM sources WHERE source_id=?',(sid,)).fetchone(): continue
        text=extract(path)
        kind=classify(path)
        cur.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',(sid,path.name,rel,release,path.suffix.lower(),sha,text,kind))
        for i,(loc,chunk) in enumerate(_chunks(path,text),1):
            eid=f"EV-{sha[:8].upper()}-{i:03d}"
            cur.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?)',(eid,sid,loc,chunk,release,kind)); ev_count+=1
        count+=1
    conn.commit(); conn.close()
    # Normalize structured exports into queryable tables after provenance ingestion.
    from .normalize import normalize_all
    normalize_all()
    return {'files_ingested':count,'evidence_units_added':ev_count}

_STOP={'the','what','when','where','who','why','how','did','does','was','were','are','is','and','for','from','with','about','into','this','that','have','has','had',
 'could','would','should','will','can','you','your','company','cockpit','know','known','ceo','tell','show','give','list','please','any','all','our','their','them','they','there',
 'which','whose','been','being','than','then','also','over','under','between','records','record','data','file','files'}

def _stem(t:str)->str:
    for suf in ('ing','ed','es','s'):
        if len(t)>4 and t.endswith(suf): return t[:-len(suf)]
    return t

def _terms(text:str)->list[str]:
    return [_stem(t) for t in re.findall(r'[a-z0-9]+',text.lower()) if len(t)>2 and t not in _STOP]

def search_evidence(query: str, as_of: str='2026-11-20T18:00:00+05:30', limit:int=8):
    """IDF-weighted retrieval over release-gated, non-restricted evidence.

    `matched` = number of DISTINCT query terms found in the unit; callers treat <2 as "no relevant record".
    Templates (blank worksheets) and restricted payroll rows are never searchable.
    """
    conn=connect()
    q_terms=list(dict.fromkeys(_terms(query)))
    rows=conn.execute("""SELECT e.evidence_id,e.text,e.release_at,s.file_name,s.relative_path,e.locator
                         FROM evidence e JOIN sources s USING(source_id) WHERE e.kind='record'""").fetchall()
    conn.close()
    cutoff=ts(as_of)
    docs=[(r,Counter_(_terms(r['text']+' '+r['file_name']))) for r in rows if ts(r['release_at'])<=cutoff]
    n=max(len(docs),1)
    df={t:sum(1 for _,c in docs if t in c) for t in q_terms}
    scored=[]
    for r,c in docs:
        hit=[t for t in q_terms if t in c]
        if not hit: continue
        score=sum(math.log(1+n/(1+df[t]))*(1+math.log(c[t])) for t in hit)
        scored.append((score,len(hit),r))
    scored.sort(key=lambda x:(-x[1],-x[0],x[2]['file_name']))
    return [dict(score=round(s_,3),matched=m,**dict(r)) for s_,m,r in scored[:limit]]

def Counter_(items):
    from collections import Counter
    return Counter(items)
