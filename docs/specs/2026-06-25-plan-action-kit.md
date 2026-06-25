# Plan/Action Kit — `loreweave_mcp` shared agent-execution layer

**Status:** DESIGN draft · 2026-06-25 · owner: `sdks/go/loreweave_mcp` + `sdks/python/loreweave_mcp`
**Consumers:** glossary-service (Phase 1 reference consumer), then any agentic domain service.
**Builds on:** the existing confirm-token spine (`confirm_token.go` / `.py`) — this kit is the *plan/execute layer above it*, not a replacement.
**Companion spec:** `docs/specs/2026-06-25-glossary-assistant-planner.md` (the architecture + why; this doc is the mechanism).

---

## 0. Why this exists (one paragraph)

A single ReAct agent calling N write-tools in a loop compounds failure: each step is an LLM decision
that can drop a required param, duplicate state, or mis-sequence. The fix (companion spec) is
**plan-and-execute**: a capable planner emits ONE typed plan; a deterministic executor applies it under
ONE human confirm. The mechanism that makes that reliable — the typed plan envelope, the propose→confirm
spine wiring, the deterministic executor, and the planner contract — is **identical across every agentic
service**, so it lives in the shared `loreweave_mcp` kit. A domain service only registers its **op-set +
handlers**; it never re-implements the propose/confirm/execute glue (today glossary hand-rolls it in
`action_propose_tools.go` / `action_confirm.go`).

This spec is written so the four edge-case classes that batching introduces — **concurrency tokens,
idempotency, destructive-confirm, error reporting** — are resolved in the design, not discovered at build.

## 1. Placement & language alignment

- Go: `sdks/go/loreweave_mcp/plan.go`, `propose.go`, `execute.go`, `planner.go` (one package, alongside
  the existing `confirm_token.go`).
- Python: `sdks/python/loreweave_mcp/plan.py`, `propose.py`, `execute.py`, `planner.py`.
- **Alignment rule (COMPOSE-A, inherited):** the two kits are aligned at the **API + envelope-schema +
  claim level**, NOT byte-level wire interop. A plan is minted AND executed inside ONE service in ONE
  language; the JSON envelope shape is the contract both kits implement identically. Rust gets the kit
  only when a Rust agentic service needs it.
