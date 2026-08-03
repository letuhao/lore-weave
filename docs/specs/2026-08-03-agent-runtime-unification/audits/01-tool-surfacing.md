# Audit 01 — Tool Surfacing / Discovery layer (chat-service)

Scope: how an MCP tool reaches (or fails to reach) the model's `tools[]` array on a
LoreWeave chat turn. Read-only. All paths are `services/chat-service/app/services/*`
unless noted.

Method note: `stream_service.py` was NOT read in full (owned by the main session) —
only targeted `grep -n` windows around the symbols this layer exposes. Every claim below
carries a file:line.

---

## 0 · TL;DR

There is no single "tool surface" object. There are **six independent producers** and
**eleven independent suppressors** of the advertised set, spread across three modules
plus `stream_service`, plus a **second, divergent implementation of the same discovery
tools in TypeScript** (`services/ai-gateway/src/federation/find-tools.ts`). Each was
added to fix a specific live incident; each is individually defensible; none of them
knows about the others. The result is exactly the reported symptom: the tool is in the
catalog, the model can name it, and it still is not on the wire — for a reason no single
place can report.

Five load-bearing defects are proven below (§5). The worst is that the tool-list
`include_deprecated` contract the model is shown is the **opposite** of what
chat-service's own handler does, and the regression test written to prevent exactly
that compares the schema against the *wrong* handler (§5.1).

---

## 1 · INVENTORY — every mechanism by which a tool can reach the model's tool list

The advertised set for a pass is assembled by `_advertise_discovery_tools`
(`stream_service.py:1297-1395`) as `core ∪ extra_frontend ∪ active_tool_names`, where
`active_tool_names` starts as the seed and grows during the loop. Producers:

| # | Mechanism | Where |
|---|---|---|
| P1 | **ALWAYS_ON_CORE** — a 4-name tuple, resolved from catalog-def → generic-frontend-def → nothing | `tool_discovery.py:282-318`; consumed `stream_service.py:1344-1361` |
| P2 | **Surface hot-seed** — domains derived from `resolve_skills_to_inject(enabled_skills=[])` ∪ `{story}`, expanded to names, token-budgeted | `tool_discovery.py:362-415`, `487-504`; `tool_surface.py:276-299` |
| P3 | **Sticky domains** — domains called in the last 8 assistant messages, unioned into hot domains | `tool_discovery.py:806-843`; wired `stream_service.py:5772-5785` |
| P4 | **Mode-binding `seed_tool_categories`** — a workflow mode binding can add categories | `tool_surface.py:281-292` |
| P5 | **Curated pins** — `session.enabled_tools`, plus per-pinned-skill `hot_domains` unions (three separate branches) | `tool_surface.py:300-388` |
| P6 | **`pinned_legacy_tools`** — manual per-session escape hatch, bypasses everything | `tool_surface.py:459-463` |
| P7 | **Pinned workflow rail step tools** — budgeted in declared step order, with a next-step exemption | `tool_surface.py:402-443` |
| P8 | **Skill-prompt-named tools** — backtick-scraped from injected skill prompts, budget-exempt | `tool_surface.py:527-568` |
| P9 | **`activated_tools` persistence** — curated: whole set; auto: `∩ workflow_step_tools` **plus** the last-6 recency tail | `tool_surface.py:571-608` |
| P10 | **`tool_load` at runtime** — unions loaded names into `active_tool_names` and persists | `stream_service.py:2904-2960` |
| P11 | **`tool_list` loop-breaker auto-load** — a *re-list* of a category silently auto-loads that whole category's tools | `stream_service.py:2808-2830` |
| P12 | **`find_tools` matches** — unioned into the active set. **Never advertised to the model** (P1 no longer contains it), so reachable only by hallucinated name | `stream_service.py:3084-3200`; retired at `tool_discovery.py:283-289` |
| P13 | **`frontend_tool_defs(editor, book_scoped)`** — a hardcoded 3-tool surface branch | `frontend_tools.py:651-676` |
| P14 | **Gateway-down fallback** — `tool_defs = catalog` (the *entire* federated catalog, no budget, no discovery) | `stream_service.py:5845-5855` |
| P15 | **`compose_prose_defs()`** appended when a composer model is configured | `stream_service.py:5858-5860` |
| P16 | **Workflow / load_skill meta-tools** — conditionally added | `stream_service.py:1362-1373` |

Sixteen. Note P14: when ai-gateway is unreachable the surface inverts from
"≈20 budgeted tools" to "≈200 unbudgeted tools" with no discovery loop — the two
extremes of the design, selected by an availability accident.

---

## 2 · MECHANISM — the real end-to-end path

