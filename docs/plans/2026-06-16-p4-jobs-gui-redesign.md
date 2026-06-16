# P4 Jobs GUI — redesign implementation plan

**Effort:** L (continuous-flow, checkpoint per milestone)
**Spec / DESIGN artifact:** `design-drafts/2026-06-16-p4-jobs-gui-redesign-mockup.html` (PO-approved 2026-06-16)
**Epic:** Unified Job Control Plane (`docs/specs/2026-06-15-unified-job-control-plane.md`) — P4 (GUI).
**Origin:** the shipped P4 v1 (`9e5bc3ad`) was rejected by PO as too thin (title+status only, no cost/tokens/timestamps, controls hidden). This redesign re-implements against the warm-theme mockup.

## Acceptance criteria (from the mockup)

1. **List** = two tables:
   - **Active (live, unpaginated)** — non-terminal jobs (pending/running/paused/cancelling), updated in place via SSE; campaign parents with children grouped under them.
   - **History (offset+total pagination, ORDER BY created_at DESC)** — terminal jobs (completed/failed/cancelled). Stable order (SSE doesn't reorder it). Page-size selector (25/50/100) + "X–Y of N" + pager, matching glossary/chapter lists.
2. **Status summary cards** (Active / Completed / Failed / Cancelled) with owner-scoped counts, acting as quick-filters.
3. **Widened search** — spans title · kind · service · model · job ID (debounced on FE).
4. **Cost · tokens column** on every row — `cost_usd` (reliable) + `tokens_in → tokens_out` (best-effort).
5. **Detail** = progress panel (elapsed/throughput/ETA/in-flight) + **Cost & Usage** panel (cost prominent, tokens best-effort, models, Result link→P4.2) + **dynamic Parameters** panel (key-value from the job's `params` JSONB: model now, effort later — no schema change) + metadata grid + activity timeline (from SSE transitions) + child jobs + error/retry.
6. **Mobile** layout.

## Milestones (risk boundaries → checkpoint/commit each)

### M1 — backend contract + projection + read API  ← THIS milestone
- **SDK** (`sdks/python/loreweave_jobs/`):
  - `contract.py`: add to `JobEvent` **and** `JobRecord`: `model: str|None`, `cost_usd: float|None`, `tokens_in: int|None`, `tokens_out: int|None`, `params: dict|None`. Update `to_payload`/`from_payload`, `to_dict`/`from_dict`.
  - `emit.py`: add the 5 kwargs to `emit_job_event`, pass through.
- **jobs-service** (`services/jobs-service/`):
  - `migrate.py`: add columns to `job_projection` (`model TEXT`, `cost_usd NUMERIC`, `tokens_in BIGINT`, `tokens_out BIGINT`, `params JSONB`) — both in CREATE TABLE (fresh) and as `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (existing deploys; additive, nullable, on a rebuildable MIRROR). Add `idx_job_projection_owner_created` for History ORDER BY created_at.
  - `projection/store.py`:
    - `_UPSERT`: add the 5 columns to INSERT + ON CONFLICT SET with **COALESCE(EXCLUDED.x, existing.x)** (latest non-null wins — monotonic-safe because the WHERE already gates to forward-in-time/terminal events; a later event without cost never wipes the accumulated value).
    - `_COLS` + `_row_to_dict`: surface the 5 fields (cost_usd Decimal→float; params/jsonb via `_json`).
    - `list_jobs`: add **`bucket`** (`active`|`history`|None), **`offset`** (offset mode → return `total`, ORDER BY job_created_at DESC), and **widen `q`** to OR across title/kind/service/model/job_id::text. Keep keyset (cursor) for the live Active list.
    - new `count_summary(owner)` → `{active, completed, failed, cancelled}` (top-level, matching the default list view).
  - `sse.py`: `event_to_payload` carries the 5 new fields so live frames update cost/tokens without refetch.
  - `routers/jobs.py`: `list_jobs` route gains `bucket`/`offset`, returns `total`; new `GET /v1/jobs/summary`.
- **Tests:** SDK round-trip (new fields), emit passthrough, store param-mapping (spy) + real-PG (COALESCE merge, offset+total, widened search, summary), API route (bucket/offset/total/summary).
- **VERIFY:** unit green; real-PG store tests via `JOBS_TEST_PG_DSN` if reachable, else `live infra unavailable`.

### M2 — producers assemble + emit params/model/cost/tokens (cross-service, ≥2 services → live-smoke)
Each producer assembles a **whitelisted** params dict + resolved model NAME + cumulative cost/tokens and passes them to `emit_job_event` at its status chokepoints; reconcile `/internal/*/jobs` sources emit them too. Never the raw prompt/secret blob. (knowledge extraction, translation, composition, video-gen, lore-enrichment, campaign, glossary-translate.)

### M3 — FE rewrite (`frontend/src/features/jobs/`) to the mockup (warm theme, Active+History, cost/tokens, Cost&Usage + dynamic Parameters + timeline + children + error/retry, mobile).

### M4 — Playwright browser smoke on the rebuilt stack.

## Deferred
- `result_ref` deep-link (Result → entities/output) → **P4.2**.
- `provider_calls` count — dropped from v1 (sparse data).
- FE search debounce tuning → `D-JOBS-P4-SEARCH-DEBOUNCE`; overlay eviction → `D-JOBS-P4-OVERLAY-EVICT`.
