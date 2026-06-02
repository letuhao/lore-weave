# Plan — Precision filter runtime reload (cycle 73f)

**Cycle:** 73f — D-PASS2-FILTER-RUNTIME-FLAG
**Size:** L (7 files: 1 NEW + 6 MODIFIED; ~4 logic blocks; 1 side effect = Redis pub/sub channel)
**Session:** 1 (single-session BUILD-VERIFY-SHIP)

## Goal

Ops can change Pass2 precision filter config (categories, partial_policy, model_ref) WITHOUT compose restart. Architecture: Redis-key as source of truth + pub/sub for change notification + module-level cache in both KS + worker-ai.

## Sub-phases

### Phase 1 — SDK shared module (filter_config_store)

**Files:**
- NEW `sdks/python/loreweave_extraction/filter_config_store.py` (~80 lines)
  - `FILTER_CONFIG_REDIS_KEY = "loreweave:precision-filter-config"`
  - `FILTER_RELOAD_PUBSUB_CHANNEL = "loreweave:precision-filter-reload"`
  - `WIRE_SCHEMA_VERSION = 1`
  - `async def get_filter_config(redis_client) -> PrecisionFilterConfig | None`: GET key, parse JSON, validate schema_version, instantiate PrecisionFilterConfig OR None on disabled/missing/parse-error
  - `async def set_filter_config(redis_client, config: PrecisionFilterConfig | None) -> None`: SET (or DELETE if None) + publish pubsub signal
  - `async def subscribe_filter_reload(redis_client, on_message: Callable[[], Awaitable[None]]) -> None`: subscriber loop with backoff
- NEW `sdks/python/tests/test_extraction/test_filter_config_store.py` (~50 lines, 2 tests)

### Phase 2 — Knowledge-service integration

**Files:**
- MODIFY `services/knowledge-service/app/extraction/pass2_orchestrator.py`
  - Add `reload_precision_filter_config(new_config)` helper that atomically swaps module-level cache
  - Add `_subscribe_filter_reload_task()` async task that subscribes on startup
  - Startup hook reads Redis key first; falls through to env if empty
- MODIFY `services/knowledge-service/app/routers/internal_admin.py`
  - NEW `POST /internal/admin/precision-filter/reload` endpoint
  - Request: `FilterReloadRequest` (model_ref required unless disable=true; validators: 422 on both-set + 422 on both-empty; Field(ge=1) on max_items)
  - Response: `FilterReloadResponse` with server-generated reloaded_at + current effective config + redis-write-status
- MODIFY `services/knowledge-service/app/main.py`
  - Lifespan startup: GET filter config from Redis + spawn subscriber task
- MODIFY `services/knowledge-service/app/metrics.py`
  - NEW counter `knowledge_extraction_filter_reload_total{source, outcome}`
- MODIFY `services/knowledge-service/tests/unit/test_internal_admin.py`
  - 4 new tests: auth, happy path SET, disable path, validation errors

### Phase 3 — Worker-ai integration

**Files:**
- MODIFY `services/worker-ai/app/runner.py`
  - Startup helper that reads Redis key to seed module-level cache
  - Subscriber loop that calls store's subscribe helper + updates cache on signal
- MODIFY `services/worker-ai/app/main.py`
  - Wire subscriber task into asyncio.gather (gate via settings if needed)

### Phase 4 — VERIFY + REVIEW + SHIP

- Run all 9 new tests + regression sweep
- Cross-service live smoke (if container stable): `curl POST KS reload → wait 2s → check worker logs`
  - If container restart hits: defer smoke to D-CYCLE73F-LIVE-SMOKE, ship without
- /review-impl r2 on BUILD diff (catch fix-delta issues per cycle 73e precedent)
- POST-REVIEW human checkpoint
- SESSION_HANDOFF update
- 3-4 commits

## Verify gates

- All 9 new unit tests pass
- Regression sweep: focused entity+writer+orchestrator+resolver+test_internal_admin tests pass
- KS-only smoke: curl POST reload + GET /metrics shows counter bumped
- Cross-service smoke OR documented "live infra unavailable" deferral

## Risk → mitigation → test mapping

| Risk | Mitigation | Test |
|---|---|---|
| Drift between KS + worker cache | Single source of truth (Redis key) | `test_get_filter_config_returns_redis_value` |
| Failed Redis write = silent half-state | 502 on SET failure (not 200) | `test_reload_redis_unavailable_returns_502` |
| Subscriber crash kills worker | Outer try/except with backoff | (manual code review; integration test) |
| Malformed Redis value | Parse with try/except, log + skip, fall through to env | `test_get_filter_config_skips_malformed_json` |
| Schema drift between KS + worker | WIRE_SCHEMA_VERSION check; skip unknown versions | `test_get_filter_config_skips_unknown_schema_version` |
| In-flight job inconsistency | Documented as accepted (orchestrator already uses fresh module read per call) | (none — accepted) |

## Out of scope (deferred)

- **D-PASS2-FILTER-PER-JOB-OVERRIDE** — StartJobRequest extension + per-job carry
- **D-PASS2-FILTER-PER-USER-UI** — FE surface
- **D-CYCLE73F-LIVE-SMOKE** — cross-service smoke deferred if container restart blocks

## Expected commits

1. `feat(sdk): cycle 73f filter_config_store shared module [L/BUILD-1]`
2. `feat(knowledge-service): cycle 73f precision-filter reload endpoint + subscriber [L/BUILD-2]`
3. `feat(worker-ai): cycle 73f subscribe to filter reload + cache update [L/BUILD-3]`
4. `chore(c73f): SESSION + RETRO [L/SHIP]`

---

**PLAN locked. Ready for BUILD.**
