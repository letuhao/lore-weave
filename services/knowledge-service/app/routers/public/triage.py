"""KG extraction-triage public router (epic 2026-06-20).

L1 pre-registers this as an EMPTY stub for lane LH (triage list grouped by
signature + resolve/dismiss + glossary hand-off) — handlers land here without
touching main.py. Contract: contracts/api/knowledge-service/triage.yaml.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.middleware.jwt_auth import get_current_user

router = APIRouter(
    prefix="/v1/kg",
    tags=["kg-triage"],
    dependencies=[Depends(get_current_user)],
)

# Handlers added by lane LH (triage repo + triage_apply via central write path).
