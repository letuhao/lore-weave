# SESSION_PATCH — LoreWeave Project Status

> **Source of truth for current project state.**
> Update this file at the end of every session AND at each phase/sub-phase transition.

---

## Document Metadata

- Last Updated: 2026-04-14 (session 38 — Knowledge Service K7c + K7d + K7e COMPLETE, D-K5-01 cleared)
- Updated By: Assistant (K7e end-to-end X-Trace-Id propagation across chat → knowledge → glossary → book, + JSON 500 envelopes carrying trace_id in all three services. Clears D-K5-01.)
- Active Branch: `main` (K7e commit pending)
- HEAD: K7e commit (see git log) — K7c = `160de10`, K7d = committed, K7e = this commit
- **Session Handoff:** `docs/sessions/SESSION_HANDOFF_V7.md` — full context for next agent
- **Session 37 commit count:** 10 commits (chat-service K5 + knowledge-service K6 + K7a + K7b, each with its review-fix follow-up)

---

## Deferred Items (cross-session tracking)

> **Why this section exists:** during multi-phase builds deferred items tend to drift out of mind. Every item below is something a review found and deliberately postponed rather than ignored. Check this list at the start of every phase — any row whose "Target phase" equals the current phase is a must-do.
>
> ID scheme: `D-K*-NN` = normal deferral from phase K*; `D-T2-NN` = deferred to Track 2 planning; `P-K*-NN` = perf-only, fix when profiling shows pain.

### Naturally-next-phase (actionable later)

| ID | Origin | Description | Target phase |
|---|---|---|---|
| D-K2a-01 | K2a | Glossary summary DB CHECK `content <> ''` (glossary-service side, different schema) | Standalone glossary-service pass |
| D-K2a-02 | K2a | Glossary summary size cap (glossary-service side) | Standalone glossary-service pass |

### Track 2 planning (document only, no Track 1 action)

| ID | Origin | Description |
|---|---|---|
| D-T2-01 | K2b, K4a | CJK token estimate undercounts by ~3× — swap `len/4` heuristic for tiktoken |
| D-T2-02 | K4b | `ts_rank` non-normalized — switch to `ts_rank_cd` with normalization flag |
| D-T2-03 | K5 | Unify `DEGRADED_RECENT_MESSAGE_COUNT` (chat-service) and the Mode-1/Mode-2 builder constants (knowledge-service) behind a single config knob — currently both default to 50 in two unrelated files |
| D-T2-04 | K6 | Cross-process cache invalidation for L0/L1 (Redis pub/sub or event bus). Track 1 accepts ≤60s staleness per-instance; KSA §7.3 confirms this is Track 2 scope |
| D-T2-05 | K6 | Glossary circuit-breaker half-open "one probe" guarantee — currently all concurrent calls race through when cooldown elapses. For Track 1 the breaker still re-opens on the first failure so the blast radius is bounded. Proper fix needs an asyncio.Lock or probe-in-flight flag; pair with D-T2-04 cache-invalidation work since both touch cross-call coordination |

### Perf items (fix when profiling shows pain)

| ID | Origin | Description |
|---|---|---|
| P-K2a-01 | K2a | Sequential backfill loop — one row at a time, will matter at 10k+ entities |
| P-K2a-02 | K2a | Pin toggle bumps `updated_at` → fires full `recalculate_entity_snapshot` for a bit flip |
| P-K3-01 | K3 | Backfill UPDATE on `short_description` also fires snapshot trigger per row |
| P-K3-02 | K3 | Description PATCH triggers 4 UPDATEs for 1 logical operation (CTE + trigger + regen + trigger-again) |

### Won't-fix (conscious decisions, not debt)

- **Hard-coded English Mode-1/Mode-2 instructions.** chat-service has no i18n either — revisit when the whole product ships i18n.
- **`loreweave_knowledge` backup script.** No backup infra for any service in Track 1 — cross-cutting concern owned by infra, not knowledge-service.
- **K5 retry backoff between attempts.** 500ms × 2 = 1000ms total budget leaves no room for backoff. If we ever raise the timeout, revisit. Conscious decision.
- **K5 `KnowledgeClient` is a per-worker singleton.** With multi-worker uvicorn each worker has its own client + its own pool, which is correct (httpx.AsyncClient must be constructed after fork). The "singleton" is per-process, not per-cluster, by design. Not debt — the right shape.
- **`close_knowledge_client` not guarded against concurrent calls.** Lifespan shutdown is single-threaded; not a real risk.
- **K6 glossary circuit-breaker `_cb_fail_count` drifts past threshold.** After the breaker opens at count=3, any subsequent failure that reaches `_cb_record_failure` climbs to 4, 5, … Never causes incorrect behavior (count only resets to 0 on success, and the short-circuit prevents new failures from arriving in practice). Cosmetic only — the log message `"opened after %d consecutive failures"` could over-report during a long outage. Not worth the complexity to cap.

### Recently cleared

| ID | Origin | How it was resolved |
|---|---|---|
| (K4.3) | K4b | Implemented in K4c — was mis-classified as defer; actually a Mode 2 FTS quality bug |
| (K4.12) | K4b | Implemented in K4c — no-deadline policy: if we can do it now, we do it |
| K4-I1..I9 | K4 review | All 9 K4 review issues resolved — commits `6ac161b`, `171574b` |
| **D-K4a-01** | **K4a** | **`RECENT_MESSAGE_COUNT=50` hardcoded → naturally cleared by K5: chat-service now uses `kctx.recent_message_count` from the response. Plumbing done.** |
| D-K4a-02 | K4a | Subsumed by `D-K5-01` — trace_id propagation is now tracked as a coordinated K6 task spanning all internal HTTP calls |
| K5-I1..I5 | K5 review | All 5 K5 must-fix items resolved — commit `417ae97` |
| K5-I7 | K5 review | Test patch style (brittle to import refactor) — fixed via `httpx.MockTransport` constructor injection (zero `@patch` decorators in `test_knowledge_client.py` now) |
| K5-I9 | K5 review | Mis-flagged. KnowledgeClient is per-worker by design and works correctly with multi-worker uvicorn (httpx.AsyncClient is constructed after fork inside the lifespan). Removed from review notes. |
| K6-I1..I4 | K6 review | All 4 review items fixed in the same commit as K6 BUILD plus follow-up: I1 unused `attempt` loop var → `_`; I2 added TTL-expiration test (tiny-TTL `cachetools.TTLCache` monkeypatched into the cache module); I3 `context_build_duration_seconds` histogram now labels error paths as `"not_found"` / `"not_implemented"` / `"error"` instead of lumping all under `"error"`; I4 conftest autouse fixture resets the `circuit_open` gauge between tests so a breaker-tripping test doesn't leak state into the next test's metric assertions. |
| D-K5-01 | K5 | **Cleared in K7e (this commit).** chat-service and glossary-service now have matching trace_id middleware (ASGI + chi), both forward `X-Trace-Id` on outbound internal calls (KnowledgeClient, GlossaryClient, book_client.go), and all three services return JSON 500 envelopes carrying `trace_id`. Full chain: chat → knowledge → glossary → book. |
| K7a-I1..I3 | K7a review | Empty-bearer regression test, `alg=none` + HS512 whitelist regression tests, sub-claim guard clause re-ordered for readability. Commit `b4b70de`. |
| **D-K1-01** | **K1** | **Cleared in K7b (commit `575cc36`). `SummaryContent` Annotated str (max_length=50000) in `app/db/models.py` + matching `knowledge_summaries_content_len` CHECK constraint in `app/db/migrate.py`. Pydantic guards public API, DB CHECK is defense-in-depth.** |
| **D-K1-02** | **K1** | **Cleared in K7b (commit `575cc36`). `ProjectInstructions` Annotated str (max_length=20000) + `ProjectDescription` (max_length=2000) in models, matching idempotent `knowledge_projects_instructions_len` and `knowledge_projects_description_len` CHECK constraints in migrate.py. PATCH route maps `asyncpg.CheckViolationError` → 422.** |
| **D-K1-03** | **K1** | **Cleared in K7b (commit `575cc36`). `ProjectsRepo.list()` now takes `cursor_created_at` + `cursor_project_id` with `(created_at DESC, project_id DESC)` tiebreak ordering; `GET /v1/knowledge/projects` returns `ProjectListResponse { items, next_cursor }` with base64url-encoded opaque cursor. limit is 1..100 (default 50). Cursor encoding is base64url to survive URL-encoding of `+00:00` in ISO timestamps.** |
| K7b-I1..I7 | K7b review | Commit `4fbda14`. I1 (HIGH): `ProjectsRepo.delete()` cascade order reversed — project DELETE runs first inside the transaction and rolls back the summaries cascade on 0 rows, so cross-user / nonexistent deletes never run the summary path. I2 (MEDIUM): `archive()` returns `Project | None` via `UPDATE … RETURNING`, eliminating the follow-up SELECT and its tiny race window. I3 (HIGH): `_decode_cursor` catches `UnicodeError` (parent class) — non-ASCII cursor like `?cursor=café` now returns 400 instead of leaking a 500 + traceback. I4 (MEDIUM): new test exercises the `CheckViolationError → 422` mapping via an injected exploding repo. I5..I7 cosmetic (archive docstring, hoist `cache` import, drop dead `AttributeError` catch). Also swapped `HTTP_422_UNPROCESSABLE_ENTITY` (deprecated in FastAPI 0.120) for `HTTP_422_UNPROCESSABLE_CONTENT`. |

---

---

## Module Status Matrix

| Module | Name                       | Backend | Frontend | Tests (unit) | Acceptance | Status        |
| ------ | -------------------------- | ------- | -------- | ------------ | ---------- | ------------- |
| M01    | Identity & Auth            | ✅ Done  | ✅ Done   | ✅ Partial    | ⚠️ Smoke only | **Closed (smoke)** |
| M02    | Books & Sharing            | ✅ Done  | ✅ Done   | ✅ Partial    | ⚠️ Smoke only | **Closed (smoke)** |
| M03    | Provider Registry          | ✅ Done  | ✅ Done   | ✅ Partial    | ⚠️ Smoke only | **Closed (smoke)** |
| M04    | Raw Translation Pipeline   | ✅ Done  | ✅ Done   | ✅ Passing    | ⚠️ Smoke only | **Closed (smoke)** |
| M05    | Glossary & Lore Management | ✅ Done  | ✅ Done   | ✅ Partial    | ⚠️ Smoke only | **Closed (smoke)** |

> **"Closed (smoke)"** = all code exists, smoke tests pass, formal acceptance evidence pack not yet produced.

---

## Current Active Work

**Phase 9: COMPLETE (12/12).** All phases 8A-8H + Phase 9 done. No placeholder tabs remain.

**Translation Pipeline V2: IMPLEMENTED (P1-P8).** All 8 priorities from V2 design doc implemented. Proven with real Ollama gemma3:12b model calls.

**Glossary Extraction Pipeline: FULLY COMPLETE (BE + FE + TESTED).** 13 BE tasks + 7 FE tasks + 49 integration test assertions + browser smoke test. Tested with real Qwen 3.5 9B model via LM Studio. 90 entities extracted from 5 chapters.

**Voice Pipeline V2: COMPLETE + DEBUGGED + REFACTORED.** All 48 tasks + 5 analytics tasks. V1 code cleaned up (1576 lines deleted). Pipeline state machine added. **Chat page re-architected** (session 34): MVC separation, ChatSessionContext + ChatStreamContext split by update frequency, ChatView replaces ChatWindow (never unmounts), useVoiceAssistMic unified with VadController + backend STT. Voice Assist button now wired end-to-end with backend STT + backend TTS (audio stored in S3 for replay).

**Knowledge Service: K0 + K1 + K2 + K3 + K4 + K5 + K6 + K7a + K7b COMPLETE.** (Sessions 36–37 — 7 of 9 Track 1 phases done + K7 started: K0 scaffold, K1 schema/repos, K2 glossary cache/FTS, K3 shortdesc, K4 context builder Mode 1+2, K5 chat-service integration, K6 degradation, K7.1 JWT middleware, K7.2 public Projects CRUD. Every phase review-passed.) Remaining for Track 1: **K7c (summaries endpoints), K7d (user data export/delete), K7e (gateway routes + trace_id propagation)**. Then Gate 4 end-to-end verification, then K8 frontend.

> Below is one growing section per phase, newest first. Each phase is followed by its review and any deferred-fix commits. Tests at end of session 37:
> - **knowledge-service: 164/164 passing** (up from 131/131 at end of session 36)
> - **chat-service: 156/156 passing** (unchanged after K5 landed; stable)
> - **glossary-service: all green** (untouched this session)

### K7e — End-to-End X-Trace-Id Propagation ✅ (session 38, commit pending)

**Clears D-K5-01.** Three-service middleware + outbound-client plumbing so a single `X-Trace-Id` survives the full chat → knowledge → glossary → book hop, and JSON 500 envelopes carry the id back to callers.

