"""
F2-app — the canonical FOLD pass (temporal-knowledge §12.1).

The glossary writeback flags an entity's narrative canonical `dirty` whenever its facts
change (append / retract). After an extraction job finishes, this pass:

  1. fetches the dirty (non-quarantined) entities + their bounded CURRENT facts from
     glossary-service (the fold input — INV-FACTS: facts are the SSOT),
  2. folds each entity's facts into ONE bounded canonical description via a single LLM call
     (through the SAME provider-registry path extraction used — the job's `llm_client` +
     `model_ref`; no new provider plumbing, no hardcoded model), and
  3. writes the snapshot back (compare-and-clear on the coverage fingerprint; a failure
     reports backoff so a poison entity can't wedge the loop — B4).

It is BEST-EFFORT and decoupled from the job's success (the extraction already committed).
The canonical stays in the SOURCE language (never silently translated). This mirrors the
#26/#7 `resummarize` pass — the difference is the input is the bi-temporal FACTS (so the
canonical is regenerable from the SSOT and time-travel-ready), not the flat raw-item set.
"""
from __future__ import annotations

import asyncio
import logging

from loreweave_llm.reasoning import ReasoningDirective, reasoning_fields

from ..llm_client import LLMClient
from .glossary_client import fetch_fold_dirty, post_fold_snapshot

log = logging.getLogger(__name__)

_FOLD_MAX_CONCURRENCY = 8
# The canonical card is bounded (the glossary ~2000-rune cap); keep the output tight.
_FOLD_OUTPUT_TOKENS = 512


def _build_messages(entity_name: str, facts: list[dict], source_language: str) -> list[dict]:
    """One fold prompt: synthesize the entity's current facts into a single bounded canonical
    description, in the source language, emitting ONLY the description (no preamble/labels)."""
    lang = source_language or "the source language"
    system = (
        "You synthesize the CURRENT facts about ONE entity in a novel into a SINGLE concise, "
        "coherent canonical description (a few sentences). Use every distinct fact; do not "
        "invent anything not in the facts; prefer the most specific wording. Write in "
        f"{lang} (do NOT translate). Output ONLY the description text — no preamble, no "
        "bullet list, no labels, no quotes."
    )
    fact_block = "\n".join(f"- {f.get('attr')}: {f.get('value')}" for f in facts if f.get("value"))
    user = (
        f"Entity: {entity_name or '(unnamed)'}\n"
        f"Current facts:\n{fact_block}\n\n"
        "Canonical description:"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def _fold_one(
    item: dict, *, book_id: str, owner_user_id: str, model_source: str,
    model_ref: str | None, fallback_language: str, llm_client: LLMClient,
) -> bool:
    """Fold + write back one entity. Never raises (best-effort); reports backoff on failure."""
    entity_id = item.get("entity_id")
    facts = [f for f in (item.get("facts") or []) if f.get("value")]
    fingerprint = item.get("fold_fingerprint", "")
    head_ordinal = int(item.get("head_ordinal") or 0)
    if not entity_id or not facts:
        return False

    messages = _build_messages(item.get("entity_name", ""), facts, fallback_language)
    try:
        sdk_job = await llm_client.submit_and_wait(
            user_id=str(owner_user_id),
            operation="chat",
            model_source=model_source,
            model_ref=str(model_ref),
            input={
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": _FOLD_OUTPUT_TOKENS,
                # Synthesis, not reasoning — disable hidden thinking (a reasoning model would
                # otherwise spend the whole budget on reasoning_content → empty output).
                **reasoning_fields(ReasoningDirective(effort="none", passthrough=False, source="user")),
            },
            chunking=None,
            job_meta={
                "usage_purpose": "glossary_canonical_fold",
                "extractor": "glossary",
                "entity_id": str(entity_id),
            },
            transient_retry_budget=1,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort
        log.warning("fold: LLM call failed for entity=%s: %s", entity_id, exc)
        await post_fold_snapshot(book_id, entity_id, content="", as_of_ordinal=head_ordinal,
                                 fold_fingerprint=fingerprint, failed=True)
        return False

    text = ""
    if sdk_job.status == "completed":
        msgs = (sdk_job.result or {}).get("messages") or []
        if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
            text = (msgs[0].get("content") or "").strip()
    if not text:
        log.warning("fold: empty synthesis for entity=%s — backoff", entity_id)
        await post_fold_snapshot(book_id, entity_id, content="", as_of_ordinal=head_ordinal,
                                 fold_fingerprint=fingerprint, failed=True)
        return False

    resp = await post_fold_snapshot(book_id, entity_id, content=text, as_of_ordinal=head_ordinal,
                                    fold_fingerprint=fingerprint)
    return resp is not None


async def run_fold_pass(
    *, book_id: str, owner_user_id: str, model_source: str, model_ref: str | None,
    source_language: str, llm_client: LLMClient,
) -> dict:
    """Run the end-of-job canonical fold for a book. Best-effort throughout — returns
    {dirty, folded, failed}; logs and swallows all errors so a fold problem never propagates
    into the extraction job's terminal state."""
    try:
        items = await fetch_fold_dirty(book_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("fold: dirty fetch failed for book=%s: %s", book_id, exc)
        return {"dirty": 0, "folded": 0, "failed": 0}
    if not items:
        return {"dirty": 0, "folded": 0, "failed": 0}

    log.info("fold: book=%s — %d dirty entit(y/ies)", book_id, len(items))
    sem = asyncio.Semaphore(max(1, _FOLD_MAX_CONCURRENCY))

    async def _guarded(it: dict) -> bool:
        async with sem:
            return await _fold_one(
                it, book_id=book_id, owner_user_id=owner_user_id,
                model_source=model_source, model_ref=model_ref,
                fallback_language=source_language, llm_client=llm_client,
            )

    results = await asyncio.gather(*(_guarded(it) for it in items), return_exceptions=True)
    folded = sum(1 for r in results if r is True)
    failed = len(results) - folded
    log.info("fold: book=%s — folded=%d failed=%d", book_id, folded, failed)
    return {"dirty": len(items), "folded": folded, "failed": failed}
