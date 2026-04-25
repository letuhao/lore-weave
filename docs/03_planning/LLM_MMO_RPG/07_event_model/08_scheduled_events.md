# 08 — Scheduled Events Framework

> **Status:** LOCKED Phase 4 (Option C discipline 2026-04-25). Per [EVT-T5 Generated](03_event_taxonomy.md#evt-t5--generated) sub-class **Scheduler**, this file specifies the **scheduler framework** for fiction-time-triggered events (Scheduled:NPCRoutine / Scheduled:WorldTick / Scheduled:QuestTrigger / future). Mechanism-only — specific scheduler implementations live in feature designs (world-rule-scheduler V1+30d, future quest-engine).
> **Stable IDs:** EVT-L7..EVT-L11. Continuation of EVT-L* lifecycle namespace from `07_llm_proposal_bus.md`.
> **V1 status:** **placeholder.** No scheduler emits in V1 (V1 paused-when-solo per MV12-D4). Framework reserved for V1+30d activation when world-rule-scheduler service ships.
> **Resolves:** [EVT-Q4](99_open_questions.md) (CalibrationEvent emission ordering) + [EVT-Q8](99_open_questions.md) (idempotency key for WorldTick / NPCRoutine across big jumps) + MV12-D10 deferral.

---

## How to use this file

When implementing a scheduler-based feature (V1+30d world-rule-scheduler; future quest-engine):

1. Confirm your service plays the **Generator role** with `produce: [Generated]` JWT claim per [EVT-P5](04_producer_rules.md#evt-p5--generated-evt-t5).
2. Honor [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25) — wall-clock + non-deterministic sources forbidden.
3. Subscribe to **trigger source events** per EVT-L7 (CalibrationEvent / Scheduled-Beat aggregate).
4. Implement **idempotency for big-jumps** per EVT-L9 — fast-forward crossing N thresholds fires N events exactly once each.
5. Implement **recovery on restart** per EVT-L10 — missed beats during downtime fire on resume in fiction-chronological order.
6. Register your Generator sub-type in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md) per [EVT-A11](02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25).

Specific scheduler implementations (V1+30d world-rule-scheduler service shape, future quest-engine) live in their owning feature designs. This file specifies the **framework**.

---

## EVT-L7 — Scheduler trigger sources

**Rule:** Schedulers fire on **two trigger sources only**: (a) **CalibrationEvent stream** (EVT-T3 Derived sub-type DayPasses / MonthPasses / YearPasses) for fiction-date-boundary-aligned beats; (b) **fiction-time-threshold check** on EVT-T3 Derived `aggregate_type=fiction_clock` advance for arbitrary-fiction-time-aligned beats. **No wall-clock cron**, no external trigger sources. Both sources are fully deterministic per [EVT-A9](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25).

**Trigger source (a) — CalibrationEvent stream:**
- Scheduler subscribes via `dp::subscribe_channel_events_durable<CalibrationEvent>` per DP-K6.
- Each calibration event triggers re-evaluation of pending beats matched to date-boundary thresholds.
- Use case: "siege starts on day 1257-thu-3" — declare beat with trigger `date_match: "1257-thu-3 00:00"`; fires when DayPasses crosses that boundary.

**Trigger source (b) — FictionClockAdvance check:**
- Scheduler subscribes via `dp::subscribe_channel_events_durable<FictionClockAdvance>` (same DP-K6 mechanism).
- On each advance, scheduler checks pending beats with sub-day-precision thresholds.
- Use case: "NPC opens shutters at giờ Mão sơ" — declare routine with trigger `fiction_time_match: "Mão sơ"`; fires when FictionClock advance crosses that sub-day phase.

**Why two sources, not one:** trigger source (a) is fiction-date-aligned and natural for slow-cadence beats (siege day, festival, season change). Trigger source (b) is sub-day-aligned and natural for routine NPC behavior (dawn shutters, noon meal, dusk return). Combined, they cover the full fiction-time granularity DP supports.

**Forbidden trigger sources:** wall-clock time, system entropy, external HTTP polls, message queues outside DP. All would break replay determinism.

**Cross-ref:** [DP-K6 durable subscribe](../06_data_plane/04c_subscribe_and_macros.md#dp-k6--subscription-primitives), [EVT-T3 Derived calibration sub-shapes](03_event_taxonomy.md#evt-t3--derived), [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25).

---

## EVT-L8 — Beat declaration registry

**Rule:** Each scheduled beat is declared in a **per-reality registry aggregate** owned by the scheduler service. Beat declaration carries: `beat_id` (UUID, stable across schedule mutations); `trigger_specification` (CalibrationEvent date-match OR FictionClockAdvance threshold); `target_channel` (where to commit the resulting Generated event); `payload_template` (feature-defined per scheduler sub-type); `probability` (optional, 0.0..1.0; uses RNG per EVT-A9 if <1.0); `lifecycle_state` (Pending / Fired / Cancelled).

**Schedule mutation:** authors edit beats via Forge (WA_003) — Forge emits EVT-T8 Administrative; scheduler's beat registry is the consumed aggregate. Mutations create NEW `beat_id` (additive); editing in-place forbidden to prevent double-fire across schedule edits.

**Beat identity discipline:** `beat_id` is stable. If author moves "siege day" from 1257-thu-3 to 1257-thu-15, that's a NEW beat_id (the original beat_id stays as Cancelled in the registry). This prevents "is this the original beat or the moved one?" ambiguity in replay.

**Why per-reality registry:** scheduled beats are reality-scoped (a siege in reality A doesn't affect reality B). Registry aggregate fits naturally as RealityScoped T2 per DP-A14.

**Why additive mutation:** the alternative (mutate in-place) would break replay determinism — replaying the event log would re-fire the OLD beat_id at OLD threshold, which no longer exists. Additive mutation preserves history.

**Cross-ref:** [WA_003 Forge](../features/02_world_authoring/WA_003_forge.md), [EVT-A11 sub-type ownership](02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25), [DP-A14 aggregate scope](../06_data_plane/02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25).

---

## EVT-L9 — Big-jump idempotency (resolves EVT-Q8)

**Rule:** When a fast-forward (PCTurn::FastForward `/sleep` or `/travel`) advances FictionClock by a duration that crosses **N beat thresholds**, the scheduler fires **N Generated events**, exactly once each, in **fiction-chronological order**.

**Idempotency key composition:** `(producer="<scheduler-service>", reality_id, beat_id, fired_at_fiction_ts)` per Phase 0 EVT-Q8 default. Components:
- `beat_id` — the stable beat declaration ID (per EVT-L8)
- `fired_at_fiction_ts` — the exact fiction-time when this firing crossed the threshold (DayPasses target date, or FictionClockAdvance threshold-cross fiction_ts)

The composite ensures: same beat firing on same threshold-crossing = same idempotency key = same canonical event_id (DP commit dedup). Big-jump replay re-derives the same N firings.

**Worst-case example (per SPIKE_01 turn 16):** PC `/travel 23 days` from 1256-thu-3 to 1256-thu-26 crosses 23 day-boundaries + 1 month-boundary. Scheduler subscribes to CalibrationEvent stream → consumes 23 DayPasses + 1 MonthPasses → checks pending beats against each → fires N matching beats. Each beat fires with its unique `(beat_id, fired_at_fiction_ts)` key.

**Trigger ordering:** scheduler emits in **strictly fiction-chronological order** — a beat at day 5 fires before a beat at day 10 even if both cross during the same FastForward. This preserves causal coherence (a quest trigger that depends on weather change must fire AFTER the weather change).

**Why composite key:** simpler keys like `(scheduler, beat_id)` would prevent re-firing on schedule resumption (after pause/cancel/edit cycles). Including `fired_at_fiction_ts` lets the same beat_id fire at multiple fiction-times if its trigger spec is recurring (e.g., "every dawn"); each firing has unique key.

**Cross-ref:** [EVT-Q8 idempotency for WorldTick/NPCRoutine](99_open_questions.md), uniform idempotency-key shape ([EVT-P*](04_producer_rules.md)), [DP-A15 per-channel ordering](../06_data_plane/02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25).

---

## EVT-L10 — Recovery on scheduler restart

**Rule:** When the scheduler service restarts after downtime, it MUST **fire all missed beats** that crossed thresholds during the downtime window, in fiction-chronological order, before resuming live operation. Idempotency (EVT-L9) ensures duplicate fires from pre-restart inflight don't double-commit.

**Recovery sequence:**
1. On restart, scheduler queries beat registry for `(lifecycle_state = Pending OR Fired) AND last_evaluated_fiction_ts < current_fiction_clock`.
2. For each missed beat, scheduler re-runs trigger evaluation against the CalibrationEvent + FictionClockAdvance stream replay (from last-evaluated cursor).
3. If trigger spec matches, scheduler fires the beat with composite idempotency key per EVT-L9.
4. Idempotency dedup at DP commit layer: if the beat already fired pre-restart (cached event_id), commit returns the existing event_id and skips re-execution.
5. After replay catches up, scheduler advances `last_evaluated_fiction_ts` and resumes live operation.

**Bounded recovery cost:** missed beats during a 6-hour wall-clock downtime are bounded by the fiction-clock advance during that window. V1 paused-when-solo means fiction-clock barely advances during scheduler downtime (only PC turns advance it). V1+30d pure-scheduled mode may advance fiction-clock autonomously — recovery cost scales with that advance rate; specific bounds are operational.

**Why fire-on-resume vs skip-on-restart:** skipping missed beats would create silent canon corruption — the world state would diverge from "events that should have happened by fiction-time T". Firing on resume preserves canon integrity at the cost of brief recovery latency.

**Cross-ref:** [EVT-L9 big-jump idempotency](#evt-l9--big-jump-idempotency-resolves-evt-q8), I13 outbox replay semantics.

---

## EVT-L11 — Phasing (V1 / V1+30d / V2+)

**Rule:** Scheduler activation phased per [MV12-D6 V1/V2/V3 split](../decisions/locked_decisions.md):

**V1 (paused-when-solo):**
- Scheduler service NOT deployed.
- No EVT-T5 Generated/Scheduled:* events emit.
- Fiction-clock advances ONLY on PC turn submission.
- Beat registry MAY exist (for author-side declaration via Forge) but no beats fire.

**V1+30d (scheduled-canon-events activated):**
- world-rule-scheduler service deployed.
- Subscribes to CalibrationEvent + FictionClockAdvance streams.
- Fires Scheduled:WorldTick + Scheduled:NPCRoutine beats per registered declarations.
- Probabilistic beats use deterministic RNG per EVT-A9.

**V2+ (per-tier autonomous):**
- Scheduler additionally fires periodic-tick beats per S6 cost model + SR8 capacity tier.
- Free tier: paused-when-solo.
- Paid tier: scheduled-canon-events only.
- Premium tier: periodic autonomous tick (every-N-minute fiction-time advance even with 0 PCs).

**MV12-D10 resolution:** "NPC-only routine scenes happening in the cell while PC is asleep" — answer: in V1, NO (paused-when-solo means NPC routines don't fire when PC is offline). In V1+30d, YES (scheduler fires NPCRoutine beats based on fiction-clock advance regardless of PC presence; routine narration when no PC observes is flavor per [EVT-A8](02_invariants.md#evt-a8--non-canonical-regenerable-content-is-not-events-reframed-2026-04-25), only structural deltas commit).

**Cross-ref:** [MV12-D6](../decisions/locked_decisions.md), [MV12-D10 deferral](99_open_questions.md), [MV12-D4 V1 paused-when-solo](../decisions/locked_decisions.md), S6 cost model.

---

## Locked-decision summary

| ID | Short name | One-line |
|---|---|---|
| EVT-L7 | Scheduler trigger sources | CalibrationEvent stream + FictionClockAdvance check; NO wall-clock or external triggers (replay-deterministic) |
| EVT-L8 | Beat declaration registry | Per-reality T2 aggregate; beat_id stable; mutations are additive (NEW beat_id, OLD as Cancelled) |
| EVT-L9 | Big-jump idempotency (EVT-Q8 resolved) | Composite key `(scheduler, reality_id, beat_id, fired_at_fiction_ts)`; N threshold crossings → N firings |
| EVT-L10 | Recovery on scheduler restart | Fire missed beats in fiction-chronological order; idempotency dedup catches duplicates |
| EVT-L11 | Phasing (MV12-D6 + D10 resolved) | V1 no scheduler; V1+30d scheduled-canon-events; V2+ per-tier autonomous tick |

---

## Cross-references

- [EVT-T5 Generated](03_event_taxonomy.md#evt-t5--generated) — category this scheduler emits to
- [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25) — applies to all scheduler probability gates
- [EVT-P5 Generator producer rule](04_producer_rules.md#evt-p5--generated-evt-t5) — scheduler is a Generator role sub-class
- [`09_causal_references.md`](09_causal_references.md) — scheduler beats reference triggering CalibrationEvent / FictionClockAdvance via causal_refs
- [`10_replay_semantics.md`](10_replay_semantics.md) — EVT-L10 recovery is a replay use case
- [DP-K6 durable subscribe](../06_data_plane/04c_subscribe_and_macros.md#dp-k6--subscription-primitives) — trigger source subscription
- [DP-A14 aggregate scope](../06_data_plane/02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25) — per-reality registry scope
- [WA_003 Forge](../features/02_world_authoring/WA_003_forge.md) — author UI for editing beats
- [MV12-D4 / D6 / D10](../decisions/locked_decisions.md) — fiction-time + scheduler phasing decisions
- Future world-rule-scheduler feature design (V1+30d) — concrete service implementation
- Future quest-engine feature design — Scheduled:QuestTrigger sub-type owner
