# Accuracy & Hallucination Control

> **Short answer to "is it accurate?"** The original build passed its 49 tests but those tests only exercised the exact phrasings
> they were written with. Re-asking the same questions in other words exposed unanswered questions, three wrong/misleading answers,
> one information leak across release dates and a privacy hole. This version fixes those, measures accuracy independently, and makes
> hallucination structurally impossible for factual content. Details and honest numbers below.

## 1. What was wrong with the first version (found by audit, not by the tests)

| # | Finding | Severity |
|---|---|---|
| 1 | At the Day 1/2 cutoff it said Atlas "moved its GA date to **December 2026**". The Jul–Sep board PDF gives *no* new date; "15 December" exists only in the **Day 3 Jira export**. A test (`test_36`) asserted the leak. | Leak / fabricated-by-inference |
| 2 | 57 rows with **individual salaries** were stored in SQLite (`evidence` + `sources.extracted_text`); only a *filename filter* kept them out of the UI. T2 says salaries must never reach the CEO. | Privacy |
| 3 | "How many employees do we have?" answered **14** (the agent count) instead of 19 records. | Wrong answer |
| 4 | Substring matching (`'cro' in q`, `'arr' in q`, `'as of' in q`) fires on "a**cro**ss", "w**arr**anty", "h**as of**fered". The "private thoughts" check used `in` with a regex string, so it never matched. | Wrong routing |
| 5 | Many paraphrases ("What is our ARR?", "Who does Nikhil report to?", "Is Siddharth still employed?") fell through to raw excerpt dumps or "I don't know". | Low recall |
| 6 | Any text from the optional LLM was shown **unchecked**. No post-generation verification. | Hallucination path |
| 7 | `git_log.csv` (1,453 rows) was indexed as one blob, so it matched almost every search. Blank templates were searchable as "evidence". | Retrieval noise |
| 8 | Hard-coded KPI strings and answer numbers (`6.1`, `44`, `66`, `13`) instead of values computed from the files. | Staleness risk |

## 2. How hallucination is now prevented (by design, not by prompting)

```
question -> normalise -> word-boundary intent routing -> release gate -> facts.py (computed from raw files)
         -> formatted answer + row-level citations + confidence -> [optional] guarded LLM re-phrase
```

1. **Facts are computed, never typed.** `veloxa/facts.py` derives every figure (Jira counts, SEV1s, GL totals, pulse, hiring, board metrics…) from the raw workbooks/PDFs with row references. Only two identity inferences exist (Jira initials → people; `Sid`/`Pria`… → employees), each with its own evidence.
2. **The model never writes facts.** Language models are allowed two jobs only: (a) *re-phrase* an already-verified answer, (b) *pick one label from a closed menu* when no rule matched (the handler then writes the facts). Both are optional.
3. **Guard (`veloxa/guard.py`)** accepts a re-phrase only if every number/date, identifier and person name already occurs in the verified text/evidence, number-words ("about thirty") are not introduced, uncertainty wording survives, and no forbidden pattern appears (salary amounts, resignation predictions, Slack content, prompt-injection echoes). Otherwise the verified text is shown.
4. **Abstention is first-class.** Unknown → "I don't know based on the records". Periods/forecasts the records don't cover → explicit abstention. Missing data sources (HubSpot, NPS, churn…) → listed as not supplied.
5. **Release gating at the handler.** Each handler declares which release it needs; earlier cutoffs get "not available until DayN". Replaying Day 1/2/3 cannot leak later files.
6. **Privacy enforced in code.** `permissions.py` is an allow-list; salary columns are never loaded or stored. Blank templates and payroll rows are excluded from search.

## 3. How accuracy is measured (`python scripts/evaluate_accuracy.py`, also the in-app **Accuracy & audit** page and `pytest`)

* **Independent oracle** (`eval/oracle.py`): re-reads the raw files with *separate* code (no import from the app) so a parser bug can't hide in the expectation. `tests/test_oracle_anchors.py` pins it to numbers verified by hand.
* **Per-question checks:** required facts present · forbidden facts absent · cited source present · refusal/uncertainty flag · confidence level · salary-value leak scan.
* **Groundedness audit:** every number in every answer must appear in a *cited* source, the question, or a declared derivation (sum/percentage). Untraceable number ⇒ failure.
* **Adversarial LLM test:** 10 hostile "model outputs" (changed number, invented person/ID, prediction, number-words, dropped caveat, injection echo, salary claim) are pushed through the same production path; all must be rejected, and a faithful rewrite must be accepted.

### Results

| Set | Written | Questions | Score |
|---|---|---|---|
| Golden (tuned against) | before tuning | 210 | **210/210** |
| Held-out round 2 — *first pass, before any fix* | after tuning on golden | 56 | **40/56 = 71.4 %** → 56/56 after fixes |
| Fresh round 3 — *first pass, before any fix* | after round-2 fixes | 30 | **22/30 = 73.3 %** → 30/30 after fixes |
| **All sets now** | | **296** | **296/296**, 0 untraceable numbers, 0 salary leaks, 10/10 hostile outputs blocked |

**How to read this honestly.** The 100 % on the golden set is *tuned* accuracy and overstates real-world performance. The unseen-question
first-pass scores (~71–73 %) are the realistic recall figure for *new phrasings*. What matters is the failure mode: in both unseen rounds
**no answer contained an invented or untraceable number**; every miss was the system under-answering (abstaining, returning a profile card,
or missing a synonym), never asserting something false. The "after fixes" numbers are tuned again. Each round of new questions should
be added to `eval/` the same way: score first, then fix, never re-score silently.

**Not claimed:** accuracy on questions outside the supplied data room; correctness of the LLM's *wording* quality (only its factual
fidelity is guarded); coverage of every possible phrasing. If a phrasing isn't understood the system abstains rather than guesses.

## 4. Known limits / next steps
* Intent coverage is rule-based; with Ollama running, the closed-menu classifier lifts recall without opening a hallucination path. Without it, add rules from new failures.
* Jira-initials→person and `Sid`→Siddharth are documented inferences (High confidence); everything else ambiguous (Sneha/Snehal, `pnair` alias, Vicky) stays unresolved.
* Answers cite file + sheet/row/email; PDF page-level locators are coarse.
