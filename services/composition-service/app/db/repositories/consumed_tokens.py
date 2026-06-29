"""consumed_tokens repository (W4 — Tier-W confirm-token single-use ledger).

A verbatim clone of knowledge-service's ``ActionTokenRepo`` (KM6). Backs the
replay-prevention guarantee for the W-motif confirm actions (adopt / mine /
import / conformance): ``consume`` records a jti the FIRST time a confirm-token is
redeemed and reports whether THIS call won the claim. A replay of the same token
hits the PK and is rejected (0 rows -> ``False``).

The composition confirm spine (``app/routers/actions.py``) needs this because the
W-motif effects are NOT idempotent-by-effect like publish/generate are: a replayed
adopt past the per-user quota, or a replayed mine, would double-spend. The
confirm-token kit is deliberately stateless / not single-use (``confirm_token.py``:
*"a consuming service that needs one-shot semantics records the (u, r, d, exp) in
its own consumed-token ledger at confirm time"*), so this is that ledger.

``jti = sha256(token_string)`` (W4-MD7): the C-KIT confirm token carries no ``jti``
claim, so we synthesize a deterministic id from the signed token's bytes — a replay
reuses the exact string -> same hash -> ``ON CONFLICT`` rejects it.

Not tenant-scoped: the jti namespace is server-minted and globally unique; the
authority/identity checks happen at the confirm endpoint BEFORE the claim. The
ledger only enforces one-shot.
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

__all__ = ["ConsumedTokenRepo"]


class ConsumedTokenRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def consume(self, *, jti: str, descriptor: str, exp: datetime) -> bool:
        """Atomically claim a jti. Returns ``True`` the FIRST time a jti is seen,
        ``False`` on a replay (PK conflict -> ``ON CONFLICT DO NOTHING`` -> 0 rows).

        Consume-first / fail-closed (W4 §3.1): the caller claims BEFORE running the
        effect; once claimed, a later failed effect does NOT release the jti — a
        spent token never re-applies, the human re-proposes.
        """
        status = await self._pool.execute(
            """
            INSERT INTO consumed_tokens (jti, descriptor, exp)
            VALUES ($1, $2, $3)
            ON CONFLICT (jti) DO NOTHING
            """,
            jti, descriptor, exp,
        )
        # asyncpg returns the command tag, e.g. "INSERT 0 1" (1 row) or
        # "INSERT 0 0" (conflict -> nothing inserted).
        return status.endswith(" 1")
