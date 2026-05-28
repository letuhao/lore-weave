# ADR — Hierarchical Extraction Pipeline (knowledge-service)

- **Status:** Proposed
- **Date:** 2026-05-23 (session 61, post-correction)
- **Deciders:** PO (user) + Lead (agent)
- **Supersedes/relates:** previous session-61 in-handoff sketch ("4-tier semantic-chunking architecture"). That framing was empirically wrong (see §3); this ADR replaces it.

---

## 1. Context

Sessions 60–61 closed the measurement instrument (LLM-judge) and the gateway aggregator markdown-fence bug. Extraction now scores **P=0.97 / R=0.81** on 9/10 golden chapters with the local Qwen3.6-35B-A3B target.

The remaining gap is **scale**. Concretely:
- `sherlock_speckled_band` (1139 lines, 17 chunks × 4 ops ≈ 1 hour of LLM time) hangs the local target via mid-stream model eviction. Session-61 cycle 2 added an **idle-timeout safety net** in the gateway streamer — failures fail-fast but the chapter still excluded from baselines.
- The user explicitly asks for an architecture that handles novels **of any size, up to 50 MB+ corpora**, on the existing local-first stack with cloud as a speed-up option, NOT a feasibility requirement.

The current pipeline cannot scale because every chapter is treated as **one extraction job** with **serial chunks inside** and **flat, key-only dedup across chunks**. Sessions ≥ ~1 hour reliably trigger LM Studio TTL eviction; flat dedup misses cross-chapter coreference; there is no checkpoint/resume.

### 1.1 Anti-pattern this ADR avoids

A first sketch (in [SESSION_HANDOFF.md](../sessions/SESSION_HANDOFF.md) "What's NEXT") proposed **semantic chunking as the primary lever** of a 4-tier design. The user-PO rejected that framing:

> "Việc dùng SEMANTIC CHUNKING 1 cách máy móc là 1 sai lầm. Không có document nào nặng như vậy mà không thể chia nhỏ từng phần và liên kết kết quả KG cả. Không ai chỉ dùng 1 thuật toán để xử lý tài liệu — smart là kết hợp nhiều loại với nhau."

The correction is correct. Re-research confirmed (see §2): **every production system that handles long documents at scale uses multi-algorithm composition with cheap deterministic decomposition first.** Semantic chunking, where it appears, is an **escape valve for unstructured leaves**, not the primary lever.

---

## 2. SOTA re-research (multi-algorithm composition)

Reviewed in May 2026: Microsoft GraphRAG, Anthropic Contextual Retrieval, Cohere Compass, OpenAI Assistants File Search, Vectara, Pinecone Assistant, LangChain/LlamaIndex production guides, Google NotebookLM, recent papers (RAPTOR, GraphRAG, HippoRAG/HippoRAG-2, LongRAG, LightRAG, Late Chunking, Contextual Retrieval).

### 2.1 Findings

**Every production system composes multiple techniques.** None uses a single algorithm.

| System | Pipeline |
|---|---|
| **Microsoft GraphRAG** | TextSplitter (recursive char, structural) → entity-extract per chunk (LLM) → graph construction → **Leiden community detection** → per-community summary (LLM) → hierarchical retrieval. **Semantic chunking absent**. |
| **Anthropic Contextual Retrieval** | Naive token chunking → **LLM contextual augmentation** per chunk → dual BM25+embedding → rerank. **Semantic chunking absent**. |
| **Cohere Compass** | Structural parse (per heading/paragraph/table) → **multi-vector element indexing** → ColBERT late interaction. **Semantic chunking absent**. |
| **OpenAI Assistants File Search** | Structural parse → token-budget chunk → embed → retrieve+rerank. **No semantic chunking publicly described**. |
| **NotebookLM** | Structural parse → hierarchical map-reduce summarization → community detection. **No semantic chunking publicly described**. |
| **LangChain / LlamaIndex production guides** | "Try `RecursiveCharacterTextSplitter` first. Use `SemanticChunker` ONLY when retrieval quality is unsatisfactory AND structural boundaries fail." → semantic is **fallback**. |

