"""Interview-roleplay session templates (the goal authority).

A template = a reusable interviewer persona (`system_prompt`) + a `scenario`
that seeds a new session's **frozen `charter`**. Tenancy (LOCKED):

- **System tier** (`owner_user_id IS NULL`) — seeded via migration, admin-managed,
  **read-only** to users. Never writable through this user-facing API.
- **Per-user tier** (`owner_user_id = caller`) — the user's own templates.

The write endpoints (`POST` / `PATCH` / `DELETE`) only ever match the caller's
own rows (`owner_user_id = user_id`); a System row (or another user's) yields
404 — a regular user can never mutate a shared/System row. Resolution/listing
merges System (defaults) with the user's own.

`POST /{id}/start` clones a template into a real chat session: it writes the
session's `system_prompt` + `model_ref` and **seeds `working_memory_seed`** with
the frozen charter (cold-start anchor, EC-2; degraded fallback, EC-4).
"""
import json
import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from app.client.knowledge_client import get_knowledge_client
from app.deps import get_current_user, get_db
from app.models import (
    ChatSession,
    CreateTemplateRequest,
    PatchTemplateRequest,
    SessionTemplate,
    SessionTemplateScenario,
    StartPracticeRequest,
    TemplateListResponse,
    WorkingMemory,
    WorkingMemoryCharter,
)
from app.routers.sessions import _row_to_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat/templates", tags=["templates"])


def _jsonb(v):
    return json.loads(v) if isinstance(v, str) else (v or {})


