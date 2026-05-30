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
from loreweave_extraction._version import (
    __extractor_version__,
    get_extractor_version,
)
from loreweave_extraction.context_budget import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MODEL_CONTEXT,
    ContextBudget,
    Language,
    estimate_paragraph_count,
    estimate_text_tokens,
)
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
from loreweave_extraction.extractors.summarize import (
    LevelSummary,
    summarize_level,
)
from loreweave_extraction.pass2 import FilterStatus, Pass2Candidates, extract_pass2
from loreweave_extraction.pass2_filter import (
    FilterDecision,
    PrecisionFilterConfig,
    apply_precision_filter,
    load_candidates_from_dump,
)
from loreweave_extraction.entity_recovery import (
    EntityRecoveryConfig,
    RecoveryDecision,
    recover_missing_entities,
)
from loreweave_extraction.filter_config_store import (
    FILTER_CONFIG_REDIS_KEY,
    FILTER_RELOAD_PUBSUB_CHANNEL,
    WIRE_SCHEMA_VERSION,
    delete_filter_config,
    get_filter_config,
    set_filter_config,
    subscribe_filter_reload,
)
from loreweave_extraction.extractors.precision_filter_prompts import (
    NO_THINK_PREFIX,
    build_precision_prompt,
    precision_prompt_body,
)

__all__ = [
    # Orchestration
    "Pass2Candidates",
    "FilterStatus",
    "extract_pass2",
    # Cycle 72 — Pass2 precision filter
    "apply_precision_filter",
    "PrecisionFilterConfig",
    "FilterDecision",
    "load_candidates_from_dump",
    "build_precision_prompt",
    "precision_prompt_body",
    "NO_THINK_PREFIX",
    # Cycle 73d — entity recovery (3-tier glossary/hints/LLM)
    "recover_missing_entities",
    "EntityRecoveryConfig",
    "RecoveryDecision",
    # Cycle 73f — runtime filter config store (Redis-backed)
    "FILTER_CONFIG_REDIS_KEY",
    "FILTER_RELOAD_PUBSUB_CHANNEL",
    "WIRE_SCHEMA_VERSION",
    "get_filter_config",
    "set_filter_config",
    "delete_filter_config",
    "subscribe_filter_reload",
    # Per-op extractors
    "extract_entities",
    "extract_relations",
    "extract_events",
    "extract_facts",
    "summarize_level",
    "LevelSummary",
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
    # P2 — extractor version (sha256 of prompts/*.md)
    "__extractor_version__",
    "get_extractor_version",
    # Model-context-aware chunking + concurrency
    "ContextBudget",
    "Language",
    "estimate_text_tokens",
    "estimate_paragraph_count",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DEFAULT_MODEL_CONTEXT",
]
