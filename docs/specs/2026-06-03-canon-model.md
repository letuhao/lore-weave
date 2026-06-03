# Canon Model — platform primitives (DESIGN spec)

> **Date:** 2026-06-03 · **Phase:** CLARIFY→DESIGN · **Branch:** `feat/composition-service`
> **Status:** DESIGN — prerequisite **Cycle 0** for composition-service (and a durable foundation for enrichment, translation-assist, future agents).
> **Task size:** **XL** — cross-service contract change (book-service + worker-infra + knowledge-service + extraction SDK) + a data migration + a backfill. `/amaw` recommended (schema/migration + cross-service contract).
> **Why now:** the composition architecture review (composition-design §12/§13) verified two platform-level holes that no single feature can fix from its own side. Rather than bolt a workaround onto composition, we fix the **canon model** once, as a primitive every feature shares.

---

## §0 Problem — pre-existing platform bugs (surfaced by composition, not caused by it)

> **Framing (PO, 2026-06-03):** these are **latent platform bugs / architectural debt that already exist** — not composition's scope. Composition is merely the **first feature to exercise these paths**, so it is the *discovery vehicle* ("not exploited yet, so not seen"). The Canon Model is justified **independently** as a bug-fix that today harms knowledge/chat/wiki/enrichment; composition just forced us to look. Do not frame its size as composition scope-creep.

The platform conflates three things that must be orthogonal:

> **"content = canon = now"** — every chapter draft-save indexes straight into the semantic store (and, on a manual rebuild, the graph), with no notion of *reviewed/published*, and no notion of *in-world time*.

**Pre-existing bugs this fixes (live today, composition-independent):**
- **B1 — `timeline?before_chronological=`/`before_order` are no-op filters.** `chronological_order`/`event_order` are never written → any client setting these bounds gets a silently-empty/wrong result *today*.
- **B2 — `extraction_pending` chapter rows are dead code** — queued on every `chapter.saved`, never consumed (only `chat` reads the table), cleared only on delete.
- **B3 — extraction/passage-ingest read the live draft when the worker runs**, which can differ from the content that triggered them → a latent race (extracts the wrong snapshot).
- **B4 — the semantic index contains unreviewed draft prose** — every keystroke-save embeds the current draft into L3/L4, so chat-grounding/drawer-search already surface half-written drafts as if they were lore.
- **B5 — `chapter_range` scope is shipped-but-broken** (preview-only; the runner ignores it).
- **B6 — re-extraction causes canon drift.** Pass-2 graph persist is **upsert-only** (`pass2_writer.py` has no DELETE); re-extracting a chapter that REMOVED a character/fact leaves the stale entity/relation/event in the graph. The retraction functions exist (`provenance.py:419-455,548`) but are **not wired** into the persist hot path. Passages self-heal (delete-first); the graph does not.
- **B7 — chat extraction drainer mis-reads chapter rows.** `_enumerate_pending_chat_turns` (`runner.py:906-923`) has no `aggregate_type` filter → a `chat`-scope run consumes `chapter`-typed `extraction_pending` rows as empty chat turns.

Verified consequences (file:line in §6):
- **No editorial lifecycle.** `chapters` has only a trash `lifecycle_state` (active/trashed) — no draft/in_review/published. (`book-service migrate.go:38-84`.)
- **Extraction = canonization fires on every keystroke.** `chapter.saved` is emitted on *every* draft PATCH (`server.go:1537`); knowledge-service extracts unconditionally on it (`handlers.py:83-138`), gated only by a project-wide on/off. → an AI co-writer's accepted-but-unreviewed prose is canonized immediately; a fabricated fact then becomes "canon" the critic enforces forever (the OI-1 failure). Autosave makes this a per-debounce extraction storm.
- **No usable ordering axis.** `chronological_order` AND `event_order` are **never written** — the LLM schema has no such field; both are NULL ~100% (`pass2_writer.py:510-523`, `event.py:111-134`). A spoiler cutoff `before_chronological=N` therefore matches **zero** events and returns empty — a no-op that *looks* spoiler-safe (the worst false-green). Meanwhile `event_date_iso` (in-world wall-clock the LLM already emits) and chapter `sort_order` (reading order, in `hierarchy_writer.py:53`) **are** populated — the data for a real cutoff exists, just unprojected.

This spec separates the conflated concerns into **four platform primitives**, built once.

---

## §1 The four primitives

### §1.1 Primitive 1 — Editorial lifecycle (book-service owns)
A chapter has an explicit editorial state and a pointer to the content snapshot that is canon.

