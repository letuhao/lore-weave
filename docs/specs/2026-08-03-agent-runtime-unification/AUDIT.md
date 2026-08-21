# Agent Runtime — Comprehensive Audit (2026-08-03)

**Status:** AUDIT COMPLETE · no spec written yet · no code changed
**Subject:** the product's own agentic runtime — how an MCP tool reaches the model, how skills,
rails, guards and workflows select and withhold it.
**Not in subject:** the repo's human dev workflow (`agentic-workflow/`, `scripts/workflow-gate.py`,
`.github/workflows`), which merely shares the word "workflow".
**Repo state:** branch `feat/frontend-tools-mcp-migration`. The six layer reports were taken at HEAD
`24dd7bdac`; four commits landed during the audit (`b05cfcf7e`, `363e22f43`, `9154d67fe`,
`d497ebf7a`), of which `363e22f43` touches this domain directly. Its effect is reconciled in
[`SPEC.md`](SPEC.md) §4 P0-1 and §8 — three of its four fixes hold; the fourth was re-measured
end-to-end on the running stack **after** it shipped and is inert.

**Method.** Six parallel read-only auditors over disjoint file sets (tool surfacing · skills ·
rails/guards/state · MCP servers + federation · workflows + agent-registry · documented intent and
drift), plus a main-session read of `stream_service.py` (7,818 lines — the spine every layer meets
in, deliberately not given to any auditor so it was read once, not six times). Full per-layer
reports, with `file:line` on every claim, are in [`audits/`](audits/). Load-bearing findings were
re-verified independently before being recorded here; one auditor claim was found inverted and is
corrected in §2.3.

---

## 0 · The one-paragraph answer

The architecture is not broken. **For tool availability specifically, it never existed.** What
exists is thirteen successive, individually-correct mechanisms for "which tools does the model see
this turn", accumulated between 2026-06-10 and now, of which **exactly one was ever retired**. Each
was built to fix a measured live incident; each is defensible on its own; none composes with the
others, and none can report why it fired. Underneath that sits the actual hole the owner named:
**no artifact anywhere — code, database, contract, or document — assigns a tool to a skill.** The
finest granularity ever specified is a *name prefix*. The code states this plainly at
`services/chat-service/app/services/skill_registry.py:154`:

> `# surface_hot_domains() are DOMAIN-level only, not per-tool — a real constraint,`

Everything else in this audit follows from that one sentence.

---

## 1 · The numbers

### 1.1 Coverage against the owner's two stated invariants

| Invariant the owner wants | Measured today |
|---|---|
| Every MCP tool belongs to **one skill group** | **98 of 202** advertised tools are named by any skill (≈49%). 74 sit in a domain a skill claims but name no tools from; 30 sit in a domain **no skill claims at all** — including all **17 `world_*`** tools. |
| Every MCP tool sits in **≥1 workflow** | **30 of 223** ≈ **13%**. Twelve seeded rails name thirty distinct tools between them. |

### 1.2 There are four different answers to "how many tools do we have"

This is itself a finding, not bookkeeping noise — a coverage ratio is only as honest as its
denominator, and this project currently has four.

| Count | What it counts | Source |
|---|---|---|
| **312** | federated `/mcp` tools across 10 owner services | registration-site scan, [audits/04](audits/04-mcp-servers-federation.md) §1.1 |
| **315** | what `tools/list` actually serves (312 + `tool_list` + `tool_load` + `propose_edit`) | `ai-gateway/src/mcp/handlers.ts:69-82` |
| **≈334** | distinct names incl. admin surface, consumer-local, edge-synthetic, chat-only frontend tools | [audits/04](audits/04-mcp-servers-federation.md) §1.1 |
| **223** | `contracts/tool-liveness.json` — **eval-derived, not catalog-derived**, and blind to consumer-local tools | [audits/05](audits/05-workflows-registry.md) §9.1 |
| **202 / 114** | advertised vs `visibility:"legacy"`, per `scripts/deprecated-tool-scan.py` | [audits/02](audits/02-skills.md) header |

**37% of the federated catalog is tagged legacy and still served.**

### 1.3 The control surface, counted

- **16 producers** that can put a tool on the wire ([audits/01](audits/01-tool-surfacing.md) §1).
- **18 filters** that can take it off. **13 of the 18 are completely silent** — no log, no counter,
  no note to the model, no SSE field. The most frequently-firing one of all,
  `budget_names_by_tokens`, is among the silent ([audits/01](audits/01-tool-surfacing.md) §3).
