# THE GOAL PROMPT — frontend journey loop

> **STATUS: COMPLETE (2026-08-13) — DO NOT PASTE THIS AS A `/goal`.** Both denominators
> closed (12/12 workflows, 5/5 real skills). The instruction below to paste the block as a
> session goal would re-enter a finished loop. *(Added 2026-09-03.)*

Paste the block below as the session's `/goal`. Nothing else.

It carries **only** the core policy and the loop guide — the two things a prompt can lose. Every
definition lives in [`2026-08-12-frontend-journey-loop-RUNBOOK.md`](2026-08-12-frontend-journey-loop-RUNBOOK.md):
the phases, the derived denominator, the pre-flight, the run configuration, the stop condition, the
inherited rules, and the precedent behind each rule below.

---

```
Execute docs/plans/2026-08-12-frontend-journey-loop-RUNBOOK.md continuously.
The RUNBOOK is the source of truth: its phases, denominator, pre-flight, stop
condition and inherited rules all override this prompt.

THE UNIT
A JOURNEY finds defects. A DEFECT is the unit of work. Every defect gets its own
full cycle -- test, investigate, fix, prove, conclude, commit -- its own ledger
row, its own falsifier. NEVER BATCH. One mechanism at N sites is ONE defect; the
RUNBOOK gives the test.

THE LOOP
One journey at a time, in the order the RUNBOOK derives. Never choose, reorder,
batch, skip or defer one yourself. On `proven` or `blocked`, immediately derive
the next and run it. Do not return control while executable work remains, and
THE GOAL IS NOT COMPLETE while a declared journey has no conclusion. Never stop
with a handoff, a progress report, or a question I could have answered by
measuring. The ledger is the progress authority -- not this prompt, not any
summary I write.

THE BAR -- all three, for every defect
CODE: tests, plus a falsifier proven RED on the ORIGINAL defect.
LIVE: the journey completed through the BROWSER, driven by the model, against
images verified current. IF I TYPE A TOOL ARGUMENT, THE JOURNEY IS NOT PROVEN.
DATA: measured state, an explicit falsifier, and NEVER a typed denominator.

NOT TERMINAL
converted, tested, investigated, "mostly works", "known issue", "ready for next",
"continue?". Only `proven` or `blocked`. A failed verification does not advance
the loop: investigate, fix, rerun, verify again.

FIXING
Fix the defect where it LIVES -- another service, the frontend, a skill body, a
workflow row, a tool description. PROSE IS NOT THE LEVER: rewording a message is
not a fix without new evidence.

BLOCKED BY A PRODUCT DECISION
Record the question and its evidence as the next DQ, then continue. Do not ask,
do not invent an answer. An unresolved question is not permission to stop.
```
