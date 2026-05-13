# _spikes — Index

> **Purpose:** Cross-category exploratory design spikes. A "spike" = small end-to-end concrete work that surfaces design questions the abstract discussion didn't. Output is either (a) graduates into a specific category/DF subfolder once scope is clear, or (b) stays here as a design-exercise reference.

**Active:** (empty — no agent currently editing)

---

## Spike list

| ID | Title | Status | Target categories | Commit |
|---|---|---|---|---|
| [SPIKE_01](SPIKE_01_two_sessions_reality_time.md) | Two-Sessions Reality Time (Thần Điêu Đại Hiệp, Yên Vũ Lâu) | DRAFT Session 1 | PL + NPC + PCS; exercises MV12 | pending |
| [SPIKE_02](SPIKE_02_reference_games_gap_analysis.md) | Reference Games Gap Analysis (RPG/strategy/sim/adventure backlog) | DRAFT 2026-04-27 | cross-cat — A..N domains; informs V1+30d / V2 / V3 / V4+ feature triage | pending |
| [SPIKE_03](SPIKE_03_tilemap_world_view.md) | Tilemap World View (HOMM3-style camera-rendered map) | **GRADUATED 2026-05-13 → [TMP_001](../00_tilemap/TMP_001_tilemap_foundation.md)** (DRAFT). Multi-game genre prior art surveyed (HoMM3, Wesnoth, Civ V/VI, Dwarf Fortress, Caves of Qud, VCMI as one open-source reference); algorithm foundations cited per academic literature (Fruchterman & Reingold 1991, Penrose 1974, Kahn 1962, Tarjan 1976, Dijkstra 1965, Hart et al. 1968, Gamma et al. 1994). Full design surface in `features/00_tilemap/` (TMP_001..TMP_008 + catalog row + boundary lock). | TMP_* namespace claimed; sibling of MAP/PF/CSC; demo PoC retained at `_ui_drafts/MAP_GUI_v1.html` and SPIKE_03 §3-§5 | pending |

---

## When to create a spike

- A design question is unclear in the abstract; one concrete example would force the answer
- The question spans multiple categories and you're not sure which category owns it
- You need a throwaway / low-commitment investigation before designing the real feature

## When to NOT create a spike

- Scope is clear → go straight to the category / DF subfolder
- Work is infra-only → kernel (and kernel-design phase is closed anyway)
- Work is tiny → inline in a category feature doc

## Graduation path

Each spike ends with **observations** that feed:
- Category-level features → created as files in `02_*` through `12_*` subfolders
- Big-feature design → created as sub-subfolder in `DF/`
- Kernel extensions (on-demand only) → minimal edit in existing `02_storage/§12*` chunk + foundation cascade

Spikes stay in this folder as permanent reference; they are not deleted after graduation.