**Files — chat-service:**
- `app/middleware/trace_id.py` (NEW) — pure-ASGI middleware (not `BaseHTTPMiddleware`) so the `trace_id_var` ContextVar is set in the same task that runs the endpoint. Mirrors knowledge-service's existing pattern. Inbound `X-Trace-Id` adopted verbatim, else `uuid.uuid4().hex` generated; echoed on response.
- `app/main.py` — mounts `TraceIdMiddleware` first (ends up innermost via Starlette's reverse-insert stack — CORS wraps it, preflights handled by CORS before TraceId runs, normal requests flow through both). Adds `@app.exception_handler(Exception)` returning `{detail, trace_id}` JSON with `X-Trace-Id` header.
- `app/client/knowledge_client.py` — `build_context` reads `current_trace_id()` once per call and forwards the header on **every** retry attempt (not just the first).
- `tests/test_trace_id_middleware.py` (NEW, 4 tests) + `tests/test_knowledge_client.py::TestTraceIdForwarding` (3 new tests) — covers generation, adoption, contextvar isolation, retry-consistency, and empty-var → no-header.

**Files — glossary-service:**
- `internal/api/trace_id.go` (NEW) — `traceIDMiddleware` + `jsonRecovererMiddleware` + `TraceIDFromContext` + `newTraceID` (32-char hex, same wire format as the Python services). The recoverer replaces chi's `middleware.Recoverer` so panic responses carry the trace id in both the response body and the `X-Trace-Id` header.
- `internal/api/server.go` — middleware stack is now `RequestID → RealIP → traceID → jsonRecoverer`. chi's `RequestID` is deliberately kept — it's per-request-lifecycle (for panic logs); `X-Trace-Id` is the cross-service id and the two are independent.
- `internal/api/book_client.go` — both `fetchBookProjection` and `fetchBookChapters` forward `TraceIDFromContext(ctx)` as `X-Trace-Id` to book-service.
- `internal/api/trace_id_test.go` (NEW, 5 tests in package `api` — not `api_test` — so we can reach unexported `traceIDMiddleware`/`jsonRecovererMiddleware`/`newTraceID` without building a full `Server`). Covers generate-when-absent, adopt-incoming, empty-outside-middleware, 500-from-panic carries trace id, and `newTraceID` format.

**Files — knowledge-service:**
- `app/clients/glossary_client.py` — `select_for_context` reads `trace_id_var.get()` after the circuit-breaker check and forwards the header on every retry attempt. Empty var → no header (glossary-service will mint one).
- `app/main.py` — adds `@app.exception_handler(Exception)` returning `{detail, trace_id}` JSON with `X-Trace-Id` header, using the existing `trace_id_var` from `app.logging_config`.
- `tests/unit/test_trace_id_propagation.py` (NEW, 4 tests) — uses `object.__new__(GlossaryClient)` to skip `__init__` and avoid a pre-existing local-env truststore/SSL failure unrelated to this work. Uses `httpx.MockTransport` (same pattern as `test_knowledge_client.py`) for request capture. Tests: forwards on outbound, omits when unset, 500 handler body + header, 500 handler does not swallow HTTPException (404 keeps FastAPI's own envelope, trace id still echoed via middleware).

**Test results after K7e:**
- chat-service: **161/161 non-env tests passing** (154 baseline + 7 new trace_id tests).
- glossary-service: `go test ./...` all green (5 new Go tests).
- knowledge-service: **180/180 non-env tests passing** (176 baseline + 4 new trace_id tests).

**K7e second-pass review:** one comment in `chat-service/app/main.py` was inaccurate — the original note claimed "TraceIdMiddleware before CORSMiddleware so the header lands on preflights". Starlette stacks middleware such that the last-added is outermost, so CORS actually wraps TraceId and preflight OPTIONS never reach it. **Behaviour is correct** (normal requests still get X-Trace-Id; preflights don't need it), but the comment was wrong. Fixed in this commit. No functional issues found.

**Why not Redis pub/sub / OpenTelemetry:** Track 1 scope is "can an operator grep one id across three services' logs". Full distributed tracing (spans, parent/child, W3C traceparent) is Track 2 — a `traceparent` header could live alongside `X-Trace-Id` later without breaking the current plumbing.

---

### K7d — User Data Export + GDPR Erasure ✅ (session 38, commit pending)

**Files:** new `app/routers/public/user_data.py`, new `app/db/repositories/user_data.py`, new `tests/unit/test_public_user_data.py` (13 tests), additions to `app/db/repositories/summaries.py` (`EXPORT_HARD_CAP`, `list_all_for_user`), `app/db/repositories/projects.py` (`EXPORT_HARD_CAP = 10_000`, `list_all_for_user`), `app/context/cache.py` (`invalidate_all_for_user`), `app/deps.py` (`get_user_data_repo`), `app/main.py` (router mount).

- **Two endpoints under /v1/knowledge/user-data**: `GET /export` returns a `JSONResponse` with `Content-Disposition: attachment; filename="loreweave-knowledge-export-{uuid}-{date}.json"` containing `{schema_version: 1, user_id, exported_at, projects: [...], summaries: [...]}`. `DELETE ""` hard-deletes every project + summary owned by the caller and returns `{deleted: {summaries: int, projects: int}}`. Both routes JWT-authenticated via router-level `dependencies=[Depends(get_current_user)]`; `user_id` sourced ONLY from the JWT `sub` claim (never query string or body).
- **Atomic erasure via `UserDataRepo`:** new thin repo owning the cross-table delete. Both DELETEs (`knowledge_summaries` then `knowledge_projects`) run inside a single `async with conn.transaction()` so the user-visible answer is "either both tables are cleared or neither is". Cache invalidation via `cache.invalidate_all_for_user(user_id)` runs AFTER commit succeeds — if the transaction rolled back we don't want to drop fresh cached rows that are still valid.
- **New `cache.invalidate_all_for_user`:** walks `_l0_cache` + a snapshot of `_l1_cache.keys()` (not the live dict — we mutate during iteration) and pops any matching key. O(N) over total cache size; called only on erasure which is rare. Cross-process invalidation still tracked as D-T2-04.
- **Overflow safety on BOTH lists:** `ProjectsRepo.list_all_for_user` and `SummariesRepo.list_all_for_user` fetch `LIMIT EXPORT_HARD_CAP + 1` (10_000 + 1) so the route can detect the boundary. If either collection exceeds its cap the route raises HTTP 507 Insufficient Storage with a clear detail message rather than silently truncating. Silent truncation would violate GDPR's "complete copy" requirement — the whole reason export exists.
- **GDPR audit trail:** both routes emit `logger.info("gdpr.export …")` / `logger.info("gdpr.erasure …")` at INFO level with `user_id` + projects/summaries counts. Regulated data-subject requests must be traceable after the fact. Verified by `caplog` in two tests (`test_export_empty_user`, `test_delete_empty_user`).
- **Track 1 scope note (from route docstring):** export reads projects and summaries in two separate connections, NOT a single transaction. A concurrent edit between the two reads could yield a bundle where summaries reference projects that were just deleted. Track 1 accepts this — the user is exporting their own data interactively, not racing themselves. Track 3's streaming export will add a REPEATABLE READ snapshot.
- **Cross-service cascade is Track 3, not K7d:** Track 1 scope is knowledge-service-owned data only (`knowledge_projects` + `knowledge_summaries`). Chapters, chat history, glossary entries, billing records etc. stay where they are — the full cross-service GDPR orchestrator lives on a later cross-service phase and is not blocking on this work.
- **K7d review pass:** **K7d-I1 (HIGH)** — initial BUILD used `SummariesRepo.list_for_user` in the export path, which silently caps at 1000 rows. Would produce a truncated bundle for any user with >1000 summaries and quietly violate GDPR. Fixed by adding a parallel `list_all_for_user` (with its own `EXPORT_HARD_CAP = 10_000`) and a matching 507 overflow check in the route, symmetric with the projects path. **K7d-I2 (MEDIUM)** — no audit logging for these regulated operations. Added the two `gdpr.*` log lines above plus `caplog` assertions. **K7d-I3 (LOW)** — `_rows_changed` helper now duplicated in `projects.py` + `user_data.py`; deliberately not extracted because cross-coupling two unrelated repos for a 5-line parser is worse than the duplication.

**Tests after K7d (knowledge-service): 176/176 would-be passing** (up from 175 baseline to 176: 20 K7c tests untouched + 13 new K7d tests + the 7 pre-existing env-failures still ignored). Verified locally: `python -m pytest tests/unit/test_public_user_data.py` → 13 passed; full suite (minus the 3 ignored files) → 176 passed.

---

### K7c — Public Summaries Endpoints ✅ (session 38, commit `160de10`)

**Files:** new `app/deps.py` (hoisted DI helpers), new `app/routers/public/summaries.py`, new `tests/unit/test_public_summaries.py`, `SummariesRepo.list_for_user` added, small import updates in `app/routers/context.py` + `app/routers/public/projects.py` + `app/main.py`.

- **Three endpoints under /v1/knowledge/**: `GET /summaries`, `PATCH /summaries/global`, `PATCH /projects/{project_id}/summary`. Body schema for both PATCHes: `{content: str}` with `SummaryContent` Annotated max_length=50000. Empty string is allowed and persisted (does NOT delete — K7d owns user-data deletion).
- **Cross-router refactor (planned cleanup from K7b handoff):** new `app/deps.py` is now the canonical home for `get_summaries_repo` / `get_projects_repo` / `get_glossary_client`. Both `app/routers/context.py` (internal) and `app/routers/public/{projects,summaries}.py` import from `app.deps`. `context.py` re-exports the three names so existing tests' `app.dependency_overrides[app.routers.context.get_projects_repo] = ...` still work — pure refactor, zero behavioural change. K7b's awkward cross-router import is gone.
- **Project ownership check on PATCH project-summary:** `knowledge_summaries` has no FK to `knowledge_projects` (`scope_id` is nullable + shared across multiple scope_types), so an upsert against an unknown / cross-user `project_id` would silently plant an orphan row. Router calls `projects_repo.get(user_id, project_id)` first; None → 404. Test `test_patch_project_summary_cross_user_returns_404` verifies the orphan was NOT planted (`summaries_repo._rows == {}` and `invalidations == []`).
- **`SummariesRepo.list_for_user`:** new method returning all of a user's summary rows in one round-trip. Ordered by intentional `CASE scope_type` (global → project → session → entity) then `updated_at DESC`, with a hard `LIMIT 1000` safety belt so a user with thousands of project rows can't DoS the Memory page. Track 1 expects one global + a handful of projects per user — if anyone hits the cap that's a clear signal we need router-level pagination on GET /summaries.
- **Response envelope** `SummariesListResponse`: `{global: Summary | null, projects: [Summary]}`. `global` is a Python keyword so the field is named `global_` with `Field(alias="global")` and `populate_by_name=True`. Router partitions the rows from `list_for_user` and silently skips session/entity scopes (defensive — Track 1 only writes global/project anyway).
- **422 mapping:** both PATCH endpoints catch `asyncpg.CheckViolationError` and return 422 with `detail="value out of bounds: <constraint_name>"`. Pydantic gates the public surface; the DB CHECK + 422 mapping is defense-in-depth and exercised via the `_ExplodingSummariesRepo` fake.
- **K7c review pass (two rounds, all fixes landed before session end):**
  - **First pass (in-line with BUILD):** K7c-I2 (MEDIUM, `list_for_user` ordering CASE-based + LIMIT 1000), K7c-I6 (LOW, dead `ProjectCreate` import), K7c-I7 (MEDIUM, hard cap on un-paginated list).
  - **Second pass (deeper review):** **K7c-R1 (MEDIUM)** — replaced the router's two-step "ownership check then upsert" with a single `SummariesRepo.upsert_project_scoped(user_id, project_id, content)` CTE: `WITH owned AS (SELECT 1 FROM knowledge_projects WHERE user_id=$1 AND project_id=$2), upserted AS (INSERT … SELECT … WHERE EXISTS (SELECT 1 FROM owned) ON CONFLICT … RETURNING …) SELECT * FROM upserted`. Returns `Summary | None`; None → 404 in the router. **Closes the TOCTOU window between ownership check and upsert** AND halves DB pool acquisitions on the hot edit path. The router's `update_project_summary` no longer takes a `projects_repo` dep at all. K7c-R2 (LOW) — new test `test_list_global_appears_first_regardless_of_seed_order` defends the `CASE scope_type` ORDER BY; FakeSummariesRepo now mirrors the real ordering. K7c-R3 (LOW) — dropped dead `ScopeType` import. K7c-R5 (LOW) — `app/deps.py` docstring flags itself as canonical home so future devs don't redefine the helpers elsewhere. K7c-R6 (LOW) — both create-path tests now assert `version == 1`.
  - K7c-R4 (`raise … from exc` chain) intentionally skipped for K7b consistency.

**Tests after K7c (knowledge-service):** **184/184** would-be passing (164 baseline + 20 new — 19 originals + R2 ordering test). Verified locally: `python -m pytest tests/unit/test_public_summaries.py tests/unit/test_public_projects.py` → 47 passed; full suite → 168 passed (the 17 missing are pre-existing httpx/SSL truststore environment failures in `test_glossary_client.py` + `test_circuit_breaker.py` + `test_config.py` that reproduce on clean main, unrelated to K7c).

---

### K7b — Public Projects CRUD API ✅ (session 37)

**Two commits (`575cc36` BUILD + `4fbda14` review fixes).** First real user-facing surface of knowledge-service under `/v1/knowledge/projects`.

- **Router:** new `app/routers/public/projects.py` mounted in `main.py`. Six endpoints: `GET` (paginated list), `POST` (create), `GET/{id}`, `PATCH/{id}`, `POST/{id}/archive`, `DELETE/{id}`. Router-level `dependencies=[Depends(get_current_user)]` ensures 401 before any route logic runs, and every route also takes `user_id: UUID = Depends(get_current_user)` so the id is in scope for the repo call (FastAPI dedupes the dep within a request). **Cross-user access → 404** per KSA §6.4 — never leak existence of other users' rows.
- **Pagination (D-K1-03 cleared):** `ProjectsRepo.list()` now takes keyword args `cursor_created_at` + `cursor_project_id`, orders by `(created_at DESC, project_id DESC)` for a deterministic tiebreak, and fetches `limit + 1` rows so the router can detect `has_more` without a second COUNT. Cursor format is **base64url(`<iso8601>|<uuid>`)** — the base64url wrapping is not decoration, it's required: the `+` in `+00:00` and the `|` separator both collide with URL parsing without it (caught during BUILD when the first round-trip test failed). `limit` is 1..100 (default 50) enforced both at the Query parameter and defensively in the repo.
- **Length caps (D-K1-01, D-K1-02 cleared):** new Annotated str types in `app/db/models.py`: `ProjectDescription` (max 2000), `ProjectInstructions` (max 20000), `SummaryContent` (max 50000). Three new idempotent DO-blocks in `app/db/migrate.py` install matching CHECK constraints (`knowledge_projects_instructions_len`, `knowledge_projects_description_len`, `knowledge_summaries_content_len`) so the DB enforces the same limits as Pydantic. `patch_project` catches `asyncpg.CheckViolationError` and maps to 422 so DB-level rejects surface as validation errors not 500s.
- **Cascade delete:** `knowledge_summaries` has no FK to `knowledge_projects` (scope_id is nullable and shared across multiple scope types), so `ProjectsRepo.delete()` cascades manually inside a single transaction. K7b-I1 fix (review): the project DELETE now runs FIRST with an early-return + rollback on rowcount=0, so a cross-user or nonexistent delete never runs the summaries cascade. After commit, invalidates the L1 cache key (same-process only; cross-process invalidation is D-T2-04 Track 2).
- **K7b review fixes (7 issues):** Commit `4fbda14`.
  - **K7b-I1 (HIGH)** — reversed cascade order in `delete()`; added regression test `test_delete_cross_user_does_not_touch_summaries`.
  - **K7b-I2 (MEDIUM)** — `archive()` now returns `Project | None` via `UPDATE … RETURNING`, eliminating the follow-up SELECT + its race window.
  - **K7b-I3 (HIGH)** — `_decode_cursor` catches `UnicodeError` parent class; non-ASCII cursor now returns 400 not 500. Regression test `test_list_non_ascii_cursor_returns_400`.
  - **K7b-I4 (MEDIUM)** — new `test_patch_db_check_violation_maps_to_422` injects an exploding `FakeProjectsRepo` that raises `asyncpg.CheckViolationError` so the defense-in-depth 422 mapping is actually covered.
  - **K7b-I5 (LOW)** — `archive_project` docstring no longer says "idempotent-ish" (it's not idempotent — second call returns 404).
  - **K7b-I6 (LOW)** — hoisted `from app.context import cache` to module level in projects repo.
  - **K7b-I7 (LOW)** — dropped dead `AttributeError` catch from `_decode_cursor`.
  - Also swapped `HTTP_422_UNPROCESSABLE_ENTITY` → `HTTP_422_UNPROCESSABLE_CONTENT` (deprecated in FastAPI 0.120+).

**Tests after K7b (knowledge-service):** **164/164 green** — 27 new tests in `test_public_projects.py` using a `FakeProjectsRepo` + `dependency_overrides` on `get_projects_repo` / `get_current_user`. Covers list (empty, isolation, archived filter, pagination round-trip across 3 pages, invalid cursor, non-ASCII cursor, limit validation), create (happy + 4 validation modes), get (own/cross-user/nonexistent), patch (partial, cross-user, oversize, CheckViolation→422), archive (flips bit, already-archived → 404, cross-user → 404), delete (own/cross-user preserves other row/cross-user does not touch summaries/nonexistent), and the router-level missing-JWT 401.

---

### K7a — JWT Middleware for Public API ✅ (session 37)

**Two commits (`7e594f8` BUILD + `b4b70de` review fixes).** Foundation for all K7 public endpoints.

- **`app/middleware/jwt_auth.py`** — `get_current_user` FastAPI dependency parses `Authorization: Bearer <token>` with HS256 + `settings.jwt_secret` (same key as auth-service and chat-service), decodes, extracts the `sub` claim, and returns it as a `UUID`. Uses `HTTPBearer(auto_error=False)` so we own the 401 path uniformly (FastAPI's default auto-raise returns 403 for missing creds, inconsistent with the other failure modes). All failure modes return 401 with `WWW-Authenticate: Bearer` per RFC 6750.
- **Security invariants:** `user_id` is ONLY sourced from the JWT sub claim — never from query string or body. Every future /v1/knowledge/* endpoint takes `user_id: UUID = Depends(get_current_user)`. One test (`test_user_id_in_body_is_ignored`) directly proves that an attacker-supplied body field is ignored when the dep is in scope.
- **Failure modes covered (14 tests):** missing header, malformed header, expired token, wrong signature, missing sub, empty sub, non-string sub, non-UUID sub, empty bearer token, `alg=none` forgery attack (whitelist regression guard), HS512 with correct secret (whitelist regression guard), happy path with exp, happy path without exp, body-override ignored.
- **K7a review fixes (3 issues):** Commit `b4b70de`.
  - **K7a-I1 (MEDIUM)** — added `test_empty_bearer_token_returns_401` for `Authorization: Bearer ` (no token after the space).
  - **K7a-I2 (MEDIUM)** — added `test_alg_none_token_rejected` and `test_wrong_algorithm_token_rejected`. These are the load-bearing regression guards for the `algorithms=["HS256"]` whitelist — if a future refactor weakens that list the tests fail loudly. Highest-impact security test in the JWT surface.
  - **K7a-I3 (LOW)** — sub-claim guard re-ordered from `if not sub or not isinstance(sub, str)` to `if not isinstance(sub, str) or not sub` — type check first, then truthiness. Reads more clearly for non-string sub values.

---

### K6 — Graceful Degradation (Timeouts + Cache + Circuit Breaker + Metrics) ✅ (session 37)

**Two commits (`ce56986` BUILD + `94793e6` review fixes).** Makes knowledge-service robust under dependency failure and fast for hot reads. All 5 tasks (K6.1–K6.5) landed.

- **K6.1 Per-layer timeouts** — `app/context/modes/no_project.py` and `static.py` wrap each selector call (`load_global_summary`, `load_project_summary`, `select_glossary_for_context`) in `asyncio.wait_for` with env-tunable budgets (`context_l0_timeout_s=0.1`, `context_l1_timeout_s=0.1`, `context_glossary_timeout_s=0.2`, total ceiling 400ms). On timeout the layer is skipped and the build continues — partial context is preferable to a failed turn. `knowledge_layer_timeout_total{layer}` counter tracks how often each budget is exceeded.
- **K6.2 TTL cache** — new `app/context/cache.py` with `cachetools.TTLCache(ttl=60, maxsize=10_000)` instances for L0 and L1. Keyed by `user_id` (L0) and `(user_id, project_id)` (L1). Negative caching via a `MISSING` sentinel so users without a bio / without a project summary don't re-query Postgres every turn. Selectors (`load_global_summary`, `load_project_summary`) check cache first, fall through to repo on miss, `put` the result. Hit/miss metrics via `knowledge_cache_hit_total` / `knowledge_cache_miss_total`.
- **K6.3 Invalidation on writes** — `SummariesRepo.upsert/delete` call a new `_invalidate_cache()` helper after the DB write succeeds, routing by `scope_type` to `cache.invalidate_l0()` or `cache.invalidate_l1()`. Same-process only; cross-process invalidation is Track 2 (D-T2-04).
- **K6.4 Circuit breaker** — hand-rolled ~40-line state machine in `GlossaryClient` (no `purgatory` dep). Three states encoded in `(_cb_fail_count, _cb_opened_at)`: closed / open (cooldown elapsing) / half-open (cooldown elapsed, probe allowed). Opens after 3 consecutive failures, 60s cooldown, one probe allowed through on expiry. Success closes; failure re-opens with a fresh clock. **4xx / decode / shape errors do NOT trip the breaker** — only true upstream failures (timeouts, transport errors, 5xx end-to-end). `knowledge_circuit_open{service}` gauge exposes state.
- **K6.5 /metrics endpoint** — new `app/metrics.py` holds a module-level `CollectorRegistry` (not the default REGISTRY, so we only export LoreWeave metrics, not process/GC noise) and all counters/gauges/histograms. New `app/routers/metrics.py` mounted in `main.py` exposes `GET /metrics` in Prometheus format. `context_build_duration_seconds{mode}` histogram observed in the context router with a `finally` clause so error paths are also timed (labels distinguish successful modes from `not_found` / `not_implemented` / `error`).
- **K6 review fixes (4 issues):** Commit `94793e6`.
  - **K6-I1 (LOW)** — unused `attempt` loop variable in glossary_client retry → `_`.
  - **K6-I2 (HIGH)** — new TTL-expiration tests for both L0 and L1 caches using monkey-patched tiny-TTL (50ms) `TTLCache`. Guards the core eviction invariant.
  - **K6-I3 (MEDIUM)** — `context_build_duration_seconds` now distinguishes `not_found` / `not_implemented` / `error` labels. Dashboards can separate "user sent a stale project_id" (routine 404) from "knowledge-service crashed" (alert-worthy 500).
  - **K6-I4 (LOW)** — conftest autouse fixture resets the `circuit_open` gauge between tests.
- **Deps added:** `cachetools>=5.3`, `prometheus-client>=0.20`.
- **New defers filed:** D-T2-04 (cross-process cache invalidation via Redis pub/sub), D-T2-05 (breaker half-open "one probe" race — currently all concurrent calls race through when cooldown elapses). Both correctly target Track 2 since they need cross-call coordination.
- **Re-targeted defer:** D-K5-01 (trace_id propagation) moved K6 → K7e because trace_id spans middleware in 3 services and naturally belongs with K7's public-API + JWT middleware work. Not drift: K6 was the degradation phase, not the observability phase.

**Tests after K6 (knowledge-service):** 123/123 green — 41 new unit tests (`test_context_cache.py`, `test_context_timeouts.py`, `test_circuit_breaker.py`, `test_metrics_endpoint.py`) covering cache get/put/invalidate, negative caching, TTL expiration, layer timeouts per layer, breaker open/half-open/re-open transitions, 4xx not tripping the breaker, /metrics scrape format + counter observation.

---

### K5 — Chat-Service Knowledge Integration ✅ (session 37)

**Three commits (`348f49c` BUILD + `417ae97` review fixes + `f6afb27` K5-I7 MockTransport fix).** chat-service now calls knowledge-service before every LLM turn to inject a memory block into the system prompt, with graceful degradation when knowledge-service is unavailable.

- **New `app/client/knowledge_client.py`** — long-lived `httpx.AsyncClient` wrapper around `POST /internal/context/build`. **Graceful-degradation contract**: every failure path (timeout, transport error, 5xx, 4xx, decode, unexpected shape) returns a `"degraded"` `KnowledgeContext` with empty context and `recent_message_count=50`. Never raises. Chat keeps working when knowledge-service is down. Pattern mirrors `GlossaryClient` and `BillingClient`. Module-level singleton lifecycle (`init_knowledge_client` / `close_knowledge_client` / `get_knowledge_client`) managed via FastAPI lifespan.
- **`stream_service.py` + `voice_stream_service.py`** — both call `knowledge_client.build_context()` before opening the LLM stream, use the returned `recent_message_count` for history limit, and compose the system prompt as `memory_block + "\n\n" + session_system_prompt` (K5-I3 review fix: strips each part before join to avoid triple newlines). Use `session_row.get("project_id")` for dict-mock test compatibility (K5-I5 fix, revisited in K5-I5 dead-code removal).
- **`app/routers/sessions.py` (K5.5)** — `CreateSessionRequest`, `PatchSessionRequest`, `ChatSession` models get `project_id: UUID | None`. PATCH uses 3-state semantics (omit/set/explicit-null-clear) via `body.model_fields_set`, routed through a dynamic SQL boolean rather than COALESCE which can't distinguish "unset" from "clear".
- **`infra/docker-compose.yml`** — chat-service gains `KNOWLEDGE_SERVICE_URL`, `KNOWLEDGE_CLIENT_TIMEOUT_S=0.5`, `KNOWLEDGE_CLIENT_RETRIES=1` env vars. Deliberately **no** `depends_on knowledge-service` (graceful degradation — chat must start and serve requests even if knowledge-service is down).
- **K5 review fixes (5 must-fix + 2 follow-up):** Commit `417ae97`.
  - K5-I1/I2: empty-string `project_id`/`session_id` omitted from body (not sent as empty strings that would 422 via UUID validation); `message` truncated to `MESSAGE_MAX_CHARS=4000` at the client boundary to avoid pointless 422→degraded cycles on paste-heavy turns.
  - K5-I3: strip each part before `"\n\n".join()` in system prompt composition.
  - K5-I4: single warning per failed call (not per retry attempt) — eliminates log spam during outages.
  - K5-I5: remove dead guard clause in the PATCH session route + use `.get()` for asyncpg.Record compatibility with test dict mocks.
- **K5-I7 (MockTransport refactor, commit `f6afb27`):** tests previously used `@patch` decorators to monkey-patch `httpx.AsyncClient`, which would silently break if `knowledge_client.py` ever switched from `import httpx` to `from httpx import AsyncClient`. Rewrote `test_knowledge_client.py` to inject a `transport` kwarg at construction time using `httpx.MockTransport(handler)`. Zero `@patch` decorators in the file now — refactor-proof. 19/19 K5 client tests pass.
- **K5-I9** — mis-flagged, removed from deferred list. `KnowledgeClient` is per-worker by design and works correctly with multi-worker uvicorn (httpx.AsyncClient is constructed after fork inside the lifespan).

**Tests after K5 (chat-service):** **156/156 green**. Full chaos test verified: knowledge-service stopped mid-flight, chat-service kept streaming responses (degraded mode); knowledge-service restarted, chat-service resumed using memory on the next turn.

---

### K4 — Context Builder (Mode 1 + Mode 2) ✅

**Five commits across three sub-phases (a/b/c) + two review-fix commits.** Knowledge-service now exposes `POST /internal/context/build` that chat-service will call (in K5) before every LLM turn to inject a memory block into the system prompt.

- **K4a (commits `21e0a16`, `00994c3`):** foundations + Mode 1 (no project)
  - K4.1 `app/context/formatters/xml_escape.py` — `sanitize_for_xml()` strips C0/C1 controls, lone surrogates (U+D800..U+DFFF), Unicode noncharacters (U+FFFE/U+FFFF), then HTML-entity-escapes. Mandatory helper for any memory-block construction.
  - K4.2 `app/context/formatters/token_counter.py` — `len/4` heuristic (Track 2 will swap for tiktoken — `D-T2-01`).
  - K4.5 `app/context/selectors/summaries.py` — `load_global_summary` thin wrapper on `SummariesRepo`.
  - K4.7 `app/context/modes/no_project.py` — Mode 1 builder. XML: `<memory mode="no_project">` with optional `<user>` and required `<instructions>`. Two instruction variants — with-bio references "the `<user>` element above"; no-bio says "user has not provided any global bio" (review fix K4a-I3 caught the misleading "above" text).
  - K4.10 `app/context/builder.py` — `build_context()` dispatcher (K4a only handled Mode 1; K4b extended for Mode 2).
  - K4.11 `app/routers/context.py` — `POST /internal/context/build`. FastAPI dependency injection (`get_summaries_repo`, K4a-I4) replaced K4a's first-pass module-global monkey-patching. `ContextBuildResponse.model_validate(built, from_attributes=True)` (K4a-I5) eliminates manual field-copy from dataclass.
  - **K4a review fixes (8 issues):** I1 strip surrogates, I2 strip Unicode noncharacters (regression test pipes through `xml.etree.ElementTree`), I3 instruction text branches on L0 presence, I4 FastAPI DI replaces `_knowledge_pool` monkey-patch, I5 `model_validate(from_attributes=True)`, I6 `message` max_length 10000 → 4000, I7 surrogate test cases, I8 Mode 2 test parses JSON envelope.

- **K4b (commit `f89cde5`):** Mode 2 (static, project linked, extraction off)
  - K4b.0 — `glossary_service_url`, `glossary_client_timeout_s`, `glossary_client_retries` in `Settings`. `respx>=0.22` added to `requirements-test.txt` for HTTP mocking.
  - K4.4 `app/clients/glossary_client.py` — long-lived `httpx.AsyncClient` wrapper around K2b's `POST /internal/books/{id}/select-for-context`. Lifespan-managed via `init_glossary_client()` / `close_glossary_client()` in `app/main.py`. **Graceful degradation contract**: every failure path (timeout, transport error, 5xx, 4xx, decode error, unexpected shape, row validation) returns `[]` and never raises — chat keeps working when glossary-service is unavailable. `GlossaryEntityForContext` Pydantic model mirrors K2b's Go response with `extra="ignore"` for forward compat.
  - K4.6 `app/context/selectors/projects.py` — `load_project` and `load_project_summary` thin wrappers on existing repos.
  - K4.8 `app/context/selectors/glossary.py` — `select_glossary_for_context` orchestrator. Handles `book_id IS NULL` → `[]`, glossary-down → `[]`, empty result → `[]`.
  - K4.9 `app/context/modes/static.py` — Mode 2 builder. XML structure: `<memory mode="static">` with optional `<user>` (L0), required `<project name="...">` containing optional `<instructions>` and optional `<summary>` (L1), optional `<glossary>` containing one `<entity kind="" tier="" score="">` per row, and required mode-level `<instructions>`. All content XML-escaped via `sanitize_for_xml()`.
  - K4.10 dispatcher extension — fetches project, raises `ProjectNotFound` (→ 404) if missing/cross-user, raises `NotImplementedError` (→ 501) if `extraction_enabled=true`. New `ProjectNotFound` domain exception in `app/context/builder.py`.
  - K4.11 router updates — added `get_projects_repo` and `get_glossary_client` FastAPI deps, threaded `message` through, mapped `ProjectNotFound` → 404.

- **K4c (commit `6059d45`):** entity candidate extractor + cross-layer L1/glossary dedup. **K4.3 was originally classified as a defer but turned out to be a Mode 2 quality bug.**
  - **K4.3 — `extract_candidates(message)` in `selectors/glossary.py`.** The original K4b sent the raw user message to K2b as the FTS query. K2b uses `plainto_tsquery('simple', query)` which **AND-combines every token**. For "tell me about Alice", the query becomes `tell & me & about & alice` — fails because the entity vector for Alice contains only `alice`, missing `tell`/`me`/`about`. So natural-language queries hit the recent-fallback path in K2b, not the exact tier. K4.3 fixes this by extracting proper-noun candidates and issuing one parallel K2b call per candidate. Three regex passes: (1) double/single-quoted strings (trusted, no stripping), (2) English capitalized phrases 1-3 words (with leading verb-stopphrase strip and last-token push for "Master Lin" → also "Lin"), (3) CJK runs of 2+ chars secondarily split on common particles (的, 是, 了, ...). Articles ("the", "a", "an") get special handling — push BOTH "The Wanderer" AND "Wanderer" so K2b can match either (K4-I6 review fix). Verb-led phrases like "Is Mary-Anne" still get the leading "Is" stripped because verbs are never names.
  - **K4.12 — `app/context/formatters/dedup.py` `filter_entities_not_in_summary()`.** Drops glossary entries whose ≥4-char keyword overlap with the L1 summary crosses `min_overlap=2` distinct tokens (default tunable via `settings.dedup_min_overlap`, K4-I7 review fix). Pinned entities never dropped. Conservative — better to leave a redundant entry than wrongly drop one. CJK 2+ char runs counted alongside Latin tokens.
  - Wired into `static.py` after the glossary call, before XML emission.
  - **SESSION_PATCH "Deferred Items" tracking section added** (this section!) so future deferrals don't drift out of mind. CLAUDE.md updated with the "No Deadline · No Defer Drift" policy in commit `171574b`.

- **K4 review fixes (commits `6ac161b`, `171574b`):** 9 issues found across K4 (a+b+c) — all fixed.
  - K4-I1: `init_glossary_client()` idempotent guard against connection-pool leak on double-init
  - K4-I2: per-candidate K2b limit divides `max_entities` across parallel calls (`per_call = max(5, max // N + 2)`) — was over-fetching by ~5×
  - K4-I3: shared `app/context/formatters/stopwords.py` (`STOPPHRASES_LOWER`, `KEYWORD_STOPWORDS_LOWER`, `CJK_PARTICLES`, `ARTICLE_STOPPHRASES`) replaces two drifting copies
  - K4-I4: glossary client logs ONE warning per failed call (not per retry attempt) — eliminates outage log spam
  - K4-I5: dead `self._token` field removed
  - K4-I6: article-prefixed names preserved in candidate extraction
  - K4-I7: `dedup.min_overlap` plumbed through `settings.dedup_min_overlap`
  - K4-I8: `gc` pytest fixture for glossary client teardown — no manual `aclose()` leakage on test failure
  - K4-I9: `AsyncMock(spec=GlossaryClient)` / `AsyncMock(spec=SummariesRepo)` catches signature drift

**Tests after K4 (knowledge-service):** **131/131 green** — 76 unit + 55 integration. New tests since K3: 27 xml_escape (incl. surrogate regression), 8 token_counter, 5 no_project_mode, 8 glossary_client (incl. init-idempotent + log-once regressions), 7 static_mode, 17 candidate_extraction, 11 dedup, 5 glossary_selector_budget, 9 context_build endpoint integration.

**Runtime smoke verified end-to-end through docker:** K4a Mode 1 (with/without L0, XML escape, 501 on Mode 2), K4b Mode 2 (with real glossary-service call, ProjectNotFound → 404, extraction_enabled → 501, project without book → no glossary), K4c (un-pinned Alice retrieved via exact tier proving K4.3 fixed the FTS bug, CJK 李雲 retrieved end-to-end, L1 summary mentioning Alice → glossary entry dropped via K4.12 dedup, token count 163 → 144 even though L1 was added).

---

### K3 — Short Description Auto-Generator ✅

**Two commits (`2a7a76d`, `ecf9b6d`).** Glossary-service-side feature in Go.

- **K3.0 — `short_description_auto BOOLEAN NOT NULL DEFAULT true`** column added to `glossary_entities` via new `UpShortDescAuto` migration step. Should have shipped with K2a but K2a was already merged.
- **K3.1 — `internal/shortdesc/generator.go`.** Pure Go function `Generate(name, description, kindName, maxChars)`. CJK-safe (rune-counting, not byte-counting). Three-rule strategy: empty description → fallback `"{kindName}: {name}"` (with explicit 4-way switch handling all permutations of empty name/kind, K3-I6 fix), first-sentence ≤ maxChars → return first sentence (terminators: `.!?。！？`), otherwise truncate at last word boundary + `…` (one-rune ellipsis). 19 unit tests cover ASCII, CJK, hyphenated, mixed, length invariants.
- **K3.2 — `migrate.BackfillShortDescription`.** Iterates entities with NULL `short_description` AND `auto=true`, joins EAV directly for `name` (K3-I2 fix — don't rely on `cached_name` which may be NULL for untriggered rows), runs the generator, writes back via CAS-guarded UPDATE. **Cursor-based pagination on `entity_id > $cursor`** (K3-I1 fix) so the loop always makes forward progress even if a row's UPDATE returns 0 affected — eliminates a latent infinite-loop path. Honours `ctx.Err()` between batches AND between per-row UPDATEs (K3-I4 fix). Run in a background goroutine from `cmd/glossary-service/main.go` after the HTTP listener comes up, with parent ctx wired from `signal.NotifyContext`.
- **K3.3a — `patchEntity` flips `short_description_auto = false`** when the user supplies `short_description` directly. Sticky override.
- **K3.3b — `patchAttributeValue` regen hook.** When the patched attribute's `code = 'description'` AND the entity's `short_description_auto = true`, calls `regenerateAutoShortDescription(ctx, entityID)` which fetches name/desc/kind from EAV, runs the generator, and writes back guarded by `WHERE short_description_auto = true` (race protection). Errors are now logged via `slog.Warn` with entity_id (K3-I3 fix).
- **K3 review fixes (6 issues):** K3-I1 cursor-based backfill (latent infinite-loop fix with regression test using a pathological `func() string { return "" }` generator that must terminate within 3s), K3-I2 backfill SELECT joins EAV for name, K3-I3 regen error logged, K3-I4 ctx threaded into goroutine, K3-I6 generator fallback switch fixes "character:" trailing-colon bug, K3-I7 dead whitespace-walk loop in `firstSentence` removed.

**Tests after K3 (glossary-service):** 19 generator unit tests + 6 K3 integration tests (schema column, backfill populates Latin/CJK/empty-desc/auto-false-skip, backfill idempotent, cursor forward-progress, auto-regen on description update, sticky override). All pass.

**Runtime smoke verified:** seeded 3 entities (Latin + CJK + long-no-terminator), restarted glossary-service, logs showed `"backfill short-description complete processed=3"`, DB query confirmed all populated correctly. Then full HTTP round-trip with claude-test account: PATCH description → auto-regen → "A brilliant scholar.", user PATCH `short_description="USER-WRITTEN OVERRIDE"` → `auto=false`, PATCH description AGAIN → user value preserved (sticky override).

---

### K2 — Glossary Schema Additions ✅

**Four commits (`0122206`, `7405869`, `dd3d293`, `ccca20b`).** Glossary-service-side, split into K2a (schema + cache + pin endpoints) and K2b (internal FTS tiered selector + auth middleware).

- **K2b — `POST /internal/books/{book_id}/select-for-context`** (commit `dd3d293`, review fixes `ccca20b`). Tiered glossary selector used by knowledge-service's L2 fallback (KSA §4.2.5). Sequential tiers with running dedupe + budget gate:
  - Tier 0 `pinned` — `is_pinned_for_context = true`, cap 10
  - Tier 1 `exact` — `lower(cached_name) = lower(query)` OR query in `cached_aliases` (case-insensitive)
  - Tier 2 `fts` — `search_vector @@ plainto_tsquery('simple', query)` ordered by `ts_rank` (only runs when query non-empty)
  - Tier 3 `recent` — `ORDER BY updated_at DESC` fallback. **Only runs when (a) no query was given OR (b) query produced zero results** (K2b-I1 review fix — was originally pulling random recent entries even for satisfied queries, polluting the LLM context).
  - All tiers filter by `book_id + deleted_at IS NULL + NOT ANY(exclude_ids)`. `exclude_ids` accumulates across tiers via a deterministic parallel `excludedList` slice (K2b-I3 review fix — was originally rebuilt from a Go map per tier with non-deterministic order).
  - `dedupeCushion = 5` added to per-tier LIMIT to absorb dedupe overlap (K2b-I4 review fix).
  - **`requireInternalToken` middleware was already present** in glossary-service from earlier work — K2.5 was effectively already done.
  - **Bonus bug caught by tests during refactor:** `append([]uuid.UUID(nil), excluded...)` for an empty exclude list returned `nil`, which pgx serialised as SQL `NULL`, and `NOT (entity_id = ANY(NULL::uuid[]))` evaluates to NULL for every row → filters ALL rows. Fixed with explicit `make([]uuid.UUID, 0, ...)`.

- **K2a — Schema additions for L2 fallback** (commit `0122206`, review fixes `7405869`). Already documented in detail below — see "K0 + K1 + K2a COMPLETE" section.

**Tests after K2 (glossary-service):** 11 K2a integration tests + 15 K2b integration tests (including 3 added on K2b review for tier-priority, recent-skipped-when-matched, recent-fallback-when-zero-hits). All pass.

**Runtime smoke verified for K2b:** 50-entity seed with mixed pinned + un-pinned + CJK + Latin + dragon-shared-FTS-tokens. ~50ms p50 latency through HTTP for the tiered selector. Zero duplicates under aggressive tier overlap. Real `ts_rank` floats (0.0608) for FTS hits while pinned stays 1.0.

---

**Knowledge Service: K0 + K1 + K2a COMPLETE (Gates 1/2/3 passed).** (Session 36)
- **K2a — Glossary schema additions for L2 fallback (Gate 3 passed).** New columns on `glossary_entities` in `loreweave_glossary`: `short_description TEXT`, `is_pinned_for_context BOOLEAN NOT NULL DEFAULT false`, `cached_name TEXT`, `cached_aliases TEXT[] NOT NULL DEFAULT '{}'`, `search_vector tsvector` (plain column, not GENERATED). GIN index `idx_ge_search_vector` on search_vector; partial index `idx_ge_pinned_book` on `(book_id) WHERE is_pinned_for_context AND deleted_at IS NULL`.
- **Architectural decision documented**: `glossary_entities` uses EAV — `name`/`aliases` live in `entity_attribute_values`, not as first-class columns. Promoting them would break translations (`attribute_translations.attr_value_id` FK), evidence linkage, and the GEP extraction pipeline. Chose the **cache** path: `cached_name` + `cached_aliases` are trigger-maintained denormalizations; EAV stays source of truth. Reversible and touches no downstream code.
- **Trigger strategy**: extended the existing `recalculate_entity_snapshot(p_entity_id)` PL/pgSQL function (CREATE OR REPLACE preserves all trigger bindings) to ALSO write `cached_name`, `cached_aliases`, and `search_vector` in a single UPDATE. `cached_name` reads from EAV where `ad.code IN ('name','term')` ordered by priority. `cached_aliases` parses the JSON-array string stored in the `aliases` attribute's `original_value` via `jsonb_array_elements_text` inside a BEGIN/EXCEPTION block (defensive on malformed JSON → empty array). `search_vector` uses `to_tsvector('simple', cached_name || ' ' || array_to_string(cached_aliases,' ') || ' ' || short_description)`.
- **Why `search_vector` is NOT a `GENERATED ALWAYS AS ... STORED` column**: Postgres 18 rejects the expression as "not immutable" — `array_to_string` over a nullable text[] combined with multi-coalesce trips the planner check even with `'simple'::regconfig` cast. Falling back to a plain column maintained by the same single trigger path is simpler and has zero write amplification vs a generated column.
- **Self-trigger extended**: `trig_fn_entity_self_snapshot` now also watches `short_description` changes (in addition to `status`/`alive`/`tags`/`kind_id`/`updated_at`), so direct SQL updates to `short_description` refresh `search_vector` even when `updated_at` isn't bumped. The API PATCH path already bumped `updated_at`; this is defensive for migrations and backfills.
- **Recursion safety**: the UPDATE inside `recalculate_entity_snapshot` only touches `entity_snapshot`, `cached_*`, `search_vector` — none of which are watched by the self-trigger — so no recursive trigger cascade. WHERE-clause distinctness guard REMOVED (it would have suppressed writes when only `short_description` changed, leaving `search_vector` stale).
- **Go API changes** (`entity_handler.go`, `server.go`):
  - `entityListItem` gains `short_description *string` + `is_pinned_for_context bool` (JSON keys `short_description`, `is_pinned_for_context`).
  - `loadEntityDetail` + `listEntities` SELECTs updated to return the new fields.
  - `patchEntity` accepts `short_description` (string/null, 500-char trimmed max) and `is_pinned_for_context` (bool).
  - New `POST/DELETE /v1/glossary/books/{book_id}/entities/{entity_id}/pin` endpoints (idempotent, 204 on success, 403 on cross-user, 404 on missing/soft-deleted).
- **Backfill**: new `BackfillKnowledgeMemory` migrate step iterates entities where `cached_name IS NULL` and calls `recalculate_entity_snapshot` per row. Idempotent (once cached, future runs skip). Verified: 190/191 live entities got `cached_name`, 191/191 got `search_vector` (the one without cached_name is an entity with no name/term attribute value in EAV).
- **Gate 3 verified end-to-end**: rebuilt glossary-service, all 5 columns + 2 indexes present, CJK `cached_name` + `cached_aliases` populated on real entities, `search_vector @@ plainto_tsquery('simple', 'direct')` finds entity right after direct `short_description` UPDATE (proving trigger fires), `is_pinned_for_context` toggle + partial-index roundtrip works, `go build ./...` + `go vet ./...` + existing `go test ./...` all clean (no regression).
- **Deferred to K2b**: `POST /internal/glossary/select-for-context` tiered FTS endpoint, internal-auth middleware for `/internal/*` routes, dedicated Go integration tests. Frontend pin UI and `short_description` editor are K8/K3.

**Knowledge Service: K0 + K1 COMPLETE (Gate 1 + Gate 2 passed).** (Session 36)
- **K1 — Postgres schema + repositories (Gate 2 passed).** Tables `knowledge_projects` + `knowledge_summaries` created via `app/db/migrate.py` (inline DDL string + `run_migrations(pool)`, same house style as chat-service). Cross-DB FKs intentionally dropped — `user_id` and `book_id` are bare UUIDs, validated in app. Both tables include all extraction fields (default-off) from KSA §3.3 even though Track 1 doesn't use them. `knowledge_summaries` unique constraint uses Postgres 15+ `NULLS NOT DISTINCT` so `(user, 'global', NULL)` duplicates conflict.
- **Repositories:** `ProjectsRepo` (create/list/get/update/archive/delete) + `SummariesRepo` (get/upsert/delete), all parameterized ($1, $2), every query filters by `user_id = $1`. `update()` uses Pydantic `ProjectUpdate.model_dump(exclude_unset=True)` with a `_UPDATABLE_COLUMNS` allowlist as defense-in-depth. `archive()` returns True only if the bit flipped. Rowcount parsing via `_rows_changed()` instead of fragile `endswith(" 1")`.
- **Summaries upsert** uses `ON CONFLICT (user_id, scope_type, scope_id) DO UPDATE` with `version = knowledge_summaries.version + 1`. Token count heuristic `len // 4` (English-biased; Track 3 will use tiktoken).
- **chat-service change:** `chat_sessions.project_id UUID` column + `idx_chat_sessions_project` partial index added idempotently to chat-service's DDL in `app/db/migrate.py`. No FK (cross-DB). No chat-service API change in K1 — wired in K7.
- **Migrations run on lifespan startup** from knowledge-service's `main.py` via `run_migrations(get_knowledge_pool())`, after pools are created. Idempotent — verified by container restart.
- **Tests:** 16 new integration tests in `tests/integration/db/` (own subdir with local `conftest.py` so DB-autouse truncation doesn't cascade into the auth test). Covers: schema shape, idempotency, CHECK constraint rejection, partial index existence, NULLS NOT DISTINCT collision, projects CRUD, archive semantics, summaries upsert (version bump), null scope_id handling, and **cross-user isolation for both projects and summaries** — user B cannot get/list/update/archive/delete user A's rows. Pool fixture is function-scoped to avoid pytest-asyncio loop-scope conflicts. **26/26 pass total** (10 K0 unit/auth + 16 K1 DB).
- **Gate 2:** fresh `loreweave_knowledge` has both tables after container startup; restart is a no-op; CHECK constraints reject invalid `project_type`/`extraction_status`; unique index collides on repeat `(user, 'global', NULL)`; cross-user isolation verified via repo tests; chat-service container still healthy after its DDL change; `\d chat_sessions` shows `project_id` column + partial index.
- **K1 review fixes (3 issues):** J1 explicit `_UPDATABLE_COLUMNS` allowlist for dynamic SET (defense-in-depth over implicit Pydantic coupling); J2 `_rows_changed()` helper replaces fragile `status.endswith(" 1")`; J3 `archive()` docstring clarifies "returns True only if this call flipped the bit".
- **Deferred:** `extraction_pending` / `extraction_jobs` tables → K10 (Track 2); public CRUD API → K7; frontend UI → K8; repo-layer logging → K7.
- **Next:** K2 — glossary-service schema additions (`short_description`, `is_pinned_for_context`, `search_vector` tsvector + GIN index) in the glossary-service Go codebase.

**Knowledge Service: K0 SCAFFOLD COMPLETE (Gate 1 passed).** (Session 36)
- New service `services/knowledge-service/` (Python 3.12 / FastAPI, pip + requirements.txt to match chat-service style).
- Internal port **8092**, external **8216**, gateway route `/v1/knowledge/*`.
- Files: `app/config.py` (Pydantic BaseSettings, fail-fast on missing `KNOWLEDGE_DB_URL` / `GLOSSARY_DB_URL` / `INTERNAL_SERVICE_TOKEN` / `JWT_SECRET`), `app/logging_config.py` (JSON logging via `python-json-logger`, `contextvars` trace_id, `RedactFilter` stripping `sk-*` and `Bearer *`), `app/db/pool.py` (two asyncpg pools: knowledge_pool RW + glossary_pool RO for FTS), `app/middleware/internal_auth.py` (`secrets.compare_digest` on `X-Internal-Token`), `app/middleware/trace_id.py` (Starlette middleware echoing `X-Trace-Id`), `app/routers/health.py` (GET /health pings both pools, 503 on failure), `app/routers/ping.py` (temporary K0-only `/v1/knowledge/ping` + `/internal/ping` — delete in K7), `Dockerfile` (python:3.12-slim mirrored from chat-service), `main.py` (lifespan creates/closes pools, sets up logging).
- `infra/docker-compose.yml`: new `knowledge-service` service with healthcheck + json-file logging + depends_on postgres/redis/glossary-service; `api-gateway-bff` gets `KNOWLEDGE_SERVICE_URL: http://knowledge-service:8092` and new depends_on.
- `infra/db-ensure.sh`: appends `loreweave_knowledge` to auto-create list.
- `services/api-gateway-bff/src/main.ts` + `gateway-setup.ts`: new `knowledgeUrl` env, `knowledgeProxy`, path-filter dispatch for `/v1/knowledge`. TS typecheck clean. `/internal/*` NOT exposed through gateway.
- **Tests:** `tests/conftest.py` (env preload), `tests/unit/test_config.py` (3 tests — subprocess isolation for missing/present env + defaults sanity), `tests/unit/test_logging.py` (4 tests — redact filter, context filter, trace_id uniqueness), `tests/integration/test_internal_auth.py` (3 tests — 401 missing/wrong, 200 correct, using `monkeypatch.setattr` on live settings singleton). **10/10 pass, test order independent.**
- **Review fixes (9 issues):** I1 Dockerfile non-root `app` user (uid 100); I2 test isolation via subprocess-per-test_config + conftest env preload + monkeypatch-on-singleton (previous suite passed only by Python import-caching accident); I3 pool.py cleans up knowledge_pool if glossary_pool creation raises; I4 health.py narrows `except` to `(asyncpg.PostgresError, asyncio.TimeoutError, OSError, RuntimeError)`; I5 uvicorn loggers (`uvicorn`, `uvicorn.error`, `uvicorn.access`) now capture the JSON formatter — entire stdout is JSON incl. access logs; I6 `TraceIdMiddleware` rewritten as pure ASGI middleware (no `BaseHTTPMiddleware`) — trace_id contextvar lives for full task lifetime and shows up in uvicorn access logs; I7 removed vestigial `env_file=".env"`; I8 health.py logs `str(exc)` so `RedactFilter` can scrub DSN leaks; I9 `setup_logging` moved into `lifespan` startup. `X-Trace-Id` inbound header propagates end-to-end and round-trips in response header.
- **Gate 1 smoke (end-to-end, docker compose up):** container healthy in ~9s, `/health` 200 with both dbs ok, `/internal/ping` 401 on wrong token + 200 on `dev_internal_token`, `/v1/knowledge/ping` 200 direct AND through gateway :3123, JSON log lines with `trace_id` field visible, `loreweave_knowledge` DB auto-created by db-ensure on startup.
- **Deferred from Track1 doc (intentionally):** redis dep (K10), purgatory circuit breaker (K6), migrations tooling (K1.1). No schemas, no business logic — pure plumbing.
- **Next:** K1 — pick yoyo-migrations, write `migrations/001_projects.sql` + `002_summaries.sql`, add repository layer.

**Knowledge Service: DESIGN COMPLETE.** (Session 34)
- Architecture doc: `docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md` (~5500 lines). 5 review rounds (data eng, context eng, solution architect, 6-perspective, research validation).
- Three PM-grade implementation plans: `KNOWLEDGE_SERVICE_TRACK1_IMPLEMENTATION.md` (K0-K9, 64 tasks), `TRACK2` (K10-K18, 81+ tasks), `TRACK3` (K19-K22, 69 tasks). Total ~215 tasks across 22 gates.
- UI mockup: `design-drafts/screen-knowledge-service.html` (1767 lines, 14 sections, 3-step build wizard with glossary picker + pending proposals + gap report).
- **Two-layer anchoring pattern** adopted and documented: glossary-service remains authored SSOT; KS adds fuzzy/semantic entity layer with `glossary_entity_id` FK. Validated by GraphRAG seed-graph (arXiv:2404.16130, ~34% duplicate reduction), HippoRAG (arXiv:2405.14831, 18-25% multi-hop QA gain), Lettria Qdrant case study (20% KG-QA improvement).
- **Wiki is inside glossary-service**, not a separate service (`wiki_articles`, `wiki_revisions`, `wiki_suggestions` tables). KS proposes stubs via existing `/wiki/generate` endpoint — no duplicate storage.
- **Evidence storage**: existing `glossary.evidences` table already stores rich per-attribute provenance (chapter_id, block_or_line, evidence_type, original_text, translations, confidence). API returns nested array. **G-EV-1 COMPLETE** — evidence browser tab in entity editor with server-side pagination, filters, sort, language fallback, full CRUD.

**G-EV-1: Glossary Evidence Browser — COMPLETE + REVIEWED (session 35)**
- **BE:** `chapter_index` column on evidences, `GET /entities/{id}/evidences` (pagination, filters, sort, language fallback via LEFT JOIN, dynamic `available_languages`), `createEvidence` accepts `chapter_index`, `updateEvidence` supports evidence_type/chapter_id/title/index patching. Filter options only queried on first page (offset=0). Available attributes query returns ALL entity attrs (not just those with existing evidences).
- **FE:** Tab system in EntityEditorModal (Attributes / Evidences), EvidenceTab split into 4 focused modules (useEvidenceList hook, EvidenceFilterBar, EvidenceCreateForm, EvidenceCard — all under ~200 lines). ConfirmDialog for delete, separate edit/create saving state, no double-fetch on filter change, footer hidden on evidences tab, evidence count updated locally.
- **Tests:** `infra/test-evidence-browser.sh` — 30+ assertions (CRUD, filters, sort, pagination, language fallback, validation)
- **Review:** 11 issues found and fixed (1 critical, 6 high, 4 medium). Commits: `3b06f7e` (impl), `67cf138` (review fixes).

**Inline Attribute Translation Editor — COMPLETE + REVIEWED (session 35)**
- **No backend changes** — CRUD endpoints already existed (`POST/PATCH/DELETE .../translations`), frontend API layer was missing.
- **FE:** Language selector in entity editor tab bar (right side), AttrTranslationRow component renders inline below each attribute card when a language is selected. Per-attribute save (create/update/delete). Confidence selector (draft/verified/machine). Blue dot indicator on attributes that have translations. BCP-47 validation for new language codes. `bookOriginalLanguage` included in dropdown.
- **Review:** 8 issues found and fixed (4 high, 4 medium). Commit: `fa36e99`.
- **API methods added:** `glossaryApi.createTranslation()`, `patchTranslation()`, `deleteTranslation()`.

**Next priority:** K0 + K1 + K2 + K3 + K4 ALL done (5 of 9 Track 1 phases). Continue at **K5** — chat-service integration. chat-service calls `POST /internal/context/build` before every LLM turn and injects the returned memory block into the system prompt, with graceful degradation if knowledge-service is unavailable. Naturally clears two more deferrals from the tracking list: `D-K4a-01` (RECENT_MESSAGE_COUNT config — chat-service owns the replay budget) and `D-K4a-02` (500 response correlation id — chat-service becomes the first real caller). Read `docs/03_planning/KNOWLEDGE_SERVICE_TRACK1_IMPLEMENTATION.md` §9 (K5.1 through K5.x).

Before starting K5, the agent must read the **Deferred Items** section above. Any row whose `Target phase` is `K5` is a must-do for K5.

Phases completed:
- **A: Core Pipeline (11)** — TextNormalizer, SentenceBuffer, voice_stream_response, POST /voice-message, VoiceClient, VadController, useVoiceChat, VoiceChatOverlay
- **B: Audio Persistence (8)** — message_audio_segments migration, S3 upload, audio segments GET endpoint, AudioReplayPlayer, cleanup + GDPR erasure
- **C: UX Polish (8)** — mic badge, health dot, "Thinking..." indicator, error recovery, VAD presets + adaptive settings
- **D: Voice Assist (7)** — push-to-talk with backend STT, 4-state mic button, auto-TTS on AI response, stop audio button
- **E: Security (9)** — voice consent dialog, textarea guard, debug metrics toggle, headphone detection utility
- **Analytics (5)** — voice.turn events to Redis, statistics-service consumer, correlation-based recommendations, lean schema optimization

**Cloud Readiness Audit: COMPLETE (26/26 tasks).** All P0+P1+P2 tasks implemented + reviewed. 21 commits across 12 Go services, 2 Python services, 1 NestJS gateway, 8 frontend components, docker-compose.

### What was done in this session (2026-04-11→12, session 32):

**Part 1 — Voice Pipeline V2 architecture redesign (3 iterations):**
1. Original V2 (session 31): client-side `VoicePipelineController` state machine
2. V2.1: Vercel Workflow server-side orchestration → **rejected** (Vercel-only platform, doesn't run on AWS, wrong abstraction for voice)
3. V2.2: chat-service integration → **accepted** — voice is a new endpoint in existing chat-service, extends `stream_response()` with STT input + TTS output. No new service, no framework, ~70% code shared with text chat
4. 6-perspective review (architecture, cloud/infra, performance, security, data, UX) found 46 V2 issues → all resolved

**Part 2 — Cloud readiness audit (4-perspective parallel):**
- Frontend local storage, backend cloud issues, multi-device compat, platform lock-in
- Found 46 issues → created CRA-01..26 task list

**Part 3 — Cloud Readiness implementation (26 tasks, 21 commits):**

| Phase | Tasks | Commits | Summary |
|-------|-------|---------|---------|
| P0 | CRA-01..05 | `1e8eed3`..`c009a26` (5) | Secrets required across 12 services, MINIO_EXTERNAL_URL required, responsive chat layout + settings panels |
| P1 | CRA-06..15 | `a0b8e98`..`671e929` (7) | Preference sync to server (4 keys), DB pool tuning (10 Go + 2 Python), touch-accessible buttons (8 components), iOS AudioContext fix, voice on all browsers |
| P2 | CRA-16..26 | `fd66a03`..`e1851d9` (5) | Docker healthchecks (11 services), localhost fallback removal (7 Go + gateway), NestJS shutdown hooks, touch targets, DataTable overflow, VoiceModeOverlay touch, format pills wrap |

Each task followed: PLAN → BUILD → TEST → REVIEW → COMMIT → REVIEW IMPLEMENTATION ISSUES → FIX.

**Part 4 — Voice Pipeline V2 Phase A backend (6 tasks, 10 commits):**

| Task | Commit | Tests | Summary |
|------|--------|-------|---------|
| VP2-12 | `6dd0461` | — | `message_audio_segments` table migration |
| VP2-01 | `59bddab`, `3c02c9c` | 24 | TextNormalizer (markdown/code/emoji stripping + review fixes) |
| VP2-02 | `5af56ea`, `b4de4ef` | 31 | SentenceBuffer (sentence + clause + CJK + review fixes) |
| VP2-03 | `e0ad004`, `145a10a` | — | `voice_stream_response()` core pipeline + review fixes |
| VP2-05 | (in VP2-03) | — | Voice system prompt injection (Layer 0) |
| VP2-04 | `f29a811`, `5f59329` | 7 | `POST /voice-message` endpoint + review fixes |
| Test fixes | `324e70a` | +71 | Fixed 14 pre-existing test failures |

133 chat-service tests pass (0 failures).

| Work item | Files | Status |
| --------- | ----- | ------ |
| V2 architecture doc | `VOICE_PIPELINE_V2.md` | Design complete (43 tasks) |
| V2 Phase A backend | `voice_stream_service.py`, `voice.py`, `text_normalizer.py`, `sentence_buffer.py`, `migrate.py` | 6/43 tasks done |
| Cloud readiness audit doc | `CLOUD_READINESS_AUDIT.md` | 26/26 tasks complete |
| Hosting direction | Memory | Cloud (AWS), multi-device |

**Key decisions:**
- LoreWeave targets cloud hosting (AWS) — multi-device (PC, mobile, tablet)
- All user preferences sync to server (DB), localStorage is cache only
- No platform lock-in (Vercel Workflow rejected)
- All services fail-fast on missing required env vars (no silent defaults)
- Voice Pipeline V2 Phase A backend complete — next: Phase A frontend (VP2-06..11)

**What was done in previous session (2026-04-10→11, session 31):**

Five major areas completed: GEP end-to-end, Voice Mode for chat, AI Service Readiness infrastructure, Real-Time Voice pipeline (RTV), Voice Pipeline V2 architecture design. 50+ commits total.

| Work item | Files | Commit |
| --------- | ----- | ------ |
| GEP BE fixes: 10 bugs from real AI model testing (worker wiring, internal invoke, reasoning model support, truncated JSON repair, adapter params) | 6 files across 3 services | `3c5202a` |
| GEP-BE-13: Integration test script (49 assertions: cancellation, multi-batch, concurrent, dedup, API validation) | `infra/test-gep-integration.sh` | `5b66021` |
| GEP-FE-01: Extraction types + API layer | `features/extraction/types.ts`, `api.ts` | `d6f2a14` |
| GEP-FE-02: Wizard shell + extraction profile step + i18n (4 languages) | `ExtractionWizard.tsx`, `StepProfile.tsx`, `useExtractionState.ts`, 4 locale files | `10ee995` |
| GEP-FE-03: Batch config step | `StepBatchConfig.tsx` | `5b11bfb` |
| GEP-FE-04: Estimate & confirm step | `StepConfirm.tsx` | `9693a7a` |
| GEP-FE-05: Progress + results steps | `StepProgress.tsx`, `StepResults.tsx`, `useExtractionPolling.ts` | `be7e7e1` |
| GEP-FE-06: Entry point wiring (GlossaryTab, ChaptersTab, TranslationTab) | 3 tab files | `8a4ce0b` |
| GEP-FE-07: Alive badge + toggle on entity list | `GlossaryTab.tsx`, `glossary/api.ts` | `90a7410` |
| Browser smoke test: 9 screens verified (Playwright MCP) | — | — |
| Session/plan audit: SESSION_PATCH + 99A planning doc markers updated | docs | `3f33d69`, `79264c4` |
| **Voice Mode (VM-01..VM-06):** | | |
| VM-01: useSpeechRecognition hook (Web Speech API, factory pattern) | `hooks/useSpeechRecognition.ts` | `077d97d` |
| VM-02: Voice settings panel + STT/TTS model selectors, i18n 4 langs | `VoiceSettingsPanel.tsx`, `voicePrefs.ts`, 4 locale files | `ba2242f` |
| VM-01+02 review: 4 issues (singleton→factory, stale closure, restart cap, backdrop) | 2 files | `b03ef0b` |
| VM-03+04: Voice mode orchestrator + push-to-talk mic button | `useVoiceMode.ts`, `ChatInputBar.tsx` | `eaac89f` |
| VM-05: Voice mode overlay (waveform, transcript, controls) | `VoiceModeOverlay.tsx`, `WaveformVisualizer.tsx` | `5f265ff` |
| VM-06: Integration wiring (ChatHeader + ChatWindow) | `ChatHeader.tsx`, `ChatWindow.tsx` | `1542208` |
| VM review: 13 issues (stale closures, session change, ARIA, dual STT) | 7 files | `0d7318a` |
| **External AI Service Integration Guide:** | | |
| Integration guide: 830 lines, 4 service types (TTS/STT/Image/Video) | `docs/04_integration/` | `d62c4c4` |
| Spec alignment: verified against OpenAI Python SDK (2025-12) | docs | `a37ff4e` |
| Streaming TTS/STT contracts + known limitations section | docs | `75e1b4f` |
| **AI Service Readiness (AISR-01..05):** | | |
| AISR-01: Gateway /v1/audio/* proxy routes (TTS, STT, voices) | `gateway-setup.ts`, `docker-compose.yml` | `89bfc74` |
| AISR-02: Mock audio service (Python/FastAPI, sine-wave TTS, mock STT) | `infra/mock-audio-service/` | `96b8b10`, `d17f7fd` |
| AISR-03: useBackendSTT hook (MediaRecorder → multipart upload) | `hooks/useBackendSTT.ts` | `114358b` |
| AISR-04: useStreamingTTS hook (fetch → AudioContext playback) | `hooks/useStreamingTTS.ts` | `14541fc` |
| AISR-05: Integration test script (19 assertions) | `infra/test-audio-service.sh` | `bdb2153` |
| AISR-03+04 review: 20 issues (AudioContext leaks, race conditions, Safari) | 3 files | `e54557e` |
| **Real-Time Voice Pipeline (RTV-01..04):** | | |
| RTV-01+02: SentenceBuffer + TTSPlaybackQueue (18 unit tests) | `lib/SentenceBuffer.ts`, `lib/TTSPlaybackQueue.ts` | (earlier commits) |
| RTV-03: Wire streaming TTS pipeline into voice mode + review (16 issues) | `useVoiceMode.ts`, `TTSConcurrencyPool.ts` | `b9beb86`, `4f8d50b` |
| RTV-04: Barge-in detection + review (16 issues) | `BargeInDetector.ts` | `02409b1`, `0098584` |
| Voice settings button in chat header + TTS voice selector | `ChatHeader.tsx`, `VoiceSettingsPanel.tsx` | `e425587`, `6b48cb3` |
| Fix: STT language region strip, live metrics overlay | `useBackendSTT.ts`, `VoiceModeOverlay.tsx` | `91edae5`, `8ff758c` |
| Fix: double-send (imperative pipeline), infinite loop (noise), generation counter | `useVoiceMode.ts` | `425b05d`, `eaa66e5`, `8827928` |
| Fix: Silero VAD integration (4 iterations: nginx MIME, CDN, vite-plugin-static-copy) | `useBackendSTT.ts`, `nginx.conf`, `vite.config.ts` | `e117db6` + 5 fix commits |
| **Voice Pipeline V2 Architecture (design-only):** | | |
| V2 architecture doc: strict state machine, audio persistence, text normalizer | `VOICE_PIPELINE_V2.md` | `ee77ac8`, `5fac900` |
| 5 review rounds (context/data/UX/security/performance): 39 issues addressed | `VOICE_PIPELINE_V2.md` | `5b666c8` |
| Phase E (voice assist mode), Phase D (metrics), streaming TTS | `VOICE_PIPELINE_V2.md` | `4a05419`, `2fa1f40`, `6e1d81e` |
| Competitor review (OpenAI Realtime, Pipecat, LiveKit, ElevenLabs) + 5 latency optimizations | `VOICE_PIPELINE_V2.md` | uncommitted |

**9-phase workflow followed for each FE task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in previous session (2026-04-10, session 30):**

| Issue | Severity | Fix |
| ----- | -------- | --- |
| C1: Wrong config attr `provider_registry_url` | Critical | → `provider_registry_service_url` |
| C2: Silent `_, _` on 4 DB inserts in glossary upsert | Critical | → `slog.Warn` on all 4 |
| C3: Missing `json.RawMessage` cast in book-service | Critical | → Cast added in both GET responses |
| H1: No top-level try/except in extraction worker | High | → Split into handler + inner runner |
| H2: Silent batch failure in LLM invoke | High | → Log with batch index + kind codes |
| H3: Unbounded known_entities accumulation | High | → Capped at 200 |
| H4: `import json` inside function body | High | → Moved to top-level |
| M1: Hardcoded cost estimate without context | Medium | → Added design reference comment |
| M2: `ent.pop("relevance")` mutates parsed dict | Medium | → Changed to `ent.get()` |
| M3: No upper bound on queryInt limits | Medium | → Clamp recency≤1000, limit≤500 |

**Commits (session 30):**
- Prior commits: GEP-BE-01..12 (see git log for full list)
- `0a07766` fix: post-review fixes for GEP extraction pipeline (10 issues)

**What was done in previous session (2026-04-09, session 29):**

Translation Pipeline V2 — full implementation (9-phase workflow). PoC first (3 scripts with real AI model calls), then full implementation across 2 services.

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| P1: CJK-aware token estimation | `chunk_splitter.py` | Done |
| P1b: Expansion-ratio budget + 40-block cap | `block_batcher.py` | Done |
| P2: Output validation + retry (2 retries with correction prompt) | `session_translator.py` | Done |
| P3: Multi-provider token extraction (OpenAI/Anthropic/Ollama/LM Studio) | `session_translator.py` | Done |
| P4: Glossary context injection (tiered, scored, JSONL) | `glossary_client.py` (new), `session_translator.py` | Done |
| P4b: Internal glossary endpoint | `glossary-service/server.go` | Done |
| P5: Rolling context between batches | `session_translator.py` | Done |
| P6: Auto-correct post-processing (source term replacement) | `glossary_client.py` | Done |
| P7: Cross-chapter memo table + load/save | `migrate.py`, `chapter_worker.py` | Done |
| P8: Quality metrics columns (validation_errors, retry_count, etc.) | `migrate.py` | Done |
| Config: glossary-service URL | `config.py`, `docker-compose.yml` | Done |
| Tests: 31 new V2 tests (280 total pass) | 4 test files | Done |
| PoC: 3 real AI model scripts | `poc_v2_real.py`, `poc_v2_glossary.py` | Done |
| Fix: glossary endpoint Tier 2 fallback (no chapter_entity_links) | `glossary-service/server.go` | Done |
| Fix: provider-registry forward usage tokens in invoke response | `provider-registry-service/server.go` | Done |
| Fix: translated_body_json JSONB string parse in Pydantic model | `models.py` | Done |
| Docker integration test: 132-block chapter, glossary 12 entries, in=5223 out=3670 | real Ollama gemma3:12b | Pass |

**3 commits:**
- `662cbf7` feat: Translation Pipeline V2 — CJK fix, glossary injection, validation
- `1aa25b3` fix: glossary endpoint fallback when no chapter_entity_links exist
- `6db8553` fix: forward usage tokens in provider-registry, parse JSONB string in models

**Integration test results (Docker Compose, real Ollama gemma3:12b):**
- Chapter 1 (132 blocks): 4 batches (40+40+40+12), all valid first attempt, ~68s
- Chapter 2 (113 blocks): 3 batches (40+40+33), all valid first attempt, ~51s, in=5223 out=3670
- Glossary: 12 entries injected (~179 tokens), correction rules active
- Token counts: now flowing correctly from Ollama → provider-registry → translation-service → DB

**9-phase workflow followed:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in previous session (2026-04-09, session 28):**

P9-08a Wiki article CRUD + revisions — backend implementation in glossary-service. 2 tables (wiki_articles, wiki_revisions), 9 endpoints, wiki_handler.go (new), migration, routes. Review: 3 fixes (spoiler init, rows.Err checks). Integration tests: 75/75 pass.

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| Migration: wiki_articles + wiki_revisions tables | `glossary-service/internal/migrate/migrate.go` | Done |
| Wiki handler: 9 endpoints (list, create, get, patch, delete, list revisions, get revision, restore, generate) | `glossary-service/internal/api/wiki_handler.go` (new) | Done |
| Route registration | `glossary-service/internal/api/server.go` | Done |
| Migration call in main.go | `glossary-service/cmd/glossary-service/main.go` | Done |
| Review fixes: spoiler init, rows.Err checks (2 locations) | `wiki_handler.go` | Done |
| Integration tests: 75 scenarios | `infra/test-wiki.sh` (new) | Done |

**9-phase workflow followed for P9-08a:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

P9-08b Wiki settings + public reader API — cross-service. book-service: wiki_settings JSONB column, PATCH support, projection + getBookByID include field. glossary-service: 2 public endpoints (list + get), visibility gate, spoiler filtering. 21 new integration tests (96 total).

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| Migration: wiki_settings JSONB on books | `book-service/internal/migrate/migrate.go` | Done |
| PATCH + GET + projection: wiki_settings field | `book-service/internal/api/server.go` | Done |
| Glossary book_client: parse wiki_settings from projection | `glossary-service/internal/api/book_client.go` | Done |
| Public endpoints: publicListWikiArticles + publicGetWikiArticle | `glossary-service/internal/api/wiki_handler.go` | Done |
| Public routes: /wiki/public, /wiki/public/{article_id} | `glossary-service/internal/api/server.go` | Done |
| Integration tests: 21 new (T47-T62), 96 total | `infra/test-wiki.sh` | Done |

**9-phase workflow followed for P9-08b:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

P9-08c Community suggestions — glossary-service. 1 table (wiki_suggestions), 3 endpoints (submit, list, accept/reject). Auth gates: any user can suggest, only owner can review. Accept applies diff + creates community revision. community_mode gate. 26 new integration tests (122 total).

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| Migration: wiki_suggestions table | `glossary-service/internal/migrate/migrate.go` | Done |
| Migration call in main.go | `glossary-service/cmd/glossary-service/main.go` | Done |
| Suggestion handlers: submit, list, review (accept/reject) | `glossary-service/internal/api/wiki_handler.go` | Done |
| Routes: /suggestions at book + article level | `glossary-service/internal/api/server.go` | Done |
| Integration tests: 26 new (T63-T80), 122 total | `infra/test-wiki.sh` | Done |

**9-phase workflow followed for P9-08c:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

P9-08d Wiki FE reader tab — frontend. WikiTab component (3-column: sidebar + article + ToC), API client, types, i18n 4 languages. Wired into BookDetailPage tab system.

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| Types: WikiArticleListItem, WikiArticleDetail, WikiInfoboxAttr, etc. | `features/wiki/types.ts` (new) | Done |
| API client: listArticles, getArticle, listRevisions | `features/wiki/api.ts` (new) | Done |
| WikiTab: sidebar (grouped by kind, search, filter), article view (ContentRenderer + infobox), ToC | `pages/book-tabs/WikiTab.tsx` (new) | Done |
| i18n: 4 languages (en, vi, ja, zh-TW) | `i18n/locales/*/wiki.json` (4 new) | Done |
| i18n registration | `i18n/index.ts` | Done |
| BookDetailPage: wire WikiTab, remove placeholder | `pages/BookDetailPage.tsx` | Done |

**9-phase workflow followed for P9-08d:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

P9-08e Wiki FE editor — WikiEditorPage with TiptapEditor, save/publish, infobox sidebar, revision history, suggestion review. Full wiki API client (create, patch, delete, generate, revisions, suggestions). Route + edit button in WikiTab.

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| Wiki API extensions: create, patch, delete, generate, getRevision, restore, suggestions | `features/wiki/api.ts` | Done |
| Types: WikiRevisionDetail, WikiSuggestionResp, WikiSuggestionListResp | `features/wiki/types.ts` | Done |
| WikiEditorPage: TiptapEditor, save, publish toggle, infobox, revision history, suggestions | `pages/WikiEditorPage.tsx` (new) | Done |
| Route: /books/:bookId/wiki/:articleId/edit under EditorLayout | `App.tsx` | Done |
| WikiTab: Edit button navigating to editor | `pages/book-tabs/WikiTab.tsx` | Done |

**9-phase workflow followed for P9-08e:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in previous session (2026-04-08, session 27):**

P9-02 User Profile — full-stack implementation. Backend: bio/languages fields, public profile endpoint, follow system (table + 4 endpoints), favorites system (table + 3 endpoints), catalog author filter, translator stats endpoint. Frontend: 6 components (ProfileHeader, StatsRow, AchievementBar, BooksTab, TranslationsTab, StubTab), ProfilePage, i18n 4 languages. Review: 4 fixes (active user filter on followers/following/counts, achievement dedup). Gateway: `/v1/users` proxy added.

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| BE-01: bio + languages migration + profile CRUD | `auth-service/migrate.go`, `handlers.go` | Done |
| BE-02: public profile endpoint | `auth-service/handlers.go`, `server.go` | Done |
| BE-03: follow system (table + 4 endpoints) | `auth-service/migrate.go`, `handlers.go`, `server.go` | Done |
| BE-04: favorites system (table + 3 endpoints) | `book-service/migrate.go`, `favorites.go` (new), `server.go` | Done |
| BE-05: catalog author filter | `catalog-service/server.go` | Done |
| BE-06: translator stats by user endpoint | `statistics-service/server.go` | Done |
| Gateway: /v1/users proxy | `gateway-setup.ts` | Done |
| FE-01: API layer | `features/profile/api.ts` (new) | Done |
| FE-02: ProfileHeader | `features/profile/ProfileHeader.tsx` (new) | Done |
| FE-03: StatsRow + AchievementBar | `features/profile/StatsRow.tsx`, `AchievementBar.tsx` (new) | Done |
| FE-04: BooksTab | `features/profile/BooksTab.tsx` (new) | Done |
| FE-05: TranslationsTab + StubTab | `features/profile/TranslationsTab.tsx`, `StubTab.tsx` (new) | Done |
| FE-06: ProfilePage + route + i18n | `pages/ProfilePage.tsx` (new), `App.tsx`, `i18n/index.ts`, 4 locale files | Done |
| Review fixes: active user filter, achievement dedup | `handlers.go`, `AchievementBar.tsx` | Done |

**9-phase workflow followed for P9-02:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in previous session (2026-04-08, session 26):**

P9-01 Leaderboard — full-stack implementation. Backend gaps (display name denormalization, translation counts, trending sort, auth-service internal endpoint) + full frontend (12 components, i18n 4 languages, route). Then review pass fixing 6 issues. Committed at `c190e03`.

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| A1: Denormalize display names — auth-service internal endpoint + statistics-service consumer + migration + API responses | `auth-service/handlers.go`, `auth-service/server.go`, `statistics-service/migrate.go`, `consumer.go`, `api/server.go`, `config.go`, `docker-compose.yml` | Done |
| A2: translation_count on book_stats | `migrate.go`, `consumer.go`, `api/server.go` | Done |
| A3: Trending sort option | `api/server.go` | Done |
| B1: API layer (types + fetch) | `features/leaderboard/api.ts` | Done |
| B3: Components (RankMedal, TrendArrow, PeriodSelector, FilterChips, Podium, RankingList, AuthorList, TranslatorList, QuickStatsCards) | 9 new files in `features/leaderboard/` | Done |
| B2: LeaderboardPage | `pages/LeaderboardPage.tsx` | Done |
| B4: i18n (4 languages) | `i18n/locales/{en,ja,vi,zh-TW}/leaderboard.json`, `i18n/index.ts` | Done |
| B5: Route update | `App.tsx` | Done |
| Review fixes: statsBook fallback fields, translation count reset, translator name refresh, i18n Show more, quick-stats state overwrite, dead AbortController removal | `api/server.go`, `consumer.go`, `AuthorList.tsx`, `TranslatorList.tsx`, `LeaderboardPage.tsx` | Done |

**9-phase workflow followed for P9-01:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in previous session (2026-04-08, session 25):**

P9-07 .docx/.epub import — full-stack implementation via Pandoc sidecar + async worker-infra. 4 commits.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| P9-07 core: Pandoc sidecar, import_jobs table, book-service endpoints, worker-infra ImportProcessor, HTML→Tiptap converter, frontend ImportDialog rewrite | `docker-compose.yml`, `migrate.go`, `import.go` (new), `server.go`, `import_processor.go` (new), `html_to_tiptap.go` (new), `config.go`, `main.go`, `ImportDialog.tsx`, `api.ts` | `286eede` |
| P9-07 improvements: image extraction from data: URIs → MinIO, WebSocket push via RabbitMQ | `image_extractor.go` (new), `import_processor.go`, `useImportEvents.ts` (new), `ImportDialog.tsx` | `6648fa4` |
| Fix: go.sum missing checksums after adding minio-go + amqp091-go | `go.sum` | `63d6219` |
| Fix: Dockerfile Go version bump 1.22→1.25 (minio-go requires it) | `Dockerfile` | `e5cdc32` |

Unit tests: 20 tests in `html_to_tiptap_test.go` (all pass). Integration test script: `infra/test-import.sh`.

**9-phase workflow followed for P9-07:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-07→08, session 24):**

45 commits across 4 phases + cleanup + bugs + plan audit.

| Phase / Work | Tasks | Commits |
| ------------ | ----- | ------- |
| Phase 8E — AI Provider + Media Gen | 11 | 10 |
| Phase 8F — Block Translation Pipeline | 16 | 11 |
| Phase 8G — Translation Review Mode | 8 | 3 |
| Phase 8H — Reading Analytics (GA4) | 14 | 7 |
| P3-R1 Cleanup — dead code, mock data, ModeProvider | 5 | 2 |
| Bug fixes — public reader 404, Vite chunks | 2 | 1 |
| TF-10 — Editor translate button | 1 | 1 |
| Reviews (8E, 8F, 8G, 8H, deferred) | 5 rounds | 5 |
| Plan audit — 135 done, Phase 9 added | - | 1 |
| Translation fix — Ollama content_extractor | 1 | 1 |
| Test fixes — image gen endpoint path | 1 | 1 |
| Session/plan docs | - | 2 |

Phase 8H — reading analytics, GA4-style (4 commits).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| TH-01+02: reading_progress + book_views tables, 4 endpoints | `migrate.go`, `analytics.go` (new), `server.go` | `48b08cd` |
| TH-04..07: useReadingTracker + useBookViewTracker hooks, page wiring | 5 FE files (2 new hooks) | `76cb8f9` |
| TH-08+09: TOC read status + book detail stats | `TOCSidebar.tsx`, `BookDetailPage.tsx`, `api.ts` | `fdf4d07` |
| TH-12: Integration tests (19/19 pass) + route/precision fixes | `test-reading-analytics.sh`, 3 BE files | `367494e` |

Phase 8G — translation review mode (2 commits).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| TG-01..08: BlockAlignedReview, ReviewPage, route, toolbar, entry points, SplitCompareView upgrade | 6 files (2 new) | `df72b04` |
| Plan: Phase 8G (8 tasks) | planning doc | `4b80c82` |

Phase 8F — block-level translation pipeline (10 commits).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| TF-01: Migration — translated_body_json JSONB + format column | `migrate.py`, `models.py` | `27ea2f2` |
| TF-02: Block classifier (translate/passthrough/caption_only + inline marks) | `block_classifier.py` (new) | `245b48e` |
| TF-03: Block-aware batch builder ([BLOCK N] markers, token budget) | `block_batcher.py` (new) | `3c7d63d` |
| TF-04+06: translate_chapter_blocks() pipeline + block translation prompts | `session_translator.py` | `16948ee` |
| TF-05: Chapter worker routes JSON→block pipeline, TEXT→legacy | `chapter_worker.py` | `de49e96` |
| TF-07: Sync translate-text endpoint block mode | `translate.py`, `models.py` | `5d880a8` |
| TF-08+12: ReaderPage renders JSONB translations + types update | `ReaderPage.tsx`, `api.ts` | `e42017c` |
| TF-09: TranslationViewer format badges + ContentRenderer | `TranslationViewer.tsx` | `ee4ba98` |
| TF-13+14: Unit tests (45 pass — classifier + batcher) | `test_block_classifier.py`, `test_block_batcher.py` | `9769d47` |
| TF-15+16: Integration tests (19 pass — e2e block translate + backward compat) | `test-translation-blocks.sh` | `40f2f98` |

Also done: Phase 8E (9 commits), 8E review fixes, translate-text Ollama fix.

Phase 8E — AI provider capabilities + media generation (9 commits).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| PE-01: BE — capability filter (`?capability=tts`) on listUserModels | `provider-registry-service/server.go` | `a310e83` |
| PE-02: FE — media capabilities in CapabilityFlags (tts, stt, image_gen, video_gen, embedding, moderation) + capability param on API client | `CapabilityFlags.tsx`, `settings/api.ts` | `a6fd64c` |
| PE-03: FE — filter TTSSettings to tts models, ImageBlockNode to image_gen models + capability_flags on UserModel type | `TTSSettings.tsx`, `ImageBlockNode.tsx`, `ai-models/api.ts` | `e00cf57` |
| PE-04: BE — add usage billing (purpose=image_generation) to existing image gen endpoint | `media.go` | `7098e28` |
| PE-05: BE — integration tests (27 scenarios: validation, auth, upload, versions, capability filter) | `test-image-gen.sh` (new) | `78b9858` |
| PE-06: FE — wire image gen in editor (already done — verified) | — | — |
| PE-07: BE — video-gen-service provider adapter (resolve creds, call Sora-compatible API, MinIO storage, billing) | `generate.py`, `main.py`, `requirements.txt`, `docker-compose.yml` | `9d2b239` |
| PE-08: BE — video gen integration tests (13 scenarios) | `test-video-gen.sh` (new) | `0f9736f` |
| PE-09: FE — wire VideoBlockNode to provider-registry video_gen model | `VideoBlockNode.tsx` | `fb6cb47` |
| PE-10: FE — AI Models section in ReadingTab (TTS/image/video model selectors, voice picker, image size) | `ReadingTab.tsx` | `5dcab71` |
| PE-11: BE — preconfig catalog (already done — tts-1, dall-e-3, gpt-image-1 in openai_models.json) | — | — |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-06, session 23):**

Phase 8D unified audio — AU-04..AU-07 + bug fixes.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| AU-04: Gateway audio route proxy test (5 assertions) + fix videoGenUrl compile error | `proxy-routing.spec.ts`, `health.spec.ts` | `d3ba6ff` |
| AU-05: Extended integration tests (12 new scenarios, 79/79 total) | `test-audio.sh` | `72a744d` |
| AU-06: audioBlock Tiptap extension — standalone audio node with upload, player, subtitle, slash menu, media guard | `AudioBlockNode.tsx` (new), `TiptapEditor.tsx`, `SlashMenu.tsx`, `MediaGuardExtension.ts`, `api.ts` | `a273190` |
| Fix: slash menu scroll positioning (fixed pos + max-height + flip) + sticky FormatToolbar | `SlashMenu.tsx`, `FormatToolbar.tsx` | `8d1462f` |
| AU-07: Audio attachment attrs on text blocks (paragraph, heading, blockquote, callout) | `AudioAttrsExtension.ts` (new), `TiptapEditor.tsx` | `fb072f8` |
| AU-08: AudioAttachBar — mini player widget decoration on text blocks with audio | `AudioAttachBarExtension.ts` (new), `TiptapEditor.tsx` | `2882ddf` |
| AU-09: AudioAttachActions — hover upload/record/generate buttons on text blocks | `AudioAttachActionsExtension.ts` (new), `TiptapEditor.tsx` | `77b6b99` |
| AU-10: FormatToolbar audio insert button (AI mode) — slash menu already in AU-06 | `FormatToolbar.tsx` | `4326b2a` |
| AU-11: AudioBlock reader display component + CSS (purple accent) | `AudioBlock.tsx` (new), `ContentRenderer.tsx`, `reader.css` | `6f4f400` |
| AU-12+13: Audio indicator on text blocks + CSS (hover play, mismatch, badges) | `ContentRenderer.tsx`, `reader.css` | `6def03b` |
| AU-14..17: Playback engine — TTSProvider, AudioFileEngine, BrowserTTSEngine, audio-utils | `useTTS.ts`, `AudioFileEngine.ts`, `BrowserTTSEngine.ts`, `audio-utils.ts` (all new) | `8512b0b` |
| AU-18..21: Player UI — TTSBar, block scroll sync, keyboard shortcuts, ReaderPage wiring | `TTSBar.tsx`, `useBlockScroll.ts`, `useTTSShortcuts.ts`, `ReaderPage.tsx` | `c64b986` |
| AU-22..24: Settings + management — TTSSettings, AudioOverview, AudioGenerationCard | `TTSSettings.tsx`, `AudioOverview.tsx`, `AudioGenerationCard.tsx`, `TTSBar.tsx`, `ReaderPage.tsx` | `dd130b5` |
| Wire AI TTS generation to model settings (generate buttons call real AU-03 endpoint) | `api.ts`, `TTSSettings.tsx`, `AudioOverview.tsx`, `AudioAttachActionsExtension.ts` | `5a8cf9c` |
| Plan: Phase 8E — AI Provider Capabilities + Media Generation (11 tasks: PE-01..PE-11) | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | pending |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-06, session 22):**

Phase 8D unified audio — AU-01..AU-03 backend implementation.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| AU-01: chapter_audio_segments table + CRUD (3 endpoints) | `migrate.go`, `audio.go` (new), `server.go` | `770b123` |
| AU-01: integration tests (41 scenarios, all pass) | `infra/test-audio.sh` (new) | `2c24bbe` |
| AU-02: block audio upload endpoint + tests (59 total, all pass) | `audio.go`, `server.go`, `test-audio.sh` | `8644c16` |
| AU-03: AI TTS generation endpoint + tests (67 total, all pass) | `audio.go`, `server.go`, `config.go`, `docker-compose.yml`, `test-audio.sh` | `397e199` |

**9-phase workflow followed for AU-01..AU-03:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-05, session 21):**

Phase 8 design + planning + RD-00. Design review of reader architecture, 3 HTML design drafts created, 30-task breakdown across 7 sub-phases (8A-8G), design decisions finalized.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Design: reader-v2-part1 (block renderer + chrome) | `design-drafts/screen-reader-v2-part1-renderer.html` (new) | pending |
| Design: reader-v2-part2 (TTS/audio player) | `design-drafts/screen-reader-v2-part2-audio-tts.html` (new) | pending |
| Design: reader-v2-part3 (review modes) | `design-drafts/screen-reader-v2-part3-review-modes.html` (new) | pending |
| Planning: Phase 8 breakdown (30 tasks, 7 sub-phases) | `docs/03_planning/99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | pending |
| RD-00: Install 5 missing editor extensions (link, underline, highlight, sub, sup) | `TiptapEditor.tsx`, `FormatToolbar.tsx`, `package.json` | `544c047` |
| RD-01: InlineRenderer — text marks display (9 marks + hardBreak) | `InlineRenderer.tsx` (new) | `bdfd177` |
| RD-02: Text block display components (paragraph, heading, blockquote, list, hr) | `blocks/` (5 new files) | `1be9279` |
| RD-03: Media block display components (image, video, code, callout) | `blocks/` (4 new files) | `2d961f4` |
| RD-04: ContentRenderer orchestrator (block→component mapping) | `ContentRenderer.tsx` (new) | `cbc1113` |
| RD-05: Reader CSS — full + compact mode styles | `reader.css` (new) | `83d4227` |
| RD-06: ReaderPage rewrite — ContentRenderer replaces TiptapEditor | `ReaderPage.tsx` | `24d4b25` |
| RD-07: Chapter header + end marker — metadata, reading time, CJK | `ReaderPage.tsx`, `reader.css` | `4a06029` |
| RD-08: Extract TOCSidebar from ReaderPage | `TOCSidebar.tsx` (new) | `e62f25c` |
| RD-09: Language selector in TOC — switch reading language | `TOCSidebar.tsx`, `ReaderPage.tsx`, `reader.css` | `4f08f20` |
| RD-10: Top bar edit button — owner-only visibility | `ReaderPage.tsx` | `93b12b6` |
| RD-11: Keyboard shortcuts (arrows, T, Escape, Home/End) | `ReaderPage.tsx` | `6d35e16` |
| RD-12: Integration cleanup — remove old .tiptap-reader CSS, mark tasks done | `index.css`, planning doc | `1710bc4` |
| Review fixes: extractText shared util, useMemo, lang loading, Escape | `ReaderPage.tsx`, `tiptap-utils.ts` | `3ec3e55` |
| Smoke test fix: Home/End scroll targets reader container + test account | `ReaderPage.tsx`, `CLAUDE.md` | `ad1873e` |
| RD-13: Reader theme wiring — apply --reader-* CSS vars | `ReaderPage.tsx` | `a1b8d5c` |
| RD-14: ThemeCustomizer slide-over (presets, fonts, sliders) | `ThemeCustomizer.tsx` (new), `ReaderPage.tsx` | `240830f` |
| RD-15: Reading mode toggles (block indices, placeholders) | `ThemeCustomizer.tsx`, `ReaderPage.tsx` | `7dc3273` |
| 8B review fixes: Escape closes theme, mutual exclusion, top bar readability | `ReaderPage.tsx` | `2691880` |
| RD-16+17: RevisionHistory uses ContentRenderer, delete ChapterReadView | `RevisionHistory.tsx`, `ChapterReadView.tsx` (deleted) | `52556cb` |
| Bug fix: sharing status (SHARING_INTERNAL_URL), multi-file upload, fake read marks | `docker-compose.yml`, `ImportDialog.tsx`, `TOCSidebar.tsx`, planning | `a94a25b` |
| Bug fix: remove circular dependency book↔sharing | `docker-compose.yml` | `39d591a` |
| Design: Part 4 unified audio system (audio blocks + playback) | `screen-reader-v2-part4-audio-blocks.html` (new) | `01e021b` |
| Plan: Phase 8D unified audio — 24 tasks replacing old 8D+8E | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | `f667955` |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-05, session 20):**

E2E browser review fixes (8 issues) + P3-KE Kind Editor Enhancement COMPLETE (13 tasks: 6 BE + 7 FE). 17 commits, 67/67 BE integration tests.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| B1: Fix raw \u2026 in trash search placeholder | `TrashPage.tsx` | `b2f60d4` |
| B2: Genre tags on public book detail page | `PublicBookDetailPage.tsx` | `b2f60d4` |
| B3: "Back to Workspace" link on 404 page | `PlaceholderPage.tsx` | `b2f60d4` |
| B4: Recharts negative dimension warning | `DailyChart.tsx` | `b2f60d4` |
| U1: Display Name field on registration | `RegisterPage.tsx` | `b2f60d4` |
| U3: Lazy-load BookDetailPage tabs (mount on first visit) | `BookDetailPage.tsx` | `b2f60d4` |
| U4: Genre tags on workspace book cards | `BooksPage.tsx` | `b2f60d4` |
| Critical fix: null-guard genre_tags (11 access sites, 5 files) | `EntityEditorModal.tsx`, `GenreGroupsPanel.tsx`, `GlossaryTab.tsx`, `KindEditor.tsx`, `SettingsTab.tsx` | `b2f60d4` |
| P3-KE plan added to 99A (13 tasks, BE-first strategy) | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | `b2f60d4` |
| BE-KE-01: Kind + attr description field — expose existing columns | `domain/kinds.go`, `kinds_handler.go`, `kinds_crud.go` | `b2f60d4`, `67879aa` |
| BE-KE-02: Entity count per kind — correlated subquery in listKinds | `domain/kinds.go`, `kinds_handler.go` | `731ab9d` |
| BE-KE-03: Attribute is_active toggle — migration + CRUD | `migrate.go`, `domain/kinds.go`, `kinds_handler.go`, `kinds_crud.go` | `2a76891` |
| BE-KE-04: Attribute inline edit validation — field_type allowlist, empty name rejection | `kinds_crud.go` | `3da6932` |
| BE-KE-05: Attr description — already covered by BE-KE-01 | — | — |
| BE-KE-06: Sort order reorder endpoints (kinds + attrs) | `server.go`, `kinds_crud.go` | `96fd331` |
| Review fix: patchKind re-fetch missing entity_count subquery | `kinds_crud.go` | `88da9b4` |
| Integration test suite: 67 scenarios, all pass | `infra/test-kind-editor-enhance.sh` | `67879aa`..`96fd331` |
| FE-KE-01: Kind metadata panel — description textarea + entity count | `KindEditor.tsx`, `glossary/types.ts` | `eeafec7` |
| FE-KE-02: Attribute inline edit form (pencil icon, name/type/required/desc/genre) | `KindEditor.tsx` | `6624e70` |
| FE-KE-03: Attribute toggle on/off (CSS switch, is_active PATCH) | `KindEditor.tsx` | `b28925d` |
| FE-KE-04: Drag-to-reorder kinds (native HTML DnD, GripVertical, optimistic UI) | `KindEditor.tsx`, `glossary/api.ts` | `63d6b04` |
| FE-KE-05: Drag-to-reorder attributes | `KindEditor.tsx` | `cb41f1e` |
| FE-KE-06: Genre-colored dots on tag pills (genreColorMap from genre_groups) | `KindEditor.tsx`, `GlossaryTab.tsx` | `88cfadf` |
| FE-KE-07: Modified indicator + Revert to default (seedDefaults.ts, confirm dialog) | `KindEditor.tsx`, `seedDefaults.ts` (new) | `c204d1a` |
| FE-KE review: parallel revert + genre-colored kind tags | `KindEditor.tsx` | `042f4e1` |

| INF-01: Service-to-service auth — requireInternalToken middleware + internalGet | 11 files across 6 services, `docker-compose.yml` | `03644b3` |
| INF-02: Internal HTTP client — 10s timeout + 1 retry, zero http.Get remaining | `catalog/server.go`, `sharing/server.go`, `book/server.go`, `book/media.go` | `e02a1c9` |
| INF-03: Structured JSON logging — 77 log.Printf→slog across 8 Go services | 15 files across 8 services | `af1679d`, `da818cd` |
| INF-04: Health check deep mode — /health (ping) + /health/ready (SELECT 1) | 7 service server.go files, `test-infra-health.sh` (new) | `b670f7c` |
| Attr Editor: design draft (2 variants — system + user attr, AI sections) | `screen-attr-editor-modal.html` (new), `screen-glossary-management.html` | `cfd1f38` |
| Attr Editor BE: auto_fill_prompt + translation_hint columns (79/79 pass) | `migrate.go`, `domain/kinds.go`, `kinds_handler.go`, `kinds_crud.go` | `b59ef13` |
| Attr Editor FE: AttrEditorModal — floating modal replaces inline form | `AttrEditorModal.tsx` (new), `KindEditor.tsx`, `glossary/types.ts` | `8463b80` |
| Attr Editor FE: create mode — "Add Attribute" opens modal too | `AttrEditorModal.tsx`, `KindEditor.tsx`, `glossary/api.ts` | `6c82a86` |
| P4-04 plan: detailed 9-task breakdown (2 BE + 7 FE) | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | `043c990` |
| BE-TH-01+02: user_preferences JSONB table + gateway proxy (14/14 pass) | auth-service, gateway | `bc4e67f` |
| FE-TH-01: 4 app theme presets via CSS variable overrides | `index.css` | `775035b` |
| FE-TH-02: unified ThemeProvider replaces ReaderThemeProvider | `ThemeProvider.tsx` (new), `App.tsx` | `c9bf5eb` |
| FE-TH-03: theme toggle in sidebar (cycles dark/light/sepia/oled) | `Sidebar.tsx` | `b751192` |
| FE-TH-06: Settings ReadingTab rewrite (app theme + reader theme + typography) | `ReadingTab.tsx` | `b2efad4` |
| FE-TH-07: CSS audit — hardcoded colors → theme tokens | `SourceView.tsx`, `DailyChart.tsx` | `9eb24f0` |
| Custom theme editor: color pickers, paragraph spacing, save/load custom presets | `ThemeProvider.tsx`, `ReadingTab.tsx` | `5a7367d` |
| Future theme improvements plan: 22 deferred items across 5 categories | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | `54f1de3` |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-04, session 19):**

P3-08 Genre Groups — Full backend + frontend implementation (tag-based, no activation matrix). 26 commits.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Design: replaced activation matrix with tag-based genre scoping | `design-drafts/screen-glossary-management.html`, `design-drafts/screen-genre-groups.html` (new) | this session |
| Planning: rewrote P3-08a/b/c → BE-G1..G5 + FE-G1..G7 (12 tasks, backend-first) | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | this session |
| BE-G1: `genre_groups` table + CRUD (4 endpoints, 24/24 tests) | glossary-service: `migrate.go`, `genres_handler.go`, `genres_crud.go`, `domain/genres.go`, `server.go`, `main.go` | `ada8dcf` |
| BE-G1 review: UUID validation, cross-book re-fetch, length limits | `genres_crud.go`, `genres_handler.go` | `d3d7e6d` |
| BE-G2: `attribute_definitions.genre_tags` column + CRUD (12/12 tests) | `migrate.go`, `kinds_crud.go`, `kinds_handler.go`, `domain/kinds.go` | `981a9ea` |
| BE-G2 review: patchAttrDef re-fetch add kind_id + error check | `kinds_crud.go` | `7f93c5a` |
| BE-G3: `books.genre_tags` column + CRUD (11/11 tests) | book-service `migrate.go`, `server.go` | `46f1df2` |
| BE-G4: Catalog genre filter + projection (12/12 tests) | book-service `server.go`, catalog-service `server.go` | `853a1b0` |
| BE-G4 review: nil guard + pre-existing title scan bug fix | book-service `server.go` | `152f19a`, `e01e6d6` |
| BE-G5: Integration test script (65 scenarios, all pass) | `infra/test-genre-groups.sh` (new) | `401ab60` |
| H2+H3 fix: uuidv7 for genre_groups, skip hidden kinds in attr query | glossary-service `migrate.go`, `kinds_handler.go` | `7e8340c` |
| FE-G1: Types + API client (GenreGroup, genre_tags on all types) | `glossary/types.ts`, `glossary/api.ts`, `books/api.ts`, `BrowsePage.tsx` | `08d70e2` |
| FE-G2: Genre Groups tab + CRUD + detail panel | `GlossaryTab.tsx`, `GenreGroupsPanel.tsx` (new), `GenreFormModal.tsx` (new) | `213e48a` |
| FE-G2 review: dead imports, escape guard, auto-select, rename cascade | `GenreGroupsPanel.tsx`, `GenreFormModal.tsx` | `36c5ab7`, `fe9ee3d` |
| FE-G3: Kind Editor genre_tags row | `KindEditor.tsx` | `c3e662b`, `b7a3245` |
| FE-G4: Attr genre_tags pills + create form | `KindEditor.tsx` | `7e41867`, `b11bc15` |
| FE-G5: Entity Editor genre filter + kind dropdown filter | `BookDetailPage.tsx`, `GlossaryTab.tsx`, `EntityEditorModal.tsx` | `085cb61`, `c900c41` |
| FE-G6: Book SettingsTab (P3-21 + genre selector, cover, visibility) | `SettingsTab.tsx` (new), `BookDetailPage.tsx` | `1596013`, `4fbb672` |
| FE-G7: Browse genre filter chips + book card genre pills (multi-select) | `BrowsePage.tsx`, `FilterBar.tsx`, `BookCard.tsx` | `36299a4`, `64799f8` |

**9-phase workflow followed:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-03, session 18):**

