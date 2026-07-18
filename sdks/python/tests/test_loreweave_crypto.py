"""WS-1.0 — loreweave_crypto: envelope encryption for per-user private content.

Spec: DECISIONS-SEALED PO-2.

The tests that matter are the ones about LOSING data or LEAKING it:
  - a KEK rotation must NOT orphan an existing user's DEK (that would brick every diary)
  - a wrong key or a tampered row must FAIL, never silently return garbage
  - two users must not be able to read each other's content
  - a missing KEK must REFUSE TO START, never fall back to plaintext
  - the blind index must be deterministic (search works) but not reversible (that's the point)
  - encrypted vectors must round-trip so semantic recall survives being encrypted
"""

from __future__ import annotations

import base64
from uuid import uuid4

import pytest

from loreweave_crypto import (
    CryptoError,
    Keyring,
    blind_index_query_tokens,
    blind_index_tokens,
    cosine,
    decrypt,
    decrypt_vector,
    encrypt,
    encrypt_vector,
    key_ref,
    new_dek,
    unwrap_dek,
    wrap_dek,
)


def _ring(active="kek-active", retired=()) -> Keyring:
    from loreweave_crypto import _coerce_key

    a = _coerce_key(active)
    return Keyring(
        active=a, active_ref=key_ref(a), retired=tuple(_coerce_key(r) for r in retired),
    )


# ── the envelope ──────────────────────────────────────────────────────────────


def test_dek_round_trips_through_the_envelope():
    ring = _ring()
    dek = new_dek()
    wrapped, ref = wrap_dek(ring, dek)

    assert wrapped != base64.b64encode(dek).decode(), "the DEK must not be stored in the clear"
    assert ref == ring.active_ref
    assert unwrap_dek(ring, wrapped) == dek


def test_content_round_trips_under_the_user_dek():
    dek = new_dek()
    secret = "Minh said the launch slips to Q3. I disagreed and said so badly."
    ct = encrypt(dek, secret)

    assert secret not in ct
    assert decrypt(dek, ct) == secret


def test_one_user_cannot_read_another_users_content():
    """Per-user DEKs are the whole tenancy story for private content."""
    alice, bob = new_dek(), new_dek()
    ct = encrypt(alice, "my private diary")

    with pytest.raises(CryptoError):
        decrypt(bob, ct)


def test_tampered_ciphertext_is_DETECTED_not_silently_returned():
    """AES-GCM is authenticated. A modified row must raise, never decode to garbage that
    then flows into an LLM prompt or a fact."""
    dek = new_dek()
    ct = encrypt(dek, "the original truth")

    raw = bytearray(base64.b64decode(ct))
    raw[-1] ^= 0x01  # flip one bit of the tag
    tampered = base64.b64encode(bytes(raw)).decode()

    with pytest.raises(CryptoError):
        decrypt(dek, tampered)


def test_encryption_is_nondeterministic():
    """The same plaintext twice must not produce the same ciphertext — otherwise an
    operator can see which entries repeat, and equality-match across users."""
    dek = new_dek()
    assert encrypt(dek, "same text") != encrypt(dek, "same text")


# ── rotation: the data-loss test ──────────────────────────────────────────────


def test_kek_rotation_does_not_orphan_an_existing_user():
    """THE ONE THAT PREVENTS A CATASTROPHE.

    A user's DEK was wrapped under KEK-1. The operator rotates to KEK-2. If the read path
    only tried the ACTIVE key, that user's DEK would be unrecoverable — and with it every
    diary entry, chat message and fact they own. The retired keyring is what makes a
    rotation survivable.
    """
    old = _ring(active="kek-1")
    dek = new_dek()
    wrapped, _ = wrap_dek(old, dek)

    # Rotate: kek-2 is active, kek-1 is retired.
    rotated = _ring(active="kek-2", retired=("kek-1",))
    assert unwrap_dek(rotated, wrapped) == dek, "rotation orphaned the user's DEK"

    # New wraps use the new key...
    rewrapped, ref = wrap_dek(rotated, dek)
    assert ref == rotated.active_ref
    assert unwrap_dek(rotated, rewrapped) == dek

    # ...and a ring that FORGOT the old key genuinely cannot read the old row (this is
    # what the retired keyring exists to prevent, and it is also the crypto-shred primitive
    # for erasure).
    forgetful = _ring(active="kek-2")
    with pytest.raises(CryptoError):
        unwrap_dek(forgetful, wrapped)


def test_wrapped_dek_is_bound_to_its_user_id():
    """review-impl — AAD binding. A wrapped DEK carries its owner's id as AAD, so moving
    user A's wrapped_dek onto user B's row (a DB-write adversary) no longer yields a usable
    key: unwrapping under B's id fails."""
    ring = _ring()
    dek = new_dek()
    alice, bob = str(uuid4()), str(uuid4())

    wrapped, _ = wrap_dek(ring, dek, alice)
    assert unwrap_dek(ring, wrapped, alice) == dek           # right user: fine
    with pytest.raises(CryptoError):
        unwrap_dek(ring, wrapped, bob)                        # swapped row: refused


