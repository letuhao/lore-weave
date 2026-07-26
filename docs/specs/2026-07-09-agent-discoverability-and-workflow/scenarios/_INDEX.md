# Scenario backlog & fan-out board

One scenario per umbrella workflow (`S0x` ↔ `W0x`). **Claim a row (Owner) before starting.** Author
expectation-first per [`_TEMPLATE.md`](_TEMPLATE.md); live-test with `gemma-4-26b-a4b-qat` on the chat
GUI; save runs under `docs/eval/discoverability/`.

Status: ⬜ not started · ✍️ drafting · 🔬 baseline captured · 🔧 building · ✅ passing

| Scenario | Job | Persona | Mode | Priority | New backing capability? | Status | Owner |
|---|---|---|---|---|---|---|---|
| [S01](S01-glossary-bootstrap.md) | Suggest & set up a glossary/ontology for a book | P2 Linh | write | **P0** | no (existing tools) | ✅ **PASS (WS-5 2026-07-11)** — `glossary-bootstrap` rail + directive → gemma follows list→adopt→confirm; `book_kinds` 0→10-13. Real-GUI **5/5** (FE auto-render net covers model skip/corrupt/stall on confirm); headless agent-only ~3/4. | this session |
| [S02](S02-populate-glossary-entities.md) | Populate the glossary with entities (the "add entities" failure) | P1/P2 | write | **P0** | partial (seed-doc→entities for the doc variant) | ✅ **PASS (re-test 2026-07-11)** — `book_id` now injected; entity created + retrievable. Baseline ❌ 2026-07-09 drove the fix. | this session |
| [S03](S03-entity-triage.md) | Triage the entity inbox (approve / reject / merge / edit) | P2 Linh | write | P0 | no | ✅ **PASS (2026-07-11)** — W3 `entity-triage` rail + the cross-turn activation fix (`5eb76d82a`): agent follows list→merge→status_change ACROSS turns; pile **drains 27→23**. (Inbox visibility was stale data — extraction DOES tag ai-suggested.) | this session |
| [S04](S04-kg-build-from-glossary.md) | Build the KG from a populated glossary (project→adopt→graph→wiki→benchmark) | P2 Linh | write | **P0** | yes (glossary→KG node projection; manual node) | 📋 JSON authored · **fixture blocked** (needs active lore + 0 prose; none exists) — scoped in §7 | this session |
| [S05](S05-translation-pass.md) | Run a translation pass (coverage→start/dirty→confirm→watch→activate) | N-T translator | write | P0 | no | 📋 JSON authored · **fixture blocked** (needs partial coverage: some translated + one dirty) — scoped in §7 | this session |
| **[S06 ★ FLAGSHIP](S06-flagship-idea-to-arc.md)** | **"I have a story in my head — help me write it"** — one long session: vision → world structure + cast + connections + arc plan + drafted chapter, all beneath the surface. **The front door; orchestrates S01–S05.** | P1 Mai | write | **P0 (ship target)** | yes (seed-doc→entities; glossary→KG nodes; long-session continuity guards) | 🔬 ❌ **2/5 — WS-3 2026-07-11** (was 1/5). **Assent gap CLOSED**: "yeah do it" now RUNS the pinned rail (`glossary_adopt_standards`) instead of improvising `plan_propose_spec`. World gets built (**0→12 kinds**), plan retained, jargon PlanForge **27→4**, discovery calls **0**. Still ❌: cast/connections/draft never run — the agent STARTS the rail but does not CONTINUE it (no progress state + one-tool-per-turn). Next: rail continuation. | this session |
| S06b | Compose-a-chapter deep-dive (6-phase Idea→…→Assemble, standalone) | P1 Mai | write | P1 | no (design exists, doc 06) | ⬜ | — |
| S07 | End-to-end "build a book" (import→translate→glossary→KG→wiki) | P1/P2 | write | P1 | no (promote workflow_skill chain) | ⬜ | — |
| S08 | Intent-branching onboarding fork (Write / Build world / Translate / Explore) | N-* newcomer | ask | P1 | yes (onboarding fork UX) | ⬜ | — |
| S09 | Canon-check / continuity pass | P1 Mai | write | P1 | no | ⬜ | — |
| S10 | Worldbuilding-first "world container" (prose-less lore/graph/map) | P2/N-B | write | P2 | yes (world-container journey) | ⬜ | — |
| S11 | Reader / lore-seeker exploration (spoiler-aware ask-the-lore) | N-L reader | ask | P2 | yes (reader product) | ⬜ | — |
| S12 | Multi-chapter autonomous drafting over an approved plan (Agent Mode) | P1 Mai | write | P2 | no (wrap existing FSM) | ⬜ | — |

## Cross-cutting scenarios (mechanism, not a single workflow)

These test the *primitives* directly (they underlie every S0x). Author after S01/S02 baselines expose
the loop concretely.

| Scenario | Tests | Priority | Status | Owner |
|---|---|---|---|---|
| [S00a](S00a-tool-list-deterministic.md) | `tool_list(category)` returns the full, deterministic set; gemma stops looping | **P0** | ✍️ drafted | this session |
| [S00b](S00b-tool-load-progressive.md) | `tool_load(name/category)` loads exact schemas; gemma then calls correctly | **P0** | ✍️ drafted | this session |
| S00c | `workflow_list` / `workflow_load` + step-runner honors confirm gates | P0 | ⬜ | — |
| S00d | Mode → capability binding (write mode auto-seeds a skill/tool-set) | P1 | ✅ **SHIPPED (WS-3 2026-07-11)** — `mode_bindings` 3-tier + `disable_workflows` veto; `inject_workflows` PINS the rail into context. [eval](../../../eval/discoverability/2026-07-11-ws3-mode-capability-binding.md) | this session |
| S00e | Permission-management UI: view / revoke / deny an allowlisted tool | P1 | ⬜ | — |

## The front door vs. the servants

**S06 is the flagship — the thing we ship.** A user speaks pure story-vision and a real book foundation
appears (world structure → cast → connections → arc plan → drafted chapter) without ever naming a tool.
**S01–S05 are its servants** — the same capabilities as standalone jobs, and their acceptance tests are
how we prove each servant works in isolation. S06 is a *harder bar* than the sum of S01–S05 because it
alone stresses long-session continuity, token budget, and compaction — see S06 §9/§12. Build the
servants' mechanism (Phases 0–2) to make S06 reachable; S06's ❌→✅ with a mid-tier model is the go/no-go
for the whole effort.

## Suggested first fan-out wave

S06 (the ship target — run its baseline first to quantify how far gemma gets), plus S02, S00a, S00b
(the exact reported pain + the mechanism that fixes it). These baselines quantify the loop with real
gemma numbers and ground every later priority call.
