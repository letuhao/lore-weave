"""Canonical entity name + deterministic ID derivation (Phase 4b-α).

Pure functions, no I/O. Moved from knowledge-service's
`app/db/neo4j_repos/canonical.py` + `relations.py` so the 4 extractors
+ pass2 orchestrator can derive the same canonical_id / relation_id
without depending on knowledge-service internals.

The Neo4j `merge_entity` / `create_relation` functions remain in the
service-side repo modules; only the pure ID derivation helpers move.

Re-running an extraction on the same source produces the exact same
node ID — that is the property that makes every write idempotent.
"""

from __future__ import annotations

import hashlib
import re

__all__ = [
    "HONORIFICS",
    "canonicalize_entity_name",
    "canonicalize_text",
    "entity_canonical_id",
    "relation_id",
]

# Honorifics stripped from both ends of the name before hashing.
# The trailing/leading space matters: "master kai" → strip "master "
# → "kai", but "mastermind" stays.
#
# **Tuple, not set** — set/frozenset iteration order is hash-
# randomized between interpreter runs, which would make canonical_id
# non-deterministic across process restarts. A tuple pins iteration
# order so the same input always produces the same id, forever.
# Order is longest-first as a defensive measure: if two honorifics
# ever overlap (e.g., a future "captain general " vs "captain "),
# the longer one strips first and the result is stable.
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


def canonicalize_text(text: str) -> str:
    """Generic text normalizer for events and facts.

    Lowercase + strip outer whitespace + collapse internal whitespace
    runs + strip punctuation (apostrophes preserved). Does NOT strip
    honorifics — those are entity-specific. Used to derive
    deterministic ids for events and facts so the same description
    re-extracted from the same chapter collapses to one node.

    Steps mirror `canonicalize_entity_name` minus the honorific pass;
    if you change one, change the other or factor out the shared
    core. Kept intentionally separate so an entity name rule change
    doesn't silently re-key every event in the graph.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    normalized = text.strip().lower()
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


def relation_id(
    user_id: str,
    subject_id: str,
    predicate: str,
    object_id: str,
) -> str:
    """Deterministic id for a `(:Entity)-[:RELATES_TO]->(:Entity)` edge.

    Same `(user_id, subject_id, predicate, object_id)` tuple produces
    the same id, forever. The id is the structural key for the MERGE
    in `create_relation`, which makes re-extracting the same SVO from
    any source a no-op (the second create just appends the new
    source_event_id to the existing edge).

    The id encodes `user_id` so two users with the same SVO pattern
    get distinct ids — defensive even though the matched
    subject/object nodes are themselves user-scoped via the
    canonical_id.

    Returns a 32-char hex (truncated SHA-256). Same shape as
    `entity_canonical_id`, same collision properties.
    """
    if not user_id:
        raise ValueError("user_id is required for relation_id")
    if not subject_id:
        raise ValueError("subject_id is required for relation_id")
    if not predicate:
        raise ValueError("predicate is required for relation_id")
    if not object_id:
        raise ValueError("object_id is required for relation_id")
    key = f"v1:{user_id}:{subject_id}:{predicate}:{object_id}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
