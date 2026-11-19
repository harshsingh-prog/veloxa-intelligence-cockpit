import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import csv
from veloxa.ingestion import connect
from pathlib import Path

if __name__ == '__main__':
    conn=connect()
    rows=conn.execute('''SELECT e.evidence_id,s.file_name,s.relative_path,e.locator,e.release_at,e.text
                         FROM evidence e JOIN sources s USING(source_id)
                         WHERE lower(s.file_name) NOT LIKE '%payroll_register%'
                         ORDER BY s.relative_path,e.locator''').fetchall()
    out=Path(__file__).resolve().parents[1]/'data'/'evidence_index.csv'
    with out.open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['evidence_id','file_name','relative_path','locator','available_from_ist','evidence_text'])
        w.writerows([tuple(r) for r in rows])
    conn.close()
    print(f'Wrote {len(rows)} evidence rows to {out}')
