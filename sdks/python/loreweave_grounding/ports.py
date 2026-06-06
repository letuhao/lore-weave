"""Protocols for the grounding port (mui #3).

The verifier and composer are service-agnostic: they consume duck-typed objects
that each service already has (a proposal-like object with a canonical name +
grounding excerpts, fact-like objects with a dimension + content). Defining
these as Protocols means a consumer passes its own domain objects unchanged —
adoption is an import swap, not a data rewrite.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Protocol, Sequence, runtime_checkable


@runtime_checkable
class GroundingItemLike(Protocol):
    """A grounding citation as the verifier needs it: an excerpt + a stable
    locator pair used to name the field in an injection flag."""

    corpus_id: str
    chunk_index: int
    excerpt: str


@runtime_checkable
class FactLike(Protocol):
    """A generated fact: the dimension it fills + the content to verify."""

    dimension: str
    content: str


@runtime_checkable
class ProposalLike(Protocol):
    """The unit verified: a canonical entity name + its grounding citations."""

    canonical_name: str
    grounding: Sequence[GroundingItemLike]


@runtime_checkable
class GroundingReadPort(Protocol):
    """Optional read port a service can implement to feed `compose_cites` — the
    SSOT canon + retrieval passages + chapter locators. Services may instead keep
    their own clients and map results to `GroundingCite` via the adapters."""

    async def get_glossary_canon(self, entity_name: str, dimension: str) -> str | None: ...
    async def get_passages(self, query: str, *, top_k: int) -> Sequence[object]: ...
    async def get_chapter_locators(self, chapter_ids: Sequence[str]) -> dict[str, int]: ...
