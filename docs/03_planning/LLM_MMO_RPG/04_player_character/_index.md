# 04_player_character — Index

> **Purpose:** Player Character semantics for the LLM MMO RPG track — three-layer identity (User/PC/Session), PC vs NPC rules, creation/lifecycle/social/canon semantics, and forward-links to DF1..DF15 registry. Split from `04_PLAYER_CHARACTER_DESIGN.ARCHIVED.md` on 2026-04-24 via `scripts/chunk_doc.py`. `VERIFY OK`, sha256=`d6a842683a7530e389886a72455e742745775cd3b0420770f2649da237a63d1f`, 18 777 bytes, 11 chunks.

**Active:** (empty — no agent currently editing)

---

## Chunk map (source order)

| # | File | Former section | Lines | Owned IDs |
|---:|---|---|---:|---|
| 00 | [00_preamble.md](00_preamble.md) | H1 + intro | 8 | — |
| 01 | [01_identity_model.md](01_identity_model.md) | §1 Three-layer identity (User/PC/Session) | 27 | Identity layering contract |
| 02 | [02_pc_vs_npc.md](02_pc_vs_npc.md) | §2 PC vs NPC rules | 14 | PC/NPC distinction rules |
| 03 | [03_creation.md](03_creation.md) | §3 Creation | 36 | PC-A1..PC-A3 |
| 04 | [04_lifecycle.md](04_lifecycle.md) | §4 Lifecycle | 59 | PC-B1..PC-B3 |
| 05 | [05_identity_and_agency.md](05_identity_and_agency.md) | §5 Identity & Agency | 43 | PC-C1..PC-C3 |
| 06 | [06_social_sessions.md](06_social_sessions.md) | §6 Social — Sessions, not Parties | 28 | PC-D1..PC-D3 |
| 07 | [07_canon_interaction.md](07_canon_interaction.md) | §7 Canon interaction (DF-forward) | 14 | PC-E1..PC-E3 (deferred via DF3/DF4) |
| 08 | [08_data_model.md](08_data_model.md) | §8 Data model adjustments | 29 | PCS-* schema slots |
| 09 | [09_deferred_big_features.md](09_deferred_big_features.md) | §9 Deferred big features (forward links) | 75 | DF1..DF8 registration (DF9+ added post-04; canonical registry is `../decisions/deferred_DF01_DF15.md`) |
| 10 | [10_decisions_and_refs.md](10_decisions_and_refs.md) | §10 Decisions status + §11 References | 36 | — |

**Totals:** 11 chunks · 18 777 bytes · 369 lines. All chunks far under 500-line soft cap.

---

## Exported stable IDs (authoritative owner = this subfolder)

- **PC-A1..PC-A3** — creation (chunk 03)
- **PC-B1..PC-B3** — lifecycle / death / offline (chunk 04)
- **PC-C1..PC-C3** — slots / personality / stats (chunk 05; PC-C3 concrete schema in DF7)
- **PC-D1..PC-D3** — social / PvP / scope (chunk 06)
- **PC-E1..PC-E3** — canon interaction (chunk 07; all deferred via DF3/DF4)
- **Identity model** — `User` account layer · `PC` persona layer · `Session` embodiment layer (chunk 01)

**Cross-references (not owned here):**
- Storage layer (NPC aggregate split backing PC-B1 death events) → `../02_storage/R08_npc_memory_split.md`
- DF registry (DF1..DF15) → `../decisions/deferred_DF01_DF15.md`
- Decision log rows → `../decisions/locked_decisions.md`

---

## How to work here

1. Claim the subfolder by setting the **Active:** line above with your agent name + ISO UTC timestamp + scope.
2. **Changing a PC-* decision:** edit the row in the owning chunk, and append the change to `../decisions/locked_decisions.md` (supersede-by-ID, never renumber) in the same commit.
3. **Adding a new PC-* decision:** use the next free number in the relevant letter namespace (PC-A4, PC-B4, etc.).
4. **Graduating a DF to implementation:** the DF design doc goes in `docs/03_planning/10X_*.md` (per ORGANIZATION.md migration plan), not here. Update §9 forward-link with the new doc path.
5. Clear the **Active:** line when you finish.

For the full rules see [`../AGENT_GUIDE.md`](../AGENT_GUIDE.md).

---

## Regenerate from archive

```bash
cd d:/Works/source/lore-weave-game
python scripts/chunk_doc.py split docs/03_planning/LLM_MMO_RPG/04_player_character/chunk_rules.json --force
python scripts/chunk_doc.py verify docs/03_planning/LLM_MMO_RPG/04_player_character/chunk_rules.json
```
