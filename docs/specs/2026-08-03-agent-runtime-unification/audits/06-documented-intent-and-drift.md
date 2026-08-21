# Audit 06 — The Documented Intent and Its Drift

**Scope:** the product's own agentic runtime (chat-service turn loop + ai-gateway MCP federation +
mcp-public-gateway edge). NOT Claude Code's harness.
**Method:** docs-only, read-only, with targeted greps to confirm/refute load-bearing doc claims.
**Repo state:** branch `feat/frontend-tools-mcp-migration`, HEAD `24dd7bdac`, 2026-08-03.

> **Auditor's stance.** A doc asserting something is not evidence it is true. Every claim below that
> matters is marked either **[doc]** (asserted in a document, not verified here) or **[verified]**
> (checked against code/scripts this pass, with the command's finding stated).

---

## 0. The one-paragraph answer

The project has **not** been designing without an architecture. It has designed the *same*
architecture **four times**, each time from a different starting premise, and **never retired the
previous one**. Five mechanisms for "which tools does the model see this turn" are live
simultaneously (hot-seed budget · `tool_list`/`tool_load` · legacy-visibility filter · intent→workflow
pin · capability floor), each individually correct, none composed — a state the project has itself
diagnosed and written down (`docs/specs/2026-07-30-chat-service-control-plane-refactor.md`), deferred,
and left prose-only so no gate can see it. Separately, and this is the actual hole: **no document
anywhere assigns a tool to a skill.** The finest granularity ever specified is `SkillDef.hot_domains`
— a *domain prefix*, not a tool — and the code carries an inline comment admitting it
(`skill_registry.py:154`).

---

## 1. THE DECIDED ARCHITECTURE (as it stands on paper)

Reconstructed from the docs, in the order a turn actually flows. Each element cites the doc that
decided it.

### 1.1 The four-tier model — decided, and it is the spine of everything after

```
User Intent → Skill Selection (which workflow applies) → Workflow (ordered tool sequence) → Tool Calls
```

**Source:** `docs/specs/2026-07-07-mcp-discovery-and-reliability-hardening.md:55-63` (§0.5), stated as
the PO's reframing on the day the spec was drafted. The load-bearing claim is that `find_tools`-style
search *"can only ever answer 'is there a tool that might match these words' — it cannot answer 'given
this ambiguous request, what sequence of steps and tools should I actually run.'"* Search belongs at
the bottom tier only, as a long-tail fallback.

This is the closest thing the project has to a unified architecture statement. **It was never promoted
to a standard.** It lives in §0.5 of a spec whose own status line says *"DRAFT (CLARIFY phase)"*.

### 1.2 Discovery: the deterministic list/load triad

**Source:** `docs/specs/2026-07-09-agent-discoverability-and-workflow/2026-07-09-…-architecture.md`
§4.1 (the umbrella spec), frozen as contract **C2** in that folder's `contracts.md:35-62`.

```
             list(category?)                 load(name | [names] | category)
TOOLS      tool_list   → {name, desc, tier}   tool_load   → full inputSchema(s) [+ activate]
SKILLS     skill_list  → {code, label, desc}  skill_load  → full L2 markdown body
WORKFLOWS  workflow_list → {slug,title,desc}  workflow_load → step recipe + tool set
(optional) find_tools / find_skills — semantic, NEVER the sole gate
```

Locked design constraints, verbatim from §4.1:
- **Complete + deterministic** — `*_list(category)` returns everything in scope, unranked, no
  similarity floor, reproducible call-to-call.
- **No capability unreachable by construction** — `tool_list = catalog ∩ non-legacy ∩ isToolAllowed`.
  A deprecated tool is **labeled** `deprecated:true` + `superseded_by`, *not* silently dropped (OQ5).
- **Single-sourced category enum** — `GROUP_DIRECTORY`'s keys + an `all` sentinel; three declarations
  (`find-tools.ts`, `tool_discovery.py`, `tool-policy.ts` `Domain`) held in lockstep by
  `find-tools.spec.ts`. Final closed set (contracts.md C1): `book · catalog · composition · glossary ·
  jobs · knowledge · plan · registry · research · settings · story · translation` + `all`; `admin`
  excluded (OQ2); `lore_enrichment` folded into `glossary`.
- **`load` is progressive disclosure, not execution** — pulls schemas into context and (on the public
  edge) marks them activated so a raw `tools/call` works.

**[verified]** `TOOL_LIST_NAME`/`TOOL_LOAD_NAME` exist at `services/chat-service/app/services/tool_discovery.py:51-52`;
`visible_tools(...)` implements the labeled-deprecated rule at `:877-921` with `include_deprecated: bool = True`.

### 1.3 Skills: prose guides with a declared domain, selected structurally then semantically

**Source:** `docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md` (Parts A–F).

- A **skill** is `{code, label, surfaces, prompt_loader (markdown), description (L1), hot_domains}`
  — *a prose tool-use guide, not a machine-readable step list* (umbrella §2.3).
- **Part A (shipped)** added `hot_domains: frozenset[str]` — *"the GROUP_DIRECTORY domain(s) this
  skill's prose names tools from DIRECTLY"* — enforced by
  `test_skill_registry.py::test_every_skills_named_tools_are_in_its_hot_domains`, which scans the
  prose for real catalog tool names and asserts the domain is declared hot. **[verified]** the field
  and its docstring are at `skill_registry.py:33-40`.
- **Part D (shipped)** deleted the three hand-authored constants (`_BOOK_SCOPED_HOT_DOMAINS`,
  `_STUDIO_HOT_DOMAINS`, `PLAN_HOT_DOMAINS`) and derived `surface_hot_domains()` from
  *which skills would be injected this turn*. This is the single most architecturally coherent
  decision in the whole corpus: **the skill registry became the source of truth for tool seeding.**
- **Part F (`skill_router.py`, shipped)** — an embedding-similarity Intent→Skill router, strictly
  additive to the surface-flag path, `ROUTER_CONFIDENCE_THRESHOLD=0.35`, falling back to today's
  static behaviour on any embed failure (umbrella §2.3 confirms it shipped; §"Prior art" demotes it
  from *"the answer"* to *"an optional convenience layer"*).
- Coverage bar (§3.2): a domain earns a dedicated skill at ≥~10 tools, or a multi-step/confirm-gated
  workflow, or a recorded live misfire. Ten system skills exist (glossary, knowledge, plan_forge,
  composition, translation, book, settings, jobs, universal, admin) + a DB-backed user/book tier in
  `agent-registry-service`.

### 1.4 Workflows: the net-new primitive, C3-schema'd, runner-driven

**Source:** umbrella §4.3; schema frozen as **C3** in `contracts.md:63-84`.

```yaml
slug: glossary-bootstrap
tier: system | user | book
surfaces: [chat, book, editor, studio]
inputs: { book_id: required }
steps:
  - id: adopt
    tool: glossary_adopt_standards     # exact name, must be in catalog ∩ policy-allowed
    gate: none | confirm | approval
    when?: <predicate>   repeat?: per_item:<key>   inputs_map?: {...}
notes_md: <prose the agent reads; NOT executed>
```

The stated distinction, which the docs insist must not collapse: *"a **skill** teaches how to drive a
domain (prose, model decides order); a **workflow** encodes the exact order for a named job (data,
runner drives it)"* (§4.3).

A deterministic **step-runner** in the chat loop drives it, never bypassing the existing
propose→confirm / Tier-A approval gates, and adds a **structural async-honesty guard** (OQ9): a step
whose tool starts a job is annotated `async_job:true` and "done" is gated on an observed terminal
status. **[verified]** `services/chat-service/app/services/workflow_runner.py` header states exactly
this, including *"the runner never bypasses confirm/approval"*.

**Twelve system workflows** were authored and seeded in `agent-registry-service` `migrate.go`
(BOARD.md:17): glossary-bootstrap · entity-triage · populate-from-notes · kg-build · vision-to-book ·
translation-pass · draw-a-map · lore-so-far · canon-check · chapter-compose · build-a-book ·
autonomous-drafting.

### 1.5 Mode → capability binding (C6) and how a workflow gets pinned

**Source:** `contracts.md:118-133` (C6), amended 2026-07-11.

```
mode_binding: { mode, inject_skills[], inject_workflows[], seed_tool_categories[], disable_workflows[] }
```
Resolved **additively** in `resolve_skills_to_inject()`; effective = System ∪ per-user ∪ per-book,
**minus** the union of every tier's `disable_workflows`. `inject_workflows` means **PIN** — render the
rail into context AND pre-activate its step tools — not merely "advertise". The amendment's stated
reason is a measurement, not taste: *"advertising alone provably does NOT work (S06: the right
workflow was advertised WITH a steering directive and the agent still improvised, because the user
only ever ASSENTS to the agent's own offer — it never 'asks')"* (contracts.md:139-146).

A second pinning mechanism, **intent→workflow pinning**, was added 2026-07-15 (`8bd7a2108`) because
the mode binding pins only ONE rail per mode. **[verified]** `services/chat-service/app/services/intent_workflows.py`
is a deterministic keyword→slug table; its header explicitly rejects the embedding router for this job:
*"Deterministic keyword match (no LLM call — cheap, and reliable in a way an embedding router is not
for a small closed rail set)."*

