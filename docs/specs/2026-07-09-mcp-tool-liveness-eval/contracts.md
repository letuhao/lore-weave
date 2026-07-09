# Track D — Frozen Contracts (CD1–CD4)

**Status: FROZEN 2026-07-09.** Track D owns these. Other tracks code against them.
Changing one is a cross-track decision (it moves the ship gate).

Every claim below was verified against source before freezing — see `README.md` §8 for the
evidence, and the **Rejected findings** section at the bottom for what did *not* survive.

---

## CD1 · The `_meta` completeness law

> **Every MCP tool declares what it is. An absent declaration is a defect, not a default.**

| Field | Required | Values | Meaning |
|---|---|---|---|
| `tier` | **always** | `R` \| `A` \| `W` \| `S` | R=read/inert · A=auto-commit + undo · W=mints `confirm_token` · S=schema/secret |
| `scope` | **always** | `book` \| `project` \| `user` \| `none` | declarative today (no runtime consumer) — keep accurate |
| `async` | **iff it starts a background job** | `true` | "called" ≠ "done"; the runner annotates the step, the agent must watch the job |
| `paid` | **iff the call can spend real money** | `true` | **NEW** — see below |

**The load-bearing rule:** consumers read `_meta.tier` to gate execution, and an **absent tier
silently defaults to `R` (read/inert)**. That default is a back-compat crutch, *not* permission to
omit. An untiered write is therefore executable in read-only **ask** mode and skips the Tier-A
approval card, the per-op auto-write caps, and the write budget. This exact hole was found and fixed
in knowledge-service (`f191cb858`) and **still exists across glossary-service** (verified: ≥27 of 35
scanned tools carry no `Meta:`).

**`paid` is new and justified.** Today `mcp-public-gateway`'s `TOOL_POLICY` hand-maintains a
`paid_read` scope tier — knowledge duplicated away from the tool that owns it, which drifts. The
durable signal belongs on the tool. Kit additions mirror `async`:
- Go: `lwmcp.WithPaid(m)` (alongside `WithAsync`)
- Py: `require_meta(..., paid=True)`

**Derived rules (machine-checkable):**
1. A `paid` tool **MUST NOT** be tier `R`. Money is an effect. *(Today `glossary_web_search` and
   `glossary_deep_research` are untiered ⇒ `R` ⇒ callable in ask mode with no approval card. This is
   live, unmetered spend exposure — the highest-severity finding in the inventory.)*
2. A tool that enqueues a job **MUST** declare `async`.
3. `mcp-public-gateway`'s `paid_read` classification **derives from** `_meta.paid` rather than
   restating it.

**Enforcement — per service, on the REAL `tools/list` wire:** a regression test asserting every
advertised tool declares a valid `tier` + `scope`, that `paid ⇒ tier != R`, and that the known
job-starters declare `async`. Reference implementation already shipped:
`services/knowledge-service/tests/test_mcp_server.py` (`…_every_tool_declares_meta_tier_and_scope`).
A new untiered tool must fail CI, not ship.

---

## CD2 · The `propose_*` semantics law

> **A `propose_*` tool changes nothing canonical at call time.**

`propose_*` is currently **overloaded** across two *legitimate* behaviors, with no declared rule
separating them — so neither an LLM nor a human can tell from the name whether a confirm round-trip
is required:

| Pattern | Tier | What happens at call time | Example |
|---|---|---|---|
| **token** | `W` | mints a `confirm_token`; **writes nothing** | `glossary_propose_merge`, `glossary_propose_kinds` |
| **draft** | `A` | writes a clearly-marked **pending/draft** row that a human must approve to become canonical | `glossary_propose_entities`, `kg_propose_edge`, `glossary_propose_translation` (`confidence='draft'`) |

