# DF05 — Session / Group Chat — Index

> **Status:** **CANDIDATE-LOCK 2026-04-27 — V1-blocking biggest unknown RESOLVED — 4-commit cycle COMPLETE** — concept-notes at [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (Phase 0 0080b533). 4-commit cycle: lock claim 1/4 745e9f6e + DRAFT 2/4 5d5dddd3 + Phase 3 cleanup 3/4 60536f19 + closure 4/4 (THIS commit). DRAFT spec at [`DF05_001_session_foundation.md`](DF05_001_session_foundation.md) (~1446 lines, 25 sections including SDK §16). Catalog at [`cat_18_DF5_session_group_chat.md`](../../../catalog/cat_18_DF5_session_group_chat.md) (DF5-A1..A11 axioms + 48 catalog entries DF5-1..DF5-48). Q1-Q12 ALL LOCKED via 4-batch deep-dive 2026-04-27 zero revisions. §16 SDK Architecture LOCKED. 14 V1 reject rules in `session.*` namespace + 5 V1+ reservations. 11 invariants DF5-A1..A11 + 4 cross-aggregate consistency rules DF5-C1..C4 (mapped to global C26-C29). 25 V1-testable acceptance scenarios AC-DF5-1..25. 17 deferrals DF5-D1..D17.
>
> **Architecture pivoted from initial single-session-per-cell to multi-session-per-cell sparse model** per user direction 2026-04-27 (billion-NPC AIT scaling concern + real-life conversation parallel). 95%+ cell actors AMBIENT (zero LLM cost); M concurrent sessions per cell (soft cap 50 V1); each session = explicit social act not spatial co-location. Per-actor POV memory distill on close (LLM × N participants); cached in EVT-T3 payload for replay-determinism.
>
> **NEW priority post-CANDIDATE-LOCK:** 16 cross-feature closure-pass-extensions (PL_002 + PL_005 + NPC_001..003 + ACT_001 + REP_001 + WA_003 + WA_006 + AIT_001 + PCS_001 + PL_001 + PF_001 + EM-7 + 07_event_model + RealityManifest) + 2 NEW directories scaffold (contracts/api/session/v1/ + services/session-service/) + V1+30d implementation phase (LruDistillProvider backend + ContractTestSuite mandatory CI gate).
>
> **Scope preview (revised post-pivot):** Sparse multi-session-per-cell architecture; Active/Closed lifecycle V1 (Idle V1+30d / Frozen V2+); per-actor POV memory distill on close (LLM × N participants); cross-session privacy enforced; PC anchor invariant; tier-aware participation (Untracked excluded per AIT-A8); same-channel constraint per TDIL-A5.
>
> **SDK architecture LOCKED 2026-04-27:** Versioned contract `contracts/api/session/v1/` (SessionService + MemoryProvider traits + DTOs + MemoryQuery DSL + ContractTestSuite). Implementation `services/session-service/` with swappable backends (V1 LruDistill / V1+30d SalienceTranscript / V2+ KnowledgeServiceBridge). Consumers depend on trait only; CI lint enforces. Backend rework without consumer breakage via shadow-read + dual-write + tolerant readers + capability probe + contract test suite.
>
> **Scope size estimate (DRAFT):** ~700-900 lines (between AIT_001 and TDIL_001 in complexity; integrates 16 features via closure-pass-extensions + 2 NEW directories per §15.9).

**Active:** (empty — concept-notes phase doesn't claim lock; main session captured concept)

---

## When DRAFT work starts

When Q1-Q12 LOCKED + boundary lock claimed, this `_index.md` expands into proper TOC. File list populates:

- `00_CONCEPT_NOTES.md` (✅ already created 2026-04-27)
- `01_REFERENCE_GAMES_SURVEY.md` (Discord / Foundry VTT / SillyTavern / NovelAI / TTRPG patterns) — if needed
- `DF05_001_session_foundation.md` (main DRAFT spec ~700-900 lines)
- (V2+ future: DF05_002 multi_pc_join, DF05_003 whisper, DF05_004 pvp_consent, DF05_005 npc_initiated...)

DRAFT promotion triggers 16 cross-feature closure-pass-extensions (per `00_CONCEPT_NOTES.md` §11):
- PL_001 / PL_002 / PL_005 (play loop)
- NPC_001 / NPC_002 / NPC_003 (NPC stack)
- ACT_001 (actor_session_memory R8 post-close write path)
- REP_001 (NPC consent reputation gating)
- WA_003 (Forge admin actions)
- WA_006 (mortality in session)
- AIT_001 (Untracked exclusion + capacity coordination)
- PCS_001 (body_memory feeds session prompt-assembly)
- PF_001 (cell-tier session capacity tracking)
- EM-7 (reality close cascade)
- 07_event_model (T3 + T4 sub-types registration)
- RealityManifest (canonical_sessions OPTIONAL extension)

If DF5 exposes gaps in SR11/S12/R7 kernel behavior, minimal kernel extensions allowed per feature-first-on-demand rule.

---

## Reading order for someone resuming

1. [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) §1 — user's pivotal direction (verbatim quote)
2. [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) §2-§3 — multi-session-per-cell model + simplified lifecycle
3. [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) §4 — close cascade with per-actor POV distill (the critical mechanism)
4. [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) §6 — invariants DF5-A1..A11
5. [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) §10 — Q1-Q12 PENDING deep-dive items
6. [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) §11 — 16 cross-feature closure-pass-extensions queued

---

## Pre-pivot history (archived note)

Initial main-session proposal 2026-04-27 framed DF5 as "single session per (PC, cell) container with auto-join all-cell-actors". User rejected with billion-NPC scaling concern + real-life conversation parallel argument. Architecture pivoted to multi-session sparse model captured in `00_CONCEPT_NOTES.md`. Pre-pivot draft NOT preserved (superseded entirely).
