"""KM5-M1 — RS256 admin-JWT verification unit tests (security keystone).

Pure, no DB. Proves the verifier matches the `contracts/adminjwt` Go contract:
RS256-only (alg:none + HS256 alg-confusion rejected), iss/aud pinned, exp
required + enforced, kid pinned, SPKI-only key parsing, fail-closed when the key
is unset. Tokens are minted with a throwaway RSA key generated per-test.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth.admin_jwt import (
    AUDIENCE,
    ISSUER,
    SCOPE_ADMIN_WRITE,
    AdminTokenInvalid,
    key_fingerprint,
    load_admin_key,
    parse_rsa_public_key_pem,
    verify_admin_token,
)


# ── key + token helpers ───────────────────────────────────────────────────────
def _gen_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _spki_pem(priv: rsa.RSAPrivateKey) -> str:
    return priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def _pkcs1_pem(priv: rsa.RSAPrivateKey) -> str:
    return priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.PKCS1,  # "RSA PUBLIC KEY" — must be rejected
    ).decode()


def _mint(
    priv: rsa.RSAPrivateKey,
    *,
    kid: str | None = None,
    iss: str = ISSUER,
    aud: str = AUDIENCE,
    scopes: list[str] | None = None,
    ttl_s: int = 3600,
    sub: str = "admin-principal",
    include_exp: bool = True,
    alg: str = "RS256",
    key=None,
) -> str:
    now = int(time.time())
    claims: dict = {
        "sub": sub,
        "iss": iss,
        "aud": aud,
        "iat": now,
        "jti": "tok-1",
        "role": "admin",
        "scopes": scopes if scopes is not None else [SCOPE_ADMIN_WRITE],
    }
    if include_exp:
        claims["exp"] = now + ttl_s
    headers = {"kid": kid} if kid is not None else None
    signing_key = key if key is not None else priv
    return jwt.encode(claims, signing_key, algorithm=alg, headers=headers)


@pytest.fixture()
def priv() -> rsa.RSAPrivateKey:
    return _gen_key()


@pytest.fixture()
def admin_key(priv):
    return load_admin_key(_spki_pem(priv))


# ── happy path ────────────────────────────────────────────────────────────────
def test_valid_token_verifies_and_carries_scope(priv, admin_key):
    tok = _mint(priv, kid=admin_key.kid)
    claims = verify_admin_token(tok, admin_key)
    assert claims.sub == "admin-principal"
    assert claims.has_scope(SCOPE_ADMIN_WRITE)
    assert claims.role == "admin"
    assert claims.jti == "tok-1"


def test_scope_check_is_caller_side(priv, admin_key):
    # A token with NO admin:write still verifies (authentication) — the route,
    # not verify, enforces scope (mirror glossary requireAdminScope).
    tok = _mint(priv, kid=admin_key.kid, scopes=["admin:read"])
    claims = verify_admin_token(tok, admin_key)
    assert claims.has_scope(SCOPE_ADMIN_WRITE) is False
    assert claims.has_scope("admin:read") is True


# ── signature / algorithm ─────────────────────────────────────────────────────
def test_wrong_key_rejected(priv, admin_key):
    other = _gen_key()
    tok = _mint(other, kid=admin_key.kid)  # signed by a different key, claims our kid
    with pytest.raises(AdminTokenInvalid):
        verify_admin_token(tok, admin_key)


def test_alg_none_rejected(priv, admin_key):
    # An unsigned alg:none token must never be honored.
    tok = jwt.encode(
        {"sub": "x", "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 60},
        key="",
        algorithm="none",
        headers={"kid": admin_key.kid},
    )
    with pytest.raises(AdminTokenInvalid):
        verify_admin_token(tok, admin_key)


def test_hs256_alg_confusion_rejected(priv, admin_key):
    # Classic downgrade: attacker signs HS256 using the PUBLIC KEY PEM bytes as
    # the HMAC secret. PyJWT refuses to *encode* this footgun, so we hand-craft
    # the token bytes the way an attacker would — then prove the RS256-only
    # allow-list rejects it on *verify*.
    import base64
    import hashlib
    import hmac
    import json

    def _b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    pub_pem = _spki_pem(priv).encode()
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": admin_key.kid}).encode())
    payload = _b64(json.dumps({
        "sub": "attacker", "iss": ISSUER, "aud": AUDIENCE,
        "exp": int(time.time()) + 60, "scopes": [SCOPE_ADMIN_WRITE],
    }).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = _b64(hmac.new(pub_pem, signing_input, hashlib.sha256).digest())
    forged = f"{header}.{payload}.{sig}"
    with pytest.raises(AdminTokenInvalid):
        verify_admin_token(forged, admin_key)


# ── claim pins ────────────────────────────────────────────────────────────────
def test_expired_rejected(priv, admin_key):
    tok = _mint(priv, kid=admin_key.kid, ttl_s=-10)
    with pytest.raises(AdminTokenInvalid):
        verify_admin_token(tok, admin_key)


def test_missing_exp_rejected(priv, admin_key):
    tok = _mint(priv, kid=admin_key.kid, include_exp=False)
    with pytest.raises(AdminTokenInvalid):
        verify_admin_token(tok, admin_key)


def test_bad_issuer_rejected(priv, admin_key):
    tok = _mint(priv, kid=admin_key.kid, iss="evil-issuer")
    with pytest.raises(AdminTokenInvalid):
        verify_admin_token(tok, admin_key)


def test_bad_audience_rejected(priv, admin_key):
    tok = _mint(priv, kid=admin_key.kid, aud="some-other-service")
    with pytest.raises(AdminTokenInvalid):
        verify_admin_token(tok, admin_key)


# ── kid pinning ───────────────────────────────────────────────────────────────
def test_kid_mismatch_rejected(priv, admin_key):
    tok = _mint(priv, kid="not-our-kid")
    with pytest.raises(AdminTokenInvalid):
        verify_admin_token(tok, admin_key)


def test_missing_kid_rejected(priv, admin_key):
    tok = _mint(priv, kid=None)  # no kid header at all
    with pytest.raises(AdminTokenInvalid):
        verify_admin_token(tok, admin_key)


# ── fail-closed config ────────────────────────────────────────────────────────
def test_none_key_rejects(priv):
    tok = _mint(priv, kid="whatever")
    with pytest.raises(AdminTokenInvalid):
        verify_admin_token(tok, None)


def test_empty_token_rejected(admin_key):
    with pytest.raises(AdminTokenInvalid):
        verify_admin_token("   ", admin_key)


def test_unset_key_loads_none():
    assert load_admin_key("") is None
    assert load_admin_key("   ") is None


# ── key parsing ───────────────────────────────────────────────────────────────
def test_spki_pem_parses_and_fingerprint_is_stable(priv):
    pub = parse_rsa_public_key_pem(_spki_pem(priv).encode())
    fp1 = key_fingerprint(pub)
    fp2 = key_fingerprint(priv.public_key())
    assert fp1 == fp2 and len(fp1) == 64  # hex sha256


def test_pkcs1_pem_rejected(priv):
    with pytest.raises(AdminTokenInvalid):
        parse_rsa_public_key_pem(_pkcs1_pem(priv).encode())


def test_load_admin_key_accepts_base64_of_pem(priv):
    import base64

    pem = _spki_pem(priv)
    b64 = base64.b64encode(pem.encode()).decode()
    key = load_admin_key(b64)
    assert key is not None and key.kid == key_fingerprint(priv.public_key())


def test_load_admin_key_raises_on_garbage():
    with pytest.raises(AdminTokenInvalid):
        load_admin_key("-----BEGIN PUBLIC KEY-----\nnot-valid-der\n-----END PUBLIC KEY-----")


def test_non_rsa_spki_key_rejected():
    # A valid SPKI "PUBLIC KEY" PEM that is NOT RSA (EC here) must hit the
    # isinstance guard — we only ever verify RS256 against an RSA key.
    from cryptography.hazmat.primitives.asymmetric import ec

    ec_priv = ec.generate_private_key(ec.SECP256R1())
    ec_pem = ec_priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with pytest.raises(AdminTokenInvalid):
        parse_rsa_public_key_pem(ec_pem)


def test_kid_binds_loaded_key_to_signer(priv, admin_key):
    # End-to-end: a token whose kid == load_admin_key(pem).kid and is signed by
    # the matching private key verifies; this is the "same key both sides" proof.
    tok = _mint(priv, kid=admin_key.kid)
    assert verify_admin_token(tok, admin_key).sub == "admin-principal"
