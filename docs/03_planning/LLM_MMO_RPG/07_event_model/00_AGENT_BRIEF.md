# 00 — Agent Brief: Event Model design (parallel work commission)

> **Status:** LOCKED brief. Issued 2026-04-25 by the main session that produced [`PL_001_continuum.md`](../features/04_play_loop/PL_001_continuum.md) ("Continuum"). The agent receiving this brief is expected to design `07_event_model/` to LOCK over multiple work-sessions, mirroring the pattern that `06_data_plane/` followed.
>
> **Read order before starting:** §0 Identity → §1 Why → §2 IN scope → §3 OUT of scope → §4 Required reading → §5 Phase plan → §6 Stable ID namespace → §7 Process discipline → §8 Coordination with other streams → §9 Success criteria → §10 First-session deliverable.

---

## §0 — Your identity for this work

You are the **Event Model design agent**. You own `docs/03_planning/LLM_MMO_RPG/07_event_model/` end-to-end. You are NOT the same agent that designed 06_data_plane (that work is LOCKED — you cannot touch it). You are NOT the agent doing feature design in `features/` (separate stream — you produce taxonomy they will consume). You operate in a fresh worktree branch for cleanliness; coordinate via the parent branch when locking.

**Output language for design docs:** English (matches 06_data_plane convention).
**Output language for user-facing summaries / commit messages headlines:** English; commit body may include Vietnamese annotations if helpful.
**User communicates in:** Vietnamese + English mixed. Interpret accordingly.

---

## §1 — Why this work exists

The main session committed [`PL_001_continuum.md`](../features/04_play_loop/PL_001_continuum.md) ("Continuum") at `b4ea611`. It treats "events" as a primitive: `TurnEvent`, `MembershipEvent`, `BubbleUpEvent`, `AmbientEvent`, ... — but never defines:

1. The closed set of event categories the game will ever have
2. Who is allowed to produce each category, and through which pipeline
3. What validators run before an event commits, in which order
4. The concrete LLM proposal bus protocol (DP-A6 mentions but defers it)
5. How fiction-time-triggered events ("siege starts day X") are scheduled and emitted
6. The schema for "event B was caused by event A" links
7. Replay semantics — session catch-up vs canon-promotion vs time-travel debug
8. Schema versioning + migration

DP (06_data_plane) only owns event TRANSPORT (ordering, durability, fan-out, capability gating). DP does NOT own event SHAPE or LIFECYCLE. That gap is what this folder closes.

If this layer is wrong, every feature built on top of it has to be reworked when the rules eventually crystallize. So it must be designed and locked BEFORE feature work proceeds past PL_001.

The user explicitly approved spawning this parallel work stream and asked for a detailed brief so you understand exactly what to do.

---

## §2 — IN scope (you MUST design these)

Each item below must reach LOCKED status before you can declare Phase complete. Use the EVT-* stable ID namespace (see §6).

### S1. Event taxonomy (top-level closed set)

A closed set of category names + a one-line definition each. Tentative top-level categories observed during PL_001 design (you will refine):

- **PlayerTurn** — emitted via `dp::advance_turn` when a PC submits an action
- **NPCRoutine** — NPC-initiated event when no PC is in the cell (NPC sleeps, eats, walks routine)
- **WorldTick** — fiction-time-triggered (siege starts day X-thu-1257, festival begins, weather change)
- **QuestBeat** — quest scaffold trigger, beat advancement, outcome
- **LLMProposal** — Python-emitted proposal awaiting Rust validation (DP-A6)
- **CanonPromotion** — emergent state crystallizes into the canonical layer (per 03_multiverse)
- **AdminAction** — operator-initiated (pause channel, force-end scene, override world-rule)
- **SystemEvent** — DP-emitted canonical (MemberJoined/Left, ChannelPaused/Resumed, TurnSlotTimedOut) — already locked by DP-A18 etc.; you classify them, you do not redesign

