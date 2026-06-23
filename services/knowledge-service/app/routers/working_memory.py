"""POST /internal/working-memory/init — the goal-authority write path (M4).

chat-service calls this when a roleplay/interview session starts, pushing the
FROZEN charter (derived from the template — the goal authority). Idempotent: a
re-init never overwrites the charter or clobbers accumulated state.

The executive (M5) is the ONLY other writer, and it can write `state` only —
there is no charter-write endpoint, so the summarizing model can never move the
goal. (For full roleplay the world model would become the authority calling a
charter-write path here; the executive/anchoring core is unchanged — the POC
seam, see docs/specs/2026-06-23-interview-roleplay.md §9.)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.db.repositories.working_memory import WorkingMemoryRepo
from app.deps import get_working_memory_repo
from app.middleware.internal_auth import require_internal_token

router = APIRouter(
    prefix="/internal/working-memory",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


class WorkingMemoryCharter(BaseModel):
    goal: str
    phases: list[str]
    checklist: list[str] = []
    time_budget_min: int | None = None
    language: str = "en"


class InitWorkingMemoryRequest(BaseModel):
    session_id: UUID
    user_id: UUID
    charter: WorkingMemoryCharter


@router.post("/init", status_code=204)
async def init_working_memory(
    req: InitWorkingMemoryRequest,
    repo: WorkingMemoryRepo = Depends(get_working_memory_repo),
) -> None:
    await repo.init_charter(req.session_id, req.user_id, req.charter.model_dump())
