# LLM MMO RPG — Extension Design Track (Phase 6+)

> **Status:** Extension design track — **core long-term direction** (Phase 6+ on root roadmap)
> **Created:** 2026-04-23
> **Blocks:** Nothing. Phase 1–5 novel-platform work continues unaffected.
> **Gated on:** V1 novel-platform maturity + remaining `OPEN` problems in `01_OPEN_PROBLEMS.md` (A4 retrieval quality, D1 cost/user-hour, E3 IP ownership).

---

## Why this folder exists

LoreWeave's long-term direction extends from **writing novels** to **playing inside the worlds you write**: a text-based MMO RPG where NPCs, narrator, and world events are driven by LLMs and grounded in the LoreWeave knowledge graph + glossary + book canon. This is the extension referenced as **Phase 6+** in the root [README](../../../README.md).

The novel platform remains the MVP; this track is a committed extension that reuses the same substrate (glossary, knowledge graph, book canon), not a replacement.

This folder exists to:

1. **Hold the extension design** — vision, architecture, multiverse model, PC semantics, storage engineering, open problems, decisions
2. **Track the open problems** that must be solved (or consciously accepted) before implementation begins
3. **Stage the commitment** — the design is locked; implementation is gated on V1 novel-platform maturity and prototype-level cost/retrieval data
4. **Keep the conversation resumable** — any future session can pick up here

## What this folder is NOT

- Not an implementation-ready design doc — each deferred big feature (DF1–DF13) graduates to its own `10X_*.md` when work begins
- Not part of active Phase 1–5 implementation — status on root roadmap is **Design track**, not In Progress
- Not a dependency for any in-flight module
- Not a scheduled milestone — "Phase 6+" means "after V1 novel platform is stable", not a calendar date

## Contents

| File | Purpose |
|---|---|
| `00_VISION.md` | The vision — four shapes of role-play, why Shape D (shared persistent world) is the dream, what LoreWeave uniquely brings, and a staged path that de-risks it |
| `01_OPEN_PROBLEMS.md` | Honest list of problems that must be solved before implementation is credible. Categorized by difficulty and type. Includes multiverse-specific risks (§M). |
| [`02_storage/`](02_storage/) | Storage engineering — full event sourcing + DB-per-reality. **Split into 36 chunks on 2026-04-24**; start at [`02_storage/_index.md`](02_storage/_index.md). Monolith archived at `02_STORAGE_ARCHITECTURE.ARCHIVED.md` until external refs migrated. |
| `03_MULTIVERSE_MODEL.md` | Conceptual foundation — peer realities (no privileged root), snapshot fork, four-layer canon model. Sits above 02 and reframes several 01 problems. |
| `04_PLAYER_CHARACTER_DESIGN.md` | PC semantics — identity layering (User/PC/Session), PC vs NPC rules, creation/lifecycle/social/canon decisions. Registers DF1–DF8 deferred big features. |
| `05_LLM_SAFETY_LAYER.md` | Cross-cutting LLM I/O discipline — 3-intent classifier, command dispatch, World Oracle (determinism), 5-layer injection defense. Resolves A3/A5/A6 from 01. Implementation contract for `roleplay-service` + `world-service`. |
| `FEATURE_CATALOG.md` | **Bird's-eye catalogue of features** across 12 categories with stable IDs. Cross-references every numbered design doc. V1/V2/V3/V4 scope rollup. |
| [`decisions/`](decisions/) | Tracking for all pending user decisions + registry of DF1–DF15 deferred big features (DF12 withdrawn). **Split into 6 chunks on 2026-04-24**; start at [`decisions/_index.md`](decisions/_index.md). Monolith archived at `OPEN_DECISIONS.ARCHIVED.md` until external refs migrated. |
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
7. [`02_storage/`](02_storage/) — engineering detail. Start at [`_index.md`](02_storage/_index.md); R1–R13 are in `R01_*.md`..`R13_*.md`.
8. `04_PLAYER_CHARACTER_DESIGN.md` — PC semantics + deferred big features registry
9. `05_LLM_SAFETY_LAYER.md` — cross-cutting LLM I/O discipline (A3/A5/A6 resolution)
10. [`decisions/`](decisions/) — every decision locked or pending + DF1–DF15 registry. Start at [`_index.md`](decisions/_index.md).

## Status checkpoint

Before any implementation decision, review `01_OPEN_PROBLEMS.md` and answer:

- How many problems marked `OPEN` are blockers (would make the product non-viable)?
- How many `OPEN` problems have no known approach in the public research?
- What is the smallest credible slice (V1 solo RP, coop scene, full MMO) that avoids the hardest unsolved problems?

If the answers don't fit on a napkin, the project is not ready.
