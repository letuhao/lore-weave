# Spec — Enrichment Compose: free-form input modes (FS / XL) · 2026-06-03 (REVISED 2026-06-04)

> **✅ STATUS: REVISED — READY TO BUILD (slices 1–4).** The benchmark
> ([`2026-06-03-enrichment-compose-review.md`](2026-06-03-enrichment-compose-review.md)) said
> *REVISE before build*; this revision folds in every finding (F1–F11) and **reconciles the spec
> with what the de-bias epic actually shipped (C1+C2+C3 + followups, all live-proven + pushed)**.
> Branch `lore-enrichment/foundation`.
>
> **What changed since the original (2026-06-03 → 2026-06-04):**
> - **F2 (BLOCK) — RESOLVED.** Prompts are no longer 封神-hardcoded: C1 made every generator
>   prompt **book-aware** via per-book `BookProfile` (worldview/era/voice/language + dynamic
>   dimensions), C3 added the authoring API + FE Settings. Compose now works on **any book in its
>   own worldview/voice/language** — the old "Slice 0 prerequisite" is **DONE**, not pending.
> - **F6 — RESOLVED-by-pattern.** C2 shipped the exact ingest seam C/F need:
>   `SourceCorpusStore.ingest_corpus(text, license, embed_fn, model_ref)` driven from a handler that
>   builds the embed seam (`POST …/books/{id}/ground` is the working precedent). C/F copy that shape.
> - **Multi-kind reconcile.** C1 shipped `character/location/item/faction/event` + a **GENERIC**
>   fallback, all *dynamic* (free `str`, `resolve_dimensions(kind, profile)`). The original
>   "`location`+new `freeform` kind only, others later" is **obsolete** — Compose targets **any
>   modeled kind or GENERIC** (PO 2026-06-04). No new `freeform`/`Dimension.DESCRIPTION` enum is added.
> - **PO decisions (2026-06-04):** new-entity creation is **in slice 1** (not deferred) ·
>   target kind = **any modeled kind + GENERIC** · mode **D = P1 ungated** · mode **F = full incl OCR**.
> - F1/F3/F4/F5/F7 folded into §2.2/§2.5/§2.6; F8–F11 into §6.
>
> **Type:** XL full-stack, build in slices (§5), each its own VERIFY+POST-REVIEW+COMMIT.
> **Drafts:** [`design-drafts/enrichment-create.html`](../../design-drafts/enrichment-create.html) +
> [`design-drafts/enrichment-create-modes.md`](../../design-drafts/enrichment-create-modes.md).
>
> **Goal:** let the author start enrichment *the way they want*, not only "fill a detected gap's
> dimensions". Adds 4 input modes to the existing gap-fill, unified into one async **Compose** flow.

