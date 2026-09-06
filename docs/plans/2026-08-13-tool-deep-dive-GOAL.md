# THE GOAL PROMPT — tool deep-dive loop

Reconciles: MCP Tool `_meta` Completeness Law + Tool Liveness · MCP Tool I/O Standard — the deep dive's per-tool verdict IS the liveness row's G1-G4 chain, run to conclusion on every shippable tool, with the I/O row supplying what a correct call and return look like.

> **STATUS: COMPLETE (superseded 2026-09-02).** This loop finished — every shippable tool is
> concluded and every defect row it opened is closed. The dated figures below are an honest
> SNAPSHOT of 2026-08-21 and are left as written; do not read them as current. Live counts are
> derived in `contracts/tool-deep-dive-ledger.json` (`gate.py audit` recomputes `progress` from
> the rows and refuses to let it drift) and in `docs/sessions/OPEN_DECISIONS.md` (generated,
> with a currency test).
>
> **WHY THE WORD MATTERS:** a plan that says ACTIVE is re-entered. This one said so for twelve
> days after it was done, which is how a finished stream gets re-served as work.
>
> **Originally — STATUS 2026-08-21: ACTIVE — v2.** The v1 directive was cleared after batch 18; this is its
> replacement, rewritten against the real state rather than re-dated. State when written, derived
> not typed: **109 of 198 shippable concluded** (81 proven, 28 blocked, 0 in flight), **89
> remaining**, batches 1-18 closed.
>
> **What v2 carries that v1 could not**, because each was learned by paying for it: run the
> control that would refute you BEFORE writing the fix (four hypotheses died to controls in
> batches 17-18, and one shipped fix was measured and refuted); prose is not the lever (now four
> refuted interventions); the PROGRESS rule (counts_toward_release != false — counting state
> alone read five too high); a ship_audit records what was EXERCISED; declare a UUID where it is
> ADVERTISED; and the explicit LEFTOVERS — DQ-T33/34/35 and two open defects.

Paste the block below as the session's `/goal`. Nothing else.

It is sized for `/goal`'s ~4000-character limit (currently **3736**). It carries **only** what a
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
is the source of truth: phases, denominator, ordering, pre-flight, stop condition.

STATE 2026-08-21: 109 of 198 shippable concluded, 89 remaining, 0 in flight.
Re-derive, never type: python scripts/toolloop/work_remaining.py

THE UNIT — one batch of five tools, exactly one active, derived in RUNBOOK order.
Never choose, reorder, skip or narrow. Cost never narrows the denominator.

THE GATE, NOT MY JUDGEMENT — python scripts/toolloop/gate.py check decides. It
reads evidence written BY THE RUN, so snapshots and repeat counts cannot be typed
by me. Non-zero exit = not concluded. NEVER EDIT THE GATE TO MAKE IT PASS.
`conclude` WRITES the ledger row; `gate.py audit` must stay clean.

THE BAR
LIVE: real chat path, plain prose, K>=3 as a distribution. IF I TYPE A TOOL
ARGUMENT, THE TOOL IS NOT PROVEN. A transport error is not a model result: re-run.
DATA: the OWNING store before/after, rows not counts. A read-intent turn that
CHANGED the store is a defect whatever the model said.
CODE: regression test + falsifier proven RED on the ORIGINAL defect, no
bystanders, full suite green, deployed and verified BY CONTENT (md5 per file,
every service sharing that tree). Restart ai-gateway after a description change.
SHIP: refusals, gates, tenancy, idempotency, empty/absent.

RUN THE CONTROL THAT WOULD REFUTE ME BEFORE WRITING THE FIX. Measured 2026-08-21:
four of my causal hypotheses died to a control in two batches, and one SHIPPED fix
was measured and REFUTED. PROSE IS NOT THE LEVER — four prose interventions
refuted. A tidy explanation is not evidence. A scenario premise can be wrong.

FIX THE INVARIANT, NOT THE INSTANCE — name it, enforce at ONE chokepoint, prove
against EVERY past incident of the class, then state what it does NOT fix.

PROGRESS — concluded = state in {proven,blocked} AND counts_toward_release !=
false. Counting state alone reads five too high (deprecated-but-proven rows).

EVIDENCE — a ship_audit records what was EXERCISED, never what is owed. Conclude
only from a clean arm; keep a superseded arm with its reason rather than deleting
it. A fixture that failed is evidence about my fixture, not about the tool.

