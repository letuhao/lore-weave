# catalog — Index

> **Purpose:** Bird's-eye feature catalog for the LLM MMO RPG track — 397 features across 12 categories with stable IDs, plus V1/V2/V3/V4 scope rollup. Split from `FEATURE_CATALOG.ARCHIVED.md` on 2026-04-24 via `scripts/chunk_doc.py`. Every chunk is a verbatim byte-range of the archived monolith; `chunk_rules.json` + `chunk_doc.py verify` prove losslessness (`VERIFY OK`, sha256=`74722e07f2bc13d1f764fea452feb8810c5ad029d4a78c2aedc325a3787108c8`, 77 227 bytes, 14 chunks).

**Active:** (empty — no agent currently editing)

---

## Chunk map (source order)

| # | File | Category / Section | Lines | Owned stable IDs | Feature count |
|---:|---|---|---:|---|---:|
| 00 | [00_preamble.md](00_preamble.md) | H1 + "How to use" + Category map | 54 | — | — |
| 01 | [cat_01_IF_infrastructure.md](cat_01_IF_infrastructure.md) | IF — Infrastructure | 289 | IF-1..IF-39 (+ IF-*-sub; IF-39..IF-39j added 2026-04-24 per SR6) | 133 |
| 02 | [cat_02_WA_world_authoring.md](cat_02_WA_world_authoring.md) | WA — World Authoring | 12 | WA-1..WA-4 + WA4-D1..D5 | ~10 |
| 03 | [cat_03_PO_player_onboarding.md](cat_03_PO_player_onboarding.md) | PO — Player Onboarding | 21 | PO-1..PO-N | ~15 |
| 04 | [cat_04_PL_play_loop.md](cat_04_PL_play_loop.md) | PL — Play Loop (core runtime) | 39 | PL-1..PL-N | ~30 |
| 05 | [cat_05_NPC_systems.md](cat_05_NPC_systems.md) | NPC — NPC Systems | 24 | NPC-1..NPC-N | ~18 |
| 06 | [cat_06_PCS_pc_systems.md](cat_06_PCS_pc_systems.md) | PCS — PC Systems | 15 | PCS-1..PCS-N | ~10 |
| 07 | [cat_07_SOC_social.md](cat_07_SOC_social.md) | SOC — Social | 15 | SOC-1..SOC-7 (SOC-6/SOC-7 out-of-scope) | ~7 |
| 08 | [cat_08_NAR_narrative_canon.md](cat_08_NAR_narrative_canon.md) | NAR — Narrative / Canon | 22 | NAR-1..NAR-N | ~15 |
| 09 | [cat_09_EM_emergent.md](cat_09_EM_emergent.md) | EM — Emergent / Advanced (fork, travel, reality lifecycle) | 32 | EM-1..EM-N | ~25 |
| 10 | [cat_10_PLT_platform_business.md](cat_10_PLT_platform_business.md) | PLT — Platform / Business | 16 | PLT-1..PLT-N | ~12 |
| 11 | [cat_11_CC_cross_cutting.md](cat_11_CC_cross_cutting.md) | CC — Cross-cutting | 26 | CC-1..CC-6 (CC-6 + CC-6-D1..D7) | ~20 |
| 12 | [cat_12_DL_daily_life.md](cat_12_DL_daily_life.md) | DL — Daily Life (DF1 umbrella) | 18 | DL-1..DL-N | ~10 |
| 99 | [99_scope_and_refs.md](99_scope_and_refs.md) | Status summary · V1/V2/V3/V4 scopes · Relationships · References | 97 | — | — |

**Totals:** 14 chunks · 669 lines from original split + IF-39..IF-39j appended 2026-04-24 (SR6 resolution) · **408 features** across 12 categories (**301 Designed** · 38 Partial · **64 Deferred** · 3 Open · 2 out-of-scope).

---

## Exported stable IDs (authoritative owner = this subfolder)

Each category file owns the ID namespace named in the chunk map. External docs cite these like "IF-31" (SVID) or "CC-6" (a11y) or "SOC-6" (parties, out-of-scope).

**Umbrella links to related specs (not owned here):**
- DF1..DF15 registry → [`../decisions/deferred_DF01_DF15.md`](../decisions/deferred_DF01_DF15.md)
- Decisions log (including per-feature D-numbers) → [`../decisions/locked_decisions.md`](../decisions/locked_decisions.md)
- Storage implementations (IF-1..IF-38 mostly implemented in §12 sections) → [`../02_storage/_index.md`](../02_storage/_index.md)

---

## Pending splits / follow-ups

| File | Lines | Issue | Proposed action |
|---|---:|---|---|
| `cat_01_IF_infrastructure.md` | 278 | Under soft cap. Largest chunk (IF grew from ~10 features in original to 122 after Security+SRE review added IF-25..IF-38a-j chains). | No split needed today. If future security reviews push past 500 lines, split by sub-batch (auth / network / obs / secrets / schema / etc.) — current subsections include IF-29 prompt, IF-30 severance, IF-31 SVID, IF-32 WebSocket, IF-33 canon, IF-34 SLO, IF-35 incident, IF-36 runbook, IF-37 postmortem, IF-38 deploy. |

No chunk exceeds the 1500-line hard cap. No chunk is over soft cap today.

---

## How to work here

1. Claim the subfolder by setting the **Active:** line above with your agent name + ISO UTC timestamp + scope.
2. **Adding a new feature:** append a new row to the relevant `cat_NN_*.md` file, with a stable ID (next free number in that category's namespace). Cross-link to its design doc (in `02_storage/` or `03_multiverse/` or similar).
3. **Moving feature status (Designed / Partial / Deferred / etc.):** edit the row in place, update the top-of-file status counters, and re-sum the feature total in this index in the same commit.
4. **Never renumber** stable IDs (IF-31 stays IF-31 forever; retired IDs get `~~IF-25~~` strike-through, as happened in S8 when IF-25/IF-26 were renumbered — wait, that was a one-time migration, not a pattern to repeat).
5. Clear the **Active:** line when you finish.

For the full rules see [`../AGENT_GUIDE.md`](../AGENT_GUIDE.md).

---

## Regenerate from archive

If chunks are accidentally corrupted or deleted:

```bash
cd d:/Works/source/lore-weave-game
python scripts/chunk_doc.py split docs/03_planning/LLM_MMO_RPG/catalog/chunk_rules.json --force
```

Verify without rewriting:

```bash
python scripts/chunk_doc.py verify docs/03_planning/LLM_MMO_RPG/catalog/chunk_rules.json
```
