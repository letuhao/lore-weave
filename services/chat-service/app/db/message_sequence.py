"""One place that allocates a message's position in a session.

🔴 D-AN-ABORTED-TURNS-DETACHED-WRITE-RACES-THE-RETRYS-SEQUENCE. Every caller did this:

    seq = SELECT COALESCE(MAX(sequence_num),0)+1 FROM chat_messages
          WHERE session_id=$1 AND branch_id=0
    INSERT INTO chat_messages (... sequence_num ...) VALUES (... seq ... 0 ...)

a read-then-write with nothing between them, against a UNIQUE index on
(session_id, sequence_num, branch_id). Under READ COMMITTED two transactions read the same MAX
quite happily, so two concurrent writers pick the same number and the second gets a 500.

The second writer is the platform's own. When a client aborts a turn, stream_service DETACHES
the persist — "interrupt-persist detached ... (write continues after cancel)" — and then writes
the interrupted assistant reply. A client that retries the aborted turn races that write, which
is the ordinary shape of impatience: stop a slow reply, ask again.

MEASURED 2026-08-26, batch c-motiflink13, 2 of 5 runs:

    interrupt-persist detached for session 01a03eaa-823b-... (write continues after cancel)
    terminal-persist: saved interrupted assistant reply ... 0 chars, outcome=abandoned_by_user
    POST /messages (the retry) -> 500
    duplicate key value violates unique constraint "idx_chat_messages_branch_unique"
    DETAIL: Key (session_id, sequence_num, branch_id)=(01a03eaa-..., 2, 0) already exists.

WHY AN ADVISORY LOCK AND NOT A RETRY. A retry-on-unique-violation would paper over the race
while leaving two writers free to interleave anywhere else; the lock makes allocation and insert
one indivisible step for a session, which is the property the unique index is actually asserting.
It needs no migration, and it releases at COMMIT rather than on a code path someone can miss.

WHY IT MUST BE CALLED INSIDE A TRANSACTION. `pg_advisory_xact_lock` is scoped to the
transaction. Called on an autocommit connection it is taken and released by the same statement,
which is a silent no-op — the worst possible outcome, because the code would look protected.
This function therefore REFUSES rather than degrade, and the two voice-surface call sites (which
acquire a connection without a transaction) are deliberately NOT converted here: wrapping them
changes behaviour on a surface this defect was never measured on.
"""
from __future__ import annotations

import asyncpg


#: Arbitrary but FIXED — two locks with the same key in different namespaces do not contend.
#: Changing it would silently stop serialising against any writer still using the old value, so
#: it is a constant rather than a parameter.
_LOCK_NAMESPACE = 0x6D736571  # "mseq"


class SequenceAllocationUnsafe(RuntimeError):
    """Raised when the caller is not in a transaction, so the lock would be a no-op."""


async def next_sequence_num(conn: asyncpg.Connection, session_id: str, *, branch_id: int = 0) -> int:
    """The next free `sequence_num` for a session, allocated under a per-session lock.

    The lock is held until the caller's transaction commits, so the INSERT that uses this number
    is covered by it. Concurrent callers for the SAME session serialise; different sessions do
    not contend at all.
    """
    if not conn.is_in_transaction():
        raise SequenceAllocationUnsafe(
            "next_sequence_num must be called inside a transaction — pg_advisory_xact_lock is "
            "released at transaction end, so on an autocommit connection it would be taken and "
            "dropped by the same statement and protect nothing"
        )
    # 🔴 THE TWO OVERLOADS ARE NOT INTERCHANGEABLE, and mixing them shipped a 500. This first
    # read `pg_advisory_xact_lock(hashtextextended($1, 0), $2)` — a bigint AND an int — and
    # Postgres has only `(key bigint)` or `(key1 int4, key2 int4)`, so every message POST failed
    # with `function pg_advisory_xact_lock(bigint, unknown) does not exist`. Measured 5/5 on the
    # first live batch after deploy; the unit suite could not catch it because the connection
    # there is a fake.
    #
    # The single-bigint form is the right one: hashtextextended takes the namespace as its SEED,
    # so the lock is still namespaced and cannot collide with an unrelated advisory lock.
    await conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended($1, $2))",
        str(session_id), _LOCK_NAMESPACE,
    )
    return await conn.fetchval(
        "SELECT COALESCE(MAX(sequence_num), 0) + 1 FROM chat_messages "
        "WHERE session_id = $1 AND branch_id = $2",
        str(session_id), branch_id,
    )
