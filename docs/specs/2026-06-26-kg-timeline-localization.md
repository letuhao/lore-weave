# Spec — KG Timeline tab localization (Event timeline, reader-language)

**Date:** 2026-06-26
**Status:** DRAFT (DESIGN — pending REVIEW)
**Author:** session (knowledge-graph-ontology track)
**Scope:** knowledge-service (timeline router + clients), glossary-service (read join), book-service client, frontend knowledge feature
**Extends:** `docs/specs/2026-06-23-kg-multilingual.md` (C7) and `docs/plans/2026-06-23-kg-multilingual.md` (M5/C7)

---

## 1. Problem

The **KG Timeline tab** renders a visible **mix of two languages** in the same row: the chapter
heading shows in the book's display/translated language (e.g. Vietnamese), while the event title,
participant names, summary, and `time_cue` show in the **source/origin language** (e.g. Chinese).
A reader who picked the vi translation sees "Chương 12 — Cây cầu" next to a zh event title and a zh
summary — an unsignalled language soup that reads as a bug.

This is the **Event timeline** surface (`/v1/knowledge/timeline`), distinct from the *entity*
edge-timeline/graph-view that the multilingual work (C7) already localized. The Event timeline was
never wired into the Layer-2 localization, and the only localized fragment it *does* show — the
chapter heading — comes in via a join that has **no language awareness**, which is what makes the
mix glaringly visible.

---

## 2. Root cause (verified, file:line)

Events are **source-language by design** — that is correct (Layer-1 canonical content). The defect is
that the Event-timeline **read path** serves raw Layer-1 fields with no Layer-2 localization, and
simultaneously injects one *display-language* fragment (the chapter title) so the mix is conspicuous.

| # | Fact | Evidence |
|---|---|---|
| RC1 | Event fields are extracted in the **ORIGINAL script** of the source text — by design. | `sdks/python/loreweave_extraction/prompts/event_extraction_system.md:14-16` — *"Keep `name`, `participants`, `location`, `time_cue`, and `summary` in the ORIGINAL script of TEXT. Keep `kind` values in English."* |
| RC2 | The Timeline endpoint has **no `language` param** and **no Layer-2 localization** — it returns the raw source-language Event projection. | `services/knowledge-service/app/routers/public/timeline.py:64-286` (handler signature 64-174; no `language` Query; serves `rows` straight from the repo at 264-286). Repo projection: `services/knowledge-service/app/db/neo4j_repos/events.py:120-155` (`title`/`summary`/`time_cue`/`participants` are raw strings). |
| RC3 | The **visible mix is injected** by the chapter-title enricher joining a **display/translated-language** heading. | `services/knowledge-service/app/clients/chapter_title_enricher.py:53-78` (`enrich_events_with_chapter_titles` mutates `e.chapter_title`), fed by `services/knowledge-service/app/clients/book_client.py:300-343` `get_chapter_titles` — which has **no `language` param**, so book-service returns the book's display-language "Chapter N — Title". `timeline.py:280-286` calls the enricher unconditionally. |
| RC4 | The multilingual localization (plan change **C7**) was built **only for the entity edge-timeline/graph-view nodes**, never for the Event timeline. | `services/knowledge-service/app/routers/public/graph_views.py:113-118` (localized `kind_label`/`name_label` fields on `GraphNode`), `:139-157` (`TimelineInstance.target_label_localized` / `EdgeTimeline.edge_type_label`), `:693-771` (`read_edge_timeline` resolves reader language + localizes). The Event-timeline router shares **none** of this. |
| RC5 | Events store participants as **plain NAME strings**, not `glossary_entity_id` — so participant-name localization has no anchor id to join on at read time. | `services/knowledge-service/app/db/neo4j_repos/events.py:152` — `participants: list[str]`. Contrast the entity path, which carries `glossary_entity_id` on the node (`graph_views.py:112`, `:146-148`). |

### 2.1 The pattern C7 already established (to copy)

`graph_views.read_graph` resolves the reader's language and then localizes labels via glossary
translation joins. The reusable shape:

