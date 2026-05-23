# Spec — P2 Parallel Map + Checkpoint (hierarchical extraction T3)

> **Status:** DESIGN 2026-05-23. XL task (14 files, 7 logic, 1 side-effect = knowledge-service Postgres schema). Branch `main`.
> **Workflow:** v2.2 default. `/review-impl` invoked at REVIEW (design) per `feedback_review_impl_on_design_cycles`.
> **Parent ADR:** [`docs/03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md`](../03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md) §3 T3 + §6 P2 + §7 P2 acceptance.
> **P1 precondition:** [`docs/specs/2026-05-23-p1-structural-decomposer.md`](2026-05-23-p1-structural-decomposer.md) — `parts`/`scenes` tables + tree-shape contract. **P2 fallback contract from P1 D2 MUST be honored** (legacy chapters w/o scenes → fall back to `chapter_drafts.body`).
> **CLARIFY answers (PO, locked session 62):**
>   1. Cache shape — **2 tables** (`extraction_leaves` hot candidates + `extraction_leaves_raw` cold full response).
>   2. Invalidation — **explicit DELETE** on parse_version bump (NEW invalidation endpoint).
>   3. Worker placement — **extend knowledge-service `worker-ai`** (Python; existing service).
>   4. Glossary anchor failure — **hard fail leaf 502** (no degrade).

---

## 1. Problem

Per ADR §1: extraction can't scale to 50MB+ novels. P1 broke documents into `parts→chapters→scenes`; P2 makes each scene's per-op extraction **parallel + idempotent + resumable**. Today's `pass2_orchestrator._run_pipeline` processes ONE chapter at a time, gathering `relations/events/facts` in parallel (`asyncio.gather`) but with no persistent checkpoint. A 17-chunk chapter (`sherlock_speckled_band`) hangs the LM Studio target under sustained load; a 50MB novel = 12,500 scenes × 4 ops = 50,000 LLM calls of ~30s each = unattainable without checkpoint + restart.

P2 lays the **checkpoint layer** (Postgres `extraction_leaves` + `extraction_leaves_raw`) and the **per-leaf parallel dispatcher** that the existing extractors plug into. T4 (P3 hierarchical reduce) consumes the per-leaf candidates; that's the next phase.

## 2. Scope

In scope (one XL cycle):

