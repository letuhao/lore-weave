"""P2 — deterministic task ID computation.

Spec: docs/specs/2026-05-23-p2-parallel-map-checkpoint.md §D2.

task_id = sha256(normalized_text + op + extractor_version + model_ref)

Properties:
  - Same content + op + prompts + model -> same hash -> P2 cache hit.
  - Prompt template change -> extractor_version bumps -> hash changes
    -> implicit invalidation via cache miss.
  - Different LLM model (qwen3.6 vs gemma-4) -> different hash ->
    no cross-model cache poisoning (SR-2).
  - scenes.parse_version is INTENTIONALLY NOT IN THE HASH (SR-4):
    explicit DELETE via D5 endpoint.
"""

from __future__ import annotations

import hashlib

# UTF-8 unit separator — guaranteed not to appear in any UTF-8 text field.
_SEP = "\x1f"


def compute_task_id(
    normalized_text: str,
    op: str,
    extractor_version: str,
    model_ref: str,
) -> str:
    """Return the deterministic per-leaf-per-op-per-model task ID hash.

    M2 normalization:
      - op.lower() (defensive — caller variance)
      - model_ref.lower() (UUID strings may arrive in either case
        from different serializers; case-sensitive hash would
        silently cache-miss for what should be a hit)
      - normalized_text: caller must pre-normalize via the SDK's
        canonicalize_text (NFC + collapse-ws + lower).
      - extractor_version: as-is (SDK constant, already canonical
        format "v1-<8hex>")
    """
    payload = (
        f"{normalized_text}{_SEP}{op.lower()}{_SEP}{extractor_version}{_SEP}{model_ref.lower()}"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = ["compute_task_id"]