### 2.2 Where semantic chunking IS used

Semantic chunking (LangChain `SemanticChunker`, LlamaIndex `SemanticSplitterNodeParser`, Jina Late Chunking) is genuinely valuable for:
- **Chat transcripts / call logs** — no structural markers.
- **Scraped web pages** — inconsistent headings.
- **Stream-of-consciousness prose** within a leaf that already exhausted paragraph + sentence boundaries.

Novels / books have structural boundaries the author CREATED (parts, chapters, scenes via dinkus/ornament). Detecting them is FREE and lossless. Bypassing this layer in favor of embedding-similarity splitting is **premature optimization that throws away author intent and pays embedding cost for no signal gain**.

### 2.3 Common pattern across SOTA

```
Step 1 — STRUCTURAL DECOMPOSITION   (free, deterministic, lossless)
Step 2 — LEAF SIZING                (cheap; paragraph/sentence split)
Step 3 — PARALLEL MAP               (embarrassingly parallel)
Step 4 — HIERARCHICAL REDUCE        (key-based dedup; deterministic first)
Step 5 — GATED LLM REFINEMENT       (only for ambiguous/uncertain cases)
Step 6 — POST-HOC VERIFY            (consistency, lifecycle, anomaly)
Step 7 — MULTI-RESOLUTION INDEX     (chunk + section + doc embeddings)
```

Each step uses the cheapest tool sufficient for its role. Expensive tools (LLM, embedding) gated by metric / heuristic, not the default.

### 2.4 Key insight: scale is wall-clock, not capability

The previous sketch claimed 50MB "needs cloud". This conflated two things:
- **Capability** — can the system process it at all?
- **Latency** — how fast?

With **checkpoint + parallel map + idempotent task ID**, local 35B is FULLY CAPABLE of any size. Cloud only changes wall-clock. For 50MB at ~30s per leaf, parallelism=4, ~12,500 leaves → ~24 hours of local wall-clock, fully recoverable from checkpoint. Cloud (Haiku at ~4s/leaf, parallelism=20) ~1.5 hours. **Both are feasible; choice is cost vs. time.**

---

## 3. Decision: 7-tier pipeline composition

Replace the single-job-per-chapter, serial-chunks-inside, flat-dedup pipeline with a **7-tier composition**, each tier addressing one failure mode using the cheapest sufficient tool.

```
INPUT (any size: 1KB → 50MB+)
   ↓
[T1] STRUCTURAL DECOMPOSITION  — free, deterministic, lossless
[T2] LEAF SIZING + OVERFLOW    — paragraph → sentence → semantic (escape valve)
[T3] PARALLEL MAP EXTRACTION   — embarrassingly parallel, idempotent, checkpointed
[T4] HIERARCHICAL DETERMINISTIC REDUCE — tree-merge by canonical_id + alias UF
[T5] GATED LLM REFINEMENT      — coreference only for ambiguous candidate pairs
[T6] CROSS-LEVEL VERIFY        — consistency checks + LLM-as-judge sample
[T7] MULTI-RESOLUTION INDEX    — per-scene + per-chapter + per-book vectors
   ↓
OUTPUT: hierarchical KG ready for multi-resolution retrieval
```

### T1 — Structural decomposition (deterministic, no LLM, no embedding)

**Goal:** parse INPUT into a tree of natural boundaries the author created.

**Multi-format dispatcher:**

| Source | Algorithm | Tool |
|---|---|---|
| EPUB / MOBI | XML spine walk → reading order + ToC | `ebooklib` (Python) |
| PDF | PDF outline (ToC bookmarks) + page-break heuristic | `pdfplumber`, `pymupdf` |
| Markdown | ATX header tree (`#`, `##`, `###`) | `markdown-it`, `mistune` |
| TEI XML | Structural element walk (`<div type="chapter">`) | `lxml` |
| Plain text (English) | Regex: `^Chapter\s+\d+`, `^[IVX]+\.`, dinkus `* * *`, ornament Unicode | custom |
| Plain text (Chinese trad./simp.) | Regex: `第[一二三...]章`, `第[一二三...]回` | custom |
| Plain text (Vietnamese) | Regex: `Chương\s+\d+`, `Hồi\s+\d+` | custom |
| Plain text (Japanese) | Regex: `第[一二三...]章`, `その[一二三...]` | custom |

