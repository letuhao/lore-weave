# 12 — Generation Framework (EVT-G*)

> **Status:** LOCKED Phase 6 (Option C closure follow-up, 2026-04-25 late evening). Per [EVT-A12 extensibility framework](02_invariants.md#evt-a12--extensibility-framework-new-2026-04-25) extension point (f) "new generation rule", this file specifies the **systematic management framework** for event-emitting logic — registry, trigger source taxonomy, cycle detection, capacity governance, coordinator service spec, extension procedure.
> **Stable IDs:** EVT-G1..EVT-G6. New prefix `EVT-G*` reserved 2026-04-25 (registered in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md)).
> **Why a new file post-closure:** the original Phase 5 closure noted "all Phase deferrals resolved", but user identified a **systematic management gap** for event generation that the existing axiom layer (EVT-A9 + EVT-A12) implicitly required but didn't operationalize. Phase 6 fills that gap at framework level (no new service binary; coordinator is logical role).
> **Realizes original goal #4** ("generate event theo điều kiện + xác suất") at systematic level.

---

## 1. Why this framework exists

After Phase 5 closure, the user surfaced 6 failure modes that fragmented per-feature generation would hit:

1. **Race conditions** — two generators fire on same trigger with conflicting output
2. **Cycle bombs** — Generator A → Generator B → Generator A loops infinitely (DP-Ch29 caps cascade depth for bubble-up only; cross-feature cycles unaddressed)
3. **Replay corruption** — feature dev forgets `dp::deterministic_rng`, uses `rand::thread_rng()` → silent canon drift on replay (violates EVT-A9 silently)
4. **Cost runaway** — feature adds generator firing 1000/s → reality DB flooded; no per-generator capacity governance
5. **Discovery hell** — no central registry; debug "what caused this event?" requires full codebase search
6. **Capacity governance gap** — DP-S* covers DP-level capacity; per-generator emit-rate ceiling has no home

This framework operates at **mechanism level** (not new service binary) — coordinator is a **logical role** within the existing channel-writer process, mirroring how DP-Ch26 runs aggregators in-process. Zero new infrastructure; full systematic governance.

**Categorization clarification:** "Generator" here means any registered emitter that produces an EVT-T5 Generated event (or rare EVT-T3 Derived from state-threshold sources). Generators include: bubble-up aggregators (DP-Ch28 pattern), schedulers (08_scheduled_events.md EVT-L7..L11), future combat damage RNG, future loot drop RNG, future weather drift, future faction reputation drift, future quest-trigger evaluators.

---

## EVT-G1 — Generator Registry as first-class concept

**Rule:** Every generator (emitter producing EVT-T5 Generated or specific state-threshold-derived EVT-T3) MUST be **registered** in a unified Generator Registry. The registry has two views:

**Declarative SSOT** (boundary-coordinated, lock-gated):
- Source of truth for "what generators exist" — registered in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md) Generator-rows section.
- Each entry declares: `logical_id` + `registry_uuid` + `trigger_sources` + `output_category` + `output_sub_type` + `rng_seed_strategy` + `capacity_ceiling` + `owner_service`.
- Boundary lock-gated; concurrent feature designs cannot accidentally co-author a generator.

**Runtime registry** (loaded by coordinator at startup):
- Coordinator loads declarative SSOT entries on boot, validates them (cycle detection per EVT-G3, RNG determinism per EVT-A9).
- Subscribes to trigger sources on behalf of registered generators.
- Maintains in-memory dispatch table per channel-writer process.

### Generator declaration shape

