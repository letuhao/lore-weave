# Spec — Enrichment Compose: free-form input modes (FS / XL) · 2026-06-03

> **Status:** DESIGN-LOCKED, BUILD-PENDING. Branch `lore-enrichment/foundation`.
> **Type:** XL full-stack (BE: new endpoint + strategy + entity-kind + file pipeline; FE: new
> composer tab). Build in slices (§7), each its own VERIFY+POST-REVIEW+COMMIT.
> **Drafts:** [`design-drafts/enrichment-create.html`](../../design-drafts/enrichment-create.html)
> (mockup) + [`design-drafts/enrichment-create-modes.md`](../../design-drafts/enrichment-create-modes.md) (analysis).
>
> **Goal:** let the author start enrichment *the way they want*, not only "fill a detected gap's
> dimensions". Adds 4 input modes to the existing gap-fill, unified into one async **Compose** flow.

## 0. Locked decisions (PO, 2026-06-03)
- **Modes:** A gap-fill *(exists)* · **B** free-text intent · **C** paste context · **D** from-draft · **F** attach files. **Mode E (web search) DROPPED** — copyright-indefensible (analysis §9).
- **Target:** **both** — enrich an *existing* glossary entity OR **create a new entity** from the input.
- **Entity-kind:** **`location` + a new `freeform`** kind (one `description` dimension). CHARACTER/ITEM/FACTION tables are a later, separate unlock.
- **D expand:** **user-selectable** — `add_only` (keep prose verbatim, only add missing dims) | `rewrite` (rewrite + voice-sync).
- **F files:** `.txt .md .pdf .docx .epub`, **OCR ON** for scanned PDFs; user self-asserts responsibility per file (default-deny on a `copyrighted` assertion, same posture as C).
- **Build order:** D → C → F → B.

## 1. Architecture — 5 input *sources*, one async Compose flow

```
[input source] → (resolve TARGET entity) → (ingest text/files as corpus | seed draft | resolve intent)
   → create_job + save_job_request + enqueue → WORKER re-drives (existing path) → generate dimensions
   → C11 H0 chokepoint → ② abstract (recook) → ③ regurgitation guard → C12 verify → quarantined proposal
   → Proposals tab → ④ author promote
```

**The reuse map (why this is mostly composition, not new engines):**
| Mode | How it maps onto existing machinery |
|---|---|
| **A** gap-fill | unchanged — selected gaps → `POST /jobs` / auto-enrich `targets` (already shipped, incl. LE-064 per-row) |
| **C** context | `store.ingest_corpus(text, license)` → corpus → **retrieval/recook job** on the target (worker re-drives unchanged) |
| **F** files | upload → **extract text (+OCR)** → `ingest_corpus` per file → same as C |
| **D** draft | **new `compose_draft` strategy** that expands `StrategyContext.seed_text`; no corpus needed |
| **B** intent | **upfront intent→target resolver** (LLM) → then a normal fabrication/retrieval job |

The async spine is the **existing resume worker** ([`app/worker/resume_consumer.py`](../../services/lore-enrichment-service/app/worker/resume_consumer.py)): it is entirely **request-driven** (`load_job_request` → `targets` → `build_live_runner(technique,…)` → `run_job`). So Compose jobs just persist the right request shape + enqueue — C/F/B need **zero worker change**; D needs only `seed_text`/`expand_mode` threaded into the `StrategyContext`.

## 2. Backend design

### 2.1 Entity-kind: add `freeform` (`app/gaps/model.py`)
- `class EntityKind`: add `FREEFORM = "freeform"`.
- `FREEFORM_DIMENSIONS = (DimensionSpec(dimension=Dimension.DESCRIPTION, label="description", required=True, weight=3.0, payload_shape="prose: free-form description of the subject"),)` — add `Dimension.DESCRIPTION = "description"`.
- `DIMENSIONS_BY_KIND[EntityKind.FREEFORM] = FREEFORM_DIMENSIONS`.
- Everything downstream iterates `dimensions_for(kind)`, so a 1-dim freeform target flows through the runner/strategies/verify unchanged. **Risk:** the C12 dimension-specific checks assume the LOCATION set — verify `description` doesn't break anachronism/contradiction parsing (it shouldn't; they operate on text). Pin with a test.

