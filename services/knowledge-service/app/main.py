import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from loreweave_obs import current_otel_trace_id, setup_tracing

from app.clients.book_client import close_book_client, get_book_client
from app.clients.grant_client import close_grant_client, get_grant_client
from app.clients.embedding_client import close_embedding_client, get_embedding_client
from app.clients.glossary_client import close_glossary_client, init_glossary_client
from app.clients.llm_client import close_llm_client, get_llm_client
from app.config import settings
from app.db.migrate import run_migrations
from app.db.neo4j import close_neo4j_driver, get_neo4j_driver, init_neo4j_driver
from app.db.neo4j_schema import run_neo4j_schema
from app.db.pool import close_pools, create_pools, get_knowledge_pool
from app.db.seed_graph_schemas import seed_system_graph_schemas
from app.logging_config import setup_logging, trace_id_var
from app.middleware.trace_id import TraceIdMiddleware
from app.routers import (
    context,
    coref,
    health,
    internal_admin,
    internal_backfill,
    internal_canon,
    internal_benchmark,
    internal_dispatch,
    internal_job_control,
    internal_enrichment,
    internal_extraction,
    internal_kg_state,
    internal_parse,
    internal_parse_pdf,
    internal_summarize,
    internal_timeline,
    internal_wiki,
    metrics,
    ping,
    working_memory,
)
from app.routers.public import costs as public_costs
from app.routers.public import drawers as public_drawers
from app.routers.public import labels as public_labels
from app.routers.public import raw_search as public_raw_search
from app.routers.public import entities as public_entities
from app.routers.public import extraction as public_extraction
from app.routers.public import logs as public_logs
from app.routers.public import pending_facts as public_pending_facts
from app.routers.public import events as public_events
from app.routers.public import projects as public_projects
from app.routers.public import relations as public_relations
from app.routers.public import facts as public_facts
from app.routers.public import summaries as public_summaries
from app.routers.public.summaries import close_cooldown_client
from app.routers.public import timeline as public_timeline
from app.routers.public import user_data as public_user_data
# KG customizable-ontology epic (L1) — empty router stubs pre-registered here
# so lanes LC/LD/LH add handlers in their own files without touching main.py.
from app.routers.public import ontology as public_ontology
from app.routers.public import graph_views as public_graph_views
from app.routers.public import triage as public_triage
from app.routers.public import kg_actions as public_kg_actions
# ARCH-1 C1 — MCP server facade. build_mcp_app() returns the ASGI app
# mounted at /mcp; mcp_server's StreamableHTTP session manager is run
# inside the lifespan below.
from app.mcp.server import build_mcp_app, mcp_server
# KM5-M3 — the System-tier admin MCP server, a PHYSICALLY separate endpoint
# (/mcp/admin) RS256-gated at the transport before tools/list (INV-T6). Its
# session manager is run alongside mcp_server in the lifespan below.
from app.mcp.admin_server import build_admin_mcp_app, mcp_admin_server

logger = logging.getLogger(__name__)


