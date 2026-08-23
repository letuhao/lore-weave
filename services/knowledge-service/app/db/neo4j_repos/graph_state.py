"""D-EMB-MODEL-REF-04 — the GROUND-TRUTH answer to "does this project hold vectors?".

Three call sites guard an embedding-model change (the Tier-A `kg_project_set_embedding_model`
tool, `PATCH /v1/knowledge/projects/{id}`, and the campaign `set-campaign-models` dispatch).
All three asked ``extraction_status != 'disabled'``, treating an INGESTION state as a
DATA-EXISTENCE fact. Those are not the same question, and one supported user action makes
them disagree: ``POST /extraction/disable`` sets ``extraction_status='disabled'`` while
explicitly preserving the graph — it even returns ``graph_preserved: true``. After that
call, a project stuffed with `:Passage` vectors reads as "no graph", the guard opens, and the
model can be swapped with no confirm and no purge. Every passage then sits in the dead vector
space, invisible to the new index: the silent zero-recall the guard exists to prevent.

``extraction_status`` also cannot distinguish delete-graph (vectors gone) from
disable-extraction (vectors kept) — both land on the same terminal ``'disabled'``. No amount
of reading that column recovers the difference, so the question has to be asked of Neo4j.
"""
from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


async def project_has_embedded_passages(user_id: UUID | str, project_id: UUID | str) -> bool:
    """True when the project still holds `:Passage` vectors a model change would orphan.

    FAILS CLOSED. If Neo4j is unconfigured or unreachable we cannot prove the project is
    empty, and the two errors are not symmetric: a false "no vectors" silently destroys
    retrieval for a whole project, while a false "has vectors" only routes the user to the
    confirm-gated path that would have been correct anyway. So an unknown answer is `True`.
    """
    from app.config import settings
    from app.db.neo4j import graph_session
    from app.db.neo4j_repos.passages import project_has_passages

    if not settings.neo4j_uri:
        # No Neo4j configured at all ⇒ no vector store ⇒ genuinely nothing to orphan.
        # This is the ONE case where "unknown" collapses to a real "no".
        return False
    try:
        async with graph_session() as session:
            return await project_has_passages(
                session, user_id=str(user_id), project_id=str(project_id),
            )
    except Exception:  # noqa: BLE001 — see the fail-closed note above
        logger.warning(
            "passage-existence probe failed for project %s — assuming the project HAS "
            "vectors so an embedding-model change stays confirm-gated",
            project_id, exc_info=True,
        )
        return True