### 2.1 Catalog acquisition
`KnowledgeClient.get_tool_definitions(user_id)` (`client/knowledge_client.py:557-624`)
does MCP `list-tools` against `ai-gateway/mcp`, converts to OpenAI function shape,
preserves `_meta`, and caches **per user_id for 60 s** (`_TOOL_CATALOG_TTL_S`, line 40).
Failure returns `[]` and is deliberately not cached (line 597-601). Catalog-level
`_meta` is stashed on the client instance (line 620-622) and read later by
`provider_availability()`.

**Cache staleness surfaces:**
- Tool catalog: 60 s TTL, per-user key (`:557-624`).
- Tool embedding vectors: 60 s, keyed `(catalog-name-hash, model_source, model_ref)` (`tool_discovery.py:1189-1294`).
- Embedding-model resolution: 60 s per user (`tool_discovery.py:1238-1256`).
- `_skill_prompt_named_tokens`: **`@lru_cache(maxsize=64)`, no TTL, never invalidated** (`tool_surface.py:527`).
- Admin catalog: **cached forever, process lifetime** (`knowledge_client.py:643-645`).
- ai-gateway's own federated tool list is separately cached (known lesson: restart to re-federate).

### 2.2 Hot-set derivation
`surface_hot_domains(editor, book_scoped, studio, permission_mode)`
(`tool_discovery.py:362-415`) calls `resolve_skills_to_inject(enabled_skills=[], ...)` —
**without `lazy_bodies`**, so it takes the legacy auto-inject branch
(`skill_registry.py:505-530`) and returns `{glossary, book, knowledge, composition,
universal…}` → their declared `SkillDef.hot_domains`, plus `story` on any book-bound
surface (`tool_discovery.py:359, 413-414`).

`hot_tool_names(catalog, domains)` (`:487-504`) expands to names by **prefix match**
through `_domain_of` (`:788-793`), excluding legacy-tagged and `DISCOVER_ONLY_HIGH_IMPACT`.

`budget_names_by_tokens` (`tool_surface.py:125-162`) trims to
`scale_by_window(HOT_SEED_TOKEN_BUDGET=2000, context_length)`. Order:
`ALWAYS_HOT_WRITES` unconditionally first (`:147-151`), then read-tools-first
(`_is_read_tool`, substring match on 13 verbs, `:113-122`), then ascending schema size,
tie-break by name. **No logging when a tool is dropped.**

### 2.3 Rail budget
`budget_rail_tools` (`tool_surface.py:180-214`) is a *separate* budget
(`RAIL_STEP_TOKEN_BUDGET=6000`) with the *opposite* ordering rule (declared step order,
not read-first), preceded by a three-way candidate reordering
(never-done → repeat-done → one-shot-done, `:420-426`) and a next-step exemption
(`:427-438`). This one **does** log its drops (`:439-443`).

### 2.4 The lazy tail
`tool_list` → `tool_load`. Both are consumer-local, handled inside chat-service's own
loop, never routed to ai-gateway:
- `tool_list` dispatch `stream_service.py:2792-2896` → `tool_list_result` (`tool_discovery.py:972-994`) → `visible_tools` (`:884-926`).
- `tool_load` dispatch `stream_service.py:2904-2975` → `tool_load_result` (`tool_discovery.py:997-1077`), then re-budgeted through `budget_names_by_tokens` at the hot-seed ceiling (`stream_service.py:2921-2936`), then persisted via `merge_activated_tools`.

`find_tools` still has a full implementation — token-overlap scorer, embeddings-blended
async twin, per-session retry tracker, enumeration fallbacks (`tool_discovery.py:698-750,
1080-1387, 1527-1677`) ≈ 700 of the module's 1678 lines — for a tool that
**F17 removed from `ALWAYS_ON_CORE_NAMES`** (`:283-289`). The model cannot see it, so
this code runs only on a hallucinated call.

---

## 3 · THE BLOCK LIST — every filter / gate / cap / rename / silent drop