- **Reader-language resolution** (`graph_views.py:657-666`): `clean_lang_param(language)` (explicit
  `?language=`, malformed ignored) → `book_client.get_reader_language(book_id, caller)` (the stored
  per-(user,book) preference, `book_client.py:272-298`) → `None` (canonical, unchanged). Then
  `primary_subtag(...)` folds `vi-VN` → `vi` so all label axes resolve on one subtag.
- **Entity-name localization** via the glossary join: `glossary.fetch_entity_display_names(book_id,
  entity_ids, language)` (`graph_views.py:758-760`; client at
  `services/knowledge-service/app/clients/glossary_client.py:476-511`) → glossary-service
  `POST /internal/books/{book_id}/entity-display-names`
  (`services/glossary-service/internal/api/entity_display_names_handler.go:51-130`). It returns
  `display_name` = `COALESCE(translation, original)` **plus a `translated` boolean** so an
  untranslated name falls back to canonical **with an explicit signal** (AC1).

---

## 3. Relationship to the DRAFT multilingual spec / C7

This spec **EXTENDS C7 to the Event timeline.** It does not change the locked multilingual
principles — it applies them to the one surface C7 missed:

- **Layer-1 stays source-language** (RC1 is correct; events are never re-extracted) —
  `2026-06-23-kg-multilingual.md` §2 ("Layer 1 is built once, from the source language").
- **Localization is Layer-2 derived at read time** — same as C7 for entity names/kinds/predicates.
- **AC1 (the binding rule):** *"never raw untranslated source with no signal"*
  (`2026-06-23-kg-multilingual.md` §10 AC1). Today the Event timeline violates AC1 twice: it shows
  raw source **and** it silently mixes in a display-language chapter heading. This spec brings it to
  compliance.
- **Reader-language preference is server-side per-(user,book)** (D10/R3) — reuse the existing
  `get_reader_language` resolver, do not invent a new source of truth.
- **Plan placement:** C7 lives in **M5** of `docs/plans/2026-06-23-kg-multilingual.md:119-134`
  ("timeline/graph-view label resolution"). M5 delivered the *graph-view + edge-timeline* half; this
  spec is the **Event-timeline completion of C7** and slots alongside M5's deliverables.

This spec adds **one capability C7 did not cover: on-demand translation of free-text Event
`summary`/`time_cue`.** Entity names are short, glossary-owned, and translated by the existing
glossary pipeline; event summaries are free prose with no glossary owner, so they need their own
derived-translation cache (§5d).

---

## 4. Decision

**Do BOTH** (per product decision):

1. **(i) Localize participant NAMES + chapter TITLES** — kills the visible mix fast and cheaply by
   reusing the existing C7 glossary join + a language-aware chapter-title fetch.
2. **(ii) Translate free-text Event `summary` + `time_cue`** — so the expanded-row detail is readable
   in the reader's language too.

**Critical constraint on (ii): translate ON-DEMAND + CACHED, the way glossary does it** — lazily
translate **only when a reader requests a language that isn't cached yet**, then cache the result;
**NOT** an eager pre-translation pipeline that translates every event up front. Per **AC1**, a
cache-miss returns the **source text with an explicit `translated:false`/language marker** rather than
silently mixing or blocking the response.

### 4.1 The glossary on-demand + cache pattern (verified — this is the model)

Glossary's localization is exactly "cache table keyed by `(value, target-language)` + read coalesces
to source with a flag + write upserts machine translation, never clobbering verified":

