# 99 — Boundary Folder Changelog

> Append-only log of `_boundaries/*` edits + lock claims/releases.
>
> **Format:** newest entries at top.

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