Phase 6 Chat Enhancement — Backend implementation + integration tests (28/28 pass).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Phase 6 planning: competitive analysis, 16 tasks (C6-01..C6-16), BE-first strategy | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | this session |
| Design draft: enhanced chat GUI (thinking block, session settings, format pills, branch nav) | `design-drafts/screen-chat-enhanced.html` (new) | this session |
| BE-C6-01: `generation_params` JSONB column + `is_pinned` BOOLEAN on chat_sessions | `migrate.py`, `models.py`, `sessions.py` | this session |
| BE-C6-02: stream_service reads generation_params → passes temperature/top_p/max_tokens to LLM | `stream_service.py` | this session |
| BE-C6-03: system_prompt injection — prepend session system_prompt as system message | `stream_service.py` | this session |
| BE-C6-04: thinking mode — parse `reasoning_content`, emit `reasoning-delta` SSE events | `stream_service.py`, `messages.py`, `models.py` | this session |
| BE-C6-05: message search endpoint — FTS with `ts_headline` snippets | `sessions.py`, `models.py`, `migrate.py` | this session |
| BE-C6-06: session pin — `is_pinned` field, pinned-first sort in list | `sessions.py`, `models.py`, `migrate.py` | this session |
| BE-C6-07: auto-title generation — async LLM call after first exchange, reasoning fallback | `stream_service.py` | this session |
| Critical fix: bypass LiteLLM for streaming (strips `reasoning_content`), use OpenAI SDK directly | `stream_service.py` | this session |
| Route fix: move `/search` before `/{session_id}` to prevent path conflict | `sessions.py` | this session |
| Test setup: LM Studio provider + qwen3-1.7b model insertion script | `infra/setup-chat-test-model.sh` (new) | this session |
| Integration test: 28 scenarios (T20-T33), all pass, covers CRUD + streaming + thinking + search | `infra/test-chat-enhanced.sh` (new) | this session |
| FE-C6-01: SessionSettingsPanel slide-over (model, system prompt, gen params, info) | `SessionSettingsPanel.tsx` (new), `ChatHeader.tsx`, `ChatWindow.tsx`, `ChatPage.tsx` | `d16f54b` |
| FE-C6-02: Thinking mode UI (Think/Fast toggle, ThinkingBlock, reasoning-delta parsing) | `ThinkingBlock.tsx` (new), `ChatInputBar.tsx`, `AssistantMessage.tsx`, `MessageBubble.tsx`, `MessageList.tsx`, `useChatMessages.ts` | `d16f54b` |
| FE-C6-03: Token display per-message (thinking/input/output counts, Fast/Think badge) | `AssistantMessage.tsx` | `d16f54b` |
| FE-C6-04: Sidebar search + temporal groups (Pinned/Today/Yesterday/Week/Older) + pin/unpin | `SessionSidebar.tsx`, `useSessions.ts`, `ChatPage.tsx` | `7a1c2a6` |
| FE-C6-05: Enhanced NewChatDialog (model search, presets, badges, system prompt) | `NewChatDialog.tsx`, `ChatPage.tsx` | `8b3fdec` |
| FE-C6-06: Keyboard shortcuts (Ctrl+N new, Esc stop, Ctrl+Shift+Enter think) | `ChatPage.tsx`, `ChatInputBar.tsx` | `502abbe` |
| FE-C6-07: FTS message search in sidebar (debounced, snippet highlights) | `api.ts`, `SessionSidebar.tsx` | `502abbe` |
| Types updated: GenerationParams, is_pinned, thinking field, SearchResult | `types.ts` | `d16f54b` |
| Code review: 4 critical + 5 high fixes (tautology, client leak, validation, XSS, timers) | 7 files | `d87931c` |
| C6-12: Format pills (Auto/Concise/Detailed/Bullets/Table) | `ChatInputBar.tsx` | `7f06c22` |
| C6-14: Message actions dropdown (Copy Markdown, Send to Editor) | `AssistantMessage.tsx` | `7f06c22` |
| C6-16: Prompt template library ("/" trigger, 8 templates, arrow key nav) | `PromptTemplates.tsx` (new), `ChatInputBar.tsx` | `7f06c22` |
| M1: gen_params PATCH clear to null + "Reset to Defaults" button | `sessions.py`, `SessionSettingsPanel.tsx` | `7f06c22` |
| M3: NewChatDialog auto-focus + error toast | `NewChatDialog.tsx` | `7f06c22` |
| M4: ChatPage loading spinner on session switch | `ChatPage.tsx` | `7f06c22` |
| Fix: Send to Editor event name mismatch (paste-to-editor → loreweave:paste-to-editor) | `AssistantMessage.tsx` | `c2d1840` |
| Fix: Context resolution warning toast | `ChatPage.tsx` | `c2d1840` |
| FE-C6-08 BE: branch_id column, edit-as-branch (UPDATE not DELETE), branches endpoint | `migrate.py`, `messages.py`, `stream_service.py` | `7a74be9` |
| FE-C6-08 FE: BranchNavigator component, branch switching, listBranches API | `BranchNavigator.tsx` (new), `MessageBubble.tsx`, `MessageList.tsx`, `ChatWindow.tsx`, `api.ts`, `types.ts` | `7a74be9` |
| Branching review: 3 critical + 2 high (refreshBranch, listMessages branch_id, fallback) | 6 files | `5ad82af` |

