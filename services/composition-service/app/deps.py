"""FastAPI dependency-injection factories (composition-service, M2).

Canonical home for repo + client DI. Routers (M3+) `from app.deps import ...`.
Repos are cheap wrappers around the shared asyncpg pool (constructed per
request — no state); the knowledge client is a process singleton (owns an
httpx.AsyncClient). `outbox` is a module of free functions (txn-local), so it
has no factory — callers import `app.db.repositories.outbox` directly and pass
the active connection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.clients.book_client import BookClient, get_book_client
from app.clients.embedding_client import EmbeddingClient, get_embedding_client
from app.clients.glossary_client import GlossaryClient, get_glossary_client
from app.clients.kal_client import KalClient, get_kal_client
from app.clients.knowledge_client import KnowledgeClient, get_knowledge_client
from app.clients.llm_client import LLMClient, get_llm_client
from app.db.pool import get_pool
from app.db.repositories.arc_template_repo import ArcTemplateRepo
from app.db.repositories.authoring_runs import AuthoringRunsRepo, AuthoringRunUnitsRepo
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.daily_progress import DailyProgressRepo
from app.db.repositories.derivatives import DerivativesRepo
from app.db.repositories.generation_corrections import GenerationCorrectionsRepo
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.grounding_pins import GroundingPinsRepo
from app.db.repositories.import_source_repo import ImportSourceRepo
from app.db.repositories.motif_application import MotifApplicationRepo
from app.db.repositories.motif_repo import MotifRepo
from app.db.repositories.motif_retrieve import MotifRetriever
from app.db.repositories.narrative_thread import NarrativeThreadRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.plan_bootstrap_proposals import PlanBootstrapProposalsRepo
from app.db.repositories.plan_runs import PlanRunsRepo
from app.db.repositories.references import ReferencesRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.structure_templates import StructureTemplatesRepo
from app.db.repositories.style_voice import StyleProfileRepo, VoiceProfileRepo
from app.db.repositories.works import WorksRepo
from app.services.plan_forge_service import PlanForgeService

if TYPE_CHECKING:  # runtime import stays deferred (the service pulls in the engine)
    from app.services.authoring_run_service import AuthoringRunService
    from app.services.bootstrap_service import BootstrapService


async def get_plan_runs_repo() -> PlanRunsRepo:
    return PlanRunsRepo(get_pool())


async def get_plan_forge_service() -> PlanForgeService:
    from app.clients.llm_client import get_llm_client

    return PlanForgeService(
        PlanRunsRepo(get_pool()),
        GenerationJobsRepo(get_pool()),
        WorksRepo(get_pool()),
        llm=get_llm_client(),
    )


async def get_bootstrap_service() -> "BootstrapService":
    """PlanForge auto-bootstrap gate — see
    docs/specs/2026-07-06-planforge-auto-bootstrap.md §3.1/§6."""
    from app.services.bootstrap_service import BootstrapService

    return BootstrapService(
        PlanBootstrapProposalsRepo(get_pool()),
        PlanRunsRepo(get_pool()),
        get_book_client(),
        get_glossary_client(),
        GenerationJobsRepo(get_pool()),
    )


async def get_authoring_run_service() -> "AuthoringRunService":
    """RAID Wave D2+D3+D4 — the autonomous authoring-run FSM + start-gate +
    DURABLE sequential driver (wired to the REAL in-process engine drafting
    seam) plus the D3 per-unit ledger + Run Report + accept/reject/Revert-All
    (real book-service revision capture). D4 defaults: notify=None → the real
    NotificationClient (lazy), driver_id=None → the process identity; the
    per-request instances share the module-level driver-task registry, so the
    inflight cap and sweep see one another. D5 default: critic=None → the real
    EngineCriticSeam (in-process judge_prose over the drafted chapter). Tests
    inject fakes."""
    from app.services.authoring_run_service import (
        AuthoringRunService,
        BookRevisionCapture,
        EngineDraftingSeam,
    )

    return AuthoringRunService(
        AuthoringRunsRepo(get_pool()),
        PlanRunsRepo(get_pool()),
        EngineDraftingSeam(),
        AuthoringRunUnitsRepo(get_pool()),
        BookRevisionCapture(),
    )


async def get_works_repo() -> WorksRepo:
    return WorksRepo(get_pool())


async def get_derivatives_repo() -> DerivativesRepo:
    """C23 (dị bản M0) — the divergence_spec + entity_override writer for the
    derive flow."""
    return DerivativesRepo(get_pool())


async def get_outline_repo() -> OutlineRepo:
    return OutlineRepo(get_pool())


async def get_structure_repo() -> "StructureRepo | None":
    """The arc lens repo (23 BA12). Tolerant of an uninitialised pool: this dep was added
    to existing pack-calling handlers, and their many unit tests override only the deps
    they knew about — a hard get_pool() here would 500 every such test. The packer treats
    structure_repo=None as the DORMANT arc lens (no <arc> frame, zero extra reads), which
    is the correct behaviour when no pool exists. Production always has a pool, so the arc
    is injected there; the wired DB test proves that path explicitly."""
    from app.db.pool import get_pool as _get_pool
    from app.db.repositories.structure import StructureRepo
    try:
        return StructureRepo(_get_pool())
    except RuntimeError:
        return None  # pool not initialised (unit test) → arc lens dormant


async def get_scene_links_repo() -> SceneLinksRepo:
    return SceneLinksRepo(get_pool())


async def get_narrative_thread_repo() -> NarrativeThreadRepo:
    """FD-1 — the promise/foreshadow ledger writer (S2 producer). Wired into the
    auto-generate path when a Work opts into `narrative_thread_enabled`."""
    return NarrativeThreadRepo(get_pool())


async def get_canon_rules_repo() -> CanonRulesRepo:
    return CanonRulesRepo(get_pool())


async def get_grounding_pins_repo() -> GroundingPinsRepo:
    """T3.4 — per-scene grounding pin/exclude steering. Wired into pack() (the
    grounding preview AND every engine generation call site) so the set is honored
    everywhere a scene is packed."""
    return GroundingPinsRepo(get_pool())


async def get_daily_progress_repo() -> DailyProgressRepo:
    """T4.2 — server-SSOT writing-progress stats (per-chapter word-count snapshots
    differenced into per-day authored words + streak + book total)."""
    return DailyProgressRepo(get_pool())


async def get_style_profile_repo() -> StyleProfileRepo:
    """T3.5 — per-scope Density/Pace prose-style steering. Resolved by pack() and
    threaded into the draft prompts."""
    return StyleProfileRepo(get_pool())


async def get_voice_profile_repo() -> VoiceProfileRepo:
    """T3.5 — per-character voice tags, injected by pack() for present entities."""
    return VoiceProfileRepo(get_pool())


async def get_generation_jobs_repo() -> GenerationJobsRepo:
    return GenerationJobsRepo(get_pool())


async def get_generation_corrections_repo() -> GenerationCorrectionsRepo:
    return GenerationCorrectionsRepo(get_pool())


async def get_structure_templates_repo() -> StructureTemplatesRepo:
    return StructureTemplatesRepo(get_pool())


async def get_motif_repo() -> MotifRepo:
    """F0 — the narrative motif library CRUD + clone primitive. W1 extends it with
    the HTTP surface (adopt/publish/catalog); the engine (W2)/MCP (W4) consume the
    same instance through this factory."""
    return MotifRepo(get_pool())


async def get_arc_template_repo() -> ArcTemplateRepo:
    """W10 — the arc-template library CRUD + clone primitive + apply-preview. Mirrors
    get_motif_repo; the router (arc.py) consumes this. W9 (import/deconstruct) will
    consume the same repo through this factory."""
    return ArcTemplateRepo(get_pool())


async def get_import_source_repo() -> ImportSourceRepo:
    """W9 — the per-user deconstruct-input store (import/deconstruct, §12.3/§12.6).
    The import_source CRUD router consumes this; the worker handler
    (engine/motif_deconstruct) loads the row owner-checked off the same table.
    Mirrors get_motif_repo (cheap per-request wrapper over the shared pool)."""
    return ImportSourceRepo(get_pool())


async def get_motif_repo_opt() -> "MotifRepo | None":
    """X-7 — the MOTIF lens's repo, for the pack-calling handlers ONLY.

    Pool-tolerant, for exactly the reason `get_structure_repo` (:118) is: this dep is being
    added to EXISTING pack-calling handlers whose many unit tests override only the deps they
    knew about, so a hard get_pool() here would 500 every one of them. The packer treats a
    None motif repo as the DORMANT motif lens (no <motif> frame, zero extra reads) — the
    correct behaviour when there is no pool. Production always has a pool, so the motif IS
    injected there, and test_pack_motif_wired.py proves that path against a real DB.

    ⚠ Deliberately SEPARATE from `get_motif_repo` (:183), which the motif CRUD routers use and
    which must keep returning a non-Optional repo — do not merge them.
    """
    from app.db.pool import get_pool as _get_pool
    try:
        return MotifRepo(_get_pool())
    except RuntimeError:
        return None  # pool not initialised (unit test) → motif lens dormant


async def get_motif_application_repo_opt() -> "MotifApplicationRepo | None":
    """X-7 — the motif BINDING ledger for the pack-calling handlers. See
    `get_motif_repo_opt` above; same pool-tolerant rationale, same dormant-lens contract."""
    from app.db.pool import get_pool as _get_pool
    try:
        return MotifApplicationRepo(_get_pool())
    except RuntimeError:
        return None  # pool not initialised (unit test) → motif lens dormant


async def get_motif_retriever() -> MotifRetriever:
    """F0 frozen signature; W3 implements. The planner (W2) and the MCP
    _suggest_for_chapter (W4) both resolve candidates through this one core."""
    return MotifRetriever(get_pool())


async def get_motif_application_repo() -> MotifApplicationRepo:
    """W2 — the motif_application binding ledger (W2 is the sole writer; W5's
    conformance trace + the planner read it). Added at the Wave-1 reconcile node as
    the F0 follow-up W2/W5 both requested (deps was F0-frozen during the wave)."""
    return MotifApplicationRepo(get_pool())


async def get_references_repo() -> ReferencesRepo:
    """T3.6 — the author's per-Work reference shelf (embedded influences). Resolved
    by pack() (gather_references) and the references router (CRUD + search)."""
    return ReferencesRepo(get_pool())


async def get_knowledge_client_dep() -> KnowledgeClient:
    return get_knowledge_client()


async def get_embedding_client_dep() -> EmbeddingClient:
    """T3.6 — provider-registry /internal/embed (reference content + scene queries).
    The ONLY embedding path in composition (provider-gateway invariant)."""
    return get_embedding_client()


async def get_book_client_dep() -> BookClient:
    return get_book_client()


async def get_grant_client_dep():
    """E0-4c — the book-grant authority for the collaboration gate. Overridable
    in tests."""
    from app.grant_client import get_grant_client
    return get_grant_client()


async def get_glossary_client_dep() -> GlossaryClient:
    """Wired for the M4 packer L0 lens (built in M3)."""
    return get_glossary_client()


async def get_kal_client_dep() -> KalClient:
    """The KAL (knowledge-gateway) read boundary — the planner's roster source
    (INV-KAL). Overridable in tests."""
    return get_kal_client()


async def get_llm_client_dep() -> LLMClient:
    """Wired for the M6 engine + critic (built in M3)."""
    return get_llm_client()
