# Audit 05 — Workflow definition, storage, execution; and agent-registry-service as SSOT

**Scope:** the PRODUCT's agentic workflows (curated multi-step rails the chat agent runs for users).
Explicitly excludes the repo's human dev workflow (`agentic-workflow/`, `scripts/workflow-gate.py`, `.github/workflows`).
**Method:** read-only. Every claim below carries a `file:line`. Behaviour verified by running code where the
source was ambiguous (see §7.1 — a Go JSON round-trip was executed to settle a silent-drop question).
**Constraint honoured:** `stream_service.py` read only via targeted `grep -n` + narrow `sed` windows.

---

## 1. WHAT IS A WORKFLOW — the concrete data model

A **workflow** is a persisted, tiered, ordered list of *named tool calls* plus prose. It is **data**, not code,
and it is **not executable** — nothing in the system runs a workflow. It is rendered into the model's context
and the model is asked to follow it.

### 1.1 Storage — one table, one home

`workflows` in `loreweave_agent_registry` — `services/agent-registry-service/internal/migrate/migrate.go:395-423`:

| column | type | note |
|---|---|---|
| `workflow_id` | UUID pk | |
| `tier` | `system\|user\|book` | 3-tier tenancy, CHECK-pinned scope key (`:413-417`) |
| `owner_user_id` / `book_id` | UUID | exactly one non-null per tier |
| `slug` | TEXT | per-tier partial UNIQUE (`:421-423`) — correct, not a global UNIQUE |
| `title`, `description` | TEXT | |
| `surfaces` | TEXT[] | see §7.3 — **two incompatible vocabularies** |
| `inputs` | JSONB | `{ "<name>": "required"\|"optional" }` |
| `steps` | JSONB | the C3 step array |
| `notes_md` | TEXT | prose the agent reads; **not executed** |
| `status` | `draft\|published\|archived` | |
| `source` | `user\|agent\|system\|import` | |
| `used_count`, `last_run_at` | | **both dead — never written anywhere** (grep: no UPDATE touches them) |

Satellites: `workflow_proposals` (`:427-450`), `workflow_revisions` (`:453-464`), `workflow_enablement`
(`:471-477`), and `mode_bindings` (`:791-813`) which pins workflows per mode.

### 1.2 The step schema

`services/agent-registry-service/internal/api/workflows.go:40-66`:

```go
type workflowStepIn struct {
    ID        string            `json:"id"`         // kebab, unique in rail
    Tool      string            `json:"tool"`       // exact tool name — a FREE STRING
    Gate      string            `json:"gate"`       // none | confirm | approval
    When      string            `json:"when,omitempty"`      // "predicate ... (evaluated by the runner)"
    Repeat    string            `json:"repeat,omitempty"`    // none | per_item:<inputs key>
    InputsMap map[string]string `json:"inputs_map,omitempty"`
    AsyncJob  *bool             `json:"async_job,omitempty"`
    DoneWhen  string            `json:"done_when,omitempty"` // "<key> <op> <n>", closed grammar
}
```

`done_when` grammar is closed and enforced: `workflows.go:76` (`doneWhenRe`), keys single-sourced from
`contracts/book-state-keys.contract.json`. Gates: `workflows.go:28` `validWorkflowGates = {none, confirm, approval}`,
mirrored in `chat-service/app/services/workflow_runner.py:35`.

**Fields that are declared but inert:**
- `when` — its jsonschema says *"evaluated by the runner"* (`workflows.go:44`). **No runner evaluates it.**
  The only consumer copies it verbatim into the rail dict (`workflow_runner.py:150-151`) and
  `pinned_rail_block` never even renders it (`workflow_runner.py:300-306` renders id/tool/gate/async_job only).
- `repeat` — see §7.1, it is dropped in transit and is semantically **two different things** in two layers.
- `inputs` / `inputs_map` — surfaced to the model as text; never bound to anything.

### 1.3 Who authors one

Three authors, three paths, **only one of which is validated**:

| author | path | validated? |
|---|---|---|
| **platform** (System tier) | raw `INSERT` in `migrate.go:497-782` | **NO** — bypasses `validateWorkflow` entirely |
| **agent** | MCP `registry_propose_workflow` → `workflow_proposals` → human approve | yes (`validateWorkflow`) |
| **user** | no direct create route. `server.go:296-298`: *"Create stays propose→approve (no direct POST)"* — so a user can only author one by asking the agent to propose it | yes, via the same path |

---

## 2. INVENTORY — every workflow that exists today

**12 System-tier workflows**, all defined *only* as SQL seed literals in
`services/agent-registry-service/internal/migrate/migrate.go`. There is no YAML, no code constant, no duplicate.

