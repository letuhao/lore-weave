"""V3 orchestrator — M0 skeleton.

For M0 the v3 entrypoints delegate to the V2 implementations so the
``pipeline_version='v3'`` path is exercised end-to-end with byte-identical output.
M1 replaces the block delegation with the Verifier rule-tier; M2 adds the
Translator→Verifier→Corrector loop. See
docs/specs/2026-06-06-translation-pipeline-v3-multi-agent.md (§12.4).

Imports of the V2 functions are intentionally lazy (inside each call) so the path
stays patchable in tests and avoids an import cycle with session_translator.
"""
from __future__ import annotations

from uuid import UUID


async def translate_chapter_blocks_v3(
    blocks: list[dict],
    source_lang: str,
    msg: dict,
    pool,
    chapter_translation_id: UUID,
    *,
    llm_client,
    context_window: int = 8192,
):
    """M0 parity: delegate the block pipeline to V2 unchanged."""
    from ..session_translator import translate_chapter_blocks
    return await translate_chapter_blocks(
        blocks, source_lang, msg, pool, chapter_translation_id,
        llm_client=llm_client, context_window=context_window,
    )


async def translate_chapter_v3(
    chapter_text: str,
    source_lang: str,
    msg: dict,
    pool,
    chapter_translation_id: UUID,
    *,
    llm_client,
    context_window: int = 8192,
):
    """M0 parity: delegate the text pipeline to V2 unchanged."""
    from ..session_translator import translate_chapter
    return await translate_chapter(
        chapter_text, source_lang, msg, pool, chapter_translation_id,
        llm_client=llm_client, context_window=context_window,
    )