### 1.6 Permissions, tiers and gates — the enforcement spine

**Source:** umbrella §2.2 + §4.2; `docs/standards/mcp-tool-io.md` Part 5.

- `permission_mode ∈ {ask, write, plan}` filters the advertised set by `_meta.tier ∈ {R,A,W,S}`,
  blocks execution defence-in-depth, and runs a per-user Tier-A allowlist (`user_tool_approvals`).
- **Tier-R is the silent default** — the umbrella names this as *the one hole*, and the fix
  (a CI tier-tag gate) was Phase-0 scope.
- **GATE-1..4** (`mcp-tool-io.md:113-121`): a KIND-C confirm is a durable owner-scoped ext-task
  (`mcp_gate_tasks`), with `confirm_token` + `confirm_action` as the **permanent** fallback (GATE-2,
  spec OQ3). GATE-4 is the `Out=any` ⇒ explicit `outputSchema` rule whose violation de-federates a
  whole provider.
- INV-T1..T6 (standards README §C): MCP writes mint a confirm token; admin MCP is a physically
  separate `/mcp/admin` endpoint.

### 1.7 The I/O discipline for an individual tool

**Source:** `docs/standards/mcp-tool-io.md` — status **ACTIVE**, the only *standard* (as opposed to
spec) in this whole domain. IN-1..8 (identity from the envelope; explicit `project_id` because the
gateway drops `X-Project-Id`; closed set ⇒ `enum` registered in `CLOSED_SET_ARGS`; bounds in schema
not prose; tolerate a harmless extra but reject smuggled scope; one-line self-correcting errors;
one-name-one-concept; the 4-source drift lockstep) and OUT-1..6 (reference-first; detail+limit
defaulting *small*; the single `_tool_result_content` helper; bare-payload success; honest partiality
flags; no data-bearing frontend tools). Plus CAT-1..4 catalog hygiene and Part 3's
**verify-by-EFFECT** rule.

### 1.8 The 2026-07-27 pivot — the state machine leaves the agent

**Source:** `docs/specs/2026-07-27-glossary-kg-build-workflows.md`.

This is the newest architectural statement in the corpus and it partially *reverses* the direction of
everything above:

> *"A weak local model (gemma-4-26b) in the conversational agent **cannot reliably CHOOSE tools**,
> even after 10 platform fixes made the surface correct… Tool-choice is the unfixable link; content
> generation is not. **Therefore: move the state machine OUT of the agent** (the PlanForge pattern).
> The LLM only fills content inside a step; the platform makes every tool call deterministically;
> the human approves at checkpoints."*

