# D-E0-3-CALLER-PAYS-EXTRACTION — DESIGN

> **Date:** 2026-06-11. **Phase:** DESIGN (loom, **XL**, no AMAW). Fixes the **shipped BYOK breach** found in the E0-4 re-audit: E0-3 made `start_extraction = EDIT` + resolve-to-owner, so an **edit-collaborator triggers extraction on the OWNER's embedding/LLM key + budget** — violating the BYOK invariant (only the key owner may cause their key to be charged). PO: **full caller-pays-same-model split**, executed **secure-first**.
>
> **▶ TWO-PHASE (the investigation found the full split spans 3 provider-call surfaces × 2 services × 2 SDKs + a migration — too large to land+verify safely in one tail-of-session pass without risking a broken, live security path):**
> - **✅ Phase 1 — secure-closure (LANDED this session).** `start_extraction` + `benchmark-run` → **OWNER-ONLY** (`require_project_grant(GrantLevel.OWNER)`). Definitively closes the high-value bulk-spend breach: an edit-collaborator can no longer trigger extraction/benchmark on the owner's key. Collaborators keep **view** (search/drawers/project). Minimal, fully-testable, no broken intermediate.
> - **⏳ Phase 2 — caller-pays capability (NEXT, designed below).** Re-open extraction to collaborators on **their own same-model key** (the dual-identity split §1–§7). Re-enables the feature Phase 1 temporarily removed. Residual surface to fold in: collaborator `raw_search`/`drawers` query-embeddings currently bill the owner (view-tier, ~1 small embedding/search — `D-E0-3-SEARCH-QUERY-CALLER-PAYS`).

## 1. The invariant + the constraint
- **BYOK:** provider-registry resolves a model with `WHERE user_model_id=$ref AND owner_user_id=$user`. A model ref is a **per-user UUID** — the owner and a collaborator have *different* `user_models` rows even for the **same underlying model** (e.g. `bge-m3`). So a collaborator MUST supply **their own** ref; the owner's ref won't resolve under the collaborator.
- **Shared graph:** Neo4j passages store `embedding_model` (the model **UUID string**) as a property and **search filters** `WHERE node.embedding_model = $project_model` (passages.py:280,292); the vector index is per-**dimension**. So passages a collaborator extracts must be **stored tagged with the PROJECT's canonical model UUID** (owner's) — else they're filtered out of search — even though the vectors were **generated with the collaborator's ref+key**.

