"""Schema-governed GENERATION + H0 tagging (RAID C11).

The cycle where the C9 empty scaffold + C10 retrieved grounding become real
Chinese lore, normalized to a game-ready schema and PERMANENTLY marked NOT-canon.

Three modules behind one chokepoint:

  * ``provenance`` — the H0 chokepoint. :func:`make_enriched_fact` is the ONLY
    path to an :class:`EnrichedFact`; it stamps ``origin='enriched:<technique>'``
    + non-empty provenance + ``confidence<1.0`` + non-empty source_refs +
    ``pending_validation=True`` BY CONSTRUCTION. An untagged / canon-looking fact
    is impossible to build (validators raise).
  * ``repair`` — normalization-repair. :func:`repair_generation` turns raw LLM
    output (fenced JSON, trailing commas, prose, English-leakage) into the
    schema-governed dimension map OR raises a typed :class:`RepairError` — no
    silent data loss.
  * ``generate`` — :class:`SchemaGovernedGenerator` orchestrates prompt → LLM
    (injected ``CompleteFn``, model_ref via provider-registry, NEVER a hardcoded
    name) → repair → H0-tag. Output: one :class:`EnrichedFact` per missing
    dimension, all quarantined.

Locked: H0 (enriched ≠ canon); output Chinese, source-faithful; no hardcoded
model names; generation STOPS before any write-back (C13), canon-verify (C12),
or orchestration (C14).
"""

from app.generation.generate import (
    CompleteFn,
    GenerationError,
    SchemaGovernedGenerator,
    build_generation_prompt,
)
from app.generation.provenance import (
    ENRICHED_ORIGIN,
    GENERATION_CONFIDENCE,
    EnrichedFact,
    H0OriginError,
    SourceRef,
    build_provenance,
    make_enriched_fact,
)
from app.generation.repair import (
    RepairError,
    RepairReport,
    cjk_ratio,
    has_english_leakage,
    repair_generation,
)

__all__ = [
    # provenance / H0 chokepoint
    "EnrichedFact",
    "SourceRef",
    "make_enriched_fact",
    "build_provenance",
    "GENERATION_CONFIDENCE",
    "ENRICHED_ORIGIN",
    "H0OriginError",
    # repair
    "repair_generation",
    "RepairError",
    "RepairReport",
    "has_english_leakage",
    "cjk_ratio",
    # generate
    "SchemaGovernedGenerator",
    "CompleteFn",
    "GenerationError",
    "build_generation_prompt",
]
