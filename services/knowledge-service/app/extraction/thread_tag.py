"""D-W10-ARC-CONFORMANCE-THREAD-TAG — narrative-thread classifier over :Event nodes.

Tags each event with a narrative-thread label (combat/romance/intrigue/…) drawn from a
CALLER-SUPPLIED vocabulary (the arc template's threads), classified from the event's
``title`` + ``summary`` + ``participants`` — no chapter re-read needed. This upgrades the
``motif_beat`` extractor's ``thread`` from the ``chapter_id`` proxy (Option A) to a real
narrative thread, so deep arc-conformance can measure realized thread-progression from prose.

ADVISORY / UNCALIBRATED: an LLM classifier with no gold set yet — its output feeds the
ADVISORY deep-conformance dimension, never a hard gate. The LLM call routes through the SDK
(``operation='chat'``) → provider-registry (the provider-gateway invariant; NO provider SDK
import here). It NEVER raises — an outage / bad output degrades to "untagged" so the
``motif_beat`` ``narrative_thread or chapter_id`` fallback keeps working.

The pure pieces (``build_messages`` / ``parse_assignments``) are the test surface; the
classify loop only adds batching + the SDK call + honest degradation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a narrative-structure analyst. You classify story EVENTS into one of a fixed "
    "set of NARRATIVE THREADS — parallel through-lines such as combat, romance, or intrigue. "
    'Use ONLY the thread keys provided. If an event fits none of them, use "none". '
    "Reply with STRICT JSON only: an object mapping each event id to its chosen thread key. "
    "No prose, no code fence."
)

# Cost-bound a single classify call; larger event sets loop over batches.
_MAX_EVENTS_PER_CALL = 60


def build_messages(events: list[dict[str, Any]], threads: list[dict[str, Any]]) -> list[dict[str, str]]:
    """PURE — the chat messages for one classify batch. ``events``:
    ``[{id, title, summary?, participants?}]``; ``threads``: ``[{key, label?}]``. The user
    message lists the legal thread keys then each event's id + title (+ summary/participants
    when present) and asks for ``{event_id: thread_key}`` JSON over exactly those ids."""
    thread_lines = "\n".join(
        f"- {t['key']}: {t.get('label') or t['key']}" for t in threads if t.get("key"))
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
        'THREADS (use these keys only, or "none"):\n' + thread_lines
        + "\n\nEVENTS:\n" + "\n".join(ev_blocks)
        + "\n\nReturn JSON {event_id: thread_key} for every event id listed above."
    )
    return [{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": user}]


def _loads_lenient(content: str) -> Any:
    """Parse model JSON tolerantly: strip a ```json fence, else grab the first {…} block."""
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


def parse_assignments(content: str, *, valid_keys: set[str], event_ids: set[str]) -> dict[str, str]:
    """PURE — parse the model's ``{id: thread}`` JSON, keeping ONLY rows whose id is a real
    event in this batch AND whose thread is a legal key. ``"none"`` / unknown keys / unknown
    ids are dropped — never fabricate a thread the caller didn't define."""
    obj = _loads_lenient(content)
    if not isinstance(obj, dict):
        return {}
    return {k: v for k, v in obj.items()
            if k in event_ids and isinstance(v, str) and v in valid_keys}


def _job_content(job: Any) -> str:
    result = getattr(job, "result", None) or {}
    msgs = result.get("messages") or []
    if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
        return msgs[0].get("content", "") or ""
    return ""


async def classify_event_threads(
    llm: Any, *, user_id: str, model_source: str, model_ref: str,
    events: list[dict[str, Any]], threads: list[dict[str, Any]],
) -> dict[str, str]:
    """Classify events → ``{event_id: thread_key}``, batching to ``_MAX_EVENTS_PER_CALL``.
    ADVISORY: NEVER raises — an LLM failure / non-completed job / unparseable output yields a
    partial (or empty) map, and the caller treats a missing id as untagged."""
    valid_keys = {t["key"] for t in threads if t.get("key")}
    if not valid_keys or not events:
        return {}
    assignments: dict[str, str] = {}
    for start in range(0, len(events), _MAX_EVENTS_PER_CALL):
        batch = events[start:start + _MAX_EVENTS_PER_CALL]
        batch_ids = {e["id"] for e in batch}
        try:
            job = await llm.submit_and_wait(
                user_id=user_id, operation="chat", model_source=model_source,
                model_ref=model_ref,
                input={"messages": build_messages(batch, threads),
                       "temperature": 0.0, "max_tokens": 1500},
                job_meta={"extractor": "narrative_thread"},
            )
        except Exception as exc:  # advisory — an LLM outage never fails tagging
            logger.warning("thread-tag classify batch failed: %r", exc)
            continue
        if getattr(job, "status", None) != "completed":
            logger.warning("thread-tag job not completed: %s", getattr(job, "status", "?"))
            continue
        assignments.update(parse_assignments(
            _job_content(job), valid_keys=valid_keys, event_ids=batch_ids))
    return assignments
