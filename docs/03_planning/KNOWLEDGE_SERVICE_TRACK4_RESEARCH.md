# Knowledge Service — Track 4 Research Backlog

> **Status:** Research / exploration. **Do not implement from this doc.**
> **Created:** 2026-04-13 (session 36)
> **Scope:** Cognitive-architecture and advanced-retrieval ideas worth investigating *after* Track 1–3 ship and we have real production telemetry to validate against.

---

## What this document is — and isn't

This is a parking lot for ideas that came up while we were building Tracks 1–3, but that we deliberately did **not** implement because:

1. We don't have real usage data yet to know if they'd help.
2. Several of them require infrastructure (Neo4j, telemetry pipeline, LLM-driven extraction) that only lands in Track 2.
3. They're cognitive-architecture borrowings from human memory research — promising but speculative.
4. We need to ship Track 1 → Track 2 → Track 3 first to learn where the *actual* quality bottlenecks are. Some of these may turn out to be unnecessary; others may turn out to be obviously needed once we see real chat sessions.

**Rule for this doc:** every entry should explain (a) what the idea is, (b) where it came from, (c) what we already have that overlaps with it, and (d) the specific signal that would tell us "yes, build this now." If we can't articulate the trigger, the idea isn't ready to research yet.

When an idea graduates from "research" to "design", it moves out of this file into a real Track-N implementation plan with tasks and gates.

---

## Sources