- **8 independent answers** to "is this tool available?", enumerated by the project itself in
  `docs/specs/2026-07-30-chat-service-control-plane-refactor.md:69-78`, with its own verdict:
  *"Nobody can answer 'why is tool X not on the wire?' without reading all eight."*
- **3 independent selectors** for "which workflow applies": the C6 mode binding, the embedding
  skill-router, and 43 hardcoded English regexes.
- **14 loop breakers**, all function-local, all reset by a confirm suspend/resume.

---

## 2 · The five structural defects

Everything in the per-layer reports reduces to five shapes. Each is stated with its sharpest
evidence; the reports carry the rest.

### 2.1 Group membership is a name prefix, mirrored by hand in three languages

`_domain_of(name)` (`chat-service/app/services/tool_discovery.py:788-793`) resolves a tool's group
from its **name prefix** through a 7-entry alias table. `GROUP_DIRECTORY`
(`tool_discovery.py:65-109`) is the nearest thing to a group registry, and it exists **three times**:
Python, `ai-gateway/src/federation/find-tools.ts:27`, and
`agent-registry/internal/api/mode_bindings.go:46-50` — held together by the words *"Keep in lockstep
with ai-gateway"*, written four times in one file.

**They have already drifted.** The registry knows 12 categories; the other two know 14. So
`mode_bindings.go:340-342` rejects a legitimate pin with a categorical falsehood:

> `"'world' is not a tool category — it would seed nothing"`

It is one, and it seeds the entire namespace the `draw-a-map` rail depends on.

The cost of prefix-as-membership is paid at federation too: `computeCatalog`
(`ai-gateway/src/federation/catalog.ts:65-77`) **silently drops** any tool whose name escapes a
hand-maintained prefix allowlist. The comments in `config.ts:109-134` are an incident log — `story_`,
`lore_`, `world_` were each added *after* the gate deleted them, each entry ending *"same drop class
as story_search"*. Five namespaces, five identical outages, five hand-patches, nothing preventing the
sixth.

### 2.2 The skill→tool edge is a regex over English prose

The mechanism that actually decides which of a skill's tools ride budget-exempt onto the wire is one
line, `chat-service/app/services/tool_surface.py:556`:

