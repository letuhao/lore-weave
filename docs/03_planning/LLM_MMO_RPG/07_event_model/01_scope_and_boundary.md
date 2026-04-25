# 01 — Scope and Boundary

> **Status:** LOCKED. Purpose: prevent scope creep into adjacent locked folders + prevent gaps between Event Model and adjacent folders. Every IN/OUT line is enforceable: drift triggers a [`99_open_questions.md`](99_open_questions.md) escalation, never a silent workaround.
> **Reference:** Brief [`00_AGENT_BRIEF.md`](00_AGENT_BRIEF.md) §2 (IN scope) + §3 (OUT of scope). This file mirrors and refines.

---

## 1. IN scope (this folder MUST design these)

### S1 — Event taxonomy (top-level closed set)
Closed set of category names + one-line definition each. **Every event mentioned in PL_001 + every observation in SPIKE_01 maps to exactly one category.** No "Other". Locked in [`03_event_taxonomy.md`](03_event_taxonomy.md) Phase 1.

### S2 — Producer rules per category (EVT-P*)
Per category: allowed producer service/role · capability gate (DP-K9 JWT claim) · idempotency key composition · semantic rate limit · forbidden producer list. Locked in `04_producer_rules.md` Phase 2.

### S3 — Validator pipeline (EVT-V*)
Six validator stages (schema · capability · intent classification · world-rule lint · canon-drift / retrieval-isolation · causal-ref integrity) with locked ordering, fail-mode contract (reject vs sanitize vs quarantine), retry policy, dead-letter destination. SLOTS 05_llm_safety A3/A5/A6 in; does NOT redesign them. Locked in `05_validator_pipeline.md` Phase 3.

### S4 — Per-category contracts (event shapes)
Per category: required fields · optional fields · idempotency key composition · causal-ref shape (which categories MAY/MUST reference parent) · max payload size · schema version field placement. Reconciles + formalizes PL_001 §3.5 `TurnEvent` as canonical contract. Locked in `06_per_category_contracts.md` Phase 2.

### S5 — LLM proposal bus protocol (EVT-L1..)
Resolves DP-A6 deferred bits. Concrete: transport (Redis Streams via I13 outbox) · topic naming (reality-prefixed per DP-A7) · proposal envelope shape · acknowledgment model · retry + dead-letter · ordering guarantee · backpressure when validator lags. Implementable for Python roleplay-service after Phase 3 lock. Locked in `07_llm_proposal_bus.md` Phase 3.

### S6 — Scheduled / fiction-time-triggered events
Producer model for WorldTick + NPCRoutine (scheduler service vs sidecar vs CP responsibility). Trigger evaluation (when fiction-clock advances vs polled vs cron). Idempotency for big jumps that pass multiple scheduled thresholds in one advance. Recovery if scheduler is down. Locked in `08_scheduled_events.md` Phase 4.

### S7 — Causal references (EVT-L2..)
Schema for "event B caused by event A": per-channel `(channel_id, channel_event_id)` from DP-A15; cross-channel for bubble-up; LLM-proposal-to-committed chain; QuestBeat-causes-WorldTick chain. Field name + type + validation rule (referenced event must exist + same-reality constraint). Locked in `09_causal_references.md` Phase 4.

### S8 — Replay semantics (EVT-L3..)
Three replay use cases with separate contracts:
1. **Session catch-up replay** — UI client reconnects via DP-K6 `subscribe_channel_events_durable`; specifies which categories user-visible vs internal-filtered.
2. **Canon-promotion replay** — emergent events get promoted via DF3 (V2+); chain validation.
3. **Time-travel debug replay** — operator queries "what happened in cell X between turn N and M"; deterministic guarantee.
Locked in `10_replay_semantics.md` Phase 4.

### S9 — Schema versioning + migration (EVT-S*)
Resolves DP Q5 (schema migration) deferred from CP spec. Schema version field placement on every event · forward-compat rules · backward-compat rules · migration triggers · replay against migrated schemas. Inherits I14 additive-first discipline. Locked in `11_schema_versioning.md` Phase 4.

### S10 — Bridging quickstart for feature authors
Worked example re-mapping PL_001's TurnEvent + BubbleUpEvent + AmbientUpdate using EVT-T*/EVT-P*/EVT-V* contracts. Decision flowchart "I need to emit an event — which category, which producer, which validator chain?". Mirrors [`../06_data_plane/22_feature_design_quickstart.md`](../06_data_plane/22_feature_design_quickstart.md) shape. Locked in `22_event_design_quickstart.md` Phase 5.

---

## 2. OUT of scope (this folder MUST NOT touch)

### O1 — Anything LOCKED in `06_data_plane/`
DP-A1..A19 axioms · DP-T0..T3 tier taxonomy · DP-R1..R8 rulebook · DP-K1..K12 SDK API surface · DP-C* control plane · DP-X* cache coherency · DP-F* failure recovery · DP-Ch1..Ch53 channel primitives + ordering + durable subscribe + turn boundary + bubble-up + lifecycle + causality + redaction + operational + turn-slot. **READ-ONLY.** If a real conflict surfaces, escalate via [`99_open_questions.md`](99_open_questions.md).

### O2 — Specific feature event sub-types
Each feature in [`features/<category>/<NNN>_*.md`](../features/) declares its own event sub-types within an EVT-T* category. This folder defines TAXONOMY (top-level) + CONTRACT SHAPE (envelope), not every NPC dialog line type or every quest-beat outcome shape.

### O3 — Implementation code
No Rust, Python, TypeScript. Diagrams in markdown text or mermaid; no images. Schema field types described abstractly (e.g., "UUID", "timestamp millis", "JSON object") — concrete Rust types land in feature implementation, not here.

