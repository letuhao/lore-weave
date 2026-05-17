# V1+30d Implementation Plan — Geography + Travel

> ⚠️ **SUPERSEDED for the current goal (2026-05-17).** The near-term goal is a *standalone world-map generator*, not the event-sourced MMO. See **[`GEO_GENERATOR_PLAN.md`](GEO_GENERATOR_PLAN.md)** — a focused 4-phase plan with no DP-kernel / foundation dependency. This document is retained only as a record; it is relevant only if the full event-sourced MMO engine is ever built.

> **Purpose:** turn the DRAFT geography + travel design docs (GEO_001 / GEO_001b / POL_001 / SET_001 / ROUTE_001 / TVL_001..TVL_005) into running code, split into **8 dependency-ordered cycles, each executed as one `/amaw` workflow**.
>
> **Status:** NOT STARTED — this is a forward plan.
>
> **Greenlight precondition:** the `LLM_MMO_RPG` track is still "Exploratory — NOT approved for implementation" ([SESSION_HANDOFF §1](SESSION_HANDOFF.md)). This plan does not execute until that gate is lifted.
>
> **Foundation precondition:** cycles 1–3 (geography) need only the DP-kernel + RealityManifest. Cycles 4–7 (travel) additionally require the **foundation actor substrate implemented** — EF_001, RES_001, PL_001/005/006, TDIL_001, AIT_001, PROG_001. That foundation build is **out of scope for this plan** — it is a prerequisite program before Cycle 4.

---

## Cycle status board

> The batch driver (§2) reads this board: it runs the lowest-numbered cycle whose `Status` ≠ `DONE` and whose `Depends-on` cycles are all `DONE`.

| Cycle | Title | Status | Depends on |
|---|---|---|---|
| 0 | Readiness gate + contract freeze | **DONE** (scoped — 2026-05-17; scaffolds + contract homes; see [V1_30D_CYCLE_LOG.md](V1_30D_CYCLE_LOG.md)) | — |
| 1 | GEO_001 world geometry foundation | **BLOCKED** — needs the DP-kernel (unbuilt) | 0 |
| 2 | Activation triangle: POL_001 + SET_001 | NOT STARTED (blocked via 1) | 1 |
| 3 | Activation triangle: ROUTE_001 + POL culture | NOT STARTED (blocked via 1) | 2 |
| 4 | `travel-service` scaffold + TVL_001 atomic travel | NOT STARTED (blocked via 1; + foundation substrate) | 3 (+ foundation substrate) |
| 5 | TVL_002 composite + TVL_003 mount | NOT STARTED (blocked via 1) | 4 |
| 6 | TVL_004 encounters + TVL_005 parties | NOT STARTED (blocked via 1) | 5 |
| 7 | Cross-service integration + S9 context + CI hardening | NOT STARTED (blocked via 1) | 6 |

> **Batch loop halted after Cycle 0.** Cycle 1 is BLOCKED on the unbuilt DP-kernel + foundation tier (a repo audit confirmed the MMO RPG engine is 100% design docs, 0% code — see [V1_30D_CYCLE_LOG.md](V1_30D_CYCLE_LOG.md)). Cycles 2–7 depend transitively on Cycle 1, so no cycle is runnable; the §2 batch-driver terminal rule ends the loop. **Real next step:** a separate FOUNDATION program (DP-kernel → foundation tier) — see the cycle log.

**Status values:** `NOT STARTED` · `IN PROGRESS` · `BLOCKED` · `DONE`.

**Dependency spine:** `GEO_001 → POL+SET → ROUTE+culture → travel-service/TVL_001 → TVL_002/003 → TVL_004/005 → integration`

---

## §1 — The 8 cycles

Each cycle is one `/amaw` workflow (12 phases, cold-start Adversary at REVIEW, Scope Guard at QC + POST-REVIEW). Each is sized L/XL — the AMAW sweet spot.

