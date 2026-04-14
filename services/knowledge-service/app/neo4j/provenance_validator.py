"""K11.Z — Provenance write validator (L-CH-06).

Pure function: every Neo4j write that carries provenance goes through
`validate_provenance` before reaching the driver. Encodes ContextHub
lesson L-CH-06: their git-intelligence wrote the literal string
"[object Object]" into source_refs and nobody noticed because no query
ever filtered on that field. Provenance is write-heavy, read-rare — so
bad data hides forever unless caught at write time.

Scope (Track 1 laptop-friendly slice):
  - Pure validator, no I/O, no driver calls, no DB lookups.
  - Raises `ProvenanceValidationError` with `field` + `value` + `reason`
    so the caller can log to `extraction_errors` (K10.2, pending).

Deferred to follow-up tasks when K11.1 / K10.2 land:
  - Wrapping `writer.py` so every `session.run(...)` goes through here.
  - Cross-checking `chapter_id` / `chunk_id` / `book_id` against Postgres.
  - Emitting `provenance_validation_failed` metric counter.

Budget: < 0.5ms per edge. Pre-compiled regex + frozenset lookups only.
"""

from __future__ import annotations

import math
import re
from datetime import datetime

__all__ = ["ProvenanceValidationError", "validate_provenance"]


# Literal sentinel strings that JS/Python serializers produce when
# they stringify the wrong thing. All case-insensitive.
_BAD_STRING_SENTINELS = frozenset(
    s.lower()
    for s in (
        "[object Object]",
        "undefined",
        "null",
        "None",
        "NaN",
    )
)

# Python repr leak: "<module.Class object at 0x7f...>". Matches the
# exact shape so we don't reject legitimate angle-bracketed content.
_PYTHON_REPR_RE = re.compile(r"^<[\w.]+ object at 0x[0-9a-fA-F]+>$")

# Fields we treat as provenance. If a writer passes one of these with
# bad content, it almost always means the extractor handed us garbage.
_STRING_FIELDS = frozenset(
    (
        "chapter_id",
        "chunk_id",
        "book_id",
        "extractor_version",
        "trace_id",
    )
)

# Fields that are collections of strings (source_refs is plural, e.g.
# list of chunk ids that support one edge).
_STRING_LIST_FIELDS = frozenset(("source_refs",))


class ProvenanceValidationError(Exception):
    """Raised when a provenance field fails validation.

    `field` and `value` are preserved so the caller can write a row to
    `extraction_errors` (K10.2) with enough context to debug the
    offending extractor run without replaying the whole job.
    """

    def __init__(self, field: str, value: object, reason: str) -> None:
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(f"provenance[{field}]={value!r}: {reason}")


def _check_string(field: str, value: object) -> None:
    if value is None:
        raise ProvenanceValidationError(field, value, "is None")
    if not isinstance(value, str):
        raise ProvenanceValidationError(field, value, "is not a string")
    stripped = value.strip()
    if not stripped:
        raise ProvenanceValidationError(field, value, "empty or whitespace-only")
    if stripped.lower() in _BAD_STRING_SENTINELS:
        raise ProvenanceValidationError(field, value, "serializer sentinel")
    if _PYTHON_REPR_RE.match(stripped):
        raise ProvenanceValidationError(field, value, "python repr leak")


def _check_confidence(value: object) -> None:
    if value is None:
        raise ProvenanceValidationError("confidence", value, "is None")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProvenanceValidationError("confidence", value, "not a number")
    if not math.isfinite(value):
        # Covers NaN, +inf, -inf with a clearer reason than "outside [0,1]"
        # — reason matters for the extraction_errors row (K10.2).
        raise ProvenanceValidationError("confidence", value, "non-finite")
    if not (0.0 <= float(value) <= 1.0):
        raise ProvenanceValidationError("confidence", value, "outside [0, 1]")


def _check_timestamp(field: str, value: object) -> None:
    if value is None:
        raise ProvenanceValidationError(field, value, "is None")
    if isinstance(value, datetime):
        return
    if not isinstance(value, str):
        raise ProvenanceValidationError(field, value, "not a datetime or ISO string")
    try:
        # fromisoformat in 3.11+ accepts the trailing "Z".
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProvenanceValidationError(field, value, f"invalid ISO-8601: {exc}") from None


def validate_provenance(props: dict) -> None:
    """Validate a provenance-bearing property bag.

    Intended call site: immediately before `session.run(...)` inside the
    knowledge-service Neo4j writer. `props` is the dict that the writer
    would pass to Cypher as `$props`.

    Raises `ProvenanceValidationError` on the FIRST offending field.
    The caller is responsible for rolling back the current event and
    logging to `extraction_errors`.
    """
    if not isinstance(props, dict):
        raise ProvenanceValidationError("<root>", props, "props is not a dict")

    for field, value in props.items():
        if field in _STRING_FIELDS:
            _check_string(field, value)
        elif field in _STRING_LIST_FIELDS:
            if not isinstance(value, (list, tuple)):
                raise ProvenanceValidationError(field, value, "not a list")
            if not value:
                raise ProvenanceValidationError(field, value, "empty list")
            for i, item in enumerate(value):
                try:
                    _check_string(field, item)
                except ProvenanceValidationError as exc:
                    raise ProvenanceValidationError(
                        f"{field}[{i}]", item, exc.reason
                    ) from None
        elif field == "confidence":
            _check_confidence(value)
        elif field in ("extracted_at", "created_at", "updated_at"):
            _check_timestamp(field, value)
        # Unknown fields pass through — validator is a deny-list for
        # known-bad patterns, not a whitelist schema. K11.1 will own
        # the schema contract.
