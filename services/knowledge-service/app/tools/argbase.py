"""Shared arg-model base for project-scoped MCP tools (H-I).

`ProjectScopedArgs` adds an OPTIONAL, ownership-checked ``project_id`` parameter.
The public MCP edge (`mcp-public-gateway`) mints NO ``X-Project-Id`` envelope
header, so a public agent has no other way to say which project a call targets —
it supplies it here. The trusted envelope still WINS when present (a first-party
chat session's project scope is authoritative — see ``_resolve_project_scope`` in
``executor.py``); the arg only SUPPLIES scope when the envelope has none.

INV-K2 amendment: ``user_id`` and ``session_id`` remain envelope-only FOREVER —
they are identity/session and an LLM must never set them. ``project_id`` is the
single deliberate exception: it is a *selector*, not identity, and is confined by
the per-call owner gate (a caller can only ever address a project it owns — see
``_require_project_owner_memory`` / ``_resolve_project_owner``). A hallucinated or
hostile ``project_id`` therefore cannot escape the caller's own tenancy.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_PROJECT_ID_DESC = (
    "Knowledge project to scope this call to. Omit to use the project linked to "
    "the current session. On the public API there is no session project, so set "
    "this to the id of one of YOUR projects (you can only address projects you own)."
)


class ProjectScopedArgs(BaseModel):
    """Base for tool arg models that operate within a knowledge project."""

    model_config = ConfigDict(extra="forbid")
    project_id: str | None = Field(default=None, description=_PROJECT_ID_DESC)