### Cycle 0 — Readiness gate + contract freeze · S/M
- **Goal:** freeze every shared contract so the 7 build cycles cannot drift.
- **Builds:** `contracts/api/` OpenAPI specs for `world-service` + `travel-service`; the frozen aggregate schema definitions (`world_geometry`, `actor_travel_state` at its **final union schema** — see §3.1, `composite_journey`, `mount`, `travel_encounter`, `travel_party`); the EVT-T sub-type registry additions; the `geography.*` + `travel.*` reject namespaces; the RealityManifest extensions; empty `world-service` + `travel-service` scaffolds; the Thần Điêu Đại Hiệp Nam Tống test fixture (per SPIKE_04).
- **Design refs:** all of GEO_001/POL/SET/ROUTE/TVL_001..005 §3 + §8 + §11; `_boundaries/02_extension_contracts.md`.
- **Adversary focus:** contract completeness — any field/event/rule_id missing here costs a re-freeze later. Resolve every remaining cross-cutting open question (GEO-Q* / POL-Q* / … / TVP-Q*).
- **Exit:** all contract files committed; both service scaffolds compile empty; the fixture loads. No AC scenarios (no behavior yet).

### Cycle 1 — GEO_001 world geometry foundation · XL
- **Goal:** a continent's geometry can be generated, stored, queried, and edited via deltas.
- **Builds:** procedural pipeline stages 1–4 (Voronoi dual-mesh · heightmap · ClimateZone 8-variant · BiomeKind 14-variant + rivers); the `world_geometry` aggregate (T2/Channel); deterministic-base + delta-overlay; GEO_001b CreativeSeed authoring flow + `authoring.*` namespace; the 13 V1 `geography.*` rule_ids.
- **Design refs:** [GEO_001](features/00_geography/GEO_001_world_geometry.md), [GEO_001b](features/00_geography/GEO_001b_creativeseed_authoring.md).
- **Adversary focus:** replay-determinism — same `(seed, creative_seed, pipeline_version)` → byte-identical geometry; the delta-overlay replay (base + ordered deltas).
- **Exit:** AC-GEO-1..11 + AC-AUTHOR-1..10 pass as integration tests; replay-determinism CI gate green; GEO_001 + GEO_001b → CANDIDATE-LOCK.

### Cycle 2 — Activation triangle: POL_001 + SET_001 · XL
- **Goal:** pipeline stages 5–6 activate the political + settlement layers.
- **Builds:** stage 5 political growth (Province / State); stage 6 burg-score Poisson-disk settlement placement + role assignment; GeographyDeltaKind additive bumps (POL +4 / SET +3); the `can_edit_political_geography` + `can_edit_settlement_geography` capability claims + the auth-service one-shot migration jobs; CreativeSeed schema_version bumps (2→3→4); POL-V1..20 + SET-V1..15 validators.
- **Design refs:** [GEO_002 POL_001](features/00_geography/GEO_002_political_layer.md), [GEO_003 SET_001](features/00_geography/GEO_003_settlement_generator.md).
- **Adversary focus:** R3 additive-schema discipline (closed-enum bumps, default-tolerant readers); the **capability migration** (security-critical — auth-service claim grants).
- **Exit:** AC-POL-1..21 + AC-SET-1..15 pass; the schema_version bumps replay-clean; POL_001 + SET_001 → CANDIDATE-LOCK.

### Cycle 3 — Activation triangle: ROUTE_001 + POL culture · L/XL
- **Goal:** pipeline stages 7–8 complete the V1+30d activation triangle.
- **Builds:** stage 7 route network (Road Dijkstra · Trail nearest-connection · SeaLane BFS · MountainPass edge-betweenness · RiverNavigation); stage 8 culture spread; ROUTE GeographyDeltaKind (+1) + `can_edit_route_geography` claim + migration; `world_geometry.schema_version` bump (Route.seed_source); ROUTE-V1..14 validators.
- **Design refs:** [GEO_004 ROUTE_001](features/00_geography/GEO_004_route_network_generator.md).
- **Adversary focus:** route-graph determinism; the POL-stage-5 → SET-stage-6 → ROUTE-stage-7 → POL-stage-8 ordering; one-route-per-pair + canonical-order pair normalization.
- **Exit:** AC-ROUTE-1..15 pass; the full geography activation triangle integration-tested; ROUTE_001 → CANDIDATE-LOCK.

