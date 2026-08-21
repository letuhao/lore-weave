# Audit 02 — The SKILL layer (chat-service agentic runtime)

Scope: LoreWeave's own product agent (chat-service → LLM → MCP tools). Read-only audit.
Date: 2026-08-03. Branch `feat/frontend-tools-mcp-migration`, HEAD `24dd7bdac`.

Catalog facts used throughout, derived live from the owning services via
`scripts/deprecated-tool-scan.py::build_catalog()`:
**202 advertised tools · 114 retired tools · 14 GROUP_DIRECTORY domains.**

---

## 1 · INVENTORY — what IS a skill here

There are **three unrelated things called a "skill"** in this repo, and they do not share a
schema, a surface vocabulary, a storage layer, or a tool-binding mechanism.

### 1a · Tier 1 — the real one: `SkillDef` in code

`services/chat-service/app/services/skill_registry.py:21-40` defines the only structure the
runtime actually uses:

```python
@dataclass(frozen=True)
class SkillDef:
    code: str
    label: str
    surfaces: frozenset[str]        # {"book","editor","studio","chat","admin"}
    prompt_loader: Callable[[], str]
    description: str = ""           # L1 line + the ONLY router-embedded text
    hot_domains: frozenset[str] = frozenset()
```

A skill is therefore: **a name, a surface list, one static prompt string, a one-line
description, and a set of tool-DOMAIN prefixes.** It has **no** state machine, **no** rails,
**no** per-tool declaration, **no** entry/exit conditions, and **no** link to a workflow.

`SYSTEM_SKILLS` (`skill_registry.py:104-287`) — **13 entries**:

| code | label | surfaces | hot_domains | prompt file:line | how selected |
|---|---|---|---|---|---|
| `glossary` | Glossary assistant | book, editor | `{glossary}` | `glossary_skill.py:13` | surface-default (book/editor/studio, non-lazy), pin, router, world-setup gate |
| `glossary_shaping` | Glossary ontology-shaping | book, editor | `{glossary}` | `glossary_skill.py:106` | ONLY via a `glossary` pin, the world-setup keyword gate, or the router. Hidden from catalog + `load_skill` |
| `universal` | Universal driver | chat | `{}` | `universal_skill.py:15` + `workflow_skill.py:23` (concatenated) | surface-default on chat (non-lazy) |
| `knowledge` | Knowledge graph | book, editor, chat | `{knowledge}` | `knowledge_skill.py:16` | surface-default everywhere non-admin (non-lazy) |
| `admin` | CMS admin | admin | `{}` | `glossary_skill.py:233` | admin surface only; never lazy-deferred |
| `plan_forge` | PlanForge | book, editor | `{plan}` | `plan_forge_skill.py:10` | plan-mode force-inject + pin + router |
| `co_write` | Co-writing | book, editor | `{}` | `co_write_skill.py:17` | write-mode force-inject + pin + router |
| `composition` | Composition | book, editor, studio | `{composition, book}` | `composition_skill.py:17` | studio surface-default (non-lazy), pin, router |
| `translation` | Translation | book, editor | `{translation}` | `translation_skill.py:14` | pin + router only |
| `book` | Book | book, editor, studio | `{book}` | `book_skill.py:28` | surface-default on book-bound (non-lazy), pin, router |
| `settings` | Settings | book, editor, studio, chat | `{settings}` | `settings_skill.py:21` | pin + router only |
| `jobs` | Jobs | book, editor, studio, chat | `{jobs}` | `jobs_skill.py:17` | pin + router only |

Two skills share one prompt module (`glossary` / `glossary_shaping` / `admin` all live in
`glossary_skill.py`), and one skill's body is **two prompts concatenated at load time**
(`universal` = `UNIVERSAL_SKILL_PROMPT + WORKFLOW_SKILL_PROMPT`, `skill_registry.py:58-61`).
`workflow_skill.py` is therefore a **skill fragment with no registry entry** — it is invisible
to `catalog_items()`, to `load_skill`, to the router (it has no description of its own), and
to every lint that iterates `SYSTEM_SKILLS`; its text is only ever linted *as part of* the
`universal` skill.

### 1b · Tier 2 — DB rows in agent-registry-service

`services/agent-registry-service/internal/migrate/migrate.go:89-118`:

```sql
CREATE TABLE skills (
  skill_id, plugin_id, tier CHECK IN ('system','user','book'),
  owner_user_id, book_id, slug, description, frontmatter JSONB,
  body_md TEXT, surfaces TEXT[], triggers JSONB, book_scoped BOOL,
  status, source, used_count, last_triggered_at, ...)
```

Note `triggers JSONB` and `frontmatter JSONB` — **neither is ever read**. Grep confirms no
consumer. There is no `tools` column and no `tools` frontmatter key: `skills_md.go:30-56`
parses exactly three keys — `name`, `description`, `surfaces`. **A user-authored skill
physically cannot declare a tool.**

**Skills defined in two places (the drift you asked about):**
`migrate.go:377-388` seeds **only 5** System-tier rows —
`glossary`, `universal`, `knowledge`, `admin`, `plan_forge` — with the comment
*"seed the 5 hardcoded chat-service skills."* Chat-service has **13**. The other **8**
(`glossary_shaping`, `co_write`, `composition`, `translation`, `book`, `settings`, `jobs`
— plus the un-registered `workflow` fragment) have **no DB row**, therefore:
* no `skill_enablement` row can be written for them (FK to `skills.skill_id`),
* so the per-user "disable this skill" toggle silently cannot exist for them,
* while `stream_service.py:5366-5384` *does* check `system_disabled(...)` for
  `composition`/`translation`/`book`/`settings`/`jobs` — five checks against rows that
  cannot exist. Dead branches, permanently false.

