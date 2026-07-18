# WS-3a — Mode → capability binding (C6) + the pinned rail

**Track:** C (agent-discoverability umbrella) · **Size:** L · **Date:** 2026-07-11
**Drives:** S06 flagship ❌ → the *assent gap* ([S06 re-test](../eval/discoverability/2026-07-11-S06-flagship-retest.md)).

## The problem this must solve (evidence, not theory)

S06 had `glossary-bootstrap` **advertised** and the WS-5 steering directive **injected**, and gemma still
never called `workflow_load`. It improvised (`find_tools` → `plan_propose_spec`) and leaked the machinery
to the user (PlanForge ×27). Root cause:

> **The rail fires on a REQUEST, not on an ASSENT to the agent's own offer.** S01 passes because the user
> says *"help me set up the world info"*. S06 fails because the user only says *"yeah do it"* — assenting to
> an offer **the assistant made in its own words**. To use the rail the agent must (a) still hold its own
> offer and (b) recognise it as a workflow. It does neither.

**So advertising is not enough.** The fix must remove the model's need to *decide to load* the rail: put the
rail **in the context from turn 1**. That is exactly what C6's `inject_workflows` is for.

## Design

### C6 record (contract already frozen)

```
mode_binding: { mode: ask|write|plan, inject_skills: [code], inject_workflows: [slug], seed_tool_categories: [category] }
```
Stored per **System / user / book** (the 3 tenancy tiers, same as `workflows`/`skills`). Effective binding =
**union** of the three tiers (additive — a tier may only ADD; it never removes a lower tier's entry, and never
removes a static default). Generalizes today's single hardcoded `plan→plan_forge`.

### Storage — `mode_bindings` (agent-registry)

Mirrors `workflows` exactly: `tier ∈ (system,user,book)`, scope-key CHECK, partial UNIQUE per tier on
`(scope, mode)`. Arrays are `TEXT[]`.

### Read — folded into the existing `/internal/workflows` call

chat-service already fetches workflows **once per turn** with `user_id` + `book_id` + `surface`. Add `&mode=`
→ response gains `"mode_binding": {mode, inject_skills, inject_workflows, seed_tool_categories, sources{}}`.
One hop, one failure path, already degrade-safe (client returns `_EMPTY` on any error ⇒ no binding ⇒ today's
behavior exactly). `sources` carries the per-tier contribution so the effective value + its source tier are
visible (Settings & Config SET rule — no silent hidden default).

### Write — `GET/PUT /v1/mode-bindings/{mode}[?book_id=]`

User-authorable (SET: "would two users want different values?" → **yes**; a translator does not want the
co-writer rail). System tier is read-only to users (tenancy law). `mode` is enum-validated on write;
`inject_workflows` slugs must resolve to a workflow visible to that user (no silent no-op pin).

### Consumption (chat-service) — three effects, all additive

| Field | Effect | Seam |
|---|---|---|
| `inject_skills` | union into the injected skill set (surface-filtered, same as pins) | `resolve_skills_to_inject(binding_skills=…)` — new kwarg, default `[]` ⇒ no change for existing callers |
| `seed_tool_categories` | union into the surface's hot domains | `discovery_seed_for_surface(binding_categories=…)` |
| **`inject_workflows`** | **PIN: render the rail into the prompt + pre-activate its step tools** | reuses `workflow_load_result()` verbatim — one source of truth for rail rendering |

**The pin is the load-bearing part.** A pinned workflow is rendered by the *same* function `workflow_load`
uses, so the agent sees the identical ordered rail (steps, gates, async flags, `notes_md`, guidance) **without
having to call anything**, and its step tools are pre-activated under the same `HOT_SEED_TOKEN_BUDGET` ceiling
`workflow_load` already uses (no new budget regime). The directive then names the assent case explicitly:
*"…or agrees to an offer you made ('yes', 'do it') — execute the steps IN ORDER."*

An unresolved pin (slug not visible on this surface) is **dropped + logged**, never a silent no-op.

### System seeds

| mode | binding |
|---|---|
| `plan` | `inject_skills: [plan_forge]` — generalizes the hardcode (which STAYS as the degrade-safe fallback) |
| `write` | `inject_workflows: [vision-to-book]` |
| `ask` | none |

### the flagship `vision-to-book` rail (the thing worth binding)

A binding is useless without a rail worth pinning; `glossary-bootstrap` covers only movement C. vision-to-book is the
flagship spine — its steps ARE S06's movements C→F, and its `notes_md` **owns the vocabulary** (which is what
kills the jargon leak: no rail ⇒ no vocabulary owner). Surfaces `{book, editor}` (a bookless chat turn must
not carry a book-building rail). All backing tools verified present in the liveness manifest.

Steps: see-standards → adopt → apply(confirm) → read-back → capture-cast(`glossary_extract_entities_from_doc`)
→ save-cast(`glossary_propose_entities`) → apply-cast(confirm) → connect(`kg_project_create`,
`kg_project_entities_to_nodes`) → arc-plan(`plan_propose_spec`, async) → draft.

## Risks

- **Token cost of an always-on rail.** ~600-700 tok of rail + ~10 pre-activated tool schemas on every
  write-mode book turn. Measured against the `contextBudget` events in the eval (Context Budget Law), not
  asserted.
- **Wrong-rail noise** — a translation-focused write session carries a co-writer rail. Mitigated by
  `notes_md` scoping ("run this when the user is building/writing their book") and, structurally, by the
  binding being **user/book overridable** (that is precisely why C6 is a user setting, not an env flag).
- **Pin ≠ permission.** Pre-activation is *advertisement* only (re-confirmed twice in review-impl); every
  Tier-A/Tier-W gate still fires on execution.

## Verify

1. agent-registry Go suite + new `mode_bindings` tests (tiers, union, unresolved-pin rejection).
2. chat-service suite (binding union in skills/seed; pinned-rail render; degrade-safe when registry is down).
3. **Live eval** — re-run S06 flagship on a fresh empty book: does the assent land on the rail?
   Compare kinds/entities/projects/chapters + the jargon count + `contextBudget`.
