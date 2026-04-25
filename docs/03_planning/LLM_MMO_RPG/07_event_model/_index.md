# 07_event_model — Index

> **Purpose:** Domain-shaped layer above the Data Plane. Owns event TAXONOMY, PRODUCER rules, VALIDATOR pipeline, per-category CONTRACTS, LIFECYCLE (proposal → validation → commit → fan-out), and SCHEMA VERSIONING. Sits on top of [`../06_data_plane/`](../06_data_plane/) (LOCKED) which owns transport (ordering, durability, fan-out, channel hierarchy).
>
> **Status:** **Phase 1 LOCKED 2026-04-25 + Option C redesign 2026-04-25.** Foundation: **12 axioms** (EVT-A1..A12 — A4/A7/A8 reframed mechanism-level; A9/A10/A11/A12 added) + **6 active mechanism-level categories** (EVT-T1 Submitted / T3 Derived / T4 System / T5 Generated / T6 Proposal / T8 Administrative) + 5 retired (T2/T7/T9/T10/T11 `_withdrawn` per I15). Closed-set proof against PL_001 / PL_002 / NPC_001 / NPC_002 / SPIKE_01 holds under redesigned taxonomy. Feature authors MAY cite EVT-A* / EVT-T* IDs. Phase 2 (producers + contracts) thin-rewrite pending; Phase 3 (validators + LLM bus), Phase 4 (scheduling + causal + replay + versioning), Phase 5 (quickstart) pending.
>
> **Relationship to DP:** DP is "TCP/IP for game state". Event Model is "HTTP semantic for game state". DP guarantees a totally-ordered durable event stream per channel; Event Model defines what TYPES of events exist, who produces them, how they're validated, and how their schemas evolve.

---

## Why this folder exists

[`PL_001_continuum.md`](../features/04_play_loop/PL_001_continuum.md) ("Continuum", committed `b4ea611` then renamed) treated "events" as a primitive concept inherited from DP — but DP only locks event ORDERING and DELIVERY, not event SHAPE or LIFECYCLE.

Concretely missing as of 2026-04-25:

1. **Taxonomy** — every feature is on track to invent its own event type (TurnEvent, MembershipEvent, BubbleUpEvent, AmbientEvent, RoutineEvent, ...) with no shared closed-set classification.
2. **Producer rules** — DP-A6 says "Python proposes, Rust validates and writes" but defers the bus protocol, retry policy, dead-letter, and idempotency.
3. **Validator pipeline** — five existing checks (canon-drift, world-rule, capability, schema, intent classification) have no agreed ordering or fail-mode contract.
4. **Scheduled events** — "siege Tương Dương starts day X-thu-1257" is a fiction-time-triggered event with no producer assigned.
5. **Causal references** — DP-A15 mentions `(child_channel_id, child_channel_event_id)` for bubble-up; no general schema for "event B caused by event A".
6. **Replay semantics** — session catch-up replay, canon-promotion replay, and time-travel debug replay have different requirements; not differentiated.
7. **Schema versioning** — DP-K3 has `SchemaVersionMismatch` variant; migration protocol deferred to "Q5 in CP spec" — actually belongs here.

Without this folder, every feature has to relitigate event semantics. With it, feature authors pick from the taxonomy and reference producer/validator rules instead of redefining them.

---

## Reading order

**Phase 1 (LOCKED 2026-04-25):**