The bodies are deliberately NOT in the DB (`'(System skill — body served by chat-service
skill_registry)'`), so the DB row is pure catalog metadata that has already gone stale.

### 1c · Tier 3 — eval scenario JSON

`scripts/eval/skill_scenarios/{book,composition,jobs,settings,translation}.json` — 37
scenarios that encode "what this skill is supposed to make the agent do", each with a
`ground_truth` paragraph and `enabled_skills: [...]`. This is the closest thing the repo has
to a *specification* of a skill's behaviour. It is measured against by
`scripts/eval/run_skill_gate.py`, which is **not wired into CI** (only referenced by
`scripts/gate-wiring-gate.py:160` as an explicitly-exempt "live service" harness).

### 1d · Not a skill, but adjacent

* **Workflows / rails** — `workflows` table (`migrate.go:395+`), pinned by mode-binding
  (`mode_bindings.inject_workflows`) or by regex (`intent_workflows.py:32-105`). A rail is an
  *ordered list of tool steps* — the thing a "skill" is not. **Nothing links a skill to a
  workflow.** They are two parallel, independently-routed systems that both inject text and
  both seed tools.
* **Subagents** — `subagent_runtime.py`. A subagent *does* declare tools, via
  `tool_scope` fnmatch globs (`subagent_runtime.py:102-120`), enforced at advertise time AND
  execute time. **This is the one place in the codebase where a "capability" actually owns a
  tool whitelist** — and skills do not use it.

---

## 2 · SELECTION — how a skill is chosen for a turn

Single entry point: `resolve_skills_to_inject_async` (`skill_registry.py:589-707`), awaited
once per turn at `stream_service.py:5190`. Order of operations:

1. **Kill switch** — `skill_registry.py:642`: if env `LW_LAZY_ALL_SKILLS` is truthy, return
   `["admin"] if admin else []` and skip everything below. A live A/B POC knob left in
   shipped code.
2. **Hard gate** (`:488`) — non-`agui` stream format, `disable_tools`, or
   `not tool_calling_enabled` ⇒ `[]`.
3. **Surface key** (`:404-423`) — `admin` wins outright; otherwise `studio` is unioned
   additively, then `editor ⇒ {editor,book}`, `book_scoped ⇒ {book}`, else `{chat}`.
4. **Base selection** — three mutually exclusive branches:
   * `enabled_skills` non-empty (curated pins) ⇒ pins, surface-filtered.
   * `lazy_bodies` (config default **True**, `app/config.py:272`) ⇒ `["admin"] if admin
     else []` — **the blanket surface default is skipped entirely.**
   * else legacy auto-inject (`:505-531`): admin → `[admin]`; studio →
     `[glossary, composition, book]`; editor/book → `[glossary, book]`; chat →
     `[universal]`; plus `knowledge` for every non-admin surface.
5. **Deterministic gates, all hardcoded, all additive:**
   * `:542` `permission_mode == "plan"` ⇒ append `plan_forge`.
   * `:553` `permission_mode == "write"` ⇒ append `co_write`.
   * `:565` `"glossary" in enabled_skills` ⇒ append `glossary_shaping`.
   * `:571-585` mode-binding `inject_skills` from agent-registry, surface-filtered; an
     unknown code logs a warning and is dropped.
   * `:682-687` (async only) `_is_world_setup_intent(intent_text)` — a 17-substring keyword
     list (`:434-443`) — ⇒ append `glossary`, `glossary_shaping`.
6. **The embedding router** (`skill_router.py:137-203`) — additive only:
   * embed `f"{label}: {description}"` per skill, cached for process lifetime keyed on the
     sorted tuple of skill codes (`:91-92`, `:104-134`),
   * embed the turn text, cosine-rank,
   * **floor**: `ROUTER_CONFIDENCE_THRESHOLD = 0.35` (`:55`) — explicitly documented as
     *"NOT yet empirically tuned"*,
   * **top-K cap**: `ROUTER_MAX_ADDITIONS = 2` (`:71`),
   * tie-break: `sorted(..., reverse=True)` is stable ⇒ `SYSTEM_SKILLS` **insertion order**
     (`:202`). Dict literal order is the tie-break rule. Not documented anywhere a skill
     author would look.
   * Surface filter is re-applied (`:190`) — the router can never widen `surfaces`.

**What the comment at `skill_router.py:61-70` admits is the real state of the ranking:**

> "measured against the shipping bge-m3 embedder, EVERY novel-authoring skill description
> scores 0.35-0.66 cosine to ANY authoring intent (they are all 'assist with a novel'
> one-liners in one tight semantic cluster), so a bare `>= 0.35` gate passed ~all 10
> studio-visible skills on EVERY turn and re-injected ~15.5k tokens."

So the threshold is inert and **K=2 is the entire discriminator.** The router is effectively
"pick the 2 highest of a compressed, near-uniform distribution."

**When the router is wrong or drops a skill:** nothing detects it. There is no
"router picked X" event, no confidence in the surface tracker, no fallback re-rank. The
project's own response to a measured miss was to bolt on a keyword gate: `skill_registry.py:670-681`
documents that `glossary_shaping` *"was ranked out (a 'propose ontology + seed the core
entities' turn injected co_write/knowledge/plan_forge but NOT glossary_shaping), so gemma
proposed entities of kinds that did not exist yet and looped on `unknown kind`, book
untouched."* **One skill got a deterministic escape hatch; the other twelve did not.**

Failure modes on any embedding error are correct and well-tested: `route_additional_skills`
never raises (`:174-179`), and the caller re-catches (`:700-704`).

---

## 3 · SKILL → TOOL BINDING — declared? enforced?

**A skill declares tools in two ways, neither of them explicit, both derived from prose.**

### 3a · `hot_domains` — a DOMAIN declaration, advisory-with-a-lint

