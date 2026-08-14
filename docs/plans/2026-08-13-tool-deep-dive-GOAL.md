# THE GOAL PROMPT — tool deep-dive loop

Paste the block below as the session's `/goal`. Nothing else.

It is sized for `/goal`'s ~4000-character limit (currently **3609**). It carries **only** what a
prompt can lose: the core policy, the owner's cleared decisions, and the
standing safety constraints. Every definition lives in
[`2026-08-13-tool-deep-dive-RUNBOOK.md`](2026-08-13-tool-deep-dive-RUNBOOK.md) — the phases, the
derived denominator, the pre-flight, the ordering, the run configuration, the stop condition, and
the precedent behind each rule below.

Written 2026-08-14, after a compaction lost the goal mid-loop. The predecessor
[`2026-08-12-frontend-journey-loop-GOAL.md`](2026-08-12-frontend-journey-loop-GOAL.md) is the format
this follows.

---

```
Execute docs/plans/2026-08-13-tool-deep-dive-RUNBOOK.md continuously. The RUNBOOK
is the source of truth: its phases, denominator, ordering, pre-flight and stop
condition override this prompt. Policy + cleared decisions:
docs/plans/2026-08-13-tool-deep-dive-GOAL.md.

THE UNIT — ONE BATCH OF FIVE TOOLS, exactly one active, derived in RUNBOOK order.
Never choose, reorder, skip or narrow it. Batching makes the ARCHITECTURAL fix
visible; it changes the unit of work, never the standard of proof, which applies
to each of the five individually.

THE GATE, NOT MY JUDGEMENT — `python scripts/toolloop/gate.py check` decides
whether a batch may be concluded. It reads evidence written BY THE RUN, so
snapshots and repeat counts cannot be typed by me. Non-zero exit = not concluded,
whatever I believe. NEVER EDIT THE GATE TO MAKE IT PASS.

THE BAR — all four, every tool:
LIVE: real chat path, model driven from plain user prose, K>=3 as a distribution.
  IF I TYPE A TOOL ARGUMENT, THE TOOL IS NOT PROVEN.
DATA: the OWNING STORE before and after — rows, not counts, never the tool's own
  response. A read-intent turn that CHANGED the store is a defect whatever the
  model said. Explicit falsifier. Never a typed denominator.
CODE: regression test + falsifier proven RED on the ORIGINAL defect, the owning
  service's FULL suite green, deployed and verified BY CONTENT (md5).
SHIP: past the happy path — refusals, gates, tenancy, idempotency, empty/absent.

FIX THE INVARIANT, NOT THE INSTANCE — name the invariant, enforce it at ONE
chokepoint, prove it against EVERY past incident of the class. Allowlisting a name
is not a fix. PROSE IS NOT THE LEVER: rewording is not a fix without new evidence
— three prose interventions were MEASURED AND REFUTED on 2026-08-14.

NOT TERMINAL — "works", "tested", "investigated", "mostly works", "known issue",
"ready for next", "continue?". Only `proven` or `blocked`. A failed verification
does not advance the loop: investigate, fix, rerun, verify again.

COMPACTION IS NOT A STOP CONDITION — /compact and continue. Never hallucinate
state across it: re-read the ledger, re-derive the queue, resume. The ledger is
the progress authority — not this prompt, not any summary I write. Never end a
turn citing context or token spend while a tool lacks a conclusion.

BLOCKED BY A PRODUCT DECISION — record the question and its evidence as the next
DQ, then continue. Do not ask, do not invent an answer. An unresolved question is
not permission to stop.

SAFETY, STANDING — one throwaway book per scenario, provisioned and torn down,
NEVER the dogfood book; a read-only TOOL does not make a read-only TURN, the turn
is bounded by the whole advertised surface plus every standing approval. Auth
durably via /v1/auth/login from git-ignored docs/dev/LOCAL_TEST_ENV.md — never
scrape a browser token, never invent or scavenge a credential. SELECT before any
DML. Everything goes through the LLM provider layer; there is no local model.

SETTLED, DO NOT RE-ASK — denominator is EVERY non-deprecated federated tool (198;
deprecated = visibility=legacy or superseded_by), because no ship means no
release; speed never narrows it. DQ-T30 = (c) a data question must be answered
from a tool call THIS TURN, independent of any rail. DQ-T3 = (a) stamp withheld
tools with the gate and how to open it. Lazy tail: make discovery a rail step.

ORDER OF WORK — DQ-T30 (c), then discovery-as-rail-step, then DQ-T3 (a) MEASURED
not merely shipped, then batch 4's three unconcluded tools, then derive the next
batch from the 158 remaining. Do not return control while executable work remains.
```

---

## THE OWNER'S CLEARED DECISIONS — settled, do not re-litigate

| # | Question | Decision |
|---|---|---|
| Denominator | Which tools must ship? | **Every non-deprecated federated tool.** *"they build for the workflows, we need ship them to make platform work, not because they slow or not, no ship mean this platform cannot release."* Speed is never a reason to narrow it. |
| Deprecated | Do legacy/superseded tools count? | **No.** Deprecated is abandoned after migration; the successor carries the traffic. |
| Consumer | Which model proves a tool? | The account's active `chat` default via the **provider layer** (`google/gemma-4-26b-a4b-qat`). Never bypass the provider-gateway rule. |
| DQ-T30 | A rail is DONE — what re-reads the data? | **(c)** A data question must be answered from a tool call **THIS TURN**, independent of any rail. The general fix and the most expensive. |
| DQ-T3 | Should `tool_list` name withheld tools? | **(a)** Stamp them with the gate and how to open it. |
| D-LAZY-TAIL-UNUSED | The lazy tail never fires. | **Make discovery a rail step.** |
| story_state: 0 tokens | Expected? | **Not expected — investigate.** *(Done 2026-08-14: the measurement is `STORY_STATE_BLOCK_ENABLED=false`, deliberate; a separate real logic bug was found and fixed in the same pass and is INERT until the flag is on. See `2aa9169ae`.)* |

## RUNSTATE POINTERS — derived, never typed

* Progress: `contracts/tool-deep-dive-ledger.json` (`tools` rows, `state` ∈ {`proven`,`blocked`}).
* Remaining: `python scripts/toolloop/work_remaining.py` — counts against the release surface.
* Next batch: `scripts/toolloop/derive-tool-order.py`, then `scengen.next_from_ledger()`.
* Conclusion authority: `python scripts/toolloop/gate.py check`.
