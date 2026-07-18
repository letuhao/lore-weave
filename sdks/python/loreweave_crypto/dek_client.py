"""WS-1.0 — the consumer-side DEK client (DECISIONS-SEALED PO-2).

Every Python service that stores or reads a user's private content (chat-service,
knowledge-service, worker-ai) needs that user's DEK. This is the one way to get it:

    auth-service  ──(wrapped dek, over the internal network)──>  this client
                                                                     │
                                            unwrap with the KEK from OUR OWN env
                                                                     │
                                                          plaintext DEK, in memory only

The plaintext key never crosses the network, and auth-service itself cannot read it — it
stores an opaque blob.

CACHING. The DEK is fetched once per user and held in-process. Without a cache, every
message write and every recall query would add an HTTP round-trip to auth on the hot path.
The cache is bounded (LRU) so a large multi-tenant worker cannot pin every user's key in
memory forever.

⚠️ A cached plaintext DEK is exactly what an operator with server access can read. That is
the documented, accepted limit of this design (see the module docstring in __init__): a
server-side AI pipeline must see plaintext. The cache does not make it worse — the key is
already unavoidably in memory whenever we decrypt — but do not pretend otherwise.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from uuid import UUID

import httpx

from . import DEK, CryptoError, Keyring, unwrap_dek

logger = logging.getLogger(__name__)

__all__ = ["DEKClient", "DEKUnavailable"]


class DEKUnavailable(CryptoError):
    """We could not obtain the user's key.

    Callers MUST fail the operation. They must NOT fall back to writing plaintext — a
    "temporarily unencrypted" write is permanent, and the row will look identical to an
    encrypted one to every future reader.
    """


class DEKClient:
    """Fetches + unwraps + caches per-user DEKs."""

    def __init__(
        self,
        auth_base_url: str,
        internal_token: str,
        keyring: Keyring,
        *,
        max_cached: int = 512,
        timeout_s: float = 5.0,
        ttl_s: float = 300.0,
        _clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base = auth_base_url.rstrip("/")
        self._keyring = keyring
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )
        # value = (dek, expires_at_monotonic). The TTL is a SAFETY BACKSTOP for erasure and
        # rotation: forget() is the prompt path, but if an erasure elsewhere forgets to call
        # it (or races a concurrent worker that already cached the key), a shredded/rotated
        # key must not linger forever letting this process decrypt content that is supposed
        # to be gone. A bounded lifetime bounds that window without an auth round-trip per op.
        self._cache: OrderedDict[UUID, tuple[DEK, float]] = OrderedDict()
        self._max = max_cached
        self._ttl_s = ttl_s
        self._clock = _clock

    async def aclose(self) -> None:
        await self._http.aclose()

    def forget(self, user_id: UUID) -> None:
        """Drop a cached key.

        Call this on erasure (D18) and on a KEK rotation. A stale cached DEK for a user
        whose key was destroyed would let this process keep decrypting content that is
        supposed to be unrecoverable. The TTL is the backstop; this is the prompt path.
        """
        self._cache.pop(user_id, None)

    async def get(self, user_id: UUID) -> DEK:
        """The user's plaintext DEK, provisioning it on first use.

        Raises DEKUnavailable on ANY failure — auth down, no KEK configured, a wrapped blob
        we cannot unwrap. The caller must abort, never degrade to plaintext.
        """
        cached = self._cache.get(user_id)
        if cached is not None:
            dek, expires_at = cached
            if self._clock() < expires_at:
                self._cache.move_to_end(user_id)
                return dek
            # Expired → treat as a miss and re-fetch. If the key was shredded, the re-fetch
            # will mint a NEW one (or fail closed), never resurrect the old plaintext.
            self._cache.pop(user_id, None)

        url = f"{self._base}/internal/users/{user_id}/dek"
        try:
            resp = await self._http.get(url)
        except httpx.HTTPError as exc:
            raise DEKUnavailable(
                f"auth-service unreachable while fetching the DEK for {user_id}: {exc}. "
                f"Refusing to continue — writing this content unencrypted is not an option."
            ) from exc

        if resp.status_code == 503:
            # auth-service has no KEK configured. This is a deployment error, and it must
            # be loud: the alternative is a service that quietly stores diaries in the clear.
            raise DEKUnavailable(
                "auth-service reports no DIARY_ENCRYPTION_KEY is configured. Private "
                "content cannot be stored. Fix the deployment; do not store plaintext."
            )
        if resp.status_code != 200:
            raise DEKUnavailable(
                f"auth-service returned {resp.status_code} fetching the DEK for {user_id}"
            )

        try:
            body = resp.json()
            wrapped = body["wrapped_dek"]
        except (ValueError, KeyError) as exc:
            raise DEKUnavailable(f"malformed DEK response for {user_id}") from exc

        try:
            # Pass user_id — auth-service bound the wrap to it (AAD). A wrapped_dek that
            # belongs to a different user (a row-swap) fails to unwrap here.
            dek = unwrap_dek(self._keyring, wrapped, str(user_id))
        except CryptoError as exc:
            # The KEK this service holds cannot unwrap what auth stored. Almost always a
            # rotation where the previous KEK was not added to the retired keyring —
            # which, left alone, makes every affected user's content unreadable.
            raise DEKUnavailable(
                f"could not unwrap the DEK for {user_id} with this service's KEK "
                f"(key_ref={body.get('key_ref')!r}). If the KEK was rotated, the PREVIOUS "
                f"value must be in the retired keyring."
            ) from exc

        self._cache[user_id] = (dek, self._clock() + self._ttl_s)
        self._cache.move_to_end(user_id)
        while len(self._cache) > self._max:
            self._cache.popitem(last=False)
        return dek