| Piece | Glossary implementation (cite) |
|---|---|
| **Cache table** | `attribute_translations` — `services/glossary-service/internal/migrate/migrate.go:111-121`. Columns: `attr_value_id`, `language_code`, `value`, `confidence` (`'draft'`/`'machine'`/`'verified'`), `translator`, `updated_at`; **`UNIQUE(attr_value_id, language_code)`** is the cache key. |
| **Read = coalesce + signal** | `services/glossary-service/internal/api/entity_display_names_handler.go:84-106` — `COALESCE(NULLIF(at.value,''), eav.original_value)` and a separate `... IS NOT NULL AS translated`. Returns `{display_name, translated}` so the caller renders a source-fallback marker on a miss (AC1; handler doc-comment `:36-39`). |
| **Write = upsert machine, never clobber verified** | `services/glossary-service/internal/api/glossary_translate_handler.go:312-327` — `INSERT … ON CONFLICT (attr_value_id, language_code) DO UPDATE … WHERE attribute_translations.confidence <> 'verified'`. |
| **The translate primitive** | Synchronous text translate: `POST /v1/translation/translate-text` → `services/translation-service/app/routers/translate.py:33-118` (book-agnostic; resolves the user's translation model via prefs, BYOK; returns translated text). The glossary *entity-attribute* path drives this in a batch via `POST /v1/glossary-translate/books/{book_id}/translate` (async job) → `services/translation-service/app/routers/glossary_translate.py:46-70`. |

**What we copy:** the *cache-table + coalesce-read-with-`translated`-flag + upsert-never-clobber*
shape, and we invoke the **same `translate-text` primitive** for the actual MT call (provider-rule
invariant: translation-service owns the provider call; knowledge-service never calls a provider SDK).
**What we adapt:** glossary keys its cache on `attr_value_id`; an event summary has no glossary attr,
so we key on the **Event node id** (or a hash of the source text) + `language` (§5d).

---

## 5. Design

All five sub-changes live behind reader-language resolution; when no reader language resolves (no
`?language=`, no stored preference), the endpoint returns today's behavior byte-for-byte
(back-compatible canonical source — an explicit no-op, not a silent default).

### (a) Add `language` resolution to `public/timeline.py`

Mirror `graph_views.read_graph:657-666`:

1. Add `language: str | None = Query(default=None, max_length=35, description="…reader language; malformed ignored; omit to resolve the caller's stored reader-language preference")` to `list_timeline_events` (`timeline.py:64-174`). Add `book_client` is already injected; inject `glossary: GlossaryClient` and (for resolution) keep `user_id`.
2. Resolve: `reader_lang = primary_subtag(clean_lang_param(language) or await book_client.get_reader_language(book_id, user_id))`.
   - **`book_id` source:** the Event timeline is project/global-scoped, not book-scoped, in its query. Resolve the book per **project** the way the edge-timeline does (`graph_views.py:740-745` via `projects_repo.project_meta(project_id)` → `meta[1]`). For the **cross-project / global** browse (`project_id is None`), reader-language is **per-(user,book)**, so a multi-book browse can't resolve a single book — in that case fall back to the **explicit `?language=`** only, else canonical (documented limitation; the FE passes the active book's language when the tab is scoped to one project — the common case).
3. If `reader_lang` is falsy → skip (b)–(d) entirely (return canonical). This keeps the world-timeline rollup (`/worlds/{world_id}/timeline`) and unscoped browse safe.

### (b) Pass `language` to `get_chapter_titles` / the chapter enricher (kills the mix)

Today `book_client.get_chapter_titles(ids)` (`book_client.py:300-343`) POSTs to
`book-service /internal/chapters/titles` **without** a language → book returns the book's
display-language heading. Fix so the joined heading matches the **reader language**:

1. Add an optional `language: str | None` to `get_chapter_titles` and forward it in the POST body
   (`{"chapter_ids": [...], "language": "vi"}`).
2. **Book-service side (cross-service):** `/internal/chapters/titles` must accept `language` and
   return the chapter heading in that language when a translated heading exists, else the source
   heading. *Verify book-service's chapter model carries per-language headings; if it does not, the
   honest behavior is to return the source heading and mark it (Open Question Q3).* This is the one
   genuinely cross-service edit — **live-smoke through knowledge → book** (cross-service rule).
3. `enrich_events_with_chapter_titles(events, book_client, language=reader_lang)`
   (`chapter_title_enricher.py:53-78`) threads `language` to the client call. The graceful-degrade
   chain is unchanged (any failure → `chapter_title=None` → FE UUID-short fallback).