async def _close_all_startup_resources() -> None:
    """D-K11.3-01 (session 46) — partial-startup cleanup.

    If any pre-yield step raises, this runs every close_* that is
    safe to call regardless of whether the corresponding init
    actually completed. close_* functions are idempotent / no-op
    when the resource is None or already closed.

    Teardown order mirrors the post-yield block (reverse dependency).
    """
    for close_fn_name, close_fn in (
        ("cooldown_client", close_cooldown_client),
        ("llm_client", close_llm_client),
        ("embedding_client", close_embedding_client),
        ("book_client", close_book_client),
        ("grant_client", close_grant_client),
        ("glossary_client", close_glossary_client),
        ("neo4j_driver", close_neo4j_driver),
        ("pools", close_pools),
    ):
        try:
            await close_fn()
        except Exception:
            logger.warning(
                "startup cleanup: failed to close %s (non-fatal)",
                close_fn_name, exc_info=True,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    # D-K11.3-01: wrap startup so a failure mid-init closes what DID
    # initialize. Without this the post-yield cleanup only runs when
    # the yield is reached, leaking pools/drivers/clients on any
    # startup exception.
    try:
        # Fail-fast: if either pool cannot be created, raise and stop startup.
        await create_pools(settings.knowledge_db_url, settings.glossary_db_url)
        await run_migrations(get_knowledge_pool())
        # KG ontology epic (L1) — seed the System graph-schema templates
        # (general + xianxia-harem). Idempotent + hash-gated; additive (no
        # project reads these until it adopts → zero behavior change).
        await seed_system_graph_schemas(get_knowledge_pool())
        # Long-lived httpx client for glossary-service calls (K4b).
        init_glossary_client()
        # K16.2 — long-lived httpx client for book-service chapter counts.
        get_book_client()
        # E0-3 — long-lived httpx client for the book-service grant authority.
        get_grant_client()
        # D-GRANT-INSTANT-REVOKE — tail book-service grant revokes (Redis) → drop the
        # cached grant on the spot (vs the 45s TTL). Best-effort; no redis → TTL only.
        if settings.redis_url:
            get_grant_client().start_revoke_consumer(settings.redis_url)
        # K12.2 — long-lived httpx client for embedding calls.
        get_embedding_client()
        # loreweave_llm SDK wrapper for unified-gateway LLM calls. Touched
        # here so SDK construction errors (bad base_url, missing
        # internal_token) surface at startup rather than at first
        # extraction job. Lifecycle close in _close_all_startup_resources
        # + the post-yield teardown.
        get_llm_client()
        # K11.2 — Neo4j driver. No-op in Track 1 mode (NEO4J_URI empty);
        # fail-fast on unreachable Neo4j when configured.
        await init_neo4j_driver()
        # K11.3 — apply the Cypher schema (constraints + indexes +
        # vector indexes) on every startup. Idempotent. Only runs when
        # the K11.2 driver init actually configured a connection;
        # Track 1 mode skips this entirely.
        if settings.neo4j_uri:
            await run_neo4j_schema(get_neo4j_driver())
        # D-P2-STALE-CLAIM-LIFESPAN-HOOK. Reset extraction_leaves rows
        # stuck in status='running' for >30 min back to 'pending' so
        # new workers can pick them up. Idempotent + multi-replica safe
        # (status='running' filter atomically scopes the UPDATE).
        # Best-effort: a Postgres hiccup here MUST NOT block startup
        # of the rest of the service — claim_pending also has its own
        # retry path, this hook just removes the multi-hour wait until
        # that natural retry catches up.
        try:
            from app.db.repositories.extraction_leaves import ExtractionLeavesRepo
            reset_n = await ExtractionLeavesRepo(get_knowledge_pool()).reset_stale_claims()
            if reset_n > 0:
                logger.info(
                    "D-P2-STALE-CLAIM-LIFESPAN-HOOK: reset %d stale 'running' claims to 'pending'",
                    reset_n,
                )
        except Exception:
            logger.warning(
                "D-P2-STALE-CLAIM-LIFESPAN-HOOK: stale-claim recovery failed (non-fatal)",
                exc_info=True,
            )
        # Q4b-feed — prune extraction_run_samples older than the judging
        # window. The sample is a transient buffer feeding the online judge;
        # rows past the window are dead novel-text weight. Best-effort: a
        # Postgres hiccup here MUST NOT block service startup.
        try:
            from app.db.repositories.extraction_run_samples import (
                ExtractionRunSamplesRepo,
            )
            pruned_n = await ExtractionRunSamplesRepo(
                get_knowledge_pool()
            ).prune_older_than(settings.extraction_run_sample_ttl_days)
            if pruned_n > 0:
                logger.info(
                    "Q4b-feed: pruned %d extraction_run_samples older than %d days",
                    pruned_n, settings.extraction_run_sample_ttl_days,
                )
        except Exception:
            logger.warning(
                "Q4b-feed: extraction_run_samples prune failed (non-fatal)",
                exc_info=True,
            )
    except Exception:
        logger.exception(
            "lifespan startup failed before yield — running partial cleanup"
        )
        await _close_all_startup_resources()
        raise
    # Cycle 73f r2 H1 fold — hydrate filter config from Redis on startup
    # so a container restart preserves ops-override. Spawn subscriber
    # task so multi-replica KS deployments see each others' reloads via
    # pubsub. Non-fatal: failure logs warn and falls through to env.
    filter_reload_task = None
    if settings.redis_url:
        try:
            from app.extraction.pass2_orchestrator import (
                consume_filter_reload_signal,
                hydrate_precision_filter_config_from_redis,
            )
            await hydrate_precision_filter_config_from_redis(settings.redis_url)
            filter_reload_task = asyncio.create_task(
                consume_filter_reload_signal(settings.redis_url),
            )
            logger.info("cycle 73f: filter reload hydrate + subscriber started")
        except Exception:
            logger.warning(
                "cycle 73f: filter reload startup failed (non-fatal — "
                "using env defaults)",
                exc_info=True,
            )

    # K14.1 — start event consumer as background task.
    # Imports inline to avoid circular imports (consumer needs pool).
    consumer_task = None
    try:
        from app.events.consumer import EventConsumer
        from app.events.dispatcher import EventDispatcher
        from app.events.handlers import (
            handle_chat_turn,
            handle_chapter_published,
            handle_chapter_unpublished,
            handle_chapter_kg_indexed,
            handle_chapter_kg_excluded,
            handle_chapter_scenes_reparsed,
            handle_chapter_deleted,
            handle_chat_message_feedback,
            handle_glossary_entity_updated,
            handle_glossary_entity_merged,
            handle_translation_published,
        )

        dispatcher = EventDispatcher()
        dispatcher.register("chat.turn_completed", handle_chat_turn)
        # Track 4 P3b — thumbs on a chat turn → salience feedback attribution
        # (advisory; only affects ranking once salience_feedback_weight > 0).
        dispatcher.register("chat.message_feedback", handle_chat_message_feedback)
        # KG-ML M2 — a chapter's translation became active → dual-index its vi
        # passages (index-only; never re-extracts Layer 1).
        dispatcher.register("translation.published", handle_translation_published)
        # Canon Model CM3c: canon = published. BOTH graph extraction AND L3
        # passage-ingest now trigger on chapter.published (at the pinned
        # revision), never chapter.saved — so unreviewed draft prose never
        # canonizes. chapter.saved is no longer consumed by knowledge (the
        # handler was dropped); statistics-service still consumes it separately.
        dispatcher.register("chapter.published", handle_chapter_published)
        dispatcher.register("chapter.unpublished", handle_chapter_unpublished)
        # WS-0.8 (spec 2026-07-11-publish-independent-kg-indexing §3.7/§3.8) — publishing
        # no longer gates the knowledge graph. These two registrations are what make the
        # feature EXIST: the dispatcher drops an unregistered event_type at DEBUG level,
        # so without them book-service commits the pointer, re-parses the scenes, returns
        # 200, the UI shows "indexed" — and the event is acked into the void. No
        # extraction_pending row, no passages, nothing in the graph. A perfect silent
        # success.
        #
        #   chapter.kg_indexed  — the user added a (possibly DRAFT) chapter to their KG.
        #                         Mirrors chapter.published's two writes, but stamps
        #                         passage canon = (revision_id == published_revision_id),
        #                         so draft prose never becomes canon (§3.7 / P1-8).
        #   chapter.kg_excluded — the user retracted a chapter ("forget this"). This is
        #                         the retraction path that chapter.unpublished used to
        #                         perform; unpublish is now an EDITORIAL act that must
        #                         NOT destroy the user's index (§3.8 / acceptance #9).
        #
        # chapter.saved stays UNREGISTERED (see above): indexing is an explicit act,
        # autosave is not.
        dispatcher.register("chapter.kg_indexed", handle_chapter_kg_indexed)
        dispatcher.register("chapter.kg_excluded", handle_chapter_kg_excluded)
        # IX-10 (spec 26 / RB-5) — book-service re-parsed a chapter's index
        # (publish path or sweeper); invalidate this book's extraction cache so
        # the graph re-derives from the fresh scenes (the F6 endpoint's logic,
        # finally wired to its event trigger). Arrives on the chapter stream.
        dispatcher.register("chapter.scenes_reparsed", handle_chapter_scenes_reparsed)
        dispatcher.register("chapter.deleted", handle_chapter_deleted)
        # C4 (K14) — auto glossary→KG propagation. glossary-service emits
        # glossary.entity_updated on every entity write (single + bulk
        # extract); this triggers the existing glossary_sync → Neo4j.
        dispatcher.register(
            "glossary.entity_updated", handle_glossary_entity_updated,
        )
        # mui #1c — glossary.entity_merged consolidates the KG: merge the loser
        # :Entity into the winner + entity_alias_map (anti-resurrection).
        dispatcher.register(
            "glossary.entity_merged", handle_glossary_entity_merged,
        )

        consumer = EventConsumer(
            redis_url=settings.redis_url,
            pool=get_knowledge_pool(),
            dispatcher=dispatcher,
        )
        consumer_task = asyncio.create_task(consumer.run())
        logger.info("K14.1: event consumer started as background task")
    except Exception:
        logger.warning("K14.1: event consumer failed to start (non-fatal)", exc_info=True)

    # K13.1 — start nightly anchor_score refresh loop as background task.
    # Skipped in Track 1 / no-Neo4j mode since recompute_anchor_score has
    # nothing to do without a graph.
    refresh_task = None
    if settings.neo4j_uri:
        try:
            from app.db.neo4j import neo4j_session
            from app.jobs.anchor_refresh_loop import run_anchor_refresh_loop

            def _anchor_session_factory():
                return neo4j_session()

            refresh_task = asyncio.create_task(
                run_anchor_refresh_loop(
                    get_knowledge_pool(),
                    _anchor_session_factory,
                )
            )
            logger.info("K13.1: anchor-refresh loop started as background task")
        except Exception:
            logger.warning(
                "K13.1: anchor-refresh loop failed to start (non-fatal)",
                exc_info=True,
            )

    # K20.3 — scheduled project summary regeneration. Skipped in
    # Track 1 / no-Neo4j mode since the regen helper reads raw
    # :Passage nodes from the graph — with no graph there's nothing
    # to regenerate from.
    #
    # Construction pattern matches K13.1's anchor_refresh_loop wire
    # just above: pool + session factory passed positionally,
    # downstream collaborators constructed inline here rather than
    # via the async `get_*_repo()` factories in deps.py. Those
    # factories exist for FastAPI `Depends()` integration; calling
    # them here would create a throwaway coroutine for a pure
    # pass-through. Consistency with the neighbor scheduler wins
    # over consistency with router DI.
    summary_regen_task = None
    global_regen_task = None
    if settings.neo4j_uri:
        try:
            from app.db.neo4j import neo4j_session
            from app.db.repositories.summaries import SummariesRepo
            from app.db.repositories.summary_spending import SummarySpendingRepo
            from app.jobs.summary_regen_scheduler import (
                run_global_regen_loop,
                run_project_regen_loop,
            )

            def _summary_session_factory():
                return neo4j_session()

            # C16-BUILD — single SummarySpendingRepo instance shared
            # across both regen loops. Wires D-K20α-01 budget pre-check
            # + global spend recorder. Project loop also uses it to
            # ungate K16.11 record_spending in the project regen path.
            _summary_spending_repo = SummarySpendingRepo(get_knowledge_pool())

            # K20.3 α — project-scope (L1) regen, daily cadence.
            summary_regen_task = asyncio.create_task(
                run_project_regen_loop(
                    get_knowledge_pool(),
                    _summary_session_factory,
                    get_llm_client(),
                    SummariesRepo(get_knowledge_pool()),
                    summary_spending_repo=_summary_spending_repo,
                )
            )
            logger.info(
                "K20.3: project summary regen loop started as background task"
            )

            # K20.3 β — global-scope (L0) regen, weekly cadence with
            # 15-min offset so it doesn't start simultaneously with
            # the project loop on first boot.
            global_regen_task = asyncio.create_task(
                run_global_regen_loop(
                    get_knowledge_pool(),
                    _summary_session_factory,
                    get_llm_client(),
                    SummariesRepo(get_knowledge_pool()),
                    summary_spending_repo=_summary_spending_repo,
                )
            )
            logger.info(
                "K20.3: global summary regen loop started as background task"
            )
        except Exception:
            logger.warning(
                "K20.3: summary regen loops failed to start (non-fatal)",
                exc_info=True,
            )

    # wiki-llm M6 — wiki-gen stream consumer. ALWAYS started (D-JOURNEY-WIKI-FLAG):
    # the consumer is idle/free until a job arrives — it does NOT spend by running,
    # it only blocks on the Redis stream. Spend is bounded where it belongs: per
    # REQUEST (the user-triggered, cost-gated kg_build_wiki confirm + the job's
    # max_spend_usd). The old `wiki_gen_enabled` env gated the CONSUMER, so off-by-
    # default a deploy accepted wiki-gen jobs (202) and then silently pended them
    # forever — a dead-end with no signal. An ops kill-switch, if ever needed,
    # belongs on the TRIGGER endpoint (fail loud), never on the consumer.
    # Cancel-driven shutdown like the other background loops.
    wiki_gen_task = None
    try:
        from app.jobs.wiki_gen_processor import run_wiki_gen_consumer
        wiki_gen_task = asyncio.create_task(run_wiki_gen_consumer())
        logger.info("wiki-llm M6: wiki-gen consumer started as background task")
    except Exception:
        logger.warning(
            "wiki-llm M6: wiki-gen consumer failed to start (non-fatal)",
            exc_info=True,
        )

    # C14a — reconcile-evidence-count + quarantine-cleanup schedulers.
    # Both wrap existing per-user/global Neo4j functions (K11.9 + K15.10)
    # in periodic sweeps. Gated on neo4j_uri same as summary regen
    # loops (both need working Cypher sessions). Advisory-lock keys
    # 20_310_004 (reconcile) + 20_310_005 (quarantine) distinct from
    # 001-003 so all schedulers can run concurrently without blocking.
    reconcile_sweep_task = None
    quarantine_sweep_task = None
    if settings.neo4j_uri:
        try:
            from app.db.neo4j import neo4j_session
            from app.db.repositories.sweeper_state import SweeperStateRepo
            from app.jobs.reconcile_evidence_count_scheduler import (
                run_reconcile_loop,
            )
            from app.jobs.quarantine_cleanup_scheduler import (
                run_quarantine_loop,
            )

            def _scheduler_session_factory():
                return neo4j_session()

            # C14b — pass the sweeper_state repo so reconciler's
            # per-user cursor resumes mid-sweep on restart.
            _sweeper_state_repo = SweeperStateRepo(get_knowledge_pool())

            reconcile_sweep_task = asyncio.create_task(
                run_reconcile_loop(
                    get_knowledge_pool(),
                    _scheduler_session_factory,
                    sweeper_state_repo=_sweeper_state_repo,
                )
            )
            logger.info(
                "C14a: reconcile-evidence-count loop started as background task"
            )

            quarantine_sweep_task = asyncio.create_task(
                run_quarantine_loop(
                    get_knowledge_pool(),
                    _scheduler_session_factory,
                )
            )
            logger.info(
                "C14a: quarantine-cleanup loop started as background task"
            )
        except Exception:
            logger.warning(
                "C14a: reconcile/quarantine loops failed to start (non-fatal)",
                exc_info=True,
            )

    # C3 (D-K19b.8-01) — job_logs retention cron. Not gated on
    # neo4j_uri because retention only needs the knowledge-service
    # Postgres pool. 20-min startup offset from the K20.3 loops'
    # 10/15-min windows so the three schedulers don't converge at boot.
    job_logs_retention_task = None
    try:
        from app.jobs.job_logs_retention import run_job_logs_retention_loop

        job_logs_retention_task = asyncio.create_task(
            run_job_logs_retention_loop(get_knowledge_pool())
        )
        logger.info(
            "C3: job_logs retention loop started as background task"
        )
    except Exception:
        logger.warning(
            "C3: job_logs retention loop failed to start (non-fatal)",
            exc_info=True,
        )

    # D-T2-04 — cross-process cache invalidator via Redis pub/sub.
    # Only installed when redis_url is configured; Track 1 single-
    # worker deploys stay local-only.
    cache_invalidator = None
    if settings.redis_url:
        try:
            from app.context import cache as cache_module
            from app.context.cache_invalidation import CacheInvalidator

            cache_invalidator = CacheInvalidator(settings.redis_url)
            await cache_invalidator.start()
            cache_module.set_invalidator(cache_invalidator)
            logger.info(
                "D-T2-04: cache invalidator registered (cross-process pub/sub active)"
            )
        except Exception:
            logger.warning(
                "D-T2-04: cache invalidator failed to start (non-fatal) — "
                "falling back to local-only invalidation",
                exc_info=True,
            )

    # ARCH-1 C1 — run the MCP StreamableHTTP session manager. The /mcp
    # sub-app is mounted at module level (after app construction), but a
    # mounted Starlette sub-app's lifespan is NOT auto-run under FastAPI,
    # so we enter its session manager here. stateless_http=True means no
    # per-session state survives between calls; scope arrives in headers.
    # Failure to start affects only the MCP path — the bespoke
    # /internal/tools/* routes stay up regardless (dual-run).
    mcp_exit_stack: AsyncExitStack | None = None
    try:
        mcp_exit_stack = AsyncExitStack()
        await mcp_exit_stack.enter_async_context(mcp_server.session_manager.run())
        # KM5-M3 — the /mcp/admin session manager runs in the SAME exit stack so
        # both stop together at shutdown. Its surface is RS256-gated at transport.
        await mcp_exit_stack.enter_async_context(mcp_admin_server.session_manager.run())
        logger.info("ARCH-1 C1 + KM5-M3: MCP session managers started; /mcp + /mcp/admin live")
    except Exception:
        logger.warning(
            "ARCH-1 C1: MCP session manager failed to start (non-fatal) — "
            "/mcp facade unavailable, bespoke /internal/tools/* still serve",
            exc_info=True,
        )
        if mcp_exit_stack is not None:
            await mcp_exit_stack.aclose()
            mcp_exit_stack = None

    logger.info("knowledge-service started on port %d", settings.port)
    try:
        yield
    finally:
        # ARCH-1 C1 — stop the MCP session manager first so in-flight
        # tool calls are cancelled before the repos/pools they touch are
        # closed. The SDK's session-manager shutdown cancels its anyio
        # task group (streamable_http_manager.run() -> tg.cancel_scope
        # .cancel()); it does NOT drain — there is no grace period for a
        # mid-query handler. The ORDERING still matters: cancelling here,
        # ahead of close_pools() below, lets a cancelled handler unwind
        # against a still-open pool instead of hitting a closed one.
        if mcp_exit_stack is not None:
            try:
                await mcp_exit_stack.aclose()
            except Exception:
                logger.warning(
                    "ARCH-1 C1: error stopping MCP session manager",
                    exc_info=True,
                )
        # Stop cache invalidator first so in-flight publishes drain
        # before we close the Redis client.
        if cache_invalidator is not None:
            try:
                from app.context import cache as cache_module
                cache_module.set_invalidator(None)
                await cache_invalidator.stop()
            except Exception:
                logger.warning(
                    "Error stopping cache invalidator", exc_info=True,
                )

        # Cycle 73f r3 M3 fold: stop filter-reload subscriber. Without
        # this cancel block, the BG task leaks its Redis client + pubsub
        # connection on container shutdown — slow teardown + connection
        # exhaustion on repeated dev restarts.
        if filter_reload_task is not None:
            filter_reload_task.cancel()
            try:
                await filter_reload_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning(
                    "cycle 73f: error stopping filter-reload subscriber",
                    exc_info=True,
                )

        # Stop anchor-refresh loop next (quick cancel).
        if refresh_task is not None:
            refresh_task.cancel()
            try:
                await refresh_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning("Error stopping anchor-refresh loop", exc_info=True)

        # wiki-llm M6: stop the wiki-gen consumer.
        if wiki_gen_task is not None:
            wiki_gen_task.cancel()
            try:
                await wiki_gen_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning("wiki-llm M6: error stopping wiki-gen consumer", exc_info=True)

        # K20.3: stop summary regen loops (project first, then global).
        if summary_regen_task is not None:
            summary_regen_task.cancel()
            try:
                await summary_regen_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning(
                    "K20.3: error stopping project regen loop",
                    exc_info=True,
                )
        if global_regen_task is not None:
            global_regen_task.cancel()
            try:
                await global_regen_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning(
                    "K20.3: error stopping global regen loop",
                    exc_info=True,
                )

        # C3: stop job_logs retention loop.
        if job_logs_retention_task is not None:
            job_logs_retention_task.cancel()
            try:
                await job_logs_retention_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning(
                    "C3: error stopping job_logs retention loop",
                    exc_info=True,
                )

        # C14a: stop reconcile + quarantine sweepers.
        if reconcile_sweep_task is not None:
            reconcile_sweep_task.cancel()
            try:
                await reconcile_sweep_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning(
                    "C14a: error stopping reconcile sweep loop",
                    exc_info=True,
                )
        if quarantine_sweep_task is not None:
            quarantine_sweep_task.cancel()
            try:
                await quarantine_sweep_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning(
                    "C14a: error stopping quarantine sweep loop",
                    exc_info=True,
                )

        # Stop event consumer next.
        if consumer_task is not None:
            try:
                await consumer.stop()
                consumer_task.cancel()
                try:
                    await consumer_task
                except asyncio.CancelledError:
                    pass
            except Exception:
                logger.warning("Error stopping event consumer", exc_info=True)

        # Phase 3 review issue 8: close in reverse dependency order.
        # C2: close the cooldown Redis client ahead of other resources
        # since it's self-contained (no inbound dependencies).
        await close_cooldown_client()
        await close_llm_client()
        await close_embedding_client()
        await close_book_client()
        await close_grant_client()
        await close_glossary_client()
        await close_neo4j_driver()
        await close_pools()
        logger.info("knowledge-service stopped")


app = FastAPI(title="knowledge-service", lifespan=lifespan)

app.add_middleware(TraceIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 6c-γ — OpenTelemetry: instrument this app for SERVER spans + httpx
# for outbound CLIENT spans. No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset.
# Called AFTER add_middleware so the OTel ASGI middleware lands OUTERMOST
# (Starlette prepends middleware) — the SERVER span then covers the full
# request, CORS + TraceId middleware included. /review-impl(6c-γ) LOW#4.
setup_tracing("knowledge-service", app=app)

@app.exception_handler(Exception)
async def _trace_id_500_handler(request: Request, exc: Exception) -> JSONResponse:
    """K7e + D-PHASE6C-TRACE-ID-UNIFY: include BOTH ids in the 500 body
    so a caller staring at a UI error can:
      - `trace_id` → grep this service's structured logs
      - `otel_trace_id` → paste straight into Grafana Tempo to follow
        the request across services (chat → knowledge → book → glossary)

    The two ids are unrelated by design: TraceIdMiddleware's id is a
    uuid4 hex per-request set BEFORE any OTel span exists; Tempo
    indexes by the OTel trace id minted inside FastAPIInstrumentor's
    SERVER span. Empty string when OTel is no-op
    (`OTEL_EXPORTER_OTLP_ENDPOINT` unset) — operators can tell apart
    "Tempo down" from "this service crashed before the span started".

    HTTPException (4xx + explicit 5xx from handlers) is NOT caught
    here — FastAPI's built-in HTTPException handler runs first and
    keeps its own envelope.
    """
    logger.exception("unhandled exception (500): %s", exc)
    tid = trace_id_var.get()
    otel_tid = current_otel_trace_id()
    return JSONResponse(
        status_code=500,
        content={
            "detail": "internal server error",
            "trace_id": tid,
            "otel_trace_id": otel_tid,
        },
        headers={"X-Trace-Id": tid or ""},
    )


app.include_router(health.router)
app.include_router(ping.public_router)
app.include_router(ping.internal_router)
app.include_router(context.router)
app.include_router(working_memory.router)
app.include_router(coref.router)
app.include_router(internal_admin.router)
app.include_router(internal_backfill.router)
app.include_router(internal_canon.router)
app.include_router(internal_benchmark.router)
app.include_router(internal_dispatch.router)
app.include_router(internal_job_control.router)
app.include_router(internal_enrichment.router)
app.include_router(internal_extraction.router)
app.include_router(internal_kg_state.router)
app.include_router(internal_parse.router)
app.include_router(internal_parse_pdf.router)
app.include_router(internal_summarize.router)
app.include_router(internal_timeline.router)
app.include_router(internal_wiki.router)
app.include_router(metrics.router)
app.include_router(public_costs.router)
app.include_router(public_drawers.router)
app.include_router(public_raw_search.router)
app.include_router(public_labels.router)
app.include_router(public_entities.router)
app.include_router(public_entities.entities_router)
app.include_router(public_relations.relations_router)
app.include_router(public_facts.facts_router)
app.include_router(public_events.events_router)
app.include_router(public_extraction.router)
app.include_router(public_extraction.jobs_router)
app.include_router(public_logs.router)
app.include_router(public_pending_facts.router)
app.include_router(public_projects.router)
app.include_router(public_summaries.router)
app.include_router(public_timeline.timeline_router)
app.include_router(public_user_data.router)
# KG ontology epic (L1) — empty stubs; lanes LC/LD/LH fill the handlers.
app.include_router(public_ontology.router)
app.include_router(public_graph_views.router)
app.include_router(public_triage.router)
# KM6 — class-C confirm-token machinery (generalized preview/confirm spine).
app.include_router(public_kg_actions.router)

# KM5-M3 — the System-tier admin MCP server. MOUNTED BEFORE "/mcp" because
# Starlette matches mounts by prefix in registration order: "/mcp" would also
# match "/mcp/admin", so the more-specific admin prefix must be registered first.
# RS256-gated at the transport (build_admin_mcp_app) before tools/list, so the
# admin surface cannot be enumerated without a verified X-Admin-Token (INV-T6).
app.mount("/mcp/admin", build_admin_mcp_app())

# ARCH-1 C1 — MCP server facade. (KM0, 2026-06-20: the legacy dual-run
# /internal/tools/* HTTP path was retired — MCP is the sole tool transport.)
# Streamable HTTP transport; auth via X-Internal-Token is checked inside
# each tool handler's _build_tool_context(). build_mcp_app() returns the
# Starlette ASGI app synchronously; mounted AFTER all routers so FastAPI
# routes take precedence over the Starlette sub-app. The StreamableHTTP
# session manager is run by the lifespan above.
app.mount("/mcp", build_mcp_app())
