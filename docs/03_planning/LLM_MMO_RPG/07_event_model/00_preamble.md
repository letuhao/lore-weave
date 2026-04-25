# 00 — Preamble: Why 07_event_model Exists

> **Status:** LOCKED (foundation). Do not edit substance without reopening decision in [`99_open_questions.md`](99_open_questions.md) first.
> **Scope:** Context, motivation, and relation to neighboring folders. No new requirements live here — only framing.

---

## 1. The semantic gap above the data plane

[`06_data_plane/`](../06_data_plane/) (LOCKED 2026-04-25) defines how all per-reality kernel state is read and written: tier taxonomy, channel hierarchy, ordering invariants, capability tokens, durable subscribe, bubble-up aggregators, turn slots. **DP guarantees a totally-ordered durable event stream per channel.** It does NOT define:

1. **What kinds of events exist** (event taxonomy)
2. **Who is allowed to produce each kind** (producer rules)
3. **What validators run before commit, in which order** (validator pipeline)
4. **The LLM proposal bus protocol** (DP-A6 explicitly defers this)
5. **How fiction-time-triggered events get scheduled** (siege starts day X-thu-1257)
6. **The schema for "event B caused by event A"** (causal references)
7. **Replay semantics** (session catch-up vs canon-promotion vs debug replay)
8. **Schema versioning + migration** (DP-K3 has the error variant; protocol unspecified)

This folder fills that gap.

The metaphor: **DP is "TCP/IP for game state". 07_event_model is "HTTP semantic on top".** DP guarantees ordered byte delivery; Event Model defines what types of messages exist and how they're processed.

---

## 2. Why this folder exists, concretely

The first feature consuming events — [`PL_001_continuum.md`](../features/04_play_loop/PL_001_continuum.md), committed 2026-04-25 — treats "events" as a primitive concept inherited from DP. It mentions `TurnEvent`, `MembershipEvent`, `BubbleUpEvent`, `AmbientEvent`, `ActorBindingDelta::MoveTo`, `FictionClockAdvance`, calibration events, and at least 5 other shapes — but has no shared taxonomy to anchor them.

Without this folder:

- Every feature reinvents event types with overlapping/conflicting names
- Producer roles drift (does roleplay-service write directly? Does world-service?)
- Validator order is ad-hoc per feature → inconsistent canon discipline
- LLM proposal bus stays a hand-wavy "Python emits, Rust consumes" → blocks roleplay-service implementation
- Scheduled canon events (siege day X) have no producer assigned
- "Event B caused by event A" gets reinvented per feature (bubble-up uses one shape, quest-beat uses another)
- Replay across session catch-up + canon promotion + debug stays a forever-deferred hard problem

With this folder, every feature picks event types from EVT-T* taxonomy, cites EVT-P* producer rules, defers to EVT-V* validator pipeline, follows EVT-S* schema versioning. Feature designers spend their attention on the feature's domain, not on relitigating the substrate.

---

## 3. What this folder is NOT

- **NOT a redesign of DP.** Every DP-A* / DP-T* / DP-R* / DP-K* / DP-C* / DP-X* / DP-F* / DP-Ch* axiom is LOCKED and immutable from this folder's perspective. If a real conflict surfaces, it goes into [`99_open_questions.md`](99_open_questions.md) for user escalation — never silent workaround.
- **NOT a feature design.** Each feature in [`features/<category>/`](../features/) declares its own event sub-types within an EVT-T* category. This folder defines the TAXONOMY (top-level categories) and CONTRACT SHAPE (envelope + lifecycle), not every NPC dialog line type or every quest beat type.
- **NOT a redesign of LLM safety.** [`05_llm_safety/`](../05_llm_safety/) already locked A3 (World Oracle), A5-D1 (3-intent classifier), A5 (command dispatch), A6 (5-layer injection defense). Event Model SLOTS those into the validator pipeline; it does NOT redesign them.
- **NOT a redesign of canon promotion.** [`03_multiverse/`](../03_multiverse/) owns L1/L2/L3/L4 canon layering and the L3 → L2 canonization flow (DF3, V2+). Event Model respects the layering; it does not own the promotion mechanism.
- **NOT a redesign of storage.** [`02_storage/`](../02_storage/) (locked R*/S*/C*/SR* items) owns event-log durability, outbox pattern, projection rebuild, single-writer per session. Event Model consumes those unchanged.
- **NOT implementation code.** No Rust, Python, TypeScript. Diagrams in markdown text or mermaid; no images.
- **NOT V1 alone — designed for V1, V1+30d, V2+ together.** V1 paused-when-solo; V1+30d adds NPCRoutine + WorldTick; V2+ adds CanonPromotion through DF3. Taxonomy locks now to avoid retrofit.

