"""Confirm resolver — the single biggest gap the harness closes.

No NL harness in this repo posts to `/v1/<domain>/actions/confirm`, so every
Tier-W tool suspends after minting a `confirm_token` and never executes — which is
exactly why the S06 baseline recorded `effectful_tool_calls: 0`.

This module:
  1. detects a `confirm_token` anywhere in a tool's result envelope,
  2. POSTs it to the owning domain's confirm route (Bearer JWT edge; the same route
     the browser UI uses — body `{confirm_token, enabled_ops?}`, verified against
     `glossary-service/internal/api/action_confirm.go`),
  3. returns (ok, status, body) so the caller resumes the run and reads the effect.

Route contract (verified in source): dual-auth — a user Bearer JWT (browser path)
OR an internal envelope (`X-Internal-Token` + `X-User-Id`). We use the Bearer edge
first (auth path under test); internal envelope is the fallback.
"""
from __future__ import annotations

import httpx

from . import config
from .auth import Auth

# Result keys that may carry a confirm token (scan defensively; token names vary).
_TOKEN_KEYS = ("confirm_token", "confirmToken", "token")


def find_confirm_token(result) -> str | None:
    """Recursively scan a tool-result envelope for a confirm token."""
    if isinstance(result, dict):
        for k in _TOKEN_KEYS:
            v = result.get(k)
            if isinstance(v, str) and v:
                return v
        for v in result.values():
            t = find_confirm_token(v)
            if t:
                return t
    elif isinstance(result, list):
        for v in result:
            t = find_confirm_token(v)
            if t:
                return t
    return None


def domain_of(tool_name: str) -> str:
    """Prefix-derived domain (matches the platform's own `_domain_of`)."""
    prefix = tool_name.split("_", 1)[0]
    return {
        "glossary": "glossary", "book": "book", "kg": "knowledge",
        "knowledge": "knowledge", "composition": "composition",
        "translation": "translation", "plan": "composition",
    }.get(prefix, prefix)


def confirm(auth: Auth, tool_name: str, token: str, *,
            enabled_ops: list | None = None) -> tuple[bool, int, object]:
    """Redeem a confirm token via the owning domain's confirm route.

    Tries the gateway edge first (Bearer JWT — the real browser path, so the auth
    edge is under test), then the direct service port with the internal envelope.
    Returns (ok, status_code, body).
    """
    domain = domain_of(tool_name)
    body: dict = {"confirm_token": token}
    if enabled_ops is not None:
        body["enabled_ops"] = enabled_ops
    path = f"/v1/{domain}/actions/confirm"

    # 1) gateway edge, Bearer JWT (auth path under test)
    for base, headers in (
        (config.GATEWAY, auth.bearer_header()),
        (config.DOMAIN_BASE.get(domain, ""), {
            "X-Internal-Token": config.INTERNAL_TOKEN, "X-User-Id": config.USER_ID}),
    ):
        if not base:
            continue
        try:
            r = httpx.post(f"{base}{path}", json=body, headers=headers, timeout=180)
        except Exception as e:
            last = (False, 0, f"{type(e).__name__}: {e}")
            continue
        ct = r.headers.get("content-type", "")
        parsed = r.json() if ct.startswith("application/json") else r.text
        if r.status_code in (200, 201, 202):
            return True, r.status_code, parsed
        last = (False, r.status_code, parsed)
    return last