| Field | Type | Required | Purpose |
|---|---|:---:|---|
| `logical_id` | composite `(feature_owner, sub_type)` | ✅ | Human-readable — e.g., `gossip:RumorBubble`, `world-rule-scheduler:NPCRoutine`, `combat:DamageRoll`. Registered in boundary matrix. |
| `registry_uuid` | UUID derived as `blake3(logical_id)` | ✅ | Auto-derived deterministically; replay-safe runtime key. Never authored manually. |
| `trigger_sources` | `Vec<TriggerSourceDecl>` per [EVT-G2](#evt-g2--trigger-source-taxonomy) | ✅ (≥1) | What events / state thresholds / time markers cause this generator to evaluate |
| `output_category` | `EvtCategory` enum | ✅ | Typically `Generated` (EVT-T5); rare `Derived` (EVT-T3) for state-threshold sources |
| `output_sub_type` | String | ✅ | Sub-type the generator emits (registered in `_boundaries/` per EVT-A11) |
| `rng_seed_strategy` | enum: `DeterministicCausalRef` \| `Stateless` \| `StateChecksum` | ✅ | How RNG is seeded per [EVT-A9](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25). `Stateless` = no RNG used (purely conditional). |
| `capacity_ceiling` | `EmitRateLimit { per_second, per_minute, burst }` | ✅ | Per [EVT-G4](#evt-g4--per-generator-capacity-governance) — feature-declared ceiling |
| `owner_service` | String | ✅ | Service-account name; matches `_boundaries/01_feature_ownership_matrix.md` |
| `replay_test_corpus_ref` | String (optional) | optional | Path to test corpus for replay-correctness CI gate (per [EVT-S5](11_schema_versioning.md#evt-s5--replay-against-migrated-schemas)) |

### Why composite logical_id + UUID

- **logical_id** = composite `(feature_owner, sub_type)` for human readability — debug logs, audit traces, ownership attribution all use this.
- **registry_uuid** = `blake3(logical_id)` for runtime collision-proof keying without manual UUID authoring.

This satisfies D6.2 (both schemes from Phase 6 sub-decisions): composite for design/debug; UUID for runtime registry key.

### Registry update flow

1. Feature design declares new generator in feature doc
2. Author claims `_boundaries/_LOCK.md`
3. Adds entry to `_boundaries/01_feature_ownership_matrix.md` Generator-rows
4. Boundary review checks ownership uniqueness + trigger source validity + RNG strategy
5. Lock-release
6. Feature implements generator code; coordinator loads entry on next deploy

**Forbidden:** generators that exist in code but NOT in registry (would bypass cycle detection + capacity governance + discovery). Lint/CI step (Phase 6+ ops) verifies code-side generator instantiations match registry entries.

**Cross-ref:** [EVT-A11 sub-type ownership](02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25), [EVT-A12 extensibility (f)](02_invariants.md#evt-a12--extensibility-framework-new-2026-04-25), [DP-Ch28 aggregator registry pattern](../06_data_plane/16_bubble_up_aggregator.md#dp-ch28--cp-aggregator-registry).

---

## EVT-G2 — Trigger source taxonomy

**Rule:** Trigger sources are a **closed set of 5 typed kinds**. New sources require axiom-level decision (similar to new EVT-T* category — extension point (b) of EVT-A12).

### The 5 trigger source kinds

| # | Kind | Subscribed via | Use case |
|---|---|---|---|
| **(a)** | `CommittedEventOf { category, sub_type_filter? }` | `dp::subscribe_channel_events_durable<E>` (DP-K6) per channel | bubble-up consumes Submitted events at descendant; reputation aggregator consumes Generated events |
| **(b)** | `StateThresholdOn { aggregate_type, predicate }` | projection-update notification + predicate evaluation | weather drift fires when humidity aggregate crosses threshold; quest trigger fires when NPC mood crosses hostile threshold |
| **(c)** | `FictionTimeMarker { calibration_kind \| fiction_ts_match }` | `dp::subscribe_channel_events_durable<CalibrationEvent>` + FictionClockAdvance check (per [EVT-L7](08_scheduled_events.md#evt-l7--scheduler-trigger-sources)) | scheduled NPC routines (dawn shutters); WorldTick beats (siege day X) |
| **(d)** | `OtherGeneratorOutput { generator_logical_id }` | DP-K6 subscribe to the upstream generator's output channel | cascade: gossip rumor at tavern triggers reputation-drift at country level |
| **(e)** | `LifecycleMarker { system_event_sub_type }` | DP-K6 subscribe filtered by EVT-T4 System sub-type | scheduler activates on RealityActivated; cleanup generator on ChannelDissolved |

### Closed-set proof

Every generator currently designed (DP-Ch28 bubble-up + 08 scheduled events) maps to one of (a) / (c). Future generators (combat damage, loot drops, weather drift, quest triggers, faction reputation) map to (a) / (b) / (c) / (d). Cross-feature cascades use (d). System lifecycle hooks use (e).

**Forbidden trigger sources** (per EVT-A9 RNG determinism):
- Wall-clock time
- System entropy
- External HTTP polls
- Message queues outside DP / proposal bus
- Random external services

All would break replay determinism. If a feature genuinely needs an external trigger, it MUST be wrapped in an EVT-T1 Submitted event (operator-emitted) first; the generator subscribes to that as kind (a).

### Trigger source declaration shape

Each entry in `trigger_sources: Vec<TriggerSourceDecl>` is one of the 5 kinds above with kind-specific fields. Generator may have multiple trigger sources (any of which fires causes evaluation). Multi-source uses inclusive-OR semantics at evaluation: any matched source triggers `on_event`; the generator's own logic decides whether to emit.

**Cross-ref:** [EVT-L7 scheduled trigger sources](08_scheduled_events.md#evt-l7--scheduler-trigger-sources) (subset case (c) and (a)), [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25), [DP-K6 subscribe](../06_data_plane/04c_subscribe_and_macros.md#dp-k6--subscription-primitives).

---

## EVT-G3 — Cycle detection (static + runtime)

**Rule:** Cycles in the Generator-to-Generator graph are FORBIDDEN. Detection runs at **two layers**:

### Static cycle detection (registration time)

When the coordinator loads the Generator Registry on startup (or receives a delta from boundary matrix update via CP):

1. Build directed graph: for each generator G with trigger source kind (d) `OtherGeneratorOutput { upstream_id }`, add edge `upstream → G`.
2. Run topological sort.
3. If cycle detected → coordinator REFUSES to start (or refuses the new registration); operator alerted with cycle path; boundary review must resolve.

**Captures:** obvious cycles where Generator A subscribes to Generator B's output AND Generator B subscribes to Generator A's output. Static check is fast (registry size bounded — typically <100 generators per reality at V1+30d).

### Runtime cycle detection (dynamic cascade)

When generators emit events that trigger other generators (kind (a) or (d) trigger), the coordinator tracks **cascade depth** per causal chain:

1. Each Generated event carries an implicit `cascade_depth: u8` in coordinator-internal context (NOT in the event payload — derived from causal_refs walk if needed for audit).
2. When Generator G fires due to cascade, depth increments.
3. **Hard cap at 16** (matches [DP-Ch29 cascade prevention](../06_data_plane/16_bubble_up_aggregator.md#dp-ch29--cascading--loop-prevention-rules)).
4. Exceeds cap → emit REJECTED with `EventModelError::GeneratorCycleDetected { depth, chain }` audit-logged at SEV2.

**Captures:** dynamic cycles where conditional triggers create chains only at runtime (Generator A only sometimes triggers B; B only sometimes triggers A; under specific input combinations they form a cycle). Static check would miss these because the trigger-edge is conditional.

### Why both layers

Static catches obvious-by-design cycles cheaply at startup; runtime catches dynamic cycles arising from conditional logic. Defense-in-depth.

**Forbidden:** cycle-tolerant generators (no "loop until convergence" patterns); silent cycle suppression (must audit-log + reject).

**Cross-ref:** [DP-Ch29 cascade prevention](../06_data_plane/16_bubble_up_aggregator.md#dp-ch29--cascading--loop-prevention-rules) (V1 implementation pattern for bubble-up; EVT-G3 generalizes to all generators).

---

## EVT-G4 — Per-generator capacity governance

**Rule:** Every generator declares an **emit-rate ceiling** at registration time (per EVT-G1 `capacity_ceiling: EmitRateLimit { per_second, per_minute, burst }`). Coordinator enforces with **tiered policy** matching SR9 alert pattern:

| Utilization | Coordinator action | Audit |
|---|---|---|
| 0-49% of ceiling | normal dispatch | metrics only |
| 50-89% of ceiling | warn (log + metric `generator.capacity.warn`) | warn-level audit |
| 90-99% of ceiling | warn-page (SR9 pager-eligible alert) | warn-level audit |
| ≥100% of ceiling | **reject emit** with `EventModelError::GeneratorRateLimited { retry_after }` | SEV2 audit |

**Specific ceiling values:** feature-declared per generator (operational tunable). Default guidance:
- Bubble-up aggregators (high-frequency): ceiling per descendant event-rate × emit-probability
- Schedulers (sparse): ceiling per fiction-time-density × beat count
- Combat damage RNG: ceiling per turn-rate × actor count
- Loot drops: ceiling per encounter-rate

Specific numbers locked in operational ops doc when V1+30d ramps; framework specifies the **mechanism**.

**Backpressure propagation:** rejected emit propagates per [DP-R6 backpressure](../06_data_plane/11_access_pattern_rules.md#dp-r6--backpressure-propagation-not-swallow-and-retry) — caller (typically the trigger-source consumer loop) sees `Result<EmitDecision, GeneratorRateLimited>` and propagates upstream rather than swallowing.

**Why tiered (not just hard-reject):**
- Catches cost-runaway BEFORE it cascades (50% warn allows operator response before 100% reject)
- Avoids surprise-rejection cliffs that would create cascading retries in upstream consumers
- Matches existing SR9 alert tiers for operator UX consistency

**Capacity-budget audit:** `generator_capacity_budgets.yaml` (operational config) declared per-generator ceiling; CI lint enforces declarations match registry entries. Boundary review checks ceiling reasonableness vs documented use case.

**Forbidden:**
- Undeclared ceilings (forces explicit operator decision)
- Hard-reject-only enforcement (skips warn → no advance signal)
- Silent-drop on rate-limit (must audit)

**Cross-ref:** [DP-R6 backpressure propagation](../06_data_plane/11_access_pattern_rules.md#dp-r6--backpressure-propagation-not-swallow-and-retry), SR9 alert tiers, SR12 observability cost.

---

## EVT-G5 — Coordinator service responsibilities + deployment

**Rule:** A **Generator Coordinator** is a logical role that fulfills 7 responsibilities. Per Phase 6 D6.1 decision: deployment is **in-process per channel-writer** (matches DP-Ch26 aggregator pattern; no new service binary in V1).

### 7 coordinator responsibilities

| # | Responsibility | Mechanism |
|---|---|---|
| **1** | Registry view maintenance | On boot, load declarative SSOT entries (filtered to generators registered to channels owned by this writer per DP-A16). Receive delta updates from CP via channel-tree-delta-stream pattern (DP-Ch3). |
| **2** | Trigger source subscription | Coordinate per-trigger-source subscriptions on behalf of registered generators. **Deduplicate**: if 5 generators subscribe to the same `CommittedEventOf { category=Submitted }`, coordinator opens ONE DP-K6 subscription and fans out to all 5 generators in-process. Saves DP fan-out cost. |
| **3** | Dispatch | On trigger fire, evaluate which registered generators match the trigger declaration; invoke each generator's `on_event(trigger_event)` (per DP-Ch25 aggregator trait pattern). Generators run sequentially within coordinator's event loop (preserves per-channel ordering). |
| **4** | Cycle detection | Static at registration receipt (build graph, topological sort, reject cycles); runtime depth-counter (cap 16 per EVT-G3); audit-log + reject on cycle. |
| **5** | Capacity governance | Track per-generator emit rate via sliding window; enforce tiered limits per EVT-G4. |
| **6** | Determinism enforcement | At registration, verify `rng_seed_strategy` is declared (EVT-A9); CI lint catches code that bypasses `dp::deterministic_rng`. Replay-test corpus runs as CI gate. |
| **7** | Failure handling | Generator panic during `on_event` → coordinator catches, audit-logs, continues with other generators (matches DP-Ch26 panic-isolation). Generator timeout (>500ms default) → coordinator kills, audit. Channel-writer crash → coordinator state lost; recovers from Registry on restart. |

### Deployment model

**In-process per channel-writer:**
- Coordinator code is a Rust module within the channel-writer process (per [DP-A16 channel writer-node binding](../06_data_plane/02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25)).
- One coordinator instance per channel-writer process.
- Generators registered to channels owned by THIS writer execute here.
- Cross-writer cascade (Generator A in writer X emits event consumed by Generator B in writer Y) flows via DP commit + DP-K6 subscribe — coordinator-to-coordinator coordination is automatic (no special protocol).

**No separate service binary in V1** — coordinator is logical role, not deployment unit. V2+ may extract to dedicated service if measured load demands (operational decision; out of Phase 6 scope).

**Why in-process:**
- Generators ALREADY run in-process per DP-Ch26 (existing bubble-up aggregator runtime).
- Zero new service to deploy + maintain.
- Hot-path latency: trigger → coordinator → generator is a function call (microseconds), not network hop.
- Failure isolation: coordinator failure = channel-writer failure (which already has DP-Ch failover); no separate failure mode to manage.

### Failure modes spec

| Failure | Coordinator behavior | Recovery |
|---|---|---|
| Generator panic during `on_event` | catch, audit-log SEV3, continue with other generators | next trigger fire retries; persistent panics escalate to operator review |
| Generator timeout (>500ms default) | kill task, audit-log SEV2 | next trigger; ceiling tunable per generator |
| Channel-writer crash | coordinator state lost (in-memory) | on restart: re-load Registry from boundary matrix + re-subscribe to triggers; in-flight emits lost (acceptable per DP-A11 T1 30s loss window for transient state) |
| Registry corruption (boundary matrix unreadable) | coordinator REFUSES to start | operator intervention; alert at SEV1 |
| Trigger source backpressure | coordinator propagates per DP-R6; generators see `RateLimited` | upstream consumer handles |
| Cycle detected at startup | coordinator REFUSES to start; alerts operator with cycle path | boundary review must resolve before re-deploy |
| Cycle detected at runtime (depth > 16) | reject emit; audit-log SEV2; alert operator | feature design review for offending chain |

### Boundary with DP

| DP owns | Coordinator owns |
|---|---|
| DP-Ch25..Ch30 bubble-up aggregator runtime (single-aggregator focus) | Generalized generator runtime (all 5 trigger source kinds; multi-generator coordination) |
| DP-Ch28 CP aggregator registry (bubble-up specific) | Coordinator-level Registry view per channel-writer (general-purpose) |
| DP-K6 durable subscribe primitive | Subscription deduplication across registered generators |
| DP-A16 channel writer-node binding | In-process coordinator instance binding |

Coordinator does NOT modify DP — it COMPOSES DP primitives. EVT-A2 invariant preserved.

**Cross-ref:** [DP-A16 channel writer-node binding](../06_data_plane/02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25), [DP-Ch26 aggregator runtime](../06_data_plane/16_bubble_up_aggregator.md#dp-ch26--aggregator-runtime-loop), [DP-Ch28 aggregator registry](../06_data_plane/16_bubble_up_aggregator.md#dp-ch28--cp-aggregator-registry), DP-Ch3 CP channel-tree-delta-stream pattern.

---

## EVT-G6 — Extension procedure (adding a new generator)

**Rule:** Adding a new generator follows a **6-step procedure**. CI gates enforce each step before deploy.

### The 6 steps

1. **Declare in feature design doc** — generator's purpose, trigger sources (one of EVT-G2 5 kinds), output category + sub-type, RNG strategy, capacity ceiling rationale.

2. **Register ownership** in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md) Generator-rows (claim `_boundaries/_LOCK.md` first per `_boundaries/00_README.md`):
   ```
   logical_id: <feature_owner:sub_type>
   registry_uuid: <auto-derived blake3(logical_id)>
   trigger_sources: [<TriggerSourceDecl per EVT-G2>]
   output_category: Generated  | Derived (rare)
   output_sub_type: <feature-defined>
   rng_seed_strategy: DeterministicCausalRef | Stateless | StateChecksum
   capacity_ceiling: { per_second, per_minute, burst }
   owner_service: <service-account name>
   replay_test_corpus_ref: <path-or-omit>
   ```

3. **Implement generator code** in feature crate — `impl Generator for <YourGenerator>` (per DP-Ch25 trait pattern, generalized for non-bubble-up cases).
   - MUST use `dp::deterministic_rng(channel_id, channel_event_id)` for any randomness (EVT-A9).
   - MUST emit via correct DP primitive (`dp::t2_write` for T5/T3 typically).
   - MUST honor capacity_ceiling — coordinator enforces but generator should self-throttle when feasible.

4. **Boundary review** — reviewer checks:
   - Ownership unique (no duplicate logical_id)
   - Trigger sources valid (in EVT-G2 closed set)
   - RNG strategy declared + matches code
   - Capacity ceiling reasonable (cited use case + measured rationale)
   - No obvious cycles (graph check vs existing registry)

5. **CI gate** — automated checks:
   - Lint: `dp::deterministic_rng` used in generator code
   - Replay-correctness: replay-test-corpus runs (if declared) → asserts replay-deterministic output
   - Capacity-budget: declared ceiling appears in `generator_capacity_budgets.yaml`
   - Registry-code sync: generator code's logical_id matches a registry entry

6. **Activate** — typically V1+30d for new Generator features:
   - Generator becomes part of coordinator's Registry view on next channel-writer restart
   - Trigger subscriptions activate
   - Capacity tracking begins from first emit

### CI gate examples

**Replay-correctness gate** (when `replay_test_corpus_ref` declared):
```
1. Snapshot a representative event log segment containing trigger events for this generator
2. Run replay with the new generator → produce projection state P_new
3. Run replay AGAIN with same input → produce P_new_repeat
4. Assert P_new == P_new_repeat (bit-deterministic per EVT-A9)
5. If unequal → CI fail; generator violates determinism
```

**Capacity-budget gate** (declarative):
```
1. Parse generator_capacity_budgets.yaml
2. For each Generator-row in boundary matrix, verify entry exists with matching ceiling
3. If missing or mismatched → CI fail
```

### Forbidden shortcuts

- Code-only generators (not in registry) — bypass cycle detection + capacity governance
- Generators using `rand::thread_rng()` or wall-clock — silent canon corruption
- Generators sharing a registry_uuid — composite logical_id MUST be unique across all features
- Generators emitting to wrong category (e.g., declaring `Submitted` when output is purely rule-derived) — taxonomy violation

**Cross-ref:** [`../_boundaries/00_README.md`](../_boundaries/00_README.md) lock-claim procedure, [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25), [EVT-A11 sub-type ownership](02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25), [EVT-S5 replay-test CI gate](11_schema_versioning.md#evt-s5--replay-against-migrated-schemas).

---

## Locked-decision summary

| ID | Short name | One-line |
|---|---|---|
| EVT-G1 | Generator Registry | Unified registry; declarative SSOT in `_boundaries/01_feature_ownership_matrix.md`; runtime view per channel-writer; composite logical_id + blake3 UUID |
| EVT-G2 | Trigger source taxonomy | Closed set of 5 kinds: (a) CommittedEventOf / (b) StateThresholdOn / (c) FictionTimeMarker / (d) OtherGeneratorOutput / (e) LifecycleMarker |
| EVT-G3 | Cycle detection | Static at registration (topological sort) + runtime depth-counter (cap 16); cycle-tolerant tolerance forbidden |
| EVT-G4 | Capacity governance | Tiered enforcement (50% warn / 90% pager / 100% reject); per-generator ceilings declared at registration; `EventModelError::GeneratorRateLimited` propagated per DP-R6 |
| EVT-G5 | Coordinator service spec | 7 responsibilities (registry / subscription / dispatch / cycle detect / capacity / determinism / failure); in-process per channel-writer; no new service binary V1 |
| EVT-G6 | Extension procedure | 6 steps: declare → register → implement → boundary review → CI gate → activate |

---

## Cross-references

- [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25) — invariant generators must honor
- [EVT-A11 sub-type ownership](02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25) — boundary matrix discipline
- [EVT-A12 extensibility framework](02_invariants.md#evt-a12--extensibility-framework-new-2026-04-25) — extension point (f) "new generation rule" formalized here
- [EVT-T5 Generated](03_event_taxonomy.md#evt-t5--generated) — primary output category
- [EVT-T3 Derived](03_event_taxonomy.md#evt-t3--derived) — secondary output category for state-threshold generators
- [`08_scheduled_events.md` EVT-L7..L11](08_scheduled_events.md) — scheduler subset of generators (now subsumed under EVT-G2 kind (c))
- [`11_schema_versioning.md` EVT-S5](11_schema_versioning.md#evt-s5--replay-against-migrated-schemas) — replay-correctness CI gate
- [DP-Ch25..Ch30 BubbleUp aggregator](../06_data_plane/16_bubble_up_aggregator.md) — aggregator runtime pattern (subset of generators; specific to bubble-up)
- [DP-A16 channel writer-node binding](../06_data_plane/02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25) — coordinator deployment binding
- [DP-K6 subscribe primitive](../06_data_plane/04c_subscribe_and_macros.md#dp-k6--subscription-primitives) — coordinator subscribes on generators' behalf
- [DP-R6 backpressure propagation](../06_data_plane/11_access_pattern_rules.md#dp-r6--backpressure-propagation-not-swallow-and-retry) — capacity governance backpressure discipline
- [`../_boundaries/00_README.md`](../_boundaries/00_README.md) + [`01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md) — boundary lock + Generator-rows ownership SSOT
- [22_event_design_quickstart.md](22_event_design_quickstart.md) — bridging doc; updated cross-ref section may cite EVT-G* in future revision
