"""The fact-type VOCABULARY — what a producer may say, not where it is stored (T17 A6).

These are two producers' vocabularies: the memory extractor's and the story extractor's
(`loreweave_extraction.extractors.fact.FactType`). Neither is a property of a graph engine,
and `tools/definitions.py` — which builds MCP tool schemas and touches no Cypher — was
counted as bound to `graph_repos` solely for reading `MEMORY_FACT_TYPES` out of it.

They are re-exported from `db/graph_repos/facts.py`, so every existing importer keeps working
and there is still exactly ONE definition of each.
"""
from __future__ import annotations

from typing import Literal, get_args

__all__ = ["MemoryFactType", "StoryFactType", "FactType",
           "MEMORY_FACT_TYPES", "STORY_FACT_TYPES", "FACT_TYPES"]


MemoryFactType = Literal[
    "decision", "preference", "milestone", "negation", "statement", "commitment",
]
# The story extractor's vocabulary — `loreweave_extraction.extractors.fact.FactType`, i.e.
# what the LLM is actually prompted to produce. `negation` lives in the memory tuple above
# and is shared, not duplicated here.
StoryFactType = Literal["description", "attribute", "temporal", "causal"]

FactType = MemoryFactType | StoryFactType

# DERIVE the runtime validation tuples from the Literals — never hand-maintain a parallel
# copy. WS-2.1 added 'statement' to the Literal but a hand-kept tuple missed it, so a
# statement fact queued fine yet 500'd at merge_fact (caught by the WS-2.4 live smoke).
# `get_args` on the UNION returns the two Literal types rather than their members, so the
# tuples are concatenated instead — same discipline, one indirection less.
MEMORY_FACT_TYPES: tuple[str, ...] = get_args(MemoryFactType)
STORY_FACT_TYPES: tuple[str, ...] = get_args(StoryFactType)
FACT_TYPES: tuple[str, ...] = MEMORY_FACT_TYPES + STORY_FACT_TYPES
