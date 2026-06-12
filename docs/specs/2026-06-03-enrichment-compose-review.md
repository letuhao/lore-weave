# Benchmark / design review — Enrichment Compose spec · 2026-06-03

> Adversarial review of [`2026-06-03-enrichment-compose.md`](2026-06-03-enrichment-compose.md)
> **against the actual code**, before building. Verdict: **REVISE before build** — the async spine
> + the FE approach are sound, but 3 load-bearing claims are wrong/under-specified and one
> pre-existing constraint (封神-hardcoded prompts) undercuts the "free-form / any subject" premise.
> Severity: BLOCK (must fix) · HIGH · MED · LOW.

## ✅ Confirmed SOUND (the reuse story mostly holds)
- **Async spine** — `create_job` + `save_job_request` + enqueue → the request-driven worker
  (`resume_consumer.redrive_one`) rebuilds gaps from `targets` + `build_live_runner(technique)` +
  `run_job`. C/F/B add no worker change; D needs only `seed_text`/`expand_mode` on the context. ✓
- **C/F ingest** — `SourceCorpusStore.ingest_corpus(text, license, embed_fn, model_ref)` exists and
  is the right reuse point (but see F6 — it needs an embed seam in the handler). ✓
- **Existing-target dims + B's entity list** — `GlossaryClient.list_entities` + `list_enrichment_coverage` exist. ✓
- **FE** — `EnrichmentPanel` is an open union; adding a `compose` panel inside `EnrichmentView`
  needs no route/BookDetailPage change; `providerApi.listUserModels` reuse is real. ✓
- **StrategyContext** is `frozen` but adding optional `seed_text`/`expand_mode` fields is fine. ✓

## 🟥 HIGH / BLOCK

### F1 (HIGH) — `target.mode = "new"` has NO client seam (spec §2.2 is false)
Spec §2.2 says Compose creates a new entity via "`GlossaryClient.bulkExtractEntities`". **That method
does not exist** on the lore-enrichment `GlossaryClient` — it only has `list_entities`,
`list_enrichment_coverage`, `list_wiki`, `_get` (`app/clients/glossary.py:82-159`). The writeback
(promote) path *resolves an existing* entity; nothing here *creates* one.
- **Impact:** "create a new entity from the input" doesn't work as specced.
- **Fix:** (a) add a `GlossaryClient.create_entity` (or `bulk_extract`) wrapper calling glossary's
  `/internal/books/{id}/extract-entities` bulk endpoint (it exists on glossary-service per CLAUDE.md)
  with the internal token — verify the endpoint contract + that a brand-new entity is H0-safe; OR
  (b) **scope v1 to `target.mode = "existing"` only** and defer new-entity creation. Recommend (b)
  for slice 1, (a) as a follow-up.

### F2 (HIGH — BLOCK beyond the Fengshen demo) — generation prompts HARDCODE the 封神演义 worldview
Every generator prompt is pinned to 封神/商周:
- `app/generation/generate.py:85` — `"你是一位忠于《封神演义》原著的世界观补全助手"`
- `app/strategies/fabrication.py:202,210` — `"深谙《封神演义》世界观…须符合商周·封神纪元的时代背景"`
- `app/strategies/recook.py` — `"商周·封神演义"` re-contextualisation, anachronism = anything post-商周.
- **Impact:** Compose's `freeform` kind + "any subject" premise is undercut — using it on a
  **non-Fengshen book** (the platform is multi-book) forces the user's content into the Shang-Zhou /
  Fengshen frame → **wrong output**. Most acute for **mode D** (expanding the *author's own* draft
  for some other book in 封神 voice is clearly wrong).
- **Fix:** prompts must be **book-aware** — derive the worldview/era/voice from the book, not a
  hardcoded constant. **CONFIRMED A BUG by the PO (2026-06-03)** — not a Compose-only limitation:
  it's broader (4 axes hardcoded: worldview 封神演义 · era policy 商周/no-modern · language 中文 ·
  entity-kind 地点) and already produces wrong output for **every non-Fengshen book**. Full fix
  design → [`2026-06-03-enrichment-debias-book-profile.md`](2026-06-03-enrichment-debias-book-profile.md)
  (per-book `enrichment_book_profile` + parameterized prompts + profile-driven anachronism +
  Fengshen-default = no regression). **This is the foundational fix — Slice 0a/0b, do it before the
  Compose build.**

