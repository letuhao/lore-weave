"""Tool permissions — the management surface for the per-user consent allowlist.

Track C WS-3 (``D-C-ALLOWLIST-WRITE-ONLY``). ``user_tool_approvals`` was INSERT-ONLY:
the chat loop could WRITE a standing "Always allow" when the user clicked it on an
approval card, and nothing could ever read it back. A user could hand an autonomous
agent a permanent permission to write their data or spend their money and then had no
way to see the grant, withdraw it, or refuse the tool outright.

This router is the missing half of that loop — the Claude-Code ``/permissions`` analogue:

* ``GET    /v1/chat/tool-permissions``               — every standing decision, so a grant is VISIBLE
* ``PUT    /v1/chat/tool-permissions/{tool_name}``   — set ``allow`` (pre-approve) or ``deny`` ("never")
* ``DELETE /v1/chat/tool-permissions/{tool_name}``   — withdraw it; the tool prompts again next call

Tenancy: the owner is derived from the JWT (``get_current_user``) and NEVER from the
body or a query param — a consent surface that let a caller name the user whose
permissions it edits would be a far worse defect than the one it fixes.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Literal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from app.db.tool_approvals import (
    APPROVAL_KINDS,
    MUTATION_KIND,
    get_tool_decision,
    list_tool_decisions,
    revoke_tool_decision,
    set_tool_decision,
)
from app.deps import get_current_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat/tool-permissions", tags=["tool-permissions"])

# Closed sets — enum-validated on write (Frontend-Tool-Contract / SET-4 discipline).
# A free-string `kind` would silently write a row under a consent axis the gate never
# reads: the setting would GET back as effective and do nothing, forever.
_DECISIONS = ("allow", "deny")

# The storage key is `<kind>::<tool>` for non-mutation kinds, so a tool_name containing
# "::" would collide with that namespace: PUT /tool-permissions/spend::web_search with
# kind=mutation writes the key `spend::web_search` — i.e. it forges (or erases) the SPEND
# consent for `web_search` while claiming to touch `web_search`'s write consent. Real tool
# names are `[a-z0-9_]` identifiers, so the encoding is sound; this makes the invariant it
# relies on an ENFORCED one instead of an assumed one.
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,200}$")


class ToolPermission(BaseModel):
    tool_name: str
    kind: str = Field(description="mutation (may write) | spend (may cost money)")
    decision: str = Field(description="allow (Always allow) | deny (Never allow)")
    created_at: str


class ToolPermissionList(BaseModel):
    permissions: list[ToolPermission]


class SetPermissionBody(BaseModel):
    kind: Literal["mutation", "spend"] = MUTATION_KIND
    # NO DEFAULT — an omitted `decision` used to silently mean "allow", so a partial or
    # empty body created a standing GRANT. On a consent surface the safe failure is a 422,
    # never an unrequested permission.
    decision: Literal["allow", "deny"]


def _validate(tool_name: str, kind: str, decision: str | None = None) -> None:
    if not _TOOL_NAME_RE.match(tool_name):
        raise HTTPException(
            status_code=422,
            detail=(
                "tool_name must match [A-Za-z0-9_.-]{1,200} "
                "(in particular it may not contain '::')"
            ),
        )
    if kind not in APPROVAL_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"kind must be one of {list(APPROVAL_KINDS)}, got {kind!r}",
        )
    if decision is not None and decision not in _DECISIONS:
        raise HTTPException(
            status_code=422,
            detail=f"decision must be one of {list(_DECISIONS)}, got {decision!r}",
        )


@router.get("", response_model=ToolPermissionList)
async def list_permissions(
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ToolPermissionList:
    """Every standing tool decision this user has made."""
    rows = await list_tool_decisions(pool, user_id)
    return ToolPermissionList(
        permissions=[
            ToolPermission(
                tool_name=r["tool_name"],
                kind=r["kind"],
                decision=r["decision"],
                created_at=r["created_at"].isoformat(),
            )
            for r in rows
        ]
    )


@router.put("/{tool_name}", response_model=ToolPermission)
async def set_permission(
    body: SetPermissionBody,
    tool_name: str = Path(..., min_length=1, max_length=200),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ToolPermission:
    """Set a standing decision: ``allow`` (pre-approve, never prompt) or ``deny``
    ("Never allow" — the gate blocks the call outright instead of prompting)."""
    _validate(tool_name, body.kind, body.decision)
    await set_tool_decision(pool, user_id, tool_name, body.kind, body.decision)
    logger.info(
        "tool permission set: user=%s tool=%s kind=%s decision=%s",
        user_id, tool_name, body.kind, body.decision,
    )
    # Read back the EXACT key we wrote (not a scan of the decoded list — that mismatched
    # for any name the encoding could not round-trip, and then 500'd on a write that had
    # in fact persisted). Echoing the request body instead would be a fabricated 200: the
    # silent-success class this slice exists to kill.
    stored = await get_tool_decision(pool, user_id, tool_name, body.kind)
    if stored is None:
        raise HTTPException(status_code=500, detail="permission write did not persist")
    return ToolPermission(
        tool_name=tool_name, kind=body.kind, decision=stored,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@router.delete("/{tool_name}", status_code=204)
async def revoke_permission(
    tool_name: str = Path(..., min_length=1, max_length=200),
    kind: str = Query(default=MUTATION_KIND),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> None:
    """Withdraw a standing decision. The tool prompts again on its next call.

    404s when there was nothing to withdraw — a revoke that reported success for a
    permission that never existed would leave the user believing they had taken
    something back when they had not."""
    _validate(tool_name, kind)
    removed = await revoke_tool_decision(pool, user_id, tool_name, kind)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"no standing {kind} decision for {tool_name!r}",
        )
    logger.info(
        "tool permission revoked: user=%s tool=%s kind=%s", user_id, tool_name, kind
    )
