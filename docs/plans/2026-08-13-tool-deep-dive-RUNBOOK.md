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
> **THE LOOP** — In the order this RUNBOOK derives. Never choose, reorder, skip or defer. On
> `proven` or `blocked`, immediately derive the next and run it. Do not return control while
> executable work remains. The ledger is the progress authority — not this file, not any summary
> I write.
>
> 🔴 **AMENDED 2026-08-14 — THE UNIT IS A BATCH OF FIVE, AND THE FIX IS ARCHITECTURAL.** The
> original unit above was one tool per cycle, and this section said NEVER BATCH. That was right
> while every cycle needed a hand-built browser run; it is wrong now, and it was costing about
> fifteen cycles a day against a denominator of 285.
>
> Two things changed. First, [`scripts/toolloop/fe_runner.py`](../../scripts/toolloop/fe_runner.py)
> drives the real chat path unattended, with a throwaway book per repeat, so the per-tool cost is
> a scenario row rather than a session of my attention. Second — and this is the substantive part
> — batching is what makes the ARCHITECTURAL fix visible. One tool at a time produces one local
> patch at a time, and this loop has now shipped the same defect twice under that discipline:
> `book_update_details` starved from the hot seed in v1 (2026-07-21), `composition_list_outline`
> withheld at `domain_not_selected` in v2 (2026-08-13). Five tools failing the same way in one
> batch names the invariant; one tool failing alone names a symptom, and a symptom gets an
> allowlist entry.
>
> So: **five tools per batch, exactly one batch active, and a fix must name the invariant it
> restores and be proven against every past incident of that class.** Adding a name to an
> allowlist is not a fix. The per-tool bar below is unchanged and still applies to each of the
> five individually — batching changes the unit of work, never the standard of proof.
>
> **THE GATE, NOT MY JUDGEMENT** — [`scripts/toolloop/gate.py`](../../scripts/toolloop/gate.py)
> `check` decides whether a batch may be concluded. It reads evidence written BY THE RUN
> (`fe_runner --batch-out`), so the store snapshots and repeat counts it checks cannot be typed
> by me. A non-zero exit means the batch is not concluded, whatever I believe about it. Never
> edit the gate to make it pass.
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

   🔴 **A READ-ONLY TOOL DOES NOT MAKE A READ-ONLY TURN — USE A THROWAWAY BOOK FOR EVERY LIVE
   RUN.** Amended 2026-08-13 after cycle 11 damaged a real chapter. The cycle's tool was
   `glossary_get_entity` (tier R, reads nothing but the glossary), and the prose asked only to
   look up a character, so the dogfood book `Mị Đế` looked safe. The model could not find the
   entity, and instead of failing it reached for an unrelated WRITE: four `book_chapter_save_draft`
   calls that overwrote chapter 1's prose with *"This is a test."*. All four returned `ok=true`
   with no confirm card, because `book_chapter_save_draft` carries a standing `allow` in
   `user_tool_approvals` from 2026-07-11 — the gate was satisfied by a decision made weeks
   earlier, for a call the author never saw.

   The chapter was restored through the product's own `book_chapter_restore_revision` from the
   `before assistant save` snapshot the write itself had taken, and the restoration was verified
   by reading the live body back (author prose present, test string absent). But the rule that
   would have prevented it is the one above, applied to the TURN rather than the tool: **what
   the model may do in a turn is bounded by its whole advertised surface plus every standing
   approval, not by the tier of the tool under test.** Pick the book on that basis.

---

## DENOMINATOR — the RELEASE SURFACE (amended 2026-08-14)

🔴 **THE COHORT IS EVERY NON-DEPRECATED FEDERATED TOOL, AND THE REASON IS RELEASE, NOT COVERAGE.**
Owner's decision, 2026-08-14: *"all non deprecated tools because they build for the workflows, we
need ship them to make platform work, not because they slow or not, no ship mean this platform
cannot release."* So the set is not negotiable on grounds of effort, and **speed is never a reason
to narrow it**.

A tool is DEPRECATED when it carries `visibility=legacy` or `_meta.superseded_by` — the platform's
own machine-readable statement that it has been migrated away from. A deprecated tool is abandoned
after its migration; its successor carries the traffic, so it is not part of what ships.

Re-derived against the live catalogue. **This block is a DATED SNAPSHOT, not a source** — the
section below says never to read a total out of this file, and that applies here too.

```
                       2026-08-14   2026-08-21   2026-08-21(pm)
315  federated total        315          315          315
117  deprecated             117          117          117
198  SHIPPABLE                                                     <- the denominator
     concluded within it     30          109          198
     remaining              168           89            0
```

Re-derive both halves with:

```bash
python -c "import sys,json;sys.path.insert(0,'scripts/toolloop');import catalog;c=catalog.load();L=json.load(open('contracts/tool-deep-dive-ledger.json',encoding='utf-8'));dep={n for n,t in c.items() if (t.get('meta') or {}).get('visibility')=='legacy' or (t.get('meta') or {}).get('superseded_by')};ok=lambda v: v.get('counts_toward_release') is not False;d=sum(1 for v in L['tools'].values() if v.get('state') in ('proven','blocked') and ok(v));print(len(c)-len(dep),'shippable |',d,'concluded |',len(c)-len(dep)-d,'remaining')"
```