**Output schema (Pydantic):**

```python
class StructuralNode(BaseModel):
    path: str  # "book/part-1/chapter-3/scene-2"
    level: Literal["book", "part", "chapter", "scene"]
    title: str | None
    children: list["StructuralNode"]
    leaf_text: str | None  # only at scene level

class StructuralTree(BaseModel):
    source_format: Literal["epub", "pdf", "markdown", "tei", "plain"]
    root: StructuralNode
```

**Constraint:** leaf (scene) text size ≤ `LEAF_TOKEN_TARGET` (default 2000 tokens, model-dependent). Leaves over this go through T2.

**Cost:** O(input size) regex/AST. No LLM, no embedding. Free.

### T2 — Leaf sizing + structural-overflow handler

**Goal:** ensure every leaf fits the extractor model's effective window. Composition try-in-order:

1. **Paragraph split** (`\n\s*\n`) — handles ~95% of overflowed leaves.
2. **Sentence split** (existing `split_by_language`, language-aware) — handles ~4% more.
3. **Semantic chunking** (NEW, escape valve only): embedding-similarity adjacent-sentence breakpoint with percentile threshold (LangChain-style). Applies to ~1% of leaves (long dialogue, stream-of-consciousness).

**When semantic kicks in:** leaf still > token cap AFTER paragraph + sentence split. Rare for narrative fiction.

**Cost:** stages 1-2 free; stage 3 = 1 embedding batch call per leaf (~50ms with bge-m3 local). Bounded by leaf rarity.

### T3 — Parallel map extraction (embarrassingly parallel)

**Goal:** per-leaf extract E/R/V/F independently, idempotent, resumable.

**Composition:**

| Concern | Mechanism |
|---|---|
| Idempotent task ID | `sha256(leaf.normalized_text + extractor_op_name)` — same input → same hash → cache hit skips |
| Checkpoint table | NEW Postgres `extraction_leaves(book_id, leaf_path, op, status, result_jsonb, retried_n, started_at, completed_at)` keyed `(book_id, leaf_path, op) UNIQUE` |
| Job orchestration | Existing Redis Streams + RabbitMQ — DAG over leaves, parallelism bound by `LM_STUDIO_MAX_CONCURRENT` |
| Rolling context | Per-chapter `known_entities` window: top-K (cap 200) canonical names from previously-completed leaves in same chapter, threaded to extractor for cross-leaf anchor |
| Failure handling | Per-leaf retry budget (default 2); on exhaustion, leaf marked `failed`, reduce-step ignores |
| Resume on restart | Skip leaves with `status = 'completed'`; recompute everything else from scratch |

**Reuses existing** `gather_relations_events_facts` extractor. No prompt change. No new ML.

**Cost:** wall-clock = leaves × per-leaf-latency / parallelism. Local 35B example: 250 leaves × 30s / 4 ≈ 30 min per novel.

### T4 — Hierarchical deterministic reduce (tree-merge)

**Goal:** merge per-leaf KGs bottom-up using only deterministic dedup. **No LLM in this tier.**

**Algorithm — tree-merge pairwise:**

```
Level 0: scene KGs (output of T3)
   ↓ pairwise merge by parent path
Level 1: chapter KGs
   ↓ pairwise merge by parent path
Level 2: part KGs
   ↓ pairwise merge by parent path
Level 3: book KG
```

**Merge operation (per level):**

1. **Entity merge** by existing `canonical_id` (already deterministic from `canonicalize_entity_name`).
2. **Alias union-find** (Tarjan UF): two entities with ≥2 shared aliases → same canonical group. Bridges name variants the canonicalizer missed.
3. **Relation merge** by `(subject_canonical_id, predicate, object_canonical_id, polarity)` (existing key extended to use post-merge canonical IDs).
4. **Event merge** by `(name_norm, time_cue)` (existing).
5. **Per-level summary embedding**: NEW — for T7 multi-resolution storage. LLM-generated 2-3 sentence summary per chapter/part/book node, embedded and indexed.