### 2.2 Target resolution (existing | new)
- `target.mode = "existing"` → `canonical_name` must resolve to a glossary entity for the book (reuse `GlossaryClient.list_entities` / the coverage read). The gap's `present_dimensions` come from coverage (as auto-enrich does).
- `target.mode = "new"` → Compose **creates** the entity in glossary first via the existing bulk-extract path the writeback already uses (`GlossaryClient.bulkExtractEntities` resolves-or-creates by `canonical_name`), kind = `location|freeform`. Then enrich it. H0 unchanged — a freshly-created entity with an enriched supplement is still a quarantined proposal until promote.

### 2.3 `POST /v1/lore-enrichment/compose` (async, 202 + job_id)
Discriminated by `input_source`. Reuses `PgProposalStore.create_job` + `save_job_request` + the resume stream (exactly like `auto-enrich`).
```jsonc
{
  "book_id": "uuid",
  "input_source": "gap | intent | context | draft | files",
  "target": { "mode": "existing|new", "canonical_name": "碧遊宮", "entity_kind": "location|freeform",
              "dimensions": ["history","geography","culture"] | "auto" },
  // one of:
  "gap_targets":  [ { canonical_name, target_ref?, entity_kind, present_dimensions } ],  // A (= existing GapTarget)
  "intent_text":  "…",                                  // B
  "context_text": "…", "context_license": "public_domain|licensed|owned|copyrighted",   // C
  "draft_text":   "…", "expand_mode": "add_only|rewrite", // D
  "upload_ids":   [ "uuid", … ],                         // F (from /uploads, see §2.4)
  // shared output config (same as auto-enrich):
  "technique": "retrieval|fabrication|recook",
  "generation_model_ref": "uuid", "embedding_model_ref": "uuid",
  "max_spend_usd": 0.5, "top_k": 5
}
```
Handler logic by source:
- **gap** → `gap_targets` → create_job(targets) + request + enqueue (≈ today's auto-enrich-with-targets, LE-064).
- **context** → `store.ingest_corpus(text=context_text, license=context_license, …)` (default-deny if `copyrighted`) → create_job(targets=[resolved target]) with `technique` (retrieval/recook) → request + enqueue.
- **files** → for each `upload_id`: load extracted text (from /uploads) → `ingest_corpus` → then same as context.
- **draft** → create_job(targets=[target], technique=`compose_draft`) + request carries `seed_text=draft_text`, `expand_mode` → enqueue.
- **intent** → call the **intent resolver** (§2.6) → fills `target` + `dimensions` + a suggested `technique` → then run as a normal job (fabrication/retrieval).

### 2.4 `POST /v1/lore-enrichment/uploads` (multipart) — mode F only
- Accept files (`.txt .md .pdf .docx .epub`), enforce per-file size (default 25 MB) + page cap (default 300).
- **Store** the raw file in MinIO (reuse the chat-service pattern: [`app/storage/minio_client.py`](../../services/chat-service/app/storage/minio_client.py); add `app/storage/minio_client.py` to lore-enrichment + a bucket `lore-enrichment-uploads`).
- **Extract text** (new `app/files/extract.py`): `.txt/.md` raw; `.pdf` via `pypdf`/`pdfplumber`; `.docx` via `python-docx`; `.epub` via `ebooklib` + `beautifulsoup4` (already vendored). **OCR** scanned PDFs (no/low text layer) via `ocrmypdf`/`pytesseract` (Tesseract in the image; CJK packs `chi_sim`+`chi_tra`). Return `{ upload_id, filename, pages, extracted_chars, ocr_used }`. Persist extracted text keyed by `upload_id` (a small `enrichment_upload` table or MinIO sidecar) so `/compose` can read it.
- **Auth + scope:** per-user/book; default-deny license posture (user asserts in the FE; copyrighted → refused at compose).

### 2.5 New strategy — `DraftExpandStrategy` (mode D)
- New `Technique.COMPOSE_DRAFT = "compose_draft"`, **tier P1** (active/ungated — it expands the *author's own* writing, not fabrication-from-nothing; confirm with QC). Register in `assembly.build_live_runner` factory + a `DraftExpandPipeline` in `app/jobs/stages.py`.
- `run(gap_batch, context)`: reads `context.seed_text` + `context.expand_mode`; builds the expand prompt:
  - `add_only`: "Đây là bản nháp của tác giả cho «{name}». GIỮ NGUYÊN từng câu của tác giả; chỉ BỔ SUNG các dimension còn thiếu ({missing}). Văn phong 封神, JSON."
  - `rewrite`: "…viết lại + đồng bộ giọng 封神, GIỮ NGUYÊN Ý của tác giả; điền các dimension ({dims}). JSON."
- Reuses the C11 `make_enriched_fact` chokepoint (origin=`enriched:compose_draft`, conf<1.0, H0), `repair_generation`, and C12 verify. ③ regurgitation guard still applies. No retrieval/grounding (it's the author's text).
- **`StrategyContext` extension** (`app/strategies/base.py`): `seed_text: str | None = None`, `expand_mode: str | None = None` (frozen model — additive, ignored by other strategies).

### 2.6 Intent resolver (mode B) — `app/compose/intent.py`
- One LLM call (the gen `complete` seam): given `intent_text` + the book's entity list (names+kinds from glossary), return `{ target: existing|new + canonical_name + entity_kind, dimensions: […], technique: retrieval|fabrication }`. Strict JSON, repaired like generation.
- If `existing` resolves to a gap → run that gap; if `new` → create entity (§2.2) → run. Default technique = `fabrication` (canon-grounded invention) unless the resolver finds strong corpus grounding.
- **③ applies** (the model may surface training-data text). No web, no external corpus.

### 2.7 Worker + request shape
- `save_job_request` request gains: `input_source`, `seed_text`, `expand_mode`, `context_corpus_ids` (audit). `redrive_one` ([resume_consumer.py](../../services/lore-enrichment-service/app/worker/resume_consumer.py)) threads `seed_text`/`expand_mode` into the `StrategyContext` it builds (the ONLY worker change). `entity_kind` already flows from the request.
- `build_live_runner`: register `DraftExpandStrategy` in the factory + branch the pipeline/cost for `compose_draft` (mirror the fabrication branch; P1 → ungated, metered).

### 2.8 DB + contract
- **Reuse** `enrichment_job` + `enrichment_job_request` (request is JSONB — the new fields are additive, no migration). Optional: add `enrichment_job.source TEXT` (audit: which input_source) — additive `ADD COLUMN IF NOT EXISTS`.
- New `enrichment_upload` table (mode F): `upload_id, user_id, book_id, filename, mime, pages, extracted_text, ocr_used, license_asserted, created_at`.
- Contract: add `/compose` + `/uploads` to [`contracts/api/lore-enrichment/v1/openapi.yaml`](../../contracts/api/lore-enrichment/v1/openapi.yaml). Gateway needs NO change (`/v1/lore-enrichment/*` catch-all proxy).

## 3. Frontend design (`features/enrichment/`, React-MVC)

The new **"Tạo / Compose"** surface is a **new panel inside `EnrichmentView`** — NOT a new route or BookDetailPage change (the Enrichment book-tab already mounts EnrichmentView; we add a 5th secondary panel leading the strip).

- **`EnrichmentView.tsx`**: add `'compose'` to `EnrichmentPanel` + lead the `PANELS` array; render `<ComposePanel/>` under the no-unmount idiom. (Gaps' per-row *enrich →* can `setActivePanel('compose')` + prefill mode A.)
- **components/compose/** (new):
  - `ComposePanel.tsx` — shell: Step ① mode selector (5 cards) · Step ② mode form · Step ③ shared target+config · run button. Owns compose form state (or a small `ComposeContext`).
  - `ModeSelector.tsx` — 5 cards (A/B/C/D/F) + the "E dropped" note.
  - `ComposeGapForm / ComposeIntentForm / ComposeContextForm / ComposeDraftForm / ComposeFilesForm.tsx` — per-mode inputs (mirror the mockup).
  - `ComposeTarget.tsx` — existing-entity picker | "+ new" (name + kind: location|freeform).
  - `ComposeConfig.tsx` — technique + gen/embed model pickers (reuse `providerApi.listUserModels`) + cost-cap + top_k + the ①②③④ safety strip + H0 chip + eval-gate note.
  - `FileDropzone.tsx` — drag/drop, per-file extraction+OCR status, remove, license assert + "tôi tự chịu trách nhiệm" checkbox.
- **hooks/**: `useCompose.ts` (`compose()` + `uploadFiles()` + invalidate jobs/proposals + toast, async 202 like auto-enrich) ; reuse model-picker query.
- **api.ts / types.ts**: `compose(bookId, body)`, `uploadFiles(bookId, files)` ; `ComposeBody`, `ComposeTargetInput`, `UploadResult`, `EntityKind += 'freeform'`.
- **i18n**: a `compose` namespace across en/vi/ja/zh-TW (mode labels, form labels, OCR/extraction status, responsibility copy, safety strip). UI copy mirrors the Vietnamese mockup.
- **Tests (vitest):** per form + ComposePanel (mode switch, target existing/new, run calls compose with the right body) + useCompose (compose/upload/toasts/invalidate) + FileDropzone (extraction status, license-required-to-run).

## 4. Copyright-safety (the ①②③④ layers, per mode) — reuse, do not weaken
| Layer | A | B | C | D | F |
|---|---|---|---|---|---|
| ① license default-deny | corpus | n/a | assert (deny copyrighted) | own | **assert per file (deny copyrighted)** |
| ② abstract→facts | (recook) | optional | yes | no (their idea) | yes |
| ③ regurgitation guard | yes | yes | yes | yes | yes |
| ④ promote-gate + H0 | yes | yes | yes | yes | yes |

B/C/D/F are **user-driven** (the user performs the sourcing act + bears responsibility; platform = tool). This is why they're defensible where the dropped web mode E is not. **Not legal advice — release needs IP counsel** (surface prominently for C/F).

## 5. Build slices (each = own VERIFY + POST-REVIEW + COMMIT)

| Slice | Scope | Key files | Acceptance |
|---|---|---|---|
| **1 — spine + D** | `POST /compose` skeleton (async) · `freeform` kind · target existing|new · `compose_draft` strategy + `seed_text`/`expand_mode` · worker thread-through · FE "Tạo" panel + ComposePanel shell + ComposeDraftForm + ComposeTarget + ComposeConfig + useCompose · i18n · tests | live: draft → 202 → worker → quarantined proposal for an existing AND a new freeform entity; both expand_modes; FE compose() wired |
| **2 — C paste-context** | compose `context` branch (ingest_corpus + license default-deny) · ComposeContextForm | live: pasted text → corpus → recook proposal; copyrighted assertion refused |
| **3 — F attach-files** | `POST /uploads` (multipart) + `app/files/extract.py` (pdf/docx/epub/txt/md) + OCR (Tesseract chi_sim/chi_tra) + MinIO + `enrichment_upload` · FileDropzone | live: upload .pdf+.docx+scanned-pdf → extract(+OCR) → ingest → proposal |
| **4 — B intent** | `app/compose/intent.py` resolver + compose `intent` branch · ComposeIntentForm | live: intent → resolved target+dims (existing + new) → fabrication proposal |

## 6. Risks / deferrals
- **OCR infra:** Tesseract + CJK language packs must ship in the lore-enrichment image (Dockerfile) + the worker image. Sizeable; consider a separate OCR step/flag. Build-stack freshness guard (LE-061 family) must cover the new image deps.
- **Cost of compose_draft tier:** if QC wants D gate-enforced, flip its tier to P2 (factory already enforces). Default P1 (author's own content).
- **C12 on `freeform`:** confirm anachronism/contradiction checks behave on a single `description` dim (pin a test); they operate on text so should be fine.
- **Large files / cost:** size+page caps + the existing cost-cap bound spend. OCR is slow → keep the upload async/job-like if needed.
- **Intent resolver accuracy (B):** it can mis-map; the user reviews the resolved target in the FE before running (show the resolution, let them edit) — do NOT silently run a wrong target.
- **Entity-kind beyond freeform/location** (CHARACTER/ITEM/FACTION) remains a separate unlock — out of scope here.

## 7. Test plan
- **BE pytest:** `/compose` handler per source (gap/context/draft/intent/files) — 202 + request shape + correct branch (ingest called for C/F, seed_text persisted for D, resolver called for B); `/uploads` extraction (+OCR mock) + size/page/format rejects; `freeform` dimension model; new-entity creation; copyrighted-license refusal; worker re-drive of a `compose_draft` + a `context` job; intent resolver JSON-repair.
- **FE vitest:** per the §3 test list (forms, ComposePanel, useCompose, FileDropzone) — assert on i18n KEYS (house convention).
- **Live-smoke (cross-service):** the 4 slice acceptance rows above, through the gateway, against the rebuilt stack (provider-registry freshness pre-flight; LM-Studio same-owner models). Document the LM-Studio-eviction risk as today.

## 8. Effort (rough)
Slice 1 (L) — the plumbing + D + entity-kind + the whole FE composer shell · Slice 2 (S-M, reuses ingest) · Slice 3 (M-L, OCR/extraction/MinIO infra) · Slice 4 (M, resolver). Total ~XL, multi-session.
