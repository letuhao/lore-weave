"""L1/L2 tool-response contract — reference-first + bounds (Context Budget Law §6b).

The shared, cross-service helper every Python MCP *provider* uses to make a
SET-returning tool honor:

- **L1 reference-first** — at ``detail="summary"`` an item collapses to its
  reference fields only (``id`` + ``title`` + a ≤1-line + ``version``); the full
  body is fetched on demand via the tool's ``get_by_id`` sibling.
- **L2 granularity + bounds** — a ``detail`` level (``summary`` | ``full``),
  optional ``fields`` allow-list, and a mandatory ``limit`` (hard count cap).

**Versioned-default migration (spec §6b/D2):** ``detail`` defaults to ``"full"``
so federated/legacy callers are unchanged; the chat-compiler passes
``detail="summary"``. Flip the global default only after consumers migrate.

**Never a silent truncation (§6a cross-cutting):** the returned ``meta`` always
reports ``total``/``returned``/``truncated`` so the model sees how much was
withheld and can narrow or paginate — a cap is surfaced, never hidden.

The helper is model-shape-agnostic: it operates on already-serialized ``dict``
items (post ``model_dump(mode="json")``), so it composes with any repo row.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal

DetailLevel = Literal["summary", "full"]

__all__ = ["DetailLevel", "apply_response_contract"]


def apply_response_contract(
    items: list[dict[str, Any]],
    *,
    ref_fields: Iterable[str],
    detail: DetailLevel = "full",
    limit: int | None = None,
    fields: Iterable[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Project a SET result through the L1/L2 contract.

    Args:
        items: the full serialized rows (dicts).
        ref_fields: the reference-first field set kept at ``detail="summary"``
            (the ``get_by_id`` sibling returns everything else).
        detail: ``"summary"`` → refs only; ``"full"`` → rows unchanged.
        limit: hard count cap (``None`` = no cap). Applied to BOTH detail levels.
        fields: optional caller allow-list intersected on top of the detail
            projection (L2 ``fields``). ``None`` = no extra filtering.

    Returns:
        ``(projected_items, meta)`` where ``meta`` =
        ``{detail, total, returned, truncated}``. ``truncated`` > 0 means the
        limit dropped rows — the model must narrow/paginate to see them.
    """
    total = len(items)
    capped = items[: limit] if limit is not None else items

    if detail == "summary":
        keep = tuple(ref_fields)
        projected = [{k: it[k] for k in keep if k in it} for it in capped]
    else:
        projected = [dict(it) for it in capped]

    if fields is not None:
        allow = set(fields)
        projected = [{k: v for k, v in it.items() if k in allow} for it in projected]

    meta = {
        "detail": detail,
        "total": total,
        "returned": len(projected),
        "truncated": total - len(projected),
    }
    return projected, meta
