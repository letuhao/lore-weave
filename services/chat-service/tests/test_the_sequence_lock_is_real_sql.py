"""D-AN-ABORTED-TURNS-DETACHED-WRITE-RACES-THE-RETRYS-SEQUENCE — the SQL half.

The message position was allocated with a read-then-write and no lock:

    seq = SELECT COALESCE(MAX(sequence_num),0)+1 FROM chat_messages
          WHERE session_id=$1 AND branch_id=0
    INSERT ... VALUES (... seq ... branch_id=0 ...)

against a UNIQUE index on (session_id, sequence_num, branch_id). When a client aborts a turn,
stream_service DETACHES the persist and writes the interrupted reply after cancel; a retry of
that turn races it and one of them gets a 500. Reproduced 2026-08-26, batch c-motiflink13,
2 of 5 runs, with the log open:

    interrupt-persist detached for session 01a03eaa-823b-... (write continues after cancel)
    POST /messages (the retry) -> 500 duplicate key ... idx_chat_messages_branch_unique
    DETAIL: Key (session_id, sequence_num, branch_id)=(01a03eaa-..., 2, 0) already exists.

🔴 AND THE FIRST FIX SHIPPED BROKEN SQL. It called
`pg_advisory_xact_lock(hashtextextended($1, 0), $2)` — a bigint AND an int — where Postgres has
only `(key bigint)` or `(key1 int4, key2 int4)`. Every message POST then failed with
`function pg_advisory_xact_lock(bigint, unknown) does not exist`: 5 of 5 runs on the next live
batch, a strictly worse outcome than the defect.

The whole chat suite was green through that, and it could not have been otherwise — every test
of this path uses a FAKE connection, so no assertion in 3,608 tests executes a single character
of the SQL. That is the gap this file closes: it runs the real statements against the real
database, which is two seconds and the only thing that could have caught it.
"""
from __future__ import annotations

import os

import asyncpg
import pytest

from app.db.message_sequence import _LOCK_NAMESPACE, SequenceAllocationUnsafe, next_sequence_num

#: EXPLICIT opt-in, and deliberately not `DATABASE_URL`. That variable is set in this service's
#: environment to the CONTAINER-internal host (`@postgres:5432`), which does not resolve from
#: anywhere else — so falling back to it made these four tests FAIL rather than skip in an
#: ordinary run, which is how a live-DB test becomes something people delete.
#:
#: Run them with the host-reachable DSN:
#:   CHAT_DB_URL="$(docker exec infra-chat-service-1 printenv DATABASE_URL |
#:                  sed 's#@postgres:5432#@localhost:5555#')" pytest tests/test_the_sequence_lock_is_real_sql.py
DSN = os.environ.get("CHAT_DB_URL") or ""

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="needs a host-reachable chat DB; set CHAT_DB_URL (see the note above)",
)


@pytest.mark.asyncio
async def test_the_lock_statement_is_valid_sql():
    """The defect verbatim: the overload has to EXIST. A fake connection accepts any string."""
    conn = await asyncpg.connect(DSN)
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, $2))",
                "01a03eaa-823b-7d73-86c9-dbf4d3a32f43", _LOCK_NAMESPACE,
            )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_the_WRONG_overload_really_does_fail():
    """ANTI-VACUITY. If both spellings worked, the test above would prove nothing — so pin that
    the two-argument form genuinely rejects (bigint, int), which is what shipped."""
    conn = await asyncpg.connect(DSN)
    try:
        with pytest.raises(asyncpg.exceptions.UndefinedFunctionError):
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0), $2)",
                    "01a03eaa-823b-7d73-86c9-dbf4d3a32f43", _LOCK_NAMESPACE,
                )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_it_allocates_and_serialises():
    """The behaviour the lock exists for: two concurrent allocators for the SAME session do not
    return the same number. Without the lock both read the same MAX and collide on the unique
    index — which is the 500 users saw."""
    a = await asyncpg.connect(DSN)
    b = await asyncpg.connect(DSN)
    session = "00000000-0000-4000-8000-00000000dead"
    try:
        tx_a = a.transaction()
        await tx_a.start()
        first = await next_sequence_num(a, session)

        # B blocks on the lock until A commits, so it cannot read the same MAX.
        import asyncio
        tx_b = b.transaction()
        await tx_b.start()
        task = asyncio.create_task(next_sequence_num(b, session))
        await asyncio.sleep(0.3)
        assert not task.done(), "the second allocator did not block — the lock is not serialising"

        await tx_a.rollback()
        second = await task
        await tx_b.rollback()
        assert isinstance(first, int) and isinstance(second, int)
    finally:
        await a.close()
        await b.close()


@pytest.mark.asyncio
async def test_it_REFUSES_outside_a_transaction():
    """pg_advisory_xact_lock is released at transaction end, so on an autocommit connection it
    would be taken and dropped by the same statement — protecting nothing while looking
    protected. That is worse than no lock, so it raises."""
    conn = await asyncpg.connect(DSN)
    try:
        with pytest.raises(SequenceAllocationUnsafe):
            await next_sequence_num(conn, "00000000-0000-4000-8000-00000000dead")
    finally:
        await conn.close()
