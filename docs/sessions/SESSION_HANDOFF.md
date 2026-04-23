# Session Handoff — Session 50 (28 cycles · Track 2/3 Gap Closure C2 closes P1 tier · plan file live)

> **Purpose:** orient the next agent in one read. **Source of truth for detailed state remains [SESSION_PATCH.md](SESSION_PATCH.md).** This file is the single, unversioned handoff — updated in place at the end of each session. Do NOT create `_V*.md` variants.
> **Date:** 2026-04-23 (session 50, closed)
> **HEAD:** `2812aff` (C2 scheduler trigger label + regen cooldown; C1 @ `b447a9e` + `16c56e5`; K20.3-β @ `db7cf05` + `e367377`; K20.3-α @ `474a7d8` + `e7b1d18`; K19f-ε @ `03e7774` + `56047dd`; K19f-δ @ `3a2126c` + `ca8b5f7`; K19f-γ @ `84d5eec` + `8b18a12`; K19f-β @ `b059a6b` + `2412e57`; K19f-α @ `8aeb0bc` + `bd3a81b`; K19e-γb @ `8289bf1` + `35f4a16`; K19e-γa @ `cd7aae1` + `63b639b`; K19e-β @ `36937d1` + `9311705`; K19e-α @ `10d8e95` + `e6b1eaa`; K19d-γb @ `c9aaf95` + `b7b5b3c`; K19d-γa @ `5d42afd` + `db405f6`; K19d-β @ `aeb008b` + `c920d95`; K19d-α @ `96f9b6b` + `e0fbd21`; K20-β+γ @ `9289ded` + `166c9e1`; K20-α @ `71530a1` + `5faaf08`; K19c-β @ `8baa670` + `79503f2`; K19c-α @ `a619b5f` + `f7aabae`; K19b.8 @ `526533d` + `5c6c63f`; D-K16.11-01 @ `c9f7064` + `5e9decc`; K19b.6+D-K19a.5-03 @ `32a9a18` + `e232486`; K16.12 completion @ `b313c1b` + `87c50be`; K19b.3+K19b.5+ETA @ `5e00f7b` + `0e65f17`; K19b.2+K19b.7-partial @ `4fb8b62` + `958d8da`; K19b.1+K19b.4 @ `1c208ce` + `c79ea90`; K19a.8 @ `2061b2d`; K19a.7 @ `2cbcc7c` + `c6ee80a`; K19a.6 @ `2226283` + `7cf394f`; K19a.5 @ `3148751` + `1156193`)
> **Branch:** `main` (ahead of origin by sessions 38–50 commits — user pushes manually)

## Session 50 — 28 cycles shipped (24 Track 3 + 2 Track 2 close-out + 2 Gap Closure) · Track 2/3 Gap Closure P1 tier 2/2 ✅

### Cycle 28 — Track 2/3 Gap Closure C2 [BE L] — scheduler trigger label + regen cooldown

