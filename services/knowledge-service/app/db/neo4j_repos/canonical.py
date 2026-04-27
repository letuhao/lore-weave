"""K11.5 — canonical entity name + deterministic ID.

Phase 4b-α: the actual implementation moved to
`loreweave_extraction.canonical`. This module re-exports for
back-compat with non-extraction call sites (entity_alias_map repo,
anchor_loader, glossary_sync, etc.) that already imported from this
path. New code should import from the library directly.
"""

from __future__ import annotations

from loreweave_extraction.canonical import (
    HONORIFICS,
    canonicalize_entity_name,
    canonicalize_text,
    entity_canonical_id,
)

__all__ = [
    "HONORIFICS",
    "canonicalize_entity_name",
    "canonicalize_text",
    "entity_canonical_id",
]