→ **Dual identity** per extraction job:
| Concern | Identity |
|---|---|
| Graph partition (Neo4j `user_id`), cursor, project status, telemetry | **owner** (`user_id`, unchanged) |
| Passage `embedding_model` **storage tag** + search filter + benchmark gate | **project's canonical** model (owner's ref) |
| Embedding + LLM **provider call** (key + budget) | **caller** (`billing_user_id` + caller's refs) |

## 2. Schema (knowledge-service `extraction_jobs` migration — additive, backward-compatible)
```sql
ALTER TABLE extraction_jobs
  ADD COLUMN billing_user_id        UUID,   -- caller (key/budget); NULL → user_id (owner-triggered, legacy)
  ADD COLUMN billing_embedding_model TEXT,  -- caller's embedding ref for GENERATION; NULL → embedding_model
  ADD COLUMN billing_llm_model       TEXT;  -- caller's LLM ref for the provider call; NULL → llm_model
```
NULL columns ⇒ owner-triggered (or legacy) ⇒ everything resolves as today. **Fail-safe:** if `billing_user_id` is set but a billing ref is missing, the worker must DENY (fail the job), never silently fall back to the owner's key.

## 3. knowledge-service route (`start_extraction_job` + `_start_extraction_job_core`)
- **New dep `require_project_principals(need)`** → returns `Principals(owner: UUID, caller: UUID)` (the gate already resolves both; today it discards the caller). Owner drives project/benchmark/graph/project-budget; caller drives billing.
- **Owner path (`caller == owner`):** unchanged — `billing_* = NULL` (legacy semantics). The job's `embedding_model`/`llm_model` = body's (owner's).
- **Collaborator path (`caller != owner`):**
  1. `body.embedding_model` is the **caller's** embedding ref. Validate it resolves under the caller AND `probe_embedding_dimension(caller, body.embedding_model) == project.embedding_dimension` (same vector space) → else **409 `embedding_model_mismatch`** (with the project's required dimension + model identity so the FE can prompt the collaborator to register the same model).
  2. **Storage tag stays the project's:** the job's `embedding_model` column = **`project.embedding_model`** (owner's canonical UUID — the search filter), NOT the caller's ref.
  3. `billing_user_id = caller`; `billing_embedding_model = body.embedding_model` (caller's, for generation); `billing_llm_model = body.llm_model` (caller's, for the LLM provider call).
  4. **Benchmark gate stays owner/project-scoped:** `benchmark_repo.get_latest(owner, project, project.embedding_model)` — the project's passing benchmark validates the vector space; the collaborator's dimension-match inherits it (no per-collaborator benchmark needed).
  5. **Budget:** project-budget check = owner+project (the owner's cap on their project, unchanged). **User-monthly-budget + the per-job `try_spend` = the CALLER** (`billing_user_id`) — the caller's wallet pays. (The owner's project cap still bounds total project spend; the money is the caller's.)
- **Need stays `edit`** (collaborators CAN extract — with their own key). The owner-only ops (rebuild/change-embedding/delete-graph) are unchanged.

## 4. worker-ai (`runner.py`)
- `JobRow` gains `billing_user_id`, `billing_embedding_model`, `billing_llm_model` (from the SELECT; LEFT-JOIN unchanged on owner `user_id`).
- **Billing contextvar (mirror `set_campaign_id`)** in `app/llm_client.py`: `_billing_user_id_ctx` + `set_billing_user_id()`. In `submit_and_wait`, the provider submission uses `billing_user_id_ctx.get() or user_id` as the resolving user. `process_job` calls `set_billing_user_id(str(job.billing_user_id))` (or clears to None) at the top, like `set_campaign_id`.
- **Embedding path:** the passage-embedding generation call uses `(billing_user_id, billing_embedding_model)` for the provider call but **stores `embedding_model = job.embedding_model`** (the project's canonical tag). The LLM extraction calls resolve `billing_llm_model` under `billing_user_id`.
- **Resolution helper:** `eff_billing_user = job.billing_user_id or job.user_id`; `eff_embed_ref = job.billing_embedding_model or job.embedding_model`; `eff_llm_ref = job.billing_llm_model or job.llm_model`. Used ONLY at provider-call sites; every graph/cursor/status/telemetry site keeps `job.user_id`.

## 5. Same-model guard placement
- **Dimension** is the hard vector-space constraint (`probe_embedding_dimension`), enforced at the route (409 on mismatch). The underlying-model-name match is implied by dimension + the collaborator's intent; v1 trusts dimension-equality (documented). A future tighter check could compare provider-registry model identities.

## 6. Anti-abuse / fail-safe
- A collaborator cannot extract on the owner's key: the provider call resolves `billing_embedding_model`/`billing_llm_model` under `billing_user_id=caller` — the owner's refs never enter the call.
- If `billing_user_id` is set but a billing ref is NULL → worker **fails the job** (never falls back to owner). Owner-triggered jobs (`billing_user_id` NULL) keep the legacy single-identity path.
- The stored passages remain searchable (project's canonical `embedding_model` tag), so a collaborator's contribution joins the shared graph.

## 7. Test plan
- **Route unit:** collaborator with dimension-matching ref → job persisted with `billing_*`=caller + `embedding_model`=project's; collaborator with mismatched dim → 409; owner → `billing_*` NULL. Benchmark gate hit with the project's model. Budget checks: user-budget = caller.
- **worker-ai unit:** `submit_and_wait` resolves under the billing contextvar; `process_job` sets it from the job; the eff_* helpers pick billing refs for provider sites, owner for graph; NULL billing → legacy path; billing set + ref NULL → job fails (fail-safe).
- **Migration:** additive columns, existing rows NULL.
- **Live-smoke (≥3 services):** A owns book+project (embedding bge-m3); grants B edit; B registers their own bge-m3; B starts extraction → passages generated on **B's key** (provider usage under B) but stored tagged with the **project's** model → searchable by A; B with a 768-dim model → 409. Token: `live smoke: collaborator extraction billed to caller, stored under project model`. → `D-E0-3-CALLERPAYS-LIVE-SMOKE`.

## 8. Risks
- **R-key-leak** (primary): mitigated — provider call uses billing refs under billing_user_id; fail-safe deny on partial billing data.
- **R-graph-split:** mitigated — storage tag is always the project's canonical `embedding_model`; vectors are dimension-compatible (route-enforced).
- **R-worker-conflation:** the eff_* helper isolates the 3 provider-call sites from the many owner-keyed data sites; a missed site fails safe (graph site with billing id would just mis-partition a write — caught by tests; provider site with owner id is the bug we're removing, explicitly switched).
- **R-benchmark:** owner/project-scoped benchmark inherited by dimension-match; documented (collaborator needs no own benchmark).