---

## 4. Relation to neighboring folders

| Folder | How this folder depends on it | How this folder constrains it |
|---|---|---|
| [`06_data_plane/`](../06_data_plane/) | LOCKED. Every EVT-T* event commits via a DP primitive (`advance_turn`, `t2_write`, `t3_write`, aggregator runtime). Causal-ref shape extends DP-A15. Replay sits on DP-K6 `subscribe_channel_events_durable`. | None — DP is the boundary. Event Model is layered above. |
| [`05_llm_safety/`](../05_llm_safety/) | A3 World Oracle, A5-D1 intent classifier, A5 command dispatch, A6 5-layer injection defense are validators in EVT-V* pipeline. | Validator pipeline ordering + fail-mode is owned here; A3/A5/A6 internals stay in 05_llm_safety. |
| [`03_multiverse/`](../03_multiverse/) | Canon layering (L1/L2/L3/L4) shapes which events can be CanonPromotion candidates. SEVERED marker (DF14) affects replay filtering. | None — Event Model classifies promotion mechanism, doesn't own it. |
| [`02_storage/`](../02_storage/) | I13 outbox pattern is the LLM-proposal-bus + cross-service event mechanism. I14 schema additivity is the EVT-S* baseline. R7 single-writer-per-session is preserved. | None — storage is fully consumed unchanged. |
| [`00_foundation/`](../00_foundation/) | I1..I19 invariants apply. Especially I10 (prompt assembly through `contracts/prompt/`), I13 (outbox), I14 (additive schema). Vocabulary (turn states, presence states, intent classes, canon layers) is reused; not redefined. | None — Event Model is downstream of foundation. |
| [`features/`](../features/) | Features pick EVT-T* + EVT-P* + EVT-V* contracts. PL_001 currently inlines event shapes; will be reconciled when EVT-T* locks. | Every feature must cite EVT-T* for each event it emits or consumes. Every feature design review checks the EVT-V* pipeline applies. Catalog references EVT-* IDs once locked. |
| [`decisions/locked_decisions.md`](../decisions/locked_decisions.md) | MV12-D1..D7 (page-turn fiction-time) shape WorldTick + CalibrationEvent design. MV12-D8..D11 are CANDIDATE decisions Event Model resolves. | New EVT-* decisions land here as `EVT-A*-Dn` rows. |

---

## 5. Conversation trail that produced this folder

Captured here so future sessions see the constraints, not as things to revisit.

- **PL_001 commit `b4ea611`** (2026-04-25) was the first feature consuming events. During its design, the agent observed events as primitive — but DP only locks ordering + delivery, not shape or lifecycle. Gap analysis confirmed taxonomy + producer rules + validator pipeline + LLM bus protocol were genuinely not designed.
- **User decision: design Event Model fully (Phase 1-5) before resuming feature work.** Rationale: every feature built on undocumented event semantics will need rework when the rules eventually crystallize. Hobby-project no-deadline pressure tilts toward upfront design over implementation refactor.
- **Sequencing locked:** Phase 1 (Boundary + Axioms + Taxonomy) → Phase 2 (Producers + Contracts) → Phase 3 (Validator + LLM Bus) → Phase 4 (Scheduling + Causal + Replay + Versioning) → Phase 5 (Quickstart). Each phase has a LOCK ceremony before the next begins.
- **Stable-ID namespace `EVT-*`** chosen because `EM-*` is taken by `cat_09_EM_emergent` (catalog feature ID).
- **Boundary questions B1-B6 resolved 2026-04-25** in Phase 0 POST-REVIEW:
  - B1: TurnBoundary = wire-format of PlayerTurn/NPCTurn (NOT a separate category)
  - B2: PlayerTurn + NPCTurn split (different producers + different validator chains)
  - B3: AggregateMutation kept as own category (each `t2_write` commits separate channel event)
  - B4: CalibrationEvent producer = world-service derives (DP must stay content-agnostic)
  - B5: LLMProposal included as taxonomy row (lifecycle stage observable)
  - B6: CanonPromotion EXCLUDED from taxonomy (multiverse-scope, owned by 03_multiverse + meta-worker; can revisit if DF3 lands)

These decisions are locked at the axiom and taxonomy level in [`02_invariants.md`](02_invariants.md) and [`03_event_taxonomy.md`](03_event_taxonomy.md). Changes require an entry in [`99_open_questions.md`](99_open_questions.md) and a superseding decision row in [`../decisions/locked_decisions.md`](../decisions/locked_decisions.md).