## 0. Locked decisions (PO — 2026-06-03, amended 2026-06-04)
- **Modes:** A gap-fill *(exists)* · **B** free-text intent · **C** paste context · **D** from-draft · **F** attach files. **Mode E (web search) DROPPED** — copyright-indefensible (analysis §9).
- **Target:** **both existing + new, from slice 1** (2026-06-04) — enrich an existing glossary entity OR create a new one from the input. The create path reuses the writeback `extract-entities` (resolve-or-create) seam (§2.2, F1).
- **Entity-kind:** **any kind C1 models (`character/location/item/faction/event`) or `GENERIC`** (2026-06-04). "Freeform" input → the **GENERIC** kind (C1's `GENERIC_DIMENSIONS`: description / details / significance). **No new enum** — C1's `resolve_dimensions(kind, profile)` already handles arbitrary kinds + profile overrides.
- **D expand:** **user-selectable** — `add_only` (keep prose verbatim, only add missing dims) | `rewrite` (rewrite + voice-sync to the book's profile voice).
- **D tier:** **P1 (ungated)** (2026-06-04) — it expands the *author's own* writing; still H0-quarantined + ③ + ④ promote-gate. (Flip to P2 later if QC wants the eval gate.)
- **F files:** `.txt .md .pdf .docx .epub`, **OCR ON** for scanned PDFs (Tesseract `chi_sim`+`chi_tra`); user self-asserts responsibility per file (default-deny on a `copyrighted` assertion).
- **Build order:** D → C → F → B.

## 0.1 What the de-bias epic already shipped (Compose builds on this)
Compose is now **composition on top of a book-aware foundation** — these are DONE + live-proven:
| Capability (cycle) | What Compose reuses |
|---|---|
| **Book-aware prompts** (C1) — `BookProfile` (worldview/era/voice/language) read by every generator + verifier; `NEUTRAL_PROFILE` default | every mode generates in the book's own voice/language — no 封神 hardcode |
| **Multi-kind dynamic dimensions** (C1) — `resolve_dimensions(kind, profile)`, `GENERIC` fallback, no enum gate | `freeform`→GENERIC; any target kind flows through the runner/verify unchanged |
| **Grounding composer** (C2) — corpus ∪ glossary-canon ∪ knowledge-context, deduped/top-K | C/F's ingested corpus is one more grounding source; recook/retrieval get richer grounding for free |
| **Ingest seam** (C2 `/ground`) — `ingest_corpus(text, license, embed_fn, model_ref)` from a handler with a `KnowledgeClient` embed seam | **C/F copy this exact handler shape** (F6) |
| **Profile authoring** (C3) — GET/PUT/suggest + FE Settings + i18n×4 | the author sets the book's worldview before composing; Compose inherits it at runtime |

## 1. Architecture — 5 input *sources*, one async Compose flow

```
[input source] → (resolve TARGET: existing | new) → (ingest text/files as corpus | seed draft | resolve intent)
   → create_job + save_job_request + enqueue → WORKER re-drives (existing path) → resolve_dimensions(kind, profile)
   → generate (book-aware, C1) → C11 H0 chokepoint → ② abstract (recook) → ③ regurgitation guard (N/A for D)
   → C12 verify (profile-driven anachronism) → quarantined proposal → Proposals tab → ④ author promote
```

**Reuse map (composition, not new engines):**
| Mode | How it maps onto existing machinery |
|---|---|
| **A** gap-fill | unchanged — selected gaps → auto-enrich `targets` (shipped, incl. LE-064 per-row) |
| **C** context | `ingest_corpus(text, license)` → corpus → retrieval/recook job (worker re-drives unchanged); grounding composer (C2) picks it up |
| **F** files | upload → extract text (+OCR) → `ingest_corpus` per file → same as C |
| **D** draft | **new `DraftExpandStrategy` + `DraftExpandPipeline`** seeded by `StrategyContext.seed_text`; **own generation path** (no grounding), **synthetic authored provenance** |
| **B** intent | **2-step**: `/compose/resolve-intent` (LLM → proposed target+dims+technique, no job) → FE confirm → normal `/compose` |

The async spine is the existing request-driven resume worker (`app/worker/resume_consumer.py`): `load_job_request` → `targets` → `build_live_runner(technique)` → `run_job`. C/F/B need **zero worker change**; D needs only `seed_text`/`expand_mode` threaded into `StrategyContext` + the new pipeline branch.

## 2. Backend design

### 2.1 Entity-kind — NO new kind; reuse C1's dynamic dimensions
- **Dropped from the original spec:** `EntityKind.FREEFORM`, `Dimension.DESCRIPTION`, `FREEFORM_DIMENSIONS`. C1 already provides `GENERIC_KIND` + `GENERIC_DIMENSIONS` (description/details/significance) and `resolve_dimensions(kind, *, language, overrides)` that never raises for an unknown kind.
- **Compose target `entity_kind`** is a free `str`: any modeled kind (`character/location/item/faction/event`) → its static table; `generic` (or any unmodeled string) → `GENERIC_DIMENSIONS`. Dimensions localize via the book's `profile.language` + any `dimension_overrides` (C1/C3). The "freeform" input mode simply sends `entity_kind="generic"`.
- **No glossary Go change** (C1 verified: `entity_enrichments.dimension` is free TEXT; kinds are pre-seeded by extraction). **Risk retired:** C12 checks operate on text, and C1's multi-kind live-smoke already ran character/organization dims through verify — `generic`/`description` is safe; pin with one test.

### 2.2 Target resolution (existing | new)
- `target.mode="existing"` → `canonical_name` resolves via `GlossaryClient.list_entities` / coverage (as auto-enrich does); `present_dimensions` from coverage.
- `target.mode="new"` (F1 — feasible, **not** blocked) → **defer creation to PROMOTE time (H0-cleanest — design-review 2026-06-04).** Do **NOT** write the new entity to glossary at compose/enrich time — that would pollute glossary with un-promoted anchors that survive a rejected proposal. Enrichment does **not** need the glossary entity to exist during generation: it generates dimensions for `canonical_name` (grounded via corpus/profile), and `present_dimensions = []` for a never-seen name (so every requested dim is "missing" → generate all). The proposal simply carries `target.mode="new"` + `canonical_name` + `entity_kind`. **At ④ promote**, the **existing** writeback seam mints the anchor: `write_entity_through_glossary` already POSTs `/internal/books/{id}/extract-entities` which **resolves-or-creates** by name — so a new target's first promote creates the anchor + writes the quarantined supplement, an existing target's resolves it. **H0-clean:** nothing enters glossary until the author promotes; reject leaves glossary untouched; no new compose-time glossary write, **no new client method needed** (reuse the promote path). **Verify in BUILD:** promoting a `mode="new"` proposal mints exactly one anchor (resolve-or-create idempotent) with the chosen kind + the enriched supplement, origin=enrichment.

### 2.3 `POST /v1/lore-enrichment/compose` (async, 202 + job_id)
Discriminated by `input_source`. Reuses `PgProposalStore.create_job` + `save_job_request` + the resume stream (exactly like `auto-enrich`).
```jsonc
{
  "book_id": "uuid",
  "input_source": "gap | intent | context | draft | files",
  "target": { "mode": "existing|new", "canonical_name": "碧遊宮",
              "entity_kind": "character|location|item|faction|event|generic",
              "dimensions": ["history","geography","culture"] | "auto" },
  // one of:
  "gap_targets":  [ { canonical_name, target_ref?, entity_kind, present_dimensions } ],  // A
  "intent_text":  "…",                                  // B — but B normally arrives pre-resolved (§2.6.1)
  "context_text": "…", "context_license": "public_domain|licensed|owned|copyrighted",   // C
  "draft_text":   "…", "expand_mode": "add_only|rewrite", // D
  "upload_ids":   [ "uuid", … ],                         // F (from /uploads, §2.4)
  // shared output config (same as auto-enrich):
  "technique": "retrieval|fabrication|recook|compose_draft",
  "generation_model_ref": "uuid", "embedding_model_ref": "uuid",
  "max_spend_usd": 0.5, "top_k": 5
}
```
Handler logic by source:
- **gap** → create_job(targets=gap_targets) + request + enqueue (≈ auto-enrich-with-targets, LE-064).
- **context** → `ingest_corpus(text=context_text, license=context_license)` (default-deny if `copyrighted`) via the **handler embed seam** (F6: build `make_embed_query_fn`/`embed_fn` like `assembly`/the `/ground` handler do; ingest **synchronously**) → create_job(targets=[resolved target], technique) → enqueue. **Cap `context_text`** (default ~50 KB, validated like F's per-file cap) so a huge paste can't fan out into an unbounded synchronous embed in the request path; over-cap → 413/422 with a clear message (large material → use mode F upload, which is async/poll per F10).
- **files** → for each `upload_id`: load extracted text (§2.4) → `ingest_corpus` → then same as context.
- **draft** → create_job(targets=[target], technique=`compose_draft`) + request carries `seed_text`, `expand_mode` → enqueue.
- **intent** → normally the body already carries a **confirmed** `target` (resolved via §2.6.1) → runs as a normal fabrication/retrieval job. (A one-shot `intent_text` without prior resolution is allowed but discouraged; the FE always goes through resolve-intent.)

### 2.4 `POST /v1/lore-enrichment/uploads` (multipart) — mode F
- Accept `.txt .md .pdf .docx .epub`; per-file size cap (default 25 MB) + page cap (default 300).
- Store raw in MinIO (reuse chat-service's `minio_client.py` pattern; bucket `lore-enrichment-uploads`).
- Extract text (`app/files/extract.py`): `.txt/.md` raw; `.pdf` via `pypdf`/`pdfplumber`; `.docx` via `python-docx`; `.epub` via `ebooklib`+`beautifulsoup4`. **OCR** scanned PDFs (no/low text layer) via `ocrmypdf`/`pytesseract` (Tesseract + `chi_sim`+`chi_tra` in BOTH the service + worker image). Return `{ upload_id, filename, pages, extracted_chars, ocr_used }`.
- Persist extracted text keyed by `upload_id` (`enrichment_upload` table) so `/compose` reads it. Per-user/book scope; default-deny license (asserted in the FE).
- **F10:** for large scans OCR is slow — make `/uploads` job-like (return `upload_id` immediately, extract+OCR async, poll status) so a 300-page scan can't time out the request.

### 2.5 Mode D — `DraftExpandStrategy` (own path; F3/F4/F7)
Mode D does **not** reuse the grounding generator (it has no corpus). Three hard requirements from the benchmark:
- **Own pipeline branch (F4):** add `Technique.COMPOSE_DRAFT="compose_draft"` (**tier P1**) + a `DraftExpandPipeline` in `app/jobs/stages.py`; `build_live_runner` gets an **explicit** `elif selected.technique is Technique.COMPOSE_DRAFT: pipeline = DraftExpandPipeline(...)` branch **before** the `else → GapPipeline` (which refuses empty grounding — D must never fall into it).
- **Own generation (F7):** `DraftExpandStrategy.run` makes its **own** LLM `complete` call seeded by `context.seed_text` — it does NOT call the grounding-refusing `generate()`/`GapPipeline`. Prompt is **book-aware (C1)** — built from `context.profile` (voice/language/era), NOT a hardcoded 封神 string:
  - `add_only`: instruct (in `profile.language`) "this is the author's draft for «{name}»; KEEP every sentence verbatim; only ADD the missing dimensions ({missing}); match the book's voice ({profile.voice}); JSON only."
  - `rewrite`: "rewrite + voice-sync to {profile.voice}, PRESERVE the author's meaning; fill dimensions ({dims}); JSON only."
- **Synthetic authored provenance (F3):** the C11 `make_enriched_fact` chokepoint **requires non-empty `source_refs`** (`provenance.py:295-298`, "impossible to forget H0"). D has no corpus, so mint a synthetic ref `SourceRef(kind="author_draft", ref=sha256(draft_text)[:16])` + `extra_provenance={"seed":"author_draft","expand_mode":…}`. Add a small `make_enriched_fact` allowance for the `author_draft` source kind so the proposal is honestly tagged **author-seeded** (not corpus-grounded), satisfies H0 (origin=`enrichment`, conf<1.0, quarantined), and stays traceable. Pin with a test that an empty-corpus draft mints a fact with the authored ref and does NOT raise.
- Reuses `repair_generation` + C12 verify (profile-driven anachronism). **③ regurgitation guard is mechanically N/A for D** (F8): ③ detects copying the *provided source corpus*, and D has none — it does **not** mean D is immune to training-data leakage (③ never addressed that for any mode); the **④ promote-gate + human review is the backstop**. Skip ③ for `author_draft` provenance.
- **Forward-looking guard (review-impl 2026-06-04, mirrors C2 grounding review #2):** the synthetic `author_draft` source_ref is **P1-local / attribution-only** — a `compose_draft` proposal MUST NEVER be fed into the re-cook (P3) path, which resolves a license per grounding source via `UUID(corpus_id)` and would break on the non-UUID `author_draft` ref. D is P1 + has its own pipeline branch (§2.7), so this is a forward guard, not a live bug; pin with a comment in `make_enriched_fact`/the strategy.
- **`StrategyContext` extension** (`app/strategies/base.py`): `seed_text: str | None = None`, `expand_mode: str | None = None` (frozen, additive, ignored by other strategies — like `profile` was in C1).

### 2.6 Intent resolver (mode B) — `app/compose/intent.py`
- One LLM call (the gen `complete` seam): given `intent_text` + the book's entity list (names+kinds from `list_entities`) + the book's `profile` (so suggestions fit the worldview), return `{ target: {mode: existing|new, canonical_name, entity_kind}, dimensions: […], technique: retrieval|fabrication }`. Strict JSON, repaired like generation.
- Default technique = `fabrication` (canon-grounded invention) unless strong corpus grounding exists. ③ applies (the model may surface training-data text).

### 2.6.1 `POST /v1/lore-enrichment/compose/resolve-intent` (F5 — B is 2-step)
- **New endpoint** (synchronous, NOT a job): body `{ book_id, intent_text }` → calls §2.6 resolver → returns `{ target, dimensions, technique, rationale }`. **No job is created.**
- The FE shows the resolved target (existing/new + name + kind + dims + technique), lets the author **edit/confirm**, then submits a normal `POST /compose` with `input_source` effectively `existing|new` (the confirmed target). **Never silently enrich a mis-resolved target** (the original §6 risk — now enforced by the 2-endpoint split).

### 2.7 Worker + request shape
- `save_job_request` gains: `input_source`, `seed_text`, `expand_mode`, `context_corpus_ids` (audit). `redrive_one` threads `seed_text`/`expand_mode` into the `StrategyContext` (the only worker change; `entity_kind` + `profile` already flow — C1). 
- `build_live_runner`: register `DraftExpandStrategy` in the factory + the explicit `compose_draft` pipeline/cost branch (P1 → ungated, metered via the C1 `UsageMeter`).

### 2.8 DB + contract
- **Reuse** `enrichment_job` + `enrichment_job_request` (JSONB request — additive fields, no migration). Optional: `enrichment_job.source TEXT` (audit; additive `ADD COLUMN IF NOT EXISTS`).
- New `enrichment_upload` table (mode F): `upload_id, user_id, book_id, filename, mime, pages, extracted_text, ocr_used, license_asserted, status, created_at` (status for the F10 async-OCR poll).
- Contract: add `/compose`, `/compose/resolve-intent`, `/uploads` to [`openapi.yaml`](../../contracts/api/lore-enrichment/v1/openapi.yaml). Gateway needs no change (catch-all proxy).

## 3. Frontend design (`features/enrichment/`, React-MVC)
New **"Tạo / Compose"** panel inside `EnrichmentView` — a 5th secondary panel (no route/BookDetailPage change; the Profile/Settings tab from C3 is the 6th — both inside the same view).
- **`EnrichmentView.tsx`**: add `'compose'` to `EnrichmentPanel` + lead the strip; render `<ComposePanel/>` under the no-unmount idiom. Gaps' per-row *enrich →* can `setActivePanel('compose')` + prefill mode A.
- **components/compose/** (new): `ComposePanel` (shell: ① mode selector · ② mode form · ③ shared target+config · run) · `ModeSelector` (A/B/C/D/F + "E dropped" note) · `ComposeGapForm/IntentForm/ContextForm/DraftForm/FilesForm` · `ComposeTarget` (existing-entity picker | "+ new": name + **kind dropdown = character/location/item/faction/event/generic**) · `ComposeConfig` (technique + gen/embed model pickers (reuse `providerApi.listUserModels`) + cost-cap + top_k + ①②③④ safety strip + H0 chip) · `FileDropzone` (drag/drop, per-file extract+OCR status, license assert + responsibility checkbox).
- **B is 2-step in the UI:** `ComposeIntentForm` calls `resolveIntent()` → shows the resolved target (editable) → run submits the confirmed target.
- **hooks/**: `useCompose.ts` (`compose()` + `resolveIntent()` + `uploadFiles()` + invalidate jobs/proposals + toast, async 202 like auto-enrich).
- **api.ts/types.ts**: `compose`, `resolveIntent`, `uploadFiles`; `ComposeBody`, `ComposeTargetInput`, `ResolvedIntent`, `UploadResult`.
- **i18n**: a `compose` namespace across en/vi/ja/zh-TW (mode labels, form labels, OCR/extraction status, responsibility copy, safety strip) — UI copy mirrors the Vietnamese mockup. (Keep parity green — the i18n:check gate.)
- **Tests (vitest):** per form + ComposePanel (mode switch, target existing/new + kind, run body) + useCompose (compose/resolveIntent/upload/toasts/invalidate) + FileDropzone (extraction status, license-required-to-run) + the B resolve→confirm→run flow.

## 4. Copyright-safety (①②③④ per mode) — reuse, do not weaken
| Layer | A | B | C | D | F |
|---|---|---|---|---|---|
| ① license default-deny | corpus | n/a | assert (deny copyrighted) | own | **assert per file (deny copyrighted)** |
| ② abstract→facts | (recook) | optional | yes | no (their idea) | yes |
| ③ regurgitation guard | yes | yes | yes | **N/A (F8 — author's own draft)** | yes |
| ④ promote-gate + H0 | yes | yes | yes | yes | yes |

B/C/D/F are **user-driven** (the user performs the sourcing act + bears responsibility; platform = tool) — why they're defensible where dropped web-mode E is not. **Not legal advice — release needs IP counsel** (surface prominently for C/F).

## 5. Build slices (each = own VERIFY + POST-REVIEW + COMMIT)
| Slice | Scope | Acceptance |
|---|---|---|
| **0 — de-bias** | ✅ **DONE (C1+C2+C3 + followups, live-proven, pushed).** Book-aware prompts + multi-kind + grounding composer + profile authoring + extract-first + chapter-ground. | n/a — shipped |
| **1 — spine + D** | `POST /compose` skeleton (async) · target existing **AND new** (new = `mode:"new"` on the proposal; anchor minted at **promote** via the existing writeback resolve-or-create — no compose-time glossary write) · any kind + GENERIC · `DraftExpandStrategy`+`DraftExpandPipeline` (own gen, synthetic authored provenance, explicit branch) · `seed_text`/`expand_mode` · worker thread-through · FE "Tạo" panel + ComposePanel shell + ComposeDraftForm + ComposeTarget + ComposeConfig + useCompose · i18n · tests | live: draft → 202 → worker → quarantined proposal for an existing AND a **new** entity (location + generic); promoting the new one mints the glossary anchor (reject leaves glossary untouched); both expand_modes; book-aware voice; FE compose() wired |
| **2 — C paste-context** | compose `context` branch (handler embed seam + `ingest_corpus` + license default-deny) · ComposeContextForm | live: pasted text → corpus → recook/retrieval proposal grounded on it; copyrighted assertion refused |
| **3 — F attach-files** | `POST /uploads` (multipart, async/poll) + `app/files/extract.py` (pdf/docx/epub/txt/md) + **OCR (Tesseract chi_sim/chi_tra in service+worker images)** + MinIO + `enrichment_upload` · FileDropzone · freshness-guard covers new image deps | live: upload .pdf+.docx+scanned-pdf → extract(+OCR) → ingest → proposal |
| **4 — B intent** | `app/compose/intent.py` resolver + `POST /compose/resolve-intent` + compose `intent` branch · ComposeIntentForm (resolve→confirm→run) | live: intent → resolved target+dims (existing + new) shown for confirm → fabrication proposal on the confirmed target |

## 6. Risks / deferrals
- **OCR infra (slice 3):** Tesseract + CJK packs in BOTH the lore-enrichment service + worker images (sizeable). `build-stack.sh` freshness guard (LE-061 family) must cover the new deps. `/uploads` async/poll for large scans (F10).
- **D tier (F11):** P1 by PO decision; flip to P2 if QC later wants the eval gate (factory enforces).
- **C12 on GENERIC (`description`) dim:** operates on text → safe; pin a test (was the original §2.1 risk; lower now — C1's multi-kind verify already runs non-location dims).
- **New-entity H0 (F1):** creation is **deferred to promote** (§2.2) — nothing enters glossary at compose/enrich time, so a rejected `mode="new"` proposal leaves glossary untouched. Confirm in BUILD that promoting a new target mints exactly one anchor (resolve-or-create idempotent) + the quarantined supplement.
- **Intent resolver accuracy (B):** mitigated by the 2-step resolve→confirm (F5) — never silently run a mis-resolved target.
- **③ for D is N/A (F8):** documented in §4 — skip the regurgitation guard for `author_draft` provenance.
- **F9 (cosmetic) retired:** no `Dimension.DESCRIPTION` enum conflation — we use C1's GENERIC kind.
- **Entity-kind:** all C1 kinds + GENERIC are in scope now (no longer "location+freeform only").

## 7. Test plan
- **BE pytest:** `/compose` per source (gap/context/draft/intent/files) — 202 + request shape + correct branch (ingest called for C/F, `seed_text` persisted for D, resolver NOT called inline for B); `/compose/resolve-intent` (returns target, no job) + JSON-repair; `/uploads` extraction (+OCR mock) + size/page/format rejects + async status; **new-entity create** (extract-entities seam, H0-safe); GENERIC dimension model; copyrighted-license refusal; worker re-drive of a `compose_draft` (synthetic authored provenance, no-raise) + a `context` job; ③ skipped for `author_draft`.
- **FE vitest:** per §3 (forms, ComposePanel, useCompose, FileDropzone, B resolve→confirm→run) — assert on i18n KEYS (house convention); keep i18n parity green.
- **Live-smoke (cross-service):** the 4 slice acceptance rows, through the gateway, against the rebuilt stack (provider-registry freshness pre-flight; LM-Studio same-owner models; note the eviction risk). Browser e2e can extend the C3 `enrichment-profile.spec.ts` harness (LE-068 pattern).

## 8. Effort (rough)
Slice 1 (L) — plumbing + D + new-entity + any-kind + the FE composer shell · Slice 2 (S-M, reuses C2 ingest) · Slice 3 (M-L, OCR/extraction/MinIO) · Slice 4 (M, resolver + resolve-intent). Total ~XL, multi-session. **Slice 0 is already done**, so the critical de-bias risk is retired before the first Compose line.
