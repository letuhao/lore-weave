"""Public-API JWT authentication dependency (K7.1).

Thin binding of the shared `loreweave_authn` verifier to this service's JWT
secret. This module used to hand-roll the `jwt.decode(token,
settings.jwt_secret, algorithms=["HS256"])` block; that logic now lives once
in the SDK (`loreweave_authn.verify_access_token`) so the platform-user token
contract cannot drift across composition / knowledge / chat / … services.

Security invariants (enforced by the SDK — see its docstring):
  - HS256 ONLY (alg-pinned — rejects `alg:none` and any RS/EC/PS token).
  - `exp` is REQUIRED and enforced.
  - `sub` MUST parse as a UUID; that UUID is the authenticated `user_id`.
  - 401 is returned UNIFORMLY for every failure mode (missing header,
    malformed header, expired, bad signature, missing/invalid sub) via
    `HTTPBearer(auto_error=False)`, so a bad actor can't distinguish modes.

`user_id` is NEVER accepted from query string or body — the ONLY source of
truth is the JWT `sub` claim. Every public /v1/knowledge/* endpoint takes
`user_id: UUID = Depends(get_current_user)`.
"""

from __future__ import annotations

from loreweave_authn import bearer_scheme, build_get_current_user

from app.config import settings

__all__ = ["get_current_user", "bearer_scheme"]

# Bound to this service's shared HS256 secret; returns the `sub` UUID — the
# exact shape every knowledge-service route already expects. `secret_provider`
# is called per-request so a rotated secret is picked up without re-import.
get_current_user = build_get_current_user(lambda: settings.jwt_secret)
