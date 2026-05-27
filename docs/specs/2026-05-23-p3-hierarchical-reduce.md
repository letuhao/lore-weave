# Spec — P3 Hierarchical Reduce + Per-Level Summaries (hierarchical extraction T4 + T7 stage 1)

> **Status:** DESIGN 2026-05-23. XL task (18 files, 8 logic, 1 side-effect = knowledge-service Postgres schema + Neo4j schema additions). Branch `main`.
> **Workflow:** v2.2 default. `/review-impl` invoked at REVIEW (design) per `feedback_review_impl_on_design_cycles`.
> **Parent ADR:** [`docs/03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md`](../03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md) §3 T4 + T7 stage 1 + §6 P3 + §7 P3.
> **P1+P2 preconditions:** [`p1-structural-decomposer.md`](2026-05-23-p1-structural-decomposer.md) ships parts/scenes schema; [`p2-parallel-map-checkpoint.md`](2026-05-23-p2-parallel-map-checkpoint.md) ships extraction_leaves cache + per-chapter cache wrap. P3 reduces what P2 caches into hierarchical KG.
> **CLARIFY answers (PO, locked session 64):**
>   1. Tree-merge implementation — **HYBRID** (deterministic merge in Python like pass2_writer; summary embedding writes Neo4j-side).
>   2. Summary generation — **ASYNC** (separate summary-job after extraction completes via Redis Stream).
>   3. Backward-compat — **NO BACKFILL** (existing flat graphs stay; Mode-3 router handles both shapes).
>   4. Summary storage — **SEPARATE** Neo4j vector index per level (chapter/part/book).

---

## 1. Problem

Per ADR §1: extraction must produce a hierarchical KG that supports multi-resolution retrieval (specific entity lookup → scene; theme/arc query → chapter/part summary). P1 ships the structural tree; P2 ships the per-leaf cache + extraction. P3 ships the **tree-merge** that turns per-leaf KGs into a `:Scene → :Chapter → :Part → :Book` Neo4j hierarchy AND ships the **per-level summary embeddings** that make abstract retrieval possible.

Today's pass2_writer writes flat `:Entity`/`:Relation`/`:Event`/`:Fact` nodes anchored only by `chapter_id`. There is no scene-level granularity, no hierarchy, no level summaries. ADR §3 T4 + T7 stage 1 specifies the missing pieces.

## 2. Scope

In scope (one XL cycle):

1. **NEW Python tree-merge module** `app/extraction/tree_merge.py` — deterministic merge bottom-up (scene → chapter → part → book) using canonical_id-keyed entity merge + alias union-find (Tarjan UF) + relation merge by `(subject_canonical_id, predicate, object_canonical_id, polarity)` + event merge by `(name_norm, time_cue)`.
2. **NEW Neo4j hierarchy nodes** `:Scene` / `:Chapter` / `:Part` / `:Book` + `:HAS_CHILD` edges + `:MENTIONED_IN` edges from existing `:Entity`/`:Relation`/`:Event`/`:Fact` to their parent hierarchy node.
3. **NEW Python writer extension** `app/extraction/hierarchy_writer.py` — writes hierarchy nodes + edges in one Cypher Tx after tree_merge completes; idempotent via `MERGE` on `path` strings.
4. **NEW async summary-job** `app/jobs/summary_processor.py` — consumes `extraction.summarize` Redis Stream messages; for each `(chapter_id|part_id|book_id, level)`: load child summaries + entities from Neo4j → call LLM for 2-3 sentence summary → embed → write to summary_chapters / summary_parts / summary_books tables + Neo4j vector index.
5. **NEW Postgres tables** for summary persistence (alongside Neo4j vectors for query):
   - `summary_chapters(chapter_id, summary_text, summary_text_md5, embedding_dim, embedding_model_uuid, generated_at)`
   - `summary_parts(part_id, ...)`, `summary_books(book_id, ...)`.
6. **NEW Neo4j vector indexes**: `chapter_summary_emb`, `part_summary_emb`, `book_summary_emb` (one per level, separate from the existing `:Passage` index per PO choice 4).
7. **EXTEND `pass2_orchestrator.extract_pass2_chapter`** — after writing per-chapter Pass2WriteResult, enqueue a `summary.chapter` message for this chapter. Final chapter of a book also enqueues `summary.part` (for each part) and `summary.book` messages.
8. **EXTEND `pass2_writer.write_pass2_extraction`** — call `hierarchy_writer.upsert_hierarchy_nodes(scene/chapter/part/book paths)` BEFORE writing entities; entity/relation/event/fact get `:MENTIONED_IN` edge to their `:Scene` (or `:Chapter` for legacy NULL-structural_path).
9. **NEW Mode-3 retrieval router extension** `app/context/selectors/passages.py` (or new selector) — when Mode-3 query is "abstract" intent (heuristic: query length > 20 tokens OR no proper-noun match in glossary), prioritize chapter/part/book summary indexes; "specific" intent uses scene-passage index (existing). NEW per-level vector queries via the new Neo4j indexes.
10. **NEW migration runner** for the 3 Postgres summary tables + Neo4j schema bootstrap (3 vector indexes + hierarchy node labels). Idempotent re-run.
11. **NEW `loreweave_extraction.summarize` extractor** — LLM prompt template for 2-3 sentence summary per level (chapter/part/book). Uses same gateway pattern as the 4 existing extractors but returns a single string (not list of candidates).
12. **Tests** — tree_merge unit (8-10 tests including 50-MB-projection-sample sanity), hierarchy_writer unit (5-6 tests), summary_processor unit (4-5 tests), Mode-3 router intent classification + multi-index query (4-5 tests).

Out of scope (P-FUTURE):
- P4 semantic chunking escape valve.
- P5 gated LLM coreference + verify + multi-resolution retrieval router refinement.
- Re-running existing graphs through P3 (per PO choice 3: no backfill).
- Summary regeneration on entity-add (incremental summary update is a follow-up).
- Per-scene summary embedding (only chapter/part/book; per-scene is the existing `:Passage` index).

## 3. Design decisions

### D1 — Tree-merge algorithm: deterministic Python (hybrid per PO choice 1)

**Input:** per-scene `Pass2Candidates` (entities + relations + events + facts) — same shape as existing pass2 output, but now keyed by scene_id instead of chapter_id.

**Output:** hierarchical KG dict structured as:

