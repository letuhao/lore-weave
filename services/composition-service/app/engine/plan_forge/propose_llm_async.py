"""Async LLM propose/refine for PlanForge worker (BYOK model_ref)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.engine.plan_forge.existing_state import (
    ExistingState,
    merge_existing_into_spec,
    render_existing_state_prompt,
)
from app.engine.plan_forge.json_extract import extract_json_object
from app.engine.plan_forge.llm import PlanForgeLLMError, ProviderPlanForgeLLM
from app.engine.plan_forge.propose_llm import normalize_spec
from app.engine.plan_forge.prompts import (
    ANALYZE_SYSTEM,
    MATERIALIZE_SYSTEM,
    REFINE_SPEC_SYSTEM,
    analyze_user_prompt,
    materialize_user_prompt,
    refine_user_prompt,
    repair_user_prompt,
)
from app.engine.plan_forge.refine import accept_refine, artifact_json_for_refine, merge_refine_output


async def _parse_with_repair(
    client: ProviderPlanForgeLLM,
    step: str,
    system: str,
    user: str,
    repair_step: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 8000,
) -> dict[str, Any]:
    content = await client.chat(
        step=step, system=system, user=user, temperature=temperature, max_tokens=max_tokens,
    )
    try:
        return extract_json_object(content)
    except (json.JSONDecodeError, ValueError) as exc:
        repair_content = await client.chat(
            step=repair_step,
            system="Output only valid JSON. No markdown.",
            user=repair_user_prompt(str(exc), content),
            max_tokens=12000,
            temperature=0.1,
        )
        return extract_json_object(repair_content)


async def analyze_markdown(
    source_markdown: str,
    client: ProviderPlanForgeLLM,
    *,
    existing: ExistingState | None = None,
) -> tuple[dict[str, Any], str]:
    checksum = hashlib.sha256(source_markdown.encode("utf-8")).hexdigest()
    block = render_existing_state_prompt(existing) if existing is not None else ""
    analyze = await _parse_with_repair(
        client,
        "analyze",
        ANALYZE_SYSTEM,
        analyze_user_prompt(source_markdown, block),
        "analyze_repair",
    )
    analyze.setdefault("version", 1)
    return analyze, checksum


async def materialize_from_analyze_async(
    analyze: dict[str, Any],
    source_checksum: str,
    client: ProviderPlanForgeLLM,
    *,
    existing: ExistingState | None = None,
    inject_cast_max: int = 1,
) -> dict[str, Any]:
    analyze_json = json.dumps(analyze, ensure_ascii=False, indent=2)
    block = render_existing_state_prompt(existing) if existing is not None else ""
    spec = await _parse_with_repair(
        client,
        "materialize",
        MATERIALIZE_SYSTEM,
        materialize_user_prompt(analyze_json, source_checksum, block),
        "materialize_repair",
        max_tokens=12000,
    )
    spec = normalize_spec(spec, source_checksum, analyze=analyze)
    if analyze.get("open_questions") and not spec.get("meta", {}).get("open_questions"):
        spec["meta"]["open_questions"] = analyze["open_questions"]
    if existing is not None:
        # A1 — the deterministic backstop: annotate + INJECT the existing protagonist over a placeholder
        # (prompt grounding alone proved insufficient in the A/B). Runs AFTER normalize's pad.
        spec = merge_existing_into_spec(spec, existing, inject_cast_max=inject_cast_max)
    return spec


async def propose_spec_llm_async(
    source_markdown: str,
    client: ProviderPlanForgeLLM,
    *,
    existing: ExistingState | None = None,
    inject_cast_max: int = 1,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Returns (spec, analyze, llm_io_log). PROPOSE-BLIND: `existing` grounds both steps; A1 injects."""
    analyze, checksum = await analyze_markdown(source_markdown, client, existing=existing)
    spec = await materialize_from_analyze_async(
        analyze, checksum, client, existing=existing, inject_cast_max=inject_cast_max,
    )
    return spec, analyze, client.io_log


async def refine_spec_async(
    spec: dict[str, Any],
    revision: dict[str, Any],
    *,
    client: ProviderPlanForgeLLM,
    source_checksum: str,
    analyze: dict[str, Any] | None = None,
) -> dict[str, Any]:
    revision = {**revision, "target": "spec"}
    payload = refine_user_prompt(artifact_json_for_refine(spec, revision), revision)
    out = await _parse_with_repair(
        client,
        "refine_spec",
        REFINE_SPEC_SYSTEM,
        payload,
        "refine_spec_repair",
        temperature=0.1,
    )
    merged = merge_refine_output(spec, out, revision)
    return normalize_spec(merged, source_checksum, analyze=analyze)


async def refine_and_accept_async(
    before: dict[str, Any],
    revision: dict[str, Any],
    *,
    client: ProviderPlanForgeLLM,
    source_checksum: str,
    analyze: dict[str, Any] | None = None,
    package: dict[str, Any] | None = None,
    fidelity_before: float | None = None,
    fidelity_after: float | None = None,
) -> dict[str, Any]:
    try:
        after = await refine_spec_async(
            before, revision, client=client, source_checksum=source_checksum, analyze=analyze,
        )
    except PlanForgeLLMError as exc:
        return {"accepted": False, "error": str(exc), "llm_io": client.io_log}
    result = accept_refine(
        before,
        after,
        revision,
        package=package,
        fidelity_before=fidelity_before,
        fidelity_after=fidelity_after,
    )
    return {
        "accepted": result.accepted,
        "reasons": result.reasons,
        "checks": result.checks,
        "spec": after,
        "llm_io": client.io_log,
    }
