"""KG graph-views + temporal-read public router (epic 2026-06-20).

L1 pre-registers this as an EMPTY stub for lane LD (views CRUD + graph read
?view=&as_of_chapter= + entity edge timeline) — handlers land here without
touching main.py. Contract: contracts/api/knowledge-service/views.yaml.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.middleware.jwt_auth import get_current_user

router = APIRouter(
    prefix="/v1/kg",
    tags=["kg-views"],
    dependencies=[Depends(get_current_user)],
)

# Handlers added by lane LD (graph_views repo + view_filter + temporal as-of).
