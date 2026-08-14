# THE GOAL PROMPT — tool deep-dive loop

Paste the block below as the session's `/goal`. Nothing else.

It carries **only** what a prompt can lose: the core policy, the owner's cleared decisions, and the
standing safety constraints. Every definition lives in
[`2026-08-13-tool-deep-dive-RUNBOOK.md`](2026-08-13-tool-deep-dive-RUNBOOK.md) — the phases, the
derived denominator, the pre-flight, the ordering, the run configuration, the stop condition, and
the precedent behind each rule below.

Written 2026-08-14, after a compaction lost the goal mid-loop. The predecessor
[`2026-08-12-frontend-journey-loop-GOAL.md`](2026-08-12-frontend-journey-loop-GOAL.md) is the format
this follows.

---

```
Execute docs/plans/2026-08-13-tool-deep-dive-RUNBOOK.md continuously.
The RUNBOOK is the source of truth: its phases, denominator, ordering, pre-flight
and stop condition all override this prompt.

THE UNIT
ONE BATCH OF FIVE TOOLS. Exactly one batch active. Derived in RUNBOOK order --
never chosen, reordered, skipped or narrowed. Batching is what makes the
ARCHITECTURAL fix visible; it changes the unit of work, never the standard of
proof, which still applies to each of the five individually.

THE GATE, NOT MY JUDGEMENT
scripts/toolloop/gate.py check decides whether a batch may be concluded. It reads
evidence written BY THE RUN, so the snapshots and repeat counts cannot be typed by
me. Non-zero exit means not concluded, whatever I believe. NEVER EDIT THE GATE TO
MAKE IT PASS.

THE BAR -- all four, for every tool
LIVE: the real chat path, driven by the model from plain user prose, K>=3 as a
  distribution. IF I TYPE A TOOL ARGUMENT, THE TOOL IS NOT PROVEN.
DATA: the owning store before and after -- the rows, not the count, and never the
  tool's own response. A read-intent turn that CHANGED the store is a defect
  whatever the model said. Explicit falsifier; never a typed denominator.
CODE: a regression test plus a falsifier proven RED on the ORIGINAL defect, the
  owning service's FULL suite green, deployed and verified BY CONTENT (md5).
SHIP: past the happy path -- refusals, gates, tenancy, idempotency, empty/absent.

FIX THE INVARIANT, NOT THE INSTANCE
Name the invariant the fix restores, enforce it at ONE chokepoint, and prove it
against EVERY past incident of that class. Adding a name to an allowlist is not a
fix. PROSE IS NOT THE LEVER: rewording a message is not a fix without new
evidence -- three prose interventions were MEASURED AND REFUTED on 2026-08-14.

NOT TERMINAL
"works", "tested", "investigated", "mostly works", "known issue", "ready for
next", "continue?". Only `proven` or `blocked`. A failed verification does not
advance the loop: investigate, fix, rerun, verify again.

CONTEXT EXHAUSTION AND COMPACTION ARE NOT STOP CONDITIONS
/compact and continue. Never hallucinate state across a compaction: re-read the
ledger and re-derive the queue, then resume. The ledger is the progress authority
-- not this prompt, not any summary I write.

BLOCKED BY A PRODUCT DECISION
Record the question and its evidence as the next DQ, then continue. Do not ask,
do not invent an answer. An unresolved question is not permission to stop.

SAFETY, STANDING
One throwaway book per scenario, provisioned and torn down. NEVER the dogfood
book. A read-only TOOL does not make a read-only TURN -- the turn is bounded by
the whole advertised surface plus every standing approval.
Auth durably via /v1/auth/login from git-ignored docs/dev/LOCAL_TEST_ENV.md.
Never scrape a browser token, never invent a credential, never scavenge one from
docs/plans/**.
Look before you delete: preview with SELECT before any DML.
Everything goes through the LLM provider layer. There is no local/direct model.
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
