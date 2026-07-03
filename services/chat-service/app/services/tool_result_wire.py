"""L3 (Context Budget Law §6a) — concise tool-result wire serialization.

Single funnel for every model-facing tool-result ``content`` string in the chat
turn loop (``stream_service._stream_with_tools`` + the resume path). Two jobs:

1. ``ensure_ascii=False`` — kill the ``\\uXXXX`` tax. Under Python's default
   ``ensure_ascii=True`` a Vietnamese ``Lâm Uyển`` serializes to
   ``L\\u00e2m Uy\\u1ec3n`` — a ~2–3× byte inflation on VI/CJK content that the
   model then pays for as input tokens (the 146K case study, spec §1).
2. drop-``None`` — omit fields whose value is ``null`` (the common MCP
   optional-field padding), recursively, WITHOUT dropping semantically-meaningful
   values. Empty containers are DELIBERATELY KEPT: ``{"results": []}`` is a
   "searched, found nothing" signal the model must still see, and ``0`` / ``False``
   / ``""`` are meaningful scalars (``{"success": false}`` must survive).

This affects ONLY the bytes the model reads. The FE ``result`` chunk and DB
persistence use the raw dict on separate seams, so trimming here never changes
what the UI shows or what is stored.

One helper, one language, zero domain-tool edits — fixes the wire for all 94
MCP tools at once (spec §14a; this is tier **T0**).
"""

from __future__ import annotations

import json
from typing import Any


def prune_none(value: Any) -> Any:
    """Recursively drop dict keys whose value is ``None``.

    Empty containers (``{}``, ``[]``) and falsy scalars (``0``, ``False``, ``""``)
    are preserved — see the module docstring for why. Lists recurse element-wise
    (indices are preserved; ``None`` elements are kept, since a list position can
    be load-bearing).
    """
    if isinstance(value, dict):
        return {k: prune_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [prune_none(v) for v in value]
    return value


def tool_result_content(payload: Any) -> str:
    """Serialize a tool result into the model-facing ``content`` string (L3).

    ``default=str`` is a robustness belt (payloads are post-JSON-parse from the
    gateway envelope and already pure-JSON, but locally-built payloads —
    subagent, compose_prose — could carry a stray non-JSON type; better to
    stringify than crash the turn).
    """
    return json.dumps(prune_none(payload), ensure_ascii=False, default=str)
