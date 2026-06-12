"""V3 Corrector — rule-triggered targeted re-translation (M1b).

When the deterministic rule-tier flags HIGH-severity issues on a block, re-translate
ONLY that block once with a correction hint. Single pass, **rule-triggered** — the
LLM-verifier + multi-round loop is M2. Best-effort: a correction failure keeps the
original draft (it must never fail an already-successful chapter).
"""
from __future__ import annotations

import logging

from ..session_translator import _parse_sdk_response, _lang_name, _SafeFormatMap

log = logging.getLogger(__name__)

_CORRECTION_SYSTEM = (
    "You are a professional {source_lang} to {target_lang} translator fixing a flawed "
    "translation of ONE text block. Output ONLY the corrected {target_lang} translation "
    "of the source — no labels, no markers, no commentary."
)


def _build_messages(source_text, draft_text, issues, source_lang, target_lang, glossary_block):
    problems = "\n".join(f"- {i.detail}" for i in issues)
    system = _CORRECTION_SYSTEM.format_map(_SafeFormatMap({
        "source_lang": _lang_name(source_lang),
        "target_lang": _lang_name(target_lang),
    }))
    if glossary_block:
        system += "\n\n" + glossary_block + "\n\nUse the EXACT glossary translations above."
    from .romanization import romanization_instruction
    rom = romanization_instruction(source_lang, target_lang)
    if rom:
        system += "\n\n" + rom
    user = (
        f"SOURCE:\n{source_text}\n\n"
        f"PREVIOUS (flawed) TRANSLATION:\n{draft_text}\n\n"
        f"PROBLEMS TO FIX:\n{problems}\n\n"
        f"Produce ONLY the corrected {_lang_name(target_lang)} translation of the SOURCE."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def correct_high_severity_blocks(
    flagged_indices,
    source_texts: dict[int, str],
    draft_texts: dict[int, str],
    report,
    source_lang: str,
    target_lang: str,
    msg: dict,
    glossary_block: str,
    *,
    llm_client,
) -> dict[int, str]:
    """Re-translate each flagged block once. Returns {idx: corrected_text} for the
    blocks that produced a non-empty result; omits blocks whose correction failed."""
    corrected: dict[int, str] = {}
    for idx in sorted(flagged_indices):
        if idx not in source_texts:
            continue
        issues = [i for i in report.issues if i.block_index == idx and i.severity == "high"]
        if not issues:
            continue
        messages = _build_messages(
            source_texts[idx], draft_texts.get(idx, ""), issues,
            source_lang, target_lang, glossary_block,
        )
        try:
            job = await llm_client.submit_and_wait(
                user_id=msg["user_id"],
                operation="translation",
                model_source=msg["model_source"],
                model_ref=str(msg["model_ref"]),
                input={
                    "messages": messages,
                    # Suppress hidden thinking on reasoning models (parity with the
                    # V2 translator) so reasoning tokens don't burn the output budget.
                    "reasoning_effort": "none",
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                chunking=None,
                job_meta={"corrector_block": idx},
                transient_retry_budget=1,
            )
            if job.status == "completed":
                text, _, _ = _parse_sdk_response(job)
                if text and text.strip():
                    corrected[idx] = text.strip()
        except Exception as exc:  # best-effort — keep the original draft on failure
            log.warning("v3 corrector: block %s re-translate failed (non-fatal): %s", idx, exc)
    return corrected