| # | Filter | Condition | What the model observes |
|---|---|---|---|
| B1 | Hot-seed **token budget** | `used + tokens > 2000` (scaled) | **Nothing.** No log, no note, no telemetry. `tool_surface.py:158-159` |
| B2 | Read-verb ordering starvation | write tools sort after all reads | Nothing. `tool_surface.py:152-155` |
| B3 | `DISCOVER_ONLY_HIGH_IMPACT` | `glossary_adopt_standards` never hot-seeded | Nothing (findable via load). `tool_discovery.py:426-428, 501-502` |
| B4 | `INTENT_GATED_SETUP_TOOLS` | 5 tools **removed from the turn catalog entirely** unless `glossary_shaping` injected or a pinned rail names them | Nothing at all — un-seedable, un-listable, un-loadable; `tool_load` answers `not_found` = "does not exist". `tool_discovery.py:442-484` |
| B5 | Legacy visibility | `_meta.visibility == "legacy"` → excluded from `search_catalog`, `enumerate_group`, every hot-seed; **labeled** (not dropped) in `visible_tools` | search: silence; list: labeled `deprecated` + `superseded_by`. `tool_discovery.py:565-576, 736, 869, 912-924` |
| B6 | **CD4 liveness** | `tool-liveness.json` `executes: false` | `tool_list`: silently absent (`:908`). `tool_load`: `unavailable` + reason (`:1031-1076`). **Two different behaviours for the same predicate.** |
| B7 | `tool_load` token truncation | loaded set > hot-seed budget | `truncated: true` + note (good). But `merge_activated_tools` persists the **untruncated** `loaded` list (`stream_service.py:2955-2959`) — the persisted set disagrees with what the model was told. |
| B8 | Ask/plan **tier gate** | `permission_mode ∈ {ask, plan}` and `tool_tier(td) != "R"` | Nothing — the tool simply is not there. `stream_service.py:1389-1393` |
| B9 | **oneshot de-advertise** | completed one-shot create; 4 modes via `settings.oneshot_deadvertise_mode` (default `"session"`) | Nothing. `stream_service.py:2067-2085, 1386` |
| B10 | **rail action-space gate** | `rail_gate_suppressions` (`sdks/python/loreweave_agent_control/rail.py:639-694`), default mode `done_suppress` | Nothing. `stream_service.py:2086-2095` |
| B11 | **repeated-failure de-advertise** | breaker fired for a tool this turn | Nothing (the earlier error text is in history). `stream_service.py:2096-2100, 1905-1911` |
| B12 | **F18 tool_list de-advertise** | >5 `tool_list` calls this turn | `tool_list` vanishes mid-turn. `stream_service.py:570-571, 1350-1356, 1921-1927` |
| B13 | `tool_list`/`find_tools` `exclude=ALWAYS_ON_CORE_NAMES` | any core tool | Absent from the listing; if it is the *only* tool in that category, the payload asserts `"no tools currently available in this category"`. `stream_service.py:2885, 3160`; `tool_discovery.py:992-993` |
| B14 | Curated pin not in catalog | `catalog_index.get(name)` → `None` → `_add(None)` returns | **Silently dropped**, no validation at the write path either. `stream_service.py:1328-1330`; `routers/sessions.py:349` |
| B15 | Skill visibility on pinned-skill hot union | `_skill_visible(skill, active_surface)` false | Nothing. `tool_surface.py:376-382` |
| B16 | Auto-mode `activated_tools` intersection | not in a visible workflow's steps and outside the last-6 tail | Nothing — the tool the model loaded last turn evaporates. `tool_surface.py:601-607` |
| B17 | `ambient_book` schema projection | `_meta.ambient_book` on a book-bound turn → `book_id` property **deleted** from the advertised schema | Nothing (deliberate). `stream_service.py:1272-1294` |
| B18 | `strip_tool_meta` | always | `_meta` never reaches the provider (correct). `tool_discovery.py:620-630` |

**Score: 13 of 18 are silent.** Only B5, B6(load), B7, and the rail budget drop
(`tool_surface.py:439-443`, a `logger.warning`, not visible to the model) say anything
at all. There is no counter, no SSE field, and no log line for B1 — the single most
frequently-firing filter in the system.

---

## 4 · COUPLING — what this layer reads from elsewhere

**Skill layer** (`skill_registry.py`) — read by `tool_discovery` and `tool_surface`
directly, via runtime imports inside function bodies:
- `SYSTEM_SKILLS` (dict) — `tool_surface.py:341, 376, 547`; `tool_discovery.py:395`
- `SkillDef.hot_domains` — `tool_surface.py:342, 381`; `tool_discovery.py:412`
- `SkillDef.prompt_loader()` — `tool_surface.py:553` (scraped with a regex)
- `resolve_skills_to_inject(...)` — `tool_discovery.py:397-407` (**called with the sync signature and default `lazy_bodies=False`**)
- `_skill_visible`, `_surface_key` (both private) — `tool_surface.py:376-377`
- `SETUP_INTENT_SKILL = "glossary_shaping"` string literal — `tool_discovery.py:451`

**Rail/state layer:**
- `RailProgress.steps[].{tool,done,repeat}`, `.next_step.tool` — `stream_service.py:5788-5814`
- `rail_gate_suppressions(progress, turn_succeeded, mode)` — `stream_service.py:2091`
- `workflow.steps[].tool` (raw dicts) — `stream_service.py:5759-5764`
- `mode_binding.seed_tool_categories`, `.inject_skills`, `.inject_workflows`

