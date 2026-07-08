"""loreweave_mcp — the shared Python MCP kit (C-KIT-PY).

The single package every Python MCP *provider* service (jobs, composition,
translation) uses to stand up an internal `/mcp` server with consistent
identity handling, ownership guards, confirm-token minting, and tool-metadata
enforcement — so 5 Python services do NOT each re-derive these (spec §4.1, INV-7).

What is **extracted** from a proven shape (knowledge-service `app/mcp/server.py`):
  - `make_stateless_fastmcp` — the `stateless_http=True, streamable_http_path="/"`
    + DNS-rebinding-disabled wiring.
  - `build_tool_context` — `X-Internal-Token` constant-time check (SEC-1) then
    lift `X-User-Id / X-Project-Id / X-Session-Id / X-Trace-Id` from headers into
    a `ToolContext`. Identity is ALWAYS from the envelope, never a tool arg.
  - `ForbidExtra` — the `extra="forbid"` arg-model base (INV-2).
  - `TolerantArgs` — the `extra="ignore"` sibling (IN-5, mcp-tool-io.md): same
    never-declare-identity rule, but a harmless unknown field is dropped, not a
    hard validation error.

What is **built fresh** (no existing instance):
  - `require_book_owner` / `require_user_scope` / `require_project` — the THREE
    scope guards (H15), fail-closed, the book guard with a ~60s positive cache.
  - `uniform_not_accessible` — H13 collapse of 403/404 to one error (no
    enumeration oracle).
  - `mint_confirm_token` / `verify_confirm_token` — the confirm-token spine,
    PORTED from the Go/glossary HMAC-SHA256 scheme so Go and Python agree on the
    wire format (INV-9).
  - `validate_tool_meta` / `require_meta` — reject a tool registered without
    `_meta.tier` AND `_meta.scope` (C-TOOL enforcement).
"""

from __future__ import annotations

from .compact_content import (
    patch_convert_result,
)
from .confirm_token import (
    ConfirmClaims,
    ConfirmTokenError,
    ConfirmTokenExpired,
    ConfirmTokenInvalid,
    mint_confirm_token,
    verify_confirm_token,
)
from .context import (
    ToolContext,
    apply_public_key_attribution_headers,
    build_tool_context,
    is_owner_only,
    make_stateless_fastmcp,
)
from .errors import (
    ForbidExtra,
    NotAccessibleError,
    TolerantArgs,
    uniform_not_accessible,
)
from .guards import (
    GrantResolver,
    OwnerResolver,
    require_book_owner,
    require_project,
    require_user_scope,
)
from .meta import (
    SCOPES,
    TIERS,
    MetaValidationError,
    require_meta,
    validate_tool_meta,
)
from .response import (
    DetailLevel,
    apply_response_contract,
)
from .shape_snapshot import (
    assert_or_write_shape_snapshot,
    build_shape_map,
    repo_root_from,
)

__all__ = [
    # context / server wiring
    "make_stateless_fastmcp",
    "build_tool_context",
    "ToolContext",
    "is_owner_only",
    "apply_public_key_attribution_headers",
    # arg models + uniform error (H13)
    "ForbidExtra",
    "TolerantArgs",
    "uniform_not_accessible",
    "NotAccessibleError",
    # scope guards (H15)
    "require_book_owner",
    "require_user_scope",
    "require_project",
    "GrantResolver",
    "OwnerResolver",
    # confirm-token spine (INV-9)
    "mint_confirm_token",
    "verify_confirm_token",
    "ConfirmClaims",
    "ConfirmTokenError",
    "ConfirmTokenInvalid",
    "ConfirmTokenExpired",
    # _meta validator (C-TOOL)
    "validate_tool_meta",
    "require_meta",
    "MetaValidationError",
    "TIERS",
    "SCOPES",
    # L1/L2 tool-response contract (Context Budget Law §6b)
    "apply_response_contract",
    "DetailLevel",
    # §13b response-shape snapshot guard (anti re-bloat)
    "assert_or_write_shape_snapshot",
    "build_shape_map",
    "repo_root_from",
    # external MCP discoverability audit #9 — payload-duplication fix
    "patch_convert_result",
]
