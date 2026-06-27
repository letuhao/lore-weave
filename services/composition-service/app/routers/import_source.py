"""import_source router — W9 the per-user deconstruct-input CRUD (§12.3/§12.6).

`/v1/composition`:
  POST   /import-sources              — paste/upload raw text + title + optional project_id
  GET    /import-sources              — list the caller's OWN rows (newest first)
  GET    /import-sources/{id}         — read one (owner-only)
  DELETE /import-sources/{id}         — hard delete (owner-only)

NAMING (load-bearing): the module is `import_source.py`, NOT `import.py` — `import` is a
Python keyword, so `from app.routers import import` is a SyntaxError. main.py wires this
as `import_source`.

TENANCY (§12.6 COPYRIGHT): an import_source is PER-USER, un-shareable BY CONSTRUCTION
(the table has no visibility column — there is NO public/unlisted path here). Every
endpoint is owner-scoped; a foreign/missing id is the uniform H13 404 (no existence
oracle). This is plain non-agentic CRUD (§13.3) → HTTP is fine. The agentic ANALYZE
(deconstruct) is the EXISTING Tier-W MCP tool `composition_arc_import_analyze` → it
enqueues an `analyze_reference` job whose worker handler lives in
engine/motif_deconstruct.py — there is intentionally NO HTTP analyze endpoint here.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, StringConstraints

from app.db.repositories.import_source_repo import ImportSourceRepo
from app.deps import get_import_source_repo
from app.middleware.jwt_auth import get_current_user

router = APIRouter(prefix="/v1/composition")

# The uniform "no existence oracle" 404 (H13) — identical for missing and foreign,
# so a caller can't distinguish "exists but not yours" from "does not exist".
_NOT_FOUND = {
    "code": "IMPORT_SOURCE_NOT_FOUND",
    "message": "import source not found or not accessible",
}


class ImportSourceCreate(BaseModel):
    # The raw text the user pasted/uploaded for deconstruct. Bounded (the row model's
    # content is _Long = 20000 chars; the deconstruct chunks it across the map rails).
    content: Annotated[str, StringConstraints(min_length=1, max_length=20000)]
    title: Annotated[str, StringConstraints(max_length=500)] = ""
    # Optional book/project scope (cross-DB, no FK — §1.4). NO visibility field: an
    # import_source is per-user by construction (§12.6).
    project_id: UUID | None = None


@router.post("/import-sources", status_code=201)
async def create_import_source(
    body: ImportSourceCreate,
    user_id: UUID = Depends(get_current_user),
    repo: ImportSourceRepo = Depends(get_import_source_repo),
) -> dict[str, Any]:
    row = await repo.create(
        user_id, content=body.content, title=body.title, project_id=body.project_id,
    )
    return row.model_dump(mode="json")


@router.get("/import-sources")
async def list_import_sources(
    project_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user_id: UUID = Depends(get_current_user),
    repo: ImportSourceRepo = Depends(get_import_source_repo),
) -> dict[str, Any]:
    rows = await repo.list_for_owner(user_id, project_id=project_id, limit=limit)
    return {"import_sources": [r.model_dump(mode="json") for r in rows]}


@router.get("/import-sources/{import_source_id}")
async def get_import_source(
    import_source_id: UUID,
    user_id: UUID = Depends(get_current_user),
    repo: ImportSourceRepo = Depends(get_import_source_repo),
) -> dict[str, Any]:
    row = await repo.get_for_owner(user_id, import_source_id)
    if row is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return row.model_dump(mode="json")


@router.delete("/import-sources/{import_source_id}", status_code=200)
async def delete_import_source(
    import_source_id: UUID,
    user_id: UUID = Depends(get_current_user),
    repo: ImportSourceRepo = Depends(get_import_source_repo),
) -> dict[str, Any]:
    if not await repo.delete_for_owner(user_id, import_source_id):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return {"id": str(import_source_id), "deleted": True}
