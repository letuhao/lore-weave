"""loreweave_crypto — envelope encryption for per-user private content (WS-1.0).

Spec: docs/specs/2026-07-11-work-assistant-mode/DECISIONS-SEALED.md **PO-2**.

═══════════════════════════════════════════════════════════════════════════════
WHAT THIS BUYS — AND WHAT IT DOES NOT. Read this before trusting it.
═══════════════════════════════════════════════════════════════════════════════

  Stolen DB dump · stolen backup · a curious DBA running `SELECT *` · a table or
  log leak                                                     -> ✅ PROTECTED
  An operator who CONTROLS THE RUNNING SERVER (can read the DEK
  from process memory, or add one log line)                    -> ❌ NOT protected

A server-side AI pipeline requires the server to see plaintext: extraction, embedding,
recall and compaction all decrypt in-process. That is physics, not laziness. The only
architecture that truly hides a diary from the operator is client-side encryption +
client-side AI — a different product.

So: this raises the bar from *"read a table"* to *"actively subvert the running
application"*. We say exactly that to the user. **We do not claim the operator cannot
read their diary.** Do not let that claim drift into the copy.

═══════════════════════════════════════════════════════════════════════════════
THE SCHEME
═══════════════════════════════════════════════════════════════════════════════

Envelope, mirroring the existing `usage_logs` precedent (usage-billing-service):

    KEK  (per deployment, from env/KMS; NEVER stored in the DB)
     └─ wraps ─> DEK (per USER, random 32B; stored WRAPPED in auth-service)
                  └─ encrypts ─> diary bodies · assistant chat_messages · :Fact.fact_text
                  └─ derives  ─> the blind-index key (HKDF, "blind-index" info)
                  └─ derives  ─> the embedding key   (HKDF, "embedding" info)

Per-user DEKs mean: erasing one user's DEK renders their ciphertext unrecoverable, which
is a genuine *crypto-shred* primitive for D18 erasure (backups included — a restored
backup without the DEK is noise).

Ciphertext format (same as the usage_logs precedent, so operators see one shape):
    base64( nonce[12] || aes_gcm_ciphertext_with_tag )

KEY ROTATION: `Keyring` holds an ACTIVE kek (all new wraps) plus RETIRED keks tried on
the read path only, so rotating the KEK does not orphan existing rows. This is not
optional decoration — without it, rotating the KEK bricks every diary.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

__all__ = [
    "CryptoError",
    "Keyring",
    "DEK",
    "new_dek",
    "wrap_dek",
    "unwrap_dek",
    "encrypt",
    "decrypt",
    "blind_index_tokens",
    "blind_index_query_tokens",
    "encrypt_vector",
    "decrypt_vector",
    "cosine",
]

_NONCE = 12
_KEY_LEN = 32


class CryptoError(Exception):
    """Any failure to wrap/unwrap/encrypt/decrypt.

    Deliberately NOT a subclass of ValueError: callers must not accidentally swallow a
    decryption failure in a broad `except ValueError`. A failed decrypt means either
    tampering or the wrong key — never something to paper over with a default.
    """


# ── keys ──────────────────────────────────────────────────────────────────────


def _coerce_key(raw: str | bytes) -> bytes:
    """Derive a 32-byte AES key from a configured secret.

    SHA-256 of the secret — never pad/truncate. A short env value silently truncated to a
    weak key is the classic footgun; hashing gives full-length entropy from any input and
    makes the key length independent of how the operator formatted the env var.
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not raw:
        raise CryptoError("empty key material")
    return hashlib.sha256(raw).digest()


@dataclass(frozen=True)
class Keyring:
    """The deployment's KEK set.

    `active` wraps every NEW dek. `retired` are previous KEKs tried on the READ path only,
    so a KEK rotation does not orphan existing users' DEKs (and therefore their entire
    diary). Rotating without a retired keyring is a data-loss event.
    """

    active: bytes
    active_ref: str
    retired: tuple[bytes, ...] = ()

    @staticmethod
    def from_env(
        active_var: str = "DIARY_ENCRYPTION_KEY",
        retired_var: str = "DIARY_ENCRYPTION_KEYS_RETIRED",
    ) -> "Keyring":
        """Build from env. Retired keys are comma-separated.

        Raises if the active key is missing — this FAILS CLOSED by construction: a service
        that stores private content must not silently start with encryption disabled.
        """
        raw = os.environ.get(active_var, "")
        if not raw:
            raise CryptoError(
                f"{active_var} is not set. Private user content cannot be stored without "
                f"it — refusing to start rather than silently writing plaintext."
            )
        active = _coerce_key(raw)
        # STRIP each retired entry before deriving it (review-impl P2). The filter used
        # k.strip() but derived from the UN-stripped k, so `DIARY_ENCRYPTION_KEYS_RETIRED=
        # "old1, old2"` derived SHA256(" old2") — a key that unwraps nothing. At rotation
        # time every user still on old2 would then hit a hard "DEK unavailable" (fail-closed,
        # so no leak — but a total outage), while the error told the operator to add a key
        # they HAD added. One stray space after a comma.
        retired = tuple(
            _coerce_key(stripped)
            for raw_k in (os.environ.get(retired_var) or "").split(",")
            if (stripped := raw_k.strip())
        )
        return Keyring(active=active, active_ref=key_ref(active), retired=retired)

    def all_for_read(self) -> tuple[bytes, ...]:
        return (self.active, *self.retired)