**Property:** O(N) total work, O(log N) sequential depth — parallelizable.

**Cost:** zero LLM in the merge; per-level summary is 1 LLM call per chapter/part/book (≪ leaf count). For a 1MB novel with 50 chapters: 50 + 5 + 1 = 56 LLM summary calls vs. 1000+ leaf extraction calls — small overhead.

### T5 — Gated LLM refinement (ambiguous-only)

**Goal:** resolve cross-section coreference that deterministic merge missed — "the Master" in chapter 5 = "Holmes" in chapter 1 (different name string, no alias overlap, but same kind + role).

**Ambiguity gate (heuristic):**

Two entities NOT linked by deterministic merge AND ALL OF:
- Same `kind` (catalogue-aligned).
- `cosine(entity_emb_A, entity_emb_B) ≥ 0.85` (entity embedding = canonical_name + aliases concat).
- Co-occurring relations overlap ≥ 50% (shared subjects/objects).

→ Flag as candidate pair.

**LLM resolution (only for candidates):**

```
Input: (entity A summary + source excerpts) + (entity B summary + source excerpts)
Prompt: "Are these the same fictional entity? Yes/No + reason."
Output: yes/no + confidence
Action: merge if yes AND confidence ≥ 0.8; record audit trail
```

**Cost bound:** Typically ≤5% of entities are ambiguous post-T4. For 10K entities → ≤500 LLM calls. Linear in document size, small.

### T6 — Cross-level verify (post-hoc consistency)

**Goal:** detect anomalies the pipeline produced silently.

**Composition (cheap → expensive):**

1. **Lifecycle consistency** (regex/graph, free): entity has `death` event in chapter 5 → flag if `:Mentions` exists in chapter 7+.
2. **Spatial consistency** (graph topology): location referenced before its introduction event → flag.
3. **Confidence calibration** (threshold): low-confidence relations + events surfaced for human review.
4. **LLM-as-judge sample** (gated, existing harness): random 5-10 entities/relations per chapter judged against source — confirms quality without judging every item.

**Output:** consistency report per book, embedded in extraction job metadata. Does NOT auto-correct — that's a separate human-in-loop track.

### T7 — Multi-resolution index

**Goal:** support retrieval at the right granularity per query type.

**Composition:**

| Vector index | Source | Use case |
|---|---|---|
| **Per-scene passages** | Existing K17.9 `:Passage` nodes | Specific event/entity lookup ("when did Holmes meet Watson") |
| **Per-chapter summary** | T4 chapter-level summary | Theme/arc query ("themes in chapter 5") |
| **Per-part summary** | T4 part-level summary | Multi-chapter abstract query |
| **Per-book summary** | T4 book-level summary | Gist / character overview |
| **Entity vectors** | canonical_name + aliases | Mention linking, fuzzy entity search |
| **Community vectors** | Optional Leiden community on entity graph | GraphRAG-style theme retrieval |

**Retrieval router (Mode-3 extension):**

```
Query → embed → cosine match against ALL 4 levels in parallel
     → score-aware blending:
        - exact-name query → prioritise scene + entity
        - abstract query   → prioritise summary levels
     → rerank top-K with cross-encoder (existing or NEW)
     → return contexts
```

Stage-0 deliverable: scene-level only (matches existing Mode-3). Stage-1: add chapter summaries. Stage-2: add part + book + community.

---

## 4. Multi-algorithm composition matrix

Smart engineering = **pick the cheapest tool sufficient for each role**, not the most powerful tool everywhere.

