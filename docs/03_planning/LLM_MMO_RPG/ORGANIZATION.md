# LLM_MMO_RPG — Folder Organization

> **Status:** Active layout spec. Read with [AGENT_GUIDE.md](AGENT_GUIDE.md) before editing anything here.
> **Created:** 2026-04-24

---

## 1. Why this layout

Current files grew past practical limits:

| File | Size | Lines |
|---|---:|---:|
| `02_STORAGE_ARCHITECTURE.md` | 476 KB | 10 010 |
| `OPEN_DECISIONS.md` | 175 KB | 619 (wide rows) |
| `SESSION_HANDOFF.md` | 78 KB | 390 (wide rows) |
| `FEATURE_CATALOG.md` | 77 KB | 669 |
| `03_MULTIVERSE_MODEL.md` | 56 KB | 956 |
| `01_OPEN_PROBLEMS.md` | 46 KB | 603 |

Consequences:
- Read tool fails on single files (25k-token limit) — agents operate on fragments and lose cross-context.
- Every edit serializes all work in that file — only one agent at a time.
- Diffs are noisy; drift across cross-refs hard to detect.

**Goal:** split monoliths into topic-scoped files under topic-scoped subfolders so multiple agents can work in parallel with minimal contention, without changing any content or stable IDs.

---

## 2. Target layout

```
LLM_MMO_RPG/
├── README.md                           # Folder index (entry point)
├── ORGANIZATION.md                     # This file
├── AGENT_GUIDE.md                      # Rules for agents working here
├── SESSION_HANDOFF.md                  # Session log (append-only)
│
├── 00_overview/
│   ├── _index.md
│   └── 00_VISION.md
│
├── 01_problems/                        # formerly 01_OPEN_PROBLEMS.md
│   ├── _index.md                       # Status table + links (A1..N*, M1..M7)
│   ├── A_retrieval_and_memory.md
│   ├── B_safety_and_ops.md
│   ├── C_narrative.md
│   ├── D_cost_and_business.md
│   ├── E_legal_and_ip.md
│   ├── F_product_design.md
│   ├── G_testing.md
│   ├── M_multiverse.md
│   └── N_surfaced_during_build.md
│
├── 02_storage/                         # formerly 02_STORAGE_ARCHITECTURE.md
│   ├── _index.md                       # Master TOC (§12A..§12AH)
│   ├── 00_overview_and_schema.md       # §1..§11 foundations
│   ├── R01_event_volume.md             # §12A
│   ├── R02_projection_rebuild.md       # §12B
│   ├── ... (R03..R13)
│   ├── C01_cascade_read.md             # §12M (SA+DE critical)
│   ├── ... (C02..C05 → §12N..§12Q)
│   ├── HMP_followups.md                # §12R (H1..H6 + M-REV-1..6 + P1..P4)
│   ├── S01_reality_creation_rate.md    # §12S part
│   ├── S02_session_scoped_memory.md
│   ├── ... (S03..S13 → §12S..§12AC)
│   ├── SR01_slo_error_budget.md        # §12AD
│   ├── SR02_incident_oncall.md         # §12AE
│   ├── SR03_runbook_library.md         # §12AF
│   ├── SR04_postmortem_process.md      # §12AG
│   └── SR05_deploy_safety.md           # §12AH
│
├── 03_multiverse/                      # formerly 03_MULTIVERSE_MODEL.md
│   ├── _index.md
│   ├── 01_peer_realities.md
│   ├── 02_four_layer_canon.md
│   ├── 03_snapshot_fork.md
│   ├── 04_M1_discovery.md              # §9.1
│   ├── 05_M3_canonization.md           # §9.7
│   ├── 06_M4_propagation.md            # §9.8
│   ├── 07_M7_progressive_disclosure.md # §9.6
│   └── 08_C1_OW_severance.md           # §9.9 (DF14 lore)
│
├── _superseded/04_player_character/                # formerly 04_PLAYER_CHARACTER_DESIGN.md
│   ├── _index.md
│   ├── A_identity.md                   # PC-A1..A3
│   ├── B_creation_lifecycle.md         # PC-B1..B2
│   ├── C_slots_monetization.md         # PC-C1
│   ├── D_social_session.md             # PC-D1..D3
│   ├── E_canon_progression.md          # PC-E1..E3
│   └── DF_registry.md                  # DF1..DF15
│
├── 05_llm_safety/                      # formerly 05_LLM_SAFETY_LAYER.md
│   ├── _index.md
│   ├── 01_intent_classifier.md
│   ├── 02_command_dispatch.md
│   ├── 03_world_oracle.md
│   └── 04_injection_defense.md
│
├── catalog/                            # formerly FEATURE_CATALOG.md
│   ├── _index.md                       # Status summary + category list
│   ├── cat_01_identity.md
│   ├── cat_02_reality_world.md
│   ├── cat_03_session_chat.md
│   ├── cat_04_npc_memory.md
│   ├── cat_05_canon_lore.md
│   ├── cat_06_social_community.md
│   ├── cat_07_progression.md
│   ├── cat_08_admin_ops.md
│   ├── cat_09_safety_policy.md
│   ├── cat_10_cost_billing.md
│   ├── cat_11_observability.md
│   └── cat_12_integration_IF.md
│
└── decisions/                          # formerly OPEN_DECISIONS.md
    ├── _index.md                       # Locked-vs-pending summary + DF registry
    ├── locked_M_batch.md
    ├── locked_A_to_G_batch.md
    ├── locked_C_HMP_batch.md
    ├── locked_S_batch.md               # S1..S13
    ├── locked_SR_batch.md              # SR1..SR5
    ├── pending.md                      # V1-blocking DF4/DF5/DF7 etc.
    └── deferred_DF01_DF15.md
```