1. [`00_AGENT_BRIEF.md`](00_AGENT_BRIEF.md) — work commission (read FIRST to understand scope of the agent's work and its boundaries)
2. [`00_preamble.md`](00_preamble.md) — context, relation to DP / 05_llm_safety / 03_multiverse / 02_storage
3. [`01_scope_and_boundary.md`](01_scope_and_boundary.md) — IN/OUT scope (S1-S10 / O1-O9) + drift watchpoints
4. [`02_invariants.md`](02_invariants.md) — **EVT-A1..A8** axioms (closed-set, layered above DP, validated commits, producer binding, fixed validator order, typed causal-refs, LLM proposal pre-validation, flavor narration is non-canonical)
5. [`03_event_taxonomy.md`](03_event_taxonomy.md) — **EVT-T1..T11** closed-set categories with closed-set proof + per-category lifecycle + DP commit primitive mapping
6. [`99_open_questions.md`](99_open_questions.md) — EVT-Q1..Q10 deferred items + cross-folder pointers + MV12-D8..D11 candidate landing points

**Pending (Phases 2-5):**

7. `04_producer_rules.md` — **EVT-P*** producer rules per category (Phase 2)
8. `06_per_category_contracts.md` — required/optional fields, idempotency keys, max payload sizes (Phase 2)
9. `05_validator_pipeline.md` — **EVT-V*** validator ordering + fail modes (Phase 3, resolves MV12-D11)
10. `07_llm_proposal_bus.md` — concrete LLM-side bus protocol (Phase 3, resolves DP-A6 deferred bits)
11. `08_scheduled_events.md` — fiction-time-triggered events (Phase 4, resolves MV12-D10 + EVT-Q4 + EVT-Q8)
12. `09_causal_references.md` — typed `CausalRef` shape (Phase 4, resolves EVT-Q5)
13. `10_replay_semantics.md` — three replay use cases (Phase 4, resolves EVT-Q6 + EVT-Q10)
14. `11_schema_versioning.md` — **EVT-S*** migration protocol (Phase 4, resolves DP Q5 + EVT-Q7 + EVT-Q9)
15. `22_event_design_quickstart.md` — bridging doc with worked example for feature authors (Phase 5)

---

## Status table

| # | File | Status | Owned IDs | Last touched |
|---:|---|---|---|---|
| 00 | [`00_AGENT_BRIEF.md`](00_AGENT_BRIEF.md) | LOCKED (commission) | — | 2026-04-25 |
| 00 | [`00_preamble.md`](00_preamble.md) | LOCKED Phase 1 | — | 2026-04-25 |
| 01 | [`01_scope_and_boundary.md`](01_scope_and_boundary.md) | LOCKED Phase 1 | — | 2026-04-25 |
| 02 | [`02_invariants.md`](02_invariants.md) | LOCKED Phase 1 + Option C redesign | EVT-A1..A12 | 2026-04-25 (redesign) |
| 03 | [`03_event_taxonomy.md`](03_event_taxonomy.md) | LOCKED Phase 1 + Option C redesign | EVT-T1/T3/T4/T5/T6/T8 active; T2/T7/T9/T10/T11 `_withdrawn` per I15 | 2026-04-25 (redesign) |
| 04 | [`04_producer_rules.md`](04_producer_rules.md) | LOCKED Phase 2a thin-rewrite (Option C) | EVT-P1/P3/P4/P5/P6/P8 active; P2/P7/P9/P10/P11 `_withdrawn` per I15 | 2026-04-25 |
| 05 | [`05_validator_pipeline.md`](05_validator_pipeline.md) | LOCKED Phase 3a (Option C) — framework rules; cite `_boundaries/03_validator_pipeline_slots.md` for stage list SSOT | EVT-V1..V7; resolves MV12-D11 | 2026-04-25 |
| 06 | [`06_per_category_contracts.md`](06_per_category_contracts.md) | LOCKED Phase 2b thin-rewrite (Option C) — envelope mechanism + extensibility framework only; sub-shape SSOT in `_boundaries/` + feature docs | — | 2026-04-25 |
| 07 | [`07_llm_proposal_bus.md`](07_llm_proposal_bus.md) | LOCKED Phase 3b (Option C) — bus framework mechanism; specific config (topics, retention) operational | EVT-L1..L6; resolves DP-A6 framework | 2026-04-25 |
| 08 | [`08_scheduled_events.md`](08_scheduled_events.md) | LOCKED Phase 4a (Option C) | EVT-L7..L11; resolves EVT-Q4/Q8 + MV12-D10 | 2026-04-25 |
| 09 | [`09_causal_references.md`](09_causal_references.md) | LOCKED Phase 4a (Option C) | EVT-L12..L15; resolves EVT-Q5 | 2026-04-25 |
| 10 | `10_replay_semantics.md` | PENDING Phase 4 | EVT-L* | — |
| 11 | `11_schema_versioning.md` | PENDING Phase 4 | EVT-S* | — |
| 22 | `22_event_design_quickstart.md` | PENDING Phase 5 | — | — |
| 99 | [`99_open_questions.md`](99_open_questions.md) | OPEN — Phase 1 seed (EVT-Q1..Q10 + MV12-D8..D11 cross-refs) | EVT-Q* | 2026-04-25 |

---

## Exported stable IDs (reserved namespace)

| Prefix | Scope | Owned by (when locked) |
|---|---|---|
| `EVT-A*` | Axioms / invariants | `02_invariants.md` |
| `EVT-T*` | Event taxonomy (closed-set categories) | `03_event_taxonomy.md` |
| `EVT-P*` | Producer rules per category | `04_producer_rules.md` |
| `EVT-V*` | Validator pipeline rules | `05_validator_pipeline.md` |
| `EVT-S*` | Schema versioning + migration | `11_schema_versioning.md` |
| `EVT-L*` | Event lifecycle stages (proposal → committed) | TBD by agent |
| `EVT-Q*` | Open questions | `99_open_questions.md` |

**Reserved — must NOT collide with:**
- `DP-A*`, `DP-T*`, `DP-R*`, `DP-S*`, `DP-K*`, `DP-C*`, `DP-X*`, `DP-F*`, `DP-Ch*` (06_data_plane)
- `MV-*`, `MV12-D*` (03_multiverse)
- `R*`, `S*`, `C*`, `SR*` (02_storage)
- `EM-*` (catalog/cat_09_EM_emergent — note: `EM-*` is taken; that is why event-model uses `EVT-*` not `EM-*`)
- `PL-*`, `WA-*`, `PO-*`, `NPC-*`, `PCS-*`, `SOC-*`, `NAR-*`, `EM-*`, `PLT-*`, `CC-*`, `DL-*` (catalog)

---

## Cross-folder references

This folder reads from and constrains:

| Folder | Relation |
|---|---|
| [06_data_plane/](../06_data_plane/) | LOCKED. Event Model uses DP transport but does NOT modify any DP-A* / DP-T* / DP-R* / DP-K* / DP-C* / DP-X* / DP-F* / DP-Ch*. |
| [05_llm_safety/](../05_llm_safety/) | A3 World Oracle, A5 intent classifier, A6 injection defense — all are validators in the EVT-V* pipeline. Event Model agent must NOT redesign these — instead, slot them into the pipeline. |
| [03_multiverse/](../03_multiverse/) | Canon promotion is an event category; canon layering shapes replay semantics. |
| [02_storage/](../02_storage/) | R7 single-writer-per-session, S* event-log shape — Event Model relies on these unchanged. |
| [features/](../features/) | Each feature picks event types from the EVT-T* taxonomy + producer roles from EVT-P*. PL_001 (committed) currently references events inline — will be reconciled when EVT-T* lands. |

---

## Pending splits

None — Phase 1 files all under 500-line soft cap.

---

## Phase 1 lock summary (2026-04-25)

**Locked decisions** (per Phase 0 boundary questions B1-B6 + Phase 1 axiom drafting, user-approved 2026-04-25):

| Decision | Resolution |
|---|---|
| B1 — TurnBoundary placement | A: wire-format SystemEvent (EVT-T4), payload IS PlayerTurn/NPCTurn/NPCRoutine/WorldTick |
| B2 — PlayerTurn vs NPCTurn | A: SPLIT (EVT-T1 + EVT-T2) — different producers + different validator chains |
| B3 — AggregateMutation | A: KEEP own category (EVT-T3) — each `t2_write` commits separate channel event |
| B4 — CalibrationEvent producer | A: world-service derives (EVT-T7) — DP stays content-agnostic |
| B5 — LLMProposal as taxonomy row | A: INCLUDE (EVT-T6) — lifecycle stage observable + validator pipeline operates on it |
| B6 — CanonPromotion | B: EXCLUDE — multiverse-scoped, owned by 03_multiverse + meta-worker; revisit if DF3 lands |
| Phase 4 sub-split | accept §5 plan; may split Phase 4 into 4a/4b if file size grows |

**Lock criterion satisfied:** the closed-set property is proven (every event from PL_001 + 22 SPIKE_01 observations + DP-emitted canonical events maps to exactly one EVT-T*). Feature authors can cite EVT-A* / EVT-T* IDs in subsequent feature docs starting now.

**Next:** Phase 2 — producer rules + per-category contracts. Will be commissioned after main session acknowledges Phase 1 lock.