| Stage | Cheap (default) | Mid-cost (gated) | Expensive (last resort) |
|---|---|---|---|
| **Decomposition** | Regex / AST marker detection | EPUB/PDF AST parse | LLM-aided ToC inference (only for noisy scans) |
| **Leaf sizing** | Paragraph split | Sentence split | Semantic chunking (escape valve only) |
| **Mention linking** | Canonical_id dictionary | Embedding similarity (cosine ≥ 0.85) | NER + entity-linking model |
| **Dedup** | Key-based hash | Alias union-find | LLM coreference (gated by ambiguity heuristic) |
| **Cross-section context** | Rolling known_entities (top-K) | Doc-level embedding | Anthropic-style contextual augmentation |
| **Hierarchical merge** | Tree-merge deterministic | Embedding-aided merge | LLM-aided merge for ambiguous |
| **Community / clusters** | (skip for small docs) | Louvain / Leiden | GraphRAG-style with LLM summaries |
| **Consistency check** | Regex anomaly detector | Graph topology checks | LLM-as-judge sample |
| **Retrieval** | BM25 | Single-vector cosine | ColBERT late interaction + rerank |

**Default = cheap.** Escalate to mid-cost when cheap fails the metric (judged via LLM-judge harness from session 60-61). Escalate to expensive only when mid-cost fails. Most LoreWeave content (narrative fiction with structural markers) never needs the expensive column.

---

## 5. Scale estimates (corrected)

| Novel size | Parts | Chapters | Scenes (leaves) | Local 35B (parallel=4, ~30s/leaf) | Cloud (Haiku, parallel=20, ~4s/leaf) |
|---|---:|---:|---:|---:|---:|
| 100 KB | 1 | 1 | ~5 | ~3 min | ~10 s |
| 1 MB | 1 | ~50 | ~250 | ~30 min | ~2 min |
| 10 MB | ~5 | ~500 | ~2,500 | ~5 h (overnight) | ~20 min |
| **50 MB** | ~10 | ~2,500 | **~12,500** | **~24 h (resumable)** | **~1.5 h** |

**Key correction from prior sketch:** local 35B is **fully capable** of 50 MB. Wall-clock is the cost, not feasibility. Checkpoint + idempotent task ID make 24h runs resumable. Cloud is a **speed-up option** users opt into, not a requirement.

---

## 6. Roadmap (5 phases, cheap-first)

| Phase | Scope | Class | Size | Dependencies |
|---|---|---|---|---|
| **P1: Structural decomposer** | Multi-format parser (EPUB/MD/TEI/plain-text + Chinese/Vietnamese/English/Japanese markers). Outputs `StructuralTree`. No LLM, no embedding. | T1 | M | (none) |
| **P2: Parallel map orchestrator + checkpoint** | DAG over leaves; idempotent `sha256` task ID; `extraction_leaves` Postgres table; resumable; reuses existing extractors. Rolling known_entities window. | T3 | L | P1 |
| **P3: Hierarchical deterministic reduce + per-level summaries** | Tree-merge with canonical_id + alias union-find; per-chapter/part/book summary embeddings; Neo4j hierarchy nodes (`:Scene`/`:Chapter`/`:Part`/`:Book` labels with parent-child edges). | T4 + T7 stage 1 | L-XL | P2 |
| **P4: Semantic chunking escape valve** | Add `semantic` strategy to `provider/chunker/chunker.go` for leaves overflowing paragraph + sentence split. Percentile-breakpoint algorithm (LangChain-style). | T2 stage 3 only | S-M | P1 |
| **P5: Gated LLM coreference + verify + multi-resolution retrieval** | Ambiguity heuristic + LLM coreference gating; consistency checklist runner; Mode-3 retrieval router across resolution levels. | T5 + T6 + T7 stages 2-3 | L | P3 |

**Order rationale:**

1. **P1 + P2** alone unlock 50 MB on local (deterministic decomposition + parallel + resume). High value, low ML risk.
2. **P3** gives hierarchical KG + multi-resolution storage. Critical for retrieval quality but no new ML.
3. **P4** semantic chunking is a small, optional escape valve. Independent of P3.
4. **P5** is quality polish — gated LLM ops + cross-section verify. Last because it's the most expensive and the cheaper tiers must be measured first.

**P1 + P2 + P3 = capability complete for 50 MB local.** Subsequent phases improve quality and retrieval routing.

---

## 7. Acceptance criteria

