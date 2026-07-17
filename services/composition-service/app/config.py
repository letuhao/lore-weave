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

    # close-21-28 D-G5-DRIVE-EXEC — rules-mode propose auto-compile (platform default ON, PO-decided
    # 2026-07-16). In `rules` mode the propose is a DETERMINISTIC transcription of an authored outline —
    # there is NO LLM judgment between propose and compile, so a valid parse materialises its structure
    # inline instead of depending on a second `plan_compile` call. The S06 flagship exposed that a weak
    # agent reliably PROPOSES (valid numbered-header spec → arcs) but drops the follow-up compile
    # (DR-G5-REROLL: 6 live gemma-4 rolls proposed, 0 compiled); the rail drive can hold+re-prompt but by
    # G1 design does not execute the deterministic step. When ON, a rules-mode propose that parses ≥1 arc
    # auto-compiles every arc so `structure_node>0` is a consequence of the governance-driven propose, not
    # a coin-flip on the model — idempotent ($0, re-links by target, preserves human edits). Default ON
    # because rules mode has nothing to review between propose and compile; set FALSE to restore a
    # propose→review→compile checkpoint. (Autocompile only fires when the spec artifact carries a real
    # list of arcs, so a mocked/degraded read is a safe no-op.)
    planforge_rules_autocompile: bool = True

    # D-PLANFORGE-PROPOSE-BLIND — the DEPLOY CEILING for propose-existing-state grounding (OQ-2).
    # This is a platform-wide MAX the per-user `ground_on_existing` run flag narrows within:
    # `effective = AND(this, ground_on_existing)`. Default OFF at ship — the RICHER cast/spine/systems
    # grounding is a behaviour change gated behind the A/B eval; a behaviour-changing default fails
    # CLOSED. Flip ON org-wide once the eval proves grounding improves the plan. This is NOT a per-user
    # knob (that is the run flag) — it is the ceiling. (The always-on arc digest `_ground_llm_source`
    # is unaffected: it is today's baseline and never regresses.)
    planforge_ground_on_existing_allowed: bool = False

    # Internal service URLs — consumed by the M3 client wrappers.
    knowledge_internal_url: str = "http://knowledge-service:8092"
    glossary_internal_url: str = "http://glossary-service:8088"
    book_internal_url: str = "http://book-service:8082"
    llm_gateway_internal_url: str = "http://provider-registry-service:8085"
    # KAL — the single versioned knowledge read/write boundary (INV-KAL). Reads the
    # KAL exposes (roster, facts, canonical, search, timeline, neighborhood) MUST go
    # through here, never the owning services' /internal/* knowledge routes directly.
    # Env KNOWLEDGE_GATEWAY_URL; auth is X-Internal-Token + a forwarded X-User-Id.
    knowledge_gateway_url: str = "http://knowledge-gateway:3000"

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
    # `source` is ALWAYS "user_model": provider-registry /internal/embed rejects
    # model_source="platform_model" (it resolves creds from user_models only) — the
    # "platform" embed model is a BYOK-as-platform credential (a bge-m3 user_model owned
    # by the reserved platform-owner below), the local-rerank precedent, NOT the
    # platform_models table (which can't serve embeds). A "platform_model" default here
    # would 400 every motif embed, so it defaults to the only value the endpoint accepts.
    motif_embed_model_source: str = "user_model"
    motif_embed_model_ref: str = ""              # platform embedding model id (a user_model_id); W3 asserts non-empty
    motif_embed_owner_id: str = ""               # RECONCILE D2 — reserved platform-owner row
    # Retrieval (W3/W2): the SQL pre-filter ceiling (rows loaded for the cosine pass),
    # the top-K returned, and the minimum cosine for a planner-bindable match.
    motif_candidate_ceiling: int = 500           # RECONCILE D2 (W3) — pre-filter cap
    motif_retrieve_top_k: int = 10
    motif_min_score: float = 0.30
    # Anti-repetition (W2): max times one motif may be applied within a single book
    # before the planner/UX warns (the cowrite craft-nudge made structural — §11).
    motif_max_reapply: int = 3
    # Planner connective-tissue floor (W2 MD-3): min match-margin a candidate must
    # clear over the next-best before the planner auto-binds without a connective hint
    # (below it, the splice adds a bridging beat). Surfaced as config per W2's request.
    motif_connective_floor_margin: float = 0.08
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
    # ── Wave-2 worker-op knobs (W2-F0 freeze — homed here so W8/W9/W5 fill their
    # engine modules, NOT config.py). Cost estimates feed the Tier-W confirm $-dialog
    # (heuristics, NOT provider pricing — pricing still resolves from provider-registry).
    motif_mine_estimate_usd_book: float = 0.50      # W8 — per-book mine $ estimate
    motif_mine_estimate_usd_corpus: float = 2.00    # W8 — whole-corpus mine $ estimate
    arc_import_estimate_usd: float = 1.00           # W9 — deconstruct $ estimate
    conformance_run_estimate_usd: float = 0.30      # W5 — arc/chapter extract-diff $ estimate
    # W8 mining (P3): the motif_beat extractor version (knowledge-service cross-service
    # contract) + default min support before a beat-pattern becomes a draft motif.
    # v2 (D-W8-MOTIF-BEAT-LLM-EXTRACTOR): the mine worker runs tag-beats first, so beat/thread
    # axes are the GENERIC namespace:local of each event's mined_motif_code (corpus-reusable)
    # rather than the Option-A title/chapter_id. Backward-compatible: an untagged event still
    # falls back to Option A, so a v2 reader over a v1/cold corpus just mines fewer patterns.
    motif_mine_extractor_version: str = "motif_beat@v2"
    motif_mine_min_support: int = 3
    # W9 import/deconstruct (§12.3/§12.4): the LLM-direct deconstruct model. EMPTY by
    # default (NO hardcoded model name — provider-gateway invariant); resolved from the
    # job input (model_source/model_ref) when present, else this PLATFORM default. The
    # handler fails closed (ValueError) if neither yields a model_ref — so a deconstruct
    # never silently runs on an unconfigured model. Source defaults to 'platform_model'
    # (the local-rerank-as-platform precedent — resolve via provider-registry).
    motif_deconstruct_model_source: str = "platform_model"
    motif_deconstruct_model_ref: str = ""        # platform chat model id; resolved at call time
    # The per-chunk character cap for the deconstruct MAP pass (rides the P1/P2 rails —
    # chunk the imported content so each map call fits the window; the arc-reduce sees
    # the abstract per-chunk extractions, never the raw text — §12.4).
    motif_deconstruct_chunk_chars: int = 12000
    # Abstraction post-check (§12.6 guardrail): the min source-token shingle overlap
    # ratio above which a generated beat/example is treated as near-verbatim source
    # retelling → scrubbed. Lower = stricter. 0.0 disables (never — the guardrail is
    # load-bearing); the default flags substantial verbatim n-gram reuse.
    motif_deconstruct_verbatim_shingle: int = 6     # shingle size (consecutive words)
    motif_deconstruct_verbatim_max_overlap: float = 0.50  # max share of source shingles allowed

    # ── Autonomous authoring runs (RAID Wave D2, DR-D / 07S §10). The v1 driver's
    # per-unit spend fallback when the engine didn't meter a cost (inline path
    # leaves generation_job.cost_usd at 0) — budget accounting must still move or
    # the cap never trips. Poll knobs cover the worker (202) path: the seam polls
    # the generation_job to terminal; timeout must exceed the worst-case chapter
    # generation wall-clock (mirror chapter_inflight_stale_secs).
    authoring_unit_estimate_usd: float = 0.05
    authoring_job_poll_secs: float = 2.0
    authoring_job_poll_timeout_secs: int = 1800
    # The seam's minted service-bearer TTL: generation runs for minutes and the
    # engine REUSES the bearer to persist the draft afterwards (actions.py
    # _GENERATE_BEARER_TTL_S precedent) — cover generation + persist.
    authoring_draft_bearer_ttl_secs: int = 1800
    # ── D4 durable driver (RAID Wave D4). DRIVER_MAX_INFLIGHT: cap on concurrent
    # per-run driver tasks in THIS process (campaign-service max_inflight spirit).
    # A start/resume beyond the cap leaves the run `running` but unclaimed — the
    # periodic sweep resumes it once a slot frees (durable by design).
    authoring_driver_max_inflight: int = 2
    # Sweep cadence: at startup + every N secs, re-claim `running` runs whose
    # heartbeat is stale (a restart killed their in-process driver task) and
    # resume them from current_unit. 0 disables the loop.
    authoring_sweep_secs: float = 30.0
    # Stale-heartbeat threshold. The heartbeat is bumped once per UNIT, so this
    # MUST exceed the worst-case single-unit wall-clock
    # (authoring_job_poll_timeout_secs = 1800) or the sweep would steal a run
    # whose driver is alive but mid-unit.
    authoring_heartbeat_stale_secs: int = 2400
    # D4 completion notification — notification-service HTTP ingest (mirrors the
    # translation-service chapter_worker producer; X-Internal-Token via
    # internal_service_token). Best-effort: a notify failure never affects a run.
    notification_service_internal_url: str = "http://notification-service:8091"
    # ── D5 per-unit continuity critic (RAID Wave D5, DR-D / 07S §10 — "interrupt
    # on severe; else Run Report"). The enable flag rides run params, NOT config:
    # params.critic_enabled defaults TRUE (an autonomous run needs the net); an
    # explicit falsy value disables. Severity thresholds map the 4-dim judge_prose
    # scores (0-5, engine/critic.py): any affirmed canon violation OR any judged
    # dim <= severe_score → 'severe' (breaker: the run PAUSES — not fails — for
    # human review); else any dim <= warn_score → 'warn' (lands on the Run Report
    # only); else 'ok'. Cost: the LLM SDK Job carries no cost field (same reason
    # the drafting seam falls back to authoring_unit_estimate_usd), so a COMPLETED
    # critique bills authoring_critic_estimate_usd into spent_usd; a degraded one
    # ('critic unavailable') bills 0 — the spend may never have reached a model.
    authoring_critic_severe_score: int = 1
    authoring_critic_warn_score: int = 2
    authoring_critic_estimate_usd: float = 0.01


settings = Settings()  # type: ignore[call-arg]