**Gateway federation:**
- Tool-name **prefix** is the sole domain key (`_provider_prefix`, `:756-759`), remapped by `_DOMAIN_ALIASES` (`:776-785`)
- `_meta.{tier, scope, synonyms, async, paid, visibility, superseded_by, undo_hint, ambient_book}`
- catalog-level `_meta.unavailable_providers` — key explicitly frozen (`:1390-1420`)

**Settings** (`config.py`): `lazy_skill_bodies` (default **True**, :272),
`oneshot_deadvertise_mode` (default `"session"`, :304), `rail_action_gate_mode`
(default `"done_suppress"`, :342), `tool_result_token_cap` (:167). Plus raw env:
`LW_HOT_SEED_TOKEN_BUDGET` (`tool_surface.py:50`), `LW_RAIL_STEP_TOKEN_BUDGET` (:59),
`LW_LAZY_ALL_SKILLS` (`skill_registry.py:641`). The last three are read via
`os.environ` at import time, bypassing the settings object entirely — a
`settings-and-config.md` SET-1/SET-7 violation on a behaviour that is per-model, not
platform-wide.

**Persisted session state:** `enabled_tools`, `enabled_skills`, `activated_tools`,
`pinned_legacy_tools` (`tool_surface.py:223-226`), and `chat_messages.tool_calls`
(read raw SQL, `stream_service.py:5776-5782`).

---

## 5 · DEFECTS & INCOHERENCES

### 5.1 `tool_list`'s advertised `include_deprecated` default is the OPPOSITE of what chat-service does — and the regression test guards the wrong handler

The schema shown to the model says false, twice:
```
tool_discovery.py:214-220
  "description": ("Include deprecated tools ... Default false — omit to see only the
                   CURRENT tools; ...")
  "default": False,
```
The handler that actually runs for the chat agent says true:
```
stream_service.py:2794-2796
  include_deprecated = args_obj.get("include_deprecated")
  if not isinstance(include_deprecated, bool):
      include_deprecated = True
```
`tests/test_tool_list_contract_drift.py` was written for exactly this bug class (its
docstring: *"chat-service advertises … but the handler that runs applies …"*). It
compares chat's schema against **ai-gateway's** `handleToolList`
(`test_tool_list_contract_drift.py:57-73`, reading
`services/ai-gateway/src/mcp/handlers.ts:252`, which defaults `false`). But
`handleToolList` is **not** the handler that runs for the chat agent — chat-service
intercepts `tool_list` in its own loop and never routes it. The test is green and the
defect it names is live. The direction has merely flipped: K22 fixed the prose, then
someone set the local fallback to `True`, and nothing could see it.

Downstream effect: on a catalog with 19 deprecated book tools vs 16 active
(the number cited in the K22 comment at `tool_discovery.py:205-211`), the chat agent's
default listing is >50 % retired names, each labeled with a `superseded_by` it must
reason past.

### 5.2 `tool_list(category="research")` tells the model web search does not exist

`web_search` is in `ALWAYS_ON_CORE_NAMES` (`tool_discovery.py:317`) and is the only
tool whose prefix aliases to `research` (`_DOMAIN_ALIASES["web"] = "research"`, `:779`).
The live call site excludes the core:
```
stream_service.py:2881-2887
  payload = tool_list_result(discovery_catalog or [], category,
                             exclude=set(ALWAYS_ON_CORE_NAMES), ...)
```
`visible_tools` skips excluded names (`tool_discovery.py:900-901`), so the category is
empty, and `tool_list_result` then asserts:
```
tool_discovery.py:992-993
  payload["reason"] = "no tools currently available in this category"
```
The GROUP_DIRECTORY block injected into the same system prompt says
`research: External web research — search the open web ... (web_search). PAID.`
(`:94`). The model is shown a domain, told to `tool_list` it, and told the domain is
empty — for a tool that is already on its wire.

**The test that should catch this is vacuous:**
```
tests/test_tool_list_load.py:64-66
  def test_web_search_lists_under_research_not_knowledge(self):
      assert "web_search" in [t["name"] for t in td.tool_list_result(cat, "research")["tools"]]
```
It calls the pure function **without the `exclude=` argument the production call site
passes**. NV-2 ("the scope never reaches it"): the subject is not the code path that
runs. The `meta` category has the same shape — its directory text
(`tool_discovery.py:87`) advertises `tool_list, tool_load` as its contents, and both are
excluded by the same line.

### 5.3 The hot-seed's justification is void under the default configuration

`surface_hot_domains`'s contract (`tool_discovery.py:333-336`, `369-394`) is:
*"HOT = the domain(s) the surface's injected SKILL names directly (so the skill works
with no discovery hop)."* It derives them by calling
`resolve_skills_to_inject(enabled_skills=[], ...)` (`:397-407`) — **omitting
`lazy_bodies`**, which therefore defaults `False` (`skill_registry.py:468`) and takes the
legacy auto-inject branch (`skill_registry.py:505-530`).

