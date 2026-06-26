"""composition-service settings (LOOM Composition V0 — M0).

pydantic-settings BaseSettings — the service fails to start if any
required secret/DSN is missing (CLAUDE.md: no hardcoded secrets).
Mirrors knowledge-service's config shape; single DB (loreweave_composition).
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Required — service fails to start if any of these are missing.
    composition_db_url: str
    internal_service_token: str
    jwt_secret: str
    # DEDICATED confirm-token signing secret (key-split from internal_service_token).
    # The Tier-W confirm token is minted/verified with THIS secret, NOT the envelope
    # gate token — so rotating/compromising one does not affect the other. Fail-closed:
    # the service refuses to start if unset (env CONFIRM_TOKEN_SIGNING_SECRET).
    confirm_token_signing_secret: str

    # Optional with defaults.
    redis_url: str = "redis://redis:6379"
    log_level: str = "INFO"
    port: int = 8093

    # Phase 3 M4 — composition batch-job worker. When True, the batch endpoints
    # (decompose/generate/selection-edit/chapter-gen/stitch) create a job + enqueue
    # on the composition_jobs stream + return 202 (a separate `python -m app.worker`
    # process runs the LLM compute off the request path); GET /jobs/{id} polls.
    # Default False → today's inline behavior verbatim (zero contract change until
    # the FE adopts the 202 + poll). The worker consumer + its sweep run only when on.
    composition_worker_enabled: bool = False
    composition_job_sweep_secs: int = 60
    composition_job_sweep_timeout_secs: int = 900

    # Internal service URLs — consumed by the M3 client wrappers.
    knowledge_internal_url: str = "http://knowledge-service:8092"
    glossary_internal_url: str = "http://glossary-service:8088"
    book_internal_url: str = "http://book-service:8082"
    llm_gateway_internal_url: str = "http://provider-registry-service:8085"

    # Packer budget knobs (M4) — declared here so config is stable across
    # milestones; unused until the packer lands.
    pack_token_budget: int = 6000

    # V1 Phase A1 — diverge→converge. Number of candidate drafts per auto generate
    # (the only K-multiplied call; cost ~K drafts). A3 makes this adaptive per
    # scene; until then it's the fixed default. K=1 degenerates to the V0 loop.
    compose_diverge_k: int = 3
    compose_diverge_temperature: float = 0.8

    # V1 Phase A3 — decompose planner + adaptive K.
    # plan_max_chapters: refuse to decompose a book with more active chapters
    # than this (bounds the per-chapter Level-2 LLM fan-out). plan_*_scenes:
    # the LLM-chosen scene count per chapter is clamped to this range.
    # plan_high_tension_threshold: scene tension at/above which adaptive K spends
    # the full ceiling (climax/midpoint beats); below it spends less. Tension is
    # the EXISTING 0..100 scale (outline_node.tension / reasoning policy, which
    # gates "high dramatic tension" at >=70) — NOT 1-5.
    plan_max_chapters: int = 40
    plan_min_scenes_per_chapter: int = 1
    plan_max_scenes_per_chapter: int = 6
    plan_high_tension_threshold: int = 70

    # S2 compress — when the packer's raw "story so far" (prior-scene prose)
    # exceeds this many chars, compress the OLDER portion into a state summary
    # (keeping the last N immediate paragraphs verbatim) so long chapters don't
    # blow the prompt budget. ~4 chars/token → 6000 chars ≈ 1500 tokens.
    pack_compress_recent_threshold_chars: int = 6000
    pack_compress_keep_immediate: int = 2

    # L1b timeline RECENT-WINDOW (LOOM-32 /review-impl MED#1) — the knowledge
    # timeline endpoint orders event_order ASC + LIMIT, so an unbounded query deep
    # in a long book returns the OLDEST prior events (chapter 1), not the
    # most-recent-prior chapters that drive continuity. Bound the lookback to the
    # last N chapters before the scene's chapter (after_order window) so the carry
    # is RECENT + scalable. 0 → no lower bound (carry all prior; small books).
    pack_timeline_recent_chapters: int = 5

    # Chapter-assembly modes (LOOM chapter-assembly-modes). The default mode for a
    # Work that hasn't set `settings.assembly_mode`: 'per_scene' (the validated
    # per-scene engine + B3 stitch) or 'chapter' (B2 single-pass from the plan).
    # A per-request override may still pick the other mode. Default per_scene =
    # co-write parity; autonomous long-form sets 'chapter' on the Work.
    composition_assembly_mode_default: str = "per_scene"
    # Output CEILINGS for the two chapter-level paths (cap the proportional
    # plan-sizing below — a long chapter is one pass and needs room, but never
    # beyond the request field's le=8192). chapter-gen/stitch size their max_tokens
    # from the plan's scene count × chapter_gen_per_scene_tokens, clamped here.
    chapter_gen_max_tokens: int = 8192
    stitch_max_tokens: int = 8192
    # Per-scene output budget for the proportional chapter/stitch sizing (so a
    # multi-scene chapter gets room instead of a flat cap that silently truncates).
    chapter_gen_per_scene_tokens: int = 700
    # FD-1 / narrative_thread S2 — cap on NEW promise threads a single generated
    # passage may open, so a verbose detector can't flood the ledger. The pass
    # itself is per-Work opt-in via `work.settings["narrative_thread_enabled"]`.
    narrative_thread_max_open_per_scene: int = 5
    # FD-1 / narrative_thread S3 — how many open promises to RE-INJECT into the
    # generation pack (the F2 lever). list_open is priority-ordered, so this is the
    # top-N highest-priority open threads; protected in the budget but bounded so a
    # large ledger can't crowd out canon/beat.
    pack_open_promises_cap: int = 8
    # Cycle-2 in-flight guard staleness window: the chapter-level generate/stitch
    # guard REJECTS a concurrent job, so a `running` job orphaned by a mid-
    # generation crash/kill would otherwise lock that chapter out forever (no
    # reaper exists). A job `running` longer than this is presumed dead and no
    # longer blocks. Must exceed the worst-case generation wall-clock (slow local
    # LLM + reflect iters on a long chapter); too short → the guard leaks a
    # double-run, too long → a longer post-crash lockout. Default 30 min.
    chapter_inflight_stale_secs: int = 1800
    # Periodic stale-job reaper (D-COMP-CHAPTER-INFLIGHT-REAPER): the in-process
    # sweep interval. Every N secs it marks jobs `running`/`pending` longer than
    # `chapter_inflight_stale_secs` (the shared "running this long ⇒ dead" window)
    # as failed — the global backstop for chapters the guard's opportunistic reap
    # never revisits. 0 disables the sweep (the opportunistic reap still runs).
    job_reaper_sweep_secs: int = 600
    # B3 stitch input cap (MED-3) — when the chapter's concatenated scene drafts
    # exceed this many chars, keep the earliest + latest scenes and elide the
    # middle (head+tail keep). ~4 chars/token → 24000 ≈ 6000 tokens of input.
    stitch_max_input_chars: int = 24000
    # S2 compress input cap (D-COMP-COMPRESS-INPUT-CAP) — bound the older
    # story-so-far prose fed to compress() so a very long chapter doesn't blow
    # compress's OWN prompt. Keep the most-recent chars (continuity-relevant).
    compress_max_input_chars: int = 24000

    # ── Narrative motif library (F0 + 00-RECONCILE §1). ONE platform embedding model
    # for ALL motif vectors (R1.1.2/B-1) — NOT the user's BYOK model — so cross-tier
    # cosine is correct and a clone can copy the vector. Resolved via provider-registry
    # /internal/embed (the embedding_client) as a (source, ref) pair, PLATFORM-fixed.
    # The owner_id is the reserved platform-owner identity whose BYOK credential holds
    # the platform embedding model (the local-rerank-as-platform precedent — D2). W3
    # fails closed if model_ref/owner are unset before its embed pipeline runs.
    motif_embed_model_source: str = "platform_model"
    motif_embed_model_ref: str = ""              # platform embedding model id; W3 asserts non-empty
    motif_embed_owner_id: str = ""               # RECONCILE D2 — reserved platform-owner row
    # Retrieval (W3/W2): the SQL pre-filter ceiling (rows loaded for the cosine pass),
    # the top-K returned, and the minimum cosine for a planner-bindable match.
    motif_candidate_ceiling: int = 500           # RECONCILE D2 (W3) — pre-filter cap
    motif_retrieve_top_k: int = 10
    motif_min_score: float = 0.30
    # Anti-repetition (W2): max times one motif may be applied within a single book
    # before the planner/UX warns (the cowrite craft-nudge made structural — §11).
    motif_max_reapply: int = 3
    # Mining gate (P3/W8): mined drafts below this judge score are shown, never
    # silently added (no silent drop — §11).
    motif_mine_min_judge: float = 0.60
    # Per-user quotas (B-4 — mirror D-MCP-BOOK-CREATE-QUOTA). The publish/adopt
    # ceilings the W1 router + W4 MCP pre-check; 0 = unlimited (dev default off).
    motif_max_public: int = 0
    motif_max_adopt: int = 0
    # ── Motif conformance (W5, §2.4) — the binary, ADVISORY beat-conformance dim
    # written into generation_job.critic. OFF by default → zero LLM cost on the hot
    # path (mirrors narrative_thread_enabled). `calibrated` flips true ONLY after the
    # calibration harness passes AND a human sets it — it drives the UI honesty label
    # (false → "unverified self-report"). Never claim calibrated from a single-model
    # self-host run (panel_safety, §5).
    motif_conformance_enabled: bool = False
    motif_conformance_calibrated: bool = False
    # The 0-100 tension-band half-width (§2.2): the planned band is centre±halfwidth.
    motif_conformance_tension_halfwidth: int = 15
    # Random-sample rate for non-high-tension bound scenes (§5.2): high-tension/
    # high-weight beats are ALWAYS judged; the rest at this %, so cost stays bounded.
    motif_conformance_sample_random_pct: int = 20
    # RECONCILE D3 — the Tier-W usage-billing precheck endpoint (W4's mine/import
    # ops; composition-service has no billing client → net-new in W4). Reuses
    # internal_service_token for the internal call.
    usage_billing_service_url: str = "http://usage-billing-service:8086"


settings = Settings()  # type: ignore[call-arg]
