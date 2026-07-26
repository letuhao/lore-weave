# Plan — Multilingual KG: milestone sequencing

**Date:** 2026-06-23
**Status:** PLAN (ready for milestone-by-milestone BUILD)
**Spec:** [`docs/specs/2026-06-23-kg-multilingual.md`](../specs/2026-06-23-kg-multilingual.md)
**Branch:** `feat/kg-multilingual`
**Effort size:** **XL** (12+ changes across 5 services + a new cross-service event) → run as ONE coherent
effort, multiple milestones, checkpoint at risk boundaries (per CLAUDE.md budget-driven cadence).

---

## 0. Orientation

The spec is gate-validated: **V1 PASS** (bge-m3 is genuinely multilingual → single-vector-space premise
holds), **V7 PASS-with-caveat** (reranker optional → D5 must work without it), **V6 FAIL** (lexical leg
not CJK-tokenized → D12 is real). The load-bearing risk is cleared, so this is now an *implementation
sequencing* problem, not a research one.

**Design recap (what we're building):** canonical Layer-1 graph stays source-language and is NEVER
re-extracted from translations; we *derive* a localization layer (Layer 2) + a language-aware retrieval
layer (Layer 3) on top. Vi content is **index-only + label-only**.

---

## 1. Dependency DAG (why this order)

```
M0 V1/V7 live probe (confidence; non-blocking)
        │
M1 FOUNDATION: source_lang tag + BookClient lang forward + cost metering   ← enables everything
        │
        ├────────────────────────────┬───────────────────────────┐
        ▼                             ▼                           ▼
M2 EVENT + DUAL-INDEX        M3 READER-LANG STORAGE        M6 LEXICAL per-language
 (translation.published       (D10 owner decision +         (D12; depends only on M1;
  → vi passages)               server-side pref)             can run anytime after M1)
        │                             │
        └──────────────┬──────────────┘
                       ▼
        M4 RETRIEVAL D5 (soft-weighting + coverage + eval harness)   ← the core user win
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
M5 LABELS (Layer 0→2)         M7 CONSUMERS (compose/chat/timeline wiring
 (kind/predicate/entity-name)   + end-to-end live-smoke)
```

**Critical path:** M1 → M2 → M4 → M7. **M3** must land before M4 (D5 ranks by reader pref). **M5** and
**M6** are parallelizable off M1 and only need to rejoin at M7. **M0** is a confidence probe, not a blocker.

---

## 2. Milestones

### M0 — V1/V7 live probe (confidence) · size S · OPTIONAL-but-recommended
- **Goal:** get real recall@k / nDCG numbers for bge-m3 (embed) + bge-reranker-v2-m3 (rerank) on a
  small zh/vi/en parallel set, to confirm the gate's documentary PASS with measured evidence.
- **Deliverable:** a throwaway probe script + a numbers table appended to spec §11. No production code.
- **Exit:** same-language recall@5 ≳ 0.85 for zh and vi; if it fails, escalate (re-open §8 per-language
  fallback) BEFORE M2. If infra not bootable: record `live infra unavailable` and proceed (V1 already
  PASS on documentation + golden-set).
- **Checkpoint:** none (no shipped code).

### M1 — Foundation: `source_lang` + lang forwarding + cost metering · size M · **risk boundary (migration)**
- **Covers:** C1 (`source_lang` on Passage/Entity + backfill), C2 (BookClient forwards
  `chapters.original_language` → ingester), C10 (record `embed_result.prompt_tokens` to usage-billing
  at the ingest chokepoint + skip-gate on unchanged republish — fixes the pre-existing leak V3 found).
- **Key rules:** backfill `source_lang` **per-chapter** (not book-level default — V2); handle
  `detect_primary_language()=="mixed"` = store dominant + `mixed=true`. Persist the detected lang that
  is currently computed-then-discarded.
- **Deliverable:** schema migration (Neo4j prop + Postgres mirror), BookClient change, ingester change,
  metering at chokepoint, backfill one-shot for existing zh nodes.
- **Exit / AC:** existing graph carries `source_lang`; new ingests tagged; **AC7** (cost recorded;
  unchanged republish bills zero); no behavior regression (existing retrieval unchanged — `source_lang`
  is dormant until M4 reads it).
- **Live-smoke:** ingest a chapter on a real stack → confirm `source_lang` set + usage-billing row.
- **Checkpoint:** POST-REVIEW (schema migration is a risk boundary).

### M2 — Event + dual-index · size M · **risk boundary (new cross-service contract)**
- **Covers:** C3a (translation-service: emit transactional-outbox `translation.published` —
  `book_id, chapter_id, target_language, revision_id, owner_user_id` — at version-activate chokepoint),
  C3b (knowledge-service: consume → dual-index vi passages, `source_lang='vi'`, eager re-embed per
  chapter on republish per R7).
- **Hard constraints:** vi path is **index-only, NEVER re-extraction** (R1); vi passages carry the
  SAME `project_id` so `purge_project` cascades (AC8); idempotent delete-then-reingest scoped to
  `(chapter_id, source_lang=vi)` so zh is never touched.
- **Deliverable:** producer + outbox wiring; consumer handler; purge coverage test.
- **Exit / AC:** **AC5** (Layer-1 byte-identical before/after dual-index); **AC8** (book/project delete
  removes vi passages, zero orphans); re-publish re-embeds only the edited chapter.
- **Live-smoke (≥2 services, MANDATORY):** translation-service emits → knowledge-service dual-indexes →
  a vi passage is queryable. Per `new-cross-service-contract-needs-consumer-live-smoke`.
- **Checkpoint:** POST-REVIEW.

### M3 — Reader-language preference storage · size S · **decision-gated**
- **Covers:** C11 / D10. **Open decision to resolve at this milestone's CLARIFY:** owner =
  book-service reading-state vs auth-service preferences. Recommendation: **book-service reading-state**
  (it is per-(user,book), already cross-device-synced, and co-located with reading position).
- **Rules:** server-side SSOT, cross-device (NOT localStorage — CLAUDE.md); per-(user,book).
- **Deliverable:** schema + read/write endpoint + (thin) preference resolution helper exposed to
  retrieval and consumers.
- **Exit / AC:** **AC3** (set on device A, observed on device B).
- **Live-smoke:** set pref via API, read from a second session.
- **Checkpoint:** POST-REVIEW (decision sign-off + tenancy: pref is per-user, grant-gated).

### M4 — Language-aware retrieval (D5) + eval · size L · **core user-facing win**
- **Covers:** C8 (`language` param on search endpoints + retriever), D5 soft-weighting ranking,
  C12 (coverage signalling), C13 (eval harness + multilingual eval set).
- **Rules:** **soft weighting, NOT hard filter** (over-fetch → boost same-reader-lang → optional rerank);
  must produce acceptable ranking with **rerank disabled** (V7 caveat); reader pref from M3, fallback
  detected query lang, fallback source.
- **Deliverable:** retriever ranking change; endpoint param; per-hit `lang` + response `coverage`;
  eval harness wired into the existing KG-benchmark gate with a committed zh/vi/cross eval set.
- **Exit / AC:** **AC2** (vi query ranks vi above cross-lingual source; each hit carries `lang`);
  **AC4** (untranslated-chapter query returns source + coverage note, never silent); **eval gate:** no
  same-language recall regression + measurable improvement on vi-reader-on-zh-source vs baseline.
- **Live-smoke:** real vi query on a dual-indexed book returns vi-first results with coverage note.
- **Checkpoint:** POST-REVIEW (this is the shippable milestone — the scenario starts working here).

### M5 — Labels (Layer 0→2) · size M · **tenancy-sensitive**
- **Covers:** C4 (`kind_labels` table + tenancy tiers), C5 (predicate i18n **backend-served**, not
  frontend-only — R5), C7 (timeline/graph-view label resolution), C9 (entity-name vi population,
  glossary-locked).
- **Rules (LOCKED tenancy):** `kind_labels` with full scope key
  `UNIQUE(scope, COALESCE(owner_user_id), COALESCE(book_id), kind_code, language_code)`; System rows
  admin-seeded via `system_admin_handler` RS256 path, read-only to users; resolution merges
  System→Per-user→Per-book. **No user write to a System row** (the `entity_kinds` bug). Per-user label
  tier **deferred** (D-KG-ML-PERUSER-LABELS) — System+Book covers the scenario. C9 needs an idempotency
  gate keyed `(glossary_entity_id, language)` to avoid double-spend (Q3).
- **Deliverable:** label table + admin seed of the 12 System kinds in vi; backend label endpoint;
  glossary entity-name vi population (one-time per entity, glossary-locked); timeline/graph-view join.
- **Exit / AC:** **AC1** (timeline shows vi labels or explicit source-fallback marker); **AC6**
  (user B cannot read/mutate user A's labels/translations without an E0 grant).
- **Live-smoke:** read timeline as a vi reader → labels in vi; attempt cross-tenant read → denied.
- **Checkpoint:** POST-REVIEW + **suggest `/review-impl`** (tenancy boundary = load-bearing).

### M6 — Lexical leg per-language (D12) · size M · parallelizable off M1
- **Covers:** D12 / V6 remediation. `source_lang` selects the lexical path: zh → CJK tokenizer
  (`pg_jieba`/`zhparser` tsvector in book-service, or a Neo4j full-text index with a `cjk` analyzer);
  vi → appropriate config; trigram kept as script-agnostic fallback.
- **Pre-step (V6 live probe):** `db.index.fulltext.listAvailableAnalyzers()` on the running Neo4j;
  test whether the Postgres image can load `pg_jieba`/`zhparser` (may need a custom image — infra change).
- **Deliverable:** per-language lexical index/config; book-service lexical-search `language` param;
  BookClient forwards it.
- **Exit / AC:** Chinese 2–3-char term keyword recall materially improved vs trigram-only baseline
  (measure in the M4 eval harness, lexical subset).
- **Live-smoke:** zh exact proper-noun keyword search returns the right block.
- **Checkpoint:** POST-REVIEW (infra change if a custom Postgres image is needed = risk boundary).

### M7 — Consumers wiring + end-to-end · size M · integration close-out
- **Covers:** C6 (composition passes `language` to `select_for_context`), chat-service forwards
  reader-language to knowledge context build, reader/cowrite surfaces the coverage note + `lang`.
- **Deliverable:** the missing caller wiring across composition + chat; UI surfacing of coverage.
- **Exit / AC:** the full driving scenario works — write a vi spin-off, query the original timeline,
  get readable vi results with honest coverage. Re-confirm **AC1–AC8** end-to-end.
- **Live-smoke (the spec's headline E2E):** translation.published → dual-index → cowrite retrieves a
  vi passage in context, with vi labels and coverage signalling. One real run across ≥3 services.
- **Checkpoint:** POST-REVIEW (final scenario sign-off).

---

## 3. Milestone summary

| M | Title | Size | Covers | Depends on | Risk boundary | Key AC |
|---|---|---|---|---|---|---|
| M0 | V1/V7 probe | S | — | — | no | (confidence) |
| M1 | Foundation source_lang | M | C1,C2,C10 | M0* | migration | AC7 |
| M2 | Event + dual-index | M | C3a,C3b | M1 | new contract | AC5,AC8 |
| M3 | Reader-lang storage | S | C11 | M1 | decision | AC3 |
| M4 | Retrieval D5 + eval | L | C8,C12,C13 | M1,M2,M3 | core win | AC2,AC4 |
| M5 | Labels | M | C4,C5,C7,C9 | M1 | tenancy | AC1,AC6 |
| M6 | Lexical per-language | M | D12 | M1 | infra (maybe) | (lexical recall) |
| M7 | Consumers + E2E | M | C6,+wiring | M2,M4,M5 | scenario close | AC1–AC8 |

\* M0 is recommended, not blocking.

---

## 4. Deferrals carried (from spec §9.4)

| ID | Item | Trigger to revisit |
|---|---|---|
| D-KG-ML-WIKI | Per-language wiki article bodies | when a per-language wiki surface is actually needed |
| D-KG-ML-PERUSER-LABELS | Per-user kind-label tier | when a concrete per-user-label need appears |
| D-KG-ML-PERLANG-EMBED | Per-language embedding model/space | only if a future V1 probe shows a weak target lang |

---

## 5. Open decisions to resolve at milestone entry

- **M3:** reader-language storage owner (rec: book-service reading-state). Resolve at M3 CLARIFY.
- **M6:** Neo4j full-text+cjk vs Postgres `pg_jieba`/`zhparser` for the zh lexical path (infra impact).
  Resolve after the V6 live probe at M6 entry.
- **M4:** soft-weighting `w_lang` default + over-fetch multiplier — tune against the eval set, not guessed.

---

## 6. Build discipline (per CLAUDE.md)

- Each milestone: classify size → BUILD (TDD) → VERIFY (real output) → 2-stage REVIEW → QC →
  POST-REVIEW (batched per-milestone) → SESSION update → COMMIT.
- Cross-service milestones (M1, M2, M6, M7) **require** the live-smoke token in VERIFY evidence.
- Run continuously while context budget is ample; checkpoint/commit + `/compact` at each risk boundary.
- M5 and M7 (tenancy + new boundaries): proactively offer `/review-impl`.
