"""Per-operation Pass 2 extractors. Each module exposes one async
function (`extract_entities`, `extract_relations`, `extract_events`,
`extract_facts`) that takes an `LLMClientProtocol`, calls the
matching gateway operation with chunking + system+user message
structure, and returns the post-processed candidate list.

Use `loreweave_extraction.extract_pass2(...)` if you want all four
in one orchestrated call; reach for the per-op functions only when
you need finer control."""

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

__all__ = [
    "EntityExtractionResponse",
    "EventExtractionResponse",
    "FactExtractionResponse",
    "LLMEntityCandidate",
    "LLMEventCandidate",
    "LLMFactCandidate",
    "LLMRelationCandidate",
    "RelationExtractionResponse",
    "extract_entities",
    "extract_events",
    "extract_facts",
    "extract_relations",
]