### Cycle 4 — `travel-service` scaffold + TVL_001 atomic travel · XL
- **Goal:** the NEW `travel-service` exists; an actor can travel one Route atomically.
- **Builds:** the `travel-service`; the `actor_travel_state` aggregate **at its final union schema** (all of `composite_journey_id` + `mount_id` + `encounter_schedule` present from day one — §3.1); `Travel:Initiate` / `Scheduled:TravelTick` / `Travel:Arrive`; the EF_001 `entity.travel_journey_id` field; the `TravelMode` enum 5-variant; selective TDIL clock advancement; hospitality at arrival; the 15 TVL-V validators + 15 `travel.*` rule_ids.
- **Design refs:** [TVL_001](features/00_travel/TVL_001_travel.md).
- **Adversary focus:** the new service boundary; the `actor_travel_state` schema is the load-bearing substrate for 4 more features — get it complete now; replay-determinism of the per-turn tick.
- **Exit:** AC-TVL-1..15 pass; TVL_001 → CANDIDATE-LOCK. **Note:** building the union schema here means there is no later "TVL_001 closure pass" — Cycles 5–6 add logic only, no migration.

### Cycle 5 — TVL_002 composite + TVL_003 mount · XL
- **Goal:** multi-segment composite journeys + mounted/vehicle travel.
- **Builds:** `composite_journey` aggregate + Dijkstra solver (lexicographic tie-break) + re-plan/strand + smart overnight stops + the `composite_travel_plan` preview query; `mount` aggregate + activated `TravelMode` variants + speed-modifier table + mode↔route matrix + `Forge:GrantMount` + `canonical_mounts`; CTV-V1..17 + TVM-V1..10 validators.
- **Design refs:** [TVL_002](features/00_travel/TVL_002_composite_travel.md), [TVL_003](features/00_travel/TVL_003_mount_vehicle_travel.md).
- **Adversary focus:** Dijkstra determinism; the composite re-plan provisions math + the `Stranded` paths.
- **Exit:** AC-TVL-16..30 + AC-TVL-46..60 pass; TVL_002 + TVL_003 → CANDIDATE-LOCK.

