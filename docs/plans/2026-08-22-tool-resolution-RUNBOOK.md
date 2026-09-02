# RUNBOOK — the tool RESOLUTION loop

> **STATUS: COMPLETE (2026-09-02).** Its denominator was "the 65 tools that loop could not
> prove". That number is now ZERO: 0 open defect rows, 0 blocked tools, and every owner ruling
> built and stamped. The dated figures below are a snapshot of 2026-08-22 and stay as written.
> Live counts: `contracts/tool-deep-dive-ledger.json`, derived by `gate.py audit`.
>
> **Originally — STATUS 2026-08-22: ACTIVE.** Successor to
> [`2026-08-13-tool-deep-dive-RUNBOOK.md`](2026-08-13-tool-deep-dive-RUNBOOK.md), which is
> **COMPLETE**: 198 of 198 shippable tools concluded, 133 proven, 65 blocked, `gate.py audit` clean
> at 203 rows.
>
> That loop's job was to **find out**. This one's job is to **fix**. Its denominator is the 65
> tools that loop could not prove, partitioned into the eleven root causes that actually block
> them — and its unit is one root cause, not five tools.

---

## THE UNIT — one problem per cycle

The predecessor's unit was a batch of five tools, which is right when you are surveying and wrong
when you are repairing: five tools drawn in RUNBOOK order share no cause, so five separate
diagnoses compete for one cycle's attention. Here the unit is a **problem**, and a problem carries
every tool it blocks — 25 in the first, 1 in the last.

Exactly one cycle is active. Cycles are never chosen, reordered, skipped or narrowed. **Cost never
narrows the denominator.**

## THE DENOMINATOR — frozen, and machine-checked

[`contracts/tool-resolution-problems.json`](../../contracts/tool-resolution-problems.json) holds the
partition: **11 problems, 65 tools, MECE**, verified by script — 65 assigned, 65 distinct, 0
missing, 0 duplicated. Re-derive the runstate, never type it:

```
python scripts/toolloop/problem_remaining.py            # headline + the next cycle
python scripts/toolloop/problem_remaining.py --verbose  # every problem, every tool
```

Its two inputs are the partition and `contracts/tool-deep-dive-ledger.json`, whose per-tool state is
written by `gate.py conclude` and cannot be hand-edited into looking finished.

A tool leaves the denominator **only by reaching `proven`**. If a re-run blocks it on a *different*
named cause it **moves to that problem** and the total is unchanged. The total never shrinks any
other way.

## THE ORDER — computed, and it caught me typing

```
sort by (a) tools in the cluster whose MEASURED outcome was a FALSE STATEMENT REACHING
           THE AUTHOR, desc
   then (b) tools the problem blocks, desc
   then (c) problem id, asc
```

A tool that cannot be measured costs the loop time; a tool that lies to the author costs the author
their work. `problem_remaining.py` recomputes this on every run and **exits non-zero if the stored
`cycle` numbers disagree** — which they did on the first write, because I typed them.

| Cycle | Problem | Tools | Title |
|---|---|---:|---|
| 0 | *(no tools)* | — | **The deferred backlog and the ledger's own numbers** |
| 1 | `P1-SURFACE` | 25 | The advertised surface drops the tool, and the turn then reports the write as done |
| 2 | `P3-NAME-TO-ID` | 8 | The model will not walk a supplier chain that is on the same wire |
| 3 | `P5-SIBLING-WINS` | 5 | A sibling tool wins the request the tool was built for |
| 4 | `P2-FABRICATED-WRITE` | 1 | A turn asserts a write it did not make, or invents the material it acts on |
| 5 | `P4-PRECONDITION` | 17 | The fixture cannot reach the state the tool needs |
| 6 | `P6-DESCRIBE-NOT-RECORD` | 2 | The model describes the answer instead of recording it |
| 7 | `P7-FALSE-ABSENCE` | 2 | The write side confirms and the read that surfaces it returns nothing |
| 8 | `P8-ANSWERABILITY` | 2 | The answerability matcher needs a contiguous phrase |
| 9 | `P10-TOOL-LOAD` | 1 | `tool_load` is not used to read a schema |
| 10 | `P11-DISTRIBUTION` | 1 | Surfaced, occasionally chosen — and the costly half of the enum never came up |
| 11 | `P9-INTENT-GATE` | 1 | The world-setup intent gate shuts on the concrete request |

