# Plan — Cycle 6: Job & work lifecycle robustness (L, cross-service)

- **Date:** 2026-06-08 · **Branch:** `feat/composition-service` · **Cycle:** branch-debt cleanup #6
- **Clears:** `D-COMP-CHAPTER-INFLIGHT-REAPER` + `D-COMP-POST-WORK-RACE`
- **Services:** composition-service (reaper) + knowledge-service (get-or-create). Cross-service → live-smoke required.
- **PO decisions (2026-06-08):** reaper = **both** (opportunistic + periodic sweep); race = **knowledge-side get-or-create**.

## Item A — D-COMP-POST-WORK-RACE (knowledge-side get-or-create)

**Root cause:** two concurrent first-POSTs for the same book both hit `resolve_work → status="none"` and both call `knowledge.create_project` → a duplicate empty book project ([works.py:128-133](../../services/composition-service/app/routers/works.py#L128)).

**Fix (knowledge-service only):** make `ProjectsRepo.create` get-or-create when `project_type=='book' AND book_id is not None`:
- In a Tx: `pg_advisory_xact_lock(_PROJECT_BOOK_LOCK_NS, hashtext(f"{user_id}:{book_id}"))` → SELECT existing non-archived `project_type='book'` project with that `book_id` (ORDER BY created_at LIMIT 1) → if found return `(it, created=False)`, else INSERT → `(new, True)`.
- Plain INSERT for all other creates (general/translation/code, or book with no `book_id`) — the FE general-project create UX is unchanged.
- Router `create_project` unpacks `(project, created)` → `response.status_code = 200 if not created else 201`; body unchanged.

**Why this also fixes composition:** both concurrent composition POSTs now receive the **same** `project_id` from knowledge → composition's existing work get-or-create (unique on `project_id`, unique-violation catch + re-get, [works.py:142-148](../../services/composition-service/app/routers/works.py#L142)) dedupes the work. **No composition code change for the race.**

**Scope guard:** gated on `project_type=='book'` so it precisely targets the book-binding path composition uses (`knowledge_client` posts `project_type:"book"`), matching `resolve_work`'s book_id-binding semantics without changing general-project creation. No schema/unique-constraint change (a UNIQUE(user,book_id) would break legacy multi-project-per-book rows).

## Item B — D-COMP-CHAPTER-INFLIGHT-REAPER (composition, both)

**Root cause:** the cycle-2 staleness window prevents lockout but leaves orphaned `running`/`pending` jobs lingering (no reaper; composition has no scheduler).

**Fix (composition-service):**
1. **Repo:** `GenerationJobsRepo.reap_stale_jobs(cutoff) -> int` — `UPDATE generation_job SET status='failed', updated_at=now() WHERE status = ANY(_ACTIVE_STATUSES) AND created_at <= $cutoff RETURNING id` (count). Covers all job types (chapter + per-scene hygiene).
2. **Opportunistic:** inside `create_chapter_job_guarded`, under the advisory lock, mark this chapter's stale active node-less jobs failed (`created_at <= cutoff` — the ones the guard's `created_at > cutoff` filter intentionally skipped) before creating the new one.
3. **Periodic sweep:** `main.py` lifespan starts `asyncio.create_task(_reap_loop())` that every `job_reaper_sweep_secs` (new config, default 600s) calls `reap_stale_jobs(now - chapter_inflight_stale_secs)`; task cancelled cleanly on lifespan shutdown. Multi-replica safe (idempotent UPDATE; concurrent sweeps just match 0 on already-reaped rows).

**Window:** reuse `chapter_inflight_stale_secs` (1800s) as THE job-staleness window (same "running this long ⇒ dead" concept); generous → won't reap a legitimately-running job.

## Files
- knowledge: `app/db/repositories/projects.py` (get-or-create), `app/routers/public/projects.py` (200/201), test.
- composition: `app/db/repositories/generation_jobs.py` (reap method + opportunistic), `app/main.py` (sweep task), `app/config.py` (`job_reaper_sweep_secs`), tests.

## Verify
- knowledge unit (get-or-create: sequential repeat returns same project; non-book unaffected) + composition unit (reap_stale marks failed; opportunistic; sweep loop smoke).
- **Cross-service live-smoke** (≥2 services): (1) two concurrent same-book POST /works → exactly one knowledge project + one work; (2) a forced-stale `running` job → reaped to `failed` by the sweep + by the opportunistic path. Mirror cycle-2's `_smoke_chapter_inflight.py`.

## /review-impl — yes (cross-service contract). /amaw — skip (contained idempotency, no migration/auth).

## Risks
- Holding... (none — knowledge get-or-create's lock is released at Tx commit before returning; no cross-service call under the lock).
- General-project UX regression → mitigated by the `project_type=='book'` gate + a test asserting a general create still always inserts.
- Sweep reaping a legitimately-long job → mitigated by the generous 1800s window (> worst-case generation).
