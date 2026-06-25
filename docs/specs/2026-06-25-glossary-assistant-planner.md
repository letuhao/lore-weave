# Glossary-Assistant — Plan-and-Execute Architecture

**Status:** DESIGN draft · 2026-06-25 · owner: glossary-service + chat-service + frontend
**Decision (this session):** plan-and-execute, scope = whole glossary-assistant (not just ontology).
**Why now:** the single ReAct agent loop has a high error rate building anything multi-step
(ontologies, bulk edits). Patching individual tools (batch, skill nudges, auto-scaffold) treats
symptoms; the root cause is architectural.

---

## 1. Problem & root cause

The glossary-assistant is a **single ReAct agent** in `chat-service/stream_service.py`: one tool-calling
loop (max 10 iterations for book-scoped), the static glossary skill as system prompt, and the **full
federated catalog (~130 tools / 8 domains) advertised every turn** (no discovery filter for book-scoped).

Observed failure modes (this session, a real ontology build):
1. **Narration without action** — the model writes "I'll now create…" and ends the turn with no tool call.
2. **Forgotten required params** — `level`, `max_results` omitted → arg-validation rejects (step-0 fail).
3. **No state awareness** — re-proposes already-created rows → conflicts (step-N fail).
4. **Wrong sequencing** — creates kinds before the ontology is scaffolded (mitigated by auto-scaffold).
5. **Tool overload** — ~130 tools + no plan → wrong tool / wrong order.
6. **`think` mode did not help** — so the gap is *structure*, not reasoning budget.

**Root cause:** PLANNING (understand intent + decompose, hard for an LLM) and EXECUTION (call N tools
exactly right, must be reliable) are **conflated in one fragile loop**. Building an ontology is a ~20-step
goal; each step is an LLM decision that can fail, so failure probability compounds.

## 2. Principle

> **Do the hard thing (plan) once, with structure. Do the reliable thing (execute) deterministically.**

Separate the two. A dedicated planner turns the user's goal into a **typed, validated plan**; a
**deterministic executor** applies it. The conversational agent shrinks from "improvise 20 fragile tool
calls" to **plan → review → execute** (3 reliable steps).

## 3. Architecture

```
User goal ("dựng ontology cho Vạn Cổ Thần Đế" / "fix all character attributes" / …)
  │
  ▼  glossary_plan            ── MCP tool (MCP-first invariant). Uses a CAPABLE model
     · reads current state (ontology, entity counts) via existing reads
     · structured-output → Plan = ordered list of TYPED operations (no narration)
     · idempotency-aware: sees current state, never proposes duplicates
  │
  ▼  Plan artifact (reviewable)   ── ONE confirm card whose payload IS the plan
     · preview rows = one per operation, human-readable; destructive ops flagged
     · (MVP) reuse the existing ConfirmCard; (later) a richer editable plan panel
  │
  ▼  glossary_confirm_action  ── the human approves the WHOLE plan ONCE (INV-1 gate)
  │
  ▼  effectExecutePlan        ── DETERMINISTIC executor (no LLM, no agent)
     · runs each op in dependency order via existing domain CORE funcs
     · idempotent (skip-existing), per-op outcome, partial-failure tolerant
     · returns {applied[], skipped[], failed[]} summary
```

Reuses, not rebuilds: the **confirm token / single-use / human-gate** infra (`action_confirm.go`), the
**batch effect** just shipped (`effectSchemaCreateKinds`), and the existing **domain core functions**
(`createKindFromParams`, `createBookKindCore`, `adoptBookOntologyCore`, entity create/edit, …).

### 3.1 The plan language (typed operations)

A **closed, discriminated union** the planner emits and the executor runs. Each op carries typed params and
an optional `rationale` (shown in the plan review). v1 set:

| `op` | params | core it calls | destructive |
|---|---|---|---|
| `adopt_genres` | `{genres: [code]}` | `adoptBookOntologyCore` | no |
| `create_kinds` | `{kinds: [{code,name,attributes[]}]}` | `createKindFromParams` (loop) | no |
| `add_attributes` | `{kind_code, attributes[]}` | `createAttrDefFromParams` | no |
| `edit_attribute` | `{kind_code, code, fields}` | `book_patch` core | no |
| `delete` | `{level, code, …}` | `book_delete` core | **YES** |
| `create_entity` | `{kind_code, name, attributes}` | entity-create core | no |
| `edit_entity` | `{entity_id, changes}` | entity-edit core | no |
| `research` | `{entity_id, query}` | `effectDeepResearch` | no (paid) |
| `sync` | `{choices}` | `applyBookSyncCore` | varies |

The executor enforces a **dependency order** (adopt → kinds → attributes → entities) and validates each op
against current state before running (re-validate at execute time, §13.5 spirit).

### 3.2 The planner (`glossary_plan`)