**The law:**
1. A `propose_*` tool **MUST** be tier `W` (token) or tier `A` (draft). It **MUST NOT** be tier `R`.
2. A `propose_*` tool **MUST NOT** mutate canonical/live state at call time.
3. A tool that *does* mutate canonical state at call time **MUST NOT** use the `propose_` prefix.
4. The tool's **description MUST state which pattern it is** — "returns a confirm_token; a human
   confirms" *or* "writes a draft awaiting approval" — because that is the only signal the model gets.

Tier already encodes the distinction (`W`=token, `A`=draft), so **no new `_meta` field is needed** —
but rule 1 is only enforceable once CD1 lands (today most `propose_*` glossary tools are untiered).

**Enforcement:** a test asserting `name matches /propose/ ⇒ tier ∈ {A, W}`, plus the CD1 wire gate.

---

## CD3 · The liveness gates (G1–G4) + matrix schema

For each tool, a **black-box natural-language ask** (never the tool name) is sent to a real mid-tier
model on a real stack. Four gates, all four required to pass:

| Gate | Assertion |
|---|---|
| **G1 · SELECT** | the model called this tool |
| **G2 · SHAPE** | args schema-valid: required present, enums honored, ids well-formed |
| **G3 · EXECUTE** | returned without `isError`; **Tier-W: the `confirm_token` round-trip completed** |
| **G4 · EFFECT** | the system actually changed — read back via an **independent path** (DB/REST), never the domain's own read tool (a shared bug would make both agree). Async: poll to terminal, assert the **artifact**, not the job id. |

**G4 is the contract.** Every harness in the repo today stops before it (`README.md` §1).

`matrix.json` row schema (frozen):
```json
{ "tool": "glossary_propose_entities", "service": "glossary", "tier": "A",
  "async": false, "paid": false, "probe": "<the NL ask>",
  "G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS",
  "evidence": { "call": {...}, "readback": {...} },
  "status": "PASS | RED | UNTESTED-PAID | WAIVED", "notes": "" }
```

**Read-tool G4:** a read tool passes G4 when its result is consistent with the **seeded fixture** —
not merely "returned 200".

---

## CD4 · The ship gate

> **A curated workflow MUST NOT reference a tool that has not passed G1–G4.**

- Wire into the C3 authoring path (`validateWorkflow`, agent-registry): a step whose `tool` is not in
  the **liveness-passing set** is rejected — or admitted with a loud `unproven_tool` warning.
  *(Phasing: warn in WS-D3, reject from WS-D4. Track A owns `validateWorkflow`; coordinate.)*
- `tool_list` **MUST NOT** advertise a tool with a RED **G3**. A tool the LLM cannot successfully
  execute is worse than an absent one: it burns turns and produces false "saved!" claims.
- The passing set is **generated** (`matrix.json`), never hand-maintained.

---

## Rejected findings (recorded so they don't resurface)

- ~~"`glossary_propose_translation` / `glossary_propose_aliases` are direct writes despite the
  `propose_` name."~~ **FALSE.** Verified: `upsertDraftTranslation` inserts with
  `confidence='draft'` (`pipeline_translate_tool.go:294-299`) — it is the legitimate *draft* pattern,
  identical to `glossary_propose_entities`. No rename needed. The real gap is that the two patterns
  were never *declared* — which is what CD2 fixes. (`glossary_propose_aliases` also touches
  `entity_attribute_values`; confirm it writes only draft/alias rows during WS-D1 — treat as
  **audit**, not a proven defect.)
- **Not yet proven:** that `composition_motif_mine`, `composition_arc_import_analyze`,
  `composition_conformance_run`, and `plan_propose_spec(mode=llm)` all enqueue background jobs.
  Verified only that composition declares `async_job=True` **exactly once**
  (`composition_generate`). WS-D0c must *audit each* before marking it `async` — do not mark on the
  inventory's word.

---

### Change log
- 2026-07-09 — initial freeze (CD1–CD4). CD1 adds the new `_meta.paid` field. CD2 rewritten after
  source-verification rejected the "propose = direct write" finding.
