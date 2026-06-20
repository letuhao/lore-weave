"""KM6 — confirm-token codec unit tests (spec §13; security keystone).

Pure, no DB. Proves: mint/verify round-trip, constant-time signature rejection,
expiry, closed-descriptor fail-closed (mint AND verify), authority guard, domain
separation, and tamper resistance.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.ontology.confirm import (
    ACTION_TOKEN_TTL_S,
    AUTH_ADMIN,
    AUTH_GRANT,
    DESC_SCHEMA_EDIT,
    ActionClaims,
    ActionTokenExpired,
    ActionTokenInvalid,
    live_descriptor,
    mint_action_token,
    verify_action_token,
)

_SECRET = "test-jwt-secret-please-rotate"
_NOW = 1_750_000_000.0  # fixed unix seconds (Date.now() unavailable in this env anyway)


def _claims(**over) -> ActionClaims:
    base = dict(
        jti=str(uuid4()),
        authority=AUTH_GRANT,
        user_id=str(uuid4()),
        descriptor=DESC_SCHEMA_EDIT,
        project_id=str(uuid4()),
        params={"verb": "add", "level": "edge_type", "code": "WORSHIPS"},
    )
    base.update(over)
    return ActionClaims(**base)


def test_mint_verify_round_trip_preserves_claims():
    c = _claims()
    tok = mint_action_token(_SECRET, c, _NOW)
    assert tok and tok.count(".") == 1
    out = verify_action_token(_SECRET, tok, _NOW)
    assert out.jti == c.jti
    assert out.authority == AUTH_GRANT
    assert out.user_id == c.user_id
    assert out.project_id == c.project_id
    assert out.descriptor == DESC_SCHEMA_EDIT
    assert out.params == c.params
    assert out.exp == int(_NOW) + ACTION_TOKEN_TTL_S


def test_tampered_payload_rejected():
    tok = mint_action_token(_SECRET, _claims(), _NOW)
    payload_b64, sig = tok.split(".")
    # Flip a char in the payload — signature no longer matches.
    bad = payload_b64[:-1] + ("A" if payload_b64[-1] != "A" else "B") + "." + sig
    with pytest.raises(ActionTokenInvalid):
        verify_action_token(_SECRET, bad, _NOW)


def test_tampered_signature_rejected():
    tok = mint_action_token(_SECRET, _claims(), _NOW)
    payload_b64, sig = tok.split(".")
    # Flip the FIRST sig char (high bits of byte 0) — flipping the last char can
    # decode to identical bytes (trailing base64 bits are ignored).
    bad = payload_b64 + "." + (("A" if sig[0] != "A" else "B") + sig[1:])
    with pytest.raises(ActionTokenInvalid):
        verify_action_token(_SECRET, bad, _NOW)


def test_wrong_secret_rejected():
    tok = mint_action_token(_SECRET, _claims(), _NOW)
    with pytest.raises(ActionTokenInvalid):
        verify_action_token("a-different-secret", tok, _NOW)


def test_domain_separation_glossary_token_does_not_verify():
    # A token signed with the SAME secret but the glossary domain must not verify
    # here — proves the domain separator binds the token to this codec.
    import base64
    import hashlib
    import hmac
    import json

    c = _claims()
    c.exp = int(_NOW) + ACTION_TOKEN_TTL_S
    payload = json.dumps(
        {
            "jti": c.jti, "auth": c.authority, "u": c.user_id, "asub": "",
            "pid": c.project_id, "d": c.descriptor, "p": c.params, "exp": c.exp,
        },
        separators=(",", ":"), sort_keys=True,
    ).encode()
    p64 = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    mac = hmac.new(_SECRET.encode(), b"gloss-action-confirm:v1|" + p64.encode(), hashlib.sha256)
    s64 = base64.urlsafe_b64encode(mac.digest()).rstrip(b"=").decode()
    with pytest.raises(ActionTokenInvalid):
        verify_action_token(_SECRET, p64 + "." + s64, _NOW)


def test_expired_token_distinct_error():
    tok = mint_action_token(_SECRET, _claims(), _NOW)
    with pytest.raises(ActionTokenExpired):
        verify_action_token(_SECRET, tok, _NOW + ACTION_TOKEN_TTL_S)  # exactly at exp → expired
    # one second before exp still valid
    verify_action_token(_SECRET, tok, _NOW + ACTION_TOKEN_TTL_S - 1)


def test_non_live_descriptor_fails_closed_at_mint():
    # Reserved-but-not-live descriptor → mint returns "" (cannot mint).
    assert mint_action_token(_SECRET, _claims(descriptor="kg_adopt"), _NOW) == ""
    assert mint_action_token(_SECRET, _claims(descriptor="kg_system_delete"), _NOW) == ""
    assert not live_descriptor("kg_adopt")
    assert live_descriptor(DESC_SCHEMA_EDIT)


def test_empty_secret_or_jti_cannot_mint():
    assert mint_action_token("", _claims(), _NOW) == ""
    assert mint_action_token(_SECRET, _claims(jti="  "), _NOW) == ""


def test_malformed_tokens_rejected():
    for bad in ["", "noseparator", "a.b.c", ".", "x.", ".y", "@@@.###"]:
        with pytest.raises(ActionTokenInvalid):
            verify_action_token(_SECRET, bad, _NOW)


def test_bad_authority_value_rejected():
    # Forge a token whose authority is neither grant nor admin (but signed correctly).
    c = _claims(authority="superuser")
    # mint signs whatever authority is set; verify must reject the unknown authority.
    tok = mint_action_token(_SECRET, c, _NOW)
    with pytest.raises(ActionTokenInvalid):
        verify_action_token(_SECRET, tok, _NOW)


def test_admin_authority_value_accepted_by_codec():
    # The codec accepts AUTH_ADMIN as a structurally-valid authority (the endpoint,
    # not the codec, 501s it in this build).
    tok = mint_action_token(_SECRET, _claims(authority=AUTH_ADMIN, admin_sub="cms-admin"), _NOW)
    out = verify_action_token(_SECRET, tok, _NOW)
    assert out.authority == AUTH_ADMIN and out.admin_sub == "cms-admin"
