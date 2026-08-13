# TOOL DEEP-DIVE RUNBOOK — 2026-08-13

Successor to [`2026-08-12-frontend-journey-loop-RUNBOOK.md`](2026-08-12-frontend-journey-loop-RUNBOOK.md),
whose declared denominators are both closed (12/12 workflows, 5/5 real skills). That loop went **wide**:
it walked declared journeys and took whatever defects fell out. This one goes **deep**: the unit is a
single **tool**, and a tool is not done until it is shippable.

This file is the source of truth for the loop. Its phases, denominator, pre-flight, bar and stop
condition override any prompt, summary or progress note.

---

## THE GOAL

> Ship individual tools at production grade, one at a time, proven live.
>
> **THE UNIT** — A TOOL is the unit of work. One cycle = one tool: run it live from plain prose in the
> browser, prove it works, investigate the DATA it actually wrote (never just the metric), and if it
> does not work, find out why and fix it **wherever it lives** — across any service — then run it
> again. Every defect found inside a tool's cycle still gets its own ledger row and its own falsifier.
> NEVER BATCH.
>
> **DEEP, NOT WIDE** — We do not need coverage. We do not need to rush to a total. We need each tool
> complete and shipped at high grade, not a POC. A tool touched but not shipped is not progress.
>
> **THE LOOP** — One tool at a time, in the order this RUNBOOK derives. Never choose, reorder, batch,
> skip or defer one. On `proven` or `blocked`, immediately derive the next and run it. Do not return
> control while executable work remains. The ledger is the progress authority — not this file, not any
> summary I write.
>
> **THE BAR — all four, for every tool**
> - **LIVE**: exercised through the BROWSER at the pinned frontend, driven by the model from plain
>   user prose. **IF I TYPE A TOOL ARGUMENT, THE TOOL IS NOT PROVEN.**
> - **DATA**: the tool's effect read back from the OWNING STORE — the rows, the values, the content —
>   not from its own response and never from a count alone. An explicit falsifier for the reading, and
>   NEVER a typed denominator.
> - **CODE**: for every defect, tests plus a falsifier proven RED on the ORIGINAL defect, and the
>   owning service's full suite green.
> - **SHIP**: the tool is audited past its happy path — schema honesty, its refusals, its gates, its
>   idempotency, its empty/absent case — because that is the difference between a POC and a product.
>
> **NOT TERMINAL** — "works", "tested", "investigated", "mostly works", "known issue", "ready for
> next", "continue?". Only `proven` or `blocked`. A failed verification does not advance the loop:
> investigate, fix, rerun, verify again.
>
> **FIXING** — Fix the defect where it LIVES — another service, the frontend, a skill body, a workflow
> row, a tool description, a contract. PROSE IS NOT THE LEVER: rewording a message is not a fix
> without new evidence.
>
> **BLOCKED BY A PRODUCT DECISION** — Record the question and its evidence as the next DQ, then
> continue. Do not ask, do not invent an answer. An unresolved question is not permission to stop.

---

## INHERITED, NON-NEGOTIABLE

Carried verbatim in force from the journey RUNBOOK:

1. **Pre-flight is by CONTENT, not by tag.** `container == image` does not imply `image == source`.
   Every entry: per-file md5 of every `*.py` under `services/<svc>/app` against `/app/app` in the
   running container for all 10 Python services (`difflines=0`), and for compiled services a grep of
   the running binary for a string literal introduced by that service's most recent commit.
   Timestamps are not evidence.
2. **A control that can refute my own claim runs BEFORE the claim is filed.** Several "defects" in the
   previous loop were killed by their own controls; that is the mechanism working.
3. **The ledger is the progress authority.** Counts are read from its rows, never typed.
4. **Live smokes that CREATE content use a throwaway book**, never the dogfood book.

---

## DENOMINATOR — derived, never typed

Re-derive at every entry. Never read a total out of this file.

```
SOURCE:  the ai-gateway's federated catalogue (tools/list), which is what the model can actually
         reach — not a repo grep, not a count of @mcp_server.tool decorators.
COHORT:  every federated tool, grouped by provider.
```

**Ordering** (fully determined, no discretion):

| Group | Membership | Order within group |
|---|---|---|
| **A** | tools with ≥1 recorded FAILED call in `loreweave_chat` | failure count desc, then name |
| **B** | tools with recorded calls and zero failures | call count desc, then name |
| **C** | tools never called | provider (most tools first), then name |

Rationale, so it is not re-litigated: group A is the demonstrably-not-shippable set, group B is what
real traffic depends on, group C is the untested tail. A tool's position is a measurement, not a
preference.

---

## THE CYCLE — one tool

1. **DERIVE** the next tool from the ordering above (live query, not from memory).
2. **READ** its schema, its contract row (if any), its owning handler, and every refusal it can raise.
   *(Memory: read the tool schema before the first call.)*
3. **LIVE** — open the pinned frontend, in a book that satisfies its precondition, and reach it with
   plain user prose. Record: was it reached at all, with what arguments, derived from where.
4. **DATA** — read the owning store for what it wrote or returned. The rows, not the count. State the
   falsifier for that reading (what would have to be true for the reading to be wrong).
5. **AUDIT** — past the happy path: the empty case, the absent case, the wrong-type case, the gate,
   the second identical call.
6. **DEFECT** — for each one found: its own row, its own falsifier proven RED on the original, fix
   where it lives, full suite of the owning service green, deploy verified BY CONTENT.
7. **RE-RUN** live. A fix that is not re-proven live has not been proven.
8. **CONCLUDE** `proven` or `blocked`, write the ledger row, commit.

---

## RUN CONFIGURATION (pinned)

- Frontend: `infra-frontend-1` → `http://localhost:5174`
- Model: this account's active `chat` default (`google/gemma-4-26b-a4b-qat` via `lm_studio`),
  not set for the run
- Driver: Playwright MCP, browser only
- Ledger: `contracts/tool-deep-dive-ledger.json`

---

## STOP CONDITION

The loop ends when every tool in the derived cohort is `proven` or `blocked`. It does not end on a
count, a report, a handoff, or a question that could have been answered by measuring.
