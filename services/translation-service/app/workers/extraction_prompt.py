"""
GEP-BE-08: Extraction prompt builder + output parser.

Builds dynamic system prompts from extraction profile + attribute metadata.
Auto-batches kinds by schema token budget. Parses and validates LLM output.

Design reference: GLOSSARY_EXTRACTION_PIPELINE.md §6.2, §6.6, §6.8
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)

SCHEMA_TOKEN_BUDGET = 2000  # max schema tokens per LLM call

SYSTEM_TEMPLATE = """\
You are a literary entity extractor. Analyze the following {source_language} novel \
chapter and identify all named entities matching the types below.

IMPORTANT — Language rules:
- ALL output (names, descriptions, attribute values) MUST be in {source_language}.
- Do NOT translate anything into English or other languages.
- Extract names EXACTLY as written in the source text.
- Attribute values (description, appearance, etc.) must be written in {source_language}, \
summarizing what the source text says.

For each type, extract ONLY the listed attributes. Do not add extra fields.

For each entity, also provide an "evidence" field: a short EXACT QUOTE from the source \
text (in {source_language}) that best supports the entity's identification. Max 1 sentence.

{dynamic_schema}

Extract up to {max_entities_per_kind} most significant entities per type.
Prioritize entities with relevance "major" over "appears".

{known_entities_context}

General rules:
- Do NOT invent information not present in the text
- Merge aliases (e.g. different names for same entity → one entry)
- For pronouns referring to named characters, do not create separate entries
- "relevance": "major" if central to the chapter, "appears" if merely mentioned
- Output ONLY valid JSON array. No other text."""

USER_TEMPLATE = """\
Extract all named entities from this chapter:

