# Plan — Full client data flow (closing the loop)

> L. PO 2026-07-27 15:49: *"design rồi implement đầy đủ data flow"*. Wire contract =
> [`20_client_wire_contract.md`](../03_planning/LLM_MMO_RPG/20_client_wire_contract.md) (CWC-*);
> server spine = [`15_commit_service.md`](../03_planning/LLM_MMO_RPG/15_commit_service.md);
> categories = `07_event_model/03_event_taxonomy.md`.

## Where the loop is broken today

Outbound is real and live (`f29c14a8c`): commit → outbox → publisher → `lw.events.*` → room →
`turn.outcome`. Three things are missing before a client can actually *play*:

| # | Gap | Consequence |
|---|---|---|
| **G1** | **Committed payloads carry a Rust `Debug` STRING** (`format!("{outcome:?}")` → `"Applied { events: [Struck { attacker: EntityId(1), … }] }"`) | The client cannot render anything. A projection cannot parse a Debug string, and it must never try — that format is not a contract, it changes when a field is added. |
| **G2** | **No W0/W1** — the room broadcasts outcomes but never tells a joining client *what the world looks like* | A client that joins mid-encounter sees nothing until the next turn resolves. |
| **G3** | **No inbound path** — proposals reach the bus only via `redis-cli` by hand | The player cannot act. |

## Design decisions

### D1 — Committed events carry STRUCTURED domain facts (fixes G1)

`CombatEvent` gains `Serialize`; the spine writes `payload.events` as a JSON **array of
structured events**, not a Debug string. The Debug rendering stays only in operator logs.

```json
{"events":[{"type":"struck","attacker":"1","target":"2","damage":10,"hp_left":30}],
 "island_seq":"7"}
```

Entity ids are **decimal strings** (CWC-A2) at this boundary too — the client reads this payload
directly, so the 2^53 rule applies to the event body exactly as it does to the envelope.

> **The rule this encodes:** a `Debug` string in a payload is a wire-format bug, not a
> formatting choice. Anything a consumer must parse is a contract; `{:?}` is explicitly not one.

### D2 — W1 is a REPLAY of the channel, not a new read API (fixes G2)

The room is already a projection (GDA-A7), and the committed stream already carries every fact.
So W1 is built by **replaying `lw.events.<reality>` from `0`** and folding the structured events
into a `CellFrame`/`RosterEntry` view — no new commit-service read endpoint, no second source of
truth that could disagree with the log.

- Cheap and correct at PoC scale; the R1 ladder / snapshot optimisation (doc 17) is the
  *performance* answer for a long-lived channel and rides a later slice, behind the same
  interface.
- This also makes GDA-D7 concrete: reconnect = W0 + catch-up from `from_tokens`, and a
  cursor-expired client just replays further back. Same code path.

### D3 — The room stamps IDENTITY; the client never names its actor (security boundary)

`TurnSubmit` carries `client_request_id` + `action` — and **no actor field** (doc 20 §6, now
enforced rather than merely drawn). The room binds `actor_entity_id` from the authenticated
session. A client that could name its actor could act *as another player* — the confused-deputy
bug the AGT-A2 vocabulary split (`{speak,gesture,emote}` for a player's narration LLM vs an
NPC's action set) exists to prevent.

### D4 — A player submission is EVT-T1, not T6

`15` §7b.2's three origin classes are explicit: **LLM proposal = T6** (full pipeline incl.
injection defense), **player = T1 Submitted** (category subset: world-rule, capability, free-text
sanitisation — *not* the LLM-output stages), system = T5. So admission needs `admit_t1` beside
`admit_t6`; they share the EVT-L3 dedup and the closed-vocabulary check, and differ in which
stages are recorded `NotRun` vs `Skip`:

| Stage | T6 (LLM) | T1 (player) |
|---|---|---|
| a5-intent · a6-sanitize · a6-output · canon-drift | `NotRun` (owed) | **`Skip`** (declared not-applicable — these gate *LLM output*, and a player's tool-call is not that) |
| capability · world-rule · structural | `NotRun` (owed) | `NotRun` (owed) |
| free-text sanitisation | — | `NotRun` (owed — applies to prose fields, which V1 `Decision.rationale` is) |

> `Skip` vs `NotRun` is the whole point of D6 (no silent skips): **`Skip` = "this category
> declares this stage inapplicable"; `NotRun` = "this stage is owed and unbuilt."** Collapsing
> them would hide real debt behind a legitimate-looking absence.

### D5 — `producer_service = "game-server"`, and the triple is minted at the edge

EVT-L3 idempotency triple = `(producer_service, client_request_id, target_channel)`. The
`client_request_id` is **client-minted** (doc 20) so a client retry is naturally idempotent; the
other two come from the room. A client that reuses an id gets the first outcome, not a second
execution — which is exactly what makes a flaky mobile connection safe.

## Build order

1. `CombatEvent: Serialize` + spine writes structured `payload.events` (D1) — with the Rust
   `wire.rs` projection updated to read them.
2. TS: fold structured events into a replayed `CellFrame` + `RosterEntry` (D2); W0/W1 on join.
3. Room: `turn.submit` handler → identity stamp (D3) → XADD T1 proposal to the cell bus (D5).
4. `admit_t1` in commit-service with the D4 stage table.
5. Live: browser-less client (a node harness) joins → W0/W1 → submits → sees its own
   `turn.outcome` come back through the real publisher.