DECLARE IT — an argument that is a UUID at the consuming end must say so where it
is ADVERTISED, and name its supplier. The description is the only declaration this
platform has: zero providers emit format:uuid.

NOT TERMINAL — only `proven` or `blocked`; never "works", "mostly", "ready".
A tool the model never called is not evidence about that tool.

COMPACTION IS NOT A STOP CONDITION — re-read the ledger, re-derive, resume.

BLOCKED BY A PRODUCT DECISION — record a DQ and continue; do not ask, do not
invent. LEFTOVERS TO CLOSE: DQ-T33, DQ-T34, DQ-T35, and two OPEN defects —
D-SILENT-TURN-NO-CARD-NO-PROSE (recording fixed, cause not) and
D-GROUNDED-REQUEST-ANSWERED-WITH-UNGROUNDED-PROSE.

SAFETY, STANDING: one throwaway book per scenario, provisioned and torn down,
NEVER the dogfood book; a read-only TOOL does not make a read-only TURN, the turn
is bounded by the whole advertised surface plus every standing approval. Auth
durably via /v1/auth/login from git-ignored docs/dev/LOCAL_TEST_ENV.md — never
scrape a browser token, never invent or scavenge a credential. SELECT before any
DML. Everything goes through the LLM provider layer; there is no local model.
A card for a COST-BEARING or IRREVERSIBLE tool is NEVER approved.

SETTLED, DO NOT RE-ASK: denominator = every non-deprecated federated tool (198).
DQ-T30 = (c). DQ-T3 = (a). Discovery is a rail step.

ORDER OF WORK — derive the next batch from the 89 remaining and run it. Do not
return control while executable work remains.
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
| DQ-T36 | The model will not chain a second tool call WITHIN one turn. What is the fix? | **OPEN — owner call, and SHARPENED by batch 30.** Batch 29 measured the world/map family failing 100/100 single-turn: UUID-only tools, suppliers `world_list`/`world_map_list`, never chained. Batch 30 asked the same tools the same sentences MULTI-TURN and four of five went to 5/5 — `world_map_remove_marker` walked FOUR hops (world_list → world_map_list → world_map_get → marker_id) on every run. **So the chain is walkable and the model can do it.** 🔴 AND THE ORIGINAL FRAMING WAS TOO BROAD — corrected 2026-08-21: the model DOES chain within a single turn elsewhere. Batch 28's `book_steering_delete` called `book_steering_list` AND the delete in the SAME turn on 4 of 5 runs, resolving the rule's name to an id and carrying it into the card (verified from the card's own proposed arguments via `card_args.py`). So this is not a general inability to chain; it is specific to the WORLD family, and the difference between the two is what an owner needs to look at. Declaring the supplier on every argument was shipped and REFUTED — it changed the model's words ("I'll list your worlds now to find it") and then the turn ended. Candidates: (a) a turn-level rule that a refusal naming a supplier must be followed by that call; (b) accept a NAME and resolve server-side; (c) leave it, and document these tools as multi-turn. Related and still open: `world_map_remove_region` surfaces 0/5 while its identical sibling surfaces 5/5, and when unsurfaced the model FABRICATED the deletion — a fresh D-CLAIMED-WRITE-WITH-ZERO-TOOL-CALLS. |
| story_state: 0 tokens | Expected? | **Not expected — investigate.** *(Done 2026-08-14: the measurement is `STORY_STATE_BLOCK_ENABLED=false`, deliberate; a separate real logic bug was found and fixed in the same pass and is INERT until the flag is on. See `2aa9169ae`.)* |

## RUNSTATE POINTERS — derived, never typed

* Progress: `contracts/tool-deep-dive-ledger.json` — `tools` rows with `state` ∈
  {`proven`,`blocked`} **AND `counts_toward_release` != false**. The flag is not optional: five
  proven rows are deprecated tools the denominator excludes, so counting state alone reads five
  too high (measured 2026-08-21 — `gate.py` had been reporting 114 against a true 109).
* Remaining: `python scripts/toolloop/work_remaining.py` — counts against the release surface.
* Next batch: `scripts/toolloop/derive-tool-order.py`, then `scengen.next_from_ledger()`.
* Conclusion authority: `python scripts/toolloop/gate.py check`.
