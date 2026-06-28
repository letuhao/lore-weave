"""D-W10-ARC-CONFORMANCE-SUCCESSION (Feature 1) — realized-motif classifier over :Event.

Tags each event with WHICH arc-placement motif it realizes (by `motif_code`), classified
from the event's title+summary+participants against the arc's placement motifs (code + name
+ summary) — so deep arc-conformance can reconstruct the realized motif ORDER from prose and
check it against the `precedes` legal-succession graph. Sibling of `thread_tag.py` (same
recipe — see that module); writes `:Event.realized_motif_code`.

ADVISORY / UNCALIBRATED: an LLM classifier with no gold set; output feeds the ADVISORY deep
succession dim, never a hard gate. LLM via the SDK (`operation='chat'` → provider-registry;
no provider SDK import; `model_ref` passed in). NEVER raises — an outage/junk output degrades
to "untagged" (the motif_beat fallback holds).
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a narrative-structure analyst. Each EVENT below is one beat of a story. You "
    "decide which MOTIF (a reusable narrative device — e.g. a face-slap reversal, a sworn "
    "oath) the event realizes, choosing ONLY from the motif codes provided. If an event "
    'realizes none of them, use "none". Reply with STRICT JSON only: an object mapping each '
    "event id to its chosen motif code. No prose, no code fence."
)

_MAX_EVENTS_PER_CALL = 50

# Size the output budget to the batch so a full batch's `{id: code}` JSON can't truncate
# (the batch would otherwise degrade to untagged) — see thread_tag (D-THREAD-TAG-BATCH-TOKENS).
_BASE_OUTPUT_TOKENS = 256
_TOKENS_PER_EVENT = 48


def _max_tokens_for(batch_len: int) -> int:
    return _BASE_OUTPUT_TOKENS + _TOKENS_PER_EVENT * batch_len


def build_messages(events: list[dict[str, Any]], motifs: list[dict[str, Any]]) -> list[dict[str, str]]:
    """PURE — chat messages for one classify batch. ``events``: ``[{id,title,summary?,
    participants?}]``; ``motifs``: ``[{code,name?,summary?}]`` (the arc's placement motifs)."""
    motif_lines = "\n".join(
        f"- {m['code']}: {m.get('name') or m['code']}"
        + (f" — {m['summary']}" if m.get("summary") else "")
        for m in motifs if m.get("code"))
    ev_blocks = []
    for e in events:
        parts = ", ".join(e.get("participants") or [])
        summ = (e.get("summary") or "").strip()
        block = f'id={e["id"]}\n  title: {e.get("title", "")}\n'
        if summ:
            block += f"  summary: {summ}\n"
        if parts:
            block += f"  participants: {parts}\n"
        ev_blocks.append(block)
    user = (
        'MOTIFS (use these codes only, or "none"):\n' + motif_lines
        + "\n\nEVENTS:\n" + "\n".join(ev_blocks)
        + "\n\nReturn JSON {event_id: motif_code} for every event id listed above."
    )
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


def parse_assignments(content: str, *, valid_codes: set[str], event_ids: set[str]) -> dict[str, str]:
    """PURE — parse ``{id: motif_code}`` JSON, keeping ONLY rows whose id is a real event in
    this batch AND whose code is a legal placement code. ``"none"``/unknown codes/unknown ids
    are dropped (never fabricate a motif the arc didn't place)."""
    obj = _loads_lenient(content)
    if not isinstance(obj, dict):
        return {}
    return {k: v for k, v in obj.items()
            if k in event_ids and isinstance(v, str) and v in valid_codes}


def _job_content(job: Any) -> str:
    result = getattr(job, "result", None) or {}
    msgs = result.get("messages") or []
    if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
        return msgs[0].get("content", "") or ""
    return ""


async def classify_event_motifs(
    llm: Any, *, user_id: str, model_source: str, model_ref: str,
    events: list[dict[str, Any]], motifs: list[dict[str, Any]],
) -> dict[str, str]:
    """Classify events → ``{event_id: motif_code}``, batched. ADVISORY: NEVER raises — an LLM
    failure / non-completed job / unparseable output yields a partial (or empty) map."""
    valid_codes = {m["code"] for m in motifs if m.get("code")}
    if not valid_codes or not events:
        return {}
    out: dict[str, str] = {}
    for start in range(0, len(events), _MAX_EVENTS_PER_CALL):
        batch = events[start:start + _MAX_EVENTS_PER_CALL]
        batch_ids = {e["id"] for e in batch}
        try:
            job = await llm.submit_and_wait(
                user_id=user_id, operation="chat", model_source=model_source,
                model_ref=model_ref,
                input={"messages": build_messages(batch, motifs),
                       "temperature": 0.0, "max_tokens": _max_tokens_for(len(batch))},
                job_meta={"extractor": "realized_motif"},
            )
        except Exception as exc:
            logger.warning("motif-tag classify batch failed: %r", exc)
            continue
        if getattr(job, "status", None) != "completed":
            logger.warning("motif-tag job not completed: %s", getattr(job, "status", "?"))
            continue
        out.update(parse_assignments(
            _job_content(job), valid_codes=valid_codes, event_ids=batch_ids))
    return out
