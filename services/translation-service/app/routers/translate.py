"""Synchronous text translation endpoint for chunk-level translation."""
import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg

logger = logging.getLogger(__name__)

from ..auth import mint_user_jwt
from ..config import (
    settings as app_settings,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_USER_PROMPT_TPL,
)
from ..deps import get_current_user, get_db
from ..models import TranslateTextRequest, TranslateTextResponse

router = APIRouter(prefix="/v1/translation", tags=["translate"])


@router.post("/translate-text", response_model=TranslateTextResponse)
async def translate_text(
    body: TranslateTextRequest,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
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

    # Safe format_map that leaves unknown {placeholders} unchanged
    class _SafeMap(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    fmt = _SafeMap(
        source_language=source_language,
        target_language=target_language,
        chapter_text=body.text,
        # Also support language code variants that some prompts use
        source_lang=source_language,
        target_lang=target_language,
        source_code=source_language,
        target_code=target_language,
    )

    user_msg = user_prompt_tpl.format_map(fmt)
    system_msg = system_prompt.format_map(fmt)

    # Mint JWT for provider-registry call
    token = mint_user_jwt(user_id, app_settings.jwt_secret, ttl_seconds=120)
    invoke_timeout = prefs["invoke_timeout_secs"] if prefs else 120

    async with httpx.AsyncClient(timeout=invoke_timeout) as client:
        try:
            r = await client.post(
                f"{app_settings.provider_registry_service_url}/v1/model-registry/invoke",
                json={
                    "model_source": model_source,
                    "model_ref": str(model_ref),
                    "input": {
                        "messages": [
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_msg},
                        ]
                    },
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Translation provider timed out")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Provider connection error: {exc}")

    if r.status_code == 402:
        raise HTTPException(status_code=402, detail="Quota and credits exhausted")
    if not r.is_success:
        raise HTTPException(
            status_code=502,
            detail=f"Provider invoke failed ({r.status_code})",
        )

    try:
        resp = r.json()
        from ..workers.content_extractor import extract_content
        translated_text = extract_content(resp["output"])
    except (ValueError, KeyError, TypeError) as exc:
        logger.error("Malformed provider response: %s", exc)
        raise HTTPException(status_code=502, detail="Malformed response from translation provider")
    usage = resp.get("usage") or {}

    return TranslateTextResponse(
        translated_text=translated_text,
        source_language=source_language,
        target_language=target_language,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
    )
