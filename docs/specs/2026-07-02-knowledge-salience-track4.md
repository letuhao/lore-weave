# Track 4 — Salience-Aware Knowledge Retrieval (spec)

**Status:** DESIGN (awaiting review) · **Owner track:** knowledge-service · **Date:** 2026-07-02
**Source research:** `docs/03_planning/KNOWLEDGE_SERVICE_TRACK4_RESEARCH.md` (R-T4-01…09)
**Related:** `07S_studio_agent_standard.md` (context buckets), Wave A compaction (chat-service),
`KNOWLEDGE_SERVICE_ARCHITECTURE.md` §4 (L0–L3 memory stack).

---

## 1. Goal & the two-layer clarification

Make knowledge retrieval **salience-aware** — the memory block should surface what *matters
most* to this user/book, learned from actual access + edits + feedback, not just static tier +
similarity + recency. This is the **computed/learned-importance** pillar of "how do we know
what's important."

**Explicitly scoped — same concept, different layer than Wave A compaction:**

| Layer | Acts on | This spec? |
|---|---|---|
| **Retrieval salience** (knowledge-service, this spec) | KG entities/facts/passages → the pinned memory block | ✅ P0–P5 |
| **Declared importance** (07S buckets + Wave C1 steering) | user-pinned / story-bible | ❌ separate build |
| **Conversation compaction** (Wave A, chat-service) | transient chat turns | ⚠️ only R-T4-09 touches it (P5) |

Because the KG memory block is re-assembled and re-injected **every turn**, improving retrieval
salience strengthens the durable backstop that already makes Wave A recency-compaction safe.

## 2. What already exists (grounded — do NOT rebuild)

- **Full retrieval pipeline** (Modes 1–3, L0–L3): `context/builder.py`, `context/modes/*.py`.
  L2 intent-classified graph facts, L3 vector passages with **MMR + recency-weight + hub penalty**,
  reverse-priority **budget trimming** (`full.py:_enforce_budget`).
- **Signals already on the graph**: `Entity.evidence_count`, `:RELATES_TO {confidence}`,
  `Event {narrative_order, event_date_iso}`, `glossary_entities.is_pinned_for_context`,
  `short_description`, `rank_score` (glossary K2b tiered selector).
- **Reranker client** (`clients/reranker_client.py`): provider-registry BYOK cross-encoder,
  graceful-degrade to None; per-project (`extraction_config.rerank_model`) + user-default resolve.
- **Feedback signal**: `chat-service POST /v1/chat/messages/{id}/feedback` → thumbs ±1 + implicit
  regenerate-negative → outbox `loreweave:events:chat` → learning-service quality_score.
- **Query-embedding cache** (`context/query_embedding.py`) shared across L3 / glossary / blend.

**What is 0-LOC (the gap):** any mechanism that *learns* per-user/per-book salience over time
(access telemetry, decay, feedback-driven promotion), pointer-based expansion, iterative retry,
consolidation, metadata filters.

## 3. Design principles (LOCKED — from CLAUDE.md)

1. **Tenancy**: every salience row carries `owner_user_id` **and** `project_id` (or `book_id`).
   Salience is per-user-per-book; **never** a shared/global signal. No cross-tenant bleed.
2. **Provider-invariant**: embeddings + rerank resolve through **provider-registry** (BYOK
   `user_model` UUIDs). No provider SDK, no hardcoded model names, no per-service model env.
3. **MCP-first**: pointer *expansion* (P4) is exposed as an MCP tool on knowledge-service, not a
   bespoke prompt endpoint.