Validate, expand, or collapse this list. Prove the closed-set property by mapping every event mentioned in PL_001 + every observation from `features/_spikes/SPIKE_01_*` to exactly one category.

### S2. Producer rules per category (EVT-P*)

Per category, specify:
- **Allowed producers** — which service / role / actor can emit
- **Capability gate** — which JWT claim (DP-K9) is required
- **Idempotency** — how duplicates are deduped (key composition)
- **Rate limit** — sane defaults; not part of DP rate-limit (DP-R6 covers transport rate-limit, not semantic rate-limit)
- **Forbidden producers** — explicit deny list (e.g., PC sessions cannot directly emit WorldTick)

### S3. Validator pipeline (EVT-V*)

Five existing checks need ordering + fail-mode contract:
1. **Schema validation** — event payload conforms to per-category contract
2. **Capability check** — DP-K9 already does this, but Event Model documents the order
3. **Intent classification** — A5 from `05_llm_safety/`
4. **World-rule lint** — feature-level invariants (PC cannot sleep in active battle)
5. **Canon-drift check** — A6 / per-PC retrieval isolation
6. **Causal-ref integrity** — referenced parent event exists, is in same reality, etc.

Lock the order, fail-mode (reject vs sanitize vs quarantine), retry policy, and dead-letter destination. Coordinate with `05_llm_safety/` — do NOT redesign A3/A5/A6, slot them into the pipeline.

### S4. Per-category contracts (event shapes)

Per category, specify:
- Required fields with types
- Optional fields with types
- Idempotency key composition
- Causal-ref shape (which categories MAY/MUST reference parent events)
- Maximum payload size
- Schema version field placement

For `PlayerTurn`, the shape is partially defined in PL_001 §3.5 (`TurnEvent` struct). Reconcile / formalize / cite that as the canonical contract; PL_001 will then update its §3.5 to cite back.

### S5. LLM proposal bus protocol (EVT-L1..)

DP-A6 says "Python emits proposal events onto an event bus consumed by Rust" but defers the concrete protocol. You design:
- **Transport** — Redis Streams? NATS? dedicated topic per event category? per reality?
- **Topic naming** — must match DP cache-key convention (reality_id first)
- **Schema** — proposal envelope wrapping the proposed event
- **Acknowledgment model** — at-least-once vs exactly-once; idempotency key requirement
- **Retry policy** — backoff, max attempts, dead-letter
- **Ordering** — per-actor? per-channel? best-effort?
- **Backpressure** — what happens when consumer (Rust validator) lags

This is the most "concrete protocol design" item in the brief. Expect it to be the single largest file.

### S6. Scheduled / fiction-time-triggered events

How does "siege Tương Dương begins day X-thu-1257" get into the event log?

- Producer model — a `world-rule-scheduler` service? a sidecar in `world-service`? a CP responsibility?
- Trigger evaluation — wall-clock cron? polled when fiction-clock advances? evaluated on every turn commit?
- Idempotency — siege fires once even if fiction-clock advances multiple turns past the trigger time
- Recovery — if scheduler is down for 6h wall-clock, do missed triggers fire on restart?

Coordinate with PL_001 §3.1 `fiction_clock` — that aggregate's writer must trigger evaluations.

### S7. Causal references (EVT-L2..)

Define the shape of "event B was caused by event A":
- For per-channel: `(channel_id, channel_event_id)` (already in DP-A15 for bubble-up)
- For cross-channel (e.g., bubble-up triggers tavern event from cell event): same shape
- For cross-reality (DF12 withdrawn — out of scope for V1)
- For LLM-proposal-to-committed-event chain
- For QuestBeat-causes-WorldTick chain

Lock the field name, the type, and the validation rule (referenced event must exist, must be in the same reality unless explicit cross-reality op).

### S8. Replay semantics (EVT-L3..)

Three different replay use cases have different requirements:

1. **Session catch-up replay** — UI client reconnects, replays missed events from resume token (DP-K6 already handles transport; you specify which events the client SHOULD see vs which are internal)
2. **Canon-promotion replay** — emergent events get promoted to canon; replay validates the chain (per `03_multiverse/`)
3. **Time-travel debug replay** — operator queries "what happened in cell X between turn N and M" — must be deterministic

