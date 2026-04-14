"""K11.5 — canonical entity name + deterministic ID.

Pure functions, no I/O. Lives at the repo layer so K11.6 (relations),
K11.7 (events + facts), K15 (pattern extractor), and K17 (LLM
extractor) can all derive the same canonical_id from the same
display name. Re-running an extraction on the same source produces
the exact same node ID — that is the property that makes every
write idempotent.

Reference: KSA §5.0 (entity resolution algorithm), 101 §3.5.4
(idempotency layer).
"""

from __future__ import annotations

import hashlib
import re

__all__ = [
    "HONORIFICS",
    "canonicalize_entity_name",
    "entity_canonical_id",
]

# Honorifics stripped from both ends of the name before hashing.
# KSA §5.0 maintains this list. The trailing/leading space matters:
# "master kai" → strip "master " → "kai", but "mastermind" stays.
#
# **Tuple, not set** — set/frozenset iteration order is hash-
# randomized between interpreter runs, which would make
# canonical_id non-deterministic across process restarts. A tuple
# pins iteration order so the same input always produces the same
# id, forever. Order is longest-first as a defensive measure: if
# two honorifics ever overlap (e.g., a future "captain general "
# vs "captain "), the longer one strips first and the result is
# stable.
HONORIFICS: tuple[str, ...] = tuple(
    sorted(
        (
            "master ",
            "lord ",
            "lady ",
            "sir ",
            "dame ",
            "mr. ",
            "mrs. ",
            "ms. ",
            "dr. ",
            "prof. ",
            "captain ",
            "commander ",
            "general ",
            "shifu ",
            "sensei ",
            # Suffix forms (Japanese/Chinese honorifics)
            "-shifu",
            "-sensei",
            "-sama",
            "-san",
            "-kun",
        ),
        key=lambda h: (-len(h), h),
    )
)

_WHITESPACE_RE = re.compile(r"\s+")
# Strip everything that's not a word char, whitespace, or apostrophe
# (apostrophes preserved for names like O'Neill).
_PUNCTUATION_RE = re.compile(r"[^\w\s']")


def canonicalize_entity_name(name: str) -> str:
    """Normalize an entity name for deduplication matching.

    Steps (must stay in this order — changing the order changes
    every canonical_id in the database, requiring a migration):

      1. Lowercase + strip outer whitespace.
      2. Strip honorifics from prefix and suffix (one pass — we
         don't recurse; "master lord kai" stays "lord kai").
      3. Collapse internal whitespace runs to single spaces.
      4. Strip punctuation except apostrophes.
      5. Strip resulting outer whitespace.

    The original display name is preserved by the caller in
    `Entity.name`; this canonical form is only used for ID hashing
    and for the `canonical_name` index property.
    """
    if not isinstance(name, str):
        raise TypeError(f"name must be str, got {type(name).__name__}")
    normalized = name.strip().lower()

    for h in HONORIFICS:
        if normalized.startswith(h):
            normalized = normalized[len(h):]
        if normalized.endswith(h):
            normalized = normalized[: -len(h)]

    normalized = _WHITESPACE_RE.sub(" ", normalized)
    normalized = _PUNCTUATION_RE.sub("", normalized)
    return normalized.strip()


def entity_canonical_id(
    user_id: str,
    project_id: str | None,
    name: str,
    kind: str,
    canonical_version: int = 1,
) -> str:
    """Deterministic ID for an entity — same canonical name + kind = same node.

    Scoped by `user_id` + `project_id` for multi-tenant isolation.
    Same display name in two different users' projects produces two
    different IDs, never colliding.

    The `canonical_version` suffix lets us migrate every entity ID
    when canonicalization rules change (e.g., adding a honorific).
    Bumping it forces a re-canonicalization pass.

    Returns a 32-char hex string (truncated SHA-256). 32 hex chars
    = 128 bits of entropy = collision-free at any conceivable scale
    for a single user × project namespace.
    """
    if not user_id:
        raise ValueError("user_id is required for canonical_id")
    if not name:
        raise ValueError("name is required for canonical_id")
    if not kind:
        raise ValueError("kind is required for canonical_id")
    canonical = canonicalize_entity_name(name)
    if not canonical:
        raise ValueError(
            f"name {name!r} canonicalizes to empty string — cannot derive id"
        )
    key = f"v{canonical_version}:{user_id}:{project_id or 'global'}:{kind}:{canonical}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