def _row_to_template(r: asyncpg.Record) -> SessionTemplate:
    return SessionTemplate(
        template_id=r["template_id"],
        owner_user_id=r["owner_user_id"],
        tier=r["tier"],
        code=r["code"],
        name=r["name"],
        description=r["description"],
        system_prompt=r["system_prompt"],
        model_source=r["model_source"],
        model_ref=r["model_ref"],
        scenario=SessionTemplateScenario(**_jsonb(r["scenario"])),
        rubric=_jsonb(r["rubric"]) if r["rubric"] is not None else None,
        is_active=r["is_active"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SessionTemplate)
async def create_template(
    body: CreateTemplateRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> SessionTemplate:
    # Always a Per-user template — the API cannot create System-tier rows.
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO session_templates
              (owner_user_id, tier, code, name, description, system_prompt,
               model_source, model_ref, scenario, rubric)
            VALUES ($1, 'user', $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb)
            RETURNING *
            """,
            user_id, body.code, body.name, body.description, body.system_prompt,
            body.model_source, str(body.model_ref) if body.model_ref else None,
            json.dumps(body.scenario.model_dump()),
            json.dumps(body.rubric) if body.rubric is not None else None,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="template code already exists for this user")
    return _row_to_template(row)


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> TemplateListResponse:
    # System defaults (owner NULL) + the user's own, active only. Per-user rows
    # with the same `code` shadow the System default (resolution precedence).
    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (code) *
        FROM session_templates
        WHERE is_active = true AND (owner_user_id IS NULL OR owner_user_id = $1)
        ORDER BY code, (owner_user_id IS NOT NULL) DESC, updated_at DESC
        """,
        user_id,
    )
    # Defensive: a single malformed row (e.g. a System seed with an empty/invalid
    # `scenario` — the JSONB DEFAULT '{}' is the smell) must NOT 500 the listing
    # for everyone. Skip + log the bad row; serve the rest. (A regular user can
    # never write a System row, so a bad System seed is an admin/migration bug,
    # not user input — but the blast radius is all tenants, so we contain it.)
    items: list[SessionTemplate] = []
    for r in rows:
        try:
            items.append(_row_to_template(r))
        except Exception:
            logger.warning("skipping malformed session_template %s (code=%s)",
                           r["template_id"], r["code"], exc_info=True)
    return TemplateListResponse(items=items)


async def _load_visible(pool: asyncpg.Pool, template_id: UUID, user_id: str) -> asyncpg.Record | None:
    """A template the caller may READ: a System default or one they own."""
    return await pool.fetchrow(
        """
        SELECT * FROM session_templates
        WHERE template_id = $1 AND (owner_user_id IS NULL OR owner_user_id = $2)
        """,
        str(template_id), user_id,
    )


@router.get("/{template_id}", response_model=SessionTemplate)
async def get_template(
    template_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> SessionTemplate:
    row = await _load_visible(pool, template_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="template not found")
    try:
        return _row_to_template(row)
    except Exception:
        raise HTTPException(status_code=422, detail="template scenario is invalid")


@router.patch("/{template_id}", response_model=SessionTemplate)
async def patch_template(
    template_id: UUID,
    body: PatchTemplateRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> SessionTemplate:
    # WHERE owner_user_id = user_id ⇒ a System row (owner NULL) or another
    # user's row never matches → 404. A regular user cannot mutate a shared row.
    scenario_json = json.dumps(body.scenario.model_dump()) if body.scenario is not None else None
    rubric_json = json.dumps(body.rubric) if body.rubric is not None else None
    row = await pool.fetchrow(
        """
        UPDATE session_templates SET
          name          = COALESCE($3, name),
          description    = COALESCE($4, description),
          system_prompt  = COALESCE($5, system_prompt),
          model_source   = COALESCE($6, model_source),
          model_ref      = COALESCE($7, model_ref),
          scenario       = COALESCE($8::jsonb, scenario),
          rubric         = COALESCE($9::jsonb, rubric),
          is_active      = COALESCE($10, is_active),
          updated_at     = now()
        WHERE template_id = $1 AND owner_user_id = $2
        RETURNING *
        """,
        str(template_id), user_id,
        body.name, body.description, body.system_prompt,
        body.model_source, str(body.model_ref) if body.model_ref else None,
        scenario_json, rubric_json, body.is_active,
    )
    if not row:
        raise HTTPException(status_code=404, detail="template not found")
    return _row_to_template(row)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> None:
    result = await pool.execute(
        "DELETE FROM session_templates WHERE template_id = $1 AND owner_user_id = $2",
        str(template_id), user_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="template not found")


@router.post("/{template_id}/start", status_code=status.HTTP_201_CREATED, response_model=ChatSession)
async def start_practice(
    template_id: UUID,
    body: StartPracticeRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ChatSession:
    tpl = await _load_visible(pool, template_id, user_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="template not found")

    # Resolve model: request override > template default. Both absent → 400.
    model_source = body.model_source or tpl["model_source"]
    model_ref = body.model_ref or tpl["model_ref"]
    if not model_source or not model_ref:
        raise HTTPException(
            status_code=400,
            detail="no model: template has no default model and none was provided",
        )

    try:
        scenario = SessionTemplateScenario(**_jsonb(tpl["scenario"]))
    except Exception:
        raise HTTPException(status_code=422, detail="template scenario is invalid")
    # Goal authority = this template: freeze the charter into working_memory_seed.
    charter = WorkingMemoryCharter(
        goal=scenario.goal,
        phases=scenario.phases,
        checklist=scenario.checklist,
        time_budget_min=scenario.time_budget_min,
        language=scenario.language,
    )
    seed = WorkingMemory(charter=charter)  # state starts empty; executive fills it later
    title = body.title or tpl["name"]

    # The seed is the session's immutable charter fallback (EC-4). M6: it also
    # carries the template's optional scoring `rubric` (a sibling key — the
    # WorkingMemory model ignores extras), since the knowledge block holds only
    # charter+state. `evaluate` reads the rubric back from here.
    seed_json = seed.model_dump(mode="json")
    rubric = _jsonb(tpl["rubric"]) if tpl["rubric"] is not None else None
    if rubric:
        seed_json["rubric"] = rubric

    row = await pool.fetchrow(
        """
        INSERT INTO chat_sessions
          (owner_user_id, title, model_source, model_ref, system_prompt,
           project_id, working_memory_seed)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        RETURNING *
        """,
        user_id, title, str(model_source), str(model_ref), tpl["system_prompt"],
        str(body.project_id) if body.project_id else None,
        json.dumps(seed_json),
    )

    # Goal-authority write path → push the frozen charter to knowledge-service so
    # it owns the evolving block (the executive then updates state). Best-effort:
    # a failure leaves the session anchored from its own seed (EC-4).
    await get_knowledge_client().init_working_memory(
        session_id=str(row["session_id"]),
        user_id=user_id,
        charter=charter.model_dump(),
    )
    return _row_to_session(row)
