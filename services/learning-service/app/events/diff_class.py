"""diff_class derivation — design §3.

Pure function over the privacy-split snapshot (structural fields + content
hashes). Evaluated top-to-bottom; `op` is authoritative and checked FIRST
(F6) so a merge whose merged-away side has an absent `after` is not mis-classed
as `spurious-drop`, and a rename+rekind resolves to `kind-change` (higher signal)
rather than dropping the rename. Works WITHOUT raw content (R2 redact).
"""

from __future__ import annotations

from typing import Any

_MERGE_OPS = {"merge", "split"}


def _absent(structural: Any, content_hash: Any) -> bool:
    """A whole-snapshot is absent when both its structural payload and its
    content hash are None (create → before absent; delete → after absent)."""
    return structural is None and content_hash is None


def derive_diff_class(
    *,
    target_type: str,
    op: str,
    before_structural: dict[str, Any] | None,
    after_structural: dict[str, Any] | None,
    before_content_hash: str | None,
    after_content_hash: str | None,
) -> str:
    # 1 — op is authoritative for merge/split
    if op in _MERGE_OPS:
        return "merge"

    # 2 — predicate fix (relations)
    if op == "predicate_fix":
        return "predicate-fix"
    if target_type == "relation" and before_structural and after_structural:
        if before_structural.get("predicate") != after_structural.get("predicate"):
            return "predicate-fix"

    # 3 — missing-add: nothing before, something after
    before_absent = _absent(before_structural, before_content_hash)
    after_absent = _absent(after_structural, after_content_hash)
    if before_absent and not after_absent:
        return "missing-add"

    # 4 — spurious-drop: something before, nothing after (delete/invalidate)
    if after_absent and not before_absent:
        return "spurious-drop"

    # 5 — kind-change (entities only): structural kind differs
    if target_type == "entity" and before_structural and after_structural:
        if before_structural.get("kind") != after_structural.get("kind"):
            return "kind-change"

    # 6 — boundary (entities only): kind equal, content (name/aliases) changed
    if (
        target_type == "entity"
        and before_content_hash is not None
        and after_content_hash is not None
        and before_content_hash != after_content_hash
    ):
        return "boundary"

    return "other"
