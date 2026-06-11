# Plan — Wiki FE gap-closure (post UI-review)

**Date:** 2026-06-11 · **Branch:** `wiki/phase2-change-control` (or a fresh `wiki/fe-polish` off it)
**Source:** the audit [`docs/reports/2026-06-11-wiki-mockup-vs-code-audit.md`](../reports/2026-06-11-wiki-mockup-vs-code-audit.md) §5 (gap list).
**Scope:** close the FE/UX gaps between the 5-screen mockup and the built UI. The **backend pipeline is complete** (audit §3) — these slices are mostly FE, with two that need a small/medium BE addition (flagged).

## Contract facts that decide FE-only vs cross-service (verified this session)
- `listWikiSuggestions` already returns `diff_json` + `user_id` + `reason` ([wiki_handler.go:1787-1797](../../services/glossary-service/internal/api/wiki_handler.go#L1787)) → **diff render is FE-only**.
- `listWikiStaleness` already returns `severity`, `reason_code`, `source_ref`, `detected_at`, `kind` ([wiki_staleness.go:46-49](../../services/glossary-service/internal/api/wiki_staleness.go#L46)) → **severity-bar + per-change metadata are FE-only**; per-row `dismiss` endpoint exists.
- `get_wiki_gen_job` → `WikiGenJobStatus` carries only aggregate counts ([internal_wiki.py:300-319](../../services/knowledge-service/app/routers/internal_wiki.py#L300)) — **no per-entity outcome / current-pass / entity name** → **job-detail needs BE**.
- `wiki/gen-config` flat cost endpoint exists ([internal_wiki.py:354-359](../../services/knowledge-service/app/routers/internal_wiki.py#L354)) → reuse for batch cost-estimate.
- The recipe/KG sweep is **internal-token only** (`POST /internal/books/{id}/wiki/staleness-sweep`) → a FE "rescan" button needs a small **public owner-gated proxy**.

---

## Slices (each its own `/loom`; ordered fast-FE-wins → cross-service)

### W1 — Suggestion diff view (screen ④) · **FE-only** · S · value HIGH
The clobber-guard / H0 trust story is invisible today (suggestions show reason text only).
- Render `diff_json` as a del/add diff in the suggestion panel (the BE already stores it).
- Distinguish **AI-regen** vs **community**: the AI-regen `diff_json` is the envelope `{body_json, generation_status, generation_provenance}`; a community one is a plain field diff. Badge accordingly ("AI tái tạo (grounded)" vs "👥 Cộng đồng").
- (Decide) surface the panel from the **reader** too, not only the editor sidebar (mockup shows it as a main surface). Minimal: a "N đề xuất chờ duyệt" entry point on the reader → opens the existing panel.
- Files: `frontend/src/.../WikiEditorPage.tsx` `SuggestionPanel` (+ a small `WikiDiff` component) · `features/wiki/types.ts` (diff_json shape) · i18n ×4 · vitest.
- **Acceptance:** an AI-regen suggestion shows the body diff + an AI badge; a community one shows a field diff + community badge; accept/reject unchanged.

### W2 — Change-feed richness (screen ⑤) · **cross-service XL** (PO 2026-06-11: include rescan + batch-dismiss endpoint) · value MED
**Scope wrinkle found at CLARIFY:** the rescan (recipe-drift) sweep needs the CURRENT prompt/pipeline versions, which live in knowledge-service — so a real rescan is cross-service, not "a small proxy". PO chose to include it + a real batch-dismiss endpoint.
- **FE (pure):** severity-breakdown bar (count `hard`/`structural`/`content`), batch cost-estimate line (reuse `wiki/gen-config` × selected count), deferred-ledger **info banner**, per-change **metadata** (reason label + `source_ref` + `detected_at`, already returned).
- **Knowledge:** extend `GET /internal/knowledge/wiki/gen-config` (`internal_wiki.py` `WikiGenConfig`) to also return `prompt_version` + `pipeline_version` (from `settings.wiki_prompt_version`/`wiki_pipeline_version`).
- **Glossary:**
  - `knowledge_client.go` `getWikiGenConfig` → parse the two new version fields.
  - `POST /v1/glossary/books/{id}/wiki/staleness/sweep` (NEW, owner-gated) → fetch versions from knowledge gen-config → `sweepRecipeDrift(versions)` + `sweepKgDrift(ownerID)` → `{flagged}`. Knowledge-down degrades to kg-only / 0.
  - `POST /v1/glossary/books/{id}/wiki/staleness/dismiss-batch` (NEW, owner-gated) `{staleness_ids:[]}` → dismiss all in-tx → clear `is_knowledge_stale` when the last pending row goes.
  - `server.go` route registration.
- **FE wiring:** `api.ts` (`sweepStaleness`, `dismissBatch`) · `useWikiStaleness` (`rescan`, `dismissMany`) · `KnowledgeUpdatesPanel.tsx` (rescan button + dismiss-all + the above). i18n ×4.
- Files: knowledge `internal_wiki.py` · glossary `knowledge_client.go`/`wiki_staleness.go`/`server.go` · FE `api.ts`/`types.ts`/`useWikiStaleness.ts`/`KnowledgeUpdatesPanel.tsx` + i18n ×4 · vitest + Go tests (sweep route + dismiss-batch).
- **Cross-service ⇒ VERIFY needs a live-smoke token** (or a tracked deferral).
- **Acceptance:** batch bar shows severity counts + ~$estimate + dismiss-all; rescan triggers a real recipe+kg sweep (versions sourced from knowledge) and refreshes the feed.

### W3 — Generate dialog + sidebar polish (screens ②①) · **FE-only** · M (reclassified from S) · value LOW–MED · ✅ DONE 2026-06-11
- Mode **segmented toggle** (Mẫu cố định / AI tạo sinh) replacing the bare dropdown (keep the same underlying state).
- Sidebar **"N bài · M do AI sinh"** count (compute M from `generation_status != null` in the list).
- (Optional, needs a signal) **grounding-status line** ("Sách đã lập chỉ mục") — needs an "is this book indexed" read; defer if no cheap signal. **Language picker** — display-only from BookProfile (advisory). **Budget/used** on the cost line — needs usage-billing data → **defer to a phase-2** of this slice.
- Files: `features/wiki/components/GenerateWikiDialog.tsx` · `WikiTab.tsx` (count) · i18n ×4 · vitest.
- **Acceptance:** toggle works + defaults to deterministic; sidebar shows the AI-count split.

### W4 — Job-progress detail (screen ③) · **cross-service, BE-first** · M · value HIGH
The richest mockup screen; the banner is a bare strip today. Slice in two:
- **W4a (BE) · L · ✅ DONE 2026-06-11 (PO at CLARIFY: rich-but-compact results + BUILD live pass tracking):** knowledge-service ONLY — the glossary job-status proxy returns the knowledge body **verbatim** (`io.ReadAll`, 64KB-capped), so new fields flow through with zero glossary change.
  - **Schema (`migrate.py`, additive `ALTER … ADD COLUMN IF NOT EXISTS`):** `results JSONB DEFAULT '{}'` (object keyed `entity_id` → `{outcome, citations, flags, name}` — cheap idempotent upsert; doubles as the in-progress + done table) + `current_entity_id TEXT` + `current_pass TEXT` (live sub-step pointer, NULL when idle).
  - **Repo (`wiki_gen_jobs.py`):** `WikiGenJob` +3 fields (+ parse); `record_result(job, entity, detail)` (`results || jsonb_build_object`); `set_progress(job, entity, pass)`; clear the live pointer (→NULL) inside `complete`/`pause`/`fail`, reset in `mark_running`.
  - **Orchestrator (`orchestrator.py`):** `_generate_one` returns `EntityResult{outcome, citations, flags, name}`; writes a preliminary `processing` result once the name is known (live row is nameable; queued entities simply absent), `set_progress` before each pass (`context→generate→verify→revise→writeback`), and the loop records the final result for **every** outcome (incl. `writeback_failed`/`skipped`/defensive `error`).
  - **Status (`internal_wiki.py`):** `WikiGenJobStatus` +`results`/`current_entity_id`/`current_pass`; `_to_status` maps them.
  - **Tests:** orchestrator (record_result + set_progress wiring, results for written/skipped) + status projection. The repo upsert/clear SQL → **D-WIKI-W4A-LIVE-SMOKE** (knowledge unit tests mock the pool, per the M7b precedent). **Risk D-WIKI-W4-RESULTS-64KB:** a single job over ~600 entities could approach the proxy's 64KB body cap (detail kept compact + name-truncated to mitigate).
- **W4b (FE) · M · ✅ DONE 2026-06-11 (PO at CLARIFY: collapsible panel persists after run + labeled step counter):** new `WikiGenJobDetail.tsx` — a collapsible panel under the banner, one row per `results` entry (outcome icon · name · cites · flags), sorted processing-first; the live entity's row shows a spinner + `Verifying… (3/5)` mapping the 5 BE passes; `expanded = open ?? isActive` (auto-open running → auto-collapse complete, toggle sticks), dismissable, `N queued` footer, `key={job_id}` reset. `types.ts` +`WikiGenPass`/`WikiEntityResult` + extended `WikiGenJobStatus` (the hook needs no change — fields arrive on `job` via the verbatim proxy). `WikiTab` mounts it after both banners. i18n ×4 `gen.results`/`gen.outcome`/`gen.pass`. vitest 7. FE-only.
- **Acceptance:** during/after a run the FE lists each entity's outcome with citation count + warning flag; matches the audit's screen-③ gap. **✅ met.**

### W5 — Per-step revise model (screen ②) · **cross-service XL** · ✅ DONE 2026-06-11 (PO greenlit — clears DEFERRED 076)
The mockup showed separate prose + verify models. Reality: `verify_article` is **rule-based** (CanonVerifier, no LLM) — so the second model drives `revise_article`'s corrective re-gen ("write with A, fix canon-flagged articles with B"); null ⇒ prose model. Named `revise_model_*`. Full spec/plan: [`2026-06-11-wiki-w5-per-step-model.md`](2026-06-11-wiki-w5-per-step-model.md).
- BE: `wiki_gen_jobs` +`revise_model_ref`/`revise_model_source` (additive nullable) threaded `WikiGenerateRequest`→`create`→orchestrator (paired fallback keyed on the ref). Glossary `triggerWikiGeneration`/`generateWikiStubs` forward both (omit-when-empty). FE: an optional 2nd picker (AI mode, batch + regen, default "Same as generation").
- **Acceptance:** picking a different revise model + an article that trips a canon flag runs the corrective revise with the override; clean articles unaffected; null ⇒ prose model. **✅ met** (each hop unit-proven; end-to-end → `D-WIKI-W5-LIVE-SMOKE`).

### W6 — Generate-dialog polish (screen ②, gap #6) + change-feed diff-link (screen ⑤, gap #3) · split W6a/W6b
- **W6a (FE) · M · ✅ DONE 2026-06-11 (PO: reuse existing apis; indexed via knowledge-projects read):** three lazy-gated advisory lines in `GenerateWikiDialog` — **language** (`booksApi.getBook().original_language`, advisory proxy; true gen-language lives in BookProfile, not FE-reachable), **grounding-status** (AI mode, `knowledgeApi.listProjects({book_id})` → built/not-built), **budget/used** (AI mode, `usageApi.getGuardrail()` → monthly used/limit, only when a limit is set). i18n ×4 `gen.context.*`. vitest 4. FE-only, no new BE.
- **W6b (cross-service XL) · ⏳ NEXT (PO chose true snapshots):** the per-staleness-row "xem thay đổi" diff. **No stored before-state today** (`source_ref` is a reference; `build_inputs` is a hash). Likely: before = `wiki_article_source_usage` snippet (captured at gen time — verify), after = current source (cross-service fetch per `source_type`), render via the W1 `wikiDiff` lib. Own `/loom` with its own CLARIFY (which source_types; degrade kg/recipe drift which lack a text before).
- **Acceptance (W6a):** the dialog shows the book language + (AI mode) the indexed status + monthly spend context. **✅ met.**

---

## Sequencing & sizing

| Order | Slice | Layer | Effort | Value | Note |
|-------|-------|-------|--------|-------|------|
| 1 | **W1** Suggestion diff | FE-only | S | HIGH | fastest high-value win; BE-ready |
| 2 | **W2** Change-feed richness | FE + small BE | S–M | MED | 1 sweep-proxy is the only BE |
| 3 | **W3** Dialog + sidebar polish | FE-mostly | S | LOW–MED | defer the indexed/budget sub-items |
| 4 | **W4** Job-progress detail | cross-service | M | HIGH | BE-first (W4a → W4b) |
| — | **W5** Per-step model | cross-service | M | — | OPTIONAL, decision-gated → DEFERRED |

**Recommendation:** run W1→W2→W3 (pure-FE / tiny-BE, low risk, quick polish) as a batch, then W4 (the one genuinely cross-service slice with real value), and hold W5 behind a PO yes/no. Each slice ships committed + handoff-updated; live-smoke the FE in a browser pass at the end (the deferred `D-WIKI-*-LIVE-SMOKE` rows).

## Out of scope
- Backend pipeline changes (complete per audit §3).
- The mockup's `.relbar` relevance-bar styling on references (cosmetic; relevance already shows in the citation-chip popover).
- Anything in the platform system-config epic (separate, DEFERRED 075).
