"""Reasoning-effort grant clamp (D-RE-OTHER-AGENTIC-EFFORT).

Reasoning effort is PAID compute; a non-owner must not escalate spend on a project they were
only granted limited access to past their grant ceiling (INV-T11). Mirrors translation-service's
`clamp_effort_to_grant` (kept LOCAL rather than promoted to `loreweave_grants` to avoid
re-triggering the SDK-distribution split — a small duplication is the cheaper trade). Applied at
BOTH the mint (the agentic build tools) AND re-applied at confirm (so a grant downgrade inside
the confirm-token TTL can't replay a now-too-high effort).
"""
from __future__ import annotations

from loreweave_grants import GrantLevel

# none < low < medium < high.
_EFFORT_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
# Per-grant ceiling: View/None can't reason; Edit caps at medium; Manage/Owner at high.
_EFFORT_CEILING_BY_GRANT = {
    GrantLevel.NONE: "none",
    GrantLevel.VIEW: "none",
    GrantLevel.EDIT: "medium",
    GrantLevel.MANAGE: "high",
    GrantLevel.OWNER: "high",
}


def clamp_effort_to_grant(requested: str | None, grant_level: GrantLevel) -> tuple[str, bool]:
    """Clamp a requested reasoning effort to the caller's grant ceiling. Returns
    ``(clamped_effort, was_capped)``. Unknown/empty/``"off"`` → ``"none"``; an out-of-range
    grant → NONE (fail-closed)."""
    req = (requested or "none").strip().lower()
    if req == "off":
        req = "none"
    if req not in _EFFORT_RANK:
        req = "none"
    try:
        gl = GrantLevel(grant_level)
    except (ValueError, TypeError):
        gl = GrantLevel.NONE
    ceiling = _EFFORT_CEILING_BY_GRANT.get(gl, "none")
    if _EFFORT_RANK[req] > _EFFORT_RANK[ceiling]:
        return ceiling, True
    return req, False
