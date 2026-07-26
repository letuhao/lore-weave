"""M3b — propose a KG schema from a natural-language premise (single-shot LLM).

A NON-agentic generate pipeline (mirrors glossary wiki-gen): one LLM call turns a
premise into a STRUCTURED proposal ``{node_kinds, edge_types, fact_types}`` that the
human reviews + confirms; nothing is written here (propose-pattern — the FE adopts
the ticked components through the A1 add routes). Because it's a single generate
(the LLM doesn't call tools or reason multi-step), it's exempt from the MCP-first
invariant like translation/enrichment; an agent-facing MCP tool can wrap this same
engine later.

Model resolution: the caller supplies ``model_ref`` (a BYOK ``user_model`` id) — no
hardcoded model (no-hardcoded-model invariant); the LLM call goes through the SDK →
ai-gateway → provider-registry like every other knowledge LLM call.
"""

from __future__ import annotations

import logging

from loreweave_llm import StructuredGenerateError, parse_json_object, structured_generate
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# Bounded output budget for the single-shot proposal. structured_generate DISABLES
# hidden reasoning by default (reasoning="none" → chat_template_kwargs.{thinking:false}),
# closing the empty-prose footgun (reproduced live: Gemma-4 26B burned its budget on
# hidden reasoning → empty content → JSON parse error) — no local knob needed here.
_MAX_OUTPUT_TOKENS = 3000

_SYSTEM_PROMPT = """You design knowledge-graph SCHEMAS (ontologies) for stories.
Given a premise, propose the node kinds (entity types), edge types (relation types),
and fact types that a graph of this story would need.

Return ONLY a JSON object, no prose, in EXACTLY this shape:
{
  "node_kinds": [{"code": "character", "label": "Character"}],
  "edge_types": [{"code": "MENTOR_OF", "label": "mentor of",
                  "source_kinds": ["character"], "target_kinds": ["character"]}],
  "fact_types": [{"code": "ascension", "label": "Ascension"}]
}

Rules:
- node_kind `code`: lower_snake_case, singular (character, location, organization, artifact…).
- edge_type `code`: UPPER_SNAKE_CASE verb phrase (MENTOR_OF, MEMBER_OF, WIELDS…).
- edge `source_kinds`/`target_kinds`: arrays of node_kind codes you ALSO define above.
- fact_type `code`: lower_snake_case noun (birth, ascension, betrayal…).
- Propose 4-10 node kinds, 4-12 edge types, 0-6 fact types. Be specific to the premise.
- Output MUST be valid JSON and nothing else."""


class ProposedNodeKind(BaseModel):
    code: str
    label: str = ""


class ProposedEdgeType(BaseModel):
    code: str
    label: str = ""
    source_kinds: list[str] = Field(default_factory=list)
    target_kinds: list[str] = Field(default_factory=list)


class ProposedFactType(BaseModel):
    code: str
    label: str = ""


class SchemaProposal(BaseModel):
    node_kinds: list[ProposedNodeKind] = Field(default_factory=list)
    edge_types: list[ProposedEdgeType] = Field(default_factory=list)
    fact_types: list[ProposedFactType] = Field(default_factory=list)


class ProposeError(Exception):
    """The LLM call failed or returned unparseable output (router → 502)."""


def parse_proposal(content: str) -> SchemaProposal:
    """LLM text → validated SchemaProposal (drops malformed components, keeps the
    rest — a partial proposal is still useful to the human reviewer). Uses the
    SDK's shared tolerant JSON extractor (fences / leading prose)."""
    try:
        obj = parse_json_object(content)
    except StructuredGenerateError as exc:
        raise ProposeError(str(exc)) from exc
    try:
        return SchemaProposal.model_validate(obj)
    except ValidationError:
        # salvage: keep only the components that individually validate
        def _keep(items, model):
            out = []
            for it in items if isinstance(items, list) else []:
                try:
                    out.append(model.model_validate(it))
                except ValidationError:
                    continue
            return out

        return SchemaProposal(
            node_kinds=_keep(obj.get("node_kinds"), ProposedNodeKind),
            edge_types=_keep(obj.get("edge_types"), ProposedEdgeType),
            fact_types=_keep(obj.get("fact_types"), ProposedFactType),
        )


def build_messages(premise: str, genre: str | None) -> list[dict[str, str]]:
    user = premise.strip()
    if genre and genre.strip():
        user = f"Genre: {genre.strip()}\n\nPremise: {user}"
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


async def propose_schema(
    llm_client,
    *,
    user_id: str,
    premise: str,
    genre: str | None,
    model_ref: str,
    model_source: str = "user_model",
) -> SchemaProposal:
    """Single-shot LLM generate → validated proposal. Raises ProposeError on an
    LLM failure / non-completed job / unparseable output."""
    if not premise.strip():
        raise ProposeError("premise is empty")
    try:
        result = await structured_generate(
            llm_client,
            user_id=user_id,
            model_source=model_source,
            model_ref=model_ref,
            messages=build_messages(premise, genre),
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            job_meta={"usage_purpose": "kg_schema_propose", "extractor": "schema_propose"},
        )
    except StructuredGenerateError as exc:  # transport / non-completed / empty
        raise ProposeError(str(exc)) from exc
    return parse_proposal(result.content)
