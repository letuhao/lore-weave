"""Technique-(b) RETRIEVAL package (RAID C10).

Corpus-grounded enrichment over the OWNED public-domain corpora (山海经 +
封神演义). Three weakly-coupled modules behind shared value types:

  * ``chunker``   — deterministic CJK-aware sentence-window chunker (stdlib only).
  * ``store``     — source_corpus + source_corpus_chunk persistence (idempotent
    ingest) + in-process cosine similarity search (no pgvector, no vector DB).
  * ``embedding`` — the ONE seam that binds the C1 ``KnowledgeClient.embed`` →
    knowledge-service ``/internal/embed`` (provider-registry ``model_ref``,
    NEVER a model name) into the store/strategy embedding callables.
  * ``strategy``  — ``RetrievalStrategy(EnrichmentStrategy)`` (technique=
    retrieval, tier P1): embeds a gap query, retrieves top-K passages, attaches
    them as ``cultural_grounding_ref`` on an H0 ``GroundedProposal``.

Locked: REUSE knowledge-service embed (no new RAG framework, no langchain/
llamaindex, no heavy dep); web/internet search OUT of scope; no hardcoded model
names; H0 — retrieval ONLY attaches grounding to a PROPOSAL (never canon, never
writes glossary/KG).
"""

from app.retrieval.chunker import (
    DEFAULT_OVERLAP_SENTENCES,
    DEFAULT_TARGET_CHARS,
    Chunk,
    chunk_text,
    sha256_text,
)
from app.retrieval.embedding import make_embed_fn, make_embed_query_fn
from app.retrieval.store import (
    IngestResult,
    ScoredChunk,
    SourceCorpusStore,
    StoredChunk,
    cosine_similarity,
    top_k,
)
from app.retrieval.strategy import (
    DEFAULT_TOP_K,
    RETRIEVAL_CONFIDENCE,
    GroundedProposal,
    GroundingRef,
    RetrievalStrategy,
)

__all__ = [
    "Chunk",
    "chunk_text",
    "sha256_text",
    "DEFAULT_TARGET_CHARS",
    "DEFAULT_OVERLAP_SENTENCES",
    "SourceCorpusStore",
    "StoredChunk",
    "ScoredChunk",
    "IngestResult",
    "cosine_similarity",
    "top_k",
    "make_embed_fn",
    "make_embed_query_fn",
    "RetrievalStrategy",
    "GroundedProposal",
    "GroundingRef",
    "RETRIEVAL_CONFIDENCE",
    "DEFAULT_TOP_K",
]
