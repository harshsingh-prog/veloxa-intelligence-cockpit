# Defensible design decisions

## 1. Storage: SQLite over a hosted database

Chosen because the evaluator must run from a fresh clone with one command and the dataset is small. SQLite is portable and inspectable. Trade-off: not intended for concurrent production use; PostgreSQL would be the production migration path.

## 2. Structured retrieval before vector RAG

Chosen because the source pack contains exact financial, HR and Jira records where deterministic filters and calculations are more reliable than semantic similarity. Full-text evidence search supports discovery. Trade-off: less flexible for open-ended semantic synthesis; optional Ollama generation is layered over retrieved evidence, never substituted for it.

## 3. One shared agent framework, fourteen profiles

Chosen to preserve consistent facts and permissions. Fourteen separate autonomous agents with independent memory could contradict each other. Each profile is grounded in Employee Master; shared evidence is retrieved by employee context. Fictional personal details are explicit assumptions.

## 4. Source authority is fact-specific

Board updates are used for board-reported ARR, burn, runway and customer count. Employee Master is used for employee identity/status as of its export. Jira is used for issue status and assignees. Emails are used for their correspondence events. A transcript can establish what a speaker said, not necessarily the underlying fact.

## 5. No individual salary in CEO UI

T2 explicitly says individual salaries must never appear in anything Ananya sees. CEO pages omit row-level payroll values. A production version would enforce this with authenticated role-based access at the service and database layers, not only UI hiding.

## 6. Refuse named resignation-probability rankings

The dataset cannot support a reliable individual prediction. Leave, workload, commits and small-team engagement are not valid substitutes. Provide team-level retention and operational continuity indicators instead.

## 7. No Slack message display

No Slack export is supplied. The likely transcript correction “slag” to “Slack” does not create source data or authorization.

## 8. Keep Sneha and Snehal separate

The roster identifies Sneha Kulkarni, while engineering exports contain both names. A contractor explanation is possible but unproven. No automatic identity merge.

## 9. Historical knowledge is release-aware

A record may describe an event from an earlier date but is not available to the cockpit before its folder release. Filter evidence by release timestamp. Full bitemporal validity is documented as a future extension.

## 10. Confidence is categorical and rule-based

Use High/Medium/Low/Unknown with reasons. Avoid model-generated probability percentages that look precise but lack calibration.

## 11. Risks are ranked qualitatively

The initial risk list is transparent and evidence-linked. It is not a statistically calibrated prediction. The system must show why an issue ranks highly and avoid treating story points as time estimates.

## 12. Optional local LLM

Ollama with Qwen 2.5 is optional for grounded persona-style synthesis. Deterministic fallback is required so fresh-clone evaluation does not fail when a local model is absent. LLM output must not resolve conflicts or introduce new facts.

## 13. Facts are computed once, from raw files (`veloxa/facts.py`)
Handlers format facts; they never type numbers. A change in a source file changes every answer, KPI tile and risk text consistently.

## 14. LLM boundary (supersedes #12)
The model may (a) re-phrase a verified answer or (b) choose one label from a closed intent menu. Re-phrases must pass `guard.check` (no new numbers/number-words/IDs/people, uncertainty preserved, no forbidden claims). It never answers refusals, never computes, never chooses sources. See ACCURACY.md.

## 15. Privacy by construction
Salary columns are excluded by an allow-list at load time (`permissions.py`), not hidden at display time. The DB is versioned (`SCHEMA_VERSION`) so an old database containing sensitive rows is dropped and rebuilt. Payroll audit uses only non-monetary fields (days payable, processed-by).

## 16. Two-layer "what did we know" answers
Company layer (records dated ≤ the asked date) is kept separate from cockpit layer (what had been released). Answers never mention events after the asked date; for dates inside the release window, only sources released by that moment are used.

## 17. Evaluate before claiming accuracy
Expected answers come from an independent oracle; new question batches are scored first-pass before fixes and the history is recorded in ACCURACY.md.
