"""Shared FastAPI dependency-injection helpers.

**This module is the canonical home for repo / client DI factories.**
Do NOT redefine `get_summaries_repo`, `get_projects_repo`, or
`get_glossary_client` anywhere else in the codebase. New routers
should `from app.deps import ...` directly.

Hoisted out of `app/routers/context.py` in K7c so public routers don't
have to cross-import from the internal context router. The names are
still re-exported from `context.py` for back-compat with existing test
overrides (`app.dependency_overrides[app.routers.context.get_projects_repo]
= ...`), so the refactor was zero behavioural change — but new code
should reach for `app.deps` first.
"""

from app.clients.book_client import BookClient
from app.clients.book_client import get_book_client as _get_book_client_singleton
from app.clients.embedding_client import EmbeddingClient
from app.clients.embedding_client import get_embedding_client as _get_embedding_client_singleton
from app.clients.glossary_client import GlossaryClient
from app.clients.glossary_client import get_glossary_client as _get_glossary_client_singleton
from app.clients.provider_client import ProviderClient
from app.clients.provider_client import get_provider_client as _get_provider_client_singleton
from app.db.pool import get_knowledge_pool
from app.db.repositories.benchmark_runs import BenchmarkRunsRepo
from app.db.repositories.extraction_jobs import ExtractionJobsRepo
from app.db.repositories.extraction_pending import ExtractionPendingRepo
from app.db.repositories.job_logs import JobLogsRepo
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.summaries import SummariesRepo
from app.db.repositories.entity_alias_map import EntityAliasMapRepo
from app.db.repositories.summary_spending import SummarySpendingRepo
from app.db.repositories.user_budgets import UserBudgetsRepo
from app.db.repositories.user_data import UserDataRepo


async def get_summaries_repo() -> SummariesRepo:
    return SummariesRepo(get_knowledge_pool())


async def get_summary_spending_repo() -> SummarySpendingRepo:
    """C16-BUILD: D-K20α-01 closer. Wires the user-wide non-project-
    attributable spend ledger into router DI so manual regen via the
    public + internal endpoints picks up the same budget pre-check +
    post-success recorder that the K20.3 scheduler loops use.
    Without this dep, manual regens silently bypass the cap."""
    return SummarySpendingRepo(get_knowledge_pool())


async def get_entity_alias_map_repo() -> EntityAliasMapRepo:
    """C17: D-K19d-γb-03 closer. Wires the post-merge alias→target
    redirect index into router DI so:
      - the merge endpoint writes alias-map rows + repoints chain
        merges after surgery, and
      - extraction writers (via the resolver) consult the table
        BEFORE the SHA-hash MERGE so re-extracted aliases land at
        the merge target rather than resurrecting source.
    Without this dep, every merge is a one-shot — extraction
    re-extraction silently re-creates the merged-away source."""
    return EntityAliasMapRepo(get_knowledge_pool())


async def get_projects_repo() -> ProjectsRepo:
    return ProjectsRepo(get_knowledge_pool())


async def get_user_data_repo() -> UserDataRepo:
    return UserDataRepo(get_knowledge_pool())


async def get_extraction_jobs_repo() -> ExtractionJobsRepo:
    return ExtractionJobsRepo(get_knowledge_pool())


async def get_extraction_pending_repo() -> ExtractionPendingRepo:
    return ExtractionPendingRepo(get_knowledge_pool())


async def get_glossary_client() -> GlossaryClient:
    return _get_glossary_client_singleton()


async def get_book_client() -> BookClient:
    return _get_book_client_singleton()


async def get_embedding_client() -> EmbeddingClient:
    return _get_embedding_client_singleton()


async def get_provider_client() -> ProviderClient:
    return _get_provider_client_singleton()


async def get_benchmark_runs_repo() -> BenchmarkRunsRepo:
    return BenchmarkRunsRepo(get_knowledge_pool())


async def get_user_budgets_repo() -> UserBudgetsRepo:
    return UserBudgetsRepo(get_knowledge_pool())


async def get_job_logs_repo() -> JobLogsRepo:
    return JobLogsRepo(get_knowledge_pool())