But `settings.lazy_skill_bodies` defaults **True** (`config.py:272`), and the live call
passes it (`stream_service.py:5209`), so `resolve_skills_to_inject` returns `[]` for any
non-curated session (`skill_registry.py:498-504`).

Consequences, all on the default config:
1. The surface hot-seeds `glossary`, `book`, `knowledge`, `story` tools while **no skill prompt is injected to teach them**. The stated rationale for which domains are hot no longer holds.
2. `skill_named_tools(injected_skill_codes=[], ...)` (`tool_surface.py:457-458`) contributes **nothing**. D-SKILL-NAMED-TOOLS-RIDE — the invariant added on 2026-07-26 after the entity_edit/propose_entities incident — is **inert by default**.
3. `filter_intent_gated_setup_tools(catalog, [], ...)` (`stream_service.py:5749-5751`) always filters, since `glossary_shaping` can only reach the empty list via the keyword gate (§5.4).
4. `load_skill` mid-turn returns a body that names tools — and *"executes nothing, activates no tools"* (`stream_service.py:3056-3060`). The seed was computed before the loop (`stream_service.py:5816`). So the model loads `plan_forge`, reads *"call `plan_propose_spec` then `plan_compile`"*, and neither is on the wire outside `permission_mode="plan"`. **This is verbatim the failure `tool_surface.py:536-546` documents as fixed** (6948 characters of plan prose, `finish_reason=stop`, 0 tool calls) — the fix covers the eager path only.

### 5.4 An English-only substring list gates whether five tools exist

`INTENT_GATED_SETUP_TOOLS` (5 tools) are removed from the **turn catalog object itself**
— the one all three reach-paths read — unless `glossary_shaping` is injected
(`tool_discovery.py:442-484`). Under lazy bodies the only deterministic way it gets
injected is:
```
skill_registry.py:434-453
_WORLD_SETUP_MARKERS = ("ontolog", "entity kind", "glossary", "codex", "taxonomy",
                        "worldbuild", "adopt standard", "seed the core entit",
                        "set up the world", ...)
def _is_world_setup_intent(intent_text):
    t = intent_text.lower()
    return any(m in t for m in _WORLD_SETUP_MARKERS)
```
Substring match, English only. The project's own dogfood corpus and PO write in
Vietnamese, so a request meaning *"set up the world for this story"* — the canonical world-setup
intent, and a verbatim match for the English marker `"set up the world"` — matches nothing → the tools do not exist
for that turn. The remaining path is the embedding router, whose top-K the same file's
comment (`skill_registry.py:673-682`) records as having **already ranked
`glossary_shaping` out on a live setup turn** — which is why the deterministic gate was
added. So the deterministic backstop for a top-K miss is itself language-coupled, and
the failure is total silence: `tool_load("glossary_adopt_standards")` answers
`not_found`, which `tool_discovery.py:1050` explicitly notes *"ASSERTS that no such tool
exists"*.

### 5.5 Two engines, one contract, drifted

`tool_list` / `tool_load` / `find_tools` / `GROUP_DIRECTORY` / `_DOMAIN_ALIASES` /
`visibleTools` / `FindToolsAttemptTracker` exist **twice** — Python
(`tool_discovery.py`) and TypeScript (`services/ai-gateway/src/federation/find-tools.ts`),
with nine separate comments instructing "keep in lockstep". Verified divergences:

| Concern | Python | TypeScript |
|---|---|---|
| `plan` group description | 9-line sequencing directive, "you MUST finish by calling plan_compile" (`tool_discovery.py:99-108`) | one line listing tool names (`find-tools.ts:60`) |
| CD4 liveness gate in `visible_tools` | present, hides `executes:false` (`tool_discovery.py:908`) | **absent** (`find-tools.ts:200-212` has no liveness check) |
| `tool_list` exclude set | `ALWAYS_ON_CORE_NAMES` (`stream_service.py:2885`) | `new Set()` (`handlers.ts:255`) |
| `include_deprecated` executed default | `True` (`stream_service.py:2795`) | `false` (`handlers.ts:252`) |

No test compares the two `GROUP_DIRECTORY` objects. The one drift test that exists
(`test_tool_list_contract_drift.py`) checks four scalar fields and, as shown in §5.1,
points at the wrong handler.

### 5.6 One name, two meanings — `_meta` availability keys

`tool_load_result` deliberately splits `unavailable` (CD4 broken) from
`provider_unavailable` (outage), with a comment stating *"One name, one concept"*
(`tool_discovery.py:1057-1058`). But `unavailable_providers` appears in **both**
branches (`:1062` and `:961`), and `_stamp_incomplete` sets `incomplete: true` while
`tool_load_result` does not — so a partial `tool_list` and a partial `tool_load` on the
same outage give the model two differently-shaped signals.

