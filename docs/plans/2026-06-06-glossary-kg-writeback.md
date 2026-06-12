# PLAN — Glossary KG→Writeback Loop (mui #1)

- **Date:** 2026-06-06
- **Branch:** `glossary/ai-pipeline-v2`
- **Spec:** `docs/specs/2026-06-06-glossary-kg-writeback.md` (CLARIFY locked)
- **Architecture:** `docs/03_planning/GLOSSARY_AI_PIPELINE_V2_ARCHITECTURE.md`
- **Size:** L (knowledge Py + glossary Go + frontend; cross-service ⇒ live-smoke at VERIFY)

---

## 0. Ground-truth confirmed during PLAN (reads, not summaries)

| Fact | Location | Impact |
|---|---|---|
| Best-effort hook point (P3 summary-enqueue pattern) | `knowledge .../internal_extraction.py:517-548` (insert after line 555) | Writeback block goes here, guarded by config, non-fatal. |
| `find_gap_candidates` is **project-wide**, `min_mentions` default **50**, **no confidence floor** in cypher | `knowledge .../db/neo4j_repos/entities.py:1303-1354` | See **ADJ-1**. Returns `Entity` objects (name, canonical_name, kind, aliases, confidence, mention_count, glossary_entity_id…). |
| `propose_entities(book_id, *, entities, source_language, attribute_actions)` — body has **no** `park_unknown_kinds`, **no** tags | `knowledge .../clients/glossary_client.py:403-435` | See **ADJ-2**. |
| Kind map + normalizer | `knowledge .../extraction/entity_resolver.py:69-84` | Reuse `_EXTRACTOR_TO_GLOSSARY_KIND` / `normalize_kind_for_anchor_lookup`. |
| glossary `extractedEntity` = `{kind_code, name, attributes, evidence, chapter_links}` — **no tags field**; `park_unknown_kinds` exists at request level | `glossary .../extraction_handler.go:339-366` | Add request-level `default_tags`. |
| Draft create path: `INSERT ... (book_id, kind_id, status) VALUES (...,'draft')` — sets no tags | `glossary .../extraction_handler.go:753-756` | Apply `default_tags` here. |
| glossary `GET /entities` **already** filters `status` + `tags` (`e.tags @> $n`) | `glossary .../entity_handler.go:493-541` | ✅ **Inbox list needs ZERO BE change.** |

### Design adjustments (surface to PO before BUILD)
- **ADJ-1 (threshold reconciliation).** Spec locked `conf≥0.7 & mention≥3`. But `find_gap_candidates` counts **project-wide cumulative** mentions and the codebase's own KSA §3.4.E recommends **50**. `mention≥3` will flood the inbox with extraction noise. **Proposed:** keep config-driven (SP1); start at **`min_mentions=10` + `confidence≥0.7`** (confidence filtered in Python post-fetch, since the cypher lacks it), tune down later if recall too low. *Needs PO nod — this changes the locked value.*
- **ADJ-2 (tag/flag plumbing).** To land entities as reviewable AI suggestions, the writeback must (a) tag them `ai-suggested`, (b) send `park_unknown_kinds=false`. Both require tiny extensions: `propose_entities` body + glossary `bulkUpsertRequest`.

---

## 1. Phases & order

```
BE-1 (knowledge: wire propose) ──┐
BE-2 (glossary: tags + tombstone)─┴─► FE-1 (inbox) ──► VERIFY (unit + live-smoke)
```
BE-1 and BE-2 are co-dependent on the payload contract (default_tags) — land the contract first (BE-2 schema), then BE-1 caller, so a live entity write is testable end-to-end.

---

## 2. BE-2 (glossary-service) — receiving contract + tombstone  [TDD]

**File:** `services/glossary-service/internal/api/extraction_handler.go` (+ migrate if needed)