def test_retired_keyring_tolerates_spaces_after_commas(monkeypatch):
    """review-impl P2 — the strip bug. The env list is human-edited; a space after a comma
    must not silently derive a wrong KEK and brick every user still on it at rotation time."""
    monkeypatch.setenv("DIARY_ENCRYPTION_KEY", "kek-2")
    monkeypatch.setenv("DIARY_ENCRYPTION_KEYS_RETIRED", " kek-1 , kek-0 ")
    ring = Keyring.from_env()

    old0 = _ring(active="kek-0")
    old1 = _ring(active="kek-1")
    d0 = new_dek()
    d1 = new_dek()
    w0, _ = wrap_dek(old0, d0)
    w1, _ = wrap_dek(old1, d1)

    # Both DEKs, wrapped under padded-in-the-env retired keys, must still unwrap.
    assert unwrap_dek(ring, w0) == d0, "a space after a comma in the retired list bricked kek-0"
    assert unwrap_dek(ring, w1) == d1, "a space after a comma in the retired list bricked kek-1"


def test_missing_kek_refuses_to_start_rather_than_writing_plaintext(monkeypatch):
    """FAIL CLOSED. A service that stores private content must not silently boot with
    encryption disabled — that is how a 'temporarily unencrypted' deploy becomes permanent."""
    monkeypatch.delenv("DIARY_ENCRYPTION_KEY", raising=False)
    with pytest.raises(CryptoError, match="refusing to start"):
        Keyring.from_env()


def test_key_ref_is_a_fingerprint_not_the_key():
    from loreweave_crypto import _coerce_key

    k = _coerce_key("kek-1")
    ref = key_ref(k)
    assert len(ref) == 16
    assert base64.b64encode(k).decode() not in ref
    assert k.hex() not in ref
    # Stable + distinguishing (that is its whole job: "which KEK wrapped this row?").
    assert key_ref(k) == ref
    assert key_ref(_coerce_key("kek-2")) != ref


# ── the cross-language contract ───────────────────────────────────────────────


def test_python_can_unwrap_a_dek_that_GO_wrapped():
    """THE CROSS-SERVICE CONTRACT, pinned with a golden vector.

    auth-service (Go) WRAPS every user's DEK. Every consumer that decrypts private content
    (chat-service, knowledge-service, worker-ai — all Python) UNWRAPS it. If the two
    implementations ever disagree about the envelope format — nonce length, base64 flavour,
    the AAD, the key derivation — the failure is total and silent-until-production: every
    diary becomes unreadable.

    Unit tests on each side in isolation cannot catch that: they would each be
    self-consistently wrong. So this is a GOLDEN VECTOR, generated by the real Go code
    (services/auth-service/internal/api/user_dek.go: deriveKEK + sealWithKEK + kekRef) and
    decrypted here by the real Python code. If either side changes its format, this reds.

    Regenerate (only if the format INTENTIONALLY changes, and update both sides):
        kek = deriveKEK("golden-test-kek"); dek = bytes(range(32)); seal(kek, dek)
    """
    from loreweave_crypto import _coerce_key

    # Generated by the real Go writer (auth-service deriveKEK+wrapAAD+sealWithKEK) with a
    # FIXED user_id. The wrap is AAD-bound to that user, so Python must pass the same id.
    GO_WRAPPED = "GBRK70VnmsY+io4OgOVwxVFb++Xy5rT+0hwG8cPonk1LGaaWn0C2m1EldAW5czLY/wPFBSqoNvqY7/Eh"
    GO_KEY_REF = "a89a34849ab8ed7f"
    GO_USER_ID = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"

    kek = _coerce_key("golden-test-kek")
    ring = Keyring(active=kek, active_ref=key_ref(kek))

    # 1. Python's key_ref must equal Go's, byte for byte.
    assert key_ref(kek) == GO_KEY_REF, (
        "Python and Go disagree about key_ref. The rotation checklist would be wrong."
    )

    # 2. Python must recover EXACTLY the DEK Go wrapped — WITH the AAD binding.
    dek = unwrap_dek(ring, GO_WRAPPED, GO_USER_ID)
    assert dek == bytes(range(32)), (
        "Python could not recover the DEK that Go wrapped. The envelope formats have "
        "DRIFTED — every user's diary would be unreadable in production."
    )

    # 3. The AAD binding is real: the SAME blob must NOT unwrap for a different user.
    with pytest.raises(CryptoError):
        unwrap_dek(ring, GO_WRAPPED, str(uuid4()))

    # 4. And that DEK really works end-to-end.
    assert decrypt(dek, encrypt(dek, "round trip")) == "round trip"


