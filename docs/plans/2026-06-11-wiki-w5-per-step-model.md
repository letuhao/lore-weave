# Spec + Plan — W5 / D-WIKI-PER-STEP-MODEL (per-step revise model)

**Date:** 2026-06-11 · **Branch:** `wiki/phase2-change-control` · **Size:** XL (cross-service: knowledge Py + glossary Go + frontend) · **Workflow:** `/loom` v2.2

## Decision (PO at CLARIFY)
The mockup (screen ②) imagined separate **prose + verify** models. Reality: `verify_article` is **rule-based** (grounding-SDK `CanonVerifier` — injection/anachronism/contradiction/regurgitation, **no LLM**). The only LLM in the verify/correction phase is `revise_article`'s **corrective re-generation** (it feeds the canon flags back to an LLM and keeps-if-improved), which today reuses the prose `model_ref`.

So the second model drives the **revise/correction re-gen** — "write with model A, fix canon-flagged articles with model B". Columns/params are named **`revise_model_*`** (not `verify_model_*`) to be honest about what they do. **Null ⇒ reuse the prose model.** A clean article (no HIGH flag, not publish-blocked) never revises, so the revise model only matters for flagged articles — surfaced in the picker hint.

PO also: an **optional** second picker, **AI mode only**, for **both batch + regenerate**, defaulting to "Same as generation".

## Param chain (prose path unchanged; this only adds an optional override on revise)

### Knowledge-service
1. `app/db/migrate.py` — additive `ALTER TABLE wiki_gen_jobs ADD COLUMN IF NOT EXISTS revise_model_ref TEXT, revise_model_source TEXT` (nullable).
2. `app/db/repositories/wiki_gen_jobs.py` — `WikiGenJob` +2 optional fields; `_COLS` + `_row_to_job`; `create()` accepts + inserts them.
3. `app/routers/internal_wiki.py` — `WikiGenerateRequest` +`revise_model_ref`/`revise_model_source` (optional); pass to `repo.create`.
4. `app/wiki/orchestrator.py` — in `_generate_one`, call `revise_article` with `model_source=job.revise_model_source or job.model_source`, `model_ref=job.revise_model_ref or job.model_ref` (fallback when null).

### Glossary-service (delegate forward)
5. `internal/api/knowledge_client.go` `triggerWikiGeneration` — signature + payload: include `revise_model_source`/`revise_model_ref` **only when non-empty** (so knowledge sees null → NULL → fallback).
6. `internal/api/wiki_handler.go` `generateWikiStubs` — request struct +`ReviseModelRef`/`ReviseModelSource`; thread to `triggerWikiGeneration`.

### Frontend
7. `features/wiki/api.ts` — `generateStubs` payload +`revise_model_ref`/`revise_model_source`.
8. `features/wiki/hooks/useWikiGenJob.ts` — `TriggerArgs` +`revise_model_ref`/`revise_model_source`; thread into the payload only when set.
9. `features/wiki/components/GenerateWikiDialog.tsx` — second optional picker in AI mode (batch + regen), state `reviseModelRef` (default '' = same), reset on open + on `selectMode('stub')`; pass `revise_model_ref`/`revise_model_source` when set. Reuses `chatModels`.
10. i18n ×4 — `gen.reviseModel.{label,hint,same}`.

## Acceptance
- Picking a different revise model + generating an article that trips a canon flag runs the corrective revise with the **revise** model; a clean article (no revise) is unaffected; null revise model ⇒ revise uses the prose model (unchanged behavior).
- The picker shows only in AI mode, defaults to "Same as generation", applies to batch + regen.

## Tests
- Knowledge orchestrator: `revise_article` called with the revise model when set; with the prose model when null (extend `test_wiki_orchestrator.py`).
- Glossary: `generateWikiStubs` forwards the revise keys to the trigger (request-parse + payload; live HTTP to knowledge → live-smoke).
- FE: `GenerateWikiDialog` second picker renders in AI mode + `onTrigger` carries `revise_model_ref`.

## Cross-service ⇒ VERIFY needs a live-smoke token (or `D-WIKI-W5-LIVE-SMOKE`).

## Risks
- The revise model is exercised only on flagged articles → easy to think it "did nothing" on a clean run. Mitigation: picker hint says it applies to the correction pass.
- No new provider/model-hardcode (model refs resolve via provider-registry as before). Additive migration; old jobs get NULL → prose-model fallback.
