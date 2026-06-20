"""KM6 — generalized class-C confirm-token codec (spec §13).

Python port of glossary's `action_confirm_token.go` (read-only reference). Same
stateless-HMAC scheme — a token is an HMAC over the claims, keyed by the service
`jwt_secret` with a **domain separator** so it can never be confused with a real
JWT (or with a glossary action token). Forging one requires the JWT secret, i.e. a
full service compromise — out of scope, unchanged threat model.

The token binds intent + authority + identity + scope + expiry. It is NOT itself
single-use (it is stateless); single-use is enforced at confirm time by recording
the `jti` in the `consumed_tokens` ledger (§13.4, `action_tokens.py`).

Descriptors are a CLOSED enum validated on BOTH mint and verify — an unknown or
not-yet-wired descriptor fails closed, so a token can never carry intent the confirm
path does not fully validate.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ACTION_TOKEN_TTL_S",
    "AUTH_GRANT",
    "AUTH_ADMIN",
    "DESC_SCHEMA_EDIT",
    "DESC_ADOPT",
    "ActionClaims",
    "ActionTokenInvalid",
    "ActionTokenExpired",
    "live_descriptor",
    "mint_action_token",
    "verify_action_token",
]

# Domain separator — DISTINCT from glossary's "gloss-action-confirm:v1|" so a token
# minted for one domain can never verify in the other. Bumped with the wire format.
_ACTION_TOKEN_DOMAIN = b"kg-action-confirm:v1|"
ACTION_TOKEN_TTL_S = 10 * 60  # human has time to read + confirm

# Authority kinds — select the confirm-time re-check branch (§13.5).
AUTH_GRANT = "grant"  # project/user tiers: re-check proposing user + MANAGE grant
AUTH_ADMIN = "admin"  # System tier: re-check the RS256 admin authority (KM5)

# Action descriptors LIVE in this build (§13.1). Reserved descriptors
# (kg_sync_apply, kg_triage_schema, kg_triage_handoff, kg_system_*) are intentionally
# NOT accepted yet — verify/mint fail closed on them until their phase wires the
# effect + preview.
DESC_SCHEMA_EDIT = "kg_schema_edit"
DESC_ADOPT = "kg_adopt"
_LIVE_DESCRIPTORS: frozenset[str] = frozenset({DESC_SCHEMA_EDIT, DESC_ADOPT})


class ActionTokenInvalid(Exception):
    """Signature / format / unknown-descriptor / bad-authority — not redeemable."""


class ActionTokenExpired(Exception):
    """Valid token past its TTL — distinct so the UI says 're-propose'."""


def live_descriptor(d: str) -> bool:
    """True iff the descriptor is wired in THIS build. Unknown / not-yet-live →
    rejected at mint and verify (fail closed)."""
    return d in _LIVE_DESCRIPTORS


@dataclass
class ActionClaims:
    """The signed payload. ``params`` is the opaque action-spec captured at mint
    (resolved ids, validated codes); confirm trusts it because it is inside the HMAC
    but STILL re-validates against current state (§13.5)."""

    jti: str
    authority: str
    user_id: str          # grant authority: the proposing user (uuid str)
    descriptor: str
    project_id: str = ""   # knowledge is project-scoped (vs glossary book-scoped)
    params: dict[str, Any] = field(default_factory=dict)
    admin_sub: str = ""    # admin authority: the RS256 subject (KM5, reserved)
    exp: int = 0           # unix seconds

    def _payload(self) -> dict[str, Any]:
        # Compact wire keys (mirror the Go json tags), stable order via sort_keys.
        return {
            "jti": self.jti,
            "auth": self.authority,
            "u": self.user_id,
            "asub": self.admin_sub,
            "pid": self.project_id,
            "d": self.descriptor,
            "p": self.params,
            "exp": self.exp,
        }

    @classmethod
    def _from_payload(cls, d: dict[str, Any]) -> "ActionClaims":
        return cls(
            jti=str(d.get("jti", "")),
            authority=str(d.get("auth", "")),
            user_id=str(d.get("u", "")),
            admin_sub=str(d.get("asub", "")),
            project_id=str(d.get("pid", "")),
            descriptor=str(d.get("d", "")),
            params=d.get("p") or {},
            exp=int(d.get("exp", 0)),
        )


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(secret: str, payload_b64: str) -> bytes:
    mac = hmac.new(secret.encode("utf-8"), digestmod=hashlib.sha256)
    mac.update(_ACTION_TOKEN_DOMAIN)
    mac.update(payload_b64.encode("ascii"))
    return mac.digest()


def mint_action_token(secret: str, claims: ActionClaims, now: float) -> str:
    """Sign a confirm token. The caller fills authority/descriptor/identity/scope/
    params + a fresh jti; mint stamps the expiry. An empty secret/jti or a non-live
    descriptor is a misconfiguration → empty token (caller treats as 'cannot mint',
    fail closed). ``now`` is unix seconds."""
    if not secret or not claims.jti.strip() or not live_descriptor(claims.descriptor):
        return ""
    claims.exp = int(now) + ACTION_TOKEN_TTL_S
    payload = json.dumps(claims._payload(), separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url(payload)
    sig = _sign(secret, payload_b64)
    return payload_b64 + "." + _b64url(sig)


def verify_action_token(secret: str, token: str, now: float) -> ActionClaims:
    """Constant-time signature check + live-descriptor + authority + expiry. Signature/
    format/unknown-descriptor/bad-authority → ``ActionTokenInvalid``; a valid-but-stale
    token → ``ActionTokenExpired``. ``now`` is unix seconds."""
    if not secret:
        raise ActionTokenInvalid()
    parts = token.split(".")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ActionTokenInvalid()
    try:
        sig = _b64url_decode(parts[1])
    except (ValueError, TypeError):
        raise ActionTokenInvalid()
    expected = _sign(secret, parts[0])
    if not hmac.compare_digest(sig, expected):
        raise ActionTokenInvalid()
    try:
        payload = _b64url_decode(parts[0])
        data = json.loads(payload)
    except (ValueError, TypeError):
        raise ActionTokenInvalid()
    if not isinstance(data, dict):
        raise ActionTokenInvalid()
    claims = ActionClaims._from_payload(data)
    if not live_descriptor(claims.descriptor) or not claims.jti.strip():
        raise ActionTokenInvalid()
    if claims.authority not in (AUTH_GRANT, AUTH_ADMIN):
        raise ActionTokenInvalid()
    if int(now) >= claims.exp:
        raise ActionTokenExpired()
    return claims