# ── blind index ───────────────────────────────────────────────────────────────


def test_blind_index_is_deterministic_so_search_actually_works():
    dek = new_dek()
    stored = set(blind_index_tokens(dek, "Minh pushed the launch to Q3"))
    query = set(blind_index_query_tokens(dek, "launch"))

    assert query, "a query must produce tokens"
    assert query <= stored, "the query's tokens must be a subset of the stored tokens"


def test_blind_index_does_not_leak_the_plaintext():
    """The stored tokens must be opaque keyed digests, not the words.

    NB: asserting `"q3" not in "".join(tokens)` would be a BAD test — a 2-char string
    appears inside random base64 by chance, so it fails for reasons that have nothing to
    do with a leak. The real property is: every token is a fixed-width keyed digest, and
    no plaintext term survives as a token.
    """
    dek = new_dek()
    toks = blind_index_tokens(dek, "Minh pushed the launch to Q3")

    for word in ("minh", "launch", "q3", "pushed", "Minh", "Q3"):
        assert word not in toks, f"the blind index stored {word!r} in the clear"

    # Every token is base64 of a 12-byte HMAC digest — a uniform, opaque shape that
    # reveals neither the term nor its length.
    for t in toks:
        assert len(base64.b64decode(t)) == 12
    assert len({len(t) for t in toks}) == 1, "token width must not vary with the term"


def test_blind_index_is_per_user_so_tokens_do_not_match_across_users():
    """Without a per-user key, two users writing the same word would produce the same
    token — letting an operator correlate content across accounts."""
    alice, bob = new_dek(), new_dek()
    assert set(blind_index_tokens(alice, "launch")) != set(blind_index_tokens(bob, "launch"))


def test_blind_index_matches_a_MULTI_WORD_query():
    """review-impl P1 — the cross-word-boundary bug.

    n-grams used to be computed over the whitespace-squished whole string, so a two-word
    query manufactured n-grams that span the gap ("launch plan" -> "launchplan" -> "hp",
    "hpl"). A document whose words are NOT adjacent in that order never produced those, so
    under the `stored ⊇ query` match a multi-word query silently returned ZERO results.
    Search that quietly finds nothing is worse than no search.
    """
    dek = new_dek()
    stored = set(blind_index_tokens(dek, "the launch was pushed and the plan slipped"))
    # "launch plan" — the two words are NOT adjacent in the document.
    query = set(blind_index_query_tokens(dek, "launch plan"))

    assert query, "a query must produce tokens"
    assert query <= stored, (
        "a multi-word query whose terms are non-adjacent in the document returned nothing — "
        "the n-grams must be computed PER WORD, not over the squished whole string"
    )


def test_blind_index_covers_cjk_which_has_no_word_boundaries():
    """A word-only index returns NOTHING for a Chinese/Japanese diary. The n-gram half is
    what makes the feature exist at all for those users (cf. the CJK dict-anchor bug)."""
    dek = new_dek()
    stored = set(blind_index_tokens(dek, "明天和小明讨论发布计划"))
    query = set(blind_index_query_tokens(dek, "发布"))

    assert query <= stored, "CJK substring search must match"


# ── embeddings ────────────────────────────────────────────────────────────────


def test_encrypted_vectors_round_trip_so_semantic_recall_survives():
    """Plaintext embeddings ≈ plaintext diary (Vec2Text recovers ~92% of short text
    exactly). Encrypting them closes that hole — but only if recall still works."""
    dek = new_dek()
    vec = [0.11, -0.42, 0.87, 0.0, 0.5]
    blob = encrypt_vector(dek, vec)

    assert "0.11" not in blob
    out = decrypt_vector(dek, blob)
    assert len(out) == len(vec)
    for a, b in zip(out, vec):
        assert abs(a - b) < 1e-6


def test_cosine_survives_the_encrypt_decrypt_round_trip():
    """The scan is: decrypt the user's vectors in memory, then brute-force cosine. A diary
    is 10k-100k vectors, so a linear scan is milliseconds and no ANN index is needed —
    which is exactly why we can afford to encrypt them."""
    dek = new_dek()
    q = [1.0, 0.0, 0.0]
    near = [0.9, 0.1, 0.0]
    far = [0.0, 0.0, 1.0]

    d_near = decrypt_vector(dek, encrypt_vector(dek, near))
    d_far = decrypt_vector(dek, encrypt_vector(dek, far))

    assert cosine(q, d_near) > cosine(q, d_far)
    assert cosine(q, d_near) == pytest.approx(cosine(q, near), abs=1e-6)


def test_another_users_key_cannot_decrypt_a_vector():
    alice, bob = new_dek(), new_dek()
    blob = encrypt_vector(alice, [0.1, 0.2])
    with pytest.raises(CryptoError):
        decrypt_vector(bob, blob)
