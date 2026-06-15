"""Control routing (Unified Job Control Plane P3).

jobs-service is the single control surface: `POST /v1/jobs/{service}/{job_id}/
{action}` verifies the caller owns the job (against the projection) + that the
action is valid for the job's CURRENT state, then **forwards** to the owning
service's internal `job_id`-keyed control endpoint over internal-token auth. The
owning service RE-VERIFIES ownership on the actual row (spec M4) — the projection
is a possibly-stale mirror, never the authority for a mutation.

`_CONTROL` is the registry of services that have shipped a P3 internal job-control
endpoint. It grows one service per P3 increment; a job whose service is NOT listed
returns 501 (honest — control isn't silently dropped, it's "not yet supported").
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from .config import settings

log = logging.getLogger(__name__)

VALID_ACTIONS = ("cancel", "pause", "resume")

# service (as stored in job_projection.service) → (internal base url, control path
# prefix). Path = f"{base}{prefix}/{job_id}/{action}". Underscored service names
# (lore_enrichment/video_gen) map to their hyphenated URL prefixes here.
_CONTROL: dict[str, tuple[str, str]] = {
    "knowledge": (settings.knowledge_service_internal_url, "/internal/knowledge/jobs"),
    "composition": (settings.composition_service_internal_url, "/internal/composition/jobs"),
    "video_gen": (settings.video_gen_service_internal_url, "/internal/video_gen/jobs"),
    # P3-3+: translation / lore_enrichment as they ship.
}

_TIMEOUT = httpx.Timeout(10.0)


class ControlResult:
    """The forwarded outcome the router relays back to the caller."""

    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self.body = body


def is_supported(service: str) -> bool:
    return service in _CONTROL


async def forward_control(service: str, job_id: str, action: str, owner_user_id: str) -> ControlResult:
    """Forward a control action to the owning service's internal endpoint.

    Returns a ControlResult mirroring the downstream status (the owning service is
    authoritative — it re-checks owner + validates the transition). A downstream
    network failure → 502 so the caller can retry; an unknown service → 501."""
    entry = _CONTROL.get(service)
    if entry is None:
        return ControlResult(501, {"detail": f"control not yet supported for service '{service}'"})
    base, prefix = entry
    url = f"{base}{prefix}/{job_id}/{action}"
    headers = {"X-Internal-Token": settings.internal_service_token}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json={"owner_user_id": owner_user_id}, headers=headers)
    except httpx.HTTPError as exc:
        log.warning("control forward to %s failed: %s", url, exc)
        return ControlResult(502, {"detail": f"owning service '{service}' unreachable"})
    try:
        body = resp.json()
    except ValueError:
        body = {"detail": resp.text}
    return ControlResult(resp.status_code, body)
