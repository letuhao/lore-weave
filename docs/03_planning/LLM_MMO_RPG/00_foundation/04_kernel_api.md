# Kernel API

> **The canonical functions every feature calls.** These are the kernel's programmatic contract — not the only code a service writes, but the code it MUST route through for certain classes of action. Skipping these = invariant violation + integration failure.

All APIs live under `contracts/` (planned Go package layout). Foundation points at the kernel chunk that specifies each signature authoritatively.

---

## `contracts/meta/MetaWrite`

**When:** any write to a table in the `loreweave_meta` DB.

```go
func MetaWrite(ctx context.Context, req MetaWriteRequest) error

type MetaWriteRequest struct {
    Table   string          // e.g., "reality_registry"
    Op      MetaWriteOp     // insert / update / delete
    Before  json.RawMessage // nil for insert
    After   json.RawMessage // nil for delete
    Actor   Actor           // user_ref_id OR service SVID
    Reason  string          // required for destructive ops; audit record
}
```

**What it does:**
- Validates schema CHECK constraints (business invariants encoded in SQL).
- Writes the row + a `meta_write_audit` row in one transaction (audit append-only).
- Emits a `meta.<table>.<op>` event via outbox (I13).

**Why you can't write directly:** per-service Postgres role grants SELECT but no INSERT/UPDATE on meta tables. Your service doesn't have the privilege.

**Source:** [02_storage/S04_meta_integrity.md](../02_storage/S04_meta_integrity.md) §12T.3 — decisions S4-D1..D8.

---

## `contracts/meta/AttemptStateTransition`

**When:** any change to a lifecycle-state column (`reality_registry.status`, other `*_lifecycle_audit`-tracked columns).

```go
func AttemptStateTransition(ctx context.Context, req TransitionRequest) error

type TransitionRequest struct {
    ResourceType string  // "reality" | "deploy" | "incident" | ...
    ResourceID   string
    FromState    string
    ToState      string
    Reason       string
    Actor        Actor
}
```

**What it does:**
- Specialization of `MetaWrite()` — adds transition-graph validation (rejects invalid state jumps) + CAS on `from_state` (prevents concurrent-transition races).
- Writes a `<resource>_lifecycle_audit` row.
- Emits `<resource>.state.<new_state>` event.

**State graphs:** defined in `contracts/meta/transitions.yaml` per resource type. Examples:
- Reality: `active → pending_close → frozen → archived → archived_verified → soft_deleted → dropped` (R9, plus `seeding` + `migrating` sidetracks).
- Incident: `declared → triaged → mitigated → resolved → postmortem → closed` (SR2).

**Source:** [02_storage/C05_lifecycle_cas.md](../02_storage/C05_lifecycle_cas.md) §12Q — decisions C5-D1..D6.

---

## `contracts/prompt/AssemblePrompt`

**When:** ANY LLM call (chat, roleplay turn, NPC reply, canon check, canon extraction, admin-triggered, world seed, summary).

```go
func AssemblePrompt(ctx context.Context, pc PromptContext) (*PromptBundle, error)

type PromptContext struct {
    Intent      PromptIntent   // one of 7 enumerated intents
    UserID      string
    RealityID   string
    SessionID   string
    ActorRefs   []string       // PC, NPC, or participant IDs to include
    MemoryRefs  []string
    HistoryRefs []string
    UserInput   string         // RAW user text — wrapped + escaped in [INPUT] section
}

type PromptBundle struct {
    RenderedPrompt string  // 8-section structure; see below
    ProviderConfig ProviderConfig  // resolved model + tier + redaction
    AuditRefID     string  // for prompt_audit row replay
}
```

**What it does:**
- Runs `ResolveContext()` (below) to drop refs that fail S2 / S3 / severance / consent gates.
- Assembles the 8-section prompt using the versioned template for `Intent`.
- XML-escapes + delimiter-wraps user input; user content NEVER appears outside `[INPUT]`.
- Applies PII redaction per provider's retention tier.
- Adds canary token (S9.L5) for injection detection in post-output scan.
- Writes `prompt_audit` row (IDs only, no body).

**8-section structure:**
```
[SYSTEM]        — fixed kernel instruction + intent-specific prelude
[WORLD_CANON]   — L1/L2/L3/L4-marked canon entries (see 05_vocabulary.md)
[SESSION_STATE] — current scene, active turn, participants
[ACTOR_CONTEXT] — target NPC / PC sheet data
[MEMORY]        — retrieved memory for this actor
[HISTORY]       — recent turn history
[INSTRUCTION]   — intent-specific ask
[INPUT]         — <user_input>...</user_input> — ONLY place user text appears
```

**Source:** [02_storage/S09_prompt_assembly.md](../02_storage/S09_prompt_assembly.md) §12Y — decisions S9-D1..D10.

---

## `contracts/prompt/ResolveContext`

**When:** called by `AssemblePrompt` before template rendering; can also be called standalone when you need to check "does this user see this NPC right now?" without building a prompt.

```go
func ResolveContext(ctx context.Context, pc PromptContext) (ResolvedContext, []RejectedRef, error)
```

