# LLM MMO RPG — Exploratory Planning Folder

> **Status:** Exploratory — **NOT approved for implementation**
> **Created:** 2026-04-23
> **Blocks:** Nothing. Phase 1–5 work continues unaffected.
> **Gated on:** Resolving the problems listed in `01_OPEN_PROBLEMS.md`.

---

## Why this folder exists

LoreWeave has a long-term product direction worth preserving but not worth acting on yet: a **text-based MMO RPG** where NPCs, narrator, and world events are driven by LLMs and grounded in the LoreWeave knowledge graph + glossary + book canon.

This folder exists to:

1. **Preserve the vision** in a way that stays honest about how hard it is
2. **Track the open problems** that must be solved (or consciously accepted as unsolved) before any code is written
3. **Prevent premature commitment** — the ideas don't become tickets until the problems are addressed
4. **Keep the conversation resumable** — any future session can pick up here

## What this folder is NOT

- Not a design doc to implement from
- Not on the roadmap (`09_ROADMAP_OVERVIEW.md`)
- Not a dependency for any in-flight module
- Not a commitment to build anything

## Contents

| File | Purpose |
|---|---|
| `00_VISION.md` | The vision — four shapes of role-play, why Shape D (shared persistent world) is the dream, what LoreWeave uniquely brings, and a staged path that de-risks it |
| `01_OPEN_PROBLEMS.md` | Honest list of problems that must be solved before implementation is credible. Categorized by difficulty and type. Includes multiverse-specific risks (§M). |
| `02_STORAGE_ARCHITECTURE.md` | Storage engineering — full event sourcing + DB-per-reality. Schema, concurrency, capacity, archive. |
| `03_MULTIVERSE_MODEL.md` | Conceptual foundation — peer realities (no privileged root), snapshot fork, four-layer canon model. Sits above 02 and reframes several 01 problems. |
| `04_PLAYER_CHARACTER_DESIGN.md` | PC semantics — identity layering (User/PC/Session), PC vs NPC rules, creation/lifecycle/social/canon decisions. Registers DF1–DF8 deferred big features. |
| `FEATURE_CATALOG.md` | **Bird's-eye catalogue of all 120 features** across 12 categories with stable IDs. Cross-references every numbered design doc. V1/V2/V3/V4 scope rollup. |
| `OPEN_DECISIONS.md` | Tracking file for all pending user decisions + registry of DF1–DF13 deferred big features (DF12 withdrawn). Defaults applied where noted; user can confirm or override at any time. |
| `SESSION_HANDOFF.md` | **Resumption doc** — current state summary, decision history, natural next steps. Read this first when resuming. Does not conflict with main `docs/sessions/SESSION_PATCH.md`. |

## Related planning

- `../References/SillyTavern_Feature_Comparison.md` — prior-art survey that seeded this direction
- `../98_CHAT_SERVICE_DESIGN.md` — sibling design (Cursor-style AI chat; different shape, lower risk)
- `../103_PLATFORM_MODE_PLAN.md` — tier/billing foundation this would eventually depend on
- `../101_DATA_RE_ENGINEERING_PLAN.md` + `KNOWLEDGE_SERVICE_ARCHITECTURE.md` — knowledge graph this would read from

## How to use this folder

- **New ideas in this space** → add to `00_VISION.md` or create `0X_*.md` beside it
- **New problem discovered** → add a numbered entry to `01_OPEN_PROBLEMS.md` under the right category
- **A problem gets solved or has a credible approach** → update its status in `01_OPEN_PROBLEMS.md` (`OPEN` → `PARTIAL` → `SOLVED`)
- **New decision raised for user** → add to `OPEN_DECISIONS.md` with default (if any); record as `Locked` once user confirms
- **Decision to proceed with implementation** → new design doc `docs/03_planning/10X_*.md` with governance sign-off; this folder becomes the ancestor reference

## Reading order for someone picking this up cold

1. `README.md` (this file)
2. **`SESSION_HANDOFF.md`** — current state, decision history, next steps (read FIRST when resuming)
3. `00_VISION.md` — what is being dreamed about
4. `FEATURE_CATALOG.md` — **menu of what the product includes** (skim the status summary first)
5. `01_OPEN_PROBLEMS.md` — why it is hard
6. `03_MULTIVERSE_MODEL.md` — conceptual foundation (read before 02)
7. `02_STORAGE_ARCHITECTURE.md` — engineering detail (§12A–§12L cover all R1–R13)
8. `04_PLAYER_CHARACTER_DESIGN.md` — PC semantics + deferred big features registry
9. `OPEN_DECISIONS.md` — every decision locked or pending + DF1–DF13 registry

## Status checkpoint

Before any implementation decision, review `01_OPEN_PROBLEMS.md` and answer:

- How many problems marked `OPEN` are blockers (would make the product non-viable)?
- How many `OPEN` problems have no known approach in the public research?
- What is the smallest credible slice (V1 solo RP, coop scene, full MMO) that avoids the hardest unsolved problems?

If the answers don't fit on a napkin, the project is not ready.
