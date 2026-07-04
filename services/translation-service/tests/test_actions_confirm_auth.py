"""D-PMCP-WORKER-CARRIER — the translation confirm-route dual-mode auth helpers.

The confirm route is the single spend path for priced translation tools. It must
accept BOTH the FE confirm card (user JWT + token in body) AND the public-MCP
auth-service replay (X-Internal-Token + X-User-Id + ?token= + X-Mcp-Key-Id). The
attribution headers are honored ONLY on the trusted internal-token path — a
first-party JWT caller must never be able to tag spend to an arbitrary key.
"""

from __future__ import annotations

import time

import jwt
import pytest
from fastapi import HTTPException

from app.config import settings as app_settings
from app.routers.actions import _parse_spend_cap, _resolve_confirm_caller

USER = "11111111-1111-1111-1111-111111111111"


def _jwt(sub: str) -> str:
    # A realistic FE user token: HS256 + `exp` (the shared loreweave_authn verifier
    # REQUIRES exp, as real auth-service tokens always carry it).
    now = int(time.time())
    return jwt.encode(
        {"sub": sub, "iat": now, "exp": now + 300}, app_settings.jwt_secret, algorithm="HS256"
    )


class TestParseSpendCap:
    def test_none_and_blank_and_garbage_are_none(self):
        assert _parse_spend_cap(None) is None
        assert _parse_spend_cap("") is None
        assert _parse_spend_cap("not-a-number") is None

    def test_valid_float(self):
        assert _parse_spend_cap("2.5") == 2.5
        assert _parse_spend_cap("0") == 0.0


class TestResolveConfirmCaller:
    def test_replay_path_authenticates_and_lifts_key(self):
        caller, key, cap = _resolve_confirm_caller(
            x_internal_token=app_settings.internal_service_token,
            x_user_id=USER,
            authorization=None,
            x_mcp_key_id="mk_live_abc",
            x_mcp_spend_cap_usd="3.0",
        )
        assert caller == USER
        assert key == "mk_live_abc"
        assert cap == 3.0

    def test_replay_path_invalid_internal_token_401(self):
        with pytest.raises(HTTPException) as exc:
            _resolve_confirm_caller("wrong-token", USER, None, "mk_live_abc", "3.0")
        assert exc.value.status_code == 401

    def test_replay_path_missing_user_id_401(self):
        with pytest.raises(HTTPException) as exc:
            _resolve_confirm_caller(app_settings.internal_service_token, None, None, "mk", None)
        assert exc.value.status_code == 401

    def test_fe_jwt_path_ignores_key_headers(self):
        # Even if a JWT caller smuggles X-Mcp-Key-Id, the key/cap are NOT honored —
        # only the internal-token replay path may attribute to a key.
        caller, key, cap = _resolve_confirm_caller(
            x_internal_token=None,
            x_user_id=None,
            authorization=f"Bearer {_jwt(USER)}",
            x_mcp_key_id="mk_smuggled",
            x_mcp_spend_cap_usd="999",
        )
        assert caller == USER
        assert key is None
        assert cap is None

    def test_fe_jwt_path_invalid_token_401(self):
        with pytest.raises(HTTPException) as exc:
            _resolve_confirm_caller(None, None, "Bearer not.a.jwt", None, None)
        assert exc.value.status_code == 401

    def test_no_credentials_401(self):
        with pytest.raises(HTTPException) as exc:
            _resolve_confirm_caller(None, None, None, None, None)
        assert exc.value.status_code == 401
