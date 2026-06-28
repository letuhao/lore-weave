"""
#26/#7 — glossary `summarize` (merge-rewrite) mode: the end-of-extraction-job LLM pass.

The glossary writeback flags `canonical_dirty` on a summarize attribute whenever its raw
item set changes (each chapter appends near-duplicate phrasings of the same fact). After an
extraction job finishes, this pass:

  1. fetches the dirty (entity, attribute) work items from glossary-service,
  2. rewrites each one's accumulated RAW mentions into ONE deduped canonical value via a
     single LLM call (through the SAME provider-registry path the extraction used — the
     job's `llm_client` + `model_ref`; no new provider plumbing, no hardcoded model), and
  3. writes the canonical value back (compare-and-clear on the dirty flag).

It is BEST-EFFORT and fully decoupled from the job's success: the extraction already
committed, so a resummarize failure is logged and skipped, never fails the job. The LLM
call runs OUT of any DB transaction. Summaries stay in the SOURCE language (the same rule
as event/KG summaries — never silently translated to English).
"""
from __future__ import annotations

import asyncio
import logging

from ..llm_client import LLMClient
from .glossary_client import fetch_canonical_dirty, post_canonical

log = logging.getLogger(__name__)

# Bounded fan-out over the per-job dirty set (mirror the extraction concurrency ceiling so a
# many-entity job can't stampede the provider/GPU). 1 ⇒ sequential.
_RESUMMARIZE_MAX_CONCURRENCY = 8

# A merged description is short; keep the output budget tight so the model stays concise and
# the canonical value respects the glossary 2000-rune cap.
_RESUMMARIZE_OUTPUT_TOKENS = 512


def _build_messages(entity_name: str, attr_label: str, raw_values: list[str],
                    source_language: str) -> list[dict]:
    """One rewrite prompt: merge the raw mentions into a single deduped canonical value,
    in the source language, emitting ONLY the merged text (no preamble/list/quotes)."""
    lang = source_language or "the source language"
    system = (
        "You merge raw notes about ONE entity attribute, extracted from different chapters "
        "of a novel, into a SINGLE concise, de-duplicated canonical description. Keep every "
        "distinct fact; collapse near-duplicate phrasings of the same fact; preserve the most "
        f"specific wording. Write in {lang} (do NOT translate). Output ONLY the merged "
        "description text — no preamble, no bullet list, no quotes, no labels."
    )
    raw_block = "\n".join(f"- {v}" for v in raw_values)
    user = (
        f"Entity: {entity_name or '(unnamed)'}\n"
        f"Attribute: {attr_label}\n"
        f"Raw mentions:\n{raw_block}\n\n"
        f"Merged canonical {attr_label}:"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def _resummarize_one(
    item: dict, *, book_id: str, owner_user_id: str, model_source: str,
    model_ref: str | None, fallback_language: str, llm_client: LLMClient,
) -> bool:
    """Rewrite + write back one dirty item. Returns True on a successful write. Never raises
    (best-effort): any LLM/parse/post failure is logged and counted as a miss."""
    entity_id = item.get("entity_id")
    attr_code = item.get("attr_code")
    raw_values = [str(v) for v in (item.get("raw_values") or []) if str(v).strip()]
    if not entity_id or not attr_code or not raw_values:
        return False
    # A single raw mention needs no merge — promote it verbatim as the canonical value (saves
    # an LLM call) and clear dirty with its fingerprint.
    if len(raw_values) == 1:
        resp = await post_canonical(
            book_id, entity_id, attr_code, raw_values[0],
            raw_fingerprint=item.get("raw_fingerprint", ""),
        )
        return resp is not None

    messages = _build_messages(
        item.get("entity_name", ""), item.get("attr_label", attr_code),
        raw_values, item.get("source_language") or fallback_language,
    )
    try:
        sdk_job = await llm_client.submit_and_wait(
            user_id=str(owner_user_id),
            # operation="chat" routes to the chatAggregator (chat-shaped result we parse).
            # The Usage-GUI billing label rides job_meta.usage_purpose (bug #24).
            operation="chat",
            model_source=model_source,
            model_ref=str(model_ref),
            input={
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": _RESUMMARIZE_OUTPUT_TOKENS,
            },
            chunking=None,
            job_meta={
                "usage_purpose": "glossary_resummarize",
                "extractor": "glossary",
                "entity_id": str(entity_id),
                "attr_code": str(attr_code),
            },
            transient_retry_budget=1,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort: a resummarize must never fail the job
        log.warning("resummarize: LLM call failed for entity=%s attr=%s: %s",
                    entity_id, attr_code, exc)
        return False

    if sdk_job.status != "completed":
        log.warning("resummarize: LLM job ended status=%s for entity=%s attr=%s",
                    sdk_job.status, entity_id, attr_code)
        return False

    result = sdk_job.result or {}
    messages_out = result.get("messages") or []
    text = ""
    if isinstance(messages_out, list) and messages_out and isinstance(messages_out[0], dict):
        text = (messages_out[0].get("content") or "").strip()
    if not text:
        log.warning("resummarize: empty synthesis for entity=%s attr=%s — skipping",
                    entity_id, attr_code)
        return False

    resp = await post_canonical(
        book_id, entity_id, attr_code, text,
        raw_fingerprint=item.get("raw_fingerprint", ""),
    )
    return resp is not None


async def run_resummarize_pass(
    *, book_id: str, owner_user_id: str, model_source: str, model_ref: str | None,
    source_language: str, llm_client: LLMClient,
) -> dict:
    """Run the end-of-job canonical resynthesis for a book. Best-effort throughout — returns
    a summary {dirty, synthesized, failed}; logs and swallows all errors so a resummarize
    problem never propagates into the extraction job's terminal state."""
    try:
        items = await fetch_canonical_dirty(book_id)
    except Exception as exc:  # noqa: BLE001 — defensive; fetch already swallows, belt + braces
        log.warning("resummarize: dirty fetch failed for book=%s: %s", book_id, exc)
        return {"dirty": 0, "synthesized": 0, "failed": 0}
    if not items:
        return {"dirty": 0, "synthesized": 0, "failed": 0}

    log.info("resummarize: book=%s — %d dirty summarize attribute(s)", book_id, len(items))
    sem = asyncio.Semaphore(max(1, _RESUMMARIZE_MAX_CONCURRENCY))

    async def _guarded(it: dict) -> bool:
        async with sem:
            return await _resummarize_one(
                it, book_id=book_id, owner_user_id=owner_user_id,
                model_source=model_source, model_ref=model_ref,
                fallback_language=source_language, llm_client=llm_client,
            )

    results = await asyncio.gather(*(_guarded(it) for it in items), return_exceptions=True)
    synthesized = sum(1 for r in results if r is True)
    failed = len(results) - synthesized
    log.info("resummarize: book=%s — synthesized=%d failed=%d", book_id, synthesized, failed)
    return {"dirty": len(items), "synthesized": synthesized, "failed": failed}
