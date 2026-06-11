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

### W3 — Generate dialog + sidebar polish (screens ②①) · **FE-mostly** · S · value LOW–MED
- Mode **segmented toggle** (Mẫu cố định / AI tạo sinh) replacing the bare dropdown (keep the same underlying state).
- Sidebar **"N bài · M do AI sinh"** count (compute M from `generation_status != null` in the list).
- (Optional, needs a signal) **grounding-status line** ("Sách đã lập chỉ mục") — needs an "is this book indexed" read; defer if no cheap signal. **Language picker** — display-only from BookProfile (advisory). **Budget/used** on the cost line — needs usage-billing data → **defer to a phase-2** of this slice.
- Files: `features/wiki/components/GenerateWikiDialog.tsx` · `WikiTab.tsx` (count) · i18n ×4 · vitest.
- **Acceptance:** toggle works + defaults to deterministic; sidebar shows the AI-count split.

### W4 — Job-progress detail (screen ③) · **cross-service, BE-first** · M · value HIGH
The richest mockup screen; the banner is a bare strip today. Slice in two:
- **W4a (BE):** the orchestrator already computes per-entity outcome tokens (`written|suggestion|skipped|writeback_failed`); persist them — add a `results JSONB` (entity_id → {outcome, citations, flags}) on `wiki_gen_jobs`, written as each entity finishes — and expose on the poll (`WikiGenJobStatus.results` + the current entity). The live **4-pass** sub-step is harder (the per-entity pipeline is synchronous); scope it as **advisory** (render the 4 passes statically, highlight none live) OR defer the live-pass indicator entirely. Files: `wiki_gen_jobs.py` (column + writes) · `orchestrator.py` (record outcome detail) · `internal_wiki.py` (`_to_status`) · `wiki_jobs.go` (proxy passthrough).
- **W4b (FE):** a per-entity result table (✓ created · ⚠ created-with-warning · ⊗ skipped-no-grounding · ⏳ processing · queued) under the banner, fed by `results`. Optional static 4-pass row. Files: `WikiGenJobBanner.tsx` (or a new `WikiGenJobDetail.tsx`) · `useWikiGenJob.ts` (thread results) · i18n ×4 · vitest.
- **Acceptance:** during/after a run the FE lists each entity's outcome with citation count + warning flag; matches the audit's screen-③ gap.

### W5 — Per-step verify model (screen ②) · **cross-service** · M · **OPTIONAL — decision-gated**
The mockup shows separate prose + verify models; **neither layer supports it** (a never-built design idea, not incomplete work). Only build if the PO wants it.
- BE: add `verify_model_ref`/`verify_model_source` to `wiki_gen_jobs` + thread into `verify_article`/`revise_article` (fall back to the prose model when null). FE: a second picker in the dialog.
- Tracked as **DEFERRED `D-WIKI-PER-STEP-MODEL`** until the PO decides; do NOT build by default.

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