4. **Measure before flip** (Track 4's own trigger discipline): each behavior-changing phase ships
   **behind a flag defaulting to current behavior**; the telemetry substrate (P0) provides the
   signal to decide whether/how far to turn it on. No speculative tuning committed as default.
5. **Graceful degrade**: salience is *additive* to the existing score; any failure (no telemetry,
   decay job stale, rerank down) falls back to today's ranking. Retrieval never 500s on salience.

## 4. The salience model

A per-(user, book, entity) **salience score** in `[0,1]`, blended into the existing ranking as an
additive, flag-weighted term — it re-orders, never gates (an entity is never *hidden* by low
salience; it just ranks lower and is trimmed first under budget):

```
final_score = base_score                     # today: tier/similarity/recency (unchanged at w=0)
            + w_access   · access_salience    # P1  — decayed retrieval frequency + recency
            + w_promote  · promotion_salience  # P3  — edits, evidence, thumbs-up, recent mentions
```

- `access_salience` = normalized Ebbinghaus-decayed retrieval count:
  `decayed = retrieval_count · 0.5^(days_since_last / HALF_LIFE_DAYS)`, min-max normalized within
  the (user, book).
- `promotion_salience` = weighted blend of edit-recency, `evidence_count` (normalized),
  recent-chapter mention, and thumbs-up-turn ratio — all signals that already exist on the graph
  or the event stream.
- `w_access`, `w_promote` are settings, **default 0** (byte-identical to today) until P0 telemetry
  justifies a value.

## 5. Phased plan (maps R-T4-01…09)

### P0 — Salience substrate (telemetry). *No behavior change.* **[buildable now]**
- New Postgres table (knowledge-service DB):
  `entity_access_log(owner_user_id, project_id, entity_id, last_retrieved_at, retrieval_count,
   decayed_score)`, `PK (owner_user_id, project_id, entity_id)`, indexed on `(owner_user_id, project_id)`.
- L2/L3/glossary selectors emit a **fire-and-forget, non-blocking** access record for every entity
  they surface (batched upsert after the block renders — off the latency path).
- **This is the trigger Track 4 was waiting for**: with the log, we can measure whether the static
  selector misses high-value entities before spending on tuning.

### P1 — Frequency/recency-weighted retrieval (R-T4-01) + cold-demote (R-T4-03). **[buildable now, flag-gated]**
- Nightly decay job applies the Ebbinghaus curve to `decayed_score`; cold entities (> N days) sink.
- Blend `access_salience` into L2 fact / L3 passage / glossary scoring (§4). Flag `w_access` default 0.
- Measure lift on the POC book before defaulting the weight > 0.

### P2 — Cross-encoder rerank in the L3 *context* path (R-T4-07). **[buildable now — client exists]**
- Wire the existing `RerankerClient` into `select_l3_passages`: pull ~30 candidates → cross-encoder
  rerank → top-k. Reuse `extraction_config.rerank_model` + user-default resolve; graceful-degrade to
  MMR order when rerank is unset/down. (Today only raw-search uses the client; L3 has only the
  optional *generative* rerank hook.)

### P3 — Salience auto-promotion (R-T4-02). **[split P3a/P3b — decision record 2026-07-02]**

**P3a (graph-native slice — BUILT):** promotion from signals already ON the KG Entity
node: `evidence_count` + `mention_count` (log-damped, max-normalized) + edit recency
(`updated_at`, 30d half-life), composed 0.5/0.3/0.2 in `promotion_score`. Blended as a
second flag-weighted term (`salience_promote_weight`, default **0.0** = no Neo4j fetch,
byte-identical). Full mode only (static mode has no graph). Pins still lead. Degrades to
identity on any Neo4j failure.

**P3b (feedback slice — SPEC'D, deferred behind the eval gate):** the thumbs signal
(`chat.message_feedback` on `loreweave:events:chat`) carries `{user_id, session_id,
message_id, rating}` but **no entity attribution** — knowledge-service would need
(1) a new consumer group on the chat stream and (2) a turn→surfaced-entities attribution
record (e.g. stamping `session_id`+timestamp onto P0 access rows, or a per-turn context
snapshot). That is a structural build (defer gate #2), and its value is unproven while
BOTH blend weights sit at 0 (the P1 eval showed explicit-query re-ranking regresses).
**Trigger to build P3b:** an ambiguous-query eval shows the blended signals lift, making
finer per-turn attribution worth the new consumer + schema.

### P4 — Hierarchical pointer retrieval (R-T4-05) + iterative-retry-on-miss (R-T4-06). **[buildable now]**
- When the glossary/entity block would dominate the budget, emit **pointers** (`id + name +
  short_description`) instead of full EAV; add an MCP tool `expand_entity(entity_id)` the agent
  calls to pull the full bundle on demand (MCP-first).
- On empty/low-quality L2+L3, auto-retry once with a widened query (no filter / stemmed / +1 graph
  hop from the anchor) before returning "no memory."

### P5 — Consolidation (R-T4-04) + metadata filters (R-T4-08) + conversation-layer LFU (R-T4-09). **[larger / partly deferred]**
- **R-T4-04** nightly "sleep": merge near-duplicate entities, refresh `cached_name`, discover
  co-occurrence edges. Batch job; depends on extraction volume.
- **R-T4-08** structured metadata filter alongside K2b text (location/topic tags). Depends on user
  tagging uptake — spec now, gate on the tagging signal.
- **R-T4-09 (the compaction bridge)**: chat-service records which past messages the user
  referenced/scrolled-back-to; Wave A compaction weights those to *keep* (not pure recency). This is
  the one item that feeds the **conversation** layer — connects Track 4 to Wave A.

## 6. Tenancy & security checklist (per feature)

- `entity_access_log`, promotion aggregates → scoped `(owner_user_id, project_id)`; every read/write
  filters by both. No `UNIQUE(entity_id)` without the scope key.
- Feedback/edit signals consumed are already owner-scoped at their source; the aggregator must not
  cross `owner_user_id`.
- Pointer-expand MCP tool → `require_book_owner` VIEW gate like every other knowledge read.

## 7. Verification plan

- **Unit**: decay math, score-blend monotonicity, normalization within tenant, flag=0 ⇒ byte-identical
  ranking (regression guard), rerank graceful-degrade, pointer/expand round-trip, tenancy filter.
- **Evaluation over the 12-ch POC book** (per the project's "prefer E2E + evaluation over one-off
  smoke" rule): compare retrieval hit-quality with `w=0` vs tuned, on a fixed query set — this is the
  trigger measurement, not a vibe check.
- **Live cross-service smoke** for P3 (feedback event → promotion aggregate) and P2 (real local
  reranker via provider-registry) — ≥2 services, per the live-smoke rule.

## 8. Deferred / trigger-gated (won't default-on without evidence)

- P1/P3 weights stay 0 until the P0 telemetry + POC evaluation show lift (Track 4's discipline).
- R-T4-08 metadata filter gated on user-tagging uptake.
- R-T4-04 consolidation gated on extraction volume + observed duplicate rate.

## 8b. Measurement results — 2026-07-02 (the flip decision, per §7)

Eval KG: POC book `019f1783-ebb4` (12 ch VN), extracted with gemma QAT + bge-m3
(40 entities / 125 events / 15 facts / 181 passages). Harness: `eval/run_salience_eval.py`
(seed 5×4 focus via real HTTP → P0 telemetry confirmed landing; measure 12 explicit
queries, in-process arms).

| Arm | MRR | mean rank | hit@list | passage-hit |
|---|---|---|---|---|
| baseline `w=0` (rerank off) | 0.5307 | 4.50 | 1.0 | 0.75 |
| salience `w=0.3` | 0.5126 | 4.67 | 1.0 | 0.75 |
| baseline `w=0` (cross-encoder ON) | 0.5307 | 4.50 | 1.0 | **0.80** |

**P1 verdict: KEEP `salience_access_weight = 0.0`.** REGRESSION on the explicit-query
set — tier/FTS ranking is already near-optimal when the query names the entity, and
the seed pattern boosts the whole co-surfaced cluster (no per-query discrimination).
Revisit trigger: an ambiguous-query eval (queries that DON'T name the entity), or the
P3 promotion signals which are per-entity rather than per-build.

**P2 verdict: SHIPPED as per-project opt-in (its designed state) — chain live-proven.**
Real HTTP build → L3 (pool 40 → final 10) → provider-registry `/internal/rerank` 200
(local bge-reranker-v2-m3 BYOK) → reorder logged. Passage-hit +0.05 (1 query) — weakly
positive, not significant at n=12; per-project opt-in stands, no default flip.

Also fixed during measurement: `rerank_model` / `cross_encoder_rerank_model` were
readable by the builder but UNREACHABLE via the public API (`extra="forbid"` on
`ProjectExtractionConfigUpdate`) — write path added.

## 9. Rollout order

`P0 (substrate) → P2 (rerank, independent quick win) → P1 (freq-weight) → P3 (promotion) → P4
(pointers/iterative) → P5 (consolidation/metadata/LFU bridge)`.
Each phase is independently shippable, flag-guarded, and reviewed on its own.
