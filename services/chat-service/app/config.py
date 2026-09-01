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
    # CP-3.6 — the suspended-run maintenance loop, which is `sweep_expired_runs`'s missing owner.
    # The interval is NOT the TTL: a run expires after 6 hours, and until this loop existed the
    # turn it belonged to went on advertising `awaiting_input` until the next process restart.
    #
    # SECONDS, not hours, and deliberately so. An hours-only knob with a 1-hour floor cannot be
    # WATCHED RUN inside a test window — and a mechanism nobody can observe running is precisely how
    # `sweep_expired_runs` stayed dead for months behind a docstring. The floor stays (60s) so a
    # zero can never turn this into a busy loop.
    suspended_run_maintenance_interval_seconds: int = 3600
    # Retention PAST expiry, not the TTL. A row stops being resumable when it expires; it stops
    # being EVIDENCE only once the turn it justifies has been resolved. See sweep_expired_runs.
    suspended_run_retention_days: int = 30
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

    # DQ-T56(1) — THE WHOLE-TURN CEILING. The longest a chat turn may run in TOTAL before the
    # platform ends it and records that it did not complete. Distinct from the idle cap above,
    # and deliberately so: the idle cap competes with a slow FIRST token and is the thing that
    # ReadTimeout'd Gemma-4 26B mid-thought, which is why it stays 0. This one cannot, because
    # it does not care how long a silence is — only how long the whole turn has run.
    #
    # 900s is "well above any legitimate think time", and that is a MEASUREMENT, not a feel:
    # over 8,222 live turns paired to their immediate reply (the pairing matters — joining a
    # user row to the next assistant row ANYWHERE in the session pairs an orphaned turn with a
    # LATER turn's reply and invented a 1,874s tail that does not exist),
    #
    #     no-tool turns   2,265   p50 6.7s   p95 22.5s   p99 59.1s   p99.9 185.5s   max 234.4s
    #     tool turns      5,957   p50 4.7s   p95 29.0s   p99 65.2s   p99.9 228.5s   max 364.9s
    #
    # so the ceiling sits ~2.5x above the longest turn ever recorded here and ~4x above p99.9.
    # The tool-turn row is a FLOOR, not an exact figure: those rows are INSERTed at the first
    # tool boundary and UPSERTed at the finish, so `created_at` marks the first tool call rather
    # than the end. It is quoted as the weaker bound it is.
    #
    # What the ceiling bounds, from provider-registry's own job rows: `chat` completions that
    # ended `completed` top out at 182.8s, while `failed` ones reach 1,858.9s — a turn hanging
    # server-side for 31 minutes long after the browser gave up at ~180s. That dangling turn is
    # the whole point; today nothing ends it.
    #
    # 🔴 IT IS NOT FREE, AND SAYING SO HERE IS DELIBERATE. Expiry cancels the tool loop where it
    # stands, so a tool mid-write can be cut off. That hazard is not NEW — a client disconnect
    # already cancels the same generator (`except (asyncio.CancelledError, GeneratorExit)` in
    # `_emit_chat_turn`) and fires at ~180s, five times sooner. This adds a server-side trigger
    # for a path that already exists, at a threshold no measured healthy turn reaches.
    #
    # 0 disables it (env LLM_TURN_CEILING_S), restoring the unbounded behaviour exactly.
    llm_turn_ceiling_s: float = 900.0

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

    # ── ext-tasks durable gate (2026-07-19-mcp-tasks-durable-gate) ────────────────
    # The ACTIVATION switch (spec §4.2, step f). When True, chat-service declares the
    # ext-tasks extension in its tool-call `_meta`, so a capability-gated domain tool
    # (composition_create_derivative) returns a durable TASK the driver holds/confirms;
    # when False, the domain falls back to today's confirm_token (byte-unchanged). A
    # DEPLOY-level kill-switch: default False so the whole ext-tasks path stays dormant
    # until it is live-verified end to end, then flipped on.
    tasks_gate_enabled: bool = True

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

    # ── F7c (2026-07-19) Lazy-context enforcement — index+load-on-demand ─────────
    # docs/plans/2026-07-19-lazy-context-enforcement.md. Three DEPLOY-LEVEL
    # kill-switches (SIBLINGS of rail_driver_enabled — NOT per-user knobs; per the
    # Settings & Config Boundary, env is the sanctioned home for a platform-wide
    # ceiling / A-B control, never a per-user behavior toggle). Each ENFORCES the
    # index+load-on-demand discipline the platform already had for tools (tool_list/
    # tool_load) but never applied to skills / studio panels / the workflow rail.
    #
    # DEFAULT TRUE (the enforce step). Validated by the capability-first A/B on the
    # target MEDIUM model gemma-4-26b (eval/run_lazy_context_ab_eval.py): skill usage
    # 3/3=3/3, panel selection 6/6=6/6 — NO capability loss — at ~5.4k tokens/turn
    # saved on a studio co-writer turn. Set the env var to 0 to revert a lever to the
    # pre-F7c behavior (the kill-switch, and how the A/B control run is measured).
    #
    # `lazy_skill_bodies` — when ON, a NON-curated turn injects only the L1 skill
    # INDEX (skill_metadata_block, ~117 tok) instead of force-injecting full L2
    # skill bodies (~5-7k). The Intent→Skill Router still preloads the matching
    # skill's L2 (smart preload), pins + mode-bindings (plan_forge/co_write) still
    # inject L2, and the new `load_skill` control tool pulls any skill's body on
    # demand. The domain's TOOLS stay hot regardless (surface_hot_domains is
    # surface-driven, not skill-body-driven) — only the verbose prose defers.
    lazy_skill_bodies: bool = True
    # `skill_router_preload` — the Intent→Skill Router's SMART PRELOAD. When ON (shipped
    # behaviour) the router cosine-ranks the turn's intent against every skill and preloads
    # the top `ROUTER_MAX_ADDITIONS` L2 bodies. When OFF the turn keeps its base/pinned/
    # mode-bound skills and the L1 index, and the model pulls a body itself with
    # `load_skill` — the twin of `tool_load`.
    #
    # 🔴 ADDED AS THE ARM OF AN A/B, NOT AS A PRODUCT LEVER, and defaulted TRUE so the
    # CONTROL is the shipped path byte-for-byte. DQ-T90 measured why the arm is worth
    # running: ALL 66 of 66 pairs of distinct skills are more similar to each other than the
    # 0.35 floor a skill must clear to be injected, so no cap and no threshold can rank
    # them — the correct domain misses by a median 0.0266 in a field 0.1537 wide. Meanwhile
    # `load_skill` is advertised on 5,982 messages, has never failed (66 of 66 ok), and is
    # used in 7 sessions, against 123 for `tool_load`. The hypothesis this flag exists to
    # test is that the preload SUPPRESSES the mechanism that would fix the row: the model is
    # handed two bodies it did not ask for, with no signal they are the wrong ones.
    #
    # THE BAR, so an arm cannot win by being cheaper: does the CORRECT skill's body end up
    # PRESENT on more than 64.8% of turns (the router's own measured hit rate)? Whether
    # `load_skill` was called is NOT the measure — a turn that proceeds without guidance is
    # a loss, because absent guidance is the defect this question was opened on.
    skill_router_preload: bool = True
    # CP-2.7 — THE ROUTE. When ON, a turn's advertised set comes from
    # `contracts/agent-runtime-manifest.json` and from nothing else: no core tools, no
    # `find_tools`, no frontend extras. "Old declarations are not hidden. They are ABSENT."
    #
    # 🔴 **OFF BY DEFAULT, AND THAT IS A MEASUREMENT DECISION RATHER THAN CAUTION.** The legacy arm
    # is CP-2's CONTROL GROUP (ARCHITECTURE §7). CP-1.9 spent a whole item establishing that a
    # control perturbed by changes nobody decided invalidates the comparison before it starts — so
    # with this flag off, the advertise chokepoint is byte-identical to what it was.
    #
    # The manifest is committed as `declarations: []`, so turning this on today advertises NOTHING.
    # That is the honest state of an empty membrane, and it is what makes CP-2.7's item A — the
    # agent SAYS it has no declarations — a thing that can be observed rather than argued.
    agentruntime_arm: bool = False
    # `lazy_workflow_directive` — when ON, the WS-5 workflow-preference block lists
    # workflow SLUGS + short titles only (drops each workflow's full description,
    # ~1-2k), keeping the "call workflow_load(<slug>) FIRST" directive that steers
    # the model to load the rail's real detail on demand.
    lazy_workflow_directive: bool = True

    # `oneshot_deadvertise_mode` — how a COMPLETED one-shot create tool (one whose target
    # already exists, e.g. kg_project_create on a book that already has a KG project) is kept
    # off the agent surface so a weak model can't loop on it (the (B) idempotent-write breaker
    # only short-circuits each *call*; this stops the model *attempting*). A/B modes measured
    # 2026-07-25 (docs/eval/e2e-newcomer): the winner is set as the default.
    #   "off"       — advertise as today; only the runtime short-circuit breaker bounds the loop.
    #   "existence" — DETERMINISTIC: don't advertise the create when the turn's context already
    #                 carries the resource id it would produce (decided ONCE per turn at
    #                 surface-build → prefix-cache-stable, the Manus lesson; never advertised so
    #                 the model never attempts — schema-gating, the strongest "can't call it").
    #   "session"   — REACTIVE + persistent: on the first `created:false`, drop the tool from the
    #                 session hot-set (activated_tools) so it never returns this session.
    #   "per_turn"  — REACTIVE + transient: on the breaker firing, de-advertise for the rest of
    #                 the turn only (resets next user message / resume pass — weakest).
    # MEASURED (2026-07-25, gemma bootstrap turn, project pre-exists = the loop condition):
    #   off        57 kg_project_create attempts, ~1.72M cumulative prompt tok
    #   existence  57 attempts, ~1.80M tok  ← NO help: the workflow rail NAMES the tool, so a
    #              weak model HALLUCINATES the call even when it is de-advertised (and dispatch
    #              executes unadvertised calls). Pre-emptive schema-gating can't stop a rail-driven
    #              model — the industry "logit-mask, don't remove" lesson doesn't transfer here.
    #   session     1 attempt, ~0.35M tok   ← WINNER: one clean created:false (a terminal state)
    #              lets the model mark the step done, THEN the tool leaves the session hot-set.
    #   per_turn    1 attempt, ~0.37M tok   (equal, but resets each turn → session is strictly better)
    # ⇒ session: 57→1 attempts, ~5x fewer tokens; the cost is causally the attempt count (each
    #   attempt is a loop iteration re-sending the growing context).
    oneshot_deadvertise_mode: str = "session"

    # `rail_action_gate_mode` — bind the ADVERTISED ACTION SPACE to the pinned rail's computed
    # progress, so a weak model cannot repeat a finished step or wander off-step. The rail's
    # state is already externalized (compute_rail_progress reads the book) and re-injected each
    # turn (render_progress_block: "ALREADY DONE — do NOT repeat"), but that re-injection is
    # ADVISORY — the model reads it and repeats anyway (glossary_propose_entities ×8). This makes
    # the verdict BINDING at the single advertise chokepoint (schema-gating, not instruction).
    # Union'd with `oneshot_deadvertise_mode`; only ever drops a rail STEP tool (never a meta/
    # discovery/answer tool), so it cannot strand the turn. A/B modes measured 2026-07-26
    # (docs/eval/e2e-newcomer); the winner is set as the default.
    #   "off"           — advisory only (byte-identical to pre-gating): the re-injected block
    #                     tells the model what's done; nothing stops it re-doing it.
    #   "done_suppress" — drop a step's tool once that step is effectively DONE (turn-start
    #                     artifact/call-log OR a this-turn success), unless the step is `repeat`
    #                     or the same tool is still owed by a not-done step. Kills repeat-a-
    #                     finished-step loops (cross-turn AND intra-turn) while staying
    #                     conversational — the model keeps discovery + off-rail tools.
    #   "step_lock"     — advertise ONLY the current step's tool; every other rail step tool is
    #                     dropped. Maximally deterministic (Dify-Workflow shape), least
    #                     conversational — an off-rail aside has no tool to answer it.
    # MEASURED (2026-07-26, world-setup turn "propose ontology + seed entities", 3 runs/cell,
    # docs/eval/e2e-newcomer). Weak model = qwen2.5-7b (reproduces the loop), mid = gemma-4-26b
    # (the real target — the prior fix stack already tamed it, so it's the REGRESSION control):
    #   WEAK qwen2.5-7b   glossary_propose_entities attempts · cumulative prompt tok · entities/3
    #     off            13 / 21 / 9   · 1.6–3.8M · 0–1   (also spirals into chapter-save ×24)
    #     done_suppress   1 /  1 / 5   · 14K–277K · 0     ← propose loop killed, ~10–100× cheaper
    #     step_lock       0 /  0 / 0   · ~25K     · 0     (zero wander, full 13-kind ontology)
    #   MID gemma-4-26b (off completes fully = must NOT regress):
    #     off             1 · ~372K · 3/3   ✅ baseline
    #     done_suppress   1 · ~342K · 3/3   ✅ NO regression (identical, marginally cheaper)
    #     step_lock       0 · 0.36–3M · 0/3 ❌ REGRESSION: 0 entities + glossary_propose_entity_edit ×59
    # ⇒ DEFAULT = done_suppress. step_lock is DISQUALIFIED: pre-emptively starving a rail-driven
    #   model's action space makes it SUBSTITUTE a non-rail tool and loop on THAT (the same failure
    #   mode as oneshot "existence"). done_suppress is a pure REACTIVE safety net — inert until a
    #   proven-DONE step would repeat, so the clean mid-tier path is byte-unchanged while a weak
    #   model's repeat spiral is capped. (Residual: it does not stop a weak model JUMPING to a
    #   future step and looping there — a smaller harm than off's spiral, tracked for later.)
    rail_action_gate_mode: str = "done_suppress"

    # D-T2-03 — degraded-mode fallback when knowledge-service is unreachable
    # or returns an error. Must agree with knowledge-service's Mode 1 + Mode 2
    # `recent_message_count` (which also defaults to 50). Both services read
    # env var RECENT_MESSAGE_COUNT so a tune stays in sync.
    recent_message_count: int = 50

    class Config:
        env_file = ".env"


settings = Settings()
