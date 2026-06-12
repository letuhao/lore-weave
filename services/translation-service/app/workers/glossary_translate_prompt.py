"""Prompt + parse helpers for glossary batch attribute translation."""
from __future__ import annotations

import json
import re
from typing import Any


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