Similarly `is_frontend_tool` vs `is_browser_executed` (`frontend_tools.py:679-716`) —
two predicates over overlapping sets, documented as having already caused one silent
telemetry corruption. The docstring is honest; the split remains a trap for a third
consumer.

### 5.7 Substring verb classification misroutes budget priority

`_is_read_tool` (`tool_surface.py:113-122`) is `any(verb in name.lower())`. `"search"`
is a substring of `"research"`, so **`glossary_deep_research`** — a PAID,
human-confirm-gated tool the universal skill explicitly warns against
(`tests/test_skill_registry.py:461-465`) — is classified a read and gets *priority* in
the hot-seed budget over genuine write tools. `_get_or_create`-style names hit the same
trap via `"get"`. There is no test asserting the classification of any real catalog name.

### 5.8 `enabled_tools` has no closed-set validation; `pinned_legacy_tools` does

`routers/sessions.py:321-324` validates `pinned_legacy_tools` against the live catalog
via `unknown_pinned_legacy_names` and rejects the write. `enabled_tools` is written
straight through (`sessions.py:349, 368`). A pin of a renamed tool then dies silently at
`stream_service.py:1328-1330` (`_add(None)` → `return`). The user's Context Rack shows
the pin; the model never sees the tool; nothing anywhere reports the mismatch.

### 5.9 Telemetry does not cover the caps

`AgentSurfaceTracker` (`agent_surface.py:102-133`) emits `pinned_count`,
`hot_seed_count`, `activated_count`, `advertised`, `servers`, `schema_tokens`. It emits
**no** dropped-by-budget count, no suppression reason, and no per-filter attribution.
The panel can show "23 tools advertised" but cannot answer "why is
`glossary_propose_kinds` not among them" — which is precisely the reported user problem.

Additionally `_SERVER_KEY_BY_PREFIX` (`agent_surface.py:45-64`) omits `world`, `catalog`,
`registry`, `settings`, `web`, `story`, `lore` — all bucket to `"other"`, the identical
defect the same block's comment (`:55-62`) says it fixed for `ui`.

### 5.10 `tool_load` truncation and persistence disagree

`stream_service.py:2926-2936` truncates `payload["tools"]` and tells the model
`"Loaded N of M tools (token budget)"`, but line 2955-2959 persists the **full**
`loaded` list into `activated_tools`. Next turn's auto-mode recency tail
(`tool_surface.py:606`) can then advertise a tool the model was told was not loaded.

---

## 6 · PATCHWORK TELLS

**Dead module.** `tool_plan.py` (130 lines, planner-executor POC for weak models) is
imported by **nothing in `app/`** — verified `grep -rn "tool_plan\|restrict_tools_to_plan"
app/ --include=*.py` returns only its own definitions. Its docstring claims
*"the async plan call + the stream wiring live in stream_service"* (`tool_plan.py:20-21`).
They do not. `tests/test_tool_plan.py` keeps it green, so it reads as live code. Its
`_EXECUTOR_KEEP_CORE = {"confirm_action", "propose_edit", "tool_load"}`
(`tool_plan.py:31-34`) omits `tool_list`, and still lists `propose_edit`, which
`frontend_tools.py:56-62` records as moved to ai-gateway.

**Dead branch.** `_advertise_discovery_tools` still special-cases `find_tools`:
```
stream_service.py:1344-1347
  for name in ALWAYS_ON_CORE_NAMES:
      if name == FIND_TOOLS_NAME:
          _add(FIND_TOOLS_TOOL); continue
```
`FIND_TOOLS_NAME` is not in `ALWAYS_ON_CORE_NAMES` (`tool_discovery.py:282-318`). The
branch cannot fire. Behind it sits ~700 lines of maintained, cross-language-mirrored,
heavily-tested machinery (`search_catalog_semantic`, `_get_tool_vectors`,
`_resolve_embedding_model`, `FindToolsAttemptTracker`, `_enumeration_result`,
`_blank_intent_result`, `_scored_result_payload`) for a tool the model cannot see.

**Hardcoded tool-name lists — seven of them, each from one incident:**
- `ALWAYS_HOT_WRITES` (6 names, `tool_surface.py:79-106`) — 27 lines of comment for 6 entries, including *"NOTE (N5a, dogfood 2026-07-18 F3): `glossary_adopt_standards` is DELIBERATELY NOT hot… Do not re-add it here."*
- `DISCOVER_ONLY_HIGH_IMPACT` (1 name, `tool_discovery.py:426-428`) — a set of one, overlapping `INTENT_GATED_SETUP_TOOLS`, which contains the same name (`:443`). Two mechanisms, one tool.
- `INTENT_GATED_SETUP_TOOLS` (5, `:442-448`)
- `ONESHOT_CREATE_TOOLS` (1, `stream_service.py:555`)
- `_STICKY_DOMAIN_IGNORE` (11, `tool_discovery.py:798-803`) — still lists `ui_navigate`, `ui_open_book`, `ui_show_panel`, `ui_watch_job`, retired 2026-07-27
- `_EXECUTOR_KEEP_CORE` (3, `tool_plan.py:31-34`) — dead
- `_BROWSER_EXECUTED_EXTRA` (1, `frontend_tools.py:692`)

