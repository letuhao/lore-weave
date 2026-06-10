"""Wiki generation §5.1 capture — the build_inputs fingerprint (wiki-llm M5 / §C7).

The fingerprint is a STABLE hash of everything an article was generated FROM
(entity content, attrs, KG neighbourhood, the exact cited blocks, retrieval
params, model + prompt + pipeline version). It is stored in
`generation_provenance.build_inputs` so the Phase-2 staleness sweep can recompute
it against the CURRENT knowledge and detect when an article has drifted from its
sources — the capture MUST land in the MVP (it can't be retrofitted onto already-
generated articles).

`stable_hash` is ported from learning-service `_stable_hash` (hashlib over
sorted-key JSON — NOT Python's PYTHONHASHSEED-randomised `hash()`), so a hash is
deterministic across processes/workers. Computed in Python only; Go never
recomputes it (it stores the JSONB opaquely).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.wiki.context import GenerationContext

__all__ = ["stable_hash", "compute_build_inputs", "BUILD_INPUTS_SCHEMA_VERSION"]

#: Bump when the build_inputs SHAPE changes (so a Phase-2 sweep can tell a
#: fingerprint computed by an old pipeline from a new one).
BUILD_INPUTS_SCHEMA_VERSION = 1


def stable_hash(content: Any) -> str:
    """Deterministic SHA-256 over JSON with sorted keys (ported from learning
    `_stable_hash`). Stable across processes — uses hashlib, never `hash()`."""
    blob = json.dumps(content, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8"), usedforsecurity=False).hexdigest()


def compute_build_inputs(
    *,
    context: GenerationContext,
    model_ref: str,
    prompt_version: str,
    pipeline_version: str,
    retrieval_params: dict[str, Any],
) -> dict[str, Any]:
    """Compute the C7 build_inputs fingerprint from the generation context + params.

    `entity_revision_num` (in the C7 spec) is OMITTED — the context doesn't carry a
    glossary revision number; `entity_content_hash` over the brief is the
    equivalent change-signal (a content edit changes the hash). Every cited
    passage contributes its (chapter, block, content-hash) so a chapter edit
    invalidates exactly the articles that cited it."""
    brief = context.brief
    kg_texts = [it.text for it in context.items if it.source.kind == "kg"]
    cited_blocks = [
        {
            "chapter_id": it.source.chapter_id,
            "block_index": it.source.block_index,
            "content_hash": stable_hash(it.text),
        }
        for it in context.items
        if it.source.kind == "passage"
    ]
    return {
        "schema_version": BUILD_INPUTS_SCHEMA_VERSION,
        "entity_id": brief.entity_id,
        "entity_content_hash": stable_hash({"name": brief.name, "kind": brief.kind}),
        "attr_set_hash": stable_hash(
            {"aliases": sorted(brief.aliases), "short_description": brief.short_description}
        ),
        "kg_neighborhood_hash": stable_hash(sorted(kg_texts)),
        "cited_blocks": cited_blocks,
        "retrieval_params_hash": stable_hash(retrieval_params),
        "model_ref": model_ref,
        "prompt_version": prompt_version,
        "pipeline_version": pipeline_version,
    }
