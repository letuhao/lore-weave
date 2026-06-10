"""Privacy split for correction snapshots (design §3, R2 redact-by-default).

The emitter sends a FULL before/after snapshot on the wire; the consumer splits
it here into a STRUCTURAL part (controlled-vocab / non-content — stored raw) and
a CONTENT hash (novel-derived text — hashed only, raw discarded in Phase B).
Raw content is NOT returned by this module; persisting it is a Phase-E
per-tenant opt-in (D#050).

Per-target_type field classification:
  entity   : structural {kind}   content {name, aliases}   description {short_description}
  relation : structural {subject_id, object_id, predicate,
                         confidence, valid_until}                 content {} (endpoint ids are structural)
  event    : structural {event_date_iso}                         content {title, summary, time_cue, participants}

FD-19/052 — `short_description` is hashed SEPARATELY from name/aliases (its own
`description_hash`), NOT folded into `content_hash`. So the diff classifier's
`boundary` class (content_hash delta) fires only on a name/alias rename, and a
description-only edit leaves content_hash stable → classed `other` (the
description change is still recorded via description_hash, privacy-preserving —
raw text is never stored). A `None` description_hash means "no description field
for this target_type" (relations/events/translations).
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
        # FD-19/052 — hashed SEPARATELY (description_hash), not folded into the
        # name/alias content_hash, so a description-only edit isn't mis-classed
        # as a `boundary` (rename) signal.
        "short_description": "description",
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
    # M7c: a human-edited translation. Language/version are structural; the
    # translated body is content (hashed here; the translation handler ALSO stores
    # the raw before/after body per the PO raw-text choice).
    "translation": {
        "target_language": "structural",
        "version_num": "structural",
        "body": "content",
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
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Split a full snapshot into (structural_dict, content_hash, description_hash).

    A `None` snapshot (whole-absent: create→before, delete→after) returns
    (None, None, None). `content_hash` covers name/alias-class fields;
    `description_hash` covers the separately-hashed `description`-class fields
    (entity short_description today — None for every other target_type). A
    snapshot with no fields of a class returns None for that hash. Unknown
    fields default to STRUCTURAL (safe: stored raw, never silently hashed away —
    an unrecognised field that is actually content would be a classification bug
    to catch in review)."""
    if snapshot is None:
        return None, None, None

    classes = _CLASSIFICATION.get(target_type, {})
    structural: dict[str, Any] = {}
    content: dict[str, Any] = {}
    description: dict[str, Any] = {}
    for key, value in snapshot.items():
        cls = classes.get(key)
        if cls == "content":
            content[key] = value
        elif cls == "description":
            description[key] = value
        else:
            structural[key] = value

    content_hash = _stable_hash(content) if content else None
    description_hash = _stable_hash(description) if description else None
    return (structural or None), content_hash, description_hash
