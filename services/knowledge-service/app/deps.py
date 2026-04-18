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
from app.clients.glossary_client import GlossaryClient
from app.clients.glossary_client import get_glossary_client as _get_glossary_client_singleton
from app.db.pool import get_knowledge_pool
from app.db.repositories.extraction_jobs import ExtractionJobsRepo
from app.db.repositories.extraction_pending import ExtractionPendingRepo
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.summaries import SummariesRepo
from app.db.repositories.user_data import UserDataRepo


async def get_summaries_repo() -> SummariesRepo:
    return SummariesRepo(get_knowledge_pool())


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
