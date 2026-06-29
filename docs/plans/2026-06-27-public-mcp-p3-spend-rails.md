# Plan — Public MCP P3: spend rails (PUB-12 BYOK-only + per-key attribution)

- **Date:** 2026-06-27
- **Branch:** feat/public-mcp-gateway
- **Spec:** docs/specs/2026-06-26-public-mcp/04-implementation-plan.md §P3 · 03 §PUB-10/12/H-B/H-C · 05 §Wave gating
- **Size:** XL (cross-service, 2 migrations, money path). Default /loom v2.2; `/review-impl` at POST-REVIEW (credential/money).
- **User decision (CLARIFY checkpoint):** "A + B bundled" — build PUB-12 **and** the attribution rails in one effort.

## Key finding that reshaped the slice

- **PUB-12 cannot live at the edge.** Whether a call uses a BYOK (`user_model`) or platform
  (`platform_model`) model is decided at provider-registry's `/v1/llm/jobs` submit
  (`jobs_handler.go:139`). So the 402 must be enforced there.
- **The `X-Mcp-Key-Id` carrier is already wired end-to-end** *except* the last link: ai-gateway
  forwards it (`federation.service.ts:51`), both kits lift it to ctx
  (`identity.go:McpKeyIDFromCtx`, `context.py:ToolContext.mcp_key_id`). The **missing** link is
  merging it from ctx into `job_meta` at the submit chokepoint.
- **Wave gating bounds the live surface.** Wave A (read) is shipped. Wave B (this P3) opens
  `paid_read` whose **only** priced tool is `glossary_web_search` — a **Go synchronous**
  `/internal/web-search` call, a *different* chokepoint. Every priced **async-job** tool
  (`translation_start_job`, `composition_generate`, `kg_build_*`, `lore_enrichment_auto_enrich`)
  is Tier-W → **Wave C / P4**, not publicly exposed yet.

## Scope of THIS slice = the generic async-jobs spend rails

The attribution chain is a near-exact mirror of the existing `campaign_id` plumbing
(`parseJobMetaCampaignID` → `usage_outbox` → relay `buildUsageFields` → usage stream), extended
so `mcp_key_id` continues into the `usage_logs` audit row (campaign_id stops at the stream for a
separate consumer).

### Slice A — PUB-12 BYOK-only (no migration)
- `services/provider-registry-service/internal/jobs/repo.go` — add exported
  `ParseJobMetaMcpKeyID(jobMeta []byte) *uuid.UUID` (nil-tolerant, mirrors `parseJobMetaCampaignID`).
- `services/provider-registry-service/internal/api/jobs_handler.go` `doSubmitJob` — after
  model_source validation: parse `job_meta.mcp_key_id`; if present **and**
  `model_source == "platform_model"` → **402 `LLM_BYOK_ONLY`** ("public MCP keys are BYOK-only;
  platform models are not permitted"). Before the guardrail reserve (no held reservation leaked).
- Tests: 402 (platform+key), accept (user_model+key), accept (platform, no key).

### Slice B — per-key attribution (2 migrations)
- provider-registry `repo.go` `FinalizeWithUsageOutbox` — `mcpKeyID := ParseJobMetaMcpKeyID(jobMeta)`;
  add to the `usage_outbox` INSERT (col + value).
- provider-registry `migrate/migrate.go` — `ALTER TABLE usage_outbox ADD COLUMN IF NOT EXISTS mcp_key_id UUID`.
- provider-registry `jobs/usage_relay.go` — `drainOnce` SELECT `mcp_key_id::text` (nullable scan);
  `buildUsageFields` gains an `mcpKey` param + `"mcp_key_id"` field (empty string when null).
- usage-billing `usage_consumer.go` `parseUsageEvent` — `get("mcp_key_id")` → optional `*uuid.UUID`.
- usage-billing `server.go` — `usageLogParams.McpKeyID *uuid.UUID`; `writeUsageLog` INSERT col + value.
- usage-billing `migrate/migrate.go` — `ALTER TABLE usage_logs ADD COLUMN IF NOT EXISTS mcp_key_id UUID`
  + `CREATE INDEX ... idx_usage_logs_mcp_key (owner_user_id, mcp_key_id, created_at DESC)`.
- usage-billing — minimal internal aggregate endpoint `GET /internal/billing/mcp-key-usage?owner_user_id=&period=`
  GROUP BY `mcp_key_id` (gives the column a consumer; basis for H-O owner view + H-K sub-cap).
- Tests: relay field map, consumer parse, writeUsageLog persists col, rollup query.

## VERIFY (≥2 services → live-smoke required)
Drive the rails directly (no priced tool is publicly exposed yet, so this is the honest proof):
1. Submit a provider-registry job with `job_meta={"mcp_key_id": <uuid>}` + `model_source=platform_model` → **402 LLM_BYOK_ONLY**.
2. Same with `model_source=user_model` (local BYOK chat model) → accepted; on completion, the
   `usage_logs` row for that `request_id` carries `mcp_key_id`.
3. `GET /internal/billing/mcp-key-usage` returns the per-key total.

## Deferred (tracked rows — see SESSION_HANDOFF)
- **D-PMCP-WEBSEARCH-BYOK** — PUB-12 + attribution on the `glossary_web_search` synchronous
  `/internal/web-search` path. Reason: distinct chokepoint; required before Wave-B `paid_read` is opened.
- **D-PMCP-KEYID-JOBMETA-WIRING** — production SET of `job_meta.mcp_key_id` from `ToolContext`/ctx
  for each Wave-C priced tool (contextvar in `loreweave_llm` + per-service worker rehydration, the
  `campaign_id` template). Reason: those tools are Wave C / P4; rails are built now, no consumer yet.
- **H-K** per-key spend sub-cap (atomic reserve, 402) · **H-O** `mcp_call_audit` + owner audit view.
