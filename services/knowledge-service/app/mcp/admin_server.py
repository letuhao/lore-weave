"""KM5-M3 — the `/mcp/admin` MCP server (System-tier, RS256-gated).

A SECOND, physically separate MCP endpoint (INV-T6): admin tool names + schemas
must NEVER appear in the `/mcp` catalog. Mounted at `/mcp/admin`, gated by an
RS256 `X-Admin-Token` at the TRANSPORT — verified BEFORE `tools/list`, so no
token = 401 and the surface cannot even be enumerated.

Two tools (spec §3f):
  - `kg_admin_template_read` (R) — list System templates.
  - `kg_admin_propose_template` (C) — verb create|patch|delete. MINTS an
    `auth=admin` confirm-token (`asub` = the verified RS256 subject) + a preview;
    it does NOT write. The human admin redeems the token at
    `POST /v1/kg/actions/confirm` (re-presenting the same X-Admin-Token), where
    the System write actually happens (KM5-M2). LLM never mutates System directly.

Defense in depth: (1) the transport gate blocks enumeration without a verified
admin token; (2) each tool re-verifies the token to recover its claims + checks
`admin:write` for the mint; (3) the confirm endpoint re-verifies AGAIN + binds
`sub == asub` before the single-use write. Three independent checks, INV-T2/T3/T6.
"""

from __future__ import annotations

import logging
import time
from typing import Annotated, Literal
from uuid import uuid4

from mcp.server.fastmcp import Context as MCPContext
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.responses import JSONResponse

from app.auth.admin_jwt import SCOPE_ADMIN_WRITE, AdminClaims, AdminTokenInvalid, verify_admin_token
from app.auth.admin_key import get_admin_key
from app.config import settings
from app.db.pool import get_knowledge_pool
from app.db.repositories.system_templates import SystemTemplatesRepo
from app.ontology.confirm import (
    ACTION_TOKEN_TTL_S,
    AUTH_ADMIN,
    ActionClaims,
    mint_action_token,
)
from app.ontology.system_effect import (
    DESCRIPTOR_BY_VERB,
    SystemTemplateParams,
    preview_system_template,
)

logger = logging.getLogger(__name__)

__all__ = ["mcp_admin_server", "build_admin_mcp_app", "rs256_gate"]

