# THE GOAL PROMPT — frontend journey loop

*Paste the block below as the session's `/goal`. It is deliberately short: the RUNBOOK is the source
of truth and the prompt's only job is to point at it and fix the discipline that a prompt can lose.*

---

```
Execute docs/plans/2026-08-12-frontend-journey-loop-RUNBOOK.md continuously.
The RUNBOOK is the source of truth: its phases, its denominator, its stop condition
and its inherited rules override this prompt.

THE UNIT AND THE CYCLE
- A JOURNEY is how a defect is FOUND. A DEFECT is the unit of work.
- Every defect gets its OWN full cycle: test -> find -> investigate -> fix ->
  prove all three legs -> conclude in the ledger -> commit.
- NEVER BATCH. Three defects in one journey is three cycles, three ledger rows,
  three falsifiers, three commits. Not one investigation covering three.
- The ONE exception: a single mechanism at several sites is ONE defect and must be
  fixed at every site in one cycle. The test is whether one falsifier injected at
  any one site reds the guard for all of them. If yes, one defect at N sites.
  If no, N defects.
- Execute exactly ONE journey at a time, in the order the RUNBOOK derives.
  Never choose, reorder, batch, silently skip, or defer a journey yourself.
- After a journey reaches `proven` or `blocked`, immediately derive the next one
  and run it. Do not return control while executable work remains.
- The goal is NOT complete while a declared journey has no conclusion.
- The ledger is the progress authority. This prompt is not, and neither is any
  summary I write.

THE BAR — all three legs, every defect
- CODE: tests, plus a falsifier proven RED on the ORIGINAL defect.
- LIVE: the journey completed through the BROWSER at localhost:5174, driven by
  google/gemma-4-26b-a4b-qat, against the DEPLOYED images verified current.
  IF I TYPE A TOOL ARGUMENT, THE JOURNEY IS NOT PROVEN. The model derives every
  argument from the prose, or the defect IS that it could not.
- DATA: measured state, an explicit falsifier, and every denominator from SSOT or
  a live query. NEVER type a denominator.

NOT TERMINAL
`converted`, `tested`, `investigated`, "mostly works", "known issue", "ready for
next", "continue?" — none of these end an iteration. Only `proven` or `blocked`.
A failed verification does not advance the loop: investigate, fix, rerun, verify.

DEFER, RECORD, CONTINUE
If a product decision blocks the current journey, record the exact question and its
evidence as the next DQ (continuing from DQ-30) and move on. Do not ask, do not
invent an answer. An unresolved question is not permission to stop.

CONTENT
Create freely — this is the dev environment. Journeys need books with real history.
```

---

## Why each clause is there

Nothing above is style. Each line is a failure this run has already paid for.

| clause | what it prevents, with the precedent |
|---|---|
| **the defect is the unit, not the journey** | the correction the PO made 2026-08-12. Tool-loop #311 fixed two tools in one iteration and the second has no ledger row |
| **the one-mechanism exception** | the opposite mistake. Splitting a mechanism across cycles is the half-fix, which the tool loop committed **five times** |
| **one at a time, never reorder** | the tool loop's stop hook fired on exactly this — a progress report delivered while executable work remained |
| **the ledger is the authority, not my summary** | a self-derived total always reads "done" |
| **a falsifier RED on the original defect** | a guard never proven red is decoration. In #312 a guard stayed green while the real check was deleted, because `mrows.Err()` contains `rows.Err()` |
| **LIVE through the browser, no typed arguments** | the entire reason this loop exists. 88.1% of 4,175 recorded failures cannot occur when the caller writes the arguments |
| **deployed images verified current** | #310 and the docker-cp false-green: a stale image turns a passing test into a lie |
| **never type a denominator** | the most repeated instruction of the last loop, and still the easiest to break |
| **not terminal** | "mostly works" is how a loop ends without finishing |
| **defer, record, continue** | 29 DQs were raised this way and not one of them stopped the run |

## Before the first journey

1. **The stack is rebuilt** (2026-08-12) — all 33 buildable services, with
   `--build-arg VITE_API_BASE=` for the frontend, because a tsc failure otherwise serves a stale
   bundle and every finding downstream is suspect.
2. **Re-derive the denominator** from `loreweave_agent_registry` — do not read the RUNBOOK's table.
3. **Confirm the model** is still this account's active `chat` default in `user_default_models`
   (`google/gemma-4-26b-a4b-qat`, `lm_studio`) — confirm it, do not set it.