1. **NEW knowledge-service Postgres tables**: `extraction_leaves` (hot — candidates_jsonb, status, retry, timing, parse_version, extractor_version) + `extraction_leaves_raw` (cold — full raw response keyed by extraction_leaf FK).
2. **NEW `app/db/repositories/extraction_leaves.py`** — `claim_pending`, `mark_completed`, `mark_failed`, `fetch_cached(task_id)`, `delete_by_book` (invalidation).
3. **NEW `app/jobs/leaf_processor.py`** — per-leaf consumer for the worker-ai DAG: fetch scene, build task_id, check cache, fetch glossary anchor (per-chapter, hard-fail), call extractor, persist candidates + raw.
4. **NEW `POST /internal/extraction/invalidate-cache/{book_id}`** — admin endpoint to DELETE all extraction_leaves rows for a book (called on parse_version bump or extractor_version drift).
5. **NEW `extractor_version` constant** in `loreweave_extraction` SDK — derived from prompt-file hashes; surfaced to P2 for invalidation triggers (per OQ-P2-4 resolution).
6. **REFACTOR `pass2_orchestrator._run_pipeline`** — replace inline chapter→`asyncio.gather` with: (a) fetch scenes via NEW `BookClient.list_scenes_by_chapter(chapter_id)` (HTTP, NOT cross-DB — per CLAUDE.md SSOT rule), (b) on empty-scenes (legacy chapter): fall back via NEW `BookClient.get_chapter_draft_text(chapter_id)` returning plain-text projection of `chapter_drafts.body`, (c) async fanout in-process per scene×op via asyncio.Semaphore (no Redis Stream — see SR-3 in D3), (d) aggregate per-leaf candidates back into the existing `Pass2Candidates` shape.
7. **NEW book-service `GET /internal/books/{book_id}/chapters/{chapter_id}/scenes`** — list active scenes for one chapter, returns `[{id, sort_order, path, leaf_text, content_hash, parse_version}]`. Plus repo method + handler.
8. **NEW book-service `GET /internal/books/{book_id}/chapters/{chapter_id}/draft-text`** — plain-text projection of `chapter_drafts.body` (Tiptap JSON → text via walk-and-concat). Used by P2 legacy-chapter fallback (D8). Plus repo method + handler + a `tiptap_json_to_text` pure helper (mirror of P1's `html_to_leaf_text`).
9. **NEW knowledge-service `app/clients/book_client.py` methods**: `list_scenes_by_chapter(chapter_id)` + `get_chapter_draft_text(chapter_id)`.
10. **NEW `KnowledgeProject.save_raw_extraction: bool = False`** column on `knowledge_projects` — opt-in for raw cache writes (OQ-P2-1 resolution).
11. **EXTEND `glossary_client.list_entities`** to pass `before_chapter_index` + `recency_window` + `limit` params (OQ-P2-2 resolution: per-chapter filtering already supported BE-side, just unwire the client args).
12. **In-worker LRU cache for glossary anchor responses** — keyed by `(book_id, chapter_index_bucket)` with TTL = duration of one extraction job (OQ-P2-2 resolution).
13. **Tests** — schema regression-lock, repo unit, leaf_processor unit (with mocked LLM + glossary), invalidation endpoint, refactored pass2_orchestrator integration, contract test that cache-hit path skips LLM call, NEW book-service endpoint tests (scenes + draft-text).

Out of scope (parent ADR phases later):
- T4 hierarchical reduce / tree-merge (P3 — separate cycle).
- Per-level summaries + Neo4j `:Scene`/`:Chapter`/`:Part`/`:Book` labels (P3).
- Semantic chunking escape valve (P4).
- Gated LLM coreference + multi-resolution retrieval (P5).
- Cross-book P2 (P2 is per-book-job; cross-book caching via content_hash works naturally via the unique index).

## 3. Design decisions

### D1 — 2-table cache (hot candidates + cold raw)

**knowledge-service Postgres schema additions:**

```sql
-- ── P2 (hierarchical extraction T3) — per-leaf checkpoint ────────────

CREATE TABLE IF NOT EXISTS extraction_leaves (
  id                 UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id            UUID NOT NULL,                    -- no FK (cross-DB to book-service)
  scene_id           UUID NOT NULL,                    -- no FK (cross-DB)
  leaf_path          TEXT NOT NULL,                    -- "book/part-1/chapter-3/scene-2"
  op                 TEXT NOT NULL CHECK (op IN ('entity','relation','event','fact')),
  task_id            TEXT NOT NULL,                    -- sha256(normalized_leaf_text + op + extractor_version)

  status             TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','running','completed','failed')),
  candidates_jsonb   JSONB,                            -- post-processed LLMxxxCandidate list; null until completed
  retried_n          INT  NOT NULL DEFAULT 0,
  error_message      TEXT,

  parse_version      INT  NOT NULL DEFAULT 1,          -- mirrors scenes.parse_version at write time
  extractor_version  TEXT NOT NULL,                    -- loreweave_extraction.__extractor_version__
  model_ref          TEXT NOT NULL,                    -- SR-2 fix: provider-registry user_model UUID used for THIS row's LLM call
  glossary_anchor_size INT,                            -- count of known_entities used; null if no anchor needed

  started_at         TIMESTAMPTZ,
  completed_at       TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE (book_id, leaf_path, op)     -- composite uniqueness: 1 row per leaf×op
);

CREATE INDEX IF NOT EXISTS idx_extraction_leaves_task_id ON extraction_leaves(task_id);
CREATE INDEX IF NOT EXISTS idx_extraction_leaves_pending
  ON extraction_leaves(book_id, status) WHERE status IN ('pending','running');
CREATE INDEX IF NOT EXISTS idx_extraction_leaves_book ON extraction_leaves(book_id);

-- Cold raw response: opt-in via knowledge_projects.save_raw_extraction
CREATE TABLE IF NOT EXISTS extraction_leaves_raw (
  extraction_leaf_id UUID PRIMARY KEY REFERENCES extraction_leaves(id) ON DELETE CASCADE,
  raw_response_jsonb JSONB NOT NULL,                   -- full gateway response incl. usage + reasoning
  raw_token_usage    JSONB NOT NULL,                   -- {input, output, reasoning}
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE knowledge_projects ADD COLUMN IF NOT EXISTS save_raw_extraction BOOLEAN NOT NULL DEFAULT false;
```

**Why the split:**
- **Hot (`extraction_leaves`):** read on every cache hit; small (~5-20KB candidates jsonb). Indexed by `task_id` for O(1) cache lookups.
- **Cold (`extraction_leaves_raw`):** opt-in. Only written when `knowledge_projects.save_raw_extraction = TRUE`. Cascades on DELETE so invalidation is atomic. Per OQ-P2-1: storage grows linearly; opt-in keeps the default tenant lean.
- **`task_id` includes `extractor_version` but NOT `parse_version`:** per PO choice 2, parse_version changes trigger explicit DELETE (no auto-invalidate via composite hash). extractor_version is hashed in because prompt template changes invalidate the cache implicitly.

**Cross-DB FK absence:** `book_id` / `scene_id` reference book-service DB; no FK by design (matches knowledge-service convention — see `knowledge_projects.book_id` comment in `migrate.py`).

### D2 — Task ID algorithm (SR-2 + SR-4 fix: include `model_ref`; document hash/explicit asymmetry)

```python
def compute_task_id(
    normalized_text: str,
    op: str,
    extractor_version: str,
    model_ref: str,
) -> str:
    """Deterministic per-leaf-per-op-per-model key.

    Input normalization (M2 fix from /review-impl round 1):
      - `normalized_text`: pre-normalized via canonicalize_text (NFC + collapse-ws + lower).
      - `op`: lowered via .lower() — defensive against caller variance.
      - `extractor_version`: as-is (SDK constant, already canonical).
      - `model_ref`: lowered via .lower() — UUID strings can arrive in either
        case from different serializers; case-sensitive hash would silently
        cache-miss for what should be a hit.

    Properties:
      - Same content + op + prompts + model -> same hash -> cache hit.
      - Prompt template change -> extractor_version bumps -> hash changes
        -> implicit invalidation via cache miss.
      - Different LLM model (qwen3.6 vs gemma-4) -> different hash ->
        no cross-model cache poisoning (SR-2 fix).
      - scenes.parse_version is INTENTIONALLY NOT IN THE HASH (SR-4):
        per PO choice 2, parse_version bumps use EXPLICIT DELETE via
        /internal/extraction/invalidate-cache/{book_id} (D5). This
        asymmetry — extractor_version in hash, parse_version out of
        hash — is by design: prompt edits are dev-triggered (frequent,
        small), re-parses are user/admin-triggered (rare, large
        blast radius). Hashing parse_version would silently churn
        the entire cache on a re-parse; explicit invalidation makes
        the operation visible.
    """
    op_norm = op.lower()
    model_norm = model_ref.lower()
    payload = f"{normalized_text}\x1f{op_norm}\x1f{extractor_version}\x1f{model_norm}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

**Regression-lock test** (§4.3): `test_task_id_case_insensitive_model_ref` — assert `compute_task_id(t, "entity", v, "019DC3DF-...")` == `compute_task_id(t, "entity", v, "019dc3df-...")`.

**`model_ref` source:** the `user_model` UUID of the extraction LLM passed at job start (matches `provider_client.submit_job(model_ref=...)`). Each extraction job carries its own `model_ref`; the leaf processor receives it as part of the per-leaf task message and uses it for both the LLM call AND the task_id.

**Normalisation** (matches existing `loreweave_extraction.canonical.canonicalize_text`): NFC unicode + collapse whitespace runs + lowercase.

**Cross-book cache hit semantics:** if Book A and Book B share a verbatim scene AND use the same `model_ref` AND same `extractor_version`, the second book's extraction reuses the first's candidates. **Acceptable** — the extraction is content+model+prompts-determined, no book-level context in the prompt.

### D3 — In-process async fanout in `worker-ai` (SR-3 fix: drop Redis Stream)

**Architecture (SR-3: simplified — no Redis Stream for P2):**

```
existing worker-ai consumers:
- extraction-job-processor  (per-CHAPTER, kept; the orchestrator entry)

P2 internal change: extraction-job-processor's _run_pipeline now uses
in-process asyncio.Queue + Semaphore-bounded workers to fan out per
scene×op. NO new Redis Stream + NO new consumer group.

Refactored pass2_orchestrator._run_pipeline(chapter, model_ref, parent_job_id):
  scenes = await fetch_scenes(chapter_id) or [virtual_scene_from_drafts]
  glossary_anchor = await glossary_anchor_lru.get(book_id, chapter_index)
  if glossary_anchor is None:
    raise GlossaryAnchorUnavailable   # hard-fail per PO choice 4

  # M4 fix: pre-dispatch dedup. Build the SET of unique (task_id, payload)
  # pairs BEFORE creating asyncio tasks — prevents same-text-different-scene
  # races from issuing 2× LLM calls for one task_id.
  unique_tasks: dict[str, tuple[Scene, str]] = {}  # task_id -> (scene, op)
  scene_op_to_task_id: dict[tuple[UUID, str], str] = {}  # so we can aggregate back
  for scene in scenes:
    for op in ("entity", "relation", "event", "fact"):
      task_id = compute_task_id(scene.leaf_text, op, extractor_version, model_ref)
      scene_op_to_task_id[(scene.id, op)] = task_id
      unique_tasks.setdefault(task_id, (scene, op))

  semaphore = asyncio.Semaphore(LM_STUDIO_MAX_CONCURRENT)
  task_results: dict[str, list] = {}
  async def _run(task_id: str, scene: Scene, op: str):
    task_results[task_id] = await _process_leaf(
      semaphore, scene, op, task_id, glossary_anchor, model_ref, parent_job_id,
    )
  await asyncio.gather(
    *(asyncio.create_task(_run(tid, sc, op)) for tid, (sc, op) in unique_tasks.items()),
    return_exceptions=True,
  )
  # Aggregate back: for each (scene, op), look up its task_id's candidates.
  candidates = aggregate_by_scene_op(scenes, scene_op_to_task_id, task_results)
  return candidates

_process_leaf(sem, scene, op, task_id, anchor, model_ref, parent_job_id):
  cached = await repo.fetch_cached(task_id)
  if cached:
    return cached.candidates_jsonb     # NO LLM CALL, NO SEMAPHORE, NO billing reserve
  async with sem:
    # H1 fix (billing integration): per-leaf LLM calls use the parent
    # chapter-job's reservation. The extractor passes parent_job_id;
    # gateway accumulates per-leaf cost against the existing reservation
    # and the chapter-level settle handles the final actual_cost_usd write.
    raw = await llm_extractor.extract_op(
      scene.leaf_text, op, anchor, model_ref,
      parent_job_id=parent_job_id,   # billing pass-through
    )
    candidates = postprocess(raw, op)
    await repo.persist(task_id, scene, op, candidates, raw, extractor_version, model_ref)
    return candidates
```

**Why no Redis Stream:**
- The DB checkpoint table `extraction_leaves` IS the durability mechanism (status='completed' rows survive worker crashes; restart skips them via task_id cache hit).
- worker-ai is one Python process; orchestrator + leaf-processor share an event loop. Redis would just be inter-coroutine plumbing — pure overhead.
- Multi-worker scale-out (when needed) reuses the SAME DB checkpoint via the existing `extraction-job-processor` Redis Stream consumer group (one chapter = one Redis message = one process handles its leaves locally). The grain stays per-chapter at the Redis layer; per-leaf is async-local.

**Concurrency (M1 fix — two levels, orthogonal):**
- **Per-chapter (intra-chapter)**: `asyncio.Semaphore(LM_STUDIO_MAX_CONCURRENT)` (env-tunable, default 4 per session 59 D-PRED-ALIGN-DEF-03). Bounds simultaneous LLM calls for ONE chapter's leaves. Cache hits skip the semaphore entirely.
- **Per-book (inter-chapter)**: number of worker-ai replicas × per-replica chapter-job consumer concurrency. Today: 1 worker-ai replica consumes the `extraction.chapter` Redis Stream with a single consumer; chapters run serially. To match ADR §5 wall-clock estimates (24h for 50MB) chapter-level concurrency MUST also scale. **P2 scope keeps default = 1 replica × 1 chapter at a time** (matches today's behavior; per-leaf parallelism is the P2 unlock). Multi-replica scale-out is a deploy-time concern; the DB checkpoint table naturally serialises via UNIQUE constraint when multiple replicas pick the same chapter from the Stream (one wins, others skip via claim conflict).
- **Implication for ADR §5 estimates**: 50MB @ ~30s/leaf with parallelism=4 INTRA-chapter = ~24h chapter-serialised. To hit ADR §5's faster estimate, deploy N worker-ai replicas reading from the Redis Stream (consumer group serialisation handles chapter assignment).
- **Documented out-of-scope for P2 code change**: no replica scale-up; no Redis Stream changes; the per-chapter concurrency mechanism stays as-is at the Stream consumer layer.

**Stale-claim recovery (D9 expanded — see L5 fix in D9):** since there is no Redis ack, worker-ai startup scans `extraction_leaves WHERE status='running' AND started_at < now() - INTERVAL '30 minutes'` and resets to `'pending'`. The next leaf task that hits the same `task_id` will see `pending` + claim it. Acceptable: a stale row only blocks RE-EXTRACTION of that exact leaf for ≤30 min; new leaves proceed unaffected.

**Rejected:** new `extraction-worker` service. Adds Dockerfile + compose + OTel for one consumer — over-engineering at P2 scale. PO confirmed.

#### D3a — Billing integration (H1 fix)

The existing per-chapter `extraction_job` lifecycle (`/v1/llm/jobs` reserve → settle) is the budget gate users rely on. P2's per-leaf LLM calls MUST plug into the SAME reservation, NOT create new per-leaf reservations.

**Contract:**
- `pass2_orchestrator._run_pipeline(chapter, model_ref, parent_job_id)` accepts the `parent_job_id` from the extraction-job-processor's reserve call (already passed today; we just thread it deeper).
- `_process_leaf` passes `parent_job_id` to the extractor's gateway call. Gateway accumulates per-leaf input/output tokens against the parent reservation.
- Per-chapter settle (existing) calls `/v1/llm/jobs/{parent_job_id}/settle` with total accumulated usage → writes `extraction_jobs.actual_cost_usd` once per chapter (NOT per leaf — avoids 4N billing writes per chapter).
- **Cache hits do NOT consume the reservation** (no LLM call → no token spend → no settle adjustment).
- **Settle on partial failure**: if some leaves succeed + some fail (e.g., 90 of 100 completed + 10 stuck pending), settle uses partial usage. Existing behavior; no change.

**Why not per-leaf reserve:** 4 ops × ~10 scenes/chapter = 40 reservations per chapter. Provider-registry's `/v1/llm/jobs` is ~50ms HTTP call → 2s of reserve-overhead per chapter. Per-chapter reserve = 1 HTTP call. PO budget-gate semantics preserved (budget checked once per chapter; chapter is the atomic budget unit).

**Edge case — runaway leaf:** if one chapter's leaves blow through the reserved budget (long scene → unexpectedly many tokens), gateway returns 402 on the over-budget leaf. Other leaves in flight continue (parallelism doesn't observe). Settle records actual usage; user sees over-budget chapter in audit but no hard cutoff mid-chapter. **Document as P-LEAF-BUDGET-CUTOFF deferred row** if this becomes a real concern.

### D4 — Glossary anchor: per-chapter, hard-fail, in-worker LRU

**Fetch contract** (extend existing `glossary_client.list_entities`):

```python
async def list_known_entities(
    self,
    book_id: UUID,
    *,
    before_chapter_index: int,
    recency_window: int = 100,
    min_frequency: int = 2,
    limit: int = 50,
) -> list[dict]:
    """GET /internal/books/{book_id}/known-entities with chapter-position filters.

    P2 hard-fail contract (PO choice 4):
      - HTTP 200 + list -> return list
      - HTTP 5xx OR timeout -> raise GlossaryAnchorUnavailable
        (caller marks the leaf failed; retry budget applies)
      - HTTP 4xx (e.g. invalid book_id) -> raise GlossaryAnchorMalformed
        (no retry; surface as job error)
    """
```

**LRU cache** (in-worker, per-process, never cleared — M3+M5 fixes):

```python
class GlossaryAnchorCache:
    """LRU keyed strictly by (book_id, chapter_index) — NO bucketing.

    M3 fix (dropped bucketing): chapter_index // 5 introduced precision
    loss (chapter 4 and chapter 6 would share an anchor despite different
    recency windows) AND caused boundary spikes (5/6 same bucket, 9/10
    different). Strict per-chapter keys are precise + simpler. Glossary
    endpoint is cheap (indexed Go query) — premature optimization risk.

    M5 fix (cache lifetime): per-process, never cleared. Glossary anchor
    is read-only within an extraction run. Staleness across jobs (user
    adds a glossary entry mid-extraction) is bounded by the slowly-
    changing nature of glossary; acceptable trade-off vs the complexity
    of per-job TTL tracking. Concurrent extraction jobs on the same book
    share the cache (read-only, no race).

    Max size = 1000 entries (caps memory at ~50KB anchor × 1000 = 50MB
    process memory — fits comfortably).

    Eviction: standard LRU.
    """
```

**Hard-fail semantics:**
- Job start: explicit health-check probe to glossary `/health` → if 5xx, fail-fast the WHOLE extraction job with `GLOSSARY_UNAVAILABLE` error. Don't waste retries.
- Per-leaf: if `list_known_entities` raises `GlossaryAnchorUnavailable`, mark the leaf `failed` with `error_message = "glossary anchor unavailable"`. Retry budget (default 2) applies. After exhaustion, leaf stays failed; P3 reduce ignores it.
- **PO accepted trade-off:** brief glossary outage = paused extraction. Surface clearly in job status so the user knows to wait + retry.

### D5 — Invalidation endpoint (H2 fix: explicit two-step counts; L3 op-filter caveat)

```
POST /internal/extraction/invalidate-cache/{book_id}
  Headers: X-Internal-Token
  Query (optional):
    op=entity|relation|event|fact  (default: all 4 ops)
  Response 200: {
    "deleted_leaves": <int>,
    "deleted_raw": <int>,
    "book_id": <uuid>,
    "invalidated_ops": ["entity", "relation", "event", "fact"]
  }
  Response 401/404 standard.
```

**H2 fix — accurate counts via two-step CTE in a single Tx:**

```sql
WITH
  target AS (
    SELECT id FROM extraction_leaves
    WHERE book_id = $1 AND op = ANY($2)
  ),
  del_raw AS (
    DELETE FROM extraction_leaves_raw
    WHERE extraction_leaf_id IN (SELECT id FROM target)
    RETURNING 1
  ),
  del_leaves AS (
    DELETE FROM extraction_leaves
    WHERE id IN (SELECT id FROM target)
    RETURNING 1
  )
SELECT
  (SELECT count(*) FROM del_raw)::int    AS deleted_raw,
  (SELECT count(*) FROM del_leaves)::int  AS deleted_leaves;
```

The `target` CTE materialises the row set ONCE; both DELETEs reference the same set. Raw deletes happen FIRST (explicit; not relying on CASCADE for the count). Single Tx, all-or-nothing.

**Why NOT rely on CASCADE for `deleted_raw`:** Postgres `DELETE … RETURNING` returns ONLY the rows from the directly-deleted table. CASCADE-deleted children don't appear in RETURNING. The two-step CTE pattern is the standard fix when caller needs both counts.

**Triggers (caller responsibilities, NOT auto):**
- After P3's structural re-parse bumps `scenes.parse_version`, the re-parse code must call this endpoint.
- After `loreweave_extraction.__extractor_version__` changes (prompt template edit), an admin / migration must call this endpoint per affected project. Could be batched via a CLI helper `python -m app.cli invalidate-all-extraction-cache`.
- Frontend "Rebuild Graph" button can call this endpoint to force a clean re-extraction.

**Idempotent:** running twice on the same book = second call returns `deleted_leaves: 0` (rows already gone).

**L3 — op-filter dependency caveat:** invalidating ONLY one op (e.g., `?op=entity`) leaves relation/event/fact rows that reference entity `canonical_id`s which may now be stale. P3 (hierarchical reduce) is when this surfaces — relation rows pointing at canonical_ids no longer in the entity layer. **For P2 this is cosmetic** (P2 doesn't reduce; per-leaf candidates are independent). **Document at P3 design**: P3 reduce step must validate FK-shape integrity OR force full-op-set invalidation. Caller-side mitigation: prefer no `op` filter (full clear) unless specifically debugging a single op.

### D6 — Raw retention: opt-in per project (OQ-P2-1)

`knowledge_projects.save_raw_extraction BOOLEAN DEFAULT FALSE`. Frontend exposes this as a toggle in the project settings (NEW UI element — defer to a follow-up FE cycle). For P2, the column exists + the leaf_processor honors it; FE wire-up is OUT OF SCOPE.

**Default OFF** because:
- Most users don't need raw responses; they want the graph.
- Raw storage = ~50KB/leaf × 12,500 leaves = ~600MB per 50MB novel. Multi-tenant scale matters.
- Power users (re-judge, debug, A/B prompt variants) can opt-in per project.

### D7 — `extractor_version` constant in SDK

```python
# sdks/python/loreweave_extraction/_version.py
"""Extractor version derived from prompt file hashes.

Computed at import time from sha256 of the concatenated prompts/*.md
files (sorted by filename). Any prompt edit -> hash changes ->
task_id changes -> cache miss -> fresh LLM call.

Format: "v1-<8-hex-chars>" — readable enough to debug, short enough
for grep.
"""
import hashlib
from pathlib import Path

def _compute_extractor_version() -> str:
    prompts_dir = Path(__file__).parent / "prompts"
    md_files = sorted(prompts_dir.glob("*.md"))
    h = hashlib.sha256()
    for f in md_files:
        h.update(f.read_bytes())
    return f"v1-{h.hexdigest()[:8]}"

__extractor_version__ = _compute_extractor_version()
```

Exported from `__init__.py`. Imported by P2 leaf_processor for task_id computation.

**Implication for invalidation:** any agent editing `sdks/python/loreweave_extraction/prompts/*.md` MUST also call the invalidation endpoint (or rely on natural cache miss on next-extraction). Document in the prompts README.

**L1 fix — dev hot-reload caveat:** the version is computed once at module-import time. In production (containerised, no hot reload) the SDK is loaded with the prompt files as they appear at image-build time → version is correct + immutable. **In dev with hot-reload**, editing a prompt file and not restarting the worker-ai means the new prompt content is used but `__extractor_version__` still reflects the OLD hash → silent cache poisoning (cache hit on stale candidates). **Mitigation**: support env var `LOREWEAVE_EXTRACTOR_VERSION_DEV_RECOMPUTE=1` that bypasses the module-level constant and recomputes on every `compute_task_id` call. Off by default (cheap module attribute access in prod); explicit opt-in for dev. Document in the SDK README + the prompts dir's README.

### D8 — P1 fallback contract enforcement (M6 from P1 DESIGN)

P2 leaf_processor MUST handle the legacy-chapter case:

```python
async def fetch_scenes(chapter_id: UUID) -> list[Scene]:
    scenes = await book_client.list_active_scenes(chapter_id)
    if not scenes:
        # Legacy chapter (P1 R-SELF-1: NULL structural_path) — no
        # P1 decomposition. Build one virtual scene from chapter_drafts.body.
        body = await book_client.get_chapter_draft_text(chapter_id)
        if not body:
            return []  # truly empty chapter — skip
        virtual = Scene(
            sort_order=1,
            path=f"legacy/chapter-{chapter_id}/scene-1",
            leaf_text=body,
            content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            parse_version=0,  # 0 = legacy sentinel
        )
        return [virtual]
    return scenes
```

**Tests must lock this branch.** Memory `feedback_validate_dead_code_before_picking_smallest_caller` warns about dead-code traps; the legacy fallback IS a live code path until all chapters are re-parsed.

`book_client.get_chapter_draft_text` is NEW — extracts plain text from Tiptap JSON (`chapter_drafts.body`). Mirror algorithm: walk `content[]` recursively, concatenate `text` properties. Pure helper, deterministic.

### D9 — Resume-on-restart semantics

- Worker-ai startup: scan `extraction_leaves WHERE status='running' AND started_at < now() - INTERVAL '30 minutes'` → reset to `'pending'` (stale-claim recovery). Document the 30-min ceiling as P-FUTURE tunable.
- Per-extraction-job: skip leaves with `status='completed'` (cache hit by `task_id`). Re-enqueue leaves with `status='failed' AND retried_n < retry_budget`. Skip leaves with `status='failed' AND retried_n >= retry_budget`.
- DB connection drop mid-task: claim is leased; next worker picks up via stale-claim recovery above. **Note:** Tx atomicity guarantees `status='completed' + candidates_jsonb populated` is all-or-nothing.

**L5 fix — multi-replica startup idempotency:** stale-claim recovery's UPDATE uses `WHERE status='running' AND started_at < now() - INTERVAL '30 minutes'`. If 2+ worker-ai replicas start simultaneously, both run the same UPDATE — the second sees zero matching rows (status flipped to 'pending' by the first). No race. Idempotent across multi-replica startup. **Caveat:** a long-running legit LLM call ≥30min would be reset prematurely; the original task continues to completion + INSERT-ON-CONFLICT-DO-NOTHING discards. Wasted work, no corruption (R6 in §6 covers this).

### D10 — Observability

OTel spans:
- `extraction.leaf_dispatch` (per scene): attrs `book_id`, `scene_id`, `parse_version`, `op_count` (4), `cache_hits` (0-4), `glossary_anchor_size`.
- `extraction.leaf_process` (per leaf-op): attrs `task_id`, `op`, `status`, `retried_n`, `llm_call_made` (bool), `glossary_anchor_size`.

Prometheus counters (new):
- `extraction_leaves_total{op,status}` — per-op outcome counter.
- `extraction_leaves_cache_hits_total{op}` — cache-hit counter.
- `extraction_leaves_glossary_unavailable_total` — hard-fail counter (alert when > 0).
- `extraction_leaves_retry_exhausted_total{op}` — leaf abandonment counter.

Histograms:
- `extraction_leaf_duration_seconds{op}` — per-leaf wall time (LLM call + write).
- `extraction_leaf_glossary_fetch_seconds` — glossary anchor fetch latency.

---

## 4. Test plan

### 4.1 Schema regression-lock (`tests/unit/test_migrate_p2.py`)

| Test | What |
|---|---|
| `test_extraction_leaves_table_present` | After migrate, table exists with all 14 columns + unique constraint `(book_id, leaf_path, op)` |
| `test_extraction_leaves_raw_table_present` | Cold table + FK CASCADE check |
| `test_extraction_leaves_task_id_indexed` | `idx_extraction_leaves_task_id` exists |
| `test_save_raw_extraction_column` | `knowledge_projects.save_raw_extraction` exists with default FALSE |
| `test_migration_idempotent` | Run migrate twice → no errors, no duplicates |

### 4.2 Repo unit (`tests/unit/test_extraction_leaves_repo.py`)

| Test | What |
|---|---|
| `test_fetch_cached_returns_completed_only` | Only `status='completed'` rows are cache hits |
| `test_claim_pending_atomic` | 2 workers can't claim the same row (SELECT FOR UPDATE SKIP LOCKED) |
| `test_mark_completed_writes_candidates_and_timestamps` | Write path correctness |
| `test_mark_failed_increments_retried_n` | Retry counter + error_message persisted |
| `test_delete_by_book_clears_raw_via_cascade` | Invalidation atomic across both tables |
| `test_save_raw_only_when_project_opted_in` | Raw insert skipped when `save_raw_extraction=False` |

### 4.3 Leaf processor unit (`tests/unit/test_leaf_processor.py`)

| Test | What |
|---|---|
| `test_cache_hit_skips_llm_call` | Pre-populated `extraction_leaves` row → leaf_processor returns cached candidates, mocked LLM client `assert_not_called()` |
| `test_cache_miss_calls_llm_then_persists` | No cache → LLM called → candidates + raw (if opted-in) written |
| `test_glossary_unavailable_marks_failed_and_increments_retry` | Mocked glossary 5xx → leaf marked failed + retried_n incremented |
| `test_retry_exhausted_no_re_enqueue` | retried_n == retry_budget → leaf stays failed, no new task |
| `test_extractor_version_in_task_id` | Same text + same op + different extractor_version → different task_id → cache miss |
| `test_task_id_case_insensitive_model_ref` | M2 regression-lock: UPPERCASE vs lowercase model_ref UUID → same task_id |

### 4.4 Pass2 orchestrator integration (`tests/unit/test_pass2_orchestrator_p2.py`)

| Test | What |
|---|---|
| `test_chapter_with_scenes_dispatches_per_leaf` | Chapter with 3 scenes × 4 ops → 12 leaf tasks enqueued |
| `test_legacy_chapter_uses_virtual_scene_fallback` | M6 fix (relocated from §4.3): chapter w/o scenes → fetch_scenes returns 1 virtual scene from chapter_drafts.body → 4 leaf tasks dispatched |
| `test_aggregation_preserves_pass2_candidates_shape` | Per-leaf candidates aggregate back into existing `Pass2Candidates` consumed by Neo4j writer |
| `test_concurrent_extraction_same_book_dedupe_via_task_id` | Two simultaneous extractions of the same chapter → only one LLM call per task_id |
| `test_pre_dispatch_dedup_same_text_different_scenes` | M4 regression-lock: chapter with 2 scenes having identical leaf_text → only 4 task_ids dispatched (not 8); aggregation correctly maps both scenes back to the same candidates |
| `test_parent_job_id_threaded_to_leaf_processor` | H1 regression-lock: leaf_processor receives the parent extraction_job_id; gateway call passes it for billing accumulation |

### 4.5 Invalidation endpoint (`tests/unit/test_internal_extraction_invalidate.py`)

| Test | What |
|---|---|
| `test_invalidate_returns_deletion_counts` | After populating 5 leaves + 3 raw → POST returns `deleted_leaves=5, deleted_raw=3` |
| `test_invalidate_op_filter` | `?op=entity` only deletes entity leaves; others remain |
| `test_invalidate_requires_internal_token` | Missing token → 401 |
| `test_invalidate_idempotent` | Second call → `deleted_leaves=0` |

### 4.6 Live smoke (cross-service)

Per CLAUDE.md cross-service evidence rule (knowledge-service + worker-ai + book-service + glossary-service → 4 services):

1. `docker compose up -d`.
2. Trigger extraction on a 3-chapter test book (use the P1-cleared smoke fixture pattern but with P1-imported book → has parts/scenes).
3. Assert: `extraction_leaves` rows created per scene×op; cache-hit rate on re-run = 100%; glossary anchor was fetched per chapter.
4. Bump `extractor_version` (touch a prompt file); re-run; assert all leaves re-extracted (new task_ids).
5. Call invalidation endpoint; assert `extraction_leaves` empty for that book.

Evidence token: `live smoke: 3-chapter book → N leaves cached → re-run 100% cache-hit → prompt-edit invalidates → invalidate endpoint clears`.

## 5. Acceptance criteria (ADR §7 P2 mapped)

- [x] `extraction_leaves` Postgres table created (migration) → D1 + §4.1.
- [x] Idempotent task ID: re-submitting same leaf returns cached result without LLM call → D2 + §4.3 `test_cache_hit_skips_llm_call`.
- [x] Resume: kill mid-job at leaf 100/500 → restart → completes 400 remaining leaves, skipping 100 done → D9 + integration test (manual, live smoke).
- [x] LM Studio Max Concurrent respected (no overload) → D3 semaphore.
- [PARTIAL — L2 caveat] 10 MB end-to-end test: completes within wall-clock estimate, no orphaned leaves. **P2 live smoke (§4.6) uses a 3-chapter book** (validates the contract end-to-end). True 10MB perf validation deferred to a dedicated perf cycle after P3 (when hierarchical reduce is in place) — file `D-P2-10MB-PERF-VALIDATION`. Per ADR §5, 10MB at parallelism=4 = ~5h wall-clock; running this against the live LM Studio target in CI is uneconomical at P2 stage.

## 6. Risks + mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | Cross-DB read (knowledge-service worker → book-service scenes) has no transactional guarantee with the leaf write | Acceptable — scenes are immutable once written (P3 re-parse soft-deletes, doesn't UPDATE). Worker sees consistent snapshot. |
| R2 | `extraction_leaves_raw` storage grows unbounded for opt-in projects | OQ-P2-1 resolved opt-in default OFF. Power users responsible for their storage. File P-FUTURE-RAW-RETENTION-PRUNE if needed. |
| R3 | Glossary hard-fail = full extraction job pauses on transient glossary outage | PO accepted. Mitigated by: (a) explicit health-check probe at job start (fail-fast vs fail-mid-leaf), (b) clear job status message so user knows to retry. |
| R4 | Stale-claim recovery 30-min ceiling may release tasks that are still legitimately running on a slow LLM | Acceptable — duplicate LLM call writes same task_id, second writer's `INSERT...ON CONFLICT(task_id) DO NOTHING` no-ops. Wasted LLM cost, but no corruption. |
| R5 | extractor_version computed at import time → import-time prompts dir lookup must succeed | The `prompts/*.md` shipping was fixed in session 58 cycle 3 (D-EMB-MODEL-REF-FIX); this dependency is already locked. |
| R6 | Concurrent extractions on same book = 2 workers both compute the same task_id, race to INSERT | `extraction_leaves (book_id, leaf_path, op) UNIQUE` constraint serialises; second INSERT fails, second worker reads the first's candidates instead. No wasted LLM call beyond the race window. |
| R7 | LRU cache for glossary anchor stale within a long-running extraction job (24h for 50MB) | Cache TTL = job duration; new job = fresh fetch. Glossary entries are slowly-changing; 24h staleness within one job is acceptable. |
| R8 | `task_id` cross-book collision (intentional cache reuse) may surface wrong entities for genre-divergent books | LLM extraction is content-determined; same text → same entities regardless of book. **If a future cross-book context becomes part of the prompt**, the prompt template change bumps `extractor_version` → all task_ids change → no stale cross-book hits. |

## 7. Locked design decisions

- **OQ-P2-1 → opt-in per-project** (`knowledge_projects.save_raw_extraction`).
- **OQ-P2-2 → in-worker LRU** (`GlossaryAnchorCache`, per-extraction-job lifetime, bucket-size 5 chapters, max 100 entries).
- **OQ-P2-3 → rely on task_id hash + UNIQUE constraint** for concurrent-job dedup. No job-level locking.
- **OQ-P2-4 → `extractor_version` column** + sha256-of-prompts derivation in SDK.

---

## 8. Out-of-scope reminders + deferred rows filed

**Out-of-scope (P-FUTURE phases):**
- No P3 hierarchical reduce / tree-merge / per-level summaries.
- No P4 semantic chunking escape valve.
- No P5 gated LLM coref / multi-resolution retrieval router.
- No automatic invalidation on `parse_version` bump (per PO choice 2 — caller responsibility).
- No cross-book context in extraction prompt (R8 only matters when this is added).
- No multi-replica worker-ai scale-up (deploy-time, orthogonal — see D3 M1 fix).

**Deferred rows filed (track in SESSION_PATCH at SESSION phase):**
- `D-P2-FE-SAVE-RAW` (L4) — FE toggle for `knowledge_projects.save_raw_extraction`. BE column exists + leaf_processor honors it; FE setting UI is a follow-up cycle.
- `D-P2-10MB-PERF-VALIDATION` (L2) — true 10MB end-to-end perf benchmark. Defer until P3 hierarchical reduce exists (then full pipeline can be perf-tested).
- `D-P2-LEAF-BUDGET-CUTOFF` (D3a edge case) — per-leaf billing cutoff if a runaway leaf blows the per-chapter reserve. Today the leaf 402s but parallel siblings continue; surface in audit, no hard cutoff.
- `D-P2-EXTRACTOR-VERSION-DEV-RECOMPUTE` (L1) — implement `LOREWEAVE_EXTRACTOR_VERSION_DEV_RECOMPUTE=1` env opt-in to bypass module-import-time hash for dev hot-reload.
- `D-P2-RAW-RETENTION-PRUNE` (R2) — if any opt-in tenant grows `extraction_leaves_raw` to multi-GB, add age-based prune job.

## 9. Review trail

### Self-review (before /review-impl round 1, all folded inline)
- **SR-1 (HIGH)** — `book_client.list_active_scenes` + `get_chapter_draft_text` don't exist. **Fix:** added §2 items 7-9 (NEW book-service endpoints + repo methods + client methods).
- **SR-2 (HIGH)** — task_id missing `model_ref` → cross-model cache poisoning. **Fix:** D2 hash includes model_ref + D1 schema gains `model_ref TEXT NOT NULL` column.
- **SR-3 (MED)** — Redis Stream + asyncio.Queue redundancy. **Fix:** D3 rewritten — in-process async fanout only, DB checkpoint is durability layer.
- **SR-4 (LOW)** — extractor_version-in-hash vs parse_version-out-of-hash asymmetry undocumented. **Fix:** D2 docstring explicitly justifies asymmetry.

### /review-impl round 1 (2 HIGH + 6 MED + 5 LOW + 2 COSMETIC; all H+M folded inline)
- **H1** — billing integration missing. **Fix:** D3 leaf_processor accepts `parent_job_id` + new D3a subsection documents single-reservation-per-chapter pattern.
- **H2** — D5 `deleted_raw` count can't be returned via CASCADE-only. **Fix:** D5 rewritten with explicit two-step CTE in a single Tx.
- **M1** — chapter-level concurrency missing. **Fix:** D3 "Concurrency" subsection clarifies intra-chapter (asyncio semaphore) vs inter-chapter (replicas + Redis Stream consumer group); orthogonality documented.
- **M2** — task_id normalization. **Fix:** D2 normalizes `op.lower()` + `model_ref.lower()` + regression-lock test added (§4.3).
- **M3** — glossary LRU bucketing precision loss. **Fix:** D4 dropped bucketing; strict per-chapter keys.
- **M4** — same-task_id race for duplicate scene text. **Fix:** D3 orchestrator pre-dispatch dedup via `unique_tasks` dict + regression-lock test (§4.4).
- **M5** — LRU cache scope ambiguous. **Fix:** D4 explicit per-process never-cleared semantic.
- **M6** — legacy fallback test in wrong file. **Fix:** §4.3 row removed; §4.4 row added with correct layer.
- **L1, L2, L3, L4, L5** — folded inline (D7 hot-reload caveat, §5 perf caveat + D-P2-10MB-PERF-VALIDATION, D5 op-filter caveat, §8 D-P2-FE-SAVE-RAW row, D9 multi-replica idempotency note).
- **C1, C2** — accepted cosmetic, no action.

POST-REVIEW (PO ratification): pending.
