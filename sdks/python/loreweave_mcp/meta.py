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

    ncf = meta.get("no_context_fill")
    if ncf is not None and not (
        isinstance(ncf, (list, tuple)) and all(isinstance(a, str) for a in ncf)
    ):
        raise MetaValidationError(
            f"_meta.no_context_fill{label} must be a list of argument names"
        )

    xa = meta.get("exclusive_args")
    if xa is not None and not (
        isinstance(xa, (list, tuple))
        and all(isinstance(g, (list, tuple)) and len(g) >= 2
                and all(isinstance(a, str) for a in g) for g in xa)
    ):
        raise MetaValidationError(
            f"_meta.exclusive_args{label} must be a list of groups, each two or more "
            "argument names"
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
    ambient_book: bool = False,
    ambient_project: bool = False,
    no_context_fill: list[str] | None = None,
    exclusive_args: list[list[str]] | None = None,
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

    ``no_context_fill=["book_id"]`` names arguments a consumer must NOT backfill from
    session context. A backfiller (chat-service's ``_inject_context_ids``) helpfully
    supplies a known id the model omitted, which is right for almost every tool and wrong
    for two measured shapes:

      * the argument SELECTS A CODE PATH rather than a scope —
        ``composition_motif_link_edit``'s ``book_id`` switches it from "link two motifs you
        own" to "link two motifs shared into that book". The runtime filled the omitted id,
        the tool refused, its refusal said to call again WITHOUT it, and the runtime put it
        back, so the remedy could never be followed.
      * the ambient value is the WRONG OBJECT —
        ``composition_entity_override_edit`` needs the DERIVATIVE Work's ``project_id``, and
        a book's ambient project is its CANONICAL Work. Filling it hands the model an id
        that is refused by definition, before it can look the right one up.

    Both reduce to one rule: AN ARGUMENT THE RUNTIME MAY SUPPLY MUST BE ONE THE CALLER COULD
    ALSO HAVE SUPPLIED AND MEANT. Renamed from ``mode_selecting_args`` on 2026-08-24, which
    named only the first reason.

    ``exclusive_args=[["book_id", "project_id"]]`` names argument groups of which the tool
    accepts EXACTLY ONE. A backfiller must not COMPLETE such a group: if any member is
    already present, the others stay absent.

    🔴 MEASURED 2026-09-01, and it refuted a wording fix. ``composition_list_derivatives``
    takes exactly one of ``book_id``/``project_id``, and a book turn in the studio carries
    BOTH — so ``_inject_context_ids`` filled both and the tool refused "give EXACTLY ONE".
    Live K=5: 24 of 24 calls carried both and every one was refused; store-wide, that shape
    is 0 done in 46 attempts. The turn before this was spent rewriting the refusal to say
    "call it with NO ARGUMENTS", which changed nothing, BECAUSE AN OBEDIENT MODEL GETS THE
    SAME SHAPE: with no arguments the runtime supplies both. No wording can fix a shape the
    runtime constructs after the model has spoken.

    The rule this states is the converse of ``no_context_fill``'s: that one says an argument
    may be MEANINGFUL BY ITS ABSENCE, this one says a COMBINATION may be invalid. They are
    separate because a tool can want one and not the other — ``composition_generate`` is
    exclusive over ``outline_node_id``/``chapter_id`` while wanting its ids filled normally.

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
    # Studio context binding (spec 2026-07-22) — the tool resolves its book_id / project_id
    # from the envelope (X-Book-Id / X-Project-Id) when the model omits it (resolve_book_scope /
    # resolve_project_scope). The chat-service surface builder reads these to drop the id from
    # `required`; only set on a tool that ACTUALLY resolves it (migration atomicity).
    # Arguments a consumer must NOT backfill from session context. See below for the two
    # measured reasons; both reduce to the same rule — an argument the runtime may supply must
    # be one the caller could also have supplied and MEANT.
    if no_context_fill:
        meta["no_context_fill"] = list(no_context_fill)
    # Groups of which the tool accepts EXACTLY ONE. A backfiller must not complete one.
    if exclusive_args:
        meta["exclusive_args"] = [list(g) for g in exclusive_args]
    if ambient_book:
        meta["ambient_book"] = True
    if ambient_project:
        meta["ambient_project"] = True
    if visibility is not None:
        meta["visibility"] = visibility
    if superseded_by is not None:
        meta["superseded_by"] = superseded_by
    validate_tool_meta(meta, tool_name=tool_name)
    return meta
