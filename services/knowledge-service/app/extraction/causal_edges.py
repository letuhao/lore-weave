"""D-W10-ARC-CONFORMANCE-SUCCESSION (Feature 2) — causal-edge inference over :Event.

Infers `(:Event)-[:CAUSES]->(:Event)` edges from the ordered timeline so deep
arc-conformance can upgrade a legal succession transition from *structural* (the order
respects the `precedes` graph) to *causally verified* (the prose actually shows motif A's
beat causing motif B's). The LLM reads a sliding WINDOW of ordered events and names which
earlier event directly causes/enables which later one (forward links only).

Cost is bounded by running ONLY over the caller-filtered event set (in practice the
motif-tagged subset — the arc-relevant beats), a window cap, and a hard window-count cap.

ADVISORY / UNCALIBRATED: NEVER raises — an outage / junk output yields fewer (or no) edges.
LLM via the SDK (`operation='chat'` → provider-registry; no provider SDK import; model_ref
passed in). Pure `build_messages` / `parse_edges` are the test surface.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a narrative-causality analyst. Given story EVENTS in reading order, you identify "
    "DIRECT causal links: which earlier event directly CAUSES or ENABLES a later one. Only "
    "forward links (the cause must appear before the effect). Reply with STRICT JSON only: a "
    "list of [cause_id, effect_id] pairs. No prose, no code fence."
)

_WINDOW = 12          # events per LLM call
_STRIDE = 6           # overlap so a cross-boundary cause→effect isn't missed
_MAX_WINDOWS = 40     # hard cap on LLM calls per request (cost backstop)


def build_messages(window: list[dict[str, Any]]) -> list[dict[str, str]]:
    """PURE — chat messages for one window of ORDERED events (``[{id,title,summary?}]``)."""
    lines = []
    for i, e in enumerate(window):
        summ = (e.get("summary") or "").strip()
        lines.append(f"{i + 1}. id={e['id']} | {e.get('title', '')}"
                     + (f" — {summ}" if summ else ""))
    user = ("EVENTS in reading order:\n" + "\n".join(lines)
            + "\n\nReturn JSON [[cause_id, effect_id], …] for the DIRECT causal links "
              "(cause must appear before effect).")
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
        i, j = s.find("["), s.rfind("]")
        if 0 <= i < j:
            try:
                return json.loads(s[i:j + 1])
            except (json.JSONDecodeError, ValueError):
                return None
        return None


def parse_edges(
    content: str, *, order_index: dict[str, int], window_ids: set[str],
) -> list[tuple[str, str]]:
    """PURE — parse ``[[cause_id, effect_id], …]``, keeping ONLY pairs where both ids are in
    the window AND the cause is strictly EARLIER than the effect in the global reading order
    (drops self-loops, backward links, and ids the model invented). Tolerates a
    ``{"edges":[…]}`` / ``{"pairs":[…]}`` wrapper or a bare list."""
    obj = _loads_lenient(content)
    if isinstance(obj, dict):
        obj = obj.get("edges") or obj.get("pairs") or []
    if not isinstance(obj, list):
        return []
    out: list[tuple[str, str]] = []
    for pair in obj:
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
            continue
        a, b = pair
        if (a in window_ids and b in window_ids and a != b
                and order_index.get(a, -1) < order_index.get(b, -1)):
            out.append((a, b))
    return out


def _job_content(job: Any) -> str:
    result = getattr(job, "result", None) or {}
    msgs = result.get("messages") or []
    if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
        return msgs[0].get("content", "") or ""
    return ""


async def infer_causal_edges(
    llm: Any, *, user_id: str, model_source: str, model_ref: str,
    events: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """Infer `(cause_id, effect_id)` edges over the ORDERED ``events`` (already filtered +
    event-order-sorted by the caller). Slides a window with overlap, ≤ ``_MAX_WINDOWS`` LLM
    calls. ADVISORY: NEVER raises; dedupes. Returns sorted unique pairs."""
    if len(events) < 2:
        return []
    order_index = {e["id"]: i for i, e in enumerate(events)}
    edges: set[tuple[str, str]] = set()
    windows = 0
    for start in range(0, len(events), _STRIDE):
        if windows >= _MAX_WINDOWS:
            logger.warning("causal-edges: hit window cap %d — truncating", _MAX_WINDOWS)
            break
        window_ev = events[start:start + _WINDOW]
        if len(window_ev) < 2:
            break
        windows += 1
        window_ids = {e["id"] for e in window_ev}
        try:
            job = await llm.submit_and_wait(
                user_id=user_id, operation="chat", model_source=model_source,
                model_ref=model_ref,
                input={"messages": build_messages(window_ev),
                       "temperature": 0.0, "max_tokens": 800},
                job_meta={"extractor": "causal_edges"},
            )
        except Exception as exc:
            logger.warning("causal-edges window failed: %r", exc)
            continue
        if getattr(job, "status", None) != "completed":
            continue
        edges.update(parse_edges(
            _job_content(job), order_index=order_index, window_ids=window_ids))
        if start + _WINDOW >= len(events):
            break
    return sorted(edges)
