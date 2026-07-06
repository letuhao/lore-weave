"""D-CANON-CHECK-SDK-UNIFY — shared symbolic-prefilter + LLM-judge plumbing.

Hoisted from two near-duplicate modules that grew independently:
`composition-service/app/engine/canon_check.py` (the original, checks a DRAFT
against the knowledge fact-for-check snapshot) and
`knowledge-service/app/extraction/canon_check.py` (a 2026-07-05 POC mirror,
checks CHAPTER TEXT being extracted against the KG's own gone-status). A
2026-07-06 diff of both found the pieces below byte-identical or
near-identical in shape; everything domain-specific (prompt wording, the
extra per-service candidate field, the top-level orchestration functions)
stays in each service's own `canon_check.py`, which imports this module for
the mechanical parts.

One real gap this unification fixes: the knowledge-service copy caught bare
`Exception` and manually indexed `job.result["messages"][0]["content"]`
instead of composition's more precise `LLMError` + `extract_judge_content`
handling. `extract_judge_text` below is that same load-bearing parsing logic
(memory: gateway responses are `messages[0].content`, not `result.content`),
now shared instead of re-invented per service.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

__all__ = [
    "SPAN_PAD",
    "find_span",
    "parse_judge_verdicts",
    "extract_judge_text",
    "build_judge_request",
    "apply_verdicts",
    "gone_entities_referenced",
    "CanonCandidateBase",
]

SPAN_PAD = 40  # chars of context either side of a match


def find_span(text: str, name: str, pad: int = SPAN_PAD) -> tuple[str, str] | None:
    """(matched_name, excerpt) if `name` occurs in `text`, else None. Word
    boundaries for ASCII names (avoids 'Al' matching inside 'Always'); plain
    lowercase containment for CJK/non-ASCII names (no \\b word boundary in
    CJK script)."""
    if not name or not name.strip():
        return None
    name = name.strip()
    idx = -1
    if name.isascii():
        m = re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE)
        if m:
            idx = m.start()
    else:
        idx = text.lower().find(name.lower())
    if idx < 0:
        return None
    start = max(0, idx - pad)
    end = min(len(text), idx + len(name) + pad)
    excerpt = ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
    return name, excerpt


def _balanced_json_objects(text: str) -> list[str]:
    """Every top-level balanced `{...}` substring in `text`, in order. A naive
    `first '{' .. last '}'` span breaks when a small local model "thinks out
    loud" and emits more than one JSON block in one response (observed live:
    a first, wrong `{"verdicts":[...]}` followed by prose starting with
    "Self-correction:" and a second, corrected block) — the naive span
    swallows the prose between them and fails to parse at all, silently
    discarding a perfectly good corrected answer. Scanning brace-by-brace
    (string-aware, so a `}` inside a quoted `why` doesn't miscount) isolates
    each object on its own."""
    objects: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_string = False
        escape = False
        start = i
        while i < n:
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    objects.append(text[start:i + 1])
                    i += 1
                    break
            i += 1
        else:
            break  # unterminated object — stop scanning
    return objects


def parse_judge_verdicts(content: str) -> dict[str, dict[str, Any]]:
    """`{entity_id: {violated, why}}` from the judge's JSON reply; tolerant of
    a markdown fence, surrounding prose, and (see `_balanced_json_objects`)
    more than one JSON block in one response — takes the LAST block that
    parses into a `{"verdicts": [...]}` shape, treating a model's own
    self-correction as its final answer. Empty dict on any hard parse
    failure — the caller treats a missing entity_id as `confirmed=None`
    (advisory), never a crash."""
    if not content:
        return {}
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text).rstrip("`").strip()
    obj = None
    for candidate in reversed(_balanced_json_objects(text)):
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict) and "verdicts" in parsed:
            obj = parsed
            break
    if obj is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for v in (obj.get("verdicts") or []) if isinstance(obj, dict) else []:
        if isinstance(v, dict) and v.get("entity_id") is not None:
            out[str(v["entity_id"])] = {
                "violated": bool(v.get("violated", False)),
                "why": v.get("why") if isinstance(v.get("why"), str) else "",
            }
    return out


def extract_judge_text(result: dict[str, Any] | None) -> str:
    """Read a gateway completion's text from a terminal Job result.

    LOAD-BEARING: the content is at `result["messages"][0]["content"]`, NOT
    `result["content"]`. Returns "" when absent so a malformed/empty frame
    degrades to unjudged rather than crashing the caller."""
    if not isinstance(result, dict):
        return ""
    messages = result.get("messages") or []
    if messages and isinstance(messages[0], dict):
        return messages[0].get("content", "") or ""
    return ""


def build_judge_request(
    messages: list[dict[str, str]],
    *,
    usage_purpose: str,
    extractor: str,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """The shared judge-call request shape (both services' proven degrade-safe
    defaults): text response format, temperature 0, thinking disabled. Returns
    `{"input": ..., "job_meta": ...}` — splat into `llm.submit_and_wait(...)`."""
    return {
        "input": {
            "messages": messages,
            "response_format": {"type": "text"},
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "reasoning_effort": "none",
            "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
        },
        "job_meta": {"usage_purpose": usage_purpose, "extractor": extractor},
    }


def apply_verdicts(candidates: list[Any], verdicts: dict[str, dict[str, Any]]) -> None:
    """Mutate each candidate's `confirmed`/`source`/`why` in place from the
    judge's verdict dict, keyed by `entity_id` (both services' candidate
    models carry this field). A candidate the judge omits is left untouched
    (`confirmed` stays whatever the caller set, normally None — advisory)."""
    for c in candidates:
        v = verdicts.get(c.entity_id)
        if v is not None:
            c.confirmed = v["violated"]
            c.source = "llm_judge"
            c.why = v["why"]


def gone_entities_referenced(
    text: str,
    snapshot: dict[str, Any] | None,
    *,
    extra_field: str | None = None,
) -> list[dict[str, Any]]:
    """Symbolic pre-filter: every `gone` entity in `snapshot` whose name (or
    canonical_name) appears in `text`. Empty when `text`/`snapshot` is absent
    (degrades to advisory — an outage never blocks). De-duped per entity (the
    first matching name form wins). Returns raw dicts (`entity_id`, `name`,
    `span`, `matched`, + `extra_field` if given) — each service wraps these
    into its own typed candidate model with its own extra domain field
    (composition: `glossary_entity_id`; knowledge: `gone_from_order`)."""
    if not text or not snapshot:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ent in snapshot.get("entities") or []:
        if not isinstance(ent, dict) or ent.get("status") != "gone":
            continue
        eid = ent.get("entity_id")
        if not eid or eid in seen:
            continue
        for name in (ent.get("name"), ent.get("canonical_name")):
            hit = find_span(text, name) if isinstance(name, str) else None
            if hit is None:
                continue
            matched, span = hit
            row: dict[str, Any] = {
                "entity_id": eid, "name": ent.get("name"),
                "span": span, "matched": matched,
            }
            if extra_field:
                row[extra_field] = ent.get(extra_field)
            out.append(row)
            seen.add(eid)
            break
    return out


class CanonCandidateBase(BaseModel):
    """The 8 fields both services' candidate models share. Each service
    subclasses this adding its own extra field and its own `kind` default
    (e.g. `kind: str = "gone_entity_present"`)."""

    kind: str
    source: str = "score_symbolic"   # vs "llm_judge"
    entity_id: str
    name: str | None = None
    status: str = "gone"
    span: str = ""                   # excerpt of the text around the match
    matched: str = ""                # the name form that matched
    confirmed: bool | None = None    # set by the judge; None = symbolic-only (advisory)
    why: str = ""
