# Lore-Enrichment — RAID Workflow (per-task pointer)

This task uses the canonical RAID spec without amendment:

➡ **[../../raid/RAID_WORKFLOW.md](../../raid/RAID_WORKFLOW.md)** (RAID v1.4 spec — ported in commit `71e6a93b`).

## Task-specific parameters
- **task_id:** `lore-enrichment` · **slug:** `2026-05-30-lore-enrichment`
- **Cycles:** C0–C18 (19 total; incl. platform deferrals K14/D4-03) — see [CYCLE_DECOMPOSITION.md](CYCLE_DECOMPOSITION.md).
- **bootstrap_cycle:** C0 (service skeleton; smoke `/health` gates C0→C1).
- **Quota profile:** [../../../contracts/raid/quota-profile.yaml](../../../contracts/raid/quota-profile.yaml).
- **Locked constraints:** [OPEN_QUESTIONS_LOCKED.md](OPEN_QUESTIONS_LOCKED.md) · pre-flight [PRE_FLIGHT_CHECKLIST.md](PRE_FLIGHT_CHECKLIST.md).

## Task-specific notes
- Cross-service cycles (C1, C4, C5, C10, C13, C14) MUST carry a live-smoke evidence token at VERIFY (real call against a stacked-up knowledge-service/glossary/book-service), per CLAUDE.md.
- Platform cycles C4 (K14 event pipeline) + C5 (D4-03 wiki-from-KG) edit glossary/knowledge-service — additive/backward-compatible only; conflict-checked safe (foundation touches 0 files there).
- Isolation: never modify the mmo-rpg foundation work (`world-service`, `game-server`, etc.) or other agents' files.
- Cost: P1 techniques only until the eval gate (C15); fabrication/re-cook gated.
- **Cost posture (locked): conservative / batched** — DPS 2–3, run cycles in batches, pause-on-quota (Max subscription), stop for human review between batches. First batch target = C14 (demo).
- **Output language = Chinese** (source-faithful); eval operates on Chinese.