**9-phase workflow followed:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-03, session 17):**

MIG-03: Usage Monitor page — full-stack build from draft design.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| BE: `purpose` column added to `usage_logs` table | `migrate.go` | this session |
| BE: `recordInvocation` accepts `purpose` field | `server.go` | this session |
| BE: `listUsageLogs` — server-side filters (provider_kind, request_status, purpose, from, to) | `server.go` | this session |
| BE: `getUsageSummary` — error_rate, by_provider, by_purpose, daily breakdowns, last_30d/90d | `server.go` | this session |
| BE: test updated for `purpose` column in scanUsageLogRow | `server_test.go` | this session |
| FE: `features/usage/types.ts` — UsageLog, UsageSummary, AccountBalance, filter types | new file | this session |
| FE: `features/usage/api.ts` — usageApi (listLogs, getLogDetail, getSummary, getBalance) | new file | this session |
| FE: `features/usage/StatCards.tsx` — 4 stat cards (tokens, cost, calls, error rate) | new file | this session |
| FE: `features/usage/BreakdownPanels.tsx` — Tokens by Provider + Purpose bar charts | new file | this session |
| FE: `features/usage/DailyChart.tsx` — Recharts stacked bar chart (input/output tokens) | new file | this session |
| FE: `features/usage/RequestLogTable.tsx` — filterable table with expandable rows | new file | this session |
| FE: `features/usage/ExpandedRow.tsx` — lazy-fetch detail, Input/Output/Raw JSON tabs | new file | this session |
| FE: `pages/UsagePage.tsx` — page shell with period selector, CSV export | new file | this session |
| FE: App.tsx — replaced /usage placeholder with UsagePage, removed /usage/:logId | `App.tsx` | this session |
| FE: recharts dependency added | `package.json` | this session |
| M4-01 BE: previous period query in `getUsageSummary` — prev_request_count, prev_total_tokens, prev_total_cost_usd, prev_error_rate | `server.go` | this session |
| M4-02 FE: trend indicators on StatCards — ↑↓ % vs prev period, sentiment coloring (green/red/neutral) | `StatCards.tsx`, `types.ts` | this session |
| MIG-05: Settings page — 5 tabs (Account, Providers, Translation, Reading, Language) | 9 new files, `App.tsx`, `translation/api.ts` | this session |
| MIG-06 BE: catalog-service — sort (recent/chapters/alpha) + language filter, over-fetch+paginate | `catalog-service/server.go` | this session |
| MIG-06 FE: Browse page — hero, search (debounced), language chips, genre chips (disabled), sort, 4-col grid, BookCard, pagination | 3 new files, `App.tsx` | this session |
| P3-08c: Genre tag + browse filter task added to planning doc | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | this session |
| Provider enhancement BE: embed preconfig JSON (26 OpenAI + 10 Anthropic), replace hardcoded 2-3 models | `adapters.go`, 2 JSON files | this session |
| Provider enhancement FE: AddModelModal (autocomplete, capability types, tags, notes) + EditModelModal (toggles, verify, delete) | 2 new files, `ProvidersTab.tsx`, `api.ts` | this session |
| Model management fix: complete data flow (API sends all fields), shared TagEditor + CapabilityFlags, delete icon on rows | 6 files | this session |
| Notes field full-stack: BE migration + create/patch/read, FE send on create + load on edit | 5 files | this session |
| TranslationTab fix: model picker dropdown grouped by provider, fix save error (missing model_source/ref) | `TranslationTab.tsx` | this session |
| Email verification flow: request + confirm in AccountTab | `api.ts`, `AccountTab.tsx` | this session |
| Sidebar display name: updateUser() in AuthProvider, instant update after profile save | `auth.tsx`, `AccountTab.tsx` | this session |
| Chat layout fix: new ChatLayout (Sidebar + full-bleed), move from FullBleedLayout | `ChatLayout.tsx`, `App.tsx` | this session |
| Chat model display: resolve model_ref UUID → display name in header + sidebar | 4 chat files | this session |
| Unicode fix: replace literal \u00B7 in JSX text with &middot; | 2 chat files | this session |
| Context picker: floating modal instead of inline absolute (no layout shift) | `ContextBar.tsx`, `ContextPicker.tsx` | this session |
| Custom providers: drop CHECK constraint, add api_standard column, accept any provider_kind | BE 5 files, FE 2 files | this session |
| LiteLLM auth fix: dummy API key for local providers (LM Studio/Ollama) | `stream_service.py` | this session |
| Planning: P3-08c genre filter task, P4-04 Reading/Theme unification plan (6 sub-tasks) | 2 planning docs | this session |
| Design draft: model editor modal (Add/Edit) + preconfig catalogs JSON | 3 new files | this session |