Lock the contract for each: which event categories are replayable, which are filtered, deterministic guarantees.

### S9. Schema versioning + migration (EVT-S*)

DP-K3 has `SchemaVersionMismatch` error variant; migration protocol was deferred to "Q5 in CP spec" — actually belongs here.

Lock:
- Schema version field placement on every event
- Forward-compat rules — when may producers emit V2 while consumers still on V1?
- Backward-compat rules — when may a consumer drop fields?
- Migration triggers — schema bump on what conditions
- Replay against migrated schemas — invariants

---

## §3 — OUT of scope (you MUST NOT touch)

### O1. Anything LOCKED in `06_data_plane/`

You may READ everything in `06_data_plane/`. You may NOT modify any file there. If you discover a real conflict between Event Model design and a DP axiom, write it up in `99_open_questions.md` and escalate to the user — do not work around silently. Specifically off-limits:

- DP-A1..A19 axioms
- DP-T0..T3 tier taxonomy
- DP-R1..R8 access pattern rulebook
- DP-K1..K12 SDK API surface
- DP-C* control plane
- DP-X* cache coherency
- DP-F* failure recovery
- DP-Ch1..Ch53 channel primitives, ordering, durable subscribe, turn boundary, bubble-up, lifecycle, causality, redaction, operational, turn-slot

### O2. Specific feature event types

Each feature in `features/<category>/<NNN>_*.md` declares the event types it owns. You define the TAXONOMY (top-level categories) and the CONTRACT SHAPE (required envelope fields) — you do NOT enumerate every NPC dialog line type or every quest beat type. Feature authors pick from the taxonomy and add their domain-specific subtypes.

### O3. Implementation code

This folder is design specification. No Rust code. No TypeScript. No SQL beyond what DP-Ch2 already established. Diagrams in markdown text or mermaid; no images.

### O4. LLM safety internals

`05_llm_safety/` already designed A3 (World Oracle), A5 (intent classifier), A6 (injection defense). You SLOT those into your validator pipeline (§S3). You do NOT redesign them. If you find a gap in A3/A5/A6, escalate via `99_open_questions.md`.

### O5. Storage event log mechanics

`02_storage/` (locked by R*/S*/C*/SR* items) owns event-log durability, outbox pattern, projection rebuild. You consume those unchanged. If your design needs a new primitive there, raise it as a `99_open_questions.md` item — do not implement it yourself.

### O6. Catalog modifications

`catalog/` is the master scope rollup; you do NOT modify it. After your work locks, the main session adds catalog references to your EVT-* IDs.

### O7. Existing committed feature designs

`features/04_play_loop/PL_001_continuum.md` ("Continuum", committed `b4ea611`) is reference material — you read it to understand the gap, you do NOT modify it. After your taxonomy locks, the main session updates PL_001 to cite EVT-* IDs.

---

## §4 — Required reading (in order)

Before writing a single line of Phase 1, you MUST have read the following. Estimate: 3-4 hours.

### 4.1 Foundation cheat sheets (mandatory)

1. [`../00_foundation/_index.md`](../00_foundation/_index.md)
2. [`../00_foundation/01_READ_THIS_FIRST.md`](../00_foundation/01_READ_THIS_FIRST.md)
3. [`../00_foundation/02_invariants.md`](../00_foundation/02_invariants.md) — I1..I19
4. [`../00_foundation/03_service_map.md`](../00_foundation/03_service_map.md)
5. [`../00_foundation/05_vocabulary.md`](../00_foundation/05_vocabulary.md) — TurnState, PresenceState, fiction-time, GoneState
6. [`../00_foundation/06_id_catalog.md`](../00_foundation/06_id_catalog.md) — see all reserved namespaces

### 4.2 DP (LOCKED — read for boundary)