### O4 — LLM safety internals
[`05_llm_safety/`](../05_llm_safety/) owns A3 World Oracle internals · A5-D1 intent classifier internals · A5 command dispatch · A5-D3 tool-call allowlist · A6 5-layer injection defense internals. Event Model SLOTS them into the EVT-V* pipeline; does NOT modify. If a gap in A3/A5/A6 surfaces, escalate via [`99_open_questions.md`](99_open_questions.md).

### O5 — Storage event-log mechanics
[`02_storage/`](../02_storage/) owns event-log durability (R*) · outbox pattern (I13) · projection rebuild (R02) · snapshot mechanics (S*) · single-writer per session (R7). Event Model consumes those unchanged. New primitives needed → raise as a [`99_open_questions.md`](99_open_questions.md) item directed at the storage track.

### O6 — Catalog modifications
[`catalog/`](../catalog/) is the master scope rollup. Event Model does NOT modify catalog files. After EVT-* IDs lock, the main session adds catalog references in a separate commit.

### O7 — Existing committed feature designs
[`features/04_play_loop/PL_001_continuum.md`](../features/04_play_loop/PL_001_continuum.md) (committed `b4ea611`) is reference material — read to understand the gap, do NOT modify. After taxonomy locks, the main session updates PL_001 to cite EVT-* IDs in a separate commit.

### O8 — Multiverse canon-promotion mechanism
Per Phase 0 boundary decision B6 (resolved 2026-04-25): CanonPromotion (L3 → L2 author-gated, L2 → L1 rare) is OUT of EVT-T* taxonomy. Owned by [`03_multiverse/`](../03_multiverse/) + DF3 (V2+) + meta-worker. If a future need surfaces to give CanonPromotion an Event Model handle, revisit via [`99_open_questions.md`](99_open_questions.md).

### O9 — Cross-reality coordination
DP-A12 + R5 cross-instance policy enforce per-reality scoping. Event Model events are reality-scoped; cross-reality coordination (canon propagation, parent-fork sync) goes through dedicated coordinator services (not this folder's concern).

---

## 3. Boundary tests (post-Phase-1 sanity check)

After Phase 1 locks, the following queries MUST return cleanly:

| Query | Expected answer | Where to look |
|---|---|---|
| "Where is the closed set of event categories?" | EVT-T1..T11 in [`03_event_taxonomy.md`](03_event_taxonomy.md) | This folder |
| "Where is the rule that PCs cannot emit WorldTick?" | EVT-P* (Phase 2) — forbidden-producer list per category | This folder |
| "Where is the validator order for an LLMProposal?" | EVT-V* (Phase 3) | This folder |
| "How does roleplay-service publish a proposal?" | `07_llm_proposal_bus.md` (Phase 3) | This folder |
| "When does the siege event fire?" | `08_scheduled_events.md` (Phase 4) | This folder |
| "How does my feature's event reference its parent?" | EVT-L* causal-ref schema (Phase 4) | This folder |
| "Why does my replay miss this event?" | `10_replay_semantics.md` (Phase 4) | This folder |
| "How do I version a schema bump?" | EVT-S* (Phase 4) | This folder |

| Query | Expected redirect (NOT this folder) | Owner |
|---|---|---|
| "How does T2 write differ from T3?" | DP-T2/T3 in [`../06_data_plane/03_tier_taxonomy.md`](../06_data_plane/03_tier_taxonomy.md) | DP |
| "What is the cache invalidation protocol?" | DP-X* in [`../06_data_plane/06_cache_coherency.md`](../06_data_plane/06_cache_coherency.md) | DP |
| "How does the prompt template enforce A6?" | A6 in [`../05_llm_safety/04_injection_defense.md`](../05_llm_safety/04_injection_defense.md) | LLM safety |
| "When does L3 → L2 canonization happen?" | DF3 in [`../03_multiverse/`](../03_multiverse/) (V2+) | Multiverse |
| "What is the outbox table schema?" | I13 in [`../02_storage/R06_R12_publisher_reliability.md`](../02_storage/R06_R12_publisher_reliability.md) | Storage |

If a query falls in the second table but a feature author asks Event Model, the answer is "redirect to the owning folder" — not "let me design that for you".

---

## 4. Drift watchpoints

These are the most likely places where Event Model could accidentally over-reach into a locked folder. Specifically called out so future agents recognize the trap.

| Watchpoint | Risk | Correct response |
|---|---|---|
| LLM proposal bus design (S5) | Tempting to redesign outbox or invent new transport | Use existing I13 outbox + Redis Streams; reality-prefix per DP-A7; do not reimplement publisher reliability |
| Validator pipeline (S3) | Tempting to redesign A3/A5/A6 internals | SLOT them in by reference; if internals seem wrong, raise EVT-Q*, do not edit `05_llm_safety/` |
| Scheduled events (S6) | Tempting to design a new "scheduler service" | Producer is feature-level (e.g., `world-rule-scheduler`); not Event Model concern beyond the producer rule + idempotency contract |
| Causal references (S7) | Tempting to redefine DP-A15 shape | Extend DP-A15's `(channel_id, channel_event_id)` for cross-category use; do not re-shape |
| Replay (S8) | Tempting to redesign DP-K6 subscribe protocol | DP-K6 gives gap-free transport; Event Model only adds "which categories are user-visible vs internal" filter rule |
| Schema versioning (S9) | Tempting to redesign R3 additivity | Inherit I14 + R3 unchanged; only add EVT-specific rules (per-category schema version field placement, etc.) |
| CanonPromotion (O8) | Tempting to give author-canonization an EVT-T* row | Excluded by Phase 0 B6 decision. If real need surfaces in V2+, raise EVT-Q* |
