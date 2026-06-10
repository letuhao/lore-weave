"""S5a — campaign cost/time estimate heuristics (pure, no I/O).

This module owns the WORKLOAD model: given the in-scope chapters' total size and
the per-role model picks, it derives per-stage input/output token counts (the
pricing-oracle items) and assembles the final band + per-stage breakdown + rough
time. The provider-registry oracle owns USD-per-token; nothing here knows prices.

The estimate is a deliberately rough, upper-leaning BAND — never sold as exact.
All tuning lives in config.Settings (the `est_*` knobs).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .config import Settings

# Pipeline roles the wizard's Model Matrix exposes (S5b makes them all editable;
# S5a only needs to price them). Embedding is priced input-only; reranker has no
# per-token pricing dimension today (Cohere rerank is per-search) → not estimated.
ROLE_EXTRACTOR = "extractor"
ROLE_EMBEDDING = "embedding"
ROLE_RERANKER = "reranker"
ROLE_TRANSLATOR = "translator"
ROLE_VERIFIER = "verifier"
ROLE_EVAL_JUDGE = "eval_judge"

# A model pick is (model_source, model_ref) or None (role unset).
ModelPick = Optional[tuple[str, str]]


@dataclass(frozen=True)
class StageMeta:
    """A pipeline stage in the estimate. `status` is filled by assemble_estimate:
    a stage with a pricing item gets the oracle's status; a stage with no model
    (or the un-token-priced reranker) is "not_estimated"."""
    stage: str            # extraction | embedding | translation | verify | eval | rerank
    role: str
    model_source: Optional[str]
    model_ref: Optional[str]
    not_estimated_reason: Optional[str] = None  # set when no oracle item is sent


def source_tokens_for(byte_sizes: list[int], cfg: Settings) -> int:
    """Total source-token estimate across the in-scope chapters. Uses each
    chapter's real byte_size (CJK-tuned: tokens ≈ bytes / est_bytes_per_token);
    a chapter with no size falls back to a configured per-chapter char average."""
    fallback_bytes = cfg.est_fallback_chars_per_chapter * cfg.est_bytes_per_token
    total_bytes = 0.0
    for b in byte_sizes:
        total_bytes += b if b > 0 else fallback_bytes
    if cfg.est_bytes_per_token <= 0:
        return 0
    return math.ceil(total_bytes / cfg.est_bytes_per_token)


def build_pricing_items(
    *,
    source_tokens: int,
    chapter_count: int,
    models: dict[str, ModelPick],
    cfg: Settings,
) -> tuple[list[dict], list[StageMeta]]:
    """Map the workload + model picks to (oracle items, stage metadata).

    Each stage's label IS the stage name (unique → maps results back). Verifier
    falls back to the translator model when unset (mirrors the V3 orchestrator's
    `_verifier_model`). A role with no model is recorded as not_estimated and
    sends no oracle item; the reranker is always not_estimated (no token price)."""
    translation_output = math.ceil(source_tokens * cfg.est_translation_output_ratio)
    extraction_output = chapter_count * cfg.est_extraction_output_per_chapter
    judge_output = chapter_count * cfg.est_judge_output_per_chapter

    verifier = models.get(ROLE_VERIFIER) or models.get(ROLE_TRANSLATOR)

    # (stage, role, model, dimension, input_tokens, output_tokens)
    plan: list[tuple[str, str, ModelPick, str, int, int]] = [
        ("extraction", ROLE_EXTRACTOR, models.get(ROLE_EXTRACTOR), "text", source_tokens, extraction_output),
        ("embedding", ROLE_EMBEDDING, models.get(ROLE_EMBEDDING), "input_only", source_tokens, 0),
        ("translation", ROLE_TRANSLATOR, models.get(ROLE_TRANSLATOR), "text", source_tokens, translation_output),
        # verify + eval read source + the candidate translation; the candidate ≈
        # translation_output (source × ratio), so input ≈ source + translation_output
        # (~2.5× source) — leaning the estimate UP, the safe side for a pre-spend screen.
        ("verify", ROLE_VERIFIER, verifier, "text", source_tokens + translation_output, judge_output),
        ("eval", ROLE_EVAL_JUDGE, models.get(ROLE_EVAL_JUDGE), "text", source_tokens + translation_output, judge_output),
    ]

    items: list[dict] = []
    metas: list[StageMeta] = []
    for stage, role, pick, dimension, tok_in, tok_out in plan:
        if pick is None:
            metas.append(StageMeta(stage, role, None, None, "no model selected"))
            continue
        src, ref = pick
        items.append({
            "label": stage,
            "model_source": src,
            "model_ref": ref,
            "dimension": dimension,
            "input_tokens": int(tok_in),
            "output_tokens": int(tok_out),
        })
        metas.append(StageMeta(stage, role, src, ref, None))

    # Reranker: surfaced in the breakdown but not token-priced (D-S5A-RERANK-COST).
    rr = models.get(ROLE_RERANKER)
    metas.append(StageMeta(
        "rerank", ROLE_RERANKER,
        rr[0] if rr else None, rr[1] if rr else None,
        "rerank has no per-token price (negligible vs LLM stages)",
    ))
    return items, metas


def assemble_estimate(
    *,
    priced: list[dict],
    metas: list[StageMeta],
    chapter_count: int,
    cfg: Settings,
) -> dict:
    """Combine the oracle's per-item results with the stage metadata into the
    response band. Unpriced/not-found stages contribute $0 to the band but are
    surfaced in `notes` — the band is therefore a FLOOR when any model is
    unpriced, and we say so."""
    by_label = {r.get("label"): r for r in priced}

    # Stages that will actually RUN drive the time estimate — that's "has a model
    # in one of the 5 LLM stages", NOT "the oracle priced it" (an unpriced model
    # still runs). rerank is excluded (it's part of retrieval, not a per-chapter pass).
    _LLM_STAGES = {"extraction", "embedding", "translation", "verify", "eval"}
    running_stages = sum(
        1 for m in metas if m.stage in _LLM_STAGES and m.model_ref is not None
    )

    per_stage: list[dict] = []
    total_high = 0.0
    notes: list[str] = []

    for m in metas:
        result = by_label.get(m.stage)
        if result is None:
            status = "not_estimated"
            usd = 0.0
            if m.not_estimated_reason:
                # Only note stages the user might expect to cost money (skip rerank's
                # inherent no-price note unless a model was actually chosen for it).
                if m.stage != "rerank" or m.model_ref is not None:
                    notes.append(f"{m.stage}: not estimated ({m.not_estimated_reason})")
        else:
            status = result.get("status", "not_estimated")
            usd = float(result.get("estimated_usd", 0.0) or 0.0)
            if status == "ok":
                total_high += usd
            elif status == "unpriced":
                notes.append(f"{m.stage}: model has no pricing configured — real cost will be higher")
            elif status == "not_found":
                notes.append(f"{m.stage}: model not found in your registry")
            elif status == "bad_request":
                notes.append(f"{m.stage}: invalid model reference")
        per_stage.append({
            "stage": m.stage,
            "role": m.role,
            "model_source": m.model_source,
            "model_ref": m.model_ref,
            "status": status,
            "estimated_usd": round(usd, 8),
        })

    total_low = total_high * cfg.est_low_factor

    # Rough wall-clock: chapters × running stages × per-call latency ÷ parallelism.
    minutes_high = 0
    if running_stages > 0 and cfg.est_concurrency > 0:
        secs = chapter_count * running_stages * cfg.est_seconds_per_stage_call / cfg.est_concurrency
        minutes_high = math.ceil(secs / 60.0)
    minutes_low = math.floor(minutes_high * cfg.est_low_factor)

    if any(p["status"] in ("unpriced", "not_found", "bad_request") for p in per_stage):
        notes.append("Some stages could not be priced — the total is a lower bound.")

    return {
        "chapter_count": chapter_count,
        "currency": "USD",
        "estimated_usd_low": round(total_low, 8),
        "estimated_usd_high": round(total_high, 8),
        "estimated_minutes_low": minutes_low,
        "estimated_minutes_high": minutes_high,
        "per_stage": per_stage,
        "notes": notes,
        "disclaimer": "Rough pre-launch estimate — actual cost depends on real chapter length, retries, and skips.",
    }