**Fix-on-fix stacks.** The three most-layered:
1. `merge_activated_tools` (`tool_surface.py:611-652`) — count cap 64 → token cap 6000 → LRU-refresh (D-ACTIVATED-LRU-REFRESH). Three revisions, and the fallback count-cap path (`:650-651`) still exists for "legacy callers / tests".
2. The rail seed (`tool_surface.py:402-443`) — budget in step order → drop done steps → **v2**: reorder done steps instead of dropping (D-RAIL-REPEAT-BUDGET) → exempt next-step (D-RAIL-NEXT-STEP-EXEMPT). Three deferrals stacked on one 40-line block.
3. The curated hot-domain union (`tool_surface.py:300-388`) — 88 lines, of which ~60 are comments about two prior `review-impl` HIGH findings and the "one shared ceiling, never a second call" rule, now expressed as **three** separate `budget_names_by_tokens` calls with a hand-maintained `covered_domains` set to keep them from double-counting.

**Two guards blind in complementary ways** (the file says so itself,
`tool_surface.py:536-546`): the authoring lint `_TOOL_TOKEN_RE = \b[a-z]+(?:_[a-z0-9]+)+\b`
(`tests/test_skill_registry.py:484`) scans **all** prose but exempts `co_write` and
`admin` via `_EXEMPT_SKILL_CODES` (`:435`); the runtime scraper
`` re.findall(r"`([a-z][a-z0-9_]{3,})(?:`|\()", prompt) `` (`tool_surface.py:556`)
covers all skills but only **backtick-quoted** tokens. A tool named without backticks in
an exempt skill is invisible to both. The comment records the exact intersection that
shipped: `plan_propose_spec` and `plan_compile`.

**Env-flag branches on tool surfacing:** `LW_HOT_SEED_TOKEN_BUDGET`,
`LW_RAIL_STEP_TOKEN_BUDGET`, `LW_LAZY_ALL_SKILLS`, `oneshot_deadvertise_mode` (4 modes),
`rail_action_gate_mode` (3 modes), `lazy_skill_bodies`. `LW_LAZY_ALL_SKILLS`
(`skill_registry.py:641-644`) returns `[]` skills — which, via `injected_skill_codes`,
also silently changes B4 and P8, i.e. an A/B knob labelled "skills" mutates the **tool
catalog**.

---

## 7 · WHAT A UNIFIED ARCHITECTURE NEEDS FROM THIS LAYER

To make *"every MCP tool belongs to exactly one skill group and appears in ≥1 workflow"*
mechanically enforceable, this layer must expose and consume the following. Each item is
justified by a specific defect above.

### 7.1 One function, one return type: an explained surface
Replace the six producers / eighteen filters with a single
`resolve_tool_surface(...) -> ToolSurface` where

```python
@dataclass(frozen=True)
class ToolSurfaceEntry:
    name: str
    admitted: bool
    admitted_by: str      # closed enum: core | hot_seed | rail_step | skill_named |
                          #   curated_pin | pinned_legacy | activated_tail | tool_load |
                          #   mode_binding | sticky_domain | frontend_surface
    excluded_by: str|None # closed enum: token_budget | tier_gate | intent_gate |
                          #   liveness | legacy | oneshot | rail_gate | failure_breaker |
                          #   f18_list_cap | not_in_catalog | ask_mode
    group: str            # exactly one, from the closed CATEGORY_ENUM
    tokens: int
```

Non-negotiable properties, each closing a finding:
- **`excluded_by` is never `None` for a name the model could plausibly want** — kills the 13 silent filters (§3).
- **`admitted_by` and `excluded_by` are closed enums**, not free strings (Frontend-Tool-Contract IN-1 discipline, already the rule for tool args).
- **The struct is emitted on the SSE `agent_surface` channel** and logged once per pass. This is the missing telemetry (§5.9) and the only way a user or an agent can answer "why can't you see X".

