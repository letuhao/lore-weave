# Vocabulary

> **All shared enums and concept names used across the LLM MMO RPG track.** Use only these. Inventing new values requires a kernel-chunk update + foundation update in the same commit.

---

## Canon layers (4 + 1 marker)

The four-layer canon model from [03_multiverse/01_four_layer_canon.md](../03_multiverse/01_four_layer_canon.md) §3.

| Layer | Name | Stability | Who sets it |
|---|---|---|---|
| **L1 AXIOM** | Absolute, never overturn | Forever | Book author (manual) + category heuristic (WA-4 defaults species/magic-system to L1) |
| **L2 SEEDED** | Canonized narrative from emergent play | Changes via canonization flow (DF3 — V2+) | Author + second reviewer (S13 Tier 1 destructive) |
| **L3 LOCAL** | Reality-local current truth | Mutable within reality | Any participant (per world rules DF4) |
| **L4 FLEX** | Soft, overridable detail | Most mutable | Narrator + context |

**Prompt markup** (used by `AssemblePrompt()`):
```
[L1:AXIOM] ... [/L1]
[L2:SEEDED] ... [/L2]
[L3:LOCAL] ... [/L3]
[L4:FLEX] ... [/L4]
[SEVERED] ... [/SEVERED]  — DF14 orphan-world lore marker
```

SYSTEM instructs the model: L1 absolute · L2 never overturn · L3 current truth · L4 soft. `[SEVERED]` = fact from an ancestry-dropped reality; treat as narrative mystery per DF14.

---

## Reality lifecycle states (9)

From [02_storage/R09_safe_reality_closure.md](../02_storage/R09_safe_reality_closure.md) §12I + HMP `seeding` addition + C2 `migrating` addition.

```
active → pending_close → frozen → archived → archived_verified → soft_deleted → dropped
                                                                        ↓
                                                                  (irreversible)

seeding — provisional state during reality-bootstrap worker run (H5)
migrating — during a DB-subtree-split migration run (C2)
```

Transitions via `AttemptStateTransition()` (see `04_kernel_api.md`). State graph enforced by `contracts/meta/transitions.yaml`.

**Minimum time from `pending_close` to `dropped` = 120 days** (R9-L1 8-layer safeguard floor). Never shorter.

---

## GoneState enum (5)

From [02_storage/S10_severance_vs_deletion.md](../02_storage/S10_severance_vs_deletion.md) §12Z.

```go
type GoneState string

const (
    Active     GoneState = "active"
    Severed    GoneState = "severed"     // ancestry-broken reality (DF14)
    Archived   GoneState = "archived"    // R9 archived, user-visible
    Dropped    GoneState = "dropped"     // R9 physically gone; unrecoverable
    UserErased GoneState = "user_erased" // S8 GDPR crypto-shred
)
```

**Precedence** (when compound states possible): `dropped > user_erased > severed > archived > active`.
**Prompt markers:** `[SEVERED]` · `[ARCHIVED]` · `[ERASED]` · `[UNRECOVERABLE]` · `[LOST]` (DF14 narrative wrapper for severed).
**Never infer gone-state from missing rows.** Always call `GetEntityStatus()`.

---

## Problem statuses (8)

Used in `01_problems/`, `decisions/locked_decisions.md`, and SESSION_HANDOFF.

`OPEN` · `PARTIAL` · `MITIGATED` · `SOLVED` · `ACCEPTED` · `DEFERRED` · `KNOWN` · `WITHDRAWN`

- **OPEN** — unsolved, no credible approach.
- **PARTIAL** — credible approach, pending V1 data / further lock.
- **MITIGATED** — layered defense in place; residual risk known + bounded.
- **SOLVED** — design complete + tests pass; no residual risk.
- **ACCEPTED** — conscious trade-off (research frontier, scope discipline).
- **DEFERRED** — not in scope for current phase; tracked on DF registry.
- **KNOWN** — well-understood, intentionally unaddressed (follows a standard pattern).
- **WITHDRAWN** — was raised, no longer a concern.

Do not invent synonyms. "TODO" / "FIXME" / "in progress" are not problem statuses.

---

## Decision statuses (3)

Used in `decisions/locked_decisions.md` and every design doc.

`LOCKED` · `PENDING` · `SUPERSEDED BY <id>`

Never just delete a locked decision. Use `SUPERSEDED BY <id>` and leave the original row (append-only history).

---

## Impact classes (3)

Every admin command declares one. From [02_storage/S05_admin_command_classification.md](../02_storage/S05_admin_command_classification.md) §12U.

| Class | Also called | Guard rails |
|---|---|---|
| **destructive** (Tier 1) | Tier 1 | Dual-actor + 100+ char reason + 24h cooldown on the first actor |
| **griefing** (Tier 2) | Tier 2 | Single-actor + 50+ char reason + user notification + weekly review |
| **informational** (Tier 3) | Tier 3 | Standard auth; no extra gate |

