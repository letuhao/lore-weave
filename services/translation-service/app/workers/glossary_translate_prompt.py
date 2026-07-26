"""Prompt + parse helpers for glossary batch attribute translation."""
from __future__ import annotations

import json
import re
from typing import Any

from .chunk_splitter import estimate_tokens


def build_system_prompt(source_language: str, target_language: str) -> str:
    return (
        f"You translate glossary entity attributes from {source_language} to {target_language}.\n"
        "Return ONLY a JSON object mapping each attribute `code` to its translated string.\n"
        "Preserve formatting for tags (comma-separated) and select values.\n"
        "Do not add keys beyond those provided. Do not wrap in markdown."
    )


def build_user_prompt(
    display_name: str,
    kind_code: str,
    attributes: list[dict[str, Any]],
) -> str:
    lines = [
        f"Entity: {display_name} (kind={kind_code})",
        "Attributes to translate:",
    ]
    for attr in attributes:
        lines.append(
            f"- code={attr['code']} field_type={attr.get('field_type', 'text')}: "
            f"{attr['original_value']}"
        )
    lines.append('Respond with JSON like: {"name": "...", "description": "..."}')
    return "\n".join(lines)


_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def parse_translation_response(raw: str, expected_codes: set[str]) -> dict[str, str]:
    text = raw.strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    out: dict[str, str] = {}
    for code, val in data.items():
        if code not in expected_codes:
            continue
        if val is None:
            continue
        s = str(val).strip()
        if s:
            out[code] = s
    return out


def attr_response_format(expected_codes: set[str]) -> dict:
    """D-LLM-FAILURE-RATE #1 — a LOOSE json_schema forcing the output to be a JSON
    OBJECT of string values keyed by the expected attribute codes (exactly what
    ``parse_translation_response`` consumes). ``additionalProperties:false`` matches
    the prompt's "do not add keys beyond those provided". Kills the malformed-JSON
    parse failures (the "Expecting ',' delimiter" class that fails an entity).
    Passed as ``response_format``; a model that rejects it is retried without it."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "translated_attributes",
            "schema": {
                "type": "object",
                "properties": {c: {"type": "string"} for c in sorted(expected_codes)},
                "additionalProperties": False,
            },
        },
    }


# bug #8 — per-entity output budget. The worker previously hard-capped max_tokens at a
# flat 4096 regardless of glossary size; a many-attribute / long-description entity exceeded
# it, truncating the structured JSON mid-output → parse_translation_response fails → the
# entity is marked failed (the "translation glossary usually fails" report). This budget
# mirrors the REAL payload (the actual attribute VALUES being translated) — unlike the
# wizard estimator below, whose flat attr_count*60 is blind to value length.
_OUTPUT_BUDGET_FLOOR = 4096      # never below the old default → no regression for small entities
_TRANSLATION_EXPANSION = 3.0     # a translated value can be ~3x the source token count (CJK→Latin worst case)
_PER_ATTR_JSON_OVERHEAD = 8      # the "code": and surrounding punctuation per key
_ENVELOPE_TOKENS = 64            # outer braces + a safety base


def entity_output_budget(
    attributes: list[dict[str, Any]],
    *,
    floor: int = _OUTPUT_BUDGET_FLOOR,
    ceiling: int = 32768,
) -> int:
    """Derive a max_tokens output budget for translating ONE entity's attributes.

    The model returns a JSON object ``{code: translated_value}``. A translated value's
    token count tracks its source value's (translation neither shrinks nor grows it
    unboundedly); ``_TRANSLATION_EXPANSION`` covers the CJK→Latin worst case where one
    CJK char (~0.67 tokens) becomes several Latin tokens. Clamped to ``[floor, ceiling]``:
    the floor keeps the old 4096 default for small entities (no regression); the ceiling
    guards a pathological entity from requesting an absurd budget — true attribute
    chunking across calls is the separate #26 work, not this fix.
    """
    total = _ENVELOPE_TOKENS
    for attr in attributes:
        val = str(attr.get("original_value") or "")
        total += int(estimate_tokens(val) * _TRANSLATION_EXPANSION)
        total += estimate_tokens(str(attr.get("code") or "")) + _PER_ATTR_JSON_OVERHEAD
    return max(floor, min(total, ceiling))


def estimate_glossary_translate_cost(entity_count: int, attr_count: int) -> dict:
    """Heuristic cost estimate for the wizard confirm step."""
    llm_calls = max(entity_count, 1)
    est_in = attr_count * 80 + entity_count * 120
    est_out = attr_count * 60
    return {
        "estimated_input_tokens": est_in,
        "estimated_output_tokens": est_out,
        "estimated_total_tokens": est_in + est_out,
        "llm_calls": llm_calls,
        "entity_count": entity_count,
        "attr_count": attr_count,
    }
