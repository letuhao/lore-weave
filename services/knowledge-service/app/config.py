from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Required — service fails to start if any of these are missing.
    knowledge_db_url: str
    glossary_db_url: str
    internal_service_token: str
    jwt_secret: str

    # KM5 — RS256 admin-signing public key (SPKI/PKIX "PUBLIC KEY" PEM, or
    # base64 of it). The public half of auth-service's KMS admin key; when set,
    # System-tier admin actions verify an RS256 admin JWT against it (INV-T2).
    # Unset (default) → System-tier admin is DISABLED, those paths 503. Same
    # contract + env-var name as glossary (ADMIN_JWT_PUBLIC_KEY_PEM) so one
    # platform admin token works across both services.
    admin_jwt_public_key_pem: str = ""

    # Optional with defaults.
    redis_url: str = "redis://redis:6379"
    # FD-22 — emit a Redis wake signal when an extraction job starts so worker-ai
    # picks it up immediately instead of waiting for its next poll. Kill-switch;
    # disabling (or an empty redis_url) cleanly reverts to pure polling.
    extraction_wake_enabled: bool = True
    log_level: str = "INFO"
    port: int = 8092

    # K4b — glossary-service HTTP client for Mode 2 fallback selector.
    glossary_service_url: str = "http://glossary-service:8088"
    glossary_client_timeout_s: float = 0.5
    glossary_client_retries: int = 1

    # K4c — cross-layer dedup tunable. Number of distinct keyword tokens
    # that must overlap between an L1 summary and a glossary entity for
    # the entity to be dropped as redundant. Lower = more aggressive
    # dedup. 2 is the conservative default; raise to 3 if you find the
    # dedup is dropping entries it shouldn't.
    dedup_min_overlap: int = 2

    # D-T2-03 — Mode 1 + Mode 2 `recent_message_count` returned in the
    # context response. chat-service replays the last N messages of the
    # session when this many are requested. PAIR: chat-service's
    # `settings.recent_message_count` has the same default; both read
    # env var RECENT_MESSAGE_COUNT so a tune stays in sync. Mode 3 has
    # its own tighter constant (20) in full.py — by design.
    recent_message_count: int = 50

    # K6.1 — per-layer timeouts inside the context builder. If any
    # layer exceeds its budget the builder skips that layer and
    # continues with the remaining pieces. Total ceiling defaults to
    # L0 + L1 + glossary = 400ms because layers run sequentially.
    context_l0_timeout_s: float = 0.1
    context_l1_timeout_s: float = 0.1
    context_glossary_timeout_s: float = 0.2
    # K18.1 — Mode 3 L2 fact selector budget. Neo4j 1-hop + optional
    # 2-hop + negation listing. Tighter than glossary because the L2
    # queries run against an indexed graph, not an HTTP service.
    context_l2_timeout_s: float = 0.3
    # K18.3 — Mode 3 L3 passage selector budget. Embed(1 text) via
    # provider-registry + Neo4j vector query + MMR. The embed call
    # dominates; 2s leaves headroom for local LM Studio on small
    # chunks while still capping a pathologically slow cloud model.
    context_l3_timeout_s: float = 2.0
    # K18.7 — Mode 3 memory-block token budget. The full L0+L1+glossary
    # +facts+passages+absences payload can easily exceed useful limits
    # on a small-context model. When over budget, the Mode 3 builder
    # drops in reverse-priority order: passages (lowest score first)
    # → absences → background facts → glossary trimmed. L0, project
    # instructions, L1 summary, negative facts, and the CoT
    # instructions block are protected.
    mode3_token_budget: int = 6000

    # Track 4 P1 — salience-weighted retrieval (R-T4-01). Blends the P0
    # entity_access_log signal (recency-decayed retrieval frequency) into the
    # glossary entity ranking so entities THIS user keeps returning to rank higher
    # (and survive budget-trim longer). Read-time Ebbinghaus decay — no cron.
    # WEIGHT DEFAULTS TO 0.0 (byte-identical to today) — measure-before-flip: only
    # raise it once the POC eval shows the learned signal beats static ranking.
    salience_access_weight: float = 0.0
    salience_half_life_days: float = 14.0
    # Track 4 P3a — graph-native promotion (evidence/mention/edit-recency).
    # Same measure-before-flip discipline; default 0.0 = no Neo4j fetch, no re-order.
    salience_promote_weight: float = 0.0
    salience_promote_half_life_days: float = 30.0
    # Track 4 P3b — thumbs-feedback attribution term (chat.message_feedback →
    # entity_access_log.feedback_score). Same discipline; default 0.0 = inert.
    salience_feedback_weight: float = 0.0
    # Track 4 P4 (R-T4-06) — ONE widened (relational, 2-hop) L2 retry when the
    # intent names entities but the first pass found ZERO facts. Additive recall
    # on the empty path only; default ON (a miss-path fallback, not a re-ranker).
    context_l2_retry_widened: bool = True

    # WS-4C (2026-07-09) — admit memory_remember / llm_tool_call facts into the
    # per-turn L2 auto-recall. These project-level "we decided X / user prefers Y"
    # facts are unanchored (no :ABOUT edge) and written at 0.7 (below the 0.8 L2
    # gate) + NULL from_order, so the entity-anchored L2 path never surfaced them —
    # the F4 continuity write-side gap. This branch selects them project-wide at
    # their own lower floor. Kill-switch default ON.
    context_l2_tool_facts: bool = True
    context_l2_tool_fact_min_confidence: float = 0.7
    # Cap on tool-facts injected per turn (they are rate-limited at write time, but
    # bound the block so a long-lived project can't bloat every turn's context).
    context_l2_tool_facts_limit: int = 20

    # M1a (2026-07-06) — passage→graph anchor bridge. After L2 facts + L3 passages
    # are retrieved, 1-hop-expand entities the PASSAGES surfaced that the message
    # didn't anchor, injecting the new relations into the L2 facts block. Deploy
    # CEILING / kill-switch (default ON) — a per-turn Mode-3 assembly step, not a
    # per-user setting. See docs/eval/context-budget/M4-graph-anchor-bridge-2026-07-06.md.
    context_passage_graph_expansion_enabled: bool = True

    # M1b (2026-07-06) — working-scope boost. When the editor `<Chat>` panel is
    # open on a chapter, chat-service forwards that chapter_id; the L3 passage
    # ranker resolves it to a chapter_index and multiplicatively boosts passages
    # WITHIN `window` chapters of it (linear falloff), so "what I'm editing right
    # now" outranks equally-relevant-but-distant lore — the Aider open-file idea
    # (research 04 §2). Intent-INDEPENDENT (separate from the recency term, which
    # only fires for HISTORICAL/RECENT_EVENT). Inert on every non-editor turn
    # (reader/glossary chat send no chapter_id) and when the chapter has no
    # ingested passages. `boost=0.0` ⇒ OFF (byte-identical). Conservative default:
    # a same-chapter passage gets ×1.3, so a distant passage with materially higher
    # cosine still wins — bounds the reorder-a-far-true-answer regression risk.
    context_working_scope_boost: float = 0.30
    context_working_scope_window: int = 2

    # M-recall (2026-07-07) — CJK/VI dictionary anchor resolution. The intent
    # classifier can't segment scriptio-continua, so `select_l2_facts` anchored on
    # its tokens returns 0 facts for Chinese queries even when the answer is a 1-hop
    # relation (measured: 3/12 wangu goldens). When the message carries a non-ASCII
    # letter, Aho-Corasick match it against the project's known entity-name dictionary
    # and UNION the hits into the L2/bridge anchors. Deploy kill-switch (default ON);
    # a per-turn Mode-3 recall step, not a per-user setting. `ttl_s` bounds dictionary
    # staleness (a new entity is anchorable within the window); `cap` bounds the
    # 1-hop fan-out; `min_len` drops 1-char generic matches.
    context_dict_anchor_enabled: bool = True
    context_dict_anchor_ttl_s: float = 300.0
    context_dict_anchor_cap: int = 12
    context_dict_anchor_min_len: int = 2

    # M-recall role-resolution — when the message names the lead by ROLE ("主角"/
    # "the protagonist") the dictionary can't match it, so anchor the project's
    # most-central entity (highest relation degree) instead. Recovers "主角的母亲是谁"
    # (measured: 4/5 remaining wangu role-queries). Additive + gated on a strict
    # protagonist-term set. Deploy kill-switch (default ON); reuses the dict-anchor TTL.
    context_role_anchor_enabled: bool = True

    # D-BACKFILL-NO-SCOPE-LIMIT (2026-07-06) — the published-passage backfill embeds
    # EVERY published chapter of a book, and on the embedding-model PUT it runs
    # SYNCHRONOUSLY in-request. On a large book (万古神帝: 4232 published chapters) that
    # is a runaway whole-book embed that a client timeout only hides. Cap the INLINE
    # (embedding-PUT) backfill: when the book has more than this many published
    # chapters and no explicit chapter_range, skip the inline backfill and let a scoped
    # extraction job ingest passages instead. The extraction-start backfill is bounded
    # to the job's chapter_range separately. Deploy ceiling; 0 ⇒ never skip (old behavior).
    kg_backfill_max_inline_chapters: int = 200

    # K16.2 — book-service HTTP client for chapter counts in cost estimation.
    book_service_url: str = "http://book-service:8082"
    book_client_timeout_s: float = 5.0

    # KG-ML M2 — translation-service internal client: fetch a chapter's ACTIVE
    # translation text (for dual-indexing vi passages on `translation.published`).
    translation_service_url: str = "http://translation-service:8087"
    translation_client_timeout_s: float = 10.0

    # wiki-llm M1 (option A) — lore-enrichment hosts the authored de-bias
    # BookProfile (worldview/voice/era/language/anachronism). The wiki
    # generator reads it over the internal token to shape its prompt. The
    # client caches per book for `book_profile_cache_ttl_s` so a wiki-gen job
    # over N entities makes ONE call per book, while an edited profile is
    # still picked up within the TTL (a failed read is NOT cached → retries).
    lore_enrichment_service_url: str = "http://lore-enrichment-service:8093"
    lore_enrichment_client_timeout_s: float = 5.0
    book_profile_cache_ttl_s: float = 60.0

    # wiki-llm M6 — batch wiki-generation orchestrator.
    # NOTE (D-JOURNEY-WIKI-FLAG): `wiki_gen_enabled` is DEPRECATED + no longer gates
    # the stream consumer, which now ALWAYS runs (it is idle/free until a user-
    # triggered, cost-gated job arrives — gating it off-by-default silently pended
    # every wiki-gen job). Spend is bounded per-request (max_spend_usd + the
    # cost-gated trigger), not by this platform env. Kept only for back-compat;
    # default True. cost_per_article is the per-article ESTIMATE charged against a
    # job's max_spend_usd. prompt/pipeline version stamp the C7 build_inputs
    # fingerprint (Phase-2 staleness).
    wiki_gen_enabled: bool = True
    wiki_gen_cost_per_article_usd: float = 0.05
    wiki_gen_passage_limit: int = 8
    wiki_prompt_version: str = "wiki-v1"
    wiki_pipeline_version: str = "wiki-m6"

    # D-WIKI-M8-EVAL-PLUS Phase 2 — automatic-sampled groundedness judge. After a wiki
    # article generates, with probability `sample_rate` it is judged via the learning
    # service's on-demand judge endpoint (the SAME Phase-1 endpoint, reusing the fresh
    # article + FULL context sources). OFF by default + rate 0.0 = zero cost; both an
    # enable flag AND a positive rate AND a model are required to sample. Best-effort:
    # a judge call never blocks or fails generation.
    wiki_llm_judge_enabled: bool = False
    wiki_llm_judge_sample_rate: float = 0.0          # P(judge) per generated article, [0,1]
    wiki_llm_judge_model_ref: str = ""               # judge model UUID (BYOK user_model)
    wiki_llm_judge_model_source: str = "user_model"
    learning_internal_url: str = "http://learning-service:8094"

    # D-WIKI-M8-FEWSHOT — inject gold AI-draft→human-edit pairs as few-shot exemplars
    # into wiki generation (the model learns the editorial style humans apply). OFF by
    # default (adds tokens to every prompt). max_examples bounds the count fetched once
    # per job; the glossary gold-pairs endpoint truncates each body server-side AND
    # hard-caps the count at 5 (goldPairsMaxLimit) — a value above 5 here is clamped.
    wiki_fewshot_enabled: bool = False
    wiki_fewshot_max_examples: int = 3

    # P1 (2026-05-23) — /internal/parse body size cap. Default 200 MiB
    # matches book-service's maxImportSize at services/book-service/internal/api/import.go.
    # H3 fix: explicit ceiling — without this, a misconfigured caller could
    # OOM the worker on a hot loop with multi-100MB bodies.
    max_parse_body_bytes: int = 209_715_200

    # K17.2 — provider-registry BYOK client for LLM extraction calls.
    # Calls provider-registry's /internal/proxy/v1/chat/completions
    # endpoint, which resolves the user's BYOK model from
    # (user_id, model_source, model_ref) and forwards to the upstream
    # provider with credentials injected server-side. Knowledge-service
    # never sees the provider API key.
    provider_registry_internal_url: str = "http://provider-registry-service:8085"
    # LLMs are slow. 60s is the plan-row budget; extractors that need
    # longer should split their work rather than raise this.
    provider_client_timeout_s: float = 60.0

    # E5B — cross-encoder rerank (raw-search junk-rejection). Routes through
    # provider-registry /internal/rerank. `rerank_enabled` is a kill-switch
    # (off ⇒ pure E5 behavior). `min_rerank_score` 0.30 is data-calibrated on
    # the eval corpus (negatives < 0.30 < real positives). top_n bounds the
    # cross-encoder passes; timeout is load-tolerant for cold-start.
    # D-RERANK-NOT-BYOK: the rerank MODEL is no longer a hardcoded env name —
    # it is the per-project `knowledge_projects.rerank_model` (BYOK user_model),
    # resolved per-user by provider-registry. NULL project model ⇒ rerank skipped.
    rerank_enabled: bool = True
    rerank_top_n: int = 30
    min_rerank_score: float = 0.30
    # Measured 2026-06-08 (bge-reranker-v2-m3, 30 CJK passages): warm p50 44ms /
    # p95 60ms (GPU-class); cold-reload (after TTL idle-unload) ~1.7s. 5s covers
    # cold with margin yet degrades fast on a real hang. PROD: scale the rerank
    # service's TTL to demand (high TTL ⇒ stays warm under traffic, only the
    # first-after-long-idle pays cold) — see rerank guide §6.6 (D-RAWSEARCH-RERANK-LATENCY).
    rerank_timeout_s: float = 5.0

    # K11.2 — Neo4j connection (Track 2 extraction graph). Empty
    # `neo4j_uri` means "skip Neo4j init at startup" — Track 1 dev
    # keeps working without Neo4j running. Set to e.g.
    # bolt://neo4j:7687 to enable. When set, the lifespan hook
    # fail-fasts on unreachable Neo4j (per the K11.2 spec).
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = "loreweave_dev_neo4j"
    # Driver-level connection acquisition timeout. Short on
    # purpose so a misconfigured URI fails the startup check
    # within ~5s rather than hanging the container.
    neo4j_connection_timeout_s: float = 5.0

    # K21.7 — max `memory_remember` tool calls the LLM may make per
    # chat session before the rate limiter rejects further writes. A
    # memory-pollution guard, not a security boundary: the limiter
    # fails open if Redis is unavailable.
    tool_remember_limit_per_session: int = 10

    # Q4b-feed — retention window for extraction_run_samples (the transient
    # items+source buffer feeding the online LLM judge). Pruned on startup.
    # 7 days is long enough for the sampled eval-runner to consume a run;
    # past that the row is dead novel-text weight.
    extraction_run_sample_ttl_days: int = 7

    # mui #1c K-detect — coreference detection (proposes merge candidates to
    # glossary). PO-locked 2026-06-07: on-demand endpoint + opt-in auto-hook
    # (default OFF); LLM-verify config-gated on-by-default with score-only
    # fallback when no judge model is configured. Signals = name + KG-structural
    # (no embeddings). Only glossary-anchored entities are candidates.
    coref_enabled: bool = True
    # Auto-run a detect pass at end-of-book extraction. OFF by default — LLM
    # verify costs tokens and L1 locks human-confirm-every-merge, so detection
    # cadence is a deliberate choice, not every extraction run.
    coref_auto_on_extraction: bool = False
    # A pair must blend to >= this to be a candidate (name·w_name + struct·w_struct).
    coref_score_floor: float = 0.5
    coref_name_weight: float = 0.6
    coref_struct_weight: float = 0.4
    # Ignore long-tail entities with very few mentions (noise).
    coref_min_mentions: int = 2
    # Hard cap on scored pairs taken forward to LLM-verify+propose per pass —
    # bounds LLM cost on a dense graph.
    coref_max_pairs: int = 200
    # Per-kind ceiling on entities loaded from Neo4j for one pass.
    coref_max_candidates_per_kind: int = 500
    # Blocking: drop name char-bigram buckets larger than this (common-char
    # explosion guard — keeps blocking sub-quadratic).
    coref_max_bucket: int = 50
    # Config-gate for the LLM verify step. Effective ONLY when coref_judge_model
    # is set; otherwise the pass degrades to score-only (propose all above floor).
    coref_llm_verify: bool = True
    coref_judge_model: str = ""
    coref_judge_user: str = ""
    coref_judge_model_source: str = "platform_model"


settings = Settings()