Planner (breadth, 1 call → worklist) / Executor (depth, 1 call per entity) split, resumable FSM rows,
a `depth: standard|deep` dial validated by a 4-experiment POC (E1–E4, results tabulated at §"POC
results"). Chat is explicitly demoted: *"Chat: unchanged (supporter for atomic edits)… the chat rail
stays for strong models."*

**[verified]** this is being built: `services/composition-service/app/services/glossary_build/service.py`
and `frontend/src/features/world-setup/` are modified in the current working tree.

### 1.9 What this adds up to, on paper

The written architecture is genuinely coherent *if you read only the umbrella spec*: deterministic
discovery at the bottom, prose skills above it declaring which domains they need hot, machine-readable
workflows above that, mode/intent pinning to select one, and one permission spine underneath. What
makes it read as incoherent in practice is that (a) each layer's *predecessor* is still running, and
(b) the newest decision (§1.8) says the top three layers do not work for the model the project
actually targets.

---

## 2. THE DECISION TIMELINE — nine successive redesigns of tool surfacing

This is the heart of the patchwork complaint. Each row: what was decided, what problem it solved, and
**whether the previous mechanism was retired**.

| # | Date | Mechanism | Problem it solved | Predecessor retired? |
|---|---|---|---|---|
| **1** | ≤2026-06-10 | **Hot-seed whole domains** — `_BOOK_SCOPED_HOT_DOMAINS = {glossary, story}`, `_STUDIO_HOT_DOMAINS = {glossary, composition, story}` | A surface's skill must work without a discovery round-trip | n/a (first) |
| **2** | ≤2026-07-06 | **`find_tools`** — token-overlap + difflib fuzzy top-K over the whole catalog, `INCLUSION_FLOOR=0.20`, `CONFIDENCE_THRESHOLD=0.30`; matched tools activated next pass | ~150-160 federated tool schemas can't ride every turn | **NO** — hot-seed kept, so a book surface paid *both* |
| **3** | 2026-07-06 (`dda88c0dd`) | **Token-budgeted hot-seed** — `budget_names_by_tokens`, `HOT_SEED_TOKEN_BUDGET=4000`, reads-first ascending schema size | Measured: a book-scoped chat paid a flat **~24K-token** schema tax per turn, re-sent N+1 times per tool loop | **NO** — landed *concurrently and independently* of the spec addressing the same bug; the spec then reconciled them as "complementary" (`2026-07-06-tool-catalog-simplification.md:90`) |
| **4** | 2026-07-06 | **`GROUP_DIRECTORY` + CAT-4 legacy visibility** — a ~15-line plain-text domain map injected in the system prompt (~188 tok live-measured); `_meta.visibility:"legacy"` excludes a superseded tool from `search_catalog` *and* hot-seed; `pinned_legacy_tools` per-session escape hatch | The model had no map of what domains exist; and the eval proved a superseded tool **out-ranks its replacement** in fuzzy search (`glossary_ontology_upsert` ranked 3rd behind `glossary_book_create`) | Legacy tools: hidden, not deleted (deliberate). Hot-seed + find_tools both kept. Live-measured result: 24K → **~4,118 tok, 83% reduction** |
| **5** | 2026-07-07 | **Skill-authoring contract (Parts A–E)** — `hot_domains` on `SkillDef` + a claims lint; 5 new domain skills; Part D folds the 3 hot-domain constants into a skill-registry derivation | A skill's prose promised `plan_propose_spec` while `plan` was never hot-seeded — *"the skill and the seeding layer drifted apart with no test connecting them"* | **YES, partially** — the three hand-authored constants were **deleted**. The only clean retirement in the whole timeline |
| **6** | 2026-07-07 | **Layer-A hardening of `find_tools`** — true per-domain enumeration, retry-cap, embeddings-backed ranking | 4 real production sessions, same query, same day, all failed: 13 duplicate-call validation errors → hallucinated news; another hit **40 iterations / 53.8s / a 0-length answer** | **NO** — and *same-day, in the same document* (§0.5) the fix was demoted to "defense-in-depth, not the fix" before it was built |
| **7** | 2026-07-07 | **Part F — Intent→Skill Router** (`skill_router.py`, embedding cosine over skill descriptions, additive, threshold 0.35) | `resolve_skills_to_inject()` takes **zero intent parameter** — selection was 100% structural (surface flags), so a general web-research ask on the universal surface had no skill to reach | **NO** — additive by design. Later **demoted** by the umbrella spec to *"an optional convenience layer"* |
| **8** | 2026-07-09 → 07-15 | **The discovery triad + Workflow primitive** — `tool_list`/`tool_load`, workflows table + C3 steps + step-runner, mode→capability binding (C6), 12 seeded rails; **OQ5 reverses CAT-4**: deprecated tools are now *labeled*, not dropped, in `tool_list` | *"the agent has no deterministic, complete way to answer 'what can I do here?' and no curated procedure for 'do this multi-step job'"* — 193 federated tools + 7 admin | **PARTIAL.** OQ1 explicitly: *"KEEP the name, reword as optional, advertise `tool_list` first."* Phase 5 was written to retire `find_tools` later — **it never ran** |
| **8b** | 2026-07-15 | **Intent→workflow pinning** (`8bd7a2108`) | The mode binding pins one rail per mode; the other 11 needed discovering, and gemma did that inconsistently (S03 0/3, S04 1/3, S09 improvised) | **NO** — a *third* pinning path alongside mode-binding and the embedding skill-router |
| **9** | ~2026-07-22 (**F17**, `f30dc77e5`) | **`find_tools` retired from the LLM's view** — *"hide find_tools from the LLM; `tool_list`/`tool_load` are the sole discovery path"* | Fuzzy top-K structurally cannot enumerate; the handler stays for compatibility | **YES for the model surface, NO for the code.** **[verified]** `tool_discovery.py:284-287` — *"find_tools was retired FROM THE LLM's view… (The find_tools handler stays)"*. `FIND_TOOLS_TOOL` is still constructed at `:132` |
| **9b** | 2026-07-22 (**F18**) | **Loop breakers** — `TOOL_LIST_CATEGORY_CAP=1`: a 2nd list of a category auto-loads the category and steers, never errors | A naive explicit error **backfired** — measured 28 → 311 calls | Additive |
| **10** | 2026-07-21 | **Eager tool-index mode — SUPERSEDED before build** | Premise (*"weak models can't run the discovery loop"*) **disproven live**; real cause was a one-line bug: `book_update_details` was budget-starved out of the advertised set | Correctly killed. The planner-executor (`tool_plan.py`/`planner_poc.py`) parked in the same banner — *"never proved a cost advantage over these targeted fixes"* |
| **11** | 2026-07-22 | **Per-domain catalog unification** — book 31→~15, glossary 42→25 (gemma 7–8/8), KG 37→? | A mid-tier model juggling 42 tools picks wrong, re-reads the list, burns its window | Superseded tools tagged legacy, never deleted (CAT-4 playbook reused) |
| **12** | 2026-07-30 | **N5a-FULL capability floor** (`filter_intent_gated_setup_tools`) — high-impact ontology tools *un-seeded, un-findable, AND un-loadable* | Stop the co-writer rebuilding a newcomer's world on an unrelated turn | Additive. **Immediately collided with the rail**, which named `glossary_adopt_standards` by name → 40,597 chars of one repeated paragraph |
| **13** | 2026-07-27 → present | **Move the FSM out of the agent** (planner/executor in composition-service, World Setup wizard) | *"tool-choice is the unfixable link"* for a weak model | Chat rail **explicitly kept** *"for strong models"* — so this is a parallel product, not a replacement |

### 2.1 What the timeline shows

- **Thirteen mechanisms, one retirement.** Only #5 (Part D deleting the three hot-domain constants)
  removed its predecessor. Everything else is additive or a partial demotion.
- **Two reversals inside three days**: #6 was demoted in the same document that proposed it (07-07);
  #8's OQ5 reversed #4's CAT-4 exclusion rule (07-06 → 07-09) — and **the standard was never updated**
  (see §3.1).
- **The premise flips at least twice.** #8 assumes deterministic enumeration fixes it. #10 disproves
  the model-capability premise entirely and shows the bug was ours. #13 concludes the model *can't*
  choose tools after all and moves the state machine out. These three cannot all be true; nothing in
  the corpus reconciles them.
- **Three independent "which workflow applies" selectors** now coexist: mode-binding pin (C6),
  embedding skill-router (Part F), keyword intent→workflow pin (`intent_workflows.py`).
- **Eight independent answers to "is this tool available?"** — enumerated by the project itself in
  `2026-07-30-chat-service-control-plane-refactor.md:69-78`: `hot_tool_names`,
  `filter_intent_gated_setup_tools`, `budget_rail_tools`, `budget_names_by_tokens`,
  `merge_activated_tools`, the action gate (`done_suppress`), the repeated-failure de-advertiser, and
  the auto-load guard. *"Nobody can answer 'why is tool X not on the wire?' without reading all eight
  — which is literally how this investigation was spent."*

---

## 3. CONTRADICTIONS

Ordered by how much they would mislead someone writing the unified spec.

### 3.1 CAT-4 (ACTIVE standard) vs OQ5 (frozen contract) — legacy: hidden or labeled?

- **`docs/standards/mcp-tool-io.md:100-111` (CAT-4, status ACTIVE):** a legacy tool *"never appears in
  a fuzzy-search result and is never hot-seeded"* — **excluded from discovery entirely**.
- **Umbrella §4.1 + OQ5 (`…architecture.md:576`) + contract C2 (`contracts.md:41-48`):** *"Deprecated-tool
  visibility → **LABELED, not hidden**… reversing today's `visibility:legacy` drop."*
  `include_deprecated?: bool = true`.
- **[verified] code does BOTH, split by surface:** `is_legacy_tool` still filters `search_catalog`
  (`tool_discovery.py:501`), `hot_tool_names` (`:736`) and one more path (`:869`) — CAT-4 holds there —
  while `visible_tools`/`tool_list` LABEL (`:877-921`) — OQ5 holds there.
- **The defect is documentary, not behavioural:** the ACTIVE standard describes only half the rule and
  never mentions `tool_list`. Anyone reading the standard alone will build the wrong thing. The
  standard's own DRIFT NOTE (`:102-109`) patches the `find_tools` naming but **not** the
  hidden-vs-labeled reversal.

### 3.2 The standards index says Track D is PROPOSED; the project says it shipped

- **`docs/standards/README.md:62`** — *"MCP Tool `_meta` Completeness Law + Tool Liveness … Status:
  **PROPOSED** (Track D · WS-D0/D1)."*
- **`docs/specs/2026-07-13-all-tracks-clear.md:23`** — *"Track D … **Code done, ZERO gaps.**"*
  BOARD.md's ND3 node is ✅ with the ship gate live as reject-on-`executes:false`.
- **`docs/specs/2026-07-09-mcp-tool-liveness-eval/README.md:3`** still says `Status: PLAN`, and
  BOARD.md:18 still shows Track D as ⬜ not-started — **inside the same folder tree** whose sibling
  spec says it is done. Three docs, three answers.

### 3.3 `tier-tag-gate` exists and is wired — and is in none of the places that track gates

- `2026-07-13-all-tracks-clear.md:46` names it the one **CONFIRMED GAP** in Track A, milestone M9a.
- **[verified] it was built and wired:** `scripts/tier-tag-gate.py` exists with a full rationale
  docstring; `.githooks/pre-commit:224-225` runs it on any touched `NewToolMeta`/`mcp_server.go`/
  `_tools.go`/`tool_discovery` file; `.github/workflows/foundation-ci.yml:190` and
  `lint-foundation.yml:95` both run it; `scripts/test_tier_tag_gate.py` self-tests it.
- **[verified] `grep -c "tier-tag-gate" docs/standards/README.md` → `0`.** The index whose own
  maintenance rule is *"a new cross-cutting rule is not 'done' until it has a row here"* does not list
  the gate that enforces the tier law it *does* list (as PROPOSED). Both directions of drift, on the
  same rule.

### 3.4 The umbrella spec's Phase 5 never happened, and nothing says so

`…architecture.md:458-461` — *"Phase 5 — Retire mandatory semantic search: … remove `find_tools`'s
'keep retrying' bias entirely and retire the retry-cap workaround."* F17 hid `find_tools` from the
model but the handler, the schema constant, the retry-cap and the `BLANK_TOOL_ARGS_CAP` breaker built
for it all remain **[verified: `tool_discovery.py:132` still constructs `FIND_TOOLS_TOOL`]**. No doc
records Phase 5 as done, deferred, or cancelled. It simply stopped being mentioned.

### 3.5 `skill_list`/`skill_load` — specified, shipped under different names, reconciled once, still miscited

The umbrella §4.1 specifies `skill_list`/`skill_load` as the key asymmetry fix. An AS-BUILT note at
`…architecture.md:213-217` corrects it: shipped as `registry_list_skills`/`registry_get_skill` under
the `registry` domain. `all-tracks-clear.md:48` calls this *"inverse-drift"* and schedules a naming
reconcile as M9b. The umbrella's own §4.1 code block (`:186-190`) **still shows the old names** three
lines above its own correction. Anyone grepping for `skill_list` finds nothing.

### 3.6 Two mutually exclusive verdicts on whether a weak model can drive tool selection

- **`2026-07-21-eager-tool-index-mode.md:28-35`** — *"❌ WRONG: 'weak models can't run the discovery
  loop.' Disproven live. ✅ RIGHT: the problems are mostly OUR code/logic… **Confirmed four-for-four.**"*
- **`docs/eval/tool-liveness/discovery-gap/RESULTS.md:15`** (2026-07-22) — *"Discovery WORKS — the
  'won't tool_load' claim is stale/false… The foundational concern is **resolved**."*
- **`2026-07-27-glossary-kg-build-workflows.md:8-11`** — *"A weak local model … **cannot reliably
  CHOOSE tools**, even after 10 platform fixes made the surface correct… Tool-choice is the unfixable
  link."*

Five days apart, both measured, neither citing the other. They are arguably compatible (discovery ≠
selection-among-many; the 07-27 failure was picking `propose_entity_edit` to *create*), but **no
document draws that distinction**, so the corpus reads as self-contradicting on its single most
load-bearing premise. The unified spec must settle this explicitly.

### 3.7 The chat-control-plane spec's own inventory is stale

`2026-07-30-chat-service-control-plane-refactor.md:41` says `stream_service.py` is 7,074 lines with 16
caps. The DEBT-REGISTER re-verified it at HEAD: **7,818 lines**, and ~8 more cap-shaped constants exist
outside the named 16 (`NARRATED_WRITE_NUDGE_CAP`, `ACTIVATED_TOOLS_CAP`, `RAIL_STEP_TOKEN_BUDGET`,
`HOT_SEED_TOKEN_BUDGET`, `STORY_STATE_TOKEN_CAP`, `STEERING_TOKEN_CAP`, `SUBAGENT_MAX_ITERATIONS`,
`ROUTER_MAX_ADDITIONS`). Three of its eight "availability places" are not addressable by name. So the
one doc that correctly diagnoses the whole problem cannot be executed from as written.

### 3.8 Minor: an Artifact-Language violation in a live design doc

`docs/specs/2026-07-28-intent-collection-fsm.md:16-19` pastes a verbatim Vietnamese PO quote into an
English design doc — precisely the MIXING failure mode CLAUDE.md's Artifact Language rule names.
`doc-language-gate.py` judges **added lines only** against a 468-file legacy baseline, so this class
survives in older files.

---

## 4. THE DEFERRED BACKLOG in this domain

**Structural finding first:** `docs/sessions/SESSION_HANDOFF.md` has **no Deferred Items table for this
domain** in the sense CLAUDE.md describes. It has one 3-line `### Deferred (new)` block at
`:2223-2227` containing exactly one row. Everything else is prose scattered across 10,198 lines.
`docs/deferred/DEFERRED.md` is the **foundation/MMO ledger** and contains essentially nothing in this
domain (two stale rows: `068 D-GLOSSARY-MCP-LIVE-SMOKE`, `066 D-AI-AGENT-MCP-MIGRATION-AUDIT`).

**[verified] Mechanisation status:** `grep -rln "deferral-registry:begin" docs/` returns exactly two
files — `docs/03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md` and
`docs/specs/2026-08-03-glossary-kg-entity-refactor/DEBT-REGISTER.md`. **No deferral in the
tools/skills/MCP/rails/workflows domain is inside a registry block, so `scripts/deferral-gate.py`
cannot see a single one of them.** Every row below is **prose-only** unless stated otherwise.

### 4.1 The one formally-tracked row — and it is the whole problem

| ID | Gate | Mechanism | Assessment |
|---|---|---|---|
| **`D-CHAT-CONTROL-PLANE`** (`SESSION_HANDOFF.md:2227`, spec `2026-07-30-…`, 7 itemised rows `2026-07-30-01`…`2026-08-03-07` in DEBT-REGISTER §B) | #2 large/structural | **PROSE-ONLY** — self-declared: *"`deferral-gate.py` cannot see it and the trigger is enforced by nobody noticing"* | **This IS the unified spec's §A.** Its four asks — a tool-availability SSOT with named stages, a `TurnState`, guards-as-policies with logged precedence, and cross-mechanism invariant tests — are exactly what "tool loading is chaotic" means mechanically. Nothing has been built (**[verified] by the register 2026-08-03**: `grep -rn "def availability\|class Availability\|Withheld" services/chat-service/app` → 0) |

Its seven sub-rows, all open, all prose-only:

| id | item |
|---|---|
| 2026-07-30-01 | §A tool-availability SSOT — 8 places answer "is this tool available"; its invariant test (*"for every step of a pinned rail, availability is never Withheld"*) is **the test that fails today** |
| 2026-07-30-02 | §B `TurnState` — one owner of rail cursor / active tools / breaker counters, recomputed at defined lifecycle points |
| 2026-07-30-03 | §C guards become policies with logged precedence (down-payment made: `_rail_is_in_flight`) |
| 2026-07-30-04 | §D cross-mechanism invariant tests — *"every mechanism has unit tests for itself; nothing tests them against each other, which is why a contradiction survived"* |
| ★2026-07-30-05 | §E the **anti-rot rule** has **no row in `docs/standards/README.md`** — *re-verified* |
| ★2026-08-03-05 | the deferral has **no mechanism** (no registry block) — *re-verified* |
| ★2026-08-03-06 | the spec's inventory is stale/unaddressable — *re-verified* |
| ★2026-08-03-07 | the spec has **no DoD, no order, no size, no gate spec** |

### 4.2 Open rows found only as prose in SESSION_HANDOFF / spec bodies

| ID | Where | Gate reason | Mechanism | Absorb into the unified spec? |
|---|---|---|---|---|
| `D-SKILL-LINT-LIVE-CATALOG` | `SESSION_HANDOFF.md:7344`; spec §8b.2 | #4→"buildable" (self-corrected) | prose-only | **YES.** The claims lint only checks the FORWARD direction; a *stale or typo'd* tool name matching nothing is invisible. Directly relevant to "the agent doesn't know a tool exists" |
| `D-INVOKE-TOOL-LIVE-SMOKE` | `:7359`, `:7319` | #4 needs infra | prose-only | Partially cleared 2026-07-08 for #2/#3; the external-client re-test never ran. Relevant to the public MCP edge slice only |
| `D-MCPTASKS-GO-STORE` | `:5757`, `:5995` | #2 structural, "interface-ready" | prose-only | **YES if the spec touches gates.** Go `InMemoryTaskStore` is per-process ⇒ the durable confirm gate is not multi-replica-safe |
| `D-P3-RETIRE-UI-FRONTEND-DEFS` | `:5739`, `:5877` | #2 large, "low-value / risky — recommend DEFER" | prose-only | **YES.** The two remaining pre-MCP frontend-tool definitions are the last un-migrated parallel tool path |
| `D-PLAN-CURATED-SKILL-FLAG-NAMING` | `:7361` | #1 out of scope | prose-only | **YES, cheap.** `tool_surface.py`'s hot-domain union gate is literally keyed on `"glossary"` (`glossary_in_skills`) though it now governs plan/composition too. A misnamed switch in the seeding path |
| `D-DOMAIN-HOTSET-NOT-STICKY` | `:5574` (`a3028d6f6`) | fixed by targeted re-seed | fixed, not mechanised | The *fix* is a heuristic (re-seed domains recent `tool_calls` engaged). The unified spec should make it a declared availability stage |
| `D-RAIL-NEXT-STEP-EXEMPT` | `:1713`, spec §1 | shipped, then defeated | — | **The canonical example**: a budget exemption computed once at turn start, defeated by mid-turn rail advance. Absorb as the motivating test case |
| `D-S05-COVERAGE-MISMATCH` | `docs/eval/discoverability/2026-07-15-M2-…:83` | #2 cross-service | prose-only | Domain bug, not tool-surfacing. Out of scope |
| `D-KNOWLEDGE-TOOL-ERRORS-NOT-ISERROR` | `:7122` | **CLEARED** | — | Closed |
| `D-BLANK-TOOL-ARGS-LOOP` | `:7302-7307` | **CLEARED**, live-verified 3× | shipped breaker | Its breaker is one of the 16 caps §A must absorb |
| `D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE`, `D-SKILL-EVAL-RERUN-AFTER-LOOP-FIX`, `D-SKILL-HOTDOMAIN-RUNTIME-WIRING`, `D-WS4C-EFFECTIVE-VALUE`, `D-WF-BOOK-TIER-AUTHORING` | various | **CLEARED** | — | Closed |

### 4.3 Recorded-but-unmechanised gaps inside the ACTIVE standard itself

`mcp-tool-io.md:138-143` lists five *"Not yet enforced (tracked gaps)"*. These are deferrals with no
ID and no row anywhere:

1. **No cross-service MCP-tool lint** for: a bare-`string` arg whose description enumerates a finite
   set (IN-3), a set-returning tool with no `get_by_id` sibling and no `@small_return` (OUT-1), or a
   tool-result site bypassing `_tool_result_content`. *Partial:* `context-budget-defaults-lint.py`
   covers one OUT-2 rule and seeds **14 current offenders** as FLIP-PENDING allow (K37 debt).
2. **No repo-wide OUT-1/OUT-2 contract-snapshot harness.** One per-tool byte-budget test exists
   (`jobs_list`); a new list tool with no such test still slips.
3. **The IN-8 4-source drift-lock is knowledge-service-only**; glossary/composition are per-service
   and uneven.
4. **CAT-4 has no lint.** Nothing checks a legacy tool is excluded on *both* federation surfaces
   (`tool_discovery.py` and `find-tools.ts`) — *"they must stay in lockstep or one surface leaks a
   legacy tool the other correctly hides."*
5. `invoke_tool`'s generic `{name, arguments}` is an accepted, documented IN-3/IN-4 deviation.

**Assessment: #1 and #4 belong in the unified spec.** #4 in particular is the exact failure shape the
project keeps hitting — two engines that must agree, with the agreement enforced by a comment.

### 4.4 Backlog verdict

- **1** row is in a table. **~10** live only as prose in a 10K-line handoff. **0** are mechanised.
- The register that *does* work (`DEBT-REGISTER.md`, opened 2026-08-03) exists precisely because
  *"three of the items were recorded as **closed** and are open; four had no written home of any kind."*
- **The unified spec must absorb, at minimum:** all 7 `D-CHAT-CONTROL-PLANE` rows (they are its §A),
  `D-SKILL-LINT-LIVE-CATALOG`, `D-P3-RETIRE-UI-FRONTEND-DEFS`, `D-PLAN-CURATED-SKILL-FLAG-NAMING`,
  and standard-gaps #1 + #4. It must also open a `deferral-registry:begin/end` block in
  SESSION_HANDOFF, or its own deferrals will be invisible the same way.

---

## 5. WHAT IS MEASURED

The project measures tool discoverability **more thoroughly than it documents it.** Four distinct
harnesses exist, all real, all runnable, none in CI.

### 5.1 The four harnesses

| Harness | Drives | Measures | Scored by | State |
|---|---|---|---|---|
| `scripts/eval/run_discoverability_scenario.py` + `discoverability_scenarios/*.json` (**18 scenarios** S00a–e, S01–S12) | real chat SSE, in-container, gemma-4-26b-a4b-qat, $0 | goal-achievement, black-box | **DB ground truth** on a fresh empty book, + judge for 4 | **Works.** Last full run 2026-07-15 |
| `scripts/eval/run_skill_gate.py` + `skill_scenarios/{book,composition,jobs,settings,translation}.json` (**37 scenarios**) | real chat SSE | hallucinated tool names, skill-rule adherence | LLM judge, absolute rubric | **Works.** Last run 2026-07-08 |
| `scripts/eval/tool_liveness/` (TLE, ~20 modules incl. `sweep.py` 26KB, `project_chain.py` 40KB) | real LLM over NL, per tool | **G1 SELECT · G2 SHAPE · G3 EXECUTE · G4 EFFECT** (DB read-back via an independent path) | machine + a proven-non-trivial negative control | **Works.** Matrix 211/224 |
| `scripts/eval/tool_liveness/tool_selection_benchmark.py` | provider-registry direct, **out-of-loop** (whole catalog at once) | pure routing accuracy, no discovery loop | exact-match | **Works.** Qwen3.6 6/6, Gemma 5/6 |

Plus a one-off probe: `docs/eval/tool-liveness/discovery-gap/probe.py` (2026-07-22).

### 5.2 The numbers that matter

**Discoverability scenarios — 2026-07-15 authoritative run**
(`docs/eval/discoverability/2026-07-15-M2-all-scenarios-clear.md`):
**18/18 ≥2/3**, DB- or judge-scored. 13 DB-scored green including the flagship **S06 3/3 (5/5
artifacts)**, S04 3/3 (`kg_projects=1 nodes=6`), S03 3/3, S05 3/3; 2/3 for S06b, S10, S12, S09.

The report is unusually honest about its own methodology, and this matters for anyone re-running it:
- An earlier draft asserting **18/18** was **retracted** as *"premature… assembled from individual
  scenario runs"*; the first authoritative batch did not reproduce it.
- The root cause of the false REDs was **not** the rail: the test account had hit the **200-active-book
  cap** (216 books, eval never cleaned up) so every fixture failed at `book_create`. Fixed by
  `run_m2_batch._free_book_quota()`.
- The final evidence is *"several small batches, not one uninterrupted 51-run batch"*, because a
  concurrent session recreated chat-service ~every 90 minutes and wiped the in-container harness.
- **The headline finding is the most useful sentence in the whole eval corpus:** *"Every 'hard'
  scenario was a fixture or harness gap — never a model-capability ceiling. The mid-tier model drove
  each rail correctly; what failed was around it."*

**Tool liveness — matrix 211/224, 0 broken** (`all-tracks-clear.md:60`); the ship gate ND3 shipped as
**reject-on-`executes:false`** with *"0 tools blocked, 26 warn-on-`null`"* — i.e. **26 tools have an
unknown liveness status and ship anyway**. The literal "must pass G1–G4" bar was consciously
redefined to "not proven-broken" (BOARD.md:26).

**Skill gate — 4 consecutive rounds of zero hallucinated tool names** (2026-07-07 first pass through
2026-07-08 post-all-fixes rerun). Two real bugs were found by it, both harness-adjacent:
`find_tools` silently degrading a blank `intent` into a zero-token search, and `is_curated()` deriving
curated mode only from `enabled_tools` so the **real frontend's skill-only pin path never hot-seeded
the pinned skill's tools** — the model then *"falsely denied real, skill-documented tools exist across
all 5 skill files."* Part B's own tests missed it because every one co-pinned a dummy `enabled_tools`.

**Token cost, live-measured 2026-07-06** (`2026-07-06-tool-catalog-simplification.md:284`): book-scoped
hot-seed against the real 190-tool catalog — 10,317 raw → 3,930 budgeted → **~4,118 total** with the
group directory, vs a **~24,000** baseline. **83% reduction, live-confirmed.**

**Out-of-loop routing ceiling** (`2026-07-21-eager-tool-index-mode.md:41-44`): handed the whole catalog
at once, Qwen3.6 routes **6/6**, Gemma **5/6** — the ceiling the in-loop mechanisms are trying to reach.

**Glossary-build POC** (`2026-07-27-…:93-127`): E1 vertical 8 attrs/entity · E2 horizontal-naive 9
entities but **3.2 attrs, monotonic collapse** first=7→last=1 · E3 planner→executor **13 entities,
5.7 attrs, 116 chars/attr** · E4 steered deep-build **6,887 chars ≈ 10× E1**, zero loops.

### 5.3 The honest state of the instrument

- **Nothing here runs in CI.** Every harness needs a live stack + LM Studio; each is invoked by hand
  via `docker cp` + `docker exec`.
- **The last full discoverability run was 2026-07-15** — before the 07-22 catalog unification (book
  31→15, glossary 42→25, KG 37→?), before the 07-30 capability floor, before the 07-27 pivot. **The
  scoreboard is 19 days and at least four mechanisms stale.**
- The harnesses know things the specs don't: the two-pass COLD/WARM protocol (a headless driver cannot
  click a Tier-A approval card), the five auto-detected hard-reds (empty-intent `find_tools`, silent
  success, unresolved calls, false persistence, async-without-status-read), and one **named known
  gap**: *"a false negative state claim ('there are no suggestions left' when 26 exist — the S03
  baseline) is not caught by the false-persistence detector."*

