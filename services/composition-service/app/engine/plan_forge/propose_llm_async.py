"""Async LLM propose/refine for PlanForge worker (BYOK model_ref)."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.engine.plan_forge.existing_state import (
    ExistingState,
    merge_existing_into_spec,
    render_existing_state_prompt,
)
from app.engine.plan_forge.json_extract import extract_json_object
from app.engine.plan_forge.llm import _ANTI_LOOP, PlanForgeLLMError, ProviderPlanForgeLLM
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
from app.engine.plan_forge.schemas import ANALYZE_SCHEMA, SPEC_SCHEMA

logger = logging.getLogger(__name__)


#: A response is DEGENERATE — a repetition loop rather than a formatting slip — when it is far
#: larger than these prompts ever legitimately produce. Measured: healthy responses land at
#: 3.3-6.5k characters; every loop observed exceeded 12k. The threshold sits between them with room
#: on both sides, and it only decides RETRY-vs-REPAIR, so an occasional misjudgement costs one call.
_DEGENERATE_CHARS = 12000


#: How many times to REGENERATE a degenerate response before giving up. One was not enough: measured
#: on the author's real 4,278-character document, attempt 1 came back at 31,401 chars and the single
#: retry at 26,420 — both loops — and the run died. Bounded at two extra calls because each is a full
#: billed generation, and because a model that loops three times running is not going to stop.
_MAX_REGENERATIONS = 2

#: The anti-loop penalty ladder. The base is what every first attempt already uses (`llm._ANTI_LOOP`);
#: each regeneration climbs a step, because the ONLY lever that addresses a repetition loop is the
#: repetition penalty itself — the grammar cannot forbid a loop inside a JSON string.
#: Read from `llm._ANTI_LOOP` rather than restated, so tuning the default cannot silently leave the
#: ladder starting below it.
_ANTI_LOOP_BASE = float(_ANTI_LOOP["frequency_penalty"])
_ANTI_LOOP_STEP = 0.4
_ANTI_LOOP_MAX = 1.8


def _is_degenerate(content: str) -> bool:
    return len(content) >= _DEGENERATE_CHARS


async def _parse_with_repair(
    client: ProviderPlanForgeLLM,
    step: str,
    system: str,
    user: str,
    repair_step: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 8000,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One step, then ONE repair on a parse failure.

    With `schema` the shape is enforced at the decoder, so the repair becomes what it should always
    have been — a fallback for a provider that will not take the grammar — rather than the routine
    cost of asking a model for JSON in prose. The repair deliberately drops the schema: repeating a
    grammar-constrained call that came back unparseable fails the same way, because the model is not
    disagreeing about the format."""
    content = await client.chat(
        step=step, system=system, user=user, temperature=temperature, max_tokens=max_tokens,
        schema=schema,
    )
    last_exc: Exception | None = None
    for attempt in range(_MAX_REGENERATIONS + 1):
        try:
            return extract_json_object(content)
        except (json.JSONDecodeError, ValueError) as exc:
            last_exc = exc
            if not _is_degenerate(content):
                break  # small and unparseable: a formatting slip, which repair CAN fix
            # A REPAIR CANNOT FIX A REPETITION LOOP, and pretending otherwise is worse than failing.
            #
            # Root-caused 2026-07-28: the failing responses were 33-43k characters ending in
            # `0_0_0_0_0…` repeated to the token cap. Handing that to a repair prompt does not
            # produce the author's plan — it produces a minimal valid object (1 arc, 0 events,
            # 0 variables), which then flows downstream as if it were a real read of their
            # document. That is a repair SUCCEEDING INTO GARBAGE, with nothing anywhere saying the
            # content was lost. Regenerating is the move that works: the same call succeeds on most
            # attempts, while repair-of-degenerate succeeded on none.
            if attempt == _MAX_REGENERATIONS:
                # Measured 2026-07-29 on the author's own 4,278-char document: a single regeneration
                # is NOT always enough (31,401 → 26,420 chars, both loops), and the old code parsed
                # the retry with nothing around it — so the whole propose died on a bare
                # `ValueError: unbalanced JSON braces`, which says nothing anyone can act on.
                raise PlanForgeLLMError(
                    f"{step}: the model returned a repetition loop on {_MAX_REGENERATIONS + 1} "
                    f"attempts (last {len(content)} chars, escalating anti-loop penalty each time). "
                    f"This is a decoding failure, not a problem with the document — retry, or use a "
                    f"different planner model."
                ) from exc
            # Escalate BOTH levers: temperature to leave the loop's basin, and the repetition penalty
            # itself, which is the one thing that directly targets the failure (a grammar cannot
            # forbid a loop inside a JSON string — enforcement guarantees shape, never termination).
            penalty = min(_ANTI_LOOP_BASE + _ANTI_LOOP_STEP * (attempt + 1), _ANTI_LOOP_MAX)
            logger.warning(
                "plan_forge %s: degenerate response (%d chars), attempt %d/%d — regenerating at "
                "frequency_penalty=%.1f rather than repairing; a repetition loop cannot be repaired "
                "into content",
                step, len(content), attempt + 1, _MAX_REGENERATIONS, penalty,
            )
            content = await client.chat(
                step=f"{step}_retry{attempt + 1}", system=system, user=user,
                temperature=min(temperature + 0.2 * (attempt + 1), 1.0),
                max_tokens=max_tokens, schema=schema, frequency_penalty=penalty,
            )

    repair_content = await client.chat(
        step=repair_step,
        system="Output only valid JSON. No markdown.",
        user=repair_user_prompt(str(last_exc), content),
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
        schema=ANALYZE_SCHEMA,
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
        schema=SPEC_SCHEMA,
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
    _attach_read_provenance(spec, client.io_log)
    return spec, analyze, client.io_log


def _attach_read_provenance(spec: dict[str, Any], io_log: list[dict[str, Any]]) -> None:
    """Say whether THIS read was clean — the honesty block, for the path that is now the default.

    `meta.ingest_unread` is written by the RULES propose and carries what the heading matcher could
    not classify. The LLM path does not classify anything, so it wrote nothing — and the coverage
    board, which reads that key to decide `absent` vs `unknown`, could therefore only ever say
    `absent` on the path most runs now take. The degrade signal built to stop a failed read reading
    as an empty book did not exist where it was most needed.

    This path has its own, better signal: whether a step had to be REGENERATED (a repetition loop) or
    REPAIRED (unparseable output). Either means the model's answer was not produced cleanly, so an
    empty kind is not safely `absent`. Same key on purpose — one name for one concept, and the board
    and the author's UI already read it.
    """
    degraded = [str(e.get("step")) for e in io_log
                if "retry" in str(e.get("step") or "") or "repair" in str(e.get("step") or "")]
    meta = spec.setdefault("meta", {})
    block: dict[str, Any] = {
        "path": "llm",
        # The LLM read the raw document, so there is no such thing as an unclassified section here.
        # Empty rather than omitted: a key that appears only sometimes cannot be told from an older
        # artifact that never reported.
        "unclassified": [],
        "degraded_steps": degraded,
        "note": (
            f"{len(degraded)} step(s) had to be regenerated or repaired ({', '.join(degraded)}) — "
            f"the read completed but not cleanly, so a missing part of the plan may be the read's "
            f"fault rather than the document's."
            if degraded else ""
        ),
    }
    existing_block = meta.get("ingest_unread")
    # Never clobber a rules-side block if one is somehow present; merge so both stories survive.
    meta["ingest_unread"] = {**existing_block, **block} if isinstance(existing_block, dict) else block


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