---
{chapter_text}
---"""


@dataclass
class KindMeta:
    """Metadata for an entity kind from extraction-profile response."""
    code: str
    name: str
    attributes: list[dict]


def find_kind(kinds_metadata: list[dict], kind_code: str) -> dict | None:
    """Find kind metadata by code."""
    for k in kinds_metadata:
        if k.get("code") == kind_code:
            return k
    return None


def find_attr(kind_meta: dict, attr_code: str) -> dict | None:
    """Find attribute metadata by code within a kind."""
    for a in kind_meta.get("attributes", []):
        if a.get("code") == attr_code:
            return a
    return None


# ── Auto-batching ────────────────────────────────────────────────────────────


def plan_kind_batches(
    extraction_profile: dict[str, dict[str, str]],
    kinds_metadata: list[dict],
) -> list[list[str]]:
    """Group kinds into batches that fit within schema token budget.

    Returns list of batches, each batch is a list of kind_codes.
    Most books (3-5 kinds) → 1 batch (1 LLM call).
    """
    batches: list[list[str]] = []
    current_batch: list[str] = []
    current_tokens = 0

    for kind_code in extraction_profile:
        kind_meta = find_kind(kinds_metadata, kind_code)
        if kind_meta is None:
            continue
        attr_actions = extraction_profile[kind_code]
        # ~40 tokens per attribute description + ~20 tokens overhead per kind
        kind_tokens = 20 + len(attr_actions) * 40

        if current_tokens + kind_tokens > SCHEMA_TOKEN_BUDGET and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0

        current_batch.append(kind_code)
        current_tokens += kind_tokens

    if current_batch:
        batches.append(current_batch)

    return batches


# ── Prompt builder ───────────────────────────────────────────────────────────


def build_extraction_prompt(
    kind_batch: list[str],
    extraction_profile: dict[str, dict[str, str]],
    kinds_metadata: list[dict],
) -> str:
    """Build dynamic schema section for ONE BATCH of kinds.

    Security: Whitelist validates kind_codes and attr_codes against
    glossary-service metadata (design §S4).
    """
    valid_kind_codes = {k["code"] for k in kinds_metadata}

    sections: list[str] = []
    for kind_code in kind_batch:
        if kind_code not in valid_kind_codes:
            continue
        attr_actions = extraction_profile.get(kind_code, {})
        kind_meta = find_kind(kinds_metadata, kind_code)
        if kind_meta is None:
            continue

        valid_attr_codes = {a["code"] for a in kind_meta.get("attributes", [])}

        attr_lines: list[str] = []
        json_fields: dict[str, str] = {"kind": kind_code}

        for code, action in attr_actions.items():
            if code not in valid_attr_codes:
                continue
            if action == "skip":
                continue

            attr_meta = find_attr(kind_meta, code)
            if attr_meta is None:
                continue

            field_type = attr_meta.get("field_type", "text")
            is_required = attr_meta.get("is_required", False)
            description = attr_meta.get("description", "")
            auto_fill_prompt = attr_meta.get("auto_fill_prompt")

            parts = [f"- {code} ({field_type}"]
            if is_required:
                parts[0] += ", required"
            parts[0] += ")"

            if description:
                parts[0] += f": {description}"

            if auto_fill_prompt:
                parts.append(f"  Hint: {auto_fill_prompt}")

            attr_lines.append("\n".join(parts))
            json_fields[code] = "[...]" if field_type == "tags" else "..."

        # Special fields always included
        json_fields["evidence"] = "..."
        json_fields["relevance"] = "major|appears"

        sections.append(
            f"## {kind_code}\n"
            f"Attributes to extract:\n"
            + "\n".join(attr_lines) + "\n"
            + f"Output format: {json.dumps(json_fields, ensure_ascii=False)}"
        )

    return "\n\n".join(sections)


def build_known_entities_context(known_entities: list[dict]) -> str:
    """Build the known entities section for cross-chapter awareness.

    Input: list of dicts from GET /internal/books/{id}/known-entities
           Each has: name, kind_code, aliases, frequency
    """
    if not known_entities:
        return ""

    lines = [
        "Previously identified entities (use EXACT names below, do NOT create duplicates):"
    ]
    for ent in known_entities:
        name = ent.get("name", "")
        kind_code = ent.get("kind_code", "")
        aliases = ent.get("aliases", [])
        line = f"- {name} ({kind_code})"
        if aliases:
            line += f" — aliases: {', '.join(aliases)}"
        lines.append(line)

    lines.append("")
    lines.append("If you find new information about these entities, use their exact names above.")
    lines.append("If you find NEW entities not in this list, add them with new names.")
    return "\n".join(lines)


def build_system_prompt(
    dynamic_schema: str,
    source_language: str,
    known_entities_context: str = "",
    max_entities_per_kind: int = 30,
) -> str:
    """Assemble the full system prompt."""
    return SYSTEM_TEMPLATE.format(
        source_language=source_language,
        dynamic_schema=dynamic_schema,
        known_entities_context=known_entities_context,
        max_entities_per_kind=max_entities_per_kind,
    )


def build_user_prompt(chapter_text: str) -> str:
    """Assemble the user prompt with chapter text."""
    return USER_TEMPLATE.format(chapter_text=chapter_text)


# ── Output parser + validator ────────────────────────────────────────────────

_MARKDOWN_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")
_JSON_ARRAY_RE = re.compile(r"\[\s*\{[\s\S]*\}\s*\]")


def _extract_json_from_text(text: str) -> str | None:
    """Try to extract a JSON array from text that may contain reasoning/thinking.

    Reasoning models often embed JSON within their thinking output.
    Strategy: find markdown fences first, then try raw JSON array extraction,
    then handle truncated arrays (missing closing bracket).
    """
    text = text.strip()

    # Try markdown fences first
    fence_match = _MARKDOWN_FENCE_RE.search(text)
    if fence_match:
        return fence_match.group(1).strip()

    # Try to find a complete JSON array directly
    arr_match = _JSON_ARRAY_RE.search(text)
    if arr_match:
        return arr_match.group(0)

    # If starts with bracket, use as-is (may need closing bracket)
    if text.startswith("["):
        if text.endswith("]"):
            return text
        # Truncated array — try to repair by closing incomplete trailing entry
        return _repair_truncated_array(text)

    return None


def _repair_truncated_array(text: str) -> str:
    """Repair a truncated JSON array by finding the last complete object.

    When a reasoning model runs out of tokens, the JSON array may be cut off
    mid-object. We find the last complete `}` that closes an object and
    close the array there.
    """
    # Find the position of the last complete object (last `},` or `}`)
    last_complete = -1
    depth = 0
    in_string = False
    escape_next = False

    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                last_complete = i

    if last_complete > 0:
        repaired = text[:last_complete + 1] + "\n]"
        log.info("extraction: repaired truncated JSON array (cut at %d/%d chars)", last_complete + 1, len(text))
        return repaired

    return text + "\n]"  # fallback: just close it


def parse_and_validate(
    response_text: str,
    kind_batch: list[str],
    extraction_profile: dict[str, dict[str, str]],
) -> list[dict]:
    """Parse LLM output and validate against extraction profile.

    Steps (design §6.8):
    1. Extract JSON from response (handles markdown fences, reasoning text, raw arrays)
    2. Parse JSON array
    3. Validate + transform each entry (whitelist kind/attr codes)
    4. Strip extra fields
    """
    # Step 0: extract JSON from response text (may contain reasoning/thinking)
    json_text = _extract_json_from_text(response_text)
    if json_text is None:
        log.warning("extraction parse failed: no JSON array found in response (len=%d)", len(response_text))
        return []

    # Step 1: parse JSON
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        log.warning("extraction parse failed: invalid JSON (extracted len=%d)", len(json_text))
        return []

    if not isinstance(data, list):
        if isinstance(data, dict):
            data = [data]
        else:
            log.warning("extraction parse: expected array, got %s", type(data).__name__)
            return []

    valid_kinds = set(kind_batch)
    validated: list[dict] = []

    for entry in data:
        if not isinstance(entry, dict):
            continue

        kind = entry.get("kind", "")
        if kind not in valid_kinds:
            continue

        name = entry.get("name", "")
        if not name:
            continue

        # Build validated entity with only whitelisted attributes
        allowed_attrs = set(extraction_profile.get(kind, {}).keys())
        attrs = {}
        for key, val in entry.items():
            if key in ("kind", "name", "evidence", "relevance"):
                continue
            if key in allowed_attrs:
                attrs[key] = val

        validated.append({
            "kind_code": kind,
            "name": name,
            "attributes": attrs,
            "evidence": entry.get("evidence", ""),
            "relevance": entry.get("relevance", "appears"),
        })

    log.info("extraction parsed: %d valid entities from %d raw entries", len(validated), len(data))
    return validated


# ── Cost estimation ──────────────────────────────────────────────────────────


def estimate_extraction_cost(
    chapters: list[dict],
    extraction_profile: dict[str, dict[str, str]],
    kinds_metadata: list[dict],
) -> dict:
    """Estimate token cost before starting extraction job.

    Returns dict with estimated_input_tokens, estimated_output_tokens,
    estimated_total_tokens, llm_calls, chapters_count.
    """
    batches = plan_kind_batches(extraction_profile, kinds_metadata)
    batches_per_chapter = len(batches)

    prompt_overhead = 200 + 250  # system template + known entities context
    schema_tokens = sum(
        20 + len(attrs) * 40
        for attrs in extraction_profile.values()
    )
    output_per_call = 2000  # ~30 entities × ~60 tokens

    total_input = 0
    total_output = 0

    for ch in chapters:
        # Estimate chapter tokens: text_length / 2 for CJK (rough)
        text_len = ch.get("text_length", ch.get("byte_size", 4000))
        chapter_tokens = max(text_len // 2, 500)

        for _ in range(batches_per_chapter):
            total_input += prompt_overhead + schema_tokens + chapter_tokens
            total_output += output_per_call

    return {
        "estimated_input_tokens": total_input,
        "estimated_output_tokens": total_output,
        "estimated_total_tokens": total_input + total_output,
        "llm_calls": len(chapters) * batches_per_chapter,
        "chapters_count": len(chapters),
        "batches_per_chapter": batches_per_chapter,
    }
