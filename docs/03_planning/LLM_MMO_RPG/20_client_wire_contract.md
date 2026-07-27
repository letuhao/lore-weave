# 20 — Client wire contract (W0/W1/W2 · movement · turns · resume · versioning)

> **Status:** DRAFT — 2026-07-27. Closes **REC-70** and **REC-74** (the "one genuinely undesigned
> surface" of `19` §15). Everything here sits on decisions ALREADY made and, where marked, on
> **live server behavior** shipped 2026-07-27 (`commit-service` spine): this contract cites running
> code, not speculation. Axioms `CWC-A1..A9`, decisions `CWC-D1..D8`, open `CWC-Q1..Q4`.
> **Prefix `CWC` + the DTO registry rows are PENDING a `_boundaries/` lock claim** — nothing in
> this doc is registered yet (stated per the record-correction discipline).
>
> Inherited settlements (do not reopen): **REC-71** — Colyseus carries the game (W0/W1/W2,
> `turn.outcome`, patch broadcast, event stream); gateway WS stays platform/chat. **REC-72** —
> resume is the DP-Ch18 `from_tokens: HashMap<ChannelId, u64>` map. **REC-73** — W1 ships client
> DTOs, never server aggregates. **REC-75** — `client_protocol: u16` in W0; server upcasts to
> latest before fanout. **REC-76** — i18n needs a per-message-class rule (given here, CWC-D7).

---

## 1. The seam in one picture

```
browser client (Colyseus JS client, one room per session)
   │  W0 bind ←→ ack · W1 first frame · W2 streamed
   │  movement intents (Class A)  · turn submissions (Class B)
   ▼
game-server (TS — WS edge ONLY; PRR-20 edge controls; Colyseus rooms)
   │  room = a PROJECTION of channel state (GDA-A7) — game-server holds no authority
   │  Class A: walkability.wasm validation (RTM-Q10) + position patch fanout
   │  Class B: proposal → the bus (EVT-T1 player category)
   ▼
commit-service spine (Rust — LIVE 2026-07-27)  →  committed events → outbox → publisher
   │                                                        │
   └── turn.resolved / turn.discarded / proposal.rejected ──┴──► room fanout (upcast to latest)
```

> **CWC-A1 — The room is a projection, and the client is a projection of the room.** No client
> message mutates state directly; every state-bearing thing the client ever receives is derived
> from committed events (Class B) or the RTM ephemeral layer (Class A). A client that invents
> state is wrong by construction; a client that caches derived state is fine (CWC-A7).

---

## 2. W0 — bind ack (≤100 ms)

Sent by the server on successful room join (auth already passed the PRR-20 edge).

```ts
interface W0BindAck {
  session_id: string;
  capability_token: string;        // DP-K9 capability, opaque to the client
  reality_id: string;              // UUID
  channel_id: string;              // the cell channel the PC binds to (BIGINT as string — JS ints lie past 2^53)
  ruleset_digest: string;          // RLS-A13 content address (hex BLAKE3)
  from_tokens: Record<string, string>; // DP-Ch18 per-channel cursors: channel_id → last channel_event_id seen server-side for this session (BIGINT-as-string)
  client_protocol: 1;              // CWC-A5: the protocol this contract defines IS v1
  server_time_hint_ms: number;     // wall-clock hint for UI only — NEVER simulation-relevant (TDIL-A9)
}
```

> **CWC-A2 — Every 64-bit integer crosses the wire as a decimal string.** `channel_event_id`,
> `from_tokens` values, `turn_number` — all BIGINT server-side and all corrupted silently by JS
> `number` past 2^53. One rule, no exceptions, enforced in the DTO schema.

Reconnect = **W0 + catch-up, never W1** (GDA-D7): the client presents its own `from_tokens`; the
server streams the gap per channel. A fresh W1 is sent only when a cursor is older than the bus
retention window (DP-X2) — the server decides, the client just renders what arrives.

## 3. W1 — first frame (≤500 ms) · the DTO layer

> **CWC-A3 — W1 DTOs are a CONTRACT surface, versioned with `client_protocol`, and they never
> leak server aggregate shapes** (REC-73: `InventorySummary` ≠ ITM-A9's prompt digest;
> `RosterEntry` ≠ any server roster row). Each DTO lives in `contracts/game-wire/` (to be
> scaffolded beside `contracts/agent/`) as JSON Schema — BE serializer and FE decoder are both
> machine-checked against the same file (Frontend-Tool-Contract discipline applied to the game).

| DTO | Contents (v1) |
|---|---|
| `PcSelf` | entity id · display name · `vital_pool` bands (current/max per pool) · stat block (DF7 client-visible subset) · `actor_status` list (PL_006 client-visible entries) |
| `InventorySummary` | equipped items (slot → `ItemCard`) · carried count · encumbrance band; **not** the ≤29-line LLM digest |
| `ItemCard` | item id · display name · kind · rarity band · one-line effect text (pre-localized, CWC-D7) |
| `RosterEntry` | entity id · display name · disposition (friendly/neutral/hostile) · hp BAND (never numeric for non-party — THR-A4/REC-79: identity and state as separate fields) · position (cell coords) |
| `CellFrame` | `place` header · `cell_scene_layout` · `tilemap_view` (RTM/TMP client slice) · `RosterEntry[]` |
| `CombatFrame` | present iff an encounter is active: encounter channel_id · initiative order (entity ids) · `turn_number` (string) · own action budget |

## 4. W2 — streamed (best-effort)

Channel history (last N committed events, upcast), ruleset client-subset **cached by digest**
(content-addressed ⇒ a returning client with the digest skips it entirely), full inventory,
adjacent-cell previews, non-active i18n bundles. Nothing in W2 blocks play; W1 alone must render.

## 5. Movement (Class A — RTM lane)

Four frames, exactly the RTM set (`08` — move-input delta · position patch · snap-back · mode-flip):

```ts
// client → server (≤ 20 Hz, client-clamped)
interface MoveIntent { seq: number; dx: number; dy: number; }        // delta, cell-local milli-units (i32 — MAP §5)
// server → client
interface PositionPatch { entities: [id: string, x: number, y: number][]; }  // AOI-filtered batch
interface SnapBack { seq: number; x: number; y: number; reason: "walkability" | "speed" | "authority"; }
interface ModeFlip { mode: "realtime" | "turn_based"; encounter_channel?: string; } // RTM↔combat handoff
```

> **CWC-A4 — Movement frames NEVER carry authority.** `MoveIntent.seq` is a client echo for
> snap-back reconciliation only. Validation is game-server-side WASM (RTM-Q10); a rejected move
> is a `SnapBack`, not an error. Movement never appears in the event log (Class A, RTM-A/GDA).

## 6. Turn submission + outcome (Class B — the spine lane)

```ts
// client → server
interface TurnSubmit {
  client_request_id: string;     // UUID minted client-side — the EVT-L3 idempotency member
  action: Decision;              // the SAME shape as contracts/agent/decision.schema.json —
}                                // a HumanDriver emits what an LlmDriver emits (AGT-A3)

// server → client (from committed events, upcast)
interface TurnOutcome {
  channel_event_id: string;
  kind: "resolved" | "discarded" | "rejected";
  turn_number: string;           // LIVE LAW (spine 2026-07-27): advances on resolved ONLY —
                                 // a rejection leaves it unchanged and the player retries
                                 // with NO turn cost (EVT-V4, provable from the event log)
  detail: RejectDetail | DiscardDetail | ResolvedDetail;
}
interface RejectDetail { stage: string; user_message: string; }   // pre-localized (CWC-D7)
```

> **CWC-A5 — One Decision vocabulary, four drivers, one wire shape.** The player's UI gestures
> compile to the identical `Decision` proposal an NPC's LlmDriver emits, validated by the same
> closed vocabulary at the same admission gate. There is no separate "player action API".

> **CWC-A6 — `turn.outcome` truth-in-labeling:** `rejected` = validator said no, no turn consumed,
> retry is free; `discarded` = the world moved (SC-A1 precondition), no turn consumed, re-read the
> frame; `resolved` = it happened, turn consumed. The client MUST distinguish the three in UI —
> collapsing them was the confusion CS-A4 exists to prevent.

## 7. Client state model (REC-74)

> **CWC-A7 — Server is the source of truth; the client holds exactly three stores:**
> 1. **Session store (memory):** the live projection — cell frame, roster, combat frame, own PC.
>    Rebuilt from W0+catch-up or W1 on every (re)connect; never persisted.
> 2. **Digest cache (IndexedDB):** content-addressed blobs ONLY — ruleset client-subset by
>    `ruleset_digest`, tilemap views by their content key, i18n bundles by locale+version. Safe
>    on any device because a digest can never be stale — it can only be unused. (This satisfies
>    GDA-D6 without violating the no-localStorage rule: IndexedDB, keyed by content, holding
>    nothing user-authored. CWC-D5.)
> 3. **Preferences:** platform rules apply unchanged (server-synced via `/v1/me/preferences`).
>
> **Epoch switch (island gen bump / reality ruleset epoch) invalidates store 1 wholesale** —
> the client treats `RulesetEpochActivated` (or a changed `ruleset_digest` in a re-W0) as
> "drop the session store, keep the digest cache, re-frame". Nothing user-visible survives an
> epoch except what the server re-sends; the digest cache survives everything by construction.

## 8. Versioning + i18n

> **CWC-A8 (REC-75) — `client_protocol` is a closed ladder.** The server upcasts every event to
> the latest schema before fanout; a client older than the server's floor receives
> `W0Reject{code:"client_upgrade_required", min_protocol}` — the force-upgrade signal — instead
> of a bind ack. No per-event negotiation, no downcasting, ever.

> **CWC-D7 (REC-76) — i18n per-message-class rule:** narration/prose = pre-resolved server-side
> in the session locale (it came from an LLM in a language; it is content, not a key);
> **system/validator messages** (`RejectDetail.user_message`, status names, item effect lines) =
> resolved server-side from the active locale at send time; **static UI chrome** = client-side
> bundles (W2, cached by version). Locale switch mid-session re-requests W1 (cheap, rare) —
> never re-translates history.

## 9. Decisions & open questions

| # | Decision |
|---|---|
| CWC-D1 | Colyseus room = the ONLY game transport to the browser (REC-71 restated as contract). |
| CWC-D2 | All 64-bit ints wire as decimal strings (CWC-A2). |
| CWC-D3 | DTO schemas live in `contracts/game-wire/` (JSON Schema, machine-checked both sides). ✅ **SCAFFOLDED 2026-07-27** — `common`/`session`/`movement`/`turn` schemas + README + lint; `TurnSubmit.action` `$ref`s `contracts/agent/decision.schema.json` rather than copying it (CWC-D6 made structural). |
| CWC-D4 | Reconnect = W0 + per-channel catch-up (GDA-D7 restated); W1 only on cursor-expiry. |
| CWC-D5 | IndexedDB digest cache — content-addressed only, never user data (satisfies GDA-D6 within platform rules). |
| CWC-D6 | `TurnSubmit.action` = the `contracts/agent/` Decision envelope verbatim (AGT-A3 four-drivers-one-shape). |
| CWC-D7 | i18n per-message-class rule (§8). |
| CWC-D8 | Movement stays out of the event log; `ModeFlip` is the only frame that touches both lanes (it announces the encounter channel W0-style binding). |

| # | Open |
|---|---|
| CWC-Q1 | AOI patch batching cadence + budget (RTM-A6..A8 gives the model; the Hz/size numbers need a measured client). |
| CWC-Q2 | W1 composition budget under Cold-cell wakeup (GDA-Q1 rescoped) — needs R1-ladder measurement with the real tilemap slice. |
| CWC-Q3 | Spectator/privacy slice of the event stream (Q32 bubble-up) — which committed events a non-participant's room projection may fan out. |
| ~~CWC-Q4~~ | ✅ **RESOLVED 2026-07-27 at scaffolding — NEITHER.** `TestOpenAPIRouteConformance` walks a live router (game-wire has no HTTP routes); the frontend-tools test regenerates a snapshot *from code* (game-wire is contract-FIRST — the schema exists because producer and consumer don't yet). The gate is a **schema-integrity lint** over the hand-authored SoT (`scripts/game-wire-lint.py`, pre-commit: refs resolve incl. cross-contract · CWC-A2 id-strings · closed objects; bite-proven on 3 planted defects), **plus producer-conformance tests per language as producers appear**. First producer shipped: `commit-service::wire` (committed event → `TurnOutcome`), whose tests red if the Rust enum drifts from the schema's closed set. |

## 10. Cross-references

`17` §4 B5 (W0/W1/W2 budgets + sources) · `08` RTM (movement authority) · `15` + the live spine
(turn law, rejection kinds) · `11` AGT (Decision shape) · `19` §11c/§12b (REC-70..76) ·
`contracts/agent/` (the Decision envelope this contract reuses).