| # | slug | line | steps → tools | reachable via |
|---|---|---|---|---|
| W1 | `glossary-bootstrap` | 498 | `glossary_list_system_standards` → `glossary_adopt_standards` → `glossary_confirm_action`(confirm) → `glossary_book_ontology_read` | **discovery only** |
| W3 | `entity-triage` | 527 | `glossary_curation_list` → `glossary_propose_curation`(confirm) ×2 → `glossary_curation_list` (`done_when: suggestions < 1`) | intent |
| W2 | `populate-from-notes` | 549 | `glossary_book_ontology_read` → `glossary_extract_entities_from_doc` → `glossary_propose_entities` | **discovery only** |
| W4 | `kg-build` | 570 | `glossary_book_ontology_read` → `kg_project_create` → `kg_add_nodes` → `kg_build`(async) | intent |
| — | `vision-to-book` | 596 | 9 steps: standards→adopt→confirm→read-back→extract→propose→kg_project_create→kg_add_nodes→`plan_propose_spec` | **mode binding** (`write`) |
| W5 | `translation-pass` | 629 | `translation_coverage` → `translation_start_job`(async) → `translation_retranslate_dirty`(async) | intent |
| W10 | `draw-a-map` | 649 | `world_list` → `world_map_create` → `world_map_add_marker` → `world_map_add_region` | intent |
| W11 | `lore-so-far` | 670 | `story_search` (single step) | intent |
| W9 | `canon-check` | 693 | `composition_list_canon_rules` → `book_list` → `book_read` | intent |
| W6 | `chapter-compose` | 722 | `book_list` → `book_chapter_save_draft` | intent |
| W7 | `build-a-book` | 741 | `plan_propose_spec`(async) → `composition_arc_suggest` → `composition_outline_node_edit` | intent |
| W12 | `autonomous-drafting` | 767 | `plan_bootstrap_propose` → `plan_bootstrap_apply`(confirm) → `composition_authoring_run_manage` ×2 → `composition_authoring_run_get` | intent |

**Real vs example:** all 12 are **real, seeded, production** rows. There are **zero** user-tier or book-tier
workflows anywhere in the repo (they can only be created at runtime by agent proposal + human approval).
The only fixture workflows are Python test dicts (`tests/test_workflow_runner.py:9-25`) and Go test structs
(`workflows_test.go:13-27`).

**Distinct tools named across all 12 rails: 30.** The liveness manifest alone knows **223** tools
(`contracts/tool-liveness.json`). **≈13% tool coverage** by the workflow layer.

---

## 3. EXECUTION — end to end

### 3.1 There is no step runner

The name is a fiction the code repeats to itself. `workflow_runner.py` contains **no execution**: it is
`workflow_list_result` (a sort), `workflow_load_result` (a normalise), and `pinned_rail_block` (a string
builder). Nothing dispatches a step. The system's actual mechanism is: **render the rail as prose, then hope.**

### 3.2 How a rail gets into context — two entry paths

**(a) PINNED (the load-bearing path).** `stream_service.py:5151-5167` fetches the turn's workflows +
mode-binding in one hop. `:5426-5448` unions the mode-binding pins with intent pins. `:5530-5533` calls
`pinned_rail_block(turn_workflows, _pinned_slugs, _turn_async_tools, progress_by_slug=...)`, whose output is
injected as a system tail-block (`:5470`, `pinned_rail_text` in `_tail_blocks`). Step tools are pre-activated.

**(b) DISCOVERED.** Two consumer-local meta-tools, advertised only when the turn has workflows
(`stream_service.py:1362-1365`): `workflow_list` (`:2984-2995`, deterministic enumeration) and
`workflow_load` (`:3002-3053`). `workflow_load` returns the rail **and activates the step tools** into
`active_tool_names` + persists them across turns (`:3020-3040`). It is explicitly "no execution":
`workflow_runner.py:96-98` — *"Loading also makes the step tools callable; it does NOT run anything."*

### 3.3 Advance / complete — the rail driver

`compute_rail_progress` (`sdks/python/loreweave_agent_control/rail.py:189-327`, re-exported through the shim
`chat-service/app/services/rail_progress.py`) answers *"where is the user?"* from two sources, in order:

1. **`done_when` artifact** — a predicate over a live probe of the book (`probe_book_state`). This is the
   honest signal; it can call a tool's "success" a lie (`rail.py:~300`: *"the book shows key=N — the effect
   never landed"*).
2. **the session's persisted tool-call log** — `succeeded_tool_counts`, consumed once per step in rail order
   (`rail.py:255-265`) so a tool used by two steps needs two successes.

`next_index` = first not-done step. The rendered block goes **last** in the rail text, deliberately
(`workflow_runner.py:321-327` — recency).

**Drive:** `RAIL_REDRIVE_CAP = 8` (`stream_service.py:588`) re-drives the rail after the model stops, with a
per-step cap of 2 nudges. Enforcement modes live in the SDK: `GATE_OFF / GATE_DONE_SUPPRESS / GATE_STEP_LOCK`
(`rail.py:707-729`) — `step_lock` advertises *only* the current step's tool; `done_suppress` drops the tools
of steps already done **this session** (`rail.py:702-705`, deliberately `session_done`, not the durable
`done` — the comment at `rail.py:159-168` records the bug where a plan proposed days earlier permanently
disarmed `plan_propose_spec`).

### 3.4 Gate on confirmation — the gate does **not** gate

`grep` for every reader of a step's `gate` (`workflow_runner.py:137,189,302`; `rail.py:243`) proves the field
has exactly two uses:

- **prose**: `workflow_runner.py:302-303` appends `[confirm: the user must approve]` to the rendered line.
- **progress inference**: `rail.py:238-251` — a `confirm` step is "done" iff the step it references in
  `inputs_map` is done, because a confirm has no artifact of its own.

