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
| **C4** | `useProjectState` action-callback hook tests | D-K19a.5-05 + D-K19a.7-01 (collapsed) | M | `[ ]` | — |
| **C5** | Mobile polish: EntitiesTable + PrivacyTab tap targets | D-K19d-β-01, D-K19f-ε-01 | M | `[ ]` | — |
| **C6** | Chapter-title resolution for Job + Timeline rows | D-K19b.3-01, D-K19e-β-01 (shared book-service edge) | L | `[ ]` | book-service `/chapters/{id}/title` edge (S add) |
| **C7** | Humanised ETA formatter + stale-offset self-heal | D-K19b.3-02, D-K19e-β-02 | S | `[ ]` | — |
| **C8** | Drawer-search UX: source_type filter + in-card highlighting | D-K19e-γa-01, D-K19e-γb-01 | M | `[ ]` | — |
| **C9** | Entity concurrency + unlock | D-K19d-γa-01 (If-Match), D-K19d-γa-02 (unlock endpoint) | M | `[ ]` | — |
| **C10** | Timeline feature gaps | D-K19e-α-01 (entity_id), D-K19e-α-03 (chronological range) | M | `[ ]` | — |
| **C11** | Cursor pagination (jobs history + Complete list) | D-K19b.1-01, D-K19b.2-01 | M | `[ ]` | — |
| **C12** | Scope + benchmark dialog UX | D-K19a.5-04 + D-K16.2-02b (paired), D-K19a.5-06, D-K19a.5-07 | L | `[ ]` | book-service `from_sort`/`to_sort` already shipped ✓ |
| **C13** | Storybook dialogs via MSW | D-K19a.8-01 | M | `[ ]` | — |
| **C14** | Resumable scheduler cursor state (Perf) | D-K11.9-01 partial, P-K15.10-01 partial | L | `[ ]` | needs `job_state` table design |
| **C15** | Neo4j fulltext index for entity search (Perf) | P-K19d-01 | S | `[ ]` | fire only when user >10k entities — defer trigger |
| **C16** 🏗 | Budget attribution for global-scope regen (DESIGN-first) | D-K20α-01 partial | XL | `[ ]` | DESIGN: phantom project vs `knowledge_summary_spending` table |
| **C17** 🏗 | Entity-merge canonical-alias mapping (DESIGN-first) | D-K19d-γb-03 | XL | `[ ]` | KSA §3.4.E amendment |
| **C18** 🏗 | Event wall-clock date (DESIGN-first) | D-K19e-α-02 | XL | `[ ]` | KSA §3.4 amendment + LLM prompt change + migration |
| **C19** | Multilingual golden-set v2 | D-K17.10-02 | S | `[⏸]` | **USER-PROVIDED** 2 xianxia + 2 VN chapter text |
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