1. **`default_tags []string` on `bulkUpsertRequest`** (line 339 struct). Optional; nil = no tags (backward-compatible).
2. **Apply tags on create** (line 753-756): `INSERT ... (book_id, kind_id, status, tags) VALUES (...,'draft',$tags)`. On *merge* of an existing entity, union tags (don't clobber user tags).
3. **Tombstone skip (P5).** Before create/merge in `bulkExtractEntities`, when a proposed name resolves (via `findEntityByNameOrAlias`, read 673-741 at BUILD) to an entity carrying tag `ai-rejected`, **skip** it → report as `skipped` (reason `tombstoned`). Do NOT re-create, re-activate, or update. (Re-proposal of a user-rejected name is suppressed until the user un-rejects.)
4. Keep existing outbox emit (579-595) — drafts still emit `glossary.entity_updated` (harmless; KG MERGE idempotent; draft not in active-canon query).

**Tests (Go):**
- create with `default_tags=['ai-suggested']` → entity row has tag, status=draft.
- merge existing user entity with default_tags → tags unioned, user tags preserved.
- propose a name tagged `ai-rejected` → response `skipped` (tombstoned), no row mutation.
- omit default_tags → behaviour unchanged (regression guard).

## 3. BE-1 (knowledge-service) — wire propose at job completion  [TDD]

**Files:** `services/knowledge-service/app/routers/internal_extraction.py` (hook), `app/clients/glossary_client.py` (extend), `app/config` or `knowledge_projects` (flags).

1. **Extend `propose_entities`** to pass `park_unknown_kinds: false` and accept `default_tags: list[str]` → include both in the POST body.
2. **Config flags** (env default + per-project override, mirror `_WRITER_AUTOCREATE_CONFIG`): `writeback_enabled` (default **off**), `writeback_min_mentions` (default 10 per ADJ-1), `writeback_confidence_floor` (0.7), `writeback_limit` (100).
3. **Hook** (after line 555, new best-effort block, only when `writeback_enabled` and `body.project_id`):
   - resolve `book_id` from `project_id` (knowledge_projects lookup — reuse existing helper).
   - `candidates = await find_gap_candidates(session, user_id, project_id, min_mentions=cfg.min_mentions, limit=cfg.limit)`.
   - filter `c.confidence >= cfg.confidence_floor` (Python; cypher has no confidence floor).
   - map each: `kind_code = normalize_kind_for_anchor_lookup(c.kind)`; payload `{kind_code, name: c.canonical_name, attributes: {aliases: c.aliases}, evidence: <top snippet or "">}`.
   - `await glossary_client.propose_entities(book_id, entities=payload, default_tags=['ai-suggested'], park_unknown_kinds=False)`.
   - wrap in try/except → on failure `logger.warning(... non-fatal)` and (stretch) enqueue retry marker; never 500.
4. **Idempotency note:** `find_gap_candidates` returns only `glossary_entity_id IS NULL` entities, and glossary dedups by name + the `ai-rejected` tombstone — re-running a job won't multiply drafts.

**Tests (pytest):**
- payload build: kind mapped, aliases carried, canonical_name used as name.
- threshold filter: entity below confidence floor / below min_mentions excluded.
- best-effort: `propose_entities` raises → hook logs, persist-pass2 still returns 200.
- `writeback_enabled=false` → propose never called.
- park_unknown_kinds=false + default_tags present in the outgoing body.

## 4. FE-1 (frontend) — "AI Suggestions" inbox  [TDD]

**Files:** `frontend/src/features/glossary/` — new `hooks/useAiSuggestions.ts`, `components/AiSuggestionsPanel.tsx` (mirror `useUnknownReview.ts` / `UnknownEntitiesPanel.tsx`).

1. **List:** `glossaryApi.listEntities(bookId, { status: 'draft', tags: 'ai-suggested' })` — **no new endpoint** (filter exists). Add the typed param to `api.ts` if not present.
2. **Actions per item:**
   - **Promote** → PATCH entity `status: 'active'` (existing endpoint). On success, invalidate `['glossary-entities']` + `['glossary-ai-suggestions']`.
   - **Edit-then-promote** → reuse entity edit form, then promote.
   - **Reject** → PATCH `status: 'inactive'` + add tag `ai-rejected` (verify entity PATCH supports tags at BUILD; else add a tag-mutation path). Keeps `ai-suggested` for audit.
   - **Un-reject** (toggle) → remove `ai-rejected`, restore `draft`.
3. **Surface:** a badge/count near the glossary view ("N AI suggestions"). Reuse the review modal pattern from the unknown-kind epic.

**Tests (vitest):**
- list renders only draft+ai-suggested.
- promote calls PATCH status=active + invalidates.
- reject sets inactive + ai-rejected tag.
- empty state renders, no crash.

## 5. VERIFY (evidence gate)

- **Unit:** Go (glossary) + pytest (knowledge) + vitest (FE) all green — paste counts.
- **Cross-service live-smoke (MANDATORY, ≥2 services):** docker stack up → enable writeback for a project → publish/extract a chapter with a repeated entity → assert a `draft` + `ai-suggested` entity appears via `GET /entities?status=draft&tags=ai-suggested` → promote → assert `status=active` and (knowledge) `:Entity.glossary_entity_id` now set (loop closed).
  - Evidence token: `live smoke: chapter extraction → ai-suggested draft visible + promote→active→KG anchor`.
  - If full stack not bootable: `live infra unavailable: <reason>` + defer row.

## 6. Risk register (from architecture eval, scoped to mui #1)

- **R1/SP1** — quality rests on threshold (no K18 validator). → config + start conservative (ADJ-1).
- **R2/R6** — tombstone dedup correctness. → covered by BE-2 test #3; read `findEntityByNameOrAlias` at BUILD before editing.
- **R-loop (NR1)** — re-sync loop. → non-risk (draft-bounded + idempotent), no action.
- Out of scope: merge (#1c), semantic retrieval (#4), grounding port (#3).

## 7. Definition of Done

- [ ] ADJ-1 + ADJ-2 acknowledged by PO.
- [ ] BE-2, BE-1, FE-1 implemented with tests green.
- [ ] Writeback default **off**; enabling is per-project config.
- [ ] Live cross-service smoke passed (or explicit deferral row).
- [ ] SESSION_HANDOFF + DEFERRED updated; committed in one commit per phase boundary.
