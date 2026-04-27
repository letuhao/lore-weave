"""Synchronous text translation endpoint for chunk-level translation."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg

from loreweave_llm.errors import (
    LLMAuthFailed,
    LLMDecodeError,
    LLMError,
    LLMInvalidRequest,
    LLMModelNotFound,
    LLMQuotaExceeded,
    LLMStreamNotSupported,
    LLMTransientRetryNeededError,
)

logger = logging.getLogger(__name__)

from ..config import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_USER_PROMPT_TPL,
)
from ..deps import get_current_user, get_db
from ..llm_client import LLMClient, get_llm_client
from ..models import TranslateTextRequest, TranslateTextResponse
from ..workers.session_translator import _parse_sdk_response

router = APIRouter(prefix="/v1/translation", tags=["translate"])


@router.post("/translate-text", response_model=TranslateTextResponse)
async def translate_text(
    body: TranslateTextRequest,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
) -> TranslateTextResponse:
    # Load user preferences for model config
    prefs = await db.fetchrow(
        "SELECT * FROM user_translation_preferences WHERE user_id = $1",
        UUID(user_id),
    )

    if prefs:
        model_source = prefs["model_source"]
        model_ref = prefs["model_ref"]
        system_prompt = prefs["system_prompt"]
        user_prompt_tpl = prefs["user_prompt_tpl"]
        target_language = body.target_language or prefs["target_language"]
    else:
        model_source = None
        model_ref = None
        system_prompt = DEFAULT_SYSTEM_PROMPT
        user_prompt_tpl = DEFAULT_USER_PROMPT_TPL
        target_language = body.target_language or "en"

    if not model_ref:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "TRANSL_NO_MODEL_CONFIGURED",
                "message": "No model configured. Set a model in Translation Settings before translating.",
            },
        )

    source_language = body.source_language if body.source_language != "auto" else "auto-detect"

    # ── Block mode (Phase 8F) ──────────────────────────────────────────────
    if body.blocks and len(body.blocks) > 0:
        from ..workers.block_classifier import rebuild_block
        from ..workers.block_batcher import build_batch_plan, parse_translated_blocks

        plan = build_batch_plan(body.blocks, context_window_tokens=8192)
        if not plan.batches:
            return TranslateTextResponse(
                translated_blocks=body.blocks,
                translated_body_format="json",
                source_language=source_language,
                target_language=target_language,
            )

        from ..workers.session_translator import _BLOCK_SYSTEM_PROMPT, _SafeFormatMap, _lang_name
        sys_content = _BLOCK_SYSTEM_PROMPT.format_map(_SafeFormatMap({
            "source_lang": _lang_name(source_language),
            "source_code": source_language,
            "target_lang": _lang_name(target_language),
            "target_code": target_language,
        }))

        translated_texts: dict[int, str] = {}
        total_in = 0
        total_out = 0

        # Phase 4c-γ: SDK call replaces /v1/model-registry/invoke.
        # Best-effort per batch — any SDK error skips the batch (matches
        # legacy `continue` on httpx.TimeoutException / RequestError);
        # missing blocks fall back to original text in the result loop.
        for batch in plan.batches:
            combined = batch.combined_text()
            try:
                sdk_job = await llm_client.submit_and_wait(
                    user_id=user_id,
                    operation="translation",
                    model_source=model_source,
                    model_ref=str(model_ref),
                    input={"messages": [
                        {"role": "system", "content": sys_content},
                        {"role": "user", "content": f"Translate the following blocks from {_lang_name(source_language)} to {_lang_name(target_language)}:\n\n{combined}"},
                    ]},
                    chunking=None,
                    job_meta={"endpoint": "translate-text-blocks"},
                    transient_retry_budget=1,
                )
            except (LLMTransientRetryNeededError, LLMError):
                continue
            if sdk_job.status != "completed":
                continue
            response_text, in_tok, out_tok = _parse_sdk_response(sdk_job)
            total_in += in_tok
            total_out += out_tok
            parsed = parse_translated_blocks(response_text, batch.block_indices)
            translated_texts.update(parsed)

        result_blocks = []
        for entry in plan.all_entries:
            if entry.index in translated_texts:
                result_blocks.append(rebuild_block(entry.block, translated_texts[entry.index]))
            else:
                result_blocks.append(entry.block)

        return TranslateTextResponse(
            translated_blocks=result_blocks,
            translated_body_format="json",
            source_language=source_language,
            target_language=target_language,
            input_tokens=total_in or None,
            output_tokens=total_out or None,
        )

    # ── Text mode (legacy) ─────────────────────────────────────────────────
    if not body.text:
        raise HTTPException(status_code=422, detail="Either text or blocks is required")

    # Safe format_map that leaves unknown {placeholders} unchanged
    class _SafeMap(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    fmt = _SafeMap(
        source_language=source_language,
        target_language=target_language,
        chapter_text=body.text,
        source_lang=source_language,
        target_lang=target_language,
        source_code=source_language,
        target_code=target_language,
    )

    user_msg = user_prompt_tpl.format_map(fmt)
    system_msg = system_prompt.format_map(fmt)

    # Phase 4c-γ: SDK call replaces /v1/model-registry/invoke. Map
    # SDK exceptions to the same HTTP status codes the legacy path
    # returned (504 timeout, 502 transport, 402 quota, 502 model not
    # found). HIGH#1 from cycle 11 reinforced: catch permanent SDK
    # subclasses BEFORE the generic LLMError so misconfigured BYOK
    # surfaces correctly to the caller.
    try:
        sdk_job = await llm_client.submit_and_wait(
            user_id=user_id,
            operation="translation",
            model_source=model_source,
            model_ref=str(model_ref),
            input={
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
            },
            chunking=None,
            job_meta={"endpoint": "translate-text"},
            transient_retry_budget=1,
        )
    except LLMTransientRetryNeededError:
        raise HTTPException(status_code=504, detail="Translation provider timed out")
    except LLMQuotaExceeded:
        raise HTTPException(status_code=402, detail="Quota and credits exhausted")
    except LLMModelNotFound as exc:
        raise HTTPException(status_code=502, detail=f"Model not found: {exc}")
    except (LLMAuthFailed, LLMInvalidRequest, LLMDecodeError, LLMStreamNotSupported) as exc:
        raise HTTPException(status_code=502, detail=f"Provider invoke failed: {exc}")
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Provider connection error: {exc}")

    if sdk_job.status != "completed":
        err_code = sdk_job.error.code if sdk_job.error else "LLM_UNKNOWN_ERROR"
        if err_code == "LLM_QUOTA_EXCEEDED":
            raise HTTPException(status_code=402, detail="Quota and credits exhausted")
        raise HTTPException(
            status_code=502,
            detail=f"Provider invoke failed ({err_code})",
        )

    translated_text, in_tok, out_tok = _parse_sdk_response(sdk_job)
    if not translated_text:
        logger.error("Empty content from translation provider")
        raise HTTPException(status_code=502, detail="Malformed response from translation provider")
    usage = {"input_tokens": in_tok, "output_tokens": out_tok}

    return TranslateTextResponse(
        translated_text=translated_text,
        source_language=source_language,
        target_language=target_language,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
    )