7. [`../06_data_plane/_index.md`](../06_data_plane/_index.md) — full status table
8. [`../06_data_plane/02_invariants.md`](../06_data_plane/02_invariants.md) — DP-A1..A19 (especially DP-A6 which delegates the LLM bus to you)
9. [`../06_data_plane/04a_core_types_and_session.md`](../06_data_plane/04a_core_types_and_session.md) — DP-K1..K3
10. [`../06_data_plane/04b_read_write.md`](../06_data_plane/04b_read_write.md) — DP-K4..K5 (write APIs your producers use)
11. [`../06_data_plane/04c_subscribe_and_macros.md`](../06_data_plane/04c_subscribe_and_macros.md) — DP-K6..K8 (subscribe APIs your consumers use)
12. [`../06_data_plane/14_durable_subscribe.md`](../06_data_plane/14_durable_subscribe.md) — DP-Ch16..Ch20 (gap-free delivery your replay sits on)
13. [`../06_data_plane/15_turn_boundary.md`](../06_data_plane/15_turn_boundary.md) — DP-Ch21..Ch24 (PlayerTurn category sits on this)
14. [`../06_data_plane/16_bubble_up_aggregator.md`](../06_data_plane/16_bubble_up_aggregator.md) — DP-Ch25..Ch30 (bubble-up event category)
15. [`../06_data_plane/17_channel_lifecycle.md`](../06_data_plane/17_channel_lifecycle.md) — DP-Ch31..Ch37 (SystemEvent: MemberJoined/Left, ChannelPaused/Resumed)
16. [`../06_data_plane/18_causality_and_routing.md`](../06_data_plane/18_causality_and_routing.md) — DP-Ch38..Ch42 (CausalityToken — informs your causal-ref design)
17. [`../06_data_plane/22_feature_design_quickstart.md`](../06_data_plane/22_feature_design_quickstart.md) — bridging doc; lets you see what feature authors expect

### 4.3 Validation pipeline inputs (LOCKED — slot in, do not redesign)

18. [`../05_llm_safety/_index.md`](../05_llm_safety/_index.md)
19. The 6 split files in `05_llm_safety/` covering A3/A5/A6

### 4.4 Domain grounding

20. [`../03_multiverse/_index.md`](../03_multiverse/_index.md) — canon layering (informs replay)
21. [`../03_multiverse/01_four_layer_canon.md`](../03_multiverse/01_four_layer_canon.md) — informs CanonPromotion category
22. [`../features/04_play_loop/PL_001_continuum.md`](../features/04_play_loop/PL_001_continuum.md) — "Continuum"; first feature consuming events (read in full, especially §3.5 TurnEvent shape, §10 cross-service handoff with CausalityToken chain)
23. [`../features/_spikes/SPIKE_01_two_sessions_reality_time.md`](../features/_spikes/SPIKE_01_two_sessions_reality_time.md) — narrative grounding; the 22 observations are real workload examples your taxonomy must absorb
24. [`../decisions/_index.md`](../decisions/_index.md) → especially MV12-D1..D11 fiction-time decisions

### 4.5 Storage backbone (LOCKED — consume unchanged)

25. [`../02_storage/_index.md`](../02_storage/_index.md) — at minimum read R7 (single-writer per session) and S* (event-log shape)

### 4.6 Catalog (read for ID-collision avoidance)

26. [`../catalog/_index.md`](../catalog/_index.md) — see all stable-ID prefixes already used

### 4.7 Process docs

27. [`../README.md`](../README.md) — folder organization
28. [`../SESSION_HANDOFF.md`](../SESSION_HANDOFF.md) — append-only log; you append rows when you finish phases
29. [`../AGENT_GUIDE.md`](../AGENT_GUIDE.md) — agent process discipline

---

## §5 — Phase plan (suggested, refine as you go)

Each phase ends with a LOCK ceremony — POST-REVIEW Phase 9 (architect sign-off) before commit, decisions logged in `../decisions/locked_decisions.md`, status table in `_index.md` updated.