Cycles 9–11 look mis-numbered and are not: tie-break (c) is a string sort, so `P10` and `P11`
precede `P9`. The order is the rule's output. Leave it.

---

## CYCLE 0 — the deferred backlog, and the ledger's own numbers

Runs **first**, because both halves are inputs to every cycle after it.

**(a) The DQ dossier.** Thirteen open deferred questions — `DQ-T1`, `T2`, `T4`, `T5`, `T6`,
`T31`–`T35`, plus `T36`, `T37`, `T38` which are *not registered anywhere and must be added*. The
predecessor's rule was record-and-continue, never ask. **That rule is superseded** (owner,
2026-08-22): write each one up with its measured evidence and a **recommendation**, present all
thirteen **together in one sitting**, and implement the chosen answers as cycles. Do not decide them
alone; do not ask them one at a time.

Several are already load-bearing: `DQ-T36` **is** cycle 1, `DQ-T32` is cycle 8, `DQ-T31` is cycle
11, `DQ-T35` is `composition_generate`'s block inside cycle 2.

**(b) Ledger hygiene.** `contracts/tool-deep-dive-ledger.json`'s `progress` block disagrees with its
own rows in seven fields — a reader sees **40 of 198**. Its text claims it "is now RECOMPUTED from
the rows on every update"; that claim is false for exactly these fields, which is the drift its own
`_stale_block_note` was written to prevent. Recompute it, **make the recompute real**, and ship a
test that fails when `progress` disagrees with the rows. Then register the seven named findings that
exist only as prose: `D-LAZY-TAIL-UNUSED`, `D-EDGELESS-NODE-INVISIBLE-TO-THE-GRAPH-READ`,
`D-STORED-BUT-UNFINDABLE-UNTIL-INDEXED`, `D-EMPTY-TRANSLATION-SAVED-AS-A-VERSION`,
`D-EMPTY-SKILL-BODY-PROPOSED`, `D-RAIL-PINNED-TURN-NEVER-COMPLETES`,
`D-ANSWERABILITY-MISSES-WORD-ORDER`.

---

## THE PHASES OF A CYCLE

**1 — STATE THE CAUSE, AND SAY WHETHER IT IS KNOWN.** Some problems arrive with the mechanism
already measured (`P8`: the matcher wants a contiguous phrase). `P1` does not: three hypotheses —
ranking, tier/scope/family, batch composition — are **already retired by measurement**, and they are
listed in the contract so nobody spends a fourth cycle on them. A cycle whose cause is unknown
**opens with diagnosis and may not write a fix until the mechanism is named and proven by a
control.**

**2 — RUN THE CONTROL THAT WOULD REFUTE ME, BEFORE WRITING THE FIX.** Non-negotiable, and paid for:
in the predecessor, four causal hypotheses died to a control in two batches, one *shipped* fix was
measured and refuted, and one committed diagnosis had to be retracted. **PROSE IS NOT THE LEVER** —
five prose interventions refuted. A tidy explanation is not evidence. A scenario premise can be
wrong, and three fixtures were green-and-wrong.

**3 — FIX THE INVARIANT, NOT THE INSTANCE.** Name it. Enforce it at **ONE** chokepoint. Prove it
against **every past incident of the class**, not the one in front of you — the predecessor declared
the empty-artefact class closed and it was violated one batch later, because the check was a
snapshot and not a sweep. State plainly **what the fix does NOT cover.**

**4 — RE-RUN EVERY TOOL IN THE CLUSTER, LIVE.** `K>=5`, real chat path, plain prose. Not one
representative: the owner's bar is the whole cluster. Each tool lands `proven`, or lands `blocked`
on a **different, named** cause — which moves it to another problem and is recorded as the move.

**5 — CONCLUDE THROUGH THE GATE.** `gate.py check` decides; `gate.py conclude` writes the row;
`gate.py audit` must stay clean. **NEVER EDIT THE GATE TO MAKE IT PASS.**

**6 — WRITE IT UP AND COMMIT.** The cycle's write-up leads with what was *refuted*, not with the
number.

---

## THE BAR — carried from the predecessor, with one reversal

**LIVE.** Real chat path, plain prose, `K>=5` as a **distribution**. **IF I TYPE A TOOL ARGUMENT,
THE TOOL IS NOT PROVEN.** A transport error is not a model result — but *"transport error"* is a
symptom, never a diagnosis: **open the run's own `error` string.** The report's `err` column is a
COUNT, and reading "5" as a provider fault put a fixture bug in three commits and the handoff.

