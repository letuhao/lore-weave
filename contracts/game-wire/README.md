# `contracts/game-wire/` — the client wire contract

JSON Schema SoT for everything that crosses between the browser client and the
server, per [`docs/03_planning/LLM_MMO_RPG/20_client_wire_contract.md`](../../docs/03_planning/LLM_MMO_RPG/20_client_wire_contract.md)
(CWC-D3). Transport is the Colyseus room (REC-71); `game-server` is the WS edge,
`commit-service` is the authority.

| File | Messages |
|---|---|
| `common.schema.json` | `Uint64String`, `EntityId`, `Uuid`, `Digest`, `HpBand`, `Disposition`, `CellCoord` |
| `session.schema.json` | `W0BindAck`, `W0Reject`, `W1FirstFrame` + the DTO layer (`PcSelf`, `InventorySummary`, `ItemCard`, `RosterEntry`, `CellFrame`, `CombatFrame`) |
| `movement.schema.json` | `MoveIntent`, `PositionPatch`, `SnapBack`, `ModeFlip` (Class A / RTM lane) |
| `turn.schema.json` | `TurnSubmit`, `TurnOutcome` + `Resolved`/`Discard`/`Reject` details (Class B / spine lane) |

## The three rules the lint enforces

1. **CWC-A2 — every 64-bit id crosses as a decimal string.** `channel_event_id`,
   `turn_number`, `channel_id`, `*_id` are all BIGINT server-side; JS `number`
   corrupts past 2^53. The bug is invisible in dev (small ids round-trip fine)
   and silent in production, so it is enforced mechanically, not by review.
2. **Closed objects.** Every object with `properties` sets
   `additionalProperties: false`, and every `enum` declares its type. An open
   object is how a field silently drifts between two languages joined only by a
   wire (the `panel_id` free-string bug — see the Frontend-Tool Contract).
3. **Refs resolve, including across contracts.** `TurnSubmit.action` `$ref`s
   [`../agent/decision.schema.json`](../agent/decision.schema.json) rather than
   copying it: a player's UI gesture and an NPC LlmDriver's proposal are the
   *same object* (AGT-A3, CWC-D6). Copying the shape would be the polyglot
   mirror-drift bug class.

## CWC-Q4 resolved (2026-07-27) — why this gate, not the other two

- `TestOpenAPIRouteConformance` walks a live chi router; game-wire has no HTTP routes.
- The frontend-tools contract test regenerates a snapshot **from code**; game-wire is
  contract-**first** — the schema exists precisely because the producer and consumer
  don't yet.

So: **schema-integrity lint over the hand-authored SoT**
(`scripts/game-wire-lint.py`, pre-commit when a `contracts/{game-wire,agent}/*.json`
is staged), plus **producer conformance tests per language, added as producers
appear**. First producer: `services/commit-service/src/wire.rs` — projects a
committed event into `TurnOutcome` and asserts against this schema (id-strings,
`kind` enum arity, the 5-variant discard set). That is what keeps the contract
*consumed* rather than stored.

## Status

Schemas are DRAFT alongside doc 20; the `CWC` prefix and these DTO rows are
**pending a `_boundaries/` lock claim** — stated, not claimed.
