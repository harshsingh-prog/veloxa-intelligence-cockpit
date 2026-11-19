"""Role-based data permissions, enforced in code (never delegated to an LLM prompt).

T2 (CFO): "Individual salaries must never show up in anything Ananya sees, only totals."
The CEO role therefore:
  * never loads salary columns from the payroll register at all (allow-list, not deny-list);
  * never stores row-level payroll amounts in the evidence index / extracted text;
  * can still audit non-monetary payroll facts (days payable, who processed the run).
"""
from __future__ import annotations

PAYROLL_FILE_MARKER = "payroll_register"
# Allow-list: the ONLY payroll columns that may enter the application.
PAYROLL_ALLOWED_COLUMNS = ["Emp ID", "Name", "Month", "Days in Month", "Days Payable", "Processed By"]
PAYROLL_BLOCKED_COLUMNS = ["Gross (Rs.)", "Deductions (Rs.)", "Net (Rs.)"]


def is_payroll_register(file_name: str) -> bool:
    return PAYROLL_FILE_MARKER in file_name.lower()


def redact_payroll_row(row: dict) -> dict:
    return {k: row[k] for k in PAYROLL_ALLOWED_COLUMNS if k in row}


def contains_blocked_payroll_values(text: str, salary_values: set[str]) -> bool:
    """Used by tests: does `text` contain any raw salary figure from the register?"""
    compact = text.replace(",", "")
    return any(v and v in compact for v in salary_values)