**Why this is M1 and ships first:** the chapter heading is the *most* visible mixed fragment, and the
fix is pure plumbing (no new table, no MT). Doing (b) alone already removes the jarring "vi heading
beside zh event" mix by either matching languages or honestly showing source for both.

### (c) Participant-name localization via the glossary translation join

Participants render as bare strings in two places (`TimelineEventRow.tsx:178-185, 221-227`). Localize
them by reusing C7's `fetch_entity_display_names`:

- **The blocker (RC5):** events store participant **names**, not `glossary_entity_id`. The C7 join
  is keyed by entity id (`fetch_entity_display_names(book_id, entity_ids, language)`).

Two implementable options — **pick one (recommend B for M2, with A as the long-game)**:

- **Option A — store the anchor id at extraction time.** Add `participant_entity_ids: list[str|null]`
  to the Event node, populated when the extractor/resolver already resolves a participant to a
  glossary entity (the resolver runs on source text anyway). Then the read join is a direct
  `fetch_entity_display_names`. *Pro:* exact, no fuzzy match, same shape as the entity path. *Con:*
  schema add on the Event node + a backfill for existing events (large/structural → its own change);
  participants the resolver couldn't anchor stay un-localizable.
- **Option B — name→entity resolution at read time.** For the reader-language page, resolve each
  distinct participant name to a glossary entity via the existing entity-resolution surface (the same
  canonicalization the timeline `entity_id` filter already uses — `timeline.py:247-262` resolves an
  entity to its `name`/`canonical_name`/aliases candidate set; invert it: name → entity), then
  `fetch_entity_display_names`. *Pro:* no schema change, works on existing data. *Con:* a read-time
  resolution step (cache it per (book, language) page), and ambiguous names (same surface form, two
  entities) need a documented tie-break (prefer the entity already present in this project's graph).

> **Recommendation:** ship **Option B in M2** (no migration, unblocks existing books immediately),
> and track **Option A** as the durable follow-up (`D-KG-TL-PARTICIPANT-ANCHOR`) since storing the
> anchor at extraction time is strictly better once a backfill is affordable. Whichever path: an
> **unresolved/untranslated participant keeps its source name** and the FE marks it (AC1) — never a
> silent mix. The event `title` may itself name a participant; localizing the title is **out of scope
> here** (free text, no anchor) — it rides the summary path (d) if we choose to translate it, or stays
> source with the marker.

### (d) On-demand cached translation of `summary` + `time_cue` (modeled on glossary)

Add a **derived-translation cache** for free-text event fields, structurally identical to
`attribute_translations`:

- **New table** (knowledge-service Postgres mirror), e.g. `event_text_translations`:
  `event_id` (or `source_hash`), `field` (`'summary'`/`'time_cue'`/optionally `'title'`),
  `language_code`, `value`, `confidence` (`'machine'`/`'verified'`), `translator`, `updated_at`,
  **`UNIQUE(event_id, field, language_code)`** — the exact glossary cache shape
  (`migrate.go:111-121`). Keying on `event_id` (not a text hash) lets a deletion/purge cascade with
  the event; a `source_hash` column additionally guards against serving a stale translation after the
  source summary is edited (re-translate when the hash changes — mirrors the glossary
  `confidence<>'verified'` upsert guard).
- **Read = coalesce + signal** (mirror `entity_display_names_handler.go:84-106`): at timeline read,
  batch-lookup `(event_id, field, reader_lang)` for the page; return
  `summary_localized = COALESCE(cache.value, source)` plus `summary_translated: bool`. On a **miss**
  the response carries the **source text with `translated:false`** (AC1) — never blocks the read.
- **Write = lazy, after the read** (the on-demand part): for the page's **misses**, fire an
  asynchronous translate via the **`translate-text` primitive**
  (`translation-service /v1/translation/translate-text`, `translate.py:33`) and **upsert** the result
  into the cache with `ON CONFLICT (event_id, field, language_code) DO UPDATE … WHERE confidence <>
  'verified'` (mirror `glossary_translate_handler.go:312-327`). The first reader of a language sees
  source-with-marker; subsequent readers (after the cache fills) see the translation — exactly the
  glossary lazy-fill behavior. **Do not** translate inline-and-block the read (that reintroduces an
  eager-per-request cost and an open-ended LLM latency on the timeline GET — see the
  `no-timeout-on-LLM-pipeline` lesson). Options for the fill trigger: (1) a fire-and-forget task
  enqueued from the read handler for the misses, or (2) a thin internal endpoint the FE calls after
  render to warm the visible page. **Pick in PLAN**; (1) is simplest and matches glossary's
  worker-fills-cache shape.
- **Provider invariant:** the MT call goes through translation-service (which owns the provider call
  via provider-registry BYOK). knowledge-service never imports a provider SDK and never hardcodes a
  model — it calls `translate-text` and lets the user's translation prefs resolve the model.
- **Cost posture:** lazy + cached means we only ever pay to translate event text that a reader of
  that language actually opens, once. This is the §6 D6 "build-time/amortized" posture applied
  lazily — a busy book's summaries get translated on first vi read and never again (until edited).

### (e) Frontend: forward reader language + render the marker

- `useTimeline.ts:34-66` and `listTimeline` (`frontend/src/features/knowledge/api.ts:1766-1792`,
  `TimelineListParams` `:679-704`): add `language?: string` to the params, push it into the
  `queryKey` (so switching language refetches), and `qs.set('language', …)` when present. Source the
  value from the active book's reader-language preference (the same value the reader/translation UI
  already uses) — not localStorage-only (server SSOT).
