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

from app.clients.llm_client import LLMClient
from app.db.repositories.working_memory import WorkingMemoryRepo
from app.deps import get_llm_client, get_working_memory_repo
from app.middleware.internal_auth import require_internal_token
from app.working_memory.executive import run_executive

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
    question_target: int | None = None  # ACP A4 (RV-M4) — optional/additive


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


class TurnInput(BaseModel):
    role: str
    content: str


class TickRequest(BaseModel):
    session_id: UUID
    user_id: UUID
    # The session's own model (a provider-registry user_model the user already
    # chose) — the executive runs on it. No separate default-model capability.
    model_source: str | None = None
    model_ref: str | None = None
    recent_turns: list[TurnInput] = []


@router.post("/tick")
async def tick_working_memory(
    req: TickRequest,
    repo: WorkingMemoryRepo = Depends(get_working_memory_repo),
    llm_client: LLMClient = Depends(get_llm_client),
) -> dict:
    """The executive pass: update `state` from recent turns. Best-effort — the
    body's `status` reports what happened (updated / no_block / no_model /
    llm_failed / bad_json); it never 500s on a skip."""
    status = await run_executive(
        repo=repo,
        llm_client=llm_client,
        session_id=req.session_id,
        user_id=req.user_id,
        model_source=req.model_source,
        model_ref=req.model_ref,
        recent_turns=[t.model_dump() for t in req.recent_turns],
    )
    return {"status": status}
