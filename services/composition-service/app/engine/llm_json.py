"""One LLM call that expects JSON — with the shape enforced by the DECODER where the provider allows.

## Why this exists

Every JSON-expecting call in this service asked for `response_format: {"type": "text"}` and then
hand-parsed whatever came back. `provider-registry.forwardOptionalChatFields` has always forwarded
`response_format` (and `seed`) straight through to LM Studio, where llama.cpp enforces it at the
**grammar layer** — the capability was there and unused.

Measured 2026-07-28 over 18 labelled lines before any of this was written
(`docs/specs/2026-07-28-poc-material-read.md` §6d):

| | text + hand parser | schema-enforced |
|---|---|---|
| parse failures | 2 | **0** |
| macro F1 | 0.88 | 0.86 — *unchanged, within noise* |
| same seed, second run | — | **identical 18/18** |
| a ranking arm previously scored 0.00 | 1/4 | **3/4** |

The quality number is the least interesting row. **Determinism** is why this is worth doing: a fixed
seed reproducing a run means a change in a number is a change in the system rather than sampling
noise. And that last row is the cautionary one — an arm was dismissed **twice** as a model failure
when the model had been fine and the hand parser had not.

## The two rules that keep the constraint from becoming a new hole

1. **The post-parse filter STAYS.** A provider that ignores `response_format` must not silently pass
   a value the caller would have rejected. Enforcement is an optimisation on top of validation, never
   a replacement for it.
2. **A provider that REJECTS the schema falls back to free-form.** `response_format` support is not a
   platform requirement, so a 400 here degrades to exactly today's behaviour rather than failing the
   call. Worst case equals the status quo.

Both mirror `translation-service._entity_response_format`, which already did enum + fallback.

## The one way enforcement can be WORSE, and how to avoid it

A grammar cannot stop early in a valid place. Free-form, a model running low on budget can wrap up;
under a grammar it is compelled to keep emitting structure, so **truncation produces JSON that no
parser can recover** — live-observed here as an unterminated string when a schema with an open shape
met a too-small `max_tokens`.

So: keep `additionalProperties: False` wherever the caller reads a known set of fields, and size
`max_tokens` for the WHOLE shape rather than for the part that matters. Leave the shape open only
where the loose fields are genuinely wanted, and give those calls room.

## What NOT to use this for

Calls that return **prose** (`compress`, `stitch`, the drafting path). Wrapping generated narrative in
a JSON grammar would constrain the writing itself, which is the opposite of the point.
"""
from __future__ import annotations

import logging
from typing import Any, Sequence

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content

logger = logging.getLogger(__name__)

#: The thinking suppressor every JSON-expecting call in this service already uses. Imported lazily
#: at call time (see `_no_think`) to avoid a package-load cycle through `app.engine.compress`.
_NO_THINK_CACHE: dict[str, Any] | None = None


def _no_think() -> dict[str, Any]:
    global _NO_THINK_CACHE
    if _NO_THINK_CACHE is None:
        from app.engine.compress import _NO_THINK
        _NO_THINK_CACHE = dict(_NO_THINK)
    return _NO_THINK_CACHE


def json_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Wrap a bare JSON schema in the `response_format` envelope the gateway forwards."""
    return {"type": "json_schema", "json_schema": {"name": name, "schema": schema}}


def enum_of(values: Sequence[Any]) -> dict[str, Any]:
    """A closed set as a schema fragment, typed from its own members.

    Integers stay integers: a `tension` enum of 1..5 emitted as the string "3" would still need
    coercion, which is the post-hoc repair this whole change is removing.
    """
    vals = list(values)
    kind = "integer" if vals and all(isinstance(v, int) and not isinstance(v, bool) for v in vals) \
        else "string"
    return {"type": kind, "enum": vals}


def array_of(item: dict[str, Any], *, key: str = "items",
             min_items: int = 0, max_items: int | None = None) -> dict[str, Any]:
    """`{key: [item, …]}` — the shape almost every planning call actually wants.

    A top-level OBJECT rather than a bare array, deliberately: several models emit a bare array when
    asked for one and an object when not, and the existing tolerant parsers already accept both, so
    the object form loses nothing and gives the schema somewhere to hang a name.
    """
    arr: dict[str, Any] = {"type": "array", "items": item, "minItems": min_items}
    if max_items is not None:
        arr["maxItems"] = max_items
    return {"type": "object", "properties": {key: arr}, "required": [key]}


async def call_json(
    llm: Any, *, user_id: str, model_source: str, model_ref: str,
    messages: list[dict[str, str]], max_tokens: int,
    job_meta: dict[str, Any],
    schema: dict[str, Any] | None = None,
    schema_name: str = "result",
    temperature: float = 0.4,
    trace_id: str | None = None,
    cancel_check: Any = None,
    seed: int | None = None,
    no_think: bool = True,
) -> str | None:
    """One call. Returns the raw content, or ``None`` when the job did not complete.

    `None` is deliberately NOT an exception: every caller here already degrades on a failed job
    (the planning passes are individually skippable), and raising would convert a degradation into
    an outage. `LLMError` is likewise caught and logged — the caller sees `None` either way, which
    is the one thing it already knew how to handle.
    """
    def _input(fmt: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "messages": messages, "response_format": fmt,
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if no_think:
            body.update(_no_think())
        if seed is not None:
            body["seed"] = seed
        return body

    async def _run(fmt: dict[str, Any]):
        return await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input=_input(fmt), job_meta=job_meta, trace_id=trace_id, cancel_check=cancel_check,
        )

    job = None
    if schema is not None:
        try:
            job = await _run(json_format(schema_name, schema))
        except LLMError as exc:
            # A provider that does not accept the schema must not lose the call. Distinguishing a
            # schema rejection from a real outage is not worth a message-shape heuristic — retrying
            # once WITHOUT the constraint covers both, and a genuine outage fails again immediately.
            logger.info("call_json[%s]: schema rejected or call failed (%s) — retrying free-form",
                        job_meta.get("extractor") or schema_name, exc)
            job = None
    if job is None:
        try:
            job = await _run({"type": "text"})
        except LLMError as exc:
            logger.warning("call_json[%s]: LLM error: %s",
                           job_meta.get("extractor") or schema_name, exc)
            return None

    if getattr(job, "status", None) != "completed":
        logger.info("call_json[%s]: job status=%s → degraded",
                    job_meta.get("extractor") or schema_name, getattr(job, "status", None))
        return None
    content = extract_judge_content(job.result)
    return content if content and content.strip() else None