- `TimelineEventRow.tsx`: render the localized fields and an explicit **untranslated marker** when the
  field's `*_translated` flag is false:
  - chapter heading (`:147`, `:151-176`) already has a fallback-marker idiom (`<code>` + aria-label) —
    reuse it conceptually for a source-language summary/participant: a subtle "source" badge or
    `lang=`-tagged span + an i18n tooltip ("shown in source language — translation pending"), so a
    sighted **and** a screen-reader user both get the signal (AC1).
  - participants (`:178-185`, `:221-227`) and summary (`:210-211`): show localized text when present,
    else source text + marker. Never render a localized chapter heading next to an unmarked source
    summary — that is the original bug.

---

## 6. Phasing

| Milestone | Covers | Why this order | Exit / AC |
|---|---|---|---|
| **M1 — language plumbing + chapter-title fix** | (a) `language` resolution on `timeline.py`; (b) language-aware `get_chapter_titles` + enricher + book-service `/internal/chapters/titles` `language` param; (e-partial) FE forwards `language`. | **Kills the visible mix fast** — the chapter heading is the most conspicuous mismatched fragment and needs no new table or MT. After M1, headings either match the reader language or honestly show source. | Reading the vi translation, the timeline no longer shows a vi heading beside an unmarked source event; chapter heading is vi when a vi heading exists, else source (no silent mix). **Live-smoke knowledge→book.** |
| **M2 — participant-name localization** | (c) Option B (read-time name→entity resolution) + `fetch_entity_display_names` join; FE renders localized participants + marker. | Reuses the shipped C7 glossary join; no migration; unblocks existing books. | Participant chips show vi names when the glossary has them, else source name + marker (AC1). Cross-tenant read still grant-gated (reuse C7 gate). |
| **M3 — on-demand cached summary/time_cue translation** | (d) `event_text_translations` cache + coalesce-read + lazy upsert via `translate-text`; FE renders localized summary/time_cue + marker. | Largest piece (new table + MT wiring + lazy-fill); built last on top of the resolved-language plumbing from M1. | First vi reader of an event sees source summary + "translation pending" marker; the cache fills; a later read shows the vi summary. No inline LLM blocking the GET. **Live-smoke knowledge→translation.** Purge of book/project cascades the cache (no orphans). |

`D-KG-TL-PARTICIPANT-ANCHOR` (Option A: store `participant_entity_ids` at extraction + backfill) is a
tracked follow-up to M2 — large/structural (Event-node schema + backfill), deferred per the gate.

---

