# Public MCP — Priced-Tool Exposure: cross-process spend-carrier (`D-PMCP-WORKER-CARRIER`)

- **Date:** 2026-06-28
- **Branch:** `feat/public-mcp-gateway`
- **Status:** PLAN (CLARIFY + DESIGN done; worker-ai section finalizes after the knowledge-path map returns)
- **Size:** XL (multi-service: translation-service + worker-ai; ≥2 migrations; an auth-path change on a spend route; AMQP message-shape change; load-bearing spend).
- **Spec:** [04-implementation-plan.md](../specs/2026-06-26-public-mcp/04-implementation-plan.md) §8 staged exposure · clears `D-PMCP-WORKER-CARRIER` + `D-PMCP-CARRIER-E2E-LIVE-SMOKE`.
- **PO decisions (2026-06-28):** ALL worker-enqueue providers now (translation + glossary-extraction + worker-ai) · ADD job-row columns (resume durability) · live-smoke on the real stack (user brings up stack + lm_studio).

## Problem (what "exposure" actually means)

Priced Tier-W tools are already in the edge allowlist + BYOK/spend-gated (P3). Only `composition_generate` is end-to-end wired for a public key, because it runs the engine **in-process** at the confirm route (slice-A hook covers it). Every other priced tool **enqueues to a background worker**, and two gaps break attribution:

- **Gap 1 — confirm route unreachable by the auth replay.** auth `replayConfirm` ([mcp_approvals.go:377-390](../../services/auth-service/internal/api/mcp_approvals.go#L377)) POSTs `…/v1/<domain>/actions/confirm?token=…` with `X-Internal-Token + X-User-Id + X-Mcp-Key-Id [+ X-Mcp-Spend-Cap-Usd]`, **no JWT**. composition's confirm accepts exactly this. translation's confirm ([actions.py](../../services/translation-service/app/routers/actions.py)) is **JWT-only + token-in-body** → the replay 401s. So a public key cannot even start a translation priced job today.
- **Gap 2 — carrier dies at the worker process boundary.** translation's confirm only *enqueues*; the LLM spend happens in the **chapter/extraction worker** (separate process). The worker re-sets only `campaign_id`; the AMQP message + job row don't carry `mcp_key_id`. The shared SDK ([loreweave_llm/attribution.py](../../sdks/python/loreweave_llm/attribution.py) `merge_attribution_into_job_meta`, fired in `Client.submit_job`) *would* attribute automatically — but the contextvar is empty in the worker.

## Design — mirror the `campaign_id` rail, add the auth dual-mode

`campaign_id` already rides: **column** `translation_jobs.campaign_id` → **AMQP message** → coordinator → chapter message → `set_campaign_id` at [chapter_worker.py:87](../../services/translation-service/app/workers/chapter_worker.py#L87). We mirror this for `mcp_key_id` + `spend_cap_usd`, threaded as **explicit params** from the confirm route (the create path uses params, not the contextvar). The shared SDK does the `job_meta` merge automatically once `set_public_key_attribution(...)` is called in the worker; provider-registry enforces the per-key cap from `job_meta.spend_cap_usd`.

### Gap-1 fix — dual-mode confirm route (per priced provider whose confirm is not yet internal-gated)

translation `confirm_action` becomes dual-mode (keep the FE/JWT path; ADD the replay path), mirroring composition [actions.py:109-180](../../services/composition-service/app/routers/actions.py#L109):
- accept the token from **either** `?token=` (replay) **or** `body.confirm_token` (FE card);
- resolve the caller from **either** `X-Internal-Token`+`X-User-Id` (replay) **or** the JWT (FE) — cannot use `Depends(get_current_user)` as a hard dep (HTTPBearer auto-401s); extract a `resolve_confirm_caller(...)` helper;
- bind `claims.user_id == caller` (anti-oracle uniform refusal — unchanged);
- lift `X-Mcp-Key-Id` / `X-Mcp-Spend-Cap-Usd` and pass them into each descriptor's core.

### Gap-2 fix — per worker-enqueue tool

For each of: `translation_start_job` (`_resolve_and_create_job`), `translation_retranslate_dirty` (`_retranslate_dirty_core`), resume/retry (`_resume_job_core`/`_retry_job_core`), `translation_start_extraction` (`_create_extraction_job_core`):
1. **Migration** (idempotent ALTER in [app/migrate.py](../../services/translation-service/app/migrate.py)): `translation_jobs` + `extraction_jobs` `ADD COLUMN IF NOT EXISTS mcp_key_id TEXT`, `spend_cap_usd NUMERIC`.
2. **Core**: gain `mcp_key_id`/`spend_cap_usd` params → INSERT columns + add to the published message (`translation.job` [jobs.py:370](../../services/translation-service/app/routers/jobs.py#L370); `extraction.job` [extraction.py:266](../../services/translation-service/app/routers/extraction.py#L266)).
3. **Resume/retry**: read the columns back off the stored job row → re-carry onto the re-published message (this is why columns, not message-only — a resume re-drives from the row, no fresh confirm).
4. **coordinator** ([coordinator.py:75](../../services/translation-service/app/workers/coordinator.py#L75)): propagate both onto the per-chapter unit.
5. **worker re-set**: `set_public_key_attribution(msg.get("mcp_key_id"), <float|None>)` next to `set_campaign_id` — [chapter_worker.py:87](../../services/translation-service/app/workers/chapter_worker.py#L87) (translation) and the extraction worker's per-chapter entry. Unconditional set (None clears) — same leak-prevention as campaign_id.

### worker-ai / knowledge extraction — **poll-based (no AMQP), mirror billing_user_id**

Knowledge extraction is NOT AMQP — knowledge-service `_create_and_start_job` ([routers/public/extraction.py:354-467](../../services/knowledge-service/app/routers/public/extraction.py#L354)) does an inline INSERT into `extraction_jobs` (knowledge DB, shared with worker-ai); worker-ai polls `status='running'`. `campaign_id`/`billing_user_id` already ride **row → resume_state → consumer re-set**. Mirror for `mcp_key_id`/`spend_cap_usd`:
1. **Migration (knowledge-service):** `extraction_jobs ADD COLUMN IF NOT EXISTS mcp_key_id TEXT, spend_cap_usd NUMERIC`.
2. **knowledge-service INSERT:** bind both in `_create_and_start_job` ([extraction.py:389-428](../../services/knowledge-service/app/routers/public/extraction.py#L389)) + `ExtractionJobCreate` ([repositories/extraction_jobs.py:182-291](../../services/knowledge-service/app/db/repositories/extraction_jobs.py#L182)). **OPEN: how mcp_key_id reaches this start path** — knowledge has its OWN ToolContext that may bypass the kit's universal `build_tool_context` hook; resolve which knowledge MCP tool starts extraction + whether it's publicly exposed (kg build/extraction tooling was P3-deferred). If the tool isn't yet edge-exposed, this carrier is inert-but-correct (like the columns existing ahead of exposure).
3. **worker-ai runner `process_job` / `_start_decoupled_chunk`:** `set_public_key_attribution(job.mcp_key_id, job.spend_cap_usd)` before extraction (next to [runner.py:1682,1733](../../services/worker-ai/app/runner.py#L1682) `set_campaign_id`/`set_billing_user_id`); seed `resume_state` with both ([runner.py:1537](../../services/worker-ai/app/runner.py#L1537)).
4. **worker-ai `llm_extract_consumer._resume`:** `set_public_key_attribution(rs.get("mcp_key_id"), rs.get("spend_cap_usd"))` after [llm_extract_consumer.py:296](../../services/worker-ai/app/llm_extract_consumer.py#L296) `set_campaign_id`; clear in `finally` ([:444](../../services/worker-ai/app/llm_extract_consumer.py#L444)). Add `from loreweave_llm.attribution import set_public_key_attribution`.
5. **No llm_client change** — worker-ai's wrapper already routes the shared SDK, so `merge_attribution_into_job_meta` fires once the contextvar is set.

## Security notes (load-bearing — `/review-impl` at POST-REVIEW)

- `mcp_key_id`/`spend_cap_usd` are **server-set** (edge → auth → confirm route). They must never be read from a public-controllable body/`job_meta` — the SDK merge already overwrites caller values; the confirm route must take them only from the replay headers (the FE/JWT path leaves them None).
- The dual-mode auth must not let the **JWT path** smuggle `X-Mcp-Key-Id` (a first-party user must not tag spend to an arbitrary key). Only honor the key headers when the **internal-token** path authenticated the caller.
- `spend_cap_usd` parse: tolerate absent/garbage → None (no cap) — never raise; the cap is a ceiling, missing ⇒ owner-guardrail default downstream.
- Anti-oracle uniform refusal on caller-mismatch is unchanged.

## VERIFY plan

- Unit: confirm-route dual-mode (JWT path unchanged; replay path authenticates + lifts key; JWT path ignores key headers); each core stamps column+message; coordinator propagates; worker re-sets (spy `set_public_key_attribution`); resume re-carries from the row.
- Real-PG: create→row has mcp_key_id; resume re-publishes it.
- **Live-smoke (stack up):** edge → auth (self-confirm or approve) → translation confirm → worker → provider-registry → `usage_logs.mcp_key_id` tagged + per-key cap enforced (402 when exceeded). Clears `D-PMCP-CARRIER-E2E-LIVE-SMOKE`.

## Execution order (serial, checkpoint per risk boundary)

1. Migrations (translation_jobs, extraction_jobs) — risk boundary, commit.
2. translation confirm dual-auth + `translation_start_job` carrier (jobs.py + coordinator + chapter_worker) — prove the pattern, commit.
3. retranslate_dirty + resume/retry carrier — commit.
4. glossary-extraction carrier (extraction.py + extraction_worker) — commit.
5. worker-ai/knowledge carrier — commit.
6. e2e live-smoke + SESSION + RETRO.

NOT fanned out: shared confirm-route helper + the auth dual-mode pattern + shared migration file create serial dependencies; providers are checkpoints, not parallel agents.