def key_ref(key: bytes) -> str:
    """A short, non-secret fingerprint of a KEK, stored beside the wrapped DEK.

    It records WHICH kek wrapped a row, so an operator can tell at a glance whether a
    rotation is complete. It is a fingerprint, not a secret: 8 hex chars of a SHA-256 over
    a domain-separated input, so it cannot be used to recover the key.
    """
    return hashlib.sha256(b"loreweave-kek-ref\x00" + key).hexdigest()[:16]


DEK = bytes  # a 32-byte per-user data key (plaintext, in memory only)


def new_dek() -> DEK:
    return os.urandom(_KEY_LEN)


def _wrap_aad(user_id: str | None) -> bytes | None:
    """The AAD that binds a wrapped DEK to its owner.

    AES-GCM authenticates the AAD without encrypting it, so wrapping user A's DEK under
    AAD="dek:A" and unwrapping it under AAD="dek:B" FAILS. That closes a DB-write
    adversary's row-swap: moving A's wrapped_dek onto B's user_deks row no longer yields a
    usable key for B. Domain-separated so a wrap AAD can never collide with a content AAD.
    """
    return None if user_id is None else b"loreweave-dek-wrap\x00" + user_id.encode("utf-8")


def wrap_dek(keyring: Keyring, dek: DEK, user_id: str | None = None) -> tuple[str, str]:
    """Wrap a user's DEK under the ACTIVE kek, BOUND to user_id. Returns (wrapped_b64, key_ref).

    user_id is optional only for back-compat with callers that predate the binding; every
    real caller (auth-service, DEKClient) passes it, and MUST pass the same value to unwrap.
    """
    if len(dek) != _KEY_LEN:
        raise CryptoError(f"dek must be {_KEY_LEN} bytes, got {len(dek)}")
    return _seal(keyring.active, dek, _wrap_aad(user_id)), keyring.active_ref


def unwrap_dek(keyring: Keyring, wrapped: str, user_id: str | None = None) -> DEK:
    """Unwrap a user's DEK, trying the active kek then each retired one.

    Trying every key on the read path is what makes rotation safe. AES-GCM is
    authenticated, so a wrong key — or a wrapped DEK that belongs to a DIFFERENT user
    (wrong AAD) — fails cleanly; it cannot silently produce garbage.
    """
    aad = _wrap_aad(user_id)
    last: Exception | None = None
    for kek in keyring.all_for_read():
        try:
            dek = _open(kek, wrapped, aad)
            if len(dek) != _KEY_LEN:
                raise CryptoError("unwrapped dek has the wrong length")
            return dek
        except CryptoError as exc:  # wrong key or wrong user — try the next kek
            last = exc
    raise CryptoError(
        "could not unwrap the user's DEK with any configured KEK. If a KEK was rotated, "
        "the previous value MUST be in the retired keyring; if this row was moved between "
        "users, the AAD binding will also refuse it."
    ) from last


# ── content ───────────────────────────────────────────────────────────────────


def _seal(key: bytes, plain: bytes, aad: bytes | None = None) -> str:
    nonce = os.urandom(_NONCE)
    ct = AESGCM(key).encrypt(nonce, plain, aad)
    return base64.b64encode(nonce + ct).decode("ascii")


def _open(key: bytes, blob: str, aad: bytes | None = None) -> bytes:
    try:
        raw = base64.b64decode(blob, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise CryptoError("ciphertext is not valid base64") from exc
    if len(raw) <= _NONCE:
        raise CryptoError("ciphertext too short")
    try:
        return AESGCM(key).decrypt(raw[:_NONCE], raw[_NONCE:], aad)
    except Exception as exc:  # noqa: BLE001 — InvalidTag or anything else
        raise CryptoError("decryption failed (wrong key, wrong AAD, or tampered ciphertext)") from exc


def encrypt(dek: DEK, plaintext: str, aad: str | None = None) -> str:
    """Encrypt user content under their DEK. Returns base64(nonce||ct).

    Optional `aad` binds the ciphertext to a context (e.g. a "chapter:<id>" row identity),
    so a DB-write adversary cannot move a ciphertext between rows and have it still decrypt.
    Forward-compatible: the diary/chat/fact writers (WS-1.4+) will pass their row identity;
    a caller that passes None gets confidentiality + integrity but no row binding.
    """
    return _seal(dek, plaintext.encode("utf-8"),
                 None if aad is None else b"loreweave-content\x00" + aad.encode("utf-8"))


def decrypt(dek: DEK, ciphertext: str, aad: str | None = None) -> str:
    """Decrypt user content. Raises CryptoError on a wrong key, a wrong AAD, OR any
    tampering — AES-GCM is authenticated, so a modified or moved row is detected, not
    silently returned. `aad` must match what encrypt() was given."""
    return _open(dek, ciphertext,
                 None if aad is None else b"loreweave-content\x00" + aad.encode("utf-8")).decode("utf-8")


# ── blind index (search over ciphertext) ──────────────────────────────────────
#
# Encrypting chat_messages.content kills the GIN trigram index — and trigram search IS
# the entire week-1 recall story (the KG is empty until entries accumulate). So we store
# HMAC-keyed tokens instead: the operator sees keyed hashes, not text.
#
# ACCEPTED LEAK (state it, do not hide it): token FREQUENCY. An operator can see that
# some token appears often, and mount a frequency/dictionary attack against common words.
# That is the known, bounded weakness of blind indexing, and it is the price of having
# search at all. It is NOT a substitute for the honest disclosure.

_WORD = re.compile(r"\w+", re.UNICODE)


def _index_key(dek: DEK) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"loreweave-blind-index",
    ).derive(dek)