- **Session 36 chat thread** (`chat.txt` in repo root, captured from a separate AI conversation about RAG / KG / memory architectures — `2026-04-13`). Most ideas in this doc trace back here.
- **Microsoft GraphRAG** ([arXiv:2404.16130](https://arxiv.org/abs/2404.16130)) — already cited in `KNOWLEDGE_SERVICE_ARCHITECTURE.md` for the seed-graph pattern. The two-layer KG already adopts part of this.
- **HippoRAG** ([arXiv:2405.14831](https://arxiv.org/abs/2405.14831)) — anchor nodes + multi-hop QA, already referenced for the `glossary_entity_id` linkage.
- **Mem0 / Letta / MemPalace** — already referenced in KSA §1 as systems we explicitly chose NOT to fork.

---

## Research items

### R-T4-01 · Frequency-weighted retrieval ranking with decay

**Idea.** Replace K2b's flat tier-rank scoring with a per-user / per-entity score that includes how often the entity has been retrieved recently and how recently it was touched. Borrowed from the human "working memory → short-term → long-term" hierarchy.

**Concrete shape (sketch, not a plan):**

```
score = w1·tier_score
      + w2·similarity
      + w3·recency
      + w4·access_count_decayed
```

Where `access_count_decayed` follows an Ebbinghaus-style forgetting curve: increments every time knowledge-service retrieves the entity, decays exponentially over wall time so a stale "hot" entity eventually cools.

**What we already have.**
- K2b's `tier × rank_score` is a static two-component score.
- `is_pinned_for_context` is a binary salience flag (the user manually says "always include this").
- No per-retrieval counter, no decay.

**What's needed to build it.**
- A side table `glossary_entity_access_log` (or Redis sorted set) keyed by `(entity_id, user_id)` with `count` + `last_accessed_at`.
- knowledge-service must increment the counter after each successful context build that included the entity.
- K2b's selector reads the counter into the score formula.
- A nightly decay job.

**Trigger to graduate.** Real telemetry showing that Track-1's static tiered selector misses high-value entities the user has been working with intensively but that don't happen to be pinned. We won't know this until K5+ ships and we have a few weeks of usage.

**Risks.** Per-entity per-user counters scale poorly if either dimension is large. Probably fine for hobby scope but will need bounding for any multi-tenant deployment.

---

### R-T4-02 · Salience-driven auto-promotion

**Idea.** Instead of relying only on the user manually pinning entities, automatically increase an entity's "salience" score when external signals indicate it matters — analogous to how the human brain marks emotionally-charged memories with norepinephrine.

**Signals worth considering.**
- Entity was recently edited by the user (`updated_at` is fresh).
- Entity has many evidences (`evidences.count` is high — already tracked in glossary K3 review).
- Entity appears in the user's chat turn that the user thumbs-up'd (requires a feedback signal that doesn't exist yet).
- Entity appears in a chat turn that immediately preceded a manual session save / project switch (probably the user thought it was important).
- Entity has many `chapter_entity_links` rows (high "screen time" in the book).

**What we already have.**
- `is_pinned_for_context` for explicit user-driven salience.
- `evidences.count` and `chapter_entity_links.count` exist as raw signals.
- No automatic promotion.

**Trigger to graduate.** Track 2 ships chat-service feedback signals (thumbs-up / down or "this turn was bad") AND we have enough usage to run statistics on which signals correlate with what users later end up pinning manually.

**Risks.** Auto-promotion is hard to undo. False positives ("the system is shouting about an entity I don't care about") are more annoying than false negatives. Conservative defaults + manual override needed.

---

### R-T4-03 · Spaced repetition / forgetting curve on glossary entries

**Idea.** Apply the inverse of R-T4-01: actively *demote* entities that haven't been retrieved in N days. Reduces noise in tier-3 recent fallback. Borrowed from synaptic pruning.

**Concrete shape.**
- Add a `last_retrieved_at` column to `glossary_entities` (or a side table).
- knowledge-service updates it after each successful context build.
- A nightly job runs `UPDATE glossary_entities SET cold = true WHERE last_retrieved_at < now() - interval '30 days'` (or similar).
- K2b's tier-3 recent fallback excludes `cold=true` entities by default.

**What we already have.**
- `updated_at` is the only freshness signal — but it tracks edits, not reads.
- No "cold" / "archived" distinction beyond `is_archived` (which is user-driven).

**Trigger to graduate.** Tier-3 recent fallback is observed to surface stale entities that haven't been touched in months and aren't relevant to the current session.

**Risks.** Cold entities are still the user's data. Demote, don't delete. Make it visible in the entity editor that an entry has been demoted, with a one-click "warm up" button.

---

### R-T4-04 · Scheduled "sleep" consolidation job

**Idea.** Run an offline batch job (chat.txt's "2 AM background job") that:
- Merges semantically similar entities that are frequently accessed together
- Discovers new edges between entities (e.g., "Alice always appears in Chapter 7 with Bob → maybe edge `appears_with`")
- Refreshes `cached_name` / `cached_aliases` for entities that have had EAV churn
- Recomputes `search_vector` if the tokenizer or stopword list changed
- Compresses old chat turns into per-session summaries (knowledge_summaries `scope_type='session'`)

**What we already have.**
- `recalculate_entity_snapshot` runs synchronously on every EAV write — the trigger version of "sleep" but eager, not batch.
- KSA Track 2 has on-demand extraction jobs (user clicks "build extraction") but no scheduler.
- No cross-entity merging.

**Trigger to graduate.** Track 2 lands extraction jobs and we have at least one project where the user notices duplicate extracted entities (`Alice`, `alice`, `Alice the swordsman` all separate when they're the same person). At that point we need merge logic anyway.

**Risks.** Auto-merging entities is dangerous. Needs a "review queue" not direct DB writes. KSA Track 2 already plans this for extraction-pipeline output via `glossary_draft_suggestions`.

---

### R-T4-05 · Hierarchical / pointer-based retrieval

**Idea.** Don't shove the full entity into the prompt. Send a **pointer** (entity_id + name + 1-line description) and let the LLM ask for "expand entity X" via tool-calling if it actually needs the details. Borrowed from the hippocampal-index theory of memory.

**What we already have.**
- K3's `short_description` is exactly this — it's a 1-sentence summary that gets injected instead of the full description.
- K4.9 Mode 2 builder emits `<name>` + `<description>` (= short_description) in `<glossary>`, NOT the full EAV bundle.
- We don't currently support tool-calling expansion — chat-service would need to expose a "fetch full entity" tool.

**Trigger to graduate.** K5+ deployment shows that Mode 2's `<glossary>` block is the dominant token consumer in the system prompt and we want to push more entities in for less cost.

**Risks.** Tool-calling adds latency (extra LLM round-trip) and complexity. Probably overkill until we have ≥20 entities per turn.

---

### R-T4-06 · Iterative retrieval / expanded brute-force on miss

**Idea.** Today K4c extracts candidates and queries K2b once per candidate. If the merged result is empty (or below some quality threshold), automatically widen the search:
- Re-query K2b with the full message (no candidate filter)
- Re-query with stemmed / synonym-expanded versions of the candidates
- Walk the (future) Neo4j graph N hops from any matched anchor entities (Track 2)

The chat thread calls this "spiral outward from the seed."

**What we already have.**
- K4c does one parallel call per candidate.
- No fallback / expansion path.
- Track 2 will have a Neo4j graph with anchor nodes — that's where N-hop expansion lives.

**Trigger to graduate.** Telemetry shows Mode 2 returns empty `<glossary>` block more than X% of the time when the user clearly meant to reference an entity (which we'd need a feedback signal to detect).

---

### R-T4-07 · Cross-encoder reranker

**Idea.** Pull more candidates than we need from K2b (say 50), then run a cheap local cross-encoder model that reads query-and-chunk together to pick the best 5-10. The chat thread calls this "two-stage retrieval."

**What we already have.**
- K2b's `ts_rank` is a fast lexical scorer — not great for semantics.
- No reranker stage.
- Track 2 plans embedding similarity on entities (via per-project embedding model from a curated list — KSA §2.3) which would take the place of this.

**Trigger to graduate.** Track 2 embeddings ship and we have a quality baseline. Then measure whether adding a cross-encoder on top of embedding-based retrieval moves the needle.

**Risks.** Cross-encoders are expensive (~10-50ms per pair × 50 pairs = 500ms-2.5s of latency). Not viable until we can run a small one locally on every chat turn.

---

### R-T4-08 · Metadata-augmented retrieval ("Graph-Lite")

**Idea.** Without building a full knowledge graph, "tag" each glossary entity with structured properties and let queries filter on them. e.g., `{"location": "Kitchen", "characters": ["Tom"], "topic": "cats"}`. Then K2b can take a structured filter alongside the text query.

**What we already have.**
- `glossary_entities.kind_code` (character / location / item / ...) — a coarse tag.
- `tags TEXT[]` on `glossary_entities` — user-driven.
- `chapter_entity_links` — implicit "appears-in" relationship.
- No structured per-entity property bag accessible to K2b's query layer.

**Trigger to graduate.** Users are manually tagging entities heavily AND complaining that K2b doesn't filter on those tags. Cheap to bolt on once both halves exist.

---

### R-T4-09 · LFU-style chat history eviction (vs FIFO truncation)

**Idea.** chat-service currently replays the last N messages as `recent_message_count`. Instead, evict by least-frequently-used: messages the user has scrolled back to or referenced in subsequent turns get kept, regardless of age.

**What we already have.**
- chat-service uses a fixed `recent_message_count` (50 by default).
- K4a's `BuiltContext.recent_message_count` is a hardcoded constant per Mode.
- No "messages have an importance score" concept.

**Trigger to graduate.** K5 ships and we have telemetry showing that important early-session messages drop out before the chat session ends. (Hard to detect automatically — might need explicit user signal: "wait, I mentioned X earlier, don't forget it.")

**Risks.** Tracking "frequently referenced" requires extra state on every chat turn. Probably not worth it at hobby scale.

---

### R-T4-10 · Lazy / scope-limited graph updates

**Idea.** When extraction lands in Track 2 and we have a Neo4j graph, **don't rebuild the whole graph on every change**. Only re-process the "affected nodes" — e.g., if a single chapter is edited, only update the entities mentioned in that chapter's evidence rows.

**Status.** Already partially planned — Track 2's extraction jobs are scoped (you choose what to extract), not whole-graph rebuilds. But the chat thread's "Shadow Graph" idea (keep a fast vector RAG for new/changing data, only promote to KG once it stabilises) is a stronger version that we haven't designed.

**Trigger to graduate.** Track 2 extraction jobs are deployed and re-extraction cost is observed to be a bottleneck.

---

## Items deliberately NOT in this doc

These came up in the source thread but are out of scope or already addressed:

- **Embeddings / vector search.** Already in Track 2 (KSA §2.3 — per-project embedding model from a curated list). Not "research" — it's planned implementation.
- **Knowledge graph construction in general.** Already in Track 2 (KSA §3.4). Not research.
- **"Neo4j vs Postgres pgvector."** Already decided in KSA — Neo4j for the graph layer, Postgres for SSOT. Not research.
- **Replacing tsvector with embeddings.** Track 2.
- **Multi-tenant pricing / scaling.** Out of scope for hobby project.
- **Production observability.** Cross-cutting concern, owned by infra not knowledge-service.

---

## Process

When you find an item in this doc whose **trigger** seems to have fired:

1. Move the item out of this file into a new task in the relevant Track-N implementation plan.
2. If no Track-N file exists yet for the targeted phase, create one before starting work.
3. Update SESSION_PATCH "Recently cleared" with the item ID and how it graduated.
4. The triggers themselves are guesses written without real data — if a trigger never fires after a year, that's a signal to either delete the item or sharpen the trigger condition.

**What this doc is NOT for:**
- Capturing every cool RAG paper that comes out. Curate ruthlessly.
- Building features speculatively. If we can't articulate the trigger, the item isn't ready to research yet.
- Hiding deferred work from the K5/K6/etc. SESSION_PATCH "Deferred Items" list. Those items have a target phase. Items in *this* file are explicitly "no target phase yet — research first."