### Cycle 6 — TVL_004 encounters + TVL_005 parties · XL
- **Goal:** encounters during a journey + group/party travel.
- **Builds:** `travel_encounter` aggregate + Poisson pre-roll (pinned schedule) + tick-generator encounter detection + pause + choice-based resolution + chat-service LLM encounter integration + engine outcome-clamp + combat abstraction + `encounter_tables`; `travel_party` aggregate + formation lifecycle + leader's-journey binding + lockstep arrival + member in-transit marking + `canonical_parties`; CTE-V1..12 + TVP-V1..13 validators.
- **Design refs:** [TVL_004](features/00_travel/TVL_004_travel_encounters.md), [TVL_005](features/00_travel/TVL_005_group_party_travel.md).
- **Adversary focus:** the LLM-in-the-loop encounter resolution (AI provider boundary, replay-caching); the member-in-transit invariant (a journey shared by actors who don't each own it).
- **Exit:** AC-TVL-31..45 + AC-TVL-61..75 pass; TVL_004 + TVL_005 → CANDIDATE-LOCK.

### Cycle 7 — Cross-service integration + S9 context + CI hardening · L
- **Goal:** the whole geography + travel surface works end-to-end across services.
- **Builds:** chat-service S9 prompt-assembly `[GEOGRAPHIC_CONTEXT]` + `[TRAVEL_CONTEXT]` extensions (all sub-fields); api-gateway-bff routing for every new event + query; knowledge-service read hooks (stubbed); the full CI gate suite (replay-determinism across all aggregates, apply_delta total-function, all invariant gates); end-to-end smoke against the SPIKE_04 fixture.
- **Design refs:** TVL_001..005 §9; GEO_001..ROUTE_001 §S9 references.
- **Adversary focus:** cross-service contract drift — the integration is where boundary assumptions bite.
- **Exit:** end-to-end smoke green (bootstrap → geography generated → an actor runs a composite mounted party journey that hits an encounter); all 5 TVL + 4 geography docs → CANDIDATE-LOCK or LOCK per their §17.

---

## §2 — Batch execution (AMAW per cycle)

The plan doc above is the **batch manifest**: each cycle's row in §1 is that cycle's complete brief, and the Cycle status board is the progress tracker. The per-cycle prompt therefore stays thin — it just points the agent at the right cycle.

### Per-cycle prompt (paste this, substitute `<N>`)

```
/amaw

Execute Cycle <N> of the V1+30d implementation plan.

Read docs/03_planning/LLM_MMO_RPG/V1_30D_IMPLEMENTATION_PLAN.md — the Cycle <N>
block in §1 is your full brief (Goal · Builds · Depends-on · Design refs ·
Adversary focus · Exit). Read the design docs the cycle cites before the DESIGN
phase. Classify the cycle's task size (it is L or XL) and run the full 12-phase
AMAW workflow as ONE task.

Hard rules:
- This task is Cycle <N> ONLY — do not start any other cycle.
- Every Depends-on cycle must already be Status=DONE on the status board; if
  not, STOP and report.
- VERIFY (Phase 6) must pass the cycle's Exit criteria (the named AC ranges +
  CI gates) with fresh evidence — no "should pass".
- At COMMIT (Phase 11): set Cycle <N>'s Status to DONE on the status board and
  include that edit in the same commit.
- STOP and report (do NOT paper over) if: VERIFY fails after a real fix
  attempt, the Scope Guard returns BLOCKED, or a design-doc gap surfaces that
  needs a design decision (the design docs are DRAFT — gaps are expected).
```

### Batch driver — `/loop` (one fire, self-paced through all cycles)

```
/loop Read docs/03_planning/LLM_MMO_RPG/V1_30D_IMPLEMENTATION_PLAN.md §1 + the
status board. Pick the lowest-numbered cycle with Status != DONE whose every
Depends-on cycle is DONE. Execute exactly that one cycle now using the §2
per-cycle prompt (invoke /amaw, run all 12 phases, set Status=DONE at COMMIT).
Then end the turn so the loop re-fires for the next cycle. If no cycle is
runnable — all DONE, or the next is BLOCKED, or a cycle reported STOP — say so
and end the loop.
```

Fire the `/loop` once; each iteration completes one cycle and the loop advances to the next. Because the cycles are a strict dependency chain, this is the *only* automatic ordering — there is no parallel batch.

### Sequencing rules

1. **Strictly sequential.** No two cycles run at once — every cycle consumes the previous cycle's committed output. "Batch" = an automated sequence.
2. **One conversation per cycle is cleaner than one `/loop` for all 8.** Each cycle is XL; 8 XL cycles in one `/loop` conversation leans hard on compaction. For tighter context + easier review, run each cycle in a fresh conversation with the per-cycle prompt — the status board makes "which cycle next" unambiguous either way.
3. **Cycle 4 gate.** Do not start Cycle 4 until the foundation actor substrate (EF/RES/PL/TDIL/AIT/PROG) is implemented — see the Foundation precondition. Cycles 1–3 may proceed without it.

### Genuine stop-points (the batch must NOT run past these)

- **Greenlight** — the track must be approved for implementation before Cycle 0.
- **A BLOCKED Scope Guard** or a **failed VERIFY** — investigate, do not advance.
- **A surfaced design gap** — the design docs are DRAFT with open questions; a cycle that hits an unresolved decision needs a human or a `/review-impl`-style pass, not an autonomous guess.
- **The Cycle 4 foundation gate** above.

---

## §3 — Cross-cutting decisions

### 3.1 — No "TVL_001 closure pass" as a separate task
The travel arc was designed expecting TVL_001 to ship first and TVL_002/003/004/005 to add `actor_travel_state` fields later via a closure pass (3 sequential `schema_version` bumps). **This plan collapses that:** Cycle 4 builds `actor_travel_state` at its *final* union schema — `composite_journey_id`, `mount_id`, `encounter_schedule` all present as `Option` (= `None`) from day one. Cycles 5–6 then add only *logic*; no migration. One schema definition instead of four.

### 3.2 — Geography and travel are separable
Cycles 1–3 depend only on the DP-kernel + GEO_001; cycles 4–7 add the foundation-actor-substrate dependency. If the foundation build slips, the geography cycles can still proceed.

### 3.3 — Heavy + light cycle pairing
Cycles 2, 5, 6 each pair one intricate feature with a simpler sibling (POL+SET, composite+mount, encounters+parties) to keep every cycle a balanced L/XL — the AMAW size sweet spot.

### 3.4 — Merge options (if fewer cycles are wanted)
- Cycle 0 can fold into Cycle 1's CLARIFY phase → 7 cycles.
- Cycles 2 + 3 can merge into one heavy geography-activation cycle → 6 cycles.
The 8-cycle split is the recommended default — it keeps each AMAW run a clean, reviewable unit.

### 3.5 — Each cycle moves design docs DRAFT → CANDIDATE-LOCK
Every TVL/GEO design doc's §17 says "CANDIDATE-LOCK upon acceptance scenarios passing integration tests" — so each cycle's VERIFY is also what advances its design docs' status. Cycle 7's end-to-end smoke is what lets the §17 LOCK conditions close.
