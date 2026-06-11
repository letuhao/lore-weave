# E0-3 Phase 2a — caller-pays billing plumbing (PLAN)

> **Date:** 2026-06-11. **Phase:** PLAN (loom, XL parent → 2a is the additive plumbing slice).
> **Invariant guard:** every change is additive; `billing_* IS NULL ⇒ legacy single-identity path`. Route stays **owner-only** through all of 2a, so there is **zero behavior change and zero breach window**. Feature goes live only in 2b.
> Parent design: [`2026-06-11-e0-3-caller-pays-extraction-design.md`](2026-06-11-e0-3-caller-pays-extraction-design.md).

## Dual-identity rule (applied at every provider-call site)
- **Provider call (key+budget):** `user_id = billing_user_id or job.user_id`; `model_ref = billing_<llm|embedding>_model or job.<llm_model|embedding_model>`.
- **Everything else (graph partition, cursor, status, storage `embedding_model` tag, telemetry):** **always** `job.user_id` / `job.embedding_model` (the project's canonical UUID — the search filter).
- **Fail-safe:** `billing_user_id` set but the matching billing ref is NULL ⇒ **fail the job** (never fall back to the owner's key).

## Commit 2a-1 — schema + repo + worker LLM caller-attribution backbone
1. **Migration** `services/knowledge-service/app/db/migrate.py` — after the `campaign_id` ALTER:
   ```sql
   ALTER TABLE extraction_jobs
     ADD COLUMN IF NOT EXISTS billing_user_id         UUID,
     ADD COLUMN IF NOT EXISTS billing_embedding_model TEXT,
     ADD COLUMN IF NOT EXISTS billing_llm_model       TEXT;
   ```
2. **Repo** `extraction_jobs.py` — add 3 fields to `_SELECT_COLS`, `ExtractionJob`, `ExtractionJobCreate`; extend `create` INSERT (NULL-defaulting). Optional/`None` defaults so all existing callers compile unchanged.
3. **worker-ai** `runner.py` — `JobRow` +3 fields; `_get_running_jobs` SELECT reads `j.billing_user_id, j.billing_embedding_model, j.billing_llm_model`.
4. **worker-ai** `runner.py` — pure resolution helpers + fail-safe:
   - `eff_billing_user(job) = job.billing_user_id or job.user_id`
   - `eff_llm_ref(job) = job.billing_llm_model or job.llm_model`
   - `eff_embed_ref(job) = job.billing_embedding_model or job.embedding_model`
   - `assert_billing_complete(job)` → raise if `billing_user_id` set and either ref NULL (fail-safe).
5. **worker-ai** `llm_client.py` — billing contextvar mirroring `set_campaign_id`: `set_billing_user_id(str|None)`; in `submit_and_wait`, resolve `user_id = _billing_user_id_ctx.get() or user_id`.
6. **worker-ai** `runner.process_job` — at top (next to `set_campaign_id`): `assert_billing_complete(job)`; `set_billing_user_id(str(job.billing_user_id) if job.billing_user_id else None)`. At the `extract_pass2` call sites, pass `model_ref=eff_llm_ref(job)` instead of `job.llm_model`/`run_snapshot.model_ref`. (Embedder sites unchanged in 2a-1 → still owner; safe because route is owner-only, so `billing_user_id` is always NULL in production until 2b.)
7. **Tests:** `eff_*` + `assert_billing_complete` (fail-safe) unit; `submit_and_wait` billing-contextvar override; repo create persists NULL billing; SELECT round-trips the 3 cols.

## Commit 2a-2 — embedder caller-attribution (separate commit, same slice)
- `persist-pass2` request gains `billing_user_id`/`billing_embedding_model`; threads to `passage_ingester` (provider call uses billing, `upsert_passage.embedding_model` stays project's).
- `summary.*` message gains billing fields → `summary_processor.embed` uses billing ref, stores project tag.
- `entity_embedder.embed` uses billing ref.

## Out of scope (2b / tracked)
- Route `require_project_principals`, OWNER→EDIT, dimension-guard 409 — **2b**.
- `raw_search`/`drawers` query-embeddings — `D-E0-3-SEARCH-QUERY-CALLER-PAYS`.

## /review-impl findings (2026-06-11)
- **MED-1 (FIXED in 2a-1):** `eff_llm_ref`/`eff_embed_ref` + the chapter-path LLM site now gate on `billing_user_id` (the identity), not the individual ref — an orphan ref without a user is ignored (owner path), staying coherent with the `submit_and_wait` contextvar. Regression test: `test_eff_ref_helpers_ignore_orphan_ref_without_billing_user`.
- **MED-2 (FIXED in 2a-1):** added `test_process_job_fails_job_on_partial_billing_identity` + `_runs_normally_with_complete_billing` — proves the fail-safe is wired inside `process_job`'s `try` (partial billing → `_fail_job`, no provider call) and complete billing proceeds.
- **LOW-1 (2b PREREQUISITE — must-do):** the START/rebuild inline INSERT `_create_and_start_job` in `routers/public/extraction.py` inserts only 8 cols and does **NOT** persist billing. 2b sets billing on the collaborator start path → it would be **silently dropped**. 2b MUST extend `_create_and_start_job`'s INSERT (or route the collaborator path through the repo `create`) before flipping the gate.
- **LOW-2 (document):** `list_active`/`list_all_for_user` build custom column lists that omit billing → a future read of `job.billing_*` off those returns None silently. Safe today; add billing to those SELECTs if a caller ever needs it.
- **LOW-3 (2b revisit):** reasoning advisory `get_model_name("user_model", job.llm_model)` (`runner.py` ~L1380) assumes owner-context; for a collaborator job revisit whether it should use `eff_llm_ref`. Non-fatal (wrapped in try/except).

## Verify
- `pytest` worker-ai + knowledge-service extraction/repo suites green.
- No live-smoke needed for 2a (NULL=legacy, no behavior change); 2b carries the ≥3-service live-smoke.
