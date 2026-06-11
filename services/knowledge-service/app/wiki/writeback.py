"""Wiki writeback assembly (wiki-llm M5 / §C5).

Assembles the request body knowledge-service POSTs to glossary's internal
writeback (`POST /internal/books/{book_id}/wiki/articles`): the TipTap body (M0
`ir_to_tiptap`), the generation_status, the full `generation_provenance`
(build_inputs fingerprint + M4 citations + verify flags + publish-blocked +
grounding/model), and the §5.1 `source_usage` reverse index (which entity / KG
neighbourhood / chapter blocks the article was built from — so the Phase-2
staleness sweep can find every article a changed source affects). Pure assembly;
the HTTP POST is the GlossaryClient's job.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from loreweave_grounding.cites import GroundingCite

from app.wiki.context import GenerationContext
from app.wiki.fingerprint import stable_hash
from app.wiki.ir import WikiArticleIR
from app.wiki.mappers import ir_to_tiptap
from app.wiki.verify import WikiVerifyResult

__all__ = ["generation_status_for", "build_source_usage", "build_writeback_body"]


def generation_status_for(verify: WikiVerifyResult) -> str:
    """Map the verify outcome to the stored generation_status: ``blocked`` (auto-
    rejected — never publish), ``needs_review`` (advisory flags), or ``generated``
    (clean)."""
    if verify.publish_blocked:
        return "blocked"
    if verify.flags:
        return "needs_review"
    return "generated"


# W6b-2 — the source text used at generation time is captured per usage row so a
# later "what changed" view can diff it against the CURRENT source. Capped to bound
# storage (one row per source per article; passages can be long).
_SRC_TEXT_MAX = 2000


def _cap(text: str) -> str:
    text = text.strip()
    return text if len(text) <= _SRC_TEXT_MAX else text[:_SRC_TEXT_MAX].rstrip() + "…"


def _brief_text(brief) -> str:
    """The entity's textual surface (what an `entity_changed` edit touches)."""
    parts = [brief.name]
    if brief.aliases:
        parts.append("(" + ", ".join(brief.aliases) + ")")
    if brief.short_description:
        parts.append(brief.short_description)
    return "\n".join(p for p in parts if p)


def build_source_usage(
    context: GenerationContext, build_inputs: dict[str, Any],
) -> list[dict[str, str]]:
    """The §5.1 reverse index. One ``entity`` row (the subject), one ``kg`` row
    (its neighbourhood, keyed by the entity) when KG facts were used, and one
    ``block`` row per distinct cited CHAPTER (the granularity of a chapter-edit
    event), each versioned by a content hash so a no-op change is distinguishable.

    W6b-2: each row also carries the ``source_text`` it was built from (capped), the
    "before" half of the future-only change diff (the "after" re-gathers live)."""
    brief = context.brief
    usage: list[dict[str, str]] = [
        {
            "source_type": "entity",
            "source_id": brief.entity_id,
            "source_version": build_inputs["entity_content_hash"],
            "source_text": _cap(_brief_text(brief)),
        }
    ]
    kg_texts = [it.text for it in context.items if it.source.kind == "kg"]
    if kg_texts:
        usage.append({
            "source_type": "kg",
            "source_id": brief.entity_id,
            "source_version": build_inputs["kg_neighborhood_hash"],
            "source_text": _cap("\n".join(kg_texts)),
        })
    by_chapter: dict[str, list[str]] = {}
    for it in context.items:
        if it.source.kind == "passage" and it.source.chapter_id:
            by_chapter.setdefault(it.source.chapter_id, []).append(it.text)
    for chapter_id, texts in by_chapter.items():
        usage.append({
            "source_type": "block",
            "source_id": chapter_id,
            "source_version": stable_hash(sorted(texts)),
            "source_text": _cap("\n".join(texts)),
        })
    return usage


def build_writeback_body(
    *,
    context: GenerationContext,
    ir: WikiArticleIR,
    verify: WikiVerifyResult,
    cites: list[GroundingCite],
    build_inputs: dict[str, Any],
    model_ref: str,
    user_id: UUID | str,
    grounding_params: dict[str, Any],
    prompt_version: str,
    pipeline_version: str,
    step_models: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the writeback POST body (pure)."""
    provenance = {
        "build_inputs": build_inputs,
        "citations": [c.model_dump(exclude_none=True) for c in cites],
        "verify_flags": verify.flags,
        "publish_blocked": verify.publish_blocked,
        "grounding": grounding_params,
        "model_ref": model_ref,
        "prompt_version": prompt_version,
        "pipeline_version": pipeline_version,
        "step_models": step_models or {},
    }
    return {
        "entity_id": context.brief.entity_id,
        "user_id": str(user_id),
        "body_json": ir_to_tiptap(ir),
        "generation_status": generation_status_for(verify),
        "generated_by": model_ref or "ai",
        "generation_provenance": provenance,
        "spoiler_horizon": ir.spoiler_horizon,
        "source_usage": build_source_usage(context, build_inputs),
    }
