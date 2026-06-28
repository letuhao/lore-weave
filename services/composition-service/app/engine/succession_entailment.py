"""D-SUCCESSION-ENTAILMENT-JUDGE — the deepest succession-verification layer.

For each LEGAL precedes transition A→B among the arc's placement motifs, an LLM judge
decides whether A's TEXTUAL effects literally entail B's preconditions — i.e. does what
motif A leaves behind actually SET UP what motif B needs? This refines the deep succession
dim beyond the structural (precedes graph) and causal (`:CAUSES` edge) signals: a legal,
caused transition can STILL be a non-sequitur if A's effects don't establish B's premises.

Mirrors the tag-classifier recipe (see `extraction/thread_tag.py` in knowledge-service):
pure `build_messages` / `parse_verdicts` + an advisory batched `judge_entailments` loop that
NEVER raises — an outage / junk output degrades the transition to structural-only (the edge
just doesn't get `entailed`). ADVISORY / UNCALIBRATED: feeds the dim's `entailed` count, never
a hard gate. The LLM call routes through the SDK (`operation='chat'`) → provider-registry (the
provider-gateway invariant; NO provider SDK import, the caller passes the BYOK `model_ref`).
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a narrative-logic analyst. For each EDGE A→B you are given motif A's EFFECTS "
    "(what A leaves true in the story) and motif B's PRECONDITIONS (what must be true for B "
    "to occur). Decide whether A's effects ENTAIL B's preconditions — i.e. whether A's "
    "outcome plausibly establishes the premises B needs. Reply with STRICT JSON only: an "
    "object mapping each edge id to true (entailed) or false. No prose, no code fence."
)

# Cost-bound a single judge call; more edges loop over batches.
_MAX_EDGES_PER_CALL = 20
_BASE_OUTPUT_TOKENS = 128
_TOKENS_PER_EDGE = 24


def _max_tokens_for(batch_len: int) -> int:
    return _BASE_OUTPUT_TOKENS + _TOKENS_PER_EDGE * batch_len


def edge_id(from_code: str, to_code: str) -> str:
    """The stable id for an A→B transition (the JSON key the judge maps)."""
    return f"{from_code}->{to_code}"


def _texts(items: list[Any] | None) -> str:
    """Flatten a freeform preconditions/effects JSONB list into a readable phrase. Each entry
    is a string or a dict; prefer a description-ish key, else join its scalar values. Tolerant
    by design — these fields are author/LLM-authored and loosely shaped."""
    out: list[str] = []
    for it in items or []:
        if isinstance(it, str):
            if it.strip():
                out.append(it.strip())
        elif isinstance(it, dict):
            val: str | None = None
            for k in ("desc", "description", "text", "condition", "effect", "label", "state"):
                v = it.get(k)
                if isinstance(v, str) and v.strip():
                    val = v.strip()
                    break
            if val is None:
                val = "; ".join(str(v) for v in it.values()
                                if isinstance(v, (str, int, float)) and str(v).strip())
            if val:
                out.append(val)
    return "; ".join(out)


def build_messages(edges: list[dict[str, Any]]) -> list[dict[str, str]]:
    """PURE — the chat messages for one judge batch. ``edges``:
    ``[{from_code, to_code, from_name?, to_name?, from_effects, to_preconditions}]`` (the
    *_effects / *_preconditions are the raw JSONB lists). Lists each edge with A's effects +
    B's preconditions and asks for ``{edge_id: bool}`` over exactly those ids."""
    blocks = []
    for e in edges:
        eid = edge_id(e["from_code"], e["to_code"])
        eff = _texts(e.get("from_effects")) or "(none stated)"
        pre = _texts(e.get("to_preconditions")) or "(none stated)"
        blocks.append(
            f'EDGE id={eid}\n'
            f'  A ({e.get("from_name") or e["from_code"]}) effects: {eff}\n'
            f'  B ({e.get("to_name") or e["to_code"]}) preconditions: {pre}\n')
    user = ("EDGES:\n" + "\n".join(blocks)
            + "\n\nReturn JSON {edge_id: true|false} for every edge id listed above "
              "(true = A's effects entail B's preconditions).")
    return [{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": user}]


def _loads_lenient(content: str) -> Any:
    s = (content or "").strip()
    if s.startswith("```"):
        parts = s.split("```")
        s = parts[1] if len(parts) > 1 else ""
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
        s = s.strip()
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        i, j = s.find("{"), s.rfind("}")
        if 0 <= i < j:
            try:
                return json.loads(s[i:j + 1])
            except (json.JSONDecodeError, ValueError):
                return None
        return None


def parse_verdicts(content: str, *, valid_edge_ids: set[str]) -> dict[str, bool]:
    """PURE — parse ``{edge_id: bool}`` JSON, keeping ONLY ids in this batch with a real
    boolean (accepts the common ``true/false`` string forms). Unknown ids / non-bool values
    are dropped — never fabricate an entailment verdict."""
    obj = _loads_lenient(content)
    if not isinstance(obj, dict):
        return {}
    out: dict[str, bool] = {}
    for k, v in obj.items():
        if k not in valid_edge_ids:
            continue
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, str) and v.strip().lower() in ("true", "false"):
            out[k] = v.strip().lower() == "true"
    return out


def _job_content(job: Any) -> str:
    result = getattr(job, "result", None) or {}
    msgs = result.get("messages") or []
    if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
        return msgs[0].get("content", "") or ""
    return ""


async def judge_entailments(
    llm: Any, *, user_id: str, model_source: str, model_ref: str,
    edges: list[dict[str, Any]],
) -> set[tuple[str, str]]:
    """Judge each A→B edge → the set of ``(from_code, to_code)`` pairs whose effects entail
    preconditions, batching to ``_MAX_EDGES_PER_CALL``. ADVISORY: NEVER raises — an LLM
    failure / non-completed job / unparseable output drops those edges (structural-only)."""
    if not edges:
        return set()
    code_by_eid = {edge_id(e["from_code"], e["to_code"]): (e["from_code"], e["to_code"])
                   for e in edges}
    entailed: set[tuple[str, str]] = set()
    for start in range(0, len(edges), _MAX_EDGES_PER_CALL):
        batch = edges[start:start + _MAX_EDGES_PER_CALL]
        batch_ids = {edge_id(e["from_code"], e["to_code"]) for e in batch}
        try:
            job = await llm.submit_and_wait(
                user_id=user_id, operation="chat", model_source=model_source,
                model_ref=model_ref,
                input={"messages": build_messages(batch), "temperature": 0.0,
                       "max_tokens": _max_tokens_for(len(batch))},
                job_meta={"extractor": "succession_entailment"},
            )
        except Exception as exc:  # advisory — an LLM outage never fails the report
            logger.warning("entailment judge batch failed: %r", exc)
            continue
        if getattr(job, "status", None) != "completed":
            logger.warning("entailment judge job not completed: %s", getattr(job, "status", "?"))
            continue
        for eid, ok in parse_verdicts(_job_content(job), valid_edge_ids=batch_ids).items():
            if ok and eid in code_by_eid:
                entailed.add(code_by_eid[eid])
    return entailed
