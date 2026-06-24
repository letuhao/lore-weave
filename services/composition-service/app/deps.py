"""FastAPI dependency-injection factories (composition-service, M2).

Canonical home for repo + client DI. Routers (M3+) `from app.deps import ...`.
Repos are cheap wrappers around the shared asyncpg pool (constructed per
request — no state); the knowledge client is a process singleton (owns an
httpx.AsyncClient). `outbox` is a module of free functions (txn-local), so it
has no factory — callers import `app.db.repositories.outbox` directly and pass
the active connection.
"""

from __future__ import annotations

from app.clients.book_client import BookClient, get_book_client
from app.clients.glossary_client import GlossaryClient, get_glossary_client
from app.clients.knowledge_client import KnowledgeClient, get_knowledge_client
from app.clients.llm_client import LLMClient, get_llm_client
from app.db.pool import get_pool
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.daily_progress import DailyProgressRepo
from app.db.repositories.derivatives import DerivativesRepo
from app.db.repositories.generation_corrections import GenerationCorrectionsRepo
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.grounding_pins import GroundingPinsRepo
from app.db.repositories.narrative_thread import NarrativeThreadRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.structure_templates import StructureTemplatesRepo
from app.db.repositories.style_voice import StyleProfileRepo, VoiceProfileRepo
from app.db.repositories.works import WorksRepo


async def get_works_repo() -> WorksRepo:
    return WorksRepo(get_pool())


async def get_derivatives_repo() -> DerivativesRepo:
    """C23 (dị bản M0) — the divergence_spec + entity_override writer for the
    derive flow."""
    return DerivativesRepo(get_pool())


async def get_outline_repo() -> OutlineRepo:
    return OutlineRepo(get_pool())


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


async def get_knowledge_client_dep() -> KnowledgeClient:
    return get_knowledge_client()


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


async def get_llm_client_dep() -> LLMClient:
    """Wired for the M6 engine + critic (built in M3)."""
    return get_llm_client()
