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


# Module-level constant — computed once at import.
__extractor_version__ = _compute_extractor_version()


def get_extractor_version() -> str:
    """Return the extractor version.

    Honors LOREWEAVE_EXTRACTOR_VERSION_DEV_RECOMPUTE=1 for dev
    hot-reload (recomputes every call).
    """
    if os.environ.get("LOREWEAVE_EXTRACTOR_VERSION_DEV_RECOMPUTE") == "1":
        return _compute_extractor_version()
    return __extractor_version__


__all__ = ["__extractor_version__", "get_extractor_version"]