**Gates applied** (in order):
1. S2 `session_participants` — is the caller a participant of that session? If not, session-scoped refs rejected.
2. S3 `privacy_level` — `sensitive` requires Tier 2+ actor; `confidential` requires Tier 1 (dual-actor).
3. `GetEntityStatus()` — refs with GoneState `severed` / `archived` / `dropped` / `user_erased` → whitelisted prompt marker or rejection.
4. S8 `user_consent_ledger` — if the referenced entity belongs to a user who revoked consent, drop or pseudonymize per scope.

Rejected IDs logged (no content) to `prompt_audit.rejected_refs`.

**Source:** [02_storage/S09_prompt_assembly.md](../02_storage/S09_prompt_assembly.md) §12Y.4.

---

## `contracts/entity_status/GetEntityStatus`

**When:** need to know the current "aliveness" of any user-visible entity (reality, session, PC, NPC, canon entry, user account).

```go
func GetEntityStatus(ctx context.Context, entityType, entityID string) (EntityStatus, error)

type EntityStatus struct {
    State           GoneState  // active | severed | archived | dropped | user_erased
    StateChangedAt  time.Time
    ReasonRef       string     // points at audit row
    Recoverable     bool
    RecoveryMethod  string     // "admin/relink-ancestor" | "admin/unarchive-reality" | ... or ""
    CompoundStates  []GoneState // full set; precedence: dropped > user_erased > severed > archived > active
}
```

**Resolution order:** `pii_kek → reality_registry → reality_ancestry → projections`. 60s Redis cache, invalidated via MetaWrite events. Never infer gone-state from missing rows — always call this.

**Source:** [02_storage/S10_severance_vs_deletion.md](../02_storage/S10_severance_vs_deletion.md) §12Z — decisions S10-D1..D8.

---

## Outbox pattern (event emission)

**When:** emitting any cross-service or cross-reality event.

```go
func Write(ctx context.Context, tx pgx.Tx, event OutboxEvent) error
```

- MUST be called inside the same `tx` as the state change that justifies the event.
- Event is written to `events_outbox` in the per-reality (or per-service) DB.
- `publisher` service drains the outbox and forwards to Redis Streams.
- Never call `redis.XAdd` directly (CI lint blocks it outside `services/publisher/`).

**Source:** [02_storage/R06_R12_publisher_reliability.md](../02_storage/R06_R12_publisher_reliability.md) §12F.

---

## WebSocket ticket handshake

**When:** client opens a WS connection to `api-gateway-bff`.

1. Client does `POST /v1/ws/ticket` with its JWT → server returns one-shot ticket (60s TTL, `user_ref_id` + `allowed_realities` + `allowed_scopes` + `origin_hash` + `fingerprint_hash`).
2. Client opens WS with `Sec-WebSocket-Protocol: lw.v1, ticket.<id>` header. **Ticket NEVER in URL.**
3. Gateway redeems ticket atomically in Redis (DEL).
4. Per-connection `WSSession` server-side state with 15-min TTL (refresh via `ws.refresh` control message).
5. Every inbound + outbound WS message re-runs S2 + S3 authorization (§12AB.L3, closes S2-regression-via-WS vector).

Forced disconnect via Redis stream `lw:ws:control` with enumerated close codes (1000, 4001..4010). Propagation SLA < 1s; P99 > 5s → PAGE.

**Source:** [02_storage/S12_websocket_security.md](../02_storage/S12_websocket_security.md) §12AB — decisions S12-D1..D10.

---

## Break-glass admin access

**When:** incident response requires bypassing normal ACLs (credential leak, security event, irrecoverable state).

```
POST /admin/break-glass
```
Tier 1 dual-actor + 100+ char reason + incident ticket reference. Returns 24h TTL admin JWT with `break_glass=true` claim. Every RPC under that JWT is double-audited and SLACK/PAGE on-call. Mandatory post-use: credential rotation + 7d postmortem.

Cannot be called by any service. Only humans, only via `admin-cli`.

**Source:** [02_storage/S11_service_to_service_auth.md](../02_storage/S11_service_to_service_auth.md) §12AA.10 — decision S11-D10; governance extension in `docs/02_governance/ADMIN_ACTION_POLICY.md` §R4.

---

## Summary table

| API | Owner chunk | When to call |
|---|---|---|
| `MetaWrite()` | S04 §12T.3 | Any write to meta DB |
| `AttemptStateTransition()` | C05 §12Q | Any lifecycle-state change |
| `AssemblePrompt()` | S09 §12Y | Any LLM call |
| `ResolveContext()` | S09 §12Y.4 | Authorizing refs without building prompt |
| `GetEntityStatus()` | S10 §12Z | Need current gone-state of entity |
| `outbox.Write()` | R06 §12F | Emitting cross-service events |
| WS ticket handshake | S12 §12AB | Client WS connect |
| Break-glass | S11 §12AA.10 | Incident-scoped admin bypass |

If you find yourself doing any of these actions WITHOUT the listed API, stop — you're about to violate an invariant.