### C7 — Humanised ETA formatter + stale-offset self-heal (P2, S)
**Why.** Two quick UX wins. ETA formatter is pure util. Stale-offset needs one `useEffect` (flagged in CLAUDE.md as smell, so encapsulate inside hook per item's own note).

**Files.**
- `frontend/src/lib/formatDuration.ts` — new `formatDuration(minutes) → "4h 0min"` / `"15min"` / `"<1min"`.
- `frontend/src/features/knowledge/hooks/useJobProgressRate.ts` + `useTimeline.ts` — consume formatter; inside useTimeline add self-heal (offset=0 when total>0 && offset>0 && events.length===0).

**Close:** D-K19b.3-02, D-K19e-β-02.

---

### C8 — Drawer-search UX: source_type filter + highlighting (P2, M)
**Files.**
- `services/knowledge-service/app/db/neo4j_repos/passages.py` — extend `find_passages_by_vector` with optional `source_type: str | None` kwarg; add WHERE branch.
- `services/knowledge-service/app/routers/public/drawers.py` — add `source_type` Query param.
- `frontend/src/features/knowledge/components/drawers/DrawerSearchFilters.tsx` — new filter pill row (chapter / chat / glossary).
- `frontend/src/features/knowledge/components/drawers/DrawerSearchResultCard.tsx` — lexical highlight via `<mark>` wrap on query-term substrings.

**Close:** D-K19e-γa-01, D-K19e-γb-01.

---

### C9 — Entity concurrency + unlock (P2, M)
**Why.** If-Match on PATCH entity matches the `D-K8-03 If-Match` contract already in effect for projects + summaries — consistency win. Unlock endpoint gives users a recovery path from accidental edits.

**Files.**
- `services/knowledge-service/app/db/neo4j_repos/entities.py` — add `Entity.version INT` via schema migration, ON MATCH `e.version = e.version + 1`.
- `services/knowledge-service/app/routers/public/entities.py` — PATCH gains If-Match contract; add `POST /v1/knowledge/entities/{id}/unlock` that resets `user_edited=false`.
- `frontend/src/features/knowledge/components/entities/EntityEditDialog.tsx` — wire `If-Match` + conflict-retry baseline refresh (mirror `ProjectFormModal` pattern).

**Close:** D-K19d-γa-01, D-K19d-γa-02.

---

### C10 — Timeline feature gaps (P3, M)
**Why.** Two filters already documented in K19e.2 plan row but scoped-out of Cycle α. Extend Cypher + router; FE already has hooks for new filters.

**Files.**
- `services/knowledge-service/app/db/neo4j_repos/events.py` — `list_events_filtered` gains `entity_id` (resolves to participant candidates) + `after_chronological` / `before_chronological` kwargs.
- `services/knowledge-service/app/routers/public/timeline.py` — 3 new Query params.
- `frontend/src/features/knowledge/components/timeline/TimelineFilters.tsx` — entity picker (reuse EntitiesTable row click) + two-axis toggle.

**Close:** D-K19e-α-01, D-K19e-α-03.

---

### C11 — Cursor pagination (P3, M)
**Files.**
- `services/knowledge-service/app/db/repositories/extraction_jobs.py` — cursor kwarg on `list_history`.
- `services/knowledge-service/app/routers/public/jobs.py` — `cursor` + `next_cursor` on response.
- `frontend/src/features/knowledge/hooks/useExtractionJobs.ts` — infinite-query replacement for single-page; "Load more" on Complete section.

**Close:** D-K19b.1-01, D-K19b.2-01.

---

### C12 — Scope + benchmark dialog UX (P3, L)
**Why.** D-K19a.5-04 (chapter-range picker) and D-K16.2-02b (runner-side range) are paired per the item row. Ship together or runner silently over-processes. D-K19a.5-06/07 are small additions in the same dialog — fold in.

**Files (BE runner).**
- `services/knowledge-service/app/extraction/chapter_runner.py` — gate `handle_chapter_saved` on the running job's `scope_range`. (Option A from D-K16.2-02b item text.)
- `services/knowledge-service/app/routers/public/extraction.py` — extend benchmark endpoint surface for "Run benchmark" CTA.

**Files (FE).**
- `frontend/src/features/knowledge/components/BuildGraphDialog.tsx` — chapter-range picker (from_sort / to_sort input); glossary_sync scope option; "Run benchmark" CTA button calling POST endpoint.

**Close:** D-K19a.5-04, D-K16.2-02b, D-K19a.5-06, D-K19a.5-07.

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
| P2 (C3–C9) | 11 items / 6 cycles | **3 items / 1 cycle (C3 ✅)** | 0 |
| P3 (C10–C13) | 7 items / 4 cycles | 0 | 0 |
| P4 (C14–C15) | 3 items / 2 cycles | 0 | 0 |
| P5 (C16–C18) | 3 items / 3 cycles | 0 | 0 DESIGN |
| User-gated (C19–C20) | 2 items / 2 cycles | 0 | 2 ⏸ |

**Total plan: 33 item-closures across 20 cycles. Completed: 7 items / 3 cycles. P1 tier done · P2 tier in progress.**
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
