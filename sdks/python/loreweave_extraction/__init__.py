"""LoreWeave Pass 2 extraction library.

Pure Python — no Neo4j, no Postgres, no service-specific state.
Extracts entities / relations / events / facts from text via the
loreweave_llm SDK and returns post-processed candidate models.
Persistence is the caller's responsibility.

Top-level exports:
- ``extract_pass2`` — high-level orchestrator (entities → gate →
  parallel R/E/F)
- ``Pass2Candidates`` — return type
- 4 per-op extractors for callers needing finer control
- ``ExtractionError`` + ``ExtractionStage`` for error handling
- Canonical ID derivation (``canonicalize_entity_name``,
  ``entity_canonical_id``, ``relation_id``, ``HONORIFICS``)
- ``LLMClientProtocol`` + ``DroppedHandler`` for typing
"""

from loreweave_extraction._types import DroppedHandler, LLMClientProtocol
from loreweave_extraction.canonical import (
    HONORIFICS,
    canonicalize_entity_name,
    canonicalize_text,
    entity_canonical_id,
    relation_id,
)
from loreweave_extraction.errors import ExtractionError, ExtractionStage
from loreweave_extraction.extractors.entity import (
    EntityExtractionResponse,
    LLMEntityCandidate,
    extract_entities,
)
from loreweave_extraction.extractors.event import (
    EventExtractionResponse,
    LLMEventCandidate,
    extract_events,
)
from loreweave_extraction.extractors.fact import (
    FactExtractionResponse,
    LLMFactCandidate,
    extract_facts,
)
from loreweave_extraction.extractors.relation import (
    LLMRelationCandidate,
    RelationExtractionResponse,
    extract_relations,
)
from loreweave_extraction.pass2 import Pass2Candidates, extract_pass2

__all__ = [
    # Orchestration
    "Pass2Candidates",
    "extract_pass2",
    # Per-op extractors
    "extract_entities",
    "extract_relations",
    "extract_events",
    "extract_facts",
    # Candidate models
    "LLMEntityCandidate",
    "LLMRelationCandidate",
    "LLMEventCandidate",
    "LLMFactCandidate",
    # LLM-response wrapper models (for tests / introspection)
    "EntityExtractionResponse",
    "RelationExtractionResponse",
    "EventExtractionResponse",
    "FactExtractionResponse",
    # Errors
    "ExtractionError",
    "ExtractionStage",
    # Canonical ID derivation
    "HONORIFICS",
    "canonicalize_entity_name",
    "canonicalize_text",
    "entity_canonical_id",
    "relation_id",
    # Typing
    "LLMClientProtocol",
    "DroppedHandler",
]
