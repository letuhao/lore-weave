"""References router — LOOM T3.6 the author's per-Work reference shelf.

`/v1/composition`:
  GET    /works/{pid}/references                       — the library (newest first)
  POST   /works/{pid}/references                       — add (embed + store)
  DELETE /references/{rid}                              — remove (hard delete)
  GET    /works/{pid}/scenes/{nid}/references?q=        — per-scene semantic retrieval

References are composition-owned authoring data. The content is embedded via
provider-registry (`/internal/embed`) — the ONLY embedding path in composition, so
the provider-gateway invariant holds without touching knowledge-service. A Work uses
ONE embedding model (persisted in `work.settings.reference_embed_model_ref/source`,
set write-through on the FIRST add) so every vector shares one space; an add before
the model is set → 422, and per-scene search returns a neutral empty result with
`embed_model_set=false`. Pins reuse T3.4 (`PUT .../grounding-pins`,
item_type='reference', item_id = the reference id) — the search annotates each hit
with its pin/exclude state so the panel can render + toggle it.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, StringConstraints

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.db.repositories.grounding_pins import GroundingPinsRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.references import (
    REFERENCE_EMBED_MODEL_REF, REFERENCE_EMBED_MODEL_SOURCE, ReferencesRepo,
    reference_embed_model,
)
from app.db.repositories.works import WorksRepo
from app.deps import (
    get_embedding_client_dep, get_grounding_pins_repo, get_outline_repo,
    get_references_repo, get_works_repo,
)
from app.middleware.jwt_auth import get_current_user

router = APIRouter(prefix="/v1/composition")


class ReferenceCreate(BaseModel):
    content: Annotated[str, StringConstraints(min_length=1, max_length=20000)]
    title: Annotated[str, StringConstraints(max_length=500)] = ""
    author: Annotated[str, StringConstraints(max_length=500)] = ""
    source_url: Annotated[str, StringConstraints(max_length=500)] = ""
    # Used ONLY to SET the Work's embedding model on the first add (write-through).
    # Once set, the Work's stored model is authoritative and a differing value here
    # is ignored (so every reference of a Work stays in one vector space).
    model_ref: str | None = None
    model_source: str | None = None


async def _require_work(works: WorksRepo, user_id: UUID, project_id: UUID):
    work = await works.get(user_id, project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    return work


@router.get("/works/{project_id}/references")
async def list_references(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    refs: ReferencesRepo = Depends(get_references_repo),
) -> dict[str, Any]:
    work = await _require_work(works, user_id, project_id)
    rows = await refs.list(user_id, project_id)
    return {
        "references": [r.model_dump(mode="json") for r in rows],
        # surface whether the embed model is configured so the FE knows to prompt.
        "embed_model_set": reference_embed_model(work.settings) is not None,
    }


@router.post("/works/{project_id}/references", status_code=201)
async def create_reference(
    project_id: UUID,
    body: ReferenceCreate,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    refs: ReferencesRepo = Depends(get_references_repo),
    embedder: EmbeddingClient = Depends(get_embedding_client_dep),
) -> dict[str, Any]:
    work = await _require_work(works, user_id, project_id)

    # Resolve the embedding model: the Work's stored choice wins; else adopt the
    # one supplied on this first add; else 422. The write-through is DEFERRED until
    # AFTER a successful embed (below) — persisting it here would brick the work if
    # the supplied model is bad/down (every later add reuses it → permanent 502,
    # with no UI to change it since write-through only fires when the model is unset).
    model = reference_embed_model(work.settings)
    is_first = model is None
    if is_first:
        if not body.model_ref:
            raise HTTPException(status_code=422, detail={"code": "REFERENCE_EMBED_MODEL_UNSET"})
        model = (body.model_source or "user_model", body.model_ref)

    model_source, model_ref = model
    try:
        result = await embedder.embed(
            user_id=user_id, model_source=model_source, model_ref=model_ref,
            texts=[body.content],
        )
    except EmbeddingError as exc:
        raise HTTPException(status_code=502, detail={
            "code": "REFERENCE_EMBED_FAILED", "retryable": exc.retryable, "message": str(exc)})
    if not result.embeddings or not result.embeddings[0]:
        raise HTTPException(status_code=502, detail={"code": "REFERENCE_EMBED_EMPTY"})

    # Embed succeeded → NOW persist the model as the Work's reference embed model
    # (only on the first add; a proven-working model, so the work can't be bricked).
    if is_first:
        merged = dict(work.settings or {})
        merged[REFERENCE_EMBED_MODEL_SOURCE], merged[REFERENCE_EMBED_MODEL_REF] = model_source, model_ref
        await works.update(user_id, project_id, {"settings": merged})

    ref = await refs.create(
        user_id, project_id, content=body.content, embedding=result.embeddings[0],
        title=body.title, author=body.author, source_url=body.source_url,
        embedding_model=result.model, embedding_dim=result.dimension,
    )
    return ref.model_dump(mode="json")


@router.delete("/references/{reference_id}", status_code=200)
async def delete_reference(
    reference_id: UUID,
    user_id: UUID = Depends(get_current_user),
    refs: ReferencesRepo = Depends(get_references_repo),
) -> dict[str, Any]:
    if not await refs.delete(user_id, reference_id):
        raise HTTPException(status_code=404, detail="reference not found")
    return {"id": str(reference_id), "deleted": True}


@router.get("/works/{project_id}/scenes/{node_id}/references")
async def search_references(
    project_id: UUID,
    node_id: UUID,
    q: str = Query(default="", max_length=2000),
    limit: int = Query(default=8, ge=1, le=30),
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    refs: ReferencesRepo = Depends(get_references_repo),
    pins: GroundingPinsRepo = Depends(get_grounding_pins_repo),
    embedder: EmbeddingClient = Depends(get_embedding_client_dep),
) -> dict[str, Any]:
    """Semantic retrieval for a scene. `q` overrides the auto query (built from the
    scene's goal/synopsis/beat/title — the same seed the packer uses). Each hit
    carries `score` + its pin/exclude state. Neutral empty when the embed model is
    unset or the query embeds to nothing (never 500s on a provider outage)."""
    work = await _require_work(works, user_id, project_id)
    node = await outline.get_node(user_id, node_id)
    if node is None or str(node.project_id) != str(project_id):
        raise HTTPException(status_code=404, detail="scene not found")

    model = reference_embed_model(work.settings)
    if model is None:
        return {"hits": [], "embed_model_set": False, "query": ""}

    query = q.strip() or " ".join(
        str(x) for x in [node.goal, node.synopsis, node.beat_role, node.title] if x
    ).strip()
    if not query:
        return {"hits": [], "embed_model_set": True, "query": ""}

    model_source, model_ref = model
    try:
        result = await embedder.embed(
            user_id=user_id, model_source=model_source, model_ref=model_ref, texts=[query])
    except EmbeddingError:
        # provider outage → neutral empty (the panel shows "retrieval unavailable"),
        # never a 500 — same degrade posture as the packer lenses.
        return {"hits": [], "embed_model_set": True, "query": query, "unavailable": True}
    if not result.embeddings or not result.embeddings[0]:
        return {"hits": [], "embed_model_set": True, "query": query}

    hits = await refs.search(user_id, project_id, result.embeddings[0], limit=limit)

    # Annotate each hit with its per-scene pin/exclude state (T3.4 reuse).
    pin_rows = await pins.list_for_scene(user_id, project_id, node_id)
    state = {str(r.item_id): r.action for r in pin_rows if r.item_type == "reference"}
    for h in hits:
        action = state.get(str(h.get("id")))
        h["pinned"] = action == "pin"
        h["excluded"] = action == "exclude"
    return {"hits": hits, "embed_model_set": True, "query": query}
