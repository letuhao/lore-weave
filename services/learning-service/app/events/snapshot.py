"""Privacy split for correction snapshots (design §3, R2 redact-by-default).

The emitter sends a FULL before/after snapshot on the wire; the consumer splits
it here into a STRUCTURAL part (controlled-vocab / non-content — stored raw) and
a CONTENT hash (novel-derived text — hashed only, raw discarded in Phase B).
Raw content is NOT returned by this module; persisting it is a Phase-E
per-tenant opt-in (D#050).

Per-target_type field classification:
  entity   : structural {kind}                                   content {name, aliases, short_description}
  relation : structural {subject_id, object_id, predicate,
                         confidence, valid_until}                 content {} (endpoint ids are structural)
  event    : structural {event_date_iso}                         content {title, summary, time_cue, participants}
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# field_name -> True if CONTENT (hash), absent/False if STRUCTURAL (store raw)
_CLASSIFICATION: dict[str, dict[str, str]] = {
    "entity": {
        "kind": "structural",
        "name": "content",
        "aliases": "content",
        "short_description": "content",
    },
    "relation": {
        "subject_id": "structural",
        "object_id": "structural",
        "predicate": "structural",
        "confidence": "structural",
        "valid_until": "structural",
    },
    "event": {
        "event_date_iso": "structural",
        "title": "content",
        "summary": "content",
        "time_cue": "content",
        "participants": "content",
    },
}


def _stable_hash(content: dict[str, Any]) -> str:
    """Deterministic SHA-256 over the content sub-dict. Uses hashlib (NOT
    Python's PYTHONHASHSEED-randomised hash()) with sorted keys so the hash is
    stable across processes/workers."""
    blob = json.dumps(content, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8"), usedforsecurity=False).hexdigest()


def split_snapshot(
    target_type: str, snapshot: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Split a full snapshot into (structural_dict, content_hash).

    A `None` snapshot (whole-absent: create→before, delete→after) returns
    (None, None). A snapshot with no content fields (e.g. relations) returns
    (structural, None). Unknown fields default to STRUCTURAL (safe: they are
    stored raw, never silently hashed away — but an unrecognised field that is
    actually content would be a classification bug to catch in review)."""
    if snapshot is None:
        return None, None

    classes = _CLASSIFICATION.get(target_type, {})
    structural: dict[str, Any] = {}
    content: dict[str, Any] = {}
    for key, value in snapshot.items():
        if classes.get(key) == "content":
            content[key] = value
        else:
            structural[key] = value

    content_hash = _stable_hash(content) if content else None
    return (structural or None), content_hash
