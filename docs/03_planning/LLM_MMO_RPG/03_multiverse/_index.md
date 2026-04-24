# 03_multiverse — Index

> **Purpose:** Conceptual foundation for the LLM MMO RPG track — peer realities (no privileged root), snapshot fork semantics, 4-layer canon model, M1/M3/M4/M7 + C1 resolutions (§9.x), and multiverse-specific risks (M1..M7). Split from `03_MULTIVERSE_MODEL.ARCHIVED.md` on 2026-04-24 via `scripts/chunk_doc.py`. Every chunk is a verbatim byte-range of the archived monolith; `chunk_rules.json` + `chunk_doc.py verify` prove losslessness (`VERIFY OK`, sha256=`def463d64d3ab5cc6b38c8fd37226428a10a11230f674b54ce1dfb5e94864c3e`, 56 329 bytes, 10 chunks).

**Active:** (empty — no agent currently editing)

---

## Chunk map (source order)

| # | File | Former section | Lines | Owned stable IDs | Status |
|---:|---|---|---:|---|---|
| 00 | [00_overview_philosophy.md](00_overview_philosophy.md) | §1 Philosophy + §2 What a reality is | 52 | — | LOCKED |
| 01 | [01_four_layer_canon.md](01_four_layer_canon.md) | §3 Four-layer canon model | 125 | L1/L2/L3/L4 definitions · WA-4 category heuristics · canonization model | LOCKED |
| 02 | [02_lifecycle_and_seeding.md](02_lifecycle_and_seeding.md) | §4 Reality lifecycle + §5 Seeding modes | 67 | `active/frozen/archived/soft_deleted/dropped` states · §5.1..§5.3 seeding | LOCKED |
| 03 | [03_fork_and_cascading.md](03_fork_and_cascading.md) | §6 Snapshot fork semantics + §7 Cascading read | 58 | LMV-Fork · read-through exception | LOCKED |
| 04 | [04_schema_additions.md](04_schema_additions.md) | §8 Schema additions vs 02 | 102 | §8.1 events `reality_id` · §8.2 projections · §8.3 reality registry · §8.4 glossary canon lock | LOCKED |
| 05 | [05_product_ux_basics.md](05_product_ux_basics.md) | §9.1 Reality discovery + §9.2..§9.5 (fork mechanic, no default canonicality, world-travel-deferred, multi-lingual canon) | 129 | M1-D1..D7 · MV5 deferred notes | LOCKED |
| 06 | [06_M_C_resolutions.md](06_M_C_resolutions.md) | §9.6 M7 progressive disclosure · §9.7 M3 canonization safeguards · §9.8 M4 canon update propagation · §9.9 C1 severance / orphan worlds | 297 | M7-D1..D5 · M3-D1..D8 · M4-D1..D6 · C1-OW-1..5 · DF14 hooks | LOCKED |
| 07 | [07_resolves_from_01.md](07_resolves_from_01.md) | §10 What this resolves from 01_OPEN_PROBLEMS | 12 | — (table of 01 problems → multiverse resolution) | LOCKED |
| 08 | [08_multiverse_risks.md](08_multiverse_risks.md) | §11 Risks specific to multiverse (M1..M7) | 32 | M1..M7 risk rows (narrative status summaries; resolution details live in chunk 06 or `02_storage/` per risk) | LOCKED |
| 09 | [09_config_and_refs.md](09_config_and_refs.md) | §12 Configuration & decisions status + §13 References | 82 | §12.1 tunables · §12.2 fork policy · §12.3 fork depth · §12.4 decisions status | LOCKED |

**Totals:** 10 chunks · 56 329 bytes · 956 lines.

---

## Exported stable IDs (authoritative owner = this subfolder)

**Conceptual IDs:**
- **Canon layers:** L1 AXIOM · L2 SEEDED · L3 LOCAL · L4 FLEX (defined in chunk 01; prompt-markup consumers live in `02_storage/S09_prompt_assembly.md`)
- **Lifecycle states:** `active` · `pending_close` · `frozen` · `archived` · `archived_verified` · `soft_deleted` · `dropped` (lifecycle authoring in chunk 02; state-machine enforcement in `02_storage/R09_safe_reality_closure.md`)

**Locked decisions owned here** (mirrored in `../decisions/locked_decisions.md`):
- WA4-D1..D5 (category heuristics, chunk 01)
- LMV-Fork · LMV-Name (chunks 03 / 00)
- M1-D1..D7 (reality discovery, chunk 05)
- M7-D1..D5 (progressive disclosure, chunk 06)
- M3-D1..D8 (canonization safeguards, chunk 06)
- M4-D1..D6 (canon update propagation, chunk 06)
- C1-OW-1..5 (ancestry severance, chunk 06)
- MV1..MV11 — primitives scattered across chunks 02/03/09

**Not owned here (cross-references only):**
- R9 closure protocol → `02_storage/R09_safe_reality_closure.md`
- C1 severance storage layer → `02_storage/C01_severance_orphan_worlds.md` + §12M
- DF14 Vanish Reality Mystery System → `../decisions/deferred_DF01_DF15.md`

---

## Pending splits / follow-ups

No chunks over the 500-line soft cap. Largest is `06_M_C_resolutions.md` at 297 lines (the four main resolutions grouped — M7 + M3 + M4 + C1).

| File | Lines | Note |
|---|---:|---|
| `06_M_C_resolutions.md` | 297 | If one resolution grows substantially (e.g. M3-D9+ / M4 force-propagate UX expands), split by sub-section boundary `^### 9\.7 `, `^### 9\.8 `, `^### 9\.9 `. |

---

## How to work here

1. Claim the subfolder by setting the **Active:** line above with your agent name + ISO UTC timestamp + scope.
2. **Adding a new M/C resolution:** either append §9.X to chunk 06 (if it fits thematically), or create a new chunk (e.g. `10_MX_new_resolution.md`) + update `chunk_rules.json` with a new boundary + re-run `split --force` + verify.
3. **Editing a conceptual layer definition** (L1..L4, lifecycle states): edit chunk 01 (canon) or chunk 02 (lifecycle). These are downstream invariants; any change must ripple to `02_storage/` + `decisions/locked_decisions.md` in the same commit.
4. **Never renumber** §-section IDs — they are cross-referenced externally. Retired sections get a strikethrough note, not renumber.
5. Clear the **Active:** line when you finish.

For the full rules see [`../AGENT_GUIDE.md`](../AGENT_GUIDE.md).

---

## Regenerate from archive

If chunks are accidentally corrupted or deleted:

```bash
cd d:/Works/source/lore-weave-game
python scripts/chunk_doc.py split docs/03_planning/LLM_MMO_RPG/03_multiverse/chunk_rules.json --force
```

Verify without rewriting:

```bash
python scripts/chunk_doc.py verify docs/03_planning/LLM_MMO_RPG/03_multiverse/chunk_rules.json
```
