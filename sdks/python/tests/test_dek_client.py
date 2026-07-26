"""WS-1.0 — DEKClient: fetch, unwrap, cache.

The rule this file exists to enforce: **there is no plaintext fallback.** Every failure
path must raise, because a row written unencrypted is indistinguishable from an encrypted
one to every future reader — so a "temporary" degradation is permanent and invisible.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from loreweave_crypto import Keyring, _coerce_key, encrypt, decrypt, key_ref, new_dek, wrap_dek
from loreweave_crypto.dek_client import DEKClient, DEKUnavailable


def _ring(active="kek-1", retired=()) -> Keyring:
    a = _coerce_key(active)
    return Keyring(active=a, active_ref=key_ref(a), retired=tuple(_coerce_key(r) for r in retired))


def _client(handler, ring: Keyring | None = None) -> DEKClient:
    ring = ring or _ring()
    c = DEKClient("http://auth", "itok", ring)
    # Keep the real client's headers — the internal token is part of the contract under
    # test, so a transport swap that drops it would make the token assertion vacuous.
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers=dict(c._http.headers),
    )
    return c


def _uid_from(request: httpx.Request) -> str:
    """The user_id auth-service is being asked about — the AAD the wrap must bind to.
    Real auth-service reads it from the path; the mock does the same, so the test wraps the
    DEK the same way production does."""
    return str(request.url).rstrip("/").rsplit("/", 2)[1]  # .../users/<uid>/dek


def _serve_dek(ring: Keyring, dek, *, count=None):
    """A handler that wraps `dek` bound to the REQUESTED user_id (as auth-service does)."""
    def handler(request: httpx.Request) -> httpx.Response:
        if count is not None:
            count["n"] += 1
        wrapped, ref = wrap_dek(ring, dek, _uid_from(request))
        return httpx.Response(200, json={"wrapped_dek": wrapped, "key_ref": ref})
    return handler


@pytest.mark.asyncio
async def test_fetches_unwraps_and_the_key_actually_works():
    ring = _ring()
    dek = new_dek()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Internal-Token"] == "itok", "the DEK read must be token-gated"
        wrapped, ref = wrap_dek(ring, dek, _uid_from(request))
        return httpx.Response(200, json={"wrapped_dek": wrapped, "key_ref": ref})

    c = _client(handler, ring)
    try:
        got = await c.get(uuid4())
        assert got == dek
        assert decrypt(got, encrypt(got, "private")) == "private"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_caches_so_the_hot_path_does_not_hit_auth_every_write():
    ring = _ring()
    dek = new_dek()
    calls = {"n": 0}
    c = _client(_serve_dek(ring, dek, count=calls), ring)
    uid = uuid4()
    try:
        a = await c.get(uid)
        b = await c.get(uid)
        assert a == b
        assert calls["n"] == 1, "the DEK must be cached — otherwise every message write adds an HTTP hop"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_forget_drops_the_cached_key():
    """Erasure (D18) and KEK rotation both depend on this. A stale cached DEK would let a
    process keep decrypting content that is supposed to be unrecoverable."""
    ring = _ring()
    calls = {"n": 0}
    c = _client(_serve_dek(ring, new_dek(), count=calls), ring)
    uid = uuid4()
    try:
        await c.get(uid)
        c.forget(uid)
        await c.get(uid)
        assert calls["n"] == 2
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_no_KEK_configured_raises_and_NEVER_degrades_to_plaintext():
    """auth returns 503 when the deployment has no KEK. The caller must ABORT.

    The alternative — quietly writing the diary unencrypted — is the failure mode this
    whole slice exists to prevent, and it would be invisible: the plaintext row looks
    exactly like an encrypted one to every future reader.
    """
    c = _client(lambda r: httpx.Response(503, json={"error": "no kek"}))
    try:
        with pytest.raises(DEKUnavailable, match="do not store plaintext"):
            await c.get(uuid4())
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_auth_unreachable_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("auth is down")

    c = _client(handler)
    try:
        with pytest.raises(DEKUnavailable, match="Refusing to continue"):
            await c.get(uuid4())
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_a_key_we_cannot_unwrap_raises_and_names_the_rotation_cause():
    """The service's KEK cannot unwrap what auth stored — almost always a rotation where
    the OLD kek was not added to the retired keyring. Left undiagnosed, that makes every
    affected user's content unreadable, so the error must say so."""
    old_ring = _ring(active="kek-OLD")
    wrapped, ref = wrap_dek(old_ring, new_dek())

    # This service only knows the NEW kek, and forgot to retire the old one.
    new_ring = _ring(active="kek-NEW")

    c = _client(lambda r: httpx.Response(200, json={"wrapped_dek": wrapped, "key_ref": ref}), new_ring)
    try:
        with pytest.raises(DEKUnavailable, match="retired keyring"):
            await c.get(uuid4())
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_rotation_with_a_retired_keyring_still_works():
    """The same rotation, done correctly, must be transparent."""
    old = _ring(active="kek-OLD")
    dek = new_dek()
    rotated = _ring(active="kek-NEW", retired=("kek-OLD",))

    def handler(request: httpx.Request) -> httpx.Response:
        # wrapped under the OLD kek, bound to the requested user
        wrapped, ref = wrap_dek(old, dek, _uid_from(request))
        return httpx.Response(200, json={"wrapped_dek": wrapped, "key_ref": ref})

    c = _client(handler, rotated)
    try:
        assert await c.get(uuid4()) == dek
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_cache_is_bounded():
    """A multi-tenant worker must not pin every user's key in memory forever."""
    ring = _ring()

    def handler(request: httpx.Request) -> httpx.Response:
        wrapped, ref = wrap_dek(ring, new_dek(), _uid_from(request))
        return httpx.Response(200, json={"wrapped_dek": wrapped, "key_ref": ref})

    c = DEKClient("http://auth", "itok", ring, max_cached=3)
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers={"X-Internal-Token": "itok"},
    )
    try:
        for _ in range(10):
            await c.get(uuid4())
        assert len(c._cache) == 3
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_cache_entry_expires_after_the_ttl_and_is_refetched():
    """DBT-6: the cache now has a TTL. A hit inside the TTL is served from cache (the hot
    path stays cheap); once it expires it is re-fetched, so a key change eventually
    propagates without a process restart."""
    ring = _ring()
    now = {"t": 1000.0}
    calls = {"n": 0}
    c = DEKClient("http://auth", "itok", ring, ttl_s=60.0, _clock=lambda: now["t"])
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(_serve_dek(ring, new_dek(), count=calls)),
        headers={"X-Internal-Token": "itok"},
    )
    uid = uuid4()
    try:
        await c.get(uid)  # fetch #1 → cached, expires at 1060
        now["t"] = 1059.0
        await c.get(uid)  # still fresh → cache hit, no fetch
        assert calls["n"] == 1, "a DEK inside its TTL must be served from cache"
        now["t"] = 1061.0  # past the TTL
        await c.get(uid)  # expired → re-fetch
        assert calls["n"] == 2, "an expired DEK must be re-fetched, never served stale forever"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_the_ttl_bounds_how_long_a_shredded_key_keeps_decrypting():
    """The reason the TTL exists. forget() is the prompt eviction path, but if an erasure
    (D18) elsewhere never calls it — or a concurrent worker cached the key just before the
    shred — the destroyed key must not linger forever. Within one TTL the client stops using
    it and picks up whatever auth now serves (a fresh key, or a fail-closed error)."""
    ring = _ring()
    now = {"t": 0.0}
    old, fresh = new_dek(), new_dek()
    served = {"dek": old}

    def handler(request: httpx.Request) -> httpx.Response:
        wrapped, ref = wrap_dek(ring, served["dek"], _uid_from(request))
        return httpx.Response(200, json={"wrapped_dek": wrapped, "key_ref": ref})

    c = DEKClient("http://auth", "itok", ring, ttl_s=30.0, _clock=lambda: now["t"])
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers={"X-Internal-Token": "itok"},
    )
    uid = uuid4()
    try:
        assert await c.get(uid) == old
        # The user's key is crypto-shredded and re-provisioned; NOBODY called forget().
        served["dek"] = fresh
        assert await c.get(uid) == old, "inside the TTL the cached key is still used (expected)"
        now["t"] = 31.0  # one TTL later
        assert await c.get(uid) == fresh, (
            "past the TTL the client must pick up the new key — never keep decrypting with "
            "the shredded one"
        )
    finally:
        await c.aclose()
