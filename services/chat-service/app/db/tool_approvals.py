"""RAID Wave C2 (DR-C2) + Track D S-SPEND — per-user tool approval allowlist.

Two ORTHOGONAL, separately-persisted consents live here, keyed by ``kind``:

* ``kind="mutation"`` (DR-C2) — "let this Tier-A tool WRITE." In Write mode the
  tool loop suspends on a Tier-A tool the user has not allowlisted; the FE renders
  approve-once / always-allow / deny. "Always allow" persists a row so the tool
  never prompts again for this user.
* ``kind="spend"`` (S-SPEND) — "let this PAID tool SPEND my money." A ``_meta.paid``
  tool (external paid search / an LLM research loop) costs real money to CALL. That
  is orthogonal to tier (a paid READ is Tier R) and to mode (``ask`` restricts
  mutation, not spend), so a paid tool prompts on the SYNC tool-call path even at
  Tier R / in ask mode. Approving "may write" is NOT approving "may spend" — the
  two consents are distinct, independently granted, and independently revocable.

Persistence uses the EXISTING ``user_tool_approvals`` table (PK ``(user_id,
tool_name)``) with NO schema migration: the mutation grant keeps the legacy,
un-namespaced ``tool_name`` key (so pre-S-SPEND rows and the Tier-A gate keep
matching); every other kind is stored under a distinct ``<kind>::<tool>`` key —
a SEPARATE row. (A ``kind`` column would be marginally cleaner but is out of this
slice's file scope; the namespaced key gives the same separation on the same PK.)

Plain async functions to match the service's inline-SQL style (chat-service has no
repository layer). Every query is scoped by user_id (tenancy).

Failure semantics: the READ helper raises; the tool-loop call site decides how to
degrade — the MUTATION gate fails OPEN (a reversible write must not brick tool
calling on a DB blip), while the SPEND gate fails CLOSED (spend is irreversible, so
a read failure must never silently spend money).
"""
from __future__ import annotations

import asyncpg

# Closed set of approval kinds (mirrors the wire card's ``approval_kinds``).
MUTATION_KIND = "mutation"
SPEND_KIND = "spend"
APPROVAL_KINDS = (MUTATION_KIND, SPEND_KIND)


def _storage_key(tool_name: str, kind: str) -> str:
    """Map ``(tool_name, kind)`` to the row's ``tool_name`` value.

    Mutation is the LEGACY un-namespaced key — backward compatible with rows
    written before S-SPEND and with the existing Tier-A gate. Every other kind is
    namespaced ``<kind>::<tool>`` so it is a DISTINCT row on the ``(user_id,
    tool_name)`` PK. Tool names are ``[a-z0-9_]``-style identifiers, so ``::`` never
    collides with a real tool name (and never contains a NUL, which Postgres TEXT
    rejects)."""
    return tool_name if kind == MUTATION_KIND else f"{kind}::{tool_name}"


async def is_tool_approved(
    pool: asyncpg.Pool, user_id: str, tool_name: str, kind: str = MUTATION_KIND
) -> bool:
    """True when the user has an "Always allow" row for this tool + consent kind."""
    row = await pool.fetchval(
        "SELECT 1 FROM user_tool_approvals WHERE user_id = $1 AND tool_name = $2",
        user_id, _storage_key(tool_name, kind),
    )
    return row is not None


async def approve_tool(
    pool: asyncpg.Pool, user_id: str, tool_name: str, kind: str = MUTATION_KIND
) -> None:
    """Persist an "Always allow" row for this tool + consent kind (idempotent —
    re-approving is a no-op). Each kind is a separate row, so approving spend does
    NOT approve mutation and vice-versa."""
    await pool.execute(
        """
        INSERT INTO user_tool_approvals (user_id, tool_name)
        VALUES ($1, $2)
        ON CONFLICT (user_id, tool_name) DO NOTHING
        """,
        user_id, _storage_key(tool_name, kind),
    )