**9-phase workflow followed:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-02, session 16):**

Phase 3.5 media blocks: E4-06 completed.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Phase 3.5 plan update: E4 expanded to 8 tasks, resize handles + alt text added to E4-01, design decisions documented | `docs/03_planning/99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | this session |
| E4-06: Code block — CodeBlockLowlight + ReactNodeViewRenderer, language selector (13 langs), copy button, hljs theme, slash menu + toolbar integration | `components/editor/CodeBlockNode.tsx` (new), `TiptapEditor.tsx`, `SlashMenu.tsx`, `FormatToolbar.tsx`, `index.css` | this session |
| E4-01: Image block — atom node with ReactNodeViewRenderer, resize handles (pointer events, 10-100%), editable caption, collapsible alt text field (WCAG), selection ring, empty state placeholder, extractText returns alt | `components/editor/ImageBlockNode.tsx` (new), `TiptapEditor.tsx` | this session |
| E4-02: Image upload — BE: MinIO upload endpoint on book-service (auth, type/size validation, UUID key), FE: drag-drop/paste/file-picker with XHR progress, error handling | `book-service/internal/api/media.go` (new), `server.go`, `config.go`, `docker-compose.yml`, `ImageBlockNode.tsx`, `features/books/api.ts` | this session |
| E4-03: AI prompt field — reusable MediaPrompt component (collapsible, textarea auto-grow, saved/empty badge, copy, re-generate placeholder), ai_prompt attr on imageBlock | `components/editor/MediaPrompt.tsx` (new), `ImageBlockNode.tsx` | this session |
| E4-04: Classic mode guards — MediaGuardExtension (backspace/delete/selection protection), compact locked placeholders for image+code blocks, mode storage sync | `components/editor/MediaGuardExtension.ts` (new), `ImageBlockNode.tsx`, `CodeBlockNode.tsx`, `TiptapEditor.tsx` | this session |
| E4-05: Video block — player placeholder, upload (MP4/WebM, 100 MB), caption, AI prompt (coming soon), Classic mode placeholder, BE video MIME support | `components/editor/VideoBlockNode.tsx` (new), `TiptapEditor.tsx`, `book-service/media.go` | this session |
| E4-07: Slash menu + toolbar — Image/Video in slash menu (AI mode), Image/Video insert buttons in FormatToolbar (AI mode) | `SlashMenu.tsx`, `FormatToolbar.tsx` | this session |
| E4-08: Source view — read-only Block JSON viewer with syntax highlighting, Copy JSON, toggle via editor handle, _text snapshots stripped | `components/editor/SourceView.tsx` (new), `TiptapEditor.tsx` | this session |
| E4-review: Cross-cutting fixes — unified upload context, bucket race fix, streaming upload, SourceView colon fix | 4 files | this session |
| E5-01: Media version tracking BE — block_media_versions table, CRUD endpoints (list/create/delete), auto-version on upload, versioned MinIO paths, public-read bucket policy | `migrate.go`, `media.go`, `server.go` | this session |
| E5-02: Version history UI — split-panel layout, side-by-side image comparison, version timeline (dots, tags, timestamps), LCS-based prompt diff, restore/download/delete actions, History button on image blocks | `VersionHistoryPanel.tsx`, `VersionTimeline.tsx`, `PromptDiff.tsx` (new), `ImageBlockNode.tsx`, `features/books/api.ts` | this session |
| Video generation service skeleton — Python/FastAPI, health/generate/models endpoints, returns "not_implemented", gateway proxy, FE wired with Generate button | `services/video-gen-service/` (new, 6 files), `gateway-setup.ts`, `main.ts`, `docker-compose.yml`, `features/video-gen/api.ts` (new), `VideoBlockNode.tsx` | this session |
| M1: Version history button in Classic mode (image + video placeholders) | `ImageBlockNode.tsx`, `VideoBlockNode.tsx` | this session |
| M2+M3: Guard toast notification + paste protection in Classic mode | `MediaGuardExtension.ts` | this session |
| M4: Drag handles for block reordering (tiptap-extension-global-drag-handle) | `TiptapEditor.tsx`, `index.css` | this session |
| M5: Copy filename button on Classic placeholders | `ImageBlockNode.tsx`, `VideoBlockNode.tsx` | this session |
| M6: Unsaved-changes dialog on AI → Classic mode switch | `ChapterEditorPage.tsx` | this session |
| E5-03: AI image generation — BE endpoint (provider-registry → AI provider → MinIO), version record, FE generateImage() API client | `media.go`, `server.go`, `config.go`, `docker-compose.yml`, `features/books/api.ts` | this session |
| E5-04: Re-generate from prompt — wired Re-generate button, fetch user models, call generateImage, loading/error states, spinner in MediaPrompt | `ImageBlockNode.tsx`, `MediaPrompt.tsx` | this session |

**9-phase workflow followed for E4-06:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-02, session 15):**

Phase 3 feature screens: 4 tasks completed.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| P3-18: Chat Page v2 — full-bleed layout, custom SSE streaming, session CRUD | `features/chat-v2/` (17 new files), `pages/ChatPageV2.tsx`, `App.tsx`, `AppNav.tsx`, `tailwind.config.cjs` | `911c249` |
| P3-20: Sharing Tab — visibility selector, unlisted link, token rotation | `features/sharing/SharingTab.tsx`, `BookDetailPageV2.tsx` | `bf83808` |
| P3-21: Book Settings Tab — metadata editing, cover image management | `features/books/SettingsTab.tsx`, `features/books/api.ts`, `BookDetailPageV2.tsx` | `b8b96b6` |
| P3-22: Universal Recycle Bin — tabbed trash, bulk actions, expiry badges | `features/trash/` (4 new files), `pages/RecycleBinPageV2.tsx`, `design-drafts/screen-recycle-bin.html` | `08e294d` |
| P3-22a+b: Recycle Bin — Chapters + Chat Sessions tabs, unified restoreItem/purgeItem | `features/trash/`, `features/books/api.ts` | `59ef220` |
| P3-19: Chat Context Integration — context picker, pills, glossary filters, format+resolve | `features/chat-v2/context/` (6 new files), `ChatInputBar`, `ChatWindow`, `MessageBubble`, `ChatPageV2`, `design-drafts/screen-chat-context.html` | `78107a1` |
| BE-S1: Fix patchBook null clearing (COALESCE bug) + getBookByID *string scan | `book-service/server.go` | `bea76f9`, `eeee14c` |
| BE-C1: Chat context field — optional `context` in SendMessageRequest, injected as system msg | `chat-service/models.py`, `stream_service.py`, `messages.py` | `bea76f9` |
| BE-S2: Gateway book proxy selfHandleResponse for multipart | `api-gateway-bff/gateway-setup.ts` | `bea76f9` |
| Integration test: chat-service (27 scenarios, all pass) | `infra/test-chat.sh` | `911c249`, `eeee14c` |
| Integration test: sharing-service (19 scenarios, all pass) | `infra/test-sharing.sh` | `bf83808` |
| Integration test: book-settings (23 scenarios, all pass) | `infra/test-book-settings.sh` | `eeee14c` |
| Docker: rebuild translation-worker (PG18 volume fix + stale image) | — | — |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-03-29, session 1):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Fix book visibility always showing "private" on BookDetailPageV2 | `frontend/src/pages/v2-drafts/BookDetailPageV2.tsx` | `2f47c89` |
| Unified chapter editor: tabbed workspace (Draft / Published), dirty tracking | `frontend/src/pages/v2-drafts/ChapterEditorPageV2.tsx` | `2f47c89` |
| Redesign book/chapter browsing UI: cover images, view modes | Multiple v2 pages | `b32f415` |
| Build ChunkEditor system: paragraph-level editing + AI context copy | `frontend/src/components/chunk-editor/` (3 new files) | `3cb8e4c` |
| Chunk selection: visible numbers, range select (shift+click), bulk copy | Same chunk-editor files | `fd4a5ea` |

**What was done in this session (2026-03-29, session 2):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Chat service backend skeleton | `services/chat-service/` (new service, 15 files) | `23bad63` |
| DB migration (3 tables: chat_sessions, chat_messages, chat_outputs) | `app/db/migrate.py` | `23bad63` |
| Sessions CRUD, messages streaming (LiteLLM), outputs CRUD | `app/routers/` (3 routers) | `23bad63` |
| Stream service: LiteLLM + AI SDK data stream protocol v1 | `app/services/stream_service.py` | `23bad63` |
| Provider-registry: internal credentials endpoint | `services/provider-registry-service/internal/api/server.go` | `23bad63` |
| docker-compose: add chat-service + loreweave_chat DB + INTERNAL_SERVICE_TOKEN | `infra/docker-compose.yml` | `23bad63` |
| Gateway: proxy /v1/chat to chat-service | `services/api-gateway-bff/src/gateway-setup.ts`, `main.ts` | `23bad63` |
| Frontend: full chat feature (ChatPage, SessionSidebar, ChatWindow, all components) | `frontend/src/features/chat/`, `frontend/src/pages/ChatPage.tsx`, `App.tsx` | `23bad63` |
| Install @ai-sdk/react, ai, react-markdown, rehype-highlight, react-textarea-autosize, sonner | `frontend/package.json` | `23bad63` |

**What was done in this session (2026-03-29, session 3):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Run all M01-M04 unit tests across all services | — | — |
| Fix gateway tests: add missing service URLs + WsAdapter | `services/api-gateway-bff/test/health.spec.ts`, `proxy-routing.spec.ts` | `bf17136` |
| Fix frontend tests: install missing @testing-library/dom peer dep | `frontend/package.json` | `bf17136` |
| Add glossary + chat proxy route test coverage | `services/api-gateway-bff/test/proxy-routing.spec.ts` | `bf17136` |

**What was done in this session (2026-03-29, session 4):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Run M05 glossary-service tests — all 22 pass, 16 DB tests skip (expected) | — | — |
| Wire OutputCards into assistant MessageBubble (code block extraction) | `MessageBubble.tsx`, new `utils/extractCodeBlocks.ts` | `b7dcc4c` |
| Add session export button to ChatHeader | `ChatHeader.tsx` | `b7dcc4c` |
| Add "Paste to Editor" integration via custom DOM event | New `utils/pasteToEditor.ts`, `OutputCard.tsx`, `ChapterEditorPageV2.tsx` | `b7dcc4c` |
| MinIO storage client skeleton (upload, presigned URL, delete) | New `app/storage/minio_client.py`, `__init__.py` | `b7dcc4c` |
| Binary download via MinIO presigned URLs | `app/routers/outputs.py` | `b7dcc4c` |
| MinIO bucket auto-creation on startup | `app/main.py` | `b7dcc4c` |

**What was done in this session (2026-03-29, session 5):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Chat-service full unit test suite (68 tests) | `tests/` (7 new files), `pytest.ini`, `requirements-test.txt` | `6847a85` |
| Fix `ensure_bucket` bug — `run_in_executor` keyword arg misuse | `app/storage/minio_client.py` | `6847a85` |

**What was done in this session (2026-03-29, session 6):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Backend: wire `parent_message_id` on edit_from_sequence | `app/routers/messages.py`, `app/services/stream_service.py` | `b7dcc4c` |
| Frontend: `useStreamingEdit` hook — manual SSE for edit/regenerate | `hooks/useStreamingEdit.ts` (new) | `b7dcc4c` |
| Frontend: edit mode on user messages (pencil icon → inline textarea) | `UserMessage.tsx` | `b7dcc4c` |
| Frontend: regenerate button on assistant messages (RefreshCw icon) | `AssistantMessage.tsx` | `b7dcc4c` |
| Frontend: wire edit/regenerate through MessageBubble → MessageList → ChatWindow | `MessageBubble.tsx`, `MessageList.tsx`, `ChatWindow.tsx` | `b7dcc4c` |
| Backend: Phase 3 unit tests (3 new, total 71) | `test_messages_router.py`, `test_stream_service.py` | `b7dcc4c` |

**What was done in this session (2026-03-29, session 7):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Fix: `message_count` drift on edit (deleted msgs not decremented) | `app/routers/messages.py` | `b7dcc4c` |
| Fix: duplicate user message in LLM context (Phase 1 bug) | `app/services/stream_service.py` | `b7dcc4c` |
| Fix: wrap edit flow in DB transaction for atomicity | `app/routers/messages.py` | `b7dcc4c` |
| Fix: conftest mock_pool supports `pool.acquire()` + `conn.transaction()` | `tests/conftest.py` | `b7dcc4c` |
| Update tests for all 3 bugfixes | `test_messages_router.py`, `test_stream_service.py` | `b7dcc4c` |
| Backend: `POST /v1/translation/translate-text` sync endpoint | `translation-service/app/routers/translate.py` (new) | `b7dcc4c` |
| New model: `TranslateTextRequest` + `TranslateTextResponse` | `translation-service/app/models.py` | `b7dcc4c` |
| Register translate router in translation-service | `translation-service/app/main.py` | `b7dcc4c` |
| Backend: translate-text unit tests (6 tests) | `tests/test_translate.py` (new) | `b7dcc4c` |
| Frontend: `translateText()` in translation API client | `features/translation/api.ts` | `b7dcc4c` |
| Frontend: per-chunk translate button in ChunkItem hover bar | `components/chunk-editor/ChunkItem.tsx` | `b7dcc4c` |
| Frontend: "Translate N chunks" in ChunkEditor selection bar | `components/chunk-editor/ChunkEditor.tsx` | `b7dcc4c` |
| Frontend: translating overlay + loading state per-chunk | `ChunkItem.tsx`, `ChunkEditor.tsx` | `b7dcc4c` |
| Frontend: wire `onTranslateChunk` in ChapterEditorPageV2 | `pages/v2-drafts/ChapterEditorPageV2.tsx` | `b7dcc4c` |

**What was done in this session (2026-04-01, session 14):**

Data Re-Engineering Phase D1 continuation: book-service JSONB handler refactor (D1-06).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| D1-06a: getDraft — body → json.RawMessage scan (inline JSON, not base64) | `services/book-service/internal/api/server.go` | this session |
| D1-06b: patchDraft — json.RawMessage body + body_format + json.Valid + outbox event | same file | this session |
| D1-06c: getRevision — body → json.RawMessage + body_format in response | same file | this session |
| D1-06d: restoreRevision — json.RawMessage both directions + body_format + outbox event | same file | this session |
| D1-06e: listRevisions — length(body) → octet_length(body::text) for JSONB | same file | this session |
| D1-06f: exportChapter — read plain text from chapter_blocks with draft fallback | same file | this session |
| D1-06g: getInternalBookChapter — json.RawMessage body + text_content from blocks | same file | this session |
| D1-06h: createChapterRecord — outbox event for chapter.created | same file | this session |
| D1-07a: plainTextToTiptapJSON converter (pure function, _text snapshots) | `services/book-service/internal/api/tiptap.go` (new) | this session |
| D1-07a: createChapterRecord stores Tiptap JSON body with draft_format='json' | `services/book-service/internal/api/server.go` | this session |
| D1-07a: 5 unit tests for plainTextToTiptapJSON | `services/book-service/internal/api/server_test.go` | this session |
| D1-08a: getDraft adds text_content from chapter_blocks | `services/book-service/internal/api/server.go` | this session |
| D1-08b: getRevision adds text_content extracted from JSONB _text fields | same file | this session |
| D1-08d: translation-service reads text_content instead of body (2 files) | `translation_runner.py`, `chapter_worker.py` | this session |
| D1-08e: translation tests updated with text_content mock responses | `test_chapter_worker.py`, `test_translation_runner.py` | this session |
| D1-05+D1-09: worker-infra Go service scaffold (config, registry, migrate, tasks) | `services/worker-infra/` (new, 10 files) | this session |
| D1-05a: loreweave_events schema (event_log, event_consumers, dead_letter_events) | `services/worker-infra/internal/migrate/migrate.go` | this session |
| D1-09b: config loader (WORKER_TASKS, OUTBOX_SOURCES, EVENTS_DB_URL, REDIS_URL) | `services/worker-infra/internal/config/config.go` + 3 tests | this session |
| D1-09c: task registry (interface, Register, RunSelected, graceful shutdown) | `services/worker-infra/internal/registry/` + 3 tests | this session |
| D1-10a+b: outbox-relay + outbox-cleanup task implementations | `services/worker-infra/internal/tasks/` | this session |
| D1-10c: worker-infra added to docker-compose | `infra/docker-compose.yml` | this session |
| D1-11a: API client types updated (body: any, text_content, body_format) | `frontend-v2/src/features/books/api.ts` | this session |
| D1-11b: TiptapEditor refactor: JSON content, addTextSnapshots, extractText | `frontend-v2/src/components/editor/TiptapEditor.tsx` | this session |
| D1-11c: ChapterEditorPage: JSONB save/load, dirty check, discard | `frontend-v2/src/pages/ChapterEditorPage.tsx` | this session |
| D1-11d: ReaderPage: read-only TiptapEditor replaces ChapterReadView | `frontend-v2/src/pages/ReaderPage.tsx` | this session |
| D1-11e: RevisionHistory: uses text_content from API | `frontend-v2/src/components/editor/RevisionHistory.tsx` | this session |
| D1-12a: Integration test script (T01-T16 scenarios) | `infra/test-integration-d1.sh` (new) | this session |
| D1-04d: transitionChapterLifecycle tx + outbox (trash/purge) | `services/book-service/internal/api/server.go` | this session |
| P3-01: Translation Matrix Tab + translation API module | `TranslationTab.tsx`, `features/translation/api.ts` | this session |
| P3-02: Translate Modal (AI batch) | `TranslateModal.tsx`, `features/ai-models/api.ts` | this session |
| P3-05: Glossary Tab (entity list, filters, CRUD) | `GlossaryTab.tsx`, `features/glossary/api.ts`, `types.ts` | this session |
| P3-06: Kind Editor (two-panel kind browser) | `KindEditor.tsx` | this session |
| P3-07: Entity Editor (dynamic attribute form, slide-over) | `EntityEditor.tsx` | this session |
| P3-06: Kind Editor backend (6 CRUD endpoints) + frontend (full editor) | `glossary-service/kinds_crud.go`, `KindEditor.tsx` | this session |
| P3-R1: GUI review fixes (S1-S11) — glow, covers, filters, EmptyState, auth, FloatingActionBar | 9 files | this session |
| P3-R1: Editor polish — saved badge, version, metadata stats, source line numbers, status bar | `ChapterEditorPage.tsx` | this session |
| P3-R1: TranslationTab polish — checkboxes, row numbers, column headers, cell labels, summary legend, floating action bar | `TranslationTab.tsx` | this session |
| P3-R1: Glossary polish — KindEditor section headers, EntityEditor SYS/USR badges + 2-col layout + footer | `KindEditor.tsx`, `EntityEditor.tsx`, `GlossaryTab.tsx` | this session |
| Entity Editor v2 — centered modal + attribute card system (8 card types, card registry) | `components/entity-editor/` (10 new files) | this session |
| P3-R1: Reader polish — gradient bars, TOC progress/labels, chapter header/footer, font/spacing, percentage | `ReaderPage.tsx`, `index.css` | this session |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-01, session 13):**

Data Re-Engineering Phase D1 continuation: chapter_blocks trigger + outbox pattern.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| D1-03: chapter_blocks table DDL (uuidv7 PK, FK CASCADE, UNIQUE index) | `services/book-service/internal/migrate/migrate.go` | `599721a` |
| D1-03: fn_extract_chapter_blocks() trigger (UPSERT from JSON_TABLE, block shrink, heading_context) | same file | `599721a` |
| D1-03: trg_extract_chapter_blocks trigger (AFTER INSERT OR UPDATE OF body) | same file | `599721a` |
| D1-04: outbox_events table DDL (partial index on pending) | same file | `f76539e` |
| D1-04: fn_outbox_notify() + trg_outbox_notify (pg_notify on INSERT) | same file | `f76539e` |
| D1-04: insertOutboxEvent() Go helper (atomic outbox write within tx) | `services/book-service/internal/api/outbox.go` (new) | `f76539e` |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-03-31 to 2026-04-01, session 12):**

Part 1: Phase 2.5 E1 Tiptap editor migration. Part 2: Data Re-Engineering architecture, planning, and initial migration.

**Part 2 — Data Re-Engineering (2026-04-01):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Data re-engineering plan (polyglot persistence, event pipeline) | `docs/03_planning/101_DATA_RE_ENGINEERING_PLAN.md` (new) | `7d25320` |
| Technology research: PG18 + Neo4j v2026.01, remove Qdrant | `101_DATA_RE_ENGINEERING_PLAN.md` | `c94c4e5` |
| Data engineer review: _text snapshots, UPSERT, outbox pattern | `101_DATA_RE_ENGINEERING_PLAN.md` | `ed20495` |
| Outbox pattern, uuidv7 everywhere, shared events DB | `101_DATA_RE_ENGINEERING_PLAN.md` | `66190da` |
| Phase D0, pre-flight concerns, expanded D1 tasks | `101_DATA_RE_ENGINEERING_PLAN.md` | `c078343` |
| Detailed task breakdown — 8 discovery cycles (58 sub-tasks) | `docs/03_planning/102_DATA_RE_ENGINEERING_DETAILED_TASKS.md` (new) | `f6b41a5` to `04b5e08` |
| Architecture presentation (pipeline, event flow, workers) | `design-drafts/data-pipeline-architecture.html` (new) | `cc9658c` |
| Architecture diagrams (C4, ERD, DFD, deployment) | `design-drafts/architecture-diagrams.html` (new) | `8abbbeb` |
| D0-01: PG18 uuidv7() + JSON_TABLE test | manual (psql) | `6dc6a09` |
| D0-02: All 9 service migrations on PG18 | manual (psql) | `e3cfd2e` |
| D0-03: JSON_TABLE trigger test (7 scenarios) | `infra/test-pg18-trigger.sql` (new) | `bb196b3` |
| D0-04: Go pgx JSONB + json.RawMessage test | `infra/pg18test-go/` (new) | `5907dce` |
| D1-01: Postgres 16→18, add Redis, add loreweave_events | `infra/docker-compose.yml`, `infra/db-ensure.sh` | `748a519` |
| D1-02: uuidv7 everywhere, JSONB body, drop pgcrypto | 8 migration files across all services | `54a4d1f` |

**Architecture decisions recorded (session 12):**
- Postgres 18 (JSON_TABLE, virtual columns, uuidv7, async I/O)
- Neo4j v2026.01 for knowledge graph + vector search (no Qdrant needed)
- Two-layer data stack: Postgres (source of truth) → Neo4j (knowledge + vectors)
- Transactional Outbox pattern for guaranteed event delivery
- Two-worker architecture: worker-infra (Go) + worker-ai (Python)
- _text snapshots per Tiptap block (frontend pre-computes, trigger reads trivially)
- UPSERT trigger for stable block IDs across saves
- Plain text → Tiptap JSON conversion at import (no dual-mode)
- Shared loreweave_events database for centralized event management
- Frontend V2 Phase 3 paused until data re-engineering complete

**Part 1 — Phase 2.5 E1 Tiptap editor migration (2026-03-31):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| E1-01: Install Tiptap + extensions, remove Lexical | `package.json` | this session |
| E1-02: TiptapEditor component + FormatToolbar | `components/editor/TiptapEditor.tsx` (new), `FormatToolbar.tsx` (new) | this session |
| E1-03: Remove chunk mode, add slash menu | `components/editor/SlashMenu.tsx` (new), `pages/ChapterEditorPage.tsx` (rewrite) | this session |
| E1-04: Callout custom node (author notes) | `components/editor/CalloutNode.tsx` (new) | this session |
| E1-05: Grammar as Tiptap DecorationPlugin | `components/editor/GrammarPlugin.ts` (new) | this session |
| E1-06+07: Mode toggle Classic/AI + classic constraints | `hooks/useEditorMode.ts` (new), `SlashMenu.tsx`, `FormatToolbar.tsx` | this session |
| E1-08: Wire auto-save (5m), Ctrl+S, dirty tracking, guards, revisions | `ChapterEditorPage.tsx` | this session |
| Tiptap editor styles | `index.css` | this session |
| Bug fixes: content prop reactivity, Windows line endings, stale doc guard | `TiptapEditor.tsx`, `GrammarPlugin.ts` | this session |
| CLAUDE.md: add 9-phase task workflow with roles | `CLAUDE.md` | this session |

**Design decisions recorded:**
- Tiptap replaces both textarea (source mode) and contentEditable chunks (chunk mode) — single editor
- Plain text round-trip: backend stores plain text, HTML ↔ text conversion on load/save (until E2 block JSON)
- Auto-save at 5 minutes (not 30s) — matches Word/Excel behavior
- Classic mode: text-only slash menu; AI mode: full features including callouts
- Chunk mode fully removed (useChunks, ChunkItem, ChunkInsertRow now dead code)

**What was done in this session (2026-03-31, session 11):**

LanguageTool grammar check integration, mixed-media editor design (4 HTML drafts), and phase planning (29 new tasks).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| LanguageTool Docker container + proxy | `infra/docker-compose.yml`, `vite.config.ts`, `nginx.conf` | this session |
| Grammar API client + decoration utilities | `src/features/grammar/api.ts` (new) | this session |
| Grammar check hooks (chunk + source mode) | `src/hooks/useGrammarCheck.ts` (new) | this session |
| ChunkItem grammar decorations (wavy underlines) | `src/components/editor/ChunkItem.tsx` | this session |
| Grammar toggle + wiring in editor page | `src/pages/ChapterEditorPage.tsx`, `src/index.css` | this session |
| Design: AI Assistant mode editor | `design-drafts/screen-editor-mixed-media.html` (new) | this session |
| Design: Classic mode editor | `design-drafts/screen-editor-classic.html` (new) | this session |
| Design: Mode spec + guards + version model | `design-drafts/screen-editor-modes.html` (new) | this session |
| Design: Media version history UI | `design-drafts/screen-editor-version-history.html` (new) | this session |
| Phase 2.5/3.5/4.5 planning (29 new tasks) | `docs/03_planning/99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | this session |

