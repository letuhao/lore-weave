# POC P1 + P2 — measured on the live stack, 2026-08-03

**Why these exist.** The spec borrows its architecture from Entity Framework, Backstage, Temporal and
the MCP registry ecosystem. **None of those has a client that is an LLM** — a caller that passes
strings and can never fail to compile. The PO's instruction was therefore to *decide the architecture
by POC rather than refactor and discover the assumption was wrong*. Each POC below is designed to
**falsify** a spec requirement, not to confirm it.

Sources: `ai-gateway /mcp tools/list` (live, 315 tools) and `loreweave_chat.chat_messages.tool_calls`
(7,442 calls across 549 sessions). Both reproducible; commands in §4.

---

## P1 — Can a group hierarchy be derived from tool names? **NO.**

R2/R14.2 assume a tool's group (and, at scale, its path) can be organised from the name. Test: does
the second name segment form a taxonomy?

| level-1 prefix | noun-first level-2 | verb-first level-2 | mixed? |
|---|---|---|---|
| `composition` (107) | 89 | 15 | ✅ |
| `glossary` (54) | 26 | 26 | ✅ |
| `kg` (31) | 19 | 11 | ✅ |
| `book` (35) | 24 | 5 | ✅ |
| `plan` (16) | 4 | 9 | ✅ |
| `world` (17) | 11 | 1 | ✅ |
| `settings` (12) | 7 | 5 | ✅ |
| `translation` (12) | 3 | 8 | ✅ |

**8 of 8 mix nouns (`arc`, `motif`, `entity`, `chapter`) with verbs (`get`, `list`, `propose`) at the
same level.** `glossary` is an exact 26/26 split.

**Verdict — the path must be DECLARED, never parsed.** Any scheme deriving structure from the name
inherits this inconsistency, which is also the root reason `_domain_of` was always fragile. Settles
DESIGN Q15's "who decides a tool's path": the author, at registration, gate-checked.

Supporting scale facts, measured (not estimated): **315 tools · ~130k tokens of schema · 413 tokens per
tool** — higher than the 375 the spec first estimated. `composition` alone is 107 tools, a third of the
catalog, so the flat taxonomy fails today rather than at 3,000. And **17 level-1 prefixes exist while
`GROUP_DIRECTORY` declares 14** — three already unaccounted for.

---

## P2 — Is the infinite loop caused by ambiguous tool errors? **PARTLY — and the larger half is us.**

R10 (the error contract) is premised on the loop being driven by errors the model cannot act on. Test:
autopsy every tool call in the real history.

### The shape of the problem

| | |
|---|---|
| tool calls | **7,442** across 549 sessions |
| failed (`ok=false`) | **4,007 — 54% of every call ever made** |
| byte-identical repeats (same session, tool, args) | **5,508 — 74% of all calls** |
| of those repeats | 3,669 error · 1,839 success |

### 🔴 The finding that changes the spec

Of 3,976 errors carrying text, **58% are not tool failures at all — they are our own loop-breakers'
output**:

| count | error text |
|---|---|
| 1,180 | *"You have already called `tool_list` with these exact arguments this turn and it returns the SAME list every time"* |
| 495 | *"You have already called `book_get` … it returned the IDENTICAL …"* |
| 263 | *"`kg_project_create` already ran this turn … reported created=false"* |
| 157 | *"`find_tools` has been called with no `intent` N times this turn — STOP…"* |
| 86 | *"`book_chapter_save_draft` keeps being called with missing/blank required arguments — STOP."* |

**2,318 of 3,976 errors (58%) are breaker feedback — 31% of every tool call in the system.** Each is a
call the model emitted, the tool never ran, and a full tool-loop pass was burned re-sending the entire
context.

**The breakers are participants in the loop, not terminators of it.** The breaker returns prose → the
prose enters context → the model reads "STOP" and calls again → the breaker fires again. This is the
context-contamination mechanism observed in our own production data.

> **A message cannot stop a model. Only an absent affordance can.**

The repo already discovered this empirically and wrote it down at `stream_service.py:1905-1911`:
*"Short-circuiting DISPATCH isn't enough; take the tool OFF THE WIRE so it physically cannot be
re-emitted."* The de-advertise escalation is the mechanism that works. **The messages are the mechanism
that fails, and they outnumber real errors 3:2.**

### R10's taxonomy, tested against real tool errors only

Excluding breaker output, the 1,658 genuine tool errors classify well:

| bucket | count | share |
|---|---|---|
| `retryable_modified` | 962 | 58% |
| `terminal_permanent` | 415 | 25% |
| UNCLASSIFIED | 277 | 17% |
| `retryable_transient` | 4 | 0% |

**83% bucket deterministically.** R10's taxonomy is sound — but it addresses **42% of error volume**,
not the loop's dominant driver. `retryable_transient` being ~0 is itself informative: these are not
flaky-network loops, they are *the model being wrong the same way repeatedly*.

### Concentration

Breaker storms occur in **73 of 549 sessions (13%)**, and the **top 5 sessions produce 66%** of all
breaker output. The median session is healthy; the failure is a tail that consumes the budget.

### Consequences for the spec

