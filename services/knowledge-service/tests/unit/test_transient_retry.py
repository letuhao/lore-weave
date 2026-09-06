"""T80 — the transaction retry, and what it must NOT retry.

The optimistic-concurrency path takes an exclusive lock and reads the version under it, which
is the only measured shape where two concurrent editors cannot both be told their edit landed.
The cost is that two transactions racing for the same node form a lock cycle often enough to
matter — the live test `test_occ_is_actually_atomic.py` failed on a `TransientError` before
this retry existed, on the very first run.

A deadlock is a *retryable* outcome. Unretried it is a 500 for a request that would have
succeeded a millisecond later. Retried, the whole transaction replays and re-reads the version,
so a retry can never turn a version mismatch into a stale success — which is the property that
makes retrying safe here specifically, and it is asserted below rather than assumed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.neo4j_helpers import in_retried_transaction, is_transient


class _FakeTransient(Exception):
    """Stands in for the driver's `TransientError`, matched by class NAME.

    `neo4j_helpers` is deliberately importable without the `neo4j` package, so the check is
    duck-typed. That is a real design choice with a real cost — a rename in the driver would
    silently stop matching — so both halves of the match are exercised here.
    """

    __name__ = "TransientError"


class TransientError(Exception):
    """Same name as the driver's class, so the NAME half of the match fires."""


class _Coded(Exception):
    """Matched by the `Neo.TransientError.` code prefix instead."""

    code = "Neo.TransientError.Transaction.DeadlockDetected"


class _NotTransient(Exception):
    code = "Neo.ClientError.Statement.SyntaxError"


def _session(op_results):
    """A session whose `begin_transaction` hands back a fresh tx each attempt."""
    session = MagicMock()
    txs = []

    async def _begin():
        tx = MagicMock()
        tx.commit = AsyncMock()
        tx.__aenter__ = AsyncMock(return_value=tx)
        tx.__aexit__ = AsyncMock(return_value=False)
        txs.append(tx)
        return tx

    session.begin_transaction = _begin
    return session, txs


@pytest.mark.parametrize("exc,expected", [
    (TransientError("deadlock"), True),
    (_Coded("deadlock"), True),
    (_NotTransient("bad cypher"), False),
    (ValueError("nothing to do with the driver"), False),
])
def test_is_transient_matches_by_code_AND_by_class_name(exc, expected):
    assert is_transient(exc) is expected


@pytest.mark.asyncio
async def test_a_deadlock_is_RETRIED_and_the_second_attempt_wins():
    session, txs = _session(None)
    calls = []

    async def op(tx):
        calls.append(tx)
        if len(calls) == 1:
            raise TransientError("deadlock detected")
        return "ok"

    out = await in_retried_transaction(session, op, base_delay=0)
    assert out == "ok"
    assert len(calls) == 2, "the operation was not retried"
    assert calls[0] is not calls[1], (
        "the retry reused the SAME transaction — a deadlocked transaction is dead, and "
        "replaying inside it would fail again for a reason that has nothing to do with locks"
    )
    assert len(txs) == 2 and txs[1].commit.await_count == 1


@pytest.mark.asyncio
async def test_a_NON_transient_error_is_not_retried():
    """A syntax error or a `VersionMismatchError` must surface on the first attempt. Retrying
    them would turn one bad request into three, and — for the mismatch — would hide a 412
    behind a delay."""
    session, _ = _session(None)
    calls = []

    async def op(tx):
        calls.append(tx)
        raise _NotTransient("bad cypher")

    with pytest.raises(_NotTransient):
        await in_retried_transaction(session, op, base_delay=0)
    assert len(calls) == 1, "a non-retryable error was retried"


@pytest.mark.asyncio
async def test_the_retry_is_BOUNDED_and_the_last_failure_surfaces():
    """A node under sustained contention must eventually return an error rather than spin."""
    session, _ = _session(None)
    calls = []

    async def op(tx):
        calls.append(tx)
        raise TransientError("deadlock detected")

    with pytest.raises(TransientError):
        await in_retried_transaction(session, op, attempts=3, base_delay=0)
    assert len(calls) == 3, f"expected exactly 3 attempts, got {len(calls)}"


@pytest.mark.asyncio
async def test_the_replay_RE_READS_rather_than_reusing_the_first_attempt_s_decision():
    """The property that makes retrying safe for optimistic concurrency.

    Attempt 1 reads version 1 and deadlocks. By the time attempt 2 runs, the other editor has
    committed and the version is 2. The replayed operation must see 2 — if the helper cached
    anything from attempt 1, the caller would apply an edit against a baseline that no longer
    exists and the concurrency guarantee would be gone.
    """
    session, _ = _session(None)
    versions = iter([1, 2])
    seen = []

    async def op(tx):
        v = next(versions)
        seen.append(v)
        if v == 1:
            raise TransientError("deadlock detected")
        return v

    out = await in_retried_transaction(session, op, base_delay=0)
    assert out == 2 and seen == [1, 2], (
        f"the replay did not re-derive its decision from fresh state: {seen}"
    )
