# 01 · Data Architecture — Work Assistant Mode

**Date:** 2026-07-11 · **Status:** design **v2** — red-teamed ([`RED-TEAM-2026-07-11.md`](RED-TEAM-2026-07-11.md)).
Verdict on v1: *"tenancy sound; **erasure and temporal models broken at the foundation**"* — and both are
load-bearing for the feature's two headline promises ("delete my day"; "what did Alice say last month?").
**§6 (temporal) and §8 (erasure) are rewritten**; §8b adds the deltas the red team found. Grounded in a
6-service current-schema map (all deltas code-verified with file:line). Extends
[`docs/DATA_ARCHITECTURE.md`](../../DATA_ARCHITECTURE.md). Implements the decisions in
[`00-overview.md`](00-overview.md) — it does not re-decide them; §9 lists corrections applied back to it.

This is the cross-cutting storage contract every sub-feature build reads first. It answers: what new/changed
tables, columns, constraints, indexes, and events exist; who owns each; what the tenancy scope key is; how
data flows write-side; the temporal model; and the complete "delete my day" copy-set.

---

## 1. Ownership & tenancy at a glance

Each microservice owns its own Postgres DB (per the platform rule). The feature adds **no new database** and
**no new service** — only columns, a few tables, and events on existing services.

| Store | Service · DB | New for this feature | Tenancy scope key |
|---|---|---|---|
| `books`, `chapters`, `chapter_revisions/drafts/blocks`, `book_collaborators`, `outbox_events` | book-service · `loreweave_book` | `books.kind`; `chapters.{entry_date, journal_kind, diary_kept_at, kg_indexed_revision_id, kg_exclude}`; new `chapter.kg_indexed` event; draft-only internal write route | `books.owner_user_id`; chapters transitively via `book_id` |
| `knowledge_projects`, `knowledge_pending_facts`, `extraction_*`, `summary_*`, Neo4j `:Fact/:Entity/:Event` | knowledge-service · `loreweave_knowledge` + Neo4j | `knowledge_projects.{is_assistant, chat_turn_extraction_enabled}`; `pending_facts` extension; `statement` fact type; `chapter.kg_indexed` handler; fact-destination branch | `user_id` (+ `project_id`); Neo4j nodes carry `user_id`+`project_id`, app-enforced via `assert_user_id_param` |
| `glossary_entities`, `system_kinds`/`user_kinds`, `wiki_*` | glossary-service · `loreweave_glossary` | System-tier **work ontology seed** (data, not schema); `flavorWorkCapture` prompt; consumes `book.kind` | `owner_user_id` / `book_id`; `UNIQUE(book_id, kind_id, normalized_name, scope_label)` |
| `chat_sessions`, `chat_messages`, `user_chat_ai_prefs` | chat-service · `loreweave_chat` | `user_chat_ai_prefs.assistant` JSONB + session override; `chat_sessions.{assistant marker, capture_status}`; pg_trgm index; `chat_search_sessions` MCP; day-window internal read | `owner_user_id`; messages also `session_id` |
| `sharing_policies` | sharing-service · `loreweave_sharing` | kind-check in `patchSharingPolicy` (no DDL) | `book_id`, `owner_user_id` |
| `spend_guardrails`, `usage_logs`, `token_reservations`, `usage_outbox` | usage-billing + provider-registry | per-feature **spend lane** column ×3 + daily-window sub-cap | `owner_user_id` (+ lane tag) |
| `users`, `user_preferences` | auth-service · `loreweave_auth` | **IANA `timezone` + day-cutoff** (recommended home) | `user_id` |

**Tenancy law compliance:** every new row carries an existing per-user/per-book scope key; no new
System-tier *mutable* row is introduced (the work ontology is System-tier **read-only** seed data; users
clone/adopt into per-book tier, per the User Boundaries law). The diary book is per-user private and
**un-shareable by construction** (§4/D10).

---

## 2. book-service deltas

