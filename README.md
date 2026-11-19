# Veloxa Intelligence — CXO Cockpit

A local-first, evidence-grounded executive cockpit for the fictional Veloxa Technologies hackathon challenge.

## What it does

- Ingests all supplied Day 1–Day 4 DOCX, XLSX, PDF, CSV, EML and TXT files.
- Preserves source file, release date, workbook sheet/document locator and evidence ID.
- Normalizes employee, finance GL, Jira, incident, pulse, hiring, leave, Git and on-call records into SQLite tables.
- Provides a CEO overview and a ranked, evidence-backed worry list.
- Answers common executive questions with explicit confidence and uncertainty.
- Provides 14 interviewable agent profiles from Employee Master: 5 Engineering, 3 Finance, 3 People & Ops, 3 Marketing.
- Includes Department/People, Atlas project, historical release replay and evidence explorer views.
- Includes explicit pushback on unsupported private-message and individual resignation-prediction requests.
- Offers optional local Ollama/Qwen synthesis. The app still runs without Ollama.

## Prerequisites

- Python 3.10 or newer.
- Internet is not required after Python packages are installed.
- Optional: Ollama installed locally with `qwen2.5:14b-instruct` pulled.

## One-command setup and run

From the repository root:

```bash
python -m pip install -r requirements.txt && python -m streamlit run app.py
```

On first launch, the application creates `data/veloxa.db` and ingests the supplied raw release folders. It is safe to delete the generated database to rebuild it. Source files remain under `data/raw/`.

## Optional local model

The deterministic answer engine handles core facts, sensitive requests and unknowns. To enable local language generation for agent interviews:

```bash
ollama pull qwen2.5:14b-instruct
```

Then launch with:

```bash
VELOXA_MODEL=qwen2.5:14b-instruct python -m streamlit run app.py
```

Optional environment variables:

- `OLLAMA_BASE_URL` (default `http://localhost:11434`)
- `VELOXA_MODEL` (default `qwen2.5:14b-instruct`)

The LLM is only a response-generation layer over retrieved records. It must not decide which source is true.

## Run the automated test set

```bash
pytest -q
```

The suite includes 49 tests, including explicit refusal/uncertainty checks and release-cutoff checks. Tests use the supplied data pack and do not require Ollama.

## Main navigation

1. Executive overview
2. Ask Intelligence
3. What should I worry about?
4. 14 AI agents
5. Departments & people
6. Project Atlas
7. Historical knowledge
8. Evidence explorer
9. Assumptions & conflicts

## Important interpretation boundaries

- The Employee Master has 19 employee rows. The 14-agent scope is the four departments named by the brief; Sales, Support and Leadership are not in the 14-agent roster.
- Employee Master explicitly says contractors are not in Keka.
- Board figures are used for board-reported ARR, burn and runway; transcript statements remain visible as conflicts.
- Individual salary data is not displayed in the CEO interface, consistent with T2.
- No Slack export is supplied. The app refuses to show Slack messages.
- The app does not rank named employees by likelihood of quitting.
- Sneha and Snehal remain unresolved identities.
- T6d is a new CEO-reported resignation claim about “Pria”, likely Priya Nair, pending HR confirmation.
- Fictional personal-life details in agent profiles are assumptions, not facts.

## Required decision logs

See `ARCHITECTURE.md`, `ASSUMPTIONS.md`, `TRANSCRIPT_NOTES.md`, `DECISIONS.md`, `AI_LOG.md` and `voice_note_responses/`.

## Repository submission notes

The hackathon requires a public repository, a final frozen commit hash and this one-command run instruction. Commit changes transparently; do not backdate commits. The database is generated on first run and should generally be excluded from Git.


## Accuracy
```bash
python scripts/evaluate_accuracy.py      # 296 question variants vs an independent oracle + hallucination & leakage audit
pytest -q                                # 439 tests incl. the accuracy gate, privacy, LLM-guard and agent-grounding suites
```
See **ACCURACY.md** for what was wrong in the first version, how hallucination is prevented, and the honest first-pass scores on unseen questions.

**LLM mode (optional).** `VELOXA_LLM_POLISH=auto|0|1` (default `auto`: used only if Ollama is reachable). The model can only re-phrase verified answers
(guard-checked) or pick an intent label from a closed list; with it off, every answer is the deterministic verified text.