### Phase 1 — Boundary + Axioms + Taxonomy (BLOCKING for feature authors)

Deliverables:
- `00_preamble.md`
- `01_scope_and_boundary.md` (IN/OUT explicit; no second-guessing later)
- `02_invariants.md` — EVT-A* (~5-10 axioms expected; see DP-A1..A19 for shape reference)
- `03_event_taxonomy.md` — EVT-T* closed set with the closed-set proof (every PL_001/SPIKE_01 event maps to exactly one)
- `99_open_questions.md` — start tracking deferred items

**Lock criterion for Phase 1:** the taxonomy is closed-set proven and feature authors can cite EVT-T* IDs in subsequent feature docs. The user (main session) acknowledges by issuing PL_002 referencing EVT-T*.

### Phase 2 — Producers + Contracts

Deliverables:
- `04_producer_rules.md` — EVT-P* per category
- `06_per_category_contracts.md` — required/optional fields, idempotency keys, max sizes, schema version field
- Update `99_open_questions.md`

**Lock criterion:** every category in EVT-T* has a producer rule and a contract.

### Phase 3 — Validator + LLM Proposal Bus

Deliverables:
- `05_validator_pipeline.md` — EVT-V* ordering + fail modes + retry + dead-letter
- `07_llm_proposal_bus.md` — concrete protocol resolving DP-A6 deferral
- Update `99_open_questions.md`

**Lock criterion:** Python LLM-side roleplay-service can be implemented against the bus contract; Rust world-service can implement validator pipeline.

### Phase 4 — Scheduling + Causal-ref + Replay + Versioning

Deliverables:
- `08_scheduled_events.md`
- `09_causal_references.md`
- `10_replay_semantics.md`
- `11_schema_versioning.md` — EVT-S* (resolves DP Q5 deferral)
- Update `99_open_questions.md`

**Lock criterion:** ALL items in §S1..S9 of this brief are LOCKED or explicitly deferred with a Q-id.

### Phase 5 — Bridging doc for feature authors

Deliverables:
- `22_event_design_quickstart.md` — mirrors DP's `22_feature_design_quickstart.md`. Worked example: redo PL_001's TurnEvent and BubbleUpEvent using the EVT-T*/EVT-P*/EVT-V* contracts. Decision flowchart for "I need to emit an event — which category, which producer, which validator chain?"

**Lock criterion:** main session uses this quickstart while drafting PL_002, finds it sufficient.

---

## §6 — Stable ID namespace (RESERVED)

You own these prefixes. Never renumber. Retired IDs use `_withdrawn` suffix.

| Prefix | Scope | File |
|---|---|---|
| `EVT-A*` | Axioms / invariants | `02_invariants.md` |
| `EVT-T*` | Event taxonomy categories (top-level closed set) | `03_event_taxonomy.md` |
| `EVT-P*` | Producer rules per category | `04_producer_rules.md` |
| `EVT-V*` | Validator pipeline rules | `05_validator_pipeline.md` |
| `EVT-S*` | Schema versioning + migration | `11_schema_versioning.md` |
| `EVT-L*` | Event lifecycle stages (proposal → committed → fanned-out → consumed) | TBD — may live in `07_llm_proposal_bus.md` or a dedicated `lifecycle.md` |
| `EVT-Q*` | Open questions | `99_open_questions.md` |

**MUST NOT collide with** (already taken):
- DP-* — 06_data_plane (all sub-prefixes A/T/R/S/K/C/X/F/Ch)
- MV* / MV12-D* — 03_multiverse
- R* / S* / C* / SR* — 02_storage
- I* — 00_foundation invariants
- PL-* / WA-* / PO-* / NPC-* / PCS-* / SOC-* / NAR-* / EM-* / PLT-* / CC-* / DL-* — catalog feature IDs
- DF1..DF15 — deferred features registry

`EM-*` is taken by `cat_09_EM_emergent`. That is why you use `EVT-*`.

---

## §7 — Process discipline

These are not optional. The main session will reject commits that violate them.