```sql
-- book-service: chapters (additive)
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS editorial_status TEXT NOT NULL DEFAULT 'draft'
  CHECK (editorial_status IN ('draft','in_review','published'));
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS published_revision_id UUID;  -- → chapter_revisions.id (in-DB FK ok)
```
- **Publish action** — `POST /v1/books/{book_id}/chapters/{chapter_id}/publish`: snapshot the current draft as a `chapter_revisions` row (the model already inserts one per save), set `published_revision_id` = that revision, `editorial_status='published'`, emit **`chapter.published {book_id, chapter_id, revision_id}`** in the same tx (transactional outbox, mirrors `chapter.saved`). `in_review` is an optional intermediate (author "marks for review"); the canon-affecting transition is →`published`.
- **Re-edit** of a published chapter mutates the draft (diverges from `published_revision_id`) but does **not** change canon until a re-publish advances the pointer. So **the published revision is a stable canon snapshot**, decoupled from the live draft.
- `chapter.saved` is retained for content-change bookkeeping (autosave, revision history) but **no longer drives canonization** (§1.2).

### §1.2 Primitive 2 — Canon = published; the KG is a derived view (knowledge + worker-ai own)
Canonization reads **published content at the pinned `published_revision_id`**, never the live draft. **OI-1 becomes structural:** AI-accepted prose sits in a `draft` chapter and is *not canon* until a human publishes. "Accept ≠ canon; publish = canon" is enforced by the data model.