| Change | Definition | Decision | Migration risk / lesson |
|---|---|---|---|
| `books.kind` | `TEXT NOT NULL DEFAULT 'novel' CHECK (kind IN ('novel','document','lore','diary'))`; **immutable** (server-set, no PATCH surface). Backfill `UPDATE books SET kind='lore' WHERE is_bible=true`. | D14 | ADD-COLUMN-won't-revisit-default → explicit backfill UPDATE, not DEFAULT alone. Audit **every** book-create path so none bypasses immutability. `is_bible` (migrate.go:362) is the exact precedent; keep it as the orthogonal hidden-container flag. |
| one-diary-per-user | Partial unique `(owner_user_id) WHERE kind='diary' AND lifecycle_state='active'`; `ON CONFLICT` repeats the predicate. | §4.1.1 | partial-index-ON-CONFLICT-predicate-must-match; `lifecycle_state` predicate exempts trashed rows (tombstone-exempt lesson). |
| `chapters.entry_date` + `journal_kind` | `entry_date DATE` (see §6 for DATE-vs-ISO decision), `journal_kind TEXT CHECK (journal_kind IN ('primary','supplement'))`, both nullable (diary-only). Partial unique `(book_id, entry_date) WHERE journal_kind='primary' AND lifecycle_state='active'`; job-level advisory lock `(user, entry_date)`. | D9, §4.3, E2 | `entry_date` has **no tz semantics at the DB layer** — the distiller must compute it from the user's IANA zone + day-cutoff before INSERT. Concurrent "End my day" on two devices must converge via the partial unique + advisory lock. |
| `chapters.diary_kept_at` | **Orthogonal column** (`diary_kept_at TIMESTAMPTZ` or `diary_status TEXT`) — **NOT** a third value on `editorial_status`. | §4.1.2 | Widening `editorial_status` (today `CHECK IN ('draft','published')`) would break the reparse sweeper's `editorial_status='published'` gate (reparse_sweeper.go:79) and the canon backfill (migrate.go:1006), and contradict "diary has no publish concept." Orthogonal column sidesteps all existing consumers. |
| `chapters.kg_indexed_revision_id` + `kg_exclude` | `kg_indexed_revision_id UUID` (no FK, mirrors `last_parsed_revision_id`'s "dangling marker heals" design, migrate.go:314); `kg_exclude BOOLEAN NOT NULL DEFAULT false`. | D15/§4.7 | **HIGH — see §5.** Not just a column add: the scenes-parse step (`upsertChapterScenes`) runs today only inside `publishChapter`; a new code path must parse a draft revision for a chapter that never publishes, or `extraction_leaves.scene_id` has nothing to key on for diary entries. |
| `chapter.kg_indexed` event (**new name**) | New MCP/REST "index / add to knowledge" action mirroring `mcpPublishChapter` (mcp_actions.go:538-616): in one Tx, sets `kg_indexed_revision_id` to the current draft's snapshotted revision and emits **`chapter.kg_indexed` `{book_id, chapter_id, revision_id}`**. Publish also sets the same pointer (compat). | D15 | **Do NOT reuse `chapter.saved`** — see §7. Fired only by the explicit action + idle-debounce, never per autosave. |
| draft-only internal write route | New `POST/PATCH /internal/...` (owner-scoped, X-Internal-Token, draft-only) for the distiller worker. | §4.3 | book-service `/internal` is 100% GET today except one image-upload POST (server.go:185-222) — genuinely new write surface. The worker has no user JWT; owner_user_id is an explicit param, must not become an ambient any-book write (internal-route-must-grant-check lesson, in spirit). |
| `getBookProjection` + `getBookAccess` contracts | Add `kind` to **both** responses (server.go:2831 projection; collaborators.go:202 access). | D10, §4.2 | Two **different** endpoints for two **different** consumers (sharing-service; glossary) — do not conflate. Additive JSON field; ship each with a consumer live-smoke. `requireGrant` currently discards the `Access` struct — wiring `kind` to the flavor point needs a small refactor. |
| collaborator handlers reject diary | `inviteCollaborator` + `putCollaborator` reject `kind='diary'` (collaborators.go:363,432). | D10(b) | No DDL. |

---

## 3. knowledge-service deltas

| Change | Definition | Decision | Risk / lesson |
|---|---|---|---|
| `knowledge_projects.is_assistant` (+ one-per-user partial unique) | Additive marker column; `project_type` CHECK **not** extended (stays `('book','translation','code','general')`, migrate.py:25). | §4.1.1 | Low/additive. Name `is_assistant` vs a `purpose` TEXT — pick one home (spec alternates; §8). |
| `knowledge_projects.chat_turn_extraction_enabled` | `BOOLEAN DEFAULT true`; provisioning sets **false** for the work project. | D6 | Must be consulted in **both** `handle_chat_turn.should_extract` (handlers.py:46 — no gate today) **and** worker-ai's `_ensure_chat_pending_jobs` drainer. One-sided wiring = silent-success bug. The `canon_capture_enabled` self-disarming normalization block (migrate.py:1385) is the safe-ship playbook if a bad default ever escapes. |
| `knowledge_pending_facts` extension | `fact_type` CHECK add `'statement'` (today `('decision','preference','milestone','negation')`, migrate.py:732); `session_id` → **nullable** (today NOT NULL, migrate.py:731); add `chapter_id`/`provenance JSONB`, structured `subject`/`predicate`/`object`, `event_date`, and a `dedup_key`. | D4, D5, PUX-1 | CHECK widen must use the idempotent **DROP-then-ADD CONSTRAINT** pattern (extraction_jobs.scope, migrate.py:431) — not an inline edit. Nullable `session_id`: every consumer with a `session_id = $N` filter mismatches NULL rows — needs a mixed-null test. `dedup_key` needs a real unique/lookup index or the E11 self-feeding guard is decorative. |
| `chapter.kg_indexed` handler | New `handle_chapter_kg_indexed` mirroring `handle_chapter_published` (handlers.py:136) but keyed off `kg_indexed_revision_id`; enqueues the existing `extraction_pending` table via `upsert_chapter_pending` (no new table). | D15 | **Must register a NEW event, not `chapter.saved`** (§7). Consumer live-smoke required (new-cross-service-contract lesson). |
| fact-destination branch | `pass2_writer`'s fact-merge branches on a per-project policy: assistant/diary projects **divert** to `knowledge_pending_facts` (inbox) instead of the trusted `pending_validation=False` Neo4j `merge_fact`. | D4 | Decide the policy-column name; verify whether Pass-1 quarantine writer also needs gating, not just Pass-2. |
| work ontology (KG schema) | System-tier `'work'` `kg_graph_schemas` template, adopted at provisioning via the existing adopt path. | D5 | Data, not DDL. |
| Neo4j — no schema change | Diary facts reuse existing `:Fact`/`:Relation` with `event_date_iso` as the wall-clock key (§6). | D9 | App-enforced tenancy (`assert_user_id_param`) — every new query path must use it. |

---

## 4. glossary / chat / sharing / billing / auth deltas

**glossary-service** (D5/§4.2) — *ontology is data, not schema* (verified: no `glossary_entities`/`wiki` column needed):
- **Work ontology seed:** System-tier kinds `colleague, project, meeting, decision, task, term, org` + attributes, added as a **new ledger chain entry** (never edit `0025_seed_*` in place — silent-no-op-on-migrated-DB bug). Adopted per-book at provisioning via the existing `adoptBookOntologyCore` (genres=`['work']`).
- `flavorWorkCapture` prompt (new, non-fiction framing), selected **server-side** from `book.kind` via the extended `getBookAccess` contract — never a caller arg (preserve-not-introduce: `captureCanonRequest` has no flavor field today).
- **Erasure gap (P2):** live-captured entities land with `book_id` provenance only (no `chapter_id`); consider a `captured_at`/session provenance column so "delete my day" can find them (§8).

**chat-service:**
- `user_chat_ai_prefs.assistant JSONB` (`enabled, distill_enabled, distill_model, spend_cap_usd`) + a `chat_sessions` session-override column. **Must extend the 4-field category whitelist + the Pydantic model together** (REST-mirror-drops-fields bug class).
- `chat_sessions`: an **assistant-session marker** (a `session_kind` column, or derive from `book_id`=diary — decide in §8) + **`capture_status`** to persist the per-turn `CaptureDecision` (today stdout-only and discarded — PUX-5) for the home-strip chip.
- `chat_search_sessions` MCP tool → chat-service becomes an **MCP host** (new infra) + `chat_`-prefixed ai-gateway registration (namespacing lesson). Owner-scoped (authenticated id only), default `session_scope='assistant'`, capped excerpts wrapped data-not-instructions.
- **Indexes:** `CREATE EXTENSION pg_trgm` (outside the DDL tx, book-service's pattern) + GIN trigram on `chat_messages(content)` (the existing english-tsvector index is useless for VI/CJK); + `idx_chat_messages(owner_user_id, created_at)` for the day-window/catch-up sweep. **Build `CONCURRENTLY`** — this table is expected to grow large, and the migrate house-style is non-concurrent (ACCESS EXCLUSIVE lock).
- New `GET /internal/chat/messages/day-window` (owner + local_date, filtered `session_kind=assistant`) for the distiller. **AS-BUILT:** filters `s.session_kind='assistant'` (sealed T-4, ratified 2026-07-12); `book_id` is an optional extra scope.
- `GET .../messages` gains `after_seq` + a **tail-default** (last N) mode — API only, no DDL (D12/EDGE-2).
- Send path: `pg_advisory_xact_lock(hashtext(session_id))` around seq-assign + retry-once on unique violation (EDGE-5) — no DDL.

**sharing-service** (D10c/E16/TEN-1) — `patchSharingPolicy` rejects `visibility ∈ {unlisted, public}` when `kind='diary'`, via a **live** kind lookup on every PATCH (it serves from the cached policy row today and never re-calls book-service — a pre-existing policy row would otherwise bypass the check). No DDL.

**usage-billing + provider-registry** (COST-3/§6) — a **generic feature/lane column** on `token_reservations` + `usage_logs` + `usage_outbox` (not another mcp-key-style special case), a **daily-window** sub-cap variant of `guardrailReserve` (the existing sub-cap is monthly), cap resolved from `assistant.spend_cap_usd`, lane tag carried in `job_meta` across every enqueue hop (consumer live-smoke). Distiller model resolves via the ModelRole cascade (`assistant.distill_model` → chat-capability default → **visible failure**; no cheapest-capable ranking exists).

**auth-service** (D9) — **IANA `timezone` + `day_cutoff`** in `user_preferences` (JSONB, migrate.go:63) is the recommended home (platform-wide fact; notifications/stats also want it), **not** a chat-specific column — but this is an explicit §8 open decision, not yet pinned. Nothing stores a timezone today.

---

## 5. The D15 indexing re-key is L-sized, not a predicate swap (own plan)

The overview treats §4.7 as its own prerequisite plan; the map confirms *why* it can't be mechanical:

1. **The sweeper is hard-gated on publish.** `sweepStaleChapters` (reparse_sweeper.go:74-84) filters on
   `editorial_status='published' AND published_revision_id IS NOT NULL AND last_parsed_revision_id IS
   DISTINCT FROM published_revision_id`. Re-keying only the *comparison* to `kg_indexed_revision_id` still
   excludes every draft-only diary entry — it would never be healed on a transient parse failure.
2. **`last_parsed_revision_id` is overloaded.** It is the **scenes/structural-decomposition** freshness
   marker (IX-3), a *different* concern from "has this been fed to the KG." Blindly re-keying it conflates
   the two. **Recommendation:** `kg_indexed_revision_id` gets its **own independent staleness check + sweep
   arm**, leaving `last_parsed_revision_id` to mean scenes-freshness. Two pointers, two sweeps.
3. **Scenes parse is publish-only today.** `upsertChapterScenes` is invoked only inside `publishChapter`
   (server.go:2401). Diary indexing needs the same parse to run for a draft revision — decide whether KG
   extraction even needs scenes, or reads `chapter_blocks`/`chapter_revisions` directly.
4. **Concurrent-reindex guard.** `reparseOneChapter`'s `FOR UPDATE ... WHERE published_revision_id=$2 AND
   editorial_status='published'` needs a `kg_indexed_revision_id`-keyed sibling for the new action's
   concurrent case.

This is why `04-publish-independent-indexing.md` is its own detail doc and a **Prereq** phase.

---

## 6. Temporal model — ⚠️ REWRITTEN (v1 was actively wrong)

The Neo4j `:Fact`/`:Relation` model is **bitemporal with three axes** (facts.py:13-220):

| Axis | Field | Meaning | Diary usage (**corrected**) |
|---|---|---|---|
| Transaction-time | `valid_from` / `valid_until` | When the fact was written/invalidated in the graph | Unchanged. `memory_forget` touches only this (soft-invalidate, Neo4j-only — **not erasure**) |
| Story-ordinal | `valid_from_ordinal` / `valid_to_ordinal` | Position in narrative time | **`valid_from_ordinal = entry_date as days-since-epoch`, NOT NULL** |
| Event date | `event_date_iso` | An optional *detected* date (novels) | Also set from `entry_date` — but it is a **sort key, not a filter**, today |

### ⚠️ v1 said "recommend NULL ordinal for diary facts." That would have broken the feature. Two ways:

**(a) NULL-ordinal facts are invisible to recall.** `_LIST_FACTS_FOR_ENTITY` filters
`AND ($before_order IS NULL OR f.from_order <= $before_order)` (facts.py:514). `NULL <= N` evaluates to NULL
→ **the row is dropped**. And `$before_order` is *never* None in production — `reader_tools.py:239-241` says
so explicitly (*"ALWAYS an int (-1 when the reader's position is unknown) — NEVER None"*), and
`entities.py:653` is fail-closed the same way. Meanwhile `event_date_iso` on `:Fact` is only ever a **sort**
key (`order_by_event_date`, default `False`, **no production caller passes `True`** — facts.py:496-499); the
codebase's only date *filter* is on `:Event` (events.py:1100-1101), which `memory_timeline` uses — and
`memory_timeline` never reads `:Fact`. **Net: "what did Alice say about the budget last month?" had no query
that could answer it.**

**(b) NULL-ordinal facts never supersede.** `maintain_chain` — the only supersession engine — hard-skips
`WHERE f.valid_from_ordinal IS NOT NULL` (temporal.py:132). So "launch is Friday" (Mon) and "launch is
Tuesday" (Wed) would **both stay open forever**, both returned by every default read
(`valid_until IS NULL` — facts.py:422, :512, :666). The feature that needs contradiction resolution *most*
would have it switched off.

### The fix

1. **Stamp the ordinal.** A diary is *perfectly* ordinal — one `primary` entry per day, strictly ordered.
   `valid_from_ordinal = days_since_epoch(entry_date)`, NOT NULL. This buys supersession, as-of reads, and
   back-fill correctness **with zero new code**. (Precedent: glossary's `entity_facts.valid_from_ordinal
   BIGINT NOT NULL` with a `-1` cold-start sentinel.)
2. **Build a date-filtered `:Fact` read** — mirror `events.py:1100-1101`'s `event_date_iso` range predicate.
   This is **net-new**; §3's *"`memory_*` … ✅ reuse unchanged"* was false.
3. **The diary writer must create the `:ABOUT` edge** — `memory_remember`/pending-facts-confirm never do
   (executor.py:677-686), and `_LIST_FACTS_FOR_ENTITY` requires it (facts.py:506).
4. **Caveat on `maintain_chain` (from `08`):** its chain key is **(subject, fact_type)** — so in a work KG
   *every* `decision` about Alice would be one chain, blind-closing unrelated decisions. **The assistant path
   must not pass `maintain_chain=True`** until the scope key gains a topic dimension. Supersession for the
   diary is therefore **D17's job** (explicit amendment), not the implicit chain.

**Also:** `chat_messages.local_date` is stamped at **write time** (not derived at distill time), so a later
timezone/day-cutoff change cannot retroactively re-bucket history and mint duplicate entries (red team T21).

---

## 7. Event & outbox contracts

The one load-bearing contract correction. **`chapter.saved` already exists** and is a live, high-frequency,
**deliberately un-consumed** event: it fires on every `book_chapter_save_draft` (autosave) and
`book_chapter_restore_revision`, payload `{book_id}` only (mcp_tools_write.go:585,674). knowledge-service was
**purposely moved off** consuming it (CM3b/CM3c, main.py:246-251: *"so unreviewed draft prose never
canonizes"*).

→ The D15 index trigger uses a **new, distinct event `chapter.kg_indexed`** (`{book_id, chapter_id,
revision_id}`), fired **only** by the explicit "index / keep entry" action + idle-debounce. `chapter.saved`
is left entirely untouched. This avoids (a) resurrecting the CM3b/CM3c canonize-drafts bug, (b) a breaking
payload-shape change, (c) autosave thrash. *(The map's knowledge-service and cross-cut readers initially
proposed re-registering `chapter.saved` — that follows the overview's original wording; the book-service
reader caught the collision. `chapter.kg_indexed` is the reconciled answer, now applied to `00-overview.md`.)*

**Identity carry:** `chapter.*` events carry only `book_id`; consumers resolve `project_id`/`user_id` via
`knowledge_projects WHERE book_id=$1` (the pattern `handle_chapter_published` already uses) — the
worker-infra outbox relay is payload-opaque, so there is **no** X-Project-Id-drop-style envelope bug here
(that is a different chokepoint, the ai-gateway MCP federation). `chat.turn_completed` already carries
`project_id`/`user_id` in-payload; the D6 gate rides that same lookup.

**Provisioning fan-out** runs through **api-gateway-bff forwarding the user's own JWT** to the public
book/knowledge APIs (composition-service's bearer-forwarding shape), not a new internal-token contract; each
step is an idempotent upsert against its partial-unique so concurrent provisions converge.

---

## 8. "Delete my day" — ⚠️ REWRITTEN. Erasure is **unbuilt infrastructure**, not a copy-set list (D18)

v1 wrote a copy-set table whose **first row was false**. The two foundational facts:

### 8.1 Chapters are NEVER row-deleted → every `ON DELETE CASCADE` in the copy-set is INERT

`grep "DELETE FROM chapters"` → **zero hits.** "Delete a chapter" is a *soft transition*:
`UPDATE chapters SET lifecycle_state='purge_pending', purge_eligible_at=now()` + emit `chapter.deleted`
(server.go:1772-1777; mcp_actions.go:691-692). **Nothing consumes `purge_eligible_at`. No purge worker
exists.** So the full diary text survives **forever** in `chapter_raw_objects.body_text`,
`chapter_drafts.body`, **`chapter_revisions.body` (every historical version)**, and `chapter_blocks.text_content`
— while `chapter.deleted` *does* fire, so the derived layer partially reacts. That is **worse than a no-op**.

→ **Deliverable: a purge worker** (`DELETE FROM chapters WHERE lifecycle_state='purge_pending' AND
purge_eligible_at < now() - grace`). Buildable — the signal and the state already exist. **The erasure test
must assert the `chapters` row is GONE, not `purge_pending`.**

### 8.2 The Neo4j facts survive at `evidence_count=0` — and re-extraction RESURRECTS them

`handle_chapter_deleted` runs exactly `MATCH (s:ExtractionSource {source_id}) … DETACH DELETE s`
(handlers.py:576-584) — that deletes **the source node and its incident edges, nothing else**. The
`:Fact`/`:Entity`/`:Event` nodes **survive**, retaining `fact_text`, subject/object (= **colleague names**),
and their `embedding_*` properties. The handler's own docstring promises *"cleanup zero-evidence nodes"* —
**that code does not exist**; `cleanup_zero_evidence_nodes` (provenance.py:721) is called from exactly one
place, gated on a **re-extraction of that same source**, which by definition never happens for a deleted
chapter. And because `merge_fact` MERGEs on a **natural key**, a later day re-mentioning the fact restores
`evidence_count ≥ 1` → **the "deleted" fact reappears with its original content.**

Zero-evidence ⇒ invisible to `evidence_count >= 1` reads. **Invisible is not erased** — and for third-party
personal data under a "delete my day" promise, that distinction is the entire point.

→ **Deliverable:** an erasure **job** (not an inline event handler — the extraction race at handlers.py:472-478
is real) that runs `remove_evidence_for_natural_key` **then** `cleanup_zero_evidence_nodes` under the
project's one-active-job lock. Test asserts the `:Fact` node is **absent**.

### 8.3 The copy-set (corrected — with the stores v1 missed)

| Store | Reached today? | Action |
|---|---|---|
| `chapters` (+ CASCADE children: drafts, revisions, raw_objects, blocks) | ❌ **row never deleted** | **purge worker (8.1)** |
| Neo4j `:Fact`/`:Entity`/`:Event` + embeddings | ❌ survive at `evidence_count=0`; **resurrect** | **erasure job (8.2)** |
| `summary_chapters/parts/books` (+ md5 cache keys) | ❌ not touched | day-scoped delete + rollup invalidation |
| `extraction_leaves` (+ `_raw` — raw LLM fact text) | ❌ only cleared book-wide on reparse | chapter-scoped delete |
| `knowledge_pending_facts` | ❌ **no chapter/day linkage exists** | the `chapter_id`/provenance column (§3) is the prerequisite to even *find* them |
| glossary `glossary_entities` (day-minted drafts) | ❌ `book_id` only | needs `captured_at`/provenance |
| **`usage_logs` / `usage_log_details`** — hold the **decryptable prompt text**, i.e. the diary content (colleague names, what they said), sent on every capture/compaction/distill/grounding call. `owner_user_id` but **no `book_id`** | ❌ **structurally unreachable**; no retention sweep | **carry the spend-lane tag onto `usage_logs`**; delete assistant-lane rows in the day's window (`usage_log_details` already CASCADEs) |
| **`chat_sessions.compact_summary`** — a *second* LLM digest of the day, on the session row | ❌ not covered by the `chat_messages` retention window | day-scoped clear |
| **glossary `evidences.original_text`** — **verbatim quotes lifted from the chapter** (`chapter_id` is a bare UUID, no FK) | ❌ the glossary `chapter.deleted` consumer only flips a staleness flag | delete by chapter |
| **MinIO objects** (`chapters.storage_key`, audio segments, page images, import files) | ❌ `RemoveObject` is never on the chapter-delete path | purge worker removes objects |
| `chat_messages` (raw transcript) | retention window | governed by §7, not chapter delete |
| **Coach transcripts + `ChatOutput` scorecards + `reflection_patterns`** | ❌ absent from v1 entirely — *the most sensitive artifacts in the feature* | add to the inventory with retention defaults |
| Backups (14-day retention) | ⚠️ a restore **resurrects erased days** | append-only erasure log replayed after any restore; state an "erasure completes within N days" promise that matches backup retention |

`memory_forget` is **not** an erasure primitive — it soft-invalidates one Neo4j fact's `valid_until`; content
and PG untouched. True erasure deletes at the PG SSOT and cascades (**D17/D18**).

---

## 8b. Additional deltas from the red team (all code-verified)

| # | Delta | Why |
|---|---|---|
| T29 | **`books.kind` immutability = a DB `BEFORE UPDATE` trigger** raising on `NEW.kind <> OLD.kind` | Today the only "enforcement" is a convention that nobody adds `kind` to the two dynamic UPDATE allowlists (`patchBook` server.go:912; MCP `book_update` mcp_tools_write.go:201). The privacy lock is load-bearing — assert it at the **DB layer** |
| T30 | **`createWorldCore` must set `kind='lore'`** in the same commit as the backfill | `mcp_worlds.go:48` inserts the world-bible with `is_bible=true` and **no `kind`** → post-migration bibles get `'novel'` while pre-migration ones are `'lore'`. There are **4** book-create paths (REST server.go:634 · MCP mcp_tools_write.go:100 · world-bible mcp_worlds.go:48 · the new diary path) — enumerate all four |
| T33 | **`getBookAccess`: gate `kind` behind `lvl != GrantNone`, and switch to `resolveAccess`** | It leaks `lifecycle_state` **unconditionally** today (an existence oracle), even though a purpose-built `resolveAccess` (collaborators.go:118-129) exists to blank it — and is not used. Adding `kind` the same way would leak *"this user has a diary"*. Pre-existing bug — **fix now** |
| T31 | **chat-service: `CREATE EXTENSION pg_trgm` + the trigram index as separate best-effort calls OUTSIDE the main DDL string; drop `CONCURRENTLY`** | Both migrators wrap DDL in a transaction → `CONCURRENTLY` raises `25001`. Worse, chat-service's migration is **one multi-statement string** — a naked `CREATE EXTENSION` on a role without CREATE privilege **aborts the whole migration → chat-service will not start**. Mirror book-service's deliberate isolation (migrate.go:598-604) |
| T34 | **`PendingFact.session_id` → `str \| None` in the SAME change as the DDL** | The Pydantic model is non-optional → a NULL row raises `ValidationError` in `model_validate` → **the LIST endpoint 500s**, it doesn't merely omit (the REST-mirror-drops-fields class) |
| T40 | **`memory_*` must require an explicit project scope for diary data; `get_entity_with_relations` gains a project filter** | `memory_recall_entity`/`memory_timeline` pass `project_id=None` when a session has no linked project → `($project_id IS NULL OR …)` = **ALL the user's projects**; `_GET_ENTITY_WITH_RELATIONS_CYPHER` (entities.py:2096-2125) has **no project filter at all**. The diary would surface inside a novel-writing session (**D16**) |
| T21 | **`chat_messages.local_date`** stamped at write time + index | Makes the catch-up sweep an indexed anti-join and immune to a later timezone/day-cutoff change (which would otherwise re-bucket history and mint duplicate entries) |
| T18 | **`employment_epoch`** on the work project | A job change otherwise blends the ex-employer's confidential facts into the new job. Recall defaults to the current epoch; export-then-purge at the boundary |

## 9. Corrections this map forced on `00-overview.md`

Applied to the overview (with a review-record line there):

1. **§4.7/D15 event name:** `chapter.saved` → **`chapter.kg_indexed`** (collision with the existing live,
   deliberately-unconsumed autosave event — §7).
2. **§4.7/D15 scope:** the sweeper re-key is not a predicate swap — `kg_indexed_revision_id` needs its own
   independent staleness pointer + sweep (last_parsed_revision_id is the scenes marker) — §5.
3. **"diary kept status"** (§8 phasing cell): resolved to an **orthogonal `diary_kept_at` column**, not a
   third `editorial_status` value — §2.
4. **Temporal model:** three axes, not two — §6.

### v2 (post-red-team) — the load-bearing reversals

5. **D9 / §6 — the ordinal.** v1's *"recommend NULL `valid_from_ordinal` for diary facts"* was **actively
   wrong**: it makes facts **invisible to every entity-anchored recall path** and **disables the only
   supersession engine**. Now: `valid_from_ordinal = days_since_epoch(entry_date)`, NOT NULL — plus a
   net-new date-filtered `:Fact` read and the `:ABOUT` edge (so §3's *"memory_* ✅ reuse unchanged"* was false).
6. **D18 / §8 — erasure.** v1's copy-set assumed a cascade that **can never fire** (chapters are never
   row-deleted) and a Neo4j cleanup that **does not exist** (facts survive at `evidence_count=0` and
   **resurrect** on re-extraction). Erasure is **unbuilt infrastructure**, not a table of stores.
7. **D6 — the extraction gate** must be **derived and fail-closed**, not `DEFAULT true`.
8. **D10 / D16 — egress.** The diary's privacy must propagate to **derived** stores (KG, glossary, wiki,
   public-MCP, notifications, listings), not just `books`.

## 10. Open decisions for the P1/P2 plans

1. **`user.timezone`/day-cutoff home:** auth-service `user_preferences` (recommended, platform-wide) vs a
   chat-service column. Blocks trustworthy `entry_date`.
2. **`entry_date` representation:** native `DATE` vs truncated-ISO string (round-trip into `event_date_iso`).
3. **`kg_indexed_revision_id` staleness:** own pointer+sweep vs re-key (recommend own — §5).
4. **assistant-session discriminator:** new `chat_sessions.session_kind` column vs derive from diary `book_id`.
5. **fact-destination policy column** name + whether it also gates the Pass-1 quarantine writer.
6. **`is_assistant` vs `purpose` TEXT** on `knowledge_projects` (one home, one name).
7. **glossary `captured_at`/provenance** column for day-scoped erasure of live-captured entities.
8. **spend-lane column** shape (generic tag) + the daily-window sub-cap.