### 7.1 Phase 9 POST-REVIEW before every commit

Present a summary to the user (architect role) and **wait for explicit approval** before committing. Format:

```
## POST-REVIEW for <phase / file / change>

What changed:
- file X (NNN lines added)
- file Y (modified — N lines)

Key decisions locked:
- EVT-Ann: <one-line rule>
- EVT-Tnn: <one-line>
- ...

Deferred to phase N+1:
- EVT-Qnn: <question>

Risk / drift watchpoint:
- <if any cross-cutting risk>

Awaiting approval to commit with message:
  docs(mmo-rpg): <commit message draft>
```

If the user says "approve" → commit. If they redirect → adjust, re-present.

### 7.2 Stable IDs never renumber

Once an EVT-A1 axiom is locked, its number is permanent. Withdrawing → `EVT-A1_withdrawn` suffix; the file keeps the entry for historical reference. Adding → next free number, never reuse.

### 7.3 Decisions log

Every locked decision goes into `../decisions/locked_decisions.md` with the EVT-* ID and a one-line summary. The main session uses this log to resolve cross-folder conflicts.

### 7.4 Session handoff log

Append a row to `../SESSION_HANDOFF.md` at the end of each work-session with: date, phase touched, files added/modified, commits, what's next.

### 7.5 Line cap soft 500 / hard 800

Files over 500 lines should be split. Files over 800 lines MUST be split. Use the existing `scripts/chunk_doc.py` if a file accidentally grows. (DP team split `04_kernel_api_contract.md` at 891 lines into 04a/b/c/d for this reason.)

### 7.6 No silent scope creep

If you find a real gap that crosses your boundary (e.g., DP needs a new primitive your design depends on), write it up in `99_open_questions.md` AND raise it to the user. Do not silently assume DP will add it.

### 7.7 Worktree cleanliness (optional but encouraged)

The user has approved running this work in a separate worktree if you find it useful (keeps your draft commits off the main feature branch until lock). Coordinate with the user on branch naming.

---

## §8 — Coordination with other streams

### 8.1 Main session (feature design)

The main session continues `features/PL_002..PL_NNN`, `NPC_001`, `PCS_001`, etc. while you work. They will:
- Use Phase 1 EVT-T* taxonomy as soon as it locks
- Hold off on detailed event-shape design in features until Phase 2 contracts lock
- Reconcile PL_001's inline event shapes (§3.5 TurnEvent) once Phase 2 lands — main session updates PL_001, not you

### 8.2 DP team (locked, no further work expected)

DP Phase 4 LOCKED 2026-04-25. They will not respond to questions. Do NOT modify their files. If you find a real conflict, escalate via `99_open_questions.md` to the user.

### 8.3 If you see your work conflicting with PL_001

PL_001 is reference, not authoritative for event shapes. If your taxonomy contradicts PL_001's `TurnEvent`, the taxonomy wins — note it in your phase POST-REVIEW so the main session can update PL_001.

---

## §9 — Success criteria (how the user judges this work)

You succeed if, at LOCK time:

1. **Closed-set taxonomy** — Every event mentioned in PL_001 + every observation in SPIKE_01 maps to exactly one EVT-T* category. No "Other" category.
2. **Producer rules with capability gates** — Every category has a clear producer rule that cites a JWT claim from DP-K9 or explains why no claim applies.
3. **Validator pipeline ordered + fail-mode locked** — A new feature author can read EVT-V* and write a producer without asking "what happens if X fails".
4. **LLM proposal bus protocol concrete enough to implement** — Python roleplay-service can be coded against your `07_llm_proposal_bus.md`. No "TBD" on transport / topic / schema / retry / dead-letter.
5. **DP-A6 fully resolved** — That axiom said "Python proposes, Rust validates and writes — exact bus protocol deferred". After your work, "deferred" is replaced with "see EVT-L1..".
6. **Schema versioning answers DP Q5** — DP's open Q5 (schema migration) gets resolved by EVT-S*.
7. **Quickstart usable** — Main session drafts PL_002 against your `22_event_design_quickstart.md` without needing to ask you questions.
8. **No DP / 05_llm_safety / 02_storage modifications** — Your work touches only `07_event_model/` + maybe small additions to `99_open_questions.md` cross-folder pointers.

