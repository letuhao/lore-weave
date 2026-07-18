# Spec: Agent Discoverability, Modes/Permissions, and the Workflow Layer

**Date:** 2026-07-09 · **Branch:** `feat/context-budget-law` · **HEAD:** `a32829f9f` · **Status:** CLARIFY
COMPLETE — all 9 decisions resolved (§7); ready for parallel PLAN/BUILD via the workstream DAG (§6b). This
is the *umbrella* doc that spawns several independent, session-ownable workstreams.

**Origin:** External cold-start MCP discoverability audit
[`D:\Works\novels\mi_de\loreweave-mcp-feedback.md`](../../../../novels/mi_de/loreweave-mcp-feedback.md)
(2026-07-07 → 2026-07-09, its own capstone at §"ARCHITECTURAL: `find_tools` semantic search is the
wrong primitive") + three user reflections (below) + a 5-thread code investigation run 2026-07-09.

**Prior art this supersedes/absorbs:**
- [`docs/plans/2026-07-07-mcp-discovery-and-reliability-hardening.md`](../../plans/2026-07-07-mcp-discovery-and-reliability-hardening.md)
  — the *tactical* track (enumeration fallback, retry-cap, embeddings). Shipped/partly-shipped. This
  spec reframes it as a stepping stone, not the destination.
- [`docs/plans/2026-07-07-intent-skill-router.md`](../../plans/2026-07-07-intent-skill-router.md) — Part F
  (embedding-based skill router, shipped as `skill_router.py`). Kept, but demoted from "the answer" to
  "an optional convenience layer" per the redirection below.
- [`docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md`](../2026-07-07-skill-authoring-and-mcp-exposure-standard.md)
  — the skill contract (Parts A–E shipped). Extended here, not replaced.

---

## 0. Executive summary

**One root cause, three surfaces.** LoreWeave has ~193 federated MCP tools + 7 admin across 11
categories, but **the agent has no deterministic, complete way to answer "what can I do here?" and no
curated procedure for "do this multi-step job for me."** Discovery is gated behind a *non-deterministic
semantic top-K search* (`find_tools`), and there is *no first-class end-user Workflow object at all*.
A capable model brute-forces around this; a mid-tier model loops on `find_tools` and gives up — the
exact user-visible failure ("a weaker model couldn't add entities to the book").

**The fix is a symmetry.** Tools, skills, and workflows should each expose the same two deterministic
primitives — **`list(category)`** (complete, unranked, enum-scoped) and **`load(name | [names] |
category)`** (exact schema/body, no guessing) — with semantic search kept only as an *optional* layer
on top, never as the sole gate and never able to make a real capability unreachable. Workflows are the
net-new primitive: a **tiered, listable, loadable object that declares a machine-readable ordered tool
sequence** (with the existing propose→confirm gates), so a weak model *invokes* a workflow instead of
*discovering* one.

**Faithful correction to the premise (important — see §3).** Two of the three reflections are partly
out of date against current code:
- **Modes are NOT unenforced.** `permission_mode ∈ {ask, write, plan}` already gates the advertised
  tool surface (ask=read-only, plan=read+`plan_*`, write=all), has a defense-in-depth execution block,
  a per-user Tier-A allowlist, and a Claude-Code-style approve/deny GUI card (`ToolApprovalCard.tsx`).
  The *real* gaps are narrower: no **user-authorable** mode→skill/workflow binding (only one hardcoded
  `plan→plan_forge`), no **permission-management UI** (the allowlist is write-only via "Always allow" —
  no viewer/revoke/deny-list), and enforcement **rides on every tool being correctly `_meta.tier`-tagged**
  (R is the silent default).
- **Some "invisible tool" complaints are already fixed.** `glossary_entity_set_attributes`,
  `glossary_propose_entities`, `glossary_entity_delete/restore` were added 2026-07-08 *in direct
  response to the feedback file* and are discoverable. The remaining invisibility (`glossary_propose_new_entity`)
  is **intentional** — it's `_meta.visibility:"legacy"`, superseded by `glossary_propose_entities`. The
  bug class is real, but the specific tool is deliberately hidden.

The redirection stands regardless: **discovery must be deterministic and complete; relevance/curation is
the job of skills and workflows, not of a fuzzy search that can silently drop the one tool you need.**

---

## 1. The three reflections (verbatim intent)

1. **Discovery primitives.** Tool search is useful but should be *optional and off the hot path*. Add a
   deterministic **`tool_list`** with a well-defined category enum (`all`, `glossary`, `kg`, …) returning
   `{name, short description}`, and **`tool_load`** to load N exact tools or a whole category. Same for
   **skills** (list/load) and add the missing **workflows** (list/load — or "commands").
2. **Modes + permissions.** The ask/write/plan modes aren't designed to *inject skills/workflows
   explicitly*, so they're under-used; and (the user believed) there's no write-restriction / no
   permission UI / no MCP whitelist. → See §3 for the grounded correction; the actionable gaps remain.
3. **Workflows.** The system lacks curated, concrete end-user workflows (e.g. "suggest a glossary, then
   plan and set it up", "populate the glossary from a seed doc", "build the KG from a populated
   glossary"). Without them a mid-tier model can't orchestrate 15–25 gated calls across 3+ services. The
   product was designed without user stories / UX workflows, so it's being patched piecemeal. **"We must
   first know what the workflows ARE."** → §5 enumerates them with real tool sequences.

---

## 2. Current-state architecture (code-grounded)

### 2.1 Tool discovery — the 3-registry drift

`find_tools` is the mandatory gate. It is **token-overlap + difflib gestalt-ratio** ranking — *no
embeddings exist yet on this branch* (the embedding client is planned in the tactical plan, not built).
Core: `services/ai-gateway/src/federation/find-tools.ts` (source of truth) with a byte-for-byte Python
twin `services/chat-service/app/services/tool_discovery.py`.

The "invisible-but-callable" bug (`glossary_propose_new_entity`) is a **drift between three independent
registries keyed off different metadata**:

| Registry | Purpose | Where | Keyed on |
|---|---|---|---|
| **(a) find_tools search/enumerate index** | discovery | `find-tools.ts::searchCatalog`/`enumerateGroup`; `computeCatalog` | `_meta.visibility` (drops `legacy`) |
| **(b) `tools/list` (public edge)** | advertised list | `mcp-public-gateway/src/scope/scope-filter.ts::filterOneListMessage` | activation-set ∩ scope (large-scope keys collapse to `find_tools`+activated only) |
| **(c) raw dispatch allowlist** | execution permit | `mcp-public-gateway/src/scope/tool-policy.ts::TOOL_POLICY` | hand-maintained static table (tier + domains) |

A tool tagged `visibility:legacy` (in Go: `WithVisibility(NewToolMeta(...), VisibilityLegacy)`,
`glossary-service/internal/api/mcp_server.go:102`) is dropped from (a) and (b) but still permitted by (c)
→ **invisible yet callable**. The 7 legacy-tagged tools are pinned by a contract test
(`mcp_tool_schema_contract_test.go`); this is intentional deprecation, not an accident — but the *class*
(a real tool discovery can't surface) is exactly what the feedback rails against.

**Category is not first-class.** No `_meta.category` exists; `_meta` carries only `tier · scope ·
undo_hint · synonyms`. Category is *derived by name prefix* via `_DOMAIN_ALIASES` (`kg_`/`memory_` →
`knowledge`). The closed enum lives in **`GROUP_DIRECTORY`** (11 keys) — triplicated across
`find-tools.ts`, `tool_discovery.py`, and the `Domain` union in `tool-policy.ts`, held in lockstep by
`find-tools.spec.ts`.

**Already-built, reusable:** `enumerateGroup(catalog, group, exclude)` already returns *every non-legacy
tool in a category, unranked* as `{name, description}` — i.e. `find_tools(group=X, intent="")` today is
`tool_list(X)` minus a clean name. The proposed primitive is largely a *promotion + rename* of existing
code, not net-new search.

### 2.2 Modes + permission spine (this exists — see §3 correction)

`permission_mode ∈ {ask, write, plan}` (BE SSOT `chat-service/app/models.py:469`; FE
`ChatInputBar.tsx`, persisted per-device in `localStorage`). Consumed in `stream_service.py`:

| Effect | ask | plan | write |
|---|---|---|---|
| System-prompt nudge | `ASK_MODE_NUDGE` | `PLAN_MODE_NUDGE` | baseline |
| Tools advertised | tier-R + `find_tools` + FE tools | +`plan_*` | full catalog |
| Skill injected | — | **`plan_forge` forced** | — |
| Execution block | non-R → error, never runs | same, `plan_*` exempt | none |
| Tier-A allowlist gate | n/a | n/a | **active** (`user_tool_approvals`) |
| Subagent clamp | forced read-only | collapses to ask | may write |

Backed by `_meta.tier ∈ {R, A, W, S}` (R default). Tier-A un-allowlisted writes suspend with a
`ToolApprovalCard` (Approve-once / Always-allow / Deny). Public API keys are separately gated by
`tool-policy.ts` (default-deny, tier∩domain scope). **This is a real, layered model** — the user's "no
write-restriction / no permission UI / no whitelist" is inaccurate for current code.

### 2.3 Skills — exist, but the agent can't `list`/`load` them like tools

`SkillDef` (`skill_registry.py`) = `{code, label, surfaces, prompt_loader (markdown body), description
(L1), hot_domains}`. **A skill is a prose tool-use guide, not a machine-readable step list.** 10 system
skills (glossary, knowledge, plan_forge, composition, translation, book, settings, jobs, universal,
admin) + a DB-backed user/book tier in `agent-registry-service` (`skills` table, prompt-only, no step
field). Selection is **platform-driven** (surface flags via `resolve_skills_to_inject()` + the additive
embedding router `skill_router.py`, `ROUTER_CONFIDENCE_THRESHOLD=0.35`) or **user-pinned** (`enabled_skills`).
**The model never calls a `skill_list`/`skill_load` tool** — the asymmetry reflection #1 targets. A skill
declares its tools only at *domain* granularity (`hot_domains`), enforced by
`test_every_skills_named_tools_are_in_its_hot_domains`.

### 2.4 Workflows — do not exist as a first-class concept

Confirmed: **no `workflows` table, no workflow runtime, no addressable ordered-step object.** The
look-alikes are each something else:
- `workflow_skill.py` — a **prose ordering paragraph** concatenated into `universal_skill` (book→translate→glossary→wiki).
- Slash-commands (`agent-registry` `slash_commands`) — **prompt-template macros** (`{{args}}` substitution), execute no tools.
- `plan_forge`, `composition_authoring_run_*` — genuine multi-step **FSMs**, but a skill+tool-domain and a server-side engine respectively — neither is a listable/loadable workflow bundle.

The spec `2026-07-07-skill-authoring...md:52` already quotes the user: *"skills should ship as **workflow
definitions + tool-use guides**, not bare 'here's MCP, go find_tools yourself.'"* — the gap is named but
unbuilt.

### 2.5 User journeys — personas exist, process doesn't

Personas are well-defined (`docs/specs/2026-06-13-writer-persona-use-cases-scenarios.md`: P1 "Mai"
author, P2 "Linh" worldbuilder, newcomers N-W/N-B/N-T/N-L, ~30 use cases, a "Blocked surfaces register"
BL-1…BL-19). The core admission is the repo's own:
`docs/specs/2026-06-30-editor-compose-overhaul/stories/06-compose-journey.md` — *"The 24 tools exist and
are individually wired, but the GUI encodes no creative PROCESS."* What's missing everywhere is the
**cross-domain step recipe per journey**.

---

## 3. Reflection → grounded reality → the real gap

| # | User's claim | Grounded reality | The actionable gap |
|---|---|---|---|
| 1 | `find_tools` is mandatory, should be optional; need `tool_list`/`tool_load` + skill/workflow list/load | Correct. `find_tools` is the only gate; it's non-deterministic top-K; `enumerateGroup` already does deterministic listing but isn't a named primitive; skills aren't agent-`list`/`load`-able; workflows don't exist | Build the deterministic **list/load triad** for tools **+ skills + workflows**; demote semantic search to optional (§4.1) |
| 1b | Tools are hidden / can't be found | Partly fixed (entity tools added 2026-07-08); remaining hidden tool is intentional (`legacy`); but the **3-registry drift class** is real | Kill the drift: define list/load as **catalog ∩ non-legacy ∩ policy-allowed**, single-source the category enum (§4.1, Phase 0) |
| 2 | Modes don't inject skills/workflows → useless | Only `plan→plan_forge` is hardcoded; ask/plan nudges + surface filtering **do** shape behavior | Add a **user-authorable mode → skill/workflow/tool-set binding** (§4.2) |
| 2b | No write-restriction / no permission UI / no MCP whitelist | **False** for current code: tier filter + execution block + Tier-A allowlist + `ToolApprovalCard` + public `tool-policy` | Add a **permission-management UI** (viewer/revoke/deny — today allowlist is write-only) and a **tier-tag correctness guarantee** (§4.2) |
| 3 | No curated workflows; designed without user stories/UX | Personas + gaps documented; the *process/recipe* layer is genuinely absent | Build the **Workflow primitive** (§4.3) + author the **workflow catalog** (§5) |

---

## 4. Target architecture

### 4.1 The deterministic discovery triad (tools · skills · workflows)

Three capability families, each exposing the **same two primitives**, plus one shared optional search:

```
                 list(category?)                 load(name | [names] | category)
  TOOLS      tool_list      → {name, desc, tier}     tool_load      → full inputSchema(s) [+ activate]
  SKILLS     skill_list     → {code, label, desc}    skill_load     → full L2 markdown body
  WORKFLOWS  workflow_list  → {slug, title, desc}    workflow_load  → step recipe + tool set
  (optional) find_tools / find_skills — semantic, NEVER the sole gate, NEVER hides a real capability
```

**Rules (locked design constraints):**
- **Complete + deterministic.** `*_list(category)` returns *everything* in scope, unranked, no
  similarity floor. Never depends on an embedding score. Reproducible call-to-call.
- **No capability is unreachable by construction.** `tool_list` = `catalog ∩ non-legacy ∩
  isToolAllowed(key/scope)`. A tool that is policy-allowed **must** appear (kills the 3-registry drift).
  A deprecated tool is *labeled* `deprecated: true` in the list, not silently dropped, and its
  replacement is named — so an agent can still find and be redirected.
- **Single-sourced category enum.** Reuse `GROUP_DIRECTORY`'s 11 keys + a sentinel **`all`**. Do **not**
  add a 4th copy — import the enum; resolve category via the existing prefix `_DOMAIN_ALIASES`. Resolve
  the two enum gaps first: (i) `lore_enrichment` (1 orphan tool — add a category or fold it); (ii) admin
  tools live in a segregated RS256 catalog — decide whether list/load may address `admin` at all.
- **`load` is progressive disclosure, not execution.** `tool_load(category)` pulls the schemas into
  context (and, on the public edge, marks them activated so raw `tools/call` works) — it does **not**
  call anything. Keeps the context-saving benefit the gateway was built for, without the guessing.
- **Semantic search stays, demoted.** `find_tools`/`skill_router` remain as an *optional* "I don't know
  the name, help me" convenience. They may *rank* within a `list` result; they may **never** be the only
  path and may never make a listed capability unreachable.
- **Lockstep tax acknowledged.** Every primitive lands in both `find-tools.ts` (TS) and
  `tool_discovery.py` (Py), guarded by `find-tools.spec.ts` drift-lock tests. Budget for it.

> **AS-BUILT (reconciled 2026-07-14, all-tracks-clear M9):** this asymmetry fix SHIPPED, but as
> `registry_list_skills` + `registry_get_skill` (agent-registry MCP, federated under the `registry`
> domain, Tier-R, discoverable via `tool_list`) — not the `skill_list`/`skill_load` names below. The
> capability is real; only the name differs. See TRACK-A.md WS-1a as-built note.

**`skill_list`/`skill_load` as agent-callable tools** is the key asymmetry fix: today skills are
injected *to* the model; the model should also be able to *ask* "what skills exist for X" and "load skill
Y" deterministically — the same way it will for tools and workflows. The existing `/v1/chat/skills/catalog`
REST + `skill_prompts()` loader already provide the data; wrap them as MCP meta-tools.

### 4.2 Mode ↔ capability binding + the permission model

Two additive pieces on top of the existing (real) enforcement spine:

**(A) User-authorable mode → capability binding.** Generalize the single hardcoded `plan→plan_forge`
into a stored, per-user (and per-book) map:
```
mode_binding: { mode: ask|write|plan, inject_skills: [code], inject_workflows: [slug], seed_tool_categories: [category] }
```
Resolved in `resolve_skills_to_inject()` alongside surface flags — additive, never removing a static
default, same `HOT_SEED_TOKEN_BUDGET` ceiling. This makes modes *configurable capability profiles*, which
is what reflection #2 actually wants. (E.g. "my *write* mode always loads the glossary + composition
skills and seeds those tool categories.")

**(B) Permission-management UI + tier-tag guarantee.** The enforcement exists; the *management surface*
doesn't:
- A **permissions screen** listing every tool the user has touched / every category, showing its tier,
  its allowlist state, with **view / revoke / deny** (today `user_tool_approvals` is insert-only via
  "Always allow", no viewer, no deny-list). This is the Claude-Code `/permissions` analogue the user
  pictured.
- A **deny-list** tier alongside the allow-list (currently only allow rows exist).
- A **tier-tag correctness gate**: a CI check that every registered write tool has an explicit non-R
  `_meta.tier` (R-as-silent-default is the one hole where a mistagged write could slip past ask mode).
  Convention → compile-time guarantee.
- **MCP-server whitelist** (for external/federated MCP servers registered via
  `agent-registry-service`): a per-user enable/disable of *which* MCP servers/tools are active — the
  "whitelist access for MCP" reflection #2 names. The registration table exists; the per-user gate + UI
  do not.

### 4.3 The Workflow primitive (net-new)

A **Workflow** is a tiered (system | user | book, mirroring skills/commands), **listable + loadable**
object that — unlike a skill (prose) or command (macro) — declares a **machine-readable ordered step
sequence** with explicit tool bindings and gate awareness. Proposed shape:

```yaml
slug: glossary-bootstrap
title: "Suggest & set up a glossary for this book"
tier: system
surfaces: [book, editor, chat]
description: "One-line L1 menu entry."          # for workflow_list
inputs: { book_id: required, genre_hint: optional }
steps:
  - id: precheck
    tool: book_get                              # exact tool name (must exist in catalog ∩ policy)
    gate: none                                  # none | confirm (Tier-W) | approval (Tier-A)
  - id: adopt
    tool: glossary_adopt_standards
    gate: confirm                               # step-runner knows to mint→confirm_action
  - id: curate_attrs
    tool: glossary_ontology_upsert
    repeat: per_attribute
notes_md: "prose guidance the agent reads (why each step, gotchas) — the skill content, retained"
```

**Runtime.** A deterministic **step-runner** in the chat agent loop drives the sequence, honoring the
*existing* propose→confirm / Tier-A approval gating (never bypasses it — each `gate: confirm` step
surfaces the same `ToolApprovalCard`/confirm flow). A weak model then *invokes* `workflow_load(glossary-bootstrap)`
and follows an explicit rail instead of orchestrating 15–25 calls blind.

**Storage substrate already exists to model on:** `agent-registry-service`'s tiered tables + `/internal/*`
resolver + degrade-safe client + propose→confirm HITL spine (`skill_proposals`/`skill_enablement`
pattern). Net-new: the `workflows` table (with the `steps` JSONB schema), a `registry_propose_workflow`
tool, `workflow_list`/`workflow_load` meta-tools, and the step-runner. **Reuse `hot_domains`-style
budgeting** for seeding a workflow's tool set.

**Workflow vs. skill (keep the distinction clean):** a **skill** teaches *how* to drive a domain (prose,
model decides order); a **workflow** encodes *the exact order* for a named job (data, runner drives it).
A workflow may *reference* skills for its `notes_md`. Do not collapse them.

### 4.4 Long-session continuity & persistent memory — GROUNDED (2026-07-09)

Full detail:
[`investigations/2026-07-09-persistent-memory-and-longsession-continuity.md`](investigations/2026-07-09-persistent-memory-and-longsession-continuity.md).
The flagship [S06](scenarios/S06-flagship-idea-to-arc.md) needs canon to survive a 40+-turn session. A
4-agent code investigation established what's already built vs. the real gaps — **most of it is built**:

- **Persistent memory is BUILT** — durable Neo4j `:Fact`/`:Entity`/`:Event` nodes, per-user/project,
  recallable in fresh sessions. But it **IS the knowledge graph re-branded** (`memory_*` = a facade over
  the derived KG). **Do not build a new memory store.**
- **Auto-recall each turn is BUILT** — `build_context` runs unconditionally every turn (retrieval over
  glossary/KG + rolling summaries) + a persisted `story_state` safety net + compaction that preserves a
  canon summary (F10 done). The **read** side of continuity is solid.
- **The gap is the WRITE side.** Conversation canon is **not auto-persisted**; `memory_remember` is
  opt-in, rate-limited, often confirm-gated, and — by a confidence gate — **excluded from auto-recall**.
  So the durable, auto-recalled path is: **persist canon as GLOSSARY entities/attributes** (authored SSOT,
  auto-injected every turn) — which is the *same* action as populating the glossary (S02). **Continuity is
  a byproduct of persisting to the glossary, not a separate subsystem.**
- **Second root cause of the discovery loop (beyond `find_tools` non-determinism):** even the auto-injected
  `knowledge` domain loses its **write** tools to a **~4000-token read-first hot-seed trim**
  (`tool_surface.py` `budget_names_by_tokens`) on the ≤200K windows mid-tier models run — so
  `memory_remember`, `glossary_propose_entities`, and kg writes route through `find_tools`. **The write
  the co-writer most needs is structurally never on the hot path.** Fix: the `tool_list`/`tool_load` triad
  (§4.1) **plus a cheap immediate lever** — an always-hot allowlist / reserved write sub-budget so key
  canon-write tools survive the trim, and fix the read-verb classifier (`recall`/`timeline` misclassed as
  writes). Fold this into **Phase 0/1**.
- **F7 async-honesty is PARTIAL** (prompt-only across 6 skills) — the workflow step-runner (§4.3) must add
  a **structural** guard (block/annotate a "done" claim against a non-terminal job). **F3 output-floor is
  default-mitigated** (reasoning off by default).

---

## 5. The Workflow catalog — what to build (the "what ARE the workflows" answer)

Each is a **curated recipe to author** (as a Workflow object per §4.3). Step sequences below are
reconstructed from **real, verified tool names** — none is written down as a recipe anywhere today. Tier
legend: R read · A auto-undoable-write · W propose→`confirm_action`.

### P0 — user-named, undefined today

**W1 · Glossary bootstrap** ("suggest → plan → adopt → curate") — *glossary (+book)*
```
book_get / book_list_chapters (R) → glossary_list_system_standards (R)
→ glossary_plan | glossary_adopt_standards | glossary_propose_kinds (W, confirm)
→ glossary_book_ontology_read (R) → glossary_ontology_upsert (A, write attr descriptions)
→ glossary_ontology_delete (W, drop misfit attrs)
```
Gotcha the recipe must encode: a kind is useless without 3–6 attributes, each with a concrete
`description` (the extraction/gen pipelines read it as the instruction).

**W2 · Populate glossary from a story-seed doc** — *NEW BRIDGE, impossible today*
Current reality: population is manual (`glossary_propose_entities`) or extraction over *existing chapter
text* (`translation_start_extraction`). PlanForge ingests a doc (`plan_propose_spec(source_markdown)`)
but outputs a *plan*, not entities. **Needs a new seed-doc → `glossary_propose_entities` path** (a
parser/LLM step that emits entity proposals), then the W-Triage tail below. This is the single most
requested workflow and it has no backing capability yet — flag as its own build.

**W3 · Entity population + triage** — *glossary (+translation for extraction, +book)*
```
populate: glossary_search (R, dedup) → glossary_propose_entities (A) [→ review inbox]
   or: translation_start_extraction(book_id, chapter_ids) (A/job) → confirm → inbox
triage (inbox defaults status=draft): glossary_list_unknown_entities / glossary_list_ai_suggestions (R)
   per entity: glossary_get_entity (R) → glossary_entity_set_attributes (A) | glossary_propose_status_change (W)
             | glossary_entity_delete (W, empty drafts) | glossary_propose_merge (W)
```
Seam to explain: extraction is namespaced `translation_*` but writes to the **glossary** inbox.

**W4 · KG build from a populated glossary** — *knowledge* — the most orchestration-heavy (~10–15 calls, 4 confirm-gates, 3 async jobs)
```
kg_project_create (A) [or composition auto-creates default] → kg_adopt_template (W, confirm) → kg_schema_edit (W)
→ kg_build_graph (W, async — projects glossary entities → nodes/edges) → kg_build_wiki (W, async)
→ kg_run_benchmark (A, golden-set gate) → curate: kg_propose_edge/kg_propose_fact (draft) → kg_triage_* → kg_graph_query (R)
```
Requires gateway `X-Project-Id` forwarding (was broken; fixed in the agent-journey-gaps batch). **Known
open blocker from the feedback:** no *manual node* tool — `kg_propose_edge` parks edges whose endpoints
aren't nodes yet, failing two steps later at confirm. The structured "project glossary entities → KG nodes"
action (`kg_project_entities_to_nodes`) is **in scope as WS-4B** (OQ4 resolved) — it unblocks the
planning-first variant.

**W5 · Translation pass** — *translation (+book, +glossary)*
```
translation_coverage (R) → translation_segment_status (R)
→ translation_start_job | translation_retranslate_dirty (A/job) → confirm → watch (translation_job_status R)
→ translation_set_active_version (A, refused on unresolved HIGH issues) → [human] translation_save_edited_version
```

### P1 — core creative loop + entry points

**W6 · Chapter compose journey** (the 6-phase Idea→Structure→Bible→Draft→Refine→Assemble) — *composition (+plan, +knowledge)* — design already exists in `stories/06-compose-journey.md`; make it a live rail.
**W7 · End-to-end "build a book"** (import/create → translate → glossary → KG → wiki) — promote `workflow_skill.py`'s prose chain to a real recipe.
**W8 · Intent-branching onboarding fork** (Write / Build a world / Translate / Explore) — BL-15; reshapes every entry point.
**W9 · Canon-check / continuity pass** — critic gate + canon rules + degraded-state visibility (UC-41, BL-11).

### P2 — structural persona gaps (named in persona doc, no product yet)

**W10 · Worldbuilding-first "world container"** (prose-less lore/graph/map authoring) — BL-6, biggest structural gap for P2/N-B.
**W11 · Reader / lore-seeker exploration** (read-only ask-the-lore + reading-progress spoiler cutoff) — BL-7.
**W12 · Multi-chapter autonomous drafting** ("Agent Mode" `composition_authoring_run_*`) over an approved PlanForge plan — wrap the existing FSM as a user-facing workflow.

**These 12 are independent** — once the Workflow primitive (§4.3) lands, each is a self-contained
authoring task that can be fanned out to a separate agent/session.

---

## 6. Phased roadmap (reflects the resolved decisions §7)

Each phase is a shippable milestone with its own VERIFY + live-smoke. Phases 0→2 are the sequential
spine; Phase 3 and the Phase-4 backing features can start in parallel once Phase 1 lands; the catalog +
flagship close it out; Phase 5 is cleanup. **§6b decomposes every phase into session-ownable
workstreams** — this section is the *what*, §6b is the *who-builds-what-in-parallel*.

### Phase 0 — Foundations: kill the drift, single-source the enum, guarantee tiers *(size M/L)*
- Single-source the category enum from `GROUP_DIRECTORY` (+ `all` sentinel); fold the `lore_enrichment`
  orphan into a category; `admin` stays a separate scope (OQ2).
- Define the canonical **visible set** = `catalog ∩ non-legacy ∩ isToolAllowed`; make `legacy` tools
  **labeled-deprecated** in listings (with `superseded_by`), not silently dropped (OQ5).
- CI **tier-tag gate**: every registered write tool must carry an explicit non-R `_meta.tier`.
- Correctness substrate only — no new user-facing primitive yet.

### Phase 1 — Discovery triad **+ the hot-path write-tool fix** *(size L/XL)*
- `tool_list(category?)` + `tool_load(name|[names]|category)` — promote `enumerateGroup`; wire
  `tool_load`→activation on the public edge. TS + Py lockstep, extend `find-tools.spec.ts`.
- `skill_list` + `skill_load` as **agent-callable** MCP meta-tools (wrap existing catalog/loader).
- Demote `find_tools`: reword as optional (keep the name — OQ1), advertise `tool_list` first; keep
  semantic ranking only as a within-list option.
- **Hot-path write-tool fix (folded in per OQ7 — the measured 2nd root cause of the loop):** an always-hot
  **write allowlist** / **reserved write sub-budget** in `tool_surface.py` so key canon-write tools
  (`glossary_propose_entities`, `memory_remember`, kg writes) survive the ~4000-token read-first trim on
  ≤200K windows; fix the read-verb classifier (`recall`/`timeline` misclassed as writes). See §4.4.
- **Live-smoke:** "list everything in glossary" returns the full set deterministically; a mid-tier model
  adds an entity via `tool_list`→`tool_load`→call **and** finds the write tool already hot — no brute-force.

### Phase 2 — The Workflow primitive **+ full authoring spine + async-honesty guard** *(size XL)*
- `workflows` table + `steps` JSONB schema in `agent-registry-service`.
- **Full authoring spine (per OQ3): `registry_propose_workflow` for BOTH system AND user/book tiers**, with
  the HITL propose→confirm/enablement spine (mirror the existing `skill_proposals`/`skill_enablement`).
- `workflow_list` + `workflow_load` meta-tools.
- Deterministic **step-runner** in the chat loop honoring existing confirm/approval gates, **plus a
  structural async-honesty guard (OQ9):** a start-job step is marked `pending`; the "done" message is
  gated on an observed terminal status (resolver flags a non-terminal job result / forces a status re-read).
- Ship **W1 (glossary bootstrap)** + **W5 (translation pass)** as reference workflows (existing tools only)
  to prove the runtime end-to-end.

### Phase 3 — Mode ↔ capability binding + permission management *(size L)* — parallel with Phase-4 features once Phase 1 lands
- Stored user/book **mode→{skills, workflows, tool-categories}** binding; generalize `plan→plan_forge`.
- **Permission-management UI:** allowlist viewer + revoke + deny-list; per-user MCP-server whitelist + its
  `/internal/*` gate.
- Surface `workflow_list` results in the FE context rack next to skills.

### Phase 4 — Net-new backing features **(all three, per OQ4/OQ8)** + the workflow catalog + flagship
- **Backing features (3 independent, disjoint services — build in parallel):**
  - **F-A · seed-doc→entities parser** (glossary domain) — turn a pasted seed/notes doc into
    `glossary_propose_entities` candidates (W2 / S02-VB).
  - **F-B · glossary→KG node projection** (knowledge domain) — `kg_project_entities_to_nodes` (+ fail-fast
    edge proposal on missing endpoints) so a prose-less book can seed the graph (W4 / S04).
  - **F-C · auto-capture of conversation canon** (chat domain) — persist stated facts as glossary
    entities as the conversation establishes them, and/or admit `llm_tool_call` facts into L2
    auto-injection (lower the 0.8 gate for that source). Closes the F4 write-side gap (§4.4).
- **Domain fixes now in scope** (Track B): entity world/`scope` identity (`scope_label`), rename,
  hard-delete, upsert/merge-on-create, dedup NFC/NFD fix, doc-drift/naming — and the W8/W10/W11
  product-journey backends (onboarding fork, world-container, reader).
- **Author the workflow catalog** W1–W12 (§5) as Workflow objects on the Phase-2 primitive —
  **parallelizable, one workflow per session** (disjoint recipe files).
- **Ship the flagship S06** (`vision-to-book`) — the front door; its go/no-go is the whole effort's.

### Phase 5 — Retire mandatory semantic search *(size S)*
- Once `tool_list`/`workflow_list` are primary and evals confirm mid-tier models succeed via them, remove
  `find_tools`'s "keep retrying" bias entirely and retire the retry-cap workaround (it only existed to
  bound the mandatory-search damage).

---

## 6b. The 3-session partition (everything in scope, run independently)

**Decision (2026-07-09): everything is in scope — nothing deferred — and the whole effort is partitioned
into AT MOST 3 independently-runnable sessions (Tracks A/B/C).** Independence is bought by **freezing the
shared contracts first** (§6b.0): once the seams are frozen, each track builds against the contract (with
stubs where needed) on **disjoint services/files**, and only final integration/testing waits at three
defined nodes. The 12 fine-grained workstreams from earlier drafts are grouped into these 3 tracks.

### 6b.0 · Frozen contracts — freeze BEFORE fan-out (this is what makes 3 independent sessions possible)

A short joint step (or Track A first) freezes these seams; then A/B/C proceed concurrently against them:
1. **Category enum** — the closed set from `GROUP_DIRECTORY` (+ `all`, `lore_enrichment` folded, `admin`
   excluded). Everyone imports it; no one re-declares it.
2. **`tool_list`/`tool_load` I/O + activation** — the request/response shape and the "loaded ⇒ activated"
   rule. (B's new tools and C's UI code against this before A finishes.)
3. **Workflow `steps` schema** — the YAML/JSONB step shape (`tool`, `gate`, `repeat`, `inputs`, `notes_md`).
   C authors W1–W12 against this before the runner exists.
4. **Error envelope** `{code, message, ...}` + the `content`/`structuredContent` uniformity rule —
   normalized centrally at the gateway (A), so B/C never hand-roll error shapes.
5. **New backing-tool signatures** — `seed_doc→entities` input, `kg_project_entities_to_nodes`, the
   auto-capture write path, the entity `scope`/rename/delete signatures. Frozen so C's workflows and B's
   implementations agree.
6. **Mode→capability binding shape** — the `{mode → skills, workflows, tool-categories}` record C's UI and
   A's resolve both read.

### Track A — Discovery & Workflow Mechanism (the critical-path spine + gateway cross-cutting)

- **Owns:** ai-gateway (TS: `find-tools.ts`, `handlers.ts`, `federation/catalog.ts`) · mcp-public-gateway
  (TS: `tool-policy.ts`, `scope-filter.ts`, `invoke-tool.ts`, activation, structured-content/error
  normalization) · chat-service (Py — **only** `tool_discovery.py`, `tool_surface.py`, `catalog.py`, the new
  step-runner + workflow client, `tool_result_wire.py`, `stream_service.py` LLM/advertise path) ·
  agent-registry-service (Go: `workflows` table + authoring API) · a tier-tag CI script.
- **Delivers:** WS-0 (single-source enum · visible-set = catalog∩non-legacy∩policy-allowed · deprecated
  **labeled** not hidden · tier-tag CI gate) → WS-1a (`tool_list`/`tool_load`/`skill_list`/`skill_load`;
  `find_tools` demoted, kept) + WS-1b (hot-path **write** fix: always-hot write allowlist / reserved write
  sub-budget + read-verb classifier) → WS-2a (`workflows` table + `steps` schema + `registry_propose_workflow`
  **system+user/book** + HITL spine) → WS-2b (deterministic **step-runner** honoring gates + **async-honesty**
  structural guard, OQ9) → WS-6 (retire mandatory `find_tools`). **Newly-in-scope, gateway-central:** #10
  **error-envelope normalization**, #9B **`content`/`structuredContent` uniformity**, #6 **gated-vs-nonexistent
  reason** in `tool_list`, **F3 reserved-output floor** (chat runtime).
- **Produces contracts** 1–4, 6 above. Internally sequential (it's the spine). One session, milestone by
  milestone.

### Track B — Domain Backend Capabilities & Fixes (Go/Py domain services)

- **Owns:** glossary-service (Go) · knowledge-service (Py) · chat-service (Py — **only** the
  context/persist files for auto-capture, disjoint from Track A's file-set).
- **Delivers:**
  - **Backing features:** WS-4A seed-doc→entities parser (glossary); WS-4B `kg_project_entities_to_nodes` +
    fail-fast edge (knowledge); WS-4C auto-capture of chat canon → glossary entities + admit `llm_tool_call`
    facts to L2 (chat/knowledge).
  - **Newly-in-scope domain items:** entity **world/`scope`** identity (complete/coordinate the in-flight
    `scope_label` work — commits `5f5fc61ca`/`ba4b40cb2`; dedup key `(name,kind,scope)`, keep name clean) ·
    entity **rename** · entity **hard-delete** · **upsert/merge-on-create** · **dedup NFC/NFD +
    read-your-writes** fix · `glossary_confirm_action` doc-drift + `propose_*`-writes-immediately naming.
  - **Product-journey backends** for W8/W10/W11 (world-container graph/map authoring; reader spoiler-cutoff).
- **Consumes:** contract 4 (error envelope — but A normalizes centrally, so B mostly gets it free) + 5
  (tool signatures). Otherwise independent — new tools appear in the catalog automatically once A's WS-1 lands.

### Track C — User-Facing, Catalog & Validation (frontend + data-authoring + tests)

- **Owns:** frontend (permission-management UI: allowlist viewer/revoke/deny + MCP-server whitelist; mode
  selector + binding UI; workflow rack; onboarding-fork W8, world-container W10, reader W11 surfaces) ·
  chat-service (Py — **only** `skill_registry.py` mode→capability resolve, disjoint from A/B) · data authoring
  (the W1–W12 Workflow objects, one file each) · `docs/eval/discoverability/` scenario runs.
- **Delivers:** WS-3 (mode→capability binding + permission UI + MCP whitelist) · WS-5 (author the W1–W12
  catalog **incl. the flagship S06 `vision-to-book` workflow** and the W8/W10/W11 journeys) · WS-7 (baseline +
  re-test the S00–S12 scenarios and flagship S06 with gemma).
- **Consumes:** contracts 1 (enum), 3 (steps schema — authors workflows against it before the runner exists),
  6 (mode-binding), and Track B's backing features for the W2/W4/W10/W11 workflows.

### Chat-service file partition (the one service all three touch — declared to avoid collision)

- **A:** `tool_discovery.py` · `tool_surface.py` · `catalog.py` · new step-runner + workflow client ·
  `tool_result_wire.py` · `stream_service.py` (LLM/advertise).
- **B:** context/persist files for auto-capture.
- **C:** `skill_registry.py` (mode→capability resolve).
`resolve_skills_to_inject()` is the one shared touch-point (A reads it, C extends it) — coordinated via
contract 6; keep edits additive.

### Integration nodes (the only places the 3 tracks must sync)

- **N1 — after Track A's WS-1:** the category enum + `tool_list`/`tool_load` + activation are live → Track B's
  new tools become discoverable; Track C's permission/catalog UIs bind to the real enum.
- **N2 — after Track A's WS-2:** the `steps` schema + step-runner are live → Track C's authored workflows
  actually run; async-honesty guard active.
- **N3 — before the flagship (WS-7):** A(mechanism) + B(features) + C(catalog+UI) all present → run the
  flagship S06 live-test. Its go/no-go is the whole effort's.

**Run it:** freeze §6b.0 → all three sessions start concurrently against the frozen contracts (A on the
spine, B on domain services, C on frontend+catalog against stubs) → sync at N1, N2, N3. Track A is the
critical path; B and C do the bulk of their build in parallel and only their final integration waits on A.
TS/Py lockstep tax lives entirely inside Track A (WS-0/WS-1a).

---

## 7. Resolved decisions (all cleared 2026-07-09)

All nine are decided — no open PLAN blockers remain. Recorded here as the frozen contract every
workstream builds against.

- **OQ1 — find_tools handling → KEEP the name, reword as optional, advertise `tool_list` first.** Semantic
  search is a within-list convenience, never the sole gate. (Phase 1 / WS-1a.)
- **OQ2 — `admin` in list/load → OUT.** The RS256-segregated admin catalog stays a separate scope; the
  user-facing triad does not address it. (Phase 0 / WS-0.)
- **OQ3 — Workflow authorship tier → SYSTEM + USER/BOOK TOGETHER.** Phase 2 builds the full
  `registry_propose_workflow` authoring + HITL propose/confirm/enablement spine for both tiers, not
  system-only. (Phase 2 / WS-2a.)
- **OQ4 — W2 & W4 backing capabilities → IN SCOPE.** Both the seed-doc→entities parser (F-A) and the
  glossary→KG node projection (F-B) are built in this effort. (Phase 4 / WS-4A, WS-4B.)
- **OQ5 — Deprecated-tool visibility → LABELED, not hidden.** Legacy tools appear in `tool_list` tagged
  `deprecated + superseded_by`, reversing today's `visibility:legacy` drop. (Phase 0 / WS-0.)
- **OQ6 — Build a persistent-memory system? → NO.** Already built (the KG *is* the memory; auto-injected
  every turn). Continuity = persisting canon as glossary entities, not a new store. F10 done, F3
  default-mitigated. (§4.4.)
- **OQ7 — Hot-path write-tool fix → FOLD INTO PHASE 1** (not a separate Phase 0 slice). The always-hot
  write allowlist / reserved write sub-budget + read-verb classifier fix ships as part of the discovery
  work. (Phase 1 / WS-1b.)
- **OQ8 — Auto-capture of conversation canon → IN SCOPE.** Build it (the co-writer auto-persists stated
  facts as glossary entities, and/or admit `llm_tool_call` facts to L2 auto-injection). (Phase 4 / WS-4C.)
- **OQ9 — Async-honesty structural guard → YES**, built into the Phase-2 step-runner (block/annotate a
  "done" claim against a non-terminal job). (Phase 2 / WS-2b.)

## 8. Risks

- **TS/Py lockstep tax** — every discovery primitive is mirrored; underestimating this re-introduces
  drift. Mitigation: `find-tools.spec.ts` drift-lock coverage on each new primitive.
- **Workflow step-runner vs. gates** — the runner must never bypass propose→confirm/Tier-A. Mitigation:
  the runner *emits* the same confirm/approval surfaces; a test asserts a `gate: confirm` step cannot
  auto-execute.
- **Mid-tier model still can't follow a rail** — eval risk. Mitigation: reuse Part E's `run_skill_gate.py`
  harness to score workflow-following, not just tool-finding, before declaring success.
- **Scope creep into "designed without user stories."** This spec deliberately does *not* redesign the
  onboarding funnel (W8/W10/W11 are P1/P2). Keep Phase 0–3 about the *mechanism*; the *catalog* (Phase 4)
  is where product/UX judgment enters per-workflow.

---

## Appendix A — Full tool inventory by category (federated user catalog, 2026-07-09 code)

| Category | Owner service (lang) | Count | Notes |
|---|---|---|---|
| glossary | glossary-service (Go) | 48 | 7 legacy-tagged (invisible-but-callable); entity-edit/batch/delete added 2026-07-08 |
| composition | composition-service (Py) | 48 | work/outline/prose/canon/motif/arc/authoring-run |
| knowledge | knowledge-service (Py) | 30 | `kg_` (24) + `memory_` (5) + resources/prompts; one category, two prefixes |
| book | book-service (Go) | 21 | chapters are `book_chapter_*` (prefix-gate) |
| translation | translation-service (Py) | 12 | extraction lives here but outputs to glossary |
| settings | provider-registry-service (Go) | 12 | MCP server literally named "settings" |
| plan | composition-service (Py) | 8 | `plan_*`, separate category from composition |
| registry | agent-registry-service (Go) | 5 | skills CRUD (`registry_*`) |
| jobs | jobs-service (Py) | 5 | list/summary/get/cancel/pause |
| catalog | catalog-service (Go) | 2 | public book discovery |
| story | knowledge-service (Py) | 1 | `story_search` |
| *lore_enrichment* | lore-enrichment-service (Py) | 1 | **orphan** — no category/prefix-map entry |
| **admin** (RS256, segregated) | glossary/knowledge (Go/Py) | 7 | glossary-admin 5 + knowledge-admin 2 |

**Total ≈ 193 federated + 7 admin.** The feedback's per-domain counts (~15 book, ~31 glossary, ~13
composition, ~5 translation) are all stale-low; every domain has grown.

## Appendix B — Anchor files (for the plans this spec spawns)

- Discovery: `services/ai-gateway/src/federation/find-tools.ts` (`enumerateGroup`, `GROUP_DIRECTORY`,
  `searchCatalog`), `services/chat-service/app/services/tool_discovery.py` (Py twin, `_DOMAIN_ALIASES`),
  `services/ai-gateway/test/find-tools.spec.ts` (drift-lock).
- Public edge: `services/mcp-public-gateway/src/scope/{tool-policy.ts, scope-filter.ts, invoke-tool.ts}`,
  `src/session/tool-activation*.ts`.
- Registration/meta: `sdks/go/loreweave_mcp/meta.go` (`NewToolMeta`, `WithVisibility`),
  `services/glossary-service/internal/api/mcp_server.go:102` + `mcp_tool_schema_contract_test.go`.
- Modes/permissions: `services/chat-service/app/services/stream_service.py` (`:774-860` advertise,
  `:1730-1990` execution gate + Tier-A), `skill_registry.py:322-327` (plan→plan_forge),
  `tool_surface.py` (curated mode, hot-seed budget), `db/tool_approvals.py` + `db/migrate.py:271-289`,
  `frontend/src/features/chat/components/{ToolApprovalCard.tsx, ChatInputBar.tsx}`.
- Skills/workflows: `services/chat-service/app/services/{skill_registry,skill_router,*_skill}.py`,
  `services/agent-registry-service/internal/{api/commands.go, migrate/migrate.go}` (no workflows table),
  `services/chat-service/app/client/{registry_commands_client,user_skills_client}.py`.
- Journeys: `docs/specs/2026-06-13-writer-persona-use-cases-scenarios.md`,
  `docs/specs/2026-06-30-editor-compose-overhaul/stories/06-compose-journey.md`,
  `docs/plans/2026-06-22-agent-journey-gaps-batch.md`.
