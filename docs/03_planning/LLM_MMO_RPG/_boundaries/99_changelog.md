# 99 — Boundary Folder Changelog

> Append-only log of `_boundaries/*` edits + lock claims/releases.
>
> **Format:** newest entries at top.

---

## 2026-04-26 — Closure-pass status promotions: PL_002 + NPC + PLT folders

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7, this conversation — closure pass continuation) at 2026-04-26 (after PL_005 agent released); commit `[boundaries-lock-claim+release]` (this turn)
- **Files modified:**
  - `01_feature_ownership_matrix.md`:
    - `tool_call_allowlist` row: PL_002 Grammar status → **CANDIDATE-LOCK 2026-04-25**; §13 acceptance: 10 scenarios
    - `npc_reaction_priority` row: NPC_002 Chorus status → **CANDIDATE-LOCK 2026-04-26**; §14 acceptance: 10 scenarios (SPIKE_01 turn 5 reproducibility verified)
    - `chorus_batch_state` row: NPC_002 Chorus status → **CANDIDATE-LOCK 2026-04-26**
    - `npc` (R8 import) row: NPC_001 Cast status → **CANDIDATE-LOCK 2026-04-26**; §14 acceptance: 10 scenarios
    - `npc_session_memory` (R8 import) row: NPC_001 Cast status → **CANDIDATE-LOCK 2026-04-26**
    - `npc_pc_relationship_projection` (R8 import) row: NPC_001 Cast status → **CANDIDATE-LOCK 2026-04-26**
    - `npc_node_binding` row: NPC_001 Cast status → **CANDIDATE-LOCK 2026-04-26**
    - `lex_config` row: WA_001 Lex status → **CANDIDATE-LOCK 2026-04-25** (date stamp added; status was set in WA closure pass)
    - `actor_contamination_decl` / `actor_contamination_state` / `world_stability` rows: WA_002 Heresy status → **CANDIDATE-LOCK 2026-04-25** (date stamp added)
    - `forge_audit_log` row: WA_003 Forge status → **CANDIDATE-LOCK 2026-04-25** (date stamp added)
    - `coauthor_grant` row: PLT_001 Charter status → **CANDIDATE-LOCK 2026-04-25**; §14 acceptance: 10 scenarios AC-CHR-1..10
    - `coauthor_invitation` row: PLT_001 Charter status → **CANDIDATE-LOCK 2026-04-25**
    - `ownership_transfer` row: PLT_002 Succession status → **CANDIDATE-LOCK 2026-04-25**; PLT_002b lifecycle split noted; §14 acceptance: 10 scenarios AC-SUC-1..10
    - `mortality_config` row: WA_006 Mortality status → **CANDIDATE-LOCK 2026-04-25** (date stamp added)
    - `meta_user_pending_invitations` row: PLT_001 Charter status → **CANDIDATE-LOCK 2026-04-25**
- **No other boundary files modified** — `02_extension_contracts.md` unchanged (PL_005 agent already added `interaction.*`); `03_validator_pipeline_slots.md` unchanged (no slot changes from closure pass).
- **Reason:** sequential closure passes (Q1-Q5 across PL_002 / NPC / PLT folders) brought 6 additional features to **CANDIDATE-LOCK** status with §13/§14 acceptance criteria. Boundary matrix updated to reflect new statuses + acceptance scenario counts. PL_005 Interaction (DRAFT 2026-04-26 by parallel agent) is intentionally NOT included in this status promotion; PL_005 is in DRAFT and will be CANDIDATE-LOCK'd in a separate future closure pass.
- **Closure pass summary** (mirrored from feature folder `_index.md` files):
  - **PL folder (04_play_loop):** PL_001/001b Continuum CANDIDATE-LOCK (boundary-tightened) · PL_002 Grammar CANDIDATE-LOCK 2026-04-25 (§13: 10 scenarios) · PL_005/005b/005c Interaction DRAFT 2026-04-26 (parallel agent)
  - **NPC folder (05_npc_systems):** CLOSED for V1 design 2026-04-26 — NPC_001 Cast CANDIDATE-LOCK 2026-04-26 (§14: 10 scenarios AC-CST-1..10) · NPC_002 Chorus CANDIDATE-LOCK 2026-04-26 (§14: 10 scenarios AC-CHO-1..10 incl. SPIKE_01 turn 5 reproducibility)
  - **PLT folder (10_platform_business):** PLT_001 Charter CANDIDATE-LOCK 2026-04-25 (§14: 10 scenarios AC-CHR-1..10) · PLT_002/002b Succession CANDIDATE-LOCK 2026-04-25 (§14: 10 scenarios AC-SUC-1..10)
  - **Total at CANDIDATE-LOCK after this pass:** 13 features across 4 closed folders (WA: 5 · PL: 3 · NPC: 2 · PLT: 3) — full V1 design surface for these folders
