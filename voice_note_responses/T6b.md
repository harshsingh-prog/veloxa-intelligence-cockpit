# T6b — Marketing reporting-line change

**Decision: Implement the data-model capability; do not activate an unconfirmed change.** Reporting relationships are stored separately from employee identity and can be time-bounded. The CEO's statement establishes that a change is being considered, but the effective date is explicitly uncertain (“next month” or “the month after”).

**Current behavior:** The active reporting tree remains as recorded in Employee Master. The proposed CRO relationship is represented as pending, with no effective date.

**Why:** This allows the organization to change without rewriting employee profiles or corrupting historical reporting. It also avoids presenting a proposal as an effective organizational fact.
