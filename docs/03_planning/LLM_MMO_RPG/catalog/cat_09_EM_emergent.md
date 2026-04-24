<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: cat_09_EM_emergent.md
byte_range: 59109-62760
sha256: 0bd571a3f59c2ffc42d881a83614bf0acb39c3487df05e172c4872f046c560c2
generated_by: scripts/chunk_doc.py
-->

## EM — Emergent / Advanced (fork, travel, reality lifecycle)

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| EM-1 | Auto-fork on capacity (system-initiated, fresh seed) | ✅ | V1 | IF-3 | [03 §12.2](03_MULTIVERSE_MODEL.md), MV4-a locked |
| EM-2 | User-initiated fork (player creates alternate timeline) | ✅ | V1 | IF-3 | [03 §12.2](03_MULTIVERSE_MODEL.md), MV4-b locked |
| EM-3 | Auto-rebase at depth limit (flatten chain into fresh-seed) | ✅ | V1 | EM-2 | [03 §12.3](03_MULTIVERSE_MODEL.md), MV9 locked N=5 |
| EM-4 | DB subtree split at threshold (50M events or 500 players) | ✅ | V3 | IF-3 | MV8 locked |
| EM-5 | Reality freeze (no writes, reads OK) | ✅ | V2 | IF-11 | MV10 locked 30d |
| EM-6 | Reality archive (drop DB, events to MinIO) | ✅ | V2 | IF-11 | MV11 locked 90d |
| EM-7 | Reality close — safe multi-stage flow | ✅ | V1 | EM-6 | [02 §12I](02_STORAGE_ARCHITECTURE.md) (R9 locked) |
| EM-7a | 6-state close machine (active → pending_close → frozen → archived → archived_verified → soft_deleted → dropped) | ✅ | V1 | EM-7 | [02 §12I.1](02_STORAGE_ARCHITECTURE.md) (R9-L1) |
| EM-7b | Archive verification drill (checksum + sample decode + sample restore + diff) | ✅ | V1 | EM-6 | [02 §12I.3](02_STORAGE_ARCHITECTURE.md) (R9-L2) |
| EM-7c | Double-approval workflow for irreversible drop | ✅ | V1 | PO-1 | [02 §12I.4](02_STORAGE_ARCHITECTURE.md) (R9-L3) |
| EM-7d | 30-day cooling period with owner cancel | ✅ | V1 | EM-7a | [02 §12I.5](02_STORAGE_ARCHITECTURE.md) (R9-L4) |
| EM-7e | Player notification cascade (30/7/1 day) | ✅ | V2 | EM-7a | [02 §12I.6](02_STORAGE_ARCHITECTURE.md) (R9-L5) |
| EM-7f | Soft-delete via DB rename (not drop) + 90d hold | ✅ | V1 | EM-7a | [02 §12I.7](02_STORAGE_ARCHITECTURE.md) (R9-L6) |
| EM-7g | Emergency cancel at any pre-drop state | ✅ | V1 | EM-7a | [02 §12I.8](02_STORAGE_ARCHITECTURE.md) (R9-L7) |
| EM-7h | Full audit log of close state transitions | ✅ | V1 | EM-7a | [02 §12I.9](02_STORAGE_ARCHITECTURE.md) (R9-L8) |
| EM-8 | World travel — cross-reality PC movement | 📦 | V4 | IF-16, many primitives | **DF6 — World Travel** |
| EM-9 | Echo visit (read-only observation of another reality) | 📦 | V4 | IF-3 | DF6 sub-feature |
| EM-10 | Dimensional rift narrative events | 📦 | V4+ | EM-8 | DF6 |
| EM-11 | Reality "pin/protect" (prevent auto-freeze/archive) | 📦 | PLT | EM-5, EM-6 | Discussed but not locked |
| EM-12 | Freeze/archive warning notifications | 📦 | V2 | EM-5 | Discussed but not locked |
| EM-13 | Reality ancestry severance — orphan worlds (C1 resolution) | ✅ | V1 | EM-7 | [02 §12M](02_STORAGE_ARCHITECTURE.md) · [03 §9.9](03_MULTIVERSE_MODEL.md); C1-OW-1..5 locked 2026-04-24 |
| EM-13a | Auto-severance at ancestor `frozen` transition | ✅ | V1 | EM-13 | [02 §12M.2](02_STORAGE_ARCHITECTURE.md) (C1-OW-1) |
| EM-13b | Baseline snapshot + cascade-read severance logic | ✅ | V1 | EM-13 | [02 §12M.4](02_STORAGE_ARCHITECTURE.md) |
| EM-13c | `reality.ancestry_severed` in-world narrative event | ✅ | V1 | EM-13, IF-5c | [02 §12M.6](02_STORAGE_ARCHITECTURE.md) (C1-OW-3) |
| EM-13d | `ancestry_fragment_trail` lore display | ✅ | V2 | EM-13 | [02 §12M.7](02_STORAGE_ARCHITECTURE.md) (C1-OW-5) |
| EM-13e | Player notification cascade pre-severance | ✅ | V2 | EM-13, CC-1 | [02 §12M.5](02_STORAGE_ARCHITECTURE.md) |
| EM-14 | Vanish Reality Mystery System — pre-severance breadcrumbs for player discovery | 📦 | V3+ | EM-13 | **DF14** — [03 §9.9.6](03_MULTIVERSE_MODEL.md); short track registered 2026-04-24 |