mcp_admin_server = FastMCP(
    "knowledge-admin",
    stateless_http=True,
    streamable_http_path="/",
    # Same rationale as the /mcp server: internal service-to-service transport on
    # the private network; the trust boundary is the RS256 admin token, not the
    # Host header. (DNS-rebinding protection matters for browser-facing servers.)
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _admin_claims(ctx: MCPContext) -> AdminClaims:
    """Re-verify the RS256 admin token from the MCP request → claims. Raises
    ValueError (surfaced as an MCP tool error) on any failure. The transport gate
    already proved a valid token to enumerate; this recovers the claims (sub for
    the asub bind, scopes for the write gate)."""
    key = get_admin_key()
    if key is None:
        raise ValueError("system-tier administration is not configured")
    token = ctx.request_context.request.headers.get("x-admin-token")
    if not token:
        raise ValueError("missing admin token")
    try:
        return verify_admin_token(token, key)
    except AdminTokenInvalid:
        raise ValueError("invalid admin token")


def _summary(s) -> dict:
    return {
        "schema_id": str(s.schema_id), "code": s.code, "name": s.name,
        "schema_version": s.schema_version, "deprecated": s.deprecated_at is not None,
    }


@mcp_admin_server.tool(
    name="kg_admin_template_read",
    description=(
        "List the System-tier graph-schema templates (admin surface). Returns each "
        "template's code, name, schema_version, and deprecation state. Read-only."
    ),
)
async def kg_admin_template_read(
    ctx: MCPContext,
    include_deprecated: Annotated[
        bool, "Include soft-deprecated templates (default false)."
    ] = False,
) -> dict:
    _admin_claims(ctx)  # any valid admin token may read
    repo = SystemTemplatesRepo(get_knowledge_pool())
    rows = await repo.list_templates(include_deprecated=include_deprecated)
    return {"templates": [_summary(r) for r in rows]}


@mcp_admin_server.tool(
    name="kg_admin_propose_template",
    description=(
        "Propose a System-tier graph-template change for human-admin confirmation. "
        "verb = create | patch | delete. MINTS a single-use confirm-token + a "
        "preview of the change; it does NOT write. The human admin confirms at "
        "/v1/kg/actions/confirm (re-presenting their admin token) to apply it. "
        "create: code + name. patch/delete: schema_id (patch carries "
        "expected_schema_version + the fields to change)."
    ),
)
async def kg_admin_propose_template(
    ctx: MCPContext,
    verb: Annotated[Literal["create", "patch", "delete"], "The proposed operation."],
    code: Annotated[str, "create: the new template's unique code."] = "",
    name: Annotated[str, "create: the template name; patch: the new name."] = "",
    description: Annotated[str | None, "Optional description (create/patch)."] = None,
    allow_free_edges: Annotated[
        bool | None, "Optional — whether the template allows free-string edges."
    ] = None,
    schema_id: Annotated[str, "patch/delete: the target template's schema_id."] = "",
    expected_schema_version: Annotated[
        int | None,
        Field(ge=0),
        "patch: the schema_version you saw (optimistic-concurrency anchor).",
    ] = None,
) -> dict:
    claims = _admin_claims(ctx)
    if not claims.has_scope(SCOPE_ADMIN_WRITE):
        raise ValueError("missing required admin scope (admin:write)")
    if not claims.sub.strip():
        raise ValueError("admin token has no subject")

    try:
        params = SystemTemplateParams(
            verb=verb, code=code, name=name, description=description,
            allow_free_edges=allow_free_edges, schema_id=schema_id,
            expected_schema_version=expected_schema_version,
        )
    except ValueError as exc:  # pydantic validation → clear tool error
        raise ValueError(str(exc))

    descriptor = DESCRIPTOR_BY_VERB[verb]
    token = mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=str(uuid4()), authority=AUTH_ADMIN, user_id="",
            descriptor=descriptor, project_id="", admin_sub=claims.sub,
            params=params.model_dump(),
        ),
        time.time(),
    )
    if not token:  # only if the descriptor is non-live / secret unset (fail closed)
        raise ValueError("cannot mint confirm-token for this action")

    repo = SystemTemplatesRepo(get_knowledge_pool())
    preview = await preview_system_template(repo, params)
    return {"confirm_token": token, "expires_in": ACTION_TOKEN_TTL_S, "preview": preview}


# ── RS256-gated ASGI factory (transport gate BEFORE tools/list) ───────────────
def build_admin_mcp_app():
    """Wrap the admin MCP ASGI app with an RS256 gate that runs on EVERY request
    (including `tools/list`), so the admin surface cannot be enumerated without a
    verified `X-Admin-Token` (INV-T6). 503 if admin is disabled, 401 otherwise."""
    return rs256_gate(mcp_admin_server.streamable_http_app())


def rs256_gate(inner):
    """The transport RS256 gate as a reusable ASGI wrapper (extracted for unit
    tests). Verifies `X-Admin-Token` BEFORE delegating to ``inner`` — a missing/
    invalid token short-circuits to 401 and ``inner`` never runs, so the wrapped
    surface cannot be enumerated."""

    async def gated(scope, receive, send):
        if scope["type"] != "http":
            await inner(scope, receive, send)
            return
        key = get_admin_key()
        if key is None:
            await _reject(scope, receive, send, 503, "system-tier administration is not configured")
            return
        token = _header(scope, b"x-admin-token")
        if not token:
            await _reject(scope, receive, send, 401, "admin token required")
            return
        try:
            verify_admin_token(token, key)
        except AdminTokenInvalid:
            await _reject(scope, receive, send, 401, "invalid admin token")
            return
        await inner(scope, receive, send)

    return gated


def _header(scope, name: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k == name:
            return v.decode("latin-1")
    return None


async def _reject(scope, receive, send, status_code: int, detail: str) -> None:
    # JSONResponse is itself an ASGI app; drive it with the real scope/receive so
    # it sends a well-formed http.response.start + body.
    await JSONResponse({"detail": detail}, status_code=status_code)(scope, receive, send)