**Design decisions recorded:**
- Tiptap (ProseMirror) chosen as editor engine -- replaces textarea + contentEditable chunks
- Two editor modes: Classic (pure writing, media locked) / AI Assistant (full features)
- Block types: paragraph, heading, divider, callout, image, video, code
- AI prompt stored on every media block (re-generation + AI context + audit trail)
- Audio/TTS per paragraph -- AI generate or manual upload, hidden by default
- Media version tracking with prompt snapshots + versioned MinIO paths
- Classic mode guards protect media blocks from accidental deletion
- Phase 2.5 (Tiptap migration) must complete before Phase 3

**What was done in this session (2026-03-31, session 10):**

Chapter editor unsaved-changes guard, universal dialog system, and toast infrastructure.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| `EditorDirtyContext` — owns `pendingNavigation`, `guardedNavigate`, `confirmNavigation` | `src/contexts/EditorDirtyContext.tsx` (new) | this session |
| Universal `ConfirmDialog` — icon, `extraAction` (3rd button), auto-stacked layout | `src/components/shared/ConfirmDialog.tsx` | this session |
| `UnsavedChangesDialog` — thin wrapper: Save & leave / Discard & leave / Stay | `src/components/shared/UnsavedChangesDialog.tsx` (new) | this session |
| `EditorLayout` — all nav links guarded via context `guardedNavigate`; logout uses `ConfirmDialog` | `src/layouts/EditorLayout.tsx` | this session |
| `ChapterEditorPage` — breadcrumb + prev/next guard; Discard button; in-place `ConfirmDialog`; navigation `UnsavedChangesDialog` | `src/pages/ChapterEditorPage.tsx` | this session |
| Install `sonner`; wire `<Toaster>` in `App.tsx` | `src/App.tsx`, `package.json` | this session |
| Replace save badge + error banner with `toast.success/error` in editor | `ChapterEditorPage.tsx` | this session |
| `RevisionHistory` — restore success/error now uses toast | `src/components/editor/RevisionHistory.tsx` | this session |
| `ChaptersTab` — download success, download/trash/create errors now use toast (were silently swallowed) | `src/pages/book-tabs/ChaptersTab.tsx` | this session |

