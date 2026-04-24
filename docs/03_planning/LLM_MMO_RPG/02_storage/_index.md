# 02_storage — Index

> **Purpose:** Storage engineering for the LLM MMO RPG track — event sourcing, DB-per-reality, and all R/C/H-M-P/S/SR resolutions. Split from `02_STORAGE_ARCHITECTURE.ARCHIVED.md` on 2026-04-24 via `scripts/chunk_doc.py`. Every chunk is a verbatim byte-range of the archived monolith; `chunk_rules.json` + `chunk_doc.py verify` prove losslessness (`VERIFY OK`, sha256=`9766f6c3afda7f648fdac6367c70cb3a691c72dc954817f4b7b252a8bea0c62b`, 476 561 bytes, 36 chunks).

**Active:** (empty — no agent currently editing)

---

## Chunk map (source order)

| # | File | Former section | Lines | Owned stable IDs | Status |
|---:|---|---|---:|---|---|
| 00 | [00_overview_and_schema.md](00_overview_and_schema.md) | §1–§12 | 710 | Decisions §1 · schema §3–§11 · capacity §12 | LOCKED |
| 01 | [R01_event_volume.md](R01_event_volume.md) | §12A | 239 | R1 · R1-L1..L6 | MITIGATED |
| 02 | [R02_projection_rebuild.md](R02_projection_rebuild.md) | §12B | 146 | R2 · R2-L1..L5 | MITIGATED |
| 03 | [R03_schema_evolution.md](R03_schema_evolution.md) | §12C | 216 | R3 · R3-L1..L6 · R3-L5 upcasters | MITIGATED |
| 04 | [R04_fleet_ops.md](R04_fleet_ops.md) | §12D | 254 | R4 · R4-L1..L7 · DF11 foundation | MITIGATED |
| 05 | [R05_cross_instance.md](R05_cross_instance.md) | §12E | 171 | R5 · R5-L1..L3 · xreality policy | MITIGATED |
| 06 | [R06_R12_publisher_reliability.md](R06_R12_publisher_reliability.md) | §12F | 254 | R6 · R12 · R6-L1..L7 | MITIGATED |
| 07 | [R07_concurrency_cross_session.md](R07_concurrency_cross_session.md) | §12G | 286 | R7 · DF13 | MITIGATED |
| 08 | [R08_npc_memory_split.md](R08_npc_memory_split.md) | §12H | 305 | R8 · A1 foundation | MITIGATED |
| 09 | [R09_safe_reality_closure.md](R09_safe_reality_closure.md) | §12I | 271 | R9 · R9-L1..L8 | MITIGATED |
| 10 | [R10_global_ordering_accepted.md](R10_global_ordering_accepted.md) | §12J | 29 | R10 | ACCEPTED |
| 11 | [R11_pgvector_footprint.md](R11_pgvector_footprint.md) | §12K | 79 | R11 | MITIGATED |
| 12 | [R13_admin_discipline.md](R13_admin_discipline.md) | §12L | 129 | R13 · R13-L1..L6 | MITIGATED |
| 13 | [C01_severance_orphan_worlds.md](C01_severance_orphan_worlds.md) | §12M | 164 | C1-OW-1..5 · DF14 | LOCKED |
| 14 | [C02_db_subtree_split.md](C02_db_subtree_split.md) | §12N | 326 | C2-D1..D5 · `migrating` state | LOCKED |
| 15 | [C03_meta_registry_ha.md](C03_meta_registry_ha.md) | §12O | 302 | C3-D1..D6 · `contracts/meta/` | LOCKED |
| 16 | [C04_l3_override_reverse_index.md](C04_l3_override_reverse_index.md) | §12P | 134 | C4-D1..D4 | LOCKED |
| 17 | [C05_lifecycle_cas.md](C05_lifecycle_cas.md) | §12Q | 203 | C5-D1..D6 · `AttemptStateTransition()` | LOCKED |
| 18 | [HMP_followups.md](HMP_followups.md) | §12R | 338 | H1..H6 · M-REV-1..6 · P1..P4 · H3-NEW-D1..D6 | LOCKED |
| 19 | [S01_03_session_scoped_memory.md](S01_03_session_scoped_memory.md) | §12S | 430 | S1-D1 · S2-NEW-D1..D5 · S3-NEW-D1..D8 | LOCKED |
| 20 | [S04_meta_integrity.md](S04_meta_integrity.md) | §12T | 314 | S4-D1..D8 · `MetaWrite()` | LOCKED |
| 21 | [S05_admin_command_classification.md](S05_admin_command_classification.md) | §12U | 262 | S5-D1..D8 · Impact classes | LOCKED |
| 22 | [S06_llm_cost_controls.md](S06_llm_cost_controls.md) | §12V | 234 | S6-D1..D8 · `user_cost_ledger` | LOCKED |
| 23 | [S07_queue_abuse.md](S07_queue_abuse.md) | §12W | 188 | S7-D1..D7 · `user_queue_metrics` | LOCKED |
| 24 | [S08_audit_pii_retention.md](S08_audit_pii_retention.md) | §12X | 328 | S8-D1..D8 · `pii_registry` · `user_consent_ledger` | LOCKED |
| 25 | [S09_prompt_assembly.md](S09_prompt_assembly.md) | §12Y | 398 | S9-D1..D10 · `contracts/prompt/` · `prompt_audit` | LOCKED |
| 26 | [S10_severance_vs_deletion.md](S10_severance_vs_deletion.md) | §12Z | 257 | S10-D1..D8 · `GoneState` enum | LOCKED |
| 27 | [S11_service_to_service_auth.md](S11_service_to_service_auth.md) | §12AA | 438 | S11-D1..D10 · SVID · DF15 | LOCKED |
| 28 | [S12_websocket_security.md](S12_websocket_security.md) | §12AB | 434 | S12-D1..D10 · `contracts/ws/v1.yaml` | LOCKED |
| 29 | [S13_canonization_pre_spec.md](S13_canonization_pre_spec.md) | §12AC | 380 | S13-D1..D10 · `canon_entries` · `canonization_audit` | LOCKED |
| 30 | [SR01_slos_error_budget.md](SR01_slos_error_budget.md) | §12AD | 223 | SR1-D1..D8 · 7 SLIs | LOCKED |
| 31 | [SR02_incident_oncall.md](SR02_incident_oncall.md) | §12AE | 365 | SR2-D1..D10 · `incidents` | LOCKED |
| 32 | [SR03_runbook_library.md](SR03_runbook_library.md) | §12AF | 387 | SR3-D1..D10 · 27-runbook gate | LOCKED |
| 33 | [SR04_postmortem_process.md](SR04_postmortem_process.md) | §12AG | 339 | SR4-D1..D10 · root-cause 12-enum | LOCKED |
| 34 | [SR05_deploy_safety.md](SR05_deploy_safety.md) | §12AH | 348 | SR5-D1..D10 · `deploy_audit` · `feature_flags` | LOCKED |
| 35 | [99_known_risks_and_close.md](99_known_risks_and_close.md) | §13–§16 | 129 | Known risks · TBC decisions · references | LOCKED |
| 36 | [SR06_dependency_failure.md](SR06_dependency_failure.md) | §12AI (new, direct-authored 2026-04-24) | 338 | SR6-D1..D10 · `dependency_events` · `contracts/resilience/` · `contracts/lifecycle/` · invariant I16 | LOCKED |
| 37 | [SR07_chaos_drills.md](SR07_chaos_drills.md) | §12AJ (new, direct-authored 2026-04-24) | 323 | SR7-D1..D10 · `chaos_drills` · `contracts/chaos/experiments.yaml` · IF-40 · activates IF-39g | LOCKED |

