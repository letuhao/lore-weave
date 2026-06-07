# M6b — full-propagate (targeted glossary-staleness) — design + plan

**Date:** 2026-06-08 · **Branch:** `feat/translation-pipeline-v3` · **Size:** XL · **Mode:** v2.2 + `/review-impl` (no AMAW, PO 2026-06-08)
**Spec anchor:** [`2026-06-06-translation-pipeline-v3-multi-agent.md`](../specs/2026-06-06-translation-pipeline-v3-multi-agent.md) §12.4 M6 ("user correction → glossary confirm → targeted re-translate + **propagate**").
**Clears:** D-TRANSL-M6A-NOTES(c) (coarse propagate) · D-TRANSL-M5C-COARSE-LANG (all-language flag) · D-TRANSL-M6A-LIVE-SMOKE core concern (translation PATCH did not emit).

## Problem

M5c-1 staleness is **coarse**: any `glossary.entity_updated` for book X →
`UPDATE chapter_translations SET is_glossary_stale=true WHERE book_id=X` — every
chapter, every target language. Two losses:

1. **No term→chapter precision** — a one-name fix flags the whole book.
2. **No language axis** — a fix to the *vi* rendering flags *en* translations too.

And a latent bug behind the flywheel: the interactive translation endpoints
(`createTranslation`/`updateTranslation`/`deleteTranslation`,
[attribute_handler.go:241+](../../services/glossary-service/internal/api/attribute_handler.go))
**emit no `entity_updated` at all** → the M6a "confirm a name" action never fires
the staleness trigger. The flywheel's first link is broken.

## PO decisions (CLARIFY 2026-06-08)

