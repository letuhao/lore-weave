"""SDK-local extraction-schema projection (KG customizable-ontology, lane LB).

This module is the SDK's **own** minimal view of a resolved KG graph-schema. It
deliberately does **NOT** import knowledge-service app code
(``app.db.ontology_models``): ``loreweave_extraction`` is a standalone SDK
consumed by THREE services (knowledge-service, worker-ai, translation-service),
so it must define the schema shape it needs locally and receive it as a plain
dict / this small dataclass.

Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md §1.1
(ontology was hardcoded as ``Literal`` kinds + ``.md`` vocab), §10-B1 (prompt
token budget — project a *projection* of only what extraction needs, soft-cap
the injected vocab + ``log()`` when truncated).

**Projection, not the full schema.** Extraction needs only the controlled
vocabularies it injects into the prompt + validates against:

  * ``entity_kinds``    — the node-kind codes (replaces the static
    ``person/place/organization/artifact/concept/other`` ``Literal``);
  * ``edge_predicates`` — the edge-type codes (the relation predicate vocab);
  * ``event_kinds``     — the event ``kind`` vocab (currently the static
    ``action/dialogue/.../other`` set);
  * ``fact_types``      — the fact ``type`` vocab (currently
    ``description/attribute/negation/temporal/causal``);
  * ``allow_free_edges`` — when True the predicate vocab is *advisory* (off-vocab
    predicates are allowed, mirroring today's free-string behavior); when False
    the edge set is *closed* (off-vocab predicates are dropped + reported to the
    caller's ``on_dropped`` so a downstream lane can triage them).

The query layer, temporal/provenance flags, cardinality, node-kind *strength*,
etc. are NOT part of this projection — they are persistence / write-path / query
concerns, not extraction-prompt concerns.

**Backward-compat:** ``schema=None`` everywhere keeps today's static behavior.
This dataclass is only constructed + threaded when knowledge-service passes a
resolved schema; worker-ai + translation-service never build one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ExtractionSchema",
    "DEFAULT_VOCAB_SOFT_CAP",
]

logger = logging.getLogger(__name__)

# §10-B1 — soft cap on how many vocab values of EACH kind we inject into a
# single extraction prompt. A schema with 200 edge types would otherwise blow
# the token budget on every chunked call (the exact economy concern §10-B1
# raises). When a vocab list exceeds the cap we inject the first N (schema
# order — most-salient-first by construction) and `log()` a truncation warning;
# we never crash and never silently drop without logging. Validation still
# accepts the FULL vocab (truncation only trims the *prompt hint*, not what the
# extractor will accept) so a truncated prompt can't make a valid value invalid.
DEFAULT_VOCAB_SOFT_CAP = 40


@dataclass(frozen=True)
class ExtractionSchema:
    """The SDK-local projection of a resolved KG schema for extraction.

    All vocab lists are *codes* (stable slugs). ``allow_free_edges`` governs
    whether off-vocab predicates are tolerated (True, today's behavior) or
    closed-set (False → drop + report off-vocab predicates).

    Construct via :meth:`from_resolved` from the plain dict knowledge-service
    builds out of its ``ResolvedSchema`` (the SDK never imports that model).
    """

    entity_kinds: tuple[str, ...] = ()
    edge_predicates: tuple[str, ...] = ()
    event_kinds: tuple[str, ...] = ()
    fact_types: tuple[str, ...] = ()
    allow_free_edges: bool = True
    # KG customizable-ontology (L7) — per-predicate cardinality
    # (predicate code → ``"single_active"`` | ``"multi_active"``). A
    # ``single_active`` edge type auto-closes the prior open instance when a new
    # instance is written between the same endpoints (the write path consults
    # this; the SDK itself never enforces it). Empty default ⇒ the write path
    # finds no cardinality ⇒ no auto-close, i.e. today's behavior. NEVER injected
    # into the prompt or used in validation — a write-path concern only.
    edge_cardinalities: dict[str, str] = field(default_factory=dict)
    # The soft cap applied when rendering vocab into a prompt (§10-B1).
    vocab_soft_cap: int = DEFAULT_VOCAB_SOFT_CAP
    # Free-form provenance for logging (project_id / schema_version) — never
    # injected into the prompt, never part of validation.
    label: str = ""
    # The resolved schema version (M3) — stamped onto written edges/facts by the
    # knowledge-service write path (L7). None for legacy/un-adopted. Never in the
    # prompt or validation; provenance only.
    schema_version: int | None = None

    @classmethod
    def from_resolved(
        cls,
        resolved: dict[str, Any],
        *,
        vocab_soft_cap: int = DEFAULT_VOCAB_SOFT_CAP,
    ) -> "ExtractionSchema":
        """Build the projection from a plain dict.

        Expected dict shape (knowledge-service projects its ``ResolvedSchema``
        into exactly this — the SDK never sees the Pydantic model):

            {
              "entity_kinds":    ["person", "cultivator", ...],
              "edge_predicates": ["pursues", "disciple_of", ...],
              "event_kinds":     ["action", "breakthrough", ...],
              "fact_types":      ["description", "realm", ...],
              "allow_free_edges": True,
              "label": "<project_id>@v<schema_version>",
            }

        Missing / wrong-typed keys degrade to empty (an empty vocab means the
        dynamic path injects no hint + validation accepts anything for that
        kind — i.e. it behaves *more* permissively, never harder, so a partial
        projection can never make extraction stricter than intended).
        """

        def _codes(key: str) -> tuple[str, ...]:
            raw = resolved.get(key)
            if not isinstance(raw, (list, tuple)):
                return ()
            out: list[str] = []
            seen: set[str] = set()
            for v in raw:
                if isinstance(v, str):
                    c = v.strip()
                    if c and c not in seen:
                        seen.add(c)
                        out.append(c)
            return tuple(out)

        def _cardinalities() -> dict[str, str]:
            raw = resolved.get("edge_cardinalities")
            if not isinstance(raw, dict):
                return {}
            out: dict[str, str] = {}
            for k, v in raw.items():
                if isinstance(k, str) and isinstance(v, str):
                    code = k.strip()
                    card = v.strip()
                    if code and card:
                        out[code] = card
            return out

        allow_free = resolved.get("allow_free_edges", True)
        return cls(
            entity_kinds=_codes("entity_kinds"),
            edge_predicates=_codes("edge_predicates"),
            event_kinds=_codes("event_kinds"),
            fact_types=_codes("fact_types"),
            allow_free_edges=bool(allow_free) if isinstance(allow_free, bool) else True,
            edge_cardinalities=_cardinalities(),
            vocab_soft_cap=vocab_soft_cap,
            label=str(resolved.get("label") or ""),
            schema_version=(
                resolved["schema_version"]
                if isinstance(resolved.get("schema_version"), int)
                else None
            ),
        )

    # ── vocab rendering (§10-B1 soft-cap + log on truncate) ──────────────

    def _capped(self, vocab: tuple[str, ...], *, what: str) -> list[str]:
        """Return the first ``vocab_soft_cap`` codes, ``log()``-ing a warning
        when truncated. The cap trims the PROMPT hint only — never validation."""
        if self.vocab_soft_cap <= 0 or len(vocab) <= self.vocab_soft_cap:
            return list(vocab)
        logger.warning(
            "ExtractionSchema vocab truncated for prompt (%s): %d values > "
            "soft cap %d (schema=%r). Injecting first %d; validation still "
            "accepts the full set.",
            what, len(vocab), self.vocab_soft_cap, self.label or "?",
            self.vocab_soft_cap,
        )
        return list(vocab[: self.vocab_soft_cap])

    def render_entity_kinds(self) -> list[str]:
        return self._capped(self.entity_kinds, what="entity_kinds")

    def render_edge_predicates(self) -> list[str]:
        return self._capped(self.edge_predicates, what="edge_predicates")

    def render_event_kinds(self) -> list[str]:
        return self._capped(self.event_kinds, what="event_kinds")

    def render_fact_types(self) -> list[str]:
        return self._capped(self.fact_types, what="fact_types")