```python
re.findall(r"`([a-z][a-z0-9_]{3,})(?:`|\()", prompt)
```

It scrapes backticked tokens out of the skill's markdown. From the `glossary` skill it extracts 27
tokens, **13 of which are not tools**. The junk is harmless only because it is intersected with the
live catalog — but the binding contract is literally *"whatever the author put in backticks."*

Its own docstring records the failure this produces (`tool_surface.py:539-546`): `co_write` named its
two plan tools in signature form rather than backticked, so `plan_propose_spec` and `plan_compile`
were never advertised, and — measured live 2026-08-02 — the co-writer emitted **6,948 characters of
plan prose with `finish_reason=stop` and zero tool calls.**

Two lints guard this rule and are blind in complementary ways: the authoring lint scans all prose but
exempts `co_write` and `admin`; the runtime scraper covers all skills but only backticked tokens. The
file names the intersection that shipped through both.

Meanwhile a **user-authored skill cannot declare a tool at all** — `skills_md.go:30-56` parses exactly
three frontmatter keys (`name`, `description`, `surfaces`), and `skill_named_tools` reads
`SYSTEM_SKILLS` only.

### 2.3 Capability and guidance are computed under opposite assumptions

`surface_hot_domains` (`tool_discovery.py:397-407`) calls `resolve_skills_to_inject(...)` **without
`lazy_bodies`**, which therefore defaults `False` (`skill_registry.py:468`) and takes the legacy
auto-inject branch — returning the full surface defaults.

The path that actually injects prompt text passes `lazy_bodies=settings.lazy_skill_bodies`
(`stream_service.py:5210`, `:7319`), which defaults **True** (`config.py:272`) — returning `[]`.

> **Correction to [audits/01](audits/01-tool-surfacing.md) §5.3.** That report stated the hot-seed
> call returns `[]`. It is the reverse: the hot-seed call returns *more* skills than the prompt does.
> Re-verified in the main session against both call sites. The consequence the report describes is
> real, and the inverted mechanism makes it worse, not better — so the finding stands and the fix
> direction flips.

**Effect, on the shipped default config:** the wire carries glossary + book + knowledge + composition
+ story tools while **no skill body is injected to teach any of them**. This is the exact inversion of
the principle the same module states at `tool_discovery.py:438` — *"Guidance and capability move as
ONE signal."*

The lazy path re-opens it from the other side. `load_skill` *"executes nothing, activates no tools"*
(`stream_service.py:3059`) and `active_tool_names` is fixed at loop entry (`:1856`). So
`load_skill('translation')` on a chat surface returns a body that opens *"emit the tool call in the
SAME turn"* and names 13 tools, **none of which are on the wire.**

And the skill body obtained that way lands as a `role:"tool"` message — the first thing a compactor
discards, with no re-load trigger. An always-injected body is regenerated; a `load_skill`ed body is
simply gone.

### 2.4 A withheld tool is indistinguishable from a nonexistent one

Six suppression sets union at a single advertise chokepoint (`stream_service.py:2066-2108`): tier
gate, `suppress_tool_list` (F18), `oneshot_suppress` (4 configurable modes),
`rail_gate_suppressions`, `failure_suppress`, and the hot-set budget. The union is a bare `set()`.
Provenance is lost at the moment it is formed.

Three places then tell the model something false rather than nothing:

1. **`tool_load` on a down provider's tool** returns `not_found` on the execution path.
   `tool_discovery.py:1050` states outright that `not_found` *"ASSERTS that no such tool exists."*
   The discovery path was fixed for exactly this after a 2026-07-23 incident
   (`find-tools.ts:568-580`: *"Asserting `not_found` there is a LIE, and it cost us a real
   incident"*); the **execution** path never got the fix and never consults `isPartial()`
   (`handlers.ts:399-401`).
2. **`tool_list(category="research")`** answers *"no tools currently available in this category"* —
   because `web_search`, the category's only member, is in the always-on core and the live call site
   excludes the core (`stream_service.py:2885`). The same prompt's `GROUP_DIRECTORY` advertises the
   domain. The `meta` category has the same shape.
3. **`INTENT_GATED_SETUP_TOOLS`** removes five tools from the turn catalog *object itself*, so they
   are un-seedable, un-listable and un-loadable. The only deterministic way to lift the gate is
   `_WORLD_SETUP_MARKERS` — **17 English substrings** (`skill_registry.py:434-453`). This project's
   dogfood corpus and its PO write in Vietnamese, so a request meaning *"set up the world for this
   story"* — the canonical world-setup intent, and a verbatim match for the marker
   `"set up the world"` in English — matches nothing, and the five tools cease to exist for that turn.

The same English-only coupling governs workflow selection: all 43 intent regexes
(`intent_workflows.py:32-105`) are English, so a Vietnamese request pins no rail at all.

### 2.5 Guards exist, but not at the seam they guard

The clearest single instance, confirmed by two independent auditors and re-verified in the main
session:

**`repeat` is destroyed in transit, and it is load-bearing for the action gate.**

- Go declares `Repeat string` — an enum `none | per_item:<key>` (`workflows.go:45`).
- Every seeded rail writes `"repeat": true` — a **bool** — in 6 rails / 13 steps
  (`migrate.go:555-745`).
- `_ = json.Unmarshal(stepsJSON, &wf.Steps)` (`workflows_rest.go:110`, `workflows.go:850`) records the
  `UnmarshalTypeError`, decodes the remaining fields, and **discards the error**. `Repeat` stays `""`;
  `omitempty` drops it from the wire.
- `rail.py:321` reads `repeat=bool(st.get("repeat"))` → always `False`, so
  `if d and not s.repeat: done_tools.add(s.tool)` (`rail.py:725`) **strips the tool of every step
  explicitly marked repeatable to prevent exactly that.**

One field, two incompatible meanings, joined by an error nobody reads. `workflows.go:61-64` carries a
comment warning about this precise drop-on-serialize trap — **two fields above `Repeat`** — and
`workflows_test.go:180` tests it, for `done_when` only.

The lint written the day before to protect this reads the **seed SQL**, not the wire: it regex-scrapes
`'[…]'::jsonb` out of `migrate.go` and asserts `st["repeat"].(bool)`
(`migrate_lint_test.go:300-316`). It is green while a sibling service drops the field. It self-checks
its sample size against vacuity but never checks its subject — NV-2, *the scope never reaches it*.

The same shape recurs across every layer:

| Guard | Guards | Cannot reach |
|---|---|---|
| `test_tool_list_contract_drift.py:57-73` | `tool_list` schema-vs-handler drift | compares chat's schema to **ai-gateway's** handler; chat intercepts `tool_list` locally and never routes it. The live default is inverted (`True` vs advertised `false`) |
| `test_tool_list_load.py:64-66` | `web_search` lists under `research` | calls the pure function **without** the `exclude=` the production site passes |
| `validateWorkflow` | step tool names | *"deliberately does NOT check tool-catalog membership — the step-runner (chat-service) owns [it]"* (`workflows.go:135-138`). **The named owner does not exist.** Grep finds no catalog check anywhere; `tool_surface.py:142` passes an unknown name through free of budget and with no diagnostic |
| `find-tools.spec.ts:203-207` | the GROUP_DIRECTORY lockstep | asserts against a **third hardcoded copy** typed into the test; never reads the Python |
| declarative `hooks` | tool deny policy | only sees backend MCP tools — a `deny` on `propose_edit` is a silent no-op |
| `VALID_GATE_MODES` | gate-mode typos | **exported and never used**; a typo'd `RAIL_ACTION_GATE_MODE` silently disables gating |
| 14 loop breakers | runaway loops | all function-local; `chat_suspended_runs` persists only `working`/`pinned_step_tools`/`book_id`, and the flagship rail's step 3 **is** a confirm gate, so reset is the normal path |

`workflow_enablement` is the settings-layer twin: the FE join returns `enabled`, so the GUI shows
"disabled" — while `internalWorkflows` (`workflows.go:817-823`), the only reader the agent uses, never
joins it. Its sibling `internalSkills` does (`skills_internal.go:48`). The toggle is write-only.

---

## 3 · Three vocabularies for one concept, three times over

The same failure recurs independently in three places, which is what makes it structural rather than
accidental.

| Concept | Copy A | Copy B | Copy C | Consequence |
|---|---|---|---|---|
| **tool group / category** | `tool_discovery.py:65` (14) | `find-tools.ts:27` (14) | `mode_bindings.go:46` (12) | registry rejects `world` and `meta` as "not a tool category" |
| **surface** | `SkillDef.surfaces` = `{book, editor, studio, chat, admin}` | Go `validSurfaces` = `{chat, compose, translate, admin}` (`skills.go:24`) | runtime emits `{admin, editor, book, chat}` (`stream_service.py:5157`) | an authored workflow or skill declaring `["chat"]` — the natural first choice — is **invisible on every book turn**. The only usable value is *empty*. `studio` matches nothing at runtime |
| **step gate** | `validWorkflowGates` (Go) | `VALID_GATES` hand-copied (`workflow_runner.py:35`) | FE types `gate?: string` and compares `!== 'auto'` — a value in none of the three enums | `gate` is decorative; nothing suspends on it. `gate:"approval"` on a Tier-R tool produces a rail that tells the model the user must approve while the tool auto-runs |

`migrate.go:500-502` diagnoses the surface mismatch exactly — then works around it for **one seed
row** instead of fixing the enum.

---

## 4 · What is already good, and must be preserved

An audit that only lists defects would mislead the spec. Five things here are genuinely well-built
and are the raw material for the fix:

1. **`_meta` is a real per-tool manifest, validated at the registration chokepoint.** It already
   carries `tier`, `scope`, `synonyms`, `visibility`, `superseded_by`, `paid`, `async`,
   `ambient_book`. **Go panics** on a missing tier (`MustValidateToolMeta`); **Python raises**
   (`require_meta`). This is the one place in the system where a per-tool declaration cannot drift
   from the tool's existence.
2. **`scripts/deprecated-tool-scan.py::build_catalog()`** derives the true tool set **from the owning
   services**, cross-language, and already backs the two strongest tests in the suite. It reads the
   services, not a hand-list — precisely the property `_KNOWN_LEGACY_TOOL_NAMES` lacked when it went
   blind to 51 composition tools.
3. **Federation plumbing**: one pure `computeCatalog`, per-call envelope isolation, PARTIAL
   degradation with outage-aware notes, and a boolean-subschema gate that already killed the
   whole-provider de-federation class.
4. **agent-registry-service is a complete SSOT for workflows** — one table, no code duplicate, no
   YAML, correct three-tier tenancy with per-tier partial UNIQUE indexes, HITL propose→approve,
   revisions, audit. It is a real service, not a shell.
5. **The rail driver grounds on observed artifacts**, not the model's memory: `done_when` reads the
   book's actual state and can call a tool's reported success a lie. That is the right instinct and
   should survive intact.

The registry that must exist is a **generated contract file**, and the generator already exists.
No new service is required.

---

## 5 · Why previous attempts did not converge

From [audits/06](audits/06-documented-intent-and-drift.md) §2 — thirteen mechanisms, one retirement:

1. whole-domain hot-seed → 2. `find_tools` → 3. token-budgeted hot-seed → 4. `GROUP_DIRECTORY` +
CAT-4 → 5. skill `hot_domains` **(the one clean retirement — Part D deleted three constants)** →
6. `find_tools` hardening *(demoted in the same document that proposed it, same day)* →
7. embedding intent→skill router → 8. `tool_list`/`tool_load` + workflows + C6 →
8b. intent→workflow regex pinning → 9. F17 hides `find_tools` *(handler and ~700 lines of
embedding/retry machinery remain live for a tool the model cannot see)* → 10. eager index
*(premise disproven, correctly killed)* → 11. catalog unification → 12. N5a capability floor
*(collided with the rail on day one: 40,597 characters of one repeated paragraph)* → 13. move the
FSM out of the agent.

Three structural reasons it kept not converging:

- **Every fix was additive.** Twelve of thirteen left the predecessor running, so each new correct
  mechanism increased the number of ways a tool could vanish.
- **Enforcement is strong per-artifact and absent per-system.** Every gate in the repo validates one
  artifact against one other artifact. **Not one gate validates a mechanism against another
  mechanism** — which is exactly the failure class every finding in §2.5 belongs to. The project
  wrote this down on 2026-07-30 (`D-CHAT-CONTROL-PLANE` §D: *"nothing tests them against each other,
  which is why a contradiction survived"*) and did not build it.
- **The backlog is invisible to its own gate.** `deferral-gate.py` requires an id inside a
  `deferral-registry:begin/end` block. Repo-wide, exactly two files have such a block, neither is
  `SESSION_HANDOFF.md`. **Zero deferrals in this domain are mechanised.** One row is in a table;
  ~10 live as prose in a 10,198-line handoff.

### 5.1 The premise contradiction the spec must settle

Three measured findings, five days apart, never reconciled:

- `2026-07-21-eager-tool-index-mode.md:28-35` — *"❌ WRONG: 'weak models can't run the discovery
  loop.' Disproven live. Confirmed four-for-four."*
- `docs/eval/tool-liveness/discovery-gap/RESULTS.md:15` (07-22) — *"Discovery WORKS… The foundational
  concern is resolved."*
- `2026-07-27-glossary-kg-build-workflows.md:8-11` — *"A weak local model cannot reliably CHOOSE
  tools, even after 10 platform fixes made the surface correct… Tool-choice is the unfixable link.
  Therefore: move the state machine OUT of the agent."*

They are arguably compatible — discovery ≠ selection-among-many — but **no document draws the
distinction**, so the corpus self-contradicts on its single most load-bearing premise. Whether the
unified architecture targets in-agent tool choice or the out-of-agent FSM depends entirely on which
of these is treated as true.

---

## 6 · What a unified architecture requires

Stated as the minimum that makes the owner's two invariants *mechanically checkable*, in dependency
order. Each item is justified by findings above; none requires a new service.

### R1 — A generated tool manifest (the blocking prerequisite)

*"Every tool appears in ≥1 workflow"* is a set difference whose **left operand does not exist as
data**. Emit `contracts/mcp-tool-catalog.json`: one row per tool with `{name, owner_service, surface,
group, tier, scope, visibility, superseded_by, paid, async, public_policy}`. Generate from a live
`tools/list` in CI, with `build_catalog()`'s static scan as the offline fallback. This single artifact
unblocks R2–R6 and fixes §1.2's four-denominator problem by construction.

### R2 — `group` becomes data, declared at the registration chokepoint

Add `group` to `require_meta` / `NewToolMeta`. The chokepoint that already panics on a missing tier
panics on a missing group. `GROUP_DIRECTORY`, `_DOMAIN_ALIASES` and `EXTRA_PREFIX_MAP` become
**derived, not authored** — which retires the three-copy lockstep and the five-incident prefix
allowlist together.

### R3 — Skills declare tools, not prefixes

Replace `SkillDef.hot_domains: frozenset[str]` with `group: str` plus a `tools` set read from R1.
Three gates then become red-able: every tool has exactly one group (catches the 30 orphans); every
group is owned by exactly one skill (catches `book` ← 2 skills); a backticked tool name in a skill's
prose must belong to that skill's group (turns the prose scraper from a *mechanism* into an
*assertion*). Extend the frontmatter so a **user-authored** skill can declare tools at all.

### R4 — One explained tool surface

Replace the 16 producers / 18 filters with one function returning a per-tool record carrying
`admitted_by` and `excluded_by` as **closed enums**, never free strings, `excluded_by` never null for
a name the model could plausibly want. Emit it on the SSE surface channel and log it once per pass.
This is `D-CHAT-CONTROL-PLANE` §A, and it is the only thing that makes *"why can't you see tool X
right now?"* answerable — by a user, by an agent, or by the next auditor.

### R5 — Guards register what they withhold

A guard that removes a tool declares it through R4's `excluded_by` enum with logged precedence. This
is `D-CHAT-CONTROL-PLANE` §C, and it is what makes the anti-rot rule enforceable instead of aspirational.

### R6 — The coverage gates, shipped with a ratchet

`skill_coverage` and `workflow_coverage` over R1, each requiring an explicit waiver row with a reason
rather than silence. **Today's numbers are 49% and 13%** — so these must ship as ratchets (a baseline
that may only shrink), never as pass/fail. A gate that goes red on day one gets disabled on day two.

### R7 — One surface vocabulary, one category enum, generated into all consumers

Per §3. Until the surface enum is unified, *"author more workflows to raise coverage"* is not even
available as a remedy, because an authored workflow cannot be visible where book work happens.

### R8 — Retire the predecessors, explicitly

Every superseded doc gets a status banner naming its successor, the way
`2026-07-21-eager-tool-index-mode.md` correctly did. A unified spec that does not do this **becomes
the fourteenth layer** — which is the specific way the previous twelve attempts failed.

### Cheap prerequisites, independently correct, unblocking the above

| Fix | Why now |
|---|---|
| Stop discarding `json.Unmarshal` errors (`workflows.go:850`, `:347`, `:371`; `workflows_rest.go:110`, `:140`) | one change; would have surfaced the `repeat` bug the day it shipped |
| Make `repeat` one type with one meaning + the `TestRepeat_SurvivesTheStepsRoundTrip` twin | 13 rail steps are wrongly disarmed today |
| `handleCallTool` consults `isPartial()` | the execution path is lying to the model during every outage |
| Delete or re-point the three `find_tools` strings the public edge still serves | every connecting client is told to call a tool that was removed |
| `LEFT JOIN workflow_enablement` in `internalWorkflows` | one join; the GUI currently lies |
| Unify the surface enum | blocks R7 and every authored artifact |

---

## 7 · The decision this audit cannot make

**Which runtime is the target?** §5.1's contradiction is a product decision, not a technical one, and
it changes the shape of the spec:

- **In-agent** — unify the chat control plane (R1–R8 as written); the 07-27 FSM stays a parallel
  product for specific jobs.
- **Out-of-agent** — the FSM pivot is the future; the chat rail is declared legacy and the spec's job
  is to define the boundary and stop investing behind it.
- **Both, with a declared boundary** — most likely correct, and the most work: it requires saying
  which capability classes live where, and R1/R2 are prerequisites either way.

R1, R2 and the cheap prerequisites are required under **all three** readings. They can begin before
the decision is made.

---

## Appendix — the per-layer reports

| Report | Covers |
|---|---|
| [`audits/01-tool-surfacing.md`](audits/01-tool-surfacing.md) | 16 producers, 18 filters, the block list, budget mechanics, the two-engine drift |
| [`audits/02-skills.md`](audits/02-skills.md) | three things called "skill", the router, the prose-scraper binding, full per-skill coverage table |
| [`audits/03-rails-guards-state.md`](audits/03-rails-guards-state.md) | state inventory, the rail model, every gate, the breaker-reset path |
| [`audits/04-mcp-servers-federation.md`](audits/04-mcp-servers-federation.md) | full tool catalog by service, 5 registration patterns, federation caching, the public-edge policy gap |
| [`audits/05-workflows-registry.md`](audits/05-workflows-registry.md) | the C3 model, 12 rails, the missing step-runner, agent-registry SSOT assessment |
| [`audits/06-documented-intent-and-drift.md`](audits/06-documented-intent-and-drift.md) | the 13-mechanism timeline, doc contradictions, the deferred backlog, what is measured |
