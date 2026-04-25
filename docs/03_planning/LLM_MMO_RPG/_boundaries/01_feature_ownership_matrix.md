# 01 — Feature Ownership Matrix

> **Status:** seed 2026-04-25 — reflects the 11 features designed before this folder existed.
>
> **Lock-gated:** edit only with the `_LOCK.md` claim active.

---

## How to read

For every aggregate, schema, namespace, or validator slot in the LoreWeave LLM-MMO-RPG design, exactly ONE feature owns it. Other features REFERENCE without redefining.

Before designing a new feature: search this matrix for the aggregates / concepts you intend to own. If already owned by another feature, EITHER reference the existing owner OR escalate via boundary-review (claim lock + propose split / transfer).

---

## Aggregate ownership

| Aggregate | Tier × Scope | Owner feature | Notes |
|---|---|---|---|
| `fiction_clock` | T2 / Reality singleton | **PL_001 Continuum** | Per-reality fiction time. |
| `scene_state` | T2 / Channel (cell) | **PL_001 Continuum** | Per-cell ambient state. |
| `participant_presence` | T1 / Channel (cell) | **PL_001 Continuum** | Live "who's here" view; re-derived from DP-emitted MemberJoined/Left. |
| `actor_binding` | T2 / Reality | **PL_001 Continuum** | "Where is X" reality-global lookup, covers PCs + NPCs uniformly. |
| `turn_idempotency_log` | T2 / Reality | **PL_001 Continuum** | Reconnect/idempotency safety. *Borderline; may relocate to PL_004 session lifecycle when designed.* |
| `tool_call_allowlist` | T2 / Reality | **PL_002 Grammar** | Per-actor-type LLM tool-call allowlist. |
| `npc_reaction_priority` | T2 / Channel (cell) | **NPC_002 Chorus** | Per-(cell, NPC) priority hint for multi-NPC reactions. |
| `chorus_batch_state` | T1 / Channel (cell) | **NPC_002 Chorus** | Transient orchestrator coordination. |
| `npc` (R8 import) | T2 / Reality | **NPC_001 Cast** | DP-A14 annotations only; aggregate body locked by 02_storage R8. |
| `npc_session_memory` (R8 import) | T2 / Reality | **NPC_001 Cast** | DP-A14 annotations only; body locked by 02_storage R8. |
| `npc_pc_relationship_projection` (R8 import) | T2 / Reality | **NPC_001 Cast** | DP-A14 annotations only; body locked by 02_storage R8. |
| `npc_node_binding` | T2 (T3 on handoff) / Reality | **NPC_001 Cast** | NPC owner-node mapping with epoch fence. |
| `lex_config` | T2 / Reality singleton | **WA_001 Lex** | Per-reality physics/ability/energy axioms. |
| `actor_contamination_decl` | T2 / Reality | **WA_002 Heresy** | Per-(actor, kind) contamination exception. |
| `actor_contamination_state` | T2 / Reality | **WA_002 Heresy** | Per-(actor, kind) runtime budget tracking. |
| `world_stability` | T3 / Reality singleton | **WA_002 Heresy** | 5-stage state machine. |
| `forge_audit_log` | T2 / Reality | **WA_003 Forge** (CANDIDATE-LOCK) | Append-only audit; ALSO USED by PLT_001 + PLT_002 + WA_006 with their own AuditAction sub-shapes. WA_003 closure-reframed 2026-04-25 — patterns extractable to future CC_NNN are V1-essential here, V2+ optimization not boundary fix. §14 acceptance: 10 scenarios. |
| `coauthor_grant` | T2 / Reality | **PLT_001 Charter** (formerly WA_004; relocated 2026-04-25) | Active Co-Author grants. |
| `coauthor_invitation` | T2 / Reality | **PLT_001 Charter** | Pending invitations with TTL. |
| `ownership_transfer` | T2 (T3 at Finalize) / Reality | **PLT_002 Succession** (formerly WA_005; relocated 2026-04-25) | Multi-stage state machine. |
| `mortality_config` | T2 / Reality singleton | **WA_006 Mortality** (CANDIDATE-LOCK) | Per-reality death-mode config. WA_006 thin-rewritten 2026-04-25 closure pass (730 → 403 lines); only legitimate WA scope kept. §12 acceptance: 6 scenarios. |
| `pc_mortality_state` | T2 / Reality | **PCS_001** (when designed) | Mechanics handed off from WA_006 in closure pass — over-extended sections removed from WA_006 entirely; future PCS_001 owner has clean slate. |
| `meta_user_pending_invitations` | global meta-DB table | **PLT_001 Charter** (formerly WA_004) | Cross-reality denormalized; CHR-D9 watchpoint. |