**Design decisions recorded:**
- Error/warning *dialogs* are NOT added — toast covers transient feedback; inline errors stay for form context (login, register, import dialog, page-load errors)
- `ConfirmDialog` is the single universal primitive: 2-button (default) or 3-button (when `extraAction` passed) — buttons auto-stack vertically on 3-button layout
- `window.confirm/alert` fully eliminated from frontend-v2

**What was done in this session (2026-03-30, session 9):**

Frontend V2 planning + CI cleanup + branch hygiene.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Remove stale Module 01 CI workflow (was spamming email on every push) | `.github/workflows/loreweave-module01.yml` (deleted) | `6f14c26` (PR #2) |
| Review all git branches — all local branches merged into main, safe to clean | — | — |
| Full GUI audit: identified 10 structural issues (layout, nav, components, forms) | — | — |
| Design navigation architecture: sidebar, 3 layout types, breadcrumbs, route map | — | — |
| Create component catalog HTML draft (cold zinc theme) | `design-drafts/components-v2.html` | — |
| Create warm literary theme draft (amber/teal, Lora serif, approved) | `design-drafts/components-v2-warm.html` | — |
| Fix Tailwind CDN color rendering (HSL → CSS variables + hex) | `design-drafts/components-v2-warm.html` | — |
| Write Frontend V2 Rebuild Plan (full planning doc) | `docs/03_planning/99_FRONTEND_V2_REBUILD_PLAN.md` | — |

**What was done in this session (2026-03-30, session 8):**

Code review + hardening pass across chat-service, translation-service, and frontend.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Fix: entire edit flow (DELETE + INSERT + UPDATE) in single transaction | `chat-service/app/routers/messages.py` | `b7dcc4c` |
| Fix: safe format_map — unknown `{placeholders}` pass through unchanged | `translation-service/app/routers/translate.py` | `b7dcc4c` |
| Fix: add `min_length=1, max_length=30000` to TranslateTextRequest.text | `translation-service/app/models.py` | `b7dcc4c` |
| Fix: "auto" source_language now returns "auto-detect" (better prompt text) | `translation-service/app/routers/translate.py` | `b7dcc4c` |
| Fix: handle malformed provider response (JSON parse + missing keys → 502) | `translation-service/app/routers/translate.py` | `b7dcc4c` |
| Fix: use user's `invoke_timeout_secs` preference instead of hard-coded 120 | `translation-service/app/routers/translate.py` | `b7dcc4c` |
| Add: structured logging in translate endpoint | `translation-service/app/routers/translate.py` | `b7dcc4c` |
| Fix: stale closure in ChunkEditor translateChunk (remove translatingIndices dep) | `frontend/src/components/chunk-editor/ChunkEditor.tsx` | `b7dcc4c` |
| Fix: bulk translate shows toast on partial failures | `frontend/src/components/chunk-editor/ChunkEditor.tsx` | `b7dcc4c` |
| Fix: per-chunk translate passes book's target_language to API | `frontend/src/pages/v2-drafts/ChapterEditorPageV2.tsx` | `b7dcc4c` |
| Test: malformed provider response → 502 | `translation-service/tests/test_translate.py` | `b7dcc4c` |
| Test: user timeout preference used in httpx client | `translation-service/tests/test_translate.py` | `b7dcc4c` |
| Update: chat-service tests for new transaction boundary | `chat-service/tests/test_messages_router.py` | `b7dcc4c` |

**Test coverage:**
- `test_output_extractor.py` — 8 tests (pure function, code block extraction)
- `test_auth.py` — 5 tests (JWT validation, expiry, wrong secret)
- `test_sessions_router.py` — 10 tests (CRUD, 404s, validation)
- `test_outputs_router.py` — 14 tests (CRUD, download, export, MinIO redirect)
- `test_messages_router.py` — 11 tests (list, send, streaming, archived, provider 404, edit, normal parent)
- `test_stream_service.py` — 7 tests (text deltas, persistence, artifacts, errors, model strings, history, parent_message_id)
- `test_minio_client.py` — 5 tests (upload, presigned, delete, bucket create/noop)
- `test_clients.py` — 4 tests (provider resolve, billing log, error swallowing)
- `test_translate.py` — 8 tests (success, override lang, 402, 500→502, no model, missing text, malformed response, user timeout)

**ChunkEditor component system (created this session):**
```
frontend/src/components/chunk-editor/
  useChunks.ts      — splits text, tracks edits, reassembles, avoids circular updates
  ChunkItem.tsx     — single paragraph chunk: view / edit / copy / reset
  ChunkEditor.tsx   — container: selection state, dirty bar, selection bar, hint bar
  index.ts          — public exports
```

---

## What Is Next

### Completion Summary (as of session 31)

| Area | Status |
| ---- | ------ |
| Frontend V2 Phase 1 (Foundation) | ✅ Done |
| Frontend V2 Phase 2 (Core Screens) | ✅ Done |
| Frontend V2 Phase 2.5 (Tiptap Editor) | ✅ Done |
| Frontend V2 Phase 3 (Features: Translation, Glossary, Chat, Wiki) | ✅ Done |
| Frontend V2 Phase 3.5 (Media Blocks) | ✅ Done |
| Frontend V2 Phase 4 (Settings, Usage, Browse) | ✅ Done |
| Phase 4.5 / 8D (Audio/TTS system) | ✅ Done |
| P4-04 Reading/Theme Unification (9 tasks) | ✅ Done |
| Phase 8A-8H (Reader v2, Translation Pipeline, Review Mode, Analytics) | ✅ Done |
| Phase 9 (Leaderboard, Profile, Wiki, Import, Audio, Account) | ✅ Done |
| MIG-03..MIG-10 (V1→V2 page migrations + old frontend deleted) | ✅ Done |
| P3-08 Genre Groups (BE+FE) | ✅ Done |
| P3-KE Kind Editor Enhancement (13 tasks) | ✅ Done |
| Data Re-Engineering D1 (JSONB, blocks, events, worker-infra) | ✅ Done |
| Translation Pipeline V2 (CJK fix, glossary, validation, memo) | ✅ Done |
| Chat Service Phase 1-3 | ✅ Done |
| Glossary Extraction Pipeline — BE (13 tasks) | ✅ Done |
| Glossary Extraction Pipeline — FE (7 tasks) | ✅ Done |
| GEP Integration Test (49 assertions) | ✅ Done |
| GEP Browser Smoke Test | ✅ Done |
| INF-01..03 (Service auth, HTTP client, structured logging) | ✅ Done |
| Voice Mode — Chat (VM-01..VM-06) | ✅ Done |
| AI Service Readiness — Gateway + Mock + FE hooks (AISR-01..05) | ✅ Done |
| External AI Service Integration Guide (1096 lines) | ✅ Done |

### Remaining Work

| Priority | Item | Scope | Notes |
| -------- | ---- | ----- | ----- |
| **P1** | **Translation Workbench** (P3-T1..T8) | 8 tasks (BE+FE) | Block-level translation UI. Design draft exists. Blocker removed (media blocks done). |
| **P1** | **Build external TTS/STT services** (separate repos) | New repos | Integration guide ready. Gateway proxy + frontend hooks done. Need: Whisper STT service, Coqui/XTTS TTS service. |
| P2 | GUI Review deferred (D1-D22) | FE polish | Editor, glossary, reader polish items |
| P2 | Chat Service Phase 4 | BE+FE | File attachments + multi-modal |
| P2 | Platform Mode | 35 tasks | `103_PLATFORM_MODE_PLAN.md` — multi-tenant SaaS features |
| P2 | Onboarding Wizard (P2-10) | FE | New user first-run experience |
| P3 | Phase 5: Advanced | Wishlist | Ambient mode, focus mode, night shift, knowledge graph |
| P3 | Formal acceptance evidence packs (M01-M05) | QA | Currently smoke-only |

> **Note:** The 99A planning doc (`99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md`) task markers are stale — 176/712 marked `[✓]` but ~640+ are actually done. The planning doc should be treated as historical reference, not active tracker.

---

## Open Blockers

| ID | Blocker | Severity | Owner |
| -- | ------- | -------- | ----- |
| BLK-01 | Formal acceptance evidence packs not produced for M01-M05 | Medium | QA |
| ~~BLK-02~~ | ~~M05 not started~~ | ~~Resolved~~ | ~~Tech Lead~~ |

> BLK-02 resolved: M05 Glossary & Lore Management is complete (closed smoke).

---

## Session History (recent)

| Date       | What happened | Key commits |
| ---------- | ------------- | ----------- |
| 2026-04-12→13 | Session 34: Chat page MVC refactor (ChatSessionContext/ChatStreamContext split, ChatView always-mounted), voice assist unified (VAD + backend STT + backend TTS with S3 replay), 422 STT/TTS fixes (model field). **Knowledge Service design end-to-end**: MemPalace review, architecture doc (5 review rounds), Track 1/2/3 implementation plans (~215 tasks), UI mockup (14 sections), 3-step build wizard with glossary picker + pending proposals + gap report. **Two-layer anchoring pattern** adopted — glossary as authored SSOT, KS as fuzzy/semantic layer with `glossary_entity_id` FK, validated by GraphRAG/HippoRAG research. Wiki confirmed inside glossary-service. Evidence storage investigated — rich table exists, FE only needs browser UI (G-EV-1 added as next-session pre-req). | `eb4b798`..`0f1fcc3` (22 commits) |
| 2026-04-10→11 | Session 31: Three features. **GEP** — 10 BE fixes from real AI testing, integration test (49 assertions), 7 FE tasks (extraction wizard), smoke test. **Voice Mode** — 6 tasks (useSpeechRecognition, VoiceSettingsPanel with STT/TTS model selectors, useVoiceMode orchestrator, push-to-talk mic, overlay UI, integration wiring), 2 review passes (17 issues fixed). **AI Service Readiness** — gateway audio proxy, mock audio service, useBackendSTT, useStreamingTTS, integration test (19 assertions), review (20 issues fixed). **Docs** — integration guide (1096 lines), 99A bulk update (464 markers), session audit. | `3c5202a`..`e54557e` (29 commits) |
| 2026-04-10 | Session 30: Glossary Extraction Pipeline — full design doc (1500+ lines), 4 review rounds (context/data, security, cost → 22 issues found and fixed), UI draft HTML (7 interactive screens), implementation task plan (13 BE + 7 FE tasks). Design artifacts: `GLOSSARY_EXTRACTION_PIPELINE.md`, `glossary_extraction_ui_draft.html`. Key decisions: source language SSOT, alive flag for entities, 3-layer known entities filtering, extraction_audit_log table, prompt injection mitigation, cost estimation. | `ee6d64e` |
| 2026-04-09→10 | Session 29: Translation Pipeline V2 — full implementation (P1-P8). CJK token fix (2.29x), glossary injection (1/6→6/6), output validation+retry, multi-provider tokens, rolling context, auto-correct, chapter memo, quality metrics. 3 services touched (translation, glossary, provider-registry). PoC with real Ollama gemma3:12b. Docker integration test: 132+113 blocks, all valid. 3 commits. | `662cbf7`..`6db8553` |
| 2026-04-03 | Session 16: Phase 3.5 (E4+E5, 12 tasks), video-gen-service skeleton, M1-M6 (design draft gaps), MIG-01 (Trash page), MIG-02 (Chat page), code block fixes (5 iterations), image block fixes (upload wiring, MinIO URL, mode switch, hover overlay), removed localStorage cache persistence, planning docs (VG, MV, VH, TR, MIG). 53 commits. | `40bb7b1`..`bec9eef` |
| 2026-04-02 | Session 15: Phase 3 FE complete (P3-18/19/20/21/22/22a+b), BE fixes (patchBook null, chat context field, gateway proxy), 5 integration test scripts (120 total scenarios), Docker fix | `911c249`..`eeee14c` |
| 2026-04-02 | Session 14: D1 complete (D1-06→D1-12), Phase 3 FE (P3-01→P3-07), GUI review (5 drafts, 41 fixes), React Query, entity editor v2, Platform Mode plan | session 14 |
| 2026-04-01 | Data re-engineering D1-06→D1-12: JSONB handlers, Tiptap import, text_content, worker-infra, frontend JSONB, integration tests | session 14 |
| 2026-04-01 | Data re-engineering D1-03 (chapter_blocks + trigger) + D1-04 (outbox_events + pg_notify + helper) | `599721a`, `f76539e` |
| 2026-04-01 | Data re-engineering: D0 pre-flight (4/4 pass), D1-01 (PG18+Redis), D1-02 (uuidv7+JSONB) | `54a4d1f` |
| 2026-03-31 | Phase 2.5 E1: Tiptap editor migration (8 tasks), bug fixes, workflow update | `4f39cf7` |
| 2026-03-31 | LanguageTool integration, mixed-media editor design (4 drafts), Phase 2.5/3.5/4.5 planning | session 11 |
| 2026-03-31 | Unsaved-changes guard (EditorDirtyContext, UnsavedChangesDialog), universal ConfirmDialog, toast system (sonner) | this session |
| 2026-03-30 | Frontend V2 planning: GUI audit, design drafts (warm literary theme), rebuild plan, CI cleanup | `6f14c26` (PR #2) |
| 2026-03-30 | Code review hardening: transaction fix, safe format_map, response validation, stale closure fix, bulk error UX | `b7dcc4c` |
| 2026-03-29 | Visibility fix, unified chapter editor, ChunkEditor system + selection, chat service, test fixes | `bf17136`, `e9d1c29`, `23bad63`, `fd4a5ea`, `3cb8e4c`, `2f47c89`, `b32f415` |
| 2026-03-23 | M04 translation pipeline implementation (backend + frontend) | — |
| 2026-03-22 | M03 provider registry implementation (backend + frontend) | — |
| 2026-03-21 | M02 UI/UX wave (BookDetailPageV2, reader pages, responsive) | — |

---

## Deferred Items (cross-module)

| Item | Status | Planned direction | Marker doc |
| ---- | ------ | ----------------- | ---------- |
| Physical garbage collector for purge_pending objects | Not implemented | Background GC worker | — |
| Gitea integration for chapter version control | Not implemented | ADR needed first | — |
| Non-text chapter formats (pdf, docx, html, OCR) | Not implemented | Future MIME extension wave | — |
| Paid storage tiers / billing integration | Not implemented | Future monetization wave | — |
| AI-generated summaries / covers | Not implemented | Future AI feature wave | — |
| Production rollout hardening (SRE, security sign-off) | Not done | Pre-release gate wave | — |
| SSE / WebSocket streaming progress for translation jobs | Not implemented | Currently polling | — |
| **Structured book/chapter zip import-export** (portable bundles with metadata, revisions, assets) | Not implemented | Post-V1 feature wave | `100_FUTURE_FEATURE_STRUCTURED_IMPORT_EXPORT_MEDIA.md` |
| **Media-rich chapters** — images and video for visual novel-style storytelling | **Phase 3.5 Done** | E4+E5 complete, image/video/code blocks | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` |
| **Video generation provider integration** — connect video-gen-service to real providers (Sora, Veo, etc.) | Skeleton deployed | 10 tasks planned (VG-01..VG-10) | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` |
| **Media version retention** — auto-delete old versions, retention policy, MinIO GC, storage usage UI | Planned | 7 tasks (MV-01..MV-07) | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` |
