# KM6-M1 — Knowledge confirm-token machinery foundation + `kg_schema_edit` canary

**Epic:** KG customizable-ontology (`2026-06-20-knowledge-graph-ontology-build.md`),
phase KM6. **Spec:** `docs/specs/2026-06-20-knowledge-assistant-mcp-tools.md` §5/§13;
**reference impl (port from, read-only):** glossary §13 = `services/glossary-service/
internal/api/action_confirm{,_token}.go` + `internal/migrate/consumed_tokens.go`.

## Goal

Build the generalized class-C **confirm-token spine** in knowledge-service (Python),
faithfully mirroring the glossary §13 contract (domain-separated HMAC + single-use
`jti` ledger, closed descriptor enum, re-validate-at-confirm, preview from current
state). Prove it end-to-end with ONE live canary descriptor — `kg_schema_edit` — so
there is no dead mint path (MCP-first: the mint is a real MCP tool).

**Out of scope (later KM6 sub-phases / KM5):** admin `/mcp/admin` + RS256
(`X-Admin-Token`) — the admin authority branch is structured but returns 501 (mirror
glossary Foundation); the other descriptors (`kg_adopt`, `kg_sync_apply`,
`kg_triage_schema`, `kg_triage_handoff`); ai-gateway federation + chat-service surface
curation + `knowledge_skill.py` + the FE confirm card. Each is additive on this spine.

## Contract (mirror glossary §13, knowledge-flavored)

- **Token wire format** (unchanged scheme): `b64url(payload) "." b64url(HMAC_sha256(domain || payloadB64))`.
  Domain separator `kg-action-confirm:v1|` (distinct from glossary's, so a token can
  never cross domains). Keyed by the service `jwt_secret` (forging = full compromise,
  unchanged threat model). TTL 10 min.
- **Claims:** `jti` (uuid), `auth` (`grant`|`admin`), `u` (proposing user), `asub`
  (admin subject, reserved), `pid` (project_id — knowledge is **project**-scoped, not
  book), `d` (descriptor), `p` (opaque params captured at mint), `exp` (unix s).
- **Descriptor enum — CLOSED, validated on mint AND verify (fail closed):** live =
  `{kg_schema_edit}`. Reserved-but-not-live (rejected until their phase wires the
  effect): `kg_adopt`, `kg_sync_apply`, `kg_triage_schema`, `kg_triage_handoff`,
  `kg_system_create|patch|delete`.
- **Single-use:** `consumed_tokens(jti PK, descriptor, consumed_at, exp)` in the
  knowledge DB. Claim = `INSERT … ON CONFLICT (jti) DO NOTHING`; 0 rows ⇒ replay ⇒ 422.
  **Consume-first / fail-closed:** authority is checked BEFORE the claim (a stranger
  can't burn a victim's token); once claimed a failed effect does NOT release it.
- **Authority re-check at confirm/preview (C3):** `grant` → redeemer == `claims.u`
  AND still holds `MANAGE` on the project (resolve-to-owner gate). `admin` → 501 (M1).
- **Re-validate at confirm, not mint (C1):** `kg_schema_edit` carries the
  `schema_id` + the `expected_schema_version` seen at mint; confirm re-resolves the
  project's active schema and rejects on **schema_version drift** (optimistic
  concurrency) or a vanished schema → re-proposable 422. Never applies stale intent.
