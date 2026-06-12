"""H0 provenance chokepoint — the point where enriched lore is permanently
marked NOT-canon (RAID C11, CORE INVARIANT H0).

This module is the *single* place an enriched fact comes into existence. Every
generated dimension value MUST pass through :func:`make_enriched_fact`, which
stamps the H0 distinguishing markers BY CONSTRUCTION:

  * ``origin``            — ``'enriched'`` or ``'enriched:<technique>'`` (NEVER
    ``'glossary'`` / authored canon). Validated; anything else raises.
  * ``technique``         — the strategy that produced it (template/retrieval/…).
  * ``provenance``        — a NON-EMPTY dict recording technique + model_ref
    (a provider-registry ref, NEVER a model NAME) + the grounding refs (C10) the
    content was generated from + a timestamp. Empty provenance raises.
  * ``confidence``        — strictly ``0 < c < 1.0``. Enriched ≠ authored canon
    (glossary canon = 1.0), so a value ``>= 1.0`` is an H0 violation and raises.
  * ``source_refs``       — the NON-EMPTY list of cultural-grounding citations
    (corpus_id + chunk_id) the fact was grounded on. Empty raises (a generated
    fact with no source is unprovenanced — an H0 bug).
  * ``pending_validation``— always ``True`` (enriched lore is quarantined until
    the author promotes it — C13). A ``False`` value raises.
  * ``review_status``     — always ``'proposed'`` (start of the C2 lifecycle DAG).

A fact with NO origin/provenance MUST be impossible to construct. There is no
zero-arg constructor path, no dict bypass, no ``confidence=1.0`` default: the
model's required fields + validators make an untagged or canon-looking fact a
hard error, not a matter of caller discipline.

This maps 1:1 onto the C2 ``enrichment_proposal`` H0 columns (``origin``,
``technique``, ``provenance_json``, ``confidence``, ``source_refs_json``,
``review_status``) so a later cycle persists it without translation. This cycle
STOPS at producing tagged in-memory records — NO write-back (that is C13).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "EnrichedFact",
    "SourceRef",
    "build_provenance",
    "make_enriched_fact",
    "GENERATION_CONFIDENCE",
    "ENRICHED_ORIGIN",
    "H0OriginError",
]


# ── H0 constants ──────────────────────────────────────────────────────────────
#: The base origin marker for every enriched fact. NEVER ``'glossary'`` (authored
#: canon). A technique-qualified form ``enriched:<technique>`` is also accepted.
ENRICHED_ORIGIN: str = "enriched"

#: The forbidden origin: authored canon. An enriched fact may never claim it.
_CANON_ORIGIN: str = "glossary"

#: A generated (and grounded) fact's default confidence. It sits ABOVE the C10
#: retrieval floor (0.05 — grounded but un-generated) because content now EXISTS,
#: yet remains well below canon (1.0): nothing is canon until the author promotes
#: it (C13). H0: strictly ``0 < c < 1.0`` — never 1.0.
GENERATION_CONFIDENCE: float = 0.30


class H0OriginError(ValueError):
    """Raised when an origin marker would violate H0 (blank, or authored-canon).

    A distinct type so tests + callers can assert the H0 chokepoint rejected an
    attempt to mark enriched lore as canon, rather than catching a generic
    ``ValueError`` that could mask an unrelated validation failure.
    """


class SourceRef(BaseModel):
    """One cultural-grounding citation a fact was generated from (C10 grounding).

    Maps onto a ``source_refs_json`` entry: which corpus + chunk grounded this
    fact, plus the similarity score that retrieval produced. A fact MUST cite at
    least one of these (see :class:`EnrichedFact`) — a generated fact with no
    source is unprovenanced (an H0 bug).
    """

    model_config = ConfigDict(frozen=True)

    corpus_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    score: float


def _is_valid_origin(origin: str) -> bool:
    """An origin is valid iff it is exactly ``enriched`` or ``enriched:<x>`` with
    a non-empty technique suffix — and never the authored-canon origin."""
    if origin == _CANON_ORIGIN or origin.startswith(_CANON_ORIGIN + ":"):
        return False
    if origin == ENRICHED_ORIGIN:
        return True
    prefix = ENRICHED_ORIGIN + ":"
    return origin.startswith(prefix) and len(origin) > len(prefix)


class EnrichedFact(BaseModel):
    """One H0-stamped generated fact (a single dimension value) — the C11 output.

    BORN quarantined: the canon-distinguishing fields are required + validated so
    a caller can neither omit them nor flip them to canon. Construct ONLY via
    :func:`make_enriched_fact`; the direct constructor is also safe (every
    invariant is a field/validator) but the factory is the supported seam that
    fills provenance/source_refs from the C10 grounding.

    H0 enforced here (not by caller discipline):
      * ``origin`` ∈ {``enriched``, ``enriched:<technique>``} — validator raises
        :class:`H0OriginError` on blank / ``glossary`` / canon-looking values.
      * ``confidence`` ``gt=0, lt=1.0`` — pydantic rejects ``>= 1.0`` or ``<= 0``.
      * ``provenance`` non-empty dict — validator raises on ``{}``.
      * ``source_refs`` non-empty — validator raises on ``[]``.
      * ``pending_validation`` must be ``True`` — validator raises on ``False``.
    """

    model_config = ConfigDict(frozen=True)

    # ── identity + Q3 scope (carried from the proposal) ───────────────────────
    user_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    entity_kind: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    target_ref: str | None = None

    # ── the generated content (one dimension) ─────────────────────────────────
    #: The dimension this fact fills (the C6 Chinese label, e.g. 历史/地理/文化).
    dimension: str = Field(min_length=1)
    #: The generated dimension value — Chinese, source-faithful prose/list.
    content: str = Field(min_length=1)

    # ── H0 distinguishing markers (REQUIRED — never defaulted to canon) ───────
    origin: str = Field(min_length=1)
    technique: str = Field(min_length=1)
    confidence: float = Field(gt=0.0, lt=1.0)
    provenance: dict[str, Any]
    source_refs: list[SourceRef]
    pending_validation: bool = True
    review_status: str = Field(default="proposed")

    @field_validator("origin")
    @classmethod
    def _origin_must_be_enriched(cls, v: str) -> str:
        if not _is_valid_origin(v):
            raise H0OriginError(
                "H0 violation: origin must be 'enriched' or 'enriched:<technique>' "
                f"(never authored canon / blank), got {v!r}"
            )
        return v

    @field_validator("provenance")
    @classmethod
    def _provenance_non_empty(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not v:
            raise ValueError(
                "H0 violation: provenance must be non-empty "
                "(a fact with no provenance is unprovenanced)"
            )
        return v

    @field_validator("source_refs")
    @classmethod
    def _source_refs_non_empty(cls, v: list[SourceRef]) -> list[SourceRef]:
        if not v:
            raise ValueError(
                "H0 violation: source_refs must cite at least one grounding ref "
                "(a generated fact with no source is unprovenanced)"
            )
        return v

    @field_validator("pending_validation")
    @classmethod
    def _must_be_pending(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError(
                "H0 violation: pending_validation must be True "
                "(enriched lore is quarantined until the author promotes it)"
            )
        return v

    @field_validator("review_status")
    @classmethod
    def _status_is_proposed(cls, v: str) -> str:
        if v != "proposed":
            raise ValueError(
                "H0 violation: a freshly-generated fact starts at 'proposed' "
                f"(the C2 lifecycle DAG entry state), got {v!r}"
            )
        return v

    @classmethod
    def model_construct(cls, *args, **kwargs):  # type: ignore[override]
        """Close pydantic's validation-skipping escape hatch for H0.

        ``BaseModel.model_construct`` builds an instance WITHOUT running
        validators — which would let a caller mint a canon-looking fact
        (``origin='glossary'``, ``confidence=1.0``). H0 must be impossible to
        forget, not merely documented, so we forbid it outright: there is exactly
        ONE supported way to make a fact, the validated path (constructor /
        :func:`make_enriched_fact`).
        """
        raise H0OriginError(
            "H0 violation: EnrichedFact.model_construct is forbidden — it skips "
            "the H0 validators. Use make_enriched_fact() (the validated chokepoint)."
        )

    def model_copy(self, *, update=None, deep=False):  # type: ignore[override]
        """Re-validate on copy so an ``update`` cannot smuggle canon in.

        pydantic's ``model_copy(update=...)`` does NOT re-run validators, so a
        caller could copy an enriched fact with ``origin='glossary'`` /
        ``confidence=1.0`` and defeat H0. We round-trip the copy back through the
        validated constructor: any update that would make the fact canon-looking
        raises, exactly as building it fresh would.
        """
        copied = super().model_copy(update=update, deep=deep)
        if update:
            # Re-validate the merged data through the constructor (H0 validators).
            return type(self)(**copied.model_dump())
        return copied


def _normalise_origin(technique: str, *, qualified: bool) -> str:
    """Return the origin marker for a technique.

    ``qualified=True`` → ``enriched:<technique>`` (technique-tagged origin, the
    locked-preferred form). ``qualified=False`` → the bare ``enriched``.
    """
    if qualified:
        return f"{ENRICHED_ORIGIN}:{technique}"
    return ENRICHED_ORIGIN


def build_provenance(
    *,
    technique: str,
    model_ref: str | None,
    source_refs: Sequence[SourceRef],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the NON-EMPTY ``provenance`` dict for a generated fact.

    Records WHICH technique produced it, WHICH provider-registry ``model_ref``
    generated it (a ref — NEVER a model NAME), WHICH grounding refs it was
    generated from (so a later cycle can audit "this came from these passages"),
    and WHEN. ``model_ref`` may be ``None`` only in tests/seams that have not
    resolved a model yet; the value recorded is always the ref, never a name.
    """
    provenance: dict[str, Any] = {
        "technique": technique,
        "model_ref": model_ref,  # a provider-registry ref, NOT a model name
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "grounding_ref_ids": [
            {"corpus_id": r.corpus_id, "chunk_id": r.chunk_id, "score": r.score}
            for r in source_refs
        ],
    }
    if extra:
        provenance.update(extra)
    return provenance


