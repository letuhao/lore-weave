# Glossary AI-Pipeline v2 — Architecture & Scenario-Based Evaluation

- **Date:** 2026-06-06
- **Branch:** `glossary/ai-pipeline-v2`
- **Status:** Architecture DRAFT + ATAM-lite evaluation. Pre-implementation.
- **Builds on:** `docs/03_planning/101_DATA_RE_ENGINEERING_PLAN.md`, `KNOWLEDGE_SERVICE_ARCHITECTURE.md`
- **Companion specs:** `docs/specs/2026-06-06-glossary-kg-writeback.md` (mui #1), `docs/specs/2026-06-06-entity-resolution-merge.md` (mui #1c, TBD)

---

# PART I — ARCHITECTURE

## 1. Problem

The glossary pipeline predates RAG + knowledge-service. It behaves like CRUD: entities are authored/upserted, search is FTS, wiki is a static template, no inference. Meanwhile the AI capability lives in *other* services (knowledge-service: LLM extraction + Neo4j KG + embeddings; lore-enrichment: generate/verify; composition: canon co-writer). The four **seams between them are underwired**, producing the "rời rạc / lãng phí / CRUD" feeling:

1. **KG → glossary writeback MISSING** — knowledge extracts entities but never proposes them back to the SSOT.
2. **Glossary retrieval ignores embeddings** — `select-for-context` (used by chat + composition) uses FTS, not the vectors knowledge already computed.
3. **Grounding is re-implemented per consumer** — enrichment, composition, chat each build their own.
4. **No entity resolution** — one real entity referred to by many names becomes many entities, and nothing detects or merges them.

## 2. Design principles (inherited, not invented)

| Principle | Source | Consequence here |
|---|---|---|
| **SSOT-first** | 101 plan | glossary (Postgres) stays authoritative; Neo4j is derived. Writes flow glossary→KG; AI proposes *into* glossary, never owns canon. |
| **Human-gate / quarantine** | H0 enrichment, draft status, K18 | AI *proposes*, human *disposes*. Discovery → `draft`; enrichment → `proposed`; merge → suggestion. Nothing becomes canon silently. |
| **Best-effort degradation** | knowledge/composition clients | A downstream service down → degrade (queue, FTS fallback, empty grounding), never 500 or block the primary path. |
| **Idempotent, event-driven sync** | outbox + Redis Streams | At-least-once delivery; MERGE keyed on stable IDs; replays are no-ops. |
| **No hardcoding** | de-bias NEUTRAL_PROFILE, provider-registry | Thresholds via config; models via registry; worldview via BookProfile. |
| **Reversibility for destructive ops** | recycle-bin, soft-delete | Merge/promote/reject must be undoable. |

## 3. Target architecture — the unifying idea

Glossary stops being a passive store and becomes the **curation surface over an AI discovery-and-resolution loop**. The single load-bearing UX primitive is an **"AI Suggestions" inbox** — a type-agnostic review queue. Every AI output is *a kind of reviewable suggestion*:

```
                         ┌──────────────────────────────────────────────┐
                         │     glossary-service  (SSOT, curation)        │
   user curates ───────► │  entities · attrs · aliases · wiki · canon    │
                         │                                                │
                         │     ┌────────  AI Suggestions Inbox  ───────┐  │
                         │     │ • new-entity proposals  (mui #1)      │  │
                         │     │ • merge candidates       (mui #1c)    │  │
                         │     │ • [future] attr/relation enrichment   │  │
                         │     └───────────────────────────────────────┘  │
                         └───▲───────────────────────────────┬────────────┘
            promote/merge    │  (events: entity_updated,      │ propose (best-effort)
            (canon writes)   │   entity_merged)               │
                             │                                ▼
                         ┌───┴────────────────────────────────────────────┐
                         │   knowledge-service  (derived AI layer)         │
                         │  Neo4j KG · entity embeddings · LLM extraction  │
                         │  • discovery (Pass 1/2)         → propose #1    │
                         │  • coreference detection        → propose #1c   │
                         │  • semantic retrieval (vectors) → serve #4      │
                         │  • merge-into + alias_map (EXISTS)              │
                         └─────────────────────────────────────────────────┘
```

### 3.1 Component responsibility split (the invariant)

| Concern | Owner | Notes |
|---|---|---|
| Canonical entities, attributes, aliases, wiki | **glossary** (Postgres SSOT) | The only place canon lives. |
| LLM extraction, embeddings, KG relations, similarity | **knowledge** (Neo4j derived) | All AI compute. Never owns canon. |
| Proposing discoveries / merges / enrichments | **knowledge → glossary** | Best-effort, lands as suggestion. |
| Approving (promote / confirm-merge / reject) | **glossary + FE** (human) | The gate. |
| Merge *execution* on canon | **glossary** (NEW endpoint) | SSOT-first; emits event; KG follows. |
| Merge *execution* on graph | **knowledge** (`merge-into` EXISTS) | Driven by glossary event. |

## 4. The four mui

### Mui #1 — KG→glossary writeback (FOUNDATION) — spec'd, CLARIFY locked
~80% infra exists (`propose_entities` client, `find_gap_candidates`, kind-map, draft gate). Wire it at job completion; land discoveries as `draft` + tag `ai-suggested`; FE inbox to promote/reject; reject = soft-archive + tombstone. **Establishes the inbox + propose pattern everything else reuses.**

### Mui #4 — Semantic retrieval for glossary (LOW RISK, runs early/parallel)
`select-for-context` gains a vector path reusing knowledge embeddings (with FTS fallback). Independent of #1, and it **also produces the entity-similarity signal #1c needs** — so doing it early is leverage, not just cleanup.

### Mui #1c — Entity resolution / merge (XL, builds on #1's inbox + #4's vectors)
Detect coreferent entities (one real entity, many names) and merge them. **Detect = automatable; merge = human-gated + reversible.** Three layers:
- **DETECT** (knowledge): blocking (ANN + same-kind + same-project) → multi-signal score (embedding cosine + name signals + KG structural co-occurrence) → optional LLM verify with evidence → emit merge-candidate clusters.
- **REVIEW** (glossary inbox): merge-candidate cards with evidence; human confirms/rejects. Tiered: very-high (one-click/opt-in auto), medium (manual).
- **EXECUTE** (glossary, NEW): merge endpoint repoints all entity_id FKs (`chapter_entity_links`, `entity_attribute_values`+`evidences`+`attribute_translations`, `entity_enrichments`, resolves `wiki_articles` UNIQUE conflict), soft-deletes loser, writes a **merge journal** for un-merge. Emits event → knowledge runs existing `merge-into` + writes `entity_alias_map` (anti-resurrection).

### Mui #3 — Shared grounding port (REFACTOR, last)
Consolidate the per-consumer grounding into one context/grounding port, after #1/#4/#1c stabilize the data shapes.

### Dependency order
```
#1 writeback ──► #1c merge (needs inbox)
       │
#4 semantic retrieval ──► (feeds #1c detection signal)
       │
       └────────────────► #3 grounding port (last; consolidates consumers)
```
Recommended sequence: **#1 → #4 (parallel/early) → #1c → #3.**

## 5. Data-flow & event topology (additions only)

- `extract-entities` (writeback) → entity `draft` + `ai-suggested` tag → emits `glossary.entity_updated` (actor=pipeline) → knowledge MERGE (idempotent on `glossary_entity_id`).
- merge confirm → glossary repoint+soft-delete+journal → emits `glossary.entity_merged{loser, winner}` → knowledge `merge-into` + `entity_alias_map` write.
- reject → `inactive` + `ai-rejected` tombstone → writeback dedup skips that name next job.
- All new cross-service writes are **best-effort with queue-on-outage**; all consumers idempotent.

## 6. Key invariants (must hold post-change)

- **INV-1** No AI output reaches canon without a human action. (draft/proposed/suggestion gates.)
- **INV-2** Merge is reversible until purge. (journal + soft-delete.)
- **INV-3** glossary↔KG eventually consistent; replays/dupes are no-ops. (idempotent MERGE.)
- **INV-4** Every cross-service AI call degrades gracefully. (no 500, no block.)
- **INV-5** All similarity/detection is tenant-scoped (user_id+project_id). No cross-tenant comparison.
- **INV-6** Thresholds & models are config/registry-resolved, never hardcoded.

---

# PART II — SCENARIO-BASED EVALUATION (ATAM-lite)

Method: derive prioritized quality attributes, write concrete scenarios (stimulus → architectural response → measure), walk each through the target architecture, then extract **Risks / Non-risks / Sensitivity points / Tradeoff points**. Scope = the four mui above.

## 7. Quality attributes (prioritized)

| # | Attribute | Why it dominates here |
|---|---|---|
| QA1 | **Data integrity / correctness** | SSOT corruption or unapproved canon is the worst outcome. |
| QA2 | **Precision > recall** | False suggestions/merges erode trust faster than missed ones; merge is destructive. |
| QA3 | **Controllability (human-in-loop)** | Core product philosophy; AI assists, never decides canon. |
| QA4 | **Consistency (SSOT ⇄ derived KG)** | Divergence/orphans break downstream (chat, composition, wiki). |
| QA5 | **Cost & performance** | Token spend (LLM verify) + O(n²) detection + retrieval latency. |
| QA6 | **Modifiability / extensibility** | Inbox must absorb new suggestion types cheaply. |
| QA7 | **Availability / graceful degradation** | Multi-service; any node may be down. |
| QA8 | **Security / multi-tenancy** | BYOK, per-user/project isolation, injection defense. |
| QA9 | **Usability (review burden)** | Too many low-value suggestions = abandonment. |

## 8. Scenarios & walkthroughs

**S1 — Discovery does not pollute canon (QA1, QA3).**
*Stimulus:* extraction discovers 50 entities in a chapter. *Response:* all land `status='draft'` + `ai-suggested`; canon query (`status='active'`) unchanged. *Measure:* entities reaching canon w/o human action = **0**. → **Satisfied** (draft gate, INV-1). Architecturally native.

**S2 — Low-quality proposal is filtered/rejected and stays gone (QA2, QA9).**
*Stimulus:* knowledge proposes a weak/hallucinated entity. *Response:* threshold (`conf≥0.7 & mention≥3`) filters most; survivors are draft-only; user rejects → `ai-rejected` tombstone; next job's name-dedup skips it. *Measure:* rejected name not re-proposed. → **Satisfied if** tombstone dedup path is correct (see R-tombstone). Quality rests on the threshold (**SP1**).

**S3 — Coreference is detected (QA2 recall).**
*Stimulus:* 姜子牙 / 太公望 / 子牙 exist as 3 entities. *Response:* detection blocks by kind+project, ANN neighbors on embeddings, scores embedding+name+KG-co-occurrence, LLM verifies, emits 1 merge cluster. *Measure:* cluster recall. → **Feasible**: 太公望↔姜子牙 share no characters but co-occur in scenes — **KG structural signal is what catches this**, embeddings+name alone would miss it. Detection quality is sensitive to the signal blend (**SP2**) and blocking (**SP3**).

**S4 — Homonym is NOT falsely merged (QA1, QA2). [stress]**
*Stimulus:* two different 李靖 (or 妲己-person vs fox-spirit) exist. *Response:* multi-signal score should diverge on context; if borderline, surfaced as low-tier suggestion, human rejects; **never auto-merged at default settings**. *Measure:* destructive false-merges = 0. → **RISK if auto-merge tier enabled or SP2 mis-tuned.** This is the sharpest tradeoff (**TP3**). Mitigation: default human-confirm, auto-merge opt-in only for the top tier, and even then kind-aware + LLM-verified.

**S5 — Un-merge restores state (QA1 reversibility). [stress]**
*Stimulus:* user merges A→B, then realizes A and B were distinct. *Response:* merge journal (repointed FKs + loser snapshot) + soft-deleted loser → un-merge repoints back and restores. *Measure:* post-un-merge state == pre-merge state. → **RISK**: journal does not exist yet (R5); attribute-conflict resolution and `wiki_articles` UNIQUE make perfect restoration non-trivial (**TP2**).

**S6 — Event loss/duplication doesn't diverge stores (QA4). [growth]**
*Stimulus:* `entity_merged` event delivered twice / lost then replayed. *Response:* knowledge `merge-into` idempotent; MERGE on `glossary_entity_id`; alias_map dedup. *Measure:* no orphan node, no double-merge. → **Satisfied** (INV-3, NR1/NR2). At-least-once + idempotent is already the house pattern.

**S7 — Detection scales to a large project (QA5). [growth]**
*Stimulus:* project has 5,000 entities; run full detection. *Response:* blocking reduces pairs from ~12.5M (O(n²)) to ~n·k via ANN+same-kind; LLM verify only top candidates within a budget cap. *Measure:* pairwise comparisons & token spend. → **Satisfied only with blocking** (**SP3**); naive pairwise is infeasible. Cost-cap pattern exists (enrichment job runner) to reuse.

**S8 — Glossary retrieval gets better without new infra (QA5, QA4). [use]**
*Stimulus:* chat/composition calls `select-for-context`. *Response:* vector path reuses knowledge embeddings; falls back to FTS if unavailable. *Measure:* relevance uplift vs FTS; added latency/coupling. → **Satisfied** but introduces a **TP1** coupling (glossary now depends on knowledge embeddings + the per-project model choice).

**S9 — A service is down (QA7). [stress]**
*Stimulus:* knowledge-service down during writeback / retrieval / detection. *Response:* writeback queues in `extraction_pending`; retrieval falls back to FTS; grounding returns []; detection simply doesn't run. *Measure:* primary paths still 200; no extraction blocked. → **Satisfied** (INV-4, NR3).

**S10 — Add a new suggestion type (QA6). [growth]**
*Stimulus:* later add "attribute enrichment" proposals to the inbox. *Response:* inbox is a type-agnostic queue; add a card renderer + a propose source; no surface rebuild. *Measure:* effort localized. → **Satisfied** — this is the payoff of the unifying-inbox decision.

**S11 — No cross-tenant comparison (QA8). [stress]**
*Stimulus:* detection runs; could it compare entities across users? *Response:* blocking + vector query filter `user_id`+`project_id`. *Measure:* zero cross-tenant candidate pairs. → **Satisfied if** scoping is enforced in the detection query (must be verified — R7). `find_entities_by_vector` already post-filters by scope.

**S12 — Project with embeddings off (QA7, QA5). [exploratory]**
*Stimulus:* extraction/embeddings disabled for a project. *Response:* detection degrades to name+structural signals; retrieval = FTS. *Measure:* features still function at lower quality. → **Satisfied** (degradation is layered, not all-or-nothing).

## 9. Findings

### Sensitivity points (single knobs that swing a quality attribute)
- **SP1 — writeback threshold (`conf`/`mention`).** Swings QA2 (precision) vs QA9 (recall/usefulness). No K18 validator yet ⇒ this is the *only* quality gate for writeback. Must be config, start conservative.
- **SP2 — merge similarity score blend + cutoff.** Swings QA1/QA2. The embedding-vs-structural-vs-name weighting decides whether 太公望 is caught and whether two 李靖 are wrongly joined.
- **SP3 — blocking strategy (ANN K, same-kind, scope).** Swings QA5 (cost) vs QA2 (recall). Under-blocking → O(n²) blowup; over-blocking → missed clusters.
- **SP4 — per-project embedding model/dimension.** Swings QA5/QA4 and cross-project comparability of retrieval+detection.

### Tradeoff points (one decision pulls two attributes opposite ways)
- **TP1 — semantic retrieval coupling.** Better ranking (QA5) ↔ glossary now depends on knowledge availability + model choice (QA7/QA4). *Mitigated* by FTS fallback.
- **TP2 — `wiki_articles` UNIQUE(entity_id) under merge.** Data model simplicity ↔ merge/un-merge complexity (QA1). Two merged entities with wiki articles is a genuine conflict requiring a policy (keep winner / merge bodies / archive loser).
- **TP3 — auto-merge tier.** Automation/usability (QA9) ↔ false-merge risk (QA1/QA2). The single most dangerous knob; default to human-confirm.
- **TP4 — SSOT-first merge.** Canon authority/consistency (QA1/QA4) ↔ added sync latency before KG reflects the merge (QA5). Accepted; eventual consistency is already the model.

### Risks
- **R1** — Writeback quality rests solely on SP1 (no validator). *Mitigation:* conservative config defaults; revisit when K18 lands.
- **R2** — Inbox review burden could overwhelm (QA9) if thresholds loose → trust erosion. *Mitigation:* tiering + batching + start strict.
- **R3** — Homonym false-merge (S4) if auto-merge enabled / SP2 mis-tuned. *Mitigation:* human-confirm default, kind-aware, LLM-verify, reversibility.
- **R4** — Detection cost blowup (S7) without disciplined blocking (SP3). *Mitigation:* ANN+same-kind+scope blocking; budget cap.
- **R5** — glossary has **no merge machinery at all**; FK repoint correctness across 6+ tables is the largest, most error-prone build. Reversibility journal does not exist. *Mitigation:* transactional repoint + journal + extensive tests; reuse knowledge's merge as a reference design.
- **R6** — Tombstone dedup correctness (S2) depends on extending `findEntityByNameOrAlias`. *Mitigation:* covered in #1 spec PLAN.
- **R7** — Cross-tenant leakage in detection (S11) if scope filter omitted. *Mitigation:* enforce scope in blocking query; test.

### Non-risks (explicitly cleared)
- **NR1** — glossary→KG re-sync loop: idempotent, draft-bounded, verified low-risk.
- **NR2** — KG-side merge: `merge-into` + `entity_alias_map` already exist and are battle-shaped.
- **NR3** — graceful degradation: established pattern across all clients.
- **NR4** — controllability: human-gate is architecturally native (draft/H0/proposed), not bolted on.

## 10. Verdict

The target architecture is **sound and largely additive** — it extends the existing SSOT⇄KG, event-driven, human-gated design rather than fighting it. The unifying "AI Suggestions inbox" gives high modifiability (S10) at low conceptual cost. The dominant attribute (QA1 integrity) is protected by native gates and the reversibility requirement.

**The architecture's risk is concentrated in mui #1c (merge)**, specifically the new glossary merge-execution path (R5), the false-merge tradeoff (TP3/R3), and reversibility (R2/S5). Sequencing #1 and #4 first is correct: they are low-risk, deliver value immediately, and #4 hardens the very signal #1c depends on. **Recommendation:** proceed #1 → #4 → #1c → #3; treat #1c as `/amaw` (destructive + schema + multi-service); lock SP1–SP4 as config; make the merge journal a non-negotiable part of #1c's definition of done.
