"""KG graph-ontology public router (epic 2026-06-20).

L1 pre-registers this as an EMPTY stub so the parallel lane LC can add its
handlers (list/read/adopt/sync/schema-CRUD) into THIS file without ever
touching main.py (the router-registration choke-point fix, build plan §3-L1).
Contract: contracts/api/knowledge-service/ontology.yaml.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.middleware.jwt_auth import get_current_user

router = APIRouter(
    prefix="/v1/kg",
    tags=["kg-ontology"],
    dependencies=[Depends(get_current_user)],
)

# Handlers added by lane LC (ontology_mutations + adopt/sync/CRUD).