**DATA.** The **owning** store, before and after, rows not counts. A read-intent turn that changed
the store is a defect whatever the model said. A **seed assertion proves the row exists where I put
it** — not that the tool reads that store, not that the predicate is scoped to the thing under test.
Three fixtures were green and wrong this way: wrong store (`translation_jobs` vs jobs-service's
cross-service projection), wrong scope (`slug='glossary'` account-wide), wrong column
(`WHERE id=` on a table keyed `project_id`; `books.visibility`, which does not exist).

**CODE.** Regression test **plus** a falsifier proven **RED on the ORIGINAL defect**, no bystanders,
full suite green — a subset run hides the regression you shipped. Deployed and verified **BY
CONTENT** (md5 per file, every service sharing that tree), and **restart `ai-gateway` after any tool
description or synonym change**, or the federated tool-list stays cached. Verify a rebuilt image by
a whole-file property, not the symbol you just added.

**SHIP.** Refusals, gates, tenancy, idempotency, empty/absent. A `ship_audit` records what was
**EXERCISED**, never what is assumed.

### The reversal — approving a card that costs or destroys

> **OWNER, 2026-08-22.** A confirm card for a **DESTRUCTIVE or COST-BEARING** tool **MAY** be
> approved when the target was created by the run's own throwaway fixture and is torn down after.
> Never against the dogfood book. Never against a pre-existing object.

This overturns the predecessor's *"a card for a COST-BEARING or IRREVERSIBLE tool is NEVER
approved"*, which left ~10 tools with a structurally unreachable DATA bar. **It is written here so
no later session re-derives the old rule from the old GOAL and silently re-blocks them.**

Paid arms still run at `K=5` — the LIVE bar is a distribution, and a cheaper `K` would be a narrowed
denominator wearing a cost excuse. What is bounded is **waste**: the cheapest configured model, the
smallest legitimate unit of work, and **a card approved at most once per tool per cycle** — the
second approval proves idempotency and is the only repeat. Every approved paid card records the
model, the unit and the observed cost in its ledger row.

---

## THE HARNESS — unchanged, and it earned its guards

| | |
|---|---|
| `scripts/toolloop/fe_runner.py` | AG-UI SSE driver. `--repeats`, `--concurrency`, `--turn-timeout`. Substitutes `{book_id}` `{chapter_id}` `{project_id}` `{run_id}` `{run_word}` **into prompts as well as seeds** — an unsubstituted prompt cost batch 29 an arm. Runs `preflight_seed_asserts()` **before spending a turn**. |
| `scripts/toolloop/provision.py` | Throwaway fixture. `{run_word}` is pronounceable and its alphabet deliberately excludes `a`–`f`, so a nonce can never be read as a hex id. |
| `scripts/toolloop/gate.py` | `check` / `conclude` / `audit` / `refresh`. Reads evidence written **by the run**. |
| `scripts/toolloop/catalog.py` | Refuses to cache a surface declaring **less** than the cached one, and names the measured cause (a poisoned Docker layer; `docker compose build --no-cache`). It caught the recurrence live. |
| `scripts/toolloop/card_args.py` | Reads a card's proposed args from `chat_suspended_runs.pending_tool_call` **without approving it**. |
| `scripts/toolloop/ship_audit.py` | `--tenancy`. |
| `scripts/toolloop/problem_remaining.py` | **New.** The runstate of this loop. |

---

## STANDING SAFETY

One throwaway book per scenario, provisioned and torn down — **never the dogfood book**. A read-only
TOOL does not make a read-only TURN: the turn is bounded by the whole advertised surface plus every
standing approval. Auth durably via `/v1/auth/login` from the git-ignored
`docs/dev/LOCAL_TEST_ENV.md` — never scrape a browser token, never invent or scavenge a credential.
**SELECT before any DML.** Everything goes through the LLM provider layer; there is no local model.
Approving a destructive or cost-bearing card is permitted **only** under the reversal above.

## NOT TERMINAL

A cycle ends `cleared` or it does not end. There is no third state, and *"this cannot be measured"*
is a claim that needs a control — twice in the predecessor it was a diagnosis I had not yet done.

## STOP CONDITION

`python scripts/toolloop/problem_remaining.py` reports `remaining=0`, **and** `gate.py audit` is
clean, **and** the DQ backlog carries a decision for every open question. Nothing else stops the
loop.
