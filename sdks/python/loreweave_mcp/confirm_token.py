"""Confirm-token spine (INV-9) — PORTED from the Go/glossary scheme in
``services/glossary-service/internal/api/action_confirm_token.go`` so a token
minted by the Go kit verifies in the Python kit and vice-versa.

WIRE FORMAT (must stay byte-identical to the Go kit — S-KIT-GO):

    token := base64url(payload_json) + "." + base64url(hmac_sha256(secret, domain || payloadB64))

  - base64url = URL-safe base64, NO padding (Go ``base64.RawURLEncoding``).
  - signature = HMAC-SHA256 keyed by the service secret, over the bytes
    ``DOMAIN || payloadB64`` where ``DOMAIN = "lw-action-confirm:v1|"`` is a
    domain separator written BEFORE the payload (Go writes the domain then the
    payloadB64 into the same HMAC — `actionTokenSign`). The separator guarantees a
    confirm token can never be confused with a real JWT.
  - constant-time signature compare on verify; signature/format/unknown → INVALID;
    valid-but-stale → EXPIRED (distinct, so the UI says "re-propose" not "denied").

CLAIM JSON SHAPE (compact keys — must match Go ``actionClaims`` tags exactly):

    { "u":   "<user_id uuid>",        // the proposing user (identity binding)
      "r":   "<resource_id uuid>",    // book/model/record the action targets
      "d":   "<descriptor>",          // e.g. "book.publish_batch", "translation.start_job"
      "p":   <opaque payload json>,   // the resolved action-spec captured at propose time
      "exp": <unix seconds> }         // absolute expiry

The token binds intent (descriptor) + identity (u) + resource (r) + payload (p) +
expiry. Single-use is NOT in the token (it is stateless) — a consuming service that
needs one-shot semantics records the (u, r, d, exp) in its own consumed-token ledger
at confirm time. The kit provides only the stateless bind+verify.

NOTE for Go/Py alignment: the Go glossary file uses ``jti`` + ``auth`` + ``b``
(book) keys for its richer scheme. The FROZEN C-KIT shape here is the SMALLER,
domain-agnostic ``{u, r, d, p, exp}`` (resource-generic, not book-specific) so the
SAME claim shape serves book / settings / translation. S-KIT-GO must emit/verify
THIS shape (see the report note for reconciliation).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

__all__ = [
    "ConfirmClaims",
    "ConfirmTokenError",
    "ConfirmTokenInvalid",
    "ConfirmTokenExpired",
    "mint_confirm_token",
    "verify_confirm_token",
]

# Domain separator — MUST match the Go kit byte-for-byte. (Distinct from the
# glossary file's legacy "gloss-action-confirm:v1|" because the C-KIT spine is
# the platform-wide, domain-agnostic shape; S-KIT-GO uses this same constant.)
_DOMAIN = b"lw-action-confirm:v1|"

DEFAULT_TTL_S = 600  # 10 minutes — human has time to read + confirm (mirrors Go)


class ConfirmTokenError(Exception):
    """Base for confirm-token failures."""


class ConfirmTokenInvalid(ConfirmTokenError):
    """Signature/format mismatch, or required claim missing/malformed."""


class ConfirmTokenExpired(ConfirmTokenError):
    """A structurally-valid, correctly-signed token whose ``exp`` has passed."""


@dataclass(frozen=True)
class ConfirmClaims:
    user_id: UUID
    resource_id: UUID
    descriptor: str
    payload: Any
    exp: int  # unix seconds


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    # Re-pad for the stdlib decoder (Go RawURLEncoding emits no padding).
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(secret: str, payload_b64: str) -> bytes:
    mac = hmac.new(secret.encode("utf-8"), digestmod=hashlib.sha256)
    mac.update(_DOMAIN)
    mac.update(payload_b64.encode("ascii"))
    return mac.digest()


def mint_confirm_token(
    secret: str,
    user_id: UUID,
    resource_id: UUID,
    descriptor: str,
    payload: Any,
    ttl: int = DEFAULT_TTL_S,
    *,
    now: float | None = None,
) -> str:
    """Mint a stateless HMAC confirm token binding (user, resource, descriptor,
    payload) with an absolute expiry ``now + ttl``.

    An empty secret or descriptor is a misconfiguration → raises
    ``ConfirmTokenInvalid`` (caller treats "cannot mint" as fail-closed, never
    issuing an unsigned token). ``now`` is injectable for tests.
    """
    if not secret:
        raise ConfirmTokenInvalid("cannot mint: empty secret")
    if not descriptor or not descriptor.strip():
        raise ConfirmTokenInvalid("cannot mint: empty descriptor")
    issued = time.time() if now is None else now
    claims = {
        "u": str(user_id),
        "r": str(resource_id),
        "d": descriptor,
        "p": payload,
        "exp": int(issued) + int(ttl),
    }
    # Sort keys for a deterministic encoding (helps cross-impl reproducibility of
    # logs/tests; the signature does not require it but determinism is cheap).
    payload_json = json.dumps(claims, separators=(",", ":"), sort_keys=True)
    payload_b64 = _b64url_encode(payload_json.encode("utf-8"))
    sig = _sign(secret, payload_b64)
    return payload_b64 + "." + _b64url_encode(sig)


def verify_confirm_token(
    secret: str, token: str, *, now: float | None = None
) -> ConfirmClaims:
    """Verify a confirm token: constant-time signature check, required-claim
    validation, then expiry.

    - bad secret / format / signature / missing-or-malformed claim →
      ``ConfirmTokenInvalid``.
    - correctly-signed but stale → ``ConfirmTokenExpired`` (distinct so the UI can
      say "re-propose").
    """
    if not secret:
        raise ConfirmTokenInvalid("empty secret")
    parts = token.split(".")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ConfirmTokenInvalid("malformed token")

    payload_b64, sig_b64 = parts
    try:
        sig = _b64url_decode(sig_b64)
    except (ValueError, base64.binascii.Error):
        raise ConfirmTokenInvalid("malformed signature")

    expected = _sign(secret, payload_b64)
    if not hmac.compare_digest(sig, expected):
        raise ConfirmTokenInvalid("signature mismatch")

    try:
        payload_raw = _b64url_decode(payload_b64)
        claims = json.loads(payload_raw)
    except (ValueError, base64.binascii.Error):
        raise ConfirmTokenInvalid("malformed payload")
    if not isinstance(claims, dict):
        raise ConfirmTokenInvalid("malformed payload")

    try:
        user_id = UUID(str(claims["u"]))
        resource_id = UUID(str(claims["r"]))
        descriptor = str(claims["d"])
        exp = int(claims["exp"])
    except (KeyError, ValueError, TypeError):
        raise ConfirmTokenInvalid("missing or malformed claim")
    if not descriptor.strip():
        raise ConfirmTokenInvalid("empty descriptor")

    current = time.time() if now is None else now
    if int(current) >= exp:
        raise ConfirmTokenExpired("token has expired")

    return ConfirmClaims(
        user_id=user_id,
        resource_id=resource_id,
        descriptor=descriptor,
        payload=claims.get("p"),
        exp=exp,
    )