### F3 (HIGH / BLOCK for mode D) — the H0 chokepoint REQUIRES non-empty `source_refs`; D has none
`make_enriched_fact` raises on `empty provenance/source_refs` ("impossible to forget H0",
`app/generation/provenance.py:295-298`). Mode D (compose_draft) generates from the **author's draft**,
**not a corpus** → no `source_refs` → minting a fact would **raise**. The spec's "D reuses the C11
`make_enriched_fact` chokepoint" therefore breaks.
- **Fix:** define a **synthetic provenance for authored content** — e.g., a `SourceRef` like
  `{kind:"author_draft", hash:<sha256(draft)>}` (and/or an `extra_provenance={"seed":"author_draft"}`)
  so the chokepoint is satisfied and the proposal is honestly tagged as author-seeded (not
  corpus-grounded). Requires a small `make_enriched_fact` allowance for an "authored" source kind.

### F7 (MED→HIGH, couples to F3) — D cannot reuse `SchemaGovernedGenerator`
`GapPipeline`/`generate()` **refuse empty grounding** (`stages.py:136-143`, "unprovenanced content is
refused"). D has no grounding, so it **cannot** use the existing generator. The spec implies reuse;
in fact `DraftExpandStrategy` needs its **own** LLM-generation call (seeded by the draft) that mints
facts via the (F3-extended) chokepoint, then runs C12 verify. Doable, but it's *new* generation code,
not reuse — adjust the effort + §2.5.

## 🟧 MED

### F4 — `compose_draft` MUST get its own assembly pipeline branch (else-fallthrough is wrong)
`build_live_runner` branches `FABRICATION → FabricationPipeline`, `RECOOK → ReCookPipeline`, **else →
`GapPipeline` (retrieval)** (`assembly.py:228-250`). A new `compose_draft` would fall into the `else`
→ the retrieval pipeline → which **requires grounding** → refuses D. So D needs an **explicit**
`DraftExpandPipeline` branch (the spec says "mirror fabrication" — make it a hard requirement, not
optional, and never let it hit the retrieval else).

### F5 — mode B is inherently TWO steps; the single async `/compose` can't confirm the target
Spec §6 risk says "the user reviews the resolved target before running", but §2.3 models B as one
`/compose` call with `intent_text` → resolve → enqueue (no confirmation). An LLM resolver that
mis-maps would silently enrich the wrong entity.
- **Fix:** split B into **`POST /compose/resolve-intent`** (returns the proposed `target` + dims +
  technique; no job) → FE shows it, user edits/confirms → then a normal `POST /compose` with the
  confirmed `target` (input_source becomes effectively `existing|new`). Two endpoints, explicit gate.

### F6 — C/F ingest needs an embed seam in the request path (under-specified)
`ingest_corpus` needs `embed_fn` + `model_ref`; the embed is a provider-registry network call. The
spec says "ingest → then a job" but doesn't say **where** the embed happens. If the handler ingests
synchronously it makes a (bounded) embedding call in the request path; if deferred to the worker it's
more plumbing.
- **Fix:** decide + specify. Recommend: handler builds the embed seam (`make_embed_query_fn`, as
  `assembly` does) and ingests synchronously (corpus chunks only — bounded), then enqueues the job.
  Note the added handler dependency (KnowledgeClient) + latency.

## 🟨 LOW
- **F8** — ③ regurgitation guard is effectively **N/A for D**: there is no external source to compare
  against, and reproducing the author's *own* draft is desired. Spec's "③ applies" is misleading for
  D — clarify (③ is for C/F/B where external/training text is involved).
- **F9** — adding `Dimension.DESCRIPTION` to the LOCATION-specific `Dimension` enum (`gaps/model.py`)
  conflates kinds. Works (it's a string enum + per-kind tables), but cleaner to namespace freeform's
  dimension separately. Cosmetic.
- **F10** — `/uploads` OCR is slow; a 300-page scanned PDF can time out a sync request. Make `/uploads`
  job-like (return an upload_id immediately, extract+OCR async, poll status) for large scans. (Spec
  flagged it; promote to a build note.)
- **F11** — `compose_draft` tier = P1 (ungated) bypasses the eval gate. Author-seeded content is
  low-risk, but it IS LLM-generated — confirm with QC whether D should be gated (the factory already
  enforces if you set tier P2).

## Recommended spec revisions (before build)
1. **Slice 0 (NEW, prerequisite):** de-hardcode the generation prompts → book-aware worldview/voice
   (F2). Without it, Compose only works on the Fengshen demo book.
2. Scope **slice 1 to `target.mode=existing`** (defer F1 new-entity creation) unless the create
   wrapper is added.
3. Rewrite **§2.5** for D: own generation path (F7) + synthetic authored provenance (F3) + its own
   assembly/pipeline branch (F4).
4. Add **`/compose/resolve-intent`** for B (F5); specify the **handler embed seam** for C/F (F6).
5. Fold F8–F11 into Risks.
