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

SCHEMA_TOKEN_BUDGET = 2000  # max schema tokens per LLM call (INPUT side)

# Output-side guard against finish_reason=length truncation. plan_kind_batches
# historically budgeted only the *schema* (input) tokens, so a book with many kinds
# packed 7+ kinds into one call — and the model's *output* (every entity × every
# attribute for all those kinds) blew past max_tokens, getting cut mid-JSON →
# unparseable → 0 entities. Output size scales with the number of kinds in a batch,
# so we also cap kinds-per-batch. With max_entities_per_kind entities × (attrs+5)
# fields each, ~3 kinds keeps a batch comfortably under the worker's max_tokens even
# on entity-dense chapters. (See D-EXTRACTION-CONSTRAINED-DECODING for the longer-term
# json_schema/grammar-constrained-decoding fix that also eliminates malformed JSON.)
MAX_KINDS_PER_BATCH = 3

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

        # Break the batch when EITHER the input schema budget OR the output-side
        # kinds cap would be exceeded — the latter prevents max_tokens truncation.
        over_schema = current_tokens + kind_tokens > SCHEMA_TOKEN_BUDGET
        over_kinds = len(current_batch) >= MAX_KINDS_PER_BATCH
        if (over_schema or over_kinds) and current_batch:
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
    *,
    block_hints: bool = False,
) -> str:
    """Build dynamic schema section for ONE BATCH of kinds.

    Security: Whitelist validates kind_codes and attr_codes against
    glossary-service metadata (design §S4). When ``block_hints``, the schema asks for an
    optional ``evidence_block`` (the ⟦B#⟧ number the evidence quote came from).
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
        if block_hints:
            # The ⟦B#⟧ block the evidence quote came from (a number, e.g. 3). The quote
            # itself must be the EXACT source text WITHOUT the ⟦B#⟧ marker.
            json_fields["evidence_block"] = "0"
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


def build_user_prompt(chapter_text: str, *, block_hints: bool = False) -> str:
    """Assemble the user prompt with chapter text. When ``block_hints``, the chapter is
    rendered as ⟦B#⟧-numbered paragraphs (the SAME segmentation the provenance validator
    uses) so the model can cite an ``evidence_block`` per quote — validated downstream."""
    if block_hints:
        from app.workers.extraction_provenance import build_block_offset_map

        blocks = build_block_offset_map(chapter_text)
        if blocks:
            chapter_text = "\n".join(
                f"⟦B{b.index}⟧ {chapter_text[b.start:b.end]}" for b in blocks
            )
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

    # Strip a markdown fence — closed OR unterminated. Truncation (finish_reason=
    # length) routinely cuts the closing ```, so a fence-only regex would miss the
    # body entirely and the salvageable partial array would be discarded. Prefer the
    # closed-fence body; otherwise just drop the opening fence line and continue.
    closed = _MARKDOWN_FENCE_RE.search(text)
    if closed:
        text = closed.group(1).strip()
    else:
        opener = re.match(r"```(?:json)?\s*", text)
        if opener:
            text = text[opener.end():].strip()

    # Everything before the first array opener is prose/reasoning.
    start = text.find("[")
    if start == -1:
        return None
    text = text[start:]

    # Complete + well-formed array → return as-is. We re-validate here (not just
    # endswith "]") because the old greedy regex could over-capture to an inner "]"
    # and yield malformed JSON; on any parse failure we fall through to repair.
    if text.endswith("]"):
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

    # Truncated or malformed — close the array at the last COMPLETE object so the
    # entities the model finished before being cut off are still recovered.
    return _repair_truncated_array(text)


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


@dataclass
class ParseStats:
    """Signals the OBS batch-outcome taxonomy needs that a bare entity list can't
    carry (extraction-pipeline §8.3 / INV-F15). ``raw_count`` is how many entries the
    model's array held BEFORE validation — the discriminator between *empty_valid* (the
    model correctly returned ``[]``) and *validation_rejected* (it returned entities that
    were all rejected, e.g. kind mismatch). ``parse_ok`` is False when no JSON array could
    be parsed at all (garbage / prose / mid-truncation that even repair couldn't close)."""

    raw_count: int = 0
    parse_ok: bool = False


def parse_and_validate(
    response_text: str,
    kind_batch: list[str],
    extraction_profile: dict[str, dict[str, str]],
) -> list[dict]:
    """Parse + validate LLM output → the validated entity list (back-compat wrapper)."""
    entities, _ = parse_and_validate_with_stats(response_text, kind_batch, extraction_profile)
    return entities


def parse_and_validate_with_stats(
    response_text: str,
    kind_batch: list[str],
    extraction_profile: dict[str, dict[str, str]],
) -> tuple[list[dict], ParseStats]:
    """Parse LLM output and validate against extraction profile, returning the validated
    entities AND a ``ParseStats`` (raw pre-validation count + parse-success) so the worker
    can classify the batch outcome (OBS/M2). The validation logic is unchanged.

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
        return [], ParseStats(raw_count=0, parse_ok=False)

    # Step 1: parse JSON
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        log.warning("extraction parse failed: invalid JSON (extracted len=%d)", len(json_text))
        return [], ParseStats(raw_count=0, parse_ok=False)

    if not isinstance(data, list):
        if isinstance(data, dict):
            data = [data]
        else:
            log.warning("extraction parse: expected array, got %s", type(data).__name__)
            return [], ParseStats(raw_count=0, parse_ok=False)

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
            if key in ("kind", "name", "evidence", "evidence_block", "relevance"):
                continue
            if key in allowed_attrs:
                attrs[key] = val

        out = {
            "kind_code": kind,
            "name": name,
            "attributes": attrs,
            "evidence": entry.get("evidence", ""),
            "relevance": entry.get("relevance", "appears"),
        }
        # PROV/M3 — carry the model's optional block citation (validated downstream).
        if "evidence_block" in entry:
            out["evidence_block"] = entry.get("evidence_block")
        validated.append(out)

    log.info("extraction parsed: %d valid entities from %d raw entries", len(validated), len(data))
    return validated, ParseStats(raw_count=len(data), parse_ok=True)


# ── Cost estimation ──────────────────────────────────────────────────────────


# Reasoning models emit hidden reasoning tokens that count toward OUTPUT, so a higher
# reasoning_effort costs MORE than the entity JSON alone. These are rough multipliers on
# the per-call output reservation (the estimate is "estimate, not quote" — design §6.7.1);
# 'none'/'off' = no reasoning overhead. Keyed defensively (unknown → 1.0).
_EFFORT_OUTPUT_MULTIPLIER = {"none": 1.0, "off": 1.0, "low": 1.5, "medium": 2.5, "high": 4.0}


def estimate_extraction_cost(
    chapters: list[dict],
    extraction_profile: dict[str, dict[str, str]],
    kinds_metadata: list[dict],
    *,
    model_context_window: int | None = None,
    reasoning_effort: str = "none",
) -> dict:
    """Estimate token cost before starting an extraction job.

    Returns dict with estimated_input_tokens, estimated_output_tokens,
    estimated_total_tokens, llm_calls, chapters_count, batches_per_chapter — plus
    (when the planner is available) calls_per_chapter, unplannable, model_fit_warning.

    D-CACHE-PLANNER-WIRING (Part 1): SPLIT-AWARE via the two-phase planner (PLAN lane,
    `loreweave_extraction.plan`). The old heuristic charged `chapters × batches` calls each
    over the WHOLE chapter — blind to the windowing the executor actually does, so a chapter
    that exceeds the model context (→ N sub-chapter windows × batches) was undercounted N×.
    The planner models each (chapter × kind-batch) as a `chunk`-splittable unit and splits an
    oversized one into windows, so the quote tracks the executor's real call fan-out.

    `max_units_per_call=1` is LOAD-BEARING: in extraction the chapter/window text is injected
    PER kind-batch call (each batch is its own LLM call), NOT shared across packed units —
    so packing would double-count the shared text. One unit per call keeps the planner's
    per-unit input sum equal to extraction's real per-call input.

    Falls back to the flat heuristic if the planner SDK isn't importable (keeps the estimate
    working through any SDK-distribution drift — the old `D-SDK-DISTRIBUTION-SPLIT` blocker)."""
    batches = plan_kind_batches(extraction_profile, kinds_metadata)
    batches_per_chapter = len(batches)

    prompt_overhead = 200 + 250  # system template + known entities context
    schema_tokens = sum(
        20 + len(attrs) * 40
        for attrs in extraction_profile.values()
    )
    _effort_mult = _EFFORT_OUTPUT_MULTIPLIER.get(reasoning_effort or "none", 1.0)
    output_per_call = int(2000 * _effort_mult)  # ~30 entities × ~60 tokens, + reasoning overhead

    def _chapter_tokens(ch: dict) -> int:
        # text_length / 2 for CJK (rough); floor so an empty/short chapter still costs a call.
        text_len = ch.get("text_length", ch.get("byte_size", 4000))
        return max(text_len // 2, 500)

    try:
        from loreweave_extraction import (
            DEFAULT_MODEL_CONTEXT, ModelCaps, PlanRequest, Policy, Unit,
            effort_output_multiplier, plan,
        )

        # D-RE-EFFORT-COST-ESTIMATE: a reasoning model spends extra OUTPUT tokens on its thinking
        # trace, so the quote must grow with effort. The planner's per-call output RESERVATION
        # already scales by effort (Policy.reasoning_effort), but the reported `est_output` is the
        # sum of unit outputs — so scale the per-call output by the SAME multiplier here, and pass
        # the effort to Policy so the split/budget math stays consistent with the larger output.
        out_per_call = int(round(output_per_call * effort_output_multiplier(reasoning_effort)))
        units: list[Unit] = []
        for ci, ch in enumerate(chapters):
            cid = str(ch.get("chapter_id") or ch.get("id") or ci)
            unit_in = prompt_overhead + schema_tokens + _chapter_tokens(ch)
            for bi in range(batches_per_chapter):
                units.append(Unit(
                    id=f"{cid}:b{bi}", kind="extract", est_input=unit_in,
                    est_output=out_per_call, splittable=True, split_axis="chunk", group=cid,
                ))
        caps = ModelCaps(context_window=model_context_window or DEFAULT_MODEL_CONTEXT)
        p = plan(PlanRequest(
            pipeline="extraction", units=units, model=caps,
            policy=Policy(max_units_per_call=1, reasoning_effort=reasoning_effort),
        ))
        total_input = sum(c.est_input for c in p.calls)
        total_output = sum(c.est_output for c in p.calls)
        return {
            "estimated_input_tokens": total_input,
            "estimated_output_tokens": total_output,
            "estimated_total_tokens": total_input + total_output,
            "llm_calls": p.est_llm_calls,
            "chapters_count": len(chapters),
            "batches_per_chapter": batches_per_chapter,
            "calls_per_chapter": round(p.calls_per_chapter, 2),
            "unplannable": len(p.unplannable),
            "model_fit_warning": p.model_fit_warning,
        }
    except Exception as exc:  # noqa: BLE001
        # Planner SDK unavailable (ImportError — the D-SDK-DISTRIBUTION-SPLIT net) OR any
        # planner failure — degrade to the flat heuristic. A cost ESTIMATE must never fail
        # job creation; a windowing-blind number beats a 500.
        if not isinstance(exc, ImportError):
            log.warning("estimate_extraction_cost: planner failed (%s) — flat heuristic", exc)
        total_input = 0
        total_output = 0
        for ch in chapters:
            chapter_tokens = _chapter_tokens(ch)
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
