# 01_problems — Index

> **Purpose:** Honest list of problems that must be solved (or consciously accepted) before the LLM MMO RPG track is implementation-ready. Organized by category with status tracking. Split from `01_OPEN_PROBLEMS.ARCHIVED.md` on 2026-04-24 via `scripts/chunk_doc.py`. Every chunk is a verbatim byte-range of the archived monolith; `chunk_rules.json` + `chunk_doc.py verify` prove losslessness (`VERIFY OK`, sha256=`7d6a8be1b376ea48f741371694c6e33114a936f6c181a734807a2b7d6feeade3`, 46 518 bytes, 10 chunks).

**Active:** (empty — no agent currently editing)

---

## Chunk map (source order)

| # | File | Category | Lines | Key IDs | Notable statuses |
|---:|---|---|---:|---|---|
| 00 | [00_preamble.md](00_preamble.md) | H1 + intro + status legend | 24 | — | — |
| 01 | [A_llm_reasoning.md](A_llm_reasoning.md) | A — LLM reasoning & grounding | 102 | A1..A6 | A1 PARTIAL · A4 OPEN (external blocker) · A3/A5/A6 PARTIAL via 05 safety layer |
| 02 | [B_distributed_systems.md](B_distributed_systems.md) | B — Distributed systems | 66 | B1..B5 | Mostly PARTIAL; all locked post R1..R13 storage work |
| 03 | [C_product_ux.md](C_product_ux.md) | C — Product / UX | 80 | C1..C6 | C2 ACCEPTED (research frontier) |
| 04 | [D_economics.md](D_economics.md) | D — Economics | 44 | D1..D3 | D1 OPEN (external — V1 prototype cost data) · D3 ACCEPTED |
| 05 | [E_moderation_safety_legal.md](E_moderation_safety_legal.md) | E — Moderation, safety, legal | 31 | E1..E3 | E3 OPEN (external — legal review) |
| 06 | [F_content_design.md](F_content_design.md) | F — Content design | 57 | F1..F5 | F2 ACCEPTED (AI GM research frontier) · F4 ACCEPTED (minimal RPG mechanics) |
| 07 | [G_testing_ops.md](G_testing_ops.md) | G — Testing & operations | 55 | G1..G3 | All PARTIAL; designs in `docs/05_qa/LLM_MMO_TESTING_STRATEGY.md` |
| 08 | [M_multiverse_specific.md](M_multiverse_specific.md) | M — Multiverse-model-specific risks | 77 | M1..M7 | M6 KNOWN; M1/M3/M4/M7 PARTIAL (resolutions in `../03_multiverse/06_M_C_resolutions.md`); M2/M5 MITIGATED |
| 09 | [99_status_and_readiness.md](99_status_and_readiness.md) | Status summary + "What ready to implement would look like" | 67 | — | Aggregate counts (last snapshot: ~2 OPEN · 26 PARTIAL · 4 ACCEPTED · 5 KNOWN) |

**Totals:** 10 chunks · 46 518 bytes · 603 lines.

---

## Exported stable IDs (authoritative owner = this subfolder)

Each category file owns its letter namespace: `A1..A6`, `B1..B5`, `C1..C6`, `D1..D3`, `E1..E3`, `F1..F5`, `G1..G3`, `M1..M7`.

**Status vocabulary (shared with AGENT_GUIDE §4):**
`OPEN` · `PARTIAL` · `MITIGATED` · `SOLVED` · `ACCEPTED` · `DEFERRED` · `KNOWN` · `WITHDRAWN`.

**Status distribution snapshot (2026-04-24):**
- **OPEN (3, all external-dependency):** A4 (retrieval quality), D1 (LLM cost), E3 (IP ownership legal)
- **ACCEPTED (4):** C2 (narrative pacing) · D3 (self-hosted vs platform) · F2 (AI GM) · F4 (progression)
- **KNOWN (~5):** tracked but not actively worked
- **PARTIAL (~26):** designed, pending V1 prototype data for final lock

Running counts live in `99_status_and_readiness.md`. Always update counts when changing a row status.

**Cross-references (not owned here, but frequently linked):**
- Storage resolutions → `../02_storage/R01..R13_*.md` + `C01..C05_*.md` + `HMP_followups.md` + `S01..S13_*.md` + `SR01..SR05_*.md`
- Multiverse resolutions for M1/M3/M4/M7 + C1 → `../03_multiverse/06_M_C_resolutions.md`
- Safety-layer resolutions for A3/A5/A6 → `../05_LLM_SAFETY_LAYER.md` (migration pending)
- Testing resolutions for G1/G2/G3 → `../../05_qa/LLM_MMO_TESTING_STRATEGY.md`
- Decision log rows → `../decisions/locked_decisions.md`

---

## Pending splits / follow-ups

No chunks over the 500-line soft cap. Largest is `A_llm_reasoning.md` at 102 lines.

Planned future sub-categories (per ORGANIZATION.md) that don't exist in source yet:
- **N — Surfaced during build** — empty category; create `N_surfaced_during_build.md` when the first build-time problem is recorded.

---

## How to work here

1. Claim the subfolder by setting the **Active:** line above with your agent name + ISO UTC timestamp + scope.
2. **Changing a problem's status** (`OPEN → PARTIAL`, `PARTIAL → MITIGATED`, etc.): edit the row in the relevant category file, and update the count in `99_status_and_readiness.md` in the **same commit**.
3. **Adding a new problem:** append to the relevant category with the next free ID in that namespace (e.g., `A7`, `B6`). Cross-link to where the design lives (or says "no design yet").
4. **Moving a problem fully to SOLVED:** keep the row (append-only history) — change status, add brief note pointing to the resolution. Do not delete rows.
5. **Adding a new category:** create a new file named after the letter, update `chunk_rules.json` with a new boundary, re-run split + verify, update this index.
6. Clear the **Active:** line when you finish.

For the full rules see [`../AGENT_GUIDE.md`](../AGENT_GUIDE.md).

---

## Regenerate from archive

If chunks are accidentally corrupted or deleted:

```bash
cd d:/Works/source/lore-weave-game
python scripts/chunk_doc.py split docs/03_planning/LLM_MMO_RPG/01_problems/chunk_rules.json --force
```

Verify without rewriting:

```bash
python scripts/chunk_doc.py verify docs/03_planning/LLM_MMO_RPG/01_problems/chunk_rules.json
```