def make_enriched_fact(
    *,
    user_id: str,
    project_id: str,
    entity_kind: str,
    canonical_name: str,
    target_ref: str | None,
    dimension: str,
    content: str,
    technique: str,
    source_refs: Sequence[SourceRef],
    model_ref: str | None = None,
    confidence: float = GENERATION_CONFIDENCE,
    qualified_origin: bool = True,
    extra_provenance: dict[str, Any] | None = None,
) -> EnrichedFact:
    """THE single seam that creates an enriched fact — H0 by construction.

    There is no other supported path to an :class:`EnrichedFact`. It:
      1. derives the H0 ``origin`` (``enriched:<technique>`` by default),
      2. builds a non-empty ``provenance`` recording technique + model_ref +
         the grounding refs the content came from,
      3. stamps ``confidence < 1.0``, ``pending_validation=True``,
         ``review_status='proposed'``,
      4. requires non-empty ``content`` and at least one ``source_ref``.

    Any attempt to mark the fact as canon (origin ``glossary``, confidence
    ``>= 1.0``, empty provenance/source_refs, ``pending_validation=False``)
    raises — it is impossible to forget H0, not merely documented.
    """
    refs = list(source_refs)
    provenance = build_provenance(
        technique=technique,
        model_ref=model_ref,
        source_refs=refs,
        extra=extra_provenance,
    )
    return EnrichedFact(
        user_id=user_id,
        project_id=project_id,
        entity_kind=entity_kind,
        canonical_name=canonical_name,
        target_ref=target_ref,
        dimension=dimension,
        content=content,
        origin=_normalise_origin(technique, qualified=qualified_origin),
        technique=technique,
        confidence=confidence,
        provenance=provenance,
        source_refs=refs,
        # pending_validation / review_status come from the validated defaults.
    )
