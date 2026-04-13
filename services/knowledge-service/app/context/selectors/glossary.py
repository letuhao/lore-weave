"""L2 glossary fallback selector.

Given a project and a user message, returns the ranked list of
glossary entities that should be injected into the memory block.
Handles three edge cases without the caller having to care:

  1. Project has no book_id         → empty list
  2. glossary-service is down       → empty list (client already logs)
  3. Empty query / empty result     → empty list

The Mode builder just iterates whatever we return.
"""

from uuid import UUID

from app.clients.glossary_client import GlossaryClient, GlossaryEntityForContext
from app.db.models import Project

__all__ = ["select_glossary_for_context"]


async def select_glossary_for_context(
    client: GlossaryClient,
    *,
    user_id: UUID,
    project: Project,
    message: str,
    max_entities: int = 20,
    max_tokens: int = 800,
) -> list[GlossaryEntityForContext]:
    if project.book_id is None:
        return []
    return await client.select_for_context(
        user_id=user_id,
        book_id=project.book_id,
        query=message,
        max_entities=max_entities,
        max_tokens=max_tokens,
    )