```python
@dataclass
class HierarchicalKG:
    book: BookKG                  # canonical entity dedup across whole book
    parts: list[PartKG]           # per-part canonical view
    chapters: list[ChapterKG]     # per-chapter canonical view (one per chapter)
    scenes: list[SceneKG]         # per-scene as input (passthrough)
    canonical_id_map: dict[str, str]   # alias -> canonical_id after union-find
```

**Merge algorithm (bottom-up):**

```python
def tree_merge(scenes: list[SceneKG]) -> HierarchicalKG:
    # 1. Group scenes by chapter_id.
    # 2. For each chapter: merge scene KGs into ChapterKG.
    # 3. Group chapters by part_id.
    # 4. For each part: merge chapter KGs into PartKG.
    # 5. Merge all parts into BookKG.
    # Each merge step uses:
    #   - Entity merge by canonical_id (already deterministic from
    #     canonicalize_entity_name).
    #   - Alias union-find (Tarjan UF): two entities with >=2 shared
    #     aliases -> same canonical group. Bridges name variants the
    #     canonicalizer missed.
    #   - Relation merge by (subject_canonical_id, predicate,
    #     object_canonical_id, polarity) — extended to use POST-merge
    #     canonical IDs.
    #   - Event merge by (name_norm, time_cue) (existing).
```

**Why deterministic + Python:**
- Mirrors existing pass2_writer logic (callers reason about candidates as Python dicts/Pydantic; tree_merge is the next pure-Python step).
- All merge logic is testable in isolation without Neo4j (huge test coverage win).
- Tarjan union-find implementation is ~50 lines; well-understood.

**H2 fix — memory pressure realistic + chunked merge strategy:**

Recomputing realistic memory for 50MB novel:
- 250k entities × ~400 bytes Python dict (name + canonical_name + canonical_id + kind + aliases list × 5 × 15-char strings + dict overhead) = ~100MB raw
- 1.25M relations (5 per entity) × ~300 bytes (with evidence arrays) = ~370MB
- 250k events × ~250 bytes = ~60MB
- 250k facts × similar = ~60MB
- Plus intermediate dict copies during merge + union-find structures: ~1.5-2× multiplier
- **Realistic total: 1-1.5GB** for a single in-process whole-book merge

Worker-ai containers typically have 1-2GB memory limit. Whole-book in-memory merge **WILL OOM on 50MB novel.**

**Locked strategy — chunked merge with per-chapter persistence:**

```python
async def tree_merge_chunked(book_id: UUID, ...) -> None:
    # 1. For each chapter (one at a time):
    #    a. Load scene KGs for THIS chapter only (from extraction_leaves).
    #    b. _merge_scene_kgs(scene_kgs) -> ChapterKG (in memory, small).
    #    c. hierarchy_writer writes :Chapter + :Scene nodes + entity :MENTIONED_IN
    #       edges for THIS chapter to Neo4j.
    #    d. Free Python memory before next chapter.
    # 2. For each part (one at a time):
    #    a. Load Chapter KG summaries (NOT raw candidates) from Postgres
    #       summary_chapters table (~500 bytes per chapter × 50 chapters = 25KB).
    #    b. _merge_chapter_kgs (cheap — already deduped at chapter level).
    #    c. hierarchy_writer writes :Part node + edges.
    # 3. For book:
    #    a. Load Part KG summaries from summary_parts table.
    #    b. _merge_part_kgs.
    #    c. hierarchy_writer writes :Book node + edges.
```

**Memory peak: per-chapter merge only.** For typical 50-scene chapter × 20 entities = 1000 entities × ~400 bytes = 400KB. Negligible. Largest chapter (sherlock-class, 17 chunks × 50 entities = 850 entities) = 340KB. Safe.

**Trade-off:** Part- and book-level merges only see SUMMARIES not raw entity sets — so cross-chapter entity coreference at part/book level is limited to what summaries surface. R-ACCEPTED: per spec ADR §3 T5 (gated LLM refinement), cross-section coreference is a separate P5 concern. P3 tree-merge correctness is bounded by per-chapter deduplication; cross-chapter dedup via global canonical_id_map happens at pass2_writer time (existing K11 logic). Document in §6 R1.

**File `D-P3-WHOLE-BOOK-MERGE-FOR-COREF`** if/when cross-chapter coreference at merge time becomes needed.

**Per-scene-merge details:**

```python
def _merge_scene_kgs(scene_kgs: list[SceneKG], parent_path: str) -> ChapterKG:
    # 1. Collect all entities; build canonical_id_map via alias UF.
    all_entities = []
    for sk in scene_kgs:
        all_entities.extend(sk.entities)
    canonical_map = _alias_union_find(all_entities)

    # 2. Re-key entities by canonical_id_map; merge duplicates.
    merged_entities = {}  # canonical_id -> Entity
    for e in all_entities:
        cid = canonical_map.get(e.canonical_id, e.canonical_id)
        if cid in merged_entities:
            merged_entities[cid] = _merge_entity_pair(merged_entities[cid], e)
        else:
            merged_entities[cid] = e

    # 3. Re-key relations using canonical_id_map; dedup by composite key.
    seen_relations = set()
    merged_relations = []
    for sk in scene_kgs:
        for r in sk.relations:
            subj_cid = canonical_map.get(r.subject_canonical_id, r.subject_canonical_id)
            obj_cid = canonical_map.get(r.object_canonical_id, r.object_canonical_id)
            key = (subj_cid, r.predicate, obj_cid, r.polarity)
            if key not in seen_relations:
                seen_relations.add(key)
                merged_relations.append(dataclasses.replace(
                    r, subject_canonical_id=subj_cid, object_canonical_id=obj_cid,
                ))

    # 4. Events: dedup by (name_norm, time_cue); merge first_chronological_index.
    # 5. Facts: dedup by (subject_canonical_id, attribute, value).
    return ChapterKG(...)
```

### D2 — Neo4j hierarchy schema (SR-1 fix: correct existing edge pattern)

NEW node labels: `:Scene`, `:Chapter`, `:Part`, `:Book`. NEW edge type: `:HAS_CHILD` (hierarchy parent→child).

**SR-1 correction (post-self-review):** existing extraction does NOT use `:MENTIONED_IN`. Real pattern (verified in `app/db/neo4j_repos/entities.py:1817` `_MERGE_REWIRE_EVIDENCED_BY_CYPHER`): `:Entity-[:EVIDENCED_BY {job_id}]->:ExtractionSource`. The `:ExtractionSource` node carries `source_type` (`chapter`/`chat_turn`) + `source_id` (chapter UUID) — provenance keyed by extraction-job.

P3 adds an ORTHOGONAL edge for hierarchy location (NOT modifying the existing provenance edge):