- **MCP tool** on glossary-service (MCP-first invariant: LLM-decides-actions logic = an MCP tool).
- **Input:** `{book_id, goal (NL), reference? (book blurb / sample text)}`.
- **Reads** current ontology (+ entity summary) so the plan is a *delta* against reality (no duplicates).
- **Model:** a **capable** model resolved via provider-registry — NOT forced to the chat's "Fast" model.
  Introduce a per-user **`planner` model role** (defaulting to a strong chat+tool model); see §6 Decision-1.
- **Output:** a **`Plan`** validated by structured-output (the op union schema). The model produces DATA,
  not prose — eliminating the narration failure mode at the planning step.
- **Mints** a confirm card with descriptor `execute_plan`, payload = the Plan, preview rows = the ops.

### 3.3 The executor (`effectExecutePlan`)

- Confirm effect for descriptor `execute_plan`. **No LLM, no agent** — pure code.
- `ensureBookScaffolded` once; then run ops in dependency order; each op idempotent (skip-on-conflict);
  collect `{applied, skipped, failed}`. A failed non-destructive op does not abort the rest (configurable);
  destructive ops can require an extra per-op confirm flag inside the plan.
- Returns a structured summary the agent reports verbatim (so it can't hallucinate the outcome).

### 3.4 The agent's shrunk role + skill

The conversational agent now: **understand intent → `glossary_plan` → present the plan → on approval
`glossary_confirm_action` → report the executor's summary.** The skill enforces this and forbids the agent
from calling individual write tools in a loop for multi-step goals. Single-op quick edits may still use the
direct tools.

## 4. Human-gate & safety (INV-1 preserved)

- The **plan review is the human gate** — the user approves the whole plan before any write. Replaces N
  per-op confirm cards with ONE plan approval.
- **Destructive ops** (`delete`, `merge`) are flagged in the plan and (Decision-2) may require a per-op
  toggle the user must explicitly enable, so "approve plan" never silently deletes.
- Untrusted-data discipline (INV-6) unchanged: research/web results stay DATA.

## 5. Phasing (XL+ → incremental, each shippable)

- **Phase 0 — DONE:** `glossary_propose_kinds` batch (one confirm → N kinds). Proves batch + auto-scaffold.
- **Phase 1 — MVP planner (ontology ops):** `glossary_plan` emitting `{adopt_genres, create_kinds,
  add_attributes, edit_attribute, delete}`; `execute_plan` descriptor + `effectExecutePlan`; reuse
  ConfirmCard to render the plan; skill routes the agent into plan→review→execute. **Validates the whole
  architecture on the highest-pain workflow.**
- **Phase 2 — entities + research + sync:** add `create_entity / edit_entity / research / sync` ops.
- **Phase 3 — richer UX + recovery:** an editable plan panel (toggle/edit ops before approve); re-plan loop
  on partial failure; planner sees prior failures.

## 6. Decisions (LOCKED 2026-06-25)

1. **Planner model — a configurable `planner` role with a strong default.** Add a per-user `planner`
   capability/role (like `rerank`) resolved via provider-registry: the user MAY pick which model plans, but
   it **defaults to one capable chat+tool model** (never the chat's "Fast" model). So planning is reliable
   out of the box and power users can override. *(User: "cho option để user chọn, nhưng mặc định là 1 model".)*
2. **Destructive ops — explicit per-op toggle.** `delete`/`merge` in a plan require the user to enable a
   per-op confirm toggle in the plan review; approving a plan never silently deletes. Preserves INV-1.
3. **Plan review UX (Phase 1) — reuse ConfirmCard.** Ops render as preview rows, approved as-is. No new FE
   for Phase 1; the editable plan panel is Phase 3.
4. **Executor atomicity — per-op idempotent + summary.** Robust to partial re-run (skip-existing), not one
   all-or-nothing transaction. Returns `{applied, skipped, failed}`.

**Build cadence:** spec LOCKED this session; **implementation deferred to a later session** (user: "chỉ chốt
spec, build sau"). Phase 1 implementation plan to be written at the start of the build session.

## 7. Risks

- **Planner model cost/latency** — one structured call per goal; far cheaper than the agent flailing, but a
  real provider call. Mitigate with the `planner` role + caching the state read.
- **Op schema coverage** — if the planner needs an op not in the union, it must degrade gracefully (emit a
  `note`/`unsupported` the agent surfaces) rather than inventing. The executor rejects unknown ops.
- **Scope creep (whole-assistant)** — bounded by phasing: Phase 1 is ontology-only; later phases add ops.
- **Two surfaces to keep in sync** — planner op schema (glossary) ↔ executor ↔ FE plan render. Keep the op
  schema as the single source; FE renders from preview rows (already generic).

## 8. Acceptance (Phase 1)

"dựng ontology cho <book>" → agent calls `glossary_plan` once → ONE plan card lists all genres+kinds+attrs
→ user approves ONCE → executor creates everything (idempotent) → agent reports the real summary. Zero
per-kind clicks, zero narration-without-action, zero forgotten-param retries.
