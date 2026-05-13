# PL_002 — Command Grammar (Parse + Dispatch + Tool-call Allowlist)

> **⚠ CLOSURE-PASS-EXTENSION 2026-04-27 — DF05_001 Session/Group Chat CANDIDATE-LOCK 71a60346:**
>
> Command surface adds 2 V1 commands per Q1 LOCKED: `/chat @actor [@actor...]` (creates session per DF05_001 §7 multi-session-per-cell sparse architecture; PL_002 grammar parser routes to session-service via existing TurnEvent PCTurn pattern) + `/leave` (instant explicit session-leave per DF5-A4). V2+ adds `/whisper @actor message` (DF5-D2 multi-PC whisper). Existing `/travel` cascades into session-service for cell-leave per PL_001 §13 closure-pass-extension. NO change to PL_002 closed-set vocabulary discipline; commands are additive per I14. PL_002 grammar-layer rate-limit serves as anti-spam for `/chat` per Q4-D4 LOCKED (no per-NPC cooldown V1). LOW magnitude — pure command surface additions; CANDIDATE-LOCK status PRESERVED. Reference: [DF05_001 §7.5 Session creation grammar](../DF/DF05_session_group_chat/DF05_001_session_foundation.md#75-pc-moves-cell-during-active-session).

> **Conversational name:** "Grammar" (GR). The closed-set vocabulary of typed commands a PC can issue and an LLM can propose. Sits on top of [Continuum (PL_001)](PL_001_continuum.md) as the input layer that turns user text into a typed `TurnEvent`.
>
> **Category:** PL — Play Loop (core runtime)
> **Status:** **CANDIDATE-LOCK 2026-04-25** (DRAFT → CANDIDATE-LOCK after §13 acceptance criteria added 2026-04-25 closure pass; Option C event-model terminology already applied by event-model agent in §2.5)
> **Catalog refs:** PL-2 (command grammar), PL-6 (LLM tool-call allowlist), PL-15 (3-intent classifier). Resolves [MV12-D9](../../decisions/locked_decisions.md) (`command_args` schema scope).
> **Builds on:** [PL_001 Continuum](PL_001_continuum.md) (`TurnEvent`, `RejectReason`, idempotency_key, capability JWT)
> **Cross-cuts:** [05_llm_safety/](../../05_llm_safety/) A5 intent classifier + A6 injection defense are the validators inside this feature's dispatch pipeline.
> **Event-model alignment (2026-04-25 + Option C redesign):** Phase 1 of [`07_event_model/`](../../07_event_model/) landed with EVT-A1..A8 axioms + EVT-T1..T11 closed-set taxonomy; Option C redesign 2026-04-25 added EVT-A9..A12 + collapsed feature-specific categories into 6 mechanism-level (T1 Submitted / T3 Derived / T4 System / T5 Generated / T6 Proposal / T8 Administrative); T2/T7/T9/T10/T11 `_withdrawn` per I15. PL_002's events all map to existing active categories via sub-types — see §2.5 mapping table. No new EVT-T* needed.

---

## §1 User story (concrete)

PC `Lý Minh` in `cell:yen_vu_lau` types text into the chat box. Three things can happen:

1. **Free narrative** — "Lý Minh nâng chén trà, nhìn ra ngoài cửa sổ" → goes through LLM (`roleplay-service`), narrator paraphrases, NPC may react. Standard PL_001 turn flow.
2. **Command** — "/sleep until dawn" → dispatched deterministically by world-service; LLM narrates the OUTCOME post-commit, not the action itself. Per PL-2 catalog: "deterministic dispatch, LLM narrates post-commit".
3. **Fact question** — "ai là Hoàng Dược Sư?" → goes to A3 World Oracle (PL-16); does NOT advance `turn_number`; returns a knowledge-grounded answer in the chat without modifying world state.

PL_002 locks: how text becomes one of those three intents; the closed set of V1 commands with their typed `command_args`; what tools an LLM is allowed to call when proposing actions (PL-6 allowlist); the rejection UX with concrete copy strings; and the dispatch contract from gateway → roleplay-service / world-service.

After this lock, PL_001's §3.5 `TurnEvent.command_kind` and `TurnEvent.command_args` fields have a concrete schema per `CommandKind` variant.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Intent** | `enum Intent { Command, FreeNarrative, FactQuestion }` | Output of A5 classifier (PL-15). Closed set of 3, per `05_llm_safety` A5-D1. |
| **Command** | `enum CommandKind { Verbatim, Prose, Sleep, Travel, Help }` | V1 closed set of 5. Each variant has a typed `CommandArgs` payload. Expansion path in §13. |
| **CommandArgs** | One typed struct per CommandKind | Resolves [MV12-D9](../../decisions/locked_decisions.md). See §6 per-command contracts. |
| **ToolCallAllowlist** | The closed set of mutations an LLM proposal is allowed to trigger when `Intent::FreeNarrative` produces tool calls | Lives in a RealityScoped T2 aggregate (§3). PL-6 catalog. |
| **DispatchTarget** | `enum DispatchTarget { RoleplayService, WorldServiceDirect, OracleService, GatewayLocal }` | Where the parsed input flows. Free narrative → RoleplayService (LLM); state-changing commands → WorldServiceDirect (no LLM); fact questions → OracleService; meta (/help) → GatewayLocal (canned response). |
| **RejectionCopy** | Per-command Vietnamese + English message templates | Used by §9 failure UX. Locked here so we don't free-form copy at runtime. |

---

## §2.5 Event-model mapping (per 07_event_model EVT-T1..T11; Option C redesign 2026-04-25)

Every PL_002 dispatch path produces zero or more events. Mapping each path to the closed-set EVT-T* taxonomy. **Updated 2026-04-25 Option C redesign**: feature-specific categories (T2/T7/T9/T10/T11) collapsed into 6 mechanism-level active categories. Citations updated below.

| PL_002 path | Produces event? | EVT-T* category | Sub-type / commit primitive |
|---|---|---|---|
| `/verbatim <text>` (Command) | yes | **EVT-T1 Submitted** | sub-type `PCTurn::Speak` (`command_kind=Verbatim`); commit via `dp::advance_turn` (Accepted) or `dp::t2_write` (Rejected — see GR-D8) |
| `/prose <text>` (Command) | yes (via Proposal) | **EVT-T6 Proposal** → **EVT-T1 Submitted** | LLM expands raw_text; commit-service validates and commits Submitted/PCTurn::Speak with `command_kind=Prose` |
| `/sleep [until X]` (Command) | yes | **EVT-T1 Submitted** + **EVT-T3 Derived** (FictionClockAdvance + calibration sub-shapes if date boundary crossed) | Submitted sub-type `PCTurn::FastForward` with `command_kind=Sleep`; commit-service derives and commits the Derived events per PL_001 §12. **Calibration sub-shapes (DayPasses/MonthPasses/YearPasses) now Derived sub-types** — formerly EVT-T7 CalibrationEvent (`_withdrawn` 2026-04-25). |
| `/travel to <place>` (Command) | yes | **EVT-T1 Submitted** + **EVT-T3 Derived** (FictionClockAdvance, EntityBindingDelta, SceneStateInit, calibration sub-shapes) + **EVT-T4 System** (MemberLeft + MemberJoined) | Submitted sub-type `PCTurn::FastForward` with `command_kind=Travel`; PL_001 §13 5-op chain emits the side-effect events |
| `/help` (Meta-command) | **NO** | — | Pure HTTP response from gateway; nothing committed; not an event per EVT-A1 closed-set proof |
| Free narrative (Intent::FreeNarrative) | yes (via Proposal) | **EVT-T6 Proposal** → **EVT-T1 Submitted** (+ possibly more EVT-T1 Submitted with NPCTurn sub-type for reactions) | Roleplay-service emits Proposal per EVT-A7; commit-service validates → commits Submitted/PCTurn::Speak; **NPC reactions are EVT-T1 Submitted with sub-type=NPCTurn** (formerly EVT-T2 NPCTurn category, `_withdrawn` 2026-04-25 — collapsed into Submitted per Option C). |
| Fact question (Intent::FactQuestion) | **NO** | — | Pure oracle query (PL-16); not committed; not an event |
| Soft-confirm response (`ConfirmRequired`) | **NO** (yet) | — | HTTP-level dispatch state; only the user-confirmed branch commits an event |
| Tool call within free narrative | yes, embedded in EVT-T6 → EVT-T1 | **EVT-T6 Proposal** carries tool_calls; promoted to EVT-T1 Submitted (PCTurn or NPCTurn sub-type) on validation | Tool-call allowlist (§7.4) enforced during validator pipeline before commit |

**Closed-set proof for PL_002:** every dispatch path either produces an active EVT-T* category from the closed set (T1/T3/T4/T6 — note T7 absorbed into T3) OR explicitly does NOT produce an event (and that's documented). No new EVT-T* row needed; PL_002 fits inside Option-C-redesigned taxonomy.

---

## §3 Aggregate inventory

PL_002 is dispatch logic — mostly stateless. Only ONE aggregate, plus references to PL_001's existing aggregates.

### 3.1 `tool_call_allowlist`

```rust
#[derive(Aggregate)]
#[dp(type_name = "tool_call_allowlist", tier = "T2", scope = "reality")]
pub struct ToolCallAllowlist {
    pub reality_id: RealityId,                          // (also from key)
    pub actor_type: ActorTypeKind,                      // PC | NPC_Routine | NPC_Reactive | World
    pub allowed_calls: Vec<ToolCallSpec>,               // closed set per V1
    pub schema_version: u32,
}

pub struct ToolCallSpec {
    pub name: String,                                   // "speak", "emote", "move_within_cell", "hint_npc"
    pub args_schema: serde_json::Value,                 // JSON Schema for runtime validation
    pub max_per_turn: u8,                               // burst cap (e.g. speak ≤3 utterances per turn)
}
```

- One row per `(reality_id, actor_type)` pair. Authored at reality-bootstrap from book manifest (§16 of PL_001 referenced) OR seeded with V1 defaults.
- T2 + RealityScoped: durable, per-reality. Read by `roleplay-service` before issuing LLM calls (cached per actor_type, refreshed on schema bump).
- Why not T0/T1: rule-set must survive restarts; cross-session.
- Why not T3: no ordering/atomicity requirement vs other writes; eventual consistency fine.

### 3.2 References (no new aggregates)

PL_002 reads/writes the following PL_001 aggregates without redefining them:

- **`TurnEvent`** (PL_001 §3.5) — populates `command_kind`, `command_args`, `outcome`, `idempotency_key`. PL_002 locks the schema for `command_args` per CommandKind.
- **`fiction_clock`** (PL_001 §3.1) — `/sleep` and `/travel` commands trigger advances per PL_001 §12, §13.
- **`entity_binding`** (PL_001 §3.6) — `/travel` triggers updates per PL_001 §13.
- **`turn_idempotency_log`** (PL_001 §14.3) — every command submission is keyed.

---

## §4 Tier + scope table (DP-R2 mandatory)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility justification |
|---|---|---|---|---|---|---|
| `tool_call_allowlist` | T2 | T2 | Reality | ~1 per LLM call (cached in roleplay-service ~5min TTL) | ~0 (authored at bootstrap; bumps rare) | Rule-set survives restart; per-reality; no atomicity. |

(All other touched aggregates inherit their tier+scope from PL_001 §4.)

---

## §5 DP primitives this feature calls

### 5.1 Reads

- `dp::read_projection_reality::<ToolCallAllowlist>(ctx, allowlist_id_for(actor_type))` — `roleplay-service` before each LLM call. Cached locally with 5-minute TTL.

### 5.2 Writes

- `dp::t2_write::<ToolCallAllowlist>(ctx, id, delta)` — only at reality-bootstrap (§16 PL_001) or schema bump. Not hot-path.

### 5.3 No new channel ops, subscriptions, or capability primitives

PL_002 reuses PL_001's claims and patterns. Its parsing/dispatch lives in `gateway` + `roleplay-service` + `world-service` consumer logic, not as separate DP entry points.

---

## §6 Per-command contracts (resolves MV12-D9)

V1 closed set: 5 commands. Every PC text submission either matches one of these OR falls through to FreeNarrative / FactQuestion. Unknown `/foo` → A5 classifier returns `Command` with parse-failure → reject with `ParseError`.

### 6.1 `/verbatim <text>` — speak text exactly, no LLM paraphrase

```rust
pub struct VerbatimArgs {
    pub raw_text: String,                               // ≤2 KB, sanitized but NOT paraphrased
}
```

- **Intent path:** Command, CommandKind::Verbatim
- **Dispatch:** WorldServiceDirect (skip roleplay-service entirely; no LLM call)
- **Capability:** standard PC-turn capability (no extra)
- **Effect:** commits `TurnEvent { intent: Speak, narrator_text: Some(raw_text), command_kind: Some(Verbatim), outcome: Accepted, fiction_duration: 5s }`
- **Validator chain:** A6 injection defense (PL-19) on raw_text; that's it. No A3 oracle, no A5 (already classified as command).
- **Why no LLM:** voice-mode override per PL-23. Player wants to control exact wording (deception, code-words, OOC clarity).
- **Rejection cases:** raw_text too long (>2 KB) → `RejectReason::WorldRuleViolation { rule_id: "verbatim_size" }`; raw_text fails A6 sanitize → `RejectReason::CanonDrift`.

### 6.2 `/prose <text>` — speak text in novel mode for THIS turn

```rust
pub struct ProseArgs {
    pub raw_text: String,                               // ≤4 KB; LLM expands into narrative
    pub style_hint: Option<String>,                     // optional: "tense", "wistful", ...
}
```

- **Intent path:** Command, CommandKind::Prose
- **Dispatch:** RoleplayService (LLM expands raw_text into novel-mode narration WITHOUT changing facts; then `WorldServiceDirect` commits)
- **Capability:** standard PC-turn capability
- **Effect:** commits `TurnEvent { intent: Speak, narrator_text: Some(<llm-expanded>), command_kind: Some(Prose), outcome: Accepted, fiction_duration: 10s }`
- **Validator chain:** A6 sanitize → A5 confirm (intent stays Speak, no escalation) → LLM expansion → A6 output filter (PL-20) → commit
- **Why LLM here, not /verbatim:** /prose is opt-in to LLM elaboration; /verbatim is opt-out. Per PL-22/23 voice modes.
- **Rejection cases:** LLM expansion fails A6 output filter (canon-drift detected) → soft retry once, then `RejectReason::CanonDrift`.

### 6.3 `/sleep [until <time-spec>]` — fast-forward fiction-time

```rust
pub struct SleepArgs {
    pub until: TimeSpec,                                // "dawn" | "noon" | "next_day" | Hours(u8) | FictionTimeAbsolute(...)
}

pub enum TimeSpec {
    Dawn,
    Noon,
    Dusk,
    NextDay,
    Hours(u8),                                          // 1..=23
    Absolute(FictionTimeTuple),                         // exact target
}
```

- **Intent path:** Command, CommandKind::Sleep
- **Dispatch:** WorldServiceDirect (no LLM for the dispatch; LLM-narration step decoupled per PL_001 §12)
- **Capability:** standard PC-turn capability
- **Effect:** PL_001 §12 sequence executes. Commits `TurnEvent { intent: FastForward, command_kind: Some(Sleep), outcome: Accepted | Rejected, fiction_duration: <resolved> }`
- **Validator chain:** A5 confirm intent → world-rule (`pc.in_combat? pc.in_private_safe?`) → A3 oracle (canon events between now and target?) → resolve TimeSpec → commit
- **Rejection cases:**
  - PC in active combat → `RejectReason::WorldRuleViolation { rule_id: "no_sleep_during_combat" }` per PL_001 §15
  - PC not in private/safe location → `RejectReason::WorldRuleViolation { rule_id: "no_sleep_in_public" }`
  - Canon event scheduled in the sleep window → `RejectReason::WorldRuleViolation { rule_id: "canon_event_intercepts_sleep", detail: "<event description>" }`
  - TimeSpec resolves to past or >30 days → `RejectReason::WorldRuleViolation { rule_id: "sleep_duration_invalid" }`

### 6.4 `/travel to <place>` — move PC to a different cell

```rust
pub struct TravelArgs {
    pub destination: PlaceRef,                          // canonical place reference (place_canon_ref string)
    pub mode: TravelMode,                               // Walking | Horse | Boat — affects fiction_duration calc
}

pub enum PlaceRef {
    CanonicalRef(String),                               // "tương_dương_west_gate"
    PathSpec(Vec<String>),                              // ["southern_song", "tương_dương", "west_gate"]
}

pub enum TravelMode {
    Walking,                                            // ~30 km/day
    Horse,                                              // ~80 km/day
    Boat,                                               // ~120 km/day downriver
}
```

- **Intent path:** Command, CommandKind::Travel
- **Dispatch:** WorldServiceDirect
- **Capability:** standard PC-turn capability
- **Effect:** PL_001 §13 5-op chain executes. Commits `TurnEvent { intent: FastForward, command_kind: Some(Travel), outcome: Accepted | Rejected, fiction_duration: <calc'd from distance + mode> }`
- **Validator chain:** A5 → A3 oracle (destination exists in canon? PC has the means? travel route safe?) → world-rule → distance calc → commit
- **Rejection cases:**
  - Destination unknown to canon → `RejectReason::OracleContradiction { fact_id: "place:<ref>" }`
  - PC blocked by active scene (NPC holding PC, dialogue tree mid-stream) → `RejectReason::WorldRuleViolation { rule_id: "travel_blocked_by_scene" }`
  - Cell at max capacity → `RejectReason::WorldRuleViolation { rule_id: "cell_capacity" }` per PL_001 §13 edge case
  - Travel duration >30 days fiction-time → `RejectReason::WorldRuleViolation { rule_id: "travel_too_long" }` (suggest split or `/long_journey` V2)
  - PC currently in turn-slot owned by another action → `RejectReason::WorldRuleViolation { rule_id: "concurrent_turn" }`

### 6.5 `/help [command]` — meta-command, returns canned response

```rust
pub struct HelpArgs {
    pub topic: Option<String>,                          // None = list all; Some("sleep") = explain /sleep
}
```

- **Intent path:** Command, CommandKind::Help (Meta-flagged)
- **Dispatch:** GatewayLocal (does NOT round-trip to roleplay-service or world-service)
- **Capability:** none required
- **Effect:** returns a canned response in HTTP 200 body; **does NOT commit a TurnEvent**, **does NOT advance `turn_number`**, **does NOT write to event log**. PC's turn-slot is NOT claimed (no validator chain).
- **Validator chain:** none beyond schema parse.
- **Rejection cases:** unknown topic → returns "Lệnh không tồn tại. Các lệnh có sẵn: /verbatim /prose /sleep /travel /help".

**Why /help is special:** meta-commands shouldn't burn a turn or block the cell's turn-slot. Treating /help as a turn would mean PC can't speak while reading help. The trade-off: /help bypasses the normal `TurnEvent` event log entry — there is no audit trail of "PC asked for help". Acceptable for V1 (low security risk). V2 may add a separate `meta_command_audit` aggregate if abuse is observed.

---

## §7 Intent classification + dispatch (parse pipeline)

### 7.1 The pipeline

```text
PC text input
    │
    ▼
gateway POST /v1/turn { session_id, turn_text, idempotency_key }
    │
    ▼
gateway: idempotency cache check (PL_001 §14)
    │ (cache miss)
    ▼
gateway → A5 intent classifier (roleplay-service has the classifier endpoint)
    │
    │ classifier output:
    │   { intent: Intent, confidence: f32, parsed_command: Option<ParsedCommand> }
    ▼
dispatch by intent:
    │
    ├── Intent::Command + parsed_command.command_kind == Help
    │       → GatewayLocal: return canned response, NO TurnEvent
    │
    ├── Intent::Command + parsed_command.command_kind == Verbatim
    │       → WorldServiceDirect: skip roleplay; commit TurnEvent
    │
    ├── Intent::Command + parsed_command.command_kind ∈ {Sleep, Travel}
    │       → WorldServiceDirect: validator chain + commit (PL_001 §12, §13)
    │       → roleplay-service decoupled narration step (post-commit)
    │
    ├── Intent::Command + parsed_command.command_kind == Prose
    │       → RoleplayService: LLM expand → A6 output filter → WorldServiceDirect commit
    │
    ├── Intent::FreeNarrative
    │       → RoleplayService: full LLM turn (PL_001 §11) including tool-call check against ToolCallAllowlist
    │
    └── Intent::FactQuestion
            → OracleService (A3): query canon → return answer in HTTP body
            → NO TurnEvent commit; NO turn_number advance; NO turn-slot claim
```

### 7.2 Classifier confidence threshold

A5 returns `confidence: f32`. PL_002 locks:

- `confidence >= 0.9` → trust the classification, dispatch
- `0.7 <= confidence < 0.9` → soft-confirm: ask user "Có phải bạn muốn /sleep until dawn không? [Y/n]" (only for Command intent — FreeNarrative ambiguity defaults to FreeNarrative without prompt)
- `confidence < 0.7` → fall through to FreeNarrative as the safe default

**Why FreeNarrative is the safe default:** misclassified commands cause unwanted state mutations (PC accidentally `/sleep`s); misclassified narrative just produces a slightly off-tone LLM response. The asymmetry is not acceptable in MMO context — state changes must be intentional.

### 7.3 Soft-confirm UX

When confidence is in `[0.7, 0.9)`, gateway returns a special response:

```json
{
  "outcome": "ConfirmRequired",
  "candidate_command": { "kind": "Sleep", "args": { "until": "Dawn" } },
  "candidate_text_render": "/sleep until dawn",
  "free_narrative_fallback": "Lý Minh tựa vào ghế, mỏi mệt sau ngày dài.",
  "idempotency_key": "<same as submit>"
}
```

UI shows: "Có phải bạn muốn `/sleep until dawn`? [Yes / No, just narrate]". User chooses → UI POSTs `/v1/turn/confirm` with the same `idempotency_key` + chosen branch. Server commits accordingly. `turn_number` only advances on the confirmed branch.

`turn_idempotency_log` (PL_001 §14.3) covers the confirm flow — second POST with same key returns the same response if already committed.

### 7.4 Tool-call allowlist enforcement

When dispatch goes to `RoleplayService` (FreeNarrative or /prose), the LLM call is wrapped:

```text
roleplay-service:
  allowlist = read tool_call_allowlist(reality, actor_type=PC) [cached]
  prompt = assemble per PL-4 with allowed_calls=allowlist.allowed_calls
  llm_response = llm.stream(prompt, tools=allowlist.allowed_calls)

  for each tool_call in llm_response.tool_calls:
    if tool_call.name not in allowlist.allowed_calls:
      reject this turn: RejectReason::WorldRuleViolation { rule_id: "tool_call_not_allowed" }
    if tool_call.count > allowlist.max_per_turn:
      reject: RejectReason::WorldRuleViolation { rule_id: "tool_call_burst_exceeded" }
    validate args against tool_call.args_schema
    if invalid: reject: ParseError

  emit proposal event with tool_calls → world-service consumer
```

**V1 allowlist for `actor_type=PC`:**

| Tool name | Args | max_per_turn | Why allowed |
|---|---|---|---|
| `speak` | `{ text: String }` | 3 | normal RP |
| `emote` | `{ animation: String, target: Option<ActorRef> }` | 2 | non-state-changing flavor |
| `move_within_cell` | `{ target_position: PositionRef }` | 1 | within-cell movement (no /travel; no cell change) |

**V1 allowlist for `actor_type=NPC_Reactive`:**

| Tool name | Args | max_per_turn |
|---|---|---|
| `speak` | `{ text: String }` | 5 |
| `emote` | `{ animation: String, target: Option<ActorRef> }` | 3 |
| `move_within_cell` | `{ target_position: PositionRef }` | 1 |
| `hint_intent` | `{ kind: IntentKind, target: ActorRef }` | 1 |

**Forbidden for ALL actor types at V1** (must go through deterministic dispatch, NOT LLM): `damage`, `currency_mutation`, `item_transfer`, `travel`, `sleep`, `canon_promotion`, `cell_create`, `actor_bind`. PL-6 catalog explicit.

---

## §8 Pattern choices

### 8.1 Parse strategy: deterministic regex + JSON Schema, NOT LLM

The PARSE step (turn_text → ParsedCommand) is deterministic regex matching. The CLASSIFY step (which Intent) uses A5's LLM-based classifier. **Don't let the LLM parse args.**

- **Why:** LLM-parsed args are non-deterministic and untrusted. A regex parser for `/sleep until dawn` is 5 lines of code and provably correct. An LLM could hallucinate `until: "tomorrow at midnight"` which doesn't fit any TimeSpec variant.
- **Implementation:** `gateway` runs regex first against known commands; on match, it constructs the typed `CommandArgs`. On no-match-but-starts-with-`/`, it returns the parse error immediately (don't even classify). On no-match-and-no-leading-`/`, route to A5 for classification.

### 8.2 LLM trust boundary

LLM is trusted to:
- Produce narrator_text (post-commit, output-filtered by A6/PL-20)
- Suggest the player's intent in /prose mode
- Issue tool calls within allowlist

LLM is NOT trusted to:
- Decide whether a command should commit
- Choose `command_kind` 
- Choose `fiction_duration` outside narrative-affecting bounds (LLM can suggest fiction_duration for FreeNarrative within [5s, 1h]; commands' fiction_duration is computed by world-service from typed args)
- Issue any tool not in `tool_call_allowlist`

### 8.3 No "macros" or "aliases" in V1

Player cannot define `/foo = /sleep until dawn`. Macros are a UI-layer concern (frontend may render shortcut buttons that expand to canonical commands) but the server-side grammar is the closed set in §6. V2 may add macros via DF-equivalent.

---

## §9 Failure-mode UX

Per command + per failure type, locked Vietnamese copy + English ops detail.

| RejectReason variant | rule_id / kind | Vietnamese copy (PC) | English (ops log) |
|---|---|---|---|
| `WorldRuleViolation` | `verbatim_size` | "Lời nói quá dài, hãy ngắt câu." | "verbatim raw_text exceeds 2 KB" |
| `WorldRuleViolation` | `no_sleep_during_combat` | "Đang loạn, không ngủ được." | "PC.in_combat=true at sleep request" |
| `WorldRuleViolation` | `no_sleep_in_public` | "Nơi này không an toàn để ngủ." | "scene.metadata.private_safe=false" |
| `WorldRuleViolation` | `canon_event_intercepts_sleep` | "Có chuyện sắp xảy ra, không ngủ được tới giờ đó." | "canon event scheduled in [now, target]" |
| `WorldRuleViolation` | `sleep_duration_invalid` | "Thời gian không hợp lệ. Thử /sleep until dawn?" | "TimeSpec resolved to past or >30d" |
| `WorldRuleViolation` | `travel_blocked_by_scene` | "Đang giữa cảnh, không thể đi ngay được." | "active turn-slot held by other actor" |
| `WorldRuleViolation` | `travel_too_long` | "Quá xa, hãy chia thành nhiều chặng." | "travel duration >30d fiction-time" |
| `WorldRuleViolation` | `cell_capacity` | "Nơi đó đông quá, chọn nơi khác?" | "target cell at max 32 actors" |
| `WorldRuleViolation` | `concurrent_turn` | "Đợi nhân vật khác hành động xong." | "different idempotency_key while turn in flight" |
| `WorldRuleViolation` | `tool_call_not_allowed` | (internal — should not surface to PC; soft-retry once, then fall through to terse turn) | "LLM proposed tool not in allowlist" |
| `WorldRuleViolation` | `tool_call_burst_exceeded` | (internal — same) | "LLM exceeded max_per_turn for tool" |
| `OracleContradiction` | `place:<ref>` | "Nơi đó không có trong thế giới này." | "PlaceRef not found in canon entity index" |
| `CanonDrift` | (any flag) | "Lời này đi lệch khỏi thế giới. Thử nói lại?" | "A6 output filter detected drift; flags=[...]" |
| `ParseError` | (parser kind) | "Không hiểu lệnh. Thử /help?" | "regex match failed; first 32 chars=..." |
| `ParseError` | `unknown_command` | "Lệnh không tồn tại. Có sẵn: /verbatim /prose /sleep /travel /help" | "leading `/` but no matching command" |
| `CapabilityDenied` | — | "Không có quyền thực hiện việc này." | "JWT lacks required claim" |

V2 may localize beyond Vietnamese (English UI, Chinese for wuxia realities). All copy keys live in a `i18n_command_copy` resource — changing copy is a config flip, NOT a re-deploy.

---

## §10 Cross-service handoff (parse pipeline, concrete)

### 10.1 Free narrative path (no command)

```text
UI → gateway POST /v1/turn { idempotency_key=K, turn_text="Lý Minh nâng chén trà..." }
    │
gateway: idempotency cache check
gateway → roleplay-service (Python LLM):
    A5 classify → Intent::FreeNarrative (confidence 0.95)
    PL-4 prompt assemble (with tool_call_allowlist for actor_type=PC)
    PL-5 LLM stream → narrator_text + zero tool_calls
    PL-19/PL-20 sanitize/filter → ok
    emit proposal event
    │
world-service consumer:
    A5 cross-check, A6 retrieval-isolation, world-rule
    claim_turn_slot → advance_turn → t2_write FictionClock → release
    return T2 to gateway
    │
gateway → UI: 200 OK with causality_token
```

### 10.2 /sleep command path (deterministic dispatch)

```text
UI → gateway POST /v1/turn { idempotency_key=K, turn_text="/sleep until dawn" }
    │
gateway: idempotency cache check
gateway: regex parse → ParsedCommand { kind: Sleep, args: SleepArgs { until: Dawn } }
gateway → roleplay-service (only for A5 confirm — single-intent classifier call):
    A5 → Intent::Command (confidence 0.99) ✓ matches gateway parse
    │
gateway → world-service (skip roleplay LLM):
    PL_001 §12 sequence
    return T2 to gateway
    │
gateway → roleplay-service decoupled narration step (NOT a new turn):
    poll FictionClock projection wait_for=T2
    LLM generates wake-up narration
    emit follow-up TurnEvent::Narration tagged with same turn_number
    │
gateway → UI: 200 OK with causality_token
UI: subscribe-stream delivers narration shortly after main commit
```

### 10.3 /travel command path

Same shape as §10.2 but executes PL_001 §13 5-op chain. Returns T5.

### 10.4 Fact question path

```text
UI → gateway POST /v1/turn { idempotency_key=K, turn_text="ai là Hoàng Dược Sư?" }
    │
gateway → roleplay-service: A5 → Intent::FactQuestion
gateway → oracle-service (A3, PL-16):
    canon-scoped retrieval (filter pc_id, timeline_cutoff, reality_id per PL-18)
    return answer
    │
gateway → UI: 200 OK with answer; NO TurnEvent committed; NO turn_number advance
```

### 10.5 /help meta path

```text
UI → gateway POST /v1/turn { idempotency_key=K, turn_text="/help" }
    │
gateway: regex parse → ParsedCommand { kind: Help, args: HelpArgs { topic: None } }
gateway: lookup canned response from local i18n table
    │
gateway → UI: 200 OK with help text; NO TurnEvent; NO classification call to roleplay-service
```

---

## §11 Sequence: ambiguous input with soft-confirm (UX-critical)

PC types `"em mệt rồi, đi nghỉ thôi"`. Is this RP narrative or a sleep command?

```text
UI → gateway POST /v1/turn { idempotency_key=K, turn_text="em mệt rồi, đi nghỉ thôi" }
    │
gateway: text doesn't start with `/` → no regex parse, route to classifier
gateway → roleplay-service A5:
    intent: Command (sleep), confidence: 0.78  ← in soft-confirm zone
    parsed_command: ParsedCommand { kind: Sleep, args: SleepArgs { until: NextDay } }
    │
gateway → UI: 200 OK with body:
    {
      outcome: ConfirmRequired,
      candidate_command: { kind: "Sleep", args: { until: "NextDay" } },
      candidate_text_render: "/sleep until next_day",
      free_narrative_fallback: "Lý Minh thở dài, đứng dậy về phòng nghỉ.",
      idempotency_key: K
    }
    │
UI: render dialog "Có phải bạn muốn /sleep until next_day? [Yes / No, just narrate]"
PC clicks "Yes":
UI → gateway POST /v1/turn/confirm { idempotency_key=K, choice: "command" }
    │
gateway: idempotency_log shows status=AwaitingConfirm; advance to commit
gateway → world-service: PL_001 §12 sequence with the candidate_command
    return T2
    │
gateway → UI: 200 OK with causality_token

(if PC clicked "No, just narrate" → gateway → roleplay-service free narrative path with the
 fallback text as the LLM seed, return regular turn flow)
```

**Idempotency edge:** if PC closes browser between confirm dialog and click, second submit with same key returns the SAME `ConfirmRequired` state (not a new classification call). When PC eventually clicks, server commits. This deduplicates the soft-confirm step itself.

---

## §12 Sequence: rejection of /sleep during siege (cross-reference PL_001 §15)

PC at `cell:yen_vu_lau` types `/sleep until dawn` while a tavern brawl event has just bubbled up.

Gateway parses → ParsedCommand { kind: Sleep, args: { until: Dawn } }. Dispatched to world-service. World-service runs validator chain per §6.3:

```text
A5 confirm: ok (intent=Command)
world-rule: pc.in_combat? → TRUE
   → REJECT: WorldRuleViolation { rule_id: "no_sleep_during_combat", detail: "tửu lâu đang loạn, không ngủ được" }

world-service: build TurnEvent {
  intent: FastForward,
  command_kind: Some(Sleep),
  outcome: Rejected { reason: ... },
  fiction_duration_proposed: 0,
  idempotency_key: K, ...
}
dp.t2_write::<TurnEvent>(...)  → tags with current turn_number = N (no advance, per PL_001 §15)
return ack to gateway

gateway → UI: 200 OK with body {
  outcome: Rejected,
  reason: { kind: "world_rule_violation", rule_id: "no_sleep_during_combat", detail: "..." },
  vi_copy: "Đang loạn, không ngủ được.",   // from §9 lookup
  turn_number: N (unchanged),
  fiction_time: <unchanged>,
}

UI renders: "⚠ Lý Minh không thể ngủ — đang loạn, không ngủ được."
```

PL_001 §15 already locked the contract for the t2_write-not-advance_turn path. PL_002 only adds the per-rule_id Vietnamese copy lookup.

---

## §13 Acceptance criteria (LOCK gate)

The design is implementation-ready when gateway-bff + roleplay-service + world-service can pass these scenarios. Each is one row in the integration test suite. LOCK granted after all 10 pass.

### 13.1 Happy-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-GR-1 FREE NARRATIVE** | PC types "Lý Minh nâng chén trà, nhìn ra ngoài cửa sổ" (no leading `/`). | gateway routes to A5 classifier → `Intent::FreeNarrative, confidence ≥ 0.9`; roleplay-service emits **EVT-T6 Proposal** (sub-type=PCTurnProposal); world-service validator chain accepts; commits **EVT-T1 Submitted/PCTurn::Speak** with `command_kind=None`, `narrator_text=<LLM output>`. fiction_clock advances per fiction_duration_proposed. |
| **AC-GR-2 /VERBATIM** | PC types "/verbatim Tôi đến từ tương lai". | gateway regex parses → `ParsedCommand { kind: Verbatim, args: VerbatimArgs { raw_text: "Tôi đến từ tương lai" } }`; dispatch=WorldServiceDirect (no LLM call); commits **EVT-T1 Submitted/PCTurn::Speak** with `narrator_text=raw_text` (exact, no paraphrase) + `command_kind=Verbatim` + `fiction_duration=5s`. A6 sanitize runs on raw_text only. |
| **AC-GR-3 /SLEEP UNTIL DAWN** | PC types "/sleep until dawn" at fiction-time 1256-thu-day3-Tý-sơ. | gateway regex → `SleepArgs { until: TimeSpec::Dawn }`; world-service: world-rule check (in_private_safe ✓, not in_combat ✓, no canon event blocks) → resolves dawn=Mão-sơ next-day → fiction_duration=6h → commits **EVT-T1 Submitted/PCTurn::FastForward** with `command_kind=Sleep`; emits derived **EVT-T3 Derived** mutations (FictionClockAdvance + DayPasses calibration sub-shape per §12 PL_001b). |
| **AC-GR-4 /TRAVEL TO TƯƠNG DƯƠNG** | PC at `cell:yen_vu_lau` types "/travel to Tương Dương". | gateway regex → `TravelArgs { destination: PlaceRef::CanonicalRef("tương_dương_west_gate"), mode: Walking }`; world-service executes PL_001 §13 5-op chain → commits **EVT-T1 Submitted/PCTurn::FastForward** + **EVT-T3 Derived** (FictionClockAdvance + EntityBindingDelta + SceneStateInit + 23×DayPasses calibration) + **EVT-T4 System** (MemberLeft + MemberJoined). UI's post-travel reads with `wait_for=T5` succeed within 20s. |

### 13.2 Failure-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-GR-5 PARSE ERROR — UNKNOWN COMMAND** | PC types "/foo blabla" (leading `/` but no matching command in V1 closed set). | gateway regex finds `/` prefix but no command match; rejects immediately with `parse.unknown_command`; UI toast: "Lệnh không tồn tại. Có sẵn: /verbatim /prose /sleep /travel /help"; no roleplay-service call, no world-service call, no event committed. |
| **AC-GR-6 SOFT-CONFIRM AMBIGUOUS** | PC types "em mệt rồi, đi nghỉ thôi" (no leading `/`; intent ambiguous). | A5 returns `Intent::Command, confidence: 0.78` (in `[0.7, 0.9)` zone per §7.2); gateway returns `200 OK { outcome: ConfirmRequired, candidate_command: Sleep, candidate_text_render: "/sleep until next_day", free_narrative_fallback: "...", idempotency_key: K }`; UI shows dialog; user picks branch; second POST `/v1/turn/confirm` with same key + chosen branch → commits accordingly. Idempotency log preserves the confirm step. |
| **AC-GR-7 REJECTION DURING COMBAT** | PC types "/sleep until dawn" while active combat scene (per WA_002 / world-rule check). | world-rule validator detects `pc.in_combat=true`; rejects with `world_rule.no_sleep_during_combat`; commits **EVT-T1 Submitted/PCTurn::FastForward** with `outcome=Rejected { rule_id: "world_rule.no_sleep_during_combat", detail }` via `t2_write` per PL_001 §15 (NOT advance_turn — see GR-D8 watchpoint); turn_number UNCHANGED; fiction_clock UNCHANGED; UI shows reject copy. |
| **AC-GR-8 TOOL-CALL DENIED** | Free narrative LLM proposes a `damage` tool-call (FORBIDDEN per §7.4 V1 allowlist). | Validator pipeline: LLM emits Proposal with tool_calls=[damage]; allowlist enforcement detects `damage NOT in allowed_calls` for `actor_type=PC`; rejects with `world_rule.tool_call_not_allowed`; soft-retry once (re-prompt without the tool); on second failure, fall through to terse turn (commit Speak with narrator_text only, no state mutations). |

### 13.3 Boundary scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-GR-9 /HELP META** | PC types "/help" or "/help sleep". | gateway regex → `HelpArgs { topic: None | Some("sleep") }`; dispatch=GatewayLocal; returns `200 OK { help_text: <canned> }`; **NO LLMProposal**, **NO TurnEvent committed**, **NO turn_number advance**, **NO turn-slot claim**. Audit-only log entry (V1 may even skip audit per §6.5). |
| **AC-GR-10 FACT QUESTION** | PC types "ai là Hoàng Dược Sư?" (no `/` prefix; A5 classifies FactQuestion). | A5 returns `Intent::FactQuestion, confidence ≥ 0.9`; gateway routes to oracle-service (PL-16); oracle returns canon-grounded answer with timeline-cutoff filter per PL-18; UI renders answer in chat; **NO TurnEvent committed**; **NO turn_number advance**; **NO turn-slot claim**. |

**Lock criterion:** all 10 scenarios have a corresponding integration test that passes. Until then, status is `CANDIDATE-LOCK` (post-acceptance criteria) → `LOCKED` (after tests).

---

## §14 Open questions deferred + their landing point

| ID | Question | Defer to |
|---|---|---|
| GR-D1 | Macros / aliases — player-defined `/myalias = /sleep until dawn` | V2 — likely a separate feature `PL_NNN_macros` |
| GR-D2 | Multi-arg commands like `/give <npc> <item>` requiring inventory state | DF7 (PC stats) — depends on item system |
| GR-D3 | Voice-mode-aware narrator paraphrasing of /verbatim outputs (e.g. terse mode quotes verbatim, novel mode wraps in scene description) | PL-22/PL-23 (catalog) |
| GR-D4 | Localization beyond Vietnamese (English / Chinese / etc.) UX copy | Phase 5 (i18n rollout) |
| GR-D5 | Per-actor-type allowlist for NPC_Routine (NPCs acting on schedule with no PC present) | DL_001 (NPC routine foundations) |
| GR-D6 | Soft-confirm threshold tuning per command kind (sleep maybe stricter than emote) | Phase 5 ops — adjust based on prod misclassification rate |
| GR-D7 | Streaming partial parse — UI hints "looks like a sleep command" as user types | UI polish (V2) |
| GR-D8 | **Drift watchpoint with EVT-T1 spec.** Rejected turns (PL_001 §15 + PL_002 §6.3 / §6.4 reject cases) commit via plain `dp::t2_write::<TurnEvent>` so `turn_number` stays at N — but old EVT-T1 PlayerTurn spec said `dp::advance_turn` unconditionally. PL_001/PL_002 honor MV12-D11 (advance only on accepted). | **Tracked in [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md)** — Option C redesign 2026-04-25 reframed EVT-T1 to "Submitted" mechanism category (sub-types feature-owned per EVT-A11). The per-outcome commit primitive distinction may be resolved by event-model agent's Phase 2 per-category contracts. The boundary folder is the single source of truth; this row is audit-trail. PL_001/PL_002's `t2_write` interpretation stands as feature-side contract until reconciled. |

---

## §15 Cross-references

- [PL_001 Continuum](PL_001_continuum.md) — TurnEvent shape, RejectReason, idempotency, capability claims
- [PL_001b Continuum lifecycle](PL_001b_continuum_lifecycle.md) — §14 reconnect+idempotency flow that GR-002's confirm step rides on
- [05_llm_safety/](../../05_llm_safety/) — A3 World Oracle (PL-16), A5 intent classifier (PL-15), A6 injection defense (PL-19/PL-20)
- [07_event_model/02_invariants.md](../../07_event_model/02_invariants.md) — EVT-A1..A8 axioms (esp. EVT-A4 producer binding + EVT-A7 LLM proposal lifecycle that this feature follows)
- [07_event_model/03_event_taxonomy.md](../../07_event_model/03_event_taxonomy.md) — EVT-T1..T11 closed set; PL_002 §2.5 maps every dispatch path to a category
- [catalog/cat_04_PL_play_loop.md](../../catalog/cat_04_PL_play_loop.md) — PL-2 (this feature), PL-6 (tool-call allowlist), PL-15 (3-intent classifier), PL-22 (voice mode), PL-23 (inline voice override)
- [decisions/locked_decisions.md](../../decisions/locked_decisions.md) — MV12-D9 resolved here
- [features/_spikes/SPIKE_01_two_sessions_reality_time.md](../_spikes/SPIKE_01_two_sessions_reality_time.md) — narrative grounding (turns 5/11/16 used /verbatim, /sleep, /travel)

---

## §16 Implementation readiness checklist

- [x] **§2.5** EVT-T* mapping (every dispatch path mapped; closed-set proven)
- [x] **§3** Aggregate inventory (1 new: `tool_call_allowlist`; 4 PL_001 references)
- [x] **§4** Tier+scope table (DP-R2)
- [x] **§5** DP primitives by name
- [x] **§6** Per-command contracts — 5 commands fully specified with typed args + validator chain + reject cases
- [x] **§7** Parse pipeline + classifier confidence threshold + soft-confirm UX
- [x] **§8** Pattern choices (deterministic regex parse, LLM trust boundary, no V1 macros)
- [x] **§9** Per-rule_id Vietnamese + English copy table
- [x] **§10** Cross-service handoff for 5 dispatch paths (free narrative, /sleep, /travel, fact question, /help)
- [x] **§11** Soft-confirm sequence
- [x] **§12** Rejection sequence (cross-references PL_001 §15)
- [x] **§13** Acceptance criteria (10 scenarios across happy-path / failure-path / boundary)
- [x] **§14** Deferrals (GR-D1..D8); GR-D8 hybrid-tracked in `_boundaries/01_feature_ownership_matrix.md`

**Status transition:** DRAFT (2026-04-25 first commit `f89aa48`; Option C terminology applied by event-model agent) → **CANDIDATE-LOCK** (2026-04-25 closure pass: §13 acceptance criteria added). LOCK granted after the 10 §13 acceptance scenarios have passing integration tests.

**Next** (when this doc locks): gateway adds command regex parser; roleplay-service adds A5 classifier endpoint + soft-confirm response shape; world-service adds the 5 command dispatchers wired to PL_001's primitives. Vertical-slice target: SPIKE_01 turns 5, 11, 16 (the three /verbatim, /sleep, /travel uses) all execute end-to-end.