**Nothing suspends on a step's gate.** The actual suspension comes from the *tool's own* Tier-A/class-C
`confirm_token` machinery, entirely independent of the workflow. `workflow_runner.py:14-15` states this
honestly (*"each step's tool call goes through the EXISTING per-tool tier/approval gate"*), but the
consequence is not acknowledged: **`gate` is decorative**. Authoring `gate:"approval"` on a Tier-R read tool
produces a rail that *tells the model* the user must approve, while the tool auto-runs. Nothing detects the
mismatch. (The registry validates the gate is in the enum — `workflows.go:186-188` — but never that the named
tool's tier can honour it.)

### 3.5 Failure

There is no failure path, because there is no execution. Failure handling is **three prose sentences**:
`workflow_runner.py:205-208` (*"If a step fails, STOP — report which steps completed"*), the same clause in
each seed's `notes_md`, and `workflow_skill.py:61-64`. The mechanical residue is in the drive loop only:
`stream_service.py:2495-2496` computes `_step_tools_hit` / `_step_tools_tried` (rail step tools that succeeded
vs errored this turn) and feeds the honesty directive. A step whose tool 404s simply never becomes done, and
the rail re-drives until `RAIL_REDRIVE_CAP`.

### 3.6 Step ↔ RAIL

A **rail** *is* a workflow's step list, once resolved for a turn. `_rail_specs` is literally
`list[tuple[slug, steps]]` (`stream_service.py:5514`). One workflow step → one `StepProgress`
(`rail.py:149-167`). The rail adds three things the workflow row does not have: the **book-state probe**, the
**session call log**, and the **action-space gate**. A workflow is the recipe; a rail is that recipe joined to
observed reality.

---

## 4. WORKFLOW → SKILL → TOOL BINDING

### 4.1 A step names a TOOL, never a skill

`workflowStepIn.Tool` (`workflows.go:42`) is a bare string. There is **no** `skill` field on a step, and no
table associating a workflow with a skill. Skills and workflows are siblings that never reference each other:

- `mode_bindings.inject_skills` and `mode_bindings.inject_workflows` are two independent TEXT[] columns
  (`migrate.go:797-798`) — the only place the two concepts co-occur, and they are unioned side by side, not
  linked (`mode_bindings.go:170-171`).
- `workflow_skill.py` is **not** a skill *for* workflows — despite the name it is a static, hardcoded prose
  fragment about cross-service *ordering* (`workflow_skill.py:23-65`), concatenated onto the universal skill
  at `chat-service/app/services/skill_registry.py:60-61`. It has no relationship to the `workflows` table and
  names its own hardcoded sequence (books → translate → glossary → wiki) that no seeded workflow implements.

**So the owner's premise "every MCP tool belongs to a skill group and sits inside one or more workflows" has
no representation in the data model at all.** There is no group table, no skill↔tool edge, no workflow↔skill
edge.

### 4.2 Is the tool name validated? — **NO, at four consecutive layers**

**Layer 1 — the author path deliberately abstains.** `workflows.go:135-138`:

> *"It deliberately does NOT check tool-catalog membership — the step-runner (chat-service, WS-2b) owns the
> catalog + policy and fails an unknown/forbidden tool gracefully at run time"*

The only tool check is `toolBlocked(st.Tool)` (`workflows.go:181`), which rejects a tool the liveness manifest
records as **proven broken** (`liveness.go:79-82`). An **absent** tool is `toolUnchecked` (`liveness.go:90-93`)
and produces only a non-blocking `Warnings[]` string (`liveness.go:99-121`, attached at `workflows.go:405`).

**Layer 2 — the promised runtime check does not exist.** The docstring above names an owner that never
implements it. Exhaustive grep for consumers of `step["tool"]` across `services/chat-service/app` and
`sdks/python/loreweave_agent_control` finds **only**: `workflow_runner.py:136` (copy into the rail),
`workflow_runner.py:183-187` (collect names to activate), `stream_service.py:1963-1964` (collect for
telemetry), and `rail.py` (progress bookkeeping). **Nothing compares a step tool to the catalog.**

**Layer 3 — activation silently passes an unknown name through.** `chat-service/app/services/tool_surface.py:142`:

```python
kept: set[str] = {n for n in want if n not in defs}  # non-catalog → passthrough
```

A step tool absent from the catalog is added to `active_tool_names` **free of budget cost and with no
diagnostic**, then never advertised (no schema exists). The model is handed a rail naming a tool it cannot
call, and the `workflow_load` payload reports success.

**Layer 4 — the seeds skip everything.** The System seeds are raw `INSERT`s (`migrate.go:497-782`); they never
touch `validateWorkflow` and therefore never touch `toolBlocked` either. The seed lint
(`migrate_lint_test.go`) checks apostrophes (`:32`), seed presence (`:84`), `DO UPDATE` (`:118`), notes budget
(`:142`), and `done_when` grammar (`:160`) — **it does not check `tool`, `gate`, `repeat`, or step `id`.**

**Proof it matters:** the seeds name 30 tools; **8 of them are absent from the liveness manifest**
(`glossary_confirm_action`, `glossary_curation_list`, `glossary_propose_curation`, `kg_add_nodes`, `kg_build`,
`world_list`, `world_map_create`, `world_map_add_marker`, `world_map_add_region`, `book_read`,
`composition_outline_node_edit`, `plan_bootstrap_propose`, `plan_bootstrap_apply`,
`composition_authoring_run_manage`). All of them *do* exist in service source today (verified by grep against
`services/*/…/mcp*.go|.py`), so the seeds are currently correct — **by luck and manual re-verification, not by
any mechanism.** The seed comments themselves record two rounds of hand-checking
(`migrate.go:545-547`, `migrate.go:620-627`: *"The audit's translation_run/canon_check names were WRONG
(verified 2026-07-12: they do not exist)"*). A workflow shipped with a hallucinated tool name is exactly what
that comment describes, and only a human reading caught it.

Note also `composition_authoring_run_manage` is in the liveness manifest as **absent** while
`composition_authoring_run_start` **is present** — a strong hint the tool was consolidated after the manifest
snapshot, with no gate noticing either way.

---

## 5. INTENT ROUTING — utterance → workflow

### 5.1 What it matches on

`chat-service/app/services/intent_workflows.py:32-105` — a hand-written list of **43 raw regexes** over the
lowercased user message, grouped by slug, compiled once (`:107-109`). `intent_pinned_workflows(text,
visible_slugs)` (`:112-126`) returns every slug with ≥1 matching pattern, filtered to the turn's visible set.
No LLM, no embedding, no scoring. Called at `stream_service.py:5432-5433`; result unioned with the mode-binding
pins at `:5439`.

### 5.2 How brittle — very, in five specific ways

1. **The slug list is a free string with no referential integrity.** `intent_workflows.py:33` writes
   `("entity-triage", [...])` with nothing tying it to `migrate.go:527`. Rename a seeded slug and the intent
   entry silently stops firing — `:122-123` drops it via the `visible_slugs` filter with **no log**. There is
   no test asserting the intent slug set ⊆ the seeded slug set. (`tests/test_intent_workflows.py:9-10` defines
   its own hand-typed `ALL` set, which is already stale: it omits `lore-so-far`, which the module does route.)
2. **Overbroad single-word patterns.** `r"\bcanon\b"` and `r"\btranslate\b"` (`:46`, `:66`) fire on any
   mention — *"is this canon-compliant with my glossary?"* pins `canon-check`; *"how do I translate the UI to
   Vietnamese"* pins `translation-pass`. `r"\bso\s+far\b"` (`:99`) pins the reader rail on *"the draft is going
   well so far"*.
3. **English-only.** Every pattern is English. This project's dogfood corpus and its PO are Vietnamese.
   A Vietnamese-language request pins **nothing** — every non-flagship rail becomes discovery-only.
4. **2 of 12 rails have no intent entry at all** — `glossary-bootstrap` and `populate-from-notes`. They are
   reachable only if the model spontaneously calls `workflow_list` → `workflow_load`, which is the measured
   failure the whole pinning mechanism exists to work around (`intent_workflows.py:8-11` cites S03 0/3,
   S04 1/3). `glossary-bootstrap` is *especially* odd: it is the only rail visible on a bookless chat turn
   (surfaces `{}`), and it is the one rail intent routing cannot reach.
5. **Intent pins evaporate on resume.** The confirm-suspend/resume path recomputes the drive context from the
   **mode binding only** — `stream_service.py:610-616`:
   ```python
   binding = wfs.mode_binding
   if not (binding and binding.inject_workflows): return [], False, None, frozenset(), []
   pinned = [s for s in binding.inject_workflows if s in visible]
   ```
   `intent_pinned_workflows` is never called here. So `entity-triage`, whose *second and third steps are both
   `gate:"confirm"`* (`migrate.go:532-533`), pins on turn 1, suspends at the confirm — and comes back with the
   rail **not driven**. Only `vision-to-book` (the mode-binding pin) survives a resume. The same function also
   hardcodes `surface="book"` (`:609`) while the fresh path computes `admin|editor|book|chat`
   (`:5157`), so an editor-turn resume additionally sees a different visible set than the turn it is resuming.

---

## 6. THE REGISTRY SERVICE — inventory and SSOT assessment

### 6.1 What agent-registry-service actually stores

18 tables (`migrate.go`), 7 resource families:

| resource | tables | public routes (`server.go`) | MCP tools | internal reader |
|---|---|---|---|---|
| **plugins** (bundle unit) | `plugins`, `plugin_enablement` | `:225-233` incl. import/export/cascade | — | via `/internal/effective-catalog` |
| **skills** (prompt-only) | `skills`, `skill_proposals`, `skill_revisions`, `skill_enablement` | `:236-245` | `registry_list_skills`, `registry_get_skill`, `registry_propose_skill`, `registry_update_skill`, `registry_set_skill_enabled` | `/internal/skills` ✔ honours enablement |
| **workflows** | `workflows`, `workflow_proposals`, `workflow_revisions`, `workflow_enablement` | `:295-309` | `registry_list_workflows`, `registry_get_workflow`, `registry_propose_workflow`, `registry_update_workflow` | `/internal/workflows` ✘ **ignores enablement** |
| **MCP servers** | `mcp_server_registrations`, `mcp_server_enablement`, `oauth_flows`, `registry_ingest_queue` | `:248-256`, `:277-280` | — | `/internal/effective-mcp-servers`, `/internal/mcp-servers/{id}/credentials` |
| **slash commands** | `slash_commands` | `:259-262` | — | `/internal/commands` |
| **hooks** (declarative) | `hooks` | `:265-268` | — | `/internal/hooks` |
| **subagents** | `subagent_defs` | `:271-274` | — | `/internal/subagents` |
| **mode bindings** | `mode_bindings` | `:291-292` | — | rides `/internal/workflows` |
| **cross-cutting** | `registry_audit`, `registry_meta` (`catalog_version`) | `:311-312` | — | — |

Auth is properly layered: platform HS256 JWT for `/v1/*` (`server.go:358-372`), RS256 admin JWT with
`admin:write` for System-tier writes (`:398-418`), `X-Internal-Token` constant-time compare, fail-closed on an
empty configured token (`:336-349`), E0 book grants for book-tier (`:95-123`), anti-oracle 404s throughout.
Tenancy is genuinely correct — per-tier partial UNIQUE indexes everywhere, no global `UNIQUE(slug)`.

### 6.2 Verdict: **a strong PARTIAL SSOT for authored artefacts; not an SSOT for tools.**

It is a real service with real tables, real tenancy, real HITL, and a real internal read surface — not a shell.
For **workflows** specifically it is a *complete* SSOT: one home, no code duplicate, no YAML.

What is missing for it to be *the* SSOT of the tool-loading architecture:

1. **No tool inventory.** There is no `tools` table. The MCP tool catalog is assembled by **ai-gateway**
   federation at runtime; chat-service reads it via `knowledge_client.get_tool_definitions`
   (`stream_service.py:5396`). The registry knows tool names only as opaque strings inside `workflows.steps`
   and inside `subagent_defs.tool_scope` globs (`migrate.go:312`). **It cannot enumerate tools, so it cannot
   check anything about them.**
2. **No skill-group / tool-category table.** The C1 category taxonomy — the nearest thing to "skill group" —
   lives in **three** places in three languages: `ai-gateway/src/federation/find-tools.ts:27` (SSOT by
   convention), `chat-service/app/services/tool_discovery.py:65` (*"keep in lockstep"*), and
   `agent-registry/internal/api/mode_bindings.go:46-50` (`validCategories`). **They have already drifted** —
   see §7.4.
3. **No skill→tool and no workflow→skill edge.** Both would be new tables.
4. **System skill BODIES are not in the registry.** `migrate.go:381-387` seeds 5 System skills with
   `body_md = '(System skill — body served by chat-service skill_registry)'` — a metadata stub pointing at
   Python. So for skills the registry is a *catalog with a hole*.
5. **Tool consent/permission state is in chat-service**, not the registry (`chat-service/app/main.py:191`,
   `tool_permissions` router; the FE `PermissionsView` sits in the Extensions page next to registry-backed
   tabs, which reads as one system and is not).
6. **The public API is uncontracted.** `contracts/api/agent-registry.yaml` documents 13 paths — plugins,
   mcp-servers, oauth, usage, audit. It documents **zero** workflow routes and **zero** skill routes, and there
   is no route-conformance test (the glossary-service pattern named in `CLAUDE.md` was never applied here).

---

## 7. DEFECTS & INCOHERENCES (evidence-backed)

### 7.1 🔴 `repeat` is silently destroyed in transit — and it is load-bearing for the action gate

The field is **two different types with two different meanings** in the same pipeline:

- **Go / C3:** `Repeat string` — `"none" | "per_item:<inputs key>"`, validated by `validateRepeat`
  (`workflows.go:204-220`), unit-tested (`workflows_test.go:58-63, 80-86`).
- **SDK rail driver:** a **boolean** — `rail.py:321`: `repeat=bool(st.get("repeat"))`, documented at
  `rail.py:156-157` as *"a legitimately-repeatable step whose tool must NEVER be action-gated as done"*.

The seeds author the **boolean** meaning — `"repeat":true` — in **6 rails / 13 steps**
(`migrate.go:576, 600-608, 727, 745`). Unmarshalling that into `Repeat string` is a type error. The error is
**discarded**: `workflows.go:850` `_ = json.Unmarshal(stepsJSON, &wf.Steps)`.

Executed to confirm (Go 1.x, the real struct):

```
err: json: cannot unmarshal bool into Go struct field workflowStepIn.repeat of type string
len: 4
  place-cast done_when="connections > 0" repeat=""
re-marshal: [... {"id":"place-cast","tool":"kg_add_nodes","gate":"none","done_when":"connections > 0"} ...]
```

Other steps survive (Go's decoder saves the first type error and continues), `done_when` survives, **`repeat`
is gone from the wire.** So `rail.py:321` reads `False` for every registry-served workflow, and the
`done_suppress` gate at `rail.py:717-729` (`if d and not s.repeat: done_tools.add(s.tool)`) **strips the tool
of every done step, including the 13 steps explicitly marked repeatable to prevent exactly that.**

The irony is documented: `workflows.go:61-65` and `workflows_test.go:180-209`
(`TestDoneWhen_SurvivesTheStepsRoundTrip`) exist *specifically* because of this drop-on-serialize trap — for
`done_when`. Nobody wrote the twin test for `repeat`, and the seed lint does not check `repeat` values
against `validateRepeat`'s grammar.

**Second-order:** because `repeat` is a bool in the seeds, the C3 `per_item:<key>` fan-out feature has **zero**
production users and cannot be reached from the seed path at all.

### 7.2 🔴 The per-user workflow disable toggle is write-only — the GUI lies

- `PUT /v1/agent-registry/workflows/{id}/enablement` writes `workflow_enablement`
  (`workflows_rest.go:290-338`).
- `GET /v1/agent-registry/workflows` (the FE rack/manager) **LEFT JOINs** it and returns the effective
  `enabled` (`workflows_rest.go:55-57, 82`), so the UI toggle flips to "disabled".
- `GET /internal/workflows` — the **only** reader the agent uses — does **not** join it. Full query,
  `workflows.go:817-823`:
  ```sql
  SELECT slug,title,description,tier,surfaces,inputs,steps,notes_md FROM workflows
   WHERE status='published' AND (tier='system' OR (tier='user' AND owner_user_id=$1)
                                 OR (tier='book' AND book_id=$2))
  ```
  `grep -rn workflow_enablement internal/` returns exactly 3 non-test hits, all in `workflows_rest.go`.

The sibling proves it is an oversight, not a design: `internalSkills` **does** join `skill_enablement`
(`skills_internal.go:10, 48`). So a user who disables a workflow in the Extensions UI sees "disabled" and the
agent keeps listing and pinning it forever. This is precisely the `SET-1` *stored-but-unread settings blob*
the repo's own Settings standard names. No test covers `internalWorkflows` at all (`grep '^func Test'`
across `workflows_test.go` + `workflows_rest_test.go`).

### 7.3 🔴 Two disjoint `surfaces` vocabularies — user/agent-authored workflows are unrunnable where work happens

- **Authoring enum** (validated + advertised to the model as a closed set):
  `skills.go:24` `validSurfaces = {"chat","compose","translate","admin"}`, enforced for workflows at
  `workflows.go:146`, exposed as `enumSurfaces` on `registry_propose_workflow`/`registry_update_workflow`
  (`mcp_server.go:84, 94`).
- **Runtime surface actually sent:** `stream_service.py:5157`
  `_wf_surface = "admin" if _admin else ("editor" if _editor else ("book" if _book_scoped else "chat"))`
  → `{admin, editor, book, chat}`.
- **Seeds use:** `{book, editor}` ×6, `{book, editor, studio}` ×4, `{book}` ×1, `{}` ×1 — i.e. **`book`,
  `editor` and `studio`, none of which the authoring enum permits.**

Overlap between what an author may declare and what the runtime emits is `{chat, admin}`. `internalWorkflows`
filters hard: `workflows.go:842` `if surface != "" && len(wf.Surfaces) > 0 && !contains(wf.Surfaces, surface)`.
**Therefore an agent- or user-authored workflow declaring `surfaces:["chat"]` — the natural choice, and the
first enum value — is invisible on every book-scoped and editor turn**, i.e. on every turn where book work
happens. The only way to author a usable workflow is to omit `surfaces` entirely.

`studio` is dead in a third way: `_wf_surface` never produces it, so the tag on 4 seeds matches nothing.

The patchwork is visible in the seed itself — `migrate.go:500-502`:
> *"surfaces EMPTY = visible on every surface. A book-scoped chat turn resolves the runtime surface key "book"
> (not "chat"), so a ['chat'] filter would hide this exact workflow on the turn that needs it."*

The author diagnosed the enum mismatch precisely, then worked around it for **one row** instead of fixing the
enum.

### 7.4 🟠 The tool-category ("skill group") list has drifted across its three copies

`mode_bindings.go:46-50` `validCategories` = `{book, catalog, composition, glossary, jobs, knowledge, plan,
registry, research, settings, story, translation}` — **12**.
`find-tools.ts:27-…` / `tool_discovery.py:65-…` `GROUP_DIRECTORY` = the same 12 **plus `world` and `meta`** — 14.

The registry rejects a legitimate category with a categorical falsehood (`mode_bindings.go:340-342`):
`"'world' is not a tool category — it would seed nothing"`. It *is* one, and it seeds the whole `world_*` /
`world_map_*` namespace — the exact namespace the `draw-a-map` rail depends on. The `meta` group (the
`tool_list`/`tool_load`/`ui_*` self-tools) is likewise unbindable. The comment at `mode_bindings.go:36-45`
even names the SSOT it is supposed to mirror; the mirror is stale.

### 7.5 🟠 A pin can validate at write and still no-op at turn time

`putModeBinding` rejects a pin naming an invisible workflow (`mode_bindings.go:353-369`), and the comment at
`:222-226` claims `workflowVisibleInBook` *"deliberately mirrors internalWorkflows' own book-tier arm — if the
two ever disagree, a book-tier pin that validates at the write silently no-ops at turn time, which is the
failure this check exists to prevent."* But `workflowVisibleInBook` (`:227-235`) has **no surface predicate**,
while `internalWorkflows` (`workflows.go:842`) filters by surface. Given §7.3, a pin of a `surfaces:["chat"]`
workflow validates cleanly and then vanishes on every book turn. Runtime does log it
(`stream_service.py:5446-5450`), so it is a *noisy* no-op rather than a silent one — but the write-time check
that claims to prevent it does not.

### 7.6 🟠 The FE shows recipes the user cannot run

`ExtensionsPage.tsx:134` mounts `<WorkflowRackPanel bookId={...} />` with **no `onPick`**. `WorkflowRack.tsx:59`
renders each recipe as a `<button onClick={() => onPick?.(w.slug)}>` — the optional-call swallows it. Every
card in "the rack the user picks from" (`workflows_rest.go:13-21`) is a **click that does nothing**.
`WorkflowsView.tsx` (the studio panel) has view / enable-disable / delete but **no run action either**
(`:68-93`). Grep confirms `WorkflowRackPanel` has exactly one mount site.

So: the product exposes a browsable catalogue of 12 recipes and provides **no user-facing way to run one**.
The only invocation paths are the model's own `workflow_load` and the two pin mechanisms.

### 7.7 🟡 Workflows unreachable from any intent

`glossary-bootstrap` and `populate-from-notes` (§5, item 4). Both are seeded, published, listed, and pinnable
by nothing — 2/12 rails depend entirely on the discovery behaviour measured at 0/3–1/3.

### 7.8 🟡 Dead columns and stale in-repo facts

- `workflows.used_count` / `workflows.last_run_at` (`migrate.go:409-410`) — never written. There is **no usage
  telemetry for workflows at all**, so "which rails work" is unanswerable from the data.
- `stream_service.py:585`: *"The vision-to-book rail is 11 steps"* — the seed has **9** (`migrate.go:599-609`).
  `RAIL_REDRIVE_CAP = 8` was sized against the wrong number.
- `S00c-workflow-confirm-gates.json` canon fact: *"workflow_list returned the seeded System rails (10)"* —
  there are **12**.
- `migrate.go:708-720` (the `chapter-compose` header comment) describes a 3-step rail
  `composition_get_outline_node` → `book_read` → `book_chapter_save_draft` and states *"book_read is REQUIRED
  before the write: save_draft hard-needs the chapter's own draft_version as base_version"*. The **actual**
  steps at `:726-727` are `book_list` → `book_chapter_save_draft`, and the `notes_md` at `:729` says the
  opposite (*"you do NOT read or pass a version first"*). The comment above the row contradicts the row.
- `migrate.go:564-568` says the `kg-build` rail uses `kg_project_entities_to_nodes`; the row uses `kg_add_nodes`.

### 7.9 🟡 A definition duplicated in code and DB — **no.** But a *namespace* is split.

Checked explicitly: `grep` for every seeded slug across `services/`, `frontend/src`, `scripts/`, `contracts/`
finds only the DB seed plus prose references. Workflows are **not** duplicated in code. Good.

However the **tool namespace a step draws from is split across two registries with no join**:
`glossary_confirm_action` is a chat-service *frontend* tool (`frontend_tools.py:50, 255, 641`), not a federated
MCP tool — so it is absent from `contracts/tool-liveness.json` and `toolUnchecked()` returns true for it. Any
agent proposing a workflow that uses it (the correct thing to do — two seeded rails do) receives a spurious
`"unproven_tool: 'glossary_confirm_action' has not been shown to execute"` warning. The liveness gate cannot
see half the tool surface.

---

## 8. PATCHWORK TELLS (quoted)

> `// It deliberately does NOT check tool-catalog membership — the step-runner (chat-service, WS-2b) owns the`
> `// catalog + policy and fails an unknown/forbidden tool gracefully at run time`
> — `workflows.go:135-138`. **The named owner does not implement it.** Responsibility handed to a component
> that does not exist, in a comment.

> `-- surfaces EMPTY = visible on every surface. A book-scoped chat turn resolves the runtime surface key`
> `-- "book" (not "chat"), so a ['chat'] filter would hide this exact workflow on the turn that needs it.`
> `-- Empty means the registry surface filter is skipped.`
> — `migrate.go:500-502`. The enum mismatch diagnosed exactly, then routed around for one row.

> `# The closed set of per-step gates (mirrors the registry's validWorkflowGates / C3).`
> `VALID_GATES = ("none", "confirm", "approval")`
> — `workflow_runner.py:34-35`. A hand-copied enum with no machine check against
> `workflows.go:28`. (The FE keeps a *third* view: `types.ts:27` types `gate?: string` — free — and
> `WorkflowsView.tsx:102` renders `s.gate !== 'auto'`, comparing against a value that exists in **none** of
> the three enums.)

> `# Structural async-honesty guard — the LAST-RESORT fallback. Precedence … 3. this name heuristic`
> `_ASYNC_JOB_VERBS = ("translat", "generate_wiki", "wiki_generate", "extract_entities", …)`
> — `workflow_runner.py:37-60`. A 12-entry substring list guessing whether a tool starts a job, with a
> comment recording that `"media"` had to be removed because it matched `media_list`. This is the shape of the
> problem: **no registry knows what a tool is, so every layer guesses from its name.**

> `# This closes that gap the SAME way the mode binding does — by PINNING.`
> — `intent_workflows.py:12`. The fix for "the model won't discover a workflow" is 43 hardcoded English regexes.

> `-- Re-seeding semantics for System WORKFLOWS: DO UPDATE, not DO NOTHING. … DO NOTHING would mean an`
> `-- already-seeded row never picks up a fixed rail … a stale July-9 glossary-bootstrap row silently`
> `-- shadowed the rewritten one.`
> — `migrate.go:487-493`. Correct fix, and a record that the seed path has already shipped stale data once.

> `// Light projection only (slug/title/description/tier) — the rack lists; the full step defs come from`
> `// the step-runner's own read. Deliberately NOT the 44KB-bloat mistake.`
> — `workflows_rest.go:21-22`. Names the runner again; the rack it feeds has no click handler (§7.6).

> `// NOTE this field MUST exist on the struct: 'steps' round-trips through json.Unmarshal into`
> `// []workflowStepIn, so an authored key that is not declared here is SILENTLY DROPPED on the way out`
> `// and the consumer never sees it.`
> — `workflows.go:61-64`. Written for `done_when`, tested for `done_when`, and **`repeat` is being dropped by
> the exact mechanism described, two fields above the warning** (§7.1).

---

## 9. WHAT A UNIFIED ARCHITECTURE NEEDS

Goal: **"every MCP tool appears in ≥1 workflow" is mechanically checkable.** That requires an *enumerable tool
universe*, a *typed binding*, and a *gate*. Assessed against what exists:

### 9.1 The blocking gap: there is no tool registry

The check is a set difference — `catalog_tools − ⋃ workflow_step_tools` — and **the left operand does not
exist as data anywhere a gate can read it.** The tool catalog is assembled at request time by ai-gateway
federating live MCP servers. `contracts/tool-liveness.json` (223 tools) is the closest static artefact, but it
is *generated from an eval sweep*, not from the catalog, and it is blind to consumer-local frontend tools
(§7.9). Everything else follows from this.

### 9.2 What is needed

| # | need | exists today | gap |
|---|---|---|---|
| 1 | **A generated tool manifest** — name, service, group, tier, scope, async, paid — emitted at build time from every MCP server's `tools/list` + chat-service's frontend/meta tools, committed as `contracts/tool-catalog.json` | ~40% — `contracts/tool-liveness.json` has 223 names + `executes`/`proven`, and per-service `tools/list` wire tests exist; `_meta` (tier/scope/async/paid) is already declared per tool and gated by `scripts/tier-tag-gate.py` | it is eval-derived, not catalog-derived; missing consumer-local tools; no group/service column |
| 2 | **One home for the group taxonomy** — a `tool_groups` table or a single generated contract, with the other two copies deriving from it | ~33% — the taxonomy is fully written, three times, in three languages, and **already drifted** (§7.4) | pick a SoT, delete two copies, add a drift test |
| 3 | **`workflows.steps[].tool` validated as a FK into #1** at write **and at seed** | ~10% — only `toolBlocked` (proven-broken) at the author path; the seed path has no tool lint at all | add the membership check to `validateWorkflow`, and a `migrate_lint_test` mirroring it over the seed JSON (the file already lints `done_when` this exact way — `migrate_lint_test.go:160-185` is the template) |
| 4 | **A step's `gate` cross-checked against the tool's `_meta.tier`** — `gate:"confirm"` on a Tier-R tool is a lie | 0% | needs #1's tier column |
| 5 | **A skill↔tool↔workflow edge model** (the owner's actual ask) | 0% — no group table, no skill↔tool edge, no workflow↔skill edge; `inject_skills` and `inject_workflows` are unrelated TEXT[]s | new tables + resolver |
| 6 | **The coverage gate itself** — `scripts/workflow-tool-coverage-gate.py`: every tool in #1 either appears in ≥1 published System workflow or carries an explicit `NOT_IN_WORKFLOW` waiver row with a reason | 0% — no such gate; the repo has 50+ sibling gates and a house pattern (`scripts/gatelib.py`) to copy | trivial once #1 and #3 exist |
| 7 | **Non-vacuity proof for #6** — today's number would be **30/223 ≈ 13%**, so the gate must ship with a ratchet (a baseline that may only shrink), not a pass/fail | 0% | |
| 8 | **A contract for the workflow REST surface** + a route-conformance test | 0% — `contracts/api/agent-registry.yaml` documents none of the 13 workflow/skill routes; the glossary-service `TestOpenAPIRouteConformance` pattern named in `CLAUDE.md` was never applied here | copy the pattern |

### 9.3 Prerequisite fixes (cheap, and they unblock the above)

1. **Make `repeat` one type with one meaning** and add the `TestRepeat_SurvivesTheStepsRoundTrip` twin
   (§7.1) — otherwise any new step field will drop the same way.
2. **Stop discarding `json.Unmarshal` errors** at `workflows.go:850` and `:347-348, :371-372, :139-140` —
   log them. This single change would have surfaced §7.1 the day it shipped.
3. **Unify the surfaces vocabulary** (§7.3) — until then no authored workflow is usable on a book turn, so
   "author more workflows to raise coverage" is not even available as a remedy.
4. **Join `workflow_enablement` in `internalWorkflows`** (§7.2) — one `LEFT JOIN`, mirroring
   `skills_internal.go:48`.
5. **Lint the intent-slug set against the seeded-slug set** (§5, item 1), and drive `_compute_rail_drive_context`
   from the same pin computation as the fresh path (§5, item 5).

### 9.4 Honest summary of readiness

The *plumbing* is largely present and of good quality: one table, correct tenancy, HITL propose→approve,
revisions, per-user enablement, a mode-binding resolver with real closed-set validation, a rail driver that
grounds on observed artefacts rather than the model's memory, and a liveness gate. What is missing is the
**noun the whole architecture is supposed to be about**: the tool. Nothing in the system can list the tools it
has. Every layer therefore falls back to string matching and name heuristics — a 12-verb substring list to
guess async, 43 regexes to guess intent, a hand-copied category list in three languages, and a step field that
is a free string the author is trusted to type correctly. The coverage question the owner wants answered is
one join away from being trivial, and that join has no left-hand table.
