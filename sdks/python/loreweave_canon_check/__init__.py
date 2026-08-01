from .base import (
    LIVENESS_ALIVE,
    LIVENESS_GONE,
    LIVENESS_SOURCE_KG,
    LIVENESS_SOURCE_NONE,
    LIVENESS_SOURCE_PLAN,
    LIVENESS_UNKNOWN,
    SPAN_PAD,
    CanonCandidateBase,
    apply_verdicts,
    build_judge_request,
    extract_judge_text,
    find_span,
    gone_entities_referenced,
    parse_judge_verdicts,
    resolve_cast_liveness,
    unresolved_cast_refs,
)

__all__ = [
    "SPAN_PAD",
    "CanonCandidateBase",
    "apply_verdicts",
    "build_judge_request",
    "extract_judge_text",
    "find_span",
    "parse_judge_verdicts",
    # `gone_entities_referenced` answers ONE question — "which of these is marked gone and
    # named in the text?" — so everything it omits reads as fine to every caller. An entity
    # the knowledge graph has never heard of takes the identical path to one the graph
    # positively knows is alive.
    "gone_entities_referenced",
    # S2 — the per-ENTITY resolution that tells those two apart, with the layer that answered.
    "resolve_cast_liveness",
    "unresolved_cast_refs",
    "LIVENESS_ALIVE",
    "LIVENESS_GONE",
    "LIVENESS_UNKNOWN",
    "LIVENESS_SOURCE_KG",
    "LIVENESS_SOURCE_PLAN",
    "LIVENESS_SOURCE_NONE",
]
