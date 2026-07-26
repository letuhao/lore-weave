# PlanForge — Market & Gap Analysis

> **Date:** 2026-07-01 · **Status:** INVESTIGATE (Phase A) · **Fixture:** `scripts/plan-forge-poc/fixtures/story-plan-v1.md`

## Product positioning

LoreWeave is a **novel-crafting platform** (schema, state, pipelines, validation, agents) — not a prose-writing assistant like Sudowrite. The architecture mirrors a **coding IDE**:

| IDE (software) | LoreWeave |
|----------------|-----------|
| Requirements doc (NL) | Planning doc / braindump |
| Architect → system spec | **PlanForge → NovelSystemSpec** |
| Type system | Glossary entities + EAV |
| Module tree | `outline_node` (arc → chapter → scene) |
| Runtime config | `PlannerState` (PA/HA/CD/THR) |
| Build pipeline | Composition `planning_pipeline` |
| Linter | Plan validator + continuity rules |
| PR review | Human checkpoint gates |

**Market gap:** Commercial tools extract into **their fixed schema** (Characters, Worldbuilding, Outline). None infer **novel-specific system design** — state machines, constraint rules, event→state traceability — then compile to platform artifacts.

## Market landscape

### Commercial patterns

| Product | Unstructured → structured? | Human gate | Limit |
|---------|---------------------------|------------|-------|
| Sudowrite Import Novel | Yes — prose/notes → Story Bible | Validation step | ~5–7 main chars; 120k words |
| Sudowrite Smart Import | Per-section paste → entities | Choose elements to import | ~30 world elements/batch |
| PlotForge | .md/.docx → characters, world, timeline | Review extracted data | Fixed output types |
| Feodary | Smart Import → library entries | Side-by-side review before commit | Auto-detect types |
| PlotLens | Manuscript → cited canon DB | Fact review | Prose-optimized, not planning docs |
| Inxtone | Scaffold markdown; no full plan ingest | Manual | CLI-first |
| NovelAI Lorebook | No — manual entries | N/A | Activation keys |

**Common pattern:** Identify → map to fixed schema → human validates → assemble context per task (never monolithic blob in prompt).

### Research patterns

| Paper | Relevant pattern |
|-------|------------------|
| WriteHERE (EMNLP 2025) | Heterogeneous recursive planning |
| Dramaturge | Global → scene → coordinated revision |
| StoryWriter | Outline → planning → writing agents |
| DOME | Dynamic hierarchical outline + memory |
| Agents' Room | Planning agents + scratchpad orchestrator |

## LoreWeave gap matrix

| Capability | Market | LW today | PlanForge POC |
|------------|--------|----------|---------------|
| NL plan ingest | Partial (fixed schema) | None | `PlanDocument` parser |
| Propose system spec | None (extract only) | None | `NovelSystemSpec` |
| Planner variables (PA/HA/CD/THR) | None | None | `PlannerState` schema |
| Event → state links | None | None | `PlanGraph` |
| Human checkpoints | Yes (all major tools) | Pipeline design only | CLI `--interactive` |
| Arc-level scene plan | Outline tools | `planning_pipeline` (1 arc) | `PlanningPackage` bridge |
| Compile to glossary/outline | Partial | `cast_plan` seed | `compile_targets` |
| Premise ≤4k for composition | N/A | Hard cap 4000 chars | Package compiler |

## Fixture annotation: `story-plan-v1.md`

~22k chars · 7 top-level sections · Vietnamese semi-structured planning doc.

| § | Title | Artifact type | Dependencies | LW compile target |
|---|-------|---------------|--------------|-------------------|
| 1 | Character Seed | `consistency_anchors`, character layer | — | Glossary entity (protagonist) |
| 2 | Công Pháp | `mechanics` (cultivation system) | §1 motivation | Glossary + wiki stub |
| 3 | Đạo Hóa | `mechanics` (corruption tiers) | §1 baseline, §2 method | Wiki + `PlannerState` tiers |
| 4 | Planner Variables | `variables[]` + transition rules | §3 tiers | `planner_state_init` |
| 5 | Arc Overview | `arcs[]`, `events[]`, planner notes | §1–4 | `outline_skeleton`, `PlanningPackage` |
| 6 | Nguyên Tắc Viết | `charter.forbids`, style constraints | §1–5 | `working_memory.charter` |
| 7 | Open Questions | `meta.open_questions[]` | — | Preserved, not auto-filled |

### Golden intent (acceptance test)

| Assertion | Source |
|-----------|--------|
| Arc 2 theme = discovery-not-power | §5 Arc 2 blockquote |
| 4 variables PA/HA/CD/THR with experience-based rules | §4 |
| ≥4 consistency anchors (bình dị, dry humor, …) | §1.3, §1.6 |
| THR not explained early | §4, Event 4/8 planner notes |
| PA not tied to cultivation realm | §4 nguyên tắc |
| Open questions preserved | §7 checklist |

### Negative test variants

1. THR explained in Arc 2 prose → validator fail (`thr_early_explain`)
2. PA delta tied to `realm` field → validator fail (`pa_realm_coupling`)
3. Arc 2 `theme` contains "power fantasy" → validator fail (`arc2_power_framing`)

## POC success metrics (S1–S8)

See [`01_PLANFORGE_ARCHITECTURE.md`](01_PLANFORGE_ARCHITECTURE.md) § POC criteria and `fixtures/story-plan-v1.expectations.yaml`.

## References

- [`2026-06-30-planning-pipeline-architecture.md`](../2026-06-30-planning-pipeline-architecture.md)
- [`services/composition-service/app/routers/plan.py`](../../../services/composition-service/app/routers/plan.py) — `premise` max 4000
- [`contracts/interview/working_memory.schema.json`](../../../contracts/interview/working_memory.schema.json)
- **[`09_PLANFORGE_BLUEPRINT.md`](09_PLANFORGE_BLUEPRINT.md)** — implement handoff (post-POC)