**The numerator obeys the same rule as the denominator**, and it did not always. `gate.py`
counted every terminal row regardless of `counts_toward_release`, so from the batch where
`conclude` started writing the ledger until 2026-08-21 the progress block read **114** when the
true figure against the shippable set was **109** — the five rows below were in the numerator and
not the denominator. Corrected, and `tools_concluded_including_deprecated` now carries the total
work done so the two can never be confused again.

That correction alone cut the remaining work from 280 to 168, and it moved five already-concluded
rows out of the count (`book_get`, `book_get_chapter`, `book_list_chapters`,
`glossary_list_chapter_links`, `glossary_web_search`) — kept with their evidence, marked
`counts_toward_release: false`, because the work happened and is still true about those tools.

By provider: composition 53, glossary 25, kg 20, world 17, book 16, plan 16, settings 12,
translation 12, registry 9, jobs 5, memory 5, catalog 2.

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
scripts/toolloop/dump-calls.sql          # the recorded-call dump AND its failure predicate
scripts/toolloop/derive-tool-owners.py   # tool -> provider -> repo service, from each provider's
                                         # OWN tools/list (never the tool-name prefix)
scripts/toolloop/derive-tool-order.py    # the A/B/C ordering, excluding concluded tools
```

🔴 **A FAILED CALL IS `error IS NOT NULL`, NEVER `ok = false`, AND THE PREDICATE LIVES IN
`dump-calls.sql` RATHER THAN IN A SESSION'S HEAD.** Two things set `ok=false` while the tool works
exactly as designed, and both mis-ranked the queue on 2026-08-13. A **gated proposal** — a Tier-A/W
call that mints a confirm card — records `ok=false, error=null, task.status='input_required'`;
counting those read `glossary_propose_curation` as 72 failures in 72 calls where this ledger's own
recorded figure is 29 in 72. **`error IS NOT NULL` reproduces 29 exactly, and that agreement is the
control for the predicate** — if it stops holding, the predicate has drifted. An **operator
decision** (`denied by user`, 23 corpus-wide) is the author pressing Deny; the tool never ran, so it
cannot have failed, and leaving it in put `kg_add_nodes` at the head of group A on the strength of
one denial — ranking a tool for investigation because its safety gate worked.

Ownership must also be stamped for the gateway-local trio. `derive-tool-order.py` treats an unknown
owner as *"cannot prove historical, so treat every failure as LIVE"* — fail-safe for a genuine
unknown, simply wrong for a tool we can name. Unstamped, that put `tool_list` at the head of group A
with 1180 *live* failures, every one of them dated 2026-07-20 and every one of them chat-service's
turn-level duplicate-call guard rather than the tool failing at all.

Both read their inputs from `$TOOLLOOP_WORKDIR` (`tools.json`, `owners.json`, `calls_ts.tsv`,
`svc_last_commit.tsv`, `ports.txt`, `providers.txt`, `itok.txt`). Dump those from Bash, not from
Python: `subprocess(shell=True)` on Windows is cmd.exe, which mangles `sh -c 'echo $VAR'` and yields
an empty string with no error.

---

## THE CYCLE — one tool

1. **DERIVE** the next tool from the ordering above (live query, not from memory).
2. **READ** its schema, its contract row (if any), its owning handler, and every refusal it can raise.
   *(Memory: read the tool schema before the first call.)*
3. **LIVE** — open the pinned frontend, ON THE SURFACE WHERE THE TOOL'S DOMAIN IS HOT, in a book
   that satisfies its precondition, and reach it with plain user prose.

   🔴 **THE SURFACE IS PART OF THE PRECONDITION, AND GETTING IT WRONG COSTS A WHOLE CYCLE.**
   `stream_service.py` states the rule: *universal (no editor/book) → ∅ hot (pure discovery);
   book-scoped (book_context) → glossary tools hot; editor (editor_context) → glossary +
   composition + book tools hot.* Cycles 22–24 were run on the universal `/chat` surface, where
   NO domain tool is seeded at all, and each was recorded `BLOCKED` on a `domain_not_selected`
   that was my testing error rather than a product limit — three conclusions that had to be
   withdrawn and re-run. Before the live run, decide which surface seeds the tool's domain and
   go there; if the tool is still withheld, read `chat_messages.withheld_tools` for the STAGE
   (`domain_not_selected` vs `hot_seed` vs `token_budget`) before concluding anything, because
   those are different findings. Record: was it reached at all, with what arguments, derived from where.
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

**Context exhaustion is not a stop condition — `/compact` and continue.** The ledger is committed and
`scripts/toolloop/` re-derives the queue, so every cycle is resumable by construction and compaction
cannot lose a conclusion. Never end a turn citing context, session length or token spend while a tool
lacks a conclusion, and never decline the next cycle on the grounds it might not fit. See
[`AGENTS.md`](../../AGENTS.md) § *Session continuity*.
