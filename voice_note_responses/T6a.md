# T6a — Daily top-three worries

**Decision: Implement.** The cockpit home page automatically displays the three highest-priority evidence-backed risks. Each risk includes a concise explanation, source references, confidence, and a note about missing or conflicting evidence. The ranking is a transparent qualitative prioritization, not a statistical prediction.

**Why:** This directly addresses the CEO's request to see the top three concerns on opening the application without typing a question.

**Guardrail:** A risk must have at least one traceable source. The system must not fabricate a concern to fill all three slots; if fewer than three risks have evidence, it should show fewer.
