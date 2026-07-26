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

**`paid` is ORTHOGONAL to `tier` — corrected 2026-07-09.** `tier` governs **mutation**; `paid` governs
**spend**. They are independent axes. `mcp-public-gateway` already models this correctly:

```ts
export type Tier = 'read' | 'paid_read' | 'write_auto' | 'write_confirm';
// ── paid_read (Tier-R but incurs cost — needs paid_read scope; P3 spend gate) ─
glossary_web_search: { tier: 'paid_read', domains: ['glossary'] },
```

A **paid read** is legitimate and must stay allowed in `ask` mode — a user researching in read-only
mode legitimately wants a web search. It must pass a **spend gate**, not a *write* gate.

**Derived rules (machine-checkable):**
1. A `paid` tool **MUST** pass a spend gate (approval-on-first-use + counted against the spend
   budget), **independent of its `tier`**. `paid` does **not** imply a write, and **must not** be
   coerced to tier `A`/`W` merely because it costs money.
   > ⚠️ **No internal spend gate exists today.** Verified: nothing in the chat tool-loop reads a
   > `paid`/spend concept, and the public gateway's own comment marks its spend gate as *"P3"*
   > (pending). So `glossary_web_search` is currently **completely ungated for spend** — this is the
   > live exposure, and building the gate is a **WS-D0 prerequisite** before any paid tool goes
   > hot-path.
2. A tool that enqueues a job **MUST** declare `async`.
3. `mcp-public-gateway`'s `paid_read` **derives from** `tier == R ∧ paid == true` rather than
   restating it in a hand-maintained table.

> **Superseded rule (was wrong, kept as a warning):** the first freeze said *"a `paid` tool MUST NOT
> be tier `R` — money is an effect."* That conflates spend with mutation and would have **blocked
> web search in ask mode**, breaking the single most legitimate read-only research flow. The public
> gateway's `paid_read` tier is the counter-example that disproved it.

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
- `tool_list` **MUST NOT** advertise a tool with a RED **G3**. A tool the LLM cannot successfully
  execute is worse than an absent one: it burns turns and produces false "saved!" claims.
- The passing set is **generated** (`matrix.json`), never hand-maintained.

**Phasing, amended 2026-07-10 (shipped in WS-D3).** The original phasing read *"warn in WS-D3,
reject from WS-D4"*. That was written when the matrix had a single, undifferentiated `RED`, which
conflated two failures with opposite owners — so rejecting on it would have blocked steps
referencing perfectly good tools. Now that the harness scores them apart, the gate splits three ways:

| verdict | `validateWorkflow` | `tool_list` / `tool_load` |
|---|---|---|
| `PASS` | admit | advertise |
| **proven broken** (`executes: false` — G3 RED or the capability re-probe failed) | **REJECT now** | **hide now** |
| `RED-SELECT` (`executes: true`; the model just never picked it) | admit, no warning | advertise |
| unproven / unchecked (`executes: null`, or no probe) | admit + `unproven_tool` **warning** | advertise |

Two consequences worth stating plainly:

1. **`RED-SELECT` does not gate a workflow.** A workflow step *names* its tool; nothing selects it.
   A model that can't pick the tool from its description is an **F5 description problem**, and
   hiding the tool from `tool_list` would *guarantee* it is never picked. Fix the description.
2. **`executes: null` must never be read as `false`.** "We didn't check" is not "it's broken".
   Blocking on unknown would reject every one of the ~200 tools that has no probe yet, and hiding
   them would empty the catalog. Both consumers therefore test for an **explicit** `false`.

**Implementation.** `contracts/tool-liveness.json` is generated by
`scripts/eval/tool_liveness/manifest.py`, which also writes the two byte-identical service copies
(Go `go:embed` and Python package data cannot climb out of their modules). A drift lock in each
service reds if a copy diverges — and it **fails**, never skips: a drift lock that quietly skips
reports green while checking nothing. The manifest carries the derived `executes` / `proven` fields
so neither consumer re-implements the verdict logic in its own language.

---

## CD5 · Universal vs domain-scoped tools — naming & placement law

> **A tool's name declares its scope. A tool's home declares who owns the capability.**

**Definition.** A tool is **universal** iff it needs **no domain context** to be callable — i.e. its
*required* args contain no `book_id` / `project_id` / `entity_id`.

**The law:**
1. A **universal** tool carries **no service prefix** (`web_search`, not `glossary_web_search`), and
   declares a scope of `user` **or** `none` — never `book`/`project`.
   *(Corrected 2026-07-10: this read "declares `scope: none`". That conflated "takes no **domain**
   scope argument" with "has no scope at all". `web_search` is universal by the definition above —
   its only required arg is `query` — yet it runs a caller-identity guard and spends the caller's own
   BYOK credential, so it is `scope: user`, exactly like its `settings_*` siblings on the same server.
   `scope: none` is for a tool that needs no caller identity at all. Conforming to the old wording
   would also have reddened provider-registry's own wire gate, which asserts every tool on that
   server is `user`-scoped — a useful signal that the rule, not the tool, was wrong.)*
2. A universal tool is **registered by the service that OWNS the capability** — for an outward call,
   that is the service holding it per the **provider-gateway invariant** (CLAUDE.md). A service that
   merely *wraps* a capability must not own its tool.
