"""Auth for the TLE harness.

Primary: authenticate the test account through the REAL `/v1/auth/login` edge
(so the auth path is itself under test — CD/README §5). Fallback: self-mint an
HS256 JWT from JWT_SECRET (the legacy in-container pattern) when the edge is
unreachable or credentials are unset.
"""
from __future__ import annotations

import time

import httpx

from . import config


class Auth:
    def __init__(self) -> None:
        self._token: str | None = None
        self._exp: float = 0.0
        self.mode: str = "unknown"

    def _login_edge(self) -> str | None:
        try:
            r = httpx.post(
                f"{config.GATEWAY}/v1/auth/login",
                json={"email": config.TEST_EMAIL, "password": config.TEST_PASSWORD},
                timeout=30,
            )
            if r.status_code == 200:
                j = r.json()
                self._exp = time.time() + int(j.get("expires_in_seconds", 3600)) - 60
                self.mode = "login-edge"
                return j["access_token"]
        except Exception:
            pass
        return None

    def _self_mint(self) -> str | None:
        if not config.JWT_SECRET:
            return None
        try:
            import jwt
        except ImportError:
            return None
        now = int(time.time())
        self._exp = now + 3600 - 60
        self.mode = "self-mint"
        return jwt.encode(
            {"sub": config.USER_ID, "iat": now, "exp": now + 3600},
            config.JWT_SECRET,
            algorithm="HS256",
        )

    def token(self) -> str:
        """Cached bearer token; refreshes near expiry. Prefers the real edge."""
        if self._token and time.time() < self._exp:
            return self._token
        tok = self._login_edge() or self._self_mint()
        if not tok:
            raise RuntimeError(
                "auth failed: /v1/auth/login edge unreachable AND no JWT_SECRET "
                "for the self-mint fallback (set TLE_JWT_SECRET)."
            )
        self._token = tok
        return tok

    def bearer_header(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}"}