**Totals:** 38 chunks (36 split-origin + 2 direct-authored) · 10 504 content lines. SR06 + SR07 are authored new content extending the SR series; they are not covered by `chunk_doc.py verify` against the archived monolith (the monolith predates them).

---

## Exported stable IDs (authoritative owner = this subfolder)

- **Risks:** R1..R13 (R12 merged into R6)
- **SA+DE Critical:** C1..C5 (plus C1-OW-1..5 orphan-worlds extension)
- **Adversarial follow-ups:** H1..H6, M-REV-1..6, P1..P4
- **Security:** S1..S13 (pre-spec for DF3 lives in S13)
- **SRE:** SR1..SR7 (SR8..SR12 not yet designed — will extend this subfolder)
- **Schema tables:** all tables defined in §12 sections — see individual files
- **Go packages:** `contracts/meta/`, `contracts/prompt/`, `contracts/pii/`, `contracts/ws/`, `contracts/service_acl/`, `contracts/entity_status/`, `contracts/resilience/` (SR6), `contracts/lifecycle/` (SR6), `contracts/dependencies/` (SR6), `contracts/chaos/` (SR7)

External docs link to these IDs, not to specific file paths.

---

## Pending splits / follow-ups

| File | Lines | Issue | Proposed action |
|---|---:|---|---|
| `00_overview_and_schema.md` | 710 | Over 500-line soft cap (foundational §1–§12 content) | Split on §-boundaries (each of §3..§12 is a candidate sub-file); defer until first edit needs it |
| `SR06`..`SR12` | — | Not yet designed — next session | Will add new chunks `SR06_*.md` .. `SR12_*.md` via direct write (not split) |

No chunk exceeds the 1500-line hard cap.

---

## How to work here (quick reminders)

1. Claim the subfolder by setting the **Active:** line above with your agent name + ISO UTC timestamp + scope.
2. Edit one chunk file at a time. Preserve stable IDs — never renumber.
3. Cross-ref by ID (e.g. "see S9-D3") not by file path or line number.
4. Update this index (status column, last-touched date) in the same commit as the chunk edit.
5. Clear the **Active:** line when you finish.

For the full rules see [`../AGENT_GUIDE.md`](../AGENT_GUIDE.md).

---

## Regenerate from archive

If chunks are accidentally corrupted or deleted:

```bash
cd d:/Works/source/lore-weave-game
python scripts/chunk_doc.py split docs/03_planning/LLM_MMO_RPG/02_storage/chunk_rules.json --force
```

Verify without rewriting:

```bash
python scripts/chunk_doc.py verify docs/03_planning/LLM_MMO_RPG/02_storage/chunk_rules.json
```

The archived monolith is the source of truth until this index's section-map is declared canonical (target: 1 session after migration, once external refs are updated).
