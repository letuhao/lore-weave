# _spikes — Index

> **Purpose:** Cross-category exploratory design spikes. A "spike" = small end-to-end concrete work that surfaces design questions the abstract discussion didn't. Output is either (a) graduates into a specific category/DF subfolder once scope is clear, or (b) stays here as a design-exercise reference.

**Active:** (empty — no agent currently editing)

---

## Spike list

| ID | Title | Status | Target categories | Commit |
|---|---|---|---|---|
| [SPIKE_01](SPIKE_01_two_sessions_reality_time.md) | Two-Sessions Reality Time (Thần Điêu Đại Hiệp, Yên Vũ Lâu) | DRAFT Session 1 | PL + NPC + PCS; exercises MV12 | pending |

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