- **Invariants preserved:** provider calls (the planner's model) go through `loreweave_llm` →
  provider-registry (provider-gateway invariant); the planner is exposed as an MCP tool (MCP-first); the
  confirm/execute path is browser-JWT-only and the mint/MCP path can never execute it (INV-1 / INV-9).

## 2. The plan envelope (the typed contract)

A plan is a **closed, validated artifact** — the planner emits it as structured output; the executor and
the FE both read it. One envelope shape for all services; the `op` set is per-domain (registered, §6).

```jsonc
Plan {
  "version": 1,
  "book_id": "uuid",                 // single-resource scope (== the token's ResourceID)
  "goal": "string",                  // the NL goal, echoed for the review header
  "ops": [ Op, ... ],                // ordered; executor re-sorts into dependency tiers (§5)
  "notes": [ "string", ... ]         // planner's surfaced un-supported intents (S3/§6.4) — NOT executed
}

Op {
  "id": "string",                    // stable within the plan (e.g. "op-3"); addresses toggles + results
  "type": "create_kinds | add_attributes | edit_attribute | delete | ...",  // domain-registered
  "params": { ... },                 // typed per `type` (the discriminated union; STRICT schema, S4)
  "rationale": "string?",            // shown in the review row
  "destructive": false,              // SET BY THE KIT from the op registration, NOT by the planner (§6, G1)
  "base_version": "string?"          // optimistic-concurrency token for edit/delete ops (G2)
}
```

**Hard envelope rules**

- `destructive` is **authoritative from the op registration**, never trusted from planner output — the
  planner cannot downgrade a `delete` to non-destructive (a prompt-injection or hallucination defense).
- `ops` is **deduped at validation** (S3): two ops with identical `(type, identity-key)` collapse to one.
- Empty `ops` (after dedup) **never mints a card** (S3) — the planner tool returns a "nothing to do /
  already satisfied" message instead. (Today's batch path 422s *after* mint+burn — the wrong place.)
- `len(ops)` is **capped** (`MaxPlanOps`, default 50). Over-cap → the planner tool returns an error asking
  the user to narrow the goal; it does not mint a truncated plan silently (no-silent-cap rule).

## 3. Propose: minting the plan card (`propose.go` / `.py`)

`MintPlan(secret, userID, bookID, plan, ttl) → confirmToken` — a thin wrapper over the existing
`mintActionToken` / `MintConfirmToken` spine:

- `descriptor = "execute_plan"`, `payload = Plan`, `authority = grant`, fresh `jti`, `resource = bookID`.
- Reuses the HMAC, domain-separator, and single-use-jti machinery unchanged — the kit adds NO new token
  crypto, only the typed payload + a longer TTL for plans.
- **TTL (S5):** plan descriptors use `PlanTokenTTL` (default **30 min**, vs the 10-min single-op TTL) — a
  multi-op plan takes longer to read. Configurable per service.
- **Token size (S3):** `MaxPlanOps` also bounds payload size; the confirm path reads the token from the
  POST **body** (never a header/URL), so KB-scale plans are fine.

The planner tool (§7) calls `MintPlan` and returns `{confirm_token, descriptor, plan_preview}` to the
agent — exactly the shape today's `glossary_propose_kinds` returns, so the FE ConfirmCard renders it
unchanged for Phase 1.

## 4. Confirm-dispatch: the gated execute path (`execute.go` / `.py`)

The kit owns a generic confirm handler that domain services mount at their `/v1/<domain>/actions/confirm`
route for the `execute_plan` descriptor. It reuses the proven order from `confirmAction`:

```
verify token → re-check authority (Manage grant) → claim jti (single-use, fail-closed)
  → decode Plan → run executor → return summary
```

**G1 — destructive toggles are a confirm-time input, NOT in the token.** The confirm request body is:

```jsonc
{ "confirm_token": "…", "enabled_ops": ["op-3", "op-7"] }   // ids of destructive ops the user enabled
```

- `enabled_ops` is validated against the decoded plan: each id must exist **and** be a `destructive` op
  (enabling a non-destructive op is a no-op; an unknown id → 422 `bad_enabled_op`).
- The executor **skips every destructive op NOT in `enabled_ops`**, reporting it as
  `skipped: not_confirmed`. So "approve plan" can never silently delete (INV-1 holds), yet a plan
  containing deletes is still approvable in one action.
- Security: `enabled_ops` comes from the user's own browser (JWT-gated); enabling a toggle *is* the user's
  authority. The MCP/mint path still cannot reach this route at all.

**Single-use + partial failure (G4):** the jti is claimed **before** the executor runs (fail-closed,
unchanged). A mid-plan hard failure leaves applied ops committed and the jti burned. Recovery is
**re-propose** (§8), which is safe because of idempotency (G3) — NOT a jti release.

## 5. Executor skeleton (`execute.go` / `.py`)

`Execute(ctx, plan, enabledOps, registry) → Summary`. Pure code, no LLM, no agent.

**Ordering.** Ops are re-sorted into **dependency tiers** declared by the op registration (§6):
`adopt(0) → kinds(1) → attributes(2) → entities(3) → edits(4) → deletes(5)`. Within a tier, original
plan order is preserved. This lets an `add_attributes` op reference a `kind_code` created by a
`create_kinds` op **in the same plan** (kinds tier runs first).

**Per-op execution + error isolation (S1 — the class table is the contract):**

| Handler error class | Outcome | Aborts plan? |
|---|---|---|
| success | `applied` | no |
| `unique_violation` (already exists) | `skipped: already_exists` | no |
| `not_found` / FK (target gone) | `failed: target_gone` | no |
| `stale_version` (G2 base_version mismatch) | `failed: changed_since_planned` | no |
| `validation` (bad/empty params, S4) | `failed: bad_params` | no |
| destructive op not in `enabledOps` (G1) | `skipped: not_confirmed` | no |
| `internal` (DB down, unexpected) | `failed: internal` | **yes — stop, return partial summary** |

Only an *internal* error aborts the remaining plan (the stack is unhealthy); every **business** error is
isolated to its op so one bad op never sinks the batch. This generalizes exactly what
`effectSchemaCreateKinds` does (unique-violation → skip; internal → 500-abort).

**G2 — optimistic concurrency.** Before an **edit** handler (`edit_attribute` / `edit_entity`) mutates, the
executor re-checks the row's current version against the op's `base_version` (captured at plan-read time).
Mismatch → `stale_version` → `failed: changed_since_planned` (no clobber). Create/adopt ops carry no
`base_version` (nothing to clobber); **`delete` carries none either** — it re-resolves by `code` and removes
whatever is present (idempotent remove; `target_gone` → skipped). See §17 for the precise rule.

**G3 — idempotency contract (declared per op in the registration):**

- Every op MUST be **safe to run twice** (re-propose / concurrent-plan convergence depends on it).
- Create ops: idempotent by skip-on-conflict (unique key).
- Set-value ops (`edit_attribute`, `edit_entity`): idempotent **only as set-to-absolute-X**; toggle /
  increment / append op shapes are **forbidden** (the registry rejects an op declared non-idempotent).
- **Paid ops (`research`)**: the handler MUST guard on prior effect — "evidence already attached for
  `(entity_id, query)`" → `skipped: already_done`, never a second paid call. A paid op with no such guard
  may not be registered.

**Summary (G4 — failures are first-class, not buried):**

```jsonc
Summary {
  "applied":  [ { "op_id": "op-1", "type": "create_kinds", "detail": "…" } ],
  "skipped":  [ { "op_id": "op-4", "type": "delete", "reason": "not_confirmed" } ],
  "failed":   [ { "op_id": "op-7", "type": "edit_attribute", "reason": "changed_since_planned",
                  "message": "human-readable cause" } ],
  "aborted":  false        // true if an internal error stopped execution early
}
```

The agent reports this **verbatim** (companion spec §3.3). The skill (§7) forbids claiming success until
this returns, and requires surfacing `failed[]`/`aborted` prominently — never "✅ applied 8" with 3
silent failures.

## 6. Op registration (what a domain service provides)

A service registers an `OpSpec` per op type; the kit knows nothing domain-specific:

```go
type OpSpec struct {
    Type        string            // "create_kinds"
    Tier        int               // dependency tier (0..5)
    Destructive bool              // authoritative; stamped onto every Op of this type
    Idempotent  bool              // MUST be true to register (G3); false → registration error
    ParamSchema json.RawMessage   // strict JSON Schema for params (S4) — required fields enforced
    Validate    func(params) error            // structural pre-checks (slug code, non-empty desc — S4)
    Handler     func(ctx, bookID, userID, params, baseVersion) (detail any, error)  // maps errors to §5 classes
}
```

- **S4 — strict params.** `ParamSchema` marks every required field per op variant; `Validate` enforces
  slug `code` (CJK novels → planner must transliterate codes, names/descriptions stay multilingual) and
  **non-empty attribute `description`** (the skill demands rich descriptions; this is what enforces it).
  This is the direct fix for the original `level`/`max_results`-dropped bug class.
- **§6.4 — missing-op degradation (S3 risk).** The op set must cover the common verbs day one
  (incl. `edit`/`rename`) so the planner never expresses an unsupported intent as a destructive
  workaround (e.g. rename-as-delete+create, which would orphan entity links). An intent with no matching
  op → the planner emits a `notes[]` entry, surfaced to the user — never an improvised op.

## 7. Planner contract (`planner.go` / `.py`)

- Exposed by the domain service as an MCP tool (e.g. `glossary_plan`). Input `{book_id, goal, reference?}`.
- **Reads current state first** (existing read funcs) so the plan is a **delta** (idempotency-aware → fewer
  duplicates, though the executor's skip is the real guarantee, not the planner's care).
- **Model:** resolved via `loreweave_llm` as a **`planner` role** — a *capable* model, defaulting to a
  strong chat+tool model, never the chat's "Fast" model (companion §6 D-1). Provider-gateway-safe.
- **Output:** the `Plan`, validated by structured-output against the registered op union (strict). Produces
  DATA, not prose — killing the narration failure mode at the planning step.
- **Skill routing (the agent's shrunk role):** understand intent → `glossary_plan` → present the plan →
  on approval `glossary_confirm_action` (+ `enabled_ops`) → **report the executor summary verbatim**.
  The skill forbids looping individual write tools for multi-step goals, and applies the
  **debugging-protocol stop**: after **K=2** re-propose rounds with the same `failed[]`, stop and ask the
  user (G4 — prevents the deterministic-failure loop).

## 8. Recovery & re-planning

- **Phase 1 (no auto re-plan):** on a partial summary, the agent surfaces `failed[]`/`skipped[]` and the
  user re-asks. The planner re-reads state (applied ops now present → skipped), and proposes only the
  remainder. Safe purely because of the §5 idempotency contract.
- **Phase 3 (auto re-plan, load-bearing — companion §9):** feed `failed[]` back into the planner with the
  failure reasons; it revises and re-proposes. The literature treats this as core, not polish — it is the
  one deliberately-deferred piece, and the K=2 stop (§7) is its Phase-1 stand-in.

## 9. Preview (non-consuming, current-state render)

The kit provides a generic plan-preview for the `/actions/preview` route (never consumes the token):

- **S2 — re-validate EACH op against live state**, do not echo the minted plan. Per op, report the live
  outcome it *would* have: `create → new | already_exists`, `edit → applies | stale | target_gone`,
  `delete → cascade blast-radius (count) | already_gone`. Mirrors `previewAdopt` / `previewBookDelete`,
  applied per op.
- Destructive ops render their cascade counts (N × `bookDeleteCascadeRows`-style queries — note the cost;
  acceptable at `MaxPlanOps=50`).
- The preview marks which ops are destructive so the FE can render the per-op enable toggles (G1).

## 10. Edge-case coverage matrix (audit → resolution)

| # | Edge case | Resolution |
|---|---|---|
| G1 | "Approve plan" would silently delete | destructive ops skipped unless in `enabled_ops` (§4) |
| G2 | Plan edits clobber concurrent edits | `base_version` per edit/delete op, re-checked at execute (§5) |
| G3 | Re-propose double-charges paid / re-applies ops | per-op idempotency contract; paid ops guard on prior effect (§5) |
| G4 | Partial failure burns jti; deterministic ops loop | `failed[]` with reasons + agent surfaces + K=2 stop (§5,§7) |
| S1 | Inconsistent partial state | error-class → outcome table is the contract (§5) |
| S2 | User approves a stale card | preview re-validates each op live (§9) |
| S3 | Oversized / empty / duplicate plan | cap + dedupe + reject-empty before mint (§2) |
| S4 | Dropped/empty required params (the original bug) | strict per-variant ParamSchema + Validate (slug, non-empty desc) (§6) |
| S5 | Big plan expires while being read | 30-min PlanTokenTTL for plan descriptors (§3) |
| — | Grant revoked between propose/confirm | existing authority re-check at confirm (unchanged) |
| — | MCP path executes without human | confirm/preview browser-JWT-only (unchanged) |
| — | Cross-book plan | out of scope — plan binds one `book_id` (== token ResourceID) |
| — | Unknown / unwired op type | `liveDescriptor` fail-closed + registry dispatch returns `failed`, never panics |

## 11. Phasing (kit-side)

- **P1 (with glossary Phase 1):** envelope (§2), propose (§3), confirm-dispatch incl. `enabled_ops` (§4),
  executor skeleton + error-class table + idempotency + base_version (§5), op registration (§6), planner
  contract (§7), preview (§9). Go first; Python kit kept aligned (COMPOSE-A). Glossary registers the
  ontology op-set and is the proof.
- **P2:** entity/research/sync ops (the paid-op idempotency guard, §5 G3, lands here for `research`).
- **P3:** auto re-planning loop (§8) — promote the K=2 stop into a real planner-revises-on-failure loop.

## 12. Acceptance (kit P1)

A domain service registers an op-set + handlers and, with **zero** propose/confirm/execute glue of its
own, gets: a planner MCP tool that mints ONE typed plan card, a confirm route that honors per-op
destructive toggles and runs a deterministic, idempotent, concurrency-checked, error-isolated executor,
and a preview that re-validates against live state. Glossary Phase 1 demonstrates all of §10 green on the
"dựng ontology cho <book>" workflow.

---

# Part II — Detailed design (every open question resolved)

This part turns the mechanism above into concrete types, the glossary Phase-1 op-set, the planner's
output strategy, and the precise rules for id/dedupe/base_version — so nothing is left to discover at
build. §20 is the explicit resolved-questions ledger.

## 13. Concrete Go types & signatures (`sdks/go/loreweave_mcp`)

```go
// ── plan.go ──────────────────────────────────────────────────────────────────
type Plan struct {
    Version int      `json:"version"`           // == 1
    BookID  uuid.UUID `json:"book_id"`
    Goal    string   `json:"goal"`
    Ops     []Op     `json:"ops"`               // ids assigned by the kit at mint (§16), frozen in the token
    Notes   []string `json:"notes,omitempty"`   // planner's unsupported-intent surfacings (§6.4)
}
type Op struct {
    ID          string          `json:"id"`           // "op-1".. assigned by kit, deterministic, in-token
    Type        string          `json:"type"`         // registered op type
    Params      json.RawMessage `json:"params"`       // validated against OpSpec.ParamSchema (§15)
    Rationale   string          `json:"rationale,omitempty"`
    Destructive bool            `json:"destructive"`  // stamped from OpSpec, NOT from planner (G1)
    BaseVersion string          `json:"base_version,omitempty"` // EDIT ops only (§17)
}

// ── execute.go ───────────────────────────────────────────────────────────────
type OpOutcome struct {
    OpID, Type string
    Status     string // "applied" | "skipped" | "failed"
    Reason     string // skip/fail class: already_exists | not_confirmed | target_gone |
                      //   changed_since_planned | bad_params | already_done | internal
    Message    string // human-readable (failures)
    Detail     any    // applied: compact {code,name}, NOT the full row (bounds summary size)
}
type Summary struct {
    Applied, Skipped, Failed []OpOutcome
    Aborted                  bool // an `internal` error stopped the run early
}

// The service supplies these; the kit owns the control flow.
type OpSpec struct {
    Type        string
    Tier        int
    Destructive bool
    Idempotent  bool                  // MUST be true; RegisterOp panics at startup if false (G3)
    ParamSchema []byte                // strict JSON Schema, required-fields-per-variant (S4)
    IdentityKey func(params json.RawMessage) (string, error)        // for dedupe/conflict (§16)
    Validate    func(params json.RawMessage) error                 // slug code, non-empty desc (S4)
    Handler     func(ctx context.Context, bookID, userID uuid.UUID,
                     params json.RawMessage, baseVersion string) (detail any, err error)
}
type Registry map[string]OpSpec // type -> spec

type TokenLedger interface { // the service's consumed_tokens; kit stays storage-agnostic
    Claim(ctx context.Context, jti, descriptor string, exp time.Time) (claimed bool, err error)
}

func Execute(ctx context.Context, p Plan, enabledOps map[string]bool, reg Registry) Summary
func MintPlan(secret string, userID, bookID uuid.UUID, p Plan, ttl time.Duration) (token string, err error)

// ConfirmPlan wires the proven order: verify → authorize(callback) → ledger.Claim → Execute.
func ConfirmPlan(ctx, secret string, token string, enabledOps []string,
                 authorize func() error, ledger TokenLedger, reg Registry) (Summary, *HTTPError)
```

**Error mapping is the handler's job, normalized by the kit.** A handler returns a sentinel
(`ErrUniqueViolation`, `ErrNotFound`, `ErrStaleVersion`, `ErrBadParams`, `ErrAlreadyDone`) or a generic
error (→ `internal`, aborts). The kit's per-op loop maps sentinel → `OpOutcome.Reason` per the §5 table.
This is the same shape `effectSchemaCreateKinds` already uses (`isUniqueViolation` → skip; default → 500).

**Each handler is self-transactional** (its own DB tx, like `createKindFromParams`). The executor does
NOT wrap the plan in one tx (D-4 non-atomic) — it loops, isolating failures per the table.

## 14. Glossary Phase-1 op-set (concrete registration)

Phase 1 is **additive-only** (resolves the D-2 ↔ D-3 tension — see §18): no destructive ops, so
`enabled_ops` is unused and the FE ConfirmCard is literally unchanged. `delete`/`merge` move to Phase 2
with the toggle UI. One-off deletes still use the existing single-op `glossary_book_delete` card.

| `type` | Tier | Destructive | Params (reuse existing types) | Identity key | Handler → core | base_version |
|---|---|---|---|---|---|---|
| `adopt_genres` | 0 | no | `{genres:[code], kinds:[code]}` (`adoptParams`) | `"adopt"` (singleton) | `adoptBookOntologyCore` | — |
| `create_kinds` | 1 | no | `{kinds:[kindCreateParams]}` (each with its `attributes`) | per kind `code` | `createKindFromParams` (loop) | — |
| `add_attributes` | 2 | no | `{kind_code, attributes:[kindAttrSpec]}` | `kind_code+attr.code` | `createAttrDefFromParams` | — |
| `edit_attribute` | 4 | no | `{kind_code, genre_code, code, fields{name?,description?,field_type?}}` | `kind+genre+code` | `book_patch` core (flat fields) | **yes (§17)** |

**Op-semantics rule (resolves the create-vs-add ambiguity):** a NEW kind's defining attributes go **inside
its `create_kinds` op** (`kindCreateParams.Attributes`, created atomically with the kind in one tx).
`add_attributes` is **only** for attaching attributes to a kind that already exists (pre-plan). The skill
states this so the planner never both creates a kind AND emits a separate `add_attributes` for the same
kind (which would race tiers and double-propose).

**`adopt_genres` is a singleton op** — at most one per plan (identity key constant); a second is a
dedupe-collapse. It always runs at tier 0 so kinds/attributes that follow can anchor to the scaffolded
`universal` genre (the executor calls `ensureBookScaffolded` equivalent via `adoptBookOntologyCore` with
the picked genres; nil-safe baseline seed unchanged).

## 15. Planner output strategy (the structured-output question, resolved)

**Decision: loose-emit + server-side strict-validate + bounded repair — NOT reliance on provider `oneOf`.**
Local lm_studio models (the $0 target, per project policy) handle discriminated-union `oneOf` schemas
poorly. So:

1. The planner asks the model for `{ops:[{type, params}], notes:[]}` where `type` is an **enum** of the
   registered op types and `params` is a free object — a schema even weak models satisfy. Provider
   structured-output / JSON-mode is used **if available** (via `loreweave_llm`), else plain JSON in the
   prompt.
2. The kit then **validates each op server-side** against `OpSpec.ParamSchema` + `OpSpec.Validate`
   (the strict gate, S4). This is the real guarantee — independent of model capability.
3. **Bounded repair:** if K ops fail validation, the planner re-asks the model **once** with the specific
   validation errors ("op create_kinds: params.kinds[0].code must match `^[a-z0-9_]+$`"). Max **1 repair
   round**; ops still invalid after it are dropped to `notes[]` ("couldn't formulate X") — never minted
   malformed. This is the same tolerate-at-validate / filter-at-postprocess discipline used elsewhere.
4. If **zero** valid ops survive → no card; return "nothing actionable" + the notes (S3).

**Planner model resolution (the `planner` role, resolved):** resolve via provider-registry
`user_default_models` in order: `planner` slot → else `chat` slot → else an explicit `model_ref` passed to
the tool → else `422 no planner model`. Adding the `planner` slot is a small provider-registry addition
(a new `user_default_models` capability key, like `rerank`); until a user sets it, the `chat` fallback
means the feature works out of the box on their existing strong chat model. The service MAY pin a
capability floor later; not required for Phase 1.

## 16. Op id assignment, dedupe & conflict (resolved)

- **Ids are assigned by the kit at mint**, not by the LLM (LLM ids are unreliable). After dedupe, ops are
  numbered `op-1..op-N` in **emitted order** and that id is **frozen in the signed Plan** (in the token).
  Preview and confirm both read ids from the token → stable across the round-trip (needed for `enabled_ops`
  when destructive ops arrive in Phase 2).
- **Dedupe:** two ops with the same `(type, IdentityKey)` AND byte-identical `params` → collapse to one.
- **Conflict:** same `(type, IdentityKey)` but **different** `params` → **validation error**
  `duplicate_conflict` (the planner contradicted itself), routed to the §15 repair round, not silently
  resolved by picking one.
- Execution order is by `Tier` then id (stable); ids do not change under the tier sort.

## 17. `base_version` — capture & re-check (resolved)

- **Applies to EDIT ops only** (`edit_attribute`, and Phase-2 `edit_entity`). Create/adopt have nothing to
  clobber; **`delete` does NOT use it** — delete re-resolves by `code` at execute and removes whatever is
  present (idempotent remove; `target_gone` → skipped). This refines §5 G2: *edit* ops carry base_version;
  *delete* is re-resolve-by-code.
- **Value:** the exact `base_version` string `glossary_book_ontology_read` already returns and
  `glossary_book_patch` already checks (the row's optimistic-concurrency token / `updated_at`). The planner
  captures it at state-read time and the kit copies it onto the op; the handler passes it straight to the
  existing `book_patch` core, which already raises a stale-version error → kit maps to
  `changed_since_planned`. **No new concurrency machinery** — it reuses the column the single-op edit path
  already enforces.

## 18. FE decision — Phase 1 needs NO ConfirmCard change (resolves D-2 ↔ D-3)

D-2 (per-op destructive toggle) and D-3 (reuse ConfirmCard, no new FE) only conflict if a Phase-1 plan
contains destructive ops. It doesn't: **§14's op-set is additive-only.** So Phase 1 sends just
`{confirm_token}` to the unchanged confirm route, ConfirmCard renders the preview rows as today, and the
`enabled_ops` mechanism — fully specified in §4 — is **first exercised in Phase 2** when `delete`/`merge`
enter, alongside the editable plan panel (companion §5 Phase 3 / Phase 2). This keeps Phase 1 a pure
backend+skill change on the FE side.

## 19. Caps, costs, and limits (resolved numbers)

| Limit | Value | Rationale |
|---|---|---|
| `MaxPlanOps` | 50 | bounds token size, execution time, preview cost; over → planner returns "narrow the goal" |
| `PlanTokenTTL` | 30 min | multi-op review time (vs 10-min single-op) |
| Planner repair rounds | 1 | bounded; residual invalid ops → `notes[]` |
| Re-propose stop (skill) | K=2 same-`failed[]` | debugging-protocol stop; prevents deterministic loop |
| Preview destructive cascade queries | ≤ `MaxPlanOps` | acceptable at 50; Phase-1 has none (additive) |
| Planner provider call | 1 per goal | metered via provider-registry like any LLM call; no extra gate Phase 1 |

## 20. Resolved-questions ledger (was open → now decided)

| Open question | Decision |
|---|---|
| Rely on model `oneOf` for the op union? | No — loose-emit + server-side strict-validate + 1 repair round (§15) |
| Which model plans? | provider-registry `planner` slot → `chat` fallback → explicit `model_ref` (§15) |
| Who assigns op ids? | the kit at mint, frozen in the token, emitted-order (§16) |
| Duplicate ops in a plan? | identical → collapse; same-identity-different-params → `duplicate_conflict` repair (§16) |
| New kind's attributes — in create or add? | inside `create_kinds`; `add_attributes` only for pre-existing kinds (§14) |
| Does `delete` need base_version? | No — re-resolve by code, idempotent remove; only EDIT ops carry base_version (§17) |
| What is base_version concretely? | the existing `glossary_book_ontology_read`/`book_patch` concurrency token (§17) |
| Does Phase 1 change the FE? | No — additive-only op-set, ConfirmCard unchanged; `enabled_ops` first used Phase 2 (§18) |
| New DB schema? | No — reuse `consumed_tokens` ledger via the `TokenLedger` interface (§13) |
| Whole-plan transaction? | No — per-op self-transactional handlers, failure-isolated (§13, D-4) |
| `applied[].detail` size? | compact `{code,name}`, not the full row (§13) |
| Plan with zero valid ops? | no card; return "nothing actionable" + notes (§15, S3) |
| Cross-book plan? | out of scope — one `book_id` per plan == token ResourceID (§10) |
| Planner cost gate? | none beyond provider-registry metering for Phase 1 (§19) |