- **Sibling work landed in same window** (informational, not part of this lock claim):
  - 07_event_model agent: Phase 1-6 LOCKED + Option C redesign + EVT-G* Generator Framework (own changelog entries above)
  - PL_005 Interaction agent: PL_005/005b/005c DRAFT 2026-04-26 (own changelog entry above)
  - PCS_001 PC substrate brief seeded at `features/06_pc_systems/00_AGENT_BRIEF.md` for parallel agent (no boundary-folder edits required for brief seeding)
- **Drift watchpoints unchanged** (8 still active; status promotions don't introduce new drift)
- **Lock release:** at end of this commit (`[boundaries-lock-claim+release]`)

---

## 2026-04-26 — PL_005 Interaction feature registered

- **Lock claim:** main session (PL_005 Interaction feature design — core gameplay primitive) at 2026-04-26; commit `990eea3` `[boundaries-lock-claim]`
- **Files modified:**
  - `01_feature_ownership_matrix.md` "Schema/envelope ownership" section, EVT-T1 Submitted sub-types row: added **PL_005 Interaction** owns 5 V1 sub-types (`Interaction:Speak` / `Interaction:Strike` / `Interaction:Give` / `Interaction:Examine` / `Interaction:Use`); V1+ kinds (Collide/Shoot/Cast/Embrace/Threaten) reserved.
  - `02_extension_contracts.md` §1.4 RejectReason namespace prefix table: added `interaction.*` owned by PL_005 Interaction.
- **Reason:** PL_005 Interaction is the core gameplay primitive (4-role pattern + ProposedOutputs/ActualOutputs split + 5 V1 InteractionKinds) per user direction "core của gameplay". Phase 0 deliverable approved with defaults: B1 NPC mortality deferred to NPC_003 future + V1 placeholder · B2 Item aggregate deferred V1 (refs only) · B3 self-output simple (agent in direct_targets) · B4 atomic outputs (world-rule WA_001 Lex derives ActualOutputs at validator stage) · B5 catalog placement = `features/04_play_loop/PL_005_interaction.md` · B6 phase plan accepted. **Zero new aggregates V1** (deliberate scope discipline; references existing aggregates from PL_001/NPC_001/PCS_001/WA_001/WA_006/PL_002).
- **PL_005 deliverable:** new `features/04_play_loop/PL_005_interaction.md` (491 lines under 500-line soft cap), 19 sections covering Domain concepts + Event-model mapping + Aggregate inventory (zero new V1) + DP primitives + Capability + Subscribe pattern + Pattern choices + Failure UX + Cross-service handoff (CausalityToken chain) + 5 sequences (Speak/Strike/Give/Examine/Use) + 6 acceptance criteria scenarios + 9 deferrals (INT-D1..D9) + cross-references + readiness checklist.
- **Closes original-goal context** for "interaction" core gameplay: provides the dispatch contract that turns user input into committed canonical events with role-typed inputs + world-rule-derived outputs + downstream cascade hooks.
- **Drift watchpoints unchanged** (8 still active; no new boundary review items)
- **Lock release:** at end of PL_005 commit (this turn)

---

## 2026-04-25 (late evening, post-closure) — 07_event_model Phase 6 Generation Framework

- **Lock claim:** event-model agent (Phase 6 Generator Framework + Coordinator service spec) at 2026-04-25 (late evening, post-folder-closure reopening); commit `03560eb` `[boundaries-lock-claim]`
- **Files modified:**
  - `01_feature_ownership_matrix.md`:
    - Stable-ID prefix table EVT-* row extended: added `EVT-P1`/`P3`/`P4`/`P5`/`P6`/`P8` active markers + `EVT-P2`/`P7`/`P9`/`P10`/`P11` `_withdrawn` markers (catching up from Option C earlier this session); added `EVT-V1..V7` / `EVT-L1..L19` / `EVT-S1..S6` numeric ranges as Phase 3-4 reflection; **added new `EVT-G1..G6` namespace** for Phase 6 Generation Framework
    - Schema/envelope ownership table: added new **Generator Registry** row (Phase 6 EVT-G1) — declares ownership pattern: 07_event_model owns the registry framework; per-feature owns specific generators with composite `logical_id` + blake3 `registry_uuid`; Coordinator runs in-process per channel-writer (no new service binary V1)
- **No other boundary files modified** — `02_extension_contracts.md` unchanged (extension contracts are about cross-feature schemas; Generator Registry is its own concept); `03_validator_pipeline_slots.md` unchanged (validators are distinct from generators)
- **Reason:** user identified post-Option-C systematic-management gap for event generation. Original Phase 1-5 had axiom-level coverage (EVT-A9 RNG determinism + EVT-A12 (f) extensibility) but lacked operational framework. User picked Option C ("đi sâu vào thiết kế cái này để nếu có sai thì chưa cháy kịp thời ngay từ bây giờ") — full framework + Coordinator service design at design phase to fail-fast before V1+30d implementation. 5 sub-decisions D6.1-D6.5 approved (in-process per channel-writer / composite+UUID ID / both static+runtime cycle detection / tiered capacity / new EVT-G* prefix).
- **Phase 6 deliverable:** new `07_event_model/12_generation_framework.md` (343 lines, 6 sections covering EVT-G1 Registry + EVT-G2 5-source typed taxonomy + EVT-G3 cycle detection + EVT-G4 capacity governance + EVT-G5 Coordinator spec + EVT-G6 extension procedure). Deployment: in-process per channel-writer (zero new service binary V1; matches DP-Ch26 pattern). 6 failure modes that fragmented per-feature generation would hit are explicitly addressed.
- **Closes original-goal #4** ("generate event theo điều kiện + xác suất") at systematic level. EVT-A12 extension point (f) "new generation rule" operationalized with 6-step procedure.
- **Drift watchpoints unchanged** (8 still active; no new boundary review items)
- **Lock release:** at end of Phase 6 commit (this turn)

---

## 2026-04-25 (late evening) — 07_event_model Option C redesign Phase 1

- **Lock claim:** event-model agent (07_event_model Option C redesign) at 2026-04-25 (late evening); commit `66ce219` `[boundaries-lock-claim]`
- **Files modified:**
  - `01_feature_ownership_matrix.md`:
    - Stable-ID prefix table row for EVT-* updated to enumerate active vs `_withdrawn` IDs (T1/T3/T4/T5/T6/T8 active; T2/T7/T9/T10/T11 `_withdrawn` per I15) + EVT-A1..A12 active
    - Schema/envelope ownership table: renamed `EVT-T8 AdminAction` → `EVT-T8 Administrative` (reframe per Option C)
    - Schema/envelope ownership table: added 3 new rows for sub-type ownership of newly-active categories — **EVT-T1 Submitted sub-types** (PL_001/PL_002 own PCTurn; NPC_001/NPC_002 own NPCTurn; future quest-engine owns QuestOutcome) · **EVT-T3 Derived sub-types** (sub-discriminator = `aggregate_type`; PL_001/NPC_001/PL_002 own respective aggregates; calibration sub-shapes absorbed from former EVT-T7) · **EVT-T5 Generated sub-types** (gossip aggregator owns BubbleUp:RumorBubble; world-rule-scheduler owns Scheduled:NPCRoutine + Scheduled:WorldTick V1+30d; quest-engine owns Scheduled:QuestTrigger; combat owns RNG-based generators)
- **Files NOT modified in this lock:** `02_extension_contracts.md` (TurnEvent envelope §1 + AdminAction §4 already at correct mechanism level — no changes needed; only category-name reference "AdminAction → Administrative" implied in §4 cross-ref, but §4 itself unchanged); `03_validator_pipeline_slots.md` (unchanged — already mechanism-level)
- **Reason:** event-model agent's Option C redesign reframed Event Model from feature-specific taxonomy (T1 PlayerTurn / T2 NPCTurn / T7 CalibrationEvent / T9 QuestBeat / T10 NPCRoutine / T11 WorldTick) to mechanism-level taxonomy (T1 Submitted / T3 Derived / T4 System / T5 Generated / T6 Proposal / T8 Administrative). 8 existing axioms preserved (A4/A7/A8 reframed wording; A1/A2/A3/A5/A6 preserved); 4 new axioms added (A9 probabilistic generation determinism · A10 event as universal source of truth · A11 sub-type ownership discipline · A12 extensibility framework). Original Phase 1 commit `ce6ea97` superseded by the redesign commit (this turn).
- **EVT-T2/T7/T9/T10/T11 retirement rationale:** each was mechanically identical to (or a sub-shape split of) one of the active mechanism categories — T2 NPCTurn merged into T1 Submitted as sub-type (only actor variant differs); T7 CalibrationEvent merged into T3 Derived (calibration is a Derived event from FictionClock advance); T9 QuestBeat split (Trigger → T5 Generated, Advance → T3 Derived, Outcome → T1 Submitted); T10 NPCRoutine + T11 WorldTick both merged into T5 Generated (different sub-types via Scheduled:* prefix).
- **Feature doc citation updates** (in same redesign commit):
  - `features/04_play_loop/PL_002_command_grammar.md` §2.5 — citations updated to active EVT-T* IDs + sub-types
  - `features/05_npc_systems/NPC_001_cast.md` §2.5 — EVT-T2 references redirected to EVT-T1 sub-type=NPCTurn
  - `features/05_npc_systems/NPC_002_chorus.md` §2.5 — EVT-T2 references redirected to EVT-T1 sub-type=NPCTurn
- **Drift watchpoints unchanged** (8 still active; ownership identifiers updated)
- **Lock release:** at end of redesign commit (this turn)

---

## 2026-04-25 (evening) — WA folder closure: ownership matrix update

- **Lock claim:** main session 2026-04-25 (Claude Opus 4.7) at 2026-04-25 (evening); released at end of this commit
- **Files modified:**
  - `01_feature_ownership_matrix.md`:
    - `forge_audit_log` row: WA_003 status PROVISIONAL → **CANDIDATE-LOCK**; reframed note (patterns extractable, V2+ optimization not boundary fix); §14 acceptance noted
    - `mortality_config` row: WA_006 status updated to **CANDIDATE-LOCK** (thin-rewrite from 730 → 403 lines closure pass); §12 acceptance noted
    - `pc_mortality_state` row: removed PROVISIONAL/over-extended note; cleanly attributes to PCS_001 (mechanics fully handed off from WA_006 in closure pass)
- **No other boundary files modified** in this pass (extension contracts §1.4 RejectReason namespace prefixes already correct; validator pipeline §6.1 unchanged; ID prefix table unchanged)
- **Reason:** WA folder closure pass (commit f436e60) brought all 5 WA features to CANDIDATE-LOCK with acceptance criteria. Boundary folder updated to reflect new statuses + clean handoffs to mechanics owners (PCS_001 / 05_llm_safety / PL_001/002 / NPC_001/002).
- **WA folder closure summary** (mirrored from `features/02_world_authoring/_index.md`):
  - WA_001 Lex CANDIDATE-LOCK (656 lines, §14: 10 scenarios)
  - WA_002 Heresy root CANDIDATE-LOCK (597 lines)
  - WA_002b Heresy lifecycle NEW + CANDIDATE-LOCK (277 lines, §14: 10 scenarios)
  - WA_003 Forge CANDIDATE-LOCK (798 lines, §14: 10 scenarios; reframed pattern-reuse not boundary violation)
  - WA_006 Mortality CANDIDATE-LOCK (403 lines thin-rewrite; §12: 6 scenarios)
  - Total: 5 docs, ~2,730 lines, all under 800-line cap
- **Drift watchpoints unchanged** (8 still active; HER-D8/D9/LX-D5 all still tracked; WA_006 over-extension watchpoint resolved by thin-rewrite)
- **Lock release:** at end of this commit

---

## 2026-04-25 (afternoon) — WA boundary shrink: ownership matrix update

- **Lock claim:** main session 2026-04-25 (Claude Opus 4.7) at 2026-04-25 (afternoon)
- **Files modified:**
  - `01_feature_ownership_matrix.md`:
    - `coauthor_grant`, `coauthor_invitation` → owner WA_004 → **PLT_001 Charter** (formerly WA_004; relocated 2026-04-25)
    - `ownership_transfer` → owner WA_005 → **PLT_002 Succession** (formerly WA_005)
    - `meta_user_pending_invitations` → owner WA_004 → **PLT_001 Charter** (formerly WA_004)
    - `forge_audit_log` consumers list updated (PLT_001 + PLT_002 + WA_006 instead of WA_004/005/006)
    - WA_003 Forge marked PROVISIONAL with note about future cross-cutting extraction
    - `RejectReason` namespace prefix table expanded — added `canon_drift.*`, `capability.*`, `parse.*`, `chorus.*`, `forge.*`, `charter.*`, `succession.*`; "Pending Path A tightening" replaced with "Path A applied 2026-04-25 (commit f7c0a54)"
    - `ForgeEditAction`, capability JWT, EVT-T8 sub-shapes — owner attributions for Charter/Succession updated WA_004/005 → PLT_001/002
    - Stable-ID prefix ownership rows: `CHR-D*`/`CHR-Q*` owner WA_004 → PLT_001; `SUC-D*`/`SUC-Q*` owner WA_005 → PLT_002
    - Drift watchpoint `CHR-D9`: owner WA_004 → PLT_001
  - `02_extension_contracts.md`: same pattern across §1.4 RejectReason table, §3 capability JWT, §4 EVT-T8 sub-shapes — all WA_004/005 references re-attributed to PLT_001/002
- **Drift watchpoints unchanged** (8 still active; ownership identifiers updated)
- **No new contracts added** — pure ownership re-attribution
- **Reason:** post-WA boundary review concluded WA's original intent ("validate rules of reality + detect paradox + allow controlled bypass") doesn't cover identity/account concerns. WA_004 Charter + WA_005 Succession relocated to `10_platform_business/` (commit 4be727d); WA_003 Forge marked PROVISIONAL pending future cross-cutting pattern extraction; WA_006 Mortality already PROVISIONAL from prior review (commit de9cf1a). WA folder shrinks from 6 to 3 active features (WA_001 Lex, WA_002 Heresy, WA_003 Forge PROVISIONAL) + 1 PROVISIONAL marker (WA_006).
- **Lock release:** at end of this commit

---

## 2026-04-25 — Folder seeded

- **Lock claim:** main session 2026-04-25 (Claude Opus 4.7) at 2026-04-25
- **Files created:**
  - `_LOCK.md` (single-writer mutex)
  - `00_README.md` (purpose, rules, how-to-use)
  - `01_feature_ownership_matrix.md` (initial entries for 11 designed features: PL_001/001b/002, NPC_001/002, WA_001..006)
  - `02_extension_contracts.md` (TurnEvent envelope §1, RealityManifest §2, capability JWT §3, EVT-T8 sub-shapes §4)
  - `03_validator_pipeline_slots.md` (proposed EVT-V* ordering pending event-model Phase 3 lock)
  - `99_changelog.md` (this file)
- **Initial drift watchpoints captured (8):** GR-D8, CST-D1, LX-D5, HER-D8, HER-D9, CHR-D9, WA_006 over-extension, B2 RealityManifest envelope
- **Reason:** post-WA_006 boundary review (2026-04-25) revealed boundary issues across the 11 features designed in one work session; a mutex'd boundary folder is the long-term fix
- **Lock release:** at end of seeding commit