1. **Path A — entity-id usage index** (precise, consistent with the platform's `glossary_entity_id` anchor). Not source-text name-matching.
2. **Precise flag only (this slice = M6b-1)**; user-triggered re-translate is a later FE slice (M6b-2). No auto-enqueue (BYOK cost/consent).
3. **Per-language now** — clears D-TRANSL-M5C-COARSE-LANG.
4. **No AMAW** — v2.2 + `/review-impl`.

## Design

### Cross-service contract

The `glossary.entity_updated` payload gains **one optional field**:

```go
TargetLanguage string `json:"target_language,omitempty"`
```

- **Set** by the interactive translation endpoints (the change is language-specific → flag only that language).
- **Absent** for name/alias/structural changes and bulk-extract (→ all-language, conservative — unchanged behavior).

The internal `translation-glossary` endpoint adds `entity_id` to each entry (the
query already `SELECT e.entity_id`; just scan + include) so the worker can record
which entities it used.

### Glossary-service (surgical)

1. **`attribute_handler.go`** — `createTranslation` / `updateTranslation` /
   `deleteTranslation` emit a best-effort, post-write `entity_updated`:
   - `actor_type="pipeline"` — **deliberate**: learning-service filters glossary
     to `actor=user` and its `EntitySnapshot` (name/kind/aliases/short_desc) has
     **no slot** for a translation-tier change, so a `user` event would record a
     0-diff correction (noise). `pipeline` is cleanly ignored by learning, still
     consumed by the staleness consumer (actor-agnostic) and captured by VG-1
     (rolling-N; translation edits stay recoverable via entity restore).
   - `target_language = language_code`, `op="updated"`.
   - book_id/entity_id are already on the path; name/kind via `loadEntityEventFields`.
2. **`outbox.go`** — `entityEventPayload + TargetLanguage`; a small
   `buildTranslationEventPayload(bookID, entityID, name, kind, lang)` helper (or
   an optional arg) that sets `target_language` and leaves before/after nil.
3. **`server.go internalTranslationGlossary`** — add `"entity_id": entityID` to
   each returned entry (scan `e.entity_id`).

`extraction_handler.go` (M4d-2b bulk emit) **untouched** — stays all-language
(machine-tier drafts + possible name writes; conservative).

### Translation-service

4. **`glossary_client.py`** — `GlossaryEntry + entity_id: str | None`; parse it.
   `build_glossary_context` retains entity_id on entries and exposes
   `used_entity_ids: set[str]` = entries that **scored > 0** (appeared in the
   chapter text) — the entities actually in play for this chapter.
5. **`migrate.py`** — new table:
   ```sql
   CREATE TABLE IF NOT EXISTS chapter_translation_glossary_usage (
     chapter_translation_id UUID NOT NULL
       REFERENCES chapter_translations(id) ON DELETE CASCADE,
     entity_id              UUID NOT NULL,
     PRIMARY KEY (chapter_translation_id, entity_id)
   );
   CREATE INDEX IF NOT EXISTS idx_ctgu_entity ON chapter_translation_glossary_usage(entity_id);
   ```
   Additive, idempotent. ON DELETE CASCADE ties usage to its translation version.
6. **`session_translator.py`** — after a chapter's glossary fetch, best-effort
   insert one usage row per `used_entity_ids` (additive; failure never breaks
   translation). Records against `chapter_translation_id` (the version).
7. **`glossary_consumer.py`** — `handle_glossary_event` becomes fine-grained:
   ```sql
   UPDATE chapter_translations ct SET is_glossary_stale = true
   WHERE ct.book_id = $1
     AND COALESCE(ct.is_glossary_stale, false) = false
     AND ($3::text IS NULL OR ct.target_language = $3)         -- per-language
     AND (
       EXISTS (SELECT 1 FROM chapter_translation_glossary_usage u
               WHERE u.chapter_translation_id = ct.id AND u.entity_id = $2)   -- precise
       OR NOT EXISTS (SELECT 1 FROM chapter_translation_glossary_usage u2     -- legacy fallback
                      WHERE u2.chapter_translation_id = ct.id)
     )
   ```
   - `$2` = entity_id (UUID), `$3` = target_language (nullable).
   - **Legacy fallback (no false-negatives):** a translation with *no* usage rows
     (translated before this slice) is still flagged — exactly today's coarse
     behavior, bounded by the language filter. **Indexed** translations that did
     *not* use the entity stay un-flagged → the precision win.
   - If the event has no `entity_id` (shouldn't happen post-deploy, but a legacy
     event might) → fall back to the old coarse book-level UPDATE.

## Parity / safety

- V2 byte-parity: usage recording is additive/post-translation; the glossary
  fetch path is unchanged except `entity_id` passthrough. `pipeline_version='v2'`
  default unaffected.
- Staleness stays a non-destructive hint; a fresh re-translation re-records usage
  and starts un-stale.
- Rolling-deploy safe: `target_language` is `omitempty` (old consumer ignores it
  → all-language, today's behavior); `entity_id` absent ⇒ coarse fallback. Either
  service can deploy first.

## Test plan

**Glossary (Go, live DB):** translation create/update/delete each emit one
`entity_updated` with `target_language` + `actor_type=pipeline`; endpoint returns
`entity_id`. **Translation (py):** `parse` keeps entity_id; `used_entity_ids` =
scored>0 set; usage rows written; consumer precise-flag (uses entity → flagged),
non-use (indexed, other entity → not flagged), legacy (no index → flagged),
language filter (vi event → en row untouched), coarse fallback (no entity_id).

**VERIFY:** ≥2 services → live-smoke token required (real glossary→relay→redis→
translation chain on a rebuilt stack, or `LIVE-SMOKE deferred to D-TRANSL-M6B-LIVE-SMOKE`).

## Deferred (anticipated)

- **D-TRANSL-M6B-LIVE-SMOKE** — full chain edit-translation → emit → consumer →
  precise per-language flag, on a rebuilt stack.
- **D-TRANSL-M6B-USAGE-BACKFILL** — legacy translations stay coarse until
  re-translated (no retro usage index). Acceptable (fallback is safe).
- **M6b-2 (FE)** — surface affected-chapter set + user-triggered "re-translate
  affected" batch.
- **D-GLOSSARY-TRANSL-CORRECTION-LEARNING** — feeding user translation-tier
  corrections to learning-service needs a translation-aware correction schema
  there; out of scope (emit is `pipeline` for now).
