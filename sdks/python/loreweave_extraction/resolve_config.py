"""Phase B2 — effective extraction-config resolution + content-addressed hashing.

This is the ONE place worker-ai and knowledge-service both compute the
effective extraction config and its `config_hash`, so two services running the
same job produce byte-identical hashes (DESIGN Q6). It merges global defaults
with per-project overrides and emits a `ResolvedConfig` + a stable `config_hash`.

Two inputs:

  global_defaults: dict   — the env/SDK-resolved baseline the caller already has
    {
      "model_ref": str,                              # extractor model
      "model_source": "user_model" | "platform_model",
      "precision_filter": PrecisionFilterConfig | None,
      "entity_recovery": EntityRecoveryConfig | None,
      "writer_autocreate": bool,
    }

  project_overrides: dict — knowledge_projects.extraction_config JSONB (may be {})
    {
      "llm_model":        {"model_ref": str, "model_source": str},
      "precision_filter": {"enabled": bool, "categories": [str], "partial_policy": str,
                            "model_ref"?: str, "model_source"?: str},
      "entity_recovery":  {"enabled": bool, "model_ref"?: str, "model_source"?: str},
      "writer_autocreate":{"enabled": bool},
      "prompts":          {<op>: {"system"?: str, "user"?: str}},
    }
  Precedence: project override > global default > SDK constant. A missing
  override key falls through to the global default. Keys not listed above
  (e.g. `embedding_model`, `rerank_model`) are IGNORED here — embedding model is
  a retrieval-layer concern and is deliberately NOT part of `config_hash`
  (DESIGN self-review #4).

Hashing discipline (memory `etag-stable-hash-all-response-fields`): canonical
JSON (sorted keys) → `hashlib.sha256`, NOT Python's `hash()` (PYTHONHASHSEED
randomizes it per-process). `config_hash` is the full 64-hex digest;
`base_default_version` is a short 8-hex label.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from loreweave_extraction._version import get_extractor_version
from loreweave_extraction.entity_recovery import EntityRecoveryConfig
from loreweave_extraction.pass2_filter import PrecisionFilterConfig
from loreweave_extraction.schema_projection import ExtractionSchema

__all__ = [
    "ResolvedConfig",
    "resolve_effective_config",
    "config_hash",
    "base_default_version",
    "PROMPT_OPS",
    "extraction_schema_from_resolved",
]

# The op set whose prompts are versioned (mirror _version._OP_PROMPTS keys).
PROMPT_OPS: tuple[str, ...] = ("entity", "relation", "event", "fact", "summarize_level")

ModelSource = Literal["user_model", "platform_model"]


@dataclass(frozen=True)
class ResolvedConfig:
    """The effective per-job extraction config after merging global + project.

    `prompts` holds raw override text (lives in the user's own project row);
    `prompt_versions` holds the hashed identity used in `config_hash` — so the
    hash and any cross-service emission carry the prompt *identity*, never the
    raw text (DESIGN Q5).
    """

    model_ref: str
    model_source: ModelSource
    precision_filter: PrecisionFilterConfig | None
    entity_recovery: EntityRecoveryConfig | None
    writer_autocreate: bool
    prompts: dict[str, dict[str, str]] = field(default_factory=dict)
    prompt_versions: dict[str, str] = field(default_factory=dict)


def _override(project_overrides: dict, key: str) -> dict | None:
    val = project_overrides.get(key)
    return val if isinstance(val, dict) else None


def _resolve_filter(
    global_filter: PrecisionFilterConfig | None, ov: dict | None,
    *, default_model_ref: str | None = None,
    default_model_source: ModelSource = "user_model",
) -> PrecisionFilterConfig | None:
    """Merge a per-project precision_filter override onto the global default.

    D-WX-PRECISION-FILTER-MODEL-ARCH: when the override enables the filter without its
    OWN model_ref, fall back to the EXTRACTION model (`default_model_*` = the campaign's
    user-owned, UI-selected, DB-stored llm_model) — NEVER an env/global model, which is
    cross-tenant (it 404'd "model not found" for every user who didn't own it and stalled
    the decoupled fold). `global_filter` is always None now (env model source removed).
    """
    if ov is None:
        return global_filter
    # `enabled` defaults to True when the key is present without it; an explicit
    # false disables the filter for this project regardless of the global.
    if ov.get("enabled", True) is False:
        return None
    model_ref = (
        ov.get("model_ref")
        or (global_filter.model_ref if global_filter else None)
        or default_model_ref
    )
    if not model_ref:
        raise ValueError(
            "precision_filter enabled but no model_ref available "
            "(none in override, no global filter, no extraction model to fall back to)"
        )
    model_source: ModelSource = (
        ov.get("model_source")
        or (global_filter.model_source if global_filter else None)
        or default_model_source
    )  # type: ignore[assignment]
    # /review-impl LOW-2: an explicit empty `categories: []` is falsy here and
    # FALLS THROUGH to the global categories (PrecisionFilterConfig forbids an
    # empty tuple — a [] would otherwise raise). To DISABLE the filter, set
    # `enabled: false`; to narrow it, pass a non-empty subset. The B2-B edit
    # endpoint should reject `[]` upfront rather than relying on this fallback.
    categories = ov.get("categories")
    partial_policy = ov.get("partial_policy") or (
        global_filter.partial_policy if global_filter else "keep"
    )
    kwargs: dict[str, Any] = {
        "model_ref": model_ref,
        "model_source": model_source,
        "partial_policy": partial_policy,
    }
    if categories:
        kwargs["categories"] = tuple(categories)
    elif global_filter is not None:
        kwargs["categories"] = global_filter.categories
    # carry operational knobs from the global filter (not part of config_hash)
    if global_filter is not None:
        kwargs.setdefault("max_items_per_batch", global_filter.max_items_per_batch)
        kwargs.setdefault("transient_retry_budget", global_filter.transient_retry_budget)
    return PrecisionFilterConfig(**kwargs)


def _resolve_recovery(
    global_recovery: EntityRecoveryConfig | None, ov: dict | None,
) -> EntityRecoveryConfig | None:
    if ov is None:
        return global_recovery
    if ov.get("enabled", True) is False:
        return None
    model_ref = ov.get("model_ref") or (global_recovery.model_ref if global_recovery else None)
    if not model_ref:
        raise ValueError(
            "entity_recovery enabled but no model_ref available "
            "(none in override and no global entity_recovery configured)"
        )
    model_source: ModelSource = (
        ov.get("model_source")
        or (global_recovery.model_source if global_recovery else "user_model")
    )  # type: ignore[assignment]
    kwargs: dict[str, Any] = {"model_ref": model_ref, "model_source": model_source}
    if global_recovery is not None:
        kwargs.setdefault("max_items_per_batch", global_recovery.max_items_per_batch)
        kwargs.setdefault("transient_retry_budget", global_recovery.transient_retry_budget)
        kwargs.setdefault("known_entity_kinds", global_recovery.known_entity_kinds)
    return EntityRecoveryConfig(**kwargs)


def _resolve_prompt_versions(prompts: dict[str, dict[str, str]]) -> dict[str, str]:
    """Per-op version string: `custom-<hash>` when overridden, else file-hash.

    The override text fed to `get_extractor_version` is the concatenation of the
    op's `system` + `user` overrides (only the keys present), so editing either
    changes the version. An op with no override falls back to its prompt-file
    hash via `get_extractor_version(op)`.
    """
    out: dict[str, str] = {}
    for op in PROMPT_OPS:
        ov = prompts.get(op)
        system = (ov or {}).get("system")
        if system:
            # /review-impl LOW-1 — hash the BARE system text so the registry's
            # custom-<8hex> is the 8-char prefix of the KS adjustment-event's
            # content_hash (sha256(system)); keeps the two joinable in E2 mining.
            # Only `system` is overridable in b2 (the user message is raw text).
            out[op] = get_extractor_version(op, override_text=system)
        else:
            out[op] = get_extractor_version(op)
    return out


def resolve_effective_config(
    *, global_defaults: dict, project_overrides: dict | None,
) -> ResolvedConfig:
    """Merge global defaults with per-project overrides into a ResolvedConfig."""
    po = project_overrides or {}

    llm = _override(po, "llm_model")
    model_ref = (llm or {}).get("model_ref") or global_defaults["model_ref"]
    model_source: ModelSource = (
        (llm or {}).get("model_source") or global_defaults.get("model_source", "user_model")
    )  # type: ignore[assignment]

    precision_filter = _resolve_filter(
        global_defaults.get("precision_filter"), _override(po, "precision_filter"),
        # fall back to the extraction model when the filter is enabled without its own
        # model (D-WX-PRECISION-FILTER-MODEL-ARCH) — per-user, never a global/env model.
        default_model_ref=model_ref, default_model_source=model_source,
    )
    entity_recovery = _resolve_recovery(
        global_defaults.get("entity_recovery"), _override(po, "entity_recovery")
    )

    ac_ov = _override(po, "writer_autocreate")
    writer_autocreate = (
        ac_ov.get("enabled", True) if ac_ov is not None
        else bool(global_defaults.get("writer_autocreate", False))
    )

    prompts_ov = po.get("prompts")
    prompts: dict[str, dict[str, str]] = (
        {op: dict(v) for op, v in prompts_ov.items() if isinstance(v, dict)}
        if isinstance(prompts_ov, dict) else {}
    )

    return ResolvedConfig(
        model_ref=model_ref,
        model_source=model_source,
        precision_filter=precision_filter,
        entity_recovery=entity_recovery,
        writer_autocreate=writer_autocreate,
        prompts=prompts,
        prompt_versions=_resolve_prompt_versions(prompts),
    )


def _canonical_dict(rc: ResolvedConfig) -> dict[str, Any]:
    """The exact field set that defines config identity (DESIGN §6.4).

    Semantic fields only: operational knobs (batch size, retry budget) and the
    embedding model are EXCLUDED so operationally-equivalent configs dedup.
    Prompt identity enters via `prompt_versions` (hashed), never raw text.
    """
    pf = rc.precision_filter
    er = rc.entity_recovery
    return {
        "model_ref": rc.model_ref,
        "model_source": rc.model_source,
        "precision_filter": None if pf is None else {
            "model_ref": pf.model_ref,
            "model_source": pf.model_source,
            "categories": sorted(pf.categories),
            "partial_policy": pf.partial_policy,
        },
        "entity_recovery": None if er is None else {
            "model_ref": er.model_ref,
            "model_source": er.model_source,
        },
        "writer_autocreate": rc.writer_autocreate,
        "prompt_versions": dict(sorted(rc.prompt_versions.items())),
    }


def config_hash(rc: ResolvedConfig) -> str:
    """Stable content-address of the effective config (full sha256 hex)."""
    canonical = json.dumps(
        _canonical_dict(rc), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def extraction_schema_from_resolved(
    resolved: dict | None, *, vocab_soft_cap: int | None = None,
) -> ExtractionSchema | None:
    """Build the SDK-local :class:`ExtractionSchema` projection for extraction.

    KG customizable-ontology (lane LB). ``resolved`` is the plain-dict
    projection knowledge-service builds from its ``ResolvedSchema`` (system→
    user→project merge — the existing tier priority is applied UPSTREAM by the
    KG ``OntologyResolver``, not re-implemented here; this is just the SDK-side
    shaping). Returns ``None`` when ``resolved`` is ``None`` so the caller can
    forward it straight into ``extract_pass2(schema=...)`` and keep the static
    byte-identical path when no schema was resolved.

    Kept here so resolve_config's consumers have ONE import surface for the
    per-job extraction shape (config + ontology); the projection logic itself
    lives in ``schema_projection`` (which never imports knowledge-service)."""
    if resolved is None:
        return None
    if vocab_soft_cap is None:
        return ExtractionSchema.from_resolved(resolved)
    return ExtractionSchema.from_resolved(resolved, vocab_soft_cap=vocab_soft_cap)


def base_default_version(global_defaults: dict) -> str:
    """Content-hash (8-hex) of the canonicalized global defaults.

    Derived, not hand-maintained (DESIGN self-review #3): it changes iff a
    global default changes, so it cannot silently drift. Built by resolving the
    globals with NO project override and hashing the same canonical field set,
    then truncating to a short label.
    """
    rc = resolve_effective_config(global_defaults=global_defaults, project_overrides={})
    return config_hash(rc)[:8]