Second cycle of the [Gap Closure Plan](../03_planning/KNOWLEDGE_SERVICE_TRACK2_3_GAP_CLOSURE_PLAN.md). Closes both remaining P1-tier observability items — **D-K20.3-α-02** (scheduler metrics) + **D-K20α-02** (regen cooldown). Reclassified S → L early in CLARIFY after audit (plan's "2 files" was optimistic; actual touch is 7 files + 3 test-file extensions).

**Two substantive code changes:**

1. **`summary_regen_total` gains `trigger` label** (`manual` | `scheduled`). Cardinality 12 → 24 pre-seeded series. `RegenTrigger = Literal["manual","scheduled"]` added to `regenerate_summaries.py`; threaded as `trigger` kwarg through `_regenerate_core`, `regenerate_global_summary`, `regenerate_project_summary` (default `"manual"` — back-compat). Scheduler passes `trigger="scheduled"`; public endpoints pass `trigger="manual"`. `/internal/summarize`'s `SummarizeRequest` gains a `trigger: RegenTrigger = "manual"` field (post /review-impl LOW#5). Duration/cost/tokens counters stay 2-label (MVP scope, documented).

2. **Redis SETNX cooldown** on both public regen endpoints. Key `knowledge:regen:cooldown:{user}:{scope_type}:{scope_id or '-'}`, 60s TTL. Per-target (scope_id in key), not per-user. Module-level lazy `aioredis` singleton with `asyncio.Lock` double-checked init + `close_cooldown_client` wired into lifespan teardown (both failure-cleanup tuple AND normal post-yield block). On 429: `Retry-After` header from `client.ttl(key)` with TTL-exception fallback to full budget + defensive floor-to-1 for the `-2`-race (key expires between SETNX=False and TTL read). Graceful degrade when `settings.redis_url` empty OR Redis raises.

**`/review-impl` caught 1 MED + 5 LOW + 1 COSMETIC; all 7 fixed in the same commit:**
- **MED#1** cooldown armed on 500-class server-side failures — live-verified via docker curl (Neo4j-not-configured 500 still armed key for 60s, punishing users for our own bugs). Fixed with `_release_regen_cooldown` helper called from `except ProviderError` AND `except Exception` in both endpoints. Business outcomes (user_edit_lock / concurrent_edit / no_op_* / regenerated) KEEP the cooldown armed — `test_regenerate_cooldown_stays_armed_on_business_outcomes` locks that primary anti-spam contract.
- **LOW#2** FakeRedis.ttl always returned the stored EX value so the defensive floor-to-1 branch never fired in tests → FakeRedis gains `expired_keys` mode returning `-2`; `test_regenerate_cooldown_retry_after_floor_when_ttl_expired_mid_race` asserts `Retry-After == 1`.
- **LOW#3** `client.ttl()` exception path had no test coverage (BoomRedis short-circuits at SET) → `_HalfBoomRedis` (SET/DELETE succeed, TTL raises) + `test_regenerate_cooldown_ttl_exception_falls_back_to_full_budget`.
- **LOW#4** `test_regenerate_project_cooldown_per_project_scope` missing `mock_regen.await_count == 2` → assertion added.
- **LOW#5** `/internal/summarize` didn't accept `trigger` → added as `SummarizeRequest.trigger` + 3 tests (default-to-manual, explicit-scheduled-forwards, Literal-validator-rejects-typo).
- **COSMETIC#7** `_check_regen_cooldown` + `_cooldown_key` used `scope_type: str` → tightened to `Literal["global", "project"]`.
- Accepted **LOW#6**: duration/cost/tokens still 2-label — documented in `_regenerate_core` docstring.

**Live manual-curl verify** (docker rebuild `infra-knowledge-service:latest` + hot-swap; Postgres/Redis/glossary healthy; Neo4j intentionally down = Track 1 mode):
- Call 1 to `/me/summary/regenerate` → 500 (Neo4j not configured); Redis key ABSENT (MED#1 release path fired)
- Call 2 → 500 not 429 (no stuck cooldown)
- Manually `redis-cli SET project:11111… EX 60` → endpoint → **429** with `Retry-After: 60` (cooldown still works for armed state)
- Endpoint to `project:22222…` → **422** guardrail (cross-user) NOT 429 (per-scope isolation holds)
- Post-422: both project keys armed independently (TTL 45s + 46s)
- `/metrics` scrape shows 24 pre-seeded series + `{scope_type="project",status="no_op_guardrail",trigger="manual"} 1.0` incremented by the 422 call

**Closes**: D-K20.3-α-02 (scheduler metrics) + D-K20α-02 (regen cooldown).

**Verify**: knowledge-service unit 1330/1330 (was 1322 at C1 end; **+8** = 5 cooldown regressions + 3 trigger-forwarding; existing-test updates: 3 metric assertions + 2 scheduler `await_args.kwargs["trigger"]` asserts + 1 `await_count == 2` assertion).

**Plan progress**: 4/33 item-closures · 2/20 cycles · **P1 tier 2/2 done** (C1 ✅ + C2 ✅); P2 tier opens with C3 next.

---

### Cycle 27 — Track 2/3 Gap Closure C1 [FS M] — merge_entities atomicity + ON MATCH union

**First cycle of the new [Track 2/3 Gap Closure Plan](../03_planning/KNOWLEDGE_SERVICE_TRACK2_3_GAP_CLOSURE_PLAN.md)** — a 20-cycle debt-drain (~32 open deferrals from Track 2 + K19/K20) the user asked for before opening further Track 3 feature work. C1 is P1 tier — the only backlog item with actual data-loss risk.

**Two changes to [`app/db/neo4j_repos/entities.py`](../../services/knowledge-service/app/db/neo4j_repos/entities.py):**

1. **Atomicity.** `merge_entities` steps 4–7 (rewire RELATES_TO / rewire EVIDENCED_BY / update target w/ glossary pre-clear / DETACH DELETE source) wrapped in `async with await session.begin_transaction() as tx:`. A Neo4j crash between glossary pre-clear and DETACH DELETE can no longer leave source orphaned with `glossary_entity_id=NULL`. Docstring added the contract: "session must be a fresh AsyncSession with no open transaction" — Neo4j async sessions don't nest tx.

2. **ON MATCH union.** `_MERGE_REWIRE_RELATES_TO_CYPHER` gained 4 CASE branches beyond the pre-existing `confidence`-MAX + `source_event_ids`-UNION: `pending_validation` via `coalesce(..., false) AND ...` (matches `relations.py`'s 8-site NULL=validated convention), `valid_from` earliest-non-null, `valid_until` NULL-wins (NULL = still-active sentinel per relations.py:13), `source_chapter` concat-when-distinct. Pass-2-validated source edge merging into quarantined target duplicate now correctly promotes to validated.

**+3 integration tests (live Neo4j):**
- `test_merge_entities_promotes_validated_edge_over_quarantined` — all 4 union branches incl. `valid_until` NULL-wins via raw-Cypher seed (`create_relation` doesn't accept the kwarg)
- `test_merge_entities_on_match_preserves_quarantine_and_validated` — both mirror AND cases a hardcoded `= false` regression would pass without
- `test_merge_entities_is_atomic_on_mid_flight_failure` — `monkeypatch`es `_MERGE_DELETE_SOURCE_CYPHER` → bad Cypher and asserts **3 rollback axes** (glossary + no rewired RELATES_TO + target aliases unchanged). Multi-axis defense against a regression moving ANY single step out of tx, not just the step the failure-injection point targets.

`/review-impl` caught **2 MED + 3 LOW + 1 COSMETIC; all 6 folded into same commit**:
- **M1** coalesce-to-true diverged from codebase NULL=false convention → switched both sides to `coalesce(..., false)`
- **M2** atomicity test proved only glossary-axis rollback → extended to 3 axes
- **L3** `valid_until` CASE never exercised → raw-Cypher seed on target
- **L4** AND-combine only tested promotion direction → new mirror test
- **L5** Python `bool(x or False)` NULL coercion — subsumed by M1 aligned defaults
- **L6** nested-tx contract undocumented → docstring updated
- Accepted #7: `source_chapter` concat bloat on repeated merges — hobby scale, in-code comment

**Closes**: D-K19d-γb-01 (ON MATCH union) + D-K19d-γb-02 (merge atomicity).

**Verify**: 26/26 `test_entities_browse_repo.py` (+3 new) + 105/105 adjacent integration + 86/86 entity unit.

**Plan progress**: 2/33 item-closures · 1/20 cycles · P1 tier: 1/2 done (C1 ✅, C2 next).

---

### Cycle 26 — K20.3 Cycle β [BE L] — Scheduled global L0 regen loop

Closes K20.3 by shipping the global-scope sweep that Cycle α deferred. Close-mirror of α with 3 substantive differences:

1. **UNION eligibility**: users with either an existing global summary OR any non-archived project — catches "keep my bio fresh" AND "will create on first successful regen once I have enough content". Locked by integration test against live Postgres.
2. **User-wide model resolution**: `SELECT llm_model FROM extraction_jobs WHERE user_id=$1 AND status='complete' ORDER BY completed_at DESC LIMIT 1` — picks the most-recent model used anywhere. Users who've never extracted get `no_model` skip.
3. **Distinct advisory lock** `_GLOBAL_REGEN_LOCK_KEY = 20_310_002` so project + global loops can run concurrently on different scopes.

Cadence: **weekly** (7d = 604800s) with 15-min startup delay (offset from project loop's 10-min).

`/review-impl` caught **2 LOW + 1 COSMETIC; all 3 addressed in-cycle**:
- **L1** UNION eligibility SQL untested at integration layer → NEW `test_summary_regen_scheduler_sql.py` with 2 tests hitting live Postgres: 5-user scenario matrix (summary-only / project-only / summary+archived / archived-only / dual-source) locks UNION dedup AND `is_archived=false` filter. Separate ordering test locks crash-resume determinism.
- **L2** no audit log showing which model was resolved per sweep → INFO log `K20.3: regen project|global user=... model=...` on both sweeps. Operators can now grep logs to trace "why did this user's regen fail?" back to the BYOK model choice (especially useful after provider model deprecations).
- **C3** FakeConn arg-count routing was fragile → SQL-text matching (`"project_id = $2" in sql`) ties the fake to the exact production code paths.

**Build-time catch**: initial integration test skipped with Postgres auth failure — container uses `loreweave:loreweave_dev@loreweave_knowledge` not `postgres:*@knowledge`. Corrected `TEST_KNOWLEDGE_DB_URL`.

**Cleared**: D-K20.3-α-01 (scheduled global L0 regen loop).

**Still deferred**: D-K20.3-α-02 (Prometheus metrics beyond logged outcome counters).

**Test deltas at K20.3 β end:**
- BE unit: **32/32 scheduler tests pass** (was 18; +14 global-sweep coverage)
- BE integration: **2/2 new SQL tests** against live `infra-postgres-1`
- BE regen-adjacent: **76/76** (no regressions)

---

### Cycle 25 — K20.3 Cycle α [BE L] — Scheduled project summary regen

Ships the scheduled auto-regen that K20α/β/γ intentionally deferred. Mirrors the K13.1 `anchor_refresh_loop` template: `sweep_projects_once` is the pure sweep function (pg_try_advisory_lock + iterate non-archived extraction-enabled projects + per-project call to `regenerate_project_summary`), `run_project_regen_loop` wraps it in an asyncio loop with 10-min startup delay + 24h interval.

**Model resolution**: scheduled regen has no caller to supply `model_ref`, so it subqueries `extraction_jobs` for the most-recent completed job per project and reuses its `llm_model`. Projects that never ran extraction are counted as `no_model` and skipped.

**Status mapping**: 6 `RegenerationStatus` Literal values collapse into 4 counter buckets on `SweepResult`:
- `regenerated` → `regenerated`
- `no_op_similarity`, `no_op_empty_source`, `no_op_guardrail` → `no_op`
- `user_edit_lock`, `regen_concurrent_edit` → `skipped`
- Unknown future status → `errored` + WARNING log (defensive branch)

**Advisory lock** via `try/finally: pg_advisory_unlock` guarantees release even on mid-sweep exception. Lock released before connection returns to pool — no orphaned state on recycled connections.

**Lifespan wire** in `main.py` matches K13.1: conditional on `settings.neo4j_uri` (Track 1 mode skips), teardown via `cancel+await+suppress CancelledError`.

`/review-impl` caught **1 LOW + 2 COSMETIC; all 3 addressed in-cycle**:
- **L1** inline `SummariesRepo(get_knowledge_pool())` vs async `get_summaries_repo()` factory → documented decision (matches K13.1 precedent; factory would make scheduler the odd one out in lifespan wire)
- **C2** `model_construct` test fixture bypass → 11-line docstring explaining forward-compat tradeoff
- **C3** sweep-complete INFO log untested → new test asserts exactly-one completion log + all 6 counter names present in message

**Build-time catches:**
- Pydantic Literal rejection on unknown status → `model_construct` bypass for the defensive-branch test
- Mock signature `**_kwargs` couldn't absorb positional args from real `sweep_projects_once(pool, session_factory, provider_client, summaries_repo)` → `*_args, **_kwargs`
- `startup_delay_s=0` guard skipped the first `asyncio.sleep` call, throwing off count expectations → tests use `startup_delay_s=1`

**Deferred to Cycle β**:
- D-K20.3-α-01 global L0 regen loop (needs cross-project model resolution)
- D-K20.3-α-02 scheduler run metrics (Prometheus counters beyond logged outcome)

**Test deltas at K20.3 α end:**
- BE unit: **18/18 scheduler tests pass** (new file)
- BE regen-adjacent: **62/62** (61 previous + 1 completion-log test)
- No regressions across all regen paths

---

### Cycle 24 — K19f Cycle ε [FE S] — Tap-target audit (K19f.5)

Closes the K19f cluster. Applied `TOUCH_TARGET_CLASS = 'min-h-[44px]'` to the 2 remaining mobile-shell links (MobileKnowledgePage privacy footer link + MobilePrivacyShell back link). Test assertions strengthened to import the constant and assert `className.toContain(TOUCH_TARGET_CLASS)` so a future refactor of the constant value (e.g. to Tailwind's `min-h-11` shorthand) stays lockable.

**Full tap-target inventory at K19f end**: GlobalMobile save (β) · ProjectsMobile toggle + Build (γ) · JobsMobile toggle + Pause/Resume/Cancel (δ) · MobileKnowledgePage privacy link (ε) · MobilePrivacyShell back link (ε). All interactive elements in mobile-rendered mobile-variant code ≥44px. Card spacing via `space-y-2` (8px), section spacing via `mb-8` (32px).

`/review-impl` caught **1 LOW + 2 COSMETIC; 1 COSMETIC fixed + 1 LOW deferred + 1 COSMETIC accepted**:
- **L1 → D-K19f-ε-01** PrivacyTab mobile audit gap. Renders on mobile via MobilePrivacyShell but its 4 buttons (Export, Delete, dialog Cancel, dialog Confirm) are ~26-30px tall. Deferred because PrivacyTab is desktop-shared — applying TOUCH_TARGET_CLASS unconditionally widens desktop buttons too. Future cycle picks between conditional (useIsMobile guard) or blanket (accept desktop cosmetic change).
- **C2** raw-string assertion in tests → import constant instead.
- **C3** no click-navigation test on Links → accepted as existing convention.

**K19f cluster 100% plan-complete** (α shell + β GlobalMobile + γ ProjectsMobile + δ JobsMobile + ε tap audit).

**Session 50 stats**:
- **24 cycles shipped** (22 Track 3 + 2 Track 2 close-out)
- All Track 3 K19-series clusters (K19a through K19f) now 100% plan-complete
- Front-end test coverage: **320 pass** at session 50 end (vs ~88 at session 47 end)
- Back-end test coverage: **1282 pass** at K19e γ-a (vs 1154 at session 47 end)

**What's next — Session 51 default path:**

Resume the **[Track 2/3 Gap Closure Plan](../03_planning/KNOWLEDGE_SERVICE_TRACK2_3_GAP_CLOSURE_PLAN.md)**. 18 cycles remain across P2→P5 tiers. P1 tier is **complete** (C1 ✅ + C2 ✅). Next default is C3 (P2 tier opens).

Next cycle — **C3 (P2, L)**: job_logs retention + richer lifecycle + tail-follow. Three items all in the `job_logs` surface (BE retention cron + orchestrator producer + FE tail-follow) — share a review pass. Detail in [plan §4 C3](../03_planning/KNOWLEDGE_SERVICE_TRACK2_3_GAP_CLOSURE_PLAN.md#c3--job_logs-retention--richer-lifecycle--tail-follow-p2-l).

**C2 aftermath — things to keep in mind for later cycles:**
- `trigger` label threaded through 5 files; any new caller of `regenerate_global_summary` / `regenerate_project_summary` / `/internal/summarize` should decide `"manual"` vs `"scheduled"` intentionally (default back-compat is `"manual"`)
- `_cooldown_client` is a module-level singleton in `app/routers/public/summaries.py` — if another endpoint needs a cooldown helper, refactor into `app/utils/redis_cooldown.py` first
- FakeRedis/BoomRedis/HalfBoomRedis stubs live inline in `test_public_summarize.py` — if C9 (entity concurrency) needs similar cooldown tests, hoist them to a shared fixture file
- Duration/cost/tokens counters intentionally stay 2-label (no `trigger` split) — revisit only if operator need emerges

Remaining cycles after C2 (grouped by tier):
- **P2 (C3–C9)** — 14 items / 7 cycles: job_logs observability trio · useProjectState hook tests · mobile polish · chapter-title resolution · ETA formatter · drawer-search UX · entity concurrency+unlock
- **P3 (C10–C13)** — 7 items / 4 cycles: timeline gaps · cursor pagination · scope+benchmark dialog · Storybook dialogs via MSW
- **P4 (C14–C15)** — 3 items / 2 cycles: resumable scheduler cursor state · Neo4j fulltext index (fire only at >10k entities)
- **P5 🏗 (C16–C18)** — 3 items / 3 cycles, all DESIGN-first: budget attribution · entity-merge canonical-alias mapping · event wall-clock date
- **User-gated ⏸ (C19–C20)** — multilingual fixtures (user provides text) + Gate-13 human walkthrough

**NOT the default path but possible if user redirects:**
- Continue Track 3 feature cycles (K19g-h, K21 tool calling, K22 privacy page)
- Gate-13 T2-close-2 walkthrough (user-attested BYOK run)
- Data re-engineering ([101_DATA_RE_ENGINEERING_PLAN](../03_planning/101_DATA_RE_ENGINEERING_PLAN.md))

**Starting-session boilerplate:**
1. Read [SESSION_PATCH.md](SESSION_PATCH.md) cycle-28 entry + the plan file's §3 cycle table
2. `./scripts/workflow-gate.sh status` to confirm previous cycle closed
3. Start C3 with `./scripts/workflow-gate.sh size L 8 5 1` then `phase clarify` (L because of retention cron + producer sites + FE tail-follow)
4. Infra: `docker ps --filter name=infra-` — Postgres + Redis + glossary-service must be healthy for integration tests; Neo4j only needed for Track 2 paths
5. For Postgres integration tests: `TEST_KNOWLEDGE_DB_URL=postgres://loreweave:loreweave_dev@localhost:5556/loreweave_knowledge` (NOT `postgres:*@knowledge`)
6. For Neo4j integration tests: `TEST_NEO4J_URI=bolt://localhost:7688 TEST_NEO4J_PASSWORD=loreweave_dev_neo4j`
7. For manual-curl verify, JWT gen one-liner: `python -c "import jwt,uuid,datetime; print(jwt.encode({'sub':str(uuid.uuid4()),'exp':datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=10)},'loreweave_local_dev_jwt_secret_change_me_32chars',algorithm='HS256'))"` → `curl -H "Authorization: Bearer $TOKEN" http://localhost:8216/...` (note: if Neo4j is down, regen paths will 500 — that's a known Track 1 limitation, unrelated to C2's cooldown behaviour)

---

### Cycle 23 — K19f Cycle δ [FE L] — JobsMobile (K19f.3)

Ships the third simplified mobile variant. Merged active+history sorted list (`STATUS_SORT_ORDER: running → paused → pending → failed → cancelled → complete`, within-status newer-first) with **Map-based dedup by job_id** (active wins on conflict — handles the 2s/10s poll transition race). Per card: project_name + colored status badge + progress bar (running/paused only) + Intl-formatted started_at. Tap → inline expand with items counters, timestamps, error message (failed only), action buttons per status. Actions: `pauseExtraction / resumeExtraction / cancelExtraction` with `stopPropagation` + `invalidateQueries(['knowledge-jobs'])` on success. **Dropped** per plan: CostSummary, per-status sections, JobDetailPanel, JobLogsPanel, retry-with-new-settings.

`/review-impl` caught **3 MED + 6 LOW + 1 COSMETIC; 3 MED + 5 LOW fixed in-cycle**:
- **M1** duplicate `key` React warning when same job_id appears in both active (2s poll, stale) + history (10s poll, fresh) during running→complete transition → Map dedup with active-wins-on-conflict + regression test.
- **M2** Resume + Cancel API paths completely untested — only Pause was exercised, so runAction's if/else-if/else branch swap would pass → 2 new tests clicking each + asserting correct mock called.
- **M3** `queryClient.invalidateQueries` contract untested (same gap class as ProjectsMobile refetch) → `vi.spyOn(QueryClient.prototype, 'invalidateQueries')` + assertions on all 3 actions + NOT-called on failure.
- **L4** stopPropagation batch coverage on Resume + Cancel · **L5** action-failure toast · **L6** project_name null fallback · **L7** same-status sort tiebreaker · **L9** historyError branch — all added.
- Accepted: **L8** progress-bar edge cases (BE data-error territory) · **C10** memoization `?? []` dep instability (minor perf).

**5th cycle in a row** `/review-impl` paid meaningful dividends. **M1 is notable** — it's a real production bug (React key collision + potential render drop), not just a coverage gap. The pattern of active+history merging should carry a dedup step any time the caller flattens them.

**What Cycle ε / final cycle inherits:**
- All 3 mobile variants (Global / Projects / Jobs) live
- `lib/touchTarget.ts` with `TOUCH_TARGET_CLASS` applied across mobile variants
- `components/mobile/` convention stable
- Stub pattern proven: data-testid buttons inside stubs expose swallowed callbacks
- `vi.spyOn(QueryClient.prototype, 'invalidateQueries')` pattern for verifying react-query contract

**Remaining K19f work:**
- **K19f.5** full tap-target audit across existing desktop components — sweep `grep -r 'py-1\|py-1.5\|h-6\|h-7'` for sub-44px interactive elements. Deferrals D-K19d-β-01 (EntitiesTable mobile grid) + D-K19e-β-02 (Timeline responsive) remain open but are hidden behind the desktop-only banner on mobile, so fixing them is not a K19f gate.

**Test deltas at δ end:**
- FE knowledge+pages vitest: **320 pass** (was 303 at K19f γ end; **+17** = 10 initial + 7 /review-impl regression)
- `tsc --noEmit` clean

---

### Cycle 22 — K19f Cycle γ [FE L] — ProjectsMobile (K19f.2)

Ships the second simplified mobile variant. Stacked card list reusing `useProjects(false)`: name + project_type badge + extraction_status badge (5-value raw status, NOT the 13-state machine) + description preview. Tap card toggles inline expand showing full description + Intl-formatted last_extracted_at + embedding_model + Build button (reuses existing BuildGraphDialog with `stopPropagation` keeping the card expanded). Dropped per plan: Create/Edit/Archive/Delete dialogs + all 13-state-machine action buttons.

`/review-impl` caught **1 MED + 4 LOW; all 5 fixed in-cycle**:
- **M1** `onStarted` → `refetch()` contract completely untested — initial BuildGraphDialog stub didn't expose the callback. Fixed by expanding stub with `simulate-build-started` button + regression test asserting `refetch` called.
- **L2** raw ISO `last_extracted_at` (same pattern K19e γ-b fixed for drawer created_at) → `Intl.DateTimeFormat` helper.
- **L3** empty-description fallback branch untested → test with `description: ''` asserts `noDescription` renders.
- **L4** truncate long-path untested → 200-char description test asserts `…` present + full 200-A's not present.
- **L5** `onOpenChange(false)` dialog-close path untested → stub exposes `simulate-close` button + regression test asserts dialog unmounts.

**Retro — 4th cycle in a row where /review-impl caught a stub-test coverage pattern.** The pattern is now clearly documented: test stubs for complex children should expose the callback props the parent contracts with, not just the render shape. A "happy div" stub that swallows callbacks hides the contract.

**What Cycle δ (JobsMobile) inherits:**
- `components/mobile/` convention established
- `lib/touchTarget.ts` with `TOUCH_TARGET_CLASS` constant applied to all interactive elements
- Stub pattern: expose callback props via `data-testid` buttons inside the stub so tests can drive them
- Keep desktop dialogs as-is (cramped but functional) unless mobile UX becomes painful
- i18n pattern: `mobile.<variantName>.*` sub-block + MOBILE_KEYS iterator extension per cycle

**Test deltas at γ end:**
- FE knowledge+pages vitest: **303 pass** (was 291 at K19f β end; **+12** = 8 core + 4 /review-impl regression)
- `tsc --noEmit` clean

---

### Cycle 21 — K19f Cycle β [FE L] — GlobalMobile (K19f.4) + tap-target utility

Ships the first simplified mobile variant. 150-line `GlobalMobile` keeps textarea + save + char count + unsaved badge; drops per plan: Reset, Regenerate, Versions, PreferencesSection, token estimate, version counter. **Keeps If-Match conflict handling** — dropping would let a mobile save silently stomp a desktop edit. NEW `lib/touchTarget.ts` exports `TOUCH_TARGET_CLASS = 'min-h-[44px]'` constant as K19f.5 audit groundwork; save button is first consumer. NEW `components/mobile/` directory (future home for ProjectsMobile + JobsMobile). MobileKnowledgePage swaps `<GlobalBioTab />` → `<GlobalMobile />`. 8 i18n keys × 4 locales.

`/review-impl` caught **1 HIGH + 2 LOW + 1 COSMETIC; all 4 fixed in-cycle**:
- **H1** 412 "regression test" used a plain-object mock error that failed `isVersionConflict`'s `err instanceof Error` type guard → took generic-error else branch, passed for wrong reason. Fixed via `makeConflictError` helper building a proper `Error` with `.status=412` and `.body={content,version}`, plus 2-click pattern asserting `expectedVersion` advances 3→4 on retry (STRONG signal the baseline absorbed).
- **L2** no assertion that `TOUCH_TARGET_CLASS` is applied to save → regression could ship 32px button; fixed with `expect(save.className).toContain('min-h-[44px]')`.
- **L3** whitespace-only save branch untested → added test verifying `"   "` → `{content: ''}` payload.
- **C4** `UseSummariesReturn = ReturnType<typeof useSummariesMock>` resolved to `undefined` → replaced with explicit `HookReturn` interface.

**Retro — third cycle in a row where /review-impl caught a test that passed for the wrong reason.** Pattern is now clear: any regression test that claims to lock a defensive branch must PROVE the branch ran (via observable downstream state change), not just that "the error path didn't crash."

**What Cycle γ (next) inherits:**
- `lib/touchTarget.ts` available — apply `TOUCH_TARGET_CLASS` to every interactive element in ProjectsMobile
- `components/mobile/` directory convention established
- i18n pattern: `mobile.<variantName>.*` sub-blocks + MOBILE_KEYS iterator extensions per-cycle
- MobileKnowledgePage swap pattern: replace desktop tab import with mobile variant, update test stub

**Test deltas at β end:**
- FE knowledge+pages vitest: **291 pass** (was 286 at K19f α end; **+5** = 4 GlobalMobile tests + 1 whitespace test; HIGH fix strengthened existing test without adding one)
- `tsc --noEmit` clean

---

### Cycle 20 — K19f Cycle α [FE L] — Mobile shell (K19f.1 MVP)

Opens the K19f Mobile UI cluster. NEW `useIsMobile` hook via `window.matchMedia('(max-width: 767px)')` with synchronous first-render read (no FOUC) + live `change` listener + SSR-safe guards + listener cleanup. NEW `MobileKnowledgePage` single-column shell: 3 stacked sections (Global bio / Projects / Extraction jobs) **reusing existing desktop tab components inline** + "use desktop for Entities/Timeline/Raw" banner + Privacy footer link. NEW `MobilePrivacyShell` renders just PrivacyTab body + back link — avoids the 7-tab desktop nav overflowing on <768px. KnowledgePage guard: `if (isMobile) { if (privacy) <MobilePrivacyShell /> else <MobileKnowledgePage /> }`.

`/review-impl` (user-invoked) caught **2 MED + 1 COSMETIC; both MEDs fixed in-cycle**:
- **M1** mobile + /knowledge/privacy fell through to desktop render shipping the 7-item tab nav → added `MobilePrivacyShell` component + dedicated mobile-privacy branch + `mobile.backToKnowledge` i18n × 4 + regression test asserting `queryByRole('tablist') === null`
- **M2** KnowledgePage had zero test coverage for the new mobile guard → created `pages/__tests__/KnowledgePage.test.tsx` with 4 branch tests (desktop / mobile-non-privacy / mobile-privacy / desktop-privacy) mocking `useIsMobile`
- **C3** mid-effect `setIsMobile(mql.matches)` is defensive-only no-op in production → accepted as documented

Scope-trim deferrals (from CLARIFY):
- **K19f.2/.3/.4** separate `ProjectsMobile/JobsMobile/GlobalMobile` simplified variants — MVP reuses existing tabs inline; build variants when the cramp becomes a real UX problem
- **K19f.5** tap-target audit (44px minimum) — do during Cycle β when mobile variants land
- **D-K19d-β-01 + D-K19e-β-02** mobile-responsive EntitiesTable + Timeline grids — those tabs are **hidden** on mobile via the desktop-only banner, so fixing their grids waits for mobile variants for those tabs

**What Cycle β (next) inherits:**
- `useIsMobile` hook + `MobileKnowledgePage` / `MobilePrivacyShell` components exist and are stable
- Embedded desktop tabs render inside sections — if ProjectRow / JobRow feel cramped at 375px, swap those for simpler mobile card variants
- Dialog `max-w-md` (448px) overflows on 375px phones — Radix pads the viewport but content may be squished; candidate for dialog-level responsive tweaks
- No automated tap-target coverage — K19f.5 audit is manual or via Playwright

**Test deltas at K19f α end:**
- FE knowledge vitest: **286 pass** (was 271 at K19e γ-b end; **+15** = 3 hook + 4 mobile-page [incl MobilePrivacyShell M1 regression] + 4 KnowledgePage + 4 iterator assertions)
- `tsc --noEmit` clean

---

### Cycle 19 — K19e Cycle γ-b [FE XL] — RawDrawersTab consuming γ-a endpoint

Ships the user-facing Raw drawers tab on top of γ-a's BE. NEW `useDrawerSearch` hook (userId-scoped queryKey per K19d β M1, disabled-gate via `project_id + query.length >= 3`, retry:false). NEW `DrawerResultCard` presentational with colored source-type badge (chapter/chat/glossary) + amber hub badge + Intl-clamped match-% + full a11y. NEW `DrawerDetailPanel` Radix slide-from-right mirroring K19d β EntityDetailPanel pattern with full text + metadata grid + `Intl.DateTimeFormat` on `created_at`. NEW `RawDrawersTab` container with **8 render branches** (no-project / no-query / short-query / loading / retryable-error+Retry / non-retryable-error+fix-config / not-indexed / empty / results) + 300ms debounce + retry-invalidates-prefix + `disabled={isFetching}` anti-double-fire.

**KnowledgePage swaps** `<PlaceholderTab name="raw" />` for `<RawDrawersTab />` **and removes PlaceholderTab + PlaceholderName entirely** — **every knowledge tab is now live**. The whole `placeholder.*` i18n block is deleted from all 4 locales, with a regression test asserting `bundle.placeholder === undefined`.

`/review-impl` (user-invoked) caught **3 LOW + 2 COSMETIC; ALL 5 fixed in-cycle**:
- **L1** no test proved 300ms debounce actually debounced rapid keystrokes (a regression to 0ms would have passed all 6 initial tests) → new test fires 5 rapid onChange events, asserts calls=1 with final query="bridge"
- **L2** `is_hub` field came over the wire but was never rendered → amber "Summary" badge on card + hub metadata row on detail panel + 4 new i18n keys × 4 locales
- **L3** raw ISO string in `created_at` → `formatCreatedAt` using `Intl.DateTimeFormat`
- **C4** redundant `&& queryActive` guard on `isLoading` (react-query's `enabled:false` already keeps it false) → removed
- **C5** error-banner could render empty string on oddly-shaped payloads → `?? t('drawers.unknownError')` fallback + new i18n key × 4 locales

Build-time catches: `jsx-a11y/button-name` lint on `<Dialog.Close asChild><button><X/></button></Dialog.Close>` (Radix merges props but lint doesn't see it) → moved `aria-label` + added `title` directly on the inner `<button>`; **fake-timers** for debounce test broke react-query's internal `setTimeout` causing cross-test cascade timeouts → switched to real timers + `waitFor`; initial project-dropdown tests fired `fireEvent.change` before `useProjects` options rendered (silent no-op) → added `selectProject` helper awaiting `findByRole('option')` first.

**What K19e Cycle γ-c / δ would inherit (if ever built):**
- Source-type filter UI on search — blocked on D-K19e-γa-01 BE fix
- Term highlighting in preview — D-K19e-γb-01
- Delete drawer (K19e.6), facts list + edit (K19e.7/.8) — separate BE work

**Test deltas at γ-b end:**
- FE knowledge vitest: **271 pass** (was 253 at K19e β end; **+18** = 3 hook + 7 tab incl debounce + 8 iterator assertions)
- `tsc --noEmit` clean

**K19e cluster 100% plan-complete** (K19e.1/.2/.3/.4/.5 shipped; K19e.6/.7/.8 deferred; K19e.9 i18n covered per-cycle; K19e.10 empty/loading states shipped).

---

### Cycle 18 — K19e Cycle γ-a [BE L] — Drawer search endpoint (K19e.5)

Opens the Raw-drawers sub-cluster. Ships the public `GET /v1/knowledge/drawers/search?project_id=&query=&limit=` endpoint — semantic search over `:Passage` nodes reusing proven K18.3 machinery 1-to-1 (no new Cypher). Server-side flow:

1. `ProjectsRepo.get(user_id, project_id)` → 404 on cross-user/missing
2. If project has no `embedding_model` → 200 `{hits:[], embedding_model:null}`
3. If `embedding_dimension` not in `SUPPORTED_PASSAGE_DIMS` → 200 empty
4. `embedding_client.embed(model_source="user_model", model_ref=project.embedding_model)` → 502 `{error_code:"provider_error", retryable:bool}` on `EmbeddingError`
5. Empty provider response (outer OR inner empty) → 200 empty
6. `find_passages_by_vector(include_vectors=False)` → `DrawerSearchHit[]`
7. 502 `{error_code:"embedding_dim_mismatch"}` if live-vs-stored dim disagree

CLARIFY-time scope trim:
- **D-K19e-γa-01** source_type filter (chapter/chat/glossary) — plan K19e.4 mentioned for FE tab layout; needs K18.3 `find_passages_by_vector` extended with new WHERE branch.
- **D-K19e-γa-02** drawer-search embed cost not tracked toward K16.11 monthly budget — hobby-scale $0.00002/search, real at scale.

`/review-impl` (user-invoked) caught **4 LOW + 1 COSMETIC; 3 fixed in-cycle + 1 deferred + 1 accepted**:
- **L1** mutable default arg in test helper (`_project_stub()` called at module load shared instance) → sentinel-guarded conditional assignment
- **L3** `retryable` flag on `EmbeddingError` was discarded → propagated onto 502 detail + paired regression tests for both True/False paths
- **L4** empty inner vector (`embeddings=[[]]`) fell through to `find_passages_by_vector` ValueError surfacing misleading `dim_mismatch` 502 → extended empty-short-circuit guard to `not result.embeddings or not result.embeddings[0]` + regression test
- **C5** no explicit test for `include_vectors=False` forwarding → added kwargs assertion
- **L2** deferred as D-K19e-γa-02

Build-time catches (all collection-error on first pytest run): `EmbedResult → EmbeddingResult` (wrong class name), `ProjectType.original → "book"` Literal (not enum), `ExtractionStatus.idle → "disabled"` Literal.

**What K19e Cycle γ-b (next) inherits:**
- `GET /v1/knowledge/drawers/search?project_id=&query=&limit=` → `{hits: DrawerSearchHit[], embedding_model: string | null}` (`hits` carries `id / project_id / source_type / source_id / chunk_index / text / is_hub / chapter_index / created_at / raw_score`)
- FE can render "not indexed yet" banner when `embedding_model === null`
- 502 `retryable: true` means show retry button; `false` means show "fix config" messaging
- `source_type` filter is UI-only today (client-side filter the returned `hits[].source_type`) OR pair with D-K19e-γa-01 BE fix
- Cycle γ-b scope: `useDrawerSearch` hook + `RawDrawersTab` container + `DrawerResultCard` (text preview + full-text slide-over click) + i18n + KnowledgePage swap for PlaceholderName='raw'

**Test deltas at γ-a end:**
- BE unit knowledge-service: **1282 pass** (was 1268 at K19e-α end; **+14** drawers)
- 63/63 router-adjacent unit pass (no regressions)

---

### Cycle 17 — K19e Cycle β [FE XL] — TimelineTab consuming α endpoint

FE consumer on top of Cycle α's BE. Ships the user-facing Timeline tab. New hook `useTimeline` (userId-scoped queryKey per K19d β M1, 30s staleTime, `enabled: !!accessToken`). New presentational `TimelineEventRow` with inline expand — event_order / title / chapter-short / up-to-3 participants chips + `+N more` overflow / confidence clamped to [0,100]. New container `TimelineTab` with project filter + prev/next pagination + loading/error/empty states + past-end escape hatch ("Back to first page" button when `total>0 && events=[] && offset>0`). KnowledgePage swaps PlaceholderTab for TimelineTab and narrows PlaceholderName to `'raw'` only. 20 i18n keys × 4 locales + `placeholder.bodies.timeline` removed from all 4 locales + TIMELINE_KEYS iterator locks both additions AND removal.

`/review-impl` caught **1 MED + 3 LOW + 2 COSMETIC, all fixed in-cycle:**
- **MED** pagination prev/next were untested — added 3 tests: Next advances offset, Prev re-disables at offset=0, Prev/Next both disabled when total fits one page.
- **L2** no `enabled: !!accessToken` regression test — added `renderHook` with `accessToken: null` asserting mock never called.
- **L3** `formatConfidence` didn't clamp to [0,100] — `Math.max(0, Math.min(100, pct))` defense vs data drift.
- **L6** stale-offset race when total shrinks below offset — added escape-hatch button + new `timeline.pagination.backToFirst` i18n key × 4 locales.
- **COSMETIC #4** duplicate `data-testid="timeline-event"` on outer `<li>` — removed.
- **COSMETIC #5** `_eventStub` underscore prefix misleading — renamed `EVENT_STUB`.

Build-time catches: `aria-expanded={boolean}` lint → switched to explicit `'true'|'false'` string; pagination tests initially used `mockClear()` + call-count assertions that raced with react-query's in-flight resolution → rewrote to assert DOM state transitions (Prev button disabled/enabled) which tests the actual user-visible contract.

**What Cycle γ (the next K19e piece) now inherits:**
- Range inputs for `after_order` / `before_order` can drop straight into TimelineTab — the hook already accepts them.
- Entity-scope drill-down requires BE work first (D-K19e-α-01 deferral).
- Chapter title resolution still shows raw UUID short form (D-K19e-β-01).
- Raw drawers tab is the next FE-only big piece (K19e.4+).

**Test deltas at K19e Cycle β end:**
- FE knowledge vitest: **253 pass** (was 232 at K19d γ-b end; **+21** = 4 hook + 9 tab + 8 iterator/placeholder-removal)
- `tsc --noEmit` clean

---

### Cycle 16 — K19e Cycle α [BE L] — Timeline list endpoint (K19e.2)

Opens the K19e Timeline + Raw-drawers cluster. BE foundation only; β ships the FE TimelineTab consuming this endpoint. CLARIFY-time scope trim:

- Shipped: `GET /v1/knowledge/timeline?project_id=&after_order=&before_order=&limit=&offset=` → `{events, total}`. JWT user-scoped, archived excluded, 2-query count+page split (O(limit) memory), stable pagination via `title ASC, id ASC` tiebreaker, 422 on reversed range.
- **D-K19e-α-01** `entity_id` filter deferred — `:Event.participants` stores display names; needs entity lookup. Natural fit for Cycle β/γ when FE drill-down lands.
- **D-K19e-α-02** ISO wall-clock `from`/`to` deferred — :Event has no date field; narrative `event_order` is the MVP axis.
- **D-K19e-α-03** `chronological_order` range deferred — let Cycle β FE decide if two-axis toggle is worth the UX.

`/review-impl` (user-invoked before COMMIT) caught **3 LOW** findings, all fixed in-cycle:
- **L1** integration test `_limit_clamped_to_max` seeded only 5 events so a removed clamp would still pass — replaced with 2 unit tests patching `run_read` to assert the exact `$limit` kwarg forwarded to Cypher (both clamp-fires and pass-through branches).
- **L2** no `event_user_project (user_id, project_id)` composite index on :Event even though `entity_user_project` exists — added to `neo4j_schema.cypher`, cleared **P-K19e-α-01**.
- **L3** unused `logger = logging.getLogger(__name__)` in `timeline.py` (read-only endpoint) — removed.

**What Cycle β (FE) now inherits:**
- `knowledgeApi.listTimeline({ projectId, afterOrder, beforeOrder, limit, offset })` wrapper to write.
- `{events: Event[], total: number}` response shape.
- `Event` type mirrors the BE Pydantic — re-use the K19d `Entity` pattern (fields: id, title, chapter_id, event_order, participants, summary, confidence, evidence_count, mention_count).
- 422 on reversed range → surface as toast + clear range input.
- No entity drill-down on BE yet — FE table can list entity names but can't filter by them.
- Schema index exists; project-scoped browse is cheap.

**Test deltas at K19e Cycle α end:**
- BE unit knowledge-service: **1268 pass** (was 1258 at K19d γ-b end; +10 net = 11 timeline - 1 weak integration test deleted)
- BE integration timeline: **11/11 live** against `infra-neo4j-1`
- 23/23 K11.7 events adjacent no regressions
- 49/49 router-adjacent no regressions from `main.py` change

---

## Session 50 — 15 cycles shipped (13 Track 3 + 2 Track 2 close-out) · K19b + K19c + K20 + K19d all 100% plan-complete

```
Track 3 K19b progress (session 50)

Cycle 1  K19b.1 + K19b.4    User-scoped jobs endpoint + hook + JobProgressBar    1c208ce + c79ea90
                            BE: list_all_for_user repo + GET /v1/knowledge/extraction/jobs
                            FE: listAllJobs, useExtractionJobs hook (2s/10s dual-poll),
                                JobProgressBar (6 statuses, indeterminate, Intl USD format)

Cycle 2  K19b.2 + K19b.7-    ExtractionJobsTab + project_name + jobs.* i18n      4fb8b62
         partial             BE: ExtractionJob +project_name + LEFT JOIN
                             FE: ExtractionJobsTab (4 sections, native <details>,
                                 per-group error banners, JobRow with fallback),
                                 jobs.* keys × 4 locales, KnowledgePage wired

Cycle 3  K19b.3 + K19b.5 +   JobDetailPanel (slide-over) + Retry + ETA           5e00f7b
         ETA                 FE-only. NEW useJobProgressRate (EMA hook, α=0.3,
                             60s stale-reset, module-scoped Map<jobId> shared
                             across hook instances). NEW JobDetailPanel (Radix
                             slide-from-right, metadata grid, Pause/Resume/Cancel
                             actions, error block, conditional Retry CTA). MOD
                             BuildGraphDialog +initialValues prop for retry
                             pre-fill. MOD ExtractionJobsTab wires row click
                             (role=button + Enter/Space), panel + retry state
                             (R1 single retryIntent, R2 close panel on retry,
                             R3 retry only for status=failed). +17 i18n keys
                             × 4 locales. Clears D-K19b.4-01 (ETA).

Cycle 4  K16.12 completion   Track 2 close-out. User-wide budget API.            b313c1b

Cycle 5  K19b.6 + D-K19a.5-03 CostSummary card + monthly-remaining hint           32a9a18

Cycle 6  D-K16.11-01         Wire budget helpers into production                 c9f7064
         [BE M]               extraction.py step 2.6 calls can_start_job +
                              check_user_monthly_budget with estimated_cost =
                              max_spend_usd ?? 0; 409 structured detail
                              (monthly_budget_exceeded / user_budget_exceeded).
                              worker-ai runner.py +_record_spending inline
                              helper (CASE-on-current_month_key rollover) +
                              called after every successful chapters / chat
                              extraction. Production current_month_spent_usd
                              now populates as jobs run → CostSummary card
                              finally shows real prod spending.

Cycle 7  K19b.8               Extraction-job log viewer MVP                       526533d

Cycle 8  K19c Cycle α          BE preload: user-scope entities endpoint           a619b5f

Cycle 15 K19d Cycle γ-b        Merge endpoint + FE edit/merge dialogs             c9aaf95
         [FS XL]                BE: merge_entities helper + MergeEntitiesError
                                with 4 codes (same_entity/entity_not_found/
                                entity_archived/glossary_conflict) + 6 Cypher
                                blocks (load/validate, collect both-direction
                                edges, UNWIND batch MERGE with Python-driven
                                relation_id recomputation, EVIDENCED_BY
                                rewire on job_id, target metadata update with
                                glossary pre-clear to dodge UNIQUE constraint,
                                DETACH DELETE source, Python post-dedupe).
                                NEW POST /v1/knowledge/entities/{id}/
                                merge-into/{other_id} with 400/404/409 error
                                envelope. FE: NEW useUpdateEntity + useMerge
                                Entity hooks with closed-union error codes +
                                source detail cache eviction on merge. NEW
                                EntityEditDialog (name/kind/aliases textarea
                                with trim+dedupe + no-op skip). NEW
                                EntityMergeDialog with search-to-select
                                target picker (reuses useEntities, filters
                                out source, FE min-2-char). EntityDetailPanel
                                gets Edit/Merge icon buttons + mounted child
                                dialogs. 37 i18n keys × 4 locales + ENTITIES
                                _KEYS iterator +148 cross-locale assertions.
                                /review-impl caught H1 (source self-relation
                                silently dropped — rewired then cascade-
                                deleted) fixed in-cycle with regression test.
                                M1/M2/M3 deferred (D-K19d-γb-01 ON MATCH
                                union gap, D-K19d-γb-02 non-atomic multi-
                                write, D-K19d-γb-03 post-merge canonical_id
                                mismatch — fundamental architectural).
                                Build-time fix: UNIQUE(glossary_entity_id)
                                violation when both source and target
                                transiently held same anchor → clear source
                                first in same SET statement. BE unit 1258
                                (+5 merge routes). Integration 23/23 live
                                (+9 merge scenarios). FE knowledge 232 (+14
                                = 5 hook + 5 edit + 4 merge dialog). tsc
                                clean; no unhandled rejections after wrapping
                                mutation calls in try/catch. K19d cluster
                                100% plan-complete. K19d.8 graph viz stays
                                optional per plan.

Cycle 14 K19d Cycle γ-a        PATCH entity + user_edited lock [BE half of γ]    5d42afd + db405f6
         [BE L]                 Entity.user_edited: bool = False + _MERGE_ENTITY_
                                CYPHER ON CREATE user_edited=false + ON MATCH
                                aliases CASE coalesce(user_edited,false)=true
                                gate (coalesce handles pre-γ-a nodes as
                                un-edited so existing extraction preserved).
                                NEW update_entity_fields helper + _UPDATE_ENTITY
                                _FIELDS_CYPHER per-field CASE (null=leave,
                                else overwrite) + canonical_name recomputed on
                                name change. NEW PATCH /v1/knowledge/entities/
                                {id} endpoint with EntityUpdate Pydantic:
                                at-least-one model_validator + per-alias
                                non-empty + ≤200 char + max 50. 404 on
                                cross-user/missing. Merge (K19d.6) split to
                                γ-b because RELATES_TO edges carry deterministic
                                IDs derived from subject_id → per-edge MERGE-
                                new+DELETE-old surgery is complex enough for
                                its own cycle. /review-impl L1 fixed (inline
                                // Cypher comments were first-in-codebase →
                                moved to Python #); M1 (no If-Match optimistic
                                concurrency, D-K19d-γa-01) + M2 (no unlock
                                mechanism for user_edited, D-K19d-γa-02)
                                deferred. Build-time catch: "The Phoenix" test
                                variant didn't hit ON MATCH branch because
                                "the" isn't in HONORIFICS strip list → switched
                                to "Master Phoenix" (master is stripped →
                                same canonical_id). BE unit 1253 (+4).
                                Integration entities browse 14/14 live (+4
                                γ-a scenarios incl user_edited-lock regression
                                + pre-γ-a regression). K19d γ-b (merge + FE
                                edit/merge dialogs + CTAs + i18n, ~12 files XL)
                                is the only K19d work remaining.

Cycle 13 K19d Cycle β          Entities tab FE (table + detail panel)            aeb008b + c920d95
         [FE XL]                NEW useEntities + useEntityDetail hooks (userId-
                                scoped queryKeys per review-impl M1, 30s/10s
                                staleTime). NEW EntitiesTable presentational
                                (a11y: role=row + tabIndex + onKeyDown for
                                Enter/Space). NEW EntityDetailPanel Radix Dialog
                                slide-from-right (metadata grid + aliases chips
                                + relations partitioned outgoing/incoming with
                                per-row ↗/↙ arrows + truncation banner +
                                pending-validation badge). NEW EntitiesTab
                                container with debounced search (300ms + FE
                                min-2-chars matching BE 422) + prev/next
                                pagination capped at maxOffset + offset-reset
                                on filter change. KnowledgePage replaces
                                PlaceholderTab with EntitiesTab. 38 i18n keys
                                × 4 locales (placeholder.bodies.entities
                                removed everywhere — same pattern as K19b.2
                                jobs removal). ENTITIES_KEYS iterator +152
                                cross-locale assertions. /review-impl caught
                                M1 (cross-tenant cache flash — 30s window
                                where logout→login swap shows prior user's
                                cached entities before refetch); fixed with
                                userId-prefixed queryKey + regression test.
                                M2 (mobile grid breaks <800px) deferred as
                                D-K19d-β-01 (K19f scope). Build-time fixes:
                                useDebounced with useMemo (leak) → useEffect;
                                useProjects.items not .projects. FE knowledge
                                218 (+15). tsc clean. K19d γ (edit/merge)
                                remains the only K19d work left.

Cycle 12 K19d Cycle α          Entities browse + detail BE [α of β/γ split]      96f9b6b + e0fbd21
         [BE L]                 NEW entities_router at /v1/knowledge prefix +
                                2 JWT-scoped endpoints: GET /entities (filters:
                                project_id/kind/search min-2ch/limit/offset) +
                                GET /entities/{id}. New neo4j repo funcs:
                                list_entities_filtered (2-query count+page split
                                per review-impl M1 for O(limit) memory) +
                                get_entity_with_relations (OPTIONAL MATCH +
                                collect-inside-subquery for 0-relations case).
                                EntityDetail Pydantic reuses existing Relation
                                subject/object projection. Anti-leak: cross-user
                                detail 404 per KSA §6.4. /review-impl caught
                                M1 (pagination materialized full tenant row-set
                                in memory to count) + L1 (entity_id Path had
                                no length cap); both fixed in-cycle with
                                regression tests. Build-time bug: plain CALL
                                subquery with MATCH drops outer row when inner
                                has 0 rows — fixed with OPTIONAL MATCH + collect
                                inside. BE unit 1249 (+10). Integration entities
                                browse 10/10 live. β (FE EntitiesTab + detail
                                panel) + γ (edit/merge) pending. P-K19d-01
                                logged (Neo4j fulltext index when entity count
                                crosses ~10k per user).

Cycle 11 K20 Cycle β+γ         FE consumer + metrics + dup check [K20 complete]   9289ded + 166c9e1
         [FS XL]                BE: metrics.py +4 series (regen_total{scope_type,
                                status}×12 pre-seeded labels + duration histogram
                                + cost_usd + tokens). regenerate_summaries.py
                                split into outer metrics wrapper + inner logic
                                (every status branch bumps counter once); +step
                                6b past-version dup check via list_versions(
                                limit=20) + same 0.95 jaccard threshold;
                                +_compute_llm_cost_usd helper + happy-path
                                cost/token recording. +8 unit tests. FE: NEW
                                useRegenerateBio hook with parseRegenerateError
                                closed-union errorCode from body.detail
                                .error_code + invalidates [SUMMARIES_KEY +
                                VERSIONS_KEY]; NEW RegenerateBioDialog reusing
                                BuildGraphDialog's ['ai-models', 'chat']
                                queryKey for cache share + inline banner for
                                user_edit_lock + distinct toasts for
                                concurrent/guardrail/provider/unknown + info
                                toast for similarity/empty-source. api.ts
                                +RegenerateRequest/Response + regenerateGlobalBio
                                wrapper. GlobalBioTab +Regenerate button
                                disabled={dirty} per review-impl H1 (without
                                guard the existing dirty-protection useEffect
                                would silently preserve local buffer over a
                                successful server regen). 21 new i18n keys ×
                                4 locales + GLOBAL_KEYS extension (+84 cross-
                                locale assertions). /review-impl caught H1
                                (dirty-textarea race), M1 (queryKey
                                fragmentation with BuildGraphDialog), L1
                                (dialog test coverage gap on 3 error paths);
                                all fixed in-cycle. BE unit 1239 (+8). FE
                                knowledge 203 (+13 = 5 hook + 8 dialog).
                                Drift integration 6/6 still live. K20 cluster
                                effectively complete — only K20.3 scheduler
                                + D-K20α-01 budget-integration half +
                                D-K20α-02 per-scope cooldown remain deferred.

Cycle 10 K20 Cycle α           BE regen helpers + public edge [unblocks K19c.2]   71530a1 + 5faaf08
         [BE L]                 NEW app/jobs/regenerate_summaries.py with 6-status
                                RegenerationResult (regenerated / no_op_similarity
                                / no_op_empty_source / no_op_guardrail /
                                user_edit_lock / regen_concurrent_edit) per KSA
                                §7.6. Drift rules: reads raw :Passage text not
                                current summary; 30-day manual-edit lock;
                                diversity check via word-set jaccard > 0.95; K20.6
                                MVP guardrails (empty / token_overflow / K15.6
                                injection) rejecting LLM output. NEW internal
                                endpoint `POST /internal/summarize` +
                                public edges `POST /v1/knowledge/me/summary/
                                regenerate` + `POST /v1/knowledge/projects/{id}/
                                summary/regenerate` (both JWT-scoped; 200/409/
                                422/502 HTTP mapping). /review-impl caught:
                                **H1** every regen wrote history as edit_source=
                                'manual' which would trip the 30-day edit lock
                                on the NEXT regen (fixed: EditSource Literal +
                                migration CHECK + SummariesRepo.upsert kwarg all
                                gain 'regen'; regen helper passes it); **M1** no
                                upfront ownership check on project scope (fixed:
                                `_owns_project` SELECT before LLM call).
                                Deferred: K20.3 scheduler, K20.5 rollback
                                endpoint, K20.7 metrics, D-K20α-01 cost
                                tracking, D-K20α-02 per-scope cooldown.
                                BE unit 1231 (was 1195; +36). Drift integration
                                6/6 live against infra-postgres-1 + infra-neo4j-1.

Cycle 9  K19c Cycle β          FE K19c-partial: reset + diff + preferences        8baa670 + 79503f2
         [FE XL]               Installed diff@^9 + @types/diff@^7. api.ts +Entity
                               type + list/archive wrappers. NEW useUserEntities
                               hook. NEW PreferencesSection (list + confirm +
                               archive + prefix-match invalidation with
                               docstring per review-impl L7). GlobalBioTab:
                               +token estimate (chars/4) + Reset button + confirm
                               dialog + <PreferencesSection/> wire below editor.
                               VersionsPanel preview modal: "Show diff vs current"
                               toggle rendering diffLines() chunks with
                               added/removed/context colour classes; useEffect
                               resets toggle per preview. +global.* i18n (26 new
                               keys × 4 locales). GLOBAL_KEYS iterator added
                               (104 cross-locale assertions). Mid-verify fix:
                               static vi.mock factory for useAuth tripped
                               vitest-2 unhandled-rejection detection on one hook
                               error test; switched to dynamic vi.fn() pattern
                               (matches useUserCosts working pattern). Review-impl
                               L7 fixed in-cycle (queryKey prefix-match docstring).
         [BE L]                 list_user_entities(scope='global') Neo4j helper +
                                GET /v1/knowledge/me/entities?scope=global +
                                DELETE /v1/knowledge/me/entities/{id} (reuses
                                archive_entity, idempotent per RFC 9110). Unblocks
                                K19c.4 FE in Cycle β. Prior audit found:
                                K19c.2 still BLOCKED on K20.x; K19c.1/.3 have
                                partial Track 1 coverage (GlobalBioTab +
                                VersionsPanel); this cycle strictly scopes to the
                                missing BE surface. /review-impl L6 caught
                                DELETE docstring lie about non-idempotent 404
                                (fixed + integration test locks contract).
         [FS XL]               BE: NEW job_logs table (BIGSERIAL + CHECK level +
                               FK CASCADE) + JobLogsRepo (append + cursor list)
                               + GET /v1/knowledge/extraction/jobs/{id}/logs
                               with since_log_id/limit pagination + 404 on
                               cross-user. Worker: _append_log inline helper +
                               5 lifecycle call sites (chapter_processed,
                               chapter_skipped, retry_exhausted, auto_paused,
                               failed). FE: listJobLogs API + useJobLogs hook
                               (staleTime 10s single-page) + NEW JobLogsPanel
                               collapsible inside JobDetailPanel. jobs.detail.
                               logs.* × 4 locales. 3 follow-up deferrals:
                               D-K19b.8-01 retention cron, D-K19b.8-02
                               orchestrator-side logs, D-K19b.8-03 tail-follow.
         [FE XL]              FE-only. NEW useUserCosts hook (staleTime 60s,
                              user_id-scoped queryKey). NEW CostSummary.tsx
                              with inline EditBudgetDialog (decimal regex
                              matches BE NUMERIC(10,4), progress bar colors
                              at 80%/100% thresholds). NEW shared
                              lib/formatUSD.ts after /review-impl caught
                              inconsistent formatting between CostSummary +
                              BuildGraphDialog. Wired into ExtractionJobsTab
                              top. BuildGraphDialog renders monthly-remaining
                              hint near max_spend via useUserCosts (clears
                              D-K19a.5-03). +17 costSummary.* keys + 1
                              maxSpend.monthlyRemaining × 4 locales.
         [BE L]              NEW user_knowledge_budgets table + UserBudgetsRepo
                             (get+upsert). Extended UserCostSummary response
                             with monthly_budget_usd + monthly_remaining_usd
                             (clamped >=0). NEW PUT /v1/knowledge/me/budget
                             endpoint (ge=0, null clears). NEW
                             check_user_monthly_budget helper in budget.py
                             (aggregates across user's projects, stale-month
                             filter). NEW idx_knowledge_projects_user_all
                             covering index for archived-inclusive scans.
                             Unblocks D-K19a.5-03 (monthly budget remaining
                             context in BuildGraphDialog). K19b.6 now has
                             everything it needs on the BE side.

Remaining K19 residuals: K19b.7-rest (other tabs' strings); K19c
                        partial (Cycle α shipped BE; Cycle β ships FE
                        deltas); K19d Entities tab (can reuse entities
                        endpoint pattern from Cycle α); K19e Raw tab.
                        K19b 100% PLAN-COMPLETE.
                        K19c.2 Regenerate still BLOCKED on K20.x.
```

**Test deltas at session 50 end (after 9 cycles):**
- Frontend knowledge: **190 pass** (was 112 at session 49 end; +78 over 6 FE cycles)
- Backend unit knowledge-service: **1195 pass** (was 1154 at session 49 end; +41 — no BE in Cycle 9)
- Backend unit worker-ai: **17 pass** (was 13 at K19b.6 end; +4 across Cycles 6+7)
- Backend integration: 30 extraction_jobs_repo + 5 user_knowledge_budgets + 5 job_logs + **6 list_user_entities** (new this cycle, against live Neo4j)
- Cycle 1 /review-impl: 5 LOW all fixed + 1 MED via review-code
- Cycle 2 review-code: 1 LOW fixed; /review-impl: 4 LOW all fixed
- Cycle 3 review-code: 2 LOW fixed; /review-impl skipped per human approval
- Cycle 4 review-code: 3 LOW accepted; /review-impl: 3 LOW all fixed
- Cycle 5 review-code: 1 LOW fixed; /review-impl: 1 LOW fixed
- Cycle 6 review-code: 10 LOW all accepted; /review-impl skipped per human approval
- Cycle 7 review-code: 1 LOW fixed; /review-impl skipped per human approval
- Cycle 8 review-code: 4 LOW accepted; /review-impl: 1 MED-doc fixed (DELETE idempotent-docstring lie + integration lock-in)
- Cycle 9 review-code: 6 LOW accepted; /review-impl: 1 LOW fixed (prefix-match queryKey invalidation docstring)

**What shipped in Cycle 3 (10 files, FE-only):**
- NEW `useJobProgressRate.ts` hook (EMA rate tracker, 6 tests)
- NEW `JobDetailPanel.tsx` (Radix slide-over with metadata grid + Pause/Resume/Cancel + conditional Retry, 6 tests)
- MOD `BuildGraphDialog.tsx` (+`initialValues` prop for retry pre-fill, +1 test)
- MOD `ExtractionJobsTab.tsx` (selectedJobId + retryIntent state, JobRow role=button + Enter/Space, retry getProject useQuery with error toast, +3 tests)
- MOD 4 locales (+17 `jobs.detail.*` + `jobs.retry.button` keys each)
- MOD `projectState.test.ts` (JOBS_KEYS +17 paths → 31 × 4 = 124 cross-locale assertions)

### What K19b.8 (next cycle candidate) can assume

**K19b.8 Log viewer** — standalone cycle, not blocked. Scope:
- BE schema: `job_logs(log_id BIGSERIAL PK, job_id UUID FK, user_id UUID, level TEXT, message TEXT, context JSONB, created_at TIMESTAMPTZ)` + index `(user_id, job_id, log_id DESC)` + retention cron (N days).
- Extraction-worker instrumentation at every chunker/extractor/error-path in `services/worker-ai/app/runner.py` keyed by `(user_id, job_id)`. Likely easiest via a custom Python logging handler that writes to the table.
- Public endpoint: `GET /v1/knowledge/extraction/jobs/{id}/logs?since_log_id=&limit=50` with cursor pagination.
- FE: `JobLogsPanel` inside `JobDetailPanel` (or new tab). Tail-follow with auto-scroll toggle. Virtual list for 1000+ lines.
- Size estimate XL; doable as a single cycle or split into BE + FE halves.

### What K19c Cycle β now ships (and what's still blocked)

K19c cluster is plan-complete except K19c.2 (regenerate). GlobalBioTab now
exposes token estimate + Reset button (server-side clear with confirm +
If-Match conflict handling). VersionsPanel preview modal has a diff-vs-current
toggle. New PreferencesSection component below the editor lists global
entities with delete-via-archive flow. See [SESSION_PATCH.md §Current Active
Work](SESSION_PATCH.md#current-active-work) for the detailed file list.

**K19c.2 still blocked on K20.x** — regenerate dialog can't land until K20
ships the `POST /internal/summarize` endpoint plus a public edge for it.

### Historical note — What K19c Cycle β initially assumed (now shipped)

Cycle α shipped the BE. Cycle β consumes:
- **GET** `/v1/knowledge/me/entities?scope=global&limit=50` → `{entities: Entity[]}` (Pydantic from `app/db/neo4j_repos/entities.py::Entity` — fields include `id`, `user_id`, `project_id: null`, `name`, `canonical_name`, `kind`, `aliases`, `confidence`, `updated_at`).
- **DELETE** `/v1/knowledge/me/entities/{entity_id}` → `204` on archive; `404` on cross-user / missing entity. **Idempotent** per RFC 9110 — second DELETE also returns 204.
- Query params validated: `scope: Literal['global']` (422 on invalid), `limit: int` ge=1 le=`ENTITIES_MAX_LIMIT=200`.

Cycle β scope (previously estimated XL, now trimmed by α):
- FE `api.ts`: `Entity` type + `listMyEntities` + `archiveMyEntity` wrappers
- NEW `hooks/useUserEntities.ts` with react-query staleTime pattern
- `GlobalBioTab.tsx`: +Reset button (confirm → clear to empty) + token estimate under char count (simple `content.length / 4` heuristic)
- `VersionsPanel.tsx`: diff viewer in preview modal (install `diff` npm ~4KB or inline line-diff)
- NEW `components/PreferencesSection.tsx`: renders global entities with delete confirm; wires into GlobalBioTab
- Tests + i18n × 4 locales

Cycle β is still ~L-XL; splitting it further if needed.

### K19b 100% plan-complete status

All 8 K19b tasks shipped this session:
- **K19b.1** ✅ (Cycle 1) — user-scoped jobs endpoint + hook
- **K19b.2** ✅ (Cycle 2) — ExtractionJobsTab layout
- **K19b.3** ✅ (Cycle 3) — JobDetailPanel slide-over
- **K19b.4** ✅ (Cycle 1) — JobProgressBar
- **K19b.5** ✅ (Cycle 3) — Retry with different settings
- **K19b.6** ✅ (Cycle 5) — CostSummary card
- **K19b.7-partial** ✅ (all cycles) — jobs.* i18n keys × 4 locales
- **K19b.8** ✅ (Cycle 7) — extraction-job log viewer MVP

**Integration state of the Jobs tab:**
- CostSummary reads real production `current_month_spent_usd` (wired in Cycle 6 via worker `_record_spending`).
- Budget-cap pre-check blocks jobs that would exceed per-project or user-wide monthly caps (Cycle 6).
- JobDetailPanel surfaces 5 lifecycle events via JobLogsPanel (chapter_processed, chapter_skipped, retry_exhausted, auto_paused, failed) alongside progress bar, metadata grid, error block, actions, and conditional retry CTA.
- ETA rendered via client-side EMA (Cycle 3).

**Follow-up polish deferrals** (none block shipping the Jobs tab):
- D-K19b.1-01 cursor pagination when user has >200 historical jobs
- D-K19b.2-01 "Show more" on Complete section
- D-K19b.3-01 human-readable "current item" from cursor
- D-K19b.3-02 humanised ETA formatter for >60min jobs
- D-K19b.8-01 retention cron for job_logs
- D-K19b.8-02 orchestrator-side pipeline logs (chunker/extractor stages)
- D-K19b.8-03 tail-follow auto-polling + load-more in JobLogsPanel

### What K19b.3 (detail panel) already ships — for future cycles consuming it

- `ExtractionJobsTab` rows are presentational, no click handler yet. Add `onClick` to `JobRow`, wire `role="button"` + `tabIndex={0}` + `onKeyDown` for Enter/Space.
- Single-job BE endpoint exists: `GET /v1/knowledge/extraction/jobs/{job_id}` (K16.5, session 47). Supports If-None-Match for 304. Returns `ExtractionJobWire` shape (including `project_name` — **wait**, no: K19b.2's `project_name` only populates via `list_all_for_user`'s LEFT JOIN. The single-job route still returns NULL for it). K19b.3 either (a) passes project_name through from the parent row (simplest, already fetched), (b) enhances the single-job endpoint to JOIN too, or (c) fetches the Project separately. Option (a) is zero-BE.
- `useExtractionJobs` exposes active + history lists. K19b.3's slide-over can look up the clicked job from that list without a second fetch (until poll staleness matters; within 2–10s the list data is fresh enough).
- Slide-over pattern: reuse shadcn `Sheet` component if present; else adapt the `Dialog` pattern from K19a.5 BuildGraphDialog. Keep state in `ExtractionJobsTab` (selectedJobId + onClose), not global.
- Retry CTA (K19b.5) goes INSIDE the slide-over on failed/cancelled jobs: button "Retry with different settings" opens BuildGraphDialog with the failed job's scope/model pre-filled. K19a.5's dialog accepts `initialValues` — verify shape matches.

### What the hook `useExtractionJobs` provides (unchanged from Cycle 1)

- Returns `{ active, history, isLoading, error, activeError, historyError }`.
- Polling: 2s active / 10s history (not-in-background via React Query default). Tab owns no timer logic.
- queryKey scoped `['knowledge-jobs', userId, 'active'|'history']` so logout→login on a shared QueryClient doesn't leak cross-user cache.
- Brief ≤10s transition gap when a job flips `running → complete` between the 2s active poll and the 10s history poll — job temporarily absent from both lists. Acceptable; `ExtractionJobsTab` doesn't mask today but K19b.3 could invalidate `['knowledge-jobs', userId, 'history']` from actions that transition jobs to terminal states.

### K19b.2 i18n boundary

- `knowledge.json` under `jobs.*` holds all K19b.2 strings (`loading`, `error.{active,history}`, `sections.*.{title,empty}`, `row.{started,completed,unknownProject}`).
- JOBS_KEYS iterator in `projectState.test.ts` neutralises the global `react-i18next` mock bypass: 14 paths × 4 bundles = 56 runtime assertions that each locale has the key populated. Any new jobs.* key needs to be appended to `JOBS_KEYS` at test-authoring time.
- `placeholder.bodies.jobs` removed from all 4 locales (the jobs tab is live; placeholder no longer reached). If someone re-introduces a placeholder state for jobs, add the key back.

### Schema-recovery lesson (session 50 Cycle 2)

The `test_k19b_2_list_all_project_name_null_when_join_misses` test initially used `ALTER TABLE DROP CONSTRAINT ... / ADD CONSTRAINT ...` to orphan a row. A mid-test failure left the DB with the FK removed AND orphan extraction_jobs rows, which meant the pool fixture's `TRUNCATE knowledge_projects CASCADE` couldn't cascade-clean extraction_jobs (no FK to cascade through), and the next run tried to re-ADD the FK against orphan data and failed. Manual recovery: `TRUNCATE extraction_jobs CASCADE` + `ALTER TABLE extraction_jobs ADD CONSTRAINT extraction_jobs_project_id_fkey FOREIGN KEY (project_id) REFERENCES knowledge_projects(project_id) ON DELETE CASCADE`. Rewritten test uses `SET LOCAL session_replication_role = 'replica'` in a transaction — skips FK triggers for writes inside that transaction only, never touches schema, auto-reverts on commit/rollback, zero leak on failure. **Takeaway for future cycles:** avoid DDL (ALTER) in tests when DML-level bypass is available. `session_replication_role`, `DEFERRABLE INITIALLY DEFERRED` constraints, and `DISABLE TRIGGER` (within a transaction) are all safer.

### FS-cycle audit lesson (K19b.1)

The CLARIFY-phase BE audit (per `feedback_fe_draft_html_be_check.md`) caught the user-scoped-list gap before any FE was drafted. Options presented were:
- (a) Reclassify to FS, add new endpoint — chosen
- (b) Expose `list_active` at HTTP layer only, defer history
- (c) Pure-FE N-fanout across `listProjects` + per-project `listExtractionJobs`

Option (a) won because K19b.2's layout sections (Running/Paused/Complete/Failed) map 1:1 to the `status_group` binary, so pushing the filter down to SQL is both cheaper (O(1) query per group) and less code-complex than any FE merging. The option-(c) N-fanout would have worked for a demo but broken at ~10 projects per account. This is exactly the class of call the `feedback_fe_draft_html_be_check.md` rule exists to force before CLARIFY is closed.

### Still deferred after K16.12 completion

- **D-K19b.1-01** → Track 3 polish: cursor pagination for history once users cross ~150 historical jobs.
- **D-K19b.2-01** → Track 3 polish: "Show more" CTA on Complete section (BE ships 50, FE slices 10).
- ~~D-K19b.2-02~~ — **Cleared in K19b.3**.
- ~~D-K19b.4-01~~ — **Cleared in K19b.3**.
- **D-K19b.3-01** → Track 3 polish: human-readable "current item" from cursor. Needs BE cursor enrichment OR FE chapter-title lookup.
- **D-K19b.3-02** → Track 3 polish: humanised ETA formatter for >60min jobs.
- ~~K19b.8~~ — **Cleared in Cycle 7** (MVP shipped). D-K19b.8-01/02/03 tracked below for polish.
- **D-K19b.8-01** → Track 3 polish: retention cron for job_logs (no auto-cleanup today).
- **D-K19b.8-02** → Track 3 polish: orchestrator-side pipeline logs in knowledge-service extract_item handler.
- **D-K19b.8-03** → Track 3 polish: tail-follow auto-polling + load-more in JobLogsPanel.
- **D-K19c.4-01** (new, Cycle 8) → K17/K18 entity-management surface: rename-aware `user_archive_entity` variant that preserves `glossary_entity_id` on archive. Current `archive_entity` clears the FK per its K11.5a scope; fine for user-MVP but imperfect for the "hide now, restore later" flow.
- ~~D-K19a.5-03~~ — **Cleared in K19b.6** (BuildGraphDialog monthly-remaining hint shipped).
- ~~D-K16.11-01~~ — **Cleared in Cycle 6.** Budget helpers wired into production; CostSummary will now populate real figures as jobs run.
- **D-K19a.5-04 + D-K16.2-02b** → Track 3 (paired): chapter_range picker + runner-side enforcement.
- **D-K19a.5-06** → Track 3 polish: `glossary_sync` scope option in BuildGraphDialog.
- **D-K19a.5-07** → Track 3 polish: "Run benchmark" CTA in BuildGraphDialog.
- **D-K19a.7-01** → naturally-next: hook-level action smoke tests for `useProjectState`.
- **D-K19a.8-01** → Track 3 polish: MSW-backed dialog stories.

---

## Session 49 — 4 Track 3 cycles shipped (K19a.5 + K19a.6 + K19a.7 + K19a.8)

```
Track 3 K19a progress (session 49)

Cycle 6  K19a.5  BuildGraphDialog + ErrorViewerDialog          3148751
         + session_handoff HEAD backfill                        1156193
Cycle 7  K19a.6  ChangeModelDialog + destructive confirms +     2226283
                 BE POST /extraction/disable (FS)
         + HEAD backfill                                        7cf394f
Cycle 8  K19a.7  i18n polish (runAction + PrivacyTab + 4        2cbcc7c
                 locales + ACTION_KEYS typo defence)
         + HEAD backfill                                        c6ee80a
Cycle 9  K19a.8  Storybook 10 install + 13 ProjectStateCard     TBD
                 stories (Vite alias @/auth → MockAuth)

Track 3 K19a cluster: 100% complete (8 non-optional + 1 optional)
```

**Test deltas at session 49 end:**
- Frontend knowledge (+ shared ConfirmDialog): **112 pass** (was 75 at session 48 end; +37 content across K19a.5/6/7)
- Storybook: 14 stories build clean; `npm run build-storybook` 10.7s
- BE: +5 new tests (POST /extraction/disable — happy + 404 + 409 active + 409 paused + idempotent no-op)
- /review-impl across all 4 cycles caught **6 MED + 13 LOW + 5 COSMETIC**; every code finding fixed in-cycle except 2 accepted silently (K19a.7 F4 vitest stub churn + K19a.8 F3 Playwright binaries one-time cost); 10 D-K19a.*-* deferrals logged, 2 cleared in K19a.6 (D-K19a.5-01 change-model, D-K19a.5-02 disable-without-delete)

**What shipped:**
- `BuildGraphDialog.tsx` — scope selector (chapters/chat/all, `chapters` hidden when `!book_id`), chat-model dropdown, embedding picker (reuses K12.4), max_spend decimal-validated input, debounced auto-fetch estimate preview, benchmark pre-flight gate, BE-detail error extractor (`readBackendError` exported for unit test).
- `ErrorViewerDialog.tsx` — shared viewer for `failed` + `building_paused_error`. Job metadata grid + pre-wrapped error text + Copy button.
- Wired via `ProjectRow` dialog-state lifting + `useProjectState` stubs becoming silent no-ops. Merge deps narrowed to `errorPayloadKey` so actions don't re-create on poll tick.

### What K19b can now assume

- All 14 `ProjectStateCardActions` callbacks are wired: 9 fire BE APIs (pause/resume/cancel/retry/extractNew/delete/rebuild/confirmModelChange/ignoreStale), 5 open parent-lifted dialogs/confirms (buildGraph/start/viewError/changeModel/disable).
- `ProjectRow` is the canonical merge point for dialog-dependent actions — lift dialog/confirm state, spread `baseActions`, override the relevant callbacks. For destructive actions, route through `runDestructive(PROJECT_ACTION_KEYS.xxx, op, close)` so ConfirmDialog's `loading` prop shows in-dialog spinner + toast carries the right translated label.
- `readBackendError` lives at `frontend/src/features/knowledge/lib/readBackendError.ts` (K19a.6 F7). Any new dialog surfacing 4xx errors should import from there — `apiJson` only reads top-level `.message` but FastAPI wraps as `{detail: ...}`.
- `ChangeEmbeddingModelResponse` is a discriminated union (warning / noop / result); future callers must narrow before treating as success — K19a.6 F2 fixed the silent-success-on-no-op bug.
- `ConfirmDialog` now disables Cancel + X buttons while `loading=true`. Pattern is consistent across all destructive flows.
- `useProjectState` exports `PROJECT_ACTION_KEYS` (K19a.7 F1) — a compile-time map of action → i18n key. Consumers wanting to surface BE errors as localised toasts should import this rather than repeating string literals; typos become build errors.
- Zero hardcoded toast/label/body strings remain in `frontend/src/features/knowledge/` — `grep -r "toast\.(error\|info\|success\|warning)\(['\"]"` confirms. New dialogs should use `useTranslation('knowledge')` from the start.
- Storybook (K19a.8) is installed with 14 stories covering all 13 `ProjectMemoryState` kinds. `npm run storybook` dev-serves at port 6006; `npm run build-storybook` produces a static catalog. `.storybook/main.ts` aliases `@/auth` → `MockAuthProvider` so any future story can render real components that call `useAuth` without wiring it explicitly.
- BE endpoints now cover all Track 3 K19a surfaces:
  - `DELETE /extraction/graph` — destructive delete
  - `PUT /embedding-model?confirm=true` — destructive change-model (deletes graph + disables)
  - `POST /extraction/disable` — **non-destructive** disable (preserves graph)
  - `POST /extraction/rebuild` — destructive rebuild (delete + start fresh job)

### Still deferred after K19a.7

- **D-K19a.5-03** → K19b.6: Monthly budget remaining context in BuildGraphDialog max-spend field (needs BE `/v1/me/usage/monthly-remaining` endpoint).
- **D-K19a.5-04** → paired with D-K16.2-02b: FE chapter_range picker (BE preview honours, runner doesn't — ship both together).
- **D-K19a.5-05** → superseded by D-K19a.7-01: half closed (F1 typo prevention via `ACTION_KEYS` const); other half now tracked as D-K19a.7-01.
- **D-K19a.5-06** → K19a.7 (NOT done in this cycle): `glossary_sync` scope option in BuildGraphDialog (BE accepts, FE doesn't expose). The "K19a.7" polish cycle focused on string i18n, not scope-list expansion. Re-target to Track 3 polish or K19b as convenient.
- **D-K19a.5-07** → Track 3 polish: "Run benchmark" CTA in BuildGraphDialog when `has_run=false` (needs POST endpoint for eval harness).
- **D-K19a.7-01** → naturally-next: hook-level action smoke tests (inherits action-fire-path coverage from D-K19a.5-05).
- **D-K19a.8-01** → Track 3 polish: dialog stories for BuildGraphDialog / ChangeModelDialog / ErrorViewerDialog. Needs MSW handlers for `knowledgeApi` interception. Mock auth already wired via K19a.8 Vite alias.

### FS-cycle payload-audit lesson — response-side variant

K19a.5 F1 surfaced the BE `{detail: {message}}` body-extraction gap. K19a.6 F2 added another class: **response shape ambiguity under idempotent/no-op paths**. The BE `PUT /embedding-model?confirm=true` returns three different shapes — warning (confirm=false), no-op (same-model, either direction), result (confirm=true, different model). FE must narrow the discriminated union before treating as success; otherwise a cross-device race turns a silent no-op into a false "success" UX. For future FS cycles with idempotent BE endpoints: **list every BE response branch at CLARIFY time**, not just the happy path.

### i18n silent-fallback lesson (K19a.7)

i18next silently falls back to the raw key path when a key is missing, so a callsite typo like `t('projects.state.actions.pauze')` doesn't crash — it renders `"projects.state.actions.pauze: rate limit"` in the user-visible toast. Runtime JSON-resource iterators catch missing resources but NOT typos at the callsite. Defence: a compile-time constant map (`ACTION_KEYS` in `useProjectState.ts`) turns every callsite into a TypeScript literal lookup so typos become build errors. For any future i18n-heavy module, introduce the const map up front rather than threading string literals.

### Storybook-init quirks (K19a.8)

`npx storybook@latest init --type react` is aggressive: it modifies `vite.config.ts` to inject `@storybook/addon-vitest` plumbing AND downloads ~200 MB of Playwright browser binaries for that addon — even on a no-install run. For a minimal Storybook-only setup:
1. Use `--skip-install` to avoid committing to deps before review.
2. Edit `package.json` to REMOVE `@storybook/addon-vitest`, `@chromatic-com/storybook`, `addon-onboarding`, `@vitest/browser`, `playwright` before `npm install`.
3. `git checkout HEAD -- vite.config.ts` to undo the vitest-addon workspace plumbing (it adds a `test: {workspace: [...]}` block that references the removed addon).
4. Ctrl-C the prompt that asks to install Playwright browser binaries — it comes AFTER addon config, not at the start.
5. Delete the `src/stories/` example directory (Button/Header/Page scaffold) and `vitest.shims.d.ts` shim file.
6. `fn()` for action spies lives in `storybook/test`, not `@storybook/test` (Storybook 10 moved it).

---

## Session 48 — 5 Track 3 cycles shipped (archived for reference)

> Previous session handoff content preserved below.

---

### Previous Session 48 Header

**Date:** 2026-04-19 (session 48 END)
**HEAD:** `5a726be` (K19a.4)
**Branch:** `main` (ahead of origin by sessions 38–48 commits — user pushes manually)

## Session 48 — 5 Track 3 cycles shipped

```
Track 3 K19a progress (session 48)

Cycle 1  K19a.1-rename           /memory → /knowledge end-to-end     d14d71b
Cycle 2  K19a.1-placeholders     4 Coming-soon tabs                   bab8829
Cycle 3  K19a.2 + K19a.7-skel    13-state TS types + i18n labels     70a3136
Cycle 4  K19a.3                  dispatcher + 13 state subcards      af4cefa
Cycle 5  K19a.4                  hook + BE graph-stats + ProjectRow  5a726be
```

**Final test counts at session 48 end:**
- Frontend (knowledge): **75 pass** (26 projectState + 23 useProjectState + 26 ProjectStateCard)
- Backend (new this session): **6 pass** (test_graph_stats.py)
- Track 2 regression tests: still green per last session 47 runs
- /review-impl caught **1 HIGH + ~15 MED/LOW findings** across the 5 cycles; every code finding fixed in-cycle, 3 LOW documented as known issues (see F4/F7/F8 below)

**User feedback adopted this session:**
- Cycle 3 onwards: batch small related tasks into one workflow cycle (rule saved to memory `feedback_batch_small_tasks.md`)
- FE draft HTML → BE audit at DESIGN phase, reclassify to FS if BE is missing (rule saved to memory `feedback_fe_draft_html_be_check.md`) — K19a.4 validated this: the graph-stats endpoint gap was caught pre-CLARIFY, user picked `(c) add BE now` rather than defer

**Cycle 1 (K19a.1-rename, d14d71b):** pure `/memory` → `/knowledge` rename + nav retranslation (24 files).

**Cycle 2 (K19a.1-placeholders, bab8829):** 4 placeholder tabs added. Navigation shell complete (7 tabs: Projects / Jobs / Global / Entities / Timeline / Raw / Privacy). Each new tab renders "Coming soon" + localized function description.

**Cycle 3 (K19a.2 + K19a.7-skeleton, 70a3136):** **First batched cycle** per user feedback. Foundation types for the 13-state memory-mode UI: `ProjectMemoryState` discriminated union + supporting types (BE-aligned per review-impl F1) + `VALID_TRANSITIONS` map + `canTransition` helper + all state/action i18n keys × 4 locales. 22/22 tests passing including runtime i18n cross-locale checks that neutralize the vitest i18n mock bypass (identified as L2 in cycle 1 review-impl).

**Cycle 4 (K19a.3 full, af4cefa):** `ProjectStateCard` dispatcher + all 13 subcomponents + shared primitives + 26-test component test file. Pure presentational (callback-prop pattern, TS exhaustive switch). `ProjectStateCardActions` union of 14 callbacks. /review-impl caught 7 more findings (3 MED dispatcher/prop drops + 1 MED i18n-coverage regression + 3 LOW polish), all fixed in-cycle. i18n runtime coverage now tracks 48 key paths × 4 locales (192 assertions).

**Cycle 5 (K19a.4 hook + BE graph-stats endpoint, 5a726be):** First FS cycle of Track 3. New `GET /v1/knowledge/projects/{id}/graph-stats` endpoint (Cypher UNION-ALL aggregation, 6 BE unit tests). New `useProjectState(project)` hook: derives `ProjectMemoryState` from `(Project, jobs, stats)`, polls `/extraction/jobs` at 2s while active, wires 11 of 14 callbacks to real endpoints (pause/resume/cancel/retry/extractNew/delete/rebuild/confirmModelChange + 3 that stay toast-stubs pointing to K19a.5 + 4 that stay toast-stubs pointing to K19a.6). `ProjectCard.tsx` deleted, replaced by `ProjectRow.tsx`. /review-impl caught 9 findings (1 **HIGH** — missing `embedding_model` on `/start` + `/rebuild` payloads would 422 at runtime; 2 MED — no error handling, no scopeOfJob tests; 5 LOW + 1 cosmetic). All code findings fixed in-cycle; 3 LOW documented as known issues.

**User feedback captured mid-session:** future small tasks should be batched into single cycles (saved to memory `feedback_batch_small_tasks.md`). Cycle 3 is the first application. Worked well — review-impl caught 9 findings in the batched scope that all got fixed in one pass.

### What K19a.5 can now assume

- `useProjectState(project)` hook returns `{ state, actions, isLoading, error }` — the dialog can import it to trigger estimate → confirm → start. When the Build button eventually opens the dialog, the dialog's Start button REPLACES `actions.onStart` (currently a toast-stub).
- `knowledgeApi.estimateExtraction(projectId, {scope, llm_model, embedding_model}, token)` returns a `CostEstimate`. `knowledgeApi.startExtraction(projectId, {scope, llm_model, embedding_model}, token)` returns an `ExtractionJobWire`. Both are ready to call.
- `EmbeddingModelPicker` (from K12.4) handles embedding-model selection UI; the dialog can reuse it.
- Call `queryClient.invalidateQueries({queryKey: ['knowledge-project-jobs', projectId]})` after starting a job to flip the ProjectStateCard from DisabledCard → BuildingRunningCard on the next poll.

### Known issues deferred from K19a.4 review-impl

- **F4 (polling scale):** 2 queries × N projects. Bounded today by the 100-item pagination cap in ProjectsTab. If pagination is ever removed, consider a `/v1/knowledge/projects/active-jobs` aggregator.
- **F7 (multi-device race):** polling stops for paused/complete/failed states. External state changes on another client aren't auto-refreshed. Future: always-on 30 s low-cadence poll OR SSE.
- **F8 (action-API test gap):** the 11 real-action callbacks have no hook-level tests. `renderHook` + mocked `knowledgeApi` would cover them. Medium lift, future hardening.

### What K19a.5 will replace

- `actions.onStart` stub — becomes the dialog's Start button calling `knowledgeApi.startExtraction`.
- `actions.onBuildGraph` stub — becomes the dialog-opener trigger on DisabledCard.
- `actions.onViewError` stub — becomes the error-viewer modal trigger on Failed/BuildingPausedError cards.

### Retro note — lesson for future FS cycles

Review-impl HIGH F1 (missing `embedding_model` on /start + /rebuild payloads) was a real 422-at-runtime trap that NO test layer could have caught: vitest doesn't hit BE, pytest doesn't hit FE, and Playwright smoke was blocked by BE not running. For FS cycles, review-impl MUST explicitly audit FE payload shape against the BE Pydantic schema — it's the only layer that catches this class of bug.

### FS cycle checklist going forward

1. **At CLARIFY:** enumerate every FE action → BE endpoint pair in a table.
2. **At DESIGN:** read the BE Pydantic request model for each endpoint; confirm every required field has a source in the FE state/props.
3. **At /review-impl:** re-read the Pydantic models; trace every payload construction call site; flag any optional-on-FE / required-on-BE mismatches as HIGH.

## Session 48 — K19a.1-rename (first Track 3 cycle) ✅

Pure `/memory` → `/knowledge` rename + nav retranslation.

**What shipped:**
- URL path + page file + component + i18n namespace all renamed to `knowledge`; hard-cut on `/memory` (old URLs 404)
- 5 product-name-referring locale strings retranslated to Knowledge / ナレッジ / Tri thức / 知識; functional/state-machine references (`staticMemory` badge, `indicator.popover.projectHeading`, `picker.*`, body text) deliberately kept as "Memory" — they describe the AI's memory function, not the product name
- `nav.memory` common-namespace key renamed + retranslated
- `tMemory` local alias renamed to `tKnowledge` in SessionSettingsPanel
- Playwright runtime evidence captured

**What still says "Memory" intentionally:**
- `projects.card.staticMemory` badge — technical state label from the 13-state memory-mode machine; backend `session.memory_mode` contract uses `"static"` / `"degraded"` / `"no_project"`
- `indicator.popover.projectHeading` / `globalHeading` / `body text` / `picker.*` — describe the AI's memory function
- Component names `MemoryIndicator`, `MemoryPage`-turned-history are a concept, not the URL — `MemoryIndicator` component kept; file renamed to `KnowledgePage.tsx`

**Test-coverage gap (important for the NEXT i18n-touching cycle):** the vitest setup at [frontend/vitest.setup.ts:24-41](../../frontend/vitest.setup.ts) globally mocks `react-i18next` such that `useTranslation(anyNamespace)` returns keys verbatim. Unit tests provide **zero** evidence of namespace correctness. Future i18n renames must rely on exhaustive grep (including `<Trans ns=>`, `useTranslation([])` array form, `t('ns:key')` prefix form, `i18n.t`, `getFixedT`) + `tsc --noEmit` + `vite build` + Playwright. Do not over-trust vitest green.

**Review-impl caught & fixed:** M1 (misleading `tMemory` alias post-namespace-rename), M2 (option c was half-shipped — retranslated 5 product labels per locale but kept functional descriptions), L1 (no runtime evidence — added Playwright smoke), L3 (2 stale "Memory page" comments).

---

## (Archived for reference) Session 47 END handoff

> Previous session handoff content preserved below for context.

---

## 1. TL;DR — what shipped this session

**20 commits. Track 2 code-complete.** Session 47 executed the full Track 2 close-out extended plan the user negotiated mid-session. All T2-close-* and T2-polish-* cycles shipped; the only remaining Track 2 item is the Gate 13 human-interactive checkpoint loop (T2-close-2), which can't be automated and is waiting on the user.

```
Track 2 close-out (26 cycles total, sessions 46 + 47)

Session 46  (12 commits, shipped first)
  Cycles 1–6 of the original Track 2 close-out roadmap

Session 47  (20 commits, extended-plan close-out)
  Cycle 7a   P-K18.3-02 MMR embedding cosine              ✅  7c666c9
  Cycle 7b   K18.9 Anthropic prompt cache_control         ✅  8f282c3
  Cycle 8a   D-K18.3-02 generative rerank                 ✅  e5aeb96
  Cycle 8b   D-T2-04 cross-process cache invalidation     ✅  239b021
  Cycle 8c   D-T2-05 glossary breaker half-open probe     ✅  2732462
  Cycle 9    K17.9.1 benchmark-runs migration             ✅  e0a94a7
  test-hygiene one-active-job-per-project fixes            ✅  609de2b
  Gate-13-report doc                                       ✅  95d336e
  T2-close-1a   K17.9 golden-set harness core wiring      ✅  525eaa5
  T2-close-1b-BE   benchmark gate + status endpoint       ✅  849be7f
  T2-close-1b-FE   picker badge + public endpoint         ✅  a484e25
  scope-out docs T2-close-1b-CI + T2-polish-4              ✅  34a4d8f
  T2-close-5   D-K16.2-01 per-model USD pricing           ✅  ed9f13d
  T2-close-6   D-K16.2-02 scope_range.chapter_range       ✅  01b8eda
  T2-close-7   P-K2a-02 + P-K3-02 glossary trigger perf   ✅  02067e2
  T2-close-3   scripted C05/C06/C08 chaos harness         ✅  fae8ce1
  T2-polish-1  test-isolation audit + 2 Go test fixes     ✅  8e3410d
  T2-polish-2a /metrics for glossary-service              ✅  0464919
  T2-polish-2b /metrics for book-service                  ✅  98623aa
  T2-polish-3  D-K18.9-01 cache_control on system_prompt  ✅  ff9ef11
  T2-close-4   Track 2 acceptance pack (doc)              ✅  e694e44
```

**Test execution at session END:**
- knowledge-service unit: **1154 pass** (up from 1049 at session 46 end)
- chat-service unit: **177 pass** (up from 169)
- glossary-service api: **100% green in 3.0 s** (was 2 persistent failures — both stale test bugs fixed in polish-1)
- book-service api: **green + new `parseSortRange` / `buildSortRangeFilter` tests**
- provider-registry-service: green

**Scoped out by user decision (not deferred):**
- T2-close-1b-CI — GitHub Actions benchmark job (no CI/CD at this stage)
- T2-polish-4 — CI integration-test wiring (same reason)

---

## 2. Where to pick up — Track 2 sealing + Track 3 onramp

### Option A — Close Gate 13 (recommended first)

The only code-path-adjacent Track 2 task remaining is **T2-close-2**: the 12-step Gate 13 human-interactive checkpoint walkthrough in [GATE_13_READINESS.md §5](GATE_13_READINESS.md). Requires:

1. BYOK credentials for one LLM provider (Anthropic / OpenAI / LM Studio) + one embedding model (bge-m3 on LM Studio or text-embedding-3-small on OpenAI).
2. A test project with 2–3 real chapters loaded via book-service API.
3. Driving the UI: enable extraction → wait for job → open chat → ask broad / specific / relational queries → inspect chat-service logs for `<memory mode="full">` → send 25+ messages to prove only last 20 in history → ask a contradiction-of-negation question → disable/re-enable extraction → check cost against provider invoice.
4. Optionally run the chaos scripts live for extra confidence: `./scripts/chaos/c0{5,6,8}_*.sh`.

Outcome: append a §10 Gate 13 attestation to [TRACK_2_ACCEPTANCE_PACK.md](TRACK_2_ACCEPTANCE_PACK.md) with captured evidence (log excerpts, screenshots, invoice line).

This is the **only** remaining step before Track 2 is formally closed. Code-wise nothing else blocks Track 3.

### Option B — Start Track 3 planning

If the Gate 13 loop is being deferred, Track 3 can start anytime because all Track 2 surfaces are shipped. The Deferred Items table in SESSION_PATCH has a "Track 3 preload" list with specific target phases — open that table and pick the cluster that fits the next session's scope.

Track 3 preload clusters (each has a target phase listed in Deferred Items):
- **D-K16.2-02b** — runner-side `chapter_range` enforcement (dormant today; frontend doesn't send `scope_range` yet).
- **D-K11.9-01 + P-K15.10-01 (partial)** — cursor-state for resumable reconciler + quarantine sweep. Paired with a job-state table. Target: K19/K20 scheduler cleanup.
- **D-K8-02 (remaining)** — project card stat tiles (entity / fact / event / glossary counts). Needs FE wiring on top of already-shipped BE surfaces.
- **D-K17.10-02** — xianxia + Vietnamese K17.10 fixtures.
- **P-K3-01 / P-K3-02 (full path)** — per-row short_description backfill → set-based SQL. Blocked on `shortdesc.Generate` ported to SQL; same port unblocks full P-K3-02.

### Resume recipe (either option)

1. **Read [SESSION_PATCH.md](SESSION_PATCH.md) + [TRACK_2_ACCEPTANCE_PACK.md](TRACK_2_ACCEPTANCE_PACK.md)** — the acceptance pack is the single-page view; SESSION_PATCH has everything else.
2. **Check Deferred Items "Naturally-next-phase" table** — any row whose Target equals the phase you're entering is in scope.
3. **Use the workflow gate:** `python scripts/workflow-gate.py reset` then `size <XS|S|M|L|XL> <files> <logic> <effects>` before each cycle; phase-by-phase through RETRO.

---

## 3. What changed in the Deferred Items table this session

### Cleared this session (moved to Recently cleared)

| ID | Cycle | Summary |
|---|---|---|
| **D-K16.2-01** | T2-close-5 | Per-model USD pricing table (`app/pricing.py`) for cost preview — replaces legacy ~$2/M fallback. |
| **D-K16.2-02** | T2-close-6 | `scope_range.chapter_range` threaded through estimate endpoint → `BookClient.count_chapters(from_sort=, to_sort=)` → book-service `parseSortRange` + `buildSortRangeFilter`. |
| **D-K18.3-02** | 8a | Generative listwise rerank on top of MMR, opt-in via `extraction_config["rerank_model"]`, inner timeout 1s, fail-safe fallback. |
| **D-T2-04** | 8b | Cross-process L0/L1 cache invalidation via Redis pub/sub. |
| **D-T2-05** | 8c | Glossary circuit-breaker half-open single-probe guarantee. |
| **D-K18.9-01** | T2-polish-3 | `cache_control` on session `system_prompt` — second Anthropic cache breakpoint used. |
| **K17.9 (harness core + BE gate + FE badge + migration)** | T2-close-1a/1b-BE/1b-FE + Cycle 9 | Golden-set benchmark end-to-end live. `project_embedding_benchmark_runs` table + gate in `/extraction/start` + picker badge + `GET /v1/knowledge/projects/{id}/benchmark-status`. |
| **P-K18.3-02** | 7a | MMR embedding cosine + `top_n` early-exit (21× perf win on dim=3072 pool=40). |
| **K18.9** | 7b | Anthropic prompt caching: structured system content with `cache_control: ephemeral` on stable memory prefix. |
| **P-K2a-02 + P-K3-02 (partial)** | T2-close-7 | Glossary trigger watch-list rewrite; pin toggle 1→0 recalcs, description PATCH 3→1 (no-op) / 2 (real). |
| **Chaos C05/C06/C08 (scripted)** | T2-close-3 | `scripts/chaos/{c05,c06,c08}_*.sh` authored + smoke-tested. |
| **T2-polish-1 test-isolation audit** | T2-polish-1 | Python suite audited clean; 2 pre-existing broken Go tests fixed. |
| **T2-polish-2a /metrics glossary** | T2-polish-2a | 4 counter vecs + 8 call sites pre-seeded; review-impl caught + killed 16 dead labels. |
| **T2-polish-2b /metrics book-service** | T2-polish-2b | 3 counter vecs, cross-service label divergence documented. |
| **T2-close-4 acceptance pack** | T2-close-4 | `TRACK_2_ACCEPTANCE_PACK.md` consolidates Track 2 evidence. |

### Still deferred (explicit Track-3-preload, no re-deferrals this session)

| ID | Target |
|---|---|
| D-K8-02 (remaining stat tiles) | Track 2 Gate 12 or Track 3 |
| D-K11.9-01 (partial, cursor state) | K19/K20 scheduler cleanup |
| P-K15.10-01 (partial, cursor state) | Paired with D-K11.9-01 |
| D-K17.10-02 | K17.10-v2 after threshold stabilisation |
| D-K16.2-02b (runner-side chapter_range) | Track 3 (when FE range-picker ships or batch-iterative runner lands) |
| D-K18.3-02b (if any — none currently) | — |
| P-K3-01 (backfill Go→SQL port) | Track 3 |
| P-K3-02 full path (same port) | Track 3 |

No new deferrals added this session besides **D-K16.2-02b** (review-impl catch during T2-close-6 — runner is event-driven and doesn't honour `chapter_range`; preview filters but runner doesn't, dormant until FE sends `scope_range`).

---

## 4. Important context the next agent must know

### Workflow enforcement unchanged (v2.2 · 12-phase)

```
CLARIFY → DESIGN → REVIEW-DESIGN → PLAN → BUILD → VERIFY → REVIEW-CODE → QC → POST-REVIEW → SESSION → COMMIT → RETRO
```

State machine: `.workflow-state.json` + `scripts/workflow-gate.py` from repo root. Pre-commit hook blocks commits without VERIFY + POST-REVIEW + SESSION completed.

**POST-REVIEW is a human checkpoint, NOT self-adversarial re-read.** Deep review is on-demand via `/review-impl`. Every cycle this session had a `/review-impl` pass and several caught HIGH issues the initial self-review missed (examples: T2-close-3 found 3 HIGH blockers in chaos scripts; T2-close-6 found 6 findings including a shared-validator bypass; T2-close-7 found a soft-delete regression from the initial trigger-rewrite).

### Key semantic changes this session

1. **`entity_snapshot.updated_at` semantics changed (T2-close-7).** Pin toggle no longer bumps `updated_at`, and the self-trigger dropped `updated_at` from its watch list. `snapshot.updated_at` now tracks last-**semantic**-change, not last-**touch**. Callers wanting last-touch should read `glossary_entities.updated_at` directly.
2. **`scope_range.chapter_range` is preview-only (T2-close-6).** The estimate endpoint filters; the event-driven extraction runner does not yet honour the range. Dormant today because no frontend sends `scope_range`. Tracked as D-K16.2-02b.
3. **Anthropic 2 of 4 cache breakpoints used (7b + polish-3).** parts[0] = stable memory (cached), parts[1] = volatile memory (uncached, changes per-message), parts[2] = session system_prompt (cached).

### Observability surfaces — all 3 Go services on knowledge-service hot paths

| Service | Endpoint | Counters |
|---|---|---|
| provider-registry | `/metrics` (session 46) | 4 (proxy / invoke / embed / verify) |
| glossary-service | `/metrics` (T2-polish-2a) | 4 (select_for_context / bulk_extract / known_entities / entity_count) |
| book-service | `/metrics` (T2-polish-2b) | 3 (projection / chapters_list / chapter_fetch) |

Outcome label sets differ intentionally between glossary (`invalid_body`) and book (`not_found`). Cross-ref comments in both metrics.go files explain why. Do NOT "normalize" them.

### Chaos scripts — live-run when needed

`scripts/chaos/` contains `lib.sh` + `c05_redis_restart.sh` + `c06_neo4j_drift.sh` + `c08_bulk_cascade.sh` + `README.md`. Each exits `0` on PASS, dies with `FAIL <reason>` on failure, and uses `trap cleanup EXIT` so a failed run still sweeps test data. Test UUIDs prefixed `00000000-0000-0000-c0XX-...` for manual sweep. Prereqs: the `infra-*` compose stack running.

### Benchmark harness is live and gate-active

`python -m eval.run_benchmark --project-id=<uuid> --embedding-model=<model>` runs the K17.9 golden-set harness. A passing row in `project_embedding_benchmark_runs` is now required to start an extraction job — the `POST /extraction/start` endpoint returns 409 with structured `{error_code: benchmark_missing | benchmark_failed, ...}` otherwise. The K12.4 embedding-model picker shows a 3-state badge (green passed / red failed / grey no-run) that drives the CTA.

### Caches + breakers shipped this session (all per-worker-process unless noted)

- `_anchor_cache` TTLCache(256, 60s) — `internal_extraction.py` (session 46).
- `_query_embedding_cache` TTLCache(512, 30s) — `selectors/passages.py` (session 46).
- L0/L1 TTLCache + **cross-process pub/sub invalidation** via `CacheInvalidator` on Redis channel `loreweave:cache-invalidate` (Cycle 8b this session). Settings-gated on `redis_url`.
- Glossary breaker with half-open single-probe guarantee (Cycle 8c this session).

### Pre-existing failing tests (not this session's fault)

- `book-service/internal/config TestLoadValidation` — missing `INTERNAL_SERVICE_TOKEN` env in test setup; the validation requirement was added later. Confirmed via `git stash`.
- `translation-service/tests/test_glossary_client.py` + `test_pipeline_v2.py` — module-import pydantic Settings validation errors (pre-existing before session 46).

### New deps this session

- `github.com/prometheus/client_golang v1.23.2` on **both** glossary-service and book-service (from T2-polish-2a/2b). Session 46 already added it to provider-registry. `go.mod` + `go.sum` committed.

### Infra & test invocation (unchanged)

- Compose: `cd infra && docker compose up -d`; Neo4j profile: `docker compose --profile neo4j up -d neo4j`.
- Neo4j port: **7688**, Postgres port: **5555**, Neo4j creds `neo4j / loreweave_dev_neo4j` (note the `_neo4j` suffix — chaos scripts default to this).
- pytest from `services/knowledge-service/` (unit: `-q tests/unit/`; integration needs `TEST_KNOWLEDGE_DB_URL` + `TEST_NEO4J_URI`).
- Go tests from `services/<svc>/` (`go test ./...`); glossary-service integration needs `GLOSSARY_TEST_DB_URL`.

---

## 5. Session 47 stats

| Metric | Before session 47 | After session 47 | Delta |
|---|---|---|---|
| Total knowledge-service unit tests | 1049 | **1154** | **+105** |
| chat-service unit tests | 169 | **177** | **+8** |
| glossary-service api test status | 2 failing (stale) | **100% green** | 2 fixed |
| book-service api test status | green | **green + new tests** | new units |
| Deferred items open | ~6 naturally-next + 4 re-deferred + 2 partial | **~6 naturally-next / partial only (no re-deferrals)** | ~4 cleared |
| Cycles complete (original Track 2 roadmap) | 6/9 | **9/9** | +3 |
| T2-close extended plan cycles | 0 | **9/9** (1 scoped out) | +9 |
| T2-polish extended plan cycles | 0 | **4/4** (1 scoped out) | +4 |
| Session commits | 0 | **20** | +20 |
| Review-impl follow-up catches | — | ~20 HIGH/MED/LOW findings across cycles | — |
| New deps | — | `prometheus/client_golang v1.23.2` on glossary + book | +1 dep × 2 services |
| New env knobs | — | — | stable |
| Services with /metrics | 1 (provider-registry) | **3** (+ glossary + book) | +2 |
| Chaos scripts (scripted live runs) | 0 | **3** (C05/C06/C08) | +3 |

---

## 6. Housekeeping note

This file is the single, unversioned handoff. **Future sessions MUST update this file in place — do NOT create a `_V48.md` or similar.**

Track 2 is **code-complete**. The repo is in a clean state to either (a) execute the Gate 13 human loop to formally seal Track 2, or (b) begin Track 3 planning — neither blocks the other. All deferrals have explicit target phases; no "we'll come back to it" rows remain.

When the Gate 13 human loop is run, append §10 attestation to [TRACK_2_ACCEPTANCE_PACK.md](TRACK_2_ACCEPTANCE_PACK.md) with the captured evidence, and move the T2-close-2 row out of "remaining" in SESSION_PATCH's header metadata.