---

## 6. EXISTING ENFORCEMENT — what is mechanical vs merely written

### 6.1 Mechanical, verified present and wired

| Mechanism | Enforces | Wiring |
|---|---|---|
| **`scripts/tier-tag-gate.py`** | **[verified]** a tool whose name leads with an unambiguous mutation verb must carry non-R `_meta.tier`. Conservative by design: ambiguous verbs go to `REVIEW_VERBS` (reported, never failed); `READ_VERBS` wins left-to-right so `glossary_list_merge_candidates` is a read | pre-commit `:224-225` + `foundation-ci.yml:190` + `lint-foundation.yml:95`; self-tested by `scripts/test_tier_tag_gate.py` |
| `test_frontend_tools_contract.py` (BE) + `frontendToolContract.test.ts` (FE) + `contracts/frontend-tools.contract.json` | Frontend-Tool Contract: closed-set arg ⇒ enum; each resolver reads every required arg and **rejects with an error** (no silent no-op) | pytest / vitest; regen `WRITE_FRONTEND_CONTRACT=1` |
| `panelCatalogContract.test.ts` | advertised `panel_id` enum ⊆ palette-openable ⊆ dock catalog | vitest |
| `test_mcp_server.py` + `test_graph_schema_tools.py` (knowledge) | the IN-8 **4-source drift lock** (`ARG_MODELS` ⇄ `TOOL_DEFINITIONS` ⇄ FastMCP signature ⇄ snapshot) + `CLOSED_SET_ARGS`/`CLOSED_SET_VALUES` | pytest — **knowledge only** |
| `test_mcp_contract.py` (knowledge) | IN-1 scope-from-headers-only, OUT-4 success-discrimination | pytest |
| `schema_federation_guard*.go` (5 Go providers) + `schema_federation.py` + `test_mcp_schema_federation_safe.py` (5 Py providers) | **no boolean subschema in an advertised tool schema** — the bug that dropped all 54 glossary tools (0 of 245) | Go **panics at boot**; Python asserts per-service |
| `find-tools.spec.ts` | the TS/Py/`tool-policy.ts` `GROUP_DIRECTORY` triplicate drift-lock (contract C1's stated invariant) | vitest |
| `test_skill_registry.py::test_every_skills_named_tools_are_in_its_hot_domains` | a skill's prose naming a real catalog tool ⇒ that tool's **domain** is in the skill's `hot_domains`; also fails on a `legacy`-tagged mention (§8b.3) | pytest |
| `mcp_tool_schema_contract_test.go` + `TestLegacyToolsCarryVisibilityMeta` (glossary) | the 7 legacy-tagged tools are pinned | go test |
| `scripts/context-budget-l3-lint.py` | OUT-3 concise-wire (`ensure_ascii=false`, drop-empty) at every tool-result site | pre-commit |
| `scripts/context-budget-defaults-lint.py` | one OUT-2 rule: a LIST tool defaults `detail=summary` + `limit<=25`. **Seeds 14 offenders as FLIP-PENDING ALLOW** — blocks new violations only | pre-commit |
| `scripts/gate-wiring-gate.py` | every `*-gate`/`*-lint` is reachable from pre-commit or a workflow, by predicate (so a gate written tomorrow is in scope), + `--run-all` with `KNOWN_RED` rows that **fail when the gate turns green** | pre-commit + `gates.yml` |
| `scripts/deferral-gate.py` | an id in a `deferral-registry` block must be named by non-comment source or carry a `PROSE_ONLY` row naming its trigger | pre-commit + CI — **[verified] sees zero ids in this domain** (no registry block outside the MMO handoff and DEBT-REGISTER) |
| `validateWorkflow` ship gate (Track D WS-D3) | rejects a workflow step naming a tool proven `executes:false`; `tool_list`/`tool_load` withdraw a proven-broken tool | per BOARD.md ND3 — **[doc]**, not verified this pass |
| `TestOpenAPIRouteConformance` (glossary) | contract-first: an undocumented public `/v1` route reds | go test `-count=1` |

### 6.2 Written down but NOT mechanically enforced

| Rule | Where written | Enforced by |
|---|---|---|
| The **four-tier model** (Intent→Skill→Workflow→Tool) | `2026-07-07-…hardening.md:55-63` | nothing — it is a paragraph in a DRAFT spec |
| **CAT-4 lockstep** — a legacy tool excluded on *both* engines | `mcp-tool-io.md:142` names it as an unenforced gap | nothing |
| **IN-3/IN-4 cross-service** — bare-string-with-enumerated-description; set-return without `get_by_id`/`@small_return` | `mcp-tool-io.md:139` | per-tool hand-written tests only ⇒ a tool with no test slips |
| **IN-8 4-source discipline outside knowledge-service** | `mcp-tool-io.md:141` | *"per-service and uneven"* |
| **The anti-rot rule** (§E: a new control mechanism must declare what it blocks + register as an availability stage) | `2026-07-30-…refactor.md:121-128` | nothing — and **[verified]** it has no row in `docs/standards/README.md` (DEBT-REGISTER 2026-07-30-05) |
| **Cross-mechanism invariant** — *"for every step of a pinned rail, availability is never Withheld"* | same spec §D | nothing. *"This is the test that fails today."* |
| **C1–C6 frozen contracts** | `contracts.md` | C1 has a drift-lock; **C2/C3/C4/C5/C6 have no gate.** A C3 `steps` schema change reds nothing |
| **The MCP-first invariant** for new agentic logic | CLAUDE.md, standards README:83 | *"review; new agentic HTTP tracked in Deferred"* — convention |
| **Verify-by-EFFECT** (Part 3) | `mcp-tool-io.md:77-83` | the TLE harness — which is not in CI |
| **Skill coverage bar** (≥10 tools ⇒ dedicated skill) | `2026-07-07-…standard.md:114-119` | nothing. *"there is no process that flags 'this domain crossed a complexity threshold'"* |

### 6.3 The pattern

Enforcement is **strong per-tool and per-schema**, and **absent per-system**. Every gate above
validates one artifact against one other artifact. Not one gate validates a *mechanism against another
mechanism* — which is precisely the failure class the 07-30 incident belongs to, and precisely what
the project wrote down and did not build.

---

## 7. THE HOLE — what has never been decided

### 7.1 Plainly: no document assigns a tool to a skill group.

I searched for it. `grep -ril "skill group\|skill-group\|tool group\|toolgroup" docs/` returns four
files, and in every one the phrase means something else:

- `2026-06-10-glossary-assistant-architecture.md:116-118` — *"advertise the glossary tool group on
  every book-scoped surface"*, with OD-4 asking *which surfaces* get it. This is **domain × surface**,
  not a group membership.
- `2026-07-06-tool-catalog-simplification.md` — "group" is `GROUP_DIRECTORY`, i.e. the **domain
  prefix** (`glossary`, `story`, …), of which there are 12.
- The two writing-studio files use it descriptively.

`grep -rniE "every (mcp )?tool must (belong|sit|be (in|assigned))" docs/` returns **nothing**.

### 7.2 The finest granularity ever specified is a domain prefix — and the code says so

`SkillDef.hot_domains` is *"the GROUP_DIRECTORY domain(s) this skill's prose names tools from
DIRECTLY"* — a set of ~12 possible values, resolved from a tool's **name prefix**
(`_domain_of()` + `_DOMAIN_ALIASES`). It is not a tool list.

**[verified] the code carries the admission inline**, `services/chat-service/app/services/skill_registry.py:154`:

> `# surface_hot_domains() are DOMAIN-level only, not per-tool — a real constraint,`

That comment is the honest one-line summary of this entire audit. Everything downstream follows from
it: because the association is domain-level, the seeding layer can only reason in whole domains, so a
domain that exceeds the token budget must be **trimmed by a heuristic** (`budget_names_by_tokens`,
reads-first) — and that heuristic is what starved `book_update_details`
(`2026-07-21-eager-tool-index-mode.md:5-8`), what starved the knowledge domain's **write** tools
(umbrella §4.4: *"the write the co-writer most needs is structurally never on the hot path"*), and what
forced the `ALWAYS_HOT_WRITES` allowlist as a patch on top of the patch.

### 7.3 No document requires a tool to belong to a workflow

The C3 workflow schema (`contracts.md:63-84`) declares the relation in **one direction only**:
a workflow's `steps[].tool` names an exact tool that *"must be in C1 catalog ∩ policy-allowed."* There
is no inverse constraint, no coverage requirement, and no gate that would notice a tool belonging to
zero workflows.

Twelve workflows exist. **[doc]** the catalog is ~193 federated + 7 admin tools (umbrella Appendix A,
2026-07-09) or 223 including consumer-local (TLE README §2, same date), reduced by the 07-22
unification wave (book 31→~15, glossary 42→25, KG 37→?). Twelve rails cannot possibly cover it, and no
document states what should happen to the remainder.

### 7.4 The partial attempts, named

Three things come close and each stops one level short. They are the raw material for the unified
spec, and it should say explicitly which it is generalising:

1. **`SkillDef.hot_domains` + its claims lint** — the *only* mechanism that binds a skill to tools.
   It binds to **domains**, and the lint is one-directional (a named tool must be in a hot domain;
   nothing asserts a tool is named by any skill). Generalising this from domain-set to tool-set is
   the smallest change that would close the hole.
2. **The C3 workflow `steps[].tool`** — the only place a tool is named as part of a procedure.
   Forward-only; no coverage inverse.
3. **`ALWAYS_HOT_WRITES` / `filter_intent_gated_setup_tools` / `budget_rail_tools`** — three
   *tool-level* allowlists and denylists that exist precisely because the domain-level abstraction
   cannot express "this specific tool must survive the trim" or "this specific tool must not be
   reachable on this turn." They are the hole's negative space: hand-maintained per-tool lists,
   each in its own file, none registered anywhere, none aware of the others.

### 7.5 The three questions the unified spec must answer, that no existing doc does

1. **What is a tool's home?** Today a tool has a *name prefix* (→ domain), a `_meta.tier`, a
   `_meta.scope`, an optional `_meta.visibility`, an optional `_meta.async`/`paid`, and possibly a
   mention in a skill's prose and a step in one of 12 workflows. Nothing declares which skill *owns*
   it, and nothing can answer "which capability group is this tool part of" without a prefix regex.
2. **What happens to a tool that belongs to nothing?** There is no rule, no gate, no report. The
   closest analogue that *does* work is `TestOpenAPIRouteConformance` for HTTP routes and the TLE
   matrix's *"a tool with no authored NL probe is a RED cell"* — both of which prove the shape is
   buildable here.
3. **Which of the five availability mechanisms wins, and where is that written?** Per the project's
   own diagnosis: *"precedence between guards is implicit in code order across 7,000 lines… no guard
   declares what it removes, so the next one cannot know what it broke."* This is `D-CHAT-CONTROL-PLANE`
   §A/§C, deferred since 2026-07-30, prose-only, nothing built.

### 7.6 The sentence to put at the top of the unified spec

The project already wrote it, on 2026-07-30, about its own turn loop, and it generalises exactly:

> *"That is the honest answer to 'is the architecture broken, or did it never exist?' — for the turn
> loop specifically, **it never existed**. What exists is a very well-documented pile of correct
> patches."*

The corollary this audit adds: **the pile is well-documented, but the documents were never retired,
so the pile has thirteen top layers and the reader cannot tell which one is current.** Any unified
spec that does not explicitly **retire** its predecessors — with a status banner on each superseded
doc, the way `2026-07-21-eager-tool-index-mode.md` correctly did — will become the fourteenth.

---

## Appendix — source inventory

**Standards read:** `docs/standards/README.md` (248 ln) · `mcp-tool-io.md` (163) ·
`agent-control-plane.md` (58) · `agent-extensibility.md` (116) · `sdk-first.md` (45); consulted:
`non-vacuity.md`, `settings-and-config.md`, `scope-separation.md`.

**Specs read in full or in substance:** `2026-06-10-glossary-assistant-architecture.md` ·
`2026-07-06-tool-catalog-simplification.md` (298) · `2026-07-07-mcp-discovery-and-reliability-hardening.md`
(384) · `2026-07-07-skill-authoring-and-mcp-exposure-standard.md` (419) ·
`2026-07-09-agent-discoverability-and-workflow/{README,architecture,contracts,tracks/BOARD}.md` ·
`2026-07-09-mcp-tool-liveness-eval/README.md` · `2026-07-13-all-tracks-clear.md` ·
`2026-07-19-frontend-tools-mcp-migration.md` · `2026-07-21-eager-tool-index-mode.md` ·
`2026-07-22-{book-tools-redesign,glossary-catalog-unification,kg-catalog-unification}.md` ·
`2026-07-27-glossary-kg-build-workflows.md` · `2026-07-28-intent-collection-fsm.md` ·
`2026-07-30-chat-service-control-plane-refactor.md` ·
`2026-08-03-glossary-kg-entity-refactor/DEBT-REGISTER.md`.

**Eval:** `scripts/eval/README.md` · `discoverability_scenarios/README.md` ·
`tool_liveness/README.md` · `docs/eval/discoverability/2026-07-15-M2-all-scenarios-clear.md` ·
`docs/eval/tool-liveness/discovery-gap/RESULTS.md`; directory inventories of
`docs/eval/{discoverability,tool-liveness,skill-authoring}` and `scripts/eval/*`.

**Backlog:** `docs/sessions/SESSION_HANDOFF.md` (10,198 ln — heading map + full D-id extraction +
`:2218-2278`) · `docs/deferred/DEFERRED.md` (271 ln, grepped).

**Greps run to confirm/refute doc claims (12):** `tier-tag-gate` presence + wiring + absence from the
standards index · `find_tools` model-facing status · `tool_list`/`tool_load` presence ·
`is_legacy_tool` vs `include_deprecated` call sites · `SkillDef` fields · `deferral-registry:begin`
repo-wide · `PROSE_ONLY` registry contents · `"skill group"`/`"tool group"` repo-wide ·
`"every tool must belong"` repo-wide · chat-service service-module inventory ·
`intent_workflows.py`/`workflow_runner.py`/`agent_surface.py` headers · workflow seeding location.