1. **R10 stays, re-scoped honestly.** It fixes the 42% and improves error quality. It is **not** the
   loop fix, and its DoD must not claim to be.
2. **The loop fix is R4/R5** — `excluded_by` withholding the affordance — promoted in priority. Add
   the rule this POC produced: **a guard withholds; it does not argue.** Returning a "STOP" string as
   a tool result is itself a defect, because the tool result is exactly the channel the model is free
   to ignore.
3. **R14 is urgent, not speculative.** `tool_list` is the **single largest loop source in the system**
   (1,180 breaker fires). The tool built to fix discovery is the biggest generator of the failure it
   was meant to fix — measured, in production data.
4. **The 54% failure rate is itself the headline.** No amount of prompt or skill work matters while
   more than half of every tool call fails.

---

## P2b — Where does the context budget actually go? **The static surface, not the conversation.**

The PO asked whether the budget is consumed by stuffing tool input/output into the session and keeping
it there as conversation. Measured over 2,029 messages carrying `context_breakdown`:

| category | avg tokens / message | share | lifetime total |
|---|---|---|---|
| **`mcp_tool_schemas`** | **11,725** | **41%** | 23.8M |
| **`skills`** | **9,162** | **32%** | 18.6M |
| `history` (the actual conversation) | 4,424 | 15% | 9.0M |
| `frontend_tool_schemas` | 2,137 | 7% | 4.3M |
| **`tool_results`** | **1,146** | **4%** | 2.3M |

**Answer: no.** Tool output is 4% and conversation history is 15%. `tool_result_token_cap` and
compaction are working — that part of the system was fixed and stayed fixed.

**80% of every turn is tool schemas plus skill bodies** — the static surface, re-sent in full on every
pass, before the conversation contributes a word.

### Why this compounds with P2

P2 measured that **74% of tool calls are byte-identical repeats**, and each repeat is another
tool-loop pass. Each pass re-sends the static surface.

> The loop does not merely waste calls — **it re-pays the 80% on every iteration.**
> Loop × static surface. Two problems we had been treating separately **multiply**.

This is the complete explanation of *"local patching cannot save the repo"*: cutting the loop without
cutting the surface still pays 23k per pass; cutting the surface without cutting the loop still pays
it N times.

### Two surprises in the same data

**1 · Schema cost does not rise with tool-call count — it falls.**

| tool calls in the turn | messages | avg `mcp_tool_schemas` |
|---|---|---|
| 0 | 1,359 | **13,033** |
| 1–2 | 304 | 9,573 |
| 3–5 | 171 | 11,259 |
| 6+ | 195 | 6,377 |

Turns that call *nothing* carry the **largest** tool surface (rail and curated modes narrow it for the
turns that do work). **We pay ~13k tokens of tool schema on conversational turns that never call a
tool.** No requirement currently covers this; it is the cheapest large saving on the board.

**2 · `skills` is 32% of all context while `lazy_skill_bodies` defaults to True.**

That flag exists precisely to *not* inject skill bodies. 9,162 tokens per message says it is not
achieving its purpose — consistent with `AUDIT.md` §2.3, where the hot-seed and the prompt are
computed under opposite `lazy_bodies` assumptions. The audit found the *mechanism*; this is its
*price*.

### Consequences for the spec

1. **R14 is the budget fix, not only the scale fix** — it attacks 41% directly.
2. **A 32% slice has no requirement covering it.** Skill-body injection needs the same
   budgeted, explained treatment R4 gives tools.
3. **New rule: a turn that offers no tools must not pay for tool schemas.** Currently the reverse is
   true.

---

## 3 · What P1 and P2 settle, and what they do not

| DESIGN question | settled by | answer |
|---|---|---|
| Q15 who decides a tool's path | P1 | declared at registration; parsing is impossible |
| Q3 group granularity | P1 (partly) | `composition` at 107 must split; the *shape* still needs Q14 |
| Q10 which breakers R10 deletes | P2 | the ones that argue: `tool_list` cap, `book_get` repeat, blank-args, `find_tools` no-intent |
| R10 scope | P2 | valid for 42% of errors; not the loop fix |

**Still open and still needing evidence:** Q14 (tool identity — P3, retrospective over git history),
Q16/Q18 (retrieval backend and budget numbers — need measurement), and R14's flat-cost claim (P4, the
synthetic 3,000-tool catalog).

---

## 4 · Reproduce

```bash
# P1 — live catalog
curl -s -X POST http://localhost:8218/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "X-Internal-Token: $INTERNAL_SERVICE_TOKEN" -H 'X-User-Id: <uid>' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# P2 — tool-call history
docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -tAc "
  select json_agg(row_to_json(x)) from (
    select session_id::text sid, created_at, tc->>'tool' tool, (tc->>'ok')::boolean ok,
           left(coalesce(tc->>'error',''),200) err, md5(coalesce(tc->>'args','')) argsig
    from chat_messages, jsonb_array_elements(tool_calls) tc
    where tool_calls is not null and jsonb_array_length(tool_calls) > 0) x;"
```

Both are read-only. P2 reads the dogfood history of the shared dev database; no cleanup is performed
and none is needed.