You fail if:
- Taxonomy has open holes (an event in PL_001 maps to nothing or to "Other")
- LLM bus protocol is hand-wavy at LOCK time
- Validator pipeline order is ambiguous
- You modified anything LOCKED upstream
- You shipped a long monolith file (>800 lines) without splitting

---

## §10 — First-session deliverable (do this first)

Before writing any axioms, deliver these as your Phase 0 confirmation that you understood the brief:

1. **Read confirmation** — list the 29 docs from §4 you read, with one-line notes on each (what it told you that matters for your work).
2. **Closed-set seed** — propose a draft EVT-T* taxonomy (just names + one-line each) by mapping the 22 SPIKE_01 observations + every event mentioned in PL_001 to a category. Mark unmapped events as "OPEN — need clarification".
3. **Open boundary questions** — list any §2 IN-scope item where you are unsure of boundary (e.g., "is QuestBeat one category or split into Trigger/Beat/Outcome?"). Phrase as decisions for the user to resolve.
4. **Phase plan refinement** — accept the §5 phase plan as-is, or propose a revision with rationale.

Present this as a POST-REVIEW (per §7.1) to the user. Once approved, you proceed to Phase 1.

---

## Appendix A — Event categories observed in PL_001 (seed list, not authoritative)

For your taxonomy seeding, here is what PL_001 + DP already mention:

| Mentioned name | Source | Likely category |
|---|---|---|
| `TurnEvent` | PL_001 §3.5 | PlayerTurn |
| `MemberJoined`, `MemberLeft` | DP-A18 (DP-emitted) | SystemEvent |
| `ChannelPaused`, `ChannelResumed` | DP-A18 | SystemEvent |
| `TurnSlotTimedOut` | DP-Ch51 | SystemEvent |
| `BubbleUpEvent` | DP-A15 + DP-Ch25 | (TBD — could be its own category or projection of source events) |
| `TurnBoundary` | DP-A17 | (TBD — boundary marker, not a content event) |
| `AmbientUpdate` (scene_state delta) | PL_001 §5.2 | NPCRoutine? WorldTick? |
| `ActorBindingDelta::MoveTo` | PL_001 §5.2 | PlayerTurn / NPCRoutine (depends on actor) |
| `FictionClockAdvance` | PL_001 §3.1 | (TBD — derived event from PlayerTurn / WorldTick / FastForward) |
| `TurnEvent::FastForward` (sleep/travel) | PL_001 §12 | PlayerTurn (subtype) |
| LLM proposal events | DP-A6 deferred | LLMProposal |
| Quest scaffold trigger | catalog Q-1..Q-9 | QuestBeat |
| "Siege Tương Dương starts day X" | SPIKE_01 obs#15 | WorldTick |
| Canon promotion | 03_multiverse | CanonPromotion |
| Admin: pause channel, end scene | DP-Ch35 | AdminAction |

Use this as input, not as a final answer. Your taxonomy may collapse some of these or split others.

---

## Appendix B — File-skeleton template

When writing each phase deliverable, mirror the DP file shape:

```markdown
# NN — <Title> (EVT-X1..EVT-Xn)

> **Status:** LOCKED / DRAFT
> **Stable IDs:** EVT-X1..EVT-Xn
> **Cross-refs:** ...

---

## How to use this file
...

## EVT-X1 — <Short name>
**Rule:** ...
**Why:** ...
**Enforcement:** ...
**Cross-ref:** ...

(repeat per ID)

## Locked-decision summary table
| ID | Short name | One-line |
| ... | ... | ... |
```

This keeps file shape consistent with `06_data_plane/02_invariants.md` for cross-folder readability.

---

**End of brief.** Begin with §10 first-session deliverable. Good luck.
