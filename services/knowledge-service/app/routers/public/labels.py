"""KG-ML M5 (C5) — backend-served label endpoints.

Exposes predicate (relation edge) localization so chat / MCP / agent / frontend
consumers all resolve labels the same way (R5: backend-served, not frontend-only).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.labels.predicate_labels import predicate_catalog, resolve_predicate_label
from app.middleware.jwt_auth import get_current_user

router = APIRouter(
    prefix="/v1/knowledge",
    tags=["labels"],
    dependencies=[Depends(get_current_user)],
)


class PredicateLabelsResponse(BaseModel):
    language: str | None
    labels: dict[str, str]


@router.get("/predicate-labels", response_model=PredicateLabelsResponse)
async def get_predicate_labels(
    language: str | None = Query(
        None, max_length=35,
        description="Reader language (e.g. 'vi'). Omit for the humanized English labels.",
    ),
    codes: str | None = Query(
        None,
        description="Optional comma-separated predicate codes to resolve (curated "
        "label else humanized fallback). Omit to return the full curated catalog.",
    ),
) -> PredicateLabelsResponse:
    """Resolve relation-predicate labels for a language. With ``codes`` it
    resolves exactly those (open-vocab predicates included, via the humanize
    fallback); without ``codes`` it returns the full curated catalog."""
    if codes:
        wanted = [c.strip() for c in codes.split(",") if c.strip()]
        labels = {c: resolve_predicate_label(c, language) for c in wanted}
    else:
        labels = predicate_catalog(language)
    return PredicateLabelsResponse(language=language, labels=labels)