## 7. Acceptance criteria

- **AC-T1 (no silent mix — the core fix):** with a reader language resolved, the timeline never
  renders a localized fragment (chapter heading) beside an *unmarked* source-language fragment
  (event title/participant/summary). Every source-language fragment shown to a reader-language reader
  carries an explicit marker (AC1 of the multilingual spec).
- **AC-T2 (chapter heading matches reader language):** when a translated heading exists, the timeline
  shows it in the reader's language; otherwise it shows the source heading marked, not the
  display-language heading from an un-scoped join.
- **AC-T3 (participants localized):** participant names show in the reader's language when the glossary
  has the translation; an unresolved/untranslated participant keeps its source name **with a marker**.
- **AC-T4 (summary on-demand + cached):** the first reader of a language sees the source summary + a
  "translation pending" marker (no blocking, no inline LLM on the GET); after the cache fills, a
  subsequent read shows the translated summary. A `verified` translation is never overwritten by a
  machine one. The timeline GET latency is unchanged by a cache miss.
- **AC-T5 (back-compat):** with **no** reader language resolved (no `?language=`, no stored pref), the
  endpoint returns today's exact canonical response — byte-identical.
- **AC-T6 (Layer-1 untouched):** no localization path creates/alters any `:Event` node field — the
  source `title`/`summary`/`time_cue`/`participants` on the node are unchanged; all localized values
  are derived (response-only or cache table). (Mirrors multilingual AC5.)
- **AC-T7 (tenancy/purge):** the `event_text_translations` cache is owner/book-scoped via the event,
  and deleting the book/project removes its rows (no orphans). Cross-tenant timeline read stays
  grant-gated (reuse the existing timeline auth).
- **AC-T8 (provider invariant):** knowledge-service performs **no** direct provider SDK call and
  hardcodes **no** model name for the summary translation — it calls translation-service
  `/translate-text`, which resolves the user's model via provider-registry (BYOK).
- **Live-smoke (≥2 services):** M1 — knowledge→book chapter-titles in vi; M3 — knowledge→translation
  summary translate-and-cache, second read returns the cached vi summary.

---

## 8. Open design questions

- **Q1 (participant anchor — extraction vs read-time):** store `participant_entity_ids` on the Event
  node at extraction (Option A — exact, needs schema + backfill) **vs** resolve name→entity at read
  time (Option B — no migration, fuzzy). Recommended: **B for M2**, A as `D-KG-TL-PARTICIPANT-ANCHOR`.
  Decide the anchor for the durable path in PLAN.
- **Q2 (summary cache key — `event_id` vs `source_hash`):** key on `event_id` for clean purge cascade,
  **plus** a `source_hash` column so an edited summary invalidates a stale translation (re-translate on
  hash change). Confirm Event ids are stable across re-extraction (re-mention updates, not re-creates).
- **Q3 (book-service per-language chapter headings):** does `/internal/chapters/titles` /
  book-service's chapter model already carry a translated heading per language? If **yes**, M1 just
  forwards `language`. If **no**, M1's honest behavior is to return the source heading **marked**
  (still removes the mix), and translated headings become a book-service follow-up. **Verify before
  M1 build.**
- **Q4 (global/cross-project browse language):** reader-language is per-(user,book); an unscoped
  (`project_id is None`) or world-rollup browse spans books and can't resolve a single book pref.
  Confirm the FE always scopes the Timeline tab to one project/book in the localized case, and define
  the unscoped behavior (explicit `?language=` only, else canonical).
- **Q5 (fill trigger for M3):** fire-and-forget enqueue from the read handler (simplest, glossary-like)
  vs a thin FE-triggered warm endpoint. Pick in PLAN; lean to the enqueue path with a timeout/bound on
  the MT call (`no-timeout-on-LLM-pipeline` lesson).
- **Q6 (title localization):** the event `title` is free text with no anchor. Decide whether it rides
  the (d) summary-translation cache (translate it too) or stays source-marked. Leaning: include
  `title` as a `field` in `event_text_translations` so the row header localizes alongside the summary.