---

## 3. Naming conventions

| Rule | Example |
|---|---|
| Lowercase snake_case for topic files | `R01_event_volume.md` |
| `_index.md` = TOC for the subfolder (leading underscore sorts first) | `02_storage/_index.md` |
| Numeric prefix matches the stable risk/section ID | `S09_prompt_assembly.md` |
| Never reuse a retired ID — add `_withdrawn` suffix | `cat_12_withdrawn.md` |
| Cross-refs use the stable ID, not a file path or line number | "see S9-D3 / §12Y" not "see line 4520" |

---

## 4. File size ceiling

- **Soft cap 500 lines.** If your edit would push the file past 500, split on the next heading boundary first.
- **Hard cap 1500 lines.** No topic file in this folder may exceed this.
- `_index.md` files are exempt but should stay under 300 lines (links + tables only).
- The Python chunk tool (next task) enforces these on migration and verifies no data loss.

---

## 5. `_index.md` contract

Every subfolder has exactly one `_index.md` containing:

1. **One-line purpose** of the subfolder.
2. **Active header** — `Active: <agent-name> <ISO timestamp> <scope>` while an agent is editing inside; cleared when done. Empty string means unlocked.
3. **Status table** — one row per topic file: ID · title · status · last-touched date · path.
4. **Exported IDs** — list of stable IDs this subfolder owns, so outside docs can cross-link unambiguously.
5. **Pending splits** — if any file is near the soft cap, note it so the next agent splits before editing.

Indexes are updated **in the same commit** as the topic files they reference.

---

## 6. What is preserved

- **Content is verbatim.** Splitting is lossless — byte-hash or text-reconstruction round-trip verifies.
- **Stable IDs unchanged:** `R*`, `C*`, `HMP`, `S*`, `SR*`, `M*`, `DF*`, `PC-*`, `IF-*`, `WA-*`, `MV*`.
- **Reading order in `README.md`** stays semantically the same, just repointed at subfolders.
- **Governance docs in `docs/02_governance/`** do not move; their references are updated in the migration commit.

---

## 7. Migration order

1. This session — land `ORGANIZATION.md` + `AGENT_GUIDE.md`. No subfolders yet.
2. Next task — write Python chunk tool with post-chunk data-loss verification.
3. Run the tool in this order (largest / most contested first):
   1. `02_STORAGE_ARCHITECTURE.md` → `02_storage/`
   2. `OPEN_DECISIONS.md` → `decisions/`
   3. `FEATURE_CATALOG.md` → `catalog/`
   4. `SESSION_HANDOFF.md` → keep at root but trim old session rows into `SESSION_HANDOFF_ARCHIVE_<date>.md`
   5. `01_OPEN_PROBLEMS.md` → `01_problems/`
   6. `03_MULTIVERSE_MODEL.md` → `03_multiverse/`
   7. `04_*` / `05_*` → their subfolders
4. After each migration: update `README.md` + append a SESSION_HANDOFF row. Old monolith kept as `*.ARCHIVED.md` for one session, then deleted.
5. External refs in `docs/02_governance/*` and `docs/sessions/SESSION_PATCH.md` are updated in the same commit as the split.

## Archive retention

**Status (2026-04-24):** All 7 `*.ARCHIVED.md` files have been removed from the working tree. They remain in git history — recover any archive with:

```bash
git log --follow -- docs/03_planning/LLM_MMO_RPG/<FILE>.ARCHIVED.md
git show <commit>:docs/03_planning/LLM_MMO_RPG/<FILE>.ARCHIVED.md > /tmp/archive.md
```

Per-chunk tamper-evidence is preserved independently of the archive: every chunk's `<!-- CHUNK-META -->` header carries the sha256 of its original byte range. A regenerate-from-chunks helper could be added to `scripts/chunk_doc.py` if re-verification without git access becomes a need; for now, `chunk_doc.py verify` against a regenerated archive from git is the recovery path.
