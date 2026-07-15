from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    provider_registry_internal_url: str = "http://provider-registry-service:8085"
    usage_billing_service_url: str = "http://usage-billing-service:8086"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "loreweave"
    minio_secret_key: str
    minio_bucket: str = "lw-chat"
    minio_use_ssl: bool = False
    minio_external_url: str = ""  # Browser-accessible MinIO URL for presigned URLs
    audio_ttl_hours: int = 48         # Voice audio retention DEPLOY CEILING (WS-4.3): the max;
                                      # each user narrows within it via voice.audio_retention_hours
    audio_cleanup_interval_hours: int = 4  # How often to run cleanup
    internal_service_token: str
    statistics_service_internal_url: str = "http://statistics-service:8089"
    # R3 (D-PROACTIVE-DELIVERY) — the notification sink for the proactive check-in's content-free push.
    # Unconfigured ⇒ the proactive turn still persists its message; the push simply no-ops (best-effort).
    notification_service_internal_url: str = "http://notification-service:8091"
    # composition-service listens on 8093 (infra/docker-compose.yml PORT: "8093"), not 8092.
    # This default said 8092 and no env var overrode it, so EVERY chat-service call to
    # composition-service has been a ConnectError — and its only consumer
    # (CompositionClient.get_book_model_roles) is degrade-safe by contract, returning {} on
    # any failure. So the Book tier of the Chat & AI settings cascade (D-CHATAI-M1B) has
    # silently never applied, and nothing ever said a word. Found by the Track C book-state
    # probe, which is the first consumer that LOGS a dead source instead of shrugging.
    composition_service_internal_url: str = "http://composition-service:8093"

    # Track C Phase 2 — the rail driver (server-side book-state grounding in the pinned
    # rail). A deploy-time kill switch, NOT a user setting: it gates an always-on prompt
    # block, and a prompt regression is invisible to every unit test in the repo. Default
    # ON; set RAIL_DRIVER_ENABLED=0 to run the pinned rail ungrounded (the pre-Phase-2
    # behavior) — which is also how the A/B control run is measured.
    rail_driver_enabled: bool = True

    # Phase G · G2 — enforcement strength + the per-step hold cap. SIBLINGS of
    # rail_driver_enabled and, like it, DEPLOY-level (a kill-switch / ceiling, per the Settings
    # Boundary), NOT a per-user knob — the rail's other loop bounds (RAIL_REDRIVE_CAP,
    # REPEAT_READ_CAP) are platform constants too. A per-USER SET-1 tuning is a deferred,
    # flagged item (D-G2-SETUSER) — it needs the full ai-prefs pipeline + FE and is genuinely
    # debatable against this established deploy-level pattern.
    #   "enforce" (default) — a REQUIRED step is HELD to rail_required_nudge_cap redrives, then
    #                         released with an honest give-up (GOV-7). This is the S06 fix.
    #   "nudge"             — the gentle pre-G1 behavior: every step nudged once, never held.
    #   "off"              — the drive does not fire at all (equivalent to the pre-drive rail).
    rail_enforcement: str = "enforce"
    # The N in GOV-7's bounded auto-release. A ceiling a deploy narrows within; the effective
    # hold count. Clamped ≥1 at the consumer so a mis-set 0 can never disable the hold silently.
    rail_required_nudge_cap: int = 3

    redis_url: str = "redis://redis:6379"
    port: int = 8090

    # LLM streaming idle-read timeout (seconds) — the longest SILENT gap between
    # SSE frames before the stream is treated as stalled. Default 0 = UNBOUNDED
    # (no cap): a slow reasoning model may think silently for minutes before its
    # first token, and an idle cap would ReadTimeout mid-thought (as Gemma-4 26B
    # at high effort did). Set a positive value (env LLM_STREAM_IDLE_READ_TIMEOUT_S,
    # e.g. 300) to cap it. The SDK Client honours <=0 as read=None.
    llm_stream_idle_read_timeout_s: float = 0.0

    # K5 — knowledge-service integration. Optional/tunable via env so we can
    # raise the timeout if knowledge-service ever becomes a real bottleneck.
    knowledge_service_url: str = "http://knowledge-service:8092"
    knowledge_client_timeout_s: float = 0.5      # 500ms total per Track1 doc
    knowledge_client_retries: int = 1            # one retry on 5xx/transport
    # K21-B — execute_tool runs a real memory tool (memory_remember does
    # injection-neutralisation + a Neo4j write) and routinely exceeds the
    # build_context budget above. Tool execution gets its own, longer
    # per-call timeout so a slow write doesn't ReadTimeout (D-K21B-06).
    knowledge_tool_timeout_s: float = 30.0

    # ai-gateway P0 (2026-06-10) — TOOLS now go through the ai-gateway (MCP
    # federation), NOT knowledge directly. Hard cutover: tool definitions + MCP
    # execution target this URL; build_context (grounding) STAYS on
    # knowledge_service_url (gateway grounding is P6, not P0).
    ai_gateway_url: str = "http://ai-gateway:8210"

    # RAID C1 (DR-C1) — per-book steering. book-service serves the enabled
    # entries via GET /internal/books/{id}/steering; failures degrade to []
    # (the turn proceeds steering-free), so the timeout stays tight.
    book_service_url: str = "http://book-service:8082"
    book_steering_timeout_s: float = 2.0

    # DBT-11 / D-R14 — chat_messages.local_date is bucketed by the user's LOCAL day,
    # resolved from prefs.timezone via auth-service's token-gated internal profile.
    # Cached in-process; a failure degrades to the UTC day (the DB DEFAULT), so the
    # message write is never blocked on auth.
    auth_service_url: str = "http://auth-service:8081"
    user_timezone_timeout_s: float = 2.0
    user_timezone_cache_ttl_s: float = 900.0

    # T5 (Context Budget Law D2) — entity-presence intent gate. chat-service reads
    # the book's known-entity token set from glossary-service's internal route and
    # caches it in-process (A3: no new table). Used ONLY to decide whether a turn's
    # message references book lore → whether the expensive grounding pull is worth
    # it. Failure degrades to "gate open" (bias-to-include), so the turn is never
    # harmed by a glossary outage.
    glossary_service_url: str = "http://glossary-service:8088"
    known_entities_timeout_s: float = 2.0
    known_entities_cache_ttl_s: float = 300.0
    # T5 intent gate. As of 2026-07-06 (D-LONG-WORK-CONTEXT-MODE) this is a deploy
    # KILL-SWITCH / CEILING, not the enablement knob — per the Settings & Config
    # Boundary (env = ceiling, not a per-user behavior toggle). Default TRUE (deploy
    # allows); the actual per-turn enablement is the `context.mode` auto-detect
    # (`context_autodetect.resolve_context_pressure`): effective = AND(this, auto).
    # So on a small/thin book `mode=auto` keeps it OFF (the 2026-07-04 audit case,
    # unchanged) and on a big-lore book it turns ON. Set False to force-kill globally.
    t5_intent_gate_enabled: bool = True

    # ── WS-4C Half A — canon auto-capture ────────────────────────────────────────
    # Spec: docs/specs/2026-07-10-ws4c-half-a-canon-auto-capture.md
    # Every Nth assistant turn, POST the exchange to glossary's /capture-canon: the
    # entities it newly NAMED land in the book's review inbox as ai-suggested drafts
    # (never canon). This closes F4's write side — a name coined at turn 3 survives to
    # turn 40 because the glossary is re-read every turn.
    #
    # `canon_capture_enabled` is a deploy CEILING / kill-switch, NOT the enablement
    # knob (Settings & Config Boundary: env is never a per-user toggle). The per-user
    # knob is `knowledge_projects.canon_capture_enabled` (OPT-IN, default false),
    # surfaced on kctx and toggled in the project settings modal.
    # effective = AND(this, kctx.canon_capture_enabled). Default True here means
    # "the deployment permits it"; nothing captures until a user opts their project
    # in. Set False to force-kill capture platform-wide regardless of user choice.
    canon_capture_enabled: bool = True
    # Cadence — capture costs one small LLM call, billed to the user's own BYOK model.
    # 4 mirrors EXECUTIVE_EVERY_N_TURNS: often enough that a coined name survives the
    # window, rare enough that it is a rounding error on the turn's own cost.
    canon_capture_every_n_turns: int = 4
    # A turn shorter than this establishes nothing worth a model call ("ok", "go on").
    canon_capture_min_chars: int = 200
    # Per-side cap on the exchange text sent for extraction (glossary re-clamps).
    canon_capture_max_chars_per_side: int = 4000
    # The capture call is a background task; this bounds it so a hung local model can't
    # leak a task for the process's lifetime.
    canon_capture_timeout_s: float = 90.0

    # ── T6/D13a (Context Budget Law) — reversible dup-read collapse ──────────────
    # When a compaction pass fires AND this is ON, collapse EXACT-duplicate tool results
    # (the model re-read an unchanged resource) to a reference, keeping the latest full copy
    # — pure-waste reduction that loses no information and can't orphan a tool pair (it only
    # rewrites content). Raw turns stay in Postgres (reversible; this is the send-time view).
    # DEFAULT OFF for staged rollout on the load-bearing compaction path; flip on with the
    # T5-phase measurement. Fires ONLY when compaction already triggered (over budget), so it
    # is inert on normal turns even when enabled.
    compact_collapse_duplicates_enabled: bool = False

    # ── T6/D7 (Context Budget Law) — single-item tool-result overflow ceiling ────
    # A single MCP tool result that ALONE exceeds this many estimated tokens is withheld
    # at the dispatch site and replaced with a self-correcting overflow notice (re-call
    # with detail=summary / limit / fields / a range) — never a silent truncation, never a
    # window-blowing dump (the 146K case class). Applies ONLY to re-requestable data-dump
    # results, NOT to generative outputs (compose prose). Default 8000 (~32KB of text — a
    # single result that large is already pathological; normal results are <2K). 0 disables.
    tool_result_token_cap: int = 8000

    # ── T4 (Context Budget Law D4/D5) — story_state Core Memory Block ────────────
    # When ON, chat-service maintains a cached, bounded `story_state` block per session
    # (chat_session_blocks, owner-scoped + OCC) distilled from the message-INDEPENDENT
    # grounding prefix (kctx.stable_context), refreshed on cadence/hash (D5), and projects
    # it as a tail block ONLY when the live grounding prefix is EMPTY — the degraded /
    # gated-empty safety net (D4: a turn that lost its live bible still carries the last
    # good one). As of 2026-07-06 this is a deploy KILL-SWITCH / CEILING (default TRUE),
    # AND-ed with the `context.mode` auto-detect: effective = AND(this, grounding_enabled,
    # _ctx_tiers_allowed). So it projects the net only when auto-detect turns the tiers on
    # (a big-lore book) AND grounding is on — inert on small books (the block would just
    # duplicate the live prefix there). Set False to force-kill globally.
    story_state_block_enabled: bool = True

    # ── T2/D3 (Context Budget Law) — task-elastic compaction trigger ────────────
    # Today compaction fires at 0.75×effective_limit (near the window). With this
    # ON, it instead fires at the task-elastic `compute_target` (a SOFT budget far
    # below the window): a lore/continuity turn keeps a roomy target, a status-op /
    # smalltalk turn a leaner one — so a light turn compacts sooner (token win).
    # DEFAULT OFF (reverted 2026-07-04 by the optimization sweep — SUPERSEDED by C_persist).
    # The ephemeral task-elastic compaction re-summarizes the full history EVERY turn (it does
    # not persist), so on a long session it made ~11 summarizer calls (62% overhead) + 7×
    # latency at EQUAL recall — a net cost/latency REGRESSION vs the flat trigger
    # (docs/eval/context-budget/OPTIMIZATION-RESULTS-2026-07-04.md). `compact_persist_enabled`
    # replaces it: compact ONCE, persist, reuse. Set True only to A/B the old ephemeral path.
    # `task_weight` for a NON-grounding turn is `compact_light_task_weight` (grounding → 1.0).
    compact_task_elastic_enabled: bool = False
    compact_light_task_weight: float = 0.5

    # T6/D6 — post-compaction recovery hint. On a turn where compaction summarized
    # earlier turns, inject a system hint telling the model the raw history is
    # recoverable via the `conversation_search` tool (so a lossy summary that dropped a
    # specific fact leads to a SEARCH, not a guess/omission). DEFAULT OFF: a live A/B
    # (docs/eval/context-budget/T2-compaction-trigger-2026-07-04.md) found gemma-4-26b
    # IGNORES the hint — across 4 compacted runs it never called conversation_search
    # (weak local-model tool-use), so the hint adds ~60 tok/compacted-turn with no benefit
    # FOR OUR MODELS. Kept + flagged for a future stronger tool-following model to enable
    # and re-validate; independent of `compact_task_elastic_enabled`.
    compact_recovery_hint_enabled: bool = False

    # C_persist (T2 optimization) — PERSISTENT automatic compaction. When ON, a turn whose live
    # history exceeds the target persists the compact ({compact_summary, compacted_before_seq})
    # BEFORE loading, so later turns load the summary (via the W3 loader) instead of
    # re-summarizing the raw history EVERY turn — fixing the 62%-summarizer-overhead regression
    # the optimization sweep found (docs/eval/context-budget/OPTIMIZATION-RESULTS-2026-07-04.md).
    # DEFAULT ON (adopted 2026-07-04 — the optimization sweep WINNER; persist threshold =
    # compute_target(context_length)). On S1 (15-turn) it compacted ONCE then reused: ~46%
    # cheaper than the flat trigger + ~55% vs task-elastic, at C1-fast latency, EQUAL recall.
    # 30-turn multi-persist-cycle test: recall stable 7/9 across the summary-of-summary fold,
    # blind judge depth 5/5 · consistency 5/5 · no confabulation · no degradation — the agent
    # stays smart post-compression. Set False to restore no-persist (ephemeral tiers only).
    compact_persist_enabled: bool = True

    # T6/D6 — compaction BREADCRUMB. Before the lossy LLM summarizer runs, a DETERMINISTIC
    # extractor (compaction.extract_breadcrumb) pulls the highest-value, most-often-dropped
    # facts (number-bearing sentences, quoted names, proper-noun phrases) VERBATIM from the
    # turns being compacted away and leads the summary with them. Fixes the root cause the
    # T2 light-target A/B found: a lossy summary drops a fact ENTIRELY → the model has no
    # trace it existed → can't answer or even know to recover it (user insight 2026-07-04).
    # Deterministic (immune to summarizer variance), ~150 tok. Default ON — a strict
    # reliability improvement to any compaction that summarizes.
    compact_breadcrumb_enabled: bool = True

    # Agent Extensibility Registry (P1) — user/book prompt-only skills. chat-service
    # reads /internal/skills and injects them alongside the built-in SYSTEM_SKILLS,
    # honouring per-user disable + shadow. EVERY failure degrades to "constants only"
    # (the built-in skills still work), so a registry outage never breaks a turn.
    agent_registry_url: str = "http://agent-registry-service:8099"
    agent_registry_timeout_s: float = 2.0

    # Context Budget Law sealed-decision #1 — retrieval mode is `prepend`/`hybrid` for ALL
    # by default (true `pull`/JIT is deferred to a future strong-model capability). Surfaced
    # in the per-turn contextBudget frame so the Inspector shows WHICH retrieval discipline
    # ran (the D1 substrate flips this to `pull` when a strong-model pull mode lands). Not a
    # model name (provider-gate exempt) — a retrieval-strategy label.
    retrieval_mode: str = "prepend"

    # ARCH-1 C3 — default stream event format when a request sends no
    # x-loreweave-stream-format header. "legacy" (LoreWeave SSE vocabulary) or
    # "agui" (AG-UI protocol). Per-request header overrides this; the default
    # stays "legacy" until the AG-UI frontend (C4) ships.
    default_stream_format: str = "legacy"

    # D-T2-03 — degraded-mode fallback when knowledge-service is unreachable
    # or returns an error. Must agree with knowledge-service's Mode 1 + Mode 2
    # `recent_message_count` (which also defaults to 50). Both services read
    # env var RECENT_MESSAGE_COUNT so a tune stays in sync.
    recent_message_count: int = 50

    class Config:
        env_file = ".env"


settings = Settings()