```
:Entity-[:EVIDENCED_BY {job_id}]->:ExtractionSource    # EXISTING (provenance — unchanged)
:Entity-[:MENTIONED_IN]->:Scene                         # NEW (hierarchy location, P3 only)
                                                        # OR :Chapter for legacy fallback
```

Rationale: provenance and hierarchy are different concerns. An entity may be mentioned in multiple scenes (multiple `:MENTIONED_IN` edges, one per scene); its `:EVIDENCED_BY` carries WHICH extraction-job produced the candidate. Keeping them separate preserves the existing query patterns + adds the hierarchy traversal path.

**Memory cost:** ~2× edge count per entity. For a 50MB novel with 10k entities each in avg 5 scenes = 50k new `:MENTIONED_IN` edges. Acceptable.

**Schema (added to `neo4j_schema.py` bootstrap):**

```cypher
// Hierarchy nodes — all use natural keys (path strings; deterministic from P1).
CREATE CONSTRAINT scene_path_unique IF NOT EXISTS
  FOR (s:Scene) REQUIRE s.path IS UNIQUE;
CREATE CONSTRAINT chapter_path_unique IF NOT EXISTS
  FOR (c:Chapter) REQUIRE c.path IS UNIQUE;
CREATE CONSTRAINT part_path_unique IF NOT EXISTS
  FOR (p:Part) REQUIRE p.path IS UNIQUE;
CREATE CONSTRAINT book_path_unique IF NOT EXISTS
  FOR (b:Book) REQUIRE b.path IS UNIQUE;
```

**SR-2 + H1 + M7 fix — per-project + per-embedding-model vector indexes:**

knowledge-service allows per-project embedding_model (K12.4 picker — bge-m3=1024 / text-embedding-3=1536 / etc.). Neo4j vector indexes are dimension-LOCKED at creation. Single global index per level = forces all projects to one dimension = breaks the picker contract.

**Naming (M7 fix — no collision risk):** use FULL dash-stripped project UUID + dash-stripped embedding_model_uuid. **H1 fix — namespace by embedding_model UUID** so changing model creates a NEW index family; old family is orphaned + can be pruned at user-triggered cleanup (NOT auto-deleted to preserve queryability of historic runs).

```
chapter_summary_emb_p<32hex>_e<32hex>
part_summary_emb_p<32hex>_e<32hex>
book_summary_emb_p<32hex>_e<32hex>
```

Where `<32hex>` is the dash-stripped UUID. Neo4j supports long index names. Zero collision.

**Index lifecycle:**
- **Create**: on first extraction of a project AT that embedding_model. The `extraction-job-processor` lazily calls `ensure_summary_indexes(project_id, embedding_model_uuid, embedding_dimension)` before writing the first summary.
- **Idempotent**: `CREATE VECTOR INDEX IF NOT EXISTS` — safe to call every job start.
- **NOT auto-dropped on embedding_model change**: per H1 reasoning, old index family is queryable for historic data. User can prune via NEW `POST /internal/extraction/prune-summary-indexes/{project_id}` admin endpoint (deferred — file `D-P3-INDEX-PRUNE-ENDPOINT`).
- **D-EMB-MODEL-REF-04 destructive endpoint** (graph delete): the existing endpoint already deletes the project's Neo4j data; extend to drop the project's old summary indexes too OR document that orphaned indexes remain (preferred — index drop is cheap, defer if not requested).

**Cypher bootstrap:**

```cypher
CREATE VECTOR INDEX $idx_name IF NOT EXISTS
  FOR (n:Chapter) ON (n.summary_embedding)
  OPTIONS {
    indexConfig: {
      `vector.dimensions`: $dim,
      `vector.similarity_function`: 'cosine'
    }
  };
```

