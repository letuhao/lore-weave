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
   Run [`scripts/tool-loop-preflight.sh`](../../scripts/tool-loop-preflight.sh) at every entry and
   require `PREFLIGHT_FAIL=0`. Part 1 is a per-file md5 of every `*.py` under `services/<svc>/app`
   against `/app/app`; Part 2 greps each compiled service's RUNNING BINARY for a string literal that
   must also be present in HEAD. Timestamps are not evidence.

   🔴 **PART 2 EXISTS BECAUSE PART 1 SILENTLY SKIPPED EVERY COMPILED SERVICE.** On 2026-08-13 the
   gate printed `glossary-service SKIP (no services/glossary-service/app)` and I read it as benign —
   it is Go, there is no `app/`. The glossary binary in the running container was then measured to
   PREDATE commit `02beee08c`: `already_trashed` and `glossary_user_restore` were in it,
   `KEEPS ITS CODE reserved` and `CANNOT re-add the same code` were not. **A SKIP that always prints
   is indistinguishable from a pass.** Each probe now asserts its literal is present in HEAD's source
   first, so an edited sentence fails loudly as `PROBE-ROTTED` instead of passing on a literal
   nothing emits any more.
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

**Ownership** is read from each provider's OWN `tools/list` (`AI_GATEWAY_PROVIDERS` gives
`provider=<url>`; the URL's hostname is the repo service), never from the tool-name prefix — a
consumer-local tool's name can lie about its owner and a prefix table misattributes it silently.
Measured 2026-08-13: 312 of the 315 federated tools are claimed by a provider; `propose_edit`,
`tool_list` and `tool_load` are gateway-local.

**Ordering** (fully determined, no discretion):

| Group | Membership | Order within group |
|---|---|---|
| **A** | tools with ≥1 recorded FAILED call in `loreweave_chat` | **live** failures desc, then total failures desc, then name |
| **B** | tools with recorded calls and zero failures | call count desc, then name |
| **C** | tools never called | provider (most tools first), then name |

A **live** failure is one recorded AFTER the last commit to the tool's owning service — i.e. one the
deployed code could still produce.

🔴 **THE `live` QUALIFIER IS A CORRECTION, MADE 2026-08-13 AFTER THE ORDERING MIS-RANKED.** The
first version ranked group A by total failures, which treats the whole corpus as a statement about
the current code. It is not. `glossary_propose_curation` ranked FIRST with 29 failures — and 26 of
them, its entire dominant mode, are dated 2026-08-10 06:28–07:03Z, while the commit that fixed them
(`cc41f8c2f`, *"the dispatch was dropping the field it then demanded"*) landed at 15:41Z the same
day. The ordering was pointing at a tool whose failures could no longer happen, and would have gone
on pointing there forever. Total failures stays as the tiebreak, so a tool with only historical
failures still sits in A rather than vanishing into B.

A tool already `proven` or `blocked` in the ledger LEAVES the cohort. Without that the loop
re-derives the tool it just finished, forever — and that is not hypothetical:
`glossary_propose_curation`'s live defect was fixed in **chat-service** (an argument repair) while
this ordering's cutoff keys on its **owning** service, glossary-service, whose last commit did not
move. The ledger is the progress authority; the ordering only decides what comes next *among the
unconcluded*.

Rationale, so it is not re-litigated: group A is the demonstrably-not-shippable set, group B is what
real traffic depends on, group C is the untested tail. A tool's position is a measurement, not a
preference.

**Reproducing the derivation** — it must not live only in one session's scratchpad:

```
scripts/toolloop/derive-tool-owners.py   # tool -> provider -> repo service, from each provider's
                                         # OWN tools/list (never the tool-name prefix)
scripts/toolloop/derive-tool-order.py    # the A/B/C ordering, excluding concluded tools
```

Both read their inputs from `$TOOLLOOP_WORKDIR` (`tools.json`, `owners.json`, `calls_ts.tsv`,
`svc_last_commit.tsv`, `ports.txt`, `providers.txt`, `itok.txt`). Dump those from Bash, not from
Python: `subprocess(shell=True)` on Windows is cmd.exe, which mangles `sh -c 'echo $VAR'` and yields
an empty string with no error.

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