### 7.2 Group membership must be data, not a name prefix
Today `_domain_of` (`tool_discovery.py:788-793`) infers group from the tool-name prefix
plus a 7-entry alias table that must be mirrored in TypeScript. Every orphan
(`lore_*`, `web_*`, `kg_*`, `memory_*`, `propose_*`, `tool_*`, `ui_*`) needed a hand
alias, and one (`ui_*`) is stale. **Move `group` into `_meta` at the domain service**,
make it a required field, and add a federation-time gate: a tool whose `_meta.group` is
absent or outside `CATEGORY_ENUM` fails the catalog build. Then "exactly one skill group"
becomes a schema property, not a prefix coincidence.

### 7.3 The skill↔tool edge must be declared, not scraped
`skill_named_tools` regex-scrapes prompt prose (`tool_surface.py:556`); the authoring
lint uses a *different* regex on a *different* scope (§6). Replace both with an explicit
`SkillDef.tools: frozenset[str]` — validated at import against the catalog — and derive
`hot_domains` from it. Then:
- `skill.tools ⊆ catalog` is a startup assertion (kills §5.7-adjacent typos).
- `⋃ skill.tools ⊇ catalog` is the *"every tool belongs to ≥1 skill group"* gate.
- The runtime budget exemption reads the declared set, so it cannot disagree with the lint.
- A skill's prose naming a tool outside `skill.tools` is a lint failure — one rule, one scope.

### 7.4 Guidance and capability must be atomic
`filter_intent_gated_setup_tools`' own docstring states the principle — *"guidance and
capability move as ONE signal"* (`tool_discovery.py:475-476`) — and then implements it
with a keyword list (§5.4) and a skill-code string literal. The contract this layer needs
is: **injecting a skill body (eager or via `load_skill`) MUST re-seed that skill's
`tools` into the active set in the same operation.** Concretely, `load_skill`'s handler
(`stream_service.py:3061-3074`) must call the same activation path `tool_load` uses. Until
it does, the default (lazy) configuration cannot satisfy D-SKILL-NAMED-TOOLS-RIDE (§5.3.4).

### 7.5 One workflow↔tool projection
Rail step tools currently enter through three separate seams with three orderings
(`workflow_step_tools`, `pinned_step_tools`, `rail_next_step_tools` —
`tool_surface.py:394, 402, 433`) and a fourth suppressor in a different package
(`rail_gate_suppressions`). A unified layer needs one `WorkflowSpec.tools` projection
that both the seed and the gate read, so *"appears in ≥1 workflow"* is a set operation
over declared data.

### 7.6 One discovery engine
The Python/TypeScript duplication (§5.5) has produced four verified drifts and cannot be
held by comments. Either chat-service stops handling `tool_list`/`tool_load` locally and
routes them to ai-gateway (one engine, chat becomes a consumer), or the shared pieces
(`GROUP_DIRECTORY`, `CATEGORY_ENUM`, alias table, visibility + liveness predicates) move
to a generated artifact both languages import — the pattern `contracts/tool-liveness.json`
already uses successfully (`tool_liveness.py:5-11`).

### 7.7 Budget must be one ceiling with one reporting seam
Three budgets exist (`HOT_SEED_TOKEN_BUDGET`, `RAIL_STEP_TOKEN_BUDGET`,
`ACTIVATED_TOOLS_TOKEN_BUDGET`) with two different priority orders and one exemption
list, and only one of the three reports its drops. A unified layer needs a single
`budget(entries, ceiling) -> (kept, dropped_with_reason)` — the shape
`budget_rail_tools` already has (`tool_surface.py:180-214`) — applied everywhere, with
`dropped` surfaced through §7.1.

### 7.8 Closed-set validation on every pin write
Apply `unknown_pinned_legacy_names`' discipline (`tool_discovery.py:586-593`,
`routers/sessions.py:321-324`) to `enabled_tools` and `enabled_skills` too (§5.8). A pin
that cannot resolve must 400 at the write, not vanish at advertise time.

---

## Appendix — non-vacuity concerns found in the guarding tests

| Test | Problem |
|---|---|
| `test_tool_list_load.py:64-66` `test_web_search_lists_under_research_not_knowledge` | Calls `tool_list_result` **without** the `exclude=` the production site passes. Asserts the opposite of live behaviour (§5.2). |
| `test_tool_list_contract_drift.py:55-73` | Compares chat's schema to ai-gateway's handler; chat's own handler is never read (§5.1). |
| `test_skill_registry.py:435` `_EXEMPT_SKILL_CODES` | Exempts `co_write` from the named-tools lint — the file that documents the resulting incident is `tool_surface.py:536-546`. Exemption still in place. |
| `test_tool_plan.py` | Keeps a module with zero production callers green (§6). |
| — | **No test** asserts a GROUP_DIRECTORY / `_DOMAIN_ALIASES` parity between Python and TypeScript, despite nine "keep in lockstep" comments. |
| — | **No test** asserts that the hot-seed budget's drop set is empty, reported, or bounded — the most frequently-firing filter has no coverage of its effect. |
