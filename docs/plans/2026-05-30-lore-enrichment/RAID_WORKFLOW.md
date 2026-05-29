# Lore-Enrichment — RAID Workflow (per-task pointer)

This task uses the canonical RAID spec without amendment:

➡ **[../../raid/RAID_WORKFLOW.md](../../raid/RAID_WORKFLOW.md)** (RAID v1.4 spec — ported in commit `71e6a93b`).

## Task-specific parameters
- **task_id:** `lore-enrichment` · **slug:** `2026-05-30-lore-enrichment`
- **Cycles:** C0–C15 (16 total) — see [CYCLE_DECOMPOSITION.md](CYCLE_DECOMPOSITION.md).
- **bootstrap_cycle:** C0 (service skeleton; smoke `/health` gates C0→C1).
- **Quota profile:** [../../../contracts/raid/quota-profile.yaml](../../../contracts/raid/quota-profile.yaml).
- **Locked constraints:** [OPEN_QUESTIONS_LOCKED.md](OPEN_QUESTIONS_LOCKED.md) · pre-flight [PRE_FLIGHT_CHECKLIST.md](PRE_FLIGHT_CHECKLIST.md).

## Task-specific notes
- Cross-service cycles (C1, C7, C10, C11) MUST carry a live-smoke evidence token at VERIFY (real call against a stacked-up knowledge-service/glossary/book-service), per CLAUDE.md.
- Isolation: never modify the mmo-rpg foundation work (`world-service`, `game-server`, etc.) or other agents' files.
- Cost: P1 techniques only until the eval gate (C12); fabrication/re-cook gated.