- **Preview (§5.1 #5):** `POST /v1/kg/actions/preview` — JWT-gated, **non-consuming**,
  recomputes the card from CURRENT state (e.g. current schema_version, would-bump-to).

## Files

| File | Change |
|---|---|
| `app/ontology/confirm.py` | **NEW** — pure token codec: `ActionClaims`, `mint_action_token`, `verify_action_token`, `live_descriptor`, domain/TTL/authority consts, `ActionTokenInvalid/Expired`. Port of `action_confirm_token.go`. |
| `app/db/migrate.py` | append idempotent `consumed_tokens` DDL to the single DDL string (serializes on the table lock like the rest). |
| `app/db/repositories/action_tokens.py` | **NEW** — `ActionTokenRepo.consume(jti, descriptor, exp) -> bool` (atomic claim). |
| `app/ontology/schema_edit_effect.py` | **NEW** — the `kg_schema_edit` descriptor: `SchemaEditParams` model, `apply_schema_edit` (re-validate drift → `add_edge_type`/`deprecate_edge_type`), `preview_schema_edit`. Wraps existing `OntologyMutationsRepo`. |
| `app/routers/public/kg_actions.py` | **NEW** — `/v1/kg/actions/{preview,confirm}`: decode→authorize→(claim)→dispatch. |
| `app/tools/graph_schema_tools.py` | uncomment + implement `_handle_kg_schema_edit` (mint only, no write) + its args model; register in the catalog. |
| `app/main.py` (or router include) | mount `kg_actions` router. |
| `app/deps.py` | provide `ActionTokenRepo` + `OntologyMutationsRepo` to the router/tools as needed. |
| tests | unit (codec, endpoint-with-fakes) + integration (real-PG: claim atomicity, drift, effect) + tool unit (mint, not-adopted). |

## Build order (TDD)

1. **`confirm.py` codec + unit tests** — round-trip, tampered-sig (constant-time)
   reject, expired→Expired, non-live descriptor → mint=="" + verify=Invalid, empty
   secret, authority-value guard. *Pure, no DB — the security keystone first.*
2. **migration + `ActionTokenRepo.consume`** — real-PG test: first claim True, replay
   False; concurrent claim → exactly one True.
3. **`schema_edit_effect.py`** — `apply_schema_edit` drift-reject + add/deprecate;
   `preview_schema_edit`. Unit with a fake mutations/resolver; integration real-PG.
4. **`kg_actions` router** — decode/authorize/claim/dispatch + preview. Unit with
   fakes: 400 missing, 422 invalid/expired, 403 wrong-user (before claim), 501 admin,
   422 replay, 422 drift, 200/204 happy. 
5. **`_handle_kg_schema_edit` mint tool** — grant MANAGE; require an adopted
   project-scoped schema (else clear "adopt first" error — never edits System
   `general`); mint token + return `{confirm_token, expires_in, preview}`; NO write.
   Unit: mints valid token (verifies under the same secret); not-adopted → error;
   off-tier (system schema) → error.
6. **VERIFY** full knowledge unit + the new integration (real PG). **2-stage REVIEW**
   + **mandatory `/review-impl`** (auth boundary: token forge/replay/drift/authority
   binding/tenancy). **Live-smoke**: mint via tool → preview → confirm → edge added +
   version bumped; replay rejected; drift rejected. COMMIT.

## Invariants honored

- **INV-K1** graph/schema writes through the central path + schema validation; class-C
  shape changes are confirm-gated (this spine). **INV-K2** identity from envelope, not
  LLM (mint binds `claims.u` = caller; confirm re-checks redeemer==u + MANAGE).
- **INV-T3** every System write human-confirmed — admin branch is 501 here (no System
  write path shipped). Tenancy: `kg_schema_edit` only edits an **adopted project**
  schema (per-book/project tier), never the shared System `general` template.
- **Provider/model invariants:** untouched (no LLM/model in this spine).
- **Migration-ledger discipline:** knowledge uses one idempotent DDL string executed in
  a single implicit txn (replicas serialize on the table lock — proven in the L7 sweep);
  the `consumed_tokens` DDL appends to it.

## KM6-M2 — `kg_adopt_template` descriptor (second class-C onto the spine)

Adds the adopt scaffold to the agent path. The **human** path already exists (direct
MANAGE-gated `POST /v1/kg/projects/{id}/adopt` — the human clicking IS the
confirmation); KM6 adds the **agent** path: `kg_adopt_template` MINTS a confirm-token →
the confirm endpoint runs the SAME `OntologyMutationsRepo.adopt` effect. Adopt is
**replace-on-adopt** (idempotent; one active project schema) so there is NO version
drift to re-validate — re-confirm just re-adopts. Re-validation at confirm = source
template still visible/adoptable (`_assert_source_adoptable` → SchemaNotWritableError →
re-proposable) + the M1 glossary node-kind gate (`NeedsGlossaryError` → 422 carrying the
missing kinds).

- `DESC_ADOPT = "kg_adopt"` added to the live set (codec); tripwire test updated.
- `app/ontology/glossary_gate.py` (NEW) — extract the glossary-codes resolution shared
  by the human adopt route + the confirm effect (project_meta → book ontology / user
  standards → `required_node_kinds` fallback when glossary is unavailable, so we never
  false-gate). Reused in `ontology.py` (DRY; its tests verify).
- `app/ontology/adopt_effect.py` (NEW) — `apply_adopt` (resolve codes → `repo.adopt` →
  map NeedsGlossary/NotWritable) + `preview_adopt` (template summary: name + child
  counts + glossary gaps, current-state).
- `GraphSchemasRepo.template_summary(source_id, user_id)` — visible-source name + child
  counts for the mint check + preview render.
- `kg_adopt_template` MCP tool — MANAGE-gated mint (no write); validates the source is a
  visible template; params `{source_schema_id}`. Catalog → 19 tools.
- Tests: codec tripwire, adopt effect integration (scaffold / re-adopt replaces /
  needs-glossary), router dispatch, tool mint. Live-smoke: mint → preview → confirm →
  project schema created.

**KM6-M2 SHIPPED.** VERIFY: 2840 unit + 33 real-PG integration (incl the rewired human
adopt route, unchanged behaviour) green. Live-smoke on the stack (real JWT + PG, glossary
fail-open): preview → confirm (scaffold `xianxia-harem`) → replay 422; project schema
created. `/review-impl`: no HIGH/MED; 1 LOW accepted (a grantee minting their OWN private
user-template adopts a token that 404s at confirm since it isn't visible to the project
owner — secure, rare; system templates pass both gates symmetrically). Catalog now 19
tools, 2 live descriptors. Still deferred: `kg_sync_apply`, KM5 admin/RS256, FE card.

## Risk boundaries (checkpoint/commit candidates)

New migration (table) · new public endpoints (auth) · new MCP tool (mint authority).
Single coherent milestone — one continuous run, commit at the end after `/review-impl`,
since the pieces are interdependent (codec ↔ repo ↔ endpoint ↔ tool) and only prove the
contract together.
