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
from app.db.pool import get_pool
from app.db.repositories.grounding_pins import GroundingPinsRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.references import (
    REFERENCE_EMBED_MODEL_REF, REFERENCE_EMBED_MODEL_SOURCE, ReferencesRepo,
    reference_embed_model,
)
from app.db.repositories.works import WorksRepo
from app.deps import (
    get_embedding_client_dep, get_grant_client_dep, get_grounding_pins_repo,
    get_outline_repo, get_references_repo, get_works_repo,
)
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_current_user
from app.packer.pack import OwnershipError

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


async def _require_work(
    works: WorksRepo, grant: GrantClient, user_id: UUID, project_id: UUID,
    need: GrantLevel,
):
    """Resolve the Work by project (un-user-scoped — 25 PM-9) and gate the
    caller's E0 grant on its book (PM-8). none→404 (no oracle), under-tier→403."""
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    try:
        await authorize_book(grant, work.book_id, user_id, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="work not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")
    return work


@router.get("/works/{project_id}/references")
async def list_references(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    refs: ReferencesRepo = Depends(get_references_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    work = await _require_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    rows = await refs.list(project_id)
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
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    work = await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)

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
        await works.update(project_id, {"settings": merged}, created_by=user_id)

    ref = await refs.create(
        project_id, created_by=user_id,
        content=body.content, embedding=result.embeddings[0],
        title=body.title, author=body.author, source_url=body.source_url,
        embedding_model=result.model, embedding_dim=result.dimension,
    )
    return ref.model_dump(mode="json")


class ReferenceMetadataPatch(BaseModel):
    """S-03: metadata-only edit — no field touches the embedding. All optional; an
    OMITTED field is left unchanged (Pydantic model_fields_set), a provided null
    clears to '' (the columns are NOT NULL DEFAULT '')."""

    title: Annotated[str, StringConstraints(max_length=500)] | None = None
    author: Annotated[str, StringConstraints(max_length=500)] | None = None
    source_url: Annotated[str, StringConstraints(max_length=500)] | None = None


class ReferenceContentPut(BaseModel):
    content: Annotated[str, StringConstraints(min_length=1, max_length=20000)]


@router.patch("/works/{project_id}/references/{reference_id}")
async def update_reference_metadata(
    project_id: UUID,
    reference_id: UUID,
    body: ReferenceMetadataPatch,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    refs: ReferencesRepo = Depends(get_references_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """S-03: edit title/author/source_url — a CHEAP column write, NO re-embed (fixing
    a typo in an author's name must not pay for a full re-embed). EDIT grant; only the
    provided fields change; 404 when the reference isn't in this project."""
    await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    fs = body.model_fields_set
    kwargs = {col: (getattr(body, col) or "") for col in ("title", "author", "source_url") if col in fs}
    ref = await refs.update_metadata(project_id, reference_id, **kwargs)
    if ref is None:
        raise HTTPException(status_code=404, detail="reference not found")
    return ref.model_dump(mode="json")


@router.put("/works/{project_id}/references/{reference_id}/content")
async def update_reference_content(
    project_id: UUID,
    reference_id: UUID,
    body: ReferenceContentPut,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    refs: ReferencesRepo = Depends(get_references_repo),
    embedder: EmbeddingClient = Depends(get_embedding_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """S-03: replace a reference's content — this DOES re-embed (a priced embed, made
    explicit by the separate route). Resolves the Work's PINNED embed model (never a
    model in the body — one embedding space per Work, OQ-9); it does not re-adopt a
    model. EDIT grant; 404 when the reference isn't in this project."""
    work = await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    # Confirm the reference is in this project BEFORE paying for the embed (also the
    # tenancy check — a reference from another project 404s here, not after an embed).
    if await refs.get(project_id, reference_id) is None:
        raise HTTPException(status_code=404, detail="reference not found")
    model = reference_embed_model(work.settings)
    if model is None:
        # A reference exists ⇒ its create set the model; defensive only.
        raise HTTPException(status_code=422, detail={"code": "REFERENCE_EMBED_MODEL_UNSET"})
    model_source, model_ref = model
    try:
        result = await embedder.embed(
            user_id=user_id, model_source=model_source, model_ref=model_ref, texts=[body.content],
        )
    except EmbeddingError as exc:
        raise HTTPException(status_code=502, detail={
            "code": "REFERENCE_EMBED_FAILED", "retryable": exc.retryable, "message": str(exc)})
    if not result.embeddings or not result.embeddings[0]:
        raise HTTPException(status_code=502, detail={"code": "REFERENCE_EMBED_EMPTY"})
    ref = await refs.update_content(
        project_id, reference_id, content=body.content, embedding=result.embeddings[0],
        embedding_model=result.model, embedding_dim=result.dimension,
    )
    if ref is None:
        raise HTTPException(status_code=404, detail="reference not found")
    return ref.model_dump(mode="json")


@router.delete("/references/{reference_id}", status_code=200)
async def delete_reference(
    reference_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    refs: ReferencesRepo = Depends(get_references_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    # By-id route (`/references/{rid}` has no project in the path): resolve the
    # reference's scope from the ROW ITSELF via an ids-only read (PM-8 scope-
    # bootstrap, mirrors works.scope_meta's anti-oracle), gate EDIT on ITS book,
    # then delete under the same project constraint.
    row = await get_pool().fetchrow(
        "SELECT project_id FROM reference_source WHERE id = $1", reference_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="reference not found")
    await _require_work(works, grant, user_id, row["project_id"], GrantLevel.EDIT)
    if not await refs.delete(row["project_id"], reference_id):
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
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Semantic retrieval for a scene. `q` overrides the auto query (built from the
    scene's goal/synopsis/beat/title — the same seed the packer uses). Each hit
    carries `score` + its pin/exclude state. Neutral empty when the embed model is
    unset or the query embeds to nothing (never 500s on a provider outage)."""
    work = await _require_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    node = await outline.get_node(node_id)
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

    hits = await refs.search(project_id, result.embeddings[0], limit=limit)

    # Annotate each hit with its per-scene pin/exclude state (T3.4 reuse).
    pin_rows = await pins.list_for_scene(project_id, node_id)
    state = {str(r.item_id): r.action for r in pin_rows if r.item_type == "reference"}
    for h in hits:
        action = state.get(str(h.get("id")))
        h["pinned"] = action == "pin"
        h["excluded"] = action == "exclude"
    return {"hits": hits, "embed_model_set": True, "query": query}
