"""Extractor version derived from prompt file hashes (P2 — D7).

Computed at module import time from sha256 of the concatenated
prompts/*.md files (sorted by filename). Any prompt edit -> hash
changes -> task_id hash changes -> P2 cache miss -> fresh LLM call.

Format: "v1-<8-hex-chars>" — readable enough to debug, short enough
for grep + DB column width.

Spec: docs/specs/2026-05-23-p2-parallel-map-checkpoint.md §D7.

Dev hot-reload caveat (L1 from /review-impl round 1):
  - Production (containerised, no hot reload): version is correct
    and immutable. Each worker-ai container has a baked-in version
    matching its prompt files.
  - Dev with hot-reload: editing a prompt file does NOT recompute
    this constant until the worker-ai process restarts. Set env
    var LOREWEAVE_EXTRACTOR_VERSION_DEV_RECOMPUTE=1 to bypass the
    module-level cache and recompute on every compute_task_id call.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _compute_extractor_version() -> str:
    """Hash all prompts/*.md (sorted by filename) into a short version string.

    Empty prompts dir returns "v1-empty" — unusual but not an error
    (some test fixtures install the package without prompts).
    """
    md_files = sorted(_PROMPTS_DIR.glob("*.md"))
    if not md_files:
        return "v1-empty"
    h = hashlib.sha256()
    for f in md_files:
        # Include filename so a rename (same content) also invalidates.
        h.update(f.name.encode("utf-8"))
        h.update(b"\x1f")
        h.update(f.read_bytes())
    return f"v1-{h.hexdigest()[:8]}"


# Module-level constant — computed once at import. Hashes ALL prompt files.
# Kept for P2 back-compat (existing task_id callers); new code should use
# get_extractor_version(op=...) for per-op invalidation.
__extractor_version__ = _compute_extractor_version()


# P3 M3 fix: per-op extractor versions. Each op's prompt-file set is hashed
# independently so editing one op's prompt only invalidates that op's cache.
_OP_PROMPTS: dict[str, list[str]] = {
    "entity": ["entity_extraction.md", "entity_extraction_system.md"],
    "relation": ["relation_extraction.md", "relation_extraction_system.md"],
    "event": ["event_extraction.md", "event_extraction_system.md"],
    "fact": ["fact_extraction.md", "fact_extraction_system.md"],
    "summarize_level": ["summarize_level_extraction.md"],
}


def _compute_op_extractor_version(op: str) -> str:
    """Hash only the prompt files relevant to a single op."""
    if op not in _OP_PROMPTS:
        raise ValueError(
            f"unknown op {op!r}; allowed: {sorted(_OP_PROMPTS.keys())}"
        )
    files = sorted(_OP_PROMPTS[op])
    h = hashlib.sha256()
    for fname in files:
        path = _PROMPTS_DIR / fname
        h.update(fname.encode("utf-8"))
        h.update(b"\x1f")
        h.update(path.read_bytes() if path.exists() else b"")
    return f"v1-{op}-{h.hexdigest()[:8]}"


def get_extractor_version(op: str | None = None, *, override_text: str | None = None) -> str:
    """Return the extractor version.

    op=None (legacy back-compat): hashes ALL prompts.
    op=<op_name>: hashes ONLY that op's prompt files (P3 M3 fix).
    override_text set (B2 per-novel raw-prompt editing): returns
        ``custom-<sha256(override_text)[:8]>`` — the identity of a
        project's custom prompt for this op, NOT the default file-hash.
        Takes precedence over the file-hash paths so a custom prompt
        invalidates the op's cache + changes the config_hash.

    Honors LOREWEAVE_EXTRACTOR_VERSION_DEV_RECOMPUTE=1 for dev
    hot-reload (recomputes every call).
    """
    if override_text is not None:
        digest = hashlib.sha256(override_text.encode("utf-8")).hexdigest()[:8]
        return f"custom-{digest}"
    dev_recompute = os.environ.get("LOREWEAVE_EXTRACTOR_VERSION_DEV_RECOMPUTE") == "1"
    if op is None:
        # P2 back-compat path; eventually deprecate after P2 migrates.
        if dev_recompute:
            return _compute_extractor_version()
        return __extractor_version__
    if dev_recompute:
        # Op-specific recompute (still respects per-op partitioning).
        return _compute_op_extractor_version(op)
    # In production, cache per-op result. _lru_op_version is itself cached
    # via the module-level dict — single-fetch per op per process.
    if op not in _OP_VERSION_CACHE:
        _OP_VERSION_CACHE[op] = _compute_op_extractor_version(op)
    return _OP_VERSION_CACHE[op]


_OP_VERSION_CACHE: dict[str, str] = {}


__all__ = ["__extractor_version__", "get_extractor_version"]
