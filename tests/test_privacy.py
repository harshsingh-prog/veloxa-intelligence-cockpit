import re
import sqlite3

from eval.oracle import O
from veloxa import data as D
from veloxa.config import DB_PATH
from veloxa.ingestion import search_evidence
from veloxa.permissions import PAYROLL_BLOCKED_COLUMNS


def test_payroll_loader_never_loads_salary_columns():
    assert not set(PAYROLL_BLOCKED_COLUMNS) & set(D.payroll_meta().columns)


def test_database_contains_no_salary_values():
    vals = {v for v in O()["salary_values"] if len(v) >= 5}
    c = sqlite3.connect(DB_PATH)
    blob = " ".join(r[0] for r in c.execute("SELECT text FROM evidence")) + " ".join(r[0] for r in c.execute("SELECT extracted_text FROM sources"))
    c.close()
    compact = blob.replace(",", "")
    legit = {"3175000", "120000", "141600", "70800", "21600"}  # GL payroll total and Patil invoice figures coincide with register values
    leaked = [v for v in vals if v not in legit and re.search(rf"(?<!\d){v}(?!\d)", compact)]
    assert not leaked, leaked[:5]


def test_payroll_evidence_is_not_searchable():
    assert not [h for h in search_evidence("Rahul Verma payroll February days payable processed") if "Payroll_Register" in h["file_name"]]


def test_templates_are_not_evidence():
    assert not [h for h in search_evidence("evidence index template entity resolution worksheet", limit=20) if h["file_name"] in ("Evidence_Index.xlsx", "Entity_Resolution.xlsx")]