---

## Schema / envelope ownership

These are SHARED across multiple features; each has a designated ENVELOPE owner who governs additive evolution.

| Schema | Envelope owner | Extending features | Extension rule |
|---|---|---|---|
| `TurnEvent` payload (EVT-T1 PlayerTurn / EVT-T2 NPCTurn) | **PL_001 Continuum** §3.5 | PL_002 (`command_kind`), NPC_002 (`reaction_intent`, `aside_target`, `action_kind`), WA_006 (provisional `outcome`) | See [`02_extension_contracts.md` §1](02_extension_contracts.md#1-turnevent-envelope) — additive only per foundation I14; envelope versioned `TurnEventSchema = N`. |
| `RealityManifest` | **(unowned — needs split)** ⚠ | PL_001 Continuum (starting_fiction_time + root_channel_tree + canonical_actors), WA_001 (LexConfig), WA_002 (contamination_allowances), WA_006 (mortality_config provisional), NPC_001 (CanonicalActorDecl extension) | See [`02_extension_contracts.md` §2](02_extension_contracts.md#2-realitymanifest) — proposal: extract to a new `IF_001_reality_manifest.md` infrastructure feature. |
| `ForgeEditAction` enum | **WA_003 Forge** §7 | PLT_001 Charter (CharterInvite/Accept/...), PLT_002 Succession (Succession*), WA_006 Mortality (MortalityConfig edits — provisional) | Closed enum extended via additive variants per I14. |
| Capability JWT (`forge.roles` + `forge.roles_version`) | **PLT_001 Charter** §6.3 | extended by PLT_002 (RealityOwner role), WA_006 (provisional MortalityAdmin) | Borderline with auth-service — flag for review when auth-service contributes. |
| `EVT-T8 AdminAction` sub-shapes | event-model agent (Phase 2) | WA_003 (`ForgeEdit`), PLT_001 (`Charter*`), PLT_002 (`Succession*`), WA_006 (`MortalityAdminKill` provisional) | Each feature DECLARES its sub-shapes; event-model agent's Phase 2 will lock the union. |
| `RejectReason` namespace prefixes | **PL_001 Continuum** §3.5 (envelope) | `lex.*` → WA_001, `heresy.*` → WA_002, `mortality.*` → WA_006 (provisional), `world_rule.*` → cross-cutting, `oracle.*` → 05_llm_safety A3, `canon_drift.*` → 05_llm_safety A6, `capability.*` → DP-K9, `parse.*` → PL_002, `chorus.*` → NPC_002, `forge.*` → WA_003, `charter.*` → PLT_001, `succession.*` → PLT_002 | Each feature owns its prefix; Continuum doesn't enumerate. **Path A tightening applied 2026-04-25 (commit f7c0a54).** |

---

## Stable-ID prefix ownership

Per [`../00_foundation/06_id_catalog.md`](../00_foundation/06_id_catalog.md). Reproduced here for boundary-review convenience.

| Prefix | Owner | Status |
|---|---|---|
| `DP-A*` / `DP-T*` / `DP-R*` / `DP-S*` / `DP-K*` / `DP-C*` / `DP-X*` / `DP-F*` / `DP-Ch*` | 06_data_plane (LOCKED) | locked |
| `EVT-A*` / `EVT-T*` / `EVT-Q*` (and EVT-P*/V*/L*/S* pending) | 07_event_model | partially locked (Phase 1) |
| `MV*` / `MV12-D*` | 03_multiverse | locked |
| `R*` / `S*` / `C*` / `SR*` | 02_storage | locked |
| `I*` (foundation invariants) | 00_foundation | locked |
| `PL-*` / `WA-*` / `PO-*` / `NPC-*` / `PCS-*` / `SOC-*` / `NAR-*` / `EM-*` / `PLT-*` / `CC-*` / `DL-*` | catalog/cat_NN_*.md per category | each catalog file owns its prefix |
| `LX-D*` / `LX-Q*` | WA_001 | per-feature deferral IDs |
| `HER-D*` / `HER-Q*` | WA_002 | per-feature deferral IDs |
| `FRG-D*` / `FRG-Q*` | WA_003 | per-feature deferral IDs |
| `CHR-D*` / `CHR-Q*` | PLT_001 | per-feature deferral IDs |
| `SUC-D*` / `SUC-Q*` | PLT_002 | per-feature deferral IDs |
| `MOR-D*` / `MOR-Q*` | WA_006 | per-feature deferral IDs |
| `GR-D*` / `GR-Q*` | PL_002 | per-feature deferral IDs |
| `CST-D*` / `CST-Q*` | NPC_001 | per-feature deferral IDs |
| `CHO-D*` / `CHO-Q*` | NPC_002 | per-feature deferral IDs |

Per-feature `*-D*` / `*-Q*` IDs are deferral IDs scoped to the feature's design doc. They never collide because the prefix is feature-specific. Foundation I15 stable-ID-renaming rule applies.

---

## Drift watchpoints (cross-cutting)

These are documented mismatches that require cross-feature coordination to resolve. Each is owned by the feature that flagged it, but resolution may require boundary-folder edits.

| ID | Owner-flagger | Drift | Resolution path |
|---|---|---|---|
| **GR-D8** | PL_002 | Rejected-turn commit primitive (`t2_write` per PL_001 §15 vs `advance_turn` per EVT-T1 spec) | event-model agent Phase 2 to absorb per-outcome sub-spec |
| **CST-D1** | NPC_001 | `npc.current_session_id` semantic (R8 wording vs OOS-1 in DP) | reconcile with 02_storage agent |
| **LX-D5** | WA_001 | Lex slot ordering in EVT-V* | event-model agent Phase 3 |
| **HER-D8** | WA_002 | EVT-T11 WorldTick V1+30d activation | event-model agent Phase 4 |
| **HER-D9** | WA_002 | LexSchema v1→v2 migration sequencing | implementation phase ops |
| **CHR-D9** | PLT_001 | Cross-reality `meta_user_pending_invitations` table | platform infrastructure |
| **WA_006 over-extension** | boundary review 2026-04-25 | 5 sections of WA_006 belong to PCS_001 / 05_llm_safety / PL_001 | rewrite WA_006 when feature owners take over |
| **B2 RealityManifest envelope** | boundary review 2026-04-25 | No single owner of the manifest schema | propose IF_001_reality_manifest.md (deferred) |

---

## Adding a new entry

When a new feature is designed:
1. Lock-claim `_boundaries/_LOCK.md`
2. Add the feature's owned aggregates to "Aggregate ownership"
3. If the feature extends a shared schema: add to "Schema / envelope ownership" + update `02_extension_contracts.md`
4. If the feature adds a validator slot: update `03_validator_pipeline_slots.md`
5. If the feature uses a new stable-ID prefix: add to "Stable-ID prefix ownership"
6. Append a row to `99_changelog.md`
7. Lock-release

---

## When ownership changes

Aggregate transfers are RARE (most aggregates stay with their original owner). When they happen (e.g., WA_006's `pc_mortality_state` will move to PCS_001):
1. Lock-claim
2. Update the matrix entry: change Owner, mark date of transfer, add reason
3. Update both feature design docs (giving + receiving)
4. Append a row to `99_changelog.md` with full transfer details
5. Lock-release
