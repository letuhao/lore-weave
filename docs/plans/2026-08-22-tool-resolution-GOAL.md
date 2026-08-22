# THE GOAL PROMPT — tool RESOLUTION loop

> **STATUS 2026-08-22: ACTIVE.** Successor to
> [`2026-08-13-tool-deep-dive-GOAL.md`](2026-08-13-tool-deep-dive-GOAL.md), whose loop is
> **COMPLETE** — 198 of 198 concluded, 133 proven, 65 blocked, audit clean at 203 rows.
>
> That loop found out. This one fixes. Denominator: the **65 blocked tools**, partitioned into
> **11 root causes**, MECE and script-verified. Unit: **one problem per cycle**, carrying every
> tool it blocks.
>
> **Two owner decisions are baked in and reverse the predecessor**, so they are stated in the
> prompt rather than left to be re-derived: a destructive **or cost-bearing** card MAY be approved
> against a throwaway fixture, and the deferred questions are now **written up and decided**, not
> recorded and skipped.

Paste the block below as the session's `/goal`. Nothing else. Every definition — phases, partition,
ordering, harness, stop condition — lives in
[`2026-08-22-tool-resolution-RUNBOOK.md`](2026-08-22-tool-resolution-RUNBOOK.md).

---

```
Execute docs/plans/2026-08-22-tool-resolution-RUNBOOK.md continuously. It is the
source of truth: phases, partition, ordering, bar, stop condition.

STATE — never typed here, always derived:
python scripts/toolloop/problem_remaining.py

ORDER OF WORK — derive the next cycle from the remaining and run it. Do not return
control while executable work remains.

THE UNIT — ONE PROBLEM, exactly one active, carrying EVERY tool it blocks (25 in
cycle 1, 1 in the last). Never choose, reorder, skip or narrow. Cost never narrows
the denominator. A tool leaves it ONLY by reaching `proven`; re-blocked on a
DIFFERENT named cause it MOVES to that problem and the total is unchanged.

CYCLE 0 FIRST — (a) all 13 open DQs written up with evidence AND a recommendation,
presented TOGETHER for the owner; T36/T37/T38 unregistered, register them.
(b) the ledger's `progress` disagrees with its own rows — make it recompute, gate it.

CLEARED ONLY WHEN: the invariant is NAMED; enforced at ONE chokepoint with a
falsifier RED on an ORIGINAL instance and the full suite green; EVERY tool in the
cluster re-run LIVE at K>=5 and now proven, or re-blocked on a different named
cause; and the write-up says what the fix does NOT cover.

CAUSE UNKNOWN => DIAGNOSE FIRST; no fix until the mechanism is named and proven by
a control. Cycle 1 has three hypotheses ALREADY RETIRED — ranking, tier/scope/
family, batch composition. Do not spend a fourth on them.

THE GATE, NOT MY JUDGEMENT — gate.py check decides, conclude writes the row,
audit stays clean. NEVER EDIT THE GATE TO MAKE IT PASS.

THE BAR
LIVE: real chat path, plain prose, K>=5 as a DISTRIBUTION. IF I TYPE A TOOL
ARGUMENT, THE TOOL IS NOT PROVEN. "Transport error" is a symptom, not a diagnosis
— OPEN THE RUN'S OWN `error` STRING; the `err` column is a COUNT, and reading "5"
as a provider fault put a fixture bug in three commits.
DATA: the OWNING store before/after, rows not counts. A SEED ASSERTION PROVES THE
ROW IS WHERE I PUT IT — not that the tool reads that store, nor that I scoped it to
the thing under test. Three fixtures were green and wrong that way.
CODE: falsifier RED on the ORIGINAL, no bystanders, FULL suite (a subset hides the
regression you shipped), deployed and verified BY CONTENT md5, restart ai-gateway
after any description or synonym change.
SHIP: refusals, gates, tenancy, idempotency, empty/absent — EXERCISED not assumed.

RUN THE CONTROL THAT WOULD REFUTE ME BEFORE WRITING THE FIX. Four hypotheses died
to one, a SHIPPED fix was refuted, a diagnosis retracted. PROSE IS NOT THE LEVER —
five refuted. A scenario premise can be wrong.

FIX THE INVARIANT, NOT THE INSTANCE — name it, ONE chokepoint, prove against EVERY
past incident of the class (a snapshot is not a sweep — the empty-artefact class was
declared closed and violated one batch later), state what it does NOT fix.

NOT TERMINAL — a cycle ends `cleared` or it does not end. "Cannot be measured" needs
a control; twice it was a diagnosis I had not run.

OWNER 2026-08-22, REVERSING THE PREDECESSOR — DO NOT RE-DERIVE THE OLD RULE:
(1) a card for a DESTRUCTIVE or COST-BEARING tool MAY be approved when the
target was created by the run's OWN THROWAWAY fixture and is torn down after —
never the dogfood book, never a pre-existing object. Paid arms still run K=5; bound
WASTE instead (cheapest model, smallest unit, ONE approval per tool per cycle — a
second only for idempotency) and record model/unit/cost in the row. (2) DQs get a
recommendation and are DECIDED BY THE OWNER in one sitting, not by me.

SAFETY, STANDING — one throwaway book per scenario, provisioned and torn down,
NEVER the dogfood book. A read-only TOOL does not make a read-only TURN: the turn
is bounded by the whole advertised surface plus every standing approval. Auth via
/v1/auth/login from git-ignored docs/dev/LOCAL_TEST_ENV.md — never scrape a browser
token, never invent a credential. SELECT before any DML. Everything goes through
the provider layer; there is no local model.
```

---

## THE OWNER'S CLEARED DECISIONS — settled, do not re-litigate

| | |
|---|---|
| Denominator | the 65 blocked tools, partitioned into 11 problems. Frozen in [`contracts/tool-resolution-problems.json`](../../contracts/tool-resolution-problems.json). |
| Cleared bar | invariant fixed **and every tool in the cluster re-run LIVE**. Not one representative. |
| Spend | destructive **and** cost-bearing cards may be approved against a throwaway fixture. |
| DQs | recommendation written, owner decides, all thirteen in one sitting. |
| `DQ-T3` | (a) — shipped. `DQ-T30` (c) — proven. Do not re-ask either. |

## RUNSTATE POINTERS — derived, never typed

```
python scripts/toolloop/problem_remaining.py --verbose   # this loop
python scripts/toolloop/work_remaining.py                # the predecessor, 198/198
python scripts/toolloop/gate.py audit                    # must stay clean
```