> **⚠️ Corrected by a trigger→execute trace (2026-06-03; plan [§8](../plans/2026-06-03-canon-model-cycle0.md#§8)).** There are TWO independent canonization paths, both of which must be gated on published — the original "switch one consumer" was an over-simplification:
> - **Graph extraction (Pass-2 entities/relations/events)** is today **user-triggered + whole-book** (a poll-job via `/extraction/start` run by **`worker-ai`**), NOT event-driven; `chapter.saved`→`extraction_pending` is dead for chapters. The redesign makes it **event-driven + single-chapter + pinned-revision** (new `chapter.published` consumer in worker-ai + a single-chapter scope + a new internal revision-text endpoint), AND gates the manual whole-book rebuild to skip `draft` chapters.
> - **Passage ingest (L3/L4 semantic)** is a **separate inline** path in the knowledge event consumer (current draft) — it must ALSO switch to `chapter.published` + pinned revision.
> - Extracting a pinned revision also fixes a latent race (the worker otherwise extracts whatever the live draft is when it runs).
> - `chapter.saved` stays emitted (bookkeeping); no other service extracts on it (statistics ignores it), so dropping it from canonization is safe.
> - **Concurrency (final sweep):** a unique partial index caps active extraction jobs at 1/project — so canonization is **coalesced via the `extraction_pending` queue + a per-project drainer (ONE job)**, NOT one job per event (which would 409-storm + bypass the per-job cost cap). Plan §8.2.
> - **Re-publish must RETRACT (B6/CRITICAL-2):** because the graph is upsert-only, re-extracting a chapter must call `remove_evidence_for_source` + `cleanup_zero_evidence_nodes` BEFORE re-writing, or stale facts from the prior revision drift forever. Wired in the canon path; mirrors passage delete-first.

### §1.3 Primitive 3 — Dual ordering, both populated (extraction owns)
Two orthogonal, populated axes on every Event (+ exposed on timeline/passages):
- **`reading_order`** = the chapter's `sort_order` composed with within-chapter position (e.g. `sort_order * 1e6 + scene_index/para_index`). Source already present (`hierarchy_writer.py` stores `chapter_index = sort_order`; events carry `chapter_id`). Populate `Event.event_order` (the design-intended "narrative/reading position" field, currently NULL) at `pass2_writer` write time. **The reader's spoiler axis.**
- **`chronological_order`** = rank of the event's **`event_date_iso`** within the project (a post-extraction sort+rank pass; events lacking a parseable date get NULL → fall back to `reading_order` for cutoff). **The in-world / flashback axis.** This is the cheap-from-existing-data win: in-world chronology data already exists as `event_date_iso`; we just project it to a comparable integer.
- **Backfill** both for existing events (one batch pass per project).
- **Passages** (semantic search) gain reading position too via the composition review's `chapter_index` fix (populate from `sort_order` at ingest) — folded here since it's the same axis.

**Spoiler-cutoff (any consumer) then has both axes:** filter by `reading_order ≤ scene.reading_position` (reader hasn't reached) AND/OR `chronological_order ≤ scene.story_order` (in-world hasn't happened) — true flashback-safety, not a no-op.

### §1.4 Primitive 4 — Provenance as a shared invariant (align, do NOT duplicate)
Generalize the principle **lore-enrichment already proved** (H0: enriched ≠ canon; permanent origin marker; promote-only; `confidence < 1.0`) to *all* generated content, reusing knowledge-service's existing `source_type` / `pending_validation` / `confidence` quarantine model.
- Vocabulary: `provenance ∈ {human_authored, ai_assisted, enrichment}` + `confidence`. `human_authored` = canon-weight; `ai_assisted` (composition) and `enrichment` = non-authored, soft-weight until human-promoted/published-and-confirmed.
- A KG fact records how it originated; a critic/validator weights a contradiction by provenance (hard against `human_authored`, soft against `ai_assisted`). This is enrichment's confidence model, generalized.
- **Composition's slice (implemented here in design, built with composition):** when composition-authored content is published→extracted, the resulting facts carry `provenance='ai_assisted'`. Knowledge accepts a provenance hint on the extraction trigger.

> **⚠️ lore-enrichment boundary (hard).** Primitive 4 is designed to be **compatible with** enrichment's existing H0 (`origin='enrichment'`, `confidence<1.0`, promote-only) — it does NOT modify enrichment code. Enrichment keeps its slice; composition adds its slice; both converge on one vocabulary. This spec only *designs* the shared model + implements knowledge's provenance-hint acceptance + composition's tag. **No edits to `services/lore-enrichment-service/`.**

---

## §2 Event & data flow (after)

```
Author writes (draft)            → chapter_drafts UPDATE → chapter.saved  → (bookkeeping only; NO extraction)
Author/composition publishes     → snapshot revision + published_revision_id + editorial_status='published'
                                   → chapter.published {book_id, chapter_id, revision_id}
worker-infra relay               → loreweave:events:chapter  (chapter.published added)
knowledge consumer               → on chapter.published: fetch revision body → extract (canonize)
                                   → assign event_order (reading) at write; provenance hint flows to facts
chronological_order pass          → rank project events by event_date_iso → set chronological_order (+ backfill)
```

Composition co-write maps onto this with **zero special-casing**: accept → draft (`chapter.saved`, no canon); review/done → publish (`chapter.published`, canon). The packer's spoiler cutoff reads the now-populated dual order.

---

## §3 Migration & rollout (no regression)

1. **book-service:** add columns; **backfill `editorial_status='published'` + `published_revision_id` = latest revision for every existing chapter** (they're already canon today). New chapters default `draft`.
2. **knowledge-service:** subscribe to `chapter.published`; **keep consuming `chapter.saved` ONLY during a transition window** to avoid a gap, then cut over (or: since existing chapters are pre-published and already extracted, cut over immediately — new canon only flows on explicit publish).
3. **Backfill orders:** one batch pass per project to set `event_order` (from chapter sort_order) + `chronological_order` (from `event_date_iso`).
4. **UX (separate FE follow-up, flagged):** normal chapter editor needs a **Publish** affordance. Until shipped, a chapter stays `draft` and won't (re-)canonize — acceptable because existing content is pre-`published`; only newly-created chapters need the action.

---

## §4 Build order (Cycle-0 milestones)

> **Detailed implementation plan:** [docs/plans/2026-06-03-canon-model-cycle0.md](../plans/2026-06-03-canon-model-cycle0.md) (per-service file changes · cutover/migration sequence · test strategy · risks · rollback).

| M | Title | Verify gate |
|---|---|---|
| **CM1** | book-service editorial_status + published_revision_id + `/publish` + `chapter.published` event (+ migration backfill=published) | migrate up/down clean; publish snapshots a revision + emits event; existing rows → published |
| **CM2** | worker-infra relay `chapter.published` (config-only, generic) | event reaches `loreweave:events:chapter` stream |
| **CM3** | knowledge consumer switch → extract on `chapter.published` at pinned `revision_id` (drop `chapter.saved` extraction) | live: publish a chapter → extraction runs on the published revision; a bare draft save does NOT extract |
| **CM4** | dual-order population: `event_order` (reading) at write + `chronological_order` (from `event_date_iso`) batch pass + passage `chapter_index` fix + backfill | unit: order assigned; live: `timeline?before_chronological=` and reading-order filters return correct non-empty sets; backfill stamps existing events |
| **CM5** | provenance: knowledge accepts a `provenance` hint on extraction; facts carry it; aligns with enrichment vocabulary (no enrichment edits) | unit: ai_assisted-hinted extraction tags facts; enrichment path unchanged |

**Critical path:** CM1→CM2→CM3 (the canon-gate spine) then CM4 (ordering) then CM5 (provenance). Composition's Cycle 0 dependency = CM1–CM4 (CM5 lands with composition's provenance slice).

---

## §5 Benchmark / risks

| # | Scenario | Verdict | Handling |
|---|---|---|---|
| K1 | Existing 200-chapter book post-migration | **PASS** | all → `published` + `published_revision_id`=latest; already-extracted canon unchanged; no re-extraction storm |
| K2 | Author edits a published chapter but doesn't re-publish | **PASS** | draft diverges; canon stays at `published_revision_id`; KG reflects published, not the unsaved edit |
| K3 | `event_date_iso` missing/unparseable on some events | **PASS (degraded)** | those events get NULL `chronological_order` → fall back to `reading_order` cutoff; in-world cutoff covers dated events only — **logged, documented**, never silently empty |
| K4 | `chapter.published` fires but no knowledge project for the book | **PASS** | knowledge skips (existing behavior); publish still records canon snapshot in book-service |
| K5 | Normal (non-composition) editing now needs a publish action | **UX change** | existing chapters pre-published (no break); new chapters need Publish affordance (FE follow-up §3.4) — this is the conscious "canon = published" platform decision |
| K6 | Two consumers of `chapter.saved` (if any beyond knowledge) | **verify at CM3** | confirm only knowledge used `chapter.saved` for canon (verified: it's the sole extraction consumer); other uses keep working |
| K7 | chronological_order from `event_date_iso` ordering wrong (e.g. relative dates "3 days later") | **LIMIT** | best-effort from extracted dates; refining in-world time resolution is a future extraction-quality cycle; reading-order axis is the robust fallback |

**Risks:** (1) cutting `chapter.saved`→extraction is a platform-wide behavior change — sequence the cutover carefully (§3.2). (2) `event_date_iso` quality bounds `chronological_order` accuracy (K7) — reading-order is the always-correct fallback. (3) provenance must align with, not fork, enrichment's H0 (§1.4 boundary).

---

## §6 Verified contract evidence (this design rests on real code, not assumptions)

- No chapter editorial status; only trash `lifecycle_state` — `book-service migrate.go:38-84`.
- `chapter.saved` on every draft PATCH; payload `{book_id}` only — `book-service server.go:1537,1706`; `outbox.go:15`.
- knowledge extracts unconditionally on `chapter.saved`, project-gated only — `knowledge handlers.py:83-138`, `gating.py:25-60`; subscriptions `main.py:199-200`.
- `chronological_order`/`event_order` never written; LLM schema lacks them — `pass2_writer.py:510-523`, `loreweave_extraction/extractors/event.py:111-134`, `events.py:163-233`.
- `event_date_iso` IS populated (LLM `event_date`) — `pass2_writer.py:516`. `chapter sort_order` IS populated in KG — `hierarchy_writer.py:53`. `chapter_revisions` immutable + REST — `book-service migrate.go:73-84`, `server.go:1548-1715`.
- knowledge already has `source_type`/`pending_validation`/`confidence` quarantine (the provenance substrate) — per enrichment SERVICE_DESIGN §4.3 / knowledge model.

**Trace corrections (2026-06-03):**
- Pass-2 graph extraction is **user-triggered whole-book** (`extraction.py:266-340` `/extraction/start` → `extraction_jobs` → `worker-ai/main.py:86-98` poll → `runner.py:534`), NOT event-driven; no single-chapter scope (`runner.py:791-823`, `extraction.py:95-107`). `chapter.saved`→`extraction_pending` is dead for chapters (only `chat` scope reads it).
- Passage ingest is **inline in the knowledge event consumer** (`handlers.py:227-245` → `passage_ingester.py:214`), current draft.
- Worker content fetch = current draft, no revision param (`clients.py:537`, `server.go:1860-1916`); revision text exists but is JWT-only (`getRevision` `server.go:1613-1654`) → needs an internal variant.
- worker-infra relay is generic by `aggregate_type` (`outbox_relay.go:149-205`) → `chapter.published` flows with no relay change. knowledge `BookClient` already carries the internal token (`book_client.py:36-39`).

---

## §7 Boundary & scope

- **Touches:** book-service (schema + `/publish` + event), worker-infra (relay config), knowledge-service (consumer switch + dual-order + provenance hint), extraction SDK (order assignment). FE Publish affordance = a flagged follow-up.
- **Does NOT touch:** `services/lore-enrichment-service/` (provenance is design-aligned only). glossary unchanged (entity ids already stable).
- **Composition** depends on CM1–CM4; its OI-1, spoiler-cutoff, and prose-source accept/publish flow all become straightforward once these primitives exist (see composition-design §11/§12/§13, rewired to reference this spec).