CI lint requires every command to declare `ImpactClass` at R13-L1 registration.

---

## Privacy levels (3)

Applied to events and memory rows. From [02_storage/S01_03_session_scoped_memory.md](../02_storage/S01_03_session_scoped_memory.md) §12S.3.

| Level | Retention | Admin-tier gating |
|---|---|---|
| **normal** | Per event type's default | All admin tiers |
| **sensitive** | 30 days | Requires Tier 2+ admin access (S5-D6) |
| **confidential** | 7 days | Requires Tier 1 (dual-actor) admin access |

Default for user chat content: `normal`. PC whispers / DMs: `sensitive` or `confidential` per world-rule.

---

## Severity (4)

Incident classification. From [02_storage/SR02_incident_oncall.md](../02_storage/SR02_incident_oncall.md) §12AE.

| Severity | TTA | IC required | Post-mortem |
|---|---|---|---|
| **SEV0** | 5 min | Yes (3 roles min: IC + fixer + comms) | Mandatory 7d |
| **SEV1** | 15 min | Yes (2 roles) | Mandatory 14d |
| **SEV2** | 30 min | Optional | Mandatory 14d if MTTR > 1h OR unknown root cause |
| **SEV3** | 120 min | No | Optional |

**Auto-escalations:** data integrity → SEV0 · canon injection → SEV1 · audit hash mismatch → SEV0 · personal-data breach → SEV0.

---

## Intent classes — 3-intent classifier (A5-D1)

From [05_llm_safety/01_intent_classifier.md](../05_llm_safety/01_intent_classifier.md) §2.

| Intent | Route to | Example |
|---|---|---|
| **story** | `AssemblePrompt(intent=session_turn)` | "Arwyn draws her sword" |
| **command** | Command dispatcher (§3) → structured tool call | `/hide`, `/whisper @alice ...`, `/stats` |
| **meta** | Meta handler (not LLM-routed) | "what reality am I in?", "show me my PC sheet" |

Classifier runs at turn-input boundary in `roleplay-service`.

---

## Prompt sections (8)

The `AssemblePrompt()` output structure. See `04_kernel_api.md`.

```
[SYSTEM] [WORLD_CANON] [SESSION_STATE] [ACTOR_CONTEXT] [MEMORY] [HISTORY] [INSTRUCTION] [INPUT]
```

User-authored text ONLY in `[INPUT]`. PR reject condition in ADMIN_ACTION_POLICY §4.

---

## Intent / template / intent IDs

7 enumerated prompt intents (S9-D1): `session_turn` · `npc_reply` · `canon_check` · `canon_extraction` · `admin_triggered` · `world_seed` · `summary`. Each has its own template dir at `contracts/prompt/templates/<intent>/v<N>.tmpl` + `.meta.yaml` + fixtures.

---

## Consent scopes (S8-D8)

Rows in `user_consent_ledger`. 5 V1 scopes:
- `core_service` — required to use the platform
- `byok_telemetry` — send BYOK call metrics to platform
- `derivative_analytics` — aggregate usage analysis
- `ip_derivative_use` — platform-trained derivative content (gates canonization consent)
- `marketing_comms` — email / platform notifications

Revocation emits `user.consent_revoked` via `meta-worker` fan-out.

---

## Retention tiers (cross-cutting)

Applied to every table. From [02_storage/S08_audit_pii_retention.md](../02_storage/S08_audit_pii_retention.md) §12X.3.

| Tier | Duration | Target |
|---|---|---|
| Hot | 15 days | `app_logs` (30d), `events_confidential` (7d), `events_sensitive` (30d) |
| Warm | 90 days | partitioned Postgres |
| Cold | 2 years | MinIO archive |
| Billing | 7 years | `billing_ledger` (pseudonymize at 2y per S8 override) |
| Audit | 5 years | `admin_action_audit`, `service_to_service_audit`, `meta_write_audit`, `incidents`, `deploy_audit` |
| Forever | — | `canon_entries`, `pii_registry` (until crypto-shredded), docs in git |

---

## Metric label conventions (SR1-D8)

- `user_ref_id` — ONLY on rare violation counters (high cardinality)
- `reality_id` — top-K + `_other` bucket above 1 000 realities
- `session_id` — FORBIDDEN on long-retention metrics
- High-cardinality detail → Prometheus exemplars, not labels

Target observability cost: < 500 GB/day at V3 scale.

---

## File-naming reminders

- Subfolder chunks: `snake_case.md` with stable-ID prefix where applicable (`R01_`, `S09_`, `cat_11_`).
- `_index.md` = subfolder TOC (leading underscore sorts first).
- Retired chunks: suffix `_withdrawn.md` — never reuse the name.

See ORGANIZATION.md for the full naming contract.