### P1 (Structural decomposer)
- Multi-format parser handles EPUB, Markdown, plain-text English/Chinese/Vietnamese/Japanese with structural markers.
- `StructuralTree` Pydantic schema with `book/part/chapter/scene` levels.
- Output for 10 fixture corpora (incl. multi-volume novels) round-trips through serialisation without data loss.
- Unit tests cover marker detection per language; integration test parses a real EPUB into a tree.
- ZERO LLM / embedding calls in T1.

### P2 (Parallel map orchestrator + checkpoint)
- `extraction_leaves` Postgres table created (migration).
- Idempotent task ID: re-submitting same leaf returns cached result without LLM call.
- Resume: kill mid-job at leaf 100/500 → restart → completes 400 remaining leaves, skipping 100 done.
- LM Studio Max Concurrent respected (no overload).
- 10 MB end-to-end test: completes within wall-clock estimate, no orphaned leaves.

### P3 (Hierarchical reduce + per-level summaries)
- Tree-merge produces book-level KG identical (modulo summary nodes) to running each leaf's KG through existing flat dedup.
- Neo4j hierarchy nodes (`:Scene` / `:Chapter` / `:Part` / `:Book`) with `:HAS_CHILD` edges.
- Per-chapter/part/book summary embeddings stored.
- LLM-judge baseline ≥ session-61 P=0.97 R=0.81 on 9 golden chapters (no regression).
- `sherlock_speckled_band` joins the baseline (no longer skipped) and meets P ≥ 0.85 R ≥ 0.70.

### P4 (Semantic chunking escape valve)
- `semantic` strategy in `chunker.go` with percentile-breakpoint algorithm.
- Falls back from paragraph → sentence → semantic correctly.
- Only triggered when leaf > token cap AFTER stages 1-2.
- Eval: chunking strategy switch shows ≥ 2% recall improvement on 1 fixture with deliberately structureless content.

### P5 (Gated LLM coref + verify + multi-res retrieval)
- Ambiguity gate (cosine ≥ 0.85, same kind, shared relations) flags ≤ 5% of entities post-T4.
- LLM coref decisions audited per merge; reversible.
- Consistency checklist runs in < 30 s on book-level KG.
- Multi-resolution retrieval router measurable improvement on abstract queries (TBD: design abstract-query eval set).

---

## 8. Risks & open questions

- **R1 — Structural marker reliability.** Some EPUBs have malformed ToC; some plain-text novels have ornament-only breaks. Mitigation: fall back to leaf-token-cap split if no structural boundary found in N tokens.
- **R2 — Rolling known_entities window size.** Cap 200 might miss long-distance recurring entities. Mitigation: tune via judge; alternative is per-chapter glossary anchor (fetch from glossary-service before extraction).
- **R3 — Cross-volume coreference in multi-novel series.** "Holmes" across multiple books should canonicalise. Out of scope here; handle when glossary catalogue gets per-series scoping.
- **R4 — LLM coref cost on large entity sets.** Ambiguity heuristic may flag too many candidates on a 50 MB corpus. Mitigation: bound by `MAX_COREF_PAIRS_PER_BOOK = 500`.
- **R5 — Summary quality at higher levels.** Per-book summary risks losing detail. Mitigation: summary embedding is a retrieval cue, not the only ground truth — drill down to scene level always available.
- **Q1 — Per-format dispatcher boundary**: which service owns format parsing (book-service vs knowledge-service)? Probably book-service already exposes the chapter text; T1 plugs into chapter ingestion path.
- **Q2 — Migration of existing extracted books**: do we re-process or backfill? Decide at P3 acceptance.

---

## 9. Lessons recorded for agent memory

- **Cheap deterministic decomposition before expensive probabilistic transforms.** Saved as `feedback_cheap_structural_before_expensive_semantic` — applies to any pipeline design involving large documents.
- **"Needs cloud for X-MB" is usually a wall-clock claim, not a feasibility claim.** Checkpoint + parallel + local can handle any size given time.
- **No production system uses a single algorithm for long-doc extraction.** Always multi-algorithm composition; signed off by SOTA survey (GraphRAG, Anthropic Contextual Retrieval, Cohere Compass, NotebookLM, LangChain/LlamaIndex production guides).
- **Author intent (structural markers) is free signal.** Bypassing it in favor of statistical methods is premature optimization.
