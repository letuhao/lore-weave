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

Persistence uses the ``user_tool_approvals`` table (PK ``(user_id, tool_name)``): the
mutation grant keeps the legacy, un-namespaced ``tool_name`` key (so pre-S-SPEND rows
and the Tier-A gate keep matching); every other kind is stored under a distinct
``<kind>::<tool>`` key — a SEPARATE row. (A ``kind`` column would be marginally cleaner
but the namespaced key gives the same separation on the same PK.)

Track C WS-3 (``D-C-ALLOWLIST-WRITE-ONLY``) added the ``decision`` column and closed the
consent loop. The table used to be INSERT-ONLY — a row's mere EXISTENCE meant "granted",
so a user could hand an autonomous agent a standing permission and then never see it,
withdraw it, or refuse it outright. A row now carries its decision:

* ``decision="allow"`` — the legacy "Always allow" (every pre-existing row is one).
* ``decision="deny"``  — a persistent "Never allow". The gate BLOCKS the call and feeds
  the model an honest error; it must not raise an approval card, because re-asking for
  something the user already refused forever is the same consent defect in a new coat.

The two are mutually exclusive by construction (one row per key), and both are listable
(:func:`list_tool_decisions`) and withdrawable (:func:`revoke_tool_decision`).

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
    collides with a real tool name.

    That last sentence used to be an ASSUMPTION, and it was wrong: the name reaches here
    from a URL path (and, in the panel, from a free-text box). ``_storage_key("spend::web",
    "mutation")`` returns ``"spend::web"`` — the SPEND slot for ``web`` — so an
    unvalidated name silently forges or erases a consent on an axis the caller never
    named. The route rejects such names with a 422; this raises as well, so the invariant
    holds for every caller, not just the one that remembered to check."""
    if "::" in tool_name:
        raise ValueError(
            f"tool_name may not contain '::' (it would collide with the kind namespace): {tool_name!r}"
        )
    return tool_name if kind == MUTATION_KIND else f"{kind}::{tool_name}"


def _split_key(storage_key: str) -> tuple[str, str]:
    """Inverse of :func:`_storage_key` — decode a stored row back to ``(tool, kind)``.

    An un-namespaced key is the legacy mutation grant. A ``<kind>::<tool>`` key is
    decoded only when ``<kind>`` is a KNOWN kind: an unrecognised prefix is treated as
    part of the tool name rather than silently inventing a consent axis the gate never
    checks (a row the user cannot see is what this whole slice exists to fix)."""
    head, sep, tail = storage_key.partition("::")
    if sep and head in APPROVAL_KINDS and tail:
        return tail, head
    return storage_key, MUTATION_KIND


async def get_tool_decision(
    pool: asyncpg.Pool, user_id: str, tool_name: str, kind: str = MUTATION_KIND
) -> str | None:
    """The user's standing decision for this tool + consent kind.

    ``"allow"`` (Always allow) · ``"deny"`` (Never allow) · ``None`` (undecided — the
    gate should prompt). ONE read serves both the allow and the deny question, so the
    deny-list adds **no new failure path**: the caller's existing degrade (mutation
    fails OPEN, spend fails CLOSED) still governs a read error, unchanged."""
    return await pool.fetchval(
        "SELECT decision FROM user_tool_approvals WHERE user_id = $1 AND tool_name = $2",
        user_id, _storage_key(tool_name, kind),
    )


async def is_tool_approved(
    pool: asyncpg.Pool, user_id: str, tool_name: str, kind: str = MUTATION_KIND
) -> bool:
    """True when the user has an "Always allow" row for this tool + consent kind.

    A ``deny`` row is NOT an approval — this must read the decision, not the row's mere
    existence, or a denied tool would present as approved (the inversion the ``decision``
    column exists to make impossible)."""
    return await get_tool_decision(pool, user_id, tool_name, kind) == "allow"


async def set_tool_decision(
    pool: asyncpg.Pool, user_id: str, tool_name: str, kind: str = MUTATION_KIND,
    decision: str = "allow",
) -> None:
    """Persist a standing ``allow``/``deny`` for this tool + consent kind.

    Upsert, so a decision is FLIPPED in place — granting a tool the user had denied (or
    denying one they had allowed) overwrites the single row rather than leaving two
    contradictory ones. Each kind is a separate row, so allowing spend does NOT allow
    mutation and vice-versa."""
    if decision not in ("allow", "deny"):
        raise ValueError(f"decision must be 'allow' or 'deny', got {decision!r}")
    await pool.execute(
        """
        INSERT INTO user_tool_approvals (user_id, tool_name, decision)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, tool_name) DO UPDATE
           SET decision = EXCLUDED.decision, created_at = now()
        """,
        user_id, _storage_key(tool_name, kind), decision,
    )


async def approve_tool(
    pool: asyncpg.Pool, user_id: str, tool_name: str, kind: str = MUTATION_KIND
) -> None:
    """Persist an "Always allow" row for this tool + consent kind (idempotent)."""
    await set_tool_decision(pool, user_id, tool_name, kind, "allow")


async def list_tool_decisions(pool: asyncpg.Pool, user_id: str) -> list[dict]:
    """Every standing decision this user has made, decoded back to (tool, kind).

    The read half of the consent loop: without it a grant is invisible, and a permission
    the user cannot see is one they cannot withdraw. Owner-scoped (tenancy)."""
    rows = await pool.fetch(
        """
        SELECT tool_name, decision, created_at
          FROM user_tool_approvals
         WHERE user_id = $1
         ORDER BY created_at DESC
        """,
        user_id,
    )
    out: list[dict] = []
    for r in rows:
        tool, kind = _split_key(r["tool_name"])
        out.append({
            "tool_name": tool,
            "kind": kind,
            "decision": r["decision"],
            "created_at": r["created_at"],
        })
    return out


async def revoke_tool_decision(
    pool: asyncpg.Pool, user_id: str, tool_name: str, kind: str = MUTATION_KIND
) -> bool:
    """Withdraw a standing decision — the tool prompts again on its next call.

    Returns whether a row was actually removed, so the route can 404 instead of
    reporting a cheerful success for a decision that never existed (a revoke that
    silently no-ops would leave the user believing they had taken a permission back
    when they had not — the worst possible lie for a consent surface)."""
    tag = await pool.execute(
        "DELETE FROM user_tool_approvals WHERE user_id = $1 AND tool_name = $2",
        user_id, _storage_key(tool_name, kind),
    )
    return bool(tag) and not str(tag).endswith(" 0")
