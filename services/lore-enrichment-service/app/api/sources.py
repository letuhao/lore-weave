"""Sources (grounding corpora) router — register · ingest · list (D2 / C3-stub→real).

Closes the QC C3 gap: corpus registration + ingest were reachable ONLY via the
smoke path. Now:

  * POST /sources                — register a corpus (metadata: name/kind/license/
                                   provenance). No chunks yet. (PO: metadata-only.)
  * POST /sources/{id}/ingest    — chunk + REAL-embed text into the registered
                                   corpus (the smoke's ingest_corpus, API-wired).
  * GET  /sources                — list the (user, project) corpora + chunk counts.

H0/licensing: license is default-deny ('unknown' → un-re-cookable, C17); a
genuinely public-domain corpus must be tagged explicitly. Embedding resolves via
provider-registry by model_ref (NO hardcoded model name). Q3-scoped (user+project).
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.principal import Principal, require_principal
from app.clients.knowledge import KnowledgeClient, KnowledgeServiceError
from app.config import settings
from app.deps import get_db
from app.retrieval.store import SourceCorpusStore

router = APIRouter(prefix="/v1/lore-enrichment/sources", tags=["sources"])
logger = logging.getLogger("lore_enrichment.sources")

# The C2 source_corpus.kind CHECK vocabulary.
_KINDS = {"fengshen", "shanhaijing", "history", "other"}


class CreateSourceBody(BaseModel):
    project_id: UUID
    name: str = Field(min_length=1, max_length=200)
    kind: str
    # Default-deny: omitting the license stamps 'unknown' → the corpus can never
    # be silently re-cooked (C17). A genuinely PD corpus must say so explicitly.
    license: str = "unknown"
    provenance_json: dict = Field(default_factory=dict)


class IngestSourceBody(BaseModel):
    project_id: UUID
    text: str = Field(min_length=1)
    embedding_model_ref: UUID  # provider-registry user_model id (NO model name)
    target_chars: int = Field(default=800, ge=40, le=4000)


def _corpus_view(row: dict) -> dict:
    """Shape a source_corpus row for the API (SourceCorpus)."""
    prov = row.get("provenance_json")
    if isinstance(prov, str):
        try:
            prov = json.loads(prov)
        except ValueError:
            prov = {}
    view = {
        "corpus_id": str(row["corpus_id"]),
        "name": row["name"],
        "kind": row["kind"],
        "license": row["license"],
        "provenance_json": prov or {},
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }
    if "chunk_count" in row:
        view["chunk_count"] = int(row["chunk_count"])
    return view


@router.get("")
async def list_sources(
    project_id: UUID = Query(...),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
    store = SourceCorpusStore(pool)
    rows, total = await store.list_corpora(
        user_id=principal.user_id, project_id=project_id, limit=limit, offset=offset
    )
    return {
        "items": [_corpus_view(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_source(
    body: CreateSourceBody,
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Register corpus metadata (idempotent on user+project+name+kind). No ingest
    here — chunks/embeddings are added via POST /sources/{id}/ingest."""
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
    if body.kind not in _KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"kind must be one of {sorted(_KINDS)}",
        )
    store = SourceCorpusStore(pool)
    corpus_id = await store.upsert_corpus(
        user_id=principal.user_id, project_id=body.project_id,
        name=body.name, kind=body.kind, license=body.license,
        provenance_json=body.provenance_json,
    )
    row = await store.get_corpus(
        user_id=principal.user_id, project_id=body.project_id, corpus_id=corpus_id
    )
    return _corpus_view(row)


@router.post("/{corpus_id}/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_source(
    corpus_id: UUID,
    body: IngestSourceBody,
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Chunk + REAL-embed text into a registered corpus. Idempotent: re-ingesting
    identical text is a no-op (UNIQUE(corpus_id, chunk_index) + content hash)."""
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
    store = SourceCorpusStore(pool)
    corpus = await store.get_corpus(
        user_id=principal.user_id, project_id=body.project_id, corpus_id=corpus_id
    )
    if corpus is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="corpus not found")

    client = KnowledgeClient(
        knowledge_base_url=settings.knowledge_service_url,
        provider_registry_base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )

    async def embed_fn(texts):
        # Embed via provider-registry by model_ref (BYOK, scoped to the acting
        # user who owns the model). NO hardcoded model name.
        result = await client.embed(
            user_id=principal.user_id, model_source="user_model",
            model_ref=str(body.embedding_model_ref), texts=list(texts),
        )
        return result.embeddings

    try:
        # ingest_corpus re-upserts the SAME corpus (idempotent on name+kind) and
        # ingests into it; we pass the REGISTERED row's name/kind/license so the
        # ingest targets exactly the corpus the caller registered.
        ingest = await store.ingest_corpus(
            user_id=principal.user_id, project_id=body.project_id,
            name=corpus["name"], kind=corpus["kind"], license=corpus["license"],
            text=body.text, embed_fn=embed_fn,
            model_ref=str(body.embedding_model_ref), target_chars=body.target_chars,
        )
    except KnowledgeServiceError as exc:
        code = status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=code, detail=f"embedding failed: {exc}")
    finally:
        await client.aclose()

    return {
        "corpus_id": str(corpus_id),
        "chunks_total": ingest.chunks_total,
        "chunks_inserted": ingest.chunks_inserted,
        "chunks_embedded": ingest.chunks_embedded,
    }