`hot_domains` is a set of *prefixes*, not tools. It reaches the wire through exactly two paths:

* **Auto (non-curated) mode** — `tool_discovery.surface_hot_domains()`
  (`tool_discovery.py:362-415`) re-invokes `resolve_skills_to_inject(enabled_skills=[])` and
  unions the resulting skills' `hot_domains`, plus `story`. Result is fed to
  `hot_tool_names` → `budget_names_by_tokens` under `HOT_SEED_TOKEN_BUDGET` (default **2000
  tokens**, `tool_surface.py:50`, "~4-6 tools hot").
* **Curated mode** — `tool_surface.py:376-388` unions the *visible* pinned skills'
  `hot_domains` under one shared budget.

**Enforcement status: ADVISORY, and the budget routinely defeats it.** A domain with 32
(glossary) or 53 (composition) tools cannot fit in a 2000-token seed; `budget_names_by_tokens`
(`tool_surface.py:125-162`) orders read-verbs first by ascending schema size and truncates. The
codebase records the consequence in its own comment (`tool_surface.py:444-456`):

> "proven on the wire: the request's instructions named `glossary_propose_entities` while the
> 21 advertised tools carried only `glossary_propose_entity_edit`, so the model mapped the
> create intent onto the similarly-named edit tool, every turn."

### 3b · `skill_named_tools` — the actual enforcement, and it parses English

`tool_surface.py:527-568`. A regex over the prompt text:

