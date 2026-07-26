"""plan_bootstrap_proposal repository (PlanForge auto-bootstrap POC gate).

Tenancy (BPS re-key, spec 25 OQ-3): rows are BOOK-scoped — every method
filters by book_id, and access is decided BEFORE the repo at the route's E0
book-grant gate. `created_by` is a plain actor stamp on the INSERT — STORED,
never filtered on. A foreign/missing id returns None, routers map to 404 (no
existence oracle).

The pending→approved→applying→applied|failed lifecycle is enforced here via
conditional `UPDATE ... WHERE status = <expected>` claims, not a DB trigger
(see the table's migration comment for why — this POC's DAG is small enough
that an app-level guard is sufficient; a `enrichment_proposal`-style
trigger-guarded DAG is available as prior art if this generalizes later).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import PlanBootstrapProposal, PlanBootstrapProposalStatus

_SELECT = """
  id, run_id, book_id, created_by, status, diff, applied_results,
  error_detail, created_at, updated_at
"""


def _jsonb(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {})


def _row(row: asyncpg.Record) -> PlanBootstrapProposal:
    data = dict(row)
    for key in ("diff", "applied_results"):
        v = data.get(key)
        if isinstance(v, str):
            data[key] = json.loads(v)
    return PlanBootstrapProposal.model_validate(data)


class PlanBootstrapProposalsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        created_by: UUID,
        book_id: UUID,
        run_id: UUID,
        *,
        diff: dict[str, Any],
    ) -> PlanBootstrapProposal:
        query = f"""
        INSERT INTO plan_bootstrap_proposal (run_id, book_id, created_by, diff)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING {_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id, book_id, created_by, _jsonb(diff))
        return _row(row)

    async def get_for_book(
        self, book_id: UUID, proposal_id: UUID,
    ) -> PlanBootstrapProposal | None:
        query = f"""
        SELECT {_SELECT} FROM plan_bootstrap_proposal
        WHERE id = $1 AND book_id = $2
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, proposal_id, book_id)
        return _row(row) if row else None

    async def list_active_for_book(
        self, book_id: UUID,
    ) -> list[PlanBootstrapProposal]:
        """Every NON-rejected record for this book (pending/approved/
        applying/applied/failed) — the propose step's second dedup source
        (alongside the book's real current chapters), per spec §4.1.3 /
        §6 M1. Deliberately NOT scoped to 'applied' only: a still-pending or
        still-approved proposal already "claims" its diff's event_ids, so a
        second propose() call before the first is applied must not re-offer
        the same chapters (the M1 hardening fix for the double-propose /
        cross-record race the POC's POST-REVIEW flagged). A real chapter row
        carries no back-reference to the `package.chapters[]` entry that
        created it, so this table is the only place that mapping lives."""
        query = f"""
        SELECT {_SELECT} FROM plan_bootstrap_proposal
        WHERE book_id = $1 AND status != 'rejected'
        ORDER BY created_at DESC
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, book_id)
        return [_row(r) for r in rows]

    async def _transition(
        self,
        book_id: UUID,
        proposal_id: UUID,
        *,
        from_status: PlanBootstrapProposalStatus,
        to_status: PlanBootstrapProposalStatus,
        extra_set: str = "",
        extra_params: list[Any] | None = None,
    ) -> PlanBootstrapProposal | None:
        """Claim a legal transition atomically: only succeeds if the row is
        currently in `from_status`. Returns None (not an error) if the row
        doesn't exist, isn't on this book, or is no longer in `from_status` —
        the caller distinguishes "not found" from "already transitioned" via a
        follow-up `get_for_book` read, same as the rest of this repo's
        no-existence-oracle convention."""
        params: list[Any] = [proposal_id, book_id, to_status, from_status]
        if extra_params:
            params.extend(extra_params)
        query = f"""
        UPDATE plan_bootstrap_proposal
        SET status = $3, updated_at = now(){extra_set}
        WHERE id = $1 AND book_id = $2 AND status = $4
        RETURNING {_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *params)
        return _row(row) if row else None

    async def mark_approved(
        self, book_id: UUID, proposal_id: UUID,
    ) -> PlanBootstrapProposal | None:
        return await self._transition(
            book_id, proposal_id,
            from_status="pending", to_status="approved",
        )

    async def mark_rejected(
        self, book_id: UUID, proposal_id: UUID,
    ) -> PlanBootstrapProposal | None:
        # Rejecting from 'pending' OR 'approved' (not-yet-applied second thoughts)
        # is allowed; kept as status='rejected' for audit, never deleted (§4.1.4).
        for from_status in ("pending", "approved"):
            result = await self._transition(
                book_id, proposal_id,
                from_status=from_status, to_status="rejected",
            )
            if result is not None:
                return result
        return None

    async def claim_for_apply(
        self, book_id: UUID, proposal_id: UUID,
    ) -> PlanBootstrapProposal | None:
        """Atomic claim: succeeds from 'approved' (first apply) OR 'failed'
        (retry after a partial failure — the service resumes via
        `applied_results` rather than restarting from scratch). A
        concurrent/duplicate caller racing this UPDATE gets None back and
        must re-read the record's current status instead of re-running
        mutations blind."""
        query = f"""
        UPDATE plan_bootstrap_proposal
        SET status = 'applying', updated_at = now()
        WHERE id = $1 AND book_id = $2
          AND status IN ('approved', 'failed')
        RETURNING {_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, proposal_id, book_id)
        return _row(row) if row else None

    async def mark_item_applied(
        self,
        book_id: UUID,
        proposal_id: UUID,
        *,
        item_key: str,
        result: dict[str, Any],
    ) -> None:
        """Record one successfully-applied diff item's real-world result
        (e.g. the created chapter_id) into `applied_results` as it happens —
        so a partial failure mid-apply leaves visible per-item progress
        instead of an opaque "500, try again"."""
        query = """
        UPDATE plan_bootstrap_proposal
        SET applied_results = applied_results || $3::jsonb, updated_at = now()
        WHERE id = $1 AND book_id = $2
        """
        async with self._pool.acquire() as c:
            await c.execute(
                query, proposal_id, book_id,
                json.dumps({item_key: result}),
            )

    async def mark_applied(
        self, book_id: UUID, proposal_id: UUID,
    ) -> PlanBootstrapProposal | None:
        return await self._transition(
            book_id, proposal_id,
            from_status="applying", to_status="applied",
            extra_set=", error_detail = NULL",
        )

    async def mark_failed(
        self, book_id: UUID, proposal_id: UUID, *, error_detail: str,
    ) -> PlanBootstrapProposal | None:
        return await self._transition(
            book_id, proposal_id,
            from_status="applying", to_status="failed",
            extra_set=", error_detail = $5", extra_params=[error_detail],
        )
