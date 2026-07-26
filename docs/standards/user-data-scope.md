# User Data Scope & Protection Standard

**Status:** ACTIVE · **Date:** 2026-07-04
**Governs:** identifying WHAT counts as user data, WHERE each class lives, and the protection each class requires — so security controls are applied by data-class, not ad hoc. Indexed in [`README.md`](./README.md). Composes with [User Boundaries & Tenancy](./README.md#a-platform-build-standards), [Security](./security.md), and [LLM Call Logging](./llm-call-logging.md).

> **Why.** Security is applied per-endpoint today, so protection depends on whoever wrote the handler remembering the rules. Defining the **data classes** up front — and binding each to a scope key, encryption policy, retention, and erasure mechanism — makes protection a property of the data, enforceable by classification lint rather than reviewer memory. It also answers "which prompts/rows contain user data?" (the LLM-logging audit found user prompts stored plaintext + unreadable).

## The user-data classes

Every table/field/payload holding user data declares a class. Each class carries a **scope key** (tenancy tier) + a **protection profile**.

| Class | Examples | Scope key | Protection profile |
|---|---|---|---|
| **C1 · Identity / PII** | auth users (email, name), OAuth ids, IP/device | `owner_user_id` | PII-tagged migration; encrypted/hashed as appropriate; erasable (crypto-shred); audit access |
| **C2 · Authored content** | books, chapters, chat messages, glossary entries, corrections | `owner_user_id` / `book_id` | tenant-scoped read (404-anti-oracle + grants); server-is-SSOT; retention per user action |
| **C3 · Derived from content** | embeddings, salience/`entity_access_log`, KG entities, summaries, projections | inherits the source's scope key | regenerable from SSOT ([Scope-Separation SCOPE-3](./scope-separation.md)); deleting the source must cascade/invalidate the derived |
| **C4 · Credentials / secrets** | BYOK provider keys, tokens | `owner_user_id` | encrypted at rest (AES-GCM/KMS); never logged; never returned in plaintext; purpose-distinct keys |
| **C5 · LLM I/O payloads** | prompts (incl. assembled system+context), completions | `owner_user_id` (+ `trace_id`) | [LLM Call Logging](./llm-call-logging.md): encrypted (dedicated key), redacted, retention-decoupled, reconstructable |
| **C6 · Usage / billing / telemetry** | usage_logs, spend, engagement events | `owner_user_id` | encrypted payloads; aggregate-only exposure; distinct from engagement analytics ([Analytics SCOPE/STAT-3](./analytics-and-learning.md)) |

## Rules

- **UDATA-1 · Classify at design time.** Every new table/field/payload holding user data declares its class (C1–C6); the class fixes its scope key + protection profile. An unclassified user-data column is a defect ([Security SEC-5](./security.md) PII tags).
- **UDATA-2 · Scope key on every row, filtered on every query.** Per [User Boundaries](./README.md#a-platform-build-standards): `owner_user_id`/`book_id` on the table, filtered on every read; cross-tenant access only via E0 grants; a shared/global user-editable row is a tenancy defect.
- **UDATA-3 · Encrypt C4 + C5 at rest, purpose-distinct keys.** BYOK creds and LLM payloads are encrypted with keys **dedicated per purpose** (never `JWT_SECRET`), rotatable ([Security SEC-6](./security.md), [LLM Logging LOG-5](./llm-call-logging.md)).
- **UDATA-4 · Never log user data unredacted.** C1/C4/C5 never appear in operational logs unredacted ([Logging LG-4](./logging.md)); LLM payloads are logged only through the encrypted chokepoint.
- **UDATA-5 · Erasability (right-to-erasure).** C1–C5 have a defined erasure mechanism (crypto-shred for encrypted classes; delete-cascade for derived C3); erasing C2 content invalidates its C3 derivatives.
- **UDATA-6 · Reconstructability + audit.** C5 LLM I/O must be reconstructable for the retention window ([LLM Logging](./llm-call-logging.md)); access to C1/C4/C5 by an operator/admin is audited ([Logging LG-7](./logging.md)).
- **UDATA-7 · Minimize exposure surface.** C6 exposed as aggregates only; a notification body ([Notification NOTIF-6](./notification.md)) is the one place server content fans to a user's devices — PII-checked.

## Enforcement

| Rule | Status | Gate |
|---|---|---|
| UDATA-1 classify | **to build** | extend `pii-classify-lint` from `migrations/meta/` to `services/*/migrations/` (require class + retention + erasure tags) |
| UDATA-2 scope key | **convention/tested** | tenancy tests (book-service `grant_mapping_test.go`); generalize the required harness |
| UDATA-3 encryption | **partly enforced** | BYOK AES-GCM (tested); C5 dedicated-key to build ([LLM Logging](./llm-call-logging.md)) |
| UDATA-4 no unredacted logs | **to build** | source-side redaction test ([Logging LG-4](./logging.md)) |
| UDATA-5 erasability | **MMO-only → to build** | crypto-shred exists in `sdks/go/piikms`/`contracts/pii` — wire to platform C1–C5 |

## Checklist — a new table/field/payload with user data
- [ ] Declares its class C1–C6 + PII/retention/erasure tags (UDATA-1)
- [ ] Carries a scope key, filtered on every query (UDATA-2)
- [ ] C4/C5 encrypted at rest with a purpose-distinct key (UDATA-3)
- [ ] Never logged unredacted (UDATA-4)
- [ ] Has an erasure mechanism; derived data cascades (UDATA-5)
- [ ] C5 reconstructable + privileged access audited (UDATA-6)
- [ ] Exposure minimized; notification bodies PII-checked (UDATA-7)
