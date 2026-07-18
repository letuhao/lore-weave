"""Per-tool `_meta` validator (C-TOOL enforcement) — built fresh.

Every kit-registered tool MUST carry machine-readable metadata so the consumer,
gateway, and FE behave correctly without hardcoding tool names:

  - ``_meta.tier``  ∈ {R, A, W, S}   — drives auto-apply vs. confirm.
  - ``_meta.scope`` ∈ {book, project, user, none} — drives which guard runs.
  - ``_meta.undo_hint`` (optional)   — {tool, args} for the Tier-A activity strip.
  - ``_meta.synonyms`` (optional)    — alias terms feeding find_tools recall.

The kit REJECTS a tool registered without BOTH ``tier`` and ``scope`` (legacy
glossary/knowledge tools predate `_meta` and are exempt; only kit-registered
providers must carry it). `require_meta` builds the validated `_meta` dict to pass
to `@server.tool(..., meta=require_meta(...))`.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "TIERS",
    "SCOPES",
    "MetaValidationError",
    "validate_tool_meta",
    "require_meta",
]

TIERS = frozenset({"R", "A", "W", "S"})
SCOPES = frozenset({"book", "project", "user", "none"})


class MetaValidationError(ValueError):
    """A tool was registered with missing/invalid ``_meta`` (no tier or scope, or
    a value outside the allowed enum)."""


def validate_tool_meta(meta: dict[str, Any] | None, *, tool_name: str = "") -> None:
    """Raise ``MetaValidationError`` unless ``meta`` carries a valid ``tier`` AND
    ``scope`` (C-TOOL). A tool with no ``_meta`` at all is rejected.

    ``tool_name`` is only used to make the error message actionable.
    """
    label = f" for tool {tool_name!r}" if tool_name else ""
    if not isinstance(meta, dict):
        raise MetaValidationError(
            f"_meta is required{label}: must declare both 'tier' and 'scope'"
        )

    tier = meta.get("tier")
    scope = meta.get("scope")
    if tier is None:
        raise MetaValidationError(f"_meta.tier is required{label} (one of {sorted(TIERS)})")
    if scope is None:
        raise MetaValidationError(f"_meta.scope is required{label} (one of {sorted(SCOPES)})")
    if tier not in TIERS:
        raise MetaValidationError(
            f"_meta.tier {tier!r} invalid{label}: must be one of {sorted(TIERS)}"
        )
    if scope not in SCOPES:
        raise MetaValidationError(
            f"_meta.scope {scope!r} invalid{label}: must be one of {sorted(SCOPES)}"
        )

    undo = meta.get("undo_hint")
    if undo is not None:
        if not isinstance(undo, dict) or "tool" not in undo:
            raise MetaValidationError(
                f"_meta.undo_hint{label} must be a dict with at least a 'tool' key"
            )

    synonyms = meta.get("synonyms")
    if synonyms is not None and not (
        isinstance(synonyms, (list, tuple))
        and all(isinstance(s, str) for s in synonyms)
    ):
        raise MetaValidationError(f"_meta.synonyms{label} must be a list of strings")


def require_meta(
    tier: str,
    scope: str,
    *,
    undo_hint: dict[str, Any] | None = None,
    synonyms: list[str] | None = None,
    async_job: bool = False,
    paid: bool = False,
    visibility: str | None = None,
    superseded_by: str | None = None,
    tool_name: str = "",
) -> dict[str, Any]:
    """Build a validated ``_meta`` dict, ready to pass as the ``meta=`` argument
    of ``@server.tool(...)``. Raises ``MetaValidationError`` if tier/scope are
    invalid — so a misdeclared tool fails at registration time, not at call time.

    ``async_job=True`` marks a tool that STARTS a background job (queued; not done
    when the call returns) — the durable async-honesty signal a consumer (the
    workflow step-runner) reads from the catalog instead of guessing from the name.

    ``paid=True`` marks a tool whose call SPENDS REAL MONEY (Track D CD1). It is
    ORTHOGONAL to ``tier``: spend governs money, tier governs mutation. A paid READ
    (e.g. web search) stays tier ``R`` and remains callable in ``ask`` mode, but must
    clear a SPEND gate — never a write gate. Do not coerce a tool to ``A``/``W``
    merely because it costs money.

    ``visibility="legacy"`` DEPRECATES the tool (CAT-4, mirrors the Go kit's
    ``WithVisibility``): it stays registered + callable, but is EXCLUDED from the
    agent's discoverable set on both federation surfaces (``tool_discovery.py`` +
    ``find-tools.ts``). Pair it with ``superseded_by=<tool>`` — the tool that REPLACES
    this one — so ``tool_list``/``tool_load`` label it and an agent migrates itself.
    Use when a tool duplicates another (e.g. a thin cross-service proxy over the
    canonical owner): deprecate, never delete.
    """
    meta: dict[str, Any] = {"tier": tier, "scope": scope}
    if undo_hint is not None:
        meta["undo_hint"] = undo_hint
    if synonyms is not None:
        meta["synonyms"] = synonyms
    if async_job:
        meta["async"] = True
    if paid:
        meta["paid"] = True
    if visibility is not None:
        meta["visibility"] = visibility
    if superseded_by is not None:
        meta["superseded_by"] = superseded_by
    validate_tool_meta(meta, tool_name=tool_name)
    return meta