# n-gram widths. BOTH 2 and 3 — not 3 alone.
#
# A word-only index returns NOTHING for a Chinese/Japanese diary (no spaces ⇒ the whole
# line is one "word"), so n-grams are what make search exist for those users at all. And
# 3-grams alone are not enough either: MOST CHINESE WORDS ARE TWO CHARACTERS (发布,
# 会议, 计划), so a 2-char query could never match a 3-gram index. Dropping bigrams
# silently breaks search for exactly the users who depend on n-grams most — the same
# class of bug as the CJK dict-anchor fix.
_NGRAMS = (2, 3)


def _tokens(text: str) -> set[str]:
    """Word tokens + character n-grams (n ∈ _NGRAMS), n-grammed PER WORD.

    Both, deliberately: whole words give precise matches, n-grams give substring and CJK
    coverage.

    ⚠️ The n-grams are computed per matched word, NOT over the whitespace-squished whole
    string (review-impl P1). Squishing manufactures n-grams that SPAN a word boundary —
    e.g. "launch plan" → "launchplan" yields "hp", "hpl". A stored document containing
    "launch" and "plan" NON-adjacently never produced those spanning n-grams, so under the
    `stored ⊇ query` containment match a two-word query would silently return ZERO results.
    Search that quietly finds nothing is worse than no search — the user concludes the
    assistant has forgotten, when it simply mis-tokenised the query.

    CJK still works because CJK "words" are runs with no internal spaces: `_WORD` matches the
    whole run as one token, and n-gramming that single token gives the substring coverage.
    """
    low = text.lower()
    words = _WORD.findall(low)
    out: set[str] = set(words)
    for w in words:
        for n in _NGRAMS:
            out.update(w[i : i + n] for i in range(max(0, len(w) - n + 1)))
    return {t for t in out if t}


def blind_index_tokens(dek: DEK, text: str) -> list[str]:
    """The keyed tokens to STORE for a piece of content (write path)."""
    k = _index_key(dek)
    return sorted(
        base64.b64encode(hmac.new(k, t.encode("utf-8"), hashlib.sha256).digest()[:12])
        .decode("ascii")
        for t in _tokens(text)
    )


def blind_index_query_tokens(dek: DEK, query: str) -> list[str]:
    """The keyed tokens to MATCH for a search query (read path).

    Same derivation as the write path — a search is `stored_tokens @> query_tokens`.
    """
    return blind_index_tokens(dek, query)


# ── embeddings ────────────────────────────────────────────────────────────────
#
# ⚠️ Plaintext embeddings ≈ plaintext diary. Vec2Text recovers ~92% of short text EXACTLY
# (BLEU 97.3) and has demonstrably recovered patient names from clinical notes; training
# an inverter needs NO access to the embedding model's parameters. Encrypting fact_text
# while leaving its embedding readable is a deadbolt on the door with the window open.
#
# So the vectors are encrypted too, and cosine is brute-forced IN MEMORY per user at query
# time. This works BECAUSE A DIARY IS TINY by vector-search standards: a few years of
# entries is 10k-100k vectors (~200MB at 1024-dim), and a linear scan is milliseconds.
# No ANN index is needed at per-user scale — which is exactly why we can afford to close
# this hole at all.


def _vec_key(dek: DEK) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"loreweave-embedding",
    ).derive(dek)


def encrypt_vector(dek: DEK, vec: list[float]) -> str:
    packed = struct.pack(f"<{len(vec)}f", *vec)
    return _seal(_vec_key(dek), packed)


def decrypt_vector(dek: DEK, blob: str) -> list[float]:
    raw = _open(_vec_key(dek), blob)
    if len(raw) % 4:
        raise CryptoError("encrypted vector has a truncated float payload")
    return list(struct.unpack(f"<{len(raw) // 4}f", raw))


def cosine(a: list[float], b: list[float]) -> float:
    """Plain cosine similarity — the brute-force scan's inner loop.

    Kept here (rather than pulling in numpy) so the crypto SDK has no heavy dependency; a
    caller with numpy should vectorize this over the decrypted matrix instead.
    """
    if len(a) != len(b):
        raise CryptoError(f"dimension mismatch: {len(a)} vs {len(b)}")
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))