```python
frozenset(re.findall(r"`([a-z][a-z0-9_]{3,})(?:`|\()", prompt))
```

intersected with the live catalog, then unioned **budget-exempt** at
`tool_surface.py:457-458`. This is the mechanism the runtime actually relies on.

**It is a prose scraper.** Verified live: it extracts **27 tokens from `glossary`, of which 13
are not tools** (`action_done`, `base_version`, `confirm_token`, `create_kinds`, `character`,
`location`, `item`, `descriptor`, `attributes`…), **44 from `glossary_shaping`, 32 non-tools**,
**42 from `composition`, 25 non-tools**. The junk is harmless only because it is intersected
with the catalog — but it means the binding contract is *"whatever the author happened to put
in backticks."* Rename a tool and the binding silently evaporates; write a name without
backticks and it never rides.

Its own docstring records exactly that failure (`tool_surface.py:539-546`):

> "`co_write` names its two plan tools ONLY in signature form, so `plan_propose_spec` and
> `plan_compile` were never put on the wire… Measured live 2026-08-02 (Mị Đế): asked to plan <!-- doc-language-gate: ok -- "Mị Đế" is the proper name of the dogfood book, an identifier used across this repo; renaming it would break cross-doc traceability -->
> Arc 1, the co-writer emitted 6948 characters of plan prose with `finish_reason=stop` and
> ZERO tool calls."

### 3c · Proof that binding is INERT on the shipped default configuration

`lazy_skill_bodies` defaults **True** (`app/config.py:272`). Executed against the real code:

```
surface            resolve_skills_to_inject(lazy_bodies=True)
book/editor write  ['co_write']
studio     write   []
chat       write   []
```

`injected_skill_codes` is what feeds **both** `skill_named_tools` (`stream_service.py:5833`)
**and** `filter_intent_gated_setup_tools` (`:5750`).

⇒ **On a studio or plain-chat turn with default settings, `skill_named_tools` receives an
empty list and contributes nothing.** The D-SKILL-NAMED-TOOLS-RIDE guarantee — the mechanism
two regression tests exist to protect (`test_skill_registry.py:604-666`) — is a no-op on two
of the four surfaces. On a book turn it protects exactly `co_write`'s 7 tools.

Meanwhile `surface_hot_domains()` (`tool_discovery.py:397-407`) calls
`resolve_skills_to_inject` **without** `lazy_bodies`, so it still derives its hot domains from
skills whose bodies were **not** injected. On a lazy studio turn the wire carries
glossary + composition + book + knowledge + story tools **with zero instructions about any of
them** — the exact inversion of the principle stated at `tool_discovery.py:438-439`
(*"Guidance and capability then move as ONE signal"*).

### 3d · `load_skill` — the lazy path re-opens the hole it was built to close

`skill_registry.py:290-368` + handler `stream_service.py:3056-3074`. The handler's own comment:

> "Executes nothing, **activates no tools** — the body lands as this tool result…"

And `stream_service.py:1856`: `active_tool_names: set[str] = set(discovery_seed_names or ())`
— the advertised set is fixed at loop entry from the pre-turn seed. `load_skill` does not
re-enter `discovery_seed_for_surface`, does not re-run `skill_named_tools`, does not touch
`injected_skill_codes`, and does not flip `filter_intent_gated_setup_tools`.

So: a chat-surface model reads the L1 index, calls `load_skill('translation')`, and receives a
body whose first section reads *"Act — do NOT narrate… emit the tool call in the SAME turn"*
naming **13 `translation_*` tools, none of which are on the wire** (translation is in no
surface's hot domains and the model just proved it wanted them). Nor is there any surface
filter: `load_skill_result` explicitly declines to filter (`skill_registry.py:344-348`), so
`load_skill('composition')` on a plain chat surface hands over 17 tool names in a context where
`composition` will never be seeded.

### 3e · User-authored skills have no binding path at all

`skill_named_tools` reads `SYSTEM_SKILLS` only (`tool_surface.py:547-551`); an unknown code
returns `frozenset()`. User/book skill bodies are injected as a separate prompt part
(`stream_service.py:5358-5364`) and their slugs never enter `injected_skill_codes`. A user who
writes *"call `glossary_propose_entities`"* in their SKILL.md gets a prompt naming a tool with
**no mechanism whatsoever** to put it on the wire.

### 3f · Coverage arithmetic

| | count |
|---|---|
| advertised tools | **202** |
| named by ≥1 skill prompt | **98** |
| in a skill-claimed domain but named by no skill | **74** |
| in a domain no skill claims at all | **30** |

**~51 % of the live tool surface belongs to no skill.**

---

## 4 · LIFECYCLE & STATE

**A skill owns no state.** There is no `activated_skills` column — this is explicit and
deliberate (`skill_registry.py:293-296`: *"The returned body lands as a tool result → persists
in message history like any other tool result, so no per-session `activated_skills` column is
needed."*).

| state | where | writer | survives compaction? |
|---|---|---|---|
| `enabled_skills` (user pins) | `chat_sessions` column | FE `useContextRack.ts` → `PATCH /v1/chat/sessions/:id` (debounced 300ms) | **yes** — DB column, re-read each turn |
| `injected_skill_codes` | local variable, `stream_service.py:5190` | recomputed every turn | n/a — never persisted |
| skill BODY (auto/pinned) | system-message part | rebuilt every turn | **yes** (rebuilt) |
| skill BODY via `load_skill` | a `role:"tool"` message | the model | **NO** — it is ordinary message history, first thing a compactor drops |
| skill-vector cache | process global `_SKILL_VECTOR_CACHE` | `skill_router.py:111-133` | process-lifetime, no TTL |
| `skill_enablement` toggle | agent-registry DB | `setSkillEnabled` (`skills_internal.go:136-170`) | yes, but only for the 5 seeded slugs |
| `skills.used_count` / `last_triggered_at` | agent-registry DB | **nobody** — never incremented | dead columns |

**The compaction asymmetry is the load-bearing one.** With `lazy_skill_bodies=True`, the
default way a model gets a skill body is `load_skill`, and that body lives in exactly the part
of the context a compactor is designed to discard. An always-injected body is regenerated; a
`load_skill`ed body is gone. There is no re-load trigger, and the L1 index does not say
"you already loaded this."

---

## 5 · DEFECTS & INCOHERENCES (evidence-backed)

**D1 — Studio + plan mode gets no PlanForge, and no `plan` tools.** Executed:
```
resolve_skills_to_inject(studio=True, permission_mode="plan")
  → ['glossary','composition','book','knowledge']      # no plan_forge
surface_hot_domains(studio=True, permission_mode="plan")
  → {glossary, composition, book, knowledge, story}    # no 'plan'
```
Cause: `plan_forge.surfaces = {"book","editor"}` (`skill_registry.py:193`) and a *pure* studio
turn's surface key is `{"studio"}` (`:418-423`), so the plan-mode force-inject at `:542-545`
fails its own `_skill_visible` check. Same for `co_write` (`:198-216`): **the Studio workbench
— the primary authoring surface — never gets the write-mode co-writing workflow.** Yet
`GROUP_DIRECTORY["plan"]` (`tool_discovery.py:99-108`) tells the model in every prompt that
`plan_propose_spec → plan_compile` is the way to lay out a story.

**D2 — Skills claiming tools that are gated OFF by another subsystem.** `glossary_shaping`
names `glossary_adopt_standards`, `glossary_plan`, `glossary_propose_batch`,
`glossary_book_sync_apply` — all four are in `INTENT_GATED_SETUP_TOOLS`
(`tool_discovery.py:442-448`) and are **removed from the turn catalog** unless
`glossary_shaping` is in `injected_skill_codes`. That is coherent *by construction*, but
`glossary` (the always-on core, `glossary_skill.py:85`) also names `glossary_propose_batch`
and `glossary_confirm_action` — and `glossary` alone does not lift the gate. On any non-setup
turn the core glossary skill instructs *"Add a new kind or attribute: `glossary_propose_batch`"*
for a tool that has been deleted from the catalog. `glossary_propose_kinds` is intent-gated and
named by **no** skill at all — it can only ever be reached by `tool_list` on a turn that already
tripped the world-setup gate.

**D3 — Domains with no skill.** `catalog`, `meta`, `registry`, `research`, `story`, `world`
are in `GROUP_DIRECTORY` (`tool_discovery.py:65-109`) and no `SkillDef` claims them.
**`world` is 17 advertised tools** (`world_*`, `world_map_*` — worldbuilding containers,
maps, markers, regions, from book-service's second federated namespace). Seventeen tools with
a directory entry, no skill, no hot domain, no prose anywhere telling the model when or how to
use them. `story` is special-cased in as a surface-level exception
(`tool_discovery.py:359, 413-414`) with an explicit comment that no skill owns it.
`registry` has a directory entry and **zero tools** in the live catalog.

**D4 — 74 tools in claimed domains that no skill's prose names.** Notably 34 of
composition's 53: the whole `composition_arc_*` family (12 tools), `composition_conformance_*`,
`composition_decompile_arcs`, `composition_derivative_*`, `composition_canon_rule_edit`.
`composition_skill.py:73-77` still teaches canon rules as
`composition_list_canon_rules`/`_create`/`_update`/`_delete` — and `_create`/`_update`/`_delete`
are all in `_KNOWN_LEGACY_TOOL_NAMES` (`test_skill_registry.py:383-385`); the live replacement
`composition_canon_rule_edit` is named nowhere. The lint at `:530` did not catch this because
`composition_list_canon_rules, _create, _update` is written as prose, not as three backticked
tokens — the regex sees one token.

**D5 — Same tool claimed by multiple skills, with contradictory rules.** Computed:

| tool | claimed by |
|---|---|
| `book_chapter_save_draft` | `book`, `composition`, `universal` |
| `book_read` | `book`, `composition` |
| `plan_propose_spec`, `plan_compile` | `co_write`, `plan_forge` |
| `translation_job_control`, `translation_job_status`, `jobs_get` | `jobs`, `translation` |
| `confirm_action` | `jobs`, `settings`, `translation`, `universal` |

And they *disagree*. `book_skill.py:78-92` says `book_chapter_save_draft(…, base_version, …)`
and that **no read tool returns the version** ("a genuine dead end"). `composition_skill.py:57-61`
says the same call takes **`expected_draft_version`** and that you should *"read the chapter
with `book_read` first"* to get it. One of these two is wrong about the real argument name, and
both can be injected in the same turn on a book/editor surface. Similarly
`workflow_skill.py:43-46` says *"PUBLISHING… has no agent tool by design"* while
`skill_registry.py:229-234` still documents composition's `book` hot-domain as existing because
*"`composition_publish` → `book_chapter_publish`"* — a tool that is now in the legacy list
(`test_skill_registry.py:403`).

**D6 — Surface-vocabulary drift between the skill store and its consumer.**
`agent-registry-service/internal/api/skills.go:24`:
```go
var validSurfaces = []string{"chat", "compose", "translate", "admin"}
```
`stream_service.py:5348`:
```python
_us_surface = "admin" if _admin else ("editor" if _editor else ("book" if _book_scoped else "chat"))
```
`skills_internal.go:78` filters `if surface != "" && len(surfaces) > 0 && !contains(surfaces, surface)`.
**`editor` and `book` are not valid surfaces at write time; `compose` and `translate` are never
sent at read time.** A user skill declaring any surface other than `chat`/`admin` can
**never** be injected. The only way a user skill reaches a book turn is by declaring an
**empty** surfaces list. Chat-service's own `SkillDef.surfaces` uses a *third* vocabulary
(`book`/`editor`/`studio`/`chat`/`admin`). Three closed sets, no shared constant, no
cross-service test.

**D7 — Dead disable branches + a hardcoded 9-name list.** `stream_service.py:5366-5384` is a
9-way `if _uskills.system_disabled(X) or _uskills.shadows(X)` chain naming
glossary/universal/knowledge/plan_forge/composition/translation/book/settings/jobs. Five of
those slugs have no DB row (§1b) so the branch can never fire; and the chain omits
`glossary_shaping` and `co_write` entirely, so those two skills **cannot be disabled or
shadowed by any user**. A new skill added to `SYSTEM_SKILLS` silently gets no disable path.

**D8 — `l1_line` is computed and never used.** `skills_md.go:91-94` renders
`"· slug — description"`; `user_skills_client.py` exposes it as `UserSkills.l1_lines`;
`stream_service.py:5354` builds its own `f"- {slug}: {description}"` instead. Two formats, one
dead.

**D9 — The eval corpus grades against 12 retired tools.** Scanned
`scripts/eval/skill_scenarios/*.json` against the live catalog:
* `book.json`: names `book_chapter_delete`, `book_chapter_publish`, `book_chapter_purge`,
  `book_get_chapter`, `book_list_chapters`, `book_set_cover` (all **legacy**) plus
  `book_invite_collaborator`, `book_share` (**never existed**).
* `composition.json`: `composition_write_prose`, `composition_get_prose`,
  `composition_outline_node_create`, `composition_outline_node_update`,
  `composition_canon_rule_delete`, `composition_motif_archive` (all **legacy**).

The `ground_truth` for `trash_delete_not_permanent_no_chat_restore` instructs the judge that
*"The correct tool is `book_chapter_delete`"* — a tool `book_skill.py:106-114` now explicitly
tells the model does not exist. **The quality gate would fail a correct agent.**
`scripts/deprecated-tool-scan.py` reports `clean` — it does not scan the eval fixtures.

**D10 — Skills that are effectively unselectable.** `workflow_skill.py` has no registry entry
(§1a) — unreachable by pin, catalog, `load_skill`, or router. `glossary_shaping` is excluded
from both `LOADABLE_SKILL_CODES` (`skill_registry.py:303-305`) and `catalog_items()`
(`:729-731`), so the *only* ways in are a `glossary` pin, a 17-substring keyword match, or a
top-2 embedding hit — and the code comment at `:670-681` records that the embedding path
measurably failed for exactly the intent it exists to serve.

**D11 — A `tool_load` leak past the N5a-FULL capability floor.**
`stream_service.py:5749-5751` seeds from `discovery_catalog` (filtered), but the advertiser at
`:5839` reads `_catalog_index(catalog)` — the **unfiltered** catalog. Combined with
`AUTO_ACTIVATED_TAIL` re-advertising the last 6 activated names in auto mode
(`tool_surface.py:601-607`), a `glossary_plan` loaded on a world-setup turn can re-appear on
the next, non-setup turn.

---

## 6 · PATCHWORK TELLS

Counted in the skill layer alone: **9 distinct layered fixes**, each with its own escape
hatch, each documented as a response to a live dogfood failure.

1. **Skill split as a bug fix.** `skill_registry.py:118-125`: *"Split OUT of the
   always-injected `glossary` core because its imperative 'adopt standards / do not skip it'
   framing made the co-writer rebuild a newcomer's ontology on a plain 'write a chapter' turn
   (a live Gemma QC proved a guard-line alone did not hold)."* — the fix for a prompt problem
   was a new skill, which then needed…
2. **…a keyword gate to un-do the router.** `skill_registry.py:670-687` +
   `_WORLD_SETUP_MARKERS` (`:434-443`), 17 substrings.
3. **…and a catalog-level capability filter to match.**
   `tool_discovery.py:431-484` `INTENT_GATED_SETUP_TOOLS` + `SETUP_INTENT_SKILL =
   "glossary_shaping"` — a **skill code hardcoded inside the tool-discovery module**. Its own
   comment: *"three prior fixes failed because hot-seed + find_tools exclusions don't cover
   `tool_load`."* Then that filter needed its own exemption for pinned rails
   (`:466-480`), documented as *"the Mị Đế 40k-character loop."* <!-- doc-language-gate: ok -- "Mị Đế" is the proper name of the dogfood book, an identifier used across this repo; renaming it would break cross-doc traceability -->
4. **Two independent "keep this tool on the wire" allowlists**, both written after the token
   budget starved something: `ALWAYS_HOT_WRITES` (`tool_surface.py:79-106`, 7 hand-picked
   tools, with a `NOTE (N5a…)` warning *"Do not re-add it here"* embedded in the literal) and
   `skill_named_tools` (`tool_surface.py:559-568`).
5. **Three budget ceilings** that must not be summed: `HOT_SEED_TOKEN_BUDGET`,
   `RAIL_STEP_TOKEN_BUDGET`, `ACTIVATED_TOOLS_TOKEN_BUDGET`, plus four rail-priority tiers
   (`tool_surface.py:420-438`: never-done → repeat-done → one-shot-done → next-step-exempt),
   each tier added by a separate dated fix (`D-RAIL-OWN-BUDGET`, `D-RAIL-REPEAT-BUDGET`,
   `D-RAIL-NEXT-STEP-EXEMPT`, all 2026-07-26).
6. **A shipped experiment knob.** `skill_registry.py:638-643` `LW_LAZY_ALL_SKILLS` —
   *"F12 A/B POC — force ALL skills lazy… Measures the max prefix cut."* An env var that
   short-circuits the entire skill layer, in production code, at the top of the function.
7. **Two lints, each blind in a different way — by their own admission.**
   `tool_surface.py:544-546`: *"The lint that guards the same rule at test time DID see both
   names; it is `co_write`'s `_EXEMPT_SKILL_CODES` entry that kept it quiet. Two guards, each
   blind in a different way, intersecting on exactly the two tools that materialise a plan."*
8. **A hand-maintained legacy list that admitted it was hand-maintained and then went blind.**
   `test_skill_registry.py:366-377`: *"This list is HAND-MAINTAINED, and that is its weakness:
   it covered only glossary, so it was blind to composition-service's 51 `visibility="legacy"`
   tools. The composition skill was consequently teaching FOURTEEN de-advertised names… The
   lint passed the whole time."*
9. **Duplicated degrade-safe hardcodes.** `skill_registry.py:536-541`: the plan→plan_forge rule
   exists **twice** — as a Go DB row (`migrate.go:818-820`) and as a Python `if`
   (`:542-545`) — *"This hardcode STAYS as the degrade-safe fallback."* Same shape for
   write→`vision-to-book`.

Per-model branching: **none found in the skill layer** — the model-specific tuning lives in
budgets and in prose (*"a weak model does worse with more tools"*, `tool_surface.py:52-56`).

Dead/superseded code: `SkillDef` docstring at `skill_registry.py:165-176` still says
`hot_domains={"knowledge"}` *"does NOT by itself mean the runtime hot-seeds 'knowledge'
today (it doesn't)"* — Part D shipped and it now does (`tool_discovery.py:384-393`). The
comment is stale in the opposite direction. `skills.triggers`, `skills.frontmatter`,
`skills.used_count`, `skills.last_triggered_at`, `UserSkills.l1_lines`, and `FIND_TOOLS_TOOL`'s
`group` enum (find_tools is de-advertised, `tool_discovery.py:283-289`) are all unread.

---

## 7 · THE GAP TO A UNIFIED MODEL

Target invariant: **every MCP tool belongs to exactly one skill group, mechanically checkable.**

### What blocks it today

| # | Blocker | Evidence |
|---|---|---|
| B1 | Skills bind to **domains** (prefixes), not tools. A prefix is a *service naming convention*, not a capability grouping. `composition` = 53 tools spanning outline, canon, motifs, arcs, conformance, derivatives, authoring runs — five capabilities under one prefix. | `skill_registry.py:40`, catalog counts |
| B2 | The *real* binding is a regex over English prose. | `tool_surface.py:556` |
| B3 | 6 of 14 domains and ~104 of 202 tools have no skill. | §5 D3/D4 |
| B4 | Domains claimed by 2 skills (`book` ← `book`+`composition`; `glossary` ← `glossary`+`glossary_shaping`) — "exactly one" is already false at the domain level. | §5 D5 |
| B5 | Three surface vocabularies, no shared constant. | §5 D6 |
| B6 | Two skill registries (code=13, DB=5) with no reconciliation test. | §1b |
| B7 | A user-authored skill cannot declare a tool at all. | `skills_md.go:41-49` |
| B8 | Skill↔workflow is unlinked; workflows *do* declare ordered tools and are routed by a *second*, regex-based router. | `intent_workflows.py:32-105` vs `skill_router.py` |

### Is there an existing registry that could be the SSOT?

**Yes — but not the obvious one.**

* ❌ `GROUP_DIRECTORY` (`tool_discovery.py:65-109`) is the closest thing to a tool→group map,
  but it is prefix-derived, duplicated in ai-gateway (`find-tools.ts`, kept in sync by comment
  only — four separate *"Keep in lockstep with ai-gateway"* notes), and it has a `registry`
  entry with zero tools and a `world` entry with 17 orphans.
* ❌ `SYSTEM_SKILLS` cannot be it — it is chat-service-local and cannot see the catalog.
* ✅ **`scripts/deprecated-tool-scan.py::build_catalog()` is the only thing in the repo that
  derives the true tool set from the owning services.** It already returns
  `(legacy, advertised)` from the Go/Python registrations themselves, already has a
  "refuse to assert on a suspiciously small catalog" guard, and is already the backing for the
  two strongest tests in the suite (`test_skill_registry.py:550`, `:604`). It reads the
  services, not a hand-list — which is exactly the property `_KNOWN_LEGACY_TOOL_NAMES` lacked
  when it went blind to 51 composition tools.
* ✅ **The MCP tool `_meta` block is the natural home for the group key.** Tools already carry
  `_meta: {tier, scope, visibility, superseded_by, async}` (see
  `skill_registry.py:335`, `tool_discovery.py:501`). A `_meta.skill_group` field would put the
  declaration **where the tool is defined**, in the owning service — the only place that can
  never drift from the tool's existence.

### The minimum change set for a mechanically-checkable invariant

1. **Add `_meta.skill_group` (a closed enum) to every MCP tool registration** in the owning
   services. One key, next to `tier`/`scope`, which those services already emit.
2. **Generate `contracts/tool-groups.contract.json`** from `build_catalog()` — same pattern as
   the existing `contracts/frontend-tools.contract.json` and
   `contracts/plan-artifacts.contract.json`, and the exact fix
   `test_skill_registry.py:373-377` says is needed but *"is a cross-service change; tracked
   rather than silently skipped."*
3. **Invert the SkillDef declaration**: replace `hot_domains: frozenset[str]` with
   `group: str` + a derived `tools` property read from the contract. A skill then owns a
   *group*, and the tools follow from the contract, not from backticks.
4. **Three gates that can actually go red:**
   * every advertised tool has exactly one `skill_group` (catches the 30 orphans);
   * every `skill_group` is owned by exactly one `SkillDef` (catches `book` ← 2 skills);
   * every backticked tool name in a skill's prose belongs to that skill's own group
     (turns the prose scraper from a *mechanism* into an *assertion*).
5. **One surface enum**, generated into all three consumers (Go `validSurfaces`, Python
   `SkillDef.surfaces`, the `_us_surface` mapper) — a `satisfies Record<keyof T, true>`-style
   mirror, per the repo's own freeform-contract lesson.
6. **Reconcile the two skill registries**: either seed all 13 System rows from
   `SYSTEM_SKILLS` at migrate time, or drop the DB rows and serve the catalog from
   chat-service. A test that the two sets are equal.
7. **Make `load_skill` re-seed.** It must union the loaded skill's group tools into
   `active_tool_names` and into `injected_skill_codes` for the intent gate — otherwise the
   default (lazy) path will keep handing the model instructions for invisible tools.

**None of this requires a new service.** The registry that must exist is a *generated
contract file*, and the generator already exists.

---

## COVERAGE TABLE — every skill, every tool it claims

Legend — **ENFORCED**: a mechanism puts it on the wire when the skill is injected
(`hot` = domain in `hot_domains` *and* it survives the 2000-tok budget, `ride` = captured by
`_skill_prompt_named_tokens` and unioned budget-exempt). **ADVISORY**: named deliberately as a
contrast/warning, exempt from both guards. **DEAD**: not a live advertised tool.
⚠ = enforcement is conditional on the skill actually being injected — which, on the shipped
`lazy_skill_bodies=True` default, it usually is not (§3c).

| Skill | Tool claimed | Status | Note |
|---|---|---|---|
| **glossary** (`hot={glossary}`) | `glossary_search`, `glossary_get_entity`, `glossary_book_ontology_read`, `glossary_list_system_standards`, `glossary_propose_entities`, `glossary_propose_entity_edit`, `glossary_ontology_upsert`, `glossary_ontology_delete`, `glossary_confirm_action`, `glossary_adopt_standards` | ENFORCED (hot+ride) ⚠ | 10/10 exist |
| | `glossary_propose_batch` | ENFORCED-but-**GATED-OFF** | in `INTENT_GATED_SETUP_TOOLS`; removed from catalog unless `glossary_shaping` injected (D2) |
| | `memory_search` | ADVISORY | `_ALLOWED_CONTRASTIVE_MENTIONS["glossary"]` — "do not use for glossary" |
| | `tool_list`, `tool_load` | ENFORCED | ALWAYS_ON_CORE |
| **glossary_shaping** (`hot={glossary}`) | `glossary_book_ontology_read`, `glossary_book_sync_available`, `glossary_confirm_action`, `glossary_list_system_standards`, `glossary_ontology_delete`, `glossary_ontology_upsert`, `glossary_propose_entity_edit`, `glossary_set_genres` | ENFORCED (hot+ride) | |
| | `glossary_adopt_standards`, `glossary_plan`, `glossary_propose_batch`, `glossary_book_sync_apply` | ENFORCED **only on a setup turn** | intent-gated; correct here — this skill *is* the gate signal |
| **universal** (`hot={}`) | `web_search` | ENFORCED | ALWAYS_ON_CORE |
| | `tool_list`, `tool_load` | ENFORCED | core |
| | `book_chapter_save_draft` | ADVISORY (rides anyway) | in contrastive allowlist as "sequencing"; the `(` -form regex now catches it, so it rides |
| | `glossary_deep_research` | ADVISORY | named as a contrast to `web_search` |
| | `confirm_action` | ENFORCED | core |
| | *(via `workflow_skill`)* `book_chapter_publish` | **DEAD** | legacy (`test_skill_registry.py:403`); text says "no agent tool by design", so it reads as deliberate — but the name is still printed |
| **knowledge** (`hot={knowledge}`) | `memory_search`, `memory_recall_entity`, `memory_timeline`, `memory_remember`, `kg_graph_query`, `kg_entity_edge_timeline`, `kg_schema_read`, `kg_propose_fact`, `kg_propose_edge`, `kg_ontology_propose`, `kg_list_templates`, `kg_sync_available`, `kg_triage_list`, `kg_triage_resolve` | ENFORCED (hot+ride) ⚠ | 14/14 exist. `knowledge` is hot on **every** non-admin surface incl. chat |
| **admin** (`hot={}`) | `glossary_admin_standards_read`, `glossary_admin_propose_create`, `glossary_confirm_action` | ENFORCED via a **different catalog** | admin surface skips discovery entirely (`stream_service.py:5241`, `_turn_catalog` empty when `admin_context`); tools come from `/mcp/admin`. `_EXEMPT_SKILL_CODES` |
| | `glossary_admin_propose_patch`, `_delete` | **not extractable** | written as `_patch` / `_delete` shorthand — neither lint nor ride sees them |
| **plan_forge** (`hot={plan}`) | `plan_propose_spec`, `plan_self_check`, `plan_interpret_feedback`, `plan_apply_revision`, `plan_handoff_autofix`, `plan_review_checkpoint`, `plan_validate`, `plan_compile`, `plan_run_pass`, `plan_pass_status` | ENFORCED (hot+ride) ⚠ | 10/10 exist. **Unreachable on a pure-studio turn** (D1) |
| | `tool_load` (structure templates) | ENFORCED | core — but the *template* tool is named only in prose, never as a token |
| **co_write** (`hot={}` — `_EXEMPT_SKILL_CODES`) | `composition_package_tree`, `composition_diagnostics`, `composition_find_references`, `composition_error_block_edit` | ENFORCED (ride only) | budget-exempt union is the **sole** carrier |
| | `plan_propose_spec`, `plan_compile` | ENFORCED (ride only) — **regression site** | written in signature form; invisible to the ride regex until 2026-08-02. Zero-tool-call incident |
| | `propose_edit` | ENFORCED (ride, `meta` domain) | frontend tool, editor surface only |
| | `tool_list`, `tool_load` | ENFORCED | core |
| **composition** (`hot={composition,book}`) | `composition_get_work`, `composition_create_work`, `composition_list_outline`, `composition_get_outline_node`, `composition_outline_node_edit`, `composition_scene_link_edit`, `composition_generate`, `composition_list_canon_rules`, `composition_motif_search`, `composition_motif_book_list`, `composition_motif_suggest_for_chapter`, `composition_motif_get`, `composition_motif_edit`, `composition_motif_bind_edit`, `composition_authoring_run_list` | ENFORCED (hot+ride) ⚠ | 15/15 exist |
| | `book_chapter_save_draft`, `book_read` | ENFORCED — **contradicts `book` skill** | arg named `expected_draft_version` here vs `base_version` in `book_skill.py:78` (D5) |
| | `composition_canon_rule_create/_update/_delete`, `composition_authoring_run_create/_gate/_start/_pause/_resume/_accept/_reject/_close`, `composition_write_prose`, `composition_publish` | **DEAD (legacy) — but not extractable** | written as prose/`_suffix`/`*` glob forms, so neither lint nor ride sees them. The replacement `composition_canon_rule_edit` is named nowhere |
| | 34 further live `composition_*` tools | **UNCLAIMED** | `composition_arc_*` (12), `_conformance_*`, `_derivative_*`, `_decompile_arcs`, … |
| **translation** (`hot={translation}`) | `translation_coverage`, `translation_segment_status`, `translation_list_versions`, `translation_start_job`, `translation_retranslate_dirty`, `translation_set_active_version`, `translation_save_edited_version`, `translation_patch_block`, `translation_update_settings`, `translation_job_control`, `translation_job_status`, `translation_start_extraction` | ENFORCED (hot+ride) ⚠ | 12/12 exist — but `translation` is in **no** surface's default hot domains, so this only holds on a pin/router turn |
| | `jobs_get` | ADVISORY | contrastive ("don't cross the two job systems") |
| | `confirm_action` | ENFORCED | core |
| **book** (`hot={book}`) | `book_list`, `book_read`, `book_update_details`, `book_chapter_create`, `book_chapter_bulk_create`, `book_chapter_update_meta`, `book_chapter_save_draft`, `book_chapter_restore_revision` | ENFORCED (hot+ride) ⚠ | 8/8 exist |
| | `story_search` | ADVISORY | contrastive allowlist; `story` is hot on book-bound surfaces regardless |
| | *(prose-only)* publish / delete / purge / media | correctly **absent** | the 2026-07-27 rewrite removed 14 legacy names + the never-existent `book_delete` |
| **settings** (`hot={settings}`) | `settings_list_providers`, `settings_list_models`, `settings_get_defaults`, `settings_provider_inventory`, `settings_model_register`, `settings_model_update`, `settings_model_set_favorite`, `settings_model_set_active`, `settings_model_set_default`, `settings_model_delete`, `settings_get_profile`, `settings_update_profile` | ENFORCED (hot+ride) ⚠ | 12/12 exist; pin/router-only skill |
| | `settings_provider_create`, `settings_provider_update_secret` | **DEAD — deliberately** | `_DELIBERATELY_ABSENT_TOOL_NAMES`; prose says they don't exist |
| | `confirm_action` | ENFORCED | core |
| **jobs** (`hot={jobs}`) | `jobs_summary`, `jobs_list`, `jobs_get`, `jobs_cancel`, `jobs_pause` | ENFORCED (hot+ride) ⚠ | 5/5 exist; pin/router-only skill |
| | `jobs_resume`, `jobs_retry` | **DEAD — deliberately** | `_DELIBERATELY_ABSENT_TOOL_NAMES` |
| | `translation_job_control`, `translation_job_status` | ADVISORY | contrastive |
| | `confirm_action` | ENFORCED | core |
| **(no skill)** | 17 × `world_*` / `world_map_*` | **UNCLAIMED** | GROUP_DIRECTORY entry, no skill, no hot domain, no prose |
| **(no skill)** | `story_search`, 2 × `catalog_*`, 2 × `workflow_*`, `run_subagent`, 3 × `meta` | **UNCLAIMED** | |

**Totals: 98 of 202 advertised tools are named by some skill. 74 sit in a skill-claimed domain
with no prose. 30 sit in a domain no skill claims.**
