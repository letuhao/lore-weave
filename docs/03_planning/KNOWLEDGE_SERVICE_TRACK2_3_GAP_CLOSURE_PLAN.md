# Track 2/3 Gap Closure Plan

> **Purpose.** Drain the ~32 open deferrals inherited from Track 2 close-out + K19/K20 Track-3 cycles before opening new Track 3 feature work. Companion to [SESSION_PATCH.md](../sessions/SESSION_PATCH.md) Deferred Items section (SSOT for per-item text) and mirrors the [Track 2 Close-out Roadmap](../sessions/SESSION_PATCH.md#track-2-close-out-roadmap-session-46) pattern: bounded cycles, each one commit, each closes a named item list.
>
> **Source of truth.** SESSION_PATCH.md owns the authoritative per-item descriptions — this plan references IDs, not duplicates text. If an item description drifts, trust SESSION_PATCH.
>
> **Created.** Session 50 — 2026-04-23, HEAD `b7b5b3c`
> **Trigger.** User audit ask: "clear all gaps/defers before moving to Track 3"

---

## 1. Rules of execution

1. **Cycles execute in number order by default.** A later cycle can jump only if every dependency-marked prior cycle is closed.
2. **Each cycle is a single commit** wired through the 12-phase workflow (CLARIFY → … → COMMIT → RETRO). No "just a bit more" scope drift — if a cycle grows past its size classification, STOP and split.
3. **Architectural cycles (marked 🏗) run DESIGN phase first and return a DESIGN doc** before any BUILD. Do not patch-fix — amend the relevant KSA section.
4. **New deferrals during closure are expected.** Log them in [§5](#5-deferrals-arisen-during-closure) with ID + origin cycle + target cycle, and carry forward into SESSION_PATCH at cycle COMMIT.
5. **Size drift = STOP.** If a "M" cycle hits 6+ files, reclassify and confirm with user before proceeding. CLAUDE.md Anti-Skip Rules apply.
6. **`/review-impl` after every BUILD.** Track record across sessions 46–50 says it finds something every cycle. Budget the time.

---

## 2. Priority ordering rationale

| Tier | Criterion | Cycles |
|---|---|---|
| P1 | Correctness drift / data-loss risk once >1 real user | **C1, C2** |
| P2 | Observability + UX polish that matters as mobile/multi-device lands | **C3, C4, C5, C6, C7, C8** |
| P3 | Coverage + naturally-next features | **C9, C10, C11, C12, C13** |
| P4 | Performance (fire when profiling shows pain) | **C14, C15** |
| P5 | Architectural / needs KSA amendment | **C16, C17, C18** |
| — | User-gated (data or attestation) | **C19, C20** |

Drain P1→P2→P3 front-to-back. P4 runs opportunistically (one cycle when suite is green between feature work). P5 runs DESIGN-first and may fork into its own module plan. C19–C20 are user-driven — stated, not scheduled.

---

## 3. Cycle table (20 cycles)

Statuses: `[ ]` open · `[D]` DESIGN in flight · `[B]` BUILD in flight · `[V]` VERIFY · `[R]` REVIEW · `[x]` done · `[⏸]` blocked

| # | Cycle | Items closed | Size | Status | Depends on |
|---|---|---|---|---|---|
| **C1** | **merge_entities atomicity + ON-MATCH union** | D-K19d-γb-01, D-K19d-γb-02 | M | `[x]` | — |
| **C2** | Scheduler observability + regen cooldown | D-K20.3-α-02, D-K20α-02 | ~~S~~ **L** (reclassified) | `[x]` | — |
| **C3** | job_logs retention + richer lifecycle + tail-follow | D-K19b.8-01, D-K19b.8-02, D-K19b.8-03 | ~~L~~ **XL** (reclassified at CLARIFY) | `[x]` | — |
| **C4** | `useProjectState` action-callback hook tests | D-K19a.5-05 + D-K19a.7-01 (collapsed) | M | `[x]` | — |
| **C5** | Mobile polish: EntitiesTable + PrivacyTab tap targets | D-K19d-β-01, D-K19f-ε-01 | M | `[x]` | — |
| **C6** | Chapter-title resolution for Job + Timeline rows | D-K19b.3-01, D-K19e-β-01 (shared book-service edge) | L | `[x]` | — |
| **C7** | Humanised ETA formatter + stale-offset self-heal | D-K19b.3-02, D-K19e-β-02 | ~~S~~ **XL** (reclassified at CLARIFY) | `[x]` | — |
| **C8** | Drawer-search UX: source_type filter + in-card highlighting (+BE facet counts per user addendum) | D-K19e-γa-01, D-K19e-γb-01 | ~~M~~ **XL** (reclassified at CLARIFY) | `[x]` | — |
| **C9** | Entity concurrency + unlock | D-K19d-γa-01 (If-Match), D-K19d-γa-02 (unlock endpoint) | ~~M~~ **XL** (reclassified at CLARIFY) | `[x]` | — |
| **C10** | Timeline feature gaps | D-K19e-α-01 (entity_id), D-K19e-α-03 (chronological range) | ~~M~~ **XL** (reclassified at CLARIFY) | `[x]` | — |
| **C11** | Cursor pagination (jobs history + Complete list) | D-K19b.1-01, D-K19b.2-01 | ~~M~~ **XL** (reclassified at CLARIFY) | `[x]` | — |
| **C12a** | Scope + runner-side chapter range (paired) | D-K19a.5-04 + D-K16.2-02b | ~~L~~ **XL** (reclassified; split from C12) | `[x]` | — |
| **C12b-a** | Run benchmark CTA — BE half (POST /benchmark-run + orchestrator) | D-K19a.5-07 (BE half) | L | `[x]` | split from C12b per user call; empty-project guard (Option A) + sentinel-set concurrency + FixtureLoadIncompleteError→502; 28 tests |
| **C12b-b** | Run benchmark CTA — FE half (button + loading UX + error toasts) | D-K19a.5-07 (FE half) | ~~M~~ **L** (reclassified at CLARIFY) | `[x]` | inline button in EmbeddingModelPicker blast-radius 3 dialogs; 9-key i18n × 4 + placeholder drift-lock; 21 tests |
| **C12c-a** | `glossary_sync` BE — new entity list endpoint + worker-ai branch + knowledge-service sync endpoint + scope='all' flip | D-K19a.5-06 (BE half) | ~~S FE-only~~ **FS L** (reclassified at CLARIFY per scope-audit feedback memory) | `[x]` | 3-service split: glossary-service Go paginated endpoint + worker-ai GlossaryClient + runner glossary branch + knowledge-service /glossary-sync-entity endpoint; scope='all' now includes glossary (previously silently excluded per TODO at worker runner.py:621); K15.11 helper ON MATCH project_id fix; 3 MED + 3 LOW /review-impl findings all fixed in-cycle |
| **C12c-b** | `glossary_sync` FE — scope radio in BuildGraphDialog + retry-fallback hardening | D-K19a.5-06 (FE half) | ~~S~~ **L** (reclassified at CLARIFY: 7 files trips 6+ threshold) | `[x]` | ALL_SCOPES += glossary_sync; availableScopes gates both chapters AND glossary_sync on book_id; openScope falls back to defaultScope when initialValues.scope is book-required but project lacks book (LOW#1 also fixes pre-existing chapters retry bug); 4 locales + drift-lock; 5 new tests |
| **C13** | Storybook dialogs via MSW | D-K19a.8-01 | M | `[x]` | — |
| **C14a** | Scheduler loops for reconciler + quarantine (create missing background tasks) | D-K11.9-01 partial BE, P-K15.10-01 partial BE | ~~L~~ **L** (split at user request; plan's C14 row understated scope — no sweep loops existed, just callable functions) | `[x]` | 2 NEW scheduler modules mirroring K20.3 shape; advisory lock keys 20_310_004/005; cadences 24h/12h; quarantine inner-loop drain (MED#1 fix 10×); metrics with clarified `errored` semantics; archived users now included (LOW#4 fix); lifespan wire + teardown cancellation; 18 tests |
| **C14b** | Resumable scheduler cursor state (`sweeper_state` table + resume-from-mid-user-list) | D-K11.9-01 cursor-state, P-K15.10-01 cursor-state | ~~M~~ **L** (reclassified at CLARIFY: 7 files trips 6+ threshold) | `[x]` | sweeper_state Postgres table + SweeperStateRepo + reconciler integration with seek predicate + per-user upsert + natural-completion clear + back-compat repo=None path; quarantine cursor doc-only per decision. 14 new tests |
| **C15** | Neo4j fulltext index for entity search (Perf) | P-K19d-01 | S | `[ ]` | fire only when user >10k entities — defer trigger |
| **C16** 🏗 | Budget attribution for global-scope regen (DESIGN-first → BUILD) | D-K20α-01 (cleared) | XL | `[x]` | **DESIGN: ADR shipped** ([KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md](./KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md)) — Option B chosen. **BUILD: shipped C16-BUILD cycle 47** — `knowledge_summary_spending` table + `SummarySpendingRepo` + `check_user_monthly_budget` cross-table SUM + `regenerate_*_summary` pre-check + post-success recorder branching by scope_type + `no_op_budget_exceeded` status + scheduler 4-fn wire-through + main.py + 3 router call sites (public global + project + internal). 1523 unit tests pass (+22 from baseline 1501: 8 repo + 5 DDL + 3 scheduler + 3 regen integration + 3 router wire-through). /review-impl found HIGH-1 (router call sites bypassed gate) — fixed in-cycle |
| **C17** 🏗 | Entity-merge canonical-alias mapping (DESIGN+BUILD bundle) | D-K19d-γb-03 (cleared) | XL | `[x]` | **DESIGN: ADR shipped** ([KNOWLEDGE_SERVICE_ENTITY_ALIAS_MAP_ADR.md](./KNOWLEDGE_SERVICE_ENTITY_ALIAS_MAP_ADR.md)) — Postgres `entity_alias_map` table, mirror-scope key, error-on-conflict, one-shot backfill. **BUILD: shipped C17 cycle 48** — DDL + EntityAliasMapRepo + merge_entity_at_id + resolver alias-map lookup-before-hash + 2 writer plumbing + router collision-precheck + post-merge writes + chain re-point + best-effort failure handling + one-shot backfill helper + KSA §5.0 amendment. 1557 unit tests pass (+34 from baseline 1523: 13 repo + 5 DDL + 5 resolver + 5 backfill + 6 router). /review-impl found HIGH-1 (self-merge wrong error code) + HIGH-2 (Postgres failure surfaced 500 even though Neo4j committed) — both fixed in-cycle |
| **C18** 🏗 | Event wall-clock date (DESIGN+BUILD bundle) | D-K19e-α-02 (cleared) | XL | `[x]` | **DESIGN: ADR shipped** ([KNOWLEDGE_SERVICE_EVENT_WALL_CLOCK_DATE_ADR.md](./KNOWLEDGE_SERVICE_EVENT_WALL_CLOCK_DATE_ADR.md)) — `event_date_iso` TEXT (truncated ISO), LLM-extracted, best-effort Python parse-from-time_cue backfill, timeline `event_date_from`/`event_date_to` Query. **BUILD: shipped C18 cycle 49** — Event model + precision-preserving Cypher CASE (review-impl HIGH-1 fix vs plain coalesce) + LLM extractor field validator + prompt rule §5 + pass2 writer thread + timeline filter (tightened regex per REVIEW-DESIGN catch) + NEW pure parser util + NEW backfill helper + KSA §3.4 amendment. 1604 unit tests (+47 from baseline 1557: 26 parser + 5 backfill + 7 timeline + 1 pass2 + 3 LLM extractor + 3 Cypher source-scan + 2 BC/AD limit locks). /review-impl HIGH-1 fixed in-cycle; MEDIUM-1 (year-range UX) + MEDIUM-2 (BC/AD parser ambiguity) documented + locked |
| **C19** | Multilingual golden-set v2 | D-K17.10-02 (cleared) | ~~S~~ **XL** (reclassified at CLARIFY: 11 files = honest sizing per workflow-gate) | `[x]` | **shipped C19 cycle 50** — 4 fixture pairs: 西遊記 ch01+ch14 (Wu Cheng'en c.1592, PD worldwide) + Sơn Tinh Thủy Tinh + Tấm Cám (Vietnamese folk tradition, PD; original paraphrases). MVTN data REJECTED at CLARIFY (scraped third-party content; LICENSE only covers pipeline software). Tests CJK canonicalization + Vietnamese diacritic preservation + non-honorific kinship terms (dì ghẻ). All 9 fixtures (5 v1 + 4 v2) load via eval_harness. /review-impl found 6 HIGH (synthetic aliases not in text) + 9 MEDIUM + 4 LOW — all fixed in-cycle. Quality eval execution deferred (needs BYOK API key) |
| **C20** | Gate-13 human walkthrough | T2-close-2 | — | `[⏸]` | **USER-ATTESTED** live BYOK walk-through |

Cycles whose single-line description is unclear: the full text lives under the item's row in [SESSION_PATCH Deferred Items](../sessions/SESSION_PATCH.md#deferred-items-cross-session-tracking).

---

## 4. Cycle details

### C1 — merge_entities atomicity + ON-MATCH union (P1, M) ✅
**Shipped.** Session 50 cycle 27.

**Files touched.**
- [`services/knowledge-service/app/db/neo4j_repos/entities.py`](../../services/knowledge-service/app/db/neo4j_repos/entities.py) — steps 4–7 wrapped in `async with await session.begin_transaction() as tx:`; `_MERGE_REWIRE_RELATES_TO_CYPHER` ON MATCH gained 4 CASE branches (`pending_validation` AND with `coalesce(..., false)` matching relations.py convention, `valid_from` earliest-non-null, `valid_until` NULL-wins, `source_chapter` concat-when-distinct); docstring extended with the "fresh session, no open tx" contract.
- [`services/knowledge-service/tests/integration/db/test_entities_browse_repo.py`](../../services/knowledge-service/tests/integration/db/test_entities_browse_repo.py) — +3 integration tests: `test_merge_entities_promotes_validated_edge_over_quarantined` (all 4 union branches incl. `valid_until` NULL-wins), `test_merge_entities_on_match_preserves_quarantine_and_validated` (both mirror AND cases), `test_merge_entities_is_atomic_on_mid_flight_failure` (3-axis rollback proof).

**Verify evidence.** 26/26 browse-repo tests + 105/105 adjacent integration (relations + provenance + entities + k11_5b) + 86/86 entity unit tests.

**/review-impl.** 2 MED + 3 LOW + 1 COSMETIC caught, all 6 folded into same commit. See SESSION_PATCH "Recently cleared" for detail.

**Closed:** D-K19d-γb-01, D-K19d-γb-02.

---

### C2 — Scheduler observability + regen cooldown (P1, S)
**Why.** D-K20.3-α-02 is a one-liner counter increment inside the sweep (folds scheduled regens into the same metric as manual ones). D-K20α-02 cooldown needs a tiny Redis guard on public `/summaries/{...}/regenerate` edges. Both touch operational visibility — pair and ship.

**Files.**
- `services/knowledge-service/app/jobs/summary_regen_scheduler.py` — `regen_status.labels(scope_type=..., status=..., trigger='scheduled').inc()` per project.
- `services/knowledge-service/app/routers/public/summaries.py` — `SETNX knowledge:regen:cooldown:{user}:{scope_type}:{scope_id} EX=60` guard before regen; 429 + Retry-After when set.

**Acceptance.**
- 2 unit tests: metric increments, cooldown 429.
- Manual curl: second regen within 60s returns 429.

**Close:** D-K20.3-α-02, D-K20α-02.

---

### C3 — job_logs retention + richer lifecycle + tail-follow (P2, L)
**Why.** Three items, all in `job_logs` surface (BE retention cron + orchestrator producer + FE tail-follow). Same review pass.

**Files (BE).**
- `services/knowledge-service/app/jobs/job_logs_retention.py` — new cron, DELETE `job_logs` WHERE created_at < now() - interval '90 days', advisory lock, wire into lifespan.
- `services/knowledge-service/app/extraction/orchestrator.py` — `JobLogsRepo.append` for 5–8 new events (chunker stage ms, candidate extractor token count, triple-extraction entities/stage, glossary selector hits).

**Files (FE).**
- `frontend/src/features/knowledge/hooks/useJobLogs.ts` — `refetchInterval: 5000` while job is running; "Load more" when `nextCursor != null`.
- `frontend/src/features/knowledge/components/JobLogsViewer.tsx` — auto-scroll to bottom when user within 100px of bottom.

**Size note.** This is the biggest cycle in the plan. If split is needed: C3a (BE retention + producer) + C3b (FE tail-follow). Confirm with user at CLARIFY if >6 files.

**Close:** D-K19b.8-01, D-K19b.8-02, D-K19b.8-03.

---

### C4 — `useProjectState` action-callback hook tests (P2, M)
**Why.** Shipping K19a.7's compile-time `ACTION_KEYS` map closed half of D-K19a.5-05 — but the other half (verify each of 11 real action callbacks fires the right `knowledgeApi` method + surfaces BE errors as toast) is genuine coverage debt. D-K19a.7-01 partially supersedes D-K19a.5-05; collapse to one cycle.

**Files.**
- `frontend/src/features/knowledge/hooks/__tests__/useProjectState.test.tsx` — new file, `renderHook` + `QueryClientProvider` + mocked `knowledgeApi`, 11 action tests (pause, resume, cancel, retry, extractNew, delete, rebuild, archive, restore, confirmModelChange, disable), each asserts API call shape + toast on BE error.

**Close:** D-K19a.5-05, D-K19a.7-01.

---

### C5 — Mobile polish: EntitiesTable + PrivacyTab (P2, M)
**Why.** K19d-β shipped desktop-first EntitiesTable; K19f shipped mobile shells for other tabs but PrivacyTab audit gap left buttons at 26–30px. Both touch the same mobile responsive strategy — pair.

**Files.**
- `frontend/src/features/knowledge/components/entities/EntitiesTable.tsx` — add `sm:grid-cols-[...] grid-cols-1` responsive split; mobile renders card-per-row with Name + Kind primary, other fields as secondary line.
- `frontend/src/features/knowledge/components/entities/EntityDetailPanel.tsx` — drop `max-w-md` constraint on mobile.
- `frontend/src/features/knowledge/components/PrivacyTab.tsx` — conditional `TOUCH_TARGET_CLASS` application via `useIsMobile()` guard per-button.

**Close:** D-K19d-β-01, D-K19f-ε-01.

---

### C6 — Chapter-title resolution for Job + Timeline rows (P2, L)
**Why.** Two UUID-truncation symptoms (JobDetailPanel "current item", TimelineEventRow chapter) share the same root cause: no chapter-title edge. One BE change unblocks both FE sites.

**BE addition.**
- `services/book-service/internal/api/chapter_titles_handler.go` — new `POST /internal/books/chapters/titles` taking `{ chapter_ids: [uuid] }` → `{ titles: { uuid: "Chapter N — Title" } }`. Batched lookup so the FE can request 10 visible rows in one call.
- knowledge-service `BookClient` gains `get_chapter_titles(chapter_ids) -> dict[UUID, str]`.

**FE wiring.**
- `useChapterTitles(chapter_ids)` hook with 5min `staleTime` + batched debounce.
- JobDetailPanel + TimelineEventRow consume hook, render `"Ch. 12 — The Bridge Duel"` instead of `…last8chars`.

**Close:** D-K19b.3-01, D-K19e-β-01.

---

### C7 — Humanised ETA formatter + stale-offset self-heal (P2, XL) ✅
**Shipped.** Session 51 cycle 33. Reclassified S→XL at CLARIFY (10 files with locales counted).

**Files touched.**
- NEW `frontend/src/lib/formatMinutes.ts` + test — pure util, `formatMinutes(minutes) → "4h"` / `"2h 5min"` / `"15min"` / `"<1min"`. **Named `formatMinutes` not `formatDuration`** per /review-impl MED: 5 local `formatDuration` helpers exist with ms/seconds semantics; explicit unit in name prevents silent misuse.
- MOD `frontend/src/features/knowledge/hooks/useTimeline.ts` — new `UseTimelineOptions.onStaleOffset?: () => void` callback + useEffect fires when `total>0 && offset>0 && events.length===0 && !isLoading && !isFetching && !error`. Backward-compat: options is optional.
- MOD `frontend/src/features/knowledge/components/TimelineTab.tsx` — passes `useCallback([])`-stable `handleStaleOffset: () => setOffset(0)` (/review-impl L4 — stable ref so effect deps don't churn on parent renders). Keeps existing "Back to first" button as defense-in-depth.
- MOD `frontend/src/features/knowledge/components/JobDetailPanel.tsx` — `formatMinutes(minutesRemaining)` at render site line 180; i18n placeholder rename `{{minutes}}` → `{{duration}}`.
- MOD 4 × `frontend/src/i18n/locales/*/knowledge.json` — `jobs.detail.eta` placeholder rename.

**Tests added.**
- `formatMinutes.test.ts` — 7 cases including regression lock for the 59.6min pre-round bug (would have produced `"0h 60min"` without `Math.round` first).
- `useTimeline.test.tsx` — 5 new: self-heal fires under stale conditions, does NOT fire during isLoading/isFetching/error/offset=0, backward-compat options-undefined path.
- `JobDetailPanel.test.tsx` — mutable mock refactor + 2 new: ETA render+spy on formatMinutes(125), paused-job-hides-ETA.
- `projectState.test.ts` — placeholder presence regex across all 4 locales (guards against locale drift).

**/review-impl fixes folded in (5):** (1) formatDuration→formatMinutes rename, (2) {{duration}} placeholder presence test, (3) mutable useJobProgressRateMock + ETA render+spy test, (4) useCallback stability, (5) options-undefined backward-compat test.

**Design decisions.**
- Exact hours drop "0min": `formatMinutes(240) === "4h"` (user preference overrode plan's `"4h 0min"`).
- Self-heal inside hook uses callback pattern (Option B), not hook-owned state (Option A). Rationale: minimal signature change, hook stays self-contained (owns the effect, parent provides callback — analogous to onClick).
- "Back to first" button kept as defense-in-depth against race where callback fires faster than guards.

**Close:** D-K19b.3-02, D-K19e-β-02.

---

### C8 — Drawer-search UX: source_type filter + highlighting + BE facet counts (P2, XL) ✅
**Shipped.** Session 51 cycle 34. Reclassified M→XL at CLARIFY (14 files with locales + user-requested BE counts).

**Files touched.**
- BE repo [`passages.py`](../../services/knowledge-service/app/db/neo4j_repos/passages.py): NEW `count_passages_by_source_type` helper + `KNOWN_SOURCE_TYPES: frozenset` single-source-of-truth constant. `find_passages_by_vector` gains `source_type: str | None = None` kwarg; Cypher WHERE extended with `AND ($source_type IS NULL OR node.source_type = $source_type)`. Helper pads every known type to 0 + logs warning on DB-side source_type drift (data mismatch with constant).
- BE router [`drawers.py`](../../services/knowledge-service/app/routers/public/drawers.py): `DrawerSourceType = Literal['chapter','chat','glossary']` enum (FastAPI 422s unknowns); new `source_type` Query param; **new `source_type_counts: dict[str, int]` response field always padded** (user addendum — requested BE return facet counts); count-session runs after project lookup (for 404 safety) but before every early return branch so "not indexed yet" states still surface coverage.
- BE test [`test_drawers_api.py`](../../services/knowledge-service/tests/unit/test_drawers_api.py): new autouse fixture patches `count_passages_by_source_type` + `neo4j_session` (both now reached in early-return branches); +6 C8 tests (counts in response, filter threads to repo, null-default passes None, enum rejects unknown, no-embedding branch runs counts, whitespace short-circuit returns zero-padded counts).
- BE test **NEW** [`test_passages_count.py`](../../services/knowledge-service/tests/unit/test_passages_count.py) (/review-impl LOW#4): 4 tests — padding missing keys, unknown-type drift+warning, empty-result all-zeros, embedding_model forwarded to Cypher.
- FE util **NEW** [`highlightTokens.ts`](../../frontend/src/lib/highlightTokens.ts) + test (+8 cases incl. regression-lock for leftmost-alternative OR-regex priority per /review-impl LOW#7): whitespace split, ≥2-char tokens (CJK 1-char limitation documented), case-insensitive OR regex with escaped specials, returns `ReactNode[]` with `<mark>` wraps.
- FE api [`api.ts`](../../frontend/src/features/knowledge/api.ts) (/review-impl MED#2): NEW `DRAWER_SOURCE_TYPES` tuple — single source of truth. `DrawerSourceType` derived via `typeof`. `DrawerSearchParams.source_type?`, `DrawerSearchResponse.source_type_counts`, `searchDrawers` forwards query param.
- FE hook [`useDrawerSearch.ts`](../../frontend/src/features/knowledge/hooks/useDrawerSearch.ts): `sourceTypeCounts` result field; `EMPTY_COUNTS` derived from `DRAWER_SOURCE_TYPES` tuple (not hardcoded); queryKey includes `source_type ?? null`. +4 hook tests (pass-through, queryKey invalidation on change, counts surface, zero-padded when disabled).
- FE component **NEW** [`DrawerSearchFilters.tsx`](../../frontend/src/features/knowledge/components/DrawerSearchFilters.tsx): radiogroup-a11y via `<fieldset><input type="radio" class="peer sr-only">` + `<label peer-checked:...>` pills styled via Tailwind. OPTIONS derived from `DRAWER_SOURCE_TYPES` tuple. Counts on typed pills only ("Any" has none).
- FE component test **NEW** [`DrawerSearchFilters.test.tsx`](../../frontend/src/features/knowledge/components/__tests__/DrawerSearchFilters.test.tsx) (/review-impl LOW#5+6): 7 tests — renders 4 pills, counts on 3 not Any, click typed pill, click Any after typed (split per browser "no refire on checked"), checked reflects value, disabled cascades, missing-key defense.
- FE component [`RawDrawersTab.tsx`](../../frontend/src/features/knowledge/components/RawDrawersTab.tsx): wires `sourceType` state + pill row + resets filter to null on project change (/review-impl MED#3) + passes debouncedQuery to cards. +4 interaction tests + 1 regression for project-reset.
- FE component [`DrawerResultCard.tsx`](../../frontend/src/features/knowledge/components/DrawerResultCard.tsx): optional `query?: string` prop; when set, `highlightTokens(textPreview(hit.text), query)` wraps matches.
- i18n 4 locales: `drawers.filters.sourceType.{label,any,chapter,chat,glossary}`.
- FE test [`projectState.test.ts`](../../frontend/src/features/knowledge/types/__tests__/projectState.test.ts) (/review-impl MED#1): added 5 new paths to DRAWERS_KEYS — cross-locale presence regression lock.

**Design decisions locked at CLARIFY.**
1. User addendum: BE returns `source_type_counts` — project-wide facet totals filtered by `project.embedding_model`, reflects "what the search can actually find". Pad to all known types (0 for absent) for stable pill layout.
2. Single-select pill filter (Any + 3), not multi-select — simpler BE contract, matches plan phrasing.
3. Enum validated via Literal at router — FastAPI 422s unknowns.
4. Native `<input type="radio">` + `<fieldset>` for free keyboard a11y (arrow keys, tab, enter/space).
5. Highlight util: whitespace-split, ≥2-char tokens (CJK 1-char documented as limitation), case-insensitive regex with escaped specials.

**/review-impl fixes folded in (7 + 1 accept-lock).**
- (MED#1) cross-locale placeholder presence test
- (MED#2) `DRAWER_SOURCE_TYPES` tuple derivation kills drift between FE/BE enum
- (MED#3) filter reset on project change
- (LOW#4) count-helper drift + embedding_model forward test
- (LOW#5+6) NEW DrawerSearchFilters.test.tsx (7 cases)
- (LOW#7) OR-regex leftmost regression lock (accept+document pattern)
- (COSMETIC#9) ternary parens for clarity

**Close:** D-K19e-γa-01 (source_type filter), D-K19e-γb-01 (in-card highlight).

---

### C9 — Entity concurrency + unlock (P2, XL) ✅
**Shipped.** Session 51 cycle 35. Reclassified M→XL at CLARIFY (15 files with tests + i18n + /review-impl HIGH regression lock).

**Files touched.**
- BE repo [`entities.py`](../../services/knowledge-service/app/db/neo4j_repos/entities.py): NEW `Entity.version: int = 1` Pydantic field. `_node_to_entity` coalesces missing → 1 (pre-C9 backfill). Atomic FOREACH `_UPDATE_ENTITY_FIELDS_CYPHER` with `applied` flag — one round-trip version check + SET. NEW `unlock_entity_user_edited` helper + `_UNLOCK_ENTITY_CYPHER` (idempotent, no If-Match). Version bumps added at 4 user-facing write sites: update, unlock, `_MERGE_ENTITY_CYPHER` (ON CREATE=1, ON MATCH `coalesce(.version, 1) + 1`), `_MERGE_UPDATE_TARGET_CYPHER`.
- BE shared [`repositories/__init__.py`](../../services/knowledge-service/app/db/repositories/__init__.py): `VersionMismatchError.current` widened (duck-typed) to accept Entity alongside Project/Summary without pulling Entity across the Postgres↔Neo4j repo-module boundary.
- BE router [`entities.py`](../../services/knowledge-service/app/routers/public/entities.py): local `_parse_if_match` + `_etag` helpers (duplicated per codebase convention — matches projects.py + summaries.py). PATCH gains strict If-Match contract: 428 on missing, 412 with current body + fresh ETag on mismatch, ETag header on success. GET detail sets ETag. NEW `POST /entities/{id}/unlock` endpoint — no If-Match (matches /archive pattern).
- BE test [`test_entities_browse_api.py`](../../services/knowledge-service/tests/unit/test_entities_browse_api.py): updated 4 existing PATCH tests (send `If-Match: W/"1"`) + 8 new C9 tests (If-Match missing → 428, bad If-Match → 422, version mismatch → 412 with body + ETag, ETag on GET detail success, unlock happy/404/no-If-Match-needed).
- BE test NEW [`test_entities_mutations.py`](../../services/knowledge-service/tests/unit/test_entities_mutations.py): 8 unit tests mocking `run_write` directly — version flow (applies / mismatch raises / returns None on missing), unlock flip + version bump, unlock 404, pre-C9 coalesce backfill, /review-impl HIGH regression locks (source-scan of 4 Cypher strings + pre-C9 round-trip at expected_version=1).
- FE api [`api.ts`](../../frontend/src/features/knowledge/api.ts): `Entity` wire gains required `version: number` + `user_edited: boolean`. `updateEntity(entityId, body, ifMatchVersion, token)` sends `If-Match: W/"N"` via existing `ifMatch()` helper. NEW `unlockEntity(entityId, token)` POST.
- FE hook [`useEntityMutations.ts`](../../frontend/src/features/knowledge/hooks/useEntityMutations.ts): `useUpdateEntity` threads `ifMatchVersion` + invalidates detail query on 412 (so FE next-open sees fresh baseline). NEW `useUnlockEntity`.
- FE hook test [`useEntityMutations.test.tsx`](../../frontend/src/features/knowledge/hooks/__tests__/useEntityMutations.test.tsx): updated updateEntity happy-path (+ifMatch arg) + 1 C9 conflict invalidation test + 2 C9 useUnlockEntity tests.
- FE component [`EntityEditDialog.tsx`](../../frontend/src/features/knowledge/components/EntityEditDialog.tsx): passes `entity.version` as ifMatchVersion on submit; 412 → `entities.edit.conflict` toast + close dialog (hook has already invalidated detail cache).
- FE component test [`EntityEditDialog.test.tsx`](../../frontend/src/features/knowledge/components/__tests__/EntityEditDialog.test.tsx): ENTITY stub gains version + user_edited; happy-path asserts `ifMatchVersion=7` threaded; +1 conflict-toast test.
- FE component [`EntityDetailPanel.tsx`](../../frontend/src/features/knowledge/components/EntityDetailPanel.tsx): NEW Unlock section + CTA, gated on `entity.user_edited=true`. Uses `window.confirm` for lightweight flag-flip recovery (non-destructive, idempotent).
- FE component test NEW [`EntityDetailPanel.test.tsx`](../../frontend/src/features/knowledge/components/__tests__/EntityDetailPanel.test.tsx): 4 tests — hidden when user_edited=false, shown when true, click fires mutation + toasts success, cancel-confirm skips mutation.
- FE test [`projectState.test.ts`](../../frontend/src/features/knowledge/types/__tests__/projectState.test.ts): ENTITIES_KEYS +6 paths (5 unlock + 1 conflict) — cross-locale drift lock.
- i18n 4 locales: 6 new keys (`entities.detail.{unlock,unlockHint,unlockConfirm,unlockSuccess,unlockFailed}` + `entities.edit.conflict`).

**Design decisions locked at CLARIFY (user approved 6 defaults).**
1. /unlock does NOT require If-Match — matches /archive pattern; idempotent flag flip.
2. /unlock flips user_edited=false only; no alias reset (no pre-edit snapshot stored).
3. Schema migration via COALESCE — existing :Entity nodes without version → coalesce to 1 on read, matched in all Cypher writes. No DDL needed.
4. `Entity.version` on response wire + FE sends on next PATCH.
5. 412 response body = current Entity (FE refreshes baseline without second GET) + fresh ETag.
6. 428 Precondition Required on missing If-Match — strict anti-stale-client mode.

**Design refinements at REVIEW-DESIGN (13 questions).**
- Atomic FOREACH pattern replaces two-query approach (one Cypher round-trip).
- Extended scope to bump version at 4 user-facing write sites (update, unlock, merge_entity ON CREATE/MATCH, merge_update_target) — system-internal writes (anchor/archive/promote) deliberately don't bump.
- `_node_to_entity` coalesce=1 matches read-path + Pydantic default.

**/review-impl HIGH + 1 LOW folded in + 3 LOW accepted + 1 COSMETIC skipped.**
- **HIGH**: pre-C9 entities permanently uneditable — read path coalesced missing version to 1 but 4 Cypher `coalesce` used 0, so FE's `If-Match: W/"1"` always 412'd against `current_version=0`. Fixed: aligned all 4 Cypher to `coalesce(.., 1)`. Regression lock via source-scan test.
- **LOW#2**: NEW `test_cypher_version_coalesce_default_matches_read_path` scans the 4 Cypher string literals at import time + NEW `test_update_entity_pre_c9_node_with_expected_version_1_applies` unit round-trip.
- LOW#3 (live-Neo4j test), LOW#4 (untyped fixtures), LOW#5 (no-op unlock bump), COSMETIC#6 (param ordering) — documented/accepted.

**Close:** D-K19d-γa-01, D-K19d-γa-02. **P2 tier 7/7 — DONE.**
**Why.** If-Match on PATCH entity matches the `D-K8-03 If-Match` contract already in effect for projects + summaries — consistency win. Unlock endpoint gives users a recovery path from accidental edits.

**Files.**
- `services/knowledge-service/app/db/neo4j_repos/entities.py` — add `Entity.version INT` via schema migration, ON MATCH `e.version = e.version + 1`.
- `services/knowledge-service/app/routers/public/entities.py` — PATCH gains If-Match contract; add `POST /v1/knowledge/entities/{id}/unlock` that resets `user_edited=false`.
- `frontend/src/features/knowledge/components/entities/EntityEditDialog.tsx` — wire `If-Match` + conflict-retry baseline refresh (mirror `ProjectFormModal` pattern).

**Close:** D-K19d-γa-01, D-K19d-γa-02.

---

### C10 — Timeline feature gaps (P3, XL) ✅
**Shipped.** Session 51 cycle 36. Reclassified M→XL at CLARIFY (15 files with tests + i18n + /review-impl debounce fix).

**Files touched.**
- BE repo [`events.py`](../../services/knowledge-service/app/db/neo4j_repos/events.py): `_LIST_EVENTS_FILTER_WHERE` gains 3 new parameterised predicates — `after_chronological`/`before_chronological` (mirror narrative `event_order` range semantics: strict, NULL excluded when bounded) + `participant_candidates` via `ANY(c IN $participant_candidates WHERE c IN e.participants)`. `list_events_filtered` signature expanded with 3 kwargs + reversed-chrono `ValueError` validation.
- BE router [`timeline.py`](../../services/knowledge-service/app/routers/public/timeline.py): 3 new Query params (`entity_id: str | None` min/max len 1/200, `after_chronological`/`before_chronological` ≥ 0). Resolves `entity_id` via `get_entity(user_id=jwt, canonical_id=entity_id)` → deduped `{ent.name, ent.canonical_name, *ent.aliases}` set (empty strings dropped) → list. Cross-user/missing entity collapses to `[]` (Cypher `ANY(c IN [] WHERE ...)` = false → 0 rows; no 404 existence leak per KSA §6.4). Chronological reversed-range → 422 mirroring existing narrative validation.
- BE test [`test_timeline_api.py`](../../services/knowledge-service/tests/unit/test_timeline_api.py): +6 C10 tests — entity_id resolution happy, entity not found → empty (no leak), chronological range threaded, reversed chrono → 422, empty-string entity_id → 422, all 3 filters combined pass-through.
- FE api [`api.ts`](../../frontend/src/features/knowledge/api.ts): `TimelineListParams` +3 optional fields; `listTimeline` URL param threading additive.
- FE hook [`useTimeline.ts`](../../frontend/src/features/knowledge/hooks/useTimeline.ts): queryKey +3 filter entries (null sentinels).
- FE hook test [`useTimeline.test.tsx`](../../frontend/src/features/knowledge/hooks/__tests__/useTimeline.test.tsx): +3 C10 tests (entity_id + chrono threading, queryKey invalidation on filter change).
- FE component **NEW** [`TimelineFilters.tsx`](../../frontend/src/features/knowledge/components/TimelineFilters.tsx): entity search dropdown reusing `useEntities` (min-2-chars debounce matching `EntityMergeDialog`, project-scoped when `projectId` set) + chronological range number inputs. Selected entity renders as a chip with X-clear. Reversed-range hint shows inline while still letting BE be the authority. **/review-impl MED#1 fix**: chronological inputs gained internal state + 400ms debounced commit so rapid keystrokes (e.g. typing "1500") coalesce to ONE parent `onChronologicalRangeChange` call instead of four. Parent-reset sync effects propagate prop changes to inputs without re-firing the commit.
- FE component test **NEW** [`TimelineFilters.test.tsx`](../../frontend/src/features/knowledge/components/__tests__/TimelineFilters.test.tsx): 7 tests — renders entity + chrono inputs, entity search dropdown (project-scoped), entity chip + clear, chronological debounce regression (4 keystrokes → 1 commit), parent-reset no-re-fire, reversed-range hint.
- FE component [`TimelineTab.tsx`](../../frontend/src/features/knowledge/components/TimelineTab.tsx): 3 new state hooks (entityFilter/afterChronological/beforeChronological) + renders `<TimelineFilters>` between project select and list. **Project-change reset** (C8 pattern) clears entity + chronological filters; filter changes pipe through `handleFilterChange` which also resets pagination offset.
- FE locale drift lock [`projectState.test.ts`](../../frontend/src/features/knowledge/types/__tests__/projectState.test.ts): `TIMELINE_KEYS` +9 paths.
- i18n × 4 locales: 9 new keys under `timeline.filters.{entity, entityPlaceholder, entitySearchMinHint, entityNoMatches, clearEntity, chronologicalRange, after, before, chronoReversed}`.

**Design decisions locked at CLARIFY (6 user-approved defaults).**
1. Resolve `entity_id` server-side → participant candidate list; missing collapses to `[]` (no 404 leak).
2. Ordering stays `event_order ASC`; `sort_by` deferred.
3. Chronological range mirrors event_order semantics.
4. Entity picker UX reuses `useEntities` search pattern.
5. Cross-user safety via JWT-threaded `user_id`.
6. Entity picker project-scoped when `project_id` filter is set.

**Design refinements at REVIEW-DESIGN (15 questions).**
- Reset entity + chrono filters on project change (mirror C8 pattern).
- Router passes `[]` (not `None`) when entity_id specified-but-not-found.
- Narrative ordering retained under chrono filter; `sort_by` follow-up if needed.
- No perf index on chronological_order deferred until profiling.

**/review-impl 1 MED fix + 7 LOW accepted + 1 COSMETIC accepted.**
- **MED#1** (fixed): chronological inputs fired BE call per keystroke — added 400ms debounce + 2 regression tests.
- LOW#2-8 + COSMETIC#9 accepted with documentation (useEntities wasted call pre-existing pattern, whitespace entity_id silent empty, no live-Neo4j test, keyboard a11y gaps, case-sensitive participant match pre-existing, no perf index, reversed-range double-guard harmless, whitespace alias through `if c` truthy check).

**Close:** D-K19e-α-01, D-K19e-α-03. **P3 tier opened: 2/5 items / 1 cycle done.**

---

### C11 — Cursor pagination (jobs history + Complete list) (P3, XL) ✅
**Shipped.** Session 51 cycle 37. Reclassified M→XL at CLARIFY (15 files with tests + i18n + /review-impl 3 fixes).

**Files touched.**
- BE repo [`extraction_jobs.py`](../../services/knowledge-service/app/db/repositories/extraction_jobs.py): NEW `CursorDecodeError` + `_encode_cursor`/`_decode_cursor` (base64-JSON of `{c: completed_at | null, r: created_at, j: job_id}`). `list_all_for_user` returns `(rows, next_cursor)` tuple + `cursor` kwarg. SQL row-value predicate for active (`(created_at, job_id) < ($cur_created, $cur_job)`) + 4-branch NULLS-LAST OR for history (both non-null completed_at: seek lower OR equal-with-tiebreak; row-null + cursor-nonnull: any; both null: tiebreak). `next_cursor` populated only when exactly `limit` rows returned.
- BE router [`extraction.py`](../../services/knowledge-service/app/routers/public/extraction.py): NEW `ExtractionJobsPage` envelope `{items, next_cursor}` + `cursor: str | None` Query param (min/max len 1/500) + 422 on `CursorDecodeError`.
- BE test [`test_extraction_job_status.py`](../../services/knowledge-service/tests/unit/test_extraction_job_status.py): updated 6 existing tests to read `body["items"]` + updated helper to return tuple; +3 new C11 tests (next_cursor threaded, cursor forwarded to repo, malformed 422).
- BE test NEW [`test_extraction_jobs_cursor.py`](../../services/knowledge-service/tests/unit/test_extraction_jobs_cursor.py): 7 codec tests (roundtrip both groups + 5 decode-rejection paths).
- BE integration test [`test_extraction_jobs_repo.py`](../../services/knowledge-service/tests/integration/db/test_extraction_jobs_repo.py) (/review-impl HIGH#1): unpacked 9 existing call sites to `(rows, _)` tuple — tests now compatible with new signature. +2 NEW integration tests (/review-impl LOW#3) exercising the cursor SQL: walk-7-rows-through-pages-of-3 + tied-completed_at-tiebreak — real coverage for the 4-branch OR.
- FE api [`api.ts`](../../frontend/src/features/knowledge/api.ts): NEW `ExtractionJobsPageResponse` type + `listAllJobs` signature with `cursor?` param.
- FE hook [`useExtractionJobs.ts`](../../frontend/src/features/knowledge/hooks/useExtractionJobs.ts): history switches to `useInfiniteQuery`; active stays `useQuery` with envelope `.items` unwrap. NEW `fetchMoreHistory` + `hasMoreHistory` + `isFetchingMoreHistory` fields. **/review-impl MED#2 fix**: conditional `refetchInterval` returns `HISTORY_POLL_MS` when `pages.length ≤ 1`, `false` otherwise — single-page users get 10s freshness back; power users who click Load more accept frozen view until next click (avoids N-page refetch storm per tick).
- FE hook test [`useExtractionJobs.test.tsx`](../../frontend/src/features/knowledge/hooks/__tests__/useExtractionJobs.test.tsx): updated 4 existing tests to return envelope + 5 new C11 pagination tests (`hasMoreHistory` true/false, `fetchMoreHistory` threads cursor, append semantics, no-op when no more).
- FE component [`ExtractionJobsTab.tsx`](../../frontend/src/features/knowledge/components/ExtractionJobsTab.tsx): dropped `COMPLETE_VISIBLE_LIMIT=10` slice (cap was meaningless once paginated) + NEW Load more button below history gated on `hasMoreHistory`; shows `jobs.loadingMore` during in-flight.
- FE component test [`ExtractionJobsTab.test.tsx`](../../frontend/src/features/knowledge/components/__tests__/ExtractionJobsTab.test.tsx): updated old "caps at 10" test to lock removal + 4 new Load-more tests (hidden when false, visible when true, click fires mutation, disabled+loading-label while fetching). `setHookState` helper gains 3 new fields.
- FE locale drift lock [`projectState.test.ts`](../../frontend/src/features/knowledge/types/__tests__/projectState.test.ts): JOBS_KEYS +2 paths.
- i18n × 4 locales: 2 new keys (`jobs.loadMore`, `jobs.loadingMore`).

**Design decisions locked at CLARIFY (6 user-approved defaults).**
1. Cursor scoped to history only; active stays 2s-poll `useQuery`.
2. Response envelope `{items, next_cursor}` applied to both groups for API consistency (active's `next_cursor` always null).
3. base64-JSON opaque cursor encoding.
4. Single Load more button below entire history (Complete + Failed share the same query).
5. Drop `COMPLETE_VISIBLE_LIMIT=10` slice.
6. Active polling preserved (2s).

**/review-impl 3 fixes + 2 LOW accepted + 1 COSMETIC accepted.**
- **HIGH#1** (fixed): 9 integration-test call sites treated return as list. Unpacked to `(rows, _)`.
- **MED#2** (fixed): history polling removed → users missed new completes. Restored as function-form `refetchInterval` gated on `pages.length ≤ 1`.
- **LOW#3** (fixed): added 2 integration tests exercising cursor SQL predicate end-to-end (walk 7 rows, tied tiebreak).
- LOW#4 (accept): mutation invalidation refetches N pages — bounded by user click-rate.
- LOW#5 (accept): `fetchMoreHistory` closure identity — single consumer.
- COSMETIC#6 (accept): cursor `max_length=500` not tested — FastAPI's validation is trusted.

**Close:** D-K19b.1-01, D-K19b.2-01. **P3 tier progress: 4/5 items / 2 cycles done (C10 ✅ + C11 ✅).**

---

### C12a — Scope + runner-side chapter range (paired) (P3, XL) ✅
**Shipped.** Session 51 cycle 38. Split from original C12 (which bundled 4 items at L); honest scope at CLARIFY showed item 3 blocked + item 4 is its own cycle, so C12a covers the paired items.

**Files touched.**
- book-service Go [`server.go`](../../services/book-service/internal/api/server.go) + test: NEW `POST /internal/chapters/sort-orders` endpoint mirrors the titles endpoint shape + 200-cap + scan-error pattern. Returns `{sort_orders: {uuid: int}}`. Keeps existing titles endpoint untouched — no breaking change to C6 callers.
- knowledge-service [`book_client.py`](../../services/knowledge-service/app/clients/book_client.py): NEW `get_chapter_sort_orders(ids) → dict[UUID, int]` with graceful-degrade on any failure (returns `{}`).
- knowledge-service [`extraction_jobs.py`](../../services/knowledge-service/app/db/repositories/extraction_jobs.py): NEW `list_active_for_project(user_id, project_id)` — returns pending/running/paused jobs on a project. Indexed on existing `(project_id)` + status partial index.
- knowledge-service [`events/handlers.py`](../../services/knowledge-service/app/events/handlers.py) `handle_chapter_saved`: C12a runner gate. After project + embedding + Neo4j checks, fetch active jobs; for each `scope='chapters'` job, collect `scope_range.chapter_range`. Disjoint union semantic: if any chapter-scope job has no range, full ingest proceeds (unbounded wins). Otherwise fetch this chapter's sort_order via `get_chapter_sort_orders` and skip (DEBUG log) when sort_order isn't in ANY range. **Graceful degrade**: sort_order fetch failure → over-ingest (safer than silent skip).
- knowledge-service [`extraction.py` router](../../services/knowledge-service/app/routers/public/extraction.py) `_extract_chapter_range`: **/review-impl MED#1 fix** — reject reversed range `from > to` with 422. Before the fix, reversed range passed validation, persisted to DB, and the runner gate then silently skipped every chapter (membership test `lo ≤ sort_order ≤ hi` always false with lo > hi). Matches FE-side `chapterRangeValid` check.
- BE tests: 3 Go (empty/oversized/invalid JSON) + 6 Python event handler (no active chapter jobs → ingest, no-range → ingest, in-range → ingest, out-of-range → skip, disjoint union across 2 jobs with gap, graceful-degrade on fetch failure) + updated estimate test with reversed-range case + **/review-impl LOW#2 fix**: 2 new integration tests for `list_active_for_project` (status filter pending+running+paused only; cross-user isolation).
- FE [`BuildGraphDialog.tsx`](../../frontend/src/features/knowledge/components/BuildGraphDialog.tsx): NEW chapter-range inputs (from/to number inputs) visible only on `scope='chapters'`. Validation: both empty = full scope; both set + from ≤ to = valid bounded range; anything else (partial, reversed, negative, non-int) = inline invalid hint + Confirm disabled. Inputs wired to both estimate and start payloads as `scope_range: {chapter_range: [from, to]}`. Estimate queryKey extended with range so preview refreshes on change. Form reset on dialog reopen.
- FE test [`BuildGraphDialog.test.tsx`](../../frontend/src/features/knowledge/components/__tests__/BuildGraphDialog.test.tsx): +4 C12a tests (picker visibility gated on scope, scope_range threaded on confirm, invalid-hint + disabled Confirm on reversed range, scope_range omitted when inputs empty).
- FE locale drift lock [`projectState.test.ts`](../../frontend/src/features/knowledge/types/__tests__/projectState.test.ts): BUILD_DIALOG_KEYS +5 paths.
- i18n × 4 locales: 5 new keys under `buildDialog.chapterRange.*`.

**Design decisions locked at CLARIFY (6 user-approved defaults).**
1. Split per user call: C12a = items 1+2; C12b = item 4 (Run benchmark CTA, next cycle); C12c = item 3 (glossary_sync, blocked on BE sync surface).
2. NEW book-service endpoint rather than extending titles endpoint — avoids breaking C6 callers.
3. Gate only fires when ≥1 active scope=chapters job has bounded range.
4. Disjoint union check (ingest if sort_order ∈ ANY range) — not outer envelope.
5. Graceful degrade on sort_order fetch failure — over-ingest.
6. FE range inputs empty = full scope; partial/reversed = Confirm disabled + inline hint.

**/review-impl 2 fixes + 3 LOW accepted.**
- **MED#1** (fixed): BE `_extract_chapter_range` accepts reversed range silently. Added `from > to` → 422. Matches FE-side check. Updated existing `test_estimate_scope_range_malformed_rejected` with reversed-range case.
- **LOW#2** (fixed): `list_active_for_project` lacked any integration test. Added 2 integration tests (status filter, cross-user isolation) mirroring existing `list_all_for_user` patterns.
- LOW#3 (accept): retry flow doesn't prefill `chapter_range` into `initialValues` — user retrying a failed ranged job re-enters range. Polish follow-up.
- LOW#4 (accept): per-event `list_active_for_project` query cost — indexed; profile first.
- LOW#5 auto-closed by MED#1 — FE ≤ BE validation symmetry restored.

**Close:** D-K19a.5-04, D-K16.2-02b. **Deferred:**
- D-K19a.5-07 (BE half) → **C12b-a** ✅ below.
- D-K19a.5-07 (FE half) → **C12b-b** deferred.
- D-K19a.5-06 → **C12c** blocked on glossary-service BE sync surface.

---

### C12b-a — Run benchmark CTA (BE half) ✅

**What shipped.** Cycle 39. NEW `app/benchmark/` module + POST endpoint.
- [`app/benchmark/__init__.py`](../../services/knowledge-service/app/benchmark/__init__.py) + [`app/benchmark/runner.py`](../../services/knowledge-service/app/benchmark/runner.py) (NEW) — `run_project_benchmark(...)` orchestrator wrapping K17.9 harness. Typed exception hierarchy (`BenchmarkRunError` + 5 subclasses). `BenchmarkRunResult` frozen dataclass wire projection.
- [`app/routers/public/extraction.py`](../../services/knowledge-service/app/routers/public/extraction.py) — new `POST /{project_id}/benchmark-run` handler + `BenchmarkRunRequest` (runs 1..5, default 3) + `BenchmarkRunResponse`.
- Empty-project guard (**Option A** per CLARIFY): `_has_real_passages` Cypher filters `source_type IN KNOWN_SOURCE_TYPES`; refuses to run on projects that already hold chapter/chat/glossary passages. Matches `eval/fixture_loader.py:54` dedicated-project assumption.
- Concurrency: pure-sync `set[tuple[user,project]]` sentinel via `_try_mark_running` / `_mark_done` (replaces initial `asyncio.Lock` draft after /review-impl MED#2 flagged pre-check + acquire as fragile to refactor).
- `SUPPORTED_PASSAGE_DIMS` pre-flight catches `nomic-embed-text` (dim 768) upfront → 409 `unknown_embedding_model`.
- Partial fixture load (embedder flake) raises `FixtureLoadIncompleteError` → 502 `embedding_provider_flake`, does NOT persist a false-negative row.
- Tests: [`test_benchmark_runner_service.py`](../../services/knowledge-service/tests/unit/test_benchmark_runner_service.py) 15 tests + [`test_public_benchmark_run.py`](../../services/knowledge-service/tests/unit/test_public_benchmark_run.py) 13 tests = 28 green, incl. 3 regression locks (source-scan passage_ingester literals, invariant `benchmark_entity ∉ KNOWN_SOURCE_TYPES`, cypher safety-clause assertion).

**Design decisions locked at CLARIFY (4 user-approved defaults).**
1. Option A empty-project guard (rejected Option B auto-provisioned project, Option C `is_benchmark` flag + migration).
2. 120s sync default — no background-task (ownership clarity > long request).
3. `runs` tunable 1..5, default 3 matches CLI + L-CH-09.
4. Golden-set source hardcoded to `eval/golden_set.yaml` (multi-golden-set would be its own cycle).

**/review-impl 5 non-cosmetic fixes in-cycle (all 5).**
- **MED#1**: regression-lock test scans `passage_ingester.py` source for `source_type=<literal>` and asserts membership in `KNOWN_SOURCE_TYPES`.
- **MED#2**: `asyncio.Lock` → sentinel set (atomic-by-construction, immune to await insertion).
- **LOW#3**: `benchmark_entity ∉ KNOWN_SOURCE_TYPES` invariant test.
- **LOW#4**: `FixtureLoadIncompleteError` + 502 + no-persist contract.
- **LOW#5**: Cypher string-literal safety-clause assertion.
- COSMETIC#6 (skip): `passes_thresholds()` 3× calls — pure comparisons, no I/O.

**Close:** D-K19a.5-07 (BE half). **Deferred:** D-K19a.5-07 (FE half) → **C12b-b**.

---

### C12b-b — Run benchmark CTA (FE half) ✅

**What shipped.** Cycle 40. Inline button in EmbeddingModelPicker + new mutation hook + typed error-code → toast map.
- [`hooks/useRunBenchmark.ts`](../../frontend/src/features/knowledge/hooks/useRunBenchmark.ts) (NEW, 143 LOC) — mirrors useRegenerateBio pattern; prefix-invalidate `['knowledge', 'benchmark-status', projectId]` on success so the badge refreshes across every model variant for this project.
- [`api.ts`](../../frontend/src/features/knowledge/api.ts) `runBenchmark(projectId, runs?, token)` POST helper.
- [`types.ts`](../../frontend/src/features/knowledge/types.ts) `BenchmarkRunResponse` wire type mirroring C12b-a BE.
- [`components/EmbeddingModelPicker.tsx`](../../frontend/src/features/knowledge/components/EmbeddingModelPicker.tsx) — NEW `<RunBenchmarkButton>` inline after the badge, visible when `!data.passed`. Click fires `mutation.mutate({runs: 3})` (hardcoded per CLI + L-CH-09 methodology). **Blast radius**: BuildGraphDialog, ChangeModelDialog, and ProjectFormModal all compose the picker → they all get the CTA for free.
- i18n × 4 locales (`en`/`ja`/`vi`/`zh-TW`) — 9 new keys under `projects.form.benchmark.*`: `run`, `running`, `success` (interpolates `{{model}}` + `{{recall}}`), 5 error codes, `errorGeneric` (interpolates `{{message}}`).
- Tests: [`useRunBenchmark.test.tsx`](../../frontend/src/features/knowledge/hooks/__tests__/useRunBenchmark.test.tsx) 11 tests + [`EmbeddingModelPicker.test.tsx`](../../frontend/src/features/knowledge/components/__tests__/EmbeddingModelPicker.test.tsx) 10 tests = 21 new. Drift-lock in `projectState.test.ts` adds 9 new benchmark paths + 2 placeholder-presence locks.

**Design decisions locked at CLARIFY (4 user-approved defaults).**
1. Button lives **inside EmbeddingModelPicker** (not a standalone BenchmarkPanel) — minimal FE footprint; CTA appears wherever the picker does.
2. **Direct-run, no confirm dialog** — picker sits adjacent to the model select so intent is clear; 15-60s spinner signals work-in-progress.
3. **Inline button spinner** (not modal overlay) — user can tab away; react-query keeps mutation alive.
4. **`runs=3` hardcoded**, not exposed — tuning runs is an operator concern.

**/review-impl 4 fixes in-cycle (MED + 3 LOWs); 2 accepted-with-docstring.**
- **MED#1** (fixed): success toast now interpolates `{{model}}` so mid-run model-swap can't mis-attribute the recall to the newly-selected model.
- **LOW#2** (fixed): `it.each(LOCALES)` placeholder-presence tests for `{{model}}`/`{{recall}}`/`{{message}}` — translator drift lock.
- **LOW#3** (fixed): hook test pins `runs=null` → BE 422 pass-through so a future coercion regression can't silently mask validation.
- LOW#4 (accept+doc): unmount-during-mutation drops the toast — BE still persists + queryClient still invalidates; documented in hook docblock.
- LOW#5 (accept+doc): `<button>` inside `<label>` is a structural smell but label-click forwarding doesn't trigger on button targets; documented + matches existing badge placement.
- COSMETIC#6 (accept+doc): double-click race — React's `disabled={isPending}` updates synchronously; BE sentinel belt-and-suspenders; documented.

**Close:** D-K19a.5-07 (FE half). **C12b pair complete.**

---

### C13 — Storybook dialogs via MSW (P3, M)
**Files.**
- `frontend/.storybook/preview.tsx` + `msw-storybook-addon` install.
- `frontend/src/features/knowledge/components/**.stories.tsx` — stories for BuildGraphDialog / ChangeModelDialog / ErrorViewerDialog, each with MSW handler for the knowledgeApi calls they make.

**Close:** D-K19a.8-01.

---

### C14 — Resumable scheduler cursor state (P4, L)
**Why.** D-K11.9-01 partial + P-K15.10-01 partial share the same root: both tenant-wide offline sweepers need a `job_state` table to survive mid-scan restart. Design the table once, apply to both.

**Files.**
- `services/knowledge-service/app/db/migrate.py` — new `sweeper_state` table (sweeper_name PK, last_user_id UUID, last_scope JSONB, updated_at).
- `services/knowledge-service/app/jobs/reconciler.py` + `app/jobs/quarantine_cleanup.py` — read cursor at start, write at progress checkpoint, clear on full sweep completion.
- 2 integration tests: sweeper restart resumes from cursor; sweeper completion clears cursor.

**Close:** D-K11.9-01 partial, P-K15.10-01 partial.

---

### C15 — Neo4j fulltext index for entity search (P4, S)
**Trigger.** Fire only when single-user entity count approaches 10k. Until then keep CONTAINS scan.

**Files.**
- `services/knowledge-service/app/db/neo4j_schema.cypher` — `CREATE FULLTEXT INDEX entity_name_fts IF NOT EXISTS FOR (e:Entity) ON EACH [e.name, e.aliases]`.
- `services/knowledge-service/app/db/neo4j_repos/entities.py` — swap `list_entities_filtered` WHERE branch to `db.index.fulltext.queryNodes`.

**Close:** P-K19d-01.

---

### C16 🏗 — Budget attribution for global-scope regen (P5, XL, DESIGN-first)
**DESIGN gate.** Produce `docs/03_planning/KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md` choosing:
- Option A: phantom project row for per-user AI spend not tied to real project.
- Option B: new `knowledge_summary_spending` table keyed on (user_id, scope_type, month).
- Trade-offs: A reuses existing code paths + budget-helper; B is cleaner schema + needs new helper.

**Not in scope of BUILD until ADR signed off.**

**Close (on BUILD):** D-K20α-01 partial.

---

### C17 🏗 — Entity-merge canonical-alias mapping (P5, XL, DESIGN-first)
**DESIGN gate.** Amend KSA §3.4.E. The canonical-id hash currently ignores aliases → post-merge extraction re-creates the source display name as a new entity. Design requires:
- New `(user_id, canonical_from_alias) → target_entity_id` lookup (Postgres table OR Neo4j index).
- `merge_entity(name)` consults the lookup BEFORE the canonical-id hash.
- Backfill story for existing merges.

**Not in scope of BUILD until KSA amendment + backfill story signed off.**

**Close (on BUILD):** D-K19d-γb-03.

---

### C18 🏗 — Event wall-clock date (P5, XL, DESIGN-first)
**DESIGN gate.** Amend KSA §3.4. Choose:
- Option A: LLM prompt extracts `event_date` where textually present + null elsewhere.
- Option B: computed from chapter published-date (no LLM change, weaker signal).

Includes Neo4j schema add, LLM prompt update, backfill job for existing :Event nodes.

**Not in scope of BUILD until KSA amendment signed off.**

**Close (on BUILD):** D-K19e-α-02.

---

### C19 — Multilingual golden-set v2 (S, USER-GATED)
**Blocked on you providing** 2 xianxia + 2 Vietnamese chapter text files (out-of-copyright or user-owned).

Once text arrives:
- `services/knowledge-service/eval/fixtures/xianxia_ch01.yaml` etc. — new fixtures mirroring the 5 English ones.
- `python -m eval.run_benchmark --project-id=<test> --embedding-model=...` against each.
- Tune thresholds if CJK canonicalization regression surfaces.

**Close:** D-K17.10-02.

---

### C20 — Gate-13 human walkthrough (USER-GATED)
**Blocked on you** running the 12-step live-stack script in [GATE_13_READINESS.md §5](../sessions/GATE_13_READINESS.md#L95). Agent-runnable pieces are done — this one is attestation.

**Close:** T2-close-2 → Track 2 formally sealed.

---

## 5. Deferrals arisen during closure

> Empty at plan-creation. Every new deferral discovered during any of C1–C20 lands here with: ID, origin cycle, description, target cycle. Carry forward to SESSION_PATCH at cycle COMMIT.

| ID | Origin cycle | Description | Target cycle |
|---|---|---|---|
| D-C3-L7 | C3 | job_logs retention is platform-wide (90d for all users). Per-tenant retention (paid-tier 365d etc.) requires `retention_days` column + per-user loop. | Track 3 (commercial scale) |
| D-C3-L8 | C3 | JobLogsPanel list isn't virtualized — 10k+ rows make DOM sluggish. Swap `<ul>` for react-window or react-virtual. | Track 3 UX polish |

---

## 6. Progress roll-up

| Tier | Open | Done | Blocked |
|---|---|---|---|
| P1 (C1–C2) | 0 | **4 items / 2 cycles (C1 ✅ + C2 ✅)** | 0 |
| P2 (C3–C9) | 0 items | **15 items / 7 cycles (C3 ✅ + C4 ✅ + C5 ✅ + C6 ✅ + C7 ✅ + C8 ✅ + C9 ✅)** | 0 |
| P3 (C10–C13) | 0 | **✅ 12 items / 8 cycles DONE (C10 ✅ + C11 ✅ + C12a ✅ + C12b-a ✅ + C12b-b ✅ + C13 ✅ + C12c-a ✅ + C12c-b ✅)** | 0 |
| P4 (C14a+C14b+C15) | 1 item / 1 cycle (C15 trigger-gated) | **2 items / 2 cycles (C14a ✅ + C14b ✅)** | 0 |
| P5 (C16–C18) | 0 | **3 cycles DONE (C16 ✅ + C17 ✅ + C18 ✅) — TIER COMPLETE** | 0 |
| User-gated (C19–C20) | 1 item / 1 cycle | **1 cycle DONE (C19 ✅)** | 1 ⏸ (C20) |
| Post-C19 quality polish (off-plan, Track-2 extension) | 0 | **5 cycles DONE 2026-04-25/26 (C-PRED-ALIGN ✅ + C-EVAL-DUMP ✅ + C-EVAL-FIX-FORM ✅ + C-BIG-FIXTURE ✅ + C-PROMPT-SCENE ✅)** | 0 |

**Total plan: 35 item-closures across 23 cycles (C14 split into C14a/C14b). Completed: 37 items / 24 cycles within plan + 5 off-plan quality cycles 2026-04-25/26. P1 tier done · P2 tier DONE (7/7) · **P3 tier DONE (12/12)** · **P4 C14 DONE (C14a ✅ + C14b ✅)** · **P5 DONE (C16 ✅ + C17 ✅ + C18 ✅) — TIER COMPLETE** · **User-gated 1/2 DONE (C19 ✅)** · remaining: C15 (trigger-gated), C20 user-gated. **Gap-closure plan itself is ONLY blocked on user attestation walkthrough (C20) and C15 perf trigger.** Post-C19 quality polish cycles addressed extraction-quality issues exposed by running the eval against real BYOK LM Studio: P 0.251→0.435 (+73% rel), R 0.356→0.573 (+61%), FP-trap 0.275→0.175 (−36%) on gemma-4-26b-a4b. See `services/knowledge-service/eval/QUALITY_EVAL_BASELINES.md` for cycle-by-cycle breakdown.
(Some cycles close > 1 item; some items appear in >1 cycle. Check the cycle table for authoritative count.)

---

## 7. Out of scope (intentional)

- **Won't-fix items from SESSION_PATCH §"Won't-fix"** — 4 conscious decisions (hard-coded English Mode-1/2 instructions, backup script, K5 retry backoff, `_cb_fail_count` cosmetic drift). Reviewed on 2026-04-23; all still sound.
- **Track 2 planning items (D-T2-01..05)** — all cleared in sessions 46–47.
- **K17.9 harness extensions** beyond multilingual fixtures — the harness itself is Gate-13 checkpoint #12 and shipped in T2-close-1a. Additional harness work is Track-3 feature expansion, not debt.
- **Gate-13 automation** for checkpoints currently requiring human — by design. Automating BYOK-dependent checkpoints would require committing credentials to CI, which violates CLAUDE.md no-hardcoded-secrets rule.

---

## 8. Success criteria for plan completion

1. All P1+P2+P3 cycles (C1–C13) shipped: correctness gaps closed, polish items landed, coverage debt paid.
2. P4 cycles (C14–C15) either shipped OR explicitly deferred with updated "fire when" trigger in SESSION_PATCH.
3. P5 cycles (C16–C18) either have signed-off DESIGN docs in `docs/03_planning/` OR are marked blocked with explicit owner.
4. C19–C20 user-gated items remain on the list as "user-owned" — plan does not claim them as agent-closable.
5. SESSION_PATCH Deferred Items section's "Naturally-next-phase" table shrinks from 25+ rows to 0–5 rows (only P5/user-gated remaining).
6. New deferrals arisen during closure ([§5](#5-deferrals-arisen-during-closure)) are all categorized and targeted — no orphans.

When 1–6 hold, Track 3 continuation opens cleanly.
