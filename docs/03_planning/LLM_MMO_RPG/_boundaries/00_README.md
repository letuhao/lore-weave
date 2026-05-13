# `_boundaries/` — Feature Boundary Discipline

> **Purpose:** prevent feature-design conflicts and duplicate work by codifying WHO OWNS WHAT and HOW shared schemas are extended.
>
> **Status:** seed 2026-04-25 (created post-WA_006 over-extension review)
>
> **Lock:** single-writer per [`_LOCK.md`](_LOCK.md). Reads unrestricted; writes require lock claim.

---

## Why this folder exists

After 11 features were designed in one work session (PL_001..003, NPC_001..002, WA_001..006), the WA_006 Mortality boundary review (2026-04-25) revealed:

1. **WA_006 over-extended** — its `pc_mortality_state` aggregate, A6 sub-validator, hot-path turn check, and respawn flow all belonged to OTHER features (PCS_001, 05_llm_safety, PL_001/002).
2. **Continuum had borderline boundary issues** — `TurnEvent` payload shape grew uncontrolled across PL_002 / NPC_002 / WA_006 with no envelope owner; `RealityManifest` extended by 5+ features with no schema owner.
3. **Validator slot ordering drift** — Lex (LX-D5), Heresy (HER-D8), Mortality, and others all proposed slot ordering in EVT-V* without coordination.
4. **No single source of truth** for "feature X owns aggregate Y" — easy to invent overlapping aggregates.

Without this folder:
- Every new feature relitigates boundary questions
- Conflicts surface only at integration time (expensive)
- Duplicate aggregates / validators ship in production

With this folder:
- Boundary truth is queryable (read [`01_feature_ownership_matrix.md`](01_feature_ownership_matrix.md) before designing)
- Schema extension is contractual (read [`02_extension_contracts.md`](02_extension_contracts.md) before extending shared schemas)
- Validator slots are coordinated (read [`03_validator_pipeline_slots.md`](03_validator_pipeline_slots.md) when adding a validator)
- Changes are audited via [`99_changelog.md`](99_changelog.md)

---

## Files

| File | Purpose |
|---|---|
| [`_LOCK.md`](_LOCK.md) | Single-writer mutex; current claim + how-to-claim |
| [`00_README.md`](00_README.md) | This file |
| [`01_feature_ownership_matrix.md`](01_feature_ownership_matrix.md) | Master truth: who owns each aggregate, schema, namespace |
| [`02_extension_contracts.md`](02_extension_contracts.md) | Rules for extending shared schemas (TurnEvent envelope, RealityManifest, capability JWT) |
| [`03_validator_pipeline_slots.md`](03_validator_pipeline_slots.md) | Coordinated slot ordering for EVT-V* (resolves drift watchpoints LX-D5 / HER-D8) |
| [`99_changelog.md`](99_changelog.md) | Append-only log of boundary changes; lock claim/release records |

---

## How to use

### Before designing a new feature

1. **Read** [`01_feature_ownership_matrix.md`](01_feature_ownership_matrix.md) to check if the aggregates / concepts you need are already owned
2. **Read** [`02_extension_contracts.md`](02_extension_contracts.md) if your feature extends a shared schema (TurnEvent fields, RealityManifest fields, capability JWT claims)
3. **Read** [`03_validator_pipeline_slots.md`](03_validator_pipeline_slots.md) if your feature adds a validator stage
4. If you need to MODIFY any of these (claim a new aggregate, extend a shared schema, add a validator slot): claim the lock first, edit, release

### During design review

- Reviewer checks: does this feature design respect the ownership matrix?
- Reviewer checks: does any new aggregate conflict with an existing claim?
- Reviewer checks: are extensions to TurnEvent / RealityManifest declared additively per the contract?

### After feature design lands

- The feature's design doc says "this feature owns aggregates X, Y" — update the ownership matrix to reflect it
- If the feature introduces a new shared schema: add an extension contract entry
- Lock-claim → edit matrix → release

### When boundaries drift

Drift signals (any of the following):
- Two features claim the same aggregate in their design docs
- A feature extends a shared schema without updating the extension contract
- A new validator stage appears that's not in the slot ordering doc
- A feature design uses a stable-ID prefix that's not in the foundation/06_id_catalog

→ Open a boundary-review thread (this folder, claim lock, edit + commit). Don't fix in-place across feature folders without first updating the boundary truth.

---

## Relationship to other folders

| Folder | Relation |
|---|---|
| [`../00_foundation/`](../00_foundation/) | Foundation defines INVARIANTS (I1..I19) + ID namespaces. `_boundaries/` defines OWNERSHIP. Both kernel-tier; complementary. |
| [`../06_data_plane/`](../06_data_plane/) | DP is LOCKED. `_boundaries/` references DP-A*/T*/R*/K* but does not modify them. |
| [`../07_event_model/`](../07_event_model/) | Event-model agent's territory. `_boundaries/` cites EVT-T* / EVT-A* but does not redesign. Validator slot ordering ([`03_validator_pipeline_slots.md`](03_validator_pipeline_slots.md)) references event-model Phase 3 EVT-V*. |
| [`../features/`](../features/) | Feature designs DECLARE their ownership; this folder RECORDS the declarations as a unified table. |
| [`../decisions/`](../decisions/) | Locked decisions are append-only. `_boundaries/` is editable but lock-gated. Different concerns. |

---

## Process discipline

The lock-claim pattern relies on agent honesty. Mechanical enforcement comes from:
- Git history shows lock claims (commit messages start with `[boundaries-lock-claim]` / `[boundaries-lock-release]`)
- Reviewers check lock state before approving any `_boundaries/*` edit
- Future: pre-commit hook checks `_LOCK.md` matches the committing agent (V2+ ops)

V1 enforcement is convention + audit. Sufficient for our small-team / multi-agent workflow.