3. A **domain-scoped** tool keeps its `<domain>_` prefix.
4. **A rename never deletes.** The old name is retained as an alias tagged
   `_meta.visibility: "legacy"` (CAT-4, `mcp-tool-io.md`) — the standing project rule: deprecate,
   don't remove.
5. Because `_domain_of()` is **prefix-derived**, a universal tool needs an explicit C1 category home
   (see the C1 change below).
6. **⚠ The C-GW prefix gate is the real constraint on where a tool may live.** `catalog.ts:71` *drops
   (with only a warn) any tool whose name does not match an allowed prefix for its provider.* So:
   - a universal (unprefixed) tool's **host provider must allowlist its prefix**
     (`EXTRA_PREFIX_MAP`), else it vanishes from the federated catalog;
   - a **legacy alias keeps the old prefix and therefore cannot move services** — it is demoted
     *in place* on its original host.
   *(`providerFor()` is name-based, but its map is only populated by tools that survive this gate — an
   earlier draft of this contract got that wrong.)*
7. Retiring a name requires `_meta.superseded_by`, which today has **zero producers** — add a
   `WithSupersededBy` kit helper (Go) alongside `WithVisibility`/`WithAsync`.

**Adjudicated applications (verified, 2026-07-09):**

| Tool | Universal? | Evidence | Action |
|---|---|---|---|
| `glossary_web_search` | **YES** | required args = `query` only; description says *"it needs no book or entity"*; capability lives in **provider-registry** (`/internal/web-search`); `composition-service` independently clients that endpoint and *mirrors this tool's safety caps* | → **`web_search`**, **moved to provider-registry**, category `research`, `scope: none`, `paid: true`, tier `R`; legacy alias retained |
| `glossary_deep_research` | **NO** | requires `book_id` **and** `entity_id`; attaches draft `reference` evidence to one glossary entity; mints a cost confirm-card | **keeps its prefix**; only its missing `_meta` is a defect |

**Enforcement (lint):** a tool with **no required domain-context arg** but a `<domain>_` prefix is a
finding; a tool **with** a required `book_id`/`project_id` and **no** prefix is a finding.

---

## Dependency — a C1 change this track requires

CD5 forces a change to **C1 (the category enum)**, which is FROZEN and owned by **Track A**
(`../2026-07-09-agent-discoverability-and-workflow/contracts.md`). Per C1's own rule, the change is
recorded there and announced on the board.

> **C1 += `research`.** `web_search` has prefix `web`, which has no `GROUP_DIRECTORY` home. Rather
> than alias `web → knowledge` (wrong: `knowledge` is the *internal* KG; web search is *external*
> retrieval), mint a `research` category. Lockstep declarations: `find-tools.ts GROUP_DIRECTORY`,
> `tool_discovery.py GROUP_DIRECTORY`, `tool-policy.ts Domain` union, plus `_DOMAIN_ALIASES: web →
> research`. Implemented in **WS-D0f**.

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
- 2026-07-09 — **CD1 rule 1 CORRECTED.** Was *"a paid tool MUST NOT be tier R"*. Wrong: it conflates
  spend with mutation and would block web search in `ask` mode. `mcp-public-gateway`'s existing
  `paid_read` tier (*"Tier-R but incurs cost"*) disproved it. New rule: `paid ⊥ tier`; a paid tool
  passes a **spend gate**, independent of tier. Also recorded: **no internal spend gate exists today**
  — building it is a WS-D0 prerequisite before any paid tool goes hot-path.
- 2026-07-09 — **CD5 added** (universal vs domain-scoped naming/placement). Adjudicates
  `glossary_web_search` → `web_search` @ provider-registry, and `glossary_deep_research` stays.
  Forces **C1 += `research`** (Track A's frozen contract — announced on the board).
- 2026-07-11 — **WS-D4 partial: `executes ∧ effect` for the workflow-critical set.** The
  deterministic sweep proves `executes` (returned ok); the *workflow-critical* tools (derived
  live from `agent_registry.workflows` — today `glossary-bootstrap`'s 4 steps) are additionally
  held to an INDEPENDENT effect read-back (CD3 anti-oracle). A silent success (ok, no effect)
  folds to `executes: false` → rejected. Manifest gains an informational `effect_verified` flag
  (`proven ⊆ effect_verified`; the gate still keys on `executes`). 3/4 critical tools pass;
  `glossary_extract_entities_from_doc` is `paid` (LLM) so unverifiable at $0 — an honest gap in
  the sole curated workflow. The **hard reject → full `proven`** tightening (needs the NL probes)
  remains the open WS-D4 decision.
- 2026-07-11 — **CD4 implementation corrected to match the frozen table (no contract change).**
  `agent-registry`'s `livenessWarnings` fired the `unproven_tool` warning on `!proven`, which
  contradicts the CD4 verdict table: `executes: true` tools (incl. `RED-SELECT`) are "admit, **no
  warning**" — only `executes: null` (unchecked) warns. Warning on `!proven` flagged all 126
  sweep-executing tools, burying the ~73 with no execution evidence. Fixed the Go predicate
  (`toolUnchecked` = `executes == null` or absent; the dead `toolUnproven` removed). The chat-service
  `tool_list`/`tool_load` side was already correct (acts only on `executes: false`). The **hard
  reject** gate is unchanged (`executes: false`). WS-D4's warn→reject tightening — and whether it
  targets full `proven`, `executes ∧ effect`, or just `executes` — remains open.
