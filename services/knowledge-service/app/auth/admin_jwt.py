"""KM5-M1 — RS256 admin-JWT verification (System-tier authority).

Python port of `contracts/adminjwt` (Go, read-only reference). Same wire
contract — `iss`/`aud`/scope/`kid` are identical bytes — so a SINGLE platform
admin token (minted by auth-service over the KMS key) verifies the same way in
Go (glossary) and Python (knowledge). Do not diverge the constants.

Strict / fail-closed (PRR-29/30; INV-T2 "admin = RS256, never X-User-Id"):
  - **RS256 ONLY.** `algorithms=["RS256"]` rejects `alg:none` and every HS/EC/PS
    variant. The classic alg-confusion downgrade (sign HS256 with the RSA public
    key bytes as the HMAC secret) is dead on two counts: the allow-list excludes
    HS*, and we hand PyJWT a parsed RSA key object, never a PEM string.
  - **exp required + enforced** (`options={"require": ["exp"]}`).
  - **iss + aud pinned** to ISSUER / AUDIENCE — a token minted for another
    audience cannot be replayed here.
  - **kid pinned** when a key fingerprint is configured: the token header's `kid`
    MUST equal `KeyFingerprint(pub)`, so a token under a different/stale key fails
    with a clear kid error instead of a blanket signature mismatch.
  - **Scope check is the caller's** (mirror glossary `requireAdminScope`): verify
    authenticates the token; the route asserts `admin:write` ∈ claims.scopes and
    returns 403 if absent.

Key config: `ADMIN_JWT_PUBLIC_KEY_PEM` — an SPKI/PKIX "PUBLIC KEY" PEM (exactly
what AWS KMS GetPublicKey emits once PEM-armored), OR base64 of it (env-friendly
single line). PKCS#1 "RSA PUBLIC KEY" is REJECTED (KMS never emits it; accepting
both shapes silently is a footgun). Unset → admin disabled (callers 503).
"""

from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import dataclass, field

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_public_key,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ISSUER",
    "AUDIENCE",
    "SCOPE_ADMIN_WRITE",
    "AdminClaims",
    "AdminKey",
    "AdminTokenInvalid",
    "key_fingerprint",
    "load_admin_key",
    "parse_rsa_public_key_pem",
    "verify_admin_token",
]

# Pinned: every admin token is issued by auth-service ("iss") for consumption by
# admin-cli ("aud"). IDENTICAL to contracts/adminjwt — do not rename without
# bumping the signer (auth-service) and every verifier (glossary + knowledge).
ISSUER = "loreweave-auth"
AUDIENCE = "admin-cli"
SCOPE_ADMIN_WRITE = "admin:write"


class AdminTokenInvalid(Exception):
    """Signature / format / alg / iss / aud / exp / kid failure — not honored.

    A single error class (uniform 401) so a caller cannot distinguish *why* a
    token was rejected (mirror glossary's single ErrVerify sentinel)."""


@dataclass
class AdminClaims:
    """The verified admin-JWT payload. ``scopes`` drives the route-level
    `admin:write` gate (verify does NOT enforce scope — the route does)."""

    sub: str                                   # admin principal user_ref_id
    scopes: list[str] = field(default_factory=list)
    role: str = ""
    break_glass: bool = False
    jti: str = ""                              # unique per token (replay forensics)
    exp: int = 0                               # unix seconds

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


@dataclass
class AdminKey:
    """A loaded admin-signing public key + its canonical fingerprint (kid)."""

    public_key: rsa.RSAPublicKey
    kid: str


def _pem_or_base64(raw: str) -> bytes:
    """Accept either a literal PEM document or a base64-encoded one (so the key
    can ride in a single-line env var). Mirror glossary's `pemOrBase64`."""
    s = raw.strip()
    if "-----BEGIN" in s:
        return s.encode("ascii", "ignore")
    try:
        return base64.b64decode(s, validate=True)
    except (ValueError, base64.binascii.Error):
        # Not base64 — hand the bytes through so PEM parsing fails with a clear error.
        return s.encode("ascii", "ignore")


def parse_rsa_public_key_pem(pem_bytes: bytes) -> rsa.RSAPublicKey:
    """Decode an RSA public key from a PEM-wrapped SPKI/PKIX document.

    REJECTS the PKCS#1 "RSA PUBLIC KEY" block — KMS only ever emits SPKI, and
    pinning the one accepted shape means a wrong-format export fails fast at load
    time rather than verifying surprising keys."""
    text = pem_bytes.decode("ascii", "ignore")
    if "BEGIN RSA PUBLIC KEY" in text:
        raise AdminTokenInvalid(
            "expected SPKI/PKIX 'PUBLIC KEY' PEM, got PKCS#1 'RSA PUBLIC KEY'"
        )
    try:
        pub = load_pem_public_key(pem_bytes)
    except Exception as exc:  # cryptography raises ValueError/UnsupportedAlgorithm
        raise AdminTokenInvalid(f"parse PKIX: {exc}") from exc
    if not isinstance(pub, rsa.RSAPublicKey):
        raise AdminTokenInvalid(f"not an RSA public key ({type(pub).__name__})")
    return pub


def key_fingerprint(pub: rsa.RSAPublicKey) -> str:
    """Canonical kid: hex(SHA-256(PKIX/SPKI DER)). Both signer and verifier
    compute it identically, so a mismatch proves the two sides hold different
    keys. Same definition as `adminjwt.KeyFingerprint`."""
    der = pub.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def load_admin_key(raw: str) -> AdminKey | None:
    """Resolve the configured admin key. Empty/blank → ``None`` (admin disabled,
    callers 503). A non-empty but unparseable value raises ``AdminTokenInvalid``
    — the caller logs loudly and disables, never crash-loops the service."""
    if not raw or not raw.strip():
        return None
    pub = parse_rsa_public_key_pem(_pem_or_base64(raw))
    return AdminKey(public_key=pub, kid=key_fingerprint(pub))


def verify_admin_token(token: str, key: AdminKey | None) -> AdminClaims:
    """Validate an admin JWT against ``key`` and return its claims. Raises
    ``AdminTokenInvalid`` on any failure (nil key, kid mismatch, bad signature,
    alg, iss, aud, missing/expired exp). Uses real time for exp (as the Go
    verifier does); tests pin determinism by minting exp in the past/future."""
    if key is None:
        raise AdminTokenInvalid("admin verification not configured")
    if not token or not token.strip():
        raise AdminTokenInvalid("empty token")

    # kid pre-check (clear error before the signature math). Reads the UNVERIFIED
    # header — the signature is still verified by jwt.decode below; this only
    # turns a stale/foreign key into a precise "kid mismatch" instead of a blanket
    # signature failure on every token.
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AdminTokenInvalid(f"bad header: {exc}") from exc
    if header.get("kid", "") != key.kid:
        raise AdminTokenInvalid(
            f"kid mismatch (token={header.get('kid', '')!r} expected={key.kid!r})"
        )

    try:
        data = jwt.decode(
            token,
            key.public_key,
            algorithms=["RS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={"require": ["exp"]},
        )
    except jwt.PyJWTError as exc:
        raise AdminTokenInvalid(str(exc)) from exc

    scopes_raw = data.get("scopes") or []
    scopes = [str(s) for s in scopes_raw] if isinstance(scopes_raw, list) else []
    return AdminClaims(
        sub=str(data.get("sub", "")),
        scopes=scopes,
        role=str(data.get("role", "")),
        break_glass=bool(data.get("break_glass", False)),
        jti=str(data.get("jti", "")),
        exp=int(data.get("exp", 0)),
    )
