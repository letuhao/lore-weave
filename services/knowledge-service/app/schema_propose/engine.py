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

import json
import logging
import re

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

_MAX_OUTPUT_TOKENS = 2000

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


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of an LLM completion (tolerates ```json fences /
    leading prose). Raises ProposeError if no object parses."""
    s = (text or "").strip()
    # strip a ```json … ``` fence if present
    fence = re.search(r"```(?:json)?\s*(.+?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    # else grab the outermost {...}
    if not s.startswith("{"):
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            s = m.group(0)
    try:
        obj = json.loads(s)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProposeError(f"proposal was not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ProposeError("proposal JSON was not an object")
    return obj


def parse_proposal(content: str) -> SchemaProposal:
    """LLM text → validated SchemaProposal (drops malformed components, keeps the
    rest — a partial proposal is still useful to the human reviewer)."""
    obj = _extract_json(content)
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
        job = await llm_client.submit_and_wait(
            user_id=user_id,
            operation="chat",
            model_source=model_source,
            model_ref=model_ref,
            input={
                "messages": build_messages(premise, genre),
                "temperature": 0.3,
                "max_tokens": _MAX_OUTPUT_TOKENS,
            },
            chunking=None,
            job_meta={"usage_purpose": "kg_schema_propose", "extractor": "schema_propose"},
            transient_retry_budget=1,
        )
    except Exception as exc:  # SDK/transport — surface as a clean 502
        raise ProposeError(f"schema-propose LLM call failed: {exc}") from exc

    if getattr(job, "status", None) != "completed":
        code = job.error.code if getattr(job, "error", None) else "LLM_UNKNOWN_ERROR"
        raise ProposeError(f"schema-propose job ended status={getattr(job, 'status', '?')} ({code})")

    result = job.result or {}
    messages_out = result.get("messages") or []
    content = ""
    if isinstance(messages_out, list) and messages_out and isinstance(messages_out[0], dict):
        content = messages_out[0].get("content", "") or ""
    return parse_proposal(content)