`$idx_name` is safely templated by knowledge-service Python (Cypher doesn't support index name in `$` substitution); regex `^[a-z_0-9]+$` validation before interpolation prevents injection.

NEW abstractions in `app/db/neo4j_helpers.py`:
- `summary_index_name(project_id: UUID, embedding_model_uuid: str, level: Literal["chapter","part","book"]) -> str`
- `ensure_summary_indexes(session, project_id, embedding_model_uuid, embedding_dimension) -> None` (idempotent)

**Hierarchy write (idempotent MERGE on `path`):**

```cypher
MERGE (b:Book {path: $book_path})
  SET b.book_id = $book_id, b.title = $book_title
MERGE (p:Part {path: $part_path})
  SET p.book_id = $book_id, p.part_index = $part_idx
MERGE (b)-[:HAS_CHILD]->(p)
MERGE (c:Chapter {path: $chapter_path})
  SET c.book_id = $book_id, c.chapter_id = $chapter_id, c.chapter_index = $chapter_idx
MERGE (p)-[:HAS_CHILD]->(c)
// For each scene:
MERGE (s:Scene {path: $scene_path})
  SET s.book_id = $book_id, s.scene_id = $scene_id, s.scene_index = $scene_idx
MERGE (c)-[:HAS_CHILD]->(s)
```

**Entity-to-hierarchy linkage (extends existing `:MENTIONED_IN`):**

```cypher
// When writing each :Entity/:Relation/:Event/:Fact:
MATCH (s:Scene {path: $scene_path})  // OR fallback chapter for legacy
MERGE (e:Entity ...)
MERGE (e)-[:MENTIONED_IN]->(s)
```

Legacy fallback (NO backfill per PO choice 3): when scene_path is NULL (chapter from pre-P1), use chapter_path target. The Cypher just substitutes the MATCH target.

### D2a — Tx boundary for hierarchy_writer + pass2_writer (M2 fix)

The 3-stage pipeline (tree_merge → hierarchy_writer → pass2_writer) must be transactionally consistent: partial failure leaves orphan `:Scene/:Chapter` nodes with no `:Entity` children → Mode-3 retrieval returns useless nodes.

**Locked Tx boundary (per chapter):**

```python
# pass2_orchestrator._run_pipeline (after entities extracted, before write):
async with session.begin_transaction() as tx:
    # 1. hierarchy_writer.upsert_for_chapter — MERGE :Book/:Part/:Chapter/:Scene
    #    + :HAS_CHILD edges (idempotent, fast).
    await hierarchy_writer.upsert_for_chapter(tx, book_id, chapter_id, scenes_paths)
    # 2. pass2_writer.write_pass2_extraction — writes :Entity/:Relation/:Event/:Fact
    #    + :MENTIONED_IN -> :Scene edges (existing logic + extended target).
    write_result = await pass2_writer.write_pass2_extraction(tx, ...)
    # Tx commits ONLY if both stages succeed.
```

**Failure semantics:**
- tree_merge raises → no Tx opened, no Neo4j writes, extraction-job marked failed (existing behavior).
- hierarchy_writer raises mid-Tx → Tx rolls back, NO :Scene/:Chapter/:Entity writes (clean).
- pass2_writer raises mid-Tx → Tx rolls back, no :Scene/:Entity writes (clean — :Scene from prior chapters in this job's earlier per-chapter Tx survive, by design — chapter-grain partial success preserved per P1 R-SELF-2).

**Note:** existing pass2_writer wraps a per-chapter Cypher Tx already. P3 extension threads hierarchy_writer INTO that same Tx — minor refactor, single-file change in pass2_writer.

### D3 — Async summary-job (PO choice 2)

**Trigger:** `pass2_orchestrator.extract_pass2_chapter` enqueues a `summary.chapter` message to the existing Redis Stream (NEW stream `extraction.summarize`) after writing per-chapter Pass2WriteResult AND before returning success. When the orchestrator processes the FINAL chapter of a book (heuristic: extraction-job carries chapter list, last one triggers), ALSO enqueue `summary.part` for each part + `summary.book`.

**Stream message shape:**

```python
class SummarizeMessage(BaseModel):
    level: Literal["chapter", "part", "book"]
    node_path: str           # "book/part-1/chapter-3"
    user_id: UUID
    project_id: UUID
    book_id: UUID
    job_id: UUID             # ties summary back to extraction job for FE display
    model_ref: str           # which LLM model to summarize with (same as extraction)
    embedding_model_uuid: str  # which embedding model (from knowledge_projects)
```

**Consumer (`worker-ai/app/jobs/summary_processor.py`):**

```python
async def process_summarize_message(msg: SummarizeMessage) -> SummaryWriteResult:
    # 1. Load child summaries (or scene leaf_texts for chapter level) via Neo4j.
    #    chapter -> all :Scene children's leaf_text (joined)
    #    part    -> all :Chapter children's summary_text (joined)
    #    book    -> all :Part children's summary_text (joined)
    # 2. Load entity list at this level via Neo4j (for prompt context).
    # 3. Call summarize_level extractor (NEW in loreweave_extraction):
    #    LLM prompt = "Summarize this <level> content + key entities in 2-3 sentences."
    # 4. Embed the summary via embedding_client (same model as the project's
    #    embedding_dimension/embedding_model).
    # 5. Persist to Postgres summary_chapters/parts/books table AND
    #    SET the hierarchy node's summary_text + summary_embedding in Neo4j.
```

**Stream design:**
- Stream: `extraction.summarize`
- Consumer group: `worker-ai-summary`
- Single consumer per worker-ai process (matches existing pattern).
- Retry budget per message: 2 (same as P2 leaf retry).
- Failure: leaf-style mark in NEW `summary_jobs` table (or reuse `extraction_jobs` with kind discriminator).

**M1 fix — extraction_jobs state machine adds `summarizing` transition:**

Current `extraction_jobs.status` enum: `('pending','running','completed','failed')`. NEW intermediate state: `('pending','running','summarizing','completed','failed')`.

State transitions:
- `running` → `summarizing` when last chapter's pass2_writer commits + last summary message enqueued.
- `summarizing` → `completed` when `summary_books` row is written (book-level summary = final summary).
- `summarizing` → `failed` if summary retry budget exhausted for any chapter/part/book level (per ADR's accept-partial-failure stance; or stay `summarizing` indefinitely with FE messaging — see L1 deferred row).

FE field: existing `extraction_jobs.status` field surfaces the new state; FE displays it as "Building summaries..." progress message. NEW migration: extend the CHECK constraint on `extraction_jobs.status`.

**M4 fix — re-enqueue mechanism: XADD with `retry_at` field:**

When defensive check at part/book level finds children not ready (per D9), the consumer:
1. XACKs the current message (so consumer-group offset advances).
2. XADDs a NEW message to the SAME `extraction.summarize` stream with:
   - `retry_at = now() + INTERVAL '30 seconds'` (configurable via env `LOREWEAVE_SUMMARY_REENQUEUE_BACKOFF_S=30`).
   - `retried_n` counter (for retry budget at the message level).
3. Consumer reads incoming messages and checks `retry_at` — if in the future, XACK + XADD (re-enqueue) without processing. Cheap server-side check.
4. Backoff caps at exponential 30s/60s/120s; after 3 re-enqueues, mark `summary_jobs.status='abandoned'` (book-level summary missing for this run — Mode-3 returns no summary for this level; user-recoverable via Rebuild Graph).

**M5 fix — summary_processor catches UniqueViolationError gracefully:**

Two concurrent extraction jobs on same book (PO accepted per P2 OQ-P2-3) both write `summary_chapters` → second hits `UNIQUE (chapter_id, embedding_model_uuid)`. Wrapper:

```python
try:
    await pool.execute(
        "INSERT INTO summary_chapters (...) VALUES (...)",
        ...,
    )
except asyncpg.UniqueViolationError:
    # Another concurrent job wrote this summary first. Verify their
    # summary_input_md5 matches ours; if yes, treat as cache-equivalent
    # (do nothing). If no, log warning + skip (their content may differ
    # due to race; ours would have been identical given same md5 input).
    existing = await pool.fetchrow(
        "SELECT summary_input_md5 FROM summary_chapters WHERE chapter_id=$1 AND embedding_model_uuid=$2",
        chapter_id, embedding_model_uuid,
    )
    if existing and existing["summary_input_md5"] == our_md5:
        return  # cache-equivalent — no-op
    logger.warning(
        "summary_chapters md5 mismatch on UniqueViolation: chapter=%s",
        chapter_id,
    )
    return  # accept the race winner's write
```

Same pattern for `summary_parts` and `summary_books`.

### D4 — Postgres summary tables

```sql
CREATE TABLE IF NOT EXISTS summary_chapters (
  id                   UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id           UUID NOT NULL,                    -- no FK (cross-DB)
  book_id              UUID NOT NULL,
  summary_text         TEXT NOT NULL,
  summary_input_md5    TEXT NOT NULL,                    -- C1+SR-4: md5 of (joined_child_texts + level + extractor_version + model_ref)
  embedding_dimension  INT  NOT NULL,
  embedding_model_uuid TEXT NOT NULL,                    -- provider-registry user_model UUID
  generated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (chapter_id, embedding_model_uuid)
);

CREATE TABLE IF NOT EXISTS summary_parts (
  id                   UUID PRIMARY KEY DEFAULT uuidv7(),
  part_id              UUID NOT NULL,
  book_id              UUID NOT NULL,
  summary_text         TEXT NOT NULL,
  summary_input_md5    TEXT NOT NULL,                    -- C1+SR-4 (same as chapters)
  embedding_dimension  INT  NOT NULL,
  embedding_model_uuid TEXT NOT NULL,
  generated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (part_id, embedding_model_uuid)
);

CREATE TABLE IF NOT EXISTS summary_books (
  id                   UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id              UUID NOT NULL,
  summary_text         TEXT NOT NULL,
  summary_input_md5    TEXT NOT NULL,                    -- C1+SR-4 (same as chapters)
  embedding_dimension  INT  NOT NULL,
  embedding_model_uuid TEXT NOT NULL,
  generated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (book_id, embedding_model_uuid)
);
```

**Why duplicate Postgres + Neo4j storage:** Postgres = audit trail + summary_text_md5 for cache idempotency (re-run skips if text unchanged); Neo4j = vector index for retrieval. Both updated atomically inside the summary_processor.

### D5 — Mode-3 retrieval router extension

Current Mode-3 (`app/context/modes/full.py`) queries the `:Passage` vector index. P3 extension: when query intent is "abstract" (heuristic), ALSO query chapter_summary_emb + part_summary_emb + book_summary_emb in parallel, blend results by score.

**Intent classification (cheap heuristic):**

```python
def is_abstract_query(query: str, glossary_entities: set[str]) -> bool:
    """Cheap heuristic — saves LLM intent classification.

    - Query > 20 tokens AND no proper-noun matches glossary -> abstract.
    - Query contains "summary", "overview", "theme", "arc", "plot" -> abstract.
    - Query contains a proper-noun matching glossary -> specific.
    - Default: specific (preserves existing behavior).
    """
```

**Retrieval flow:**

```python
async def select_l3_passages(query: str, ...) -> list[PassageContext]:
    query_emb = await embed(query)
    intent = classify_intent(query, glossary_entities)

    if intent == "specific":
        # Existing path: query :Passage index.
        return await _query_passage_index(query_emb, ...)
    else:  # abstract
        # NEW: query 3 summary indexes in parallel; blend.
        scene_results, chapter_results, part_results, book_results = await asyncio.gather(
            _query_passage_index(query_emb, ...),
            _query_chapter_summary_index(query_emb, ...),
            _query_part_summary_index(query_emb, ...),
            _query_book_summary_index(query_emb, ...),
        )
        return _blend_multi_level_results(
            scene_results, chapter_results, part_results, book_results,
            weights={"scene": 0.3, "chapter": 0.3, "part": 0.2, "book": 0.2},
        )
```

### D6 — No-backfill semantics (PO choice 3) — corrected per SR-1 + M6

**SR-1 correction**: existing extraction does NOT use `:MENTIONED_IN`. It uses `:Entity-[:EVIDENCED_BY]->:ExtractionSource` for provenance (per `app/db/neo4j_repos/entities.py:1817`).

NEW P3 extractions ADD:
- `:Scene`/`:Chapter`/`:Part`/`:Book` hierarchy nodes + `:HAS_CHILD` edges
- `:Entity-[:MENTIONED_IN]->:Scene` (or `:Chapter` for legacy chapters per P1 fallback)

while PRESERVING `:Entity-[:EVIDENCED_BY]->:ExtractionSource` (untouched).

**M6 fix — mixed-state per chapter is expected post-P3 re-extraction:**

A single chapter MAY have entities in 2 states post P3:
- **Legacy entities** (written pre-P3): only `:EVIDENCED_BY → :ExtractionSource` edge. No `:MENTIONED_IN`.
- **NEW entities** (written post-P3): both `:EVIDENCED_BY → :ExtractionSource` AND `:MENTIONED_IN → :Scene` edges.

This happens when:
- A chapter was originally extracted pre-P3 (flat entities).
- User triggers re-extraction post-P3 → P2 cache hit on most leaves (no new entity rows) BUT NEW :Scene + :Chapter hierarchy nodes are created with the chapter's pre-existing flat entities NOT linked to :Scene (cache hit returns cached candidates which write existing entities idempotently via MERGE — but the :MENTIONED_IN edge IS NEW so it gets added).

**Mode-3 retrieval handles BOTH shapes:** the `:Passage` index queries returns existing flat passages (unchanged); summary-index queries return rows that exist; entity-traversal queries use `OPTIONAL MATCH (e)-[:MENTIONED_IN]->(s:Scene)` so legacy entities surface with `s=null`.

**Mixed-state semantic is acceptable**: Mode-3 falls through gracefully, and the eventual `Rebuild Graph` operation (user-triggered) re-extracts everything fresh with consistent hierarchy. Documented as P-FUTURE `D-P3-MIXED-STATE-CONSOLIDATION` if FE wants a one-click cleanup.

### D7 — `loreweave_extraction.summarize_level` extractor

NEW extractor follows the same gateway pattern as the 4 existing (entity/relation/event/fact). Difference: returns a single Pydantic model, not a list:

```python
# L3 fix: relax Pydantic max_length to 2000; writer truncates to 500
# at persistence time. Memory `feedback_llm_schema_tolerate_filter_dont_reject`
# — strict schemas on LLM output cause permanent failures for valid-but-
# slightly-long responses. Tolerate at validation, filter at postprocess.
class LevelSummary(BaseModel):
    summary_text: str = Field(min_length=20, max_length=2000)
    token_usage: dict  # for billing audit

async def summarize_level(
    *,
    level: Literal["chapter", "part", "book"],
    child_texts: list[str],     # joined scene leaf_texts (chapter) or child summaries (part/book)
    entity_names: list[str],     # 5-20 top entities at this level
    user_id: str, project_id: str,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    llm_client: LLMClient,
) -> LevelSummary:
    """LLM-generated 2-3 sentence summary."""
```

**Prompt template** (`sdks/python/loreweave_extraction/prompts/summarize_level.md`):

```
You are summarizing a <level> of a book.

Key entities (must mention if relevant):
{entity_names}

Content:
{child_texts (truncated to 8000 chars)}

Write a 2-3 sentence summary capturing the central themes, characters,
and arc of this <level>. Do NOT list events sequentially; synthesize.

Respond with JSON: {"summary_text": "..."}
```

**Cache integration:** summary_processor checks `summary_chapters.summary_text_md5` before LLM call — if md5(joined child texts) matches existing row, skip LLM. P2 lessons applied.

**SR-4 + M3 fix — per-op extractor versions:**

Same pattern as P2 task_id. Prompt template edit at `sdks/python/loreweave_extraction/prompts/summarize_level.md` MUST invalidate the summary cache implicitly. BUT M3 finding: P2 task_id currently uses `loreweave_extraction.__extractor_version__` = sha256 of ALL prompts. Adding `summarize_level.md` means editing summary prompt would ALSO invalidate ALL P2 caches — opposite of what's wanted.

**Locked: introduce per-op extractor versions in SDK (extension of P2 `_version.py`):**

```python
# sdks/python/loreweave_extraction/_version.py — EXTENDED

# Mapping op -> which prompt files contribute to its version hash.
# P2 task_id MUST use op-specific version (each leaf op has its own
# prompt file); summary_processor uses summarize_level prompt only.
_OP_PROMPTS: dict[str, list[str]] = {
    "entity": ["entity_extraction.md"],
    "relation": ["relation_extraction.md"],
    "event": ["event_extraction.md"],
    "fact": ["fact_extraction.md"],
    "summarize_level": ["summarize_level.md"],
}

def get_extractor_version(op: str | None = None) -> str:
    """Return per-op extractor version hash.

    op=None (legacy) -> hashes ALL prompts (kept for backwards-compat
    with P2 callers that pre-date this extension).
    op=<op_name>    -> hashes ONLY that op's prompt files; bumps
                       independently of other ops.
    """
    if op is None:
        # P2 back-compat path; eventually deprecate after P2 migrates.
        return _compute_extractor_version()  # full-prompts hash
    if op not in _OP_PROMPTS:
        raise ValueError(f"unknown op: {op!r}")
    files = sorted(_OP_PROMPTS[op])
    h = hashlib.sha256()
    for fname in files:
        path = _PROMPTS_DIR / fname
        h.update(fname.encode("utf-8"))
        h.update(b"\x1f")
        h.update(path.read_bytes() if path.exists() else b"")
    return f"v1-{op}-{h.hexdigest()[:8]}"
```

**Migration plan:**
- Extending `get_extractor_version(op=None)` keeps P2 working AS-IS (no cache thrash from this change alone).
- Filed `D-P2-MIGRATE-TO-PER-OP-EXTRACTOR-VERSION` as a P2 polish — when P2's compute_task_id is updated to pass its op, task_ids change once (one cache rebuild) but future prompt edits only invalidate that op.
- P3 summary_processor uses `get_extractor_version(op="summarize_level")` from day 1.

**md5 input becomes:**

```python
md5_input = (
    f"{joined_child_texts}\x1f{level}\x1f"
    f"{get_extractor_version(op='summarize_level')}\x1f{model_ref}"
)
summary_input_md5 = hashlib.md5(md5_input.encode("utf-8"), usedforsecurity=False).hexdigest()
```

**Column renamed**: `summary_input_md5` (it's the input hash, not the output).

### D8 — `:HAS_CHILD` edge direction + idempotency

Direction: parent → child (`book HAS_CHILD part HAS_CHILD chapter HAS_CHILD scene`). Idempotency via `MERGE` on the natural-key path string. Re-running extraction = MERGE returns existing nodes/edges (no duplicates).

### D9 — Final-chapter-of-book detection (SR-3 fix: defensive check)

`pass2_orchestrator.extract_pass2_chapter` needs to know if THIS chapter is the FINAL one in the book to enqueue part/book summary jobs. Two options:
- (a) Caller supplies `is_last_chapter: bool` (extraction-job runner already iterates chapters; knows the answer).
- (b) Orchestrator queries `chapters WHERE book_id = ? AND sort_order > ?` — if zero, this is the last.

**Locked (a)**: cleaner separation; runner already has the iteration context.

**SR-3 fix — defensive check at consumer side:** caller could be wrong (e.g., chapters processed in parallel, "is_last" arrives before all earlier chapters committed). Summary processor for `part`/`book` levels MUST verify ALL children are present before generating the summary:

```python
async def process_part_summary(msg: SummarizeMessage) -> None:
    # Defensive: verify all chapters of this part have summary_chapters rows.
    expected_chapter_count = await neo4j_count_children(msg.node_path, level="chapter")
    actual_count = await postgres_count_summary_rows(part_id=msg.part_id, level="chapter")
    if actual_count < expected_chapter_count:
        logger.info(
            "part summary deferred: %d/%d chapter summaries present",
            actual_count, expected_chapter_count,
        )
        return  # re-enqueue via Stream pending retry budget; idempotent
    # ... proceed with summary generation
```

Same defensive check at book level. This makes the caller flag a HINT, not a hard precondition.

### D10 — Re-run / re-summarize semantics

When user re-triggers extraction on the same book (via "Rebuild Graph"): P2 cache hits avoid LLM extraction calls; P3 should similarly avoid LLM summary calls when content unchanged. Mechanism: `summary_text_md5` cache check. Re-run path:

```
re-extraction job:
  for each chapter:
    pass2_orchestrator.extract_pass2_chapter (P2 cache hits everywhere)
    write Pass2WriteResult (idempotent MERGE)
    enqueue summary.chapter message
  on final chapter:
    enqueue summary.part × N + summary.book

summary_processor receives messages:
  for each summarize message:
    compute new_md5 = md5(joined child texts)
    if summary_<level> row exists AND row.summary_text_md5 == new_md5:
      SKIP (no LLM, no embedding)
    else:
      call summarize_level + embed + persist
```

This makes re-run cheap. Aligns with P2's cache philosophy.

---

## 4. Test plan

### 4.1 Tree-merge unit (`tests/unit/test_tree_merge.py`)

| Test | What |
|---|---|
| `test_alias_union_find_merges_two_entities_with_2_shared_aliases` | Tarjan UF correctness |
| `test_entity_merge_uses_post_uf_canonical_id` | After UF, relation/event re-key uses post-UF ids |
| `test_relation_dedup_by_composite_key` | (subj, pred, obj, polarity) dedup |
| `test_event_dedup_by_name_norm_time_cue` | Event merge |
| `test_fact_dedup_by_subject_attribute_value` | Fact merge |
| `test_scene_to_chapter_aggregation_preserves_all_unique_entities` | Bottom-up aggregation |
| `test_chapter_to_part_aggregation_dedup_across_chapters` | One Entity across 2 chapters → 1 in PartKG |
| `test_book_kg_is_global_dedup` | Final BookKG has each canonical_id at most once |
| `test_legacy_chapter_no_scenes_uses_chapter_path_directly` | Fallback when scenes empty |
| `test_50_chapter_book_merge_completes_under_5s` | Perf sanity (in-process Python) |

### 4.2 Hierarchy writer unit (`tests/unit/test_hierarchy_writer.py`)

| Test | What |
|---|---|
| `test_upsert_book_part_chapter_scene_creates_4_levels` | MERGE chain via mocked CypherSession |
| `test_has_child_edges_correct_direction` | parent → child |
| `test_idempotent_re_run_no_duplicate_nodes_or_edges` | MERGE on path |
| `test_legacy_chapter_no_scene_uses_chapter_target_for_mentioned_in` | D6 fallback path |
| `test_entity_mentioned_in_scene_when_scene_path_present` | NEW write path |

### 4.3 Summary processor unit (`tests/unit/test_summary_processor.py`)

| Test | What |
|---|---|
| `test_processor_calls_summarize_extractor_with_joined_children` | LLM prompt input |
| `test_md5_cache_hit_skips_llm_call` | D10 re-run cheapness |
| `test_persist_to_postgres_and_neo4j_atomic` | Both writes inside one session.run |
| `test_chapter_level_loads_scene_leaf_texts` | Level-specific child loading |
| `test_part_level_loads_chapter_summaries` | Level-specific aggregation |

### 4.4 Mode-3 router unit (`tests/unit/test_mode3_intent_classification.py`)

| Test | What |
|---|---|
| `test_intent_classifier_specific_on_glossary_proper_noun` | "what did Holmes say" → specific |
| `test_intent_classifier_abstract_on_long_question_no_proper_noun` | "what are the central themes?" → abstract |
| `test_intent_classifier_abstract_on_overview_keyword` | "summary of chapter 5" → abstract |
| `test_abstract_query_blends_4_level_results` | Multi-index gather |
| `test_specific_query_only_queries_passage_index` | Back-compat |

### 4.5 Extractor unit (`sdks/python/tests/test_extraction/test_summarize_level.py`)

| Test | What |
|---|---|
| `test_summarize_level_returns_2_to_3_sentence_summary` | Output format |
| `test_summarize_level_includes_entity_names_in_prompt` | Prompt construction |
| `test_summarize_level_truncates_content_to_8000_chars` | Long-input bound |

### 4.6 Live smoke (cross-service)

Per CLAUDE.md cross-service evidence rule (knowledge-service + worker-ai + book-service + neo4j → 4 services):

1. `docker compose up -d` after Neo4j schema bootstrap migration runs.
2. Trigger extraction on a 3-chapter test book (re-use the P1+P2 smoke fixture pattern).
3. Assert:
   - `extraction_leaves` rows present (P2).
   - Neo4j `:Book`, `:Part`, `:Chapter`, `:Scene` nodes created with `:HAS_CHILD` edges.
   - `:Entity` nodes have `:MENTIONED_IN` edges to `:Scene` (not `:ChapterAnchor`).
   - `summary_chapters` row exists for each chapter post-extraction.
   - `chapter_summary_emb` Neo4j vector index contains entries.
4. Re-trigger extraction: assert summary_text_md5 cache hits → no new LLM call → 0 new rows.
5. Mode-3 abstract query (e.g. "themes of this book") returns blended results from summary indexes.

Evidence token: `live smoke: 3-chapter book → hierarchy nodes + per-chapter summary + chapter_summary_emb populated → re-run shows md5 cache hits`.

## 5. Acceptance criteria (ADR §7 P3 mapped)

- [ ] Tree-merge produces book-level KG identical (modulo summary nodes) to running each leaf's KG through existing flat dedup → §4.1 test_book_kg_is_global_dedup + integration test.
- [ ] Neo4j hierarchy nodes (`:Scene` / `:Chapter` / `:Part` / `:Book`) with `:HAS_CHILD` edges → §4.2 + live smoke §4.6.
- [ ] Per-chapter/part/book summary embeddings stored → §4.3 + live smoke.
- [ ] LLM-judge baseline ≥ session-61 P=0.97 R=0.81 on 9 golden chapters (no regression) → DEFERRED to post-build run (P3 doesn't change extraction prompts; should be a no-regression check).
- [ ] `sherlock_speckled_band` joins the baseline (no longer skipped) and meets P ≥ 0.85 R ≥ 0.70 → DEFERRED to post-build full eval run.

## 6. Risks + mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | In-process tree_merge for 50MB / 12.5k scenes / 250k entities may pressure memory | ~50MB process memory (entity ~200 bytes × 250k). Test perf at §4.1 test_50_chapter_book_merge_completes_under_5s with a synthetic large fixture. |
| R2 | Tarjan UF correctness on edge cases (entity with N aliases shared with M others) | Comprehensive unit tests in §4.1. Reference impl widely documented. |
| R3 | Neo4j vector index per level (×3 NEW indexes) doubles index maintenance load | Acceptable — Neo4j's HNSW handles many indexes efficiently. Worth flagging if observed slow at scale. |
| R4 | Async summary-job means user sees "graph done, summaries pending" UX state | FE shows extraction status "completed" + new field "summaries: building/ready"; ~5 min latency for 50-chapter book. Acceptable for first-pass. |
| R5 | Final-chapter detection by caller-supplied `is_last_chapter` could be wrong (caller bug) | Defensive: summary_processor for `part`/`book` levels checks if all children have summaries before enqueueing; if not, no-op. |
| R6 | re-run with prompt template change (extractor_version bumps) - summary md5 still matches but LLM output would differ | Add `extractor_version` to summary_text_md5 input (hash includes extractor_version). Same pattern as P2 task_id. |
| R7 | NO-BACKFILL means Mode-3 retrieval has 2 shapes long-term | Document explicitly in Mode-3 router code; if/when backfill becomes desirable, file P-FUTURE-HIERARCHY-BACKFILL row. |
| R8 | summary_processor crashes mid-batch → some summaries missing | Stream + retry pattern (same as P2 leaf retry budget). After exhaustion, summary row stays missing; Mode-3 retrieval gracefully returns no summary results for that level. |

## 7. Locked design decisions (post-CLARIFY)

- **Tree-merge = HYBRID** (deterministic Python merge + Neo4j-side schema writes).
- **Summary = ASYNC** (separate summary-job consumer).
- **Backward-compat = NO BACKFILL** (existing flat graphs untouched; Mode-3 handles both shapes).
- **Summary storage = SEPARATE Neo4j vector indexes per level** (chapter_summary_emb, part_summary_emb, book_summary_emb).
- **D9 final-chapter detection: caller-supplied `is_last_chapter` flag.**
- **D10 re-run idempotency: summary_text_md5 cache hit skips LLM.**

---

## 8. Out-of-scope + deferred rows

**Out-of-scope (P-FUTURE):**
- P4 semantic chunking escape valve.
- P5 gated LLM coreference + verify.
- Mode-3 retrieval router refinement beyond intent classification (ColBERT late-interaction is P5).
- Per-scene summary embedding (only chapter/part/book; per-scene is :Passage existing).
- Summary regeneration on partial entity-add (full re-summary on re-extraction only).

**Deferred rows to file at SESSION (post-BUILD):**
- `D-P3-LIVE-SMOKE` — full extraction + hierarchy + summary live smoke once BUILD ships.
- `D-P3-LLM-JUDGE-BASELINE-CHECK` — verify session-61 P=0.97 R=0.81 baseline maintained post-P3.
- `D-P3-SHERLOCK-BASELINE` — sherlock_speckled_band joins baseline with cache (P2 + P3 enable it).
- `D-P3-HIERARCHY-BACKFILL` (P-FUTURE) — if users request backfill for legacy graphs.
- `D-P3-SUMMARY-REGEN-ON-CHANGE` (P-FUTURE) — incremental summary update on entity-add.

**Round-1 /review-impl deferred rows (from session 64):**
- `D-P3-WHOLE-BOOK-MERGE-FOR-COREF` (H2 follow-up) — when cross-chapter coreference at merge time becomes needed (currently bounded by per-chapter dedup + global canonical_id_map at pass2_writer).
- `D-P3-INDEX-PRUNE-ENDPOINT` (H1 follow-up) — admin endpoint to drop orphaned per-(project, embedding-model) vector indexes.
- `D-P2-MIGRATE-TO-PER-OP-EXTRACTOR-VERSION` (M3 follow-up) — migrate P2 task_id to per-op extractor version (one-time cache rebuild; future prompt edits invalidate only the relevant op).
- `D-P3-INTENT-CLASSIFIER-GLOSSARY-METRIC` (L1) — Prometheus counter for glossary-unavailable degradation in Mode-3 intent classifier.
- `D-P3-LEGACY-BOOK-ABSTRACT-FALLBACK` (L2) — FE UX surface for "abstract queries require re-extraction" on legacy books.
- `D-P3-MIXED-STATE-CONSOLIDATION` (M6 follow-up) — one-click cleanup if user wants consistent hierarchy on chapters with mixed legacy/new entity state.

## 9. Review trail

### Self-review (all 4 findings folded inline)

- **SR-1 (HIGH)** — D2 used non-existent edge name `:MENTIONED_IN`. Verified real pattern in `app/db/neo4j_repos/entities.py:1817`: `:Entity-[:EVIDENCED_BY {job_id}]->:ExtractionSource`. **Fix:** D2 documents the orthogonal-edges approach (preserve `:EVIDENCED_BY` for provenance; ADD `:MENTIONED_IN -> :Scene` for hierarchy). 2× edge count acceptable.
- **SR-2 (HIGH)** — D2 single global vector index per level breaks K12.4 per-project embedding picker (dimension mismatch). **Fix:** D2 added per-project, per-level vector indexes with naming `<level>_summary_emb_<short_project_id>` (matches K17.9 passage convention). NEW `summary_index_name()` helper in `neo4j_helpers.py`.
- **SR-3 (MED)** — D9 caller-supplied `is_last_chapter` could be wrong on parallel chapter processing. **Fix:** D9 documents defensive check at summary_processor (verify expected_chapter_count == actual rows before generating part/book summary; re-enqueue if not ready).
- **SR-4 (MED)** — D10 md5 cache doesn't invalidate on prompt template edit. **Fix:** D7+D10 include `summarize_extractor_version` in md5 input (renamed column to `summary_input_md5`); reuses P2's `loreweave_extraction.__extractor_version__` constant.

### /review-impl round 1 (10 fix-now folded inline; 2 LOW filed as deferred rows)

- **H1 (HIGH)** — Per-project index lifecycle on embedding_model change. **Fix:** D2 namespaces indexes by `(project_id, embedding_model_uuid)`; old families orphaned + pruned via admin endpoint (filed `D-P3-INDEX-PRUNE-ENDPOINT`).
- **H2 (HIGH)** — Tree-merge memory estimate wrong by 5-10×; would OOM on 50MB. **Fix:** D1 locked chunked merge with per-chapter persistence; whole-book in-memory deferred via `D-P3-WHOLE-BOOK-MERGE-FOR-COREF`.
- **M1 (MED)** — extraction_jobs state machine missing intermediate state. **Fix:** D3 adds `summarizing` status.
- **M2 (MED)** — Partial-failure Tx boundary unaddressed. **Fix:** NEW D2a section locks `hierarchy_writer + pass2_writer` in one Cypher Tx per chapter.
- **M3 (MED)** — Global `__extractor_version__` thrash. **Fix:** D7 SR-4 extended with per-op `get_extractor_version(op=...)` in SDK; P2 migration filed as `D-P2-MIGRATE-TO-PER-OP-EXTRACTOR-VERSION`.
- **M4 (MED)** — Re-enqueue mechanism unspecified. **Fix:** D3 locks XADD with `retry_at` + exponential backoff (30/60/120s) + abandoned after 3 retries.
- **M5 (MED)** — Concurrent extraction race on summary UNIQUE. **Fix:** D3 catches `UniqueViolationError`, verifies md5 match, treats as cache-equivalent.
- **M6 (MED)** — Mixed-state per chapter undocumented. **Fix:** D6 explicit note + `D-P3-MIXED-STATE-CONSOLIDATION` deferred for one-click cleanup.
- **M7 (MED)** — Index naming collision risk. **Fix:** D2 uses FULL dash-stripped UUID `p<32hex>_e<32hex>` — zero collision.
- **L1 (LOW)** — Glossary intent-classifier degradation. **Filed:** `D-P3-INTENT-CLASSIFIER-GLOSSARY-METRIC`.
- **L2 (LOW)** — Legacy graphs abstract-query UX gap. **Filed:** `D-P3-LEGACY-BOOK-ABSTRACT-FALLBACK`.
- **L3 (LOW)** — Pydantic max_length=500 may reject valid summaries. **Fix:** D7 relaxes to max_length=2000; writer truncates to 500.
- **C1 (COSMETIC)** — md5 column name inconsistency. **Fix:** D4 + D10 use `summary_input_md5` consistently.

### POST-REVIEW: pending
