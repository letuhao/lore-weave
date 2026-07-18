# 26 · Structure↔Prose Indexing — the source map, staleness, and the debugger

> **Status:** 📐 SEALED (multi-agent authored + adversarially reviewed 2026-07-10; PO ratified all product decisions same day — see 00B §6) — buildable
> **Scope:** `book-service` (Go) + `composition-service` (Python) + `sdks/python/loreweave_parse` + one knowledge-service event handler + frontend state rendering. Decision prefix **IX-\***.
> **Prerequisites:** [`23_book_architecture.md`](23_book_architecture.md) Phase 0 + A1 (`structure_node`, `outline_node.book_id`); [`22_scene_model_and_crud.md`](22_scene_model_and_crud.md) A1 (`scenes.book_id`/`title`/`source_scene_id`).
> **Ownership boundaries honored:** migration DDL execution + backfills + re-key order → **25**; PlanForge link-step detail → **27**; `structure_node` MCP CRUD → 23 BA11; Plan Hub panel wiring → **24**. This file defines target shapes and read contracts; it duplicates none of the above.
> Follows [`docs/standards/scope-separation.md`](../../standards/scope-separation.md) (SCOPE-1..6), [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (IN-1..8 / OUT-1..6), [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md).

---

## Why

The package model ([`00A`](00A_BOOK_PACKAGE_STRUCTURE.md) §2) gives the book a `spec/` (desired
state, composition) and a `manuscript/` (actual state, book-service), reconciled like `terraform
plan` — and an `.index/` (`scenes`) that is supposed to be the **source map** joining them, like a
compiler's debug info. Today that source map is a lie told once at import and never again:

1. **The index is write-once.** `scenes` rows are inserted by the importer and then frozen forever.
   The first prose edit silently invalidates every `leaf_text` and `content_hash` in the chapter,
   and nothing — no flag, no event, no re-parse — records that it happened. Knowledge-service's P2
   extraction and summaries keep reading **import-time prose** while passage ingestion reads the
   fresh pinned revision: the same KG ingests two different ages of the same book (§F7).
2. **The two scene identity spaces are unjoined.** The rail's `data-scene-id` anchors point at
   composition `outline_node` rows; the parse leaves are book-service `scenes` rows; the
   `source_scene_id` column that 22 specs as the join **does not exist in code** (§F4). Navigation
   plan→prose works only through a title-equality backfill living inside the draft JSON.
3. **Nobody can tell when the debugger's answer went stale.** `arc_conformance` computes a report,
   returns it (or parks it in `generation_job.result` for one poll), and persists no durable record
   of *what state of the book it was true of* (§F5). An author edits three chapters and the Hub
   would still show last week's green conformance with no dirty marker.

This spec makes the index **honestly derived** (it re-derives when the canon changes), the map
**bidirectional and lifecycle-explicit** (a scene is always in a nameable state, rendered, never
silent — BPS-13), and conformance **staleness-aware** (a report knows its inputs and can say "the
book has moved since I ran").

---

## Investigation findings

Every claim below was read from source at HEAD (`feat/context-budget-law`) on 2026-07-10.

### F1 — the index has three writers, all INSERT-only, all `parse_version=1`

`scenes` DDL: [`migrate.go:270-283`](../../../services/book-service/internal/migrate/migrate.go#L270-L283)
— `chapter_id` FK (**`ON DELETE CASCADE`**), `sort_order` (`UNIQUE(chapter_id, sort_order)`),
`path`, `leaf_text`, `content_hash`, `parse_version INT DEFAULT 1`, `lifecycle_state`. Writers:

| Writer | Path | Insert |
|---|---|---|
| .txt import (sync) | [`parse.go:280-290`](../../../services/book-service/internal/api/parse.go#L280-L290) | `INSERT INTO scenes(..., parse_version) VALUES(..., 1)` |
| epub/docx worker | [`import_processor.go:289-297`](../../../services/worker-infra/internal/tasks/import_processor.go#L289-L297) | identical SQL |
| pdf worker | [`import_processor_pdf.go:173`](../../../services/worker-infra/internal/tasks/import_processor_pdf.go#L173) | identical SQL |

All three call knowledge's stateless `POST /internal/parse`
([`internal_parse.py:37-100`](../../../services/knowledge-service/app/routers/internal_parse.py#L37-L100)).
**Only the two book-service sync import paths auto-publish**: the .txt path inserts the revision,
then pins `published_revision_id` + flips `editorial_status='published'`
([`parse.go:266-278`](../../../services/book-service/internal/api/parse.go#L266-L278); same at
[`import.go:392`](../../../services/book-service/internal/api/import.go#L392)). The **worker-infra
epub/docx and pdf importers never publish** — grep `editorial_status|published_revision_id` under
`services/worker-infra`: **zero hits**; their chapters ride the schema default `'draft'` with
`published_revision_id NULL`
([`migrate.go:298-302`](../../../services/book-service/internal/migrate/migrate.go#L298-L302)).
Two of the three index writers therefore birth `scenes` rows that parse an **unpublished draft
revision** — a fact IX-1's import corollary and the `draft-indexed` state below must absorb.

### F2 — nothing ever updates, deletes, or re-parses the index

Grep across all services: **zero** `UPDATE scenes`, **zero** `DELETE FROM scenes`; `parse_version`
appears only as the literal `1`. Draft saves
([`server.go:2247`](../../../services/book-service/internal/api/server.go#L2247),
[`:2699`](../../../services/book-service/internal/api/server.go#L2699);
[`mcp_tools_write.go:585`](../../../services/book-service/internal/api/mcp_tools_write.go#L585),
[`:674`](../../../services/book-service/internal/api/mcp_tools_write.go#L674)) update
`chapter_drafts` + `chapters` and emit `chapter.saved` — none touch `scenes`, none call
`/internal/parse`. Knowledge's cache-invalidation endpoint
([`internal_extraction.py:1245-1286`](../../../services/knowledge-service/app/routers/internal_extraction.py#L1245-L1286))
self-describes as *"Triggered by parse_version bumps (P3 re-parse)"* — **and nothing bumps
`parse_version`, and nothing calls this endpoint automatically.** The P3 re-parse it anticipates
was never built. Chapters created by typing (never imported) have **zero scenes rows forever** and
permanently ride the legacy draft-text fallback
([`scenes.go:96-141`](../../../services/book-service/internal/api/scenes.go#L96-L141)).

### F3 — the anchor lifecycle lives entirely inside the draft JSON

[`SceneAnchor.ts`](../../../frontend/src/components/editor/SceneAnchor.ts): the marker is a
`sceneId` GlobalAttribute on `heading` nodes serialized as `data-scene-id` (`:13-31` — the
declaration is load-bearing; without it Tiptap strips the attr and a save erases every marker).
`applySceneAnchors` (`:87-129`) backfills by **normalized-title equality** (`normalizeTitle`
`:36-43` — NFC + casefold + whitespace-collapse + trailing-punctuation strip, diacritics
preserved), unique matches only, one transaction, explicit user action. `jumpToSceneAnchor`
(`:66-73`) returns `false` when unanchored — the rail shows a hint, never a silent no-op
([`SceneRail.tsx:167-171`](../../../frontend/src/features/studio/manuscript/SceneRail.tsx#L167-L171)).
Book-service is oblivious: anchors persist only in `chapter_drafts.body`.

### F4 — the two identity spaces are disjoint; `source_scene_id` exists only in docs

The rail's scenes — and therefore every `data-scene-id` value — are **composition `outline_node`
rows**, not book-service `scenes` rows:
[`ManuscriptUnitProvider.tsx:144-153`](../../../frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx#L144-L153)
`loadScenes` → `compositionApi.listChapterScenes` →
[`outline.py:157-177`](../../../services/composition-service/app/routers/outline.py#L157-L177)
(`OutlineRepo.scenes_for_chapter`). Grep for `source_scene_id` under `services/` and `frontend/`:
**no hits** — every occurrence is under `docs/`. The only prose↔plan stitch in the running system
is F3's title-equality backfill.

### F5 — conformance persists no durable "what was true when"

`build_arc_conformance` / `build_deep_report`
([`arc_conformance.py`](../../../services/composition-service/app/engine/arc_conformance.py)) are
pure; the shared orchestrator
([`arc_conformance_orchestrate.py:28-128`](../../../services/composition-service/app/engine/arc_conformance_orchestrate.py#L28-L128))
is called from the synchronous `GET …/conformance?scope=arc` (which persists **nothing**) and from
the Tier-W worker, whose result *"is written to `generation_job.result` for the poll"*
([`motif_conformance_run.py:16-17`](../../../services/composition-service/app/engine/motif_conformance_run.py#L16-L17)).
There is **no table holding the latest report per arc, and no record of the input state** (which
revisions, which bindings) a report was computed against. Conformance never reads book-service
`scenes` or prose directly — "realized" is the plan-side `motif_application` ledger; prose enters
only via knowledge's motif_beat/`:Event` extraction. The worker is still keyed by
`arc_template_id` (`:78-80`) — [`23`](23_book_architecture.md) BA4 retargets it to `arc_id`
(`structure_node`); this spec writes everything against the post-BA4 shape.

### F6 — knowledge's cache identity deliberately excludes `parse_version`, and the escape hatch is orphaned

`task_id = sha256(text, op, extractor_version, model_ref, schema_key)`
([`task_id.py`](../../../services/knowledge-service/app/jobs/task_id.py)) — `parse_version` was
excluded (SR-4) in favor of the explicit invalidation endpoint (F2), which nothing calls. A changed
leaf therefore *naturally* cache-misses (the text hash changed); invalidation is hygiene (dead
rows, claim rows), not correctness. `_p2_cache_wrap` still claims leaves with a
`scene_id=chapter_id` placeholder and the literal `parse_version=1`
([`pass2_orchestrator.py:703-713`](../../../services/knowledge-service/app/extraction/pass2_orchestrator.py#L703-L713),
tracked `D-P2-PER-SCENE-FANOUT`).

### F7 — the mixed-freshness split inside one KG

P2 entity/relation/event/fact extraction and summaries are **scenes-first**
([`pass2_orchestrator.py:615-637`](../../../services/knowledge-service/app/extraction/pass2_orchestrator.py#L615-L637),
[`summary_processor.py:418-447`](../../../services/knowledge-service/app/jobs/summary_processor.py#L418-L447)
via [`book_client.py:520-560`](../../../services/knowledge-service/app/clients/book_client.py#L520-L560))
— frozen at import. Passage ingestion reads the **fresh pinned revision**
([`book_client.py:477-515`](../../../services/knowledge-service/app/clients/book_client.py#L477-L515))
on `chapter.published`. Publish an edited chapter today and the graph's entities come from the old
prose while its passages come from the new.

### F8 — event inventory and the delivery spine

Book-service outbox events (all via
[`outbox.go:18`](../../../services/book-service/internal/api/outbox.go#L18)): `chapter.created`,
`chapter.saved`, `chapter.published`, `chapter.unpublished`, `chapter.trashed`,
`chapter.deleted`, `import.requested`, `book.viewed`, `reading.progress`. **No scenes/parse
event exists.** The domain-event spine is **outbox → worker-infra relay → Redis Streams**
([`outbox.go:17`](../../../services/book-service/internal/api/outbox.go#L17) — *"relays them to
Redis Streams"*); AMQP in this system carries WS job-status pushes
([`import_processor.go:26-30`](../../../services/worker-infra/internal/tasks/import_processor.go#L26-L30))
and notif-service delivery, **not** these domain events. The `chapter.*` consumers are all
Redis-Streams consumer groups: knowledge's K14 `EventConsumer`
([`main.py:265-268`](../../../services/knowledge-service/app/main.py#L265-L268)), glossary's
staleness consumer
([`staleness_consumer.go:85`](../../../services/glossary-service/internal/events/staleness_consumer.go#L85)
`XReadGroup`), statistics
([`consumer.go:61`](../../../services/statistics-service/internal/consumer/consumer.go#L61)
`XReadGroup`). `chapter.saved` is explicitly *refused* as a staleness trigger by glossary —
*"high-volume autosave — NOT a staleness trigger"*
([`staleness_consumer_test.go:28`](../../../services/glossary-service/internal/events/staleness_consumer_test.go#L28))
— and knowledge no longer canonizes on it
([`main.py:246-252`](../../../services/knowledge-service/app/main.py#L246-L252)): extraction +
passage-ingest fire on `chapter.published` at the pinned revision. Composition-service consumes
**no domain event today** — but it is not consumer-naked: it already runs a Redis-stream job
consumer ([`job_consumer.py`](../../../services/composition-service/app/worker/job_consumer.py))
and a Redis grant-revoke listener
([`main.py:133`](../../../services/composition-service/app/main.py#L133)), so a
`scenes_reparsed` consumer group would reuse existing machinery, not build new infrastructure.

### F9 — the parse SDK is book-scoped and anchor-blind; the path prefix is recoverable

[`loreweave_parse/_types.py`](../../../sdks/python/loreweave_parse/_types.py): `SourceFormat =
Literal["html","plain"]`; `StructuralTree` requires ≥1 part ≥1 chapter ≥1 scene; `Scene` carries
`sort_order/path/leaf_text/content_hash` and **no anchor field** — a heading's `data-scene-id`
cannot currently survive parsing. Re-parsing identical input produces identical paths + hashes
(the SDK's own invariant, `_types.py:7-13`). `chapters.structural_path`
([`migrate.go:287`](../../../services/book-service/internal/migrate/migrate.go#L287)) preserves the
import-time path prefix, so a single-chapter re-parse can rewrite `path` to the chapter's true
coordinates. Book-service already has a Go Tiptap-JSON→text projection that self-describes as
*mirroring* the SDK's text-strip ([`scenes.go:143-149`](../../../services/book-service/internal/api/scenes.go#L143-L149))
— an acknowledged, display-only duplication this spec must not widen (SCOPE-4).

### F10 — publish is a clean, low-volume, transactional seam

Two publish sites, both already transactional with an outbox emit: REST
[`server.go:2354`](../../../services/book-service/internal/api/server.go#L2354) and MCP
[`mcp_actions.go:579`](../../../services/book-service/internal/api/mcp_actions.go#L579) (idempotent
via confirm-token replay, proven by
[`mcp_actions_db_test.go:139-151`](../../../services/book-service/internal/api/mcp_actions_db_test.go#L139-L151)).
Publish is an explicit user action — the natural debounce that `chapter.saved` is not. An internal
batch-resolver precedent for cheap cross-service marker reads already exists:
[`server.go:3248`](../../../services/book-service/internal/api/server.go#L3248)
(`postInternalChapterSortOrders`, 200-id cap, partial-response contract).

**Verdict.** No staleness or dirty tracking exists anywhere; the index is a decaying import
artifact; the source map column is unshipped; conformance results are point-in-time answers with
no memory of their inputs. Everything below is buildable now — no external dependency.

---

## The design in one diagram

Four freshness relations, each with exactly one owner and one detection predicate:

```
   spec/ (composition, desired)                 manuscript/ (book-service, actual)
   outline_node · structure_node                chapter_drafts ──save──▶ chapter_revisions
        ▲      ▲                                                │ publish (THE trigger)
        │      │ ③ conformance snapshot                         ▼
        │      │   (arc_conformance_state:                 published_revision_id  ── canon
        │      │    recorded revisions + spec fingerprint)      │
        │      │                                     ① re-parse│(same Tx: upsert index,
        │      └────────────────────────────┐                  │ set last_parsed_revision_id,
        │                                   │                  ▼ emit chapter.scenes_reparsed)
        │ ② source map                 .index/ scenes  (leaf_text · content_hash · parse_version)
        └── scenes.source_scene_id ────────┘                   │
            (anchor evidence, parser-written)                  ▼ unchanged read contract
                                                    knowledge P2 / summaries (canon-fed at last)

 ① index freshness   = chapters.last_parsed_revision_id vs published_revision_id
                       (book-local; published chapters only — IX-1 corollary)
 ② map completeness  = the IX lifecycle state machine (§ below)                    (read-time union)
 ③ report freshness  = arc_conformance_state.input_manifest vs current markers     (poll-on-read)
 ④ draft-ahead       = draft newer than published revision                         (already exists)
```

---

## Locked decisions

| # | Decision | Why |
|---|---|---|
| **IX-1** | **The index indexes CANON.** A `scenes` row is the parse of the chapter's **pinned published revision**, never of the live draft. Publish is the sole re-parse trigger — and therefore the debounce. **Import corollary (decided change to the writers):** the worker-infra epub/docx/pdf importers — which today insert draft-only chapters (F1) — gain the same auto-publish (pin `published_revision_id` + flip `editorial_status='published'`) the sync .txt path already performs, so every import path births index rows that parse the pinned published revision. Chapters that are indexed but not published (the legacy worker-imported corpus predating this fix, or a later `chapter.unpublished`) are the explicit `draft-indexed` state (§ state machine) and are **excluded from every freshness predicate**, all of which guard on `editorial_status='published'`. | The index's real consumers are canon-driven: P2 extraction and summaries fire on `chapter.published` (F8) and read scenes-first (F7). Indexing the draft would re-open the split F7 documents, and `chapter.saved` is autosave-frequency — glossary already refused it for exactly this reason (F8). Publish-as-debounce means no timer, no debounce state, no thundering re-parse. The import corollary exists because without it two of the three writers violate this decision at birth (F1), and an unguarded staleness predicate would flag their chapters **permanently** — stale by `IS DISTINCT FROM` yet invisible to a published-gated sweeper: a false badge with no exit. |
| **IX-2** | **Re-parse runs in the publish request path: parse BEFORE the Tx, upsert INSIDE it.** The handler parses the to-be-pinned body via `/internal/parse` (stateless, F9) first, then one transaction pins the revision, upserts `scenes`, sets `chapters.last_parsed_revision_id`, and emits `chapter.published` **and** `chapter.scenes_reparsed`. A parse failure does not block publish (OQ-1 default): the Tx runs without the scenes upsert, the freshness marker stays behind, the sweeper heals. | Ordering: `chapter.published` triggers knowledge extraction which reads scenes — if the re-parse were post-commit-async, extraction could race it and read the OLD index. Same-Tx upsert makes the event provably ordered after the index write. No cross-service call ever runs inside the transaction. |
| **IX-3** | **`chapters.last_parsed_revision_id` is the index freshness marker**, and a book-service background sweeper re-parses any published chapter where `last_parsed_revision_id IS DISTINCT FROM published_revision_id`. The sweeper emits the same `chapter.scenes_reparsed` event. | The marker makes staleness a queryable fact instead of an inference. The sweeper reuses the producer's own predicate — the `reconcile-by-truth-mirror-producer-predicate` lesson — so heal and produce can never disagree about what "stale" means. It also backfills IX-1 for the legacy corpus: every already-published chapter (including typed-only chapters with zero rows, F2) is stale by predicate and gets indexed on the first sweep. |
| **IX-4** | **Hash-preserving upsert**, keyed on `(chapter_id, sort_order)`: identical `content_hash` → row untouched (id and back-link preserved); changed → in-place `UPDATE` of `leaf_text`/`content_hash`/`path`; leaves beyond the new count → `DELETE`; new leaves → `INSERT`. Any change bumps a single per-chapter `parse_version = max(parse_version)+1` stamped on every touched row — unchanged rows keep their older stamps, so one chapter's rows carry mixed values by design. **The chapter-scalar `parse_version`** — the one value carried by the IX-10 event payload, the IX-9 canon-markers response, and the IX-8 manifest — is defined here, once: `MAX(parse_version)` over the chapter's **active** rows (equal to the bump value after any change; no chapters-level column). Returns per-chapter counts `{unchanged, updated, inserted, deleted}` — a re-parse reporting all-zero deltas for a changed revision is a bug. | Preserving row ids across an edit keeps knowledge's leaf claims and any external references stable for the (typical) majority of unchanged leaves. `DELETE` over tombstoning: the index is derived and disposable (22 SC13/D5); a soft-deleted parse leaf has no reader. The counts satisfy `silent-success-is-a-bug-not-environment`. |
| **IX-5** | **Back-link evidence rules, in precedence order:** (1) the leaf's opening heading carries `data-scene-id` → `source_scene_id` = that value (anchor wins, 22 SC7/A5); (2) no anchor, but the `(chapter_id, sort_order)` row already existed → **keep its existing `source_scene_id`** (sort-order stability); (3) otherwise `NULL`. A back-link pointing at a deleted/archived `outline_node` is treated as orphaned **at read time** by the union join — no cross-service cleanup write exists (see the integrator note on 22 D5). | Anchor evidence is authored intent; positional stability is the honest fallback that stops a one-word edit from severing every link in the chapter. Rule 3, surfaced per BPS-13, is what makes "anchor lost" a visible state instead of silent data decay. |
| **IX-6** | **The parse SDK gains `source_format='tiptap'` and `Scene.anchor_scene_id`.** The tiptap walker splits scenes by the same heading/`hr` semantics as the html walker and carries the opening heading's `data-scene-id` through to the leaf. The book-service re-parser rewrites each leaf's `path` prefix from `chapters.structural_path` (F9). The Go `tiptapJSONToPlainText` stays a display-only helper and gains **no** scene-splitting logic. | SCOPE-4: scene-splitting exists once, in `loreweave_parse`, for import and re-parse alike — a second Go implementation is the `cross-service-normalization-bug-class` (two walkers disagreeing on where a scene starts would corrupt the map silently). Additive schema change; `anchor_scene_id` defaults `None` so import paths are untouched. |
| **IX-7** | **The scene lifecycle is a closed state machine** (§ state machine below): `authored → drafted → linked → dirty → (re-linked | orphaned | prose-deleted)`, plus `draft-indexed` for an indexed chapter with no pinned canon (IX-1's corollary) and `unplanned` for an index row with no spec. Every state has a detection predicate, a named transition writer, and a rendering surface. No state is silent. | BPS-13 locked "surfaced, never silent" for one state; this generalizes it to all of them. A lifecycle an agent and a human can both read is the difference between a source map and a heap of soft ids. |
| **IX-8** | **Conformance reports become durable + input-pinned: `arc_conformance_state`** (composition, `.runs/`), one row per `(book_id, structure_node_id)`, UPSERT-latest. Columns: `report JSONB`, `input_manifest JSONB` (per-chapter `published_revision_id` + `parse_version`, plus a spec fingerprint), `deep`, `generation_job_id` provenance, `computed_at`. **Both** the sync GET and the Tier-W worker write it, through one persist helper at the `compute_arc_report` seam. History stays in `generation_job` rows; this table is only "the latest and what it was true of". | The assignment's "last_conformed_hash" made durable and arc-scoped. `.runs/` is the correct package home — derived build output, not spec (DA-2/DA-3: **no new write path into `spec/` or into the index**). One persist seam because the GET and the worker already share `compute_arc_report` (F5) — two writers would fork the manifest format. |
| **IX-9** | **Dirty is computed poll-on-read, composition-side; composition gains NO domain-event consumer.** Book-service adds an internal batch route `POST /internal/books/{book_id}/chapters/canon-markers` (mirrors the `postInternalChapterSortOrders` contract — 200-id cap, partial responses, F10) returning `{chapter_id: {published_revision_id, last_parsed_revision_id, parse_version, editorial_status}}` (`parse_version` = the IX-4 chapter scalar). The conformance-status read compares those markers to the snapshot's manifest. | Not an infrastructure argument — composition could add a Redis-Streams consumer group cheaply (F8: it already runs two Redis consumers). The reason is that a stored dirty *bit* would be a stale-able projection: events consumed to precompute what a two-table comparison answers on demand, a derived flag that can itself drift from the truth it summarizes. Poll-on-read is one bounded internal call per status read, on a surface (the Hub) that is human-opened, not hot-path. The event alternative stays available later without schema change — the manifest comparison is the same either way. |
| **IX-10** | **One new outbox event: `chapter.scenes_reparsed {book_id, chapter_id, parse_version, published_revision_id}`** (`parse_version` = the IX-4 chapter scalar), emitted in the same Tx as every index upsert (publish path and sweeper alike). Frozen schema (SCOPE-2). Consumer: a new knowledge K14 handler that calls the existing invalidation logic (F6) book-scoped. `chapter.published` keeps its exact shape and meaning. | Where a consumer already exists, prefer the event (`notification-delivery-two-buses-outbox`: outbox + relay is the delivery spine). Knowledge is the one party that materially benefits (cache hygiene + the F6 orphaned endpoint finally gets its caller). Extending `chapter.published`'s payload instead would mutate a frozen contract three services consume. |
| **IX-11** | **Provenance lands on the spec: `structure_node.source` and `outline_node.source`**, `TEXT CHECK (source IN ('authored','decompiled','planforge')) DEFAULT 'authored'`, plus `outline_node.decompile_key TEXT` with `UNIQUE(book_id, decompile_key) WHERE decompile_key IS NOT NULL`. Consumed, not just stored: (a) the decompiler's upsert predicate — a re-run may update only `source='decompiled'` rows and **never overwrites an authored node**; (b) the inspector/Hub render a "mined" badge; (c) `decompile_key = '<chapter_id>:<sort_order>'` is the idempotency key 22 SC6 requires. | Answers the assignment's open question: yes, the spec needs a source field — `arc_template.imported_derived` is the precedent. Without (a), an import retry silently clobbers human authoring — the exact `worker-loaded-id-needs-parent-scoping`/tenancy bug class transposed to provenance. A stored-but-unread `source` would be the write-only-blob bug; (a) is its consuming effect, testable. |
| **IX-12** | **The decompiler returns the map; the index owner writes it.** `POST /internal/books/{book_id}/materialize-scenes` (22 SC6/B4) gains a response field `mappings: [{chapter_id, sort_order, outline_node_id}]`; the **import tail** (parse.go / worker-infra) writes `scenes.source_scene_id` from it. Composition never writes book-service's DB (SCOPE-2). Import does **not** rewrite draft bodies to inject anchors — the ⚓ backfill (F3) remains the lazy anchor injector; on the next publish, IX-5 rule 2 preserves the written-back links even though the prose carries no anchors. | Completes the loop 22 left open: for an imported book there is no anchor in the prose, so the back-link must come from the decompile result — but the *writer* must stay on the index-owner side or `source_scene_id` gets two writing services, the exact `kg-glossary-fk-is-globally-unique` shape DA-8 exists to prevent. Rewriting user draft JSON at import is a migration over user content for no behavioral gain (SC7's own reasoning). |
| **IX-13** | **Chapter↔structure integrity is surfaced, never auto-repaired.** A `chapters` delete/trash cascades the index rows away (F1's FK) but **never deletes spec nodes**: an `outline_node` whose `chapter_id` no longer resolves renders as `prose-deleted`, with explicit re-link (`composition_outline_node_update` chapter_id) or archive as user actions. Chapter reorder syncs nothing — spec-side order is `outline_node.story_order` (span stays derived, 23 BA6); prose-vs-plan order divergence is a conformance finding, not a reconciliation. | The plan is durable desired state (DA-1's spirit inverted: deleting actual state must not destroy desired state). Auto-archiving the spec on a prose delete would silently destroy authored work — the same class as regenerating the manuscript from the spec. Detection is the same read-time chapter-marker batch call IX-9 already makes. |
| **IX-14** | **The conformance read contract is defined once, here** (§ debugger below): `GET /v1/composition/books/{book_id}/conformance/status` + MCP read tool `composition_conformance_status`. 24's Hub and 22's scene-inspector consume this contract and define no sibling *shape*. **Consumer note (final, NC-1 resolution 2026-07-10):** 24's Hub consumes **this route directly** as its read surface #7 (24 PH18 revised; its cold-open budget is ≤5 to carry it) — drift never rides `plan-overlay`, giving staleness one wire shape and an independent refresh cadence (re-fetch on focus without re-pulling the overlay). 28's `composition_diagnostics` and `composition_package_tree` compose the same **server-side helper** into their one-call agent aggregates (28 AN-2/AN-4). One computation; this route + the MCP tool are its canonical transport. Full reports stay on the existing per-arc GET / Tier-W job. | The assignment's "define the read contract ONCE" — the alternative is 24 and 22 each inventing a staleness shape and drifting (the CSS-var-duplication lesson at the API layer). |
| **IX-15** | **Knowledge-service P2 stays index-fed and untouched in contract (22 SC3 reaffirmed).** The `/internal/.../scenes` and `/hierarchy` response shapes are frozen; the scenes-first-with-draft-fallback read is unchanged; extraction never reads spec tables. IX changes only *when the rows change* — which repairs F7's mixed-freshness split as a side effect (post-IX, scenes and passages both reflect the published revision). | Non-interference guarantee, stated so the next agent doesn't "optimize" extraction into reading `outline_node`. The one knowledge change (the IX-10 handler) is additive and event-side. |
| **IX-16** | **Conformance dirtiness is canon-scoped: only publish (revision drift) or spec drift marks a report dirty — draft edits do not.** | Forced, not taste: the deep overlay's realized signal comes from knowledge extractions of **published** prose (F5, F7); a draft that hasn't published cannot have moved anything conformance measures. Draft-ahead-of-canon is already its own visible fact (④) and stays orthogonal. |

---

## The index lifecycle — state machine

States are properties of a **spec scene** (`outline_node kind='scene'`) joined against the index
(`scenes.source_scene_id`) and the anchors (draft JSON). One extra state (`unplanned`) belongs to
an index row with no spec.

| State | Definition (detection predicate) | Entered by (writer) | Renders |
|---|---|---|---|
| **authored** | spec node exists; no index row back-links it; no anchored heading | `composition_outline_node_create` (human or agent, 22 SC5) | rail + browser: *"not yet written"*, prose columns greyed (22's union row 2) |
| **drafted** | an anchored heading (`data-scene-id` = node id) exists in the draft, but no index row back-links yet (not yet published, or parse failed) | the editor — ⚓ backfill or an anchor-carrying heading insert (F3) | rail: ⚓ set, jump works against the live editor; browser: still *"not yet written"* + the ④ *draft ahead* hint |
| **linked** | index row with `source_scene_id` = node id, the chapter is **published** (`editorial_status='published'`), and its index is fresh (`last_parsed_revision_id = published_revision_id`) | **the parser** at publish/sweep (IX-2/IX-3, evidence rules IX-5) — or the import tail's decompile write-back (IX-12, post-corollary imports publish at birth) | rail + browser: normal joined row; inspector: identity + intent both live |
| **draft-indexed** | index row back-links the node, but the chapter's `editorial_status='draft'` — no pinned canon exists, so the freshness comparison is undefined (legacy worker import predating the IX-1 corollary, or a later `chapter.unpublished`) | the import tail (legacy corpus) or the unpublish action | inspector + browser: *"indexed from draft — publish to canonize"*; excluded from `index_stale` and the sweeper (both guard on published) |
| **dirty** | linked, but the owning arc's `arc_conformance_state` manifest records an older `published_revision_id` for this chapter (or no snapshot exists → `never_run`) | implicit — a predicate over ③, no stored transition | inspector: amber *"canon moved since last conformance"*; Hub: per-arc dirty badge (IX-14 contract) |
| **orphaned** (anchor lost) | index row with `source_scene_id NULL` in a chapter that has spec scenes, **or** a back-link whose node no longer resolves (read-time join miss, IX-5) | the parser (evidence rules exhausted) or a spec-node delete | browser union row 3: greyed intent + **⚓ re-anchor** action (BPS-13) |
| **prose-deleted** | spec node whose `chapter_id` no longer resolves to an active chapter (index rows already cascaded, F1) | book-service chapter delete/trash; detected via the canon-markers batch (IX-13) | inspector + Hub: *"prose deleted"* + explicit re-link / archive actions — never auto-archived |
| *(unplanned)* | index row, `source_scene_id NULL`, in a chapter with **no** spec scenes | the parser over never-decompiled prose | browser union row 3 variant: *"written, not planned"* + decompile affordance (22 SC6) |

```
                 write prose under an
   authored ──── anchored heading (⚓/editor) ───▶ drafted
      │                                             │ publish → re-parse (IX-2)
      │ decompile write-back (IX-12,                ▼ back-link via anchor (IX-5 r1)
      │  imported books skip the anchor)  ┌──▶  linked  ◀──────────────┐
      └───────────────────────────────────┘      │  ▲                  │ conformance run
              canon publishes past the snapshot  │  │ re-parse keeps   │ refreshes the
              (manifest drift, IX-16)            ▼  │ link (IX-5 r2)   │ snapshot (IX-8)
                                               dirty ──────────────────┘
   linked ── heading deleted/renamed + publish, evidence exhausted ──▶ orphaned ── ⚓ + publish ──▶ linked
   linked ── chapter unpublished (canon unpinned) ───────────────────▶ draft-indexed ── publish ──▶ linked
   any    ── chapter deleted/trashed (spec survives, IX-13) ─────────▶ prose-deleted ── re-link ──▶ linked
```

Chapter-kind nodes run the same machine minus the anchor states: `authored` (no `chapter_id`) →
`linked` (`chapter_id` set, 00A §6's join point) → `dirty` / `prose-deleted`.

---

## Re-parse — the index writer, precisely

The publish handler (both sites, F10) becomes:

1. Load the draft body that is about to be pinned (already in hand).
2. `POST /internal/parse` with `{source_format:'tiptap', content:<body JSON>, language:<book lang>}`
   (IX-6). Deterministic, stateless, no DB. On failure → skip steps 3b/3d, log, continue (OQ-1).
3. One transaction: **(a)** insert the revision + pin `published_revision_id` (unchanged);
   **(b)** hash-preserving upsert of the chapter's `scenes` per IX-4, back-links per IX-5, `path`
   prefix from `structural_path` (F9), `book_id`/`title` per 22 A1/A5; **(c)** set
   `last_parsed_revision_id = <new revision>`; **(d)** emit `chapter.scenes_reparsed`; **(e)** emit
   `chapter.published` (unchanged). Commit.
4. Return the IX-4 delta counts in the publish response's existing envelope (additive field).

The **sweeper** (book-service goroutine, interval-configured) selects
`WHERE editorial_status='published' AND last_parsed_revision_id IS DISTINCT FROM
published_revision_id AND lifecycle_state='active'` in small batches, runs steps 2–3(b–d) against
the **pinned revision body** (never the draft — IX-1), and is the legacy backfill: on first deploy
every published chapter (imported or typed) satisfies the predicate once `last_parsed_revision_id`
ships NULL. Import writers (F1) set `last_parsed_revision_id` to the import revision **and the
worker importers additionally gain the sync path's auto-publish (IX-1's corollary)**, so freshly
imported books are born published and fresh **by the sweeper's own predicate** — not swept. The
legacy worker-imported draft corpus is outside the sweeper's `editorial_status='published'` gate
by design: it sits in `draft-indexed` until its first publish, which indexes it through the normal
IX-2 path.

**What re-parse never does:** write `outline_node` or any composition table (DA-2/DA-3 — the index
points at the spec, the parser writes only the index); read or modify the draft; run on
`chapter.saved`.

---

## Dirty tracking — storage, predicate, invalidation query

### `arc_conformance_state` (composition · `.runs/`)

```sql
CREATE TABLE IF NOT EXISTS arc_conformance_state (
  book_id            UUID NOT NULL,
  structure_node_id  UUID NOT NULL REFERENCES structure_node(id) ON DELETE CASCADE,
  report             JSONB NOT NULL,           -- the full report body (coarse ± deep)
  input_manifest     JSONB NOT NULL,           -- {v:1, chapters:[...], spec:{...}} — see below
  deep               BOOLEAN NOT NULL DEFAULT false,
  generation_job_id  UUID,                     -- provenance when the Tier-W job computed it
  computed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (book_id, structure_node_id)
);
```

*(Execution order, backfill, and its place in the Phase-0 re-key: **25**. This table is new and
empty — no backfill needed.)*

`input_manifest` (versioned envelope, 22 SC12's discipline):

```json
{ "v": 1,
  "chapters": [ {"chapter_id": "…", "published_revision_id": "…", "parse_version": 3} ],
  "spec": { "structure_node_version": 4,
            "outline_fingerprint":  "sha256:…",
            "bindings_fingerprint": "sha256:…" } }
```

- `chapters` — the arc's member chapters (via `outline_node.structure_node_id` →
  `outline_node.chapter_id`) with the canon markers **as read at compute time** through IX-9's
  batch route. `parse_version` here is the IX-4 chapter scalar (`MAX` over active rows) — the
  same derivation the event and the markers route use, defined once in IX-4.
- `outline_fingerprint` — sha256 over the ordered member nodes' `(id, version, tension,
  story_order, beat_role)`; `bindings_fingerprint` — sha256 over the arc's `motif_application`
  rows' `(id, motif_version, outline_node_id)`. Coarse by design: a false-dirty (touch without
  semantic change) errs conservative; a false-clean cannot happen.

**One writer:** a `persist_conformance_state(...)` helper called by both `compute_arc_report`
callers (the sync GET and `run_conformance_run`) immediately after compute — the manifest is
assembled from the same reads the compute just did, so report and manifest can never describe
different states.

### The dirty predicate (poll-on-read, IX-9)

`dirty_reasons ⊆ {never_run, prose_drift, spec_drift, index_stale}`:

```
never_run    ⇔ no arc_conformance_state row for the arc
prose_drift  ⇔ ∃ member chapter: current published_revision_id ≠ manifest's recorded one
spec_drift   ⇔ current fingerprints ≠ manifest.spec (recompute both, compare)
index_stale  ⇔ ∃ member chapter: editorial_status = 'published'
               AND last_parsed_revision_id ≠ published_revision_id   (advisory — the deep
               overlay's scenes-fed extraction lags the canon; heals via IX-3's sweep. The
               published guard repeats the sweeper's own WHERE clause, so the badge can never
               fire on a chapter the sweeper cannot heal — a draft-indexed chapter is not stale,
               it is unpublished)
```

The invalidation query is therefore **not a write** — dirtiness is derived at read time from
`arc_conformance_state` + one canon-markers batch call + two in-DB fingerprint scans. Nothing
stores a dirty bit that could itself go stale.

---

## The decompiler — recovering source from binary

Two decompilers exist at two granularities; this section is their single coherent home. Both mint
**spec** rows with `source='decompiled'` (IX-11); both are propose-shaped in spirit — mined
structure is a recovered *approximation*, visibly distinct from authored intent.

| | `materialize-scenes` (22 SC6) | `composition_arc_import_analyze` (+ `motif_mine`) |
|---|---|---|
| Granularity | chapter + scene `outline_node` per parse leaf | arc-scale: `structure_node` + motif placements |
| Runs | import tail (automatic, after parse commits); re-runnable on demand | on demand, Tier-W propose→confirm (cost-gated: [`mcp/server.py:2931-2946`](../../../services/composition-service/app/mcp/server.py#L2931-L2946), engine [`motif_deconstruct.py`](../../../services/composition-service/app/engine/motif_deconstruct.py)) |
| Cost | deterministic, $0 | LLM, ledger-claimed |
| Idempotency | `outline_node.decompile_key = '<chapter_id>:<sort_order>'`, partial-unique (IX-11); already-mapped leaves (`source_scene_id NOT NULL`) are skipped | the existing Tier-W confirm-token replay guard (`consumed_tokens`) |
| Provenance | `source='decompiled'` on every minted node | `source='decompiled'` on minted `structure_node`s; `arc_template_id` stays NULL (23 BA13 — no template involved) |
| Back-link | response `mappings[]` → import tail writes `scenes.source_scene_id` (IX-12) | none — arcs have no index row; membership is `outline_node.structure_node_id` |

**Re-run safety (the IX-11 predicate, testable):** a decompiler upsert may update only rows whose
`source='decompiled'`; an authored node matching a decompile key is **left alone and reported** in
the response counts (`skipped_authored`), never overwritten. A retry after a failed IX-12
write-back finds the `decompile_key` rows already present and returns the same mappings —
idempotent per `idempotency-gate-exists-not-active-version` (the gate checks *exists*, not
*in-flight*).

**Volume-aligned arc proposals (IX-17 — the BPS-9 ✅ resolution, PO-decided 2026-07-10).** When the
book has `parts` rows (an imported volume/folder structure), the **arc-level** decompiler
(`composition_arc_import_analyze`) includes the volume boundaries in its analysis input and may
**propose** arc boundaries aligned to them — each proposed arc carrying a
`boundary_hint: 'volume' | 'content'` marker so the reviewer can see *why* the split is where it
is. The proposal flows through the tool's **existing Tier-W propose→confirm gate**: nothing is
written until the human approves (or redraws the boundaries in the review payload). The
scene-level decompiler (`materialize-scenes`) is untouched — it maps parse leaves, not narrative
structure. **DA-12 ✏️ is the law here:** the *silent* path stays forbidden — a `structure_node`
minted from `parts` without a confirm token is a defect, not a feature; the confirm-token replay
guard is the enforcement seam, and a test asserts that an unconfirmed analyze proposes but writes
zero rows. Orthogonality in data is unchanged: no schema relation between `parts` and
`structure_node` exists or is added — the hint lives only in the proposal payload, and an approved
arc is `source='decompiled'` authored structure like any other, with no back-pointer to the volume
that suggested it.

**PlanForge's link step (27)** is the third producer of spec rows and stamps `source='planforge'`;
its detail (pass orchestration, `event_id` idempotency) is owned entirely by 27 — IX only reserves
the enum value so provenance is closed-set from day one.

---

## Conformance as the debugger — the read contract (defined once)

### `GET /v1/composition/books/{book_id}/conformance/status` — VIEW-gated (E0 grants, BPS-8 `_book_or_deny`)

Cheap: no LLM, no compute — `arc_conformance_state` + one canon-markers batch + fingerprints.

```json
{ "book_id": "…",
  "arcs": [ {
      "structure_node_id": "…", "title": "Betrayal", "kind": "arc",
      "computed_at": "2026-07-10T…", "deep": true,
      "dirty": true, "dirty_reasons": ["prose_drift"],
      "stale_chapters": ["<chapter_id>", "…"],
      "summary": { "thread_progress": 0.62, "pacing_drift": 14,
                   "succession_violations": 1, "unmaterialized": 3 } } ],
  "index": { "stale_chapter_count": 2 } }
```

`summary` is a fixed five-field projection of the stored report (OUT-1: reference-first — the full
report body is fetched per-arc via the existing conformance GET or the job result, not dumped
here). `dirty_reasons` values are the IX-9 closed set. An arc with `never_run` returns
`computed_at: null, dirty: true` — absence is stated, not omitted (the
`fe-status-default-fallback-signals-backend-field-omission` lesson: a LIST that omits the field
makes every consumer invent a default).

### MCP: `composition_conformance_status` (R)

Args `{book_id: uuid, arc_id?: uuid}` (explicit scope per IN-2; identity from the envelope per
IN-1). Returns the same shape, filtered when `arc_id` is given. No closed-set *input* args beyond
uuids; the `dirty_reasons` **output** vocabulary is asserted by the contract snapshot test. Output
through `_tool_result_content` (OUT-3). This tool is pillar-26 machinery, defined here; 28 adds no
sibling.

### Consumers (reference, not re-specified)

- **24 · Plan Hub** — per-arc dirty badges + the `index.stale_chapter_count` rollup come from this
  route, polled on Hub open/focus. 24 defines placement; OQ-3 defines aggressiveness.
- **22 · scene-inspector** — the per-scene `dirty` chip = the owning arc's `dirty ∧ this scene's
  chapter ∈ stale_chapters`. The inspector reads the same response; no per-scene endpoint exists.
- **Refresh action** — "re-run conformance" from either surface is the existing
  `composition_conformance_run(scope='arc', arc_id=…)` Tier-W flow (23 BA4). On completion the
  snapshot updates (IX-8) and the badge clears by predicate — no cache to invalidate.

---

## Cross-service events — decided

| Event | Status | Decision |
|---|---|---|
| `chapter.scenes_reparsed {book_id, chapter_id, parse_version, published_revision_id}` | **NEW** (IX-10) | Emitted in the same Tx as every index upsert. Consumer: knowledge K14 handler → book-scoped cache invalidation (finally wiring F6's orphaned endpoint logic). Schema frozen at birth. |
| `chapter.published` | unchanged | Stays the canon/extraction trigger. IX-2's same-Tx ordering guarantees the index is current when it fires. |
| `chapter.saved` | unchanged, **explicitly not used** | High-volume autosave; refused precedent in glossary (F8). Publish is the debounce (IX-1). |
| a composition-side consumer | **not built** (IX-9) | Poll-on-read on the status route; composition's existing Redis consumers (F8) would make one cheap, but a dirty *bit* would be a stale-able projection of a two-table comparison — the wrong artifact, not missing plumbing. |

**Benign race, stated honestly:** knowledge's `scenes_reparsed` invalidation and its
`chapter.published` extraction handler may interleave; because `task_id` keys on the text hash
(F6/SR-4), the worst case is a deleted-then-recomputed cache entry — cost, never corruption.

---

## Non-interference guarantee (P2 extraction — 22 SC3 reaffirmed)

1. `/internal/.../scenes` and `/internal/.../hierarchy` response **shapes are frozen** (F1's
   `sceneRow` fields; additive-only if 22's `book_id`/`title` surface there).
2. Extraction's read contract — scenes-first, draft-projection fallback for zero-row chapters —
   is untouched. Post-IX the fallback population shrinks toward zero (typed chapters get rows at
   first publish) but the path remains.
3. Extraction never reads `outline_node`, `structure_node`, or any spec table. The spec steers
   *generation* (23 BA12); the KG ingests *prose*.
4. The mixed-freshness split (F7) closes as a side effect: scenes and passages both derive from
   the pinned published revision after IX-1/IX-2.
5. Knowledge's placeholder claims (`scene_id=chapter_id`, literal `parse_version=1`, F6) are
   tolerated — text-hash keying makes them harmless — and remain tracked under
   `D-P2-PER-SCENE-FANOUT`, not expanded here.

---

## Target data model (shapes here · execution order + backfills in 25)

```sql
-- book-service ──────────────────────────────────────────────────────────────
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS last_parsed_revision_id UUID;   -- IX-3 (NULL = never
  -- indexed → the sweeper's legacy-backfill predicate matches every published chapter once)

-- scenes: no new columns beyond 22 A1 (book_id, title, source_scene_id). IX-4's upsert and
-- IX-5's evidence rules are behavior over the existing shape; parse_version becomes meaningful.

-- composition-service ───────────────────────────────────────────────────────
-- arc_conformance_state: full DDL in §Dirty tracking above (new table, empty, no backfill).

ALTER TABLE structure_node ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'authored'
  CHECK (source IN ('authored','decompiled','planforge'));                    -- IX-11
ALTER TABLE outline_node   ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'authored'
  CHECK (source IN ('authored','decompiled','planforge'));
ALTER TABLE outline_node   ADD COLUMN IF NOT EXISTS decompile_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_outline_decompile_key
  ON outline_node(book_id, decompile_key) WHERE decompile_key IS NOT NULL;   -- IX-11 idempotency
```

SDK (additive): `SourceFormat` gains `"tiptap"`; `Scene` gains `anchor_scene_id: str | None = None`
([`_types.py`](../../../sdks/python/loreweave_parse/_types.py)) — existing callers unaffected.

---

## API + MCP surface (delta only)

| Surface | Change | Gate |
|---|---|---|
| book-service publish (REST + MCP action) | runs IX-2; response gains the IX-4 delta counts | unchanged (EDIT + confirm-token) |
| `POST /internal/books/{book_id}/chapters/canon-markers` | **new** internal batch resolver (IX-9; mirrors `postInternalChapterSortOrders`) | `requireInternalToken` |
| `POST /internal/books/{book_id}/materialize-scenes` | response gains `mappings[]` + `skipped_authored` count (IX-12; route itself is 22 B4) | internal |
| `GET /v1/composition/books/{book_id}/conformance/status` | **new** (IX-14) | VIEW (E0, `_book_or_deny`) |
| `composition_conformance_status` | **new MCP read tool** (IX-14) | VIEW |
| `chapter.scenes_reparsed` | **new outbox event** (IX-10), frozen schema | — |
| knowledge K14 dispatcher | **new handler** for `chapter.scenes_reparsed` → existing invalidation repo | — |

Everything else (scene CRUD, structure CRUD, conformance run) is 22/23 surface, referenced not
re-specified.

---

## GUI surfaces — state rendering (panels owned by 22/24; states owned here)

| Surface (owner) | Renders |
|---|---|
| `SceneRail` (22) | per-scene state chip: ⚓ present/absent (`drafted` vs `authored`), jump-fails hint (F3), the union's third shape for `unplanned`/`orphaned` |
| `scene-inspector` (22) | the full state machine word-for-word: *not yet written / drafted / linked / indexed from draft / changed since last conformance / anchor lost / prose deleted*, plus the ⚓ re-anchor and re-link actions (BPS-13) |
| `scene-browser` (22) | the union table's three row shapes, `dirty` as an amber column chip; group-by-Arc header shows the arc's `dirty_reasons` |
| Plan Hub (24) | per-arc dirty badge + `index.stale_chapter_count` from the IX-14 route; "re-run conformance" affordance → existing Tier-W flow |
| chapter list (15) | optional `index_fresh` column from the canon markers — integrator note, not required for v1 |

No new panels. No new dock entries. DOCK-2 (no forks): every chip reads the IX-14 contract or the
22 union — no surface computes its own staleness.

---

## Task breakdown

**Phase A — parse SDK + endpoint (Python; gates B)**
| # | Task | Files |
|---|---|---|
| A1 | `source_format='tiptap'` walker: heading/`hr` scene splits identical to `html_walker`; carries `anchor_scene_id` from `data-scene-id`; determinism round-trip tests (same input → same paths/hashes) | `sdks/python/loreweave_parse/{_types,dispatcher,tiptap_walker}.py` |
| A2 | `/internal/parse` accepts the new format (dispatcher passthrough); body-cap + 422 semantics unchanged | `services/knowledge-service/app/routers/internal_parse.py` |

**Phase B — book-service re-parse (Go; gates C, E)**
| # | Task | Files |
|---|---|---|
| B1 | `chapters.last_parsed_revision_id` (shape here; ordering in **25**); import writers set it; worker importers gain the sync path's auto-publish — pin `published_revision_id` + flip `editorial_status='published'` (IX-1 corollary) | `internal/migrate/migrate.go`, `internal/api/parse.go`, `worker-infra/…/import_processor{,_pdf}.go` |
| B2 | `reparse.go`: pre-Tx parse call + IX-4 hash-preserving upsert + IX-5 evidence rules + `path` prefix rewrite + delta counts | `internal/api/reparse.go` (new) |
| B3 | Wire both publish sites (REST `server.go` + MCP `mcp_actions.go`) per IX-2; emit `chapter.scenes_reparsed` in-Tx | `internal/api/server.go`, `mcp_actions.go`, `outbox.go` |
| B4 | Sweeper goroutine on the IX-3 predicate (batched, interval-configured); re-parses the **pinned revision** | `internal/api/reparse_sweeper.go` (new), `cmd/` wiring |
| B5 | `POST /internal/.../canon-markers` batch route (200-cap, partial-response, mirrors `postInternalChapterSortOrders`) | `internal/api/server.go` |

**Phase C — composition dirty tracking (Python; needs B5 + 23 A1)**
| # | Task | Files |
|---|---|---|
| C1 | `arc_conformance_state` table + repo (shape here; ordering in **25**) | `app/db/migrate.py`, `app/db/repositories/conformance_state.py` (new) |
| C2 | `persist_conformance_state` helper; call from both `compute_arc_report` callers; manifest assembly (fingerprints + canon markers) | `app/engine/arc_conformance_orchestrate.py`, `app/routers/conformance.py`, `app/engine/motif_conformance_run.py` |
| C3 | `book_client.canon_markers(...)`; status route + `composition_conformance_status` tool (IN/OUT rules; contract snapshot) | `app/clients/book_client.py`, `app/routers/conformance.py`, `app/mcp/server.py` |

**Phase D — decompiler completion (needs 22 B4 + 23 Phase 0)**
| # | Task | Files |
|---|---|---|
| D1 | `source` + `decompile_key` columns (shapes here; ordering in **25**); IX-11 never-overwrite-authored predicate + `skipped_authored` count in materialize | `app/db/migrate.py`, `app/routers/outline.py` |
| D2 | `mappings[]` in the materialize response; import-tail write-back of `source_scene_id` (IX-12) | `app/routers/outline.py`; `book-service/internal/api/parse.go`, `worker-infra/…/import_processor{,_pdf}.go` |
| D3 | `arc_import_analyze` commit path stamps `source='decompiled'` on minted `structure_node`s | `app/engine/motif_deconstruct.py` |

**Phase E — knowledge handler (needs B3)**
| # | Task | Files |
|---|---|---|
| E1 | Handler for `chapter.scenes_reparsed` registered in knowledge's Redis-Streams K14 `EventDispatcher` (`app/events/dispatcher.py`) → existing invalidation repo, book-scoped | `app/main.py`, `app/events/handlers.py`, `app/events/dispatcher.py` |

**Phase F — FE + verification**
| # | Task |
|---|---|
| F1 | State chips per the GUI table (rail / inspector / browser / Hub hook); i18n keys |
| F2 | **Cross-service live-smoke** (≥2 services — mandatory): import a book → edit a chapter → publish → assert `scenes` rows changed (IX-4 counts), `last_parsed_revision_id` advanced, `chapter.scenes_reparsed` consumed by knowledge (invalidation logged), P2 re-extraction reads the NEW leaf text (F7 closed), and the Hub status flips the arc to `dirty:prose_drift` then clears after a conformance run. Drive the real path per `prefer-e2e-and-evaluation-over-live-smoke-poc`; rebuild images first per `live-smoke-rebuild-stale-images-first`. |
| F3 | Effect tests: IX-5 rule 2 (one-word edit preserves every link); IX-11 predicate (re-import never clobbers an authored node); sweeper heals a synthetically-stale chapter (`sweeper-live-smoke-strand-recipe`); DB tests carry `xdist_group("pg")` |

**Ordering.** A → B → {C, E} in parallel; D needs 22/23 prerequisites and is independent of B2-B4;
F last. Per `fanout-independent-slices-parallel-build-serial-integrate`: disjoint files, one serial
VERIFY.

---

## Open questions

| # | Question | Disposition |
|---|---|---|
| OQ-1 | Should a parse failure block publish? | ✅ **RATIFIED (PO 2026-07-10) — decision: NO** (publish proceeds; index marked stale; sweeper heals — IX-2). Rationale: prose availability beats index freshness for a derived artifact, and the failure is visible (marker + `index_stale` reason), not silent. The alternative (publish 500s on a parser bug) holds user prose hostage to infrastructure. |
| OQ-2 | Should the scene browser index **drafts** (debounced re-parse on save) or canon only? | ✅ **RATIFIED (PO 2026-07-10) — decision: canon-only in v1** (IX-1). Draft divergence is already visible via ④. Draft-indexing re-opens F7's split, needs debounce machinery, and serves only browsing-before-publish — revisit on a real user request, not speculation. |
| OQ-3 | How loudly does the Hub surface dirtiness? | ✅ **RATIFIED (PO 2026-07-10) — decision: per-arc badges + one `stale_chapter_count` rollup line; no book-level banner.** A global banner for a normal authoring loop (edit → publish → eventually re-run conformance) trains users to ignore it. |
| OQ-4 | Does a spec-node delete physically NULL `scenes.source_scene_id` (22 D5's wording)? | **Decided: read-time orphaning (IX-5), no cross-service cleanup write — and no physical clearing either.** Composition cannot write book-service's DB (SCOPE-2), and the re-parser consults no node liveness: IX-5 rule 2 keeps an existing back-link unconditionally on a positional match (book-service reads no composition table — § *What re-parse never does*). A dangling back-link therefore renders as null via the union join **for as long as it dangles**; the stored value changes only when the leaf itself is re-evidenced — rule 1 (a new anchor wins) or rule 3 (a positional miss nulls it). **Integrator note:** 22 D5's phrase "deleting a spec node nulls `source_scene_id`" should be read as *renders-as-null*; suggest a one-line amendment in 22. |
| OQ-5 | 22 SC5 says the index row is emitted "by the parser, **on draft/save**" — IX-1 says on publish. | **Decided here: publish (IX-1), superseding SC5's cadence parenthetical.** Evidence: the index's consumers are publish-driven (F7/F8); `chapter.saved` is autosave-frequency and already refused as a trigger by glossary; publish is the free debounce. SC5's *substance* (no cross-service write on create; the parser emits the row) is untouched. **Integrator note:** 22 SC5 needs a two-word amendment ("on publish"). |
| OQ-6 | Who writes `source_scene_id` — 00A §6 says "sole writer: the parser", but IX-12's import write-back is the import tail. | **Decided: one writing ROLE, honestly spanning TWO services** — book-service (`parse.go`, the publish re-parser) and worker-infra's already-sanctioned book-DB import tail (`import_processor{,_pdf}.go`, which INSERTs the very `scenes` rows being back-linked — F1); composition never writes it and only returns maps. DA-8's letter ("exactly one **service** writes each soft id") is therefore **amended, not satisfied** — the invariant's substance holds (one identity arbiter, one evidence-rule set IX-5, no composition-side second writer, no two writers disagreeing), its per-service phrasing does not, and pretending "book-service + its worker path" is one service would paper over the fact. Routing the import write-back through a book-service internal endpoint was considered and rejected: false hygiene while worker-infra already inserts the rows themselves. **Integrator note:** amend 00A §6 + DA-8 to "sole writer: the index-owner role — book-service's parser plus worker-infra's book-DB import tail; never composition". |
| OQ-7 | Should `arc_conformance_state` keep history? | **Decided: latest-only** (IX-8). History already exists in `generation_job` rows for job runs; a history table would duplicate it for a reader nobody has named. Revisit if the Hub grows a timeline view. |
| OQ-8 | Sweeper cadence and batch size? | **Decided: config-driven, default 5-minute interval, 20 chapters/batch** — engineering, not product; both are env-tunable deploy ceilings (settings-and-config: platform infra, not user choice). |

---

## Risks

| Risk | Mitigation (lesson) |
|---|---|
| Re-parse silently no-ops (helper returns success, no rows changed on a changed revision) | IX-4 delta counts in the publish response + the F2-style grep becomes a test: an integration test edits one leaf and asserts `{updated:1}` (`silent-success-is-a-bug-not-environment`, `checklist-is-self-report-enforce-by-tests`) |
| A second scene-splitting implementation drifts from the SDK (the Go text helper grows split logic) | IX-6 confines splitting to `loreweave_parse`; the Go helper is display-only and documented as such (`cross-service-normalization-bug-class`; F9's existing mirror comment) |
| The sweep and the publish path disagree on "stale" | Both use the one predicate on `last_parsed_revision_id` (`reconcile-by-truth-mirror-producer-predicate`) |
| Import retry duplicates spec nodes after a failed write-back | `decompile_key` partial-unique + skip-mapped-leaves; the gate checks *exists*, not *in-flight* (`idempotency-gate-exists-not-active-version`) |
| A re-import clobbers authored spec nodes | IX-11's never-overwrite-authored predicate + `skipped_authored` count + an effect test (F3) |
| Knowledge's mocked book-client hides canon-markers' live shape | Consumer-path live smoke through the real route (F2 task; `new-cross-service-contract-needs-consumer-live-smoke`, `mocked-client-hides-server-side-default-filters`) |
| Stale FE/BE images produce a false-green live smoke | rebuild first (`live-smoke-rebuild-stale-images-first`) |
| Manifest false-dirty on a no-op touch (fingerprint includes `updated_at`-adjacent churn) | Fingerprints hash **values** (`tension`, `story_order`, `motif_version`), not timestamps; residual false-dirty errs conservative and costs one advisory badge, never a wrong report |
| The one-Tx publish grows a cross-service call inside the transaction "for simplicity" | IX-2 states the pre-Tx/in-Tx split explicitly, where the next agent will look (the 22-risk-table pattern); the parse call is step 2, the Tx is step 3 |
| `arc_conformance_state` writes bind strings to timestamptz | asyncpg needs datetimes; integration test on live PG (`asyncpg-timestamptz-param-needs-datetime`) |
| New DB tests interleave on the shared dev Postgres | `pytestmark = pytest.mark.xdist_group("pg")` on every new real-DB test file (CLAUDE.md test-parallelization rule) |
| Event handler added but never fires in prod (relay/binding gap) | E1 verified by the F2 live smoke asserting the *invalidation effect*, not handler registration (`emit-wiring-live-proof-catches-bypass-chokepoint`) |
