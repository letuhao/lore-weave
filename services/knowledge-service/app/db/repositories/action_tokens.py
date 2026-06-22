"""consumed_tokens repository (KM6 — class-C confirm-token single-use ledger).

Backs the §13.4 single-use guarantee: ``consume`` records a jti the first time a
confirm-token is redeemed and reports whether THIS call won the claim. A replay of
the same token hits the PK and is rejected (0 rows → ``False``).

Not tenant-scoped: the jti namespace is server-minted and globally unique; the
authority/identity checks happen at the confirm endpoint BEFORE the claim. The
ledger only enforces one-shot.
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

__all__ = ["ActionTokenRepo"]


class ActionTokenRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def consume(self, *, jti: str, descriptor: str, exp: datetime) -> bool:
        """Atomically claim a jti. Returns ``True`` the FIRST time a jti is seen,
        ``False`` on a replay (PK conflict → ``ON CONFLICT DO NOTHING`` → 0 rows).

        Consume-first / fail-closed (§13.4): the caller claims BEFORE running the
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
        # "INSERT 0 0" (conflict → nothing inserted).
        return status.endswith(" 1")
